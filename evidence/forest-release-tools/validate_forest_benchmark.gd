extends SceneTree

var world: Node3D
var camera: Camera3D
var report: Dictionary = {"captures": [], "moving_camera": {}, "failures": []}
var output_dir: String = "res://tests/terrain_render"
var started_us: int = 0
var fixture: Dictionary = {}
var fixture_path: String = ""
var benchmark_label: String = "Updated release benchmark"
var expected_forcing: Dictionary = {}
var benchmark_checks: int = 0
var input_callbacks_disabled: int = 0

class ComparisonPlot extends Control:
	var frames: Array = []
	var time_s: float = 0.0
	func _draw() -> void:
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.035, 0.06, 0.055, 0.92))
		if frames.is_empty():
			return
		var low: float = INF
		var high: float = -INF
		for frame: Dictionary in frames:
			low = minf(low, minf(float(frame.control_c), float(frame.intervention_c)))
			high = maxf(high, maxf(float(frame.control_c), float(frame.intervention_c)))
		var duration: float = float(frames[-1].t_s)
		for key: String in ["control_c", "intervention_c"]:
			var points: PackedVector2Array = PackedVector2Array()
			for frame: Dictionary in frames:
				if float(frame.t_s) > time_s:
					break
				points.append(Vector2(20 + float(frame.t_s) / duration * (size.x - 40),
					size.y - 24 - (float(frame[key]) - low) / maxf(high-low, 0.01) * (size.y - 48)))
			if points.size() > 1:
				draw_polyline(points, Color(0.65, 0.81, 0.77) if key == "control_c" else Color(1.0, 0.69, 0.34), 3.0, true)
		draw_line(Vector2(20, size.y - 18), Vector2(size.x - 20, size.y - 18), Color(0.6, 0.65, 0.6), 1.0)
		var font: Font = ThemeDB.fallback_font
		draw_string(font, Vector2(20, 18), "Downstream C: control / intervention    %.2f to %.2f" % [low, high], HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		draw_string(font, Vector2(20, size.y - 2), "0                      model seconds                       %.0f" % duration, HORIZONTAL_ALIGNMENT_LEFT, -1, 12)

func _initialize() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--out="):
			output_dir = arg.trim_prefix("--out=")
		if arg.begins_with("--fixture="):
			fixture_path = arg.trim_prefix("--fixture=")
		if arg.begins_with("--benchmark-label="):
			benchmark_label = arg.trim_prefix("--benchmark-label=")
	call_deferred("run")

func run() -> void:
	started_us = Time.get_ticks_usec()
	if fixture_path.is_empty() or not FileAccess.file_exists(fixture_path):
		push_error("Explicit --fixture=<absolute JSON path> required.")
		quit(1)
		return
	fixture = JSON.parse_string(FileAccess.get_file_as_string(fixture_path))
	if fixture.get("schema") != "yellowstone.forest_benchmark_forcing.v1":
		push_error("Unsupported benchmark fixture.")
		quit(1)
		return
	for forbidden: String in ["--portfolio", "--core-debug", "--core-ground-only"]:
		if forbidden in OS.get_cmdline_user_args():
			push_error("Graphics-changing capture options forbidden in benchmark.")
			quit(1)
			return
	if DisplayServer.get_name() == "headless":
		push_error("Terrain captures require a visible rendering backend.")
		quit(1)
		return
	ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:1")
	root.size = Vector2i(1440, 900)
	root.mode = Window.MODE_WINDOWED
	root.title = benchmark_label
	root.gui_disable_input = true
	root.show()
	root.grab_focus()
	create_timer(900.0 if "--portfolio" in OS.get_cmdline_user_args() else 300.0).timeout.connect(func(): push_error("Terrain capture timed out."); quit(1))
	world = load("res://scenes/main.tscn").instantiate()
	root.add_child(world)
	current_scene = world
	# Freeze before yielding to any process frame or pending HTTP completion.
	lock_benchmark_forcing()
	for frame: int in range(12):
		await process_frame
	check_benchmark_forcing("warmup")
	# Adversarially inject the real time-jump key; disabled game input must ignore it.
	var jump := InputEventKey.new()
	jump.keycode = KEY_T
	jump.physical_keycode = KEY_T
	jump.pressed = true
	root.push_input(jump, true)
	jump = jump.duplicate()
	jump.pressed = false
	root.push_input(jump, true)
	await process_frame
	check_benchmark_forcing("injected_time_jump_key")
	report.benchmark_fixture["input_probe"] = "T press/release after lock, state checked after next frame"
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
	report.benchmark_fixture["camera"] = {"fov_deg": camera.fov, "near_m": camera.near, "far_m": camera.far}
	DirAccess.make_dir_recursive_absolute(output_dir)
	if "--portfolio" in OS.get_cmdline_user_args():
		await record_portfolio()
		return
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
	if "--lock-probe" in OS.get_cmdline_user_args():
		camera.position = cases[0].position
		camera.look_at(cases[0].target)
		await capture("overlook_current", cases[0], angles[0])
		report.benchmark_fixture["last_state"] = forcing_state()
		report.benchmark_fixture["forcing_checks"] = benchmark_checks
		report.benchmark_fixture["forcing_unchanged"] = expected_forcing == forcing_state()
		report["mode"] = "Native fixture setup probe; no performance claim"
		report["ok"] = report.failures.is_empty() and report.captures.size() == 1
		var probe_file: FileAccess = FileAccess.open(output_dir.path_join("report.json"), FileAccess.WRITE)
		probe_file.store_string(JSON.stringify(report, "\t") + "\n")
		probe_file.close()
		print("BENCHMARK_LOCK_PROBE ", "PASS" if report.ok else "FAIL", " failures=", report.failures)
		quit(0 if report.ok else 1)
		return
	for view: Dictionary in cases:
		camera.position = view.position
		camera.look_at(view.target)
		for angle: Dictionary in angles:
			world.sun.rotation = angle.rotation
			await capture(str(view.id) + "_" + str(angle.id), view, angle)
	world.sun.rotation = original_rotation
	camera.position = cases[0].position
	camera.look_at(cases[0].target)
	report["startup_s"] = float(Time.get_ticks_usec() - started_us) / 1000000.0
	var frame_times: Array[float] = []
	var draw_calls: Array[float] = []
	var process_times: Array[float] = []
	var primitives: Array[float] = []
	var drawn_steps: Array[int] = []
	var configured_cap: int = Engine.max_fps
	Engine.max_fps = 0
	for frame: int in range(180):
		var started: int = Time.get_ticks_usec()
		var drawn_before := Engine.get_frames_drawn()
		camera.position = cases[0].position + Vector3(sin(float(frame) * 0.035) * 8.0, 0, cos(float(frame) * 0.035) * 6.0)
		camera.look_at(cases[0].target)
		await process_frame
		check_benchmark_forcing("moving_camera_%03d" % frame)
		if frame >= 60:
			drawn_steps.append(Engine.get_frames_drawn() - drawn_before)
			frame_times.append(float(Time.get_ticks_usec() - started) / 1000.0)
			draw_calls.append(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
			process_times.append(Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0)
			primitives.append(Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME))
	frame_times.sort()
	report.moving_camera = {"sample_frames": frame_times.size(), "median_wall_frame_ms": frame_times[int(frame_times.size() / 2)], "p95_wall_frame_ms": frame_times[int(frame_times.size() * 0.95)], "process_frame_mean_ms": mean(process_times), "draw_calls_mean": mean(draw_calls), "fps_cap": Engine.max_fps, "configured_fps_cap": configured_cap, "scope": "Frozen forcing and foliage with a moving camera; wall time includes common per-frame forcing verification and any display synchronization. No isolated GPU timing."}
	report["resolution"] = [root.size.x, root.size.y]
	report.moving_camera["primitives_mean"] = mean(primitives)
	report.moving_camera["drawn_frame_steps"] = drawn_steps
	var canopy: Node3D = world.find_child("AuthoredCanopySurface", true, false)
	report["feature_state"] = {"residual_canopy_visible": canopy != null and canopy.visible, "source_cells": canopy.get_meta("active_cells") if canopy != null else 0, "far_tree_lod_end_m": 3000.0}
	report["cpu"] = OS.get_processor_name()
	report["memory_static_peak_bytes"] = Performance.get_monitor(Performance.MEMORY_STATIC_MAX)
	report["mode"] = "offline baked; frozen forcing during timing"
	report["release_id"] = world.ecosystem.frame_header.get("release_id", "legacy")
	report["renderer"] = RenderingServer.get_current_rendering_method()
	report["godot"] = Engine.get_version_info().string
	report["shadow"] = {"range_m": world.sun.directional_shadow_max_distance, "normal_bias": world.sun.shadow_normal_bias, "bias": world.sun.shadow_bias}
	report.benchmark_fixture["last_state"] = forcing_state()
	report.benchmark_fixture["forcing_checks"] = benchmark_checks
	report.benchmark_fixture["forcing_unchanged"] = expected_forcing == forcing_state()
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
	check_benchmark_forcing("capture_" + id, angle.rotation)
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
	report.captures.append({"id": id, "file": path.get_file(), "position_m": vector_array(view.position), "target_m": vector_array(view.target), "sun_rotation_radians": vector_array(world.sun.rotation), "expected_sun_rotation_radians": vector_array(angle.rotation), "forcing_epoch_unix": world.atmosphere_controller.get("_simulation_epoch_unix"), "sha256": FileAccess.get_sha256(path)})
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

func record_portfolio() -> void:
	var source: String = world.ReleaseData.resolve_path("res://data/portfolio_comparison.json")
	var comparison: Variant = JSON.parse_string(FileAccess.get_file_as_string(source))
	if not comparison is Dictionary or comparison.get("schema") != "yellowstone.portfolio_comparison.v1":
		push_error("The portfolio build and its comparison artifact are required.")
		quit(1)
		return
	world.ecosystem.paused = true
	var layer := CanvasLayer.new()
	layer.layer = 100
	root.add_child(layer)
	var header := Label.new()
	header.position = Vector2(28, 24)
	header.add_theme_font_size_override("font_size", 24)
	header.add_theme_color_override("font_shadow_color", Color.BLACK)
	header.add_theme_constant_override("shadow_outline_size", 5)
	layer.add_child(header)
	var note := Label.new()
	note.position = Vector2(28, 74)
	note.add_theme_font_size_override("font_size", 17)
	note.add_theme_color_override("font_shadow_color", Color.BLACK)
	note.add_theme_constant_override("shadow_outline_size", 4)
	layer.add_child(note)
	var plot := ComparisonPlot.new()
	plot.position = Vector2(880, 620)
	plot.size = Vector2(530, 250)
	plot.frames = comparison.frames
	layer.add_child(plot)
	var probe: Dictionary = comparison.probe_cell
	var position: Array = probe.position_xyz
	var river_target := Vector3(float(position[0]), float(position[1]), float(position[2]))
	var route: Array[Dictionary] = [
		{"name": "thermal boardwalk", "position": Vector3(-115, 19, -110), "target": Vector3(-99, 11, -9)},
		{"name": "mapped river probe", "position": river_target + Vector3(28, 8, 14), "target": river_target},
		{"name": "overlook", "position": Vector3(-242, 52, 160), "target": Vector3(-213, 30, 125)}]
	var frame_times: Array[float] = []
	var fps: int = 30
	var seconds: float = 72.0
	var frame_count: int = int(seconds * fps)
	for frame: int in range(frame_count):
		var begun: int = Time.get_ticks_usec()
		var elapsed: float = float(frame) / fps
		var model_s: float = clampf((elapsed - 20.0) / 42.0, 0.0, 1.0) * float(comparison.frames[-1].t_s)
		world.ecosystem.elapsed = model_s
		world.ecosystem.call("_apply_replay", model_s)
		world.update_environment()
		var route_index: int = 0 if elapsed < 20 else 1 if elapsed < 62 else 2
		var view: Dictionary = route[route_index]
		camera.position = view.position + Vector3(sin(elapsed * 0.15) * 2.0, 0, cos(elapsed * 0.15) * 2.0)
		camera.look_at(view.target)
		plot.visible = elapsed >= 20 and elapsed < 62
		plot.time_s = model_s
		plot.queue_redraw()
		world.overlay.visible = elapsed >= 12 and elapsed < 20
		world.menu.visible = false
		world.map_view.visible = world.overlay.visible
		header.text = "YELLOWSTONE | actual Godot render | " + str(world.ReleaseData.active.manifest.release_id).left(12)
		var row: Dictionary = comparison.frames[mini(int(model_s / 10.0), comparison.frames.size()-1)]
		if elapsed < 12:
			note.text = "Midway thermal boardwalk | fixed June 21 scenario | measured geography, illustrative ecology"
		elif elapsed < 20:
			note.text = "USGS 2020 elevation / canopy | USDA NAIP July 19, 2022 | EPSG:32612; 1 unit = 1 m"
		elif elapsed < 62:
			note.text = "Baked Newton model | time %.0f s | input %.2f C
Probe %s: control %.3f C / intervention %.3f C
One authored intervention: Excelsior river-entry temperature +18 C, 600-3600 s" % [model_s, float(row.input_c), str(probe.id), float(row.control_c), float(row.intervention_c)]
		else:
			note.text = "Measured geography | simulated river heat | authored widths, depths and ecological rates
Numerical closure and execution parity checked; ecological forecast validation unavailable."
		await RenderingServer.frame_post_draw
		frame_times.append(float(Time.get_ticks_usec() - begun) / 1000.0)
		if frame in [150, 450, 1050, 1950]:
			root.get_texture().get_image().save_png(output_dir.path_join("portfolio_%04d.png" % frame))
	frame_times.sort()
	var receipt := {"schema": "yellowstone.portfolio_capture.v1", "status": "actual_engine_recording",
		"duration_s": seconds, "frames": frame_count, "fps": fps, "resolution": [root.size.x, root.size.y],
		"release_id": world.ReleaseData.active.manifest.release_id, "build_id": comparison.build_id,
		"comparison_sha256": FileAccess.get_sha256(source), "model_variant_id": comparison.model_variant_id,
		"date_utc": world.ecosystem._replay.simulation_time.start_utc,
		"wind_seed": 11, "route": route, "mode": "offline baked with fixed sampled model time",
		"renderer": RenderingServer.get_current_rendering_method(), "godot": Engine.get_version_info().string,
		"cpu": OS.get_processor_name(), "median_capture_wall_frame_ms": frame_times[int(frame_times.size()/2)],
		"p95_capture_wall_frame_ms": frame_times[int(frame_times.size()*0.95)],
		"performance_scope": "Movie capture overhead; normal exploration performance is measured separately"}
	var file := FileAccess.open(output_dir.path_join("portfolio-capture.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(receipt, "\t") + "\n")
	file.close()
	print("PORTFOLIO_CAPTURE PASS frames=", frame_count)
	quit(0)

# Work-only control fixture. The original project harness and baseline package are untouched.
func disable_benchmark_input(node: Node) -> void:
	for flag: String in ["set_process_input", "set_process_unhandled_input", "set_process_unhandled_key_input", "set_process_shortcut_input"]:
		node.call(flag, false)
	input_callbacks_disabled += 1
	for child: Node in node.get_children():
		disable_benchmark_input(child)

func stop_external_reader(node: Node) -> void:
	if node == null:
		return
	node.set_process(false)
	node.set_physics_process(false)
	# Disconnect callbacks as well as polling: a queued request can finish after process(false).
	for signal_info: Dictionary in node.get_signal_list():
		for connection: Dictionary in node.get_signal_connection_list(signal_info.name):
			node.disconnect(signal_info.name, connection.callable)
	for child: Node in node.get_children():
		if child is HTTPRequest:
			child.cancel_request()
		stop_external_reader(child)

func lock_benchmark_forcing() -> void:
	world.set_process(false)
	world.ecosystem.set_process(false)
	world.ecosystem.paused = true
	world.ecosystem.live_mode = false
	world.atmosphere_controller.set_process(false)
	stop_external_reader(world.weather_snapshot_reader)
	world.weather_snapshot_reader.live_snapshot_path = ""
	stop_external_reader(world.live_client)
	stop_external_reader(world.data_watcher)
	disable_benchmark_input(world)
	world.player.enabled = false
	world.player.set_physics_process(false)
	world.ecosystem.elapsed = float(fixture.elapsed_s)
	world.ecosystem.call("_apply_replay", float(fixture.elapsed_s))
	world.ecosystem.epoch_unix = float(fixture.simulation_epoch_unix)
	world.set("_simulation_start_epoch_unix", float(fixture.simulation_epoch_unix))
	world.set("_simulation_epoch_unix", float(fixture.simulation_epoch_unix))
	world.set("_has_simulation_epoch", true)
	world.ecosystem.air_c = float(fixture.weather.air_temperature_c)
	world.ecosystem.humidity = float(fixture.weather.relative_humidity)
	world.ecosystem.cloud = float(fixture.weather.cloud_fraction)
	world.ecosystem.wind = Vector2(float(fixture.ecosystem_wind_xz_mps[0]), float(fixture.ecosystem_wind_xz_mps[1]))
	world.update_environment()
	world.refresh_env_caches()
	var atmosphere: Node = world.atmosphere_controller
	atmosphere.smooth_weather_transitions = false
	atmosphere.set("_visual_weight", 1.0)
	atmosphere.set_simulation_timestamp(float(fixture.simulation_epoch_unix), float(fixture.utc_offset_hours))
	if atmosphere.has_method("reset_simulation_elapsed"):
		atmosphere.reset_simulation_elapsed(float(fixture.elapsed_s))
	atmosphere.set("_cloud_offset", Vector2.ZERO)
	var state: Dictionary = fixture.weather.duplicate(true)
	state["terrain"] = fixture.terrain.duplicate(true)
	atmosphere.set_weather_state(state)
	atmosphere.call("_update_atmosphere", 0.0)
	# Same physical lighting in both versions; old source used the opposite north/south sign.
	var az: float = deg_to_rad(float(state.solar_azimuth_deg))
	var el: float = deg_to_rad(float(state.solar_elevation_deg))
	var direction := Vector3(sin(az) * cos(el), sin(el), -cos(az) * cos(el)).normalized()
	world.sun.look_at(world.sun.global_position - direction, Vector3.UP)
	var cloud_material: ShaderMaterial = atmosphere.get("_cloud_material")
	cloud_material.set_shader_parameter("sun_direction", direction)
	for material: ShaderMaterial in world.foliage_materials:
		material.set_shader_parameter("wind_vector", Vector2.ZERO)
	world.overlay.visible = false
	var canonical: String = FileAccess.get_file_as_string(fixture_path).strip_edges()
	var hashes: Dictionary = {}
	for source: String in ["res://scripts/shadow_quality.gd", "res://shaders/physical_daylight.gdshader", "res://shaders/yellowstone_cloud_shell.gdshader", "res://project.godot", "res://scripts/world.gd", "res://scripts/yellowstone_atmosphere.gd", "res://scripts/weather_snapshot_reader.gd", "res://tools/validate_terrain_render.gd", "res://scenes/authored_world.tscn", "res://data/release.json"]:
		hashes[source] = FileAccess.get_sha256(source)
	for source: String in ["res://data/world.json", "res://data/weather_snapshot.json", "res://data/ecosystem.json", "res://data/river_replay.json"]:
		hashes["active:" + source] = world.ReleaseData.get_sha256(source)
	validate_requested_forcing(direction)
	expected_forcing = forcing_state()
	report["benchmark_fixture"] = {"schema": "yellowstone.forest_benchmark_lock.v1", "canonical_payload": fixture, "canonical_payload_json": canonical, "canonical_payload_sha256": canonical.sha256_text(), "fixture_path": fixture_path, "fixture_file_sha256": FileAccess.get_sha256(fixture_path), "harness_path": get_script().resource_path, "harness_sha256": FileAccess.get_sha256(get_script().resource_path), "source_hashes": hashes, "first_state": expected_forcing.duplicate(true), "window_title": benchmark_label, "input_nodes_disabled": input_callbacks_disabled, "external_readers_disabled": true, "requested_forcing_validated": report.failures.is_empty(), "normalization": fixture.provenance.solar_convention, "scope": "Identical authored meteorological forcing, frozen replay t=0, zero foliage wind, original render settings and geometry per version. Shader TIME/particles remain animated; renderer improvements remain active."}

func forcing_state() -> Dictionary:
	var atmosphere: Node = world.atmosphere_controller
	var cloud_material: ShaderMaterial = atmosphere.get("_cloud_material")
	var cloud_offset: Vector2 = atmosphere.get("_cloud_offset")
	var sun_color: Color = world.sun.light_color
	return {"simulation_epoch_unix": atmosphere.get("_simulation_epoch_unix"), "world_epoch_unix": world.get("_simulation_epoch_unix"), "ecosystem_epoch_unix": world.ecosystem.epoch_unix, "elapsed_s": world.ecosystem.elapsed, "weather": atmosphere.get("_weather").duplicate(true), "weather_target": atmosphere.get("_weather_target").duplicate(true), "terrain": atmosphere.get_terrain_state(), "source_solar_degrees": [atmosphere.get("_solar_azimuth_deg"), atmosphere.get("_solar_elevation_deg")], "sun_rotation_radians": vector_array(world.sun.rotation), "sun_direction": vector_array(world.sun.global_basis.z), "cloud_sun_direction": vector_array(cloud_material.get_shader_parameter("sun_direction")), "cloud_offset": [cloud_offset.x, cloud_offset.y], "sun_energy": world.sun.light_energy, "sun_color": [sun_color.r, sun_color.g, sun_color.b], "ecosystem_wind_xz_mps": [world.ecosystem.wind.x, world.ecosystem.wind.y], "resolution": [root.size.x, root.size.y], "msaa_3d": root.msaa_3d, "shadow_enabled": world.sun.shadow_enabled, "shadow_mode": world.sun.directional_shadow_mode, "shadow_splits": [world.sun.directional_shadow_split_1, world.sun.directional_shadow_split_2, world.sun.directional_shadow_split_3], "shadow_blend_splits": world.sun.directional_shadow_blend_splits, "shadow_fade_start": world.sun.directional_shadow_fade_start, "shadow_atlas_size": ProjectSettings.get_setting_with_override("rendering/lights_and_shadows/directional_shadow/size"), "shadow_filter_quality": ProjectSettings.get_setting_with_override("rendering/lights_and_shadows/directional_shadow/soft_shadow_filter_quality"), "shadow_range_m": world.sun.directional_shadow_max_distance, "shadow_bias": world.sun.shadow_bias, "shadow_normal_bias": world.sun.shadow_normal_bias, "world_process": world.is_processing(), "ecosystem_process": world.ecosystem.is_processing(), "atmosphere_process": atmosphere.is_processing(), "weather_reader_process": world.weather_snapshot_reader.is_processing(), "live_reader_process": world.live_client.is_processing(), "data_watcher_process": world.data_watcher.is_processing(), "world_unhandled_input": world.is_processing_unhandled_input(), "gui_input_disabled": root.gui_disable_input}

func check_benchmark_forcing(stage: String, expected_rotation: Vector3 = Vector3(INF, INF, INF)) -> void:
	benchmark_checks += 1
	var actual: Dictionary = forcing_state()
	var expected: Dictionary = expected_forcing.duplicate(true)
	if expected_rotation.is_finite():
		expected["sun_rotation_radians"] = vector_array(expected_rotation)
		expected["sun_direction"] = vector_array(Basis.from_euler(expected_rotation).z)
	for key: String in expected:
		# Basis reconstruction can round at 1e-7; rotations and all other forcing remain exact.
		if key == "sun_direction" and expected_rotation.is_finite():
			var a: Array = actual[key]
			var b: Array = expected[key]
			if Vector3(a[0], a[1], a[2]).distance_to(Vector3(b[0], b[1], b[2])) <= 0.000001:
				continue
		if actual[key] != expected[key]:
			var failure: String = "Benchmark forcing drift at %s: %s" % [stage, key]
			if failure not in report.failures:
				report.failures.append(failure)

func validate_requested_forcing(direction: Vector3) -> void:
	var actual: Dictionary = forcing_state()
	for key: String in ["simulation_epoch_unix", "world_epoch_unix", "ecosystem_epoch_unix"]:
		if actual[key] != float(fixture.simulation_epoch_unix):
			report.failures.append("Fixture epoch not applied: " + key)
	if actual.elapsed_s != float(fixture.elapsed_s):
		report.failures.append("Fixture elapsed time not applied")
	for group: String in ["weather", "weather_target", "terrain"]:
		var requested: Dictionary = fixture.terrain if group == "terrain" else fixture.weather
		for key: String in requested:
			if not actual[group].has(key) or absf(float(actual[group][key]) - float(requested[key])) > 0.000000001:
				report.failures.append("Fixture field not applied: " + group + "." + key)
	if actual.source_solar_degrees != [float(fixture.weather.solar_azimuth_deg), float(fixture.weather.solar_elevation_deg)]:
		report.failures.append("Fixture solar angles not applied")
	for key: String in ["sun_direction", "cloud_sun_direction"]:
		var values: Array = actual[key]
		if Vector3(values[0], values[1], values[2]).distance_to(direction) > 0.000001:
			report.failures.append("Fixture physical sun direction not applied: " + key)
	if actual.cloud_offset != fixture.cloud_offset:
		report.failures.append("Fixture cloud origin not applied")
	var node: Node = world
	if node.is_processing_input() or node.is_processing_unhandled_input() or node.is_processing_unhandled_key_input() or node.is_processing_shortcut_input():
		report.failures.append("World input remains active")
	for key: String in ["world_process", "ecosystem_process", "atmosphere_process", "weather_reader_process", "live_reader_process", "data_watcher_process", "world_unhandled_input"]:
		if actual[key]:
			report.failures.append("Fixture process lock not applied: " + key)
	if not actual.gui_input_disabled:
		report.failures.append("GUI input remains active")
	if actual.resolution != [1440, 900] or actual.msaa_3d != 2 or actual.shadow_atlas_size != 4096 or actual.shadow_filter_quality != 3 or not actual.shadow_enabled or actual.shadow_range_m != 140.0:
		report.failures.append("Original benchmark render/shadow quality settings differ")
	for material: ShaderMaterial in world.foliage_materials:
		if material.get_shader_parameter("wind_vector") != Vector2.ZERO:
			report.failures.append("Fixture foliage wind not frozen")
			break
