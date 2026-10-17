class_name MidwayTerrainMaterials
extends RefCounted
## Shared geographic and PBR terrain bindings.

const ReleaseData = preload("res://scripts/release_data.gd")
const COLOR_MIP_MANIFEST := "res://assets/textures/color_mips/color_mips.json"
const COLOR_LAYER_NAMES := ["geography_layers", "ground_color_layers"]
const COLOR_TEXTURE_NAMES := ["rock_albedo", "spring_apron_display"]

const LAYER_PATHS: Dictionary = {
 "geography_layers": ["res://assets/textures/midway_macro.jpg", "res://references/midway_orthophoto_detail.jpg", "res://assets/textures/mapped_surface_detail.png"],
 "ground_color_layers": ["res://assets/textures/forrest_ground_03_diff_1k.jpg", "res://assets/textures/rocky_trail_diff_1k.jpg", "res://assets/textures/forest_ground_04_diff_1k.jpg"],
 "ground_normal_layers": ["res://assets/textures/forrest_ground_03_nor_gl_1k.jpg", "res://assets/textures/rocky_trail_nor_gl_1k.jpg", "res://assets/textures/mineral_surface.png", "res://assets/textures/forest_ground_04_nor_gl_1k.jpg"],
 "ground_arm_layers": ["res://assets/textures/forrest_ground_03_arm_1k.jpg", "res://assets/textures/rocky_trail_arm_1k.jpg", "res://assets/textures/forest_ground_04_arm_1k.jpg"],
}
const TEXTURE_PATHS: Dictionary = {
 "rock_albedo": "res://assets/textures/rock_boulder_dry_diff_1k.jpg",
 "biome_map": "res://assets/textures/habitat_mask.png",
 "detail_map": "res://assets/textures/detail.png",
 "trail_mask": "res://assets/textures/trail_mask.png",
 "snow_mask": "res://assets/textures/snow_map.png",
 "spring_apron_display": "res://assets/textures/prismatic_apron_display.png",
 "spring_terrace_detail": "res://assets/textures/prismatic_terrace_detail.png",
}
const MIDWAY_SQUARE_MIN_M := -2048.0
const MIDWAY_SQUARE_SIZE_M := 4096.0
const FRAME_META := "ground_frame"
## Layer minima and extents in meters.
const VEC2_LAYERS: Dictionary = {
 "geography": ["geography_origin_m", "geography_extent_m"],
 "biome": ["biome_origin_m", "biome_extent_m"],
 "trail": ["trail_origin_m", "trail_extent_m"],
 "snow": ["snow_origin_m", "snow_extent_m"],
 "water": ["water_level_origin_m", "water_level_extent_m"],
}
## Scalar layer fields: x minimum, z minimum, width, height.
const SCALAR_LAYERS: Dictionary = {
 "detail": ["detail_x_min_m", "detail_z_min_m", "detail_width_m", "detail_height_m"],
 "extent": ["extent_x_min_m", "extent_z_min_m", "extent_width_m", "extent_height_m"],
 "pigment": ["pigment_x_min_m", "pigment_z_min_m", "pigment_width_m", "pigment_height_m"],
 "outflow": ["outflow_x_min_m", "outflow_z_min_m", "outflow_width_m", "outflow_height_m"],
}
const CORE_CUT_LAYER := "core_cut"
## Shifted scalar uniforms map to an axis (x=0, z=1) and default.
const SHIFTED_SCALARS: Dictionary = {
 "detail_x_min_m": [0, -640.0], "detail_z_min_m": [1, -640.0],
 "extent_x_min_m": [0, 0.0], "extent_z_min_m": [1, 0.0],
 "pigment_x_min_m": [0, -640.0], "pigment_z_min_m": [1, -640.0],
 "outflow_x_min_m": [0, -640.0], "outflow_z_min_m": [1, -640.0],
 "core_cut_x_min_m": [0, 0.0], "core_cut_x_max_m": [0, 0.0],
 "core_cut_z_min_m": [1, 0.0], "core_cut_z_max_m": [1, 0.0],
}
const TILE_DEFAULTS: Dictionary = {"soil_tile_width_m": 3.15, "forest_tile_width_m": 2.0, "trail_tile_width_m": 2.0, "detail_normal_tile_m": 0.42, "rock_tile_width_m": 1.8}
## Repeat phases map to a period, rotation flag, and scale.
const REPEAT_PHASES: Array = [
 ["soil_phase", "soil_tile_width_m", false, 1.0],
 ["soil_rotated_phase", "soil_tile_width_m", true, 0.23],
 ["forest_phase", "forest_tile_width_m", false, 1.0],
 ["forest_rotated_phase", "forest_tile_width_m", true, 1.0],
 ["trail_phase", "trail_tile_width_m", false, 1.0],
 ["variation_phase", 67.0, false, 1.0],
 ["mineral_phase", 4.0, false, 1.0],
 ["mineral_meso_phase", 19.0, true, 1.0],
 ["fine_detail_phase", 1.8, false, 1.0],
 ["detail_normal_phase", "detail_normal_tile_m", false, 1.0],
 ["detail_normal_fine_phase", "detail_normal_tile_m", true, 4.7619], # fine octave scale 1/0.21
 ["rock_tri_phase", "rock_tile_width_m", false, 1.0],
]
static var _textures: Dictionary = {}
static var _layers: Dictionary = {}
static var _detail_header: Dictionary = {}
static var _detail_decoded: bool = false
static var _color_mips: Dictionary = {}

static func _load_color_image(path: String) -> Image:
 if _color_mips.is_empty():
  var parsed: Variant = JSON.parse_string(ReleaseData.get_file_as_string(COLOR_MIP_MANIFEST))
  if not parsed is Dictionary or parsed.get("schema") != "yellowstone.color_mips.v1":
   push_error("terrain_materials: missing linear-light color manifest")
   return null
  _color_mips = parsed.get("entries", {})
 var entry: Variant = _color_mips.get(path.trim_prefix("res://"))
 if not entry is Dictionary or not str(entry.path).begins_with("assets/textures/color_mips/") or ".." in str(entry.path).split("/"):
  push_error("terrain_materials: missing color mip entry " + path)
  return null
 var buffer_path: String = "res://" + str(entry.path)
 if ReleaseData.get_sha256(path) != str(entry.source_sha256) or ReleaseData.get_sha256(buffer_path) != str(entry.sha256):
  push_error("terrain_materials: color source or mip buffer differs " + path)
  return null
 var bytes := ReleaseData.get_file_as_bytes(buffer_path)
 if bytes.size() != int(entry.bytes):
  push_error("terrain_materials: color mip byte size differs " + path)
  return null
 var image := Image.create_from_data(int(entry.width), int(entry.height), true, Image.FORMAT_RGBA8, bytes)
 if image.is_empty() or not image.has_mipmaps():
  push_error("terrain_materials: incomplete color mip chain " + path)
  return null
 return image

static func _load_image(path: String) -> Image:
 path = ReleaseData.resolve_path(path)
 if path.is_empty() or not FileAccess.file_exists(path):
  return null
 if ResourceLoader.exists(path):
  var texture: Texture2D = load(path) as Texture2D
  if texture != null:
   var image: Image = texture.get_image()
   if image.is_compressed():
    image.decompress()
   image.clear_mipmaps()
   return image
 var image := Image.new()
 if image.load(ProjectSettings.globalize_path(path)) == OK:
  return image
 return null

static func bind_ground_material(mat: ShaderMaterial) -> bool:
 if mat == null:
  return false
 for uniform_name: String in LAYER_PATHS:
  if not _layers.has(uniform_name):
   var images: Array[Image] = []
   for path: String in LAYER_PATHS[uniform_name]:
    var image: Image = _load_color_image(path) if uniform_name in COLOR_LAYER_NAMES else _load_image(path)
    if uniform_name == "geography_layers" and images.size() == 1:
     if image == null or image.get_size() != images[0].get_size():
      image = images[0].duplicate()
      _detail_decoded = false
     else:
      _detail_decoded = true
    if image == null:
     push_error("terrain_materials: missing PBR map %s" % path)
     return false
    if uniform_name not in COLOR_LAYER_NAMES:
     image.convert(Image.FORMAT_RGBA8)
     image.generate_mipmaps()
    images.append(image)
   var layers := Texture2DArray.new()
   if layers.create_from_images(images) != OK:
    push_error("terrain_materials: incompatible texture layers %s" % uniform_name)
    return false
   _layers[uniform_name] = layers
  mat.set_shader_parameter(uniform_name, _layers[uniform_name])
 for uniform_name: String in TEXTURE_PATHS:
  if not _textures.has(uniform_name):
   var path: String = TEXTURE_PATHS[uniform_name]
   var image: Image = _load_color_image(path) if uniform_name in COLOR_TEXTURE_NAMES else _load_image(path)
   if image == null:
    if uniform_name != "snow_mask" and uniform_name != "naip_detail":
     push_error("terrain_materials: missing ground texture %s" % path)
     return false
    image = Image.create(1, 1, false, Image.FORMAT_RGBA8)
    image.fill(Color.BLACK)
   if uniform_name not in COLOR_TEXTURE_NAMES:
    image.generate_mipmaps()
   _textures[uniform_name] = ImageTexture.create_from_image(image)
  mat.set_shader_parameter(uniform_name, _textures[uniform_name])
 mat.set_shader_parameter("soil_tile_width_m", 3.15)
 mat.set_shader_parameter("forest_tile_width_m", 2.0)
 mat.set_shader_parameter("trail_tile_width_m", 2.0)
 mat.set_shader_parameter("detail_normal_tile_m", 0.42)
 mat.set_shader_parameter("rock_tile_width_m", 1.8)
 mat.set_shader_parameter("macro_color_strength", 0.28)
 var detail_path := "res://references/midway_orthophoto_detail.json"
 if _detail_header.is_empty() and FileAccess.file_exists(detail_path):
  var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(detail_path))
  if parsed is Dictionary:
   _detail_header = parsed
 var extent: Variant = _detail_header.get("local_extent_xz_m")
 var valid_extent: bool = extent is Array and extent.size() == 4
 if valid_extent:
  for value in extent:
   if not typeof(value) in [TYPE_INT, TYPE_FLOAT] or not is_finite(float(value)):
    valid_extent = false
  if valid_extent and (float(extent[2]) <= float(extent[0]) or float(extent[3]) <= float(extent[1])):
   valid_extent = false
 if valid_extent and _detail_decoded:
  set_layer_rect(mat, "detail", float(extent[0]), float(extent[1]), float(extent[2]) - float(extent[0]), float(extent[3]) - float(extent[1]))
  mat.set_shader_parameter("naip_detail_available", 1.0)
 else:
  mat.set_shader_parameter("naip_detail_available", 0.0)
 var state: Dictionary = _frame_state(mat)
 for layer: String in VEC2_LAYERS:
  if not state.absolute.has(VEC2_LAYERS[layer][0]):
   set_layer_rect(mat, layer, MIDWAY_SQUARE_MIN_M, MIDWAY_SQUARE_MIN_M, MIDWAY_SQUARE_SIZE_M, MIDWAY_SQUARE_SIZE_M)
 _write_repeat_phases(mat, _declared_uniforms(mat))
 return true

## Return the absolute render origin in x and z meters.
static func get_render_origin(mat: ShaderMaterial) -> Array:
 return (_frame_state(mat).origin as Array).duplicate()

## Set layer bounds in absolute meters and upload rebased coordinates.
static func set_layer_rect(mat: ShaderMaterial, layer: String, x_min_m: float, z_min_m: float, width_m: float, height_m: float) -> bool:
 var state: Dictionary = _frame_state(mat)
 if VEC2_LAYERS.has(layer):
  var names: Array = VEC2_LAYERS[layer]
  _put_vec2(mat, state, names[0], x_min_m, z_min_m)
  mat.set_shader_parameter(names[1], Vector2(width_m, height_m))
 elif SCALAR_LAYERS.has(layer):
  var names: Array = SCALAR_LAYERS[layer]
  _put_scalar(mat, state, names[0], x_min_m)
  _put_scalar(mat, state, names[1], z_min_m)
  mat.set_shader_parameter(names[2], width_m)
  mat.set_shader_parameter(names[3], height_m)
 elif layer == CORE_CUT_LAYER:
  _put_scalar(mat, state, "core_cut_x_min_m", x_min_m)
  _put_scalar(mat, state, "core_cut_x_max_m", x_min_m + width_m)
  _put_scalar(mat, state, "core_cut_z_min_m", z_min_m)
  _put_scalar(mat, state, "core_cut_z_max_m", z_min_m + height_m)
 else:
  push_error("terrain_materials: unknown layer " + layer)
  return false
 return true

## Rebase layer bounds and repeat phases after shifting the hierarchy.
static func set_render_origin(mat: ShaderMaterial, origin_x_m: float, origin_z_m: float) -> void:
 var state: Dictionary = _frame_state(mat)
 var declared: Dictionary = _declared_uniforms(mat)
 _adopt_external_writes(mat, state, declared)
 state.origin = [origin_x_m, origin_z_m]
 for name: String in state.absolute:
  if SHIFTED_SCALARS.has(name):
   _put_scalar(mat, state, name, state.absolute[name])
  else:
   _put_vec2(mat, state, name, state.absolute[name][0], state.absolute[name][1])
 _write_repeat_phases(mat, declared)

## Follow the frame render origin after each rebase.
static func follow_frame(frame: Object, mat: ShaderMaterial) -> void:
 set_render_origin(mat, frame.origin_x_m, frame.origin_z_m)
 frame.rebased.connect(_on_frame_rebased.bind(weakref(frame), mat))

## Return the rotated, scaled repeat phase modulo one texture period.
static func repeat_phase(origin_x_m: float, origin_z_m: float, period_m: float, rotated: bool, scale: float) -> Vector2:
 var x: float = origin_x_m / period_m
 var z: float = origin_z_m / period_m
 if rotated:
  var c: float = _f32(0.8)
  var s: float = _f32(0.6)
  var rotated_x: float = c * x + s * z
  z = -s * x + c * z
  x = rotated_x
 var k: float = _f32(scale)
 return Vector2(fposmod(x * k, 1.0), fposmod(z * k, 1.0))

static func _f32(value: float) -> float:
 return PackedFloat32Array([value])[0]

static func _on_frame_rebased(_delta: Vector3, frame_ref: WeakRef, mat: ShaderMaterial) -> void:
 var frame: Object = frame_ref.get_ref()
 if frame != null:
  set_render_origin(mat, frame.origin_x_m, frame.origin_z_m)

static func _frame_state(mat: ShaderMaterial) -> Dictionary:
 if not mat.has_meta(FRAME_META):
  mat.set_meta(FRAME_META, {"origin": [0.0, 0.0], "absolute": {}, "written": {}})
 return mat.get_meta(FRAME_META)

static func _declared_uniforms(mat: ShaderMaterial) -> Dictionary:
 var declared: Dictionary = {}
 if mat.shader != null:
  for entry: Dictionary in mat.shader.get_shader_uniform_list():
   declared[entry.name] = true
 return declared

static func _put_scalar(mat: ShaderMaterial, state: Dictionary, name: String, absolute_m: float) -> void:
 var relative_m: float = absolute_m - float(state.origin[SHIFTED_SCALARS[name][0]])
 state.absolute[name] = absolute_m
 state.written[name] = relative_m
 mat.set_shader_parameter(name, relative_m)

static func _put_vec2(mat: ShaderMaterial, state: Dictionary, name: String, absolute_x_m: float, absolute_z_m: float) -> void:
 var relative := Vector2(absolute_x_m - float(state.origin[0]), absolute_z_m - float(state.origin[1]))
 state.absolute[name] = [absolute_x_m, absolute_z_m]
 state.written[name] = relative
 mat.set_shader_parameter(name, relative)

## Treat external rectangle writes as coordinates relative to the render origin.
static func _adopt_external_writes(mat: ShaderMaterial, state: Dictionary, declared: Dictionary) -> void:
 for name: String in SHIFTED_SCALARS:
  if not declared.has(name):
   continue
  var current: Variant = mat.get_shader_parameter(name)
  if current == null:
   if state.absolute.has(name):
    continue
   current = SHIFTED_SCALARS[name][1]
  elif state.written.has(name) and float(current) == float(state.written[name]):
   continue
  state.absolute[name] = float(current) + float(state.origin[SHIFTED_SCALARS[name][0]])
 for layer: String in VEC2_LAYERS:
  var name: String = VEC2_LAYERS[layer][0]
  var current: Variant = mat.get_shader_parameter(name)
  if current is Vector2 and state.written.has(name) and current != state.written[name]:
   state.absolute[name] = [float(current.x) + float(state.origin[0]), float(current.y) + float(state.origin[1])]

static func _write_repeat_phases(mat: ShaderMaterial, declared: Dictionary) -> void:
 var origin: Array = _frame_state(mat).origin
 for entry: Array in REPEAT_PHASES:
  if not declared.has(entry[0]):
   continue
  var period_m: float
  if entry[1] is String:
   var tile: Variant = mat.get_shader_parameter(entry[1])
   period_m = float(tile) if tile != null else float(TILE_DEFAULTS[entry[1]])
  else:
   period_m = float(entry[1])
  mat.set_shader_parameter(entry[0], repeat_phase(float(origin[0]), float(origin[1]), period_m, entry[2], entry[3]))

static func bind_pigment_layers(mat: ShaderMaterial, previous: Texture2D, current: Texture2D) -> bool:
 var images: Array[Image] = []
 for texture in [previous if previous != null else current, current]:
  var image: Image
  if texture != null:
   image = texture.get_image()
   if image.is_compressed():
    image.decompress()
   image.clear_mipmaps()
   image.convert(Image.FORMAT_RGBA8)
  else:
   image = Image.create(1, 1, false, Image.FORMAT_RGBA8)
   image.fill(Color.TRANSPARENT)
  image.generate_mipmaps()
  images.append(image)
 if images[0].get_size() != images[1].get_size():
  push_error("terrain_materials: pigment layer dimensions disagree.")
  return false
 var layers: Texture2DArray = mat.get_shader_parameter("pigment_layers") as Texture2DArray
 if layers == null or layers.get_width() != images[0].get_width() or layers.get_height() != images[0].get_height():
  layers = Texture2DArray.new()
  if layers.create_from_images(images) != OK:
   return false
 else:
  layers.update_layer(images[0], 0)
  layers.update_layer(images[1], 1)
 mat.set_shader_parameter("pigment_layers", layers)
 return true

static func swap_pigment_layers(mat: ShaderMaterial, current: Texture2D) -> bool:
 var layers: Texture2DArray = mat.get_shader_parameter("pigment_layers") as Texture2DArray
 var previous: Texture2D = current
 if layers != null:
  previous = ImageTexture.create_from_image(layers.get_layer_data(1))
 return bind_pigment_layers(mat, previous, current)
