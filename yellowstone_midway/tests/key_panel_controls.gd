extends SceneTree

const Settings = preload("res://scripts/interface_settings.gd")
const Help = preload("res://scripts/input_help.gd")
const SETTINGS_PATH: String = "user://test_interface_settings.cfg"

var world: Node
var failures: Array[String] = []
var checks := 0

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		push_error(message)

func key(code: int, down: bool, ctrl: bool = false) -> void:
	var event := InputEventKey.new()
	event.keycode = code
	event.physical_keycode = code
	event.ctrl_pressed = ctrl
	event.pressed = down
	Input.parse_input_event(event)
	await process_frame
	await process_frame

func tap(code: int, ctrl: bool = false) -> void:
	await key(code, true, ctrl)
	await key(code, false, ctrl)

func run() -> void:
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))
	world = load("res://scenes/main.tscn").instantiate()
	world.interface_settings_path = SETTINGS_PATH
	root.add_child(world)
	await process_frame
	if world.key_panel == null or world.settings_panel == null:
		push_error("World initialization failed")
		quit(2)
		return
	var panel: Node = world.key_panel
	var editor: Node = world.input_help
	check(world.help_label.text == "Hold / for shortcuts", "Default bottom text is a single shortcut hint")
	check(not panel.visible, "Shortcut panel starts hidden")
	check(panel.row_count() >= 14, "Shortcut panel lists the common controls")
	check(Help.bindings_text().contains("Shortcut panel") and Help.bindings_text().contains("Conditions"), "Controls text lists every group")
	await key(KEY_SLASH, true)
	check(panel.visible and not world.help_label.visible, "Holding the panel key shows the panel in place of the hint")
	await create_timer(0.3).timeout
	check(panel.visible, "The panel stays up while the key is held")
	await key(KEY_SLASH, false)
	check(not panel.visible and world.help_label.visible, "Releasing the panel key restores the hint")
	check(world.menu.visible, "The starting menu is open")
	world.show_settings(true)
	check(world.settings_panel.visible and not world.content.visible, "Settings replace the menu page")
	world.settings_panel.toggle_mode_toggle.button_pressed = true
	check(panel.toggle_mode and world.help_label.text == "Press / for shortcuts", "Toggle mode updates the panel and hint")
	await tap(KEY_SLASH)
	check(panel.visible, "In toggle mode a press and release leaves the panel open")
	await tap(KEY_SLASH)
	check(not panel.visible, "In toggle mode a second press closes the panel")
	world.settings_panel.shortcut_bar_toggle.button_pressed = true
	check(world.help_label.text.contains("WASD  Walk") and world.help_label.text.contains("M  Map") and world.help_label.text.contains("P  Menu"), "The shortcut bar setting restores the full bar")
	world.settings_panel.controls_requested.emit()
	check(editor.visible and not world.player.enabled, "Settings open the controls editor")
	editor.listen("key_panel")
	await tap(KEY_B)
	check(not editor.is_listening() and Help.keys_for(["key_panel"]) == "B", "A key box takes the next key pressed")
	check(world.menu_hint_label.text.begins_with("Press B for shortcuts"), "Menu hint names the rebound key")
	check(InputMap.action_get_events("key_panel").any(func(e: InputEvent) -> bool: return e is InputEventJoypadButton), "Rebinding keeps the gamepad binding")
	editor.listen("map")
	await tap(KEY_I)
	check(Help.keys_for(["map"]) == "I" and Help.keys_for(["field_notes"]) == "M", "A taken key trades places with its old action")
	check(editor._message.text == "Map is now I. Field notes moved to M.", "The editor reports the trade")
	editor.listen("map")
	await tap(KEY_ESCAPE)
	check(not editor.is_listening() and Help.keys_for(["map"]) == "I", "Esc cancels listening")
	check(not world.interface_settings.bind("map", _event(KEY_F4)).ok, "Reserved keys are refused")
	editor.listen("brisk_walk")
	await tap(KEY_CTRL)
	check(Help.keys_for(["brisk_walk"]) == "Ctrl" and Help.keys_for(["fly_down"]) == "Shift", "A modifier alone binds as its own key")
	editor.listen("calibration")
	await key(KEY_CTRL, true)
	await key(KEY_K, true, true)
	await key(KEY_K, false, true)
	await key(KEY_CTRL, false)
	check(Help.keys_for(["calibration"]) == "Ctrl+K", "Modifier combinations bind")
	await tap(KEY_B)
	check(panel.visible, "The rebound key opens the panel")
	await tap(KEY_B)
	await tap(KEY_SLASH)
	check(not panel.visible, "The previous key no longer opens the panel")
	var stored := Settings.new()
	stored.path = SETTINGS_PATH
	editor.reset_all()
	check(Help.keys_for(["map"]) == "M" and Help.keys_for(["key_panel"]) == "/" and Help.keys_for(["study_scene"]) == "Ctrl+S", "Reset restores every default")
	editor.listen("pause")
	await tap(KEY_Y)
	stored.load_settings()
	check(stored.shortcut_bar and stored.key_panel_toggle, "Interface settings persist")
	var config := ConfigFile.new()
	config.load(SETTINGS_PATH)
	check(config.get_section_keys("bindings") == PackedStringArray(["pause"]), "Only changed keys are stored")
	world.set_controls_open(false)
	await tap(KEY_P)
	check(not world.menu.visible and not world.settings_panel.visible and world.content.visible, "Closing the menu returns settings to the main page")
	check(world.get("_geochemistry_summary").size() > 0, "Geochemistry is published in the active generation")
	await tap(KEY_G)
	var markers: Node3D = world.get("_overlays").get_node_or_null("GeochemistryMarkers")
	check(markers != null and markers.visible and markers.get_child_count() > 0, "G shows the geochemistry markers")
	check(world.toast_label.text == "Geochemistry overlay on", "G reports the overlay state")
	await tap(KEY_G)
	check(markers != null and not markers.visible, "G hides the geochemistry markers")
	editor.reset_all()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))
	print("KEY_PANEL_CONTROLS ", "PASS" if failures.is_empty() else "FAIL", " checks=", checks,
		" markers=", markers.get_child_count() if markers != null else 0, " failures=", failures)
	quit(0 if failures.is_empty() else 1)

func _event(code: Key) -> InputEventKey:
	var event := InputEventKey.new()
	event.physical_keycode = code
	return event
