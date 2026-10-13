extends SceneTree
## Validate saved instance arrays without dummy-renderer getters, read-only against a complete offline bake. Buffer order: RenderingServer.multimesh_set_buffer. Run: godot --headless --path . --script tools/validate_multimesh.gd

const SCENE_PATH := "res://scenes/authored_world.tscn"
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
	# Three pine meshes plus one distant representation; each group occupies a 128 m tile.
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
		if not kind in ["pine", "grass", "rock", "log"]:
			fail("unsupported_placement_kind", id, kind)
			continue
		if not finite_vector(p) or not is_finite(float(r.scale)) or float(r.scale) <= 0:
			fail("invalid_placement", id, "Nonfinite position or nonpositive scale")
			continue
		var copies := 4 if kind == "pine" else 1
		records[id] = r
		seen[id] = 0
		expected_instances += copies
		expected_kind_counts[kind] = int(expected_kind_counts.get(kind, 0)) + copies
		min_expected_y = minf(min_expected_y, p.y)
		max_expected_y = maxf(max_expected_y, p.y)
		var cell := cell_for(p)
		if not position_index.has(cell):
			position_index[cell] = []
		position_index[cell].append(id)
		var key := "%s:%d:%d:%d" % [kind, int(r.get("variant", 0)), int(floor(p.x / 256.0)), int(floor(p.z / 256.0))]
		bins[key] = copies
	for copies: int in bins.values():
		expected_resources += copies
	for pool: Dictionary in world.get("pools", []):
		if not pool.get("thermal", false):
			continue
		var count := 45 if int(pool.source_id) in [1030, 1034] else 10
		expected_steam[str(pool.id)] = {"count": count, "pool": pool}
		expected_instances += count
		expected_resources += 1
	expected_kind_counts["steam"] = expected_instances - int(expected_kind_counts.get("pine", 0)) - int(expected_kind_counts.get("grass", 0)) - int(expected_kind_counts.get("rock", 0)) - int(expected_kind_counts.get("log", 0))

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

func mesh_kind(mesh: Mesh) -> String:
	# Source mesh families disambiguate co-located tree/log/rock records. Source pines ~15 m high; grass clumps under 0.4 m. Node names unreliable after LOD renaming.
	if mesh is QuadMesh:
		return "pine"
	if mesh is CylinderMesh:
		return "log"
	if mesh is SphereMesh:
		return "rock"
	return "pine" if mesh.get_aabb().size.y > 2.0 else "grass"

func validate_vegetation(node: MultiMeshInstance3D, xf: Transform3D, world_xf: Transform3D, path: String, index: int) -> void:
	var p := world_xf.origin
	var kind := mesh_kind(node.multimesh.mesh)
	var id := nearest_record(p, kind)
	if id.is_empty():
		fail("unmatched_authored_origin", path, "World XZ does not match a fixed placement: " + str(p), index)
		return
	var r: Dictionary = records[id]
	seen[id] = int(seen[id]) + 1
	actual_kind_counts[kind] = int(actual_kind_counts.get(kind, 0)) + 1
	var expected := Vector3(r.position[0], r.position[1], r.position[2])
	var scale := float(r.scale)
	if kind == "pine" and node.multimesh.mesh is QuadMesh:
		expected.y += 7.7 * scale
	elif kind == "log":
		expected.y += 0.2 * scale
	var error := p.distance_to(expected)
	max_position_error = maxf(max_position_error, error)
	if error > POSITION_TOLERANCE:
		fail("authored_position_mismatch", path, "%s differs by %.6f m" % [id, error], index)
	var scales := Vector3(xf.basis.x.length(), xf.basis.y.length(), xf.basis.z.length())
	if maxf(absf(scales.x - scale), maxf(absf(scales.y - scale), absf(scales.z - scale))) > 0.002:
		fail("authored_scale_mismatch", path, "%s expected %.5f, decoded %s" % [id, scale, str(scales)], index)

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
		if not mm.use_colors or mm.use_custom_data:
			fail("vegetation_format_flags", path, "Expected colors only")
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
		else:
			validate_vegetation(node, xf, world_xf, path, index)

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
	prepare_expectations()
	if failure_total == 0:
		var scene: PackedScene = load(SCENE_PATH)
		if scene == null:
			fail("missing_baked_scene", SCENE_PATH, "Run the offline bake first")
		else:
			var world := scene.instantiate()
			# Compose saved Node3D transforms on the CPU.
			walk(world)
			world.free()
	for id: String in records:
		var expected := 4 if str(records[id].kind) == "pine" else 1
		if int(seen[id]) != expected:
			fail("placement_multiplicity", id, "Expected %d representations, found %d" % [expected, int(seen[id])])
	for id: String in expected_steam:
		if int(seen_steam.get(id, 0)) != int(expected_steam[id].count):
			fail("steam_multiplicity", id, "Expected %d, found %d" % [int(expected_steam[id].count), int(seen_steam.get(id, 0))])
	if actual_resources != expected_resources:
		fail("resource_count_mismatch", SCENE_PATH, "Expected %d, found %d" % [expected_resources, actual_resources])
	if actual_instances != expected_instances:
		fail("instance_count_mismatch", SCENE_PATH, "Expected %d, found %d" % [expected_instances, actual_instances])
	if actual_instances > 0 and zero_local_origins == actual_instances:
		fail("all_origins_zero", SCENE_PATH, "All serialized translations are zero")
	var report := {
		"ok": failure_total == 0,
		"engine": Engine.get_version_info().string,
		"validation_method": "CPU decode of saved MultiMesh.buffer; no renderer instance-transform/AABB getters",
		"scene_sha256": FileAccess.get_sha256(SCENE_PATH),
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
