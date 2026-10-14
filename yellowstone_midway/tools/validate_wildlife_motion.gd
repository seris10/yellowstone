extends SceneTree
## Wildlife asset playback and route contracts.

class FlatTerrain:
	extends RefCounted
	func sample(_x: float, _z: float) -> float:
		return 0.0

class TestEcology:
	extends Node
	var elapsed: float = 0.0
	var paused: bool = false
	var clock_held: bool = false
	var active: bool = true
	var world_data: Dictionary = {"pools": []}
	func patch(_id: String) -> Dictionary:
		return {"biomass": 1.0}
	func mammal_state(_id: String, _kind: String, _position: Vector3) -> Dictionary:
		return {"active": active, "activity_index": 0.8, "speed_multiplier": 1.0, "behavior": "walk"}
	func set_grazer_activity(_id: String, _patch: String, _active: bool, _rate: float) -> void:
		pass
	func unregister_actor(_id: String) -> void:
		pass

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/wildlife_motion_assets.json"))
	assert(manifest is Dictionary)
	assert(manifest.schema == "yellowstone.wildlife_motion_assets.v1")
	var rows: Array = []
	for entry: Dictionary in manifest.assets:
		var packed: PackedScene = load("res://" + str(entry.path))
		assert(packed != null)
		var scene: Node3D = packed.instantiate()
		root.add_child(scene)
		await process_frame
		var players: Array[Node] = scene.find_children("*", "AnimationPlayer", true, false)
		var skeletons: Array[Node] = scene.find_children("*", "Skeleton3D", true, false)
		var clips: Array = []
		if not players.is_empty():
			assert(skeletons.size() == 1)
			var player: AnimationPlayer = players[0]
			var skeleton: Skeleton3D = skeletons[0]
			player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
			for name: StringName in player.get_animation_list():
				if name == &"RESET":
					continue
				var animation: Animation = player.get_animation(name)
				var first: Array[Transform3D] = []
				var motion: float = 0.0
				for phase: float in [0.0, 0.125, 0.25, 0.375, 0.5, 0.75, 1.0]:
					player.play(name)
					player.seek(animation.length * phase, true)
					player.advance(0.0)
					for bone: int in range(skeleton.get_bone_count()):
						var pose: Transform3D = skeleton.get_bone_global_pose(bone)
						assert(pose.is_finite())
						if phase == 0.0:
							first.append(pose)
						else:
							motion = maxf(motion, pose.origin.distance_to(first[bone].origin))
				clips.append({"name": str(name), "duration_s": animation.length, "finite": true, "joint_motion_asset_units": motion})
		rows.append({"id": entry.id, "clips": clips})
		scene.free()
	var ecology: TestEcology = TestEcology.new()
	root.add_child(ecology)
	var actor_checks: Array = []
	for kind: String in ["bison", "elk", "bobcat", "grizzly", "badger", "wolf", "deer", "black_bear", "canada_lynx"]:
		ecology.elapsed = 0.0
		ecology.active = true
		ecology.paused = false
		var actor: MidwayWildlifeActor = load("res://scripts/wildlife_actor.gd").new()
		actor.setup({"id": "check_"+kind, "kind": kind, "mammal_guild": "omnivore", "medium": "land", "patch_id": "qa", "path_xz": [[0, 0], [10, 0]], "approx_dimensions_m": {"length": 1.5}, "walk_mps": 0.5, "initial_state": "walk"}, FlatTerrain.new(), ecology)
		root.add_child(actor)
		actor.set_process(false)
		await process_frame
		var start: Vector3 = actor.get("_world_position")
		ecology.elapsed = 1.0
		actor.call("_process", 1.0)
		var endpoint: Vector3 = actor.get("_world_position")
		assert(is_equal_approx(endpoint.x - start.x, 0.5))
		var controller: MidwayWildlifeMotionController = actor.get("_motion")
		assert(controller != null or kind == "elk")
		if controller != null:
			assert(controller.last_clip != "Idle")
			ecology.elapsed = 1.5
			actor.call("_process", 0.5)
			assert(controller.last_rate > 0.0)
		ecology.paused = true
		var paused_position: Vector3 = actor.get("_world_position")
		actor.call("_process", 1.0)
		assert(actor.get("_world_position") == paused_position)
		ecology.paused = false
		ecology.active = false
		actor.call("_process", 1.0)
		assert(not actor.visible)
		actor_checks.append({"kind": kind, "travel_m": 0.5, "paused": true, "inactive_hidden": true, "animation": controller.last_clip if controller != null else "articulated_shape_proxy"})
		actor.free()
	var route_actor: MidwayWildlifeActor = load("res://scripts/wildlife_actor.gd").new()
	var pool: Dictionary = {"pools": [{"thermal": true, "ring": [[-1, -1], [1, -1], [1, 1], [-1, 1]]}]}
	assert(route_actor.call("_crosses_thermal_pool", Vector3(-2, 0, 0), Vector3(2, 0, 0), pool))
	assert(not route_actor.call("_crosses_thermal_pool", Vector3(-2, 0, 2), Vector3(2, 0, 2), pool))
	route_actor.free()
	var report: Dictionary = {"schema": "yellowstone.wildlife_native_checks.v1", "engine": Engine.get_version_info(), "assets": rows, "actors": actor_checks, "pool_segment_checks": 2, "status": "automated_runtime_checks", "scientific_acceptance": "not_yet_accepted"}
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--report="):
			var file: FileAccess = FileAccess.open(argument.trim_prefix("--report="), FileAccess.WRITE)
			file.store_string(JSON.stringify(report, "  "))
	ecology.free()
	print("WILDLIFE_MOTION_PASS assets=", rows.size(), " actors=", actor_checks.size())
	quit()
