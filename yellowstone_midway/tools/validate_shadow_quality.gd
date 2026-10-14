extends SceneTree
## Headless parameter and solar-update regression check; visual/contact/performance checks are separate.

const ShadowQuality = preload("res://scripts/shadow_quality.gd")
const Atmosphere = preload("res://scripts/yellowstone_atmosphere.gd")
var failures: Array[String] = []
var checks: int = 0

func _initialize() -> void:
	call_deferred("validate")

func check(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures.append(label)

func same_shadow_state(sun: DirectionalLight3D, expected: Dictionary, label: String) -> void:
	for name: String in expected:
		var value: Variant = sun.get(name)
		var wanted: Variant = expected[name]
		check(is_equal_approx(float(value), float(wanted)) if wanted is float else value == wanted, label + ":" + name)

func shadow_state(sun: DirectionalLight3D) -> Dictionary:
	var state: Dictionary = {}
	for name: String in ["shadow_enabled", "directional_shadow_mode", "directional_shadow_max_distance", "directional_shadow_split_1", "directional_shadow_split_2", "directional_shadow_split_3", "directional_shadow_blend_splits", "directional_shadow_fade_start", "shadow_bias", "shadow_normal_bias"]:
		state[name] = sun.get(name)
	return state

func validate() -> void:
	var scope: Node3D = Node3D.new()
	get_root().add_child(scope)
	var sun: DirectionalLight3D = DirectionalLight3D.new()
	scope.add_child(sun)
	var settings: Dictionary = ShadowQuality.apply(sun)
	check(sun.shadow_enabled, "sun enabled")
	check(sun.directional_shadow_mode == DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS, "four cascades")
	check(is_equal_approx(sun.directional_shadow_max_distance, float(settings["range_m"])), "configured coverage")
	check(sun.directional_shadow_split_1 < sun.directional_shadow_split_2 and sun.directional_shadow_split_2 < sun.directional_shadow_split_3, "ordered cascade offsets")
	check(is_equal_approx(sun.shadow_normal_bias, float(settings["normal_bias"])), "configured normal bias")
	check(str(ProjectSettings.get_setting_with_override("rendering/renderer/rendering_method")) == "gl_compatibility", "Compatibility retained")
	check(int(settings["atlas_size"]) == 4096, "default 4096 atlas")
	check(int(settings["filter_quality"]) == 3, "default Soft Medium filter")
	var preset_results: Dictionary = {}
	for preset: String in ShadowQuality.PRESET_RANGES_M:
		var resolved: Dictionary = ShadowQuality.apply(sun, preset)
		preset_results[preset] = resolved["range_m"]
		check(is_equal_approx(sun.directional_shadow_max_distance, float(resolved["range_m"])), "preset applied:" + preset)
	ShadowQuality.apply(sun)
	var authored: Dictionary = shadow_state(sun)
	var controller: Node3D = Atmosphere.new()
	scope.add_child(controller)
	controller.set("_sun", sun)
	for hour: float in [6.0, 12.0, 17.0]:
		controller.call("set_simulation_time", hour, 196, -6.0)
		same_shadow_state(sun, authored, "clock preserves policy")
	for elevation: float in [8.0, 30.0, 65.0]:
		controller.call("set_weather_state", {"solar_azimuth_deg": 210.0, "solar_elevation_deg": elevation, "cloud_fraction": 0.55})
		same_shadow_state(sun, authored, "weather preserves policy")
	sun.shadow_enabled = false
	sun.directional_shadow_max_distance = 123.0
	var diagnostic: Dictionary = shadow_state(sun)
	controller.call("set_simulation_timestamp", 1784156400.0, -6.0)
	controller.call("clear_weather_solar_override")
	same_shadow_state(sun, diagnostic, "solar preserves diagnostic override")
	var canonical: String = FileAccess.get_file_as_string("res://scripts/yellowstone_atmosphere.gd")
	var bundle_path: String = ProjectSettings.globalize_path("res://").path_join("../yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd")
	check(FileAccess.file_exists(bundle_path), "atmosphere bundle exists")
	check(canonical == FileAccess.get_file_as_string(bundle_path), "atmosphere canonical pair identical")
	check(not canonical.contains("directional_shadow_max_distance ="), "atmosphere owns no shadow range")
	check(not canonical.contains("_sun.shadow_enabled ="), "atmosphere owns no shadow enable switch")
	var report: Dictionary = {"ok": failures.is_empty(), "checks": checks, "failures": failures, "settings": settings, "preset_ranges_m": preset_results, "verification": "Headless parameter tests; visual contact, movement and GPU frame time require rendered checks."}
	print("SHADOW_QUALITY ", JSON.stringify(report))
	scope.free()
	quit(0 if failures.is_empty() else 1)
