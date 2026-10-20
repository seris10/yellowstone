class_name YellowstoneKeyPanel
extends PanelContainer

## Compact shortcut popover docked to the lower-left corner.
const InputHelp = preload("res://scripts/input_help.gd")
const UiTheme = preload("res://scripts/ui_theme.gd")
const ACTION: String = "key_panel"
# Rows with "requires" appear only when that sidecar published data.
const ROWS: Array = [
	{"label": "Walk", "actions": ["move_forward", "move_left", "move_back", "move_right"]},
	{"label": "Look", "keys": "Mouse"},
	{"label": "Brisk walk", "actions": ["brisk_walk"]},
	{"label": "Hop", "actions": ["jump"]},
	{"label": "Map", "actions": ["map"]},
	{"label": "Field notes", "actions": ["field_notes"]},
	{"label": "Conditions", "actions": ["conditions"]},
	{"label": "Time and weather", "actions": ["time_weather"]},
	{"label": "River probe", "actions": ["probe"]},
	{"label": "Pause", "actions": ["pause"]},
	{"label": "Step one frame", "actions": ["step_frame"]},
	{"label": "Jump two hours", "actions": ["jump_two_hours"]},
	{"label": "Back to start", "actions": ["return_to_anchor"]},
	{"label": "Cycle the HUD", "actions": ["photo_mode"]},
	{"label": "Study mode", "actions": ["study_scene"]},
	{"label": "Calibration", "actions": ["calibration"], "requires": "calibration"},
	{"label": "Plume overlay", "actions": ["plume"], "requires": "plume"},
	{"label": "Geochemistry overlay", "actions": ["geochemistry"], "requires": "geochemistry"},
	{"label": "Census (map open)", "actions": ["census"], "requires": "census"},
	{"label": "Overland overlay", "actions": ["overland"], "requires": "overland"},
	{"label": "Groundwater overlay", "actions": ["groundwater"], "requires": "groundwater"},
	{"label": "Menu", "actions": ["menu"]},
	{"label": "All controls", "actions": ["help"]},
]

## False: visible while the key is held. True: each press shows or hides.
var toggle_mode: bool = false
var _grid: GridContainer

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	anchor_left = 0.0
	anchor_right = 0.0
	anchor_top = 1.0
	anchor_bottom = 1.0
	offset_left = 34.0
	offset_right = 34.0
	offset_top = -34.0
	offset_bottom = -34.0
	grow_vertical = Control.GROW_DIRECTION_BEGIN
	theme = UiTheme.theme()
	add_theme_stylebox_override("panel", UiTheme.sign_box(20, 16))
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	add_child(box)
	box.add_child(UiTheme.heading("Shortcuts", 12))
	_grid = GridContainer.new()
	_grid.columns = 4
	# Cell padding carries the spacing so each row band stays unbroken.
	_grid.add_theme_constant_override("h_separation", 0)
	_grid.add_theme_constant_override("v_separation", 0)
	box.add_child(_grid)
	visible = false

func refresh(available: Dictionary) -> void:
	for child: Node in _grid.get_children():
		_grid.remove_child(child)
		child.queue_free()
	var shown: int = 0
	for row: Dictionary in ROWS:
		if row.has("requires") and not bool(available.get(row["requires"], false)):
			continue
		var keys: String = str(row.get("keys", InputHelp.keys_for(row.get("actions", []))))
		if keys.is_empty():
			continue
		var key := _label(keys, 15, UiTheme.FOREST)
		key.add_theme_font_override("font", UiTheme.font(700))
		_grid.add_child(_cell(key, shown / 2, 10, 12))
		_grid.add_child(_cell(_label(str(row["label"]), 15, UiTheme.INK), shown / 2, 0, 16))
		shown += 1

func row_count() -> int:
	return _grid.get_child_count() / 2

## Consumes the panel key; returns true when the event was the panel key.
func handle(event: InputEvent) -> bool:
	# The pad button belongs to the panel only without a shoulder layer held.
	if event is InputEventJoypadButton and (Input.is_joy_button_pressed(event.device, JOY_BUTTON_LEFT_SHOULDER)
			or Input.is_joy_button_pressed(event.device, JOY_BUTTON_RIGHT_SHOULDER)):
		return false
	if event.is_action_pressed(ACTION):
		visible = (not visible) if toggle_mode else true
		return true
	if event.is_action_released(ACTION):
		if not toggle_mode:
			visible = false
		return true
	return event.is_action(ACTION)

func _process(_delta: float) -> void:
	# Hide the held panel once its key is up, including after a focus change.
	if visible and not toggle_mode and not Input.is_action_pressed(ACTION):
		visible = false

## One grid cell carried on its row band.
func _cell(label: Label, row: int, margin_left: int, margin_right: int) -> PanelContainer:
	var band := PanelContainer.new()
	var style: StyleBox = UiTheme.row_tint(row, 0, 3)
	style.content_margin_left = margin_left
	style.content_margin_right = margin_right
	band.add_theme_stylebox_override("panel", style)
	band.add_child(label)
	return band

func _label(text: String, size: int, color: Color) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	return label
