extends SceneTree
## Saved MultiMesh buffer validation against authored sources.

const Library := preload("res://scripts/lodgepole_library.gd")
const Canopy := preload("res://scripts/canopy_surface.gd")
const Floor := preload("res://scripts/forest_floor.gd")
const Receipt := preload("res://scripts/verification_receipt.gd")
const CANOPY_PATH := "res://data/lidar_canopy/unresolved_render_canopy.json"
var canopy_source: Dictionary = {}
var canopy_anchors: Dictionary = {}
var floor_records: Dictionary = {}
var expected_parts: Dictionary = {}
var seen_parts: Dictionary = {}
var asset_transforms: Dictionary = {}
var canopy_mesh_arrays: Dictionary = {}
const OUTPUT_PATH := "res://tests/multimesh_validation.json"
const POSITION_TOLERANCE := 0.01
const BOUNDS_TOLERANCE := 0.003
const MAX_EXAMPLES := 100
var failures: Array[Dictionary] = []
var failure_counts: Dictionary = {}
var failure_total := 0
var records: Dictionary = {}
var position_index: Dictionary = {}
var seen: Dictionary = {}
var expected_steam: Dictionary = {}
var seen_steam: Dictionary = {}
var expected_instances := 0
var expected_resources := 0
var actual_instances := 0
var actual_resources := 0
var vegetation_instances := 0
var steam_instances := 0
var zero_local_origins := 0
var buffer_floats := 0
var expected_kind_counts: Dictionary = {}
var actual_kind_counts: Dictionary = {}
var mesh_bounds_cache: Dictionary = {}
var world_half := 2048.0
var min_expected_y := 0.0
var max_expected_y := 0.0
var min_origin := Vector3(INF, INF, INF)
var max_origin := Vector3(-INF, -INF, -INF)
var max_position_error := 0.0
var max_bounds_error := 0.0
var min_determinant := INF
var max_determinant := 0.0
var started := 0

func _initialize() -> void:
	call_deferred("verify")

func fail(code: String, path: String, detail: String, instance := -1) -> void:
	failure_total += 1
	failure_counts[code] = int(failure_counts.get(code, 0)) + 1
	if failures.size() < MAX_EXAMPLES:
		failures.append({"code": code, "node": path, "instance": instance, "detail": detail})

func read_json(path: String) -> Dictionary:
	var result: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not result is Dictionary:
		fail("invalid_input_json", path, "Expected a JSON object")
		return {}
	return result

func finite_vector(v: Vector3) -> bool:
	return is_finite(v.x) and is_finite(v.y) and is_finite(v.z)

func vec_list(v: Vector3) -> Array:
	return [v.x, v.y, v.z] if finite_vector(v) else []

func cell_for(v: Vector3) -> Vector2i:
	return Vector2i(int(floor(v.x)), int(floor(v.z)))

func prepare_expectations() -> void:
	var world := read_json("res://data/world.json")
	world_half = float(world.get("georeference", {}).get("extent", 4096.0)) * 0.5
	var source := read_json("res://data/placements.json")
	var overrides := read_json("res://data/placement_overrides.json")
	var pending: Array = []
	for category in ["trees", "grass", "rocks", "logs"]:
		pending.append_array(source.get(category, []))
	pending.append_array(overrides.get("add", []))
	canopy_source = Canopy.read_source(CANOPY_PATH)
	if canopy_source.is_empty():
		fail("canopy_source", CANOPY_PATH, "Validated source is unavailable")
		return
	var detail_origin := Vector2(canopy_source.first_cell_x_m, canopy_source.first_cell_z_m) - Vector2.ONE * float(canopy_source.cell_size_m) * 0.5
	var detail_bounds := Rect2(detail_origin, Vector2(canopy_source.width, canopy_source.height) * float(canopy_source.cell_size_m))
	var bins: Dictionary = {}
	for original: Dictionary in pending:
		if original.id in overrides.get("remove", []):
			continue
		var r: Dictionary = overrides.get("replace", {}).get(original.id, original)
		var id := str(r.id)
		if records.has(id):
			fail("duplicate_placement_id", id, "Active authored IDs must be unique")
			continue
		var p := Vector3(r.position[0], r.position[1], r.position[2])
		var kind := str(r.kind)
		if not kind in ["pine", "snag", "grass", "rock", "log"]:
			fail("unsupported_placement_kind", id, kind)
			continue
		if not finite_vector(p) or not is_finite(float(r.scale)) or float(r.scale) <= 0:
			fail("invalid_placement", id, "Nonfinite position or nonpositive scale")
			continue
		records[id] = r
		seen[id] = 0
		min_expected_y = minf(min_expected_y, p.y)
		max_expected_y = maxf(max_expected_y, p.y)
		var cell := cell_for(p)
		if not position_index.has(cell):
			position_index[cell] = []
		position_index[cell].append(id)
		var tree := kind in ["pine", "snag"]
		var cell_m := 64.0 if tree and detail_bounds.has_point(Vector2(p.x, p.z)) else 256.0
		var form := Library.archetype(r) if tree else ""
		var variant := 0 if tree else int(r.get("variant", 0))
		var bin_key := "%s:%s:%d:%d:%d:%d" % [kind, form, variant, int(cell_m), floori(p.x / cell_m), floori(p.z / cell_m)]
		var parts: Array = []
		if tree:
			for part: String in Library.PARTS:
				if part == "NeedleCards" and form == "snag":
					continue
				for lod: float in ([180.0] if part == "Billboard" else [0.0, 18.0, 65.0]):
					var part_key := "%s:%d" % [part, int(lod)]
					parts.append(part_key)
					var architecture := Library.variation_key(r) if part in ["Branches", "NeedleCards"] else "all"
					bins[bin_key + ":" + part_key + ":" + architecture] = true
		else:
			parts.append("single")
			bins[bin_key] = true
		expected_parts[id] = parts
		expected_instances += parts.size()
		expected_kind_counts[kind] = int(expected_kind_counts.get(kind, 0)) + parts.size()
	var floor_source := Floor.read_source("res://data/forest_floor.json")
	if floor_source.is_empty():
		fail("floor_source", "forest_floor", "Validated source is unavailable")
		return
	for r: Dictionary in floor_source.records:
		var id := "floor:" + str(r.id)
		floor_records[id] = r
		var parts: Array = []
		var p := Vector3(r.position[0], r.position[1], r.position[2])
		var variant := Library.variation_key(r) if r.kind == "snag" else "0"
		var key := "floor:%s:%s:%s:%d:%d" % [r.kind, str(r.get("guild", "woody")), variant, floori(p.x / Floor.BIN_SIZE_M), floori(p.z / Floor.BIN_SIZE_M)]
		for asset: Array in Floor._assets(r):
			var part := "%s:%d" % [asset[4], int(asset[2])]
			parts.append(part)
			bins[key + ":" + part] = true
		expected_parts[id] = parts
		expected_instances += parts.size()
		expected_kind_counts["floor"] = int(expected_kind_counts.get("floor", 0)) + parts.size()
	for index: int in canopy_source.unresolved_cells.size():
		if canopy_source.unresolved_cells[index] == 0:
			continue
		var center := Vector2(canopy_source.first_cell_x_m + (index % canopy_source.width) * canopy_source.cell_size_m, canopy_source.first_cell_z_m + int(index / canopy_source.width) * canopy_source.cell_size_m)
		canopy_anchors[index] = Canopy._cluster_anchor(canopy_source, index)
		var id := "canopy:" + str(index)
		expected_parts[id] = ["0", "1", "2"]
		for lod: int in 3:
			bins["canopy:%d:%d:%d" % [floori(center.x / Canopy.CLUSTER_TILE_M), floori(center.y / Canopy.CLUSTER_TILE_M), lod]] = true
		expected_instances += 3
		expected_kind_counts["canopy"] = int(expected_kind_counts.get("canopy", 0)) + 3
	expected_resources = bins.size()
	for pool: Dictionary in world.get("pools", []):
		if not pool.get("thermal", false):
			continue
		var count := 45 if int(pool.source_id) in [1030, 1034] else 10
		expected_steam[str(pool.id)] = {"count": count, "pool": pool}
		expected_instances += count
		expected_resources += 1
	expected_kind_counts["steam"] = 0
	for entry: Dictionary in expected_steam.values():
		expected_kind_counts["steam"] += int(entry.count)

func decode_transform(data: PackedFloat32Array, at: int) -> Transform3D:
	# Read row-major serialization into column-vector Basis.
	var x := Vector3(data[at], data[at + 4], data[at + 8])
	var y := Vector3(data[at + 1], data[at + 5], data[at + 9])
	var z := Vector3(data[at + 2], data[at + 6], data[at + 10])
	return Transform3D(Basis(x, y, z), Vector3(data[at + 3], data[at + 7], data[at + 11]))

func nearest_record(p: Vector3, kind: String) -> String:
	var best := ""
	var best_distance := POSITION_TOLERANCE * POSITION_TOLERANCE
	var center := cell_for(p)
	for dz in range(-1, 2):
		for dx in range(-1, 2):
			for id: String in position_index.get(center + Vector2i(dx, dz), []):
				var r: Dictionary = records[id]
				if str(r.kind) != kind:
					continue
				var distance := pow(p.x - float(r.position[0]), 2) + pow(p.z - float(r.position[2]), 2)
				if distance <= best_distance:
					best = id
					best_distance = distance
	return best

func bounds_overflow(outer: AABB, inner: AABB) -> float:
	var lo := outer.position - inner.position
	var hi := inner.end - outer.end
	return maxf(0.0, maxf(maxf(lo.x, maxf(lo.y, lo.z)), maxf(hi.x, maxf(hi.y, hi.z))))

func mark_part(id: String, part: String, path: String, index: int) -> void:
	if part not in expected_parts.get(id, []):
		fail("unexpected_representation", path, id + ":" + part, index)
	var key := id + ":" + part
	seen_parts[key] = int(seen_parts.get(key, 0)) + 1

func compare_transform(actual: Transform3D, expected: Transform3D, path: String, id: String, index: int) -> void:
	var error := actual.origin.distance_to(expected.origin)
	max_position_error = maxf(max_position_error, error)
	if error > POSITION_TOLERANCE:
		fail("authored_position_mismatch", path, "%s differs by %.6f m" % [id, error], index)
	var basis_error := maxf((actual.basis.x - expected.basis.x).length(), maxf((actual.basis.y - expected.basis.y).length(), (actual.basis.z - expected.basis.z).length()))
	if basis_error > 0.002:
		fail("authored_basis_mismatch", path, "%s differs by %.6f" % [id, basis_error], index)

func tree_asset_transform(record: Dictionary, part: String, lod: float) -> Transform3D:
	var form := Library.archetype(record)
	var variant := int(Library.variation_key(record))
	var key := "%s:%d:%s:%d" % [form, variant, part, int(lod)]
	if not asset_transforms.has(key):
		var assets: Array
		if part == "Billboard":
			assets = [Library.load_billboard_batch(form, false)]
		elif part in ["Branches", "NeedleCards"]:
			assets = Library.load_architecture(form, variant, 0 if lod == 0.0 else (1 if lod == 18.0 else 2))
		else:
			assets = Library.load_assets(form, variant)
		for asset: Array in assets:
			if str(asset[4]) == part and float(asset[2]) == lod:
				asset_transforms[key] = asset[1]
		if not asset_transforms.has(key):
			fail("missing_tree_asset", key, "No matching source part and LOD")
	return asset_transforms.get(key, Transform3D.IDENTITY)

func validate_vegetation(node: MultiMeshInstance3D, world_xf: Transform3D, path: String, index: int) -> void:
	var kind := str(node.get_meta("vegetation_kind", ""))
	var id := nearest_record(world_xf.origin, kind)
	if id.is_empty():
		fail("unmatched_authored_origin", path, "World XZ does not match a fixed placement: " + str(world_xf.origin), index)
		return
	var r: Dictionary = records[id]
	seen[id] = int(seen[id]) + 1
	actual_kind_counts[kind] = int(actual_kind_counts.get(kind, 0)) + 1
	var p := Vector3(r.position[0], r.position[1], r.position[2])
	var local := Transform3D(Basis.from_scale(Vector3.ONE * float(r.scale)), Vector3.ZERO)
	var asset := Transform3D.IDENTITY
	var part_key := "single"
	if kind in ["pine", "snag"]:
		var part := str(node.get_meta("tree_part", ""))
		var lod := float(node.get_meta("lod_begin_m", -1.0))
		part_key = "%s:%d" % [part, int(lod)]
		local = Library.local_transform(r, part)
		asset = tree_asset_transform(r, part, lod)
		if str(node.get_meta("tree_archetype", "")) != Library.archetype(r):
			fail("tree_archetype", path, id, index)
	elif kind == "log":
		asset = Transform3D(Basis(Vector3.FORWARD, PI / 2.0), Vector3(0, 0.2, 0))
	mark_part(id, part_key, path, index)
	compare_transform(world_xf, Transform3D(Basis(Vector3.UP, float(r.yaw)), p) * local * asset, path, id, index)

func validate_floor(node: MultiMeshInstance3D, world_xf: Transform3D, path: String, index: int) -> void:
	var ids: Array = node.get_meta("source_ids", [])
	if ids.size() != node.multimesh.instance_count:
		fail("floor_source_ids", path, "Source identity count differs")
		return
	var id := "floor:" + str(ids[index])
	if not floor_records.has(id):
		fail("unknown_floor_source", path, id, index)
		return
	var record: Dictionary = floor_records[id]
	var part := str(node.get_meta("floor_part", ""))
	var lod := float(node.get_meta("root_visibility_range", [-1.0])[0])
	var part_key := "%s:%d" % [part, int(lod)]
	mark_part(id, part_key, path, index)
	var matched := false
	for asset: Array in Floor._assets(record):
		if str(asset[4]) == part and float(asset[2]) == lod:
			compare_transform(world_xf, Floor.instance_transform(record, part, asset[1]), path, id, index)
			matched = true
	if not matched:
		fail("floor_source_part", path, id + ":" + part_key, index)
	actual_kind_counts["floor"] = int(actual_kind_counts.get("floor", 0)) + 1

func validate_canopy(node: MultiMeshInstance3D, world_xf: Transform3D, path: String, index: int) -> void:
	var indices: PackedInt32Array = node.get_meta("source_indices", PackedInt32Array())
	if indices.size() != node.multimesh.instance_count:
		fail("canopy_source_indices", path, "Source identity count differs")
		return
	var source_index := indices[index]
	var id := "canopy:" + str(source_index)
	if not canopy_anchors.has(source_index):
		fail("excluded_canopy_source", path, id, index)
		return
	mark_part(id, str(node.get_meta("cluster_lod", -1)), path, index)
	var anchor: Vector2 = canopy_anchors[source_index]
	var top: float = canopy_source.canopy_top_scene_y[source_index]
	var depth: float = (top - canopy_source.ground_scene_y[source_index]) * Canopy.CLUSTER_LIVE_CROWN_RATIO
	var seed: int = (source_index * 1103515245 + 12345) & 0x7fffffff
	var yaw := float(seed) / 2147483647.0 * TAU
	var basis := Basis(Vector3.UP, yaw).scaled_local(Vector3(1.0, depth / Canopy.CLUSTER_UNIT_DEPTH_M, 1.0))
	compare_transform(world_xf, Transform3D(basis, Vector3(anchor.x, top, anchor.y)), path, id, index)
	actual_kind_counts["canopy"] = int(actual_kind_counts.get("canopy", 0)) + 1

func deform(v: Vector3, c: Color, uv: Vector2, depth: float, custom: Vector4, near: bool) -> Vector3:
	var crown_depth := minf(depth,2.0)
	if c.g > 0.5 and c.b > 0.25:
		var stem_root := Vector3(custom.x,custom.y*depth,custom.z)
		var root_radius := clampf(Vector2(stem_root.x,stem_root.z).length()*0.03,0.018,0.065) if custom.w > 0.5 else clampf(depth/112.0,0.025,0.14)
		var joint_radius := minf(root_radius,0.045)
		var start := Vector3(0,-crown_depth*1.05,0) if c.b > 0.75 else Vector3.ZERO
		var end := stem_root if c.b > 0.75 else Vector3(0,-crown_depth*1.05,0)
		var delta := end-start
		var axis := delta.normalized() if delta.length()>0.00001 else Vector3.DOWN
		var across := axis.cross(Vector3.UP if absf(axis.y)<0.9 else Vector3.RIGHT).normalized()
		var radial := across*cos(uv.y)+axis.cross(across)*sin(uv.y)
		return (start.lerp(end,uv.x)+radial*lerpf(joint_radius if c.b>0.75 else 0.006,root_radius if c.b>0.75 else joint_radius,uv.x))/Vector3(1,depth,1)
	elif near and (c.g<0.5 or c.b<0.25):
		var size_scale := minf(1.0,crown_depth/0.80)
		var half_card := 0.4*size_scale
		var anchor := lerpf(half_card,crown_depth-half_card,c.r)
		v.y=(-anchor+(v.y+c.r)*size_scale)/depth
	else:
		v.y*=crown_depth/depth
	return v

func canopy_bounds_overflow(node: MultiMeshInstance3D, xf: Transform3D, data: PackedFloat32Array, at: int) -> float:
	var mesh := node.multimesh.mesh
	var key := mesh.get_instance_id()
	if not canopy_mesh_arrays.has(key):
		canopy_mesh_arrays[key] = mesh.surface_get_arrays(0)
	var arrays: Array = canopy_mesh_arrays[key]
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var colors: PackedColorArray = arrays[Mesh.ARRAY_COLOR]
	var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	var custom := Vector4(data[at + 12], data[at + 13], data[at + 14], data[at + 15])
	var inner := AABB()
	for j: int in vertices.size():
		var p := xf * deform(vertices[j], colors[j], uvs[j], xf.basis.y.length(), custom, int(node.get_meta("cluster_lod")) < 2)
		inner = AABB(p, Vector3.ZERO) if j == 0 else inner.expand(p)
	return bounds_overflow(node.multimesh.custom_aabb, inner)

func validate_steam(node: MultiMeshInstance3D, p: Vector3, path: String, index: int) -> void:
	var id := str(node.name).trim_prefix("Steam_")
	if not expected_steam.has(id):
		fail("unknown_steam_pool", path, id, index)
		return
	var pool: Dictionary = expected_steam[id].pool
	var min_x := INF
	var max_x := -INF
	var min_z := INF
	var max_z := -INF
	for point: Array in pool.ring:
		min_x = minf(min_x, float(point[0]))
		max_x = maxf(max_x, float(point[0]))
		min_z = minf(min_z, float(point[1]))
		max_z = maxf(max_z, float(point[1]))
	if p.x < min_x - 1.0 or p.x > max_x + 1.0 or p.z < min_z - 1.0 or p.z > max_z + 1.0:
		fail("steam_outside_source_pool", path, str(p), index)
	if absf(p.y - float(pool.center[1]) - 2.5) > POSITION_TOLERANCE:
		fail("steam_height_mismatch", path, str(p), index)

func validate_node(node: MultiMeshInstance3D, parent_xf: Transform3D, path: String) -> void:
	actual_resources += 1
	var mm := node.multimesh
	if mm == null or mm.mesh == null:
		fail("missing_multimesh_or_mesh", path, "Instance resource or source geometry missing")
		return
	var count := mm.instance_count
	actual_instances += count
	if count <= 0:
		fail("empty_multimesh", path, str(count))
		return
	if mm.transform_format != MultiMesh.TRANSFORM_3D:
		fail("unexpected_transform_format", path, "This world requires 3D transforms")
		return
	var stride := 12 + (4 if mm.use_colors else 0) + (4 if mm.use_custom_data else 0)
	var data := mm.buffer
	buffer_floats += data.size()
	if data.size() != count * stride:
		fail("buffer_length_mismatch", path, "Expected %d floats, got %d" % [count * stride, data.size()])
		return
	var all_finite := true
	for value: float in data:
		if not is_finite(value):
			all_finite = false
			break
	if not all_finite:
		fail("nonfinite_buffer", path, "NaN/Infinity in saved instance data")
		return
	if mm.visible_instance_count == 0 or mm.visible_instance_count > count:
		fail("invalid_visible_count", path, str(mm.visible_instance_count))
	var box := mm.custom_aabb
	if not finite_vector(box.position) or not finite_vector(box.size) or box.size.x <= 0 or box.size.y <= 0 or box.size.z <= 0:
		fail("missing_or_invalid_explicit_aabb", path, str(box))
		return
	if box.size.x > world_half * 2 + 256 or box.size.z > world_half * 2 + 256 or box.size.y > 1000:
		fail("implausible_aabb_extent", path, str(box))
	var mesh_key := mm.mesh.get_instance_id()
	if not mesh_bounds_cache.has(mesh_key):
		mesh_bounds_cache[mesh_key] = mm.mesh.get_aabb()
	var source_box: AABB = mesh_bounds_cache[mesh_key]
	if not finite_vector(source_box.position) or not finite_vector(source_box.size) or source_box.size.length() < 0.00001:
		fail("invalid_source_mesh_bounds", path, str(source_box))
		return
	var is_steam := str(node.name).begins_with("Steam_")
	if is_steam:
		steam_instances += count
		actual_kind_counts["steam"] = int(actual_kind_counts.get("steam", 0)) + count
		var pool_id := str(node.name).trim_prefix("Steam_")
		seen_steam[pool_id] = int(seen_steam.get(pool_id, 0)) + count
		if not mm.use_custom_data or mm.use_colors:
			fail("steam_format_flags", path, "Expected custom data only")
	else:
		vegetation_instances += count
		var canopy := node.has_meta("canopy_part")
		var floor_layer := node.has_meta("floor_kind")
		var tree := str(node.get_meta("vegetation_kind", "")) in ["pine", "snag"]
		if mm.use_colors != (not canopy and not floor_layer) or mm.use_custom_data != (canopy or tree):
			fail("family_format_flags", path, "Color/custom flags differ from the family contract")
	for index in count:
		var at := index * stride
		var xf := decode_transform(data, at)
		var world_xf := parent_xf * xf
		var p := world_xf.origin
		min_origin = min_origin.min(p)
		max_origin = max_origin.max(p)
		if xf.origin.length_squared() < 0.0000001:
			zero_local_origins += 1
		var determinant := xf.basis.determinant()
		min_determinant = minf(min_determinant, determinant)
		max_determinant = maxf(max_determinant, determinant)
		if determinant <= 0.00000001:
			fail("collapsed_or_reversed_basis", path, str(determinant), index)
		if absf(p.x) > world_half + 128 or absf(p.z) > world_half + 128 or p.y < min_expected_y - 128 or p.y > max_expected_y + 128:
			fail("implausible_world_origin", path, str(p), index)
		var overflow := bounds_overflow(box, xf * source_box)
		if overflow > BOUNDS_TOLERANCE and node.has_meta("canopy_part"):
			overflow = canopy_bounds_overflow(node, xf, data, at)
		max_bounds_error = maxf(max_bounds_error, overflow)
		if overflow > BOUNDS_TOLERANCE:
			fail("instance_outside_explicit_aabb", path, "Protrudes %.6f m" % overflow, index)
		if mm.use_colors and (data[at + 15] <= 0.0 or data[at + 12] + data[at + 13] + data[at + 14] <= 0.0):
			fail("invisible_instance_color", path, "Zero alpha or nonpositive RGB", index)
		if is_steam:
			var custom_at := at + 12 + (4 if mm.use_colors else 0)
			if mm.use_custom_data and (data[custom_at] < 0.0 or data[custom_at] >= 1.0):
				fail("steam_phase_out_of_range", path, str(data[custom_at]), index)
			validate_steam(node, p, path, index)
		elif node.has_meta("canopy_part"):
			validate_canopy(node, world_xf, path, index)
		elif node.has_meta("floor_kind"):
			validate_floor(node, world_xf, path, index)
		else:
			validate_vegetation(node, world_xf, path, index)

func walk(node: Node, inherited := Transform3D.IDENTITY, prefix := "") -> void:
	var xf := inherited
	if node is Node3D:
		xf = inherited * node.transform
	var path := prefix + "/" + str(node.name)
	if node is MultiMeshInstance3D:
		validate_node(node, xf, path)
	for child: Node in node.get_children():
		walk(child, xf, path)

func verify() -> void:
	started = Time.get_ticks_msec()
	# Validate the scene file the runtime loader resolves.
	var scene_path := Receipt.scene_path()
	prepare_expectations()
	if failure_total == 0:
		var scene: PackedScene = load(scene_path)
		if scene == null:
			fail("missing_baked_scene", scene_path, "Run the offline bake first")
		else:
			var world := scene.instantiate()
			# Compose saved Node3D transforms on the CPU.
			walk(world)
			world.free()
	for id: String in expected_parts:
		for part: String in expected_parts[id]:
			var count := int(seen_parts.get(id + ":" + part, 0))
			if count != 1:
				fail("representation_multiplicity", id, "Expected one %s, found %d" % [part, count])
	for id: String in expected_steam:
		if int(seen_steam.get(id, 0)) != int(expected_steam[id].count):
			fail("steam_multiplicity", id, "Expected %d, found %d" % [int(expected_steam[id].count), int(seen_steam.get(id, 0))])
	if actual_resources != expected_resources:
		fail("resource_count_mismatch", scene_path, "Expected %d, found %d" % [expected_resources, actual_resources])
	if actual_instances != expected_instances:
		fail("instance_count_mismatch", scene_path, "Expected %d, found %d" % [expected_instances, actual_instances])
	if actual_instances > 0 and zero_local_origins == actual_instances:
		fail("all_origins_zero", scene_path, "All serialized translations are zero")
	var report := {
		"ok": failure_total == 0,
		"schema": Receipt.SCHEMA,
		"source_sha256": Receipt.source_hashes(),
		"engine": Engine.get_version_info().string,
		"validation_method": "CPU decode of saved MultiMesh.buffer; no renderer instance-transform/AABB getters",
		"scene_path": scene_path,
		"scene_sha256": FileAccess.get_sha256(scene_path),
		"placements_sha256": FileAccess.get_sha256("res://data/placements.json"),
		"overrides_sha256": FileAccess.get_sha256("res://data/placement_overrides.json"),
		"expected_multimesh_resources": expected_resources,
		"actual_multimesh_resources": actual_resources,
		"expected_instance_slots": expected_instances,
		"actual_instance_slots": actual_instances,
		"expected_kind_slots": expected_kind_counts,
		"actual_kind_slots": actual_kind_counts,
		"active_authored_placements": records.size(),
		"vegetation_slots": vegetation_instances,
		"steam_slots": steam_instances,
		"serialized_buffer_floats": buffer_floats,
		"zero_local_origins": zero_local_origins,
		"world_origin_min_m": vec_list(min_origin),
		"world_origin_max_m": vec_list(max_origin),
		"maximum_authored_position_error_m": max_position_error,
		"maximum_aabb_protrusion_m": max_bounds_error,
		"minimum_basis_determinant": min_determinant if is_finite(min_determinant) else 0.0,
		"maximum_basis_determinant": max_determinant,
		"position_tolerance_m": POSITION_TOLERANCE,
		"bounds_tolerance_m": BOUNDS_TOLERANCE,
		"failure_count": failure_total,
		"failure_counts_by_code": failure_counts,
		"failures": failures,
		"failure_examples_truncated": failure_total > failures.size(),
		"elapsed_seconds": float(Time.get_ticks_msec() - started) / 1000.0
	}
	DirAccess.make_dir_recursive_absolute("res://tests")
	var output := FileAccess.open(OUTPUT_PATH, FileAccess.WRITE)
	if output == null:
		push_error("Cannot write " + OUTPUT_PATH)
		quit(2)
		return
	output.store_string(JSON.stringify(report, "  "))
	output.close()
	print("MULTIMESH_VALIDATION ok=", report.ok, " resources=", actual_resources, "/", expected_resources, " instance_slots=", actual_instances, "/", expected_instances, " failures=", failure_total, " seconds=", report.elapsed_seconds)
	if failure_total > 0:
		print("Failure counts: ", JSON.stringify(failure_counts))
	quit(0 if failure_total == 0 else 1)
