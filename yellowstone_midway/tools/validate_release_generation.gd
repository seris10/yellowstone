extends SceneTree
const ReleaseData = preload("res://scripts/release_data.gd")
const Replay = preload("res://scripts/python_river_replay.gd")

func _initialize() -> void:
	var pointer: String = "res://data/release.json"
	var refused: bool = false
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--pointer="):
			pointer = argument.trim_prefix("--pointer=")
		if argument == "--expect-refused":
			refused = true
	var generation: Dictionary = ReleaseData.prepare(pointer)
	if generation.is_empty():
		print("RELEASE_VALIDATION refused")
		quit(0 if refused else 1)
		return
	var reader: Node = Replay.new()
	reader.replay_path = str(generation.root).path_join("data/river_replay.json")
	reader.world_path = str(generation.root).path_join("data/world.json")
	var valid: bool = reader.configure(generation.parsed["data/ecosystem.json"])
	if valid:
		ReleaseData.activate(generation)
		var expected: float = float(generation.parsed["data/river_replay.json"].get("replay", generation.parsed["data/river_replay.json"]).frames[0].temperature_c[0])
		valid = absf(float(reader.river_state_at_s(0.0).temperature_c) - expected) < 0.000001
		for path: String in generation.manifest.artifacts:
			if generation.manifest.artifacts[path].get("state") == "unavailable":
				valid = valid and not ReleaseData.file_exists("res://" + path)
	reader.free()
	print("RELEASE_VALIDATION ", "PASS" if valid else "refused")
	quit(0 if valid != refused else 1)
