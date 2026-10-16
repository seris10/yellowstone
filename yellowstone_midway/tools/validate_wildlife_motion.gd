extends SceneTree
## Wildlife asset playback and route contracts.

var capture_dir: String = ""
var capture_camera: Camera3D
var capture_floor: MeshInstance3D
var captures: Array = []

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
	var speed: float = 1.0
	var behavior: String = "walk"
	var world_data: Dictionary = {"pools": []}
	func patch(_id: String) -> Dictionary:
		return {"biomass": 1.0}
	func mammal_state(_id: String, _kind: String, _position: Vector3) -> Dictionary:
		return {"active": active, "activity_index": 0.8, "speed_multiplier": speed, "behavior": behavior}
	func set_grazer_activity(_id: String, _patch: String, _active: bool, _rate: float) -> void:
		pass
	func unregister_actor(_id: String) -> void:
		pass

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--capture-out="):
			capture_dir = argument.trim_prefix("--capture-out=")
	if not capture_dir.is_empty():
		assert(DisplayServer.get_name() != "headless")
		DirAccess.make_dir_recursive_absolute(capture_dir)
		root.size = Vector2i(1200, 900)
		root.show()
		root.grab_focus()
		capture_camera = Camera3D.new()
		root.add_child(capture_camera)
		capture_camera.current = true
		var environment := WorldEnvironment.new()
		environment.environment = Environment.new()
		environment.environment.background_mode = Environment.BG_COLOR
		environment.environment.background_color = Color(0.18, 0.23, 0.26)
		environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		environment.environment.ambient_light_color = Color(0.8, 0.85, 0.9)
		environment.environment.ambient_light_energy = 0.7
		root.add_child(environment)
		var light := DirectionalLight3D.new()
		light.rotation_degrees = Vector3(-45, -35, 0)
		light.light_energy = 1.5
		root.add_child(light)
		capture_floor = MeshInstance3D.new()
		var plane := PlaneMesh.new()
		plane.size = Vector2(50, 50)
		var material := StandardMaterial3D.new()
		material.albedo_color = Color(0.32, 0.36, 0.28)
		plane.material = material
		capture_floor.mesh = plane
		root.add_child(capture_floor)
		create_timer(600).timeout.connect(func(): push_error("Wildlife captures timed out"); quit(1))
	if "--tree-capture" in OS.get_cmdline_user_args():
		await capture_tree_transitions()
		quit()
		return
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
					if not capture_dir.is_empty() and str(name).get_file() in ["Idle", "Walk"] and phase in [0.0, 0.25, 0.5, 0.75]:
						await capture_pose(scene, "%s_%s_%03d" % [entry.id, str(name).get_file(), int(phase*100)], 0.0)
				clips.append({"name": str(name), "duration_s": animation.length, "finite": true, "joint_motion_asset_units": motion})
		rows.append({"id": entry.id, "sha256": FileAccess.get_sha256("res://"+str(entry.path)), "clips": clips})
		scene.free()
	var ecology: TestEcology = TestEcology.new()
	root.add_child(ecology)
	var actor_checks: Array = []
	var actual_terrain: RefCounted = load("res://scripts/height_field.gd").new()
	for kind: String in ["bison", "elk", "bobcat", "grizzly", "badger", "wolf", "deer", "black_bear", "canada_lynx"]:
		ecology.elapsed = 0.0
		ecology.active = true
		ecology.paused = false
		ecology.speed = 1.0
		ecology.behavior = "walk"
		var actor: MidwayWildlifeActor = load("res://scripts/wildlife_actor.gd").new()
		actor.setup({"id": "check_"+kind, "kind": kind, "mammal_guild": "omnivore", "medium": "land", "patch_id": "qa", "path_xz": [[0, 0], [10, 0]], "approx_dimensions_m": {"length": 1.5}, "walk_mps": 0.5, "initial_state": "walk"}, actual_terrain if not capture_dir.is_empty() else FlatTerrain.new(), ecology)
		root.add_child(actor)
		actor.set_process(false)
		await process_frame
		var start: Vector3 = actor.get("_world_position")
		ecology.elapsed = 1.0
		actor.call("_process", 1.0)
		var endpoint: Vector3 = actor.get("_world_position")
		assert(is_equal_approx(endpoint.x - start.x, 0.5) if capture_dir.is_empty() else endpoint.distance_to(start) > 0.0)
		if not capture_dir.is_empty():
			await capture_pose(actor, kind+"_ground_walk", float(actual_terrain.sample(endpoint.x, endpoint.z)))
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
		if not capture_dir.is_empty():
			await capture_pose(actor, kind+"_paused", float(actual_terrain.sample(paused_position.x, paused_position.z)))
		ecology.paused = false
		if not capture_dir.is_empty():
			ecology.speed = 2.0
			ecology.elapsed = 2.0
			actor.call("_process", 0.5)
			var accelerated: Vector3 = actor.get("_world_position")
			await capture_pose(actor, kind+"_speed_change", float(actual_terrain.sample(accelerated.x, accelerated.z)))
			ecology.behavior = "rest"
			ecology.elapsed = 2.5
			actor.call("_process", 0.5)
			await capture_pose(actor, kind+"_walk_to_idle", float(actual_terrain.sample(accelerated.x, accelerated.z)))
			if controller != null:
				assert(controller.last_clip == "Idle")
			ecology.behavior = "walk"
			ecology.speed = 1.0
			ecology.elapsed = 30.5
			actor.call("_process", 1.0)
			var turned: Vector3 = actor.get("_world_position")
			await capture_pose(actor, kind+"_idle_to_walk_turn", float(actual_terrain.sample(turned.x, turned.z)))
		ecology.active = false
		actor.call("_process", 1.0)
		assert(not actor.visible)
		actor_checks.append({"kind": kind, "travel_xz_m": Vector2(endpoint.x-start.x, endpoint.z-start.z).length(), "paused": true, "inactive_hidden": true, "animation": controller.last_clip if controller != null else "articulated_shape_proxy"})
		actor.free()
	var route_actor: MidwayWildlifeActor = load("res://scripts/wildlife_actor.gd").new()
	var pool: Dictionary = {"pools": [{"thermal": true, "ring": [[-1, -1], [1, -1], [1, 1], [-1, 1]]}]}
	assert(route_actor.call("_crosses_thermal_pool", Vector3(-2, 0, 0), Vector3(2, 0, 0), pool))
	assert(not route_actor.call("_crosses_thermal_pool", Vector3(-2, 0, 2), Vector3(2, 0, 2), pool))
	route_actor.free()
	var report: Dictionary = {"schema": "yellowstone.wildlife_native_checks.v1", "engine": Engine.get_version_info(), "assets": rows, "actors": actor_checks, "captures": captures, "terrain_sha256": FileAccess.get_sha256("res://data/terrain.f32"), "pool_segment_checks": 2, "status": "automated_runtime_checks", "scientific_acceptance": "not_yet_accepted", "human_visual_acceptance": "unassessed"}
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--report="):
			var file: FileAccess = FileAccess.open(argument.trim_prefix("--report="), FileAccess.WRITE)
			file.store_string(JSON.stringify(report, "  "))
	ecology.free()
	print("WILDLIFE_MOTION_PASS assets=", rows.size(), " actors=", actor_checks.size())
	quit()

func capture_pose(model: Node3D, label: String, ground_y: float) -> void:
	var bounds := AABB()
	var first: bool = true
	for mesh: Node in model.find_children("*", "MeshInstance3D", true, false):
		var box: AABB = mesh.global_transform * mesh.get_aabb()
		bounds = box if first else bounds.merge(box)
		first = false
	assert(not first)
	var height: float = maxf(bounds.size.y, 0.1)
	var center: Vector3 = bounds.get_center()
	capture_camera.position = center + Vector3(height*1.8, height*0.5, height*2.3)
	capture_camera.near = maxf(0.001, height*0.001)
	capture_camera.far = maxf(1000.0, height*100.0)
	capture_camera.look_at(center, Vector3.UP)
	capture_floor.position = Vector3(center.x, ground_y, center.z)
	capture_floor.scale = Vector3.ONE*maxf(1.0, height)
	await process_frame
	await RenderingServer.frame_post_draw
	var image: Image = root.get_texture().get_image()
	assert(not image.is_empty())
	var path: String = capture_dir.path_join(label+".png")
	assert(image.save_png(path) == OK)
	captures.append({"label": label, "path": path.get_file(), "sha256": FileAccess.get_sha256(path),
		"sampled_ground_y_m_or_asset_units": ground_y, "rendered_bounds": str(bounds)})

func capture_tree_transitions() -> void:
	assert(not capture_dir.is_empty())
	var library = load("res://scripts/lodgepole_library.gd")
	root.transparent_bg = true
	capture_floor.visible = false
	var pairs: Array = []
	var budgets: Dictionary = {"18": {"silhouette_iou_min": 0.80, "occupancy_ratio_min": 0.85, "occupancy_ratio_max": 1.15},
		"65": {"silhouette_iou_min": 0.75, "occupancy_ratio_min": 0.85, "occupancy_ratio_max": 1.15},
		"180": {"silhouette_iou_min": 0.70, "occupancy_ratio_min": 0.80, "occupancy_ratio_max": 1.20}}
	for form: String in ["dense", "open", "sapling", "snag"]:
		var height: float = float(library.metadata().archetypes[form].height_m)
		for variant: int in [0, 3]:
			for angle: int in range(4):
				for boundary: int in range(3):
					var distance: float = [18.0, 65.0, 180.0][boundary]
					var names: Array = []
					for level: int in [boundary, boundary+1]:
						var model := Node3D.new()
						var assets: Array = [library.load_billboard(form, variant)] if level == 3 else library.load_architecture(form, variant, level)
						assert(not assets.is_empty())
						assert(library.bind_cutout_materials(assets, true))
						for part: Array in assets:
							var mesh := MeshInstance3D.new()
							mesh.mesh = part[0]
							mesh.transform = part[1]
							model.add_child(mesh)
						root.add_child(model)
						var center := Vector3(0, height*0.5, 0)
						var azimuth: float = angle*PI*0.5
						capture_camera.position = center+Vector3(sin(azimuth)*distance, 0, cos(azimuth)*distance)
						capture_camera.look_at(center, Vector3.UP)
						await process_frame
						await RenderingServer.frame_post_draw
						var pixels: Image = root.get_texture().get_image()
						assert(not pixels.is_empty() and pixels.get_pixel(0, 0).a < 0.01)
						var filename: String = "%s_v%d_a%d_d%d_lod%d.png" % [form, variant, angle, int(distance), level]
						assert(pixels.save_png(capture_dir.path_join(filename)) == OK)
						names.append({"path": filename, "sha256": FileAccess.get_sha256(capture_dir.path_join(filename))})
						model.free()
					pairs.append({"archetype": form, "variant": variant, "angle_degrees": angle*90,
						"distance_m": distance, "images": names})
	var report: Dictionary = {"schema": "yellowstone.tree_lod_capture.v1", "pairs": pairs, "predeclared_budgets": budgets,
		"scope": "actual bake cutout materials and mip buffers; fixed poses; runtime wind frozen; equal camera distance per pair",
		"source_metadata_sha256": FileAccess.get_sha256("res://assets/imported/lodgepole/lodgepole_metadata.json"),
		"source_graph_library_sha256": FileAccess.get_sha256("res://assets/imported/lodgepole/architecture_library.json"),
		"human_visual_acceptance": "unassessed", "biological_acceptance": "not_yet_accepted"}
	var output: FileAccess = FileAccess.open(capture_dir.path_join("tree-lod-captures.json"), FileAccess.WRITE)
	output.store_string(JSON.stringify(report, "  "))
	if "--slow-pass" in OS.get_cmdline_user_args():
		await capture_tree_pass(library)
	print("TREE_LOD_CAPTURE PASS pairs=", pairs.size())

func capture_tree_pass(library: Variant) -> void:
	var model := Node3D.new()
	root.add_child(model)
	for level: int in range(4):
		var assets: Array = [library.load_billboard("dense", 3)] if level == 3 else library.load_architecture("dense", 3, level)
		assert(library.bind_cutout_materials(assets, true))
		for part: Array in assets:
			var mesh := MeshInstance3D.new()
			mesh.mesh = part[0]
			mesh.transform = part[1]
			mesh.visibility_range_begin = float(part[2])
			mesh.visibility_range_end = float(part[3])
			model.add_child(mesh)
	for frame: int in range(240):
		var fraction: float = float(frame)/239.0
		var distance: float = lerpf(12.0, 210.0, fraction)
		var angle: float = fraction*PI*0.5
		var center := Vector3(0, 9, 0)
		capture_camera.position = center + Vector3(sin(angle)*distance, 0, cos(angle)*distance)
		capture_camera.look_at(center, Vector3.UP)
		await process_frame
		await RenderingServer.frame_post_draw
		var image: Image = root.get_texture().get_image()
		assert(image.save_png(capture_dir.path_join("pass_%04d.png" % frame)) == OK)
	model.free()
