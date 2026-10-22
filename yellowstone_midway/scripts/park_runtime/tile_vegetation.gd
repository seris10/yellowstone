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

## Build the batches owned by one tile rectangle under a group parented to the tile.
static func build_tile(tile: Node3D, records: Array, descriptor: Dictionary) -> Dictionary:
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
    var group := Node3D.new()
    group.name = "StreamedVegetation"
    var trees: int = 0
    var batches: int = 0
    for key: String in bins:
        var emitted: int = _emit_bin(group, bins[key], center, node_position, key)
        if emitted < 0:
            group.free()
            return {}
        batches += emitted
        if str(bins[key][0].get("kind", "")) in ["pine", "snag"]:
            trees += bins[key].size()
    group.set_meta("tree_records", trees)
    group.set_meta("records", records.size())
    tile.add_child(group)
    return {"group": group, "trees": trees, "batches": batches}

## Emit one kind/form/variant group as one batch per asset part and LOD.
static func _emit_bin(group: Node3D, entries: Array, center: Vector3, node_position: Vector3, key: String) -> int:
    var exemplar: Dictionary = entries[0]
    var kind := str(exemplar.kind)
    var is_tree: bool = kind in ["pine", "snag"]
    var form: String = Lodgepole.archetype(exemplar) if is_tree else ""
    var variant: int = 0 if is_tree else int(exemplar.get("variant", 0))
    var assets: Array = _assets(kind, form, variant)
    if assets.is_empty():
        push_error("Streamed vegetation assets are unavailable: " + key)
        return -1
    var asset_batches: Array = []
    for source_asset: Array in assets:
        if is_tree and str(source_asset[4]) in ["Branches", "NeedleCards"]:
            var architecture_lod: int = 0 if float(source_asset[2]) == 0.0 else (1 if float(source_asset[2]) == 18.0 else 2)
            for architecture_variant: int in range(4):
                var variant_entries: Array = []
                for record: Dictionary in entries:
                    if int(Lodgepole.variation_key(record)) == architecture_variant:
                        variant_entries.append(record)
                if variant_entries.is_empty():
                    continue
                var architecture_assets: Array = Lodgepole.load_architecture(form, architecture_variant, architecture_lod)
                if architecture_assets.is_empty() or not Lodgepole.bind_cutout_materials(architecture_assets):
                    push_error("Streamed lodgepole architecture is unavailable: " + form)
                    return -1
                for architecture_asset: Array in architecture_assets:
                    if str(architecture_asset[4]) == str(source_asset[4]):
                        asset_batches.append([architecture_asset, variant_entries, architecture_variant])
        elif is_tree and str(source_asset[4]) == "Billboard":
            var view_asset: Array = Lodgepole.load_billboard_batch(form, true)
            if view_asset.is_empty():
                push_error("Streamed impostor batch is unavailable: " + form)
                return -1
            asset_batches.append([view_asset, entries, -2])
        else:
            asset_batches.append([source_asset, entries, -1])
    var tree_meshes: Array[MultiMeshInstance3D] = []
    var tree_bin_bounds := AABB()
    var emitted: int = 0
    for batch: Array in asset_batches:
        var asset: Array = batch[0]
        var render_entries: Array = batch[1]
        var mm := MultiMesh.new()
        mm.transform_format = MultiMesh.TRANSFORM_3D
        mm.use_colors = true
        mm.use_custom_data = is_tree
        mm.mesh = asset[0]
        if is_tree:
            Lodgepole.bind_instance_lods(asset)
        mm.instance_count = render_entries.size()
        var instance_buffer := PackedFloat32Array()
        var instance_bounds := AABB()
        for i: int in render_entries.size():
            var r: Dictionary = render_entries[i]
            var p := Vector3(r.position[0], r.position[1], r.position[2])
            var basis := Basis(Vector3.UP, float(r.yaw))
            var local: Transform3D = Lodgepole.local_transform(r, str(asset[4])) if is_tree else Transform3D(Basis.from_scale(Vector3.ONE * float(r.scale)), Vector3.ZERO)
            var xf: Transform3D = Transform3D(basis, p - center) * local * asset[1]
            if not xf.is_finite():
                push_error("Vegetation transform is nonfinite: " + str(r.get("id", r.get("stable_id", "unknown"))))
                return -1
            var color := Color(float(Lodgepole.variation_key(r)) / 3.0, 1.0, 1.0, 1.0) if int(batch[2]) == -2 else Color.WHITE
            _append_instance(instance_buffer, xf, color)
            if is_tree:
                var height_m: float = float(Lodgepole.display_dimensions(r).height_m)
                instance_buffer.append_array(PackedFloat32Array([p.x, p.y + height_m * 0.5, p.z, 1.0]))
            var bounds: AABB = xf * mm.mesh.get_aabb()
            instance_bounds = bounds if i == 0 else instance_bounds.merge(bounds)
        mm.buffer = instance_buffer
        mm.custom_aabb = instance_bounds.grow(0.7)
        assert(mm.buffer.size() == render_entries.size() * (20 if is_tree else 16), "Vegetation instance data lost")
        var node := MultiMeshInstance3D.new()
        node.name = key + "_%s_%d" % [str(asset[4]), int(asset[2])] if is_tree else key
        if int(batch[2]) >= 0:
            node.name += "_variant%d" % int(batch[2]) if str(asset[4]) != "Billboard" else "_view%d" % int(batch[2])
        if int(batch[2]) == -2:
            node.set_meta("packed_impostor_variants", 4)
        node.set_meta("vegetation_kind", kind)
        if is_tree:
            node.set_meta("tree_archetype", form)
            node.set_meta("tree_part", str(asset[4]))
            node.set_meta("display_envelope_class", "transferred_or_photo_authored_unknown_local_error")
            if float(asset[2]) == 0.0 and str(asset[4]) != "Bole":
                node.set_meta("architecture_variant", int(batch[2]))
            node.set_meta("lod_begin_m", float(asset[2]))
            tree_bin_bounds = instance_bounds if tree_meshes.is_empty() else tree_bin_bounds.merge(instance_bounds)
            tree_meshes.append(node)
        node.multimesh = mm
        node.position = node_position
        node.visibility_range_end = 150.0 if kind == "grass" else 2800.0
        if asset.size() > 2:
            node.visibility_range_begin = asset[2]
            node.visibility_range_end = asset[3]
            if float(asset[2]) >= float(Lodgepole.LOD_RANGES[2][0]):
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
    if is_tree:
        _emit_trunk_colliders(group, entries, form, Vector2(center.x - node_position.x, center.z - node_position.z))
    return emitted

## Trunk colliders follow the bake's core-extent cylinder rule in absolute coordinates.
static func _emit_trunk_colliders(group: Node3D, entries: Array, form: String, tile_origin: Vector2) -> void:
    for r: Dictionary in entries:
        if absf(float(r.position[0])) > TRUNK_LIMIT_X_M or absf(float(r.position[2])) > TRUNK_LIMIT_Z_M:
            continue
        var tree_transform: Transform3D = Lodgepole.local_transform(r, "Bole")
        var tree_height: float = float(Lodgepole.metadata().archetypes[form].height_m) * tree_transform.basis.y.length()
        var collision_height: float = minf(3.0, tree_height)
        var body := StaticBody3D.new()
        body.position = Vector3(float(r.position[0]) - tile_origin.x, float(r.position[1]) + collision_height * 0.5, float(r.position[2]) - tile_origin.y)
        body.set_meta("tree_height_m", tree_height)
        var collider := CollisionShape3D.new()
        var cylinder := CylinderShape3D.new()
        cylinder.radius = float(Lodgepole.metadata().archetypes[form].dbh_m) * tree_transform.basis.x.length() * 0.5
        cylinder.height = collision_height
        collider.shape = cylinder
        body.add_child(collider)
        group.add_child(body)

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
