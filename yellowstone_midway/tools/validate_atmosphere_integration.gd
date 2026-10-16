extends SceneTree

const World = preload("res://scripts/world.gd")
const Replay = preload("res://scripts/python_river_replay.gd")
const LiveClient = preload("res://scripts/live_python_client.gd")
const Atmosphere = preload("res://scripts/yellowstone_atmosphere.gd")
var failures: Array[String] = []
var checks: int = 0


func _init() -> void:
	call_deferred("_run")


func _check(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures.append(label)


func _frame(seconds: float) -> Dictionary:
	return {"t_s": seconds, "epoch_unix": 1784052000.0 + seconds, "temperature_c": [15.0], "cells": [{"cell_id": "cell", "s_m": 5.0, "temperature_c": 15.0}], "weather": {"cloud_fraction": 0.8, "precipitation_rate_mm_h": 8.0}, "header": {}}


func _run() -> void:
	var model = Replay.new()
	model.set_process(false)
	model.begin_live({"cells": [{"id": "cell", "river_id": "test", "start_s_m": 0.0, "end_s_m": 10.0, "position_xyz": [0.0, 1.0, 5.0]}], "river_features": {}})
	_check(model.append_frames([_frame(0.0), _frame(120.0)]), "clock fixture accepted")
	var host := Node3D.new()
	root.add_child(host)
	var sun := DirectionalLight3D.new()
	var camera := Camera3D.new()
	host.add_child(sun)
	host.add_child(camera)
	var atmosphere = Atmosphere.new()
	host.add_child(atmosphere)
	atmosphere.configure(sun, Environment.new(), camera)
	atmosphere.set_process(false)
	atmosphere.smooth_weather_transitions = false
	atmosphere.set_weather_state({"cloud_fraction": 0.8, "precipitation_rate_mm_h": 8.0, "wind_speed_mps": 2.0, "wind_direction_deg": 270.0})
	var world = World.new()
	world.ecosystem = model
	world.atmosphere_controller = atmosphere
	world._sync_atmosphere_clock()
	model.time_scale = 60.0
	model._process(1.0)
	world._sync_atmosphere_clock()
	atmosphere._update_atmosphere(0.017)
	var expected: float = 0.24 * sqrt(8.0) * (1.0 - exp(-60.0 / 75.0))
	_check(absf(atmosphere._rain_curtain.optical_depth - expected) < 1e-8, "history uses accepted elapsed seconds")
	var depth: float = atmosphere._rain_curtain.optical_depth
	var offset: Vector2 = atmosphere._cloud_offset
	model.paused = true
	for i: int in range(20):
		model._process(1.0)
		world._sync_atmosphere_clock()
		atmosphere._update_atmosphere(1.0)
	_check(atmosphere.time_scale == 0.0, "pause propagates immediately")
	_check(atmosphere._rain_curtain.optical_depth == depth and atmosphere._cloud_offset == offset, "pause freezes transient liquid and clouds")
	model.paused = false
	model.clock_held = true
	model._process(10.0)
	world._sync_atmosphere_clock()
	atmosphere._update_atmosphere(10.0)
	_check(atmosphere._rain_curtain.optical_depth == depth and atmosphere._cloud_offset == offset, "backend hold freezes atmospheric history")
	model.clock_held = false
	model.computing = true
	model._process(1.0)
	world._sync_atmosphere_clock()
	atmosphere._update_atmosphere(1.0)
	_check(model.elapsed == 120.0 and atmosphere._rain_curtain.optical_depth > depth, "available buffered time advances while worker computes")
	depth = atmosphere._rain_curtain.optical_depth
	offset = atmosphere._cloud_offset
	model._process(10.0)
	world._sync_atmosphere_clock()
	atmosphere._update_atmosphere(10.0)
	_check(model.elapsed == 120.0 and model.computing, "buffer exhausted at exact endpoint")
	_check(atmosphere._rain_curtain.optical_depth == depth and atmosphere._cloud_offset == offset, "buffer exhaustion cannot extrapolate drops or wind")
	_check(model.append_frames([_frame(240.0)]), "new buffered frame accepted")
	model._process(0.5)
	world._sync_atmosphere_clock()
	atmosphere._update_atmosphere(1.0)
	_check(model.elapsed == 150.0 and atmosphere._rain_curtain.optical_depth > depth, "resume consumes only newly accepted time")
	depth = atmosphere._rain_curtain.optical_depth
	world._sync_atmosphere_clock()
	atmosphere._update_atmosphere(1.0)
	_check(atmosphere._rain_curtain.optical_depth == depth, "repeated frame cannot consume time twice")
	model.clock_held = true
	model.elapsed -= 0.5
	world._sync_atmosphere_clock()
	atmosphere._update_atmosphere(3.0)
	_check(atmosphere._rain_curtain.optical_depth == depth, "backward live correction preserves accrued history")
	model.clock_held = false
	model.elapsed += 1.0
	world._sync_atmosphere_clock()
	atmosphere._update_atmosphere(0.1)
	expected = lerpf(depth, 0.24 * sqrt(8.0), 1.0 - exp(-0.5 / 75.0))
	_check(absf(atmosphere._rain_curtain.optical_depth - expected) < 1e-8, "correction catch-up consumes only fresh physical time")
	depth = atmosphere._rain_curtain.optical_depth
	model.paused = true
	model.elapsed += 10.0
	world._sync_atmosphere_clock()
	atmosphere._update_atmosphere(0.1)
	_check(atmosphere.time_scale == 0.0 and atmosphere._rain_curtain.optical_depth > depth, "paused single-step consumes its actual interval")
	model.live_mode = false
	model.elapsed = 20.0
	world._sync_atmosphere_clock()
	atmosphere._update_atmosphere(0.1)
	_check(atmosphere._rain_curtain.optical_depth == 0.0 and atmosphere._cloud_offset == Vector2.ZERO, "backward seek discards future transient history")
	world.live_client = LiveClient.new()
	world.weather_snapshot_reader = Node.new()
	world.help_label = Label.new()
	world.add_child(world.live_client)
	world.add_child(world.weather_snapshot_reader)
	world.add_child(world.help_label)
	for origin: float in [0.0, 1000.0]:
		atmosphere._rain_curtain.optical_depth = 0.4
		atmosphere._cloud_offset = Vector2(0.3, 0.5)
		atmosphere._pending_physical_seconds = 8.0
		world.live_client.schema = {"player_t_s": origin, "cells": [{"id": "cell", "river_id": "test", "start_s_m": 0.0, "end_s_m": 10.0, "position_xyz": [0.0, 1.0, 5.0]}], "river_features": {}}
		world._python_mode_selected(true)
		_check(model.elapsed == origin and atmosphere._external_elapsed_s == origin, "explicit live session rebinds the elapsed origin %s" % origin)
		_check(atmosphere._rain_curtain.optical_depth == 0.0 and atmosphere._cloud_offset == Vector2.ZERO and atmosphere._pending_physical_seconds == 0.0, "session transition clears unavailable history and pending intervals")
		_check(model.append_frames([_frame(origin), _frame(origin + 10.0)]), "new session accepts its own frame times")
		model.paused = false
		model.clock_held = false
		model.time_scale = 1.0
		model._process(1.0)
		world._sync_atmosphere_clock()
		atmosphere._update_atmosphere(0.1)
		expected = 0.24 * sqrt(8.0) * (1.0 - exp(-1.0 / 75.0))
		_check(absf(atmosphere._rain_curtain.optical_depth - expected) < 1e-8, "new session advances immediately from its own origin")
	# Independent cardinal vectors also prove a current polar frame outranks a default vector.
	model.live_mode = true
	model.params = {"weather": {"wind_xz_mps": [9.0, 8.0]}}
	var toward: Array[Vector2] = [Vector2(0.0, 2.0), Vector2(-2.0, 0.0), Vector2(0.0, -2.0), Vector2(2.0, 0.0)]
	for i: int in range(4):
		var bearing: float = float(i) * 90.0
		model.apply_python_frame({"weather": {"wind_speed_mps": 2.0, "wind_direction_deg": bearing}})
		_check(model.wind.distance_to(toward[i]) < 1e-6, "polar wind source bearing %s" % bearing)
		world.update_environment()
		var difference: float = fposmod(float(atmosphere._weather.wind_direction_deg) - bearing + 180.0, 360.0) - 180.0
		_check(absf(difference) < 1e-6, "world polar wind roundtrip %s" % bearing)
	model.apply_python_frame({"weather": {"wind_xz_mps": [-3.0, 4.0], "wind_speed_mps": 2.0, "wind_direction_deg": 0.0}})
	_check(model.wind == Vector2(-3.0, 4.0), "explicit current world wind vector has precedence")
	model.apply_python_frame({"weather": {}})
	_check(model.wind == Vector2(9.0, 8.0), "missing current wind uses published defaults")
	var result := {"schema": "yellowstone.atmosphere_integration.v1", "checks": checks, "failures": failures, "scope": "native accepted-clock history and cardinal live-wind integration"}
	var file := FileAccess.open("res://../evidence/atmosphere-integration.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(result, "  ") + "\n")
	file.close()
	print(JSON.stringify(result))
	world.free()
	model.free()
	host.free()
	quit(0 if failures.is_empty() else 1)
