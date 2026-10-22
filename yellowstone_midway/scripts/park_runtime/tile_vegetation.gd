extends RefCounted
## Tile-scoped vegetation batches from paged placement records; shared assets load once.

const Lodgepole = preload("res://scripts/lodgepole_library.gd")

const GRASS_ROOT := "res://assets/imported/grass_medium_01/%s.gltf"
const GRASS_FILES := ["grass_tall_a", "grass_tall_b", "grass_small_a", "grass_small_b"]
const ROCK_TEXTURE := "res://assets/textures/rock_boulder_dry_diff_1k.jpg"
const BARK_TEXTURE := "res://assets/textures/pine_bark_diff_1k.jpg"
const TRUNK_LIMIT_X_M := 750.0
const TRUNK_LIMIT_Z_M := 1250.0
# Batch split mirrors tools/bake_world.gd make_vegetation per-bin assembly.
static var _grass_assets: Dictionary = {}
static var _stone_material: StandardMaterial3D = null
static var _bark_material: StandardMaterial3D = null
# Registered on the main thread during preparation; workers read the plain descriptors only.
static var _batch_plans: Dictionary = {}
static var _batch_meshes: Dictionary = {}

## Instance buffers and collider parameters for one tile rectangle; worker-safe after preparation.
static func plan_tile(records: Array, descriptor: Dictionary) -> Dictionary:
    var origin := Vector2(float(descriptor.origin_x_m), float(descriptor.origin_z_m))
    var size: float = float(descriptor.size_m)
    var center := Vector3(origin.x + size * 0.5, 0.0, origin.y + size * 0.5)
    var node_position := Vector3(size * 0.5, 0.0, size * 0.5)
    var bins: Dictionary = {}
    for record: Dictionary in records:
        var kind := str(record.get("kind", ""))
        var form: String = Lodgepole.archetype(record) if kind in ["pine", "snag"] else ""
        var variant: int = 0 if kind in ["pine", "snag"] else int(record.get("variant", 0))
        var key := "%s_%s_%d" % [kind, form, variant]
        if not bins.has(key):
            bins[key] = []
        bins[key].append(record)
    var planned: Array = []
    var trees: int = 0
    for key: String in bins:
        var bin: Dictionary = _plan_bin(bins[key], center, node_position, key)
        if bin.has("error"):
            return bin
        planned.append(bin)
        if bin.is_tree:
            trees += bins[key].size()
    return {"bins": planned, "trees": trees, "records": records.size(), "node_position": node_position}

## Create the planned batch nodes and trunk colliders under a group parented to the tile.
static func install_tile(tile: Node3D, plan: Dictionary) -> Dictionary:
    var group := Node3D.new()
    group.name = "StreamedVegetation"
    var batches: int = 0
    for bin: Dictionary in plan.bins:
        batches += _install_bin(group, bin, plan.node_position)
    group.set_meta("tree_records", int(plan.trees))
    group.set_meta("records", int(plan.records))
    tile.add_child(group)
    return {"group": group, "trees": int(plan.trees), "batches": batches}

## Shared asset key; pine and snag records of one form use the same assets.
static func _asset_key(kind: String, form: String, variant: int) -> String:
    if kind in ["pine", "snag"]:
        return "tree:" + form
    if kind == "grass":
        return "grass:%d" % posmod(variant, 4)
    return kind

## Resolve one asset key into plain batch descriptors in the bake's batch order; main thread only.
static func _register(asset_key: String, kind: String, form: String, variant: int) -> bool:
    var assets: Array = _assets(kind, form, variant)
    if assets.is_empty():
        push_error("Streamed vegetation assets are unavailable: " + asset_key)
        return false
    var is_tree: bool = kind in ["pine", "snag"]
    var resolved: Array = []
    for source_asset: Array in assets:
        if is_tree and str(source_asset[4]) in ["Branches", "NeedleCards"]:
            var architecture_lod: int = 0 if float(source_asset[2]) == 0.0 else (1 if float(source_asset[2]) == 18.0 else 2)
            for architecture_variant: int in range(4):
                var architecture_assets: Array = Lodgepole.load_architecture(form, architecture_variant, architecture_lod)
                if architecture_assets.is_empty() or not Lodgepole.bind_cutout_materials(architecture_assets):
                    push_error("Streamed lodgepole architecture is unavailable: " + form)
                    return false
                for architecture_asset: Array in architecture_assets:
                    if str(architecture_asset[4]) == str(source_asset[4]):
                        resolved.append([architecture_asset, architecture_variant])
        elif is_tree and str(source_asset[4]) == "Billboard":
            var view_asset: Array = Lodgepole.load_billboard_batch(form, true)
            if view_asset.is_empty():
                push_error("Streamed impostor batch is unavailable: " + form)
                return false
            resolved.append([view_asset, -2])
        else:
            resolved.append([source_asset, -1])
    var plans: Array = []
    var meshes: Array = []
    for item: Array in resolved:
        var asset: Array = item[0]
        if is_tree:
            Lodgepole.bind_instance_lods(asset)
        var lod_range: Array = [float(asset[2]), float(asset[3])] if asset.size() > 2 else []
        plans.append({"part": str(asset[4]) if asset.size() > 4 else "", "range": lod_range, "transform": asset[1], "aabb": (asset[0] as Mesh).get_aabb(), "batch": int(item[1])})
        meshes.append(asset[0])
    _batch_plans[asset_key] = plans
    _batch_meshes[asset_key] = meshes
    return true

## Plan one kind/form/variant group as one batch per asset part and LOD.
static func _plan_bin(entries: Array, center: Vector3, node_position: Vector3, key: String) -> Dictionary:
    var exemplar: Dictionary = entries[0]
    var kind := str(exemplar.kind)
    var is_tree: bool = kind in ["pine", "snag"]
    var form: String = Lodgepole.archetype(exemplar) if is_tree else ""
    var variant: int = 0 if is_tree else int(exemplar.get("variant", 0))
    var asset_key := _asset_key(kind, form, variant)
    var plans: Array = _batch_plans.get(asset_key, [])
    if plans.is_empty():
        return {"error": "Streamed vegetation assets are unavailable: " + key}
    # Per-record identity keys and display heights are computed once per bin.
    var variation := PackedInt32Array()
    var half_heights := PackedFloat64Array()
    if is_tree:
        for record: Dictionary in entries:
            variation.append(int(Lodgepole.variation_key(record)))
            half_heights.append(float(Lodgepole.display_dimensions(record).height_m) * 0.5)
    var batches: Array = []
    for index: int in plans.size():
        var plan: Dictionary = plans[index]
        var selected := PackedInt32Array()
        for i: int in entries.size():
            if int(plan.batch) < 0 or variation[i] == int(plan.batch):
                selected.append(i)
        if selected.is_empty():
            continue
        var part: String = plan.part
        var asset_transform: Transform3D = plan.transform
        var asset_bounds: AABB = plan.aabb
        var instance_buffer := PackedFloat32Array()
        var instance_bounds := AABB()
        for n: int in selected.size():
            var r: Dictionary = entries[selected[n]]
            var p := Vector3(r.position[0], r.position[1], r.position[2])
            var basis := Basis(Vector3.UP, float(r.yaw))
            var local: Transform3D = Lodgepole.local_transform(r, part) if is_tree else Transform3D(Basis.from_scale(Vector3.ONE * float(r.scale)), Vector3.ZERO)
            var xf: Transform3D = Transform3D(basis, p - center) * local * asset_transform
            if not xf.is_finite():
                return {"error": "Vegetation transform is nonfinite: " + str(r.get("id", r.get("stable_id", "unknown")))}
            var color := Color(float(variation[selected[n]]) / 3.0, 1.0, 1.0, 1.0) if int(plan.batch) == -2 else Color.WHITE
            _append_instance(instance_buffer, xf, color)
            if is_tree:
                instance_buffer.append_array(PackedFloat32Array([p.x, p.y + half_heights[selected[n]], p.z, 1.0]))
            var bounds: AABB = xf * asset_bounds
            instance_bounds = bounds if n == 0 else instance_bounds.merge(bounds)
        batches.append({"plan": index, "count": selected.size(), "buffer": instance_buffer, "bounds": instance_bounds})
    var colliders: Array = _plan_trunk_colliders(entries, form, Vector2(center.x - node_position.x, center.z - node_position.z)) if is_tree else []
    return {"key": key, "kind": kind, "form": form, "is_tree": is_tree, "asset_key": asset_key, "batches": batches, "colliders": colliders}

## Emit one planned bin as one MultiMesh batch per asset part and LOD.
static func _install_bin(group: Node3D, bin: Dictionary, node_position: Vector3) -> int:
    var kind: String = bin.kind
    var is_tree: bool = bin.is_tree
    var form: String = bin.form
    var key: String = bin.key
    var plans: Array = _batch_plans[bin.asset_key]
    var meshes: Array = _batch_meshes[bin.asset_key]
    var tree_meshes: Array[MultiMeshInstance3D] = []
    var tree_bin_bounds := AABB()
    var emitted: int = 0
    for batch: Dictionary in bin.batches:
        var plan: Dictionary = plans[int(batch.plan)]
        var instance_bounds: AABB = batch.bounds
        var part: String = plan.part
        var lod_range: Array = plan.range
        var mm := MultiMesh.new()
        mm.transform_format = MultiMesh.TRANSFORM_3D
        mm.use_colors = true
        mm.use_custom_data = is_tree
        mm.mesh = meshes[int(batch.plan)]
        mm.instance_count = int(batch.count)
        mm.buffer = batch.buffer
        mm.custom_aabb = instance_bounds.grow(0.7)
        assert(mm.buffer.size() == int(batch.count) * (20 if is_tree else 16), "Vegetation instance data lost")
        var node := MultiMeshInstance3D.new()
        node.name = key + "_%s_%d" % [part, int(lod_range[0])] if is_tree else key
        if int(plan.batch) >= 0:
            node.name += "_variant%d" % int(plan.batch) if part != "Billboard" else "_view%d" % int(plan.batch)
        if int(plan.batch) == -2:
            node.set_meta("packed_impostor_variants", 4)
        node.set_meta("vegetation_kind", kind)
        if is_tree:
            node.set_meta("tree_archetype", form)
            node.set_meta("tree_part", part)
            node.set_meta("display_envelope_class", "transferred_or_photo_authored_unknown_local_error")
            if float(lod_range[0]) == 0.0 and part != "Bole":
                node.set_meta("architecture_variant", int(plan.batch))
            node.set_meta("lod_begin_m", float(lod_range[0]))
            tree_bin_bounds = instance_bounds if tree_meshes.is_empty() else tree_bin_bounds.merge(instance_bounds)
            tree_meshes.append(node)
        node.multimesh = mm
        node.position = node_position
        node.visibility_range_end = 150.0 if kind == "grass" else 2800.0
        if not lod_range.is_empty():
            node.visibility_range_begin = lod_range[0]
            node.visibility_range_end = lod_range[1]
            if float(lod_range[0]) >= float(Lodgepole.LOD_RANGES[2][0]):
                node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
        if kind == "grass":
            node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
        group.add_child(node)
        emitted += 1
    for tree_mesh: MultiMeshInstance3D in tree_meshes:
        tree_mesh.multimesh.custom_aabb = tree_bin_bounds.grow(0.7)
        var radius_m: float = tree_mesh.multimesh.custom_aabb.size.length() * 0.5
        var begin_padding_m: float = radius_m + clampf(tree_mesh.visibility_range_begin * 0.1, 2.0, 18.0)
        var end_padding_m: float = radius_m + clampf(tree_mesh.visibility_range_end * 0.1, 2.0, 18.0)
        tree_mesh.set_meta("instance_lod", true)
        tree_mesh.set_meta("lod_batch_padding_m", [begin_padding_m, end_padding_m])
        tree_mesh.visibility_range_begin = maxf(0.0, tree_mesh.visibility_range_begin - begin_padding_m)
        tree_mesh.visibility_range_end += end_padding_m
    for collider_plan: Dictionary in bin.colliders:
        var body := StaticBody3D.new()
        body.position = collider_plan.position
        body.set_meta("tree_height_m", float(collider_plan.tree_height))
        var collider := CollisionShape3D.new()
        var cylinder := CylinderShape3D.new()
        cylinder.radius = float(collider_plan.radius)
        cylinder.height = float(collider_plan.height)
        collider.shape = cylinder
        body.add_child(collider)
        group.add_child(body)
    return emitted

## Trunk colliders follow the bake's core-extent cylinder rule in absolute coordinates.
static func _plan_trunk_colliders(entries: Array, form: String, tile_origin: Vector2) -> Array:
    var colliders: Array = []
    for r: Dictionary in entries:
        if absf(float(r.position[0])) > TRUNK_LIMIT_X_M or absf(float(r.position[2])) > TRUNK_LIMIT_Z_M:
            continue
        var tree_transform: Transform3D = Lodgepole.local_transform(r, "Bole")
        var tree_height: float = float(Lodgepole.metadata().archetypes[form].height_m) * tree_transform.basis.y.length()
        var collision_height: float = minf(3.0, tree_height)
        colliders.append({"position": Vector3(float(r.position[0]) - tile_origin.x, float(r.position[1]) + collision_height * 0.5, float(r.position[2]) - tile_origin.y),
            "tree_height": tree_height, "height": collision_height,
            "radius": float(Lodgepole.metadata().archetypes[form].dbh_m) * tree_transform.basis.x.length() * 0.5})
    return colliders

## Register every shared asset of one tree form for planning; main thread only.
static func prewarm_form(form: String) -> bool:
    return _register("tree:" + form, "pine", form, 0)

## Register the shared grass, rock and log assets for planning; main thread only.
static func prewarm_ground_cover() -> bool:
    for variant: int in range(4):
        if not _register("grass:%d" % variant, "grass", "", variant):
            return false
    return _register("rock", "rock", "", 0) and _register("log", "log", "", 0)

## Shared per-kind assets; foliage binding is idempotent on the cached meshes.
static func _assets(kind: String, form: String, variant: int) -> Array:
    if kind in ["pine", "snag"]:
        var tree_assets: Array = Lodgepole.load_assets(form, 0)
        if tree_assets.is_empty() or not Lodgepole.bind_cutout_materials(tree_assets):
            return []
        return tree_assets
    if kind == "grass":
        var key := posmod(variant, 4)
        if not _grass_assets.has(key):
            var path := GRASS_ROOT % GRASS_FILES[key]
            if not ResourceLoader.exists(path):
                push_error("Grass mesh is missing or unimported: " + path)
                return []
            var source: Node = (load(path) as PackedScene).instantiate()
            var assets: Array = []
            _collect_meshes(source, Transform3D.IDENTITY, assets)
            source.free()
            if assets.is_empty() or not _bind_grass_materials(assets):
                return []
            _grass_assets[key] = assets
        return _grass_assets[key]
    if kind == "rock":
        var rock := SphereMesh.new()
        rock.radial_segments = 7
        rock.rings = 4
        rock.radius = 1.4
        rock.height = 1.7
        rock.material = _stone()
        return [[rock, Transform3D.IDENTITY]]
    if kind == "log":
        var log_mesh := CylinderMesh.new()
        log_mesh.top_radius = 0.17
        log_mesh.bottom_radius = 0.25
        log_mesh.height = 6.2
        log_mesh.radial_segments = 7
        log_mesh.material = _bark()
        return [[log_mesh, Transform3D(Basis(Vector3.FORWARD, PI / 2), Vector3(0.0, 0.20, 0.0))]]
    return []

static func _collect_meshes(node: Node, parent: Transform3D, result: Array) -> void:
    var transform: Transform3D = parent * node.transform if node is Node3D else parent
    if node is MeshInstance3D and node.mesh != null:
        result.append([node.mesh, transform])
    for child: Node in node.get_children():
        _collect_meshes(child, transform, result)

## Grass cutout surfaces take the foliage shader once on the shared mesh.
static func _bind_grass_materials(assets: Array) -> bool:
    for asset: Array in assets:
        var mesh: Mesh = asset[0]
        if not mesh is ArrayMesh:
            continue
        for surface: int in mesh.get_surface_count():
            var original: Material = mesh.surface_get_material(surface)
            if original is StandardMaterial3D and original.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR:
                var leaves := ShaderMaterial.new()
                leaves.shader = load("res://shaders/foliage.gdshader")
                leaves.set_shader_parameter("albedo_texture", original.albedo_texture)
                leaves.set_shader_parameter("alpha_cutoff", 0.40)
                leaves.set_shader_parameter("use_texture", true)
                leaves.set_shader_parameter("tint", Vector3(0.96, 1.00, 0.90))
                leaves.set_shader_parameter("wind_strength", 0.045)
                mesh.surface_set_material(surface, leaves)
    return true

static func _stone() -> StandardMaterial3D:
    if _stone_material == null:
        _stone_material = StandardMaterial3D.new()
        _stone_material.albedo_color = Color(0.65, 0.63, 0.55)
        _stone_material.roughness = 0.9
        _stone_material.albedo_texture = load(ROCK_TEXTURE)
    return _stone_material

static func _bark() -> StandardMaterial3D:
    if _bark_material == null:
        _bark_material = StandardMaterial3D.new()
        _bark_material.albedo_color = Color(0.64, 0.60, 0.48)
        _bark_material.roughness = 0.9
        _bark_material.albedo_texture = load(BARK_TEXTURE)
    return _bark_material

## Serialize three row-major transform rows followed by color or custom data.
static func _append_instance(buffer: PackedFloat32Array, xf: Transform3D, extra: Color) -> void:
    buffer.append_array(PackedFloat32Array([
        xf.basis.x.x, xf.basis.y.x, xf.basis.z.x, xf.origin.x,
        xf.basis.x.y, xf.basis.y.y, xf.basis.z.y, xf.origin.y,
        xf.basis.x.z, xf.basis.y.z, xf.basis.z.z, xf.origin.z,
        extra.r, extra.g, extra.b, extra.a]))
