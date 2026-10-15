extends "/Users/kreed/!claude/roots-of-reason/5-original-games/yellowstone/work/validate_forest_benchmark.gd"

const SHARED_LOCK_PATH: String = "/Users/kreed/!claude/roots-of-reason/5-original-games/yellowstone/work/validate_forest_benchmark.gd"

var out := "/Users/kreed/!claude/roots-of-reason/5-original-games/yellowstone/evidence/forest-render"

func _initialize() -> void:
	report = {"captures": [], "inventory": [], "source_metadata": {}, "failures": []}
	fixture_path = "/Users/kreed/!claude/roots-of-reason/5-original-games/yellowstone/work/forest-benchmark-forcing.json"
	benchmark_label = "Updated release visual validation"
	call_deferred("run")

func run() -> void:
	create_timer(180).timeout.connect(func(): quit(2))
	fixture = JSON.parse_string(FileAccess.get_file_as_string(fixture_path))
	if fixture.get("schema") != "yellowstone.forest_benchmark_forcing.v1":
		push_error("Unsupported visual-capture forcing fixture.")
		quit(1)
		return
	root.title = benchmark_label
	root.gui_disable_input = true
	DirAccess.make_dir_recursive_absolute(out)
	ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:1")
	root.size = Vector2i(1440, 900)
	world = load("res://scenes/main.tscn").instantiate()
	root.add_child(world)
	current_scene = world
	lock_benchmark_forcing()
	for i: int in 12:
		await process_frame
	check_benchmark_forcing("visual_warmup")
	world.set_process(false)
	world.ecosystem.set_process(false)
	world.atmosphere_controller.set_process(false)
	world.weather_snapshot_reader.set_process(false)
	world.player.enabled = false
	world.player.set_physics_process(false)
	world.player.set_process_input(false)
	world.overlay.visible = false
	world.menu.visible = false
	if world.live_client != null:
		world.live_client.set_process(false)
	if world.data_watcher != null:
		world.data_watcher.set_process(false)
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	var pool: Dictionary = {}
	var anchor: Dictionary = {}
	for p: Dictionary in world.spec.pools:
		if p.id == "pool_1034_0": pool = p
	for a: Dictionary in world.spec.anchors:
		if a.id == "overlook": anchor = a
	camera = Camera3D.new()
	world.add_child(camera)
	camera.near = 0.08
	camera.far = 2900
	camera.position = Vector3(anchor.position[0], anchor.position[1] + 1.67, anchor.position[2])
	camera.look_at(Vector3(pool.center[0], pool.center[1], pool.center[2]))
	camera.make_current()
	for node: Node in world.get_children():
		report.inventory.append({"path": str(node.get_path()), "type": node.get_class(), "children": node.get_child_count()})
		if node.name == "AuthoredMidway":
			for child: Node in node.get_children():
				report.inventory.append({"path": str(child.get_path()), "type": child.get_class(), "children": child.get_child_count()})
	for name: String in ["AuthoredCanopySurface", "AuthoredVegetation", "AuthoredForestFloor"]:
		var group: Node3D = world.find_child(name, true, false)
		if group != null:
			var metadata := {}
			for key: StringName in group.get_meta_list(): metadata[str(key)] = group.get_meta(key)
			report.source_metadata[name] = metadata
	for fov: float in [72, 40, 30]:
		camera.fov = fov
		await capture_floor("overlook_fov%d" % fov)
		if fov == 72:
			var canopy: Node3D = world.find_child("AuthoredCanopySurface", true, false)
			canopy.visible = false
			await capture_floor("overlook_without_residual_fov72")
			canopy.visible = true
	camera.fov = 64
	camera.position = Vector3(-259.9, rendered_ground(-259.9, 160.0) + 1.67, 160.0)
	camera.look_at(Vector3(-263.5, 43.7, 155.8))
	await capture_floor("floor_wood_walk")
	camera.position = Vector3(-246.5, rendered_ground(-246.5, 152.0) + 1.67, 152.0)
	camera.look_at(Vector3(-248.8, 42.4, 148.7))
	await capture_floor("floor_plant_walk")
	camera.position = Vector3(-250.0, rendered_ground(-250.0, 136.5) + 1.67, 136.5)
	camera.look_at(Vector3(-251.75, 32.65, 133.81))
	await capture_floor("floor_litter_walk")
	camera.position = Vector3(-265.2, rendered_ground(-265.2, 153.5) + 1.67, 153.5)
	camera.look_at(Vector3(-263.63875, 43.62, 155.76435))
	await capture_floor("floor_log_walk")
	report.evidence_class = "Native Godot Mobile Metal saved-scene appearance; not frame-time evidence or field calibration"
	report.inputs = {}
	for path: String in ["res://shaders/canopy_surface.gdshader", "res://scripts/world.gd", "res://scripts/tree_submission.gd", "res://shaders/thermal_apron.gdshader", "res://data/release.json", "res://data/forest_floor.json", "res://scripts/forest_floor.gd", "res://scripts/canopy_surface.gd", "res://scripts/rendered_ground.gd", "res://shaders/ground_surface.gdshaderinc", "res://scripts/terrain_materials.gd", "res://assets/textures/color_mips/color_mips.json"]:
		report.inputs[path] = FileAccess.get_sha256(path)
	report.inputs["shared_forcing_lock_harness"] = FileAccess.get_sha256(SHARED_LOCK_PATH)
	report.inputs["capture_wrapper"] = FileAccess.get_sha256(get_script().resource_path)
	report.inputs["forcing_fixture"] = FileAccess.get_sha256(fixture_path)
	report.benchmark_fixture["shared_lock_harness_path"] = SHARED_LOCK_PATH
	report.benchmark_fixture["shared_lock_harness_sha256"] = FileAccess.get_sha256(SHARED_LOCK_PATH)
	report.benchmark_fixture["last_state"] = forcing_state()
	report.benchmark_fixture["forcing_checks"] = benchmark_checks
	report.benchmark_fixture["forcing_unchanged"] = expected_forcing == forcing_state()
	report["ok"] = report.failures.is_empty() and report.captures.size() == 8
	report.authored_world_sha256 = FileAccess.get_sha256("res://scenes/authored_world.tscn")
	var output := FileAccess.open(out.path_join("report.json"), FileAccess.WRITE)
	output.store_string(JSON.stringify(report, "  "))
	output.close()
	print("INTEGRATION_ISOLATION ", report.captures.size(), " captures")
	quit(0 if report.ok else 1)

func capture_floor(label: String) -> void:
	for i: int in 5:
		await process_frame
	await RenderingServer.frame_post_draw
	check_benchmark_forcing("visual_" + label)
	var path := out.path_join(label + ".png")
	var error := root.get_texture().get_image().save_png(path)
	if error != OK:
		report.failures.append("Image save failed: " + label)
	var canopy: Node3D = world.find_child("AuthoredCanopySurface", true, false)
	report.captures.append({"file": path, "error": error, "sha256": FileAccess.get_sha256(path), "position_m": vector_array(camera.global_position), "rotation_radians": vector_array(camera.global_rotation), "fov_deg": camera.fov, "sun_rotation_radians": vector_array(world.sun.rotation), "residual_canopy_visible": canopy != null and canopy.visible})
	print("ISOLATION_CAPTURE ", label)

func rendered_ground(x: float, z: float) -> float:
	var core: Node3D = world.get_node("CoreTerrain")
	var spacing: float = core.MESH_DECIMATION * core._cell_m
	var gx: float = (x - core._x_min_m) / spacing
	var gz: float = (z - core._z_min_m) / spacing
	var i := int(gx)
	var j := int(gz)
	var fx: float = gx - i
	var fz: float = gz - j
	var at: int = j * core.MESH_DECIMATION * core._nx + i * core.MESH_DECIMATION
	var a: float = core._heights_full[at]
	var b: float = core._heights_full[at + core.MESH_DECIMATION]
	var c: float = core._heights_full[at + core.MESH_DECIMATION * core._nx]
	var d: float = core._heights_full[at + core.MESH_DECIMATION * (core._nx + 1)]
	return a + fx * (b-a) + fz * (c-a) if fx + fz <= 1 else d + (1-fx)*(c-d)+(1-fz)*(b-d)
