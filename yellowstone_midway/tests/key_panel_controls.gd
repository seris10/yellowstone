extends SceneTree

const Settings = preload("res://scripts/interface_settings.gd")
const Help = preload("res://scripts/input_help.gd")
const UiTheme = preload("res://scripts/ui_theme.gd")
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
	check(Help.bindings_text().contains("Time and weather"), "Controls text lists the time and weather popover")
	check(panel.row_count() >= 15, "Shortcut panel lists the time and weather popover")
	var popover: Node = world.time_weather_panel
	await tap(KEY_N)
	check(popover.visible and not world.player.enabled, "N opens the popover and holds player input")
	var readout: String = popover.readout_text()
	check(readout.contains("Air temperature") and readout.contains("Cloud cover") and readout.contains(" C"),
		"The popover reads out modeled air temperature and rendered cloud cover")
	check(readout.contains("Stored model run"), "The popover names the clock it is reading")
	world.toggle_pause()
	await process_frame
	var still_elapsed: float = world.ecosystem.elapsed
	var still_air: float = world.ecosystem.air_c
	world.set_display_light_hour(23.0)
	world.update_environment()
	await process_frame
	check(float(world.atmosphere_controller.get_render_state().solar_elevation_deg) < 0.0,
		"A display hour of 23:00 puts the rendered sun below the horizon")
	check(world.ecosystem.elapsed == still_elapsed and world.ecosystem.air_c == still_air,
		"The display hour leaves the model clock and the modeled state alone")
	world.clear_display_light_hour()
	world.update_environment()
	await process_frame
	check(is_nan(world.display_light_hour())
		and float(world.atmosphere_controller.get_render_state().solar_elevation_deg) > 0.0,
		"Following the model clock restores the modeled sun")
	world.toggle_pause()
	await tap(KEY_N)
	check(not popover.visible and world.player.enabled, "A second press closes the popover")
	world.set_controls_open(true)
	editor.listen("time_weather")
	await tap(KEY_V)
	check(Help.keys_for(["time_weather"]) == "V" and not editor.is_listening(),
		"The popover key rebinds like every other control")
	world.set_controls_open(false)
	var base_sensitivity: float = world.player.mouse_sensitivity
	var ambience_bus: int = AudioServer.get_bus_index("Ambience")
	var ambience_db: float = AudioServer.get_bus_volume_db(maxi(ambience_bus, 0))
	world.show_settings(true)
	world.settings_panel.fov_slider.value = 88.0
	world.settings_panel.sensitivity_slider.value = 1.5
	world.settings_panel.invert_toggle.button_pressed = true
	world.settings_panel.scale_slider.value = 1.2
	world.settings_panel.ambience_slider.value = 0.5
	check(world.player.camera.fov == 88.0 and world.player.look_invert_y,
		"Field of view and inverted look reach the walker")
	check(is_equal_approx(world.player.mouse_sensitivity, base_sensitivity * 1.5),
		"Mouse sensitivity scales the project default")
	check(is_equal_approx(world.get_window().content_scale_factor, 1.2), "Interface scale reaches the window")
	check(ambience_bus > 0 and AudioServer.get_bus_volume_db(ambience_bus) < ambience_db,
		"Wind and wildlife have their own bus and the slider lowers it")
	world.interface_settings.save_settings()
	var comfort := Settings.new()
	comfort.path = SETTINGS_PATH
	comfort.load_settings()
	check(comfort.field_of_view == 88.0 and comfort.invert_look_y
		and is_equal_approx(comfort.mouse_sensitivity, 1.5) and is_equal_approx(comfort.ui_scale, 1.2),
		"Comfort settings persist")
	world.set_field_notes_open(true)
	world.update_notes()
	check(world.info_label.text.contains("[I] Close notes") and world.info_label.text.contains("[P] Menu"),
		"Field notes close with the keys currently bound")
	world.interface_settings.bind("field_notes", _event(KEY_X))
	world.apply_interface_settings()
	world.update_notes()
	check(world.info_label.text.contains("[X] Close notes"), "Field notes follow a rebound key")
	world.interface_settings.reset_bindings()
	world.set_field_notes_open(false)
	check(contrast(UiTheme.INK, UiTheme.WOOD) >= 4.5 and contrast(UiTheme.FOREST, UiTheme.WOOD) >= 4.5,
		"Ink and forest text clear WCAG AA on the board")
	check(contrast(UiTheme.INK, UiTheme.KEY_RECESS) >= 4.5 and contrast(UiTheme.FOREST, UiTheme.KEY_RECESS) >= 4.5,
		"Key box text clears WCAG AA on its recess")
	check(contrast(UiTheme.INK, band_color()) >= 4.5 and contrast(UiTheme.FOREST, band_color()) >= 4.5,
		"Row text clears WCAG AA on a tinted band")
	world.show_settings(false)
	editor.reset_all()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))
	print("KEY_PANEL_CONTROLS ", "PASS" if failures.is_empty() else "FAIL", " checks=", checks,
		" markers=", markers.get_child_count() if markers != null else 0, " failures=", failures)
	quit(0 if failures.is_empty() else 1)

## Return the relative luminance of one color, as the web contrast standard defines it.
func luminance(color: Color) -> float:
	var channels: Array[float] = []
	for value: float in [color.r, color.g, color.b]:
		channels.append(value / 12.92 if value <= 0.04045 else pow((value + 0.055) / 1.055, 2.4))
	return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

## Return the contrast ratio between text and its background.
func contrast(text: Color, background: Color) -> float:
	var high: float = maxf(luminance(text), luminance(background)) + 0.05
	var low: float = minf(luminance(text), luminance(background)) + 0.05
	return high / low

## Return the board color beneath a tinted row band.
func band_color() -> Color:
	return UiTheme.WOOD.lerp(UiTheme.WOOD_DARK, 0.22)

func _event(code: Key) -> InputEventKey:
	var event := InputEventKey.new()
	event.physical_keycode = code
	return event
