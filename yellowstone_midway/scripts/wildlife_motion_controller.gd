class_name MidwayWildlifeMotionController
extends RefCounted
## Manual in-place clips synchronized to root travel.
var player: AnimationPlayer
var _clips: Dictionary = {}
var _meters_per_asset_unit: float = 1.0
var _selected: StringName = &""
var _blend_seconds: float = 0.12
var _phase: float = 0.0
var last_clip: String = ""
var last_rate: float = 0.0
var rejected_root_motion: Array[String] = []

func configure(model: Node, manifest: Dictionary, meters_per_asset_unit: float, phase: float = 0.0) -> bool:
	if not is_finite(meters_per_asset_unit) or meters_per_asset_unit <= 0.0:
		return false
	_meters_per_asset_unit = meters_per_asset_unit
	_phase = phase
	var candidates: Array[Node] = model.find_children("*", "AnimationPlayer", true, false)
	if candidates.is_empty():
		return false
	player = candidates[0] as AnimationPlayer
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	player.speed_scale = 1.0
	for entry: Dictionary in manifest.get("clips", []):
		var name: String = str(entry.get("name", ""))
		if bool(entry.get("root_motion", false)):
			rejected_root_motion.append(name)
			continue
		if not bool(entry.get("loop", false)):
			continue
		for actual: StringName in player.get_animation_list():
			if str(actual) == name or str(actual).ends_with("/" + name):
				var speed: float = float(entry.get("speed_asset_units_s", 0.0)) * _meters_per_asset_unit
				if not is_finite(speed) or speed < 0.0:
					continue
				_clips[name] = {"actual": actual, "speed_mps": speed}
	return _clips.has("Idle")

func advance(behavior: String, simulation_dt: float, horizontal_distance_m: float, ghost: bool = false) -> void:
	if player == null or _clips.is_empty() or ghost or simulation_dt <= 0.0:
		return
	if not is_finite(simulation_dt) or not is_finite(horizontal_distance_m) or horizontal_distance_m < 0.0:
		return
	var speed: float = horizontal_distance_m / simulation_dt
	var desired: String = "Idle"
	if speed > 0.000001:
		var distance: float = INF
		for candidate: String in _clips:
			var reference: float = float(_clips[candidate].speed_mps)
			if reference <= 0.0:
				continue
			var score: float = absf(log(speed / reference))
			if behavior == "flee" and candidate in ["Trot", "RunningWalk", "Lope"]:
				score -= 0.1
			if score < distance:
				distance = score
				desired = candidate
	var chosen: Dictionary = _clips.get(desired, _clips["Idle"])
	var actual: StringName = chosen.actual
	var clip: Animation = player.get_animation(actual)
	if _selected != actual:
		_selected = actual
		clip.loop_mode = Animation.LOOP_LINEAR
		player.play(actual, _blend_seconds)
		player.seek(fposmod(_phase, clip.length), true)
	var reference_speed: float = float(chosen.speed_mps)
	var advance_s: float = horizontal_distance_m / reference_speed if reference_speed > 0.0 else simulation_dt
	last_clip = desired
	last_rate = advance_s / simulation_dt
	player.advance(advance_s)

func stop() -> void:
	if is_instance_valid(player):
		player.stop()
