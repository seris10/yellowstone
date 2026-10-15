class_name YellowstoneInputHelp
extends PanelContainer

const PAD_LAYERS: Dictionary = {
	"field_notes": 1, "map": 1, "photo_mode": 1, "authoring_flight": 1,
	"return_to_anchor": 1, "jump_two_hours": 1, "compare_replay": 1,
	"calibration": 2, "plume": 2, "geochemistry": 2, "census": 2,
	"overland": 2, "groundwater": 2, "study_scene": 2,
	"scale_1": 3, "scale_60": 3, "scale_600": 3, "scale_3600": 3,
	"intervene_shade": 3, "intervene_outflow": 3, "intervene_tributary": 3,
	"intervene_grazing": 3,
}

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
	position = Vector2(34, 140)
	custom_minimum_size = Vector2(620, 630)
	var scroll: ScrollContainer = ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(600, 600)
	add_child(scroll)
	var text: Label = Label.new()
	text.text = bindings_text()
	scroll.add_child(text)
	visible = false

static func bindings_text() -> String:
	var lines: PackedStringArray = PackedStringArray(["Controls (F1)", "Gamepad layers: LB, RB, or LB+RB with the listed button."])
	for action: StringName in InputMap.get_actions():
		if str(action).begins_with("ui_"):
			continue
		var bindings: PackedStringArray = PackedStringArray()
		for event: InputEvent in InputMap.action_get_events(action):
			bindings.append(event.as_text())
		var layer: int = int(PAD_LAYERS.get(str(action), 0))
		var prefix: String = " | pad layer " + str(layer) if layer > 0 else ""
		lines.append("%s: %s%s" % [str(action).capitalize(), ", ".join(bindings), prefix])
	return "\n".join(lines)
