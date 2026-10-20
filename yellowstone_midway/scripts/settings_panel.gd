class_name YellowstoneSettingsPanel
extends VBoxContainer

## Menu page for interface preferences.
signal changed
signal closed
signal controls_requested

const UiTheme = preload("res://scripts/ui_theme.gd")

var settings: YellowstoneInterfaceSettings
var shortcut_bar_toggle: CheckButton
var toggle_mode_toggle: CheckButton
var message: Label

func bind(preferences: YellowstoneInterfaceSettings) -> void:
	settings = preferences
	add_theme_constant_override("separation", 12)
	add_child(UiTheme.heading("Settings"))
	shortcut_bar_toggle = _check("Show the shortcut bar", settings.shortcut_bar)
	shortcut_bar_toggle.toggled.connect(func(on: bool) -> void:
		settings.shortcut_bar = on
		_commit())
	toggle_mode_toggle = _check("Keep shortcuts open after letting go", settings.key_panel_toggle)
	toggle_mode_toggle.toggled.connect(func(on: bool) -> void:
		settings.key_panel_toggle = on
		_commit())
	var controls := Button.new()
	controls.text = "Change controls"
	controls.alignment = HORIZONTAL_ALIGNMENT_LEFT
	controls.custom_minimum_size.y = 44
	controls.pressed.connect(func() -> void: controls_requested.emit())
	add_child(controls)
	message = Label.new()
	message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	message.add_theme_color_override("font_color", UiTheme.INK_SOFT)
	message.add_theme_font_size_override("font_size", 14)
	message.visible = false
	add_child(message)
	var back := Button.new()
	back.text = "Back"
	back.alignment = HORIZONTAL_ALIGNMENT_LEFT
	back.custom_minimum_size.y = 44
	back.pressed.connect(func() -> void: closed.emit())
	add_child(back)

func _commit() -> void:
	var err: Error = settings.save_settings()
	message.text = "" if err == OK else "Settings could not be saved (error %d)." % err
	message.visible = not message.text.is_empty()
	changed.emit()

func _check(text: String, on: bool) -> CheckButton:
	var check := CheckButton.new()
	check.text = text
	check.button_pressed = on
	check.add_theme_font_size_override("font_size", 17)
	add_child(check)
	return check
