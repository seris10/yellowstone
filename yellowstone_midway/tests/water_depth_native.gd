extends SceneTree
## Native sampled-depth and river-opacity regression fixture.

var output := "user://water-depth-native"
var failures: Array[String] = []

func _initialize() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			output = argument.trim_prefix("--out=")
	call_deferred("run")

func frame_image() -> Image:
	for frame: int in 8:
		await process_frame
	await RenderingServer.frame_post_draw
	return root.get_texture().get_image()

func run() -> void:
	if DisplayServer.get_name() == "headless":
		print("WATER_DEPTH_NATIVE NOT_TESTED: native renderer required")
		quit(2)
		return
	DirAccess.make_dir_recursive_absolute(output)
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.position = Vector3(0,8,10)
	camera.look_at(Vector3.ZERO)
	camera.current = true
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = 1.0
	root.add_child(environment)
	var floor_node := MeshInstance3D.new()
	floor_node.mesh = PlaneMesh.new()
	floor_node.mesh.size = Vector2(30,30)
	var floor_mat := StandardMaterial3D.new()
	floor_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	floor_mat.albedo_color = Color(0.4,0.22,0.08)
	floor_node.material_override = floor_mat
	root.add_child(floor_node)
	var bed := await frame_image()
	bed.save_png(output.path_join("bed.png"))
	var plane := PlaneMesh.new()
	plane.size = Vector2(15,15)
	var arrays := plane.surface_get_arrays(0)
	var colors := PackedColorArray()
	colors.resize((arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size())
	colors.fill(Color.WHITE)
	arrays[Mesh.ARRAY_COLOR] = colors
	var water := MeshInstance3D.new()
	water.mesh = ArrayMesh.new()
	water.mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	water.position.y = 0.53
	var material := ShaderMaterial.new()
	material.shader = load("res://shaders/river_water.gdshader")
	water.material_override = material
	root.add_child(water)
	var rendered := await frame_image()
	rendered.save_png(output.path_join("river.png"))
	var pixel := Vector2i(rendered.get_width() / 2, rendered.get_height() / 2)
	var bed_color := bed.get_pixelv(pixel)
	var water_color := rendered.get_pixelv(pixel)
	var difference := Vector3(water_color.r-bed_color.r,water_color.g-bed_color.g,water_color.b-bed_color.b).length()
	if difference < 0.1:
		failures.append("River draw does not visibly change the submerged bed")
	var shader := Shader.new()
	shader.code = FileAccess.get_file_as_string("res://shaders/river_water.gdshader").replace("cull_disabled;", "cull_disabled, unshaded;").replace("ALPHA=clamp(alpha,0.0,1.0);", "ALBEDO=vec3(clamp(water_depth*0.5,0.0,1.0),isnan(water_depth)||isinf(water_depth)?1.0:0.0,1.0); ALPHA=1.0;")
	material.shader = shader
	var diagnostic := await frame_image()
	diagnostic.save_png(output.path_join("depth.png"))
	var color := diagnostic.get_pixelv(pixel).srgb_to_linear()
	var depth := color.r * 2.0
	var expected := 0.53 / absf(camera.global_basis.z.y)
	# RGB8 readback bounds the depth comparison to 2 cm.
	if color.g > 0.01 or absf(depth - expected) > 0.02:
		failures.append("Sampled column %.4f differs from plane intersection %.4f m" % [depth, expected])
	var report := {"ok":failures.is_empty(),"failures":failures,"column_m":depth,"expected_column_m":expected,"opacity_color_difference":difference,"msaa_3d":root.msaa_3d,"screen_space_aa":root.screen_space_aa,"engine":Engine.get_version_info().string,"renderer":RenderingServer.get_current_rendering_method()}
	var file := FileAccess.open(output.path_join("result.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report,"  "))
	file.close()
	print("WATER_DEPTH_NATIVE ", JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
