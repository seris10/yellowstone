class_name MidwayPythonRiverReplay
extends "res://scripts/ecosystem.gd"

## Python owns river thermal state when replay_path is nonempty.
## Empty path preserves the original ecosystem.
## Replay interpolation is presentation, not a second numerical solver.
## Patch ecology remains the existing illustrative Godot model.

@export_file("*.json") var replay_path: String = ""

var replay_enabled: bool = false
var replay_finished: bool = false
var _replay: Dictionary = {}
var _cells: Array = []
var _frames: Array = []
var _features: Dictionary = {}
var _spatial_state: Array = []
var _frame_index: int = 0

func configure(data: Dictionary) -> bool:
	replay_enabled = false
	replay_finished = false
	_frame_index = 0
	_replay.clear()
	_cells.clear()
	_frames.clear()
	_features.clear()
	_spatial_state.clear()

	var base_ok: bool = super.configure(data)
	if not base_ok or replay_path.is_empty():
		return base_ok

	var value: Variant = JSON.parse_string(
		FileAccess.get_file_as_string(replay_path)
	)
	if not value is Dictionary:
		return _reject("Missing or invalid Python replay.")

	var candidate: Dictionary = value
	if str(candidate.get("schema", "")) != "yellowstone.mapped_river_replay.v1":
		return _reject("Unsupported Python replay schema.")

	var checks: Dictionary = candidate.get("numerical_checks", {})
	if not bool(checks.get("passed", false)):
		return _reject("Python replay numerical checks did not pass.")

	var input_files: Dictionary = candidate.get("input_files", {})
	var world_input: Dictionary = input_files.get("world", {})
	var expected_hash: String = str(world_input.get("sha256", ""))
	if expected_hash.is_empty():
		return _reject("Replay has no world-data hash.")

	var hashing: HashingContext = HashingContext.new()
	if hashing.start(HashingContext.HASH_SHA256) != OK:
		return _reject("Cannot initialize world-data hash.")
	if hashing.update(
		FileAccess.get_file_as_bytes("res://data/world.json")
	) != OK:
		return _reject("Cannot hash world data.")
	if hashing.finish().hex_encode() != expected_hash:
		return _reject("Replay world hash differs from loaded world.json.")

	var candidate_cells: Variant = candidate.get("cells")
	var candidate_frames: Variant = candidate.get("frames")
	var candidate_features: Variant = candidate.get("river_features")
	if not candidate_cells is Array or not candidate_frames is Array:
		return _reject("Replay cells/frames must be arrays.")
	if not candidate_features is Dictionary:
		return _reject("Replay river features must be a dictionary.")
	if candidate_cells.is_empty() or candidate_frames.is_empty():
		return _reject("Replay has no cells or frames.")

	var last_end: float = 0.0
	for row: Variant in candidate_cells:
		if not row is Dictionary:
			return _reject("Invalid replay cell.")
		var start_s: float = float(row.get("start_s_m", NAN))
		var end_s: float = float(row.get("end_s_m", NAN))
		var position_data: Variant = row.get("position_xyz")
		if not is_finite(start_s) or not is_finite(end_s):
			return _reject("Nonfinite cell bounds.")
		if absf(start_s - last_end) > 0.0001 or end_s <= start_s:
			return _reject("Replay cells have a gap or reversed bounds.")
		if not position_data is Array or position_data.size() != 3:
			return _reject("Invalid cell position.")
		for coordinate: Variant in position_data:
			if not is_finite(float(coordinate)):
				return _reject("Nonfinite cell position.")
		if float(row.get("volume_m3", 0.0)) <= 0.0:
			return _reject("Invalid cell volume.")
		last_end = end_s

	var previous_t: float = -1.0
	for row: Variant in candidate_frames:
		if not row is Dictionary:
			return _reject("Invalid replay frame.")
		var time_s: float = float(row.get("t_s", NAN))
		var temperatures: Variant = row.get("temperature_c")
		if not is_finite(time_s) or time_s <= previous_t:
			return _reject("Replay times must increase.")
		if not temperatures is Array or temperatures.size() != candidate_cells.size():
			return _reject("Replay temperature array has wrong size.")
		for temperature: Variant in temperatures:
			if not is_finite(float(temperature)):
				return _reject("Nonfinite replay temperature.")
		previous_t = time_s

	if float(candidate_frames[0]["t_s"]) != 0.0:
		return _reject("Replay must start at zero.")

	for feature_value: Variant in candidate_features.values():
		if not feature_value is Dictionary:
			return _reject("Invalid river feature.")
		var points: Variant = feature_value.get("points_xyz")
		var chainage: Variant = feature_value.get("point_s_m")
		if not points is Array or not chainage is Array:
			return _reject("Invalid river point arrays.")
		if points.size() < 2 or points.size() != chainage.size():
			return _reject("River point/chainage size mismatch.")
		var previous_s: float = -1.0
		for i: int in range(points.size()):
			if not points[i] is Array or points[i].size() != 3:
				return _reject("Invalid river vertex.")
			var location: float = float(chainage[i])
			if not is_finite(location) or location <= previous_s:
				return _reject("River vertex chainage must increase.")
			for coordinate: Variant in points[i]:
				if not is_finite(float(coordinate)):
					return _reject("Nonfinite river vertex.")
			previous_s = location

	_replay = candidate
	_cells = candidate_cells
	_frames = candidate_frames
	_features = candidate_features
	for cell: Dictionary in _cells:
		_spatial_state.append({
			"id": cell["id"],
			"river_id": cell["river_id"],
			"z": float(cell["position_xyz"][2]),
			"temperature_c": 0.0,
			"flow_m3s": float(cell["q_out_m3_s"]),
			"velocity_mps": float(cell["representative_velocity_m_s"]),
			"fish_activity": 0.0,
			"status": "Python simulated; uncalibrated.",
		})

	replay_enabled = true
	_apply_replay(0.0)
	return true

func _reject(message: String) -> bool:
	push_error(message + " Environmental updates disabled; no silent fallback.")
	configuration_valid = false
	set_process(false)
	return false

func step(dt: float) -> void:
	if not replay_enabled:
		super.step(dt)
		return
	if not configuration_valid or dt <= 0.0:
		return

	var final_t: float = float(_frames[-1]["t_s"])
	var available: float = minf(dt, maxf(0.0, final_t - elapsed))
	var remaining: float = available

	# Existing ecological transactions retain their physical-time update.
	while remaining > 0.0000001:
		var h: float = minf(DT, remaining)
		elapsed = minf(final_t, elapsed + h)
		clock_hour = fposmod(
			float(_replay["clock_hour0"]) + elapsed / 3600.0, 24.0
		)
		_update_weather()
		_apply_replay(elapsed)
		_advance_patches(h)
		remaining -= h

	replay_finished = elapsed >= final_t
	if available > 0.0:
		advanced.emit()

func _apply_replay(time_s: float) -> void:
	while _frame_index + 1 < _frames.size():
		if float(_frames[_frame_index + 1]["t_s"]) > time_s:
			break
		_frame_index += 1

	var a: Dictionary = _frames[_frame_index]
	var b: Dictionary = _frames[mini(_frame_index + 1, _frames.size() - 1)]
	var span: float = float(b["t_s"]) - float(a["t_s"])
	var weight: float = 0.0
	if span > 0.0:
		weight = clampf((time_s - float(a["t_s"])) / span, 0.0, 1.0)

	for i: int in range(_spatial_state.size()):
		var temperature: float = lerpf(
			float(a["temperature_c"][i]),
			float(b["temperature_c"][i]),
			weight
		)
		_spatial_state[i]["temperature_c"] = temperature
		# Retained artistic activity proxy, NOT mortality or refuge behavior.
		_spatial_state[i]["fish_activity"] = clampf(
			(26.0 - temperature) / 8.0, 0.0, 1.0
		)

	# Hold air forcing as Python did; do not independently evolve it.
	var weather_trace: Array = _replay["weather_trace"]
	var weather_index: int = mini(
		int(floor(time_s / 60.0)), weather_trace.size() - 1
	)
	air_c = float(weather_trace[weather_index]["air_c"])
	humidity = float(_replay["humidity"])
	cloud = float(_replay["cloud"])

	# Keep the original six-reach consumer interface as point probes.
	for query: Dictionary in _replay["legacy_queries"]:
		var reach_id: String = str(query["reach_id"])
		if _reach_indices.has(reach_id):
			var state: Dictionary = _at_s(float(query["s_m"]))
			var destination: Dictionary = river[int(_reach_indices[reach_id])]
			destination["temperature_c"] = state["temperature_c"]
			destination["fish_activity"] = state["fish_activity"]
			destination["flow_m3s"] = state["flow_m3s"]
			destination["state_basis"] = "Python spatial replay probe"

	# Use the last completed frame budget. Do not interpolate diagnostics.
	heat_ledger = a["budget"].duplicate(true)
	heat_ledger["units"] = "J; water terms m3"
	heat_ledger["budget_time_s"] = a["t_s"]
	heat_ledger["presentation_time_s"] = time_s
	heat_ledger["state_basis"] = "Last stored numerical frame; not interpolated."
	heat_budget_error = absf(float(heat_ledger["heat_residual_j"]))
	water_budget_error_m3 = absf(float(heat_ledger["water_residual_m3"]))

func _at_s(s_m: float) -> Dictionary:
	# Piecewise-constant spatial field; downstream cell owns an internal face.
	var low: int = 0
	var high: int = _cells.size() - 1
	while low < high:
		var middle: int = int((low + high) / 2)
		if s_m < float(_cells[middle]["end_s_m"]):
			high = middle
		else:
			low = middle + 1
	return _spatial_state[low]

func river_state_at_position(
	at: Vector3,
	river_id: String
) -> Dictionary:
	if not replay_enabled:
		return super.reach_at(at.z)
	if not _features.has(river_id):
		return _unavailable()

	var feature: Dictionary = _features[river_id]
	var points: Array = feature["points_xyz"]
	var chainage: Array = feature["point_s_m"]
	var position_xz: Vector2 = Vector2(at.x, at.z)
	var best_distance_squared: float = INF
	var best_s: float = 0.0

	for i: int in range(points.size() - 1):
		var a: Vector2 = Vector2(float(points[i][0]), float(points[i][2]))
		var b: Vector2 = Vector2(float(points[i + 1][0]), float(points[i + 1][2]))
		var segment: Vector2 = b - a
		var fraction: float = clampf(
			(position_xz - a).dot(segment) / segment.length_squared(),
			0.0, 1.0
		)
		var distance_squared: float = position_xz.distance_squared_to(
			a + fraction * segment
		)
		if distance_squared < best_distance_squared:
			best_distance_squared = distance_squared
			best_s = lerpf(float(chainage[i]), float(chainage[i + 1]), fraction)

	# This is a query extent for aquatic actors, not a surveyed bank test.
	var half_width: float = float(feature["width_m"]) * 0.5
	if best_distance_squared > half_width * half_width:
		return _unavailable()
	return _at_s(best_s)

func reach_at(z: float) -> Dictionary:
	# Legacy z-only callers remain compatible. New fish calls use position.
	if not replay_enabled:
		return super.reach_at(z)
	var best: Dictionary = _spatial_state[0]
	var distance: float = INF
	for state: Dictionary in _spatial_state:
		var candidate: float = absf(z - float(state["z"]))
		if candidate < distance:
			distance = candidate
			best = state
	return best

func _unavailable() -> Dictionary:
	return {
		"id": "unavailable",
		"temperature_c": 0.0,
		"flow_m3s": 0.0,
		"fish_activity": 0.0,
	}

func thermal_probe_records() -> Array:
	# Optional observation overlays can read the same authoritative state.
	var result: Array = []
	for i: int in range(_cells.size()):
		result.append({
			"position_xyz": _cells[i]["position_xyz"],
			"temperature_c": _spatial_state[i]["temperature_c"],
			"cell_id": _cells[i]["id"],
		})
	return result