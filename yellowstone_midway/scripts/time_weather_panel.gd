class_name YellowstoneTimeWeatherPanel
extends PanelContainer

## Date, clock, and weather readout on one popover with its own rebindable key.
signal closed

const UiTheme = preload("res://scripts/ui_theme.gd")
const InputHelp = preload("res://scripts/input_help.gd")
const ACTION: String = "time_weather"
const REFRESH_INTERVAL_S: float = 0.25
const WEEKDAYS: Array[String] = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday",
	"Friday", "Saturday"]
const MONTHS: Array[String] = ["January", "February", "March", "April", "May", "June", "July",
	"August", "September", "October", "November", "December"]
const COMPASS: Array[String] = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW",
	"SW", "WSW", "W", "WNW", "NW", "NNW"]
# Readouts in display order: value key and row label.
const READOUTS: Array = [
	["air", "Air temperature"],
	["cloud", "Cloud cover"],
	["humidity", "Relative humidity"],
	["rain", "Precipitation"],
	["wind", "Wind"],
	["snow", "Falling as snow"],
	["sun", "Sun"],
	["visibility", "Visibility"],
]

var world: Node
var client: YellowstoneLivePythonClient
var ecosystem: Node
var atmosphere: Node

var _date: Label
var _clock: Label
var _mode: Label
var _source: Label
var _readouts: Dictionary = {}
var _jump_date: LineEdit
var _jump_hour: SpinBox
var _jump_button: Button
var _jump_note: Label
var _light_slider: HSlider
var _light_reading: Label
var _light_note: Label
var _weather_rows: VBoxContainer
var _weather_note: Label
var _conditions_button: Button
var _close_hint: Label
var _jump_seeded: bool = false
var _elapsed: float = 0.0

## Build the popover and bind it to the clock, the live client, and the sky.
func bind(owner: Node, live_client: YellowstoneLivePythonClient, state: Node, sky: Node) -> void:
	world = owner
	client = live_client
	ecosystem = state
	atmosphere = sky
	theme = UiTheme.theme()
	set_anchors_preset(Control.PRESET_TOP_RIGHT)
	offset_left = -514.0
	offset_right = -34.0
	offset_top = 90.0
	offset_bottom = 90.0
	# Anchored to the right edge, so extra content has to grow inward.
	grow_horizontal = Control.GROW_DIRECTION_BEGIN
	grow_vertical = Control.GROW_DIRECTION_END
	custom_minimum_size = Vector2(480, 0)
	add_theme_stylebox_override("panel", UiTheme.sign_box(24, 20))
	var page := VBoxContainer.new()
	page.add_theme_constant_override("separation", 6)
	add_child(page)
	_build_header(page)
	page.add_child(UiTheme.groove())
	page.add_child(UiTheme.heading("Model clock", 12))
	_build_time_controls(page)
	page.add_child(UiTheme.groove())
	page.add_child(UiTheme.heading("Weather now", 12))
	_build_readouts(page)
	page.add_child(UiTheme.groove())
	page.add_child(UiTheme.heading("Display light", 12))
	_build_display_light(page)
	page.add_child(UiTheme.groove())
	page.add_child(UiTheme.heading("Weather controls", 12))
	_build_weather_controls(page)
	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 10)
	page.add_child(footer)
	_close_hint = _soft("", 13)
	_close_hint.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	footer.add_child(_close_hint)
	var close := Button.new()
	close.text = "Close"
	close.pressed.connect(func() -> void:
		visible = false
		closed.emit())
	footer.add_child(close)
	if client != null:
		client.schema_received.connect(func(_schema: Dictionary) -> void: _build_schema_rows())
		client.mode_selected.connect(func(_live: bool) -> void:
			_build_schema_rows()
			refresh())
	visible = false
	refresh_keys()
	refresh()

func _build_header(page: VBoxContainer) -> void:
	_date = Label.new()
	_date.add_theme_font_override("font", UiTheme.font(700))
	_date.add_theme_font_size_override("font_size", 20)
	page.add_child(_date)
	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 14)
	page.add_child(line)
	_clock = Label.new()
	_clock.add_theme_font_override("font", UiTheme.font(800))
	_clock.add_theme_font_size_override("font_size", 34)
	line.add_child(_clock)
	_mode = _soft("", 13)
	_mode.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_mode.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_mode.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	line.add_child(_mode)

func _build_time_controls(page: VBoxContainer) -> void:
	var rates := HBoxContainer.new()
	rates.add_theme_constant_override("separation", 6)
	page.add_child(rates)
	for rate: int in [1, 60, 600, 3600]:
		var button := Button.new()
		button.text = "%dx" % rate
		button.add_theme_font_size_override("font_size", 15)
		button.pressed.connect(func() -> void: world.set_time_scale(float(rate)))
		rates.add_child(button)
	var holds := HBoxContainer.new()
	holds.add_theme_constant_override("separation", 6)
	page.add_child(holds)
	var pause := Button.new()
	pause.text = "Pause or resume"
	pause.add_theme_font_size_override("font_size", 15)
	pause.pressed.connect(func() -> void: world.toggle_pause())
	holds.add_child(pause)
	var step := Button.new()
	step.text = "Step one frame"
	step.add_theme_font_size_override("font_size", 15)
	step.pressed.connect(func() -> void: world.step_simulation())
	holds.add_child(step)
	var jump := HBoxContainer.new()
	jump.add_theme_constant_override("separation", 6)
	page.add_child(jump)
	_jump_date = LineEdit.new()
	_jump_date.placeholder_text = "YYYY-MM-DD"
	_jump_date.custom_minimum_size.x = 136
	jump.add_child(_jump_date)
	_jump_hour = SpinBox.new()
	_jump_hour.min_value = 0
	_jump_hour.max_value = 23.75
	_jump_hour.step = 0.25
	jump.add_child(_jump_hour)
	_jump_button = Button.new()
	_jump_button.text = "Jump"
	_jump_button.add_theme_font_size_override("font_size", 15)
	_jump_button.pressed.connect(_jump_to_date)
	jump.add_child(_jump_button)
	_jump_note = _soft("", 13)
	_jump_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	page.add_child(_jump_note)

func _build_readouts(page: VBoxContainer) -> void:
	var grid := GridContainer.new()
	grid.columns = 4
	grid.add_theme_constant_override("h_separation", 0)
	grid.add_theme_constant_override("v_separation", 0)
	page.add_child(grid)
	for index: int in READOUTS.size():
		var entry: Array = READOUTS[index]
		var band: int = index / 2
		var name_label := Label.new()
		name_label.text = str(entry[1])
		name_label.add_theme_font_size_override("font_size", 14)
		grid.add_child(_cell(name_label, band, 8, 10))
		var value := Label.new()
		value.add_theme_font_override("font", UiTheme.font(700))
		value.add_theme_font_size_override("font_size", 14)
		value.add_theme_color_override("font_color", UiTheme.FOREST)
		_readouts[str(entry[0])] = value
		grid.add_child(_cell(value, band, 0, 12))
	_source = _soft("", 13)
	_source.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	page.add_child(_source)

func _build_display_light(page: VBoxContainer) -> void:
	_light_note = _soft("Light the scene at this hour. Display only: the model clock and the"
		+ " modeled state do not move.", 13)
	_light_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	page.add_child(_light_note)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	page.add_child(row)
	_light_slider = HSlider.new()
	_light_slider.min_value = 0.0
	_light_slider.max_value = 24.0
	_light_slider.step = 0.25
	_light_slider.custom_minimum_size = Vector2(190, 22)
	_light_slider.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(_light_slider)
	_light_reading = Label.new()
	_light_reading.add_theme_font_override("font", UiTheme.font(700))
	_light_reading.add_theme_font_size_override("font_size", 15)
	_light_reading.custom_minimum_size.x = 58
	row.add_child(_light_reading)
	var follow := Button.new()
	follow.text = "Follow the clock"
	follow.add_theme_font_size_override("font_size", 14)
	follow.pressed.connect(func() -> void:
		world.clear_display_light_hour()
		refresh())
	row.add_child(follow)
	_light_slider.value_changed.connect(func(hour: float) -> void:
		world.set_display_light_hour(hour)
		_light_reading.text = _hour_text(hour))

func _build_weather_controls(page: VBoxContainer) -> void:
	_weather_note = _soft("", 13)
	_weather_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	page.add_child(_weather_note)
	_weather_rows = VBoxContainer.new()
	_weather_rows.add_theme_constant_override("separation", 4)
	page.add_child(_weather_rows)
	_conditions_button = Button.new()
	_conditions_button.add_theme_font_size_override("font_size", 15)
	_conditions_button.pressed.connect(func() -> void: world.set_conditions_open(true))
	page.add_child(_conditions_button)
	_build_schema_rows()

## Rebuild the live weather sliders from the service schema.
func _build_schema_rows() -> void:
	if _weather_rows == null:
		return
	for child: Node in _weather_rows.get_children():
		_weather_rows.remove_child(child)
		child.queue_free()
	var entries: Array = _weather_entries()
	if entries.is_empty():
		_weather_note.text = ("Wind, cloud, and precipitation controls come from the live Python"
			+ " service schema. This build plays a stored model run, so they are read-only here.")
		return
	_weather_note.text = "Live Python service controls. Each change is sent to the model."
	for entry: Dictionary in entries:
		var key: String = str(entry.key)
		var label := _soft("%s [%s], default %s (%s)" % [entry.get("label", key),
			entry.get("unit", ""), str(entry.get("default", "")),
			entry.get("provenance", "unknown")], 13)
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.tooltip_text = str(entry.get("bound_source", ""))
		_weather_rows.add_child(label)
		if entry.get("min") != null and entry.get("max") != null:
			var slider := HSlider.new()
			slider.min_value = float(entry.min)
			slider.max_value = float(entry.max)
			var integer: bool = str(entry.get("type", "")) == "integer"
			slider.step = 1.0 if integer else (slider.max_value - slider.min_value) / 200.0
			slider.value = float(entry.default) if entry.get("default") is float or entry.get("default") is int else slider.min_value
			slider.value_changed.connect(func(value: float) -> void:
				label.text = "%s: %.3f %s (%s)" % [entry.get("label", key), value,
					entry.get("unit", ""), entry.get("provenance", "unknown")])
			slider.drag_ended.connect(func(changed: bool) -> void:
				if changed:
					client.control({key: int(slider.value) if integer else slider.value}))
			_weather_rows.add_child(slider)
		elif str(entry.get("type", "")) in ["boolean", "bool"]:
			var switch := CheckButton.new()
			switch.text = str(entry.get("label", key))
			switch.button_pressed = bool(entry.get("default", false))
			switch.toggled.connect(func(on: bool) -> void: client.control({key: on}))
			_weather_rows.add_child(switch)

## Return the schema controls that belong to weather, in schema order.
func _weather_entries() -> Array:
	var entries: Array = []
	if client == null or not client.live:
		return entries
	for entry: Variant in client.schema.get("controls", []):
		if not entry is Dictionary:
			continue
		var key: String = str(entry.get("key", ""))
		var group: String = str(entry.get("group", ""))
		if key.begins_with("weather.") or group.to_lower().contains("weather"):
			entries.append(entry)
	return entries

func _jump_to_date() -> void:
	if client == null or not client.live:
		return
	var changes: Dictionary = {"clock_hour": _jump_hour.value}
	if not _jump_date.text.is_empty():
		changes["snow.as_of_date"] = _jump_date.text
	client.control(changes)

## Update every value shown; cheap enough to run four times a second.
func refresh() -> void:
	if world == null or ecosystem == null or _date == null:
		return
	var clock: Dictionary = world.local_clock()
	var hour: float = float(clock.get("clock_hour", 0.0))
	if bool(clock.get("has_epoch", false)):
		var stamp: Dictionary = Time.get_datetime_dict_from_unix_time(
			int(float(clock.epoch_unix) + float(clock.utc_offset_hours) * 3600.0))
		_date.text = "%s %d %s %d" % [WEEKDAYS[int(stamp.weekday)], int(stamp.day),
			MONTHS[int(stamp.month) - 1], int(stamp.year)]
		hour = float(stamp.hour) + float(stamp.minute) / 60.0
	else:
		_date.text = "Model day %d" % int(clock.get("day_of_year", 0))
	_clock.text = _hour_text(hour)
	var offset: float = float(clock.get("utc_offset_hours", -6.0))
	var live: bool = bool(ecosystem.live_mode)
	_mode.text = "%s | %.0fx%s | UTC%+.0f" % ["Live Python session" if live else "Stored model run",
		float(ecosystem.time_scale), " paused" if ecosystem.paused else "", offset]
	_jump_button.disabled = not live
	_jump_date.editable = live
	_jump_hour.editable = live
	_jump_note.text = "" if live else "The date and hour jump needs the live Python service."
	if not _jump_seeded:
		_jump_seeded = true
		_jump_hour.set_value_no_signal(snappedf(clampf(hour, 0.0, 23.75), 0.25))
	_refresh_weather(live)
	var held: float = float(world.display_light_hour())
	if is_nan(held):
		_light_reading.text = "Model clock"
		if not _light_slider.has_focus():
			_light_slider.set_value_no_signal(snappedf(clampf(hour, 0.0, 24.0), 0.25))
	else:
		_light_reading.text = _hour_text(held)
	_conditions_button.text = "Open the conditions panel (%s)" % InputHelp.keys_for(["conditions"])

func _refresh_weather(live: bool) -> void:
	var render: Dictionary = atmosphere.get_render_state() if atmosphere != null else {}
	var direction: float = fposmod(rad_to_deg(atan2(-ecosystem.wind.x, ecosystem.wind.y)), 360.0)
	var rain: float = float(render.get("precipitation_rate_mm_h", 0.0))
	var elevation: float = float(render.get("solar_elevation_deg", 0.0))
	var azimuth: float = float(render.get("solar_azimuth_deg", 0.0))
	_set_readout("air", "%.1f C" % float(ecosystem.air_c))
	_set_readout("humidity", "%d%%" % int(roundf(float(ecosystem.humidity) * 100.0)))
	_set_readout("wind", "%.1f m/s %s" % [ecosystem.wind.length(), _compass(direction)],
		"From %d deg" % int(roundf(direction)))
	_set_readout("cloud", "%d%%" % int(roundf(float(render.get("cloud_fraction", 0.0)) * 100.0)))
	_set_readout("rain", "none" if rain <= 0.0 else "%.2f mm/h" % rain)
	_set_readout("snow", "%d%%" % int(roundf(float(render.get("snow_fraction", 0.0)) * 100.0)))
	_set_readout("visibility", "%.1f km" % (float(render.get("visibility_m", 0.0)) / 1000.0))
	var sun: String = "below the horizon"
	if elevation > 0.0:
		sun = "%.0f deg up, %s" % [elevation, _compass(azimuth)]
	_set_readout("sun", sun, "Azimuth %d deg" % int(roundf(azimuth)))
	_source.text = ("Air, humidity, and wind are this frame's modeled weather."
		if live else "Air, humidity, and wind come from the stored model run.") + (
		" Cloud, precipitation, visibility, and sun are the display state the sky is rendering.")

func _set_readout(key: String, text: String, tip: String = "") -> void:
	var label: Label = _readouts.get(key)
	if label != null:
		label.text = text
		label.tooltip_text = tip

## Refresh the key names shown after a rebinding.
func refresh_keys() -> void:
	if _close_hint == null:
		return
	_close_hint.text = "%s closes this panel." % InputHelp.keys_for([ACTION])
	if _conditions_button != null:
		_conditions_button.text = "Open the conditions panel (%s)" % InputHelp.keys_for(["conditions"])

## Report every readout as text; used by the control regression test.
func readout_text() -> String:
	var lines: PackedStringArray = PackedStringArray([_date.text + " " + _clock.text, _mode.text])
	for entry: Array in READOUTS:
		var label: Label = _readouts.get(str(entry[0]))
		lines.append("%s: %s" % [str(entry[1]), label.text if label != null else "unavailable"])
	return "\n".join(lines)

func _process(delta: float) -> void:
	if not visible:
		return
	_elapsed += delta
	if _elapsed < REFRESH_INTERVAL_S:
		return
	_elapsed = 0.0
	refresh()

func _hour_text(hour: float) -> String:
	var wrapped: float = fposmod(hour, 24.0)
	return "%02d:%02d" % [int(wrapped), int(roundf(fmod(wrapped, 1.0) * 60.0)) % 60]

func _compass(degrees: float) -> String:
	return COMPASS[int(roundf(fposmod(degrees, 360.0) / 22.5)) % 16]

func _soft(text: String, size: int) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", UiTheme.INK_SOFT)
	return label

## One grid cell carried on its row band.
func _cell(label: Label, row: int, margin_left: int, margin_right: int) -> PanelContainer:
	var band := PanelContainer.new()
	var style: StyleBox = UiTheme.row_tint(row, 0, 3)
	style.content_margin_left = margin_left
	style.content_margin_right = margin_right
	band.add_theme_stylebox_override("panel", style)
	band.add_child(label)
	return band
