extends SceneTree
## Checks selected-generation color binding, radial coverage, and weather response.

const ReleaseData = preload("res://scripts/release_data.gd")
const PoolOverlay = preload("res://scripts/pool_overlay.gd")
var failures: Array[String] = []
var checks := 0

func reference_sky(direction: Vector3, sun: DirectionalLight3D) -> Color:
	var mu := maxf(direction.y, 0.02)
	var toward_sun := sun.global_basis.z.normalized()
	var mu_sun := maxf(toward_sun.y, 0.03)
	var cosine := clampf(direction.dot(toward_sun), -1.0, 1.0)
	var phase_r := 3.0 / (16.0 * PI) * (1.0 + cosine * cosine)
	var g := 0.76
	var phase_m := (1.0 - g * g) / (4.0 * PI * pow(1.0 + g * g - 2.0 * g * cosine, 1.5))
	var molecular := Vector3(5.802e-6, 13.558e-6, 33.1e-6) * 8000.0 * 0.759572
	var ozone := Vector3(0.650e-6, 1.881e-6, 0.085e-6) * 15000.0
	var radiance := Vector3.ZERO
	for channel: int in 3:
		var tau := molecular[channel] + 0.0024
		var integral := 0.0
		for slice: int in 4096:
			var fraction := (slice + 0.5) / 4096.0
			integral += exp(-tau * (fraction / mu + (1.0 - fraction) / mu_sun)) / (mu * 4096.0)
		radiance[channel] = (molecular[channel] * phase_r + 0.0024 * phase_m) * integral * exp(-ozone[channel] / mu_sun)
	radiance *= 32.0 * sun.light_energy
	radiance /= 1.0 + radiance.dot(Vector3(0.2126, 0.7152, 0.0722))
	return Color(radiance.x, radiance.y, radiance.z).linear_to_srgb()

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, detail: String) -> void:
	checks += 1
	if not condition:
		failures.append(detail)

func run() -> void:
	ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:1")
	var world: Node = load("res://scenes/main.tscn").instantiate()
	root.add_child(world)
	for frame: int in 12:
		await process_frame
	world.set_process(false)
	world.atmosphere_controller.set_process(false)
	world.weather_snapshot_reader.set_process(false)
	var pools: Array[Dictionary] = []
	var overlay: Node
	for child: Node in world.get_children():
		if child is PoolOverlay:
			overlay = child
	check(overlay != null, "Pool overlay is absent from the runtime")
	for mesh: MeshInstance3D in get_nodes_in_group("thermal_surfaces"):
		var material: ShaderMaterial = mesh.mesh.surface_get_material(0)
		var name: String = str(mesh.get_meta("feature_name", ""))
		var path: String = str(material.get_meta("pool_ramp_path", ""))
		check(float(material.get_shader_parameter("ramp_mix")) == 1.0, "Unbound pool ramp: " + name)
		check(path.begins_with(str(ReleaseData.active.get("root", "missing")) + "/"), "Ramp bypasses the selected generation: " + name)
		check(FileAccess.get_sha256(path) == material.get_meta("pool_ramp_sha256", "missing"), "Ramp bytes disagree with runtime binding: " + name)
		var low := 1.0
		var high := 0.0
		var colors: PackedColorArray = mesh.mesh.surface_get_arrays(0)[Mesh.ARRAY_COLOR]
		for color: Color in colors:
			low = minf(low, color.r)
			high = maxf(high, color.r)
		check(low == 0.0 and high == 1.0, "Pool mesh omits part of the radial color range: " + name)
		var metadata: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path.get_basename() + ".json"))
		check(metadata.get("color_space") == "linear_rgb" and metadata.get("texture_color_space") == "srgb", "Pool color encoding is unspecified: " + name)
		pools.append({"name": name, "path": path, "sha256": material.get_meta("pool_ramp_sha256"), "radial_range": [low, high]})
	check(pools.size() > 0, "No thermal pools checked")
	check(int(overlay.primary_applied) == pools.size() and int(overlay.secondary_applied) == 0, "Runtime uses incomplete or fallback pool colors")
	var far_batches := 0
	var far_instances := 0
	for node: Node in world.find_children("*", "MultiMeshInstance3D", true, false):
		var material: Material = node.multimesh.mesh.surface_get_material(0)
		if material is ShaderMaterial and material.has_meta("impostor_form"):
			var layers: Texture2DArray = material.get_shader_parameter("view_layers")
			check(layers != null and layers.get_layers() == 16, "Saved scene omits distant-tree variant layers")
			far_batches += 1
			far_instances += node.multimesh.instance_count
	check(far_batches > 0 and far_instances > 0, "No saved distant-tree batches checked")
	if not pools.is_empty():
		var fixture := FileAccess.open("user://incompatible_ramp.json", FileAccess.WRITE)
		fixture.store_string('{"schema":"yellowstone.pool_radiative_ramp.v1","pool_id":"wrong-pool"}')
		fixture.close()
		var probe := ShaderMaterial.new()
		probe.shader = load("res://shaders/water.gdshader")
		check(not overlay._apply_ramp(probe, pools[0].path, "user://incompatible_ramp.json", "expected-pool"), "Mismatched pool metadata is accepted")
	var atmosphere: Node = world.atmosphere_controller
	atmosphere.smooth_weather_transitions = false
	var states: Dictionary = {}
	for case: Dictionary in [
		{"id": "clear", "cloud_fraction": 0.0, "visibility_m": 24000.0, "solar_elevation_deg": 50.0},
		{"id": "overcast", "cloud_fraction": 1.0, "visibility_m": 24000.0, "solar_elevation_deg": 50.0},
		{"id": "hazy", "cloud_fraction": 0.5, "visibility_m": 2000.0, "solar_elevation_deg": 50.0},
		{"id": "night", "cloud_fraction": 0.0, "visibility_m": 24000.0, "solar_elevation_deg": -12.0},
	]:
		case["solar_azimuth_deg"] = 180.0
		atmosphere.set_weather_state(case)
		states[case.id] = atmosphere.get_render_state()
		if case.id == "clear" and DisplayServer.get_name() != "headless":
			var camera := Camera3D.new()
			world.add_child(camera)
			camera.position = Vector3(-242, 52, 160)
			camera.look_at(camera.position + Vector3(0, 1, -0.01))
			camera.make_current()
			for frame: int in 12:
				await process_frame
			await RenderingServer.frame_post_draw
			var image := root.get_texture().get_image()
			var color := image.get_pixel(image.get_width() / 2, image.get_height() / 2)
			check(color.b > color.r * 1.3 and color.g > color.r * 1.05 and color.b > 0.4, "Clear zenith fails the declared blue-sky display check")
			states[case.id]["zenith_rgb"] = [color.r, color.g, color.b]
			var pixel_uv := Vector2(image.get_width() / 2 + 0.5, image.get_height() / 2 + 0.5) / Vector2(image.get_size())
			var expected := reference_sky(camera.project_ray_normal(pixel_uv * root.get_visible_rect().size), world.sun)
			var error := maxf(absf(color.r - expected.r), maxf(absf(color.g - expected.g), absf(color.b - expected.b)))
			check(error <= 2.0 / 255.0, "Native linear-light sky disagrees with independent optical-depth quadrature")
			states[case.id]["quadrature_maximum_channel_error"] = error
			states[case.id]["quadrature_expected_rgb"] = [expected.r, expected.g, expected.b]
			image.save_png("res://work/clear_sky_zenith.png")
			camera.free()
	check(float(states.clear.fog_sky_affect) == 0.0, "Clear physical sky receives a gray fog overlay")
	check(float(states.clear.direct_light_energy) > float(states.clear.ambient_light_energy), "Clear day lacks direct-light contrast")
	check(float(states.overcast.direct_light_energy) < float(states.clear.direct_light_energy), "Clouds fail to dim direct sunlight")
	check(float(states.overcast.ambient_light_energy) > float(states.clear.ambient_light_energy), "Clouds fail to increase diffuse lighting")
	check(float(states.hazy.fog_sky_affect) > 0.0 and float(states.hazy.sky_turbidity) > float(states.clear.sky_turbidity), "Reduced visibility fails to restore haze")
	check(float(states.night.direct_light_energy) == 0.0 and float(states.night.ambient_light_energy) > 0.0, "Night lighting response fails")
	check(float(states.clear.star_visibility) == 0.0 and float(states.night.star_visibility) == 1.0, "Stars remain visible in daylight")
	var report := {"ok": failures.is_empty(), "checks": checks, "release_id": ReleaseData.active.get("manifest", {}).get("release_id", ""), "pools": pools, "far_batches": far_batches, "far_instances": far_instances, "weather_cases": states, "failures": failures}
	var output := "res://work/display_color_report.json"
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--out="):
			output = arg.trim_prefix("--out=")
	var file := FileAccess.open(output, FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t") + "\n")
	print("DISPLAY_COLOR ", checks, " checks; ", failures.size(), " failures")
	quit(0 if failures.is_empty() else 1)
