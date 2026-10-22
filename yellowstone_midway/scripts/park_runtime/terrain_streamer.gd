extends Node3D
## Main-thread coordinator; immutable source pages, async CPU builds, budgeted commits.
signal tile_committed(key: String)
signal tile_retiring(key: String)
signal stream_error(key: String, message: String)

const Job = preload("res://scripts/park_runtime/terrain_job.gd")
const Tile = preload("res://scripts/park_runtime/tile_visual.gd")
const Planner = preload("res://scripts/park_runtime/demand_planner.gd")
const FeatureSource = preload("res://scripts/park_runtime/feature_source.gd")

@export var max_inflight: int = 2
@export var max_pending: int = 256
@export var resident_limit_mib: float = 128.0
@export var commit_budget_ms: float = 1.5
@export var max_commits_per_frame: int = 1
@export var max_collision_commits_per_tick: int = 1
@export var replan_interval_s: float = 0.2
@export var retirement_delay_s: float = 2.0

var frame: RefCounted
var camera: Camera3D
var velocity := Vector3.ZERO
var material: Material
var roots: Array = []
var resident: Dictionary = {}
var planner = Planner.new()
var stats: Dictionary = {}
var _base_path: String
var _revision: String
var _inflight: Dictionary = {}
var _ready: Array[Dictionary] = []
var _requests: Dictionary = {}
var _wanted_leaves: Array[String] = []
var _collision_wanted: Dictionary = {}
var _collisions: Dictionary = {}
var _failures: Dictionary = {}
var _features: Dictionary = {}
var _groups: Dictionary = {}
var _water_nodes: Dictionary = {}
var _water_materials: Dictionary = {}
var _route_materials: Dictionary = {}
var _elapsed: float = 0.0
var _now: float = 0.0
var _bytes: int = 0
var _physics_tick: int = 0
var _configured: bool = false

func configure(catalog_path: String, world_frame: RefCounted, observer: Camera3D, shared_material: Material = null) -> bool:
    assert(not _configured, "Create a new streamer for a new dataset; do not mix source revisions")
    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(catalog_path))
    if not parsed is Dictionary or parsed.get("schema") != "yellowstone.terrain_tiles.v1":
        push_error("Missing or invalid terrain catalog")
        return false
    roots = parsed.get("roots",[])
    if roots.is_empty() or roots.size() > 4096:
        push_error("A bootstrap catalog requires 1..4096 root descriptors")
        return false
    for root: Dictionary in roots:
        if not root.has_all(["key","page","lod","mesh_cells","size_m","origin_x_m","origin_z_m","min_y_m","max_y_m","error_m"]):
            return false
        if int(root.lod) < 0 or int(root.lod) > 24 or float(root.size_m) <= 0.0:
            return false
    if max_inflight < 1 or max_inflight > 16 or max_pending < 1 or resident_limit_mib <= 0.0 or commit_budget_ms <= 0.0:
        push_error("Invalid streaming budget configuration")
        return false
    var bootstrap_reserve: int = 0
    for root: Dictionary in roots:
        bootstrap_reserve += (int(root.mesh_cells)+1)*(int(root.mesh_cells)+1)*128
    if bootstrap_reserve > int(resident_limit_mib*1048576.0*0.75):
        push_error("Budget cannot hold bootstrap cover plus preparation/safety headroom; use coarser roots or a larger budget")
        return false
    frame = world_frame
    frame.configure(parsed.frame)
    camera = observer
    _base_path = catalog_path.get_base_dir()
    _revision = str(parsed.dataset_revision)
    if parsed.has("features"):
        _features = FeatureSource.load_index(_base_path, parsed.features)
        if _features.has("error"):
            push_error(str(_features.error))
            _features = {}
            return false
    material = shared_material
    if material == null:
        var fallback := StandardMaterial3D.new()
        fallback.albedo_color = Color(0.34,0.43,0.30)
        fallback.roughness = 0.94
        material = fallback
    frame.rebased.connect(_on_rebased)
    _configured = true
    _replan()
    return true

func _replan() -> void:
    var started: int = Time.get_ticks_usec()
    var demand: Dictionary = planner.plan(roots,resident,frame,camera,velocity)
    _requests = demand.requests
    _wanted_leaves.assign(demand.leaves)
    _collision_wanted = demand.collision
    for key: String in _inflight:
        if not _requests.has(key):
            _inflight[key].cancel()
    for key: String in resident:
        resident[key].visible = _wanted_leaves.has(key)
        if _requests.has(key):
            resident[key].last_used_s = _now
    stats["plan_ms"] = float(Time.get_ticks_usec()-started)/1000.0
    stats["planner_visits"] = demand.visits
    stats["safety_radius_m"] = demand.safety_radius_m

func _process(delta: float) -> void:
    if not _configured:
        return
    _elapsed += delta
    _now += delta
    if _elapsed >= replan_interval_s:
        _elapsed = 0.0
        _replan()
    _collect_completed()
    _commit_ready()
    _retire()
    _dispatch()
    stats.merge({"resident_tiles":resident.size(),"visible_tiles":_wanted_leaves.size(),
        "inflight":_inflight.size(),"ready":_ready.size(),"resident_estimate_mib":float(_bytes)/1048576.0,
        "collision_tiles":_collisions.size(),"failures":_failures.size()},true)

func _dispatch() -> void:
    var pending: Array = _requests.values()
    pending.sort_custom(func(a: Dictionary,b: Dictionary)->bool: return float(a.priority)>float(b.priority))
    var visited: int = 0
    for request: Dictionary in pending:
        if _inflight.size()+_ready.size() >= max_inflight or visited >= max_pending:
            break
        visited += 1
        var d: Dictionary = request.tile
        var key: String = str(d.key)
        if resident.has(key) or _inflight.has(key) or _failures.has(key):
            continue
        var already_ready: bool = false
        for data: Dictionary in _ready:
            if data.key == key:
                already_ready = true
                break
        if already_ready:
            continue
        # Reserve a conservative maximum for the candidate, including temporary copies.
        var estimated: int = (int(d.mesh_cells)+1)*(int(d.mesh_cells)+1)*128
        if _bytes + estimated > int(resident_limit_mib*1048576.0):
            stats["budget_pressure"] = true
            break
        var job = Job.new()
        job.configure(d,_base_path,_revision)
        if not _features.is_empty():
            job.configure_features(_features)
        job.task_id = WorkerThreadPool.add_task(job.run,false,"terrain " + key)
        _inflight[key] = job

func _collect_completed() -> void:
    for key: String in _inflight.keys():
        var job = _inflight[key]
        if not WorkerThreadPool.is_task_completed(job.task_id):
            continue
        WorkerThreadPool.wait_for_task_completion(job.task_id)
        _inflight.erase(key)
        if job.cancelled() or job.result.is_empty() or not _requests.has(key):
            continue
        var data: Dictionary = job.result
        if data.get("revision") != _revision:
            continue
        if data.has("error"):
            _failures[key] = str(data.error)
            stream_error.emit(key,str(data.error))
        else:
            _ready.append(data)

func _commit_ready() -> void:
    var started: int = Time.get_ticks_usec()
    var commits: int = 0
    while not _ready.is_empty() and commits < max_commits_per_frame:
        if float(Time.get_ticks_usec()-started)/1000.0 >= commit_budget_ms:
            break
        var data: Dictionary = _ready.pop_front()
        var key: String = str(data.key)
        if not _requests.has(key) or resident.has(key) or data.revision != _revision:
            continue
        if _bytes + int(data.bytes_estimate) > int(resident_limit_mib*1048576.0):
            stats["budget_pressure"] = true
            continue
        var tile = Tile.new()
        if not tile.install(data,material,frame):
            # The parent stays resident; the failure blocks retries until the pack changes.
            tile.free()
            _failures[key] = "Terrain surface build failed"
            stream_error.emit(key,"Terrain surface build failed")
            continue
        tile.last_used_s = _now
        add_child(tile)
        _commit_shoreline(tile,data)
        var water: Array = _commit_water(tile,data)
        _water_nodes[key] = water
        var routes: int = _commit_routes(tile,data)
        _groups[key] = {"pools":data.get("pools",[]),"routes":data.get("routes",[]),
            "shoreline":not data.get("shoreline_arrays",[]).is_empty(),
            "water_surfaces":water.size(),"route_pieces":routes}
        resident[key] = tile
        _bytes += tile.bytes_estimate
        commits += 1
        tile_committed.emit(key)
    stats["commit_ms"] = float(Time.get_ticks_usec()-started)/1000.0
    stats["commit_ms_max"] = maxf(float(stats.get("commit_ms_max", 0.0)), float(stats.commit_ms))
    if commits > 0:
        _replan()

func _retire() -> void:
    # One resource retirement per frame prevents a queue_free avalanche.
    for key: String in resident.keys():
        var tile = resident[key]
        if _requests.has(key) or _collisions.has(key) or _now-tile.last_used_s < retirement_delay_s:
            continue
        _bytes -= tile.bytes_estimate
        resident.erase(key)
        _groups.erase(key)
        tile_retiring.emit(key)
        _water_nodes.erase(key)
        tile.queue_free()
        return

func _physics_process(_delta: float) -> void:
    _physics_tick += 1
    if not _configured:
        return
    var count: int = 0
    for key: String in _collision_wanted:
        if count >= max_collision_commits_per_tick:
            break
        if _collisions.has(key) or not resident.has(key) or not _groups.has(key):
            continue
        var tile = resident[key]
        if int(tile.descriptor.lod) != 0:
            continue
        var cells: int = int(tile.descriptor.mesh_cells)
        var spacing: float = float(tile.descriptor.size_m)/cells
        var shape := HeightMapShape3D.new()
        shape.map_width = cells+1
        shape.map_depth = cells+1
        shape.map_data = tile.heights
        var body := StaticBody3D.new()
        var collider := CollisionShape3D.new()
        collider.shape = shape
        collider.scale = Vector3(spacing,1.0,spacing)
        body.add_child(collider)
        add_child(body)
        _collisions[key] = {"body":body,"descriptor":tile.descriptor,"ready_tick":_physics_tick+1}
        _place_body(_collisions[key])
        count += 1
    for key: String in _collisions.keys():
        if not _collision_wanted.has(key):
            _collisions[key].body.queue_free()
            _collisions.erase(key)
            break

## The shoreline surface joins the tile in the same commit; terrain and water stay separate meshes.
func _commit_shoreline(tile: Node3D, data: Dictionary) -> void:
    var shoreline: Array = data.get("shoreline_arrays",[])
    if shoreline.is_empty():
        return
    var generated := ArrayMesh.new()
    generated.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,shoreline)
    var instance := MeshInstance3D.new()
    instance.name = "Shoreline"
    instance.mesh = generated
    instance.material_override = material
    instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
    tile.add_child(instance)

## Feature group of a resident tile: pool ids, route chunks and whether a shoreline surface exists.
func tile_group(key: String) -> Dictionary:
    return _groups.get(key,{})

## Feature page index loaded at configure; empty when the catalog carries no features.
func feature_source() -> Dictionary:
    return _features

## Water surface nodes committed with a resident tile; empty for dry or absent tiles.
func tile_water_nodes(key: String) -> Array:
    return _water_nodes.get(key,[])

## Pool and river surfaces join the tile commit under the baked water material contract.
func _commit_water(tile: Node3D, data: Dictionary) -> Array:
    var nodes: Array = []
    for surface: Dictionary in data.get("water_surfaces",[]):
        var arrays: Array = surface.arrays
        if arrays.is_empty():
            continue
        var generated := ArrayMesh.new()
        generated.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
        generated.surface_set_material(0,_water_material(surface))
        var instance := MeshInstance3D.new()
        instance.name = "Water_" + str(surface.id)
        instance.mesh = generated
        instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
        if bool(surface.get("thermal",false)) and str(surface.id).begins_with("pool_"):
            instance.add_to_group("thermal_surfaces",true)
            instance.set_meta("feature_name",str(surface.get("name","")))
        if not str(surface.id).begins_with("pool_"):
            instance.add_to_group("river_surfaces",true)
            instance.set_meta("river_name",str(surface.get("name","")))
            instance.set_meta("sample_z",float(surface.get("sample_z",0.0)))
        tile.add_child(instance)
        nodes.append(instance)
    return nodes

## Route ribbons, decks, supports and rails join the leaf tile commit with baked materials.
func _commit_routes(tile: Node3D, data: Dictionary) -> int:
    var committed: int = 0
    for piece: Dictionary in data.get("route_pieces",[]):
        var arrays: Array = piece.arrays
        if arrays.is_empty():
            continue
        var generated := ArrayMesh.new()
        generated.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
        generated.surface_set_material(0,_route_material(str(piece.mat),float(piece.get("width_m",0.0))))
        var instance := MeshInstance3D.new()
        instance.name = "Route_" + str(piece.get("name","piece")) + "_" + str(piece.piece)
        instance.mesh = generated
        for meta_key: String in piece.get("meta",{}):
            instance.set_meta(meta_key,piece.meta[meta_key])
        tile.add_child(instance)
        if bool(piece.get("collision",false)):
            var shape: Shape3D = generated.create_trimesh_shape()
            if shape != null:
                var body := StaticBody3D.new()
                body.name = "RouteCollision"
                var collider := CollisionShape3D.new()
                collider.shape = shape
                body.add_child(collider)
                instance.add_child(body)
        committed += 1
    return committed

## One material per water feature; uniform values match the baked assignments.
func _water_material(surface: Dictionary) -> Material:
    var key := str(surface.id)
    if _water_materials.has(key):
        return _water_materials[key]
    var ripple: Texture2D = load("res://assets/textures/water_normal.png")
    var width := float(surface.get("width_m",0.0))
    var mat := ShaderMaterial.new()
    var is_river: bool = not str(surface.id).begins_with("pool_")
    if is_river and not bool(surface.get("thermal",false)) and str(surface.id) != "authored_excelsior_outflow_01":
        mat.shader = load("res://shaders/river_water.gdshader")
        mat.set_shader_parameter("ripple",ripple)
        mat.set_shader_parameter("flow_speed",float(surface.get("flow_mps",0.0)))
        var margin: float = clampf(width*0.23,0.8,5.0)
        mat.set_shader_parameter("width_m",(width*0.5+margin)*2.0)
        mat.set_shader_parameter("core_width_m",width)
        # Firehole DEM-transect mean depth: 0.512-0.53 m (configs/cross_sections.json).
        mat.set_shader_parameter("channel_depth_m",0.53 if width > 8.0 else 0.45)
    else:
        mat.shader = load("res://shaders/water.gdshader")
        mat.set_shader_parameter("ripple",ripple)
        if not is_river:
            mat.set_shader_parameter("pool",1.0)
            mat.set_shader_parameter("temperature_c",float(surface.get("temperature_c",0.0)))
            if bool(surface.get("thermal",false)):
                mat.set_shader_parameter("shallow_color",Vector3(.10,.64,.62))
                mat.set_shader_parameter("deep_color",Vector3(.012,.29,.48))
                mat.set_shader_parameter("flow_speed",.03)
                mat.set_shader_parameter("roughness",.20)
                var ramp_path := "res://assets/textures/pool_ramps/%s.png" % str(surface.id)
                if ResourceLoader.exists(ramp_path):
                    mat.set_shader_parameter("band_ramp",load(ramp_path))
                    mat.set_shader_parameter("ramp_mix",1.0)
        else:
            mat.set_shader_parameter("flow_speed",float(surface.get("flow_mps",0.0)))
            mat.set_shader_parameter("width_m",width)
            mat.set_shader_parameter("pool",0.0)
            if bool(surface.get("thermal",false)):
                mat.set_shader_parameter("shallow_color",Vector3(.34,.43,.32))
                mat.set_shader_parameter("deep_color",Vector3(.15,.32,.25))
                mat.set_shader_parameter("roughness",.32)
                mat.set_shader_parameter("cascade",1.0)
            if str(surface.id) == "authored_excelsior_outflow_01":
                # Advect outflow ripples; red carries the cooling and foam fraction.
                mat.set_shader_parameter("flow_speed",2.2)
    _water_materials[key] = mat
    return mat

## Route surface materials keyed by class; gravel carries the per-ribbon width uniform.
func _route_material(key: String, width_m: float) -> Material:
    var cache_key := key
    if key == "gravel":
        cache_key = "gravel:%.3f" % width_m
    if _route_materials.has(cache_key):
        return _route_materials[cache_key]
    var mat: Material
    match key:
        "asphalt":
            var standard := StandardMaterial3D.new()
            standard.albedo_color = Color(0.105,0.112,0.106)
            standard.roughness = 0.9
            mat = standard
        "gravel":
            var shadered := ShaderMaterial.new()
            shadered.shader = load("res://shaders/trail.gdshader")
            shadered.set_shader_parameter("ground_detail",load("res://assets/textures/forest_ground_04_diff_1k.jpg"))
            shadered.set_shader_parameter("width_m",width_m)
            mat = shadered
        "wood":
            mat = load("res://assets/materials/boardwalk.tres")
        "paint":
            var standard := StandardMaterial3D.new()
            standard.albedo_color = Color(0.80,0.60,0.19)
            standard.roughness = 0.9
            mat = standard
        "timber_stringer":
            mat = load("res://assets/materials/timber_stringer.tres")
        "timber_post":
            mat = load("res://assets/materials/timber_post.tres")
        "timber_beam":
            mat = load("res://assets/materials/timber_beam.tres")
        _:
            var fallback := StandardMaterial3D.new()
            fallback.albedo_color = Color(0.5,0.45,0.4)
            fallback.roughness = 0.9
            mat = fallback
    _route_materials[cache_key] = mat
    return mat

## Return routes from the containing collision-level tile; absent resident tiles yield no chunks.
func route_chunks_at(x: float,z: float) -> Array:
    for key: String in _groups:
        var tile = resident.get(key)
        if tile != null and int(tile.descriptor.lod) == 0 and _contains(tile.descriptor,x,z):
            return _groups[key].routes
    return []

func _contains(d: Dictionary,x: float,z: float) -> bool:
    return x>=float(d.origin_x_m) and x<float(d.origin_x_m)+float(d.size_m) and z>=float(d.origin_z_m) and z<float(d.origin_z_m)+float(d.size_m)

func is_collision_ready(x: float,z: float) -> bool:
    for entry: Dictionary in _collisions.values():
        if _physics_tick>=int(entry.ready_tick) and _contains(entry.descriptor,x,z):
            return true
    return false

func can_enter(local: Vector3, clearance_m: float = 0.5) -> bool:
    var p: Array[float] = frame.absolute_xz(local)
    for dx: float in [-clearance_m,0.0,clearance_m]:
        for dz: float in [-clearance_m,0.0,clearance_m]:
            if not is_collision_ready(p[0]+dx,p[1]+dz):
                return false
    return true

func height_at(x: float,z: float) -> float:
    for entry: Dictionary in _collisions.values():
        if _physics_tick>=int(entry.ready_tick) and _contains(entry.descriptor,x,z):
            return resident[str(entry.descriptor.key)].sample_height(x,z)
    return NAN  # Absence is explicit. Never substitute zero terrain.

func _place_body(entry: Dictionary) -> void:
    var d: Dictionary = entry.descriptor
    entry.body.position = frame.local_position(float(d.origin_x_m)+float(d.size_m)*0.5,0.0,float(d.origin_z_m)+float(d.size_m)*0.5)
    entry.body.reset_physics_interpolation()

func _on_rebased(_shift: Vector3) -> void:
    for tile in resident.values():
        tile.rebase(frame)
    for entry: Dictionary in _collisions.values():
        _place_body(entry)
    _elapsed = replan_interval_s

func retry_failed() -> void:
    _failures.clear()

func _exit_tree() -> void:
    for job in _inflight.values():
        job.cancel()
    for job in _inflight.values():
        WorkerThreadPool.wait_for_task_completion(job.task_id)
    _inflight.clear()
    _ready.clear()
