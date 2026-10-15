class_name MidwayPythonRiverReplay
extends "res://scripts/ecosystem.gd"

## Buffered Python river frames with a player clock.

const BAKED_REPLAY_FILES: Array[String] = ["river_replay.json", "firehole_control.json", "firehole_pulse.json"]
@export_file("*.json") var replay_path: String = ""
var world_path: String = "res://data/world.json"

var replay_enabled: bool = false
var replay_finished: bool = false
var _replay: Dictionary = {}
var _cells: Array = []
var _frames: Array = []
var _features: Dictionary = {}
var _spatial_state: Array = []
var _frame_index: int = 0
var computing: bool = false
var max_buffer_frames: int = 1024
var _projection_cache: Dictionary = {}
var _segment_bounds: Dictionary = {}
const PROJECTION_GRID_M: float = 64.0
var _trout_state: Dictionary = {}
var _live_header: Dictionary = {}

func configure(data: Dictionary) -> bool:
	if live_mode:
		return super.configure(data)
	var saved_elapsed: float = elapsed
	replay_enabled = false
	replay_finished = false
	_frame_index = 0
	_replay.clear()
	_cells.clear()
	_frames.clear()
	_features.clear()
	_segment_bounds.clear()
	_projection_cache.clear()
	_spatial_state.clear()

	var base_ok: bool = super.configure(data)
	if not base_ok or replay_path.is_empty():
		return base_ok

	var value: Variant = JSON.parse_string(
		ReleaseData.get_file_as_string(replay_path)
	)
	if not value is Dictionary:
		return _reject("Missing or invalid Python replay.")

	var candidate: Dictionary = value.get("replay", value)
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
		ReleaseData.get_file_as_bytes(world_path)
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
		# position_xyz.y is the authored cell water surface; per-frame water_surface_m is bed_elevation_m plus depth_m once the publisher ships both.
		_spatial_state.append({
			"id": cell["id"],
			"river_id": cell["river_id"],
			"z": float(cell["position_xyz"][2]),
			"temperature_c": 0.0,
			"flow_m3s": float(cell.get("q_out_m3_s", 0.0)),
			"velocity_mps": float(cell.get("representative_velocity_m_s", 0.0)),
			"water_surface_m": float(cell["position_xyz"][1]),
			"bed_elevation_m": NAN,
			"depth_m": NAN,
			"fish_activity": 0.0,
			"status": "Python simulated; uncalibrated.",
		})

	replay_enabled = true
	_frame_index = 0
	elapsed = minf(saved_elapsed, float(_frames[-1].t_s))
	_apply_replay(elapsed)
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
	if not configuration_valid or dt <= 0.0 or paused or clock_held or _frames.is_empty():
		return
	var final_t: float = float(_frames[-1].t_s)
	elapsed = minf(final_t, elapsed + dt)
	computing = live_mode and (elapsed >= final_t or bool(_live_header.get("computing", false)))
	replay_finished = not live_mode and elapsed >= final_t
	_apply_replay(elapsed)
	advanced.emit()

func buffer_headroom_s() -> float:
	return maxf(0.0, float(_frames[-1].t_s) - elapsed) if not _frames.is_empty() else 0.0

func append_frames(chunk: Array) -> bool:
	var last: float = float(_frames[-1].t_s) if not _frames.is_empty() else -INF
	for value: Variant in chunk:
		if not value is Dictionary or not is_finite(float(value.get("t_s", NAN))):
			return false
		if float(value.t_s) <= last:
			continue
		var temperatures: Variant = value.get("temperature_c")
		if not temperatures is Array or temperatures.size() != _cells.size():
			return false
		for temperature: Variant in temperatures:
			if not is_finite(float(temperature)):
				return false
		last = float(value.t_s)
	for frame: Dictionary in chunk:
		if _frames.is_empty() or float(frame.t_s) > float(_frames[-1].t_s):
			_frames.append(frame.duplicate(true))
		elif float(frame.t_s) == float(_frames[-1].t_s):
			_frames[-1] = frame.duplicate(true)
	while _frames.size() > max_buffer_frames and _frame_index > 1:
		_frames.pop_front()
		_frame_index -= 1
	computing = clock_held or bool(_live_header.get("computing", false)) or buffer_headroom_s() <= 0.0
	if not _frames.is_empty():
		_apply_replay(elapsed)
	return true

func truncate_after(t_s: float) -> void:
	while not _frames.is_empty() and float(_frames[-1].t_s) > t_s:
		_frames.pop_back()
	_frame_index = 0
	elapsed = minf(elapsed, t_s)
	computing = true

func reset_buffer(retained_after_t_s: float) -> void:
	_frames.clear()
	_frame_index = 0
	elapsed = maxf(elapsed, retained_after_t_s)
	computing = true

func begin_live(schema: Dictionary = {}) -> void:
	live_mode = true
	_live_header.clear()
	_frames.clear()
	_frame_index = 0
	elapsed = float(schema.get("player_t_s", 0.0))
	computing = true
	if schema.get("cells") is Array and schema.get("river_features") is Dictionary:
		_cells = schema.cells.duplicate(true)
		_features = schema.river_features.duplicate(true)
		_segment_bounds.clear()
		_projection_cache.clear()
		_replay["legacy_queries"] = schema.get("legacy_queries", [])
		_spatial_state.clear()
		for cell: Dictionary in _cells:
			var xyz: Array = cell.get("position_xyz", [0.0, 0.0, 0.0])
			_spatial_state.append({"id": cell.get("id", cell.get("cell_id", "")), "z": float(xyz[2]), "water_surface_m": float(xyz[1]), "temperature_c": 0.0, "flow_m3s": float(cell.get("q_out_m3_s", 0.0)), "fish_activity": 0.0})
		replay_enabled = not _cells.is_empty()
		configuration_valid = replay_enabled
	set_process(configuration_valid)
	set_clock_header(schema.get("header", {"run_mode": "illustrative", "model_components": schema.get("model_components", {}), "build_id": schema.get("build_id", "")}))

func set_clock_header(header: Dictionary) -> void:
	_live_header.merge(header.duplicate(true), true)
	frame_header = _live_header
	time_scale = float(_live_header.get("time_scale", time_scale))
	paused = bool(_live_header.get("paused", paused))
	clock_held = bool(_live_header.get("clock_held", bool(_live_header.get("computing", false)) and not paused))
	computing = clock_held or bool(_live_header.get("computing", false)) or buffer_headroom_s() <= 0.0

func step_frame() -> void:
	for frame: Dictionary in _frames:
		if float(frame.t_s) > elapsed:
			elapsed = float(frame.t_s)
			_apply_replay(elapsed)
			advanced.emit()
			return

func _apply_replay(time_s: float) -> void:
	if _frames.is_empty():
		return
	if _frame_index >= _frames.size() or float(_frames[_frame_index].t_s) > time_s:
		_frame_index = 0
	while _frame_index + 1 < _frames.size() and float(_frames[_frame_index + 1].t_s) <= time_s:
		_frame_index += 1
	var a: Dictionary = _frames[_frame_index]
	var b: Dictionary = _frames[mini(_frame_index + 1, _frames.size() - 1)]
	var span: float = float(b.t_s) - float(a.t_s)
	var weight: float = clampf((time_s - float(a.t_s)) / span, 0.0, 1.0) if span > 0.0 else 0.0
	var frame: Dictionary = interpolate_frame(a, b, weight)
	if not frame.has("weather"):
		var trace: Array = _replay.get("weather_trace", [])
		if not trace.is_empty():
			var index: int = mini(int(floor(time_s / 60.0)), trace.size() - 1)
			frame["weather"] = trace[index].duplicate(true)
			frame.weather["humidity"] = _replay.get("humidity", humidity)
			frame.weather["cloud"] = _replay.get("cloud", cloud)
	if not frame.has("ecology") and not _series.is_empty():
		var i: int = 0
		while i + 1 < _series.size() and float(_series[i + 1].t_s) <= time_s:
			i += 1
		var next: Dictionary = _series[mini(i + 1, _series.size() - 1)]
		var interval: float = float(next.t_s) - float(_series[i].t_s)
		var series_frame: Dictionary = interpolate_frame(_series[i], next, (time_s - float(_series[i].t_s)) / interval if interval > 0.0 else 0.0)
		frame["patches"] = series_frame.get("patches", [])
		if series_frame.has("feeding_by_species"):
			frame["feeding_by_species"] = series_frame.feeding_by_species
		if series_frame.has("weather"):
			frame["weather"] = series_frame.weather
		if series_frame.has("epoch_unix"):
			frame["epoch_unix"] = series_frame.epoch_unix
	apply_python_frame(frame)
	if live_mode and not _live_header.is_empty():
		frame_header = _live_header
	var per_cell: Array = frame.get("cells", [])
	for i: int in range(_spatial_state.size()):
		var destination: Dictionary = _spatial_state[i]
		destination["temperature_c"] = float(frame.temperature_c[i])
		destination["s_m"] = float(_cells[i].get("center_s_m", (_cells[i].start_s_m + _cells[i].end_s_m) * 0.5))
		if per_cell.size() == _spatial_state.size():
			destination.merge(per_cell[i], true)
		for pair: Array in [["q_cells_m3s", "flow_m3s"], ["depth_m_cells", "depth_m"], ["feeding_cells", "feeding"]]:
			var values: Variant = frame.get(pair[0])
			if values is Array and values.size() == _spatial_state.size():
				destination[pair[1]] = float(values[i])
		var species_feeding: Dictionary = frame.get("feeding_by_species", {})
		var published_feeding: Dictionary = {}
		for species: String in species_feeding:
			if species_feeding[species] is Array and species_feeding[species].size() == _spatial_state.size():
				published_feeding[species] = species_feeding[species][i]
		if not published_feeding.is_empty():
			destination["feeding_by_species"] = published_feeding
			destination["feeding"] = published_feeding.get("brown_trout", destination.get("feeding", 0.0))
		destination["fish_activity"] = float(destination.get("feeding", 0.0))
		if is_finite(float(destination.get("depth_m", NAN))):
			var bed: float = float(_cells[i].get("bed_elevation_m", _cells[i].position_xyz[1]))
			destination["bed_elevation_m"] = bed
			destination["water_surface_m"] = bed + float(destination.depth_m)
	_trout_state.clear()
	var trout: Variant = frame.get("trout_records", frame.get("trout", []))
	if trout is Dictionary:
		_trout_state["default"] = trout
	elif trout is Array:
		for row: Dictionary in trout:
			_trout_state[str(row.get("id", "default"))] = row
	for query: Dictionary in _replay.get("legacy_queries", []):
		if _reach_indices.has(str(query.reach_id)):
			river[int(_reach_indices[str(query.reach_id)])].merge(_at_s(float(query.s_m)), true)
	heat_ledger = a.get("budget", {}).duplicate(true)
	heat_budget_error = absf(float(heat_ledger.get("heat_residual_j", 0.0)))
	water_budget_error_m3 = absf(float(heat_ledger.get("water_residual_m3", 0.0)))

func trout_state(id: String) -> Dictionary:
	return _trout_state.get(id, _trout_state.get("default", {}))

func river_state_at_s(s_m: float) -> Dictionary:
	return _at_s(s_m) if not _cells.is_empty() else _unavailable()

func position_at_s(s_m: float, river_id: String) -> Vector3:
	if not _features.has(river_id):
		return Vector3.ZERO
	var feature: Dictionary = _features[river_id]
	var points: Array = feature.points_xyz
	var chainage: Array = feature.point_s_m
	var index: int = 0
	while index + 1 < chainage.size() - 1 and float(chainage[index + 1]) < s_m:
		index += 1
	var fraction: float = clampf((s_m - float(chainage[index])) / (float(chainage[index + 1]) - float(chainage[index])), 0.0, 1.0)
	var a: Array = points[index]
	var b: Array = points[index + 1]
	var result: Vector3 = Vector3(float(a[0]), float(a[1]), float(a[2])).lerp(Vector3(float(b[0]), float(b[1]), float(b[2])), fraction)
	var water: float = float(_at_s(s_m).get("water_surface_m", NAN))
	if is_finite(water):
		result.y = water
	return result

func _at_s(s_m: float) -> Dictionary:
	# Piecewise-constant spatial field.
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
	river_id: String,
	actor_id: String = ""
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

	if not _segment_bounds.has(river_id):
		var segments: Array = []
		for i: int in range(points.size() - 1):
			var a: Vector2 = Vector2(float(points[i][0]), float(points[i][2]))
			var b: Vector2 = Vector2(float(points[i + 1][0]), float(points[i + 1][2]))
			segments.append({"a": a, "vector": b - a, "length_squared": maxf(a.distance_squared_to(b), 0.000001), "min": a.min(b), "max": a.max(b)})
		var bins: Dictionary = {}
		for i: int in range(segments.size()):
			var segment: Dictionary = segments[i]
			for x: int in range(int(floor(segment.min.x / PROJECTION_GRID_M)), int(floor(segment.max.x / PROJECTION_GRID_M)) + 1):
				for z: int in range(int(floor(segment.min.y / PROJECTION_GRID_M)), int(floor(segment.max.y / PROJECTION_GRID_M)) + 1):
					var key: Vector2i = Vector2i(x, z)
					if not bins.has(key):
						bins[key] = []
					bins[key].append(i)
		_segment_bounds[river_id] = {"segments": segments, "bins": bins}
	var segments: Array = _segment_bounds[river_id].segments
	var best_index: int = 0
	var previous: int = int(_projection_cache.get(actor_id, -1))
	var first_local: int = maxi(0, previous - 2) if previous >= 0 else 0
	var last_local: int = mini(segments.size(), previous + 3) if previous >= 0 else 0
	var candidates: Array[int] = []
	var seen: Dictionary = {}
	for i: int in range(first_local, last_local):
		candidates.append(i)
		seen[i] = true
	var radius: float = float(feature.width_m) * 0.5
	var bins: Dictionary = _segment_bounds[river_id].bins
	for x: int in range(int(floor((position_xz.x - radius) / PROJECTION_GRID_M)), int(floor((position_xz.x + radius) / PROJECTION_GRID_M)) + 1):
		for z: int in range(int(floor((position_xz.y - radius) / PROJECTION_GRID_M)), int(floor((position_xz.y + radius) / PROJECTION_GRID_M)) + 1):
			for i: int in bins.get(Vector2i(x, z), []):
				if not seen.has(i):
					candidates.append(i)
					seen[i] = true
	for i: int in candidates:
		var segment: Dictionary = segments[i]
		var nearest_box: Vector2 = position_xz.clamp(segment.min, segment.max)
		if position_xz.distance_squared_to(nearest_box) > best_distance_squared:
			continue
		var fraction: float = clampf((position_xz - segment.a).dot(segment.vector) / float(segment.length_squared), 0.0, 1.0)
		var distance_squared: float = position_xz.distance_squared_to(segment.a + fraction * segment.vector)
		if distance_squared < best_distance_squared:
			best_distance_squared = distance_squared
			best_s = lerpf(float(chainage[i]), float(chainage[i + 1]), fraction)
			best_index = i
	if not actor_id.is_empty():
		_projection_cache[actor_id] = best_index
	# Query extent for aquatic actors.
	var half_width: float = float(feature["width_m"]) * 0.5
	if best_distance_squared > half_width * half_width:
		return _unavailable()
	var result: Dictionary = _at_s(best_s).duplicate()
	result["projected_s_m"] = best_s
	return result

func reach_at(z: float) -> Dictionary:
	# z-only callers use z; fish calls use position.
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
	# Observation overlays read the same state.
	var result: Array = []
	for i: int in range(_cells.size()):
		result.append({
			"position_xyz": _cells[i]["position_xyz"],
			"temperature_c": _spatial_state[i]["temperature_c"],
			"cell_id": _cells[i]["id"],
		})
	return result
