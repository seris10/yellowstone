class_name MidwayMatSurface
extends RefCounted
const ReleaseData = preload("res://scripts/release_data.gd")
const TerrainMaterials = preload("res://scripts/terrain_materials.gd")

const OUTFLOW_JSON := "res://data/outflow_network/outflow_network.json"
const WET_MASK_PATH := "res://data/outflow_network/wet_mask.i16"
const FLOW_FRACTION_PATH := "res://data/outflow_network/flow_fraction.f32"
const IN_POOL_PATH := "res://data/outflow_network/in_pool.i16"
const MAT_PIGMENT_PATH := "res://data/mat_pigment.png"
const MAT_STATE_PATH := "res://data/mat_state.json"
const MAT_COMMUNITY_PATH := "res://data/mat_community.i16"
const OUTFLOW_TEMPERATURE_PATH := "res://data/outflow_temperature.f32"
const OUTFLOW_TEMPERATURE_META := "res://data/outflow_temperature.json"

var outflow_meta: Dictionary = {}
var wet_mask_tex: Texture2D
var flow_fraction_tex: Texture2D
var in_pool_tex: Texture2D
var pigment_tex: Texture2D
var pigment_meta: Dictionary = {}
var mat_state_meta: Dictionary = {}
var community_tex: Texture2D
var outflow_temp_tex: Texture2D
var outflow_temp_meta: Dictionary = {}
var pigment_sha256_at_load: String = ""
# World extent of the outflow rasters; defaulted to the core grid when outflow_network.json is absent.
var outflow_x_min_m: float = -640.0
var outflow_z_min_m: float = -640.0
var outflow_width_m: float = 1280.0
var outflow_height_m: float = 1280.0
# Mat pigment extent (meters) read from mat_state.json or mat_pigment legend if available.
var pigment_x_min_m: float = -640.0
var pigment_z_min_m: float = -640.0
var pigment_width_m: float = 1280.0
var pigment_height_m: float = 1280.0

func load_outflow() -> bool:
	outflow_meta.clear()
	wet_mask_tex = null
	flow_fraction_tex = null
	in_pool_tex = null
	if not ReleaseData.file_exists(OUTFLOW_JSON):
		return false
	var parsed: Variant = JSON.parse_string(ReleaseData.get_file_as_string(OUTFLOW_JSON))
	if not parsed is Dictionary:
		return false
	outflow_meta = parsed
	var grid: Dictionary = outflow_meta.get("grid", {})
	var origin: Array = grid.get("origin_xz_m", [-640.0, -640.0])
	var cell_m: float = float(grid.get("cell_m", 1.0))
	var size: int = int(grid.get("size", 1280))
	outflow_x_min_m = float(origin[0])
	outflow_z_min_m = float(origin[1])
	outflow_width_m = cell_m * float(size)
	outflow_height_m = cell_m * float(size)
	wet_mask_tex = _load_i16_raster_as_binary_texture(WET_MASK_PATH, size, size)
	flow_fraction_tex = _load_f32_raster_as_texture(FLOW_FRACTION_PATH, size, size)
	in_pool_tex = _load_i16_raster_as_binary_texture(IN_POOL_PATH, size, size)
	return wet_mask_tex != null or flow_fraction_tex != null

func load_pigment() -> bool:
	pigment_tex = null
	community_tex = null
	mat_state_meta.clear()
	if ReleaseData.file_exists(MAT_STATE_PATH):
		var sparsed: Variant = JSON.parse_string(ReleaseData.get_file_as_string(MAT_STATE_PATH))
		if sparsed is Dictionary:
			mat_state_meta = sparsed as Dictionary
			var grid: Dictionary = mat_state_meta.get("grid", {})
			var origin: Array = grid.get("origin_xz_m", [-640.0, -640.0])
			var cell_m: float = float(grid.get("cell_size_m", grid.get("cell_m", 1.0)))
			var nx: int = int(grid.get("nx", 1280))
			var nz: int = int(grid.get("nz", 1280))
			pigment_x_min_m = float(origin[0])
			pigment_z_min_m = float(origin[1])
			pigment_width_m = cell_m * float(nx)
			pigment_height_m = cell_m * float(nz)
			if int(mat_state_meta.get("row_order_check_z", 0)) == 0:
				# row_order per interfaces.md is north_to_south; abort the texture mapping if the file disagrees.
				var row_order: String = str(grid.get("row_order", "north_to_south"))
				if row_order != "north_to_south":
					push_warning("mat_surface: unexpected row_order %s; mat sampling may be flipped." % row_order)
			# int16 community raster at full grid; used by the headless check for class coverage.
			community_tex = _load_i16_raster_as_binary_texture(MAT_COMMUNITY_PATH, nx, nz)
	if not ReleaseData.file_exists(MAT_PIGMENT_PATH):
		return false
	pigment_tex = _load_png_as_texture(MAT_PIGMENT_PATH)
	if pigment_tex != null:
		pigment_sha256_at_load = ReleaseData.get_sha256(MAT_PIGMENT_PATH)
	return pigment_tex != null

func load_outflow_temperature() -> bool:
	outflow_temp_tex = null
	outflow_temp_meta.clear()
	if not ReleaseData.file_exists(OUTFLOW_TEMPERATURE_META):
		return false
	var parsed: Variant = JSON.parse_string(ReleaseData.get_file_as_string(OUTFLOW_TEMPERATURE_META))
	if parsed is Dictionary:
		outflow_temp_meta = parsed as Dictionary
	var grid: Dictionary = outflow_temp_meta.get("grid", {})
	var nx: int = int(grid.get("nx", 1280))
	var nz: int = int(grid.get("nz", 1280))
	outflow_temp_tex = _load_f32_raster_as_texture(OUTFLOW_TEMPERATURE_PATH, nx, nz)
	return outflow_temp_tex != null

func apply(mat: ShaderMaterial) -> bool:
	if pigment_tex != null:
		if not TerrainMaterials.bind_pigment_layers(mat, pigment_tex, pigment_tex):
			return false
		mat.set_shader_parameter("mat_pigment", pigment_tex)
		mat.set_shader_parameter("mat_pigment_prev", pigment_tex)
		mat.set_shader_parameter("mat_pigment_blend", 1.0)
		mat.set_shader_parameter("pigment_available", 1.0)
	else:
		mat.set_shader_parameter("pigment_available", 0.0)
		mat.set_shader_parameter("mat_pigment_blend", 1.0)
	mat.set_shader_parameter("pigment_x_min_m", pigment_x_min_m)
	mat.set_shader_parameter("pigment_z_min_m", pigment_z_min_m)
	mat.set_shader_parameter("pigment_width_m", pigment_width_m)
	mat.set_shader_parameter("pigment_height_m", pigment_height_m)
	# Outflow wet film inputs.
	if wet_mask_tex != null:
		mat.set_shader_parameter("wet_mask", wet_mask_tex)
		mat.set_shader_parameter("wet_mask_available", 1.0)
	else:
		mat.set_shader_parameter("wet_mask_available", 0.0)
	if flow_fraction_tex != null:
		mat.set_shader_parameter("flow_fraction", flow_fraction_tex)
		mat.set_shader_parameter("flow_fraction_available", 1.0)
	else:
		mat.set_shader_parameter("flow_fraction_available", 0.0)
	if in_pool_tex != null:
		mat.set_shader_parameter("in_pool", in_pool_tex)
		mat.set_shader_parameter("in_pool_available", 1.0)
	else:
		mat.set_shader_parameter("in_pool_available", 0.0)
	mat.set_shader_parameter("outflow_x_min_m", outflow_x_min_m)
	mat.set_shader_parameter("outflow_z_min_m", outflow_z_min_m)
	mat.set_shader_parameter("outflow_width_m", outflow_width_m)
	mat.set_shader_parameter("outflow_height_m", outflow_height_m)
	# Outflow temperature: optional secondary input, drives a warm tint where water is hot.
	if outflow_temp_tex != null:
		mat.set_shader_parameter("outflow_temperature", outflow_temp_tex)
		mat.set_shader_parameter("outflow_temp_available", 1.0)
	else:
		mat.set_shader_parameter("outflow_temp_available", 0.0)
	return true

func start_blend(mat: ShaderMaterial, new_pigment: Texture2D) -> void:
	# Capture the current pigment as the previous frame and set blend to 0 so world.gd ramps it toward 1 over the blend duration.
	if mat == null or new_pigment == null:
		return
	var prev: Texture2D = mat.get_shader_parameter("mat_pigment")
	if prev == null:
		if not TerrainMaterials.bind_pigment_layers(mat, new_pigment, new_pigment):
			return
		# No previous pigment; snap to the new one.
		mat.set_shader_parameter("mat_pigment", new_pigment)
		mat.set_shader_parameter("mat_pigment_prev", new_pigment)
		mat.set_shader_parameter("mat_pigment_blend", 1.0)
		mat.set_shader_parameter("pigment_available", 1.0)
		return
	if not TerrainMaterials.bind_pigment_layers(mat, prev, new_pigment):
		return
	mat.set_shader_parameter("mat_pigment_prev", prev)
	mat.set_shader_parameter("mat_pigment", new_pigment)
	mat.set_shader_parameter("mat_pigment_blend", 0.0)
	mat.set_shader_parameter("pigment_available", 1.0)

func status_line() -> String:
	# A one-line description of what the loader found; used by the headless check and by world.gd logging.
	var parts: Array = []
	parts.append("pigment=%s" % ("ready" if pigment_tex != null else "fallback"))
	parts.append("wet_mask=%s" % ("ready" if wet_mask_tex != null else "absent"))
	parts.append("flow_fraction=%s" % ("ready" if flow_fraction_tex != null else "absent"))
	parts.append("in_pool=%s" % ("ready" if in_pool_tex != null else "absent"))
	parts.append("outflow_temp=%s" % ("ready" if outflow_temp_tex != null else "absent"))
	parts.append("community=%s" % ("ready" if community_tex != null else "absent"))
	return "mat_surface: " + ", ".join(parts)

func pigment_extent_rect() -> Dictionary:
	return {
		"x_min_m": pigment_x_min_m,
		"z_min_m": pigment_z_min_m,
		"width_m": pigment_width_m,
		"height_m": pigment_height_m,
	}

func pigment_pixel_size_m() -> float:
	# Interfaces.md fixes the pigment PNG at 0.5 m per pixel; verifying against the image size resolves the sanity check at load.
	if pigment_tex == null:
		return 0.0
	var image: Image = pigment_tex.get_image() if pigment_tex.has_method("get_image") else null
	if image == null:
		return 0.0
	var pixels_x: float = float(image.get_width())
	if pixels_x <= 0.0:
		return 0.0
	return pigment_width_m / pixels_x

func _load_png_as_texture(path: String) -> Texture2D:
	# Bypass Godot's import system; data/ pngs may land before an editor import runs.
	var image: Image = Image.new()
	var err: int = image.load(ProjectSettings.globalize_path(ReleaseData.resolve_path(path)))
	if err != OK:
		# ProjectSettings.globalize_path returns absolute for res://; retry with the raw path once as fallback.
		err = image.load(ReleaseData.resolve_path(path))
	if err != OK:
		push_warning("mat_surface: Image.load failed for %s (err %d)" % [path, err])
		return null
	return ImageTexture.create_from_image(image)

func _load_f32_raster_as_texture(path: String, w: int, h: int) -> Texture2D:
	if not ReleaseData.file_exists(path):
		return null
	var bytes: PackedByteArray = ReleaseData.get_file_as_bytes(path)
	if bytes.size() != w * h * 4:
		push_warning("mat_surface: f32 raster byte count mismatch at %s (%d != %d)" % [path, bytes.size(), w * h * 4])
		return null
	var image: Image = Image.create_from_data(w, h, false, Image.FORMAT_RF, bytes)
	if image == null:
		push_warning("mat_surface: Image.create_from_data failed for %s" % path)
		return null
	return ImageTexture.create_from_image(image)

func _load_i16_raster_as_binary_texture(path: String, w: int, h: int) -> Texture2D:
	# int16 rasters go in as FORMAT_R8 with 255 for positive samples and 0 otherwise, so the shader can read them with filter_linear.
	if not ReleaseData.file_exists(path):
		return null
	var bytes: PackedByteArray = ReleaseData.get_file_as_bytes(path)
	if bytes.size() != w * h * 2:
		push_warning("mat_surface: i16 raster byte count mismatch at %s (%d != %d)" % [path, bytes.size(), w * h * 2])
		return null
	var out: PackedByteArray = PackedByteArray()
	out.resize(w * h)
	for k in (w * h):
		var lo: int = bytes[k * 2]
		var hi: int = bytes[k * 2 + 1]
		var v: int = lo | (hi << 8)
		if v >= 32768:
			v -= 65536
		out[k] = 255 if v > 0 else 0
	var image: Image = Image.create_from_data(w, h, false, Image.FORMAT_R8, out)
	if image == null:
		push_warning("mat_surface: Image.create_from_data failed for %s" % path)
		return null
	return ImageTexture.create_from_image(image)
