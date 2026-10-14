extends SceneTree
## Validate authored forest-floor geometry and separate counts.

const Floor := preload("res://scripts/forest_floor.gd")
var checks := 0
var failures: Array[String] = []
var instance_slots := 0
var resources := 0
var counts: Dictionary = {}
var mesh_cache: Dictionary = {}

func _initialize() -> void:
	call_deferred("verify")

func check(condition: bool, detail: String) -> void:
	checks += 1
	if not condition:
		failures.append(detail)

func verify() -> void:
	var started := Time.get_ticks_msec()
	var arguments := OS.get_cmdline_user_args()
	var source_path := ""
	var output_path := "user://forest_floor_validation.json"
	for at: int in arguments.size():
		if arguments[at] == "--data" and at + 1 < arguments.size():
			source_path = arguments[at + 1]
		if arguments[at] == "--out" and at + 1 < arguments.size():
			output_path = arguments[at + 1]
	var fixture := make_fixture()
	validate(fixture)
	var fixture_slots := instance_slots
	if "--negative" in arguments:
		negative_controls(fixture)
	if not source_path.is_empty():
		instance_slots = 0
		resources = 0
		validate(source_path)
	var report := {"ok": failures.is_empty(), "engine": Engine.get_version_info().string, "checks": checks, "source_sha256": FileAccess.get_sha256(source_path) if not source_path.is_empty() else "fixture", "counts": counts, "instance_slots": instance_slots, "multimesh_resources": resources, "fixture_instance_slots": fixture_slots, "negative_controls": "--negative" in arguments, "evidence_class": "authored", "morphology": "illustrative_non_diagnostic", "dominant_crown_count_included": false, "scientific_acceptance": "not_yet_accepted", "elapsed_seconds": (Time.get_ticks_msec() - started) / 1000.0, "failures": failures}
	var output := FileAccess.open(output_path, FileAccess.WRITE)
	if output == null:
		push_error("Cannot write forest-floor validation report")
		quit(2)
		return
	output.store_string(JSON.stringify(report, "  "))
	output.close()
	print("FOREST_FLOOR_VALIDATION ok=", report.ok, " checks=", checks, " counts=", JSON.stringify(counts), " slots=", instance_slots, " seconds=", report.elapsed_seconds)
	for failure: String in failures:
		push_error(failure)
	quit(0 if failures.is_empty() else 1)

func validate(path: String) -> void:
	var source := Floor.read_source(path)
	check(not source.is_empty(), "Forest-floor source is invalid")
	if source.is_empty():
		return
	var parent := Node3D.new()
	get_root().add_child(parent)
	check(Floor.build(parent, path), "Forest-floor build fails")
	var group := parent.get_node_or_null("AuthoredForestFloor")
	check(group != null, "Authored forest-floor group is missing")
	if group == null:
		parent.free()
		return
	counts = source.counts
	check(group.get_meta("counts", {}) == counts, "Authored counts differ from input records")
	check(not group.get_meta("dominant_crown_count_included", true), "Authored floor counts include detected crowns")
	check(group.get_meta("evidence_class", "") == "authored" and group.get_meta("scientific_acceptance", "") == "not_yet_accepted", "Forest-floor provenance differs")
	check(group.get_meta("local_species_presence_claim", "") == "none", "Forest-floor layer makes a local species-presence claim")
	var records: Dictionary = {}
	var seen: Dictionary = {}
	for record: Dictionary in source.records:
		records[record.id] = record
		seen[record.id] = 0
	for node: Node in group.get_children():
		check(node is MultiMeshInstance3D and node.owner == parent, "Forest-floor node requires owned MultiMesh")
		if not node is MultiMeshInstance3D:
			continue
		resources += 1
		var multimesh: MultiMesh = node.multimesh
		check(multimesh != null and multimesh.mesh != null, "Forest-floor mesh is missing")
		if multimesh == null or multimesh.mesh == null:
			continue
		validate_mesh(multimesh.mesh)
		var ids: Array = node.get_meta("source_ids", [])
		var buffer := multimesh.buffer
		check(buffer.size() == multimesh.instance_count * 12 and ids.size() == multimesh.instance_count, "Forest-floor saved buffer or source IDs differ")
		check(node.visibility_range_end > node.visibility_range_begin, "Forest-floor LOD range is empty")
		if node.get_meta("floor_kind", "") == "understory_card":
			check(node.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF and node.visibility_range_end <= 110.0, "Understory requires bounded culling and disabled shadows")
		for index: int in ids.size():
			var id: String = ids[index]
			check(records.has(id), "Forest-floor instance has an unknown source ID")
			if not records.has(id):
				continue
			var record: Dictionary = records[id]
			var local := decode_transform(buffer, index * 12)
			var world: Transform3D = node.transform * local
			check(world.is_finite() and world.basis.determinant() > 0.0, "Forest-floor transform is nonfinite or reversed")
			var bounds: AABB = local * multimesh.mesh.get_aabb()
			check(multimesh.custom_aabb.grow(0.0001).encloses(bounds), "Forest-floor instance exceeds culling bounds")
			var position := Vector3(record.position[0], record.position[1], record.position[2])
			var part: String = node.get_meta("floor_part", "")
			var world_bounds: AABB = world * multimesh.mesh.get_aabb()
			if part != "Billboard":
				check(world_bounds.position.y >= position.y - 0.0001, "Forest-floor solid geometry lies below its ground anchor")
			if record.kind == "log":
				check(world.origin.distance_to(position + Vector3(0.0, record.size[0] * 0.5, 0.0)) < 0.0001, "Log center differs from source ground plus radius")
				check(absf(world_bounds.position.y - position.y) < 0.0001 and absf(world_bounds.end.y - position.y - record.size[0]) < 0.0001, "Log diameter or ground contact differs")
			elif record.kind == "understory_card":
				check(world.origin.distance_to(position) < 0.0001, "Understory source position differs")
				check(absf(world_bounds.position.y - position.y) < 0.0001 and absf(world_bounds.end.y - position.y - record.size[1]) < 0.0001, "Understory height or ground contact differs")
			elif part == "Bole":
				check(world.origin.distance_to(position) < 0.0001, "Snag source position differs")
				check(absf(world_bounds.position.y - position.y) < 0.0001 and absf(world_bounds.end.y - position.y - record.height_m) < 0.0001, "Snag height or ground contact differs")
			seen[id] += 1
			instance_slots += 1
	for id: String in records:
		var kind: String = records[id].kind
		var expected := 7 if kind == "snag" else (2 if kind == "understory_card" else 1)
		check(seen[id] == expected, "Forest-floor source ID has wrong LOD multiplicity: %s" % id)
	var packed := PackedScene.new()
	check(packed.pack(parent) == OK, "Forest-floor group does not pack")
	var restored := packed.instantiate()
	check(restored.get_node_or_null("AuthoredForestFloor") != null, "Packed forest-floor group is missing")
	restored.free()
	parent.free()

func validate_mesh(mesh: Mesh) -> void:
	if mesh_cache.has(mesh.get_instance_id()):
		return
	mesh_cache[mesh.get_instance_id()] = true
	for surface: int in mesh.get_surface_count():
		var material := mesh.surface_get_material(surface)
		check(material != null, "Forest-floor mesh material is missing")
		if material is ShaderMaterial:
			check(material.shader.resource_path == "res://shaders/foliage.gdshader" and material.get_shader_parameter("albedo_texture") is Texture2D, "Understory cutout material differs")
		elif material is StandardMaterial3D:
			check(material.albedo_texture != null and material.albedo_color.a > 0.0, "Woody or billboard material is invisible")
		var arrays := mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		check(vertices.size() > 0 and normals.size() == vertices.size(), "Forest-floor vertex arrays are empty")
		for index: int in vertices.size():
			check(vertices[index].is_finite() and normals[index].is_finite() and absf(normals[index].length() - 1.0) < 0.0001, "Forest-floor vertex or unit normal is invalid")

func decode_transform(buffer: PackedFloat32Array, at: int) -> Transform3D:
	return Transform3D(Basis(Vector3(buffer[at], buffer[at + 4], buffer[at + 8]), Vector3(buffer[at + 1], buffer[at + 5], buffer[at + 9]), Vector3(buffer[at + 2], buffer[at + 6], buffer[at + 10])), Vector3(buffer[at + 3], buffer[at + 7], buffer[at + 11]))

func make_fixture() -> String:
	var records: Array = []
	var support := {"canopy_cover_fraction": 0.5, "canopy_valid_fraction": 1.0, "slope_deg": 3.0, "apron_distance_m": 12.0, "thermal_band": true, "protected_clearance_m": 10.0}
	for guild: String in Floor.GUILDS:
		records.append({"id": guild, "kind": "understory_card", "guild": guild, "position": [records.size() * 70.0, 20.0, 3.0], "size": [0.7, 0.3, 0.7], "yaw": 0.7, "anchor": "ground_contact", "evidence_class": "authored", "support": support})
	records.append({"id": "log", "kind": "log", "position": [-15.0, 22.0, -13.0], "size": [0.6, 0.6, 4.0], "yaw": 0.3, "anchor": "ground_contact", "evidence_class": "authored", "support": support})
	records.append({"id": "snag", "kind": "snag", "archetype": "snag", "position": [-35.0, 25.0, 41.0], "size": [0.25, 8.0, 0.25], "height_m": 8.0, "dbh_m": 0.25, "crown_radius_m": 0.8, "crown_ratio": 0.0, "yaw": 1.2, "anchor": "ground_contact", "evidence_class": "authored", "support": support})
	for record: Dictionary in records:
		record.support = record.support.duplicate(true)
		record.support.terrain_y_m = record.position[1]
	var choices: Dictionary = {}
	for key: String in ["minimum_valid_fraction", "floor_slope_max_deg", "moderate_cover_low", "moderate_cover_high", "thermal_band_inner_m", "thermal_band_outer_m"]:
		var values := {"minimum_valid_fraction": 0.95, "floor_slope_max_deg": 38.0, "moderate_cover_low": 0.15, "moderate_cover_high": 0.75, "thermal_band_inner_m": 3.0, "thermal_band_outer_m": 30.0}
		choices[key] = {"status": "authored", "value": values[key]}
	var data := {"schema": Floor.SCHEMA, "status": "authored", "scientific_acceptance": "not_yet_accepted", "uncertainty": "unknown", "authoring_choices": choices, "records": records}
	var path := "user://forest_floor_fixture.json"
	write_json(path, data)
	return path

func negative_controls(path: String) -> void:
	var source: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	var parent := Node3D.new()
	get_root().add_child(parent)
	check(Floor.build(parent, path), "Negative floor setup fails")
	var original := parent.get_node("AuthoredForestFloor")
	var cases: Array = []
	for mutation: Dictionary in [{"schema": "unknown"}, {"status": "measured"}, {"scientific_acceptance": "accepted"}]:
		var invalid := source.duplicate(true)
		invalid.merge(mutation, true)
		cases.append(invalid)
	for mutation: Dictionary in [{"id": ""}, {"kind": "pine"}, {"evidence_class": "measured"}, {"position": [0, 0]}, {"size": [0, 1, 1]}, {"guild": "unknown"}, {"anchor": "canopy"}, {"support": {}}]:
		var invalid := source.duplicate(true)
		invalid.records[0].merge(mutation, true)
		cases.append(invalid)
	var duplicate := source.duplicate(true)
	duplicate.records.append(duplicate.records[0])
	cases.append(duplicate)
	var invalid_snag := source.duplicate(true)
	invalid_snag.records[5].support.thermal_band = false
	cases.append(invalid_snag)
	for mutation: Dictionary in [{"canopy_cover_fraction": 0.9}, {"canopy_valid_fraction": 0.8}, {"slope_deg": 39.0}, {"terrain_y_m": 21.0}, {"protected_clearance_m": 0.1}, {"apron_distance_m": 33.0}]:
		var invalid := source.duplicate(true)
		invalid.records[0].support.merge(mutation, true)
		cases.append(invalid)
	var excessive := source.duplicate(true)
	excessive.records = []
	for index: int in range(4097):
		var record: Dictionary = source.records[0].duplicate(true)
		record.id = "card_%d" % index
		excessive.records.append(record)
	cases.append(excessive)
	for invalid: Dictionary in cases:
		var invalid_path := "user://forest_floor_invalid.json"
		write_json(invalid_path, invalid)
		check(not Floor.build(parent, invalid_path), "Invalid authored floor input is accepted")
		check(parent.get_node("AuthoredForestFloor") == original, "Invalid floor build alters previous geometry")
	parent.free()

func write_json(path: String, data: Dictionary) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(data))
	file.close()
