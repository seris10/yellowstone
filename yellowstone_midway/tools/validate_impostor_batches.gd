extends SceneTree
## Native pixel equivalence for packed distant-tree variants.

const Lodgepole = preload("res://scripts/lodgepole_library.gd")
var failures: Array[String] = []
var comparisons := 0
var maximum_channel_error := 0
var output := "res://work/impostor_batches"

func _initialize() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--out="):
			output = arg.trim_prefix("--out=")
	call_deferred("run")

func run() -> void:
	if DisplayServer.get_name() == "headless":
		push_error("Impostor pixel comparison requires a native rendering backend")
		quit(2)
		return
	root.size = Vector2i(640, 360)
	root.show()
	DirAccess.make_dir_recursive_absolute(output)
	var viewports: Array[SubViewport] = []
	var cameras: Array[Camera3D] = []
	var parents: Array[Node3D] = []
	for side: int in 2:
		var viewport := SubViewport.new()
		viewport.size = Vector2i(256, 512)
		viewport.own_world_3d = true
		viewport.transparent_bg = true
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		root.add_child(viewport)
		var parent := Node3D.new()
		viewport.add_child(parent)
		var camera := Camera3D.new()
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = 32.0
		camera.far = 100.0
		parent.add_child(camera)
		camera.make_current()
		viewports.append(viewport)
		cameras.append(camera)
		parents.append(parent)
	for form: String in Lodgepole.ARCHETYPES:
		var batch := Lodgepole.load_billboard_batch(form, false)
		if batch.is_empty():
			failures.append("Batched asset unavailable: " + form)
			continue
		var path := "user://impostor_roundtrip_%s.tres" % form
		if ResourceSaver.save(batch[0], path) != OK:
			failures.append("Batched mesh serialization fails: " + form)
			continue
		batch[0] = ResourceLoader.load(path, "Mesh", ResourceLoader.CACHE_MODE_IGNORE)
		if batch[0] == null or not Lodgepole.bind_billboard_batch(batch[0].material):
			failures.append("Saved batched material fails to bind: " + form)
			continue
		var layers: Texture2DArray = batch[0].material.get_shader_parameter("view_layers")
		if layers == null or layers.get_layers() != 16:
			failures.append("Batched asset omits variant directions: " + form)
		for variant: int in 4:
			var reference := Lodgepole.load_billboard(form, variant)
			if reference.is_empty():
				failures.append("Reference asset unavailable: " + form)
				continue
			if reference[0].size != batch[0].size or reference[1] != batch[1]:
				failures.append("Batched physical frame differs: " + form)
			var dimensions: Dictionary = Lodgepole.metadata().archetypes[form]
			var record := {"id": "packed_variant_fixture", "archetype": form, "height_m": float(dimensions.height_m) * 1.3, "dbh_m": float(dimensions.dbh_m) * 1.1, "crown_radius_m": float(dimensions.crown_radius_m) * 1.2, "crown_ratio": dimensions.crown_ratio}
			var transform: Transform3D = Transform3D(Basis(Vector3.UP, 0.37), Vector3(1.25, 2.0, -0.75)) * Lodgepole.local_transform(record, "Billboard") * reference[1]
			var nodes: Array[MultiMeshInstance3D] = []
			for side: int in 2:
				var multimesh := MultiMesh.new()
				multimesh.transform_format = MultiMesh.TRANSFORM_3D
				multimesh.use_colors = true
				multimesh.mesh = reference[0] if side == 0 else batch[0]
				multimesh.instance_count = 1
				multimesh.set_instance_transform(0, transform)
				multimesh.set_instance_color(0, Color.WHITE if side == 0 else Color(float(variant) / 3.0, 1, 1, 1))
				var node := MultiMeshInstance3D.new()
				node.multimesh = multimesh
				parents[side].add_child(node)
				nodes.append(node)
			for direction: int in 8:
				var angle := direction * TAU / 8.0 + 0.13
				for camera: Camera3D in cameras:
					camera.position = transform.origin + Vector3(sin(angle) * 40.0, 3.0, cos(angle) * 40.0)
					camera.look_at(transform.origin)
				for frame: int in 3:
					await process_frame
				await RenderingServer.frame_post_draw
				var first := viewports[0].get_texture().get_image()
				var second := viewports[1].get_texture().get_image()
				var a := first.get_data()
				var b := second.get_data()
				var error := 0
				for index: int in a.size():
					error = maxi(error, absi(int(a[index]) - int(b[index])))
				maximum_channel_error = maxi(maximum_channel_error, error)
				comparisons += 1
				if error > 1:
					failures.append("Variant pixel mismatch %s/%d/%d: %d" % [form, variant, direction, error])
					if failures.size() <= 2:
						first.save_png(output.path_join("reference_%s_%d_%d.png" % [form, variant, direction]))
						second.save_png(output.path_join("packed_%s_%d_%d.png" % [form, variant, direction]))
			for node: MultiMeshInstance3D in nodes:
				node.free()
	var report := {"ok": failures.is_empty() and comparisons == 160, "comparisons": comparisons, "maximum_channel_error_255": maximum_channel_error, "tolerance_255": 1, "variants_per_archetype": 4, "directions_per_variant": 8, "dimensions_and_transforms_preserved": true, "saved_mesh_reload_checked": true, "renderer": RenderingServer.get_current_rendering_method(), "failures": failures}
	var file := FileAccess.open(output.path_join("report.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t") + "\n")
	print("IMPOSTOR_BATCHES ", JSON.stringify(report))
	quit(0 if report.ok else 1)
