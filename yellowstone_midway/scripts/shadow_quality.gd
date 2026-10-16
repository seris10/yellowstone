extends RefCounted
## Authored walking shadow coverage; renderer atlas/filter budgets stay in project.godot.

const PRESET_RANGES_M: Dictionary = {
	"economical": 120.0,
	"walking": 140.0,
	"capture": 160.0,
}
const PREFIX: String = "yellowstone/shadows/"

static func configuration(preset_name: String = "") -> Dictionary:
	var selected: String = preset_name
	if selected.is_empty():
		selected = str(ProjectSettings.get_setting(PREFIX + "preset", "walking"))
	if not PRESET_RANGES_M.has(selected):
		push_warning("Unknown shadow preset '%s'; using walking." % selected)
		selected = "walking"
	var distance: float = float(PRESET_RANGES_M[selected])
	var override_value: Variant = ProjectSettings.get_setting(PREFIX + "range_override_m", 0.0)
	if _is_number(override_value) and float(override_value) > 0.0:
		distance = clampf(float(override_value), 30.0, 300.0)
	var split_1: float = _number_setting("split_1", 0.04, 0.01, 0.90)
	var split_2: float = _number_setting("split_2", 0.14, 0.02, 0.95)
	var split_3: float = _number_setting("split_3", 0.40, 0.03, 0.99)
	if not split_1 < split_2 or not split_2 < split_3:
		push_warning("Shadow cascade offsets must increase; using 0.04, 0.14, 0.40.")
		split_1 = 0.04
		split_2 = 0.14
		split_3 = 0.40
	return {
		"preset": selected,
		"range_m": distance,
		"split_1": split_1,
		"split_2": split_2,
		"split_3": split_3,
		"blend_splits": bool(ProjectSettings.get_setting(PREFIX + "blend_splits", true)),
		"fade_start": _number_setting("fade_start", 0.82, 0.50, 0.99),
		"bias": _number_setting("bias", 0.03, 0.0, 1.0),
		"normal_bias": _number_setting("normal_bias", 3.0, 0.0, 8.0),
		"atlas_size": ProjectSettings.get_setting_with_override("rendering/lights_and_shadows/directional_shadow/size"),
		"filter_quality": ProjectSettings.get_setting_with_override("rendering/lights_and_shadows/directional_shadow/soft_shadow_filter_quality"),
	}

static func apply(sun: DirectionalLight3D, preset_name: String = "") -> Dictionary:
	var settings: Dictionary = configuration(preset_name)
	if sun == null:
		push_error("Shadow policy requires a DirectionalLight3D.")
		return {}
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.directional_shadow_max_distance = float(settings["range_m"])
	sun.directional_shadow_split_1 = float(settings["split_1"])
	sun.directional_shadow_split_2 = float(settings["split_2"])
	sun.directional_shadow_split_3 = float(settings["split_3"])
	sun.directional_shadow_blend_splits = bool(settings["blend_splits"])
	sun.directional_shadow_fade_start = float(settings["fade_start"])
	sun.shadow_bias = float(settings["bias"])
	sun.shadow_normal_bias = float(settings["normal_bias"])
	return settings

static func _is_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))

static func _number_setting(name: String, fallback: float, minimum: float, maximum: float) -> float:
	var value: Variant = ProjectSettings.get_setting(PREFIX + name, fallback)
	if not _is_number(value):
		push_warning("Invalid shadow setting '%s'; using authored default." % name)
		return fallback
	return clampf(float(value), minimum, maximum)
