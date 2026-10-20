class_name YellowstoneInputHelp
extends PanelContainer

## Central controls page; each key box rebinds its action.
signal bindings_changed
signal closed

const UiTheme = preload("res://scripts/ui_theme.gd")

const PAD_LAYERS: Dictionary = {
	"field_notes": 1, "map": 1, "photo_mode": 1, "authoring_flight": 1,
	"return_to_anchor": 1, "jump_two_hours": 1, "compare_replay": 1,
	"conditions": 1,
	"calibration": 2, "plume": 2, "geochemistry": 2, "census": 2,
	"overland": 2, "groundwater": 2, "study_scene": 2,
	"step_frame": 2,
	"scale_1": 3, "scale_60": 3, "scale_600": 3, "scale_3600": 3,
	"intervene_shade": 3, "intervene_outflow": 3, "intervene_tributary": 3,
	"intervene_grazing": 3,
}

# Player-facing controls; keys come from the InputMap and track remaps.
const CONTROL_GROUPS: Array = [
	{"title": "Walking", "rows": [
		{"label": "Forward", "actions": ["move_forward"]},
		{"label": "Left", "actions": ["move_left"]},
		{"label": "Back", "actions": ["move_back"]},
		{"label": "Right", "actions": ["move_right"]},
		{"label": "Brisk walk", "actions": ["brisk_walk"]},
		{"label": "Hop", "actions": ["jump"]},
		{"label": "Look around", "keys": "Mouse"},
		{"label": "Back to the starting spot", "actions": ["return_to_anchor"]},
		{"label": "Free the cursor", "keys": "Esc"},
	]},
	{"title": "Panels", "rows": [
		{"label": "Menu", "actions": ["menu"]},
		{"label": "Field notes", "actions": ["field_notes"]},
		{"label": "Map", "actions": ["map"]},
		{"label": "Conditions", "actions": ["conditions"]},
		{"label": "Controls (this page)", "actions": ["help"]},
		{"label": "Shortcut panel", "actions": ["key_panel"]},
		{"label": "Calibration", "actions": ["calibration"]},
	]},
	{"title": "Time and model", "rows": [
		{"label": "Pause", "actions": ["pause"]},
		{"label": "Step one frame", "actions": ["step_frame"]},
		{"label": "Jump two hours", "actions": ["jump_two_hours"]},
		{"label": "Compare with replay", "actions": ["compare_replay"]},
		{"label": "Speed 1x", "actions": ["scale_1"]},
		{"label": "Speed 60x", "actions": ["scale_60"]},
		{"label": "Speed 600x", "actions": ["scale_600"]},
		{"label": "Speed 3600x", "actions": ["scale_3600"]},
		{"label": "Study mode", "actions": ["study_scene"]},
	]},
	{"title": "Live model changes", "rows": [
		{"label": "Shade this reach", "actions": ["intervene_shade"]},
		{"label": "Excelsior outflow on/off", "actions": ["intervene_outflow"]},
		{"label": "Cold tributary pockets", "actions": ["intervene_tributary"]},
		{"label": "Bison grazing", "actions": ["intervene_grazing"]},
	]},
	{"title": "Overlays and camera", "rows": [
		{"label": "River probe", "actions": ["probe"]},
		{"label": "Plume overlay", "actions": ["plume"]},
		{"label": "Geochemistry overlay", "actions": ["geochemistry"]},
		{"label": "Overland flow overlay", "actions": ["overland"]},
		{"label": "Groundwater overlay", "actions": ["groundwater"]},
		{"label": "Tree census on the map", "actions": ["census"]},
		{"label": "Cycle the HUD", "actions": ["photo_mode"]},
		{"label": "Authoring flight", "actions": ["authoring_flight"]},
		{"label": "Fly down", "actions": ["fly_down"]},
	]},
]

# Punctuation key names shown as the printed character.
const KEY_GLYPHS: Dictionary = {
	"Slash": "/", "Backslash": "\\", "Period": ".", "Comma": ",", "Semicolon": ";",
	"Apostrophe": "'", "BracketLeft": "[", "BracketRight": "]", "Minus": "-",
	"Equal": "=", "QuoteLeft": "`",
}

var settings: YellowstoneInterfaceSettings
var _key_buttons: Dictionary = {}
var _listening: String = ""
var _held_modifier: Key = KEY_NONE
var _message: Label

static func action_label(action: String) -> String:
	for group: Dictionary in CONTROL_GROUPS:
		for row: Dictionary in group["rows"]:
			if action in row.get("actions", []):
				return str(row["label"])
	return action.capitalize()

static func pressed(event: InputEvent, action: String) -> bool:
	if not event.is_action_pressed(action) or event.is_echo():
		return false
	if event is InputEventJoypadButton:
		var layer: int = int(PAD_LAYERS.get(action, 0))
		var left: bool = Input.is_joy_button_pressed(event.device, JOY_BUTTON_LEFT_SHOULDER)
		var right: bool = Input.is_joy_button_pressed(event.device, JOY_BUTTON_RIGHT_SHOULDER)
		return layer == (3 if left and right else 1 if left else 2 if right else 0)
	return true

func _ready() -> void:
	theme = UiTheme.theme()
	set_anchors_preset(Control.PRESET_CENTER)
	custom_minimum_size = Vector2(820, 700)
	offset_left = -410.0
	offset_right = 410.0
	offset_top = -350.0
	offset_bottom = 350.0
	var page := VBoxContainer.new()
	page.add_theme_constant_override("separation", 10)
	add_child(page)
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 10)
	page.add_child(header)
	var title := Label.new()
	title.text = "Controls"
	title.add_theme_font_override("font", UiTheme.font(700))
	title.add_theme_font_size_override("font_size", 28)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	var reset := Button.new()
	reset.text = "Reset all keys"
	reset.pressed.connect(reset_all)
	header.add_child(reset)
	var close := Button.new()
	close.text = "Close"
	close.pressed.connect(func() -> void:
		stop_listening()
		visible = false
		closed.emit())
	header.add_child(close)
	var how := Label.new()
	how.text = "Click a key, then press the one you want. Esc cancels."
	how.add_theme_color_override("font_color", UiTheme.INK_SOFT)
	how.add_theme_font_size_override("font_size", 15)
	page.add_child(how)
	_message = Label.new()
	_message.add_theme_color_override("font_color", UiTheme.FOREST)
	_message.add_theme_font_size_override("font_size", 15)
	page.add_child(_message)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	page.add_child(scroll)
	var columns := HBoxContainer.new()
	columns.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	columns.add_theme_constant_override("separation", 32)
	scroll.add_child(columns)
	var left := VBoxContainer.new()
	var right := VBoxContainer.new()
	for column: VBoxContainer in [left, right]:
		column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		column.add_theme_constant_override("separation", 4)
		columns.add_child(column)
	for index: int in CONTROL_GROUPS.size():
		_add_group(left if index < 2 else right, CONTROL_GROUPS[index])
	var pad := Label.new()
	pad.text = "Hover a key to see its gamepad button. LB, RB, or both switch the gamepad to its other button sets."
	pad.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	pad.add_theme_color_override("font_color", UiTheme.INK_SOFT)
	pad.add_theme_font_size_override("font_size", 13)
	page.add_child(pad)
	refresh()
	visible = false

func _add_group(column: VBoxContainer, group: Dictionary) -> void:
	var heading := UiTheme.heading(str(group["title"]), 13)
	if column.get_child_count() > 0:
		heading.custom_minimum_size.y = 36
		heading.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
	column.add_child(heading)
	for row: Dictionary in group["rows"]:
		var line := HBoxContainer.new()
		column.add_child(line)
		var label := Label.new()
		label.text = str(row["label"])
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		label.add_theme_font_size_override("font_size", 15)
		line.add_child(label)
		var actions: Array = row.get("actions", [])
		var box := Button.new()
		box.custom_minimum_size = Vector2(120, 30)
		box.add_theme_font_size_override("font_size", 15)
		line.add_child(box)
		if actions.is_empty():
			box.text = str(row["keys"])
			box.disabled = true
			continue
		var action: String = actions[0]
		var pad: String = _pad_for(actions)
		box.tooltip_text = "Gamepad: " + (pad if not pad.is_empty() else "none")
		box.pressed.connect(func() -> void: listen(action))
		_key_buttons[action] = box

func refresh() -> void:
	for action: String in _key_buttons:
		var box: Button = _key_buttons[action]
		box.remove_theme_stylebox_override("normal")
		box.remove_theme_color_override("font_color")
		if action == _listening:
			box.text = "Press a key"
			box.add_theme_stylebox_override("normal", UiTheme.flat(UiTheme.PLANK_HOVER, UiTheme.FOREST, 2, 3, 14, 7))
			box.add_theme_color_override("font_color", UiTheme.FOREST)
		else:
			var keys: String = keys_for([action])
			box.text = keys if not keys.is_empty() else "Not set"

## Puts one key box into listening mode.
func listen(action: String) -> void:
	_listening = action
	_message.text = ""
	refresh()

func stop_listening() -> void:
	_listening = ""
	refresh()

func is_listening() -> bool:
	return not _listening.is_empty()

## Binds the listening action; returns the message shown to the player.
func assign(event: InputEventKey) -> String:
	var action: String = _listening
	if action.is_empty() or settings == null:
		return ""
	var result: Dictionary = settings.bind(action, event)
	if not bool(result.get("ok", false)):
		_message.text = str(result.get("message", ""))
		return _message.text
	_listening = ""
	var other: String = str(result.get("swapped", ""))
	var now: String = "%s is now %s." % [action_label(action), keys_for([action])]
	if other.is_empty():
		_message.text = now
	elif keys_for([other]).is_empty():
		_message.text = "%s %s has no key now." % [now, action_label(other)]
	else:
		_message.text = "%s %s moved to %s." % [now, action_label(other), keys_for([other])]
	refresh()
	bindings_changed.emit()
	return _message.text

func reset_all() -> void:
	stop_listening()
	if settings != null:
		settings.reset_bindings()
	_message.text = "Every key is back to its default."
	refresh()
	bindings_changed.emit()

func _input(event: InputEvent) -> void:
	if not is_listening() or not is_visible_in_tree():
		return
	if event is InputEventMouseButton and event.pressed:
		stop_listening()
		return
	if not event is InputEventKey or event.echo:
		return
	get_viewport().set_input_as_handled()
	var modifier: bool = event.physical_keycode in [KEY_SHIFT, KEY_CTRL, KEY_ALT, KEY_META]
	if not event.pressed:
		# A modifier pressed and released alone binds as its own key.
		if modifier and event.physical_keycode == _held_modifier:
			assign(event)
		return
	_held_modifier = event.physical_keycode if modifier else KEY_NONE
	if event.physical_keycode == KEY_ESCAPE:
		stop_listening()
	elif not modifier:
		assign(event)

static func bindings_text() -> String:
	var lines: PackedStringArray = PackedStringArray(["Controls (" + keys_for(["help"]) + ")",
		"Gamepad layers: LB, RB, or LB+RB with the listed button."])
	for group: Dictionary in CONTROL_GROUPS:
		lines.append("")
		lines.append(str(group["title"]).to_upper())
		for row: Dictionary in group["rows"]:
			var keys: String = str(row.get("keys", keys_for(row.get("actions", []))))
			var line: String = keys + "  " + str(row["label"])
			var pad: String = _pad_for(row.get("actions", []))
			if not pad.is_empty():
				line += "  (pad " + pad + ")"
			lines.append(line)
	return "\n".join(lines)

static func keys_for(actions: Array) -> String:
	var keys: PackedStringArray = PackedStringArray()
	for action: String in actions:
		if not InputMap.has_action(action):
			continue
		for event: InputEvent in InputMap.action_get_events(action):
			if event is InputEventKey:
				keys.append(key_text(event))
	return "/".join(keys)

static func key_text(event: InputEventKey) -> String:
	var text: String = event.as_text().replace(" (Physical)", "")
	var parts: PackedStringArray = text.split("+")
	parts[-1] = KEY_GLYPHS.get(parts[-1], parts[-1])
	return "+".join(parts)

static func _pad_for(actions: Array) -> String:
	var pads: PackedStringArray = PackedStringArray()
	for action: String in actions:
		if not InputMap.has_action(action):
			continue
		var layer: int = int(PAD_LAYERS.get(action, 0))
		var prefix: String = {1: "LB+", 2: "RB+", 3: "LB+RB+"}.get(layer, "")
		for event: InputEvent in InputMap.action_get_events(action):
			if event is InputEventJoypadButton:
				var text: String = event.as_text()
				var open: int = text.find("(")
				var close: int = text.rfind(")")
				if open >= 0 and close > open:
					text = text.substr(open + 1, close - open - 1).split(",")[0].strip_edges()
				pads.append(prefix + text)
	return ", ".join(pads)
