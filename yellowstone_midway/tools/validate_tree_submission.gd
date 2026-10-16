extends SceneTree
## Native tree submission coverage, immutable buffers and raster equivalence.

const Submission = preload("res://scripts/tree_submission.gd")
var failures: Array[String] = []
var checks := 0
var output := "res://work/tree-submission"
var records: Array = []
var movement: Dictionary = {}
var control_diagnostics: Array[String] = []

func _initialize() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			output = argument.trim_prefix("--out=")
	call_deferred("run")

func check(condition: bool, detail: String) -> void:
	checks += 1
	if not condition and failures.size() < 100:
		failures.append(detail)

func inspect_selection(controller: Node, position: Vector3, stale_offset := Vector3.ZERO) -> void:
	var selected_total := 0
	for batch: RefCounted in controller.get("_batches"):
		var original: PackedFloat32Array = batch.original.buffer
		check(original == batch.source, "Source buffer remains immutable")
		check(batch.original != batch.compact and batch.original.mesh == batch.compact.mesh, "Runtime buffer is isolated and source mesh is retained")
		check(batch.original.instance_count == batch.compact.instance_count and batch.original.custom_aabb == batch.compact.custom_aabb, "Capacity and conservative bounds remain unchanged")
		var packed: PackedFloat32Array = batch.compact.buffer
		var count: int = batch.compact.visible_instance_count
		var identities: Dictionary = {}
		for slot: int in count:
			var identity := int(batch.selected[slot])
			identities[identity] = true
			check(packed.slice(slot * 20, (slot + 1) * 20) == original.slice(identity * 20, (identity + 1) * 20), "Selected record preserves all transform, color and custom floats")
		var material: ShaderMaterial = batch.original.mesh.surface_get_material(0)
		var begin := float(material.get_shader_parameter("lod_begin_m"))
		var end := float(material.get_shader_parameter("lod_end_m"))
		var lower := maxf(0, begin - clampf(begin * 0.1, 2, 18))
		var upper := end + clampf(end * 0.1, 2, 18)
		for index: int in batch.centers.size():
			var distance: float = (position + stale_offset).distance_to(batch.centers[index])
			if distance >= lower and distance <= upper:
				check(identities.has(index), "Every shader-surviving instance remains submitted")
		selected_total += count
	check(selected_total == int(controller.metrics().selected_instances), "Selection count agrees with visible prefixes")

func synthetic() -> Dictionary:
	var group := Node3D.new()
	root.add_child(group)
	for range_m: Vector2 in [Vector2(0, 18), Vector2(18, 65), Vector2(65, 180)]:
		var material := ShaderMaterial.new()
		material.shader = load("res://shaders/tree_bark.gdshader")
		material.set_shader_parameter("instance_lod", true)
		material.set_shader_parameter("lod_begin_m", range_m.x)
		material.set_shader_parameter("lod_end_m", range_m.y)
		var mesh := BoxMesh.new()
		mesh.material = material
		var multi := MultiMesh.new()
		multi.transform_format = MultiMesh.TRANSFORM_3D
		multi.use_colors = true
		multi.use_custom_data = true
		multi.mesh = mesh
		multi.instance_count = 256
		var buffer := PackedFloat32Array()
		for index: int in multi.instance_count:
			var center := Vector3(float(index) * 1.17 - 30.0, sin(float(index)) * 8.0, cos(float(index) * 0.3) * 15.0)
			var basis := Basis(Vector3.UP, float(index) * 0.13).scaled(Vector3(0.7, 1.2, 0.8))
			buffer.append_array(PackedFloat32Array([basis.x.x, basis.y.x, basis.z.x, center.x, basis.x.y, basis.y.y, basis.z.y, center.y, basis.x.z, basis.y.z, basis.z.z, center.z, float(index % 4) / 3, 0.4, 0.9, 1, center.x, center.y, center.z, 1]))
		multi.buffer = buffer
		var node := MultiMeshInstance3D.new()
		node.multimesh = multi
		node.set_meta("instance_lod", true)
		node.set_meta("lod_begin_m", range_m.x)
		group.add_child(node)
	var controller := Submission.new()
	group.add_child(controller)
	controller.configure(group)
	check(controller.get("_batches").size() == 3, "Synthetic fixture configures three batches")
	for position: Vector3 in [Vector3.ZERO, Vector3(18, 3, 0), Vector3(65, -4, 0), Vector3(180, 0, 0), Vector3(10000, 100, 10000), Vector3.ZERO]:
		controller.refresh(position, true)
		inspect_selection(controller, position)
		inspect_selection(controller, position, Vector3(0.6, 0.2, -0.7))
		var updates := int(controller.metrics().updates)
		controller.refresh(position + Vector3(0.6, 0.2, -0.7))
		check(int(controller.metrics().updates) == updates, "Sub-meter motion retains guarded selection")
		controller.refresh(position + Vector3(1.01, 0, 0))
		check(int(controller.metrics().updates) == updates + 1, "Larger movement refreshes selection")
		controller.refresh(position + Vector3(1.01, 0, 0), true)
		check(int(controller.metrics().changed_slots) == 0, "Unchanged selection performs no prefix writes")
	controller.set_enabled(false)
	for batch: RefCounted in controller.get("_batches"):
		check(batch.node.multimesh == batch.original, "Disabled submission restores original resource")
	controller.set_enabled(true)
	controller.refresh(Vector3.ZERO, true)
	inspect_selection(controller, Vector3.ZERO)
	var result := controller.metrics()
	group.free()
	return result

func freeze(node: Node) -> void:
	node.set_process(false)
	node.set_physics_process(false)
	if node is AnimationPlayer:
		node.pause()
	if node is GPUParticles3D or node is CPUParticles3D:
		node.speed_scale = 0.0
	for child: Node in node.get_children():
		freeze(child)

func capture() -> Dictionary:
	for frame: int in 8:
		await process_frame
	await RenderingServer.frame_post_draw
	return {"image": root.get_texture().get_image(), "primitives": Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME), "draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)}

func compare_images(a: Image, b: Image) -> Dictionary:
	var bytes_a := a.get_data()
	var bytes_b := b.get_data()
	var changed := 0
	var maximum := 0
	var total := 0
	for index: int in bytes_a.size():
		var difference := absi(int(bytes_a[index]) - int(bytes_b[index]))
		if difference > 0:
			changed += 1
		maximum = maxi(maximum, difference)
		total += difference
	return {"changed_channels": changed, "maximum_byte_difference": maximum, "absolute_byte_difference": total, "total_channels": bytes_a.size()}

func run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	if DisplayServer.get_name() == "headless":
		push_error("Tree submission verification requires native MultiMesh buffer storage")
		quit(2)
		return
	var synthetic_result := synthetic()
	if "--synthetic" not in OS.get_cmdline_user_args():
		if DisplayServer.get_name() == "headless":
			check(false, "Raster comparison requires a native renderer")
		else:
			await native_world()
	var report := {"ok": failures.is_empty(), "checks": checks, "failures": failures, "control_diagnostics": control_diagnostics, "exact_control_repeatability": control_diagnostics.is_empty(), "synthetic": synthetic_result, "native": records, "movement": movement, "scope": "Frozen forcing, particles and shader TIME=0; exact original-to-compact comparisons are gating; repeat and restored-original controls are reported independently", "renderer": RenderingServer.get_current_rendering_method(), "source_sha256": FileAccess.get_sha256("res://scripts/tree_submission.gd"), "world_sha256": FileAccess.get_sha256("res://scripts/world.gd"), "validator_sha256": FileAccess.get_sha256("res://tools/validate_tree_submission.gd"), "scene_sha256": FileAccess.get_sha256("res://scenes/authored_world.tscn")}
	FileAccess.open(output.path_join("report.json"), FileAccess.WRITE).store_string(JSON.stringify(report, "\t") + "\n")
	print("TREE_SUBMISSION ", JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)

func native_world() -> void:
	ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:1")
	root.size = Vector2i(1440, 900)
	root.show()
	var world: Node3D = load("res://scenes/main.tscn").instantiate()
	root.add_child(world)
	current_scene = world
	for frame: int in 12:
		await process_frame
	freeze(world)
	for shader_name: String in ["foliage", "forest_floor_foliage", "water", "steam"]:
		var shader: Shader = load("res://shaders/%s.gdshader" % shader_name)
		shader.code = shader.code.replace("TIME", "0.0")
	world.overlay.hide()
	world.player.enabled = false
	for material: ShaderMaterial in world.foliage_materials:
		material.set_shader_parameter("wind_vector", Vector2.ZERO)
	var controller: Node = world.get_node("TreeSubmission")
	var camera := Camera3D.new()
	world.add_child(camera)
	camera.fov = 72
	camera.near = 0.08
	camera.far = 2900
	camera.make_current()
	var cases := [
		{"id": "overlook", "position": Vector3(-242, 52, 160), "target": Vector3(-213, 30, 125)},
		{"id": "forest", "position": Vector3(-242, 44, 146), "target": Vector3(-230, 39, 125)},
		{"id": "boundary", "position": Vector3(-214, 51, 173), "target": Vector3(-230, 36, 142)}]
	for view: Dictionary in cases:
		camera.position = view.position
		camera.look_at(view.target)
		controller.set_enabled(false)
		var original := await capture()
		var stable := await capture()
		controller.set_enabled(true)
		var compact := await capture()
		var noise := compare_images(original.image, stable.image)
		var difference := compare_images(stable.image, compact.image)
		controller.set_enabled(false)
		var restored := await capture()
		var original_buffers_verified := 0
		for batch: RefCounted in controller.get("_batches"):
			check(batch.node.multimesh == batch.original and batch.original.buffer == batch.source, "Restored original resource retains its complete immutable buffer")
			original_buffers_verified += 1
		controller.set_enabled(true)
		var repeated := await capture()
		var restoration_difference := compare_images(stable.image, restored.image)
		var repeat_difference := compare_images(compact.image, repeated.image)
		original.image.save_png(output.path_join(str(view.id) + "-original.png"))
		compact.image.save_png(output.path_join(str(view.id) + "-compact.png"))
		restored.image.save_png(output.path_join(str(view.id) + "-restored.png"))
		if int(noise.changed_channels) != 0:
			control_diagnostics.append("Repeated original raster differs: " + str(view.id))
		check(int(difference.changed_channels) == 0, "Compaction preserves native color and shadows: " + str(view.id))
		if int(restoration_difference.changed_channels) != 0:
			control_diagnostics.append("Restored original raster differs with identical source buffers: " + str(view.id))
		if int(repeat_difference.changed_channels) != 0:
			control_diagnostics.append("Repeated compact raster differs: " + str(view.id))
		check(float(compact.primitives) < float(original.primitives), "Compaction lowers submitted primitives: " + str(view.id))
		check(controller.is_processing() == false and int(controller.metrics().selected_instances) > 0, "Submission updates independently of frozen world processing")
		records.append({"id": view.id, "uncompacted_primitives": original.primitives, "compacted_primitives": compact.primitives, "uncompacted_draw_calls": original.draw_calls, "compacted_draw_calls": compact.draw_calls, "repeat_difference": noise, "compaction_difference": difference, "restoration_difference": restoration_difference, "recompaction_difference": repeat_difference, "restored_original_buffers_verified": original_buffers_verified, "submission": controller.metrics()})
	var prior_updates := int(controller.metrics().updates)
	camera.position += Vector3(12, 0, 0)
	await RenderingServer.frame_post_draw
	check(int(controller.metrics().updates) > prior_updates, "Frozen-world camera motion refreshes before drawing")
	check(camera.global_position.distance_to(controller.get("_last_position")) < 0.001, "First post-motion draw uses the new camera location")
	var second_camera := Camera3D.new()
	world.add_child(second_camera)
	second_camera.global_transform = camera.global_transform
	prior_updates = int(controller.metrics().updates)
	second_camera.make_current()
	await RenderingServer.frame_post_draw
	check(int(controller.metrics().updates) > prior_updates, "Camera replacement refreshes at the same location")
	check(int(controller.get("_camera_id")) == second_camera.get_instance_id(), "First replacement-camera draw uses the new camera")
	second_camera.position = Vector3(10000, 100, 10000)
	await RenderingServer.frame_post_draw
	check(int(controller.metrics().selected_instances) == 0, "First distant teleport draw empties near and middle prefixes")
	second_camera.position = cases[0].position
	await RenderingServer.frame_post_draw
	check(int(controller.metrics().selected_instances) > 0 and second_camera.global_position.distance_to(controller.get("_last_position")) < 0.001, "First return teleport draw restores required instances")
	var update_times: Array[int] = []
	var scanned_counts: Array[int] = []
	var write_counts: Array[int] = []
	for frame: int in 180:
		second_camera.position = cases[0].position + Vector3(sin(float(frame) * 0.035) * 8.0, 0, cos(float(frame) * 0.035) * 6.0)
		second_camera.look_at(cases[0].target)
		prior_updates = int(controller.metrics().updates)
		await process_frame
		await RenderingServer.frame_post_draw
		var metrics: Dictionary = controller.metrics()
		if frame >= 60 and int(metrics.updates) > prior_updates:
			update_times.append(int(metrics.update_us))
			scanned_counts.append(int(metrics.scanned_instances))
			write_counts.append(int(metrics.changed_slots))
	update_times.sort()
	check(not update_times.is_empty(), "Moving camera exercises submission updates")
	movement = {"sample_frames": 120, "update_count": update_times.size(), "update_times_us": update_times, "scanned_instances": scanned_counts, "changed_slots": write_counts, "physics_interpolation_enabled": bool(ProjectSettings.get_setting("physics/common/physics_interpolation", false))}
