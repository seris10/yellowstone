class_name MidwayEcosystem
extends Node
## Reduced observational model. Transport units: seconds, m3/s, m3, Celsius. Water geometry fixed. River internal heat flux paired. Unknown tributary flows omitted from ecosystem.json.
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
var _reach_indices: Dictionary = {}
var _patch_indices: Dictionary = {}
var _grazers: Dictionary = {}
var _insect_foragers: Dictionary = {}

func _ready() -> void:
	if not FileAccess.file_exists("res://data/ecosystem.json"):
		push_error("Ecosystem data is missing (no data/ecosystem.json); environmental updates disabled.")
		set_process(false)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/ecosystem.json"))
	if not parsed is Dictionary:
		push_error("Ecosystem data is missing or invalid; environmental updates disabled.")
		set_process(false)
		return
	configure(parsed)
	var authored: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/world.json"))
	if authored is Dictionary:
		world_data = authored

func configure(data: Dictionary) -> bool:
	params = data.duplicate(true)
	river = params.get("river_reaches", []).duplicate(true)
	patches = params.get("patches", []).duplicate(true)
	clock_hour = float(params.get("clock_hour", 16.2))
	day_rate = float(params.get("day_rate", 1.0))
	humidity = clampf(float(params.get("humidity", 0.45)), 0.0, 1.0)
	cloud = clampf(float(params.get("cloud", 0.16)), 0.0, 1.0)
	elapsed = 0.0
	accumulator = 0.0
	heat_budget_error = 0.0
	water_budget_error_m3 = 0.0
	_reach_indices.clear()
	_patch_indices.clear()
	_grazers.clear()
	_insect_foragers.clear()
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
	_update_weather()
	if configuration_valid:
		_derive_flows()
	set_process(configuration_valid)
	return configuration_valid

func _process(delta: float) -> void:
	# Retain elapsed-time debt after a slow frame.
	accumulator += maxf(0.0, delta)
	var steps: int = 0
	while accumulator >= DT and steps < MAX_STEPS_PER_FRAME:
		step(DT)
		accumulator -= DT
		steps += 1

func _derive_flows() -> void:
	var q: float = float(params.get("boundary_m3s", 8.0))
	for r: Dictionary in river:
		r["q_in_m3s"] = q
		var source_q: float = 0.0
		var source_qt: float = 0.0
		for source: Dictionary in r.get("lateral_sources", []):
			var added_q: float = maxf(0.0, float(source.get("flow_m3s", 0.0)))
			source_q += added_q
			source_qt += added_q * float(source.get("temperature_c", 0.0))
		q += source_q
		r["flow_m3s"] = q
		r["thermal_m3s"] = source_q
		r["source_heat_m3_c_per_s"] = source_qt
		r["source_c"] = source_qt / source_q if source_q > 0.0 else 0.0

func step(dt: float) -> void:
	if not configuration_valid or dt <= 0.0:
		return
	_derive_flows()
	var stable_dt: float = DT
	for r: Dictionary in river:
		var rate: float = float(r.flow_m3s) / float(r.volume_m3)
		var cooling_seconds: float = maxf(1.0, float(r.get("cooling_seconds", 18000.0)))
		rate += 1.0 / cooling_seconds
		stable_dt = minf(stable_dt, 0.45 / maxf(rate, 0.000001))
	var remaining: float = dt
	heat_budget_error = 0.0
	water_budget_error_m3 = 0.0
	while remaining > 0.0000001:
		var h: float = minf(remaining, stable_dt)
		elapsed += h
		clock_hour = fposmod(clock_hour + h * day_rate / 3600.0, 24.0)
		_update_weather()
		_advance_heat(h)
		_advance_patches(h)
		remaining -= h
	advanced.emit()

func _update_weather() -> void:
	var weather: Dictionary = params.get("weather", {})
	var sunlight: float = maxf(0.0, sin((clock_hour - 6.0) * PI / 12.0))
	air_c = float(weather.get("night_air_c", 7.0)) + float(weather.get("day_warming_c", 15.0)) * sunlight
	var direction: Array = weather.get("wind_xz_mps", [1.8, 0.6])
	var gust: float = float(weather.get("gust_mps", 0.45))
	wind = Vector2(float(direction[0]), float(direction[1])) + Vector2(sin(elapsed / 61.0), cos(elapsed / 87.0)) * gust

func _advance_heat(dt: float) -> void:
	var old: Array = river.duplicate(true)
	var before: float = 0.0
	var after: float = 0.0
	var sources_heat: float = 0.0
	var atmosphere_heat: float = 0.0
	var source_flow: float = 0.0
	for i: int in range(river.size()):
		var r: Dictionary = river[i]
		var old_c: float = float(old[i].temperature_c)
		var volume: float = float(r.volume_m3)
		var upstream_c: float = float(params.get("boundary_c", 17.5)) if i == 0 else float(old[i - 1].temperature_c)
		var incoming: float = float(r.q_in_m3s) * upstream_c + float(r.source_heat_m3_c_per_s)
		var outgoing: float = float(r.flow_m3s) * old_c
		# Newton exchange is a lumped heat-loss term.
		var atmosphere: float = (air_c - old_c) * volume / maxf(1.0, float(r.get("cooling_seconds", 18000.0)))
		var d_heat: float = (incoming - outgoing + atmosphere) * dt
		r["temperature_c"] = old_c + d_heat / volume
		before += old_c * volume
		after += float(r.temperature_c) * volume
		sources_heat += float(r.source_heat_m3_c_per_s)
		source_flow += float(r.thermal_m3s)
		atmosphere_heat += atmosphere
		water_budget_error_m3 = maxf(water_budget_error_m3, absf(float(r.q_in_m3s) + float(r.thermal_m3s) - float(r.flow_m3s)) * dt)
		# Relative visual suitability only.
		var temperature: float = float(r.temperature_c)
		var thermal_preference: float = clampf((26.0 - temperature) / 8.0, 0.0, 1.0)
		r["fish_activity"] = thermal_preference
		var exposure: float = float(r.get("thermal_exposure_index", 0.0))
		var stress: float = maxf(0.0, temperature - 20.0) / 10.0
		var recovery: float = maxf(0.0, 20.0 - temperature) / 20.0
		r["thermal_exposure_index"] = clampf(exposure + (stress - recovery) * dt / 3600.0, 0.0, 1.0)
	var last: Dictionary = old[old.size() - 1]
	var boundary_heat: float = float(params.boundary_m3s) * float(params.boundary_c)
	var exit_heat: float = float(river[river.size() - 1].flow_m3s) * float(last.temperature_c)
	var expected: float = (boundary_heat + sources_heat - exit_heat + atmosphere_heat) * dt
	var residual: float = absf((after - before) - expected)
	heat_budget_error = maxf(heat_budget_error, residual)
	var domain_water_residual: float = absf(float(params.boundary_m3s) + source_flow - float(river[river.size() - 1].flow_m3s)) * dt
	water_budget_error_m3 = maxf(water_budget_error_m3, domain_water_residual)
	heat_ledger = {"units":"m3 * degC (constant rho*cp omitted)","before":before,"after":after,"boundary_input":boundary_heat * dt,"lateral_input":sources_heat * dt,"outlet_export":exit_heat * dt,"atmosphere_exchange":atmosphere_heat * dt,"residual":residual,"dt_seconds":dt}

func _advance_patches(dt: float) -> void:
	var sunlight: float = maxf(0.0, sin((clock_hour - 6.0) * PI / 12.0))
	var hours: float = dt / 3600.0
	for p: Dictionary in patches:
		var id: String = str(p.id)
		var before: float = float(p.biomass)
		var capacity: float = maxf(0.0001, float(p.get("capacity", 1.0)))
		var moisture: float = clampf(float(p.get("moisture", 0.5)), 0.0, 1.0)
		var growth_rate: float = float(p.get("growth_per_hour", 0.012))
		var growth: float = maxf(0.0, growth_rate * sunlight * moisture * before * (1.0 - before / capacity) * hours)
		growth = minf(growth, maxf(0.0, capacity - before))
		var demand: float = 0.0
		var grazing_count: int = 0
		for grazer: Dictionary in _grazers.values():
			if str(grazer.patch_id) == id and bool(grazer.active):
				demand += float(grazer.rate_per_second) * dt
				grazing_count += 1
		var consumed: float = minf(before + growth, demand)
		p["biomass"] = before + growth - consumed
		p["grazed"] = float(p.get("grazed", 0.0)) + consumed
		p["grazer_pressure"] = float(grazing_count)
		p["last_growth"] = growth
		p["plant_budget_error"] = absf(float(p.biomass) - before - growth + consumed)
		var insects_before: float = clampf(float(p.get("insect_resource", 0.8)), 0.0, 1.0)
		var insect_gain: float = float(p.get("insect_recovery_per_hour", 0.04)) * sunlight * moisture * (1.0 - insects_before) * hours
		var insect_demand: float = 0.0
		for forager: Dictionary in _insect_foragers.values():
			if str(forager.patch_id) == id and bool(forager.active):
				insect_demand += float(forager.rate_per_second) * dt
		var insects_available: float = minf(1.0, insects_before + insect_gain)
		var insect_consumed: float = minf(insects_available, insect_demand)
		p["insect_resource"] = insects_available - insect_consumed
		p["insects_consumed"] = float(p.get("insects_consumed", 0.0)) + insect_consumed
		p["insect_activity"] = sunlight * clampf((air_c - 8.0) / 14.0, 0.0, 1.0) * (1.0 - cloud) * moisture * float(p.insect_resource)

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
		return {"id":"unavailable","temperature_c":0.0,"flow_m3s":0.0,"fish_activity":0.0}
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
	# Missing habitat raises.
	return {"id":"unavailable","biomass":0.0,"capacity":1.0,"moisture":0.0,"insect_activity":0.0,"insect_resource":0.0}

func steam_visibility(surface_c: float) -> float:
	# Artistic condensation visibility proxy.
	return clampf((surface_c - air_c) / 85.0 * (0.55 + humidity * 0.7), 0.0, 0.95)

func _saturation_vapour_pressure_kpa(t_c: float) -> float:
	# Magnus form, same convention as yellowstone_python.microclimate.
	return 0.61094 * exp(17.625 * t_c / (t_c + 243.04))

func condensation_visibility(surface_c: float) -> float:
	# Visible plume is condensed droplets. Mirrors yellowstone_python.microclimate.condensation_potential: entrained mixed parcel (30% surface-saturated, 70% ambient) is supersaturated when its vapor exceeds saturation. Returns relative supersaturation of the mixed parcel: (q_mix - es(t_mix)) / es_surf, bounded in [0,1]. Model output; renderer scales it (see STEAM_DENSITY_SCALE).
	var es_surf := _saturation_vapour_pressure_kpa(surface_c)
	var es_air := _saturation_vapour_pressure_kpa(air_c)
	var ea := clampf(humidity, 0.0, 1.0) * es_air
	var q_mix := 0.3 * es_surf + 0.7 * ea
	var t_mix := 0.3 * surface_c + 0.7 * air_c
	var supersat := maxf(0.0, q_mix - _saturation_vapour_pressure_kpa(t_mix))
	var wind_factor: float = exp(-wind.length() / 8.0)
	return clampf(supersat / maxf(es_surf, 1e-6), 0.0, 1.0) * wind_factor
