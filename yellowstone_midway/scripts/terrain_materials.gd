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
  mat.set_shader_parameter("detail_x_min_m", float(extent[0]))
  mat.set_shader_parameter("detail_z_min_m", float(extent[1]))
  mat.set_shader_parameter("detail_width_m", float(extent[2]) - float(extent[0]))
  mat.set_shader_parameter("detail_height_m", float(extent[3]) - float(extent[1]))
  mat.set_shader_parameter("naip_detail_available", 1.0)
 else:
  mat.set_shader_parameter("naip_detail_available", 0.0)
 return true

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
