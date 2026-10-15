extends SceneTree

const World = preload("res://scripts/world.gd")
const Replay = preload("res://scripts/python_river_replay.gd")
const ReleaseData = preload("res://scripts/release_data.gd")
const TerrainMaterials = preload("res://scripts/terrain_materials.gd")

func _initialize() -> void:
	var pointers: Dictionary = {}
	for argument: String in OS.get_cmdline_user_args():
		for name: String in ["a", "b", "bad"]:
			if argument.begins_with("--" + name + "="):
				pointers[name] = argument.trim_prefix("--" + name + "=")
	if pointers.size() != 3:
		quit(1)
		return
	var world: Node3D = World.new()
	world.ecosystem = Replay.new()
	var valid: bool = world._reload_generation(pointers.a)
	valid = valid and not world._overland_summary.is_empty()
	var image: Image = TerrainMaterials._load_image("res://assets/textures/pool_ramps/ramp.png")
	valid = valid and image != null and image.get_size() == Vector2i.ONE
	valid = valid and world._reload_generation(pointers.b)
	valid = valid and world._overland_summary.is_empty()
	valid = valid and TerrainMaterials._load_image("res://assets/textures/pool_ramps/ramp.png") == null
	valid = valid and world._simulation_start_epoch_unix == 1782151200.0
	valid = valid and "unavailable in this generation" in world.format_sidecar_block()
	valid = valid and "frozen" in world.format_sidecar_block()
	var identity: String = str(ReleaseData.active.manifest.release_id)
	var frames: Array = world.ecosystem._frames.duplicate(true)
	valid = valid and not world._reload_generation(pointers.bad)
	valid = valid and str(ReleaseData.active.manifest.release_id) == identity
	valid = valid and world.ecosystem._frames == frames
	world.ecosystem.free()
	world.free()
	ReleaseData.active = {}
	var restart: Dictionary = ReleaseData.prepare(pointers.b)
	valid = valid and str(restart.manifest.release_id) == identity
	print("RELEASE_RELOAD ", "PASS" if valid else "FAIL")
	quit(0 if valid else 1)
