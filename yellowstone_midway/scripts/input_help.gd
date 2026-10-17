class_name YellowstoneInputHelp
extends PanelContainer

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

# Player-facing controls page; keys come from the InputMap and track remaps.
const CONTROL_GROUPS: Array = [
	{"title": "Walk", "rows": [
		{"label": "Walk", "actions": ["move_forward", "move_left", "move_back", "move_right"]},
		{"label": "Brisk walk", "actions": ["brisk_walk"]},
		{"label": "Hop", "actions": ["jump"]},
		{"label": "Fly down during authoring flight", "actions": ["fly_down"]},
	]},
	{"title": "Look", "rows": [
		{"label": "Look around", "keys": "Mouse"},
		{"label": "Return to the starting view", "actions": ["return_to_anchor"]},
		{"label": "Release or recapture the cursor", "keys": "Esc"},
	]},
	{"title": "Panels", "rows": [
		{"label": "Menu", "actions": ["menu"]},
		{"label": "Field notes", "actions": ["field_notes"]},
		{"label": "Map", "actions": ["map"]},
		{"label": "Conditions", "actions": ["conditions"]},
		{"label": "This page", "actions": ["help"]},
		{"label": "Calibration", "actions": ["calibration"]},
	]},
	{"title": "Simulation", "rows": [
		{"label": "Pause", "actions": ["pause"]},
		{"label": "Step one frame", "actions": ["step_frame"]},
		{"label": "Jump two hours", "actions": ["jump_two_hours"]},
		{"label": "Compare replay against live", "actions": ["compare_replay"]},
		{"label": "Time scale 1x, 60x, 600x, 3600x", "actions": ["scale_1", "scale_60", "scale_600", "scale_3600"]},
		{"label": "Interventions (live Python session)", "actions": ["intervene_shade", "intervene_outflow", "intervene_tributary", "intervene_grazing"]},
		{"label": "Study mode", "actions": ["study_scene"]},
	]},
	{"title": "Photo & debug", "rows": [
		{"label": "HUD cycle", "actions": ["photo_mode"]},
		{"label": "Authoring flight", "actions": ["authoring_flight"]},
		{"label": "Thermal probe", "actions": ["probe"]},
		{"label": "Plume overlay", "actions": ["plume"]},
		{"label": "Geochemistry overlay", "actions": ["geochemistry"]},
		{"label": "Overland overlay", "actions": ["overland"]},
		{"label": "Groundwater overlay", "actions": ["groundwater"]},
		{"label": "Census circles on the map", "actions": ["census"]},
	]},
]

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
	custom_minimum_size = Vector2(620, 630)
	# Dock to the right window edge; the field-notes notebook owns the left.
	anchor_left = 1.0
	anchor_right = 1.0
	offset_left = -654.0
	offset_right = -34.0
	offset_top = 140.0
	offset_bottom = 140.0
	var scroll: ScrollContainer = ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(600, 600)
	add_child(scroll)
	var text: Label = Label.new()
	text.text = bindings_text()
	scroll.add_child(text)
	visible = false

static func bindings_text() -> String:
	var lines: PackedStringArray = PackedStringArray(["Controls (" + _keys_for(["help"]) + ")",
		"Gamepad layers: LB, RB, or LB+RB with the listed button."])
	for group: Dictionary in CONTROL_GROUPS:
		lines.append("")
		lines.append(str(group["title"]).to_upper())
		for row: Dictionary in group["rows"]:
			var keys: String = str(row.get("keys", _keys_for(row.get("actions", []))))
			var line: String = keys + "  " + str(row["label"])
			var pad: String = _pad_for(row.get("actions", []))
			if not pad.is_empty():
				line += "  (pad " + pad + ")"
			lines.append(line)
	return "\n".join(lines)

static func _keys_for(actions: Array) -> String:
	var keys: PackedStringArray = PackedStringArray()
	for action: String in actions:
		if not InputMap.has_action(action):
			continue
		for event: InputEvent in InputMap.action_get_events(action):
			if event is InputEventKey:
				keys.append(event.as_text().replace(" (Physical)", ""))
	return "/".join(keys)

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
