extends SceneTree

var world: Node3D
var camera: Camera3D
var water_material: ShaderMaterial
var apron_material: ShaderMaterial
var output_dir := "res://work/spring-display"
var report: Dictionary = {"schema": "yellowstone.spring_display_capture.v1", "scope": "Native spring bindings and projection; subjective appearance and unrelated scene assets require separate review", "failures": [], "captures": []}

func _initialize() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			output_dir = argument.trim_prefix("--out=")
	call_deferred("run")

func run() -> void:
	if DisplayServer.get_name() == "headless":
		push_error("Spring display captures require a native renderer.")
		quit(1)
		return
	create_timer(240).timeout.connect(func(): push_error("Spring display capture timed out"); quit(1))
	ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:1")
	root.size = Vector2i(1440, 900)
	root.mode = Window.MODE_WINDOWED
	root.show()
	world = load("res://scenes/main.tscn").instantiate()
	root.add_child(world)
	current_scene = world
	for frame: int in range(12):
		await process_frame
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
	for record: Dictionary in world.spec.pools:
		if record.id == "pool_1034_0":
			pool = record
	for node: Node in get_nodes_in_group("thermal_surfaces"):
		if node.get_meta("feature_name", "") == "Grand Prismatic Spring":
			water_material = node.mesh.surface_get_material(0) as ShaderMaterial
	apron_material = world.get_node("CoreTerrain").get_mat_material()
	if water_material == null or apron_material == null:
		push_error("Spring materials are unavailable")
		quit(1)
		return
	if float(water_material.get_shader_parameter("display_ramp_mix")) != 1.0:
		report.failures.append("The Grand Prismatic display ramp is not bound")
	if water_material.get_meta("pool_display_class", "") != "authored_image_informed_display":
		report.failures.append("The image-informed display class is absent")
	for parameter: String in ["spring_apron_display", "spring_terrace_detail"]:
		if apron_material.get_shader_parameter(parameter) == null:
			report.failures.append("Missing spring texture: " + parameter)
	camera = Camera3D.new()
	camera.near = 0.08
	camera.far = 2900
	world.add_child(camera)
	camera.make_current()
	var anchor: Dictionary = {}
	for record: Dictionary in world.spec.anchors:
		if record.id == "overlook":
			anchor = record
	camera.position = Vector3(anchor.position[0], anchor.position[1] + 1.67, anchor.position[2])
	var center := Vector3(pool.center[0], pool.center[1], pool.center[2])
	camera.look_at(center)
	DirAccess.make_dir_recursive_absolute(output_dir)
	camera.fov = 72
	water_material.set_shader_parameter("display_ramp_mix", 0.0)
	apron_material.set_shader_parameter("spring_display_mix", 0.0)
	await capture("radiometric_profile_fov72", pool)
	water_material.set_shader_parameter("display_ramp_mix", 1.0)
	apron_material.set_shader_parameter("spring_display_mix", 1.0)
	await capture("image_display_fov72", pool)
	camera.fov = 40
	await capture("image_display_fov40", pool)
	camera.fov = 30
	await capture("image_display_fov30", pool)
	camera.fov = 55
	camera.position = Vector3(-181, 28, 82)
	camera.look_at(Vector3(-133, 16.9, 31))
	await capture("apron_detail", pool)
	report["godot"] = Engine.get_version_info().string
	report["renderer"] = RenderingServer.get_current_rendering_method()
	report["cpu"] = OS.get_processor_name()
	report["scientific_ramp_sha256"] = water_material.get_meta("pool_ramp_sha256", "")
	report["display_ramp_sha256"] = water_material.get_meta("pool_display_sha256", "")
	report["world_sha256"] = FileAccess.get_sha256("res://data/world.json")
	report["ok"] = report.failures.is_empty() and report.captures.size() == 5
	var file := FileAccess.open(output_dir.path_join("report.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t") + "\n")
	file.close()
	print("SPRING_DISPLAY ", "PASS" if report.ok else "FAIL", " captures=", report.captures.size())
	quit(0 if report.ok else 1)

func capture(identity: String, pool: Dictionary) -> void:
	for frame: int in range(12):
		await process_frame
	await RenderingServer.frame_post_draw
	var image: Image = root.get_texture().get_image()
	var path: String = output_dir.path_join(identity + ".png")
	if image.save_png(path) != OK:
		report.failures.append("Image save failed: " + identity)
	var viewport_size := camera.get_viewport().get_visible_rect().size
	var image_scale := Vector2(image.get_size()) / viewport_size
	var low := Vector2(INF, INF)
	var high := Vector2(-INF, -INF)
	for point: Array in pool.ring:
		var projected := camera.unproject_position(Vector3(point[0], pool.center[1], point[1]))
		projected *= image_scale
		low = low.min(projected)
		high = high.max(projected)
	var aspect: float = float(root.size.x) / float(root.size.y)
	var horizontal_fov: float = rad_to_deg(2*atan(tan(deg_to_rad(camera.fov/2))*aspect))
	report.captures.append({"id": identity, "file": path.get_file(), "sha256": FileAccess.get_sha256(path),
		"camera_m": [camera.position.x, camera.position.y, camera.position.z], "vertical_fov_deg": camera.fov,
		"horizontal_fov_deg": horizontal_fov, "pool_screen_bounds_px": [low.x, low.y, high.x, high.y],
		"viewport_coordinates": [viewport_size.x, viewport_size.y],
		"image_pixels": [image.get_width(), image.get_height()],
		"pool_screen_width_fraction": (high.x-low.x)/float(image.get_width()),
		"draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
		"primitives": Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)})
	print("SPRING_CAPTURE ", identity)
