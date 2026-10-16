extends SceneTree

var world: Node
var failures: Array[String] = []
var checks := 0
var transitions: Array = []

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		push_error(message)

func press(code: int, ctrl: bool = false) -> void:
	var event := InputEventKey.new()
	event.keycode = code
	event.physical_keycode = code
	event.ctrl_pressed = ctrl
	event.pressed = true
	var start := Time.get_ticks_usec()
	Input.parse_input_event(event)
	await process_frame
	transitions.append({"key": code, "ctrl": ctrl, "next_frame_ms": (Time.get_ticks_usec() - start) / 1000.0})
	await process_frame
	event.pressed = false
	Input.parse_input_event(event)
	await process_frame

func check_cursor(visible: bool, label: String) -> void:
	if DisplayServer.get_name() != "headless":
		check(Input.mouse_mode == (Input.MOUSE_MODE_VISIBLE if visible else Input.MOUSE_MODE_CAPTURED), label)

func run() -> void:
	world = load("res://scenes/main.tscn").instantiate()
	root.add_child(world)
	await process_frame
	if world.player == null or world.info_panel == null:
		push_error("World initialization failed")
		quit(2)
		return
	check(world.menu.visible and not world.player.enabled, "Starting menu must own input")
	var build_id: String = str(world.ecosystem.params.get("build_id", world.ecosystem.frame_header.get("build_id", "unrecorded")))
	check(not world.simulation_status_text().contains(build_id), "Hashes must be hidden with F4 closed")
	await press(KEY_F4)
	check(world.perf_probe.visible, "F4 must open diagnostics")
	check(world.simulation_status_text().contains(build_id), "F4 must expose the build identity")
	await press(KEY_F4)
	check(not world.simulation_status_text().contains(build_id), "Closing F4 must hide hashes")
	await press(KEY_P)
	check(world.player.enabled and not world.menu.visible, "P must resume walking")
	await press(KEY_I)
	check(world.info_panel.visible and world.ecosystem.paused, "Notes must pause playback")
	check(not world.player.enabled, "Notes must hold player input")
	check_cursor(true, "Notes must release the cursor")
	await press(KEY_ESCAPE)
	check(not world.player.enabled and world.info_panel.visible, "Escape must preserve notes input ownership")
	check_cursor(true, "Escape must preserve a visible notes cursor")
	await press(KEY_P)
	await press(KEY_I)
	check(world.menu.visible and not world.info_panel.visible, "Closing notes must leave the menu open")
	check(not world.player.enabled, "The remaining menu must retain player input")
	check_cursor(true, "The remaining menu must retain the cursor")
	await press(KEY_P)
	check(world.player.enabled, "Closing the last modal must restore walking")
	await press(KEY_I)
	var notes_time: float = world.ecosystem.elapsed
	await press(KEY_Q)
	await create_timer(0.35).timeout
	check(world.ecosystem.paused, "Q must preserve the notes pause hold")
	check(is_equal_approx(notes_time, world.ecosystem.elapsed), "Playback must stay still inside notes")
	await press(KEY_I)
	check(not world.ecosystem.paused, "Closing notes must restore running playback")
	await press(KEY_Q)
	await press(KEY_I)
	await press(KEY_Q)
	await press(KEY_I)
	check(world.ecosystem.paused, "Closing notes must preserve a prior user pause")
	await press(KEY_Q)
	await press(KEY_S, true)
	check(world.simulation_panel.visible and not world.player.enabled, "Study controls must own input")
	await press(KEY_P)
	await press(KEY_S, true)
	check(world.menu.visible and not world.simulation_panel.visible, "Closing study must preserve the menu")
	check(not world.player.enabled, "Closing study must preserve menu input ownership")
	check_cursor(true, "Closing study must preserve the menu cursor")
	await press(KEY_P)
	check(world.player.enabled, "Closing study and menu must restore walking")
	for mode: int in [1, 2, 0]:
		await press(KEY_F)
		check(world.hud_mode == mode and world.overlay.visible, "HUD cycling must preserve the interface layer")
		await press(KEY_P)
		check(world.menu.visible and not world.player.enabled, "P must work in every HUD mode")
		await press(KEY_P)
	await press(KEY_U)
	check(world.toast_label.text.contains("Open the map"), "A closed-map census key must explain its prerequisite")
	await press(KEY_M)
	var census_before: bool = world.map_view.census_visible
	await press(KEY_U)
	check(world.map_view.visible and world.map_view.census_visible != census_before, "U must toggle the open-map census")
	await press(KEY_M)
	await press(KEY_T)
	var end_s: float = float(world.ecosystem.get("_frames")[-1].t_s)
	check(is_equal_approx(world.ecosystem.elapsed, end_s), "T must reach the replay endpoint")
	await press(KEY_T)
	check(is_equal_approx(world.ecosystem.elapsed, end_s), "An exhausted jump must preserve model time")
	check(world.toast_label.visible and world.toast_label.text == "Replay has reached its end", "An exhausted jump must show feedback")
	var result := {"checks": checks, "failures": failures, "engine": Engine.get_version_info(),
		"display": DisplayServer.get_name(), "transitions": transitions}
	var output := OS.get_environment("YELLOWSTONE_CONTROL_RESULTS")
	if not output.is_empty():
		var file := FileAccess.open(output, FileAccess.WRITE)
		if file == null:
			push_error("Control result output is unavailable")
			quit(2)
			return
		file.store_string(JSON.stringify(result, "  "))
	print("CONTROL_REGRESSION ", JSON.stringify(result))
	quit(0 if failures.is_empty() else 1)
