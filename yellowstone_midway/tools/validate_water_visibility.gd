extends SceneTree
## Native water visibility with terrain-occlusion and depth controls.

var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func probe(pool: MeshInstance3D, ignore_depth: bool) -> Image:
	var shader := Shader.new()
	shader.code = "shader_type spatial;render_mode unshaded,cull_disabled" + (",depth_test_disabled" if ignore_depth else "") + ";void fragment(){ALBEDO=vec3(1.0,0.0,1.0);}"
	var material := ShaderMaterial.new()
	material.shader = shader
	pool.material_override = material
	for frame: int in 8:
		await process_frame
	await RenderingServer.frame_post_draw
	return root.get_texture().get_image()

func mask(image: Image) -> PackedByteArray:
	image.convert(Image.FORMAT_RGBA8)
	var bytes := image.get_data()
	var result := PackedByteArray()
	result.resize(image.get_width() * image.get_height())
	for index: int in result.size():
		result[index] = 1 if bytes[index * 4] > 180 and bytes[index * 4 + 2] > 180 and bytes[index * 4 + 1] < 80 else 0
	return result

func fraction(actual: PackedByteArray, reference: PackedByteArray) -> float:
	var visible := 0
	var total := 0
	for index: int in reference.size():
		if reference[index] == 1:
			total += 1
			visible += int(actual[index])
	return float(visible) / maxf(total, 1.0)

func run() -> void:
	if DisplayServer.get_name() == "headless":
		quit(2)
		return
	ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:1")
	root.size = Vector2i(1440, 900)
	var world: Node = load("res://scenes/main.tscn").instantiate()
	root.add_child(world)
	for frame: int in 12:
		await process_frame
	world.set_process(false)
	world.ecosystem.set_process(false)
	world.atmosphere_controller.set_process(false)
	world.weather_snapshot_reader.set_process(false)
	world.overlay.visible = false
	for steam: Node3D in get_nodes_in_group("steam"):
		steam.visible = false
	var camera := Camera3D.new()
	camera.fov = 72
	camera.position = Vector3(-242, 52, 160)
	world.add_child(camera)
	camera.look_at(Vector3(-213, 30, 125))
	camera.make_current()
	var pool: MeshInstance3D
	for node: Node in get_nodes_in_group("thermal_surfaces"):
		if node.get_meta("feature_name", "") == "Grand Prismatic Spring":
			pool = node
	if pool == null:
		quit(1)
		return
	var reference := mask(await probe(pool, true))
	var positive := mask(await probe(pool, false))
	var core: Node = world.get_node("CoreTerrain")
	var cut: Dictionary = core.open_water_cut_status()
	core.cut_open_water([])
	var negative := mask(await probe(pool, false))
	core.cut_open_water(world.spec.pools)
	pool.material_override = null
	var coverage := fraction(positive, reference)
	var negative_coverage := fraction(negative, reference)
	if coverage < 0.85:
		failures.append("Mapped-water interior does not expose the water material")
	if negative_coverage > 0.1 or coverage - negative_coverage < 0.7:
		failures.append("The terrain-occlusion negative control fails")
	if not bool(cut.get("source_vertices_preserved", false)) or int(cut.get("removed_triangles", 0)) <= 0:
		failures.append("Conservative water cut metadata fails")
	for frame: int in 8:
		await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png("res://work/water_visible_material.png")
	var report := {"ok": failures.is_empty(), "positive_visible_fraction": coverage, "negative_visible_fraction": negative_coverage, "minimum_positive_fraction": 0.85, "depth_control": "identical water mesh with depth testing disabled", "scope": "Steam temporarily hidden for the isolated water-material probe; production captures preserve steam.", "cut": cut, "release_id": world.ReleaseData.active.manifest.release_id, "failures": failures}
	var file := FileAccess.open("res://work/water_visibility_report.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t") + "\n")
	print("WATER_VISIBILITY ", JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
