extends SceneTree

const Client = preload("res://scripts/live_python_client.gd")
const Replay = preload("res://scripts/python_river_replay.gd")
var failures: Array[String] = []
var payload: Dictionary = {}
var control: Dictionary = {}
var comparison: Dictionary = {}
var schema: Dictionary = {}
var model: Node
var client: Node

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, message: String) -> void:
	if not value:
		failures.append(message)
		push_error(message)

func has_evolved_frame(value: Dictionary, at_s: float) -> bool:
	for frame: Dictionary in value.get("frames", []):
		if float(frame.t_s) > at_s:
			return true
	return false

func run() -> void:
	ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:18878")
	model = Replay.new()
	model.set_process(false)
	client = Client.new()
	client.schema_received.connect(func(value: Dictionary):
		schema = value
		model.begin_live(schema))
	client.frames_received.connect(func(value: Dictionary):
		payload = value
		model.append_frames(value.get("frames", [])))
	client.control_received.connect(func(value: Dictionary):
		control = value
		model.truncate_after(float(value.truncate_after_t_s)))
	client.response_received.connect(func(kind: String, value: Dictionary):
		if kind == "compare":
			comparison = value)
	client.failed.connect(func(message: String): print("CLIENT_FAILURE ", message))
	root.add_child(client)
	var deadline: int = Time.get_ticks_msec() + 10000
	while payload.get("frames", []).size() < 2 and Time.get_ticks_msec() < deadline:
		await create_timer(0.01).timeout
	check(not schema.is_empty() and model.replay_enabled, "Actual service selects live mode and geometry")
	check(model.get("_frames").size() >= 2, "Actual service frames append")
	client.player_t_s = float(payload.get("player_t_s", 20.0))
	client.control({"hydro.boundary_c": 25.0})
	deadline = Time.get_ticks_msec() + 10000
	while control.is_empty() and Time.get_ticks_msec() < deadline:
		await create_timer(0.01).timeout
	check(control.get("ok", false), "Actual control roundtrip")
	check("river" in control.get("dirty_stages", []) and "oxygen" in control.get("dirty_stages", []) and "snow" not in control.get("dirty_stages", []), "Dependency stages reflect upstream temperature control")
	payload = {}
	deadline = Time.get_ticks_msec() + 10000
	while not has_evolved_frame(payload, float(control.get("truncate_after_t_s", INF))) and Time.get_ticks_msec() < deadline:
		await create_timer(0.01).timeout
	var new_frames: Array = payload.get("frames", [])
	check(not new_frames.is_empty(), "Recomputed frames arrive")
	if not new_frames.is_empty():
		var first: Dictionary = new_frames[-1]
		for frame: Dictionary in new_frames:
			if float(frame.t_s) > float(control.truncate_after_t_s):
				first = frame
				break
		check(float(first.temperature_c[0]) > float(first.temperature_c[1]), "Boundary responds before downstream")
		model.elapsed = float(first.t_s)
		model.call("_apply_replay", model.elapsed)
		check(model.river_state_at_s(10).temperature_c == first.temperature_c[0], "Probe matches actual Python frame")
		check(model.current_frame.weather.air_c == first.weather.air_c, "HUD weather matches Python frame")
		for species: String in ["brown_trout", "rainbow_trout"]:
			check(model.river_state_at_s(10).feeding_by_species[species] == first.feeding_by_species[species][0], "Live species feeding matches Python: " + species)
		check(not model.trout_state("brown_fixture").is_empty() and not model.trout_state("rainbow_fixture").is_empty(), "Live refuge targets are actor-specific")
		print("CAUSAL_BOUNDARY_TEMPERATURES ", first.temperature_c)
	client.player_t_s = float(control.get("truncate_after_t_s", 0.0)) + 0.137
	client.command("mark", {})
	await create_timer(0.4).timeout
	client.command("compare", {})
	deadline = Time.get_ticks_msec() + 10000
	while comparison.is_empty() and Time.get_ticks_msec() < deadline:
		await create_timer(0.01).timeout
	check(comparison.get("A", {}).get("temperature_c") == comparison.get("B", {}).get("temperature_c"), "Identical marked branches compare equally")
	print("COMPARE_METRICS ", comparison.get("metrics", {}))
	check(comparison.get("metrics", {}).get("refuge_shift_m") == 0.0, "Identical refuge shift is zero")
	client.queue_free()
	await process_frame
	model.free()
	print("LIVE_SERVICE_VALIDATION ", "PASS" if failures.is_empty() else "FAIL", " failures=", failures)
	quit(0 if failures.is_empty() else 1)
