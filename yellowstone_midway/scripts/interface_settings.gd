class_name YellowstoneInterfaceSettings
extends RefCounted

## Player interface preferences and key bindings stored in a user config file.
const InputHelp = preload("res://scripts/input_help.gd")
const SECTION: String = "interface"
const BINDINGS: String = "bindings"
# Escape frees the cursor and cancels rebinding; F4 opens diagnostics.
const RESERVED: Array[Key] = [KEY_ESCAPE, KEY_F4, KEY_CAPSLOCK]

var path: String = "user://interface_settings.cfg"
var shortcut_bar: bool = false
var key_panel_toggle: bool = false
# Project keyboard events per action before player overrides.
var _defaults: Dictionary = {}
var _overrides: Dictionary = {}

func load_settings() -> void:
	_capture_defaults()
	var config := ConfigFile.new()
	if config.load(path) != OK:
		return
	shortcut_bar = bool(config.get_value(SECTION, "shortcut_bar", shortcut_bar))
	key_panel_toggle = bool(config.get_value(SECTION, "key_panel_toggle", key_panel_toggle))
	if not config.has_section(BINDINGS):
		return
	for action: String in config.get_section_keys(BINDINGS):
		var stored: Variant = config.get_value(BINDINGS, action)
		if InputMap.has_action(action) and stored is Dictionary:
			_overrides[action] = stored
	_apply_overrides()

func save_settings() -> Error:
	var config := ConfigFile.new()
	config.set_value(SECTION, "shortcut_bar", shortcut_bar)
	config.set_value(SECTION, "key_panel_toggle", key_panel_toggle)
	for action: String in _overrides:
		config.set_value(BINDINGS, action, _overrides[action])
	return config.save(path)

## Assigns a key to an action; a key held by another action trades places with it.
func bind(action: String, event: InputEventKey) -> Dictionary:
	var record: Dictionary = _record(event)
	if record.key == KEY_NONE or record.key in RESERVED:
		return {"ok": false, "message": "%s is reserved." % InputHelp.key_text(_key_event(record))}
	var previous: Dictionary = _current(action)
	var other: String = holder(record, action)
	if not other.is_empty():
		_set_key(other, previous)
	_set_key(action, record)
	var err: Error = save_settings()
	var result: Dictionary = {"ok": true, "swapped": other}
	if err != OK:
		result["message"] = "The new key works now but could not be saved (error %d)." % err
	return result

## Returns the action other than skip whose key matches record exactly.
func holder(record: Dictionary, skip: String = "") -> String:
	for action: StringName in InputMap.get_actions():
		if str(action) == skip or str(action).begins_with("ui_"):
			continue
		if _current(str(action)) == record and not record.is_empty():
			return str(action)
	return ""

func reset_bindings() -> void:
	for action: String in _overrides.keys():
		_set_key(action, _defaults.get(action, {}))
	_overrides.clear()
	save_settings()

func _capture_defaults() -> void:
	if not _defaults.is_empty():
		return
	for action: StringName in InputMap.get_actions():
		if not str(action).begins_with("ui_"):
			_defaults[str(action)] = _current(str(action))

func _apply_overrides() -> void:
	for action: String in _overrides:
		_replace_key_events(action, _overrides[action])

func _set_key(action: String, record: Dictionary) -> void:
	_replace_key_events(action, record)
	if record == _defaults.get(action, {}):
		_overrides.erase(action)
	else:
		_overrides[action] = record

func _replace_key_events(action: String, record: Dictionary) -> void:
	for existing: InputEvent in InputMap.action_get_events(action):
		if existing is InputEventKey:
			InputMap.action_erase_event(action, existing)
	if not record.is_empty():
		InputMap.action_add_event(action, _key_event(record))

func _current(action: String) -> Dictionary:
	if not InputMap.has_action(action):
		return {}
	for event: InputEvent in InputMap.action_get_events(action):
		if event is InputEventKey:
			return _record(event)
	return {}

static func _record(event: InputEventKey) -> Dictionary:
	var key: Key = event.physical_keycode if event.physical_keycode != KEY_NONE else event.keycode
	# A modifier bound alone carries no modifier flags.
	return {"key": int(key), "ctrl": event.ctrl_pressed and key != KEY_CTRL,
		"alt": event.alt_pressed and key != KEY_ALT, "shift": event.shift_pressed and key != KEY_SHIFT,
		"meta": event.meta_pressed and key != KEY_META}

static func _key_event(record: Dictionary) -> InputEventKey:
	var event := InputEventKey.new()
	event.physical_keycode = int(record.get("key", 0)) as Key
	event.ctrl_pressed = bool(record.get("ctrl", false))
	event.alt_pressed = bool(record.get("alt", false))
	event.shift_pressed = bool(record.get("shift", false))
	event.meta_pressed = bool(record.get("meta", false))
	return event
