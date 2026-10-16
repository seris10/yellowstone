extends SceneTree

const Materials = preload("res://scripts/terrain_materials.gd")
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
 var report: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(Materials.COLOR_MIP_MANIFEST))
 for relative: String in report.entries:
  var entry: Dictionary = report.entries[relative]
  var image: Image = Materials._load_color_image("res://" + relative)
  check(image != null, "Color mip load: " + relative)
  if image == null:
   continue
  check(image.get_width() == int(entry.width) and image.get_height() == int(entry.height), "Dimensions: " + relative)
  check(image.get_format() == Image.FORMAT_RGBA8, "RGBA8 format: " + relative)
  check(image.get_data() == FileAccess.get_file_as_bytes("res://" + str(entry.path)), "Unchanged encoded bytes: " + relative)
  check(image.get_mipmap_count() == entry.levels.size() - 1, "Complete levels: " + relative)
  for level: Dictionary in entry.levels:
   check(image.get_mipmap_offset(int(level.level)) == int(level.offset), "Level offset: " + relative)
 var material := ShaderMaterial.new()
 material.shader = load("res://shaders/thermal_apron.gdshader")
 check(Materials.bind_ground_material(material), "Production texture bindings")
 for parameter: String in Materials.LAYER_PATHS:
  var layers: Texture2DArray = material.get_shader_parameter(parameter)
  check(layers != null and layers.get_layers() == Materials.LAYER_PATHS[parameter].size(), "Array layers: " + parameter)
 for parameter: String in Materials.COLOR_TEXTURE_NAMES:
  var texture: Texture2D = material.get_shader_parameter(parameter)
  check(texture != null, "Color texture: " + parameter)
 var result := {"schema": "yellowstone.color_mip_validation.v1", "checks": checks, "failures": failures,
  "manifest_sha256": FileAccess.get_sha256(Materials.COLOR_MIP_MANIFEST),
  "loader_sha256": FileAccess.get_sha256("res://scripts/terrain_materials.gd"),
  "godot": Engine.get_version_info().string, "scope": "Native buffer layout, byte-preserving load and production material bindings; appearance and performance require native world review"}
 for argument: String in OS.get_cmdline_user_args():
  if argument.begins_with("--receipt="):
   var file := FileAccess.open(argument.trim_prefix("--receipt="), FileAccess.WRITE)
   file.store_string(JSON.stringify(result, "  ") + "\n")
 print("COLOR_MIP_VALIDATION ", JSON.stringify(result))
 quit(0 if failures.is_empty() else 1)

func check(condition: bool, description: String) -> void:
 checks += 1
 if not condition:
  failures.append(description)
