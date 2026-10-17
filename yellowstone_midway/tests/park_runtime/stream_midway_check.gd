extends SceneTree
## Check headless Midway stream heights/water cut/routes against core, master raster and world data.
const Frame = preload("res://scripts/park_runtime/world_frame.gd")
const Streamer = preload("res://scripts/park_runtime/terrain_streamer.gd")
const Job = preload("res://scripts/park_runtime/terrain_job.gd")
const FeatureSource = preload("res://scripts/park_runtime/feature_source.gd")
const TileWater = preload("res://scripts/park_runtime/tile_water.gd")
const HeightField = preload("res://scripts/height_field.gd")
const CoreTerrain = preload("res://scripts/core_terrain.gd")
const WaterCut = preload("res://scripts/water_polygon_cut.gd")
const CATALOG := "res://data/park_composed/catalog.json"
const WORLD := "res://data/world.json"
const BRIDGE_ROUTES: Array[String] = ["trail_3227_0", "trail_3226_0"]
const MAX_FRAMES := 1200
const SAMPLES := 400
var failures: int = 0
var checks: int = 0
var master
var legacy
var extent: Dictionary
var catalog: Dictionary
var features: Dictionary
var world: Dictionary
var base_dir: String
var pages: Dictionary = {}
var jobs: Dictionary = {}

func _initialize() -> void:
    call_deferred("run")

func check(condition: bool, message: String) -> void:
    checks += 1
    if not condition:
        failures += 1
        push_error(message)

func settle(stream: Node, observer: Camera3D, frame: RefCounted, target: Vector3) -> bool:
    observer.global_position = frame.local_position(target.x, target.y, target.z)
    stream.velocity = Vector3.ZERO
    for _tick: int in MAX_FRAMES:
        frame.maybe_rebase(observer)
        await physics_frame
        await process_frame
        if stream.is_collision_ready(target.x, target.z) and stream.can_enter(observer.global_position, 0.5):
            return true
    return false

func page(path: String) -> Dictionary:
    if not pages.has(path):
        pages[path] = JSON.parse_string(FileAccess.get_file_as_string(base_dir.path_join(path)))
    return pages[path]

func covers(d: Dictionary, x: float, z: float) -> bool:
    return x >= float(d.origin_x_m) and x <= float(d.origin_x_m) + float(d.size_m) and z >= float(d.origin_z_m) and z <= float(d.origin_z_m) + float(d.size_m)

func leaf_descriptor(x: float, z: float) -> Dictionary:
    var node: Dictionary = {}
    for root_tile: Dictionary in catalog.roots:
        if covers(root_tile, x, z):
            node = root_tile
            break
    while not node.is_empty() and int(node.lod) > 0:
        var next: Dictionary = {}
        for child: Dictionary in page(str(node.page)).children:
            if covers(child, x, z):
                next = child
                break
        node = next
    return node

func run_job(d: Dictionary, with_features: bool = true) -> Dictionary:
    var key: String = str(d.key) + (":f" if with_features else ":b")
    if not jobs.has(key):
        var job = Job.new()
        job.configure(d, base_dir, str(catalog.dataset_revision))
        if with_features:
            job.configure_features(features)
        job.run()
        jobs[key] = job.result
    return jobs[key]

func bary(values: PackedFloat32Array, columns: int, gx: float, gz: float) -> float:
    var ix: int = clampi(int(floor(gx)), 0, columns - 2)
    var iz: int = clampi(int(floor(gz)), 0, columns - 2)
    var fx: float = gx - ix
    var fz: float = gz - iz
    var a: float = values[iz * columns + ix]
    var b: float = values[iz * columns + ix + 1]
    var c: float = values[(iz + 1) * columns + ix]
    var d: float = values[(iz + 1) * columns + ix + 1]
    return a + fx * (b - a) + fz * (c - a) if fx + fz <= 1.0 else d + (1.0 - fx) * (c - d) + (1.0 - fz) * (b - d)

func inside_core(x: float, z: float) -> bool:
    return x >= float(extent.x_min_m) and x <= float(extent.x_max_m) and z >= float(extent.z_min_m) and z <= float(extent.z_max_m)

## Core heights inside the core footprint, master heights elsewhere.
func reference_height(x: float, z: float) -> float:
    if inside_core(x, z):
        return bary(legacy._heights_full, int(extent.nx), x - float(extent.x_min_m), z - float(extent.z_min_m))
    return master.sample(x, z)

func tile_height(result: Dictionary, x: float, z: float) -> float:
    var d: Dictionary = result.page.tile
    var cells: int = int(d.mesh_cells)
    var spacing: float = float(d.size_m) / cells
    return bary(result.heights, cells + 1, (x - float(d.origin_x_m)) / spacing, (z - float(d.origin_z_m)) / spacing)

func source_entry(pack_id: String) -> Dictionary:
    for source: Dictionary in catalog.sources:
        if str(source.pack_id) == pack_id:
            return source
    return {}

func audit_provenance() -> void:
    var core_hashes: Dictionary = source_entry("core").get("core_sources", {})
    var layers: Dictionary = legacy.core_meta.get("layers", {})
    check(core_hashes.get("core_terrain.json", "") == FileAccess.get_sha256("res://data/core_terrain/core_terrain.json"), "pack was built from a different core_terrain.json")
    check(core_hashes.get("core_heightfield.f32", "") == str(layers.core_heightfield_m.sha256), "pack core heightfield differs from the legacy layer")
    check(core_hashes.get("core_microrelief.f32", "") == str(layers.core_microrelief_m.sha256), "pack core microrelief differs from the legacy layer")
    check(str(source_entry("midway").get("source_sha256", "")) == FileAccess.get_sha256("res://data/terrain.f32"), "pack master differs from terrain.f32")

func audit_boundary() -> void:
    var worst: float = 0.0
    var count: int = 0
    var x0: float = float(extent.x_min_m)
    var x1: float = float(extent.x_max_m)
    var z0: float = float(extent.z_min_m)
    var z1: float = float(extent.z_max_m)
    for step: int in range(0, 601, 8):
        for offset: float in [-2.0, -0.5, 0.0, 0.5, 2.0]:
            var points: Array[Vector2] = [Vector2(x0 + step, z0 + offset), Vector2(x0 + step, z1 + offset), Vector2(x0 + offset, z0 + step), Vector2(x1 + offset, z0 + step)]
            for point: Vector2 in points:
                var d: Dictionary = leaf_descriptor(point.x, point.y)
                if d.is_empty() or int(d.lod) != 0:
                    check(false, "no leaf tile at boundary point " + str(point))
                    continue
                var result: Dictionary = run_job(d)
                if result.has("error"):
                    check(false, "boundary tile failed: " + str(result.error))
                    continue
                worst = maxf(worst, absf(tile_height(result, point.x, point.y) - reference_height(point.x, point.y)))
                count += 1
    check(count > 1000, "boundary audit sampled too few points")
    check(worst < 0.001, "pack differs from the legacy core cut at the core boundary by %f m" % worst)
    print("BOUNDARY samples=", count, " tiles=", jobs.size(), " worst_error_m=", worst)

func polygon_area(ring: Array) -> float:
    var polygon := PackedVector2Array()
    for point: Array in ring:
        polygon.append(Vector2(float(point[0]), float(point[1])))
    return absf(WaterCut.signed_area(polygon))

func audit_water() -> void:
    var cut_pools: int = 0
    for pool: Dictionary in world.pools:
        if not bool(pool.get("thermal", false)):
            continue
        cut_pools += 1
        var outline := PackedVector2Array()
        for point: Array in pool.ring:
            outline.append(Vector2(float(point[0]), float(point[1])))
        var box: Rect2 = WaterCut.bounds(outline)
        var tiles: Dictionary = {}
        var x: float = box.position.x - 16.0
        while x <= box.end.x + 16.0:
            var z: float = box.position.y - 16.0
            while z <= box.end.y + 16.0:
                var d: Dictionary = leaf_descriptor(x, z)
                if not d.is_empty():
                    tiles[str(d.key)] = d
                z += 16.0
            x += 16.0
        var removed: float = 0.0
        var shoreline_triangles: int = 0
        var omitted: int = 0
        for d: Dictionary in tiles.values():
            var result: Dictionary = run_job(d)
            check(not result.has("error"), "pool tile failed: " + str(result.get("error", "")))
            if result.has("error"):
                continue
            check(run_job(d, false).heights == result.heights, "pool cut altered the collision height source")
            if result.pools.has(str(pool.id)):
                removed += float(result.water.removed_xz_area_m2)
                shoreline_triangles += int(result.water.shoreline_closure_triangles)
                omitted += int(result.skirts_omitted)
                audit_skirts(result, pool, d)
        var expected: float = polygon_area(pool.ring)
        check(absf(removed - expected) < 0.01 + expected * 0.00001, "%s removed %f m2 of terrain, polygon is %f m2" % [str(pool.id), removed, expected])
        check(shoreline_triangles > 0, "%s has no shoreline surface" % str(pool.id))
        print("POOL ", pool.id, " tiles=", tiles.size(), " removed_m2=", removed, " polygon_m2=", expected, " shoreline_tris=", shoreline_triangles, " skirts_omitted=", omitted)
    check(cut_pools == 4, "expected four thermal pools")

func audit_skirts(result: Dictionary, pool: Dictionary, d: Dictionary) -> void:
    var indices: PackedInt32Array = result.arrays[Mesh.ARRAY_INDEX]
    var vertices: PackedVector3Array = result.arrays[Mesh.ARRAY_VERTEX]
    var grid_indices: int = int(result.water.retained_triangles) * 3
    var ring := PackedVector2Array()
    for point: Array in pool.ring:
        ring.append(Vector2(float(point[0]) - float(d.origin_x_m), float(point[1]) - float(d.origin_z_m)))
    var quads: int = (indices.size() - grid_indices) / 6
    check(quads + int(result.skirts_omitted) == 4 * int(d.mesh_cells), "skirt quads plus omitted segments do not cover the tile perimeter")
    for start: int in range(grid_indices, indices.size(), 6):
        var middle: Vector3 = (vertices[indices[start]] + vertices[indices[start + 2]]) * 0.5
        check(not Geometry2D.is_point_in_polygon(Vector2(middle.x, middle.z), ring), "skirt hangs across open water in " + str(d.key))

func audit_cut_parity() -> void:
    var rim: Array = []
    for pool: Dictionary in world.pools:
        if str(pool.id) == "pool_1034_0":
            rim = pool.ring[0]
    var d: Dictionary = leaf_descriptor(float(rim[0]), float(rim[1]))
    var result: Dictionary = run_job(d)
    var found: Dictionary = FeatureSource.collect(features, "pools", float(d.origin_x_m), float(d.origin_z_m), float(d.origin_x_m) + float(d.size_m), float(d.origin_z_m) + float(d.size_m))
    var local: Array = TileWater.localize(found.features, float(d.origin_x_m), float(d.origin_z_m))
    var cells: int = int(d.mesh_cells)
    var n: int = cells + 1
    var spacing: float = float(d.size_m) / cells
    var vertices := PackedVector3Array()
    var normals := PackedVector3Array()
    var uvs := PackedVector2Array()
    var indices := PackedInt32Array()
    for z: int in n:
        for x: int in n:
            vertices.append(Vector3(x * spacing, result.heights[z * n + x], z * spacing))
            normals.append(Vector3.UP)
            uvs.append(Vector2(float(x) / cells, float(z) / cells))
    for z: int in cells:
        for x: int in cells:
            var a: int = z * n + x
            indices.append_array(PackedInt32Array([a, a + 1, a + n, a + 1, a + n + 1, a + n]))
    var arrays: Array = []
    arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = vertices
    arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_TEX_UV] = uvs
    arrays[Mesh.ARRAY_INDEX] = indices
    var mesh := ArrayMesh.new()
    mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
    var mesh_cut: Dictionary = WaterCut.cut(mesh, Transform3D.IDENTITY, local)
    var raw_cut: Dictionary = WaterCut.cut_arrays(arrays, Transform3D.IDENTITY, local)
    check(bool(mesh_cut.ok) and bool(raw_cut.ok), "water cut failed on the Grand Prismatic tile")
    check(int(raw_cut.get("split_boundary_triangles", 0)) > 0 and mesh_cut.mesh.get_surface_count() == 1, "the parity tile must straddle the pool rim")
    if not (bool(mesh_cut.ok) and bool(raw_cut.ok)) or mesh_cut.mesh.get_surface_count() != 1:
        return
    var mesh_arrays: Array = mesh_cut.mesh.surface_get_arrays(0)
    check(mesh_arrays[Mesh.ARRAY_INDEX] == raw_cut.arrays[Mesh.ARRAY_INDEX] and mesh_arrays[Mesh.ARRAY_VERTEX] == raw_cut.arrays[Mesh.ARRAY_VERTEX], "raw-array cut differs from the mesh cut")
    check(mesh_cut.shoreline_mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] == raw_cut.shoreline_arrays[Mesh.ARRAY_VERTEX], "raw-array shoreline differs from the mesh cut")
    check(int(result.water.removed_triangles) == int(raw_cut.removed_triangles) and int(result.water.split_boundary_triangles) == int(raw_cut.split_boundary_triangles), "worker cut report differs from the mesh cut")
    print("CUT_PARITY removed=", raw_cut.removed_triangles, " split=", raw_cut.split_boundary_triangles, " shoreline_triangles=", raw_cut.shoreline_closure_triangles)

func audit_dry_tile() -> void:
    var d: Dictionary = leaf_descriptor(500.0, 500.0)
    var result: Dictionary = run_job(d)
    check(result.pools.is_empty() and result.shoreline_arrays.is_empty() and int(result.skirts_omitted) == 0, "a tile away from water must keep its full skirt and no shoreline")
    var second = Job.new()
    second.configure(d, base_dir, str(catalog.dataset_revision))
    second.configure_features(features)
    second.run()
    check(second.result.arrays[Mesh.ARRAY_VERTEX] == result.arrays[Mesh.ARRAY_VERTEX], "tile preparation is not deterministic")

func route_by_id(id: String) -> Dictionary:
    for route: Dictionary in world.routes:
        if str(route.id) == id:
            return route
    return {}

func run() -> void:
    var scene := Node3D.new()
    root.add_child(scene)
    var frame = Frame.new()
    var observer := Camera3D.new()
    observer.far = 30000.0
    scene.add_child(observer)
    observer.make_current()
    frame.register_root(observer)
    var stream = Streamer.new()
    scene.add_child(stream)
    check(stream.configure(CATALOG, frame, observer), "Midway catalog rejected; build data/park_composed with terrain_pack --core-dir")
    if failures > 0:
        quit(1)
        return
    base_dir = CATALOG.get_base_dir()
    catalog = JSON.parse_string(FileAccess.get_file_as_string(CATALOG))
    features = FeatureSource.load_index(base_dir, catalog.features)
    check(not features.has("error"), "feature index rejected")
    world = JSON.parse_string(FileAccess.get_file_as_string(WORLD))
    master = HeightField.new()
    legacy = CoreTerrain.new()
    check(legacy._load_metadata() and legacy._load_heights(), "legacy core loader failed")
    extent = legacy.extent_rect()
    check(int(extent.nx) == 601 and float(extent.cell_m) == 1.0, "unexpected legacy core grid")
    if failures > 0:
        quit(1)
        return
    audit_provenance()
    audit_boundary()
    audit_water()
    audit_cut_parity()
    audit_dry_tile()
    var stops: Array[Vector3] = [Vector3(-242.0, 70.0, 160.0), Vector3(70.0, 30.0, -261.0), Vector3(260.0, 40.0, 950.0), Vector3(-1500.0, 60.0, -1900.0),
        Vector3(-340.0, 40.0, 0.0), Vector3(0.0, 40.0, -380.0), Vector3(260.0, 40.0, 100.0), Vector3(-100.0, 40.0, 220.0), Vector3(-59.9, 40.0, -186.4)]
    var bridge_indices: Dictionary = {}
    for id: String in BRIDGE_ROUTES:
        var route: Dictionary = route_by_id(id)
        var span: Array = route.bridge_spans[0]
        var middle: int = (int(span[0]) + int(span[1])) / 2
        var point: Array = route.points[middle]
        bridge_indices[id] = middle
        stops.append(Vector3(float(point[0]), 40.0, float(point[2])))
    for stop: Vector3 in stops:
        var ready: bool = await settle(stream, observer, frame, stop)
        check(ready, "collision not ready at " + str(stop))
        if not ready:
            continue
        var worst: float = 0.0
        var rng := RandomNumberGenerator.new()
        rng.seed = 5171
        for _i: int in SAMPLES:
            var x: float = stop.x + rng.randf_range(-30.0, 30.0)
            var z: float = stop.z + rng.randf_range(-30.0, 30.0)
            var streamed: float = stream.height_at(x, z)
            if is_nan(streamed):
                continue
            worst = maxf(worst, absf(streamed - reference_height(x, z)))
        check(worst < 0.001, "leaf height differs from the core cut or master raster by %f m at %s" % [worst, str(stop)])
        print("STOP ", stop, " worst_error_m=", worst)
    await audit_streamed_features(stream, observer, frame, bridge_indices)
    check(int(stream.stats.get("failures", 0)) == 0, "tile jobs failed")
    check(float(stream.stats.get("resident_estimate_mib", 0.0)) <= stream.resident_limit_mib, "resident estimate exceeds budget")
    print("PARK_MIDWAY_STREAM checks=", checks, " failures=", failures, " resident=", stream.stats.get("resident_tiles"), " mib=", stream.stats.get("resident_estimate_mib"))
    legacy.free()
    scene.queue_free()
    await process_frame
    quit(1 if failures else 0)

func audit_streamed_features(stream: Node, observer: Camera3D, frame: RefCounted, bridge_indices: Dictionary) -> void:
    for id: String in BRIDGE_ROUTES:
        var route: Dictionary = route_by_id(id)
        var middle: int = int(bridge_indices[id])
        var point: Array = route.points[middle]
        var ready: bool = await settle(stream, observer, frame, Vector3(float(point[0]), 40.0, float(point[2])))
        check(ready, "bridge tile not ready for " + id)
        var chunk: Dictionary = {}
        for candidate: Dictionary in stream.route_chunks_at(float(point[0]), float(point[2])):
            if str(candidate.id) == id and int(candidate.first_point) <= middle and middle <= int(candidate.last_point):
                chunk = candidate
        check(not chunk.is_empty(), "route chunk missing at the " + id + " bridge")
        if chunk.is_empty():
            continue
        check(chunk.points[middle - int(chunk.first_point)] == point, "route chunk point differs from world.json")
        check(not chunk.bridge_spans.is_empty(), "route chunk lost its bridge span at " + id)
        var min_clearance: float = INF
        var worst_error: float = 0.0
        var sampled: int = 0
        for span: Array in route.bridge_spans:
            for index: int in range(int(span[0]), int(span[1]) + 1):
                var p: Array = route.points[index]
                var streamed: float = stream.height_at(float(p[0]), float(p[2]))
                if is_nan(streamed):
                    continue
                sampled += 1
                worst_error = maxf(worst_error, absf(streamed - reference_height(float(p[0]), float(p[2]))))
                min_clearance = minf(min_clearance, float(p[1]) - streamed)
        check(sampled > 0, "no bridge samples resident for " + id)
        check(worst_error < 0.001, "%s bridge terrain differs from the legacy core cut by %f m" % [id, worst_error])
        print("BRIDGE ", id, " samples=", sampled, " worst_error_m=", worst_error, " min_deck_clearance_m=", min_clearance)
    var pool_key: String = ""
    for key: String in stream.resident:
        var d: Dictionary = stream.resident[key].descriptor
        if int(d.lod) == 0 and covers(d, -59.9, -186.4):
            pool_key = key
    check(pool_key != "", "Turquoise Pool tile is not resident")
    if pool_key != "":
        var group: Dictionary = stream.tile_group(pool_key)
        check(bool(group.shoreline) and group.pools.has("pool_1028_0"), "pool tile lost its shoreline group")
        var shoreline_node: Node = stream.resident[pool_key].get_node_or_null("Shoreline")
        check(shoreline_node is MeshInstance3D and (shoreline_node as MeshInstance3D).mesh.get_surface_count() == 1, "shoreline surface was not committed with the tile")
