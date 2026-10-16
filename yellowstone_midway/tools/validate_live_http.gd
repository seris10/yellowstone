extends SceneTree

const Client = preload("res://scripts/live_python_client.gd")
var failures: Array[String] = []
var selected: bool = false
var appended: bool = false
var roundtrip: bool = false

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:18876")
	var client: Node = Client.new()
	client.mode_selected.connect(func(live: bool): selected = live)
	client.frames_received.connect(func(payload: Dictionary): appended = not payload.get("frames", []).is_empty())
	client.control_received.connect(func(payload: Dictionary): roundtrip = payload.get("controls", {}).get("hydro.boundary_c") == 20.0)
	root.add_child(client)
	var deadline: int = Time.get_ticks_msec() + 4000
	while not appended and Time.get_ticks_msec() < deadline:
		await process_frame
	client.player_t_s = 10.0
	client.control({"hydro.boundary_c": 20.0})
	deadline = Time.get_ticks_msec() + 4000
	while not roundtrip and Time.get_ticks_msec() < deadline:
		await process_frame
	if not selected or not appended or not roundtrip:
		failures.append("Stub mode/frame/control roundtrip failed")
	client.queue_free()
	await process_frame
	ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:18877")
	var fallback: Node = Client.new()
	var result: Array = []
	fallback.mode_selected.connect(func(live: bool): result.append(live))
	root.add_child(fallback)
	deadline = Time.get_ticks_msec() + 2000
	while result.is_empty() and Time.get_ticks_msec() < deadline:
		await process_frame
	if result.is_empty() or bool(result[0]):
		failures.append("Offline service selects baked mode")
	fallback.queue_free()
	await process_frame
	print("LIVE_HTTP_VALIDATION ", "PASS" if failures.is_empty() else "FAIL", " failures=", failures)
	quit(0 if failures.is_empty() else 1)
