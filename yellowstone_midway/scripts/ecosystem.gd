class_name MidwayEcosystem
extends Node
const ReleaseData = preload("res://scripts/release_data.gd")
## Published Python state with presentation interpolation.
signal advanced
const DT: float = 1.0
const MAX_STEPS_PER_FRAME: int = 8
var accumulator: float = 0.0
var elapsed: float = 0.0
var clock_hour: float = 16.2
var day_rate: float = 1.0
var air_c: float = 18.0
var humidity: float = 0.45
var cloud: float = 0.16
var wind: Vector2 = Vector2(1.8, 0.6)
var river: Array = []
var patches: Array = []
var heat_budget_error: float = 0.0
var water_budget_error_m3: float = 0.0
var heat_ledger: Dictionary = {}
var params: Dictionary = {}
var world_data: Dictionary = {}
var transport_scale: float = 1.0 # Transport is 1:1.
var configuration_valid: bool = false
var time_scale: float = 1.0
var paused: bool = false
var clock_held: bool = false
var live_mode: bool = false
var epoch_unix: float = 0.0
var current_frame: Dictionary = {}
var frame_header: Dictionary = {}
var _series: Array = []
var _clock_hour0: float = 16.2
var _reach_indices: Dictionary = {}
var _patch_indices: Dictionary = {}
var _grazers: Dictionary = {}
var _insect_foragers: Dictionary = {}
var _mammals: Dictionary = {}
var _warned_patch_ids: Dictionary = {}

func _ready() -> void:
	if not ReleaseData.file_exists("res://data/ecosystem.json"):
		push_error("Ecosystem data is missing (no data/ecosystem.json); environmental updates disabled.")
		set_process(false)
		return
	var parsed: Variant = JSON.parse_string(ReleaseData.get_file_as_string("res://data/ecosystem.json"))
	if not parsed is Dictionary:
		push_error("Ecosystem data is missing or invalid; environmental updates disabled.")
		set_process(false)
		return
	configure(parsed)
	var authored: Variant = JSON.parse_string(ReleaseData.get_file_as_string("res://data/world.json"))
	if authored is Dictionary:
		world_data = authored

func configure(data: Dictionary) -> bool:
	var saved_elapsed: float = elapsed
	var saved_frame: Dictionary = current_frame
	params = data.duplicate(true)
	if not live_mode:
		frame_header = params.get("frame_header", frame_header).duplicate(true)
	_series = params.get("python_series", []).duplicate(true)
	river = params.get("river_reaches", []).duplicate(true)
	patches = params.get("patches", []).duplicate(true)
	_clock_hour0 = float(params.get("clock_hour", 16.2))
	clock_hour = fposmod(_clock_hour0 + saved_elapsed / 3600.0, 24.0)
	day_rate = float(params.get("day_rate", 1.0))
	humidity = clampf(float(params.get("humidity", 0.45)), 0.0, 1.0)
	cloud = clampf(float(params.get("cloud", 0.16)), 0.0, 1.0)
	elapsed = saved_elapsed
	accumulator = 0.0
	heat_budget_error = 0.0
	water_budget_error_m3 = 0.0
	_reach_indices.clear()
	_patch_indices.clear()
	_grazers.clear()
	_insect_foragers.clear()
	_mammals = params.get("mammal_initial_state", {}).get("actors", {}).duplicate(true)
	_warned_patch_ids.clear()
	configuration_valid = not river.is_empty() and not patches.is_empty()
	for i: int in range(river.size()):
		var r: Dictionary = river[i]
		var id: String = str(r.get("id", ""))
		if id.is_empty() or _reach_indices.has(id) or float(r.get("volume_m3", 0.0)) <= 0.0:
			configuration_valid = false
			push_error("Invalid or duplicate ecosystem reach: " + id)
		_reach_indices[id] = i
		var upstream: String = str(r.get("upstream_id", ""))
		if not upstream.is_empty() and (not _reach_indices.has(upstream) or int(_reach_indices[upstream]) >= i):
			configuration_valid = false
			push_error("River reaches must be an upstream-first chain: " + id)
		# Supports one chain.
		if i > 0 and upstream != str(river[i - 1].get("id", "")):
			configuration_valid = false
			push_error("Unsupported branching/gap in reduced Firehole chain: " + id)
		r["fish_activity"] = 1.0
		r["thermal_exposure_index"] = 0.0
	for i: int in range(patches.size()):
		var p: Dictionary = patches[i]
		var id: String = str(p.get("id", ""))
		if id.is_empty() or _patch_indices.has(id):
			configuration_valid = false
		_patch_indices[id] = i
		p["grazed"] = 0.0
		p["grazer_pressure"] = 0.0
		p["insect_activity"] = 0.0
		p["insects_consumed"] = 0.0
		p["plant_budget_error"] = 0.0
	if float(params.get("boundary_m3s", 0.0)) <= 0.0:
		configuration_valid = false
		push_error("A positive, explicitly sourced or illustrative boundary flow is required.")
	apply_python_frame(saved_frame if live_mode else _series[0] if not _series.is_empty() else {})
	set_process(configuration_valid)
	return configuration_valid

func _process(delta: float) -> void:
	if not paused and not clock_held:
		step(maxf(0.0, delta) * time_scale)

func step(dt: float) -> void:
	if not configuration_valid or dt <= 0.0 or live_mode:
		return
	if _series.is_empty():
		return
	elapsed = minf(elapsed + dt, float(_series[-1].get("t_s", elapsed)))
	var i: int = 0
	while i + 1 < _series.size() and float(_series[i + 1].t_s) <= elapsed:
		i += 1
	var a: Dictionary = _series[i]
	var b: Dictionary = _series[mini(i + 1, _series.size() - 1)]
	var span: float = float(b.t_s) - float(a.t_s)
	apply_python_frame(interpolate_frame(a, b, (elapsed - float(a.t_s)) / span if span > 0.0 else 0.0))
	advanced.emit()

static func interpolate_frame(a: Dictionary, b: Dictionary, weight: float) -> Dictionary:
	var result: Dictionary = a.duplicate(true)
	for key: Variant in a:
		if key in ["header", "health", "budget", "observations"]:
			continue
		if not b.has(key):
			continue
		if a[key] is Dictionary and b[key] is Dictionary:
			result[key] = interpolate_frame(a[key], b[key], weight)
		elif (a[key] is float or a[key] is int) and (b[key] is float or b[key] is int):
			result[key] = lerpf(float(a[key]), float(b[key]), weight)
		elif a[key] is Array and b[key] is Array and a[key].size() == b[key].size():
			var rows: Array = []
			for i: int in range(a[key].size()):
				if a[key][i] is Dictionary and b[key][i] is Dictionary:
					rows.append(interpolate_frame(a[key][i], b[key][i], weight))
				elif (a[key][i] is float or a[key][i] is int) and (b[key][i] is float or b[key][i] is int):
					rows.append(lerpf(float(a[key][i]), float(b[key][i]), weight))
				else:
					rows.append(a[key][i])
			result[key] = rows
	return result

func apply_python_frame(frame: Dictionary) -> void:
	current_frame = frame
	frame_header = frame.get("header", frame_header)
	if frame.get("epoch_unix") != null:
		epoch_unix = float(frame.epoch_unix)
		var local: Dictionary = Time.get_datetime_dict_from_unix_time(epoch_unix + float(world_data.get("utc_offset_hours", -6.0)) * 3600.0)
		clock_hour = float(local.hour) + float(local.minute) / 60.0 + float(local.second) / 3600.0
	else:
		clock_hour = fposmod(_clock_hour0 + elapsed / 3600.0, 24.0)
	var weather: Dictionary = frame.get("weather", {})
	air_c = float(weather.get("air_c", weather.get("air_temperature_c", air_c)))
	humidity = float(weather.get("humidity", weather.get("relative_humidity", humidity)))
	cloud = float(weather.get("cloud", weather.get("cloud_fraction", cloud)))
	var direction: Variant = weather.get("wind_xz_mps")
	if direction is Array and direction.size() == 2:
		wind = Vector2(float(direction[0]), float(direction[1]))
	elif weather.has("wind_speed_mps"):
		var angle: float = deg_to_rad(float(weather.get("wind_direction_deg", 270.0)) + 180.0)
		wind = Vector2(sin(angle), -cos(angle)) * float(weather.wind_speed_mps)
	else:
		var fallback: Variant = params.get("weather", {}).get("wind_xz_mps", [1.8, 0.6])
		if fallback is Array and fallback.size() == 2:
			wind = Vector2(float(fallback[0]), float(fallback[1]))
	for reach: Dictionary in frame.get("reaches", []):
		if _reach_indices.has(str(reach.get("id", ""))):
			river[int(_reach_indices[str(reach.id)])].merge(reach, true)
	var ecology: Dictionary = frame.get("ecology", {})
	if ecology.get("mammals") is Dictionary and ecology.mammals.get("actors") is Dictionary:
		_mammals = ecology.mammals.actors.duplicate(true)
	var incoming: Array = ecology.get("patches", frame.get("patches", []))
	for row: Dictionary in incoming:
		var id: String = str(row.get("id", row.get("patch_id", "")))
		if _patch_indices.has(id):
			patches[int(_patch_indices[id])].merge(row, true)

func mammal_state(id: String, kind: String, world_position: Vector3) -> Dictionary:
	var unavailable: Dictionary = {"active":false,"activity_index":0.0,"speed_multiplier":0.0,"behavior":"rest","availability":"unavailable"}
	if not world_position.is_finite() or not _mammals.has(id):
		return unavailable
	var row: Variant = _mammals[id]
	if not row is Dictionary:
		push_error("Invalid published mammal actor state: " + id)
		return unavailable
	var aliases: Dictionary = {"gray_wolf":"wolf","mule_deer":"deer"}
	var source_kind: String = str(row.get("kind", ""))
	if str(aliases.get(source_kind, source_kind)) != str(aliases.get(kind, kind)):
		return unavailable
	var activity: Variant = row.get("activity_index")
	var speed: Variant = row.get("speed_multiplier")
	var behavior: String = str(row.get("behavior", ""))
	if not row.get("active") is bool or not (activity is float or activity is int) or not (speed is float or speed is int):
		push_error("Invalid published mammal state fields: " + id)
		return unavailable
	if not is_finite(float(activity)) or not is_finite(float(speed)) or float(activity) < 0.0 or float(activity) > 1.0 or float(speed) < 0.0:
		push_error("Invalid published mammal activity or speed: " + id)
		return unavailable
	if behavior not in ["rest", "forage", "walk", "graze", "alert", "flee"]:
		push_error("Invalid published mammal behavior: " + id)
		return unavailable
	return row.duplicate(true)

func set_grazer_activity(id: String, patch_id: String, active: bool, rate_per_second: float) -> void:
	if not _patch_indices.has(patch_id):
		return
	_grazers[id] = {"patch_id":patch_id,"active":active,"rate_per_second":maxf(0.0, rate_per_second)}

func set_insect_forager_activity(id: String, patch_id: String, active: bool, rate_per_second: float) -> void:
	if not _patch_indices.has(patch_id):
		return
	_insect_foragers[id] = {"patch_id":patch_id,"active":active,"rate_per_second":maxf(0.0, rate_per_second)}

func unregister_actor(id: String) -> void:
	_grazers.erase(id)
	_insect_foragers.erase(id)

func reach_at(z: float) -> Dictionary:
	if river.is_empty():
		return {"id":"unavailable","temperature_c":0.0,"flow_m3s":0.0,"fish_activity":0.0,"water_surface_m":NAN}
	var best: Dictionary = river[0]
	var distance: float = INF
	for r: Dictionary in river:
		var d: float = absf(z - float(r.z))
		if d < distance:
			distance = d
			best = r
	return best

func patch(id: String) -> Dictionary:
	if _patch_indices.has(id):
		return patches[int(_patch_indices[id])]
	if not _warned_patch_ids.has(id):
		_warned_patch_ids[id] = true
		push_warning("Unknown patch id: " + id)
	return {"id":"unavailable","biomass":0.0,"capacity":1.0,"moisture":0.0,"insect_activity":0.0,"insect_resource":0.0}

func steam_visibility(surface_c: float) -> float:
	# Artistic condensation visibility proxy.
	return clampf((surface_c - air_c) / 85.0 * (0.55 + humidity * 0.7), 0.0, 0.95)

func _saturation_vapor_pressure_kpa(t_c: float) -> float:
	# Magnus form (Alduchov and Eskridge (1996) coefficients, converted to kPa).
	return 0.61094 * exp(17.625 * t_c / (t_c + 243.04))

func condensation_visibility(surface_c: float) -> float:
	# Mixed-parcel supersaturation index. Zero at ambient equilibrium, one when mixed vapor doubles its saturation.
	var es_surf: float = _saturation_vapor_pressure_kpa(surface_c)
	var es_air: float = _saturation_vapor_pressure_kpa(air_c)
	var ea: float = clampf(humidity, 0.0, 1.0) * es_air
	var e_mix: float = 0.3 * es_surf + 0.7 * ea
	var t_mix: float = 0.3 * surface_c + 0.7 * air_c
	var es_mix: float = _saturation_vapor_pressure_kpa(t_mix)
	var supersat: float = maxf(0.0, e_mix - es_mix)
	var wind_factor: float = exp(-wind.length() / 8.0)
	return clampf(supersat / maxf(es_mix, 1e-6), 0.0, 1.0) * wind_factor
