extends SceneTree

func _initialize() -> void:
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/consumers.json"))
	var failures: PackedStringArray = PackedStringArray()
	if not manifest is Dictionary or not manifest.get("consumers") is Dictionary:
		push_error("Consumer manifest requires a consumers object")
		quit(1)
		return
	for path: String in manifest.consumers:
		var found: bool = false
		for script: String in manifest.consumers[path]:
			if FileAccess.file_exists("res://" + script):
				var source: String = FileAccess.get_file_as_string("res://" + script)
				found = found or source.contains(path.get_file())
		if not found:
			failures.append(path + " has no named script consumer")
	print("CONSUMERS_VALIDATION ", "PASS" if failures.is_empty() else "FAIL", " count=", manifest.consumers.size(), " failures=", failures)
	quit(0 if failures.is_empty() else 1)
