class_name YellowstoneDataWatcher
extends Node

signal applied(path: String)
var interval_seconds: float = 1.0
var _elapsed: float = 0.0
var _entries: Dictionary = {}
var _pending: Array[String] = []

func watch(path: String, reader: Callable) -> void:
	_entries[path] = {"reader": reader, "signature": _signature(path)}

func _signature(path: String) -> int:
	if not FileAccess.file_exists(path):
		return -1
	return hash(FileAccess.get_file_as_bytes(path))

func _process(delta: float) -> void:
	var ready: Array[String] = _pending.duplicate()
	_pending.clear()
	for path: String in ready:
		var entry: Dictionary = _entries[path]
		entry.reader.call(path)
		applied.emit(path)
	_elapsed += delta
	if _elapsed < interval_seconds:
		return
	_elapsed = fmod(_elapsed, interval_seconds)
	for path: String in _entries:
		var signature: int = _signature(path)
		if signature != int(_entries[path].signature):
			_entries[path].signature = signature
			_pending.append(path)
