extends SceneTree

const Replay = preload("res://scripts/python_river_replay.gd")
const Actor = preload("res://scripts/wildlife_actor.gd")
const Atmosphere = preload("res://scripts/yellowstone_atmosphere.gd")
const Help = preload("res://scripts/input_help.gd")
var failures: Array[String] = []

class FlatTerrain extends RefCounted:
	func sample(_x: float, _z: float) -> float:
		return 0.0

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error(message)

func frame(t: float, temperature: float) -> Dictionary:
	return {"t_s": t, "epoch_unix": 1784052000.0 + t, "temperature_c": [temperature], "cells": [{"cell_id": "cell_0", "s_m": 1500.0, "temperature_c": temperature, "feeding": 1.0, "velocity_mps": 0.0}], "weather": {"air_c": 12.0 + t / 100.0}, "trout": [{"id": "trout", "refuge_s_m": 35.0, "feeding": 1.0}], "header": {"clock_held": false, "computing": false, "paused": false, "time_scale": 1.0}}

func run() -> void:
	var model: Node = Replay.new()
	model.set_process(false)
	model.begin_live({"cells": [{"id": "cell_0", "river_id": "test", "start_s_m": 0.0, "end_s_m": 3000.0, "position_xyz": [0.0, 1.0, 1500.0]}], "river_features": {"test": {"points_xyz": [[0, 1, 0], [0, 1, 2873], [0, 1, 3000]], "point_s_m": [0, 2873, 3000], "width_m": 50.0}}})
	check(model.append_frames([frame(0, 10), frame(6000, 20)]), "Valid frame append")
	model.step(3000)
	check(is_equal_approx(model.river_state_at_s(1500).temperature_c, 15.0), "Mid-frame interpolation")
	model.step(3000)
	check(model.elapsed == 6000 and model.river_state_at_s(1500).temperature_c == 20.0, "Frame-time exact values")
	model.step(60)
	check(model.elapsed == 6000 and model.computing, "Dry live buffer holds clock")
	model.truncate_after(3000)
	check(model.elapsed == 3000, "Truncation control time")
	check(model.append_frames([frame(3000, 15), frame(10000, 30)]), "Append recomputed branch")
	model.elapsed = 0.0
	model.call("_apply_replay", 0.0)
	model.time_scale = 600
	for i: int in range(100):
		model._process(0.1)
	check(absf(model.elapsed - 6000) < 0.001, "600x ten-second clock")
	model.paused = true
	var before: Dictionary = model.current_frame.duplicate(true)
	model._process(10)
	check(model.current_frame == before, "Pause holds frame values")
	model.paused = false
	model.elapsed = 0.0
	model.call("_apply_replay", 0.0)
	model.world_data = {"rivers": [{"id": "test", "name": "FIREHOLE RIVER", "points": [[0, 1, 0], [0, 1, 2873], [0, 1, 3000]], "width": 50.0}]}
	model.params = {"fish_sustained_swim_bl_s": 1.5}
	model.patches = [{"id": "test_patch", "biomass": 0.8}]
	model.set("_patch_indices", {"test_patch": 0})
	var record: Dictionary = {"id": "trout", "kind": "brown_trout", "medium": "river", "river_id": "test", "start_point_index": 1, "end_point_index": 1, "water_offset_m": -0.3, "max_route_length_m": 4000.0, "approx_dimensions_m": {"body_length": 0.35}, "initial_state": "hold", "patch_id": "test_patch"}
	var actor: Node3D = Actor.new()
	actor.setup(record, FlatTerrain.new(), model)
	root.add_child(actor)
	actor.set_process(false)
	check(bool(actor.get("_valid")), "Fish route initializes")
	var previous: float = 2873.0
	var arrival: float = 0.0
	for i: int in range(600):
		model.elapsed = float(i + 1) * 10.0
		actor.call("_update_fish", 10.0)
		check(actor.chainage_m <= previous + 0.000001, "Refuge motion decreases chainage")
		previous = actor.chainage_m
		if actor.chainage_m == 35.0:
			arrival = model.elapsed
			break
	check(actor.chainage_m == 35.0, "Fish reaches refuge")
	var expected: float = (2873.0 - 35.0) / (0.35 * 1.5)
	check(absf(arrival - expected) / expected < 0.05, "Arrival equals distance over sustained speed")
	actor.chainage_m = 2873.0
	actor.set("_world_position", Vector3(0, 0.7, 2873.0))
	model.call("_at_s", 2873.0)["feeding"] = 0.0
	model.call("_at_s", 2873.0)["refuge_drive"] = 1.0
	model.elapsed += 10.0
	actor.call("_update_fish", 10.0)
	check(actor.chainage_m < 2873.0 and actor.get("_activity") == 0.0, "Hot trout escapes with feeding zero")
	check(absf(actor.swim_speed_mps - 0.525) < 0.000001, "Refuge drive uses sustained escape speed")
	model.call("_at_s", 2873.0)["feeding"] = 1.0
	model.call("_at_s", 2873.0)["refuge_drive"] = 0.0
	model.elapsed += 1.0
	actor.call("_update_fish", 1.0)
	var predicted_time: float = model.elapsed
	var held_time: float = predicted_time - 0.5
	var held_chainage: float = actor.chainage_m
	var held_position: Vector3 = actor.get("_world_position")
	model.elapsed = held_time
	model.set_clock_header({"time_scale": 600.0, "paused": false, "clock_held": true, "computing": true, "clock_debt_s": 120.0})
	for i: int in range(5):
		model.call("_apply_replay", held_time)
		model._process(0.25)
		actor.call("_update_fish", 0.25)
		actor._process(0.25)
		check(model.elapsed == held_time and actor.chainage_m == held_chainage and actor.get("_world_position") == held_position, "Repeated held payload fixes time and physical position")
	check(not model.paused and model.clock_held and model.computing, "Backend hold is separate from user pause")
	check(actor.get("_animation_player").speed_scale == 0.0, "Backend hold freezes the rig animation clock")
	check(bool(model.frame_header.clock_held), "Historical interpolation preserves current held header")
	model.set_clock_header({"time_scale": 1.0, "paused": false, "clock_held": false, "computing": false, "clock_debt_s": 0.0})
	model.elapsed = predicted_time + 1.0
	model.call("_apply_replay", model.elapsed)
	actor.call("_update_fish", 1.0)
	check(absf(held_chainage - actor.chainage_m - 0.525) < 0.000001, "Resume counts new physical time once after a correction")
	var resumed_chainage: float = actor.chainage_m
	actor.call("_update_fish", 1.0)
	check(actor.chainage_m == resumed_chainage, "Repeated resumed frame cannot swim the interval twice")
	model.reset_buffer(model.elapsed)
	check(model.get("_frames").is_empty() and model.computing, "Expired retention window clears stale interpolation frames")
	check(model.append_frames([frame(model.elapsed, 18.0), frame(model.elapsed + 600.0, 20.0)]), "Current retained window replaces expired data")
	actor.call("_update_swim_clip", 0.5)
	var frequency: float = 4.0 / 3.0 * (0.5 / 0.35 + 1.0)
	check(absf(actor.tailbeat_hz - frequency) < 0.000001, "Bainbridge gait frequency")
	var animation: AnimationPlayer = actor.get("_animation_player")
	check(animation != null and actor.get("_swim_clips").size() == 3, "Imported trout has three swimming clips")
	if animation != null:
		var clips: Dictionary = actor.get("_swim_clips")
		check(absf(animation.speed_scale * float(clips[animation.current_animation]) - frequency) / frequency < 0.05, "Animation playback frequency")
	var rng: RandomNumberGenerator = RandomNumberGenerator.new()
	rng.seed = 2244
	for i: int in range(1000):
		var at: Vector3 = Vector3(rng.randf_range(-20, 20), 1.0, rng.randf_range(0, 3000))
		var cached: Dictionary = model.river_state_at_position(at, "test", "cached")
		var full: Dictionary = model.river_state_at_position(at, "test")
		check(absf(float(cached.projected_s_m) - float(full.projected_s_m)) < 0.000001, "Cached projection matches full projection")
	var atmosphere: Node3D = Atmosphere.new()
	atmosphere.set_weather_state({"cloud_fraction": 1.0})
	var initial_cloud: float = float(atmosphere.get("_weather").cloud_fraction)
	atmosphere.time_scale = 600.0
	atmosphere.call("_update_weather_interpolation", 0.1)
	check(float(atmosphere.get("_weather").cloud_fraction) >= initial_cloud + 0.95 * (1.0 - initial_cloud), "600x cloud closes 95 percent of the initial gap in 0.1 real seconds")
	for action: StringName in InputMap.get_actions():
		if str(action).begins_with("ui_"):
			continue
		var keyboard: bool = false
		var gamepad: bool = false
		for event: InputEvent in InputMap.action_get_events(action):
			keyboard = keyboard or event is InputEventKey
			gamepad = gamepad or event is InputEventJoypadButton or event is InputEventJoypadMotion
		check(keyboard and gamepad, "Keyboard and gamepad binding: " + str(action))
	for path: String in ["res://scripts/world.gd", "res://scripts/player.gd", "res://scripts/thermal_probe_overlay.gd"]:
		check(not FileAccess.get_file_as_string(path).contains("physical_keycode"), "Handlers use named actions")
	check(Help.bindings_text().contains("Conditions"), "Help lists actual actions")
	var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/feeding-fixture.json"))
	var curves: Node = Replay.new()
	curves.begin_live({"cells": [{"id": "cell", "start_s_m": 0.0, "end_s_m": 20.0, "position_xyz": [0, 1, 10]}], "river_features": {}})
	curves.append_frames(fixture.frames)
	for sample: Dictionary in fixture.frames:
		curves.call("_apply_replay", float(sample.t_s))
		var actual: Dictionary = curves.river_state_at_s(10.0).feeding_by_species
		for species: String in ["brown_trout", "rainbow_trout"]:
			check(absf(float(actual[species]) - float(sample.feeding_by_species[species][0])) < 0.000001, "Published species curve: " + species)
	curves.free()
	var school: Array[Node3D] = []
	for i: int in range(12):
		var fish: Node3D = Actor.new()
		var data: Dictionary = record.duplicate(true)
		data["id"] = "school_%d" % i
		fish.setup(data, FlatTerrain.new(), model)
		root.add_child(fish)
		fish.set_process(false)
		fish.target_s_m = 35.0
		school.append(fish)
	var budget_start: int = Time.get_ticks_usec()
	for i: int in range(120):
		model.elapsed += 1.0 / 60.0
		for fish: Node3D in school:
			fish._process(1.0 / 60.0)
			var player: AnimationPlayer = fish.get("_animation_player")
			if player != null:
				player.advance(1.0 / 60.0)
	var actor_ms_per_frame: float = float(Time.get_ticks_usec() - budget_start) / 120000.0
	check(actor_ms_per_frame < 16.7, "Twelve rigged actors fit the 60 Hz CPU frame budget")
	for fish: Node3D in school:
		fish.queue_free()
	await process_frame
	print("TROUT_CPU_BUDGET actors=12 ms_per_frame=", actor_ms_per_frame)
	actor.free()
	model.free()
	atmosphere.free()
	print("LIVE_STATE_VALIDATION ", "PASS" if failures.is_empty() else "FAIL", " failures=", failures.size(), " arrival_s=", arrival, " frequency_hz=", frequency)
	quit(0 if failures.is_empty() else 1)
