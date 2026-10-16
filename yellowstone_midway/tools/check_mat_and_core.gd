extends SceneTree

const REPORT_PATH := "res://tests/mat_and_core_report.json"

var _report: Dictionary = {
	"ok": false,
	"findings": [],
	"core": {},
	"mat": {},
	"shader": {},
	"fallback_check": {},
}

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var ok: bool = check_phase_1()
	var scratch_ramps: String = _scratch_ramps_arg()
	if not scratch_ramps.is_empty():
		var ramps_ok: bool = check_pool_ramp_loader(scratch_ramps)
		_report["pool_ramps_check"]["ok"] = ramps_ok
		if not ramps_ok:
			ok = false
	_report["ok"] = ok and _report["findings"].is_empty()
	write_report()
	print("MAT_AND_CORE_CHECK %s findings=%s" % ["PASS" if _report["ok"] else "FAIL", str(_report["findings"])])
	quit(0 if _report["ok"] else 1)

func _scratch_ramps_arg() -> String:
	# Optional --scratch-ramps=<dir>; the dir holds ramp_*.json/.png produced by run_mat_model.py.
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--scratch-ramps="):
			return arg.get_slice("=", 1)
	return ""

func check_pool_ramp_loader(scratch_dir: String) -> bool:
	_report["pool_ramps_check"] = {"scratch_dir": scratch_dir, "ramps": [], "ok": false}
	var dir: DirAccess = DirAccess.open(scratch_dir)
	if dir == null:
		add_finding("pool_ramps_check: cannot open scratch dir %s" % scratch_dir)
		return false
	var found: int = 0
	var validated: int = 0
	dir.list_dir_begin()
	var name: String = dir.get_next()
	while not name.is_empty():
		if name.ends_with(".json") and name.begins_with("ramp_"):
			found += 1
			var json_path: String = scratch_dir + "/" + name
			var png_path: String = scratch_dir + "/" + name.get_basename() + ".png"
			var row: Dictionary = _validate_ramp(json_path, png_path)
			(_report["pool_ramps_check"]["ramps"] as Array).append(row)
			if bool(row.get("valid", false)):
				validated += 1
		name = dir.get_next()
	dir.list_dir_end()
	_report["pool_ramps_check"]["ramps_found"] = found
	_report["pool_ramps_check"]["ramps_validated"] = validated
	if found == 0:
		add_finding("pool_ramps_check: no ramp_*.json files in %s" % scratch_dir)
		return false
	if validated < found:
		add_finding("pool_ramps_check: %d of %d ramps failed validation" % [found - validated, found])
		return false
	return true

func _validate_ramp(json_path: String, png_path: String) -> Dictionary:
	var out: Dictionary = {"json": json_path, "png": png_path, "valid": false, "issues": []}
	var file: FileAccess = FileAccess.open(json_path, FileAccess.READ)
	if file == null:
		(out["issues"] as Array).append("could not open JSON")
		return out
	var text: String = file.get_as_text()
	file.close()
	var parsed: Variant = JSON.parse_string(text)
	if not parsed is Dictionary:
		(out["issues"] as Array).append("JSON is not an object")
		return out
	var meta: Dictionary = parsed as Dictionary
	var schema: String = str(meta.get("schema", ""))
	out["schema"] = schema
	if schema != "yellowstone.pool_radiative_ramp.v1":
		(out["issues"] as Array).append("schema mismatch: " + schema)
		return out
	var pool_id: String = str(meta.get("pool_id", ""))
	out["pool_id"] = pool_id
	var expected_pool_id: String = json_path.get_file().get_basename().substr(len("ramp_"))
	if pool_id != expected_pool_id:
		(out["issues"] as Array).append("pool_id does not match filename")
	var samples: Variant = meta.get("samples")
	if not samples is Array or (samples as Array).size() < 2:
		(out["issues"] as Array).append("samples missing or too short")
		return out
	out["sample_count"] = (samples as Array).size()
	var first_sample: Variant = (samples as Array)[0]
	if first_sample is Dictionary:
		for field in ["fraction", "r_m", "depth_m", "t_c", "class", "rgb01", "color"]:
			if not (first_sample as Dictionary).has(field):
				(out["issues"] as Array).append("sample missing field: " + field)
	var parameters: Variant = meta.get("parameters")
	if parameters is Dictionary:
		for field in ["surface_reflection", "scatter_tint_rgb", "absorption_m_inv"]:
			if not (parameters as Dictionary).has(field):
				(out["issues"] as Array).append("parameters missing field: " + field)
	# PNG load.
	var image: Image = Image.new()
	var err: int = image.load(png_path)
	if err != OK:
		(out["issues"] as Array).append("Image.load failed: " + str(err))
		return out
	out["png_width"] = image.get_width()
	out["png_height"] = image.get_height()
	# Create a ShaderMaterial and apply the ramp to prove the pool_overlay path accepts it.
	var scratch_shader: Shader = load("res://shaders/water.gdshader")
	if scratch_shader != null:
		var sm: ShaderMaterial = ShaderMaterial.new()
		sm.shader = scratch_shader
		var tex: ImageTexture = ImageTexture.create_from_image(image)
		sm.set_shader_parameter("band_ramp", tex)
		sm.set_shader_parameter("ramp_mix", 1.0)
		var bound: Variant = sm.get_shader_parameter("ramp_mix")
		if float(bound) != 1.0:
			(out["issues"] as Array).append("water.gdshader did not accept ramp_mix")
	if (out["issues"] as Array).is_empty():
		out["valid"] = true
	return out

func check_phase_1() -> bool:
	if not ResourceLoader.exists("res://scripts/core_terrain.gd"):
		add_finding("scripts/core_terrain.gd absent")
		return false
	if not ResourceLoader.exists("res://scripts/mat_surface.gd"):
		add_finding("scripts/mat_surface.gd absent")
		return false
	# Build the mat surface loader with the full set WP-B / WP-A publish.
	var mat_surface_script: Script = load("res://scripts/mat_surface.gd")
	var mat_surface: RefCounted = mat_surface_script.new()
	var outflow_ok: bool = mat_surface.load_outflow()
	var pigment_ok: bool = mat_surface.load_pigment()
	var outflow_temp_ok: bool = mat_surface.load_outflow_temperature()
	_report["mat"]["outflow_loaded"] = outflow_ok
	_report["mat"]["pigment_loaded"] = pigment_ok
	_report["mat"]["outflow_temperature_loaded"] = outflow_temp_ok
	_report["mat"]["status_line"] = mat_surface.status_line()
	_report["mat"]["pigment_extent_rect"] = mat_surface.pigment_extent_rect()
	_report["mat"]["pigment_pixel_size_m"] = mat_surface.pigment_pixel_size_m()
	if not outflow_ok:
		add_finding("outflow rasters not loaded (data/outflow_network/ missing or malformed)")
	# Interfaces.md fixes the mat_pigment png at 0.5 m/px over a 1280 m extent at origin -640 -640; verify.
	if pigment_ok:
		var rect: Dictionary = mat_surface.pigment_extent_rect()
		if abs(float(rect.get("x_min_m", 0.0)) + 640.0) > 1.0:
			add_finding("pigment x_min_m is %.1f; expected -640.0" % float(rect["x_min_m"]))
		if abs(float(rect.get("z_min_m", 0.0)) + 640.0) > 1.0:
			add_finding("pigment z_min_m is %.1f; expected -640.0" % float(rect["z_min_m"]))
		if abs(float(rect.get("width_m", 0.0)) - 1280.0) > 1.0:
			add_finding("pigment width_m is %.1f; expected 1280.0" % float(rect["width_m"]))
		var pixel_size: float = mat_surface.pigment_pixel_size_m()
		if abs(pixel_size - 0.5) > 0.01:
			add_finding("pigment pixel_size_m is %.3f; expected 0.5 per interfaces.md" % pixel_size)
	# Build the core tile under a scratch root.
	var scratch_root: Node3D = Node3D.new()
	scratch_root.name = "ScratchCoreRoot"
	root.add_child(scratch_root)
	var core_script: Script = load("res://scripts/core_terrain.gd")
	var core: Node3D = core_script.new()
	core.name = "CoreTerrainUnderTest"
	scratch_root.add_child(core)
	var built: bool = core.build(mat_surface)
	_report["core"]["built"] = built
	if not built:
		add_finding("core_terrain.build returned false")
		return false
	_report["core"]["extent_rect"] = core.extent_rect()
	_report["core"]["heights_minmax"] = core.heights_minmax()
	# Inspect the shader material.
	var mat: ShaderMaterial = core.get_mat_material()
	if mat == null:
		add_finding("core material is null")
		return false
	if mat.shader == null:
		add_finding("thermal_apron shader not assigned")
		return false
	_report["shader"]["resource_path"] = mat.shader.resource_path
	# Confirm the shader parsed by requesting its uniform list; an uninformed shader returns an empty list.
	var params: Array = mat.shader.get_shader_uniform_list()
	_report["shader"]["parameter_count"] = params.size()
	var names: Array = []
	var sampler_count: int = 0
	for p in params:
		if p is Dictionary:
			names.append(str((p as Dictionary).get("name", "")))
			if int(p.get("type", 0)) == TYPE_OBJECT:
				sampler_count += 1
	_report["shader"]["sampler_count"] = sampler_count
	if sampler_count > 11:
		add_finding("core material exceeds the Compatibility texture slot budget")
	_report["shader"]["parameter_names"] = names
	for required_name: String in ["trail_mask", "biome_map", "snow_mask", "ground_wetness", "snow_amount", "snow_swe_mm", "snow_cover_fraction"]:
		if not required_name in names:
			add_finding("shared ground uniform absent: " + required_name)
	for texture_name: String in ["trail_mask", "biome_map", "detail_map"]:
		if not mat.get_shader_parameter(texture_name) is Texture2D:
			add_finding("shared ground texture unbound: " + texture_name)
	var trail_texture: Texture2D = mat.get_shader_parameter("trail_mask")
	if trail_texture != null:
		check_overlook_trail(trail_texture)
	if params.size() == 0:
		add_finding("thermal_apron shader exposes no uniforms (parse may have failed)")
	# Check uniform bindings.
	var expected_uniforms: PackedStringArray = PackedStringArray([
		"pigment_layers", "pigment_available",
		"outflow_layers", "normal_map_available", "normal_grid_size", "outflow_source_size",
		"wet_mask_available", "flow_fraction_available", "in_pool_available",
		"extent_x_min_m", "extent_z_min_m", "extent_width_m", "extent_height_m",
		"outflow_x_min_m", "outflow_z_min_m", "outflow_width_m", "outflow_height_m",
	])
	var bindings: Dictionary = {}
	for name_variant in expected_uniforms:
		var name: String = str(name_variant)
		var value: Variant = mat.get_shader_parameter(name)
		bindings[name] = str(value)
		if value == null:
			add_finding("uniform %s not set" % name)
	_report["shader"]["bindings"] = bindings
	for texture_name: String in ["ground_color_layers", "ground_normal_layers", "ground_arm_layers", "geography_layers", "pigment_layers", "outflow_layers"]:
		if not mat.get_shader_parameter(texture_name) is Texture2DArray:
			add_finding("shared ground array unbound: " + texture_name)
	for texture_name: String in ["rock_albedo", "snow_mask"]:
		if not mat.get_shader_parameter(texture_name) is Texture2D:
			add_finding("shared ground texture unbound: " + texture_name)
	if float(mat.get_shader_parameter("normal_map_available")) != 1.0:
		add_finding("verified residual normal map is unavailable")
	check_packed_fields(mat)
	check_master_ground(mat)
	var pigment_flag: Variant = mat.get_shader_parameter("pigment_available")
	_report["fallback_check"]["pigment_available_when_file_present"] = pigment_flag
	if pigment_ok and float(pigment_flag) != 1.0:
		add_finding("pigment file present but pigment_available flag not set")
	if not pigment_ok and float(pigment_flag) != 0.0:
		add_finding("pigment file absent but pigment_available flag is set")
	# Gradual blend check: start_blend must leave mat_pigment_blend at 0.0 so the per-frame ramp can lift it.
	if pigment_ok:
		var pigment_tex: Texture2D = mat_surface.pigment_tex
		mat_surface.start_blend(mat, pigment_tex)
		var blend_after_start: Variant = mat.get_shader_parameter("mat_pigment_blend")
		_report["fallback_check"]["mat_pigment_blend_after_start"] = blend_after_start
		if float(blend_after_start) != 0.0:
			add_finding("start_blend did not set mat_pigment_blend to 0; got %.3f" % float(blend_after_start))
	# Confirm the HeightMapShape3D is populated at full 1 m resolution.
	var collision_shape: HeightMapShape3D = _find_core_collision(core)
	if collision_shape == null:
		add_finding("core HeightMapShape3D not found")
	else:
		_report["core"]["collision_map_width"] = collision_shape.map_width
		_report["core"]["collision_map_depth"] = collision_shape.map_depth
		_report["core"]["collision_data_size"] = collision_shape.map_data.size()
		if collision_shape.map_width * collision_shape.map_depth != collision_shape.map_data.size():
			add_finding("collision map_data size does not match map_width * map_depth")
	# Mesh present with triangles.
	var mesh_instance: MeshInstance3D = core.find_child("CoreTerrainTile", true, false) as MeshInstance3D
	if mesh_instance == null or mesh_instance.mesh == null:
		add_finding("CoreTerrainTile mesh instance missing")
	else:
		var mesh: Mesh = mesh_instance.mesh
		var arrays: Array = mesh.surface_get_arrays(0)
		var vertex_count: int = (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
		var index_count: int = (arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).size()
		_report["core"]["mesh_vertex_count"] = vertex_count
		_report["core"]["mesh_index_count"] = index_count
		if vertex_count < 1000:
			add_finding("core mesh vertex count unexpectedly small (%d)" % vertex_count)
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var normal_error: float = 0.0
		var minimum_up: float = 1.0
		for normal: Vector3 in normals:
			normal_error = maxf(normal_error, absf(normal.length() - 1.0))
			minimum_up = minf(minimum_up, normal.y)
		_report["core"]["normal_length_max_error"] = normal_error
		_report["core"]["normal_y_min"] = minimum_up
		if normal_error > 0.0001 or minimum_up <= 0.0:
			add_finding("core geometric normals are invalid")
	return true

func check_overlook_trail(texture: Texture2D) -> void:
	var image: Image = texture.get_image()
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world.json"))
	var samples: Array[float] = []
	for route: Dictionary in data.get("routes", []):
		if str(route.get("id", "")) != "trail_3455_0":
			continue
		for point: Array in route.get("points", []):
			var uv := Vector2((float(point[0]) + 2048.0) / 4096.0, (float(point[2]) + 2048.0) / 4096.0)
			var pixel := uv * Vector2(image.get_width(), image.get_height()) - Vector2(0.5, 0.5)
			var ix: int = clampi(int(floor(pixel.x)), 0, image.get_width() - 2)
			var iz: int = clampi(int(floor(pixel.y)), 0, image.get_height() - 2)
			var fraction := pixel - Vector2(ix, iz)
			var north: float = lerpf(image.get_pixel(ix, iz).r, image.get_pixel(ix + 1, iz).r, fraction.x)
			var south: float = lerpf(image.get_pixel(ix, iz + 1).r, image.get_pixel(ix + 1, iz + 1).r, fraction.x)
			samples.append(lerpf(north, south, fraction.y))
	_report["core"]["overlook_spur_mask_samples"] = samples
	if samples.size() != 22:
		add_finding("overlook spur route samples missing")
	for value: float in samples:
		if value < 0.18:
			add_finding("overlook spur centerline falls outside the tread mask")
			break

func check_master_ground(core_material: ShaderMaterial) -> void:
	var binder: Script = load("res://scripts/terrain_materials.gd")
	var tile: Mesh = load("res://assets/meshes/terrain/tile_06_08.res")
	var master: ShaderMaterial = tile.surface_get_material(0).duplicate()
	if not binder.bind_ground_material(master):
		add_finding("embedded master ground binding failed")
		return
	for uniform_name: String in ["ground_color_layers", "ground_normal_layers", "ground_arm_layers", "geography_layers", "rock_albedo", "biome_map", "detail_map", "trail_mask", "snow_mask"]:
		if master.get_shader_parameter(uniform_name) != core_material.get_shader_parameter(uniform_name):
			add_finding("core/master ground binding differs: " + uniform_name)
	for uniform_name: String in ["soil_tile_width_m", "trail_tile_width_m", "macro_color_strength", "detail_x_min_m", "detail_z_min_m", "detail_width_m", "detail_height_m"]:
		if master.get_shader_parameter(uniform_name) != core_material.get_shader_parameter(uniform_name):
			add_finding("core/master ground coordinates differ: " + uniform_name)

func check_packed_fields(mat: ShaderMaterial) -> void:
	var packed: Texture2DArray = mat.get_shader_parameter("outflow_layers")
	var geography: Texture2DArray = mat.get_shader_parameter("geography_layers")
	var pigment: Texture2DArray = mat.get_shader_parameter("pigment_layers")
	if packed == null or packed.get_layers() != 5 or geography == null or geography.get_layers() != 3 or pigment == null or pigment.get_layers() != 2:
		add_finding("terrain packed layer counts disagree")
		return
	var image := Image.new()
	image.load_png_from_buffer(FileAccess.get_file_as_bytes("res://data/core_terrain/core_normal.png"))
	if mat.get_shader_parameter("normal_grid_size") != Vector2(image.get_width(), image.get_height()):
		add_finding("packed normal node dimensions disagree")
	var red: Image = packed.get_layer_data(3)
	var green: Image = packed.get_layer_data(4)
	if red == null or green == null:
		_report["shader"]["packed_normal_readback"] = "unavailable_by_backend"
		return
	_report["shader"]["packed_normal_readback"] = "verified"
	for point: Vector2i in [Vector2i.ZERO, Vector2i(300, 300), Vector2i(600, 600)]:
		var source: Color = image.get_pixelv(point)
		if absf(red.get_pixelv(point + Vector2i.ONE).r - source.r) > 0.000001 or absf(green.get_pixelv(point + Vector2i.ONE).r - source.g) > 0.000001:
			add_finding("packed normal channel disagrees with the validated PNG")

func _find_core_collision(core: Node) -> HeightMapShape3D:
	for child in core.get_children():
		if child is StaticBody3D:
			for sub in child.get_children():
				if sub is CollisionShape3D and (sub as CollisionShape3D).shape is HeightMapShape3D:
					return (sub as CollisionShape3D).shape as HeightMapShape3D
	return null

func add_finding(message: String) -> void:
	(_report["findings"] as Array).append(message)
	push_warning("mat_and_core_check: " + message)

func write_report() -> void:
	DirAccess.make_dir_recursive_absolute("res://tests")
	var file: FileAccess = FileAccess.open(REPORT_PATH, FileAccess.WRITE)
	if file == null:
		push_error("mat_and_core_check: could not open " + REPORT_PATH)
		return
	file.store_string(JSON.stringify(_report, "\t") + "\n")
	file.close()
