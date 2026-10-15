extends SceneTree
## Native instance-distance selection and complementary tree LOD coverage.

const Library = preload("res://scripts/lodgepole_library.gd")
var failures: Array[String] = []
var failure_count := 0
var checks := 0
var output := "res://work/tree-instance-lod"

func _initialize() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			output = argument.trim_prefix("--out=")
	call_deferred("verify")

func check(condition: bool, detail: String) -> void:
	checks += 1
	if not condition:
		failure_count += 1
		if failures.size() < 100:
			failures.append(detail)

func fixture(shader_path: String, texture: Texture2D, begin: float, end: float) -> MultiMeshInstance3D:
	var material := ShaderMaterial.new()
	material.shader = load(shader_path)
	material.set_shader_parameter("instance_lod", true)
	material.set_shader_parameter("lod_begin_m", begin)
	material.set_shader_parameter("lod_end_m", end)
	material.set_shader_parameter("wind_vector", Vector2.ZERO)
	material.set_shader_parameter("tint", Vector3.ONE)
	material.set_shader_parameter("use_texture", true)
	material.set_shader_parameter("albedo_texture", texture)
	for direction: int in 4:
		material.set_shader_parameter("view_%d" % direction, texture)
	var mesh := QuadMesh.new()
	mesh.size = Vector2(2, 2)
	mesh.material = material
	var multi := MultiMesh.new()
	multi.transform_format = MultiMesh.TRANSFORM_3D
	multi.use_custom_data = true
	multi.mesh = mesh
	multi.instance_count = 2
	multi.set_instance_transform(0, Transform3D(Basis.IDENTITY, Vector3(-1.1, 0, 0)))
	multi.set_instance_transform(1, Transform3D(Basis.IDENTITY, Vector3(1.1, 0, 0)))
	var node := MultiMeshInstance3D.new()
	node.multimesh = multi
	return node

func set_distances(node: MultiMeshInstance3D, first: float, second: float) -> void:
	node.multimesh.set_instance_custom_data(0, Color(0, 0, 10.0 - first, 1))
	node.multimesh.set_instance_custom_data(1, Color(0, 0, 10.0 - second, 1))

func capture(viewport: SubViewport) -> Image:
	for frame: int in 3:
		await process_frame
	await RenderingServer.frame_post_draw
	return viewport.get_texture().get_image()

func coverage(image: Image, left: bool) -> int:
	var pixels := 0
	for y: int in range(32, 96):
		for x: int in range(12 if left else 140, 116 if left else 244):
			if image.get_pixel(x, y).a > 0.5:
				pixels += 1
	return pixels

func inspect_baked() -> Dictionary:
	var placements: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/placements.json"))
	var overrides: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/placement_overrides.json"))
	var expected: Dictionary = {}
	var seen: Dictionary = {}
	var candidates: Array = placements.trees.duplicate()
	candidates.append_array(overrides.get("add", []))
	for source: Dictionary in candidates:
		var identity := str(source.get("id", source.get("stable_id", "")))
		if identity in overrides.get("remove", []):
			continue
		var record: Dictionary = overrides.get("replace", {}).get(identity, source)
		if record.kind not in ["pine", "snag"]:
			continue
		var center := Vector3(record.position[0], record.position[1] + float(Library.display_dimensions(record).height_m) * 0.5, record.position[2])
		var key := "%.2f,%.2f" % [center.x, center.z]
		check(not expected.has(key), "Distinct source tree centers: " + identity)
		expected[key] = {"center": center, "kind": str(record.kind)}
		seen[key] = {}
	var scene: Node3D = load("res://scenes/authored_world.tscn").instantiate()
	var batches := 0
	var instances := 0
	for node: Node in scene.get_node("AuthoredVegetation").get_children():
		if not node is MultiMeshInstance3D or str(node.get_meta("vegetation_kind", "")) not in ["pine", "snag"]:
			continue
		batches += 1
		var multi: MultiMesh = node.multimesh
		check(multi.use_custom_data and multi.use_colors and bool(node.get_meta("instance_lod", false)), "Saved tree batch carries instance LOD data: " + str(node.name))
		var data := multi.buffer
		check(data.size() == multi.instance_count * 20, "Saved tree buffer stride: " + str(node.name))
		if data.size() != multi.instance_count * 20:
			continue
		var begin := float(node.get_meta("lod_begin_m"))
		var end := 18.0 if begin == 0 else (65.0 if begin == 18 else (180.0 if begin == 65 else 3000.0))
		var width := clampf(end * 0.1, 2.0, 18.0)
		var half_diagonal := multi.custom_aabb.size.length() * 0.5
		check(node.visibility_range_begin <= maxf(0, begin - half_diagonal - clampf(begin * 0.1, 2, 18)) + 0.001 and node.visibility_range_end >= end + half_diagonal + width - 0.001, "Batch visibility encloses all per-tree transition bands: " + str(node.name))
		for surface: int in multi.mesh.get_surface_count():
			var material := multi.mesh.surface_get_material(surface) as ShaderMaterial
			check(material != null and material.get_shader_parameter("instance_lod") == true and material.get_shader_parameter("lod_begin_m") == begin and material.get_shader_parameter("lod_end_m") == end, "Saved tree material range: " + str(node.name))
		for index: int in multi.instance_count:
			var at := index * 20 + 16
			var center := Vector3(data[at], data[at + 1], data[at + 2])
			var key := "%.2f,%.2f" % [center.x, center.z]
			check(expected.has(key), "Saved instance matches a source tree center")
			if not expected.has(key):
				continue
			check(center.distance_to(expected[key].center) < 0.0003 and absf(data[at + 3] - 1.0) < 0.0001, "Source tree center survives packed float serialization")
			check(multi.custom_aabb.grow(0.001).has_point(center - node.position), "Source center lies inside batch culling bounds")
			var part := "%s/%.0f" % [str(node.get_meta("tree_part")), begin]
			seen[key][part] = int(seen[key].get(part, 0)) + 1
			instances += 1
	for key: String in expected:
		var expected_parts := 7 if expected[key].kind == "snag" else 10
		check(seen[key].size() == expected_parts, "Each source tree retains all geometry and billboard LODs")
		for count: int in seen[key].values():
			check(count == 1, "Each source tree occurs once per part and LOD")
	scene.free()
	return {"source_trees": expected.size(), "batches": batches, "instances": instances}

func verify() -> void:
	if "--baked" in OS.get_cmdline_user_args():
		DirAccess.make_dir_recursive_absolute(output)
		var baked := inspect_baked()
		baked.merge({"ok": failures.is_empty(), "checks": checks, "failure_count": failure_count, "failures": failures})
		FileAccess.open(output.path_join("report.json"), FileAccess.WRITE).store_string(JSON.stringify(baked, "\t") + "\n")
		print("TREE_INSTANCE_LOD_BAKED ", JSON.stringify(baked))
		quit(0 if failures.is_empty() else 1)
		return
	if DisplayServer.get_name() == "headless":
		push_error("Tree LOD raster verification requires a native renderer")
		quit(2)
		return
	DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(320, 180)
	var viewport := SubViewport.new()
	viewport.size = Vector2i(256, 128)
	viewport.own_world_3d = true
	viewport.transparent_bg = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var parent := Node3D.new()
	viewport.add_child(parent)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.keep_aspect = Camera3D.KEEP_WIDTH
	camera.size = 4.4
	parent.add_child(camera)
	camera.position = Vector3(0, 0, 10)
	camera.make_current()
	var opaque := Image.create(2, 2, false, Image.FORMAT_RGBA8)
	opaque.fill(Color.WHITE)
	var texture := ImageTexture.create_from_image(opaque)
	var pixel_cases := 0
	for shader: String in ["tree_bark", "foliage", "tree_impostor"]:
		for boundary: float in [18.0, 65.0, 180.0]:
			var near_node := fixture("res://shaders/%s.gdshader" % shader, texture, 0, boundary)
			var far_node := fixture("res://shaders/%s.gdshader" % shader, texture, boundary, 3000)
			parent.add_child(near_node)
			parent.add_child(far_node)
			set_distances(near_node, boundary * 0.5, boundary * 1.5)
			set_distances(far_node, boundary * 0.5, boundary * 1.5)
			far_node.hide()
			var near_only := await capture(viewport)
			check(coverage(near_only, true) > 5000 and coverage(near_only, false) == 0, "%s %.0fm selects each instance independently" % [shader, boundary])
			far_node.show()
			var reference := await capture(viewport)
			check(coverage(reference, true) > 5000 and coverage(reference, false) > 5000, "%s %.0fm covers both distant instances" % [shader, boundary])
			for fraction: float in [-0.08, 0.0, 0.08]:
				set_distances(near_node, boundary * (1.0 + fraction), boundary * (1.0 - fraction))
				set_distances(far_node, boundary * (1.0 + fraction), boundary * (1.0 - fraction))
				var blended := await capture(viewport)
				var changed := 0
				for y: int in 128:
					for x: int in 256:
						if absf(reference.get_pixel(x, y).a - blended.get_pixel(x, y).a) > 0.01:
							changed += 1
				check(changed == 0, "%s %.0fm complementary transition %.2f has %d changed alpha pixels" % [shader, boundary, fraction, changed])
				pixel_cases += 1
			near_node.free()
			far_node.free()
	var material_checks := 0
	for form: String in Library.ARCHETYPES:
		var assets := Library.load_assets(form)
		check(Library.bind_cutout_materials(assets), "Tree cutouts bind: " + form)
		assets.pop_back()
		assets.append(Library.load_billboard_batch(form))
		for asset: Array in assets:
			Library.bind_instance_lods(asset)
			var mesh: Mesh = asset[0]
			for surface: int in mesh.get_surface_count():
				var material := mesh.surface_get_material(surface) as ShaderMaterial
				check(material != null and material.get_shader_parameter("instance_lod") == true and material.get_shader_parameter("lod_begin_m") == float(asset[2]) and material.get_shader_parameter("lod_end_m") == float(asset[3]), "Tree parts preserve common LOD ranges: " + form + "/" + str(asset[4]))
				material_checks += 1
	var report := {"ok": failures.is_empty(), "checks": checks, "pixel_transition_cases": pixel_cases, "material_checks": material_checks, "renderer": RenderingServer.get_current_rendering_method(), "failure_count": failure_count, "failures": failures}
	FileAccess.open(output.path_join("report.json"), FileAccess.WRITE).store_string(JSON.stringify(report, "\t") + "\n")
	print("TREE_INSTANCE_LOD ", JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
