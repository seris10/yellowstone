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
var invert_toggle: CheckButton
var sensitivity_slider: HSlider
var fov_slider: HSlider
var master_slider: HSlider
var ambience_slider: HSlider
var scale_slider: HSlider
var message: Label
var _dirty: bool = false

func _ready() -> void:
	visibility_changed.connect(func() -> void:
		if not visible:
			_save_if_dirty())

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
	add_child(UiTheme.groove())
	add_child(UiTheme.heading("Walking and view", 12))
	var view := _grid()
	sensitivity_slider = _slider(view, "Mouse sensitivity", settings.mouse_sensitivity,
		YellowstoneInterfaceSettings.SENSITIVITY_RANGE, 0.05, "x",
		func(value: float) -> void: settings.mouse_sensitivity = value)
	fov_slider = _slider(view, "Field of view", settings.field_of_view,
		YellowstoneInterfaceSettings.FOV_RANGE, 1.0, "deg",
		func(value: float) -> void: settings.field_of_view = value)
	invert_toggle = _check("Invert vertical look", settings.invert_look_y)
	invert_toggle.toggled.connect(func(on: bool) -> void:
		settings.invert_look_y = on
		_commit())
	add_child(UiTheme.groove())
	add_child(UiTheme.heading("Sound", 12))
	var sound := _grid()
	master_slider = _slider(sound, "Master volume", settings.master_volume,
		YellowstoneInterfaceSettings.VOLUME_RANGE, 0.01, "%",
		func(value: float) -> void: settings.master_volume = value)
	ambience_slider = _slider(sound, "Wind and wildlife", settings.ambience_volume,
		YellowstoneInterfaceSettings.VOLUME_RANGE, 0.01, "%",
		func(value: float) -> void: settings.ambience_volume = value)
	add_child(UiTheme.groove())
	add_child(UiTheme.heading("Interface", 12))
	var interface_grid := _grid()
	scale_slider = _slider(interface_grid, "Interface scale", settings.ui_scale,
		YellowstoneInterfaceSettings.UI_SCALE_RANGE, 0.05, "%",
		func(value: float) -> void: settings.ui_scale = value)
	add_child(UiTheme.groove())
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

func _grid() -> GridContainer:
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 14)
	grid.add_theme_constant_override("v_separation", 6)
	add_child(grid)
	return grid

## One labeled slider row; applies live and saves once the value settles.
func _slider(grid: GridContainer, text: String, value: float, limits: Vector2, step: float,
		unit: String, apply: Callable) -> HSlider:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 16)
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(label)
	var slider := HSlider.new()
	slider.min_value = limits.x
	slider.max_value = limits.y
	slider.step = step
	slider.value = value
	slider.custom_minimum_size = Vector2(150, 22)
	slider.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	grid.add_child(slider)
	var readout := Label.new()
	readout.text = _reading(value, unit)
	readout.custom_minimum_size.x = 64
	readout.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	readout.add_theme_font_override("font", UiTheme.font(700))
	readout.add_theme_font_size_override("font_size", 15)
	grid.add_child(readout)
	slider.value_changed.connect(func(current: float) -> void:
		apply.call(current)
		readout.text = _reading(current, unit)
		_dirty = true
		changed.emit())
	slider.drag_ended.connect(func(_changed: bool) -> void: _save_if_dirty())
	slider.focus_exited.connect(_save_if_dirty)
	return slider

func _reading(value: float, unit: String) -> String:
	match unit:
		"x":
			return "%.2fx" % value
		"deg":
			return "%d deg" % int(roundf(value))
		_:
			return "%d%%" % int(roundf(value * 100.0))

func _save_if_dirty() -> void:
	if not _dirty or settings == null:
		return
	_dirty = false
	var err: Error = settings.save_settings()
	message.text = "" if err == OK else "Settings could not be saved (error %d)." % err
	message.visible = not message.text.is_empty()

func _check(text: String, on: bool) -> CheckButton:
	var check := CheckButton.new()
	check.text = text
	check.button_pressed = on
	check.add_theme_font_size_override("font_size", 17)
	add_child(check)
	return check
