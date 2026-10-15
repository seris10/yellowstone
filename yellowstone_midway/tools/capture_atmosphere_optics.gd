extends SceneTree

const Controller = preload("res://scripts/yellowstone_atmosphere.gd")
var atmosphere: Node3D
var camera: Camera3D
var environment: Environment
var capture_records: Array[Dictionary] = []
var output: String = "res://../work/atmosphere-captures"
var receipt: String = "res://../evidence/atmosphere-render.json"


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--output="):
			output = argument.trim_prefix("--output=")
		elif argument.begins_with("--receipt="):
			receipt = argument.trim_prefix("--receipt=")
	root.size = Vector2i(1280, 800)
	root.content_scale_size = Vector2i(1280, 800)
	var world := Node3D.new()
	root.add_child(world)
	var sky := WorldEnvironment.new()
	environment = Environment.new()
	environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	sky.environment = environment
	world.add_child(sky)
	var sun := DirectionalLight3D.new()
	world.add_child(sun)
	camera = Camera3D.new()
	camera.position = Vector3(0.0, 25.0, 0.0)
	camera.fov = 66.0
	camera.far = 2900.0
	world.add_child(camera)
	camera.look_at(camera.position + Vector3(0.0, 0.30, -1.0), Vector3.UP)
	var floor_mesh := MeshInstance3D.new()
	var floor_shape := PlaneMesh.new()
	floor_shape.size = Vector2(6000.0, 6000.0)
	floor_mesh.mesh = floor_shape
	var ground_material := StandardMaterial3D.new()
	ground_material.albedo_color = Color(0.25, 0.30, 0.18)
	floor_mesh.material_override = ground_material
	world.add_child(floor_mesh)
	var block := MeshInstance3D.new()
	var shape := BoxMesh.new()
	shape.size = Vector3(260.0, 250.0, 100.0)
	block.mesh = shape
	block.position = Vector3(400.0, 125.0, -550.0)
	block.material_override = ground_material
	world.add_child(block)
	atmosphere = Controller.new()
	world.add_child(atmosphere)
	atmosphere.configure(sun, environment, camera)
	atmosphere.set_process(false)
	atmosphere.smooth_weather_transitions = false
	atmosphere.set_weather_state({"cloud_fraction": 0.16, "solar_azimuth_deg": 0.0, "solar_elevation_deg": 24.0, "precipitation_rate_mm_h": 0.0})
	atmosphere._update_atmosphere(0.0)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	var clouds_image: Image = await _capture("clear-clouds")
	atmosphere._cloud_shell.visible = false
	var cloud_negative: Image = await _capture("clouds-negative")
	var cloud_foreground_delta: float = _rectangle_delta(clouds_image, cloud_negative)
	atmosphere._cloud_shell.visible = true
	atmosphere.set_weather_state({"cloud_fraction": 0.65})
	atmosphere._update_atmosphere(0.0)
	await _capture("broken-clouds")
	atmosphere.set_weather_state({"cloud_fraction": 0.0, "solar_azimuth_deg": 180.0, "solar_elevation_deg": 14.0, "precipitation_rate_mm_h": 8.0})
	atmosphere._update_atmosphere(0.0)
	var dry_reference: Image = await _capture("rainbow-negative")
	var model = atmosphere._rain_curtain
	model.optical_depth = 1.5
	model.center = Vector3(0.0, 0.0, -1800.0)
	model.base_y_m = 0.0
	model.top_y_m = 2200.0
	model.active = true
	atmosphere._update_atmosphere(0.0)
	var bow_image: Image = await _capture("double-rainbow")
	var foreground_delta: float = 0.0
	var sky_delta: float = 0.0
	for y: int in range(360, 500):
		for x: int in range(980, 1110):
			var delta_color: Color = bow_image.get_pixel(x, y) - dry_reference.get_pixel(x, y)
			foreground_delta = maxf(foreground_delta, maxf(absf(delta_color.r), maxf(absf(delta_color.g), absf(delta_color.b))))
	for y: int in range(120, 400):
		var delta_color: Color = bow_image.get_pixel(640, y) - dry_reference.get_pixel(640, y)
		sky_delta = maxf(sky_delta, maxf(delta_color.r, maxf(delta_color.g, delta_color.b)))
	atmosphere._rain_curtain = atmosphere.OPTICS.new()
	atmosphere.set_weather_state({"cloud_fraction": 0.8, "precipitation_rate_mm_h": 8.0, "wind_direction_deg": 180.0, "wind_speed_mps": 2.0})
	atmosphere._update_atmosphere(120.0)
	atmosphere.set_weather_state({"cloud_fraction": 0.0, "precipitation_rate_mm_h": 0.0})
	atmosphere._update_atmosphere(20.0)
	var post_rain: Image = await _capture("weather-driven-post-rain")
	var weather_bow_delta: float = 0.0
	for y: int in range(120, 500):
		for x: int in range(100, 850):
			var difference: Color = post_rain.get_pixel(x, y) - dry_reference.get_pixel(x, y)
			weather_bow_delta = maxf(weather_bow_delta, maxf(difference.r, maxf(difference.g, difference.b)))
	atmosphere.set_weather_state({"solar_azimuth_deg": 180.0, "solar_elevation_deg": -4.0})
	atmosphere._update_atmosphere(0.0)
	await _capture("night-no-rainbow")
	var passed: bool = foreground_delta <= 1.0 / 255.0 and cloud_foreground_delta <= 1.0 / 255.0 and sky_delta > 0.03 and weather_bow_delta > 0.015
	var result := {"schema": "yellowstone.atmosphere_render.v1", "run_mode": "illustrative", "renderer": RenderingServer.get_current_rendering_method(), "device": RenderingServer.get_video_adapter_name(), "resolution_px": [1280, 800], "camera_far_m": camera.far, "foreground_max_channel_delta": foreground_delta, "cloud_foreground_max_channel_delta": cloud_foreground_delta, "bow_max_channel_delta": sky_delta, "weather_driven_bow_max_channel_delta": weather_bow_delta, "opaque_occlusion_passed": passed, "captures": capture_records, "scope": "controlled synthetic optical fixture; field frequency and human appearance acceptance unmeasured"}
	var file := FileAccess.open(receipt, FileAccess.WRITE)
	file.store_string(JSON.stringify(result, "  ") + "\n")
	file.close()
	print(JSON.stringify(result))
	quit(0 if passed else 1)


func _capture(label: String) -> Image:
	for i: int in range(12):
		await process_frame
	await RenderingServer.frame_post_draw
	var image: Image = root.get_texture().get_image()
	var path: String = output.path_join(label + ".png")
	image.save_png(path)
	capture_records.append({"name": label, "path": path.trim_prefix("res://../"), "sha256": FileAccess.get_sha256(path), "draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME), "primitives": Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)})
	return image


func _rectangle_delta(first: Image, second: Image) -> float:
	var maximum: float = 0.0
	for y: int in range(360, 500):
		for x: int in range(980, 1110):
			var difference: Color = first.get_pixel(x, y) - second.get_pixel(x, y)
			maximum = maxf(maximum, maxf(absf(difference.r), maxf(absf(difference.g), absf(difference.b))))
	return maximum
