extends SceneTree

var world: Node3D
var camera: Camera3D
var report: Dictionary = {"captures": [], "moving_camera": {}, "failures": []}
var output_dir: String = "res://tests/terrain_render"

func _initialize() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--out="):
			output_dir = arg.trim_prefix("--out=")
	call_deferred("run")

func run() -> void:
	if DisplayServer.get_name() == "headless":
		push_error("Terrain captures require a visible rendering backend.")
		quit(1)
		return
	ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:1")
	root.size = Vector2i(1440, 900)
	root.mode = Window.MODE_WINDOWED
	root.show()
	root.grab_focus()
	create_timer(120.0).timeout.connect(func(): push_error("Terrain capture timed out."); quit(1))
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
	check_runtime_ground()
	if "--core-debug" in OS.get_cmdline_user_args():
		var debug_material := StandardMaterial3D.new()
		debug_material.albedo_color = Color(0.8, 0.2, 0.1)
		world.get_node("CoreTerrain/CoreTerrainTile").material_override = debug_material
	if "--core-ground-only" in OS.get_cmdline_user_args():
		var core_material: ShaderMaterial = world.get_node("CoreTerrain").get_mat_material()
		core_material.shader = load("res://shaders/terrain.gdshader")
		core_material.set_shader_parameter("core_cut_active", 0.0)
	for material: ShaderMaterial in world.foliage_materials:
		material.set_shader_parameter("wind_vector", Vector2.ZERO)
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	if world.live_client != null:
		world.live_client.set_process(false)
	if world.data_watcher != null:
		world.data_watcher.set_process(false)
	camera = Camera3D.new()
	camera.fov = 72.0
	camera.near = 0.08
	camera.far = 2900.0
	world.add_child(camera)
	camera.make_current()
	DirAccess.make_dir_recursive_absolute(output_dir)
	var routes: Dictionary = {}
	for route: Dictionary in world.spec.routes:
		routes[str(route.id)] = route
	var spur: Array = routes["trail_3455_0"].points
	var p: Array = spur[mini(8, spur.size() - 1)]
	var floor_y: float = surface_height(float(p[0]), float(p[2]))
	var cases: Array[Dictionary] = [
		{"id": "overlook", "position": Vector3(-242, 52, 160), "target": Vector3(-213, 30, 125)},
		{"id": "trail_detail", "position": Vector3(float(p[0]), floor_y + 1.7, float(p[2])), "target": Vector3(float(spur[mini(12, spur.size() - 1)][0]), floor_y + 0.1, float(spur[mini(12, spur.size() - 1)][2]))},
		{"id": "core_boundary", "position": Vector3(-346, surface_height(-346, 166) + 2.0, 166), "target": Vector3(-329, surface_height(-329, 155), 155)},
	]
	var original_rotation: Vector3 = world.sun.rotation
	var angles: Array[Dictionary] = [
		{"id": "current", "rotation": original_rotation},
		{"id": "low", "rotation": Vector3(deg_to_rad(-18), deg_to_rad(-35), 0)},
		{"id": "high", "rotation": Vector3(deg_to_rad(-65), deg_to_rad(25), 0)},
	]
	for view: Dictionary in cases:
		camera.position = view.position
		camera.look_at(view.target)
		for angle: Dictionary in angles:
			world.sun.rotation = angle.rotation
			await capture(str(view.id) + "_" + str(angle.id), view, angle)
	world.sun.rotation = original_rotation
	camera.position = cases[0].position
	camera.look_at(cases[0].target)
	var frame_times: Array[float] = []
	var draw_calls: Array[float] = []
	var process_times: Array[float] = []
	var configured_cap: int = Engine.max_fps
	Engine.max_fps = 0
	for frame: int in range(180):
		var started: int = Time.get_ticks_usec()
		camera.position = cases[0].position + Vector3(sin(float(frame) * 0.035) * 8.0, 0, cos(float(frame) * 0.035) * 6.0)
		camera.look_at(cases[0].target)
		await RenderingServer.frame_post_draw
		if frame >= 60:
			frame_times.append(float(Time.get_ticks_usec() - started) / 1000.0)
			draw_calls.append(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
			process_times.append(Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0)
	frame_times.sort()
	report.moving_camera = {"sample_frames": frame_times.size(), "median_wall_frame_ms": frame_times[int(frame_times.size() / 2)], "p95_wall_frame_ms": frame_times[int(frame_times.size() * 0.95)], "process_frame_mean_ms": mean(process_times), "draw_calls_mean": mean(draw_calls), "fps_cap": Engine.max_fps, "configured_fps_cap": configured_cap, "scope": "Frozen forcing and foliage with a moving camera; wall time includes display synchronization."}
	report["renderer"] = RenderingServer.get_current_rendering_method()
	report["godot"] = Engine.get_version_info().string
	report["shadow"] = {"range_m": world.sun.directional_shadow_max_distance, "normal_bias": world.sun.shadow_normal_bias, "bias": world.sun.shadow_bias}
	report["ok"] = report.failures.is_empty() and report.captures.size() == 9 and report.has("runtime_ground")
	var file: FileAccess = FileAccess.open(output_dir.path_join("report.json"), FileAccess.WRITE)
	if file == null:
		push_error("Could not write terrain render report.")
		quit(1)
		return
	file.store_string(JSON.stringify(report, "\t") + "\n")
	file.close()
	print("TERRAIN_RENDER ", "PASS" if report.ok else "FAIL", " captures=", report.captures.size(), " moving_camera=", report.moving_camera)
	quit(0 if report.ok else 1)

func capture(id: String, view: Dictionary, angle: Dictionary) -> void:
	print("TERRAIN_CAPTURE_BEGIN ", id, " visible=", root.visible, " mode=", root.mode)
	for frame: int in range(8):
		await process_frame
	await RenderingServer.frame_post_draw
	var image: Image = root.get_texture().get_image()
	var path: String = output_dir.path_join(id + ".png")
	if image.is_empty():
		report.failures.append("Capture failed: " + id)
		return
	if id == "overlook_current":
		var sum: float = 0.0
		var square_sum: float = 0.0
		var count: int = 0
		for y: int in range(770, 875, 8):
			for x: int in range(640, 1320, 8):
				var color: Color = image.get_pixel(x, y)
				var luminance: float = color.r * 0.2126 + color.g * 0.7152 + color.b * 0.0722
				sum += luminance
				square_sum += luminance * luminance
				count += 1
		var variance: float = square_sum / float(count) - pow(sum / float(count), 2.0)
		report["foreground_luminance_variance"] = variance
		if variance < 0.000001:
			report.failures.append("Core foreground is uniform; terrain material may be absent")
	if image.save_png(path) != OK:
		report.failures.append("Capture failed: " + id)
		return
	report.captures.append({"id": id, "file": path.get_file(), "position_m": vector_array(view.position), "target_m": vector_array(view.target), "sun_rotation_radians": vector_array(angle.rotation), "sha256": FileAccess.get_sha256(path)})
	print("TERRAIN_CAPTURE ", id)

func surface_height(x: float, z: float) -> float:
	var query := PhysicsRayQueryParameters3D.create(Vector3(x, 300, z), Vector3(x, -100, z))
	var hit: Dictionary = world.get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		report.failures.append("Missing surface at %.2f %.2f" % [x, z])
		return world.height_field.sample(x, z)
	return float(hit.position.y)

func check_runtime_ground() -> void:
	var cut: Dictionary = world.get_node("CoreTerrain").render_cut_status()
	report["core_render_cut"] = cut
	if not bool(cut.get("complete", false)) or int(cut.get("removed_triangles", 0)) != int(cut.get("expected_removed_triangles", -1)):
		report.failures.append("Core render footprint uses a fragment-cut fallback")
	var core_material: ShaderMaterial = world.get_node("CoreTerrain").get_mat_material()
	if not core_material in world.terrain_materials:
		report.failures.append("Core ground omitted from seasonal material list")
	var master_material: ShaderMaterial = world.terrain_materials[0]
	for name: String in ["snow_amount", "snow_swe_mm", "snow_cover_fraction", "snow_mask"]:
		if core_material.get_shader_parameter(name) != master_material.get_shader_parameter(name):
			report.failures.append("Core/master seasonal state differs: " + name)
	var weather: Dictionary = world.atmosphere_controller.get("_weather")
	var prior_wetness: float = float(weather.ground_wetness_fraction)
	var prior_bindings: Array = []
	for material: ShaderMaterial in world.terrain_materials:
		prior_bindings.append(material.get_shader_parameter("ground_wetness"))
	weather.ground_wetness_fraction = 0.6
	world.atmosphere_controller.call("_update_wetness")
	if absf(float(core_material.get_shader_parameter("ground_wetness")) - 0.6) > 0.00001:
		report.failures.append("Atmosphere wetness cache omits core ground")
	weather.ground_wetness_fraction = prior_wetness
	for index: int in range(world.terrain_materials.size()):
		world.terrain_materials[index].set_shader_parameter("ground_wetness", prior_bindings[index])
	report["runtime_ground"] = {"material_count": world.terrain_materials.size(), "core_in_seasonal_list": core_material in world.terrain_materials, "wetness_probe": 0.6}

func vector_array(v: Vector3) -> Array[float]:
	return [v.x, v.y, v.z]

func mean(values: Array[float]) -> float:
	var total: float = 0.0
	for v: float in values:
		total += v
	return total / float(maxi(values.size(), 1))
