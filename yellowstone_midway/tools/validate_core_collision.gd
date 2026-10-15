extends SceneTree

const RAY_TOLERANCE_M: float = 0.0001
var findings: Array[String] = []
var authored: Node3D
var master: PackedFloat32Array
var report: Dictionary = {"scope": "Exact master/core ground collision at four edges and corners, with ordinary boundary walks", "ray_tolerance_m": RAY_TOLERANCE_M, "rays": [], "walks": [], "limitations": ["Selected boundary traversals; arbitrary park routes and manual control are not covered.", "Native player capsule, gravity and acceleration; deterministic straight steering, without step assist, jump, flight or position correction."]}

class BoundaryWalker:
	extends "res://scripts/player.gd"
	var commanded: bool = false
	var target_point: Vector3
	func _physics_process(delta: float) -> void:
		var direction := Vector3.ZERO
		if commanded:
			direction = Vector3(target_point.x - position.x, 0.0, target_point.z - position.z).normalized()
		velocity.x = move_toward(velocity.x, direction.x * walk_speed, delta * 7.0)
		velocity.z = move_toward(velocity.z, direction.z * walk_speed, delta * 7.0)
		if not is_on_floor():
			velocity.y -= 9.81 * delta
		move_and_slide()

func _initialize() -> void:
	Engine.physics_ticks_per_second = 60
	call_deferred("run")

func require(condition: bool, message: String) -> void:
	if not condition:
		findings.append(message)

func master_height(x: float, z: float) -> float:
	var gx := (x + 2048.0) / 4.0
	var gz := (z + 2048.0) / 4.0
	var ix := int(floor(gx))
	var iz := int(floor(gz))
	var u := gx - ix
	var v := gz - iz
	var a: float = master[iz * 1025 + ix]
	var b: float = master[iz * 1025 + ix + 1]
	var c: float = master[(iz + 1) * 1025 + ix]
	var d: float = master[(iz + 1) * 1025 + ix + 1]
	if u + v <= 1.0:
		return a * (1.0 - u - v) + b * u + c * v
	return b * (1.0 - v) + c * (1.0 - u) + d * (u + v - 1.0)

func ray(x: float, z: float, mask: int = 6) -> Dictionary:
	var query := PhysicsRayQueryParameters3D.create(Vector3(x, 500.0, z), Vector3(x, -100.0, z), mask)
	var hit: Dictionary = authored.get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		return {"hit": false}
	return {"hit": true, "y_m": hit.position.y, "normal_y": hit.normal.y, "collider": str(hit.collider.get_path())}

func edge_points() -> Array[Dictionary]:
	var points: Array[Dictionary] = []
	for distance: float in [1.0, 2.0, 3.0]:
		points.append({"edge": "west", "x": -340.0 - distance, "z": 166.0})
		points.append({"edge": "east", "x": 260.0 + distance, "z": 166.0})
		points.append({"edge": "north", "x": -100.0, "z": -380.0 - distance})
		points.append({"edge": "south", "x": -100.0, "z": 220.0 + distance})
	for x: float in [-341.0, 261.0]:
		for z: float in [-381.0, 221.0]:
			points.append({"edge": "outside_corner", "x": x, "z": z})
	return points

func check_fallback() -> void:
	var core: Node3D = load("res://scripts/core_terrain.gd").new()
	var scene := Node3D.new()
	var tiles := Node3D.new()
	tiles.name = "TerrainTiles"
	scene.add_child(tiles)
	var tile := MeshInstance3D.new()
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(0, 0, 0), Vector3(4, 0, 0), Vector3(0, 0, 4), Vector3(4, 0, 4)])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2, 1, 3, 2])
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	tile.mesh = mesh
	tiles.add_child(tile)
	var body := StaticBody3D.new()
	body.position.y = 0.5
	tile.add_child(body)
	var col := CollisionShape3D.new()
	var source := HeightMapShape3D.new()
	source.map_width = 2
	source.map_depth = 2
	source.map_data = PackedFloat32Array([0, 0, 0, 0])
	col.shape = source
	body.add_child(col)
	root.add_child(scene)
	core.set("_built", true)
	core.set("_x_min_m", 0.0)
	core.set("_x_max_m", 4.0)
	core.set("_z_min_m", 0.0)
	core.set("_z_max_m", 4.0)
	var touched: int = core.cut_master_tiles(scene)
	var state: Dictionary = core.render_cut_status()
	require(touched == 0 and not state.complete and not state.collision_complete, "unsupported collision preflight accepted")
	require(tile.mesh == mesh and col.shape == source and not col.disabled, "failed preflight mutated render or exterior collision")
	require(state.fallback_exterior_collision_preserved and not state.failures.is_empty(), "unsupported collision fallback was not reported")
	var material: ShaderMaterial = load("res://assets/materials/terrain.tres").duplicate()
	core.set_terrain_cut_uniform([material])
	require(material.get_shader_parameter("core_cut_active") == 1.0, "unsupported collision disabled fragment fallback")
	report["unsupported_collision_control"] = state
	scene.free()
	core.free()

func check_world_guard() -> void:
	var world: Node3D = load("res://scripts/world.gd").new()
	var material: ShaderMaterial = load("res://assets/materials/terrain.tres").duplicate()
	material.set_shader_parameter("core_cut_active", 0.0)
	world.terrain_materials.append(material)
	# The isolated world has no AuthoredMidway child and never enters the scene tree.
	world.build_core_terrain()
	require(world.get("_core_terrain") == null and world.get("_mat_surface") == null, "world retained a core after collision preflight failure")
	require(world.terrain_materials.size() == 1 and world.terrain_materials[0] == material, "world inserted a failed core material")
	require(material.get_shader_parameter("core_cut_active") == 0.0, "world activated fragment clipping after collision failure")
	await process_frame
	require(world.get_node_or_null("CoreTerrain") == null, "world retained staged core collision after guard rejection")
	report["world_guard_control"] = {"ready_invoked": false, "core_cleared": world.get("_core_terrain") == null, "mat_surface_cleared": world.get("_mat_surface") == null, "staged_core_removed": world.get_node_or_null("CoreTerrain") == null, "material_count": world.terrain_materials.size(), "master_fragment_cut_active": material.get_shader_parameter("core_cut_active"), "expected_diagnostic": "collision cut incomplete; original master terrain retained"}
	world.free()

func legacy_control(points: Array[Dictionary], terrain: Node) -> void:
	var originals: Array[Dictionary] = []
	for tile: MeshInstance3D in terrain.get_children():
		var col: CollisionShape3D = tile.find_child("TerrainShape", true, false)
		var source: HeightMapShape3D = col.shape
		var heights: PackedFloat32Array = source.map_data.duplicate()
		var changed: bool = false
		for iz in source.map_depth:
			for ix in source.map_width:
				var x: float = tile.position.x + ix * 4.0
				var z: float = tile.position.z + iz * 4.0
				if x >= -340.0 and x <= 260.0 and z >= -380.0 and z <= 220.0:
					heights[iz * source.map_width + ix] = -10.0
					changed = true
		if changed:
			originals.append({"node": col, "shape": source})
			var sunk := HeightMapShape3D.new()
			sunk.map_width = source.map_width
			sunk.map_depth = source.map_depth
			sunk.map_data = heights
			col.shape = sunk
	for tick in 3:
		await physics_frame
	var maximum_deficit: float = 0.0
	var detected: int = 0
	for point: Dictionary in points:
		var hit := ray(point.x, point.z, 2)
		if hit.hit:
			var deficit: float = master_height(point.x, point.z) - float(hit.y_m)
			maximum_deficit = maxf(maximum_deficit, deficit)
			if deficit > 1.0:
				detected += 1
	require(detected >= 12 and maximum_deficit > 70.0, "legacy boundary sinking control did not expose exterior defect")
	report["legacy_sinking_control"] = {"detected_points": detected, "maximum_deficit_m": maximum_deficit}
	for original: Dictionary in originals:
		(original.node as CollisionShape3D).shape = original.shape
	for tick in 3:
		await physics_frame

func walk_boundary(id: String, start: Vector3, target: Vector3) -> Dictionary:
	var result := {"id": id, "pass": false, "initial_placements": 1, "teleports_within_walk": 0, "jump": false, "flight": false, "walked_horizontal_m": 0.0, "max_airborne_seconds": 0.0, "minimum_outside_clearance_m": null, "failure": ""}
	var initial := ray(start.x, start.z)
	if not initial.hit:
		result.failure = "No initial ground"
		return result
	var probe := BoundaryWalker.new()
	probe.collision_mask = 7
	probe.position = Vector3(start.x, initial.y_m + 0.55, start.z)
	root.add_child(probe)
	for tick in 90:
		await physics_frame
	if not probe.is_on_floor():
		result.failure = "Could not settle on boundary ground"
		probe.free()
		return result
	result["settled_start_m"] = [probe.position.x, probe.position.y, probe.position.z]
	result["capsule_radius_m"] = 0.29
	result["capsule_height_m"] = 1.72
	result["speed_mps"] = probe.walk_speed
	probe.target_point = target
	probe.commanded = true
	var previous: Vector3 = probe.position
	var airborne: float = 0.0
	for tick in 600:
		await physics_frame
		var p: Vector3 = probe.position
		result.walked_horizontal_m += Vector2(p.x - previous.x, p.z - previous.z).length()
		previous = p
		airborne = 0.0 if probe.is_on_floor() else airborne + 1.0 / 60.0
		result.max_airborne_seconds = maxf(result.max_airborne_seconds, airborne)
		if p.x < -340.0 or p.x > 260.0 or p.z < -380.0 or p.z > 220.0:
			var clearance: float = p.y - master_height(p.x, p.z)
			result.minimum_outside_clearance_m = clearance if result.minimum_outside_clearance_m == null else minf(result.minimum_outside_clearance_m, clearance)
			if clearance < -0.12:
				result.failure = "Walker below visible outside terrain"
				break
		if airborne > 0.8:
			result.failure = "Sustained boundary floor loss"
			break
		if Vector2(p.x - target.x, p.z - target.z).length() < 0.17:
			result.pass = probe.is_on_floor()
			if not result.pass:
				result.failure = "Arrived without floor contact"
			break
	if not result.pass and result.failure.is_empty():
		result.failure = "Boundary walk did not reach target"
	result["end_m"] = [probe.position.x, probe.position.y, probe.position.z]
	probe.free()
	await physics_frame
	return result

func run() -> void:
	check_fallback()
	await check_world_guard()
	master = FileAccess.get_file_as_bytes("res://data/terrain.f32").to_float32_array()
	authored = load("res://scenes/authored_world.tscn").instantiate()
	root.add_child(authored)
	var terrain: Node = authored.find_child("TerrainTiles", true, false)
	for tile: Node in terrain.get_children():
		var body: StaticBody3D = tile.find_child("Ground", true, false)
		body.collision_layer = 2
	for tick in 3:
		await physics_frame
	var points := edge_points()
	await legacy_control(points, terrain)
	var core: Node3D = load("res://scripts/core_terrain.gd").new()
	root.add_child(core)
	var mat: RefCounted = load("res://scripts/mat_surface.gd").new()
	mat.load_outflow()
	mat.load_pigment()
	require(core.build(mat), "Real core build failed")
	var core_body: StaticBody3D = core.find_child("CoreTerrainCollision", true, false)
	core_body.collision_layer = 4
	require(core.cut_master_tiles(authored) == 12, "Real collision tile count")
	var cut: Dictionary = core.render_cut_status()
	require(cut.complete and cut.collision_complete and cut.removed_triangles == 45000, "Real render/collision cut incomplete")
	report["cut"] = cut
	var partial: int = 0
	var disabled: int = 0
	for tile: MeshInstance3D in terrain.get_children():
		if tile.position.x + 256.0 <= -340.0 or tile.position.x >= 260.0 or tile.position.z + 256.0 <= -380.0 or tile.position.z >= 220.0:
			continue
		var col: CollisionShape3D = tile.find_child("TerrainShape", true, false)
		if tile.mesh.get_surface_count() == 0:
			disabled += 1
			require(col.disabled, "Fully covered master collider remains active")
		else:
			partial += 1
			require(col.shape is ConcavePolygonShape3D and col.transform == Transform3D.IDENTITY, "Partial collision shape or transform disagrees")
			require(col.shape.get_faces() == tile.mesh.get_faces(), "Partial collision faces disagree with retained render geometry")
	require(partial == 10 and disabled == 2, "Partial/disabled collision counts")
	for tick in 3:
		await physics_frame
	var maximum_error: float = 0.0
	for point: Dictionary in points:
		var hit := ray(point.x, point.z, 2)
		var row := point.duplicate()
		row["rendered_y_m"] = master_height(point.x, point.z)
		row["physics"] = hit
		require(hit.hit, "Outside ground missing " + str(point))
		if hit.hit:
			var error: float = hit.y_m - row.rendered_y_m
			row["error_m"] = error
			maximum_error = maxf(maximum_error, absf(error))
			require(absf(error) <= RAY_TOLERANCE_M and hit.normal_y > 0.0, "Outside height or winding mismatch " + str(point))
		report.rays.append(row)
	report["maximum_outside_ray_error_m"] = maximum_error
	var ghost_points := [Vector2(-339, -379), Vector2(259, -379), Vector2(-339, 219), Vector2(259, 219), Vector2(-40, -80)]
	for point: Vector2 in ghost_points:
		require(not ray(point.x, point.y, 2).hit, "Master ghost collision remains inside core " + str(point))
	report["inside_ghost_ray_controls"] = ghost_points.size()
	require(core.cut_master_tiles(authored) == 12, "Collision cut repeat changed result")
	var walks := [{"id": "west", "start": Vector3(-345, 0, 166), "target": Vector3(-335, 0, 166)}, {"id": "east", "start": Vector3(265, 0, 166), "target": Vector3(255, 0, 166)}, {"id": "north", "start": Vector3(-100, 0, -385), "target": Vector3(-100, 0, -375)}, {"id": "south", "start": Vector3(-100, 0, 225), "target": Vector3(-100, 0, 215)}]
	for item: Dictionary in walks:
		for reverse: bool in [false, true]:
			var id: String = item.id + ("_out" if reverse else "_in")
			var result: Dictionary = await walk_boundary(id, item.target if reverse else item.start, item.start if reverse else item.target)
			report.walks.append(result)
			require(result.pass, "Boundary walk " + id + ": " + str(result.failure))
			print("BOUNDARY_WALK ", id, " pass=", result.pass, " distance_m=", result.walked_horizontal_m)
	report["findings"] = findings
	report["pass"] = findings.is_empty()
	report["godot"] = Engine.get_version_info().string
	report["source_sha256"] = FileAccess.get_sha256("res://scripts/core_terrain.gd")
	report["world_source_sha256"] = FileAccess.get_sha256("res://scripts/world.gd")
	var args := OS.get_cmdline_user_args()
	if args.size() == 2 and args[0] == "--report-out":
		var file := FileAccess.open(args[1], FileAccess.WRITE)
		if file != null:
			file.store_string(JSON.stringify(report, "\t") + "\n")
	print("CORE_COLLISION ", "PASS" if findings.is_empty() else "FAIL", " findings=", findings)
	quit(0 if findings.is_empty() else 1)
