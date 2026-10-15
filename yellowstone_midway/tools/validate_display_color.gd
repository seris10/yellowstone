extends SceneTree
## Checks selected-generation color binding, radial coverage, and weather response.

const ReleaseData = preload("res://scripts/release_data.gd")
const PoolOverlay = preload("res://scripts/pool_overlay.gd")
var failures: Array[String] = []
var checks := 0

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
	check(float(states.clear.fog_sky_affect) == 0.0, "Clear physical sky receives a gray fog overlay")
	check(float(states.clear.direct_light_energy) > float(states.clear.ambient_light_energy), "Clear day lacks direct-light contrast")
	check(float(states.overcast.direct_light_energy) < float(states.clear.direct_light_energy), "Clouds fail to dim direct sunlight")
	check(float(states.overcast.ambient_light_energy) > float(states.clear.ambient_light_energy), "Clouds fail to increase diffuse lighting")
	check(float(states.hazy.fog_sky_affect) > 0.0 and float(states.hazy.sky_turbidity) > float(states.clear.sky_turbidity), "Reduced visibility fails to restore haze")
	check(float(states.night.direct_light_energy) == 0.0 and float(states.night.ambient_light_energy) > 0.0, "Night lighting response fails")
	var report := {"ok": failures.is_empty(), "checks": checks, "release_id": ReleaseData.active.get("manifest", {}).get("release_id", ""), "pools": pools, "far_batches": far_batches, "far_instances": far_instances, "weather_cases": states, "failures": failures}
	var output := "res://work/display_color_report.json"
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--out="):
			output = arg.trim_prefix("--out=")
	var file := FileAccess.open(output, FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t") + "\n")
	print("DISPLAY_COLOR ", checks, " checks; ", failures.size(), " failures")
	quit(0 if failures.is_empty() else 1)
