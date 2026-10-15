extends SceneTree
## Native visibility and source preservation for authored canopy attachments.

const Canopy = preload("res://scripts/canopy_surface.gd")
const Ground = preload("res://scripts/rendered_ground.gd")
var checks := 0
var failures: Array[String] = []
var output := "res://work/canopy-attachments"
var captures: Array = []
var originals: Dictionary = {}
var replacements: Dictionary = {}
var preservation: Dictionary = {}
var mask_controls: Dictionary = {}

func _initialize() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			output = argument.trim_prefix("--out=")
	call_deferred("run")

func check(condition: bool, detail: String) -> void:
	checks += 1
	if not condition and failures.size() < 60:
		failures.append(detail)

func freeze(node: Node) -> void:
	node.set_process(false)
	node.set_physics_process(false)
	if node is AnimationPlayer:
		node.pause()
	if node is GPUParticles3D or node is CPUParticles3D:
		node.speed_scale = 0.0
	for child: Node in node.get_children():
		freeze(child)

func verify_preservation() -> void:
	var authored: Node3D = load("res://scenes/authored_world.tscn").instantiate()
	var group: Node3D = authored.get_node("AuthoredCanopySurface")
	var source: Dictionary = Canopy.read_source("res://data/lidar_canopy/unresolved_render_canopy.json")
	var ground = Ground.new()
	check(ground.valid(), "Rendered terrain is available for physical support contact")
	var retained: Dictionary = {}
	var original_indices: Dictionary = {}
	var original_count := int(group.get_meta("cluster_display_count"))
	for node: Node in group.get_children():
		if node is MultiMeshInstance3D:
			retained[node.name] = node.multimesh
			original_indices[node.name] = node.get_meta("source_indices")
			originals[int(node.get_meta("cluster_lod"))] = node.multimesh.mesh
	var result := Canopy.refresh_geometry(group)
	var total_records := 0
	var root_samples := 0
	var maximum_contact_error := 0.0
	var seen: Array[Dictionary] = [{}, {}, {}]
	var first_meshes: Dictionary = {}
	for node: Node in group.get_children():
		if not node is MultiMeshInstance3D:
			continue
		var previous: MultiMesh = retained[node.name]
		var current: MultiMesh = node.multimesh
		var lod: int = node.get_meta("cluster_lod")
		var ids: PackedInt32Array = node.get_meta("source_indices")
		check(previous != current and previous.mesh != current.mesh, "Shared source resource is isolated from runtime geometry")
		check(previous.buffer == current.buffer, "Every transform and custom endpoint float is unchanged")
		check(previous.instance_count == current.instance_count and previous.visible_instance_count == current.visible_instance_count, "Every source display record is retained")
		check(previous.custom_aabb == current.custom_aabb, "Conservative source culling bounds are unchanged")
		check(ids == original_indices[node.name], "Source cell identities remain exact")
		if not first_meshes.has(lod):
			first_meshes[lod] = current.mesh
		check(current.mesh == first_meshes[lod], "Only three replacement LOD meshes are shared")
		replacements[lod] = current.mesh
		total_records += current.instance_count
		var data := current.buffer
		for slot: int in current.instance_count:
			var at := slot * 16
			var index := ids[slot]
			check(not seen[lod].has(index) and source.unresolved_cells[index] == 1, "Active source cell occurs exactly once per LOD")
			seen[lod][index] = true
			var transform := Transform3D(Basis(Vector3(data[at], data[at + 4], data[at + 8]), Vector3(data[at + 1], data[at + 5], data[at + 9]), Vector3(data[at + 2], data[at + 6], data[at + 10])), Vector3(data[at + 3], data[at + 7], data[at + 11]))
			var depth := transform.basis.y.length()
			var custom := Vector3(data[at + 12], data[at + 13], data[at + 14])
			var physical_root := custom * Vector3(1, depth, 1)
			var shader_endpoint: Vector3 = node.transform * transform * (physical_root / Vector3(1, depth, 1))
			check(shader_endpoint.is_finite(), "Shader support endpoint remains finite under actual instance scaling")
			if data[at + 15] < 0.5 and lod == 0:
				var contact_error := absf(shader_endpoint.y - ground.sample(shader_endpoint.x, shader_endpoint.z) + 0.04)
				maximum_contact_error = maxf(maximum_contact_error, contact_error)
				check(contact_error < 0.00005, "Grounded shader endpoint intersects rendered terrain by 0.04m")
				root_samples += 1
	for lod: int in 3:
		check(seen[lod].size() == original_count, "All source display cells survive every LOD")
	var again := Canopy.refresh_geometry(group)
	check(int(again.upgraded_batches) == 0, "Runtime geometry upgrade is idempotent")
	for node: Node in group.get_children():
		if node is MultiMeshInstance3D:
			check(node.multimesh.mesh == first_meshes[int(node.get_meta("cluster_lod"))], "Idempotent upgrade retains shared mesh identity")
	preservation = {"upgrade": result, "source_cells_per_lod": original_count, "source_records": total_records, "represented_area_m2": group.get_meta("represented_area_m2"), "terrain_contact_samples": root_samples, "maximum_terrain_contact_error_m": maximum_contact_error, "source_mask_sha256": source.artifacts.unresolved_render_mask.sha256, "source_top_sha256": source.artifacts.canopy_top_scene_y.sha256, "buffer_and_source_identity": "exact_all_records", "geometry_revision": Canopy.GEOMETRY_REVISION}
	for mesh: ArrayMesh in replacements.values():
		verify_mesh(mesh)
	authored.free()

func verify_mesh(mesh: ArrayMesh) -> void:
	var arrays := mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	check(vertices.size() > 0 and vertices.size() == normals.size(), "Replacement contains vertices and matching normals")
	for index: int in vertices.size():
		check(vertices[index].is_finite() and normals[index].is_finite(), "Native mesh vertex and normal remain finite")
		check(absf(normals[index].length() - 1.0) < 0.00001, "Native mesh normal is unit length")
	for at: int in range(0, indices.size(), 3):
		var a := vertices[indices[at]]
		var b := vertices[indices[at + 1]]
		var c := vertices[indices[at + 2]]
		var area := (b - a).cross(c - a)
		check(area.length() > 0.000001, "Every tube and card triangle has positive area")
		var normal := normals[indices[at]] + normals[indices[at + 1]] + normals[indices[at + 2]]
		check(area.dot(normal) < 0, "Tube and card winding matches outward normals")

func changed_channels(a: Image, b: Image) -> int:
	var first := a.get_data()
	var second := b.get_data()
	var changed := 0
	for index: int in first.size():
		changed += 1 if first[index] != second[index] else 0
	return changed

func capture(label: String) -> Image:
	for frame: int in 8:
		await process_frame
	await RenderingServer.frame_post_draw
	var path := output.path_join(label + ".png")
	var image := root.get_texture().get_image()
	check(image.save_png(path) == OK, "Native capture saves: " + label)
	captures.append({"label": label, "path": path, "sha256": FileAccess.get_sha256(path), "width": image.get_width(), "height": image.get_height(), "primitives": Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)})
	print("CANOPY_CAPTURE ", label)
	return image

func native_world() -> void:
	ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:1")
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
	world.menu.hide()
	world.player.enabled = false
	for material: ShaderMaterial in world.foliage_materials:
		material.set_shader_parameter("wind_vector", Vector2.ZERO)
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	var camera := Camera3D.new()
	world.add_child(camera)
	camera.near = 0.08
	camera.far = 2900
	camera.make_current()
	var ground = Ground.new()
	var views := [
		{"label": "wood_walk", "position": Vector3(-259.9, ground.sample(-259.9, 160) + 1.67, 160), "target": Vector3(-263.5, 43.7, 155.8), "fov": 64.0},
		{"label": "litter_walk", "position": Vector3(-250, ground.sample(-250, 136.5) + 1.67, 136.5), "target": Vector3(-251.75, 32.65, 133.81), "fov": 64.0},
		{"label": "overlook_foreground", "position": Vector3(-242, 52, 160), "target": Vector3(-213, 30, 125), "fov": 72.0}]
	var group: Node3D = world.find_child("AuthoredCanopySurface", true, false)
	check(int(group.get_meta("geometry_revision")) == Canopy.GEOMETRY_REVISION, "Main scene upgrades stale saved canopy before rendering")
	for view: Dictionary in views:
		camera.position = view.position
		camera.look_at(view.target)
		camera.fov = view.fov
		for revision: String in ["original", "tubes"]:
			for node: Node in group.get_children():
				if node is MultiMeshInstance3D:
					node.multimesh.mesh = originals[int(node.get_meta("cluster_lod"))] if revision == "original" else replacements[int(node.get_meta("cluster_lod"))]
			await capture(str(view.label) + "-" + revision)
	world.queue_free()
	await process_frame

func native_angles() -> void:
	var stage := Node3D.new()
	root.add_child(stage)
	var environment := WorldEnvironment.new()
	var settings := Environment.new()
	settings.background_mode = Environment.BG_COLOR
	settings.background_color = Color(0.16, 0.20, 0.25)
	settings.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	settings.ambient_light_color = Color.WHITE
	settings.ambient_light_energy = 0.7
	environment.environment = settings
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-42, -30, 0)
	light.light_energy = 1.1
	stage.add_child(light)
	var ground := MeshInstance3D.new()
	ground.mesh = PlaneMesh.new()
	ground.mesh.size = Vector2(40, 40)
	var ground_material := StandardMaterial3D.new()
	ground_material.albedo_color = Color(0.36, 0.31, 0.25)
	ground.mesh.material = ground_material
	stage.add_child(ground)
	var material: ShaderMaterial = replacements[0].surface_get_material(0).duplicate()
	var mask := Image.create(2, 2, false, Image.FORMAT_R8)
	mask.fill(Color.WHITE)
	material.set_shader_parameter("coverage_texture", ImageTexture.create_from_image(mask))
	material.set_shader_parameter("support_texture", ImageTexture.create_from_image(mask))
	material.set_shader_parameter("mask_origin_m", Vector2(-20, -20))
	material.set_shader_parameter("mask_extent_m", Vector2(40, 40))
	material.set_shader_parameter("lod_end_m", 100.0)
	var mesh: ArrayMesh = Canopy._shoot_mesh(sqrt(2.0), 40, material)
	var multi := MultiMesh.new()
	multi.transform_format = MultiMesh.TRANSFORM_3D
	multi.use_custom_data = true
	multi.instance_count = 1
	multi.mesh = mesh
	multi.set_instance_transform(0, Transform3D(Basis.IDENTITY.scaled(Vector3(1, 8.4, 1)), Vector3(0, 12, 0)))
	multi.set_instance_custom_data(0, Color(0, -12.04 / 8.4, 0, 0))
	multi.custom_aabb = AABB(Vector3(-3, -1, -3), Vector3(6, 14, 6))
	var node := MultiMeshInstance3D.new()
	node.multimesh = multi
	stage.add_child(node)
	var camera := Camera3D.new()
	stage.add_child(camera)
	camera.fov = 36
	camera.near = 0.05
	camera.make_current()
	var positive: Image
	for angle: int in range(0, 360, 45):
		camera.position = Vector3(cos(deg_to_rad(angle)) * 10, 10.8, sin(deg_to_rad(angle)) * 10)
		camera.look_at(Vector3(0, 10.8, 0))
		positive = await capture("bough_azimuth_%03d" % angle)
	var zero := Image.create(2, 2, false, Image.FORMAT_R8)
	zero.fill(Color.BLACK)
	material.set_shader_parameter("coverage_texture", ImageTexture.create_from_image(zero))
	var no_coverage := await capture("mask_coverage_zero")
	material.set_shader_parameter("coverage_texture", ImageTexture.create_from_image(mask))
	material.set_shader_parameter("support_texture", ImageTexture.create_from_image(zero))
	var no_support := await capture("mask_support_zero")
	var removed := changed_channels(positive, no_coverage)
	var mask_difference := changed_channels(no_coverage, no_support)
	check(removed > 500, "Positive native mask visibly retains foliage and twig pixels")
	check(mask_difference == 0, "Zero coverage and zero support produce identical bare supports")
	mask_controls = {"positive_to_zero_changed_channels": removed, "zero_coverage_to_zero_support_changed_channels": mask_difference, "scope": "Stationary native shader fixture with all-white and all-zero masks"}
	material.set_shader_parameter("support_texture", ImageTexture.create_from_image(mask))
	camera.position = Vector3(12, 6, 15)
	camera.look_at(Vector3(0, 6, 0))
	camera.fov = 42
	await capture("grounded_support_full_height")
	stage.queue_free()
	await process_frame

func run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	if DisplayServer.get_name() == "headless" and "--source-only" not in OS.get_cmdline_user_args():
		push_error("Native attachments require a real renderer")
		quit(2)
		return
	var source_only := "--source-only" in OS.get_cmdline_user_args()
	verify_preservation()
	if not source_only:
		root.size = Vector2i(1440, 900)
		root.show()
		await native_world()
		await native_angles()
		check(captures.size() == 17, "Native validation requires all 17 world, angle, contact and mask captures")
	var hashes := {}
	for path: String in ["res://scripts/canopy_surface.gd", "res://shaders/canopy_surface.gdshader", "res://scripts/world.gd", "res://scripts/rendered_ground.gd", "res://tools/validate_canopy_attachments.gd", "res://scenes/authored_world.tscn", "res://data/lidar_canopy/unresolved_render_canopy.json"]:
		hashes[path] = FileAccess.get_sha256(path)
	var report := {"schema": "yellowstone.canopy_visible_attachments.v1", "ok": failures.is_empty(), "checks": checks, "failures": failures, "mode": "source_and_geometry_only" if source_only else "native_source_geometry_and_visibility", "native_render_verified": not source_only and captures.size() == 17 and failures.is_empty(), "source_hashes": hashes, "native_mask_controls": mask_controls, "preservation": preservation, "native_views": captures, "renderer": RenderingServer.get_current_rendering_method(), "limitations": ["Authored support dimensions and bough orientations have unknown uncertainty; residual cells are not inferred measured stems.", "Visible support is inspected in native captures at eight azimuths and three world views; source contact checks alone do not establish perceptual grounding.", "Residual supports and foliage preserve the existing no-shadow policy; field botanical acceptance and other renderer backends are not tested."]}
	FileAccess.open(output.path_join("report.json"), FileAccess.WRITE).store_string(JSON.stringify(report, "\t") + "\n")
	print("CANOPY_ATTACHMENTS ", JSON.stringify({"ok": report.ok, "checks": checks, "failures": failures, "captures": captures.size(), "preservation": preservation}))
	quit(0 if failures.is_empty() else 1)
