class_name YellowstoneLodgepoleLibrary
extends RefCounted
## Authored lodgepole meshes and independent tree dimensions.

const ASSET_ROOT := "res://assets/imported/lodgepole/"
const METADATA_PATH := ASSET_ROOT + "lodgepole_metadata.json"
const ARCHETYPES := ["dense", "edge", "open", "sapling", "snag"]
const PARTS := ["Bole", "Branches", "NeedleCards", "Billboard"]
const LOD_RANGES := [[0.0, 18.0], [18.0, 65.0], [65.0, 180.0], [180.0, 3000.0]]
static var _metadata_cache: Dictionary = {}
static var _asset_cache: Dictionary = {}
static var _texture_cache: Dictionary = {}

static func archetype(record: Dictionary) -> String:
	var requested := str(record.get("archetype", ""))
	if requested in ARCHETYPES:
		return requested
	if str(record.get("kind", "")) == "snag":
		return "snag"
	if _numeric(record.get("height_m")) and float(record.height_m) <= 8.0:
		return "sapling"
	return "edge" if int(variation_key(record)) == 0 else "dense"

static func variation_key(record: Dictionary) -> String:
	if record.has("variant"):
		var value: Variant = record.variant
		if typeof(value) == TYPE_INT:
			return str(posmod(int(value), 4))
		if typeof(value) == TYPE_FLOAT and is_finite(value) and value == floor(value):
			return str(posmod(int(value), 4))
		if typeof(value) == TYPE_STRING and value.is_valid_int():
			return str(posmod(value.to_int(), 4))
	var identity := str(record.get("variation_key", record.get("stable_id", record.get("id", "0"))))
	return str(identity.sha256_text().substr(0, 8).hex_to_int() % 4)

static func metadata() -> Dictionary:
	if not _metadata_cache.is_empty():
		return _metadata_cache
	if not FileAccess.file_exists(METADATA_PATH):
		push_error("Lodgepole metadata is missing: %s" % METADATA_PATH)
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(METADATA_PATH))
	if not parsed is Dictionary or parsed.get("schema", "") != "yellowstone.lodgepole_assets.v1":
		push_error("Lodgepole metadata requires schema yellowstone.lodgepole_assets.v1")
		return {}
	if parsed.get("lod_ranges_m", []) != LOD_RANGES:
		push_error("Lodgepole metadata has unsupported LOD distance ranges")
		return {}
	var architecture_path := ASSET_ROOT + "architecture_library.json"
	if not FileAccess.file_exists(architecture_path) or FileAccess.get_sha256(architecture_path) != str(parsed.get("architecture_library_sha256", "")):
		push_error("Lodgepole architecture graph differs from its metadata SHA-256")
		return {}
	_metadata_cache = parsed
	return _metadata_cache

static func load_assets(name: String, view: int = 0) -> Array:
	if not name in ARCHETYPES:
		push_error("Unknown lodgepole archetype: %s" % name)
		return []
	var key := "%s:%d" % [name, posmod(view, 4)]
	if _asset_cache.has(key):
		return _asset_cache[key]
	var info := metadata()
	if info.is_empty():
		return []
	var assets: Array = []
	for level in range(3):
		var path := ASSET_ROOT + "%s_lod%d.gltf" % [name, level]
		if not ResourceLoader.exists(path):
			push_error("Lodgepole mesh is missing or unimported: %s" % path)
			return []
		var packed: Variant = load(path)
		if not packed is PackedScene:
			push_error("Lodgepole mesh requires an imported PackedScene: %s" % path)
			return []
		var source: Node = packed.instantiate()
		var parts: Array = []
		var valid := _collect_meshes(source, Transform3D.IDENTITY, parts, level)
		source.free()
		var expected := ["Bole", "Branches"] if name == "snag" else ["Bole", "Branches", "NeedleCards"]
		var found: Array = []
		for part: Array in parts:
			found.append(part[4])
		found.sort()
		expected.sort()
		if not valid or found != expected:
			push_error("Lodgepole %s LOD%d requires mesh parts %s; found %s" % [name, level, expected, found])
			return []
		assets.append_array(parts)
	var billboard := _billboard(info, name, posmod(view, 4))
	if billboard.is_empty():
		return []
	assets.append(billboard)
	_asset_cache[key] = assets
	return assets

static func load_architecture(name: String, variant: int, lod: int = 0) -> Array:
	if not name in ARCHETYPES:
		push_error("Unknown lodgepole archetype: %s" % name)
		return []
	if lod < 0 or lod > 2:
		push_error("Architecture LOD must be 0, 1 or 2")
		return []
	var key := "architecture:%s:%d:%d" % [name, posmod(variant, 4), lod]
	if _asset_cache.has(key):
		return _asset_cache[key]
	var files: Variant = metadata().get("near_variant_files", {}).get(name)
	if not files is Array or files.size() != 4:
		push_error("Lodgepole %s requires four near architecture variants" % name)
		return []
	var filename := str(files[posmod(variant, 4)])
	if lod > 0:
		var selected: Variant = metadata().get("architecture_lod_files", {}).get(name, [])
		if not selected is Array or selected.size() != 4:
			push_error("Rebuild the library to supply variant-specific middle LODs")
			return []
		filename = str(selected[posmod(variant, 4)][lod])
	if filename.get_file() != filename or filename.get_extension() != "gltf":
		push_error("Lodgepole architecture path requires a glTF basename")
		return []
	var path := ASSET_ROOT + filename
	if not ResourceLoader.exists(path):
		push_error("Lodgepole architecture is missing or unimported: " + path)
		return []
	var source: Node = load(path).instantiate()
	var parts: Array = []
	var valid := _collect_meshes(source, Transform3D.IDENTITY, parts, lod)
	source.free()
	if not valid:
		return []
	_asset_cache[key] = parts
	return parts

static func display_dimensions(record: Dictionary) -> Dictionary:
	var name := archetype(record)
	var base: Dictionary = metadata().get("archetypes", {}).get(name, {})
	if base.is_empty():
		return {}
	var identity := str(record.get("stable_id", record.get("id", "tree")))
	var height := _positive_number(record.get("height_m", float(base.height_m) * float(record.get("scale", 1.0))), "height_m", identity)
	var core := _positive_number(record.get("crown_radius_m", record.get("crown_r_m", float(base.crown_radius_m) * height / float(base.height_m))), "crown_radius_m", identity)
	var dbh := _positive_number(record.get("dbh_m", float(base.dbh_m) * height / float(base.height_m)), "dbh_m", identity)
	var ratio := _ratio(record.get("crown_ratio", base.crown_ratio), name == "snag", "crown_ratio", identity)
	if not is_finite(height + core + dbh + ratio):
		return {}
	if name == "snag":
		return {"height_m": height, "dbh_m": dbh, "crown_radius_m": core, "crown_ratio": ratio, "source_core_radius_m": core, "source_crown_ratio": ratio, "envelope_class": "authored_snag"}
	var model: Dictionary = metadata().get("display_envelope_model", {})
	var photo: Dictionary = metadata().get("photo_display", {})
	if model.is_empty() or photo.is_empty():
		push_error("Lodgepole metadata requires full-crown display models")
		return {}
	var width_range: Array = photo.width_height_ratio_range
	var fraction := float((identity + ":display_envelope").sha256_text().substr(0, 8).hex_to_int()) / 4294967295.0
	var photo_ratio := lerpf(float(width_range[0]), float(width_range[1]), fraction)
	var predicted := bechtold_crown_radius_m(dbh) if record.has("dbh_m") else NAN
	var envelope := predicted if is_finite(predicted) else height * photo_ratio * 0.5
	var policy: String = str(record.get("display_crown_policy", photo.get("default_crown_policy", "preserve_source")))
	if policy not in ["preserve_source", "photo_floor"]:
		push_error("Unknown display crown policy: " + policy)
		return {}
	var display_ratio: float = maxf(ratio, float(photo.live_crown_ratio_floor)) if policy == "photo_floor" else ratio
	return {"height_m": height, "dbh_m": dbh, "crown_radius_m": maxf(core, envelope), "crown_ratio": display_ratio, "crown_ratio_policy": policy, "source_core_radius_m": core, "source_crown_ratio": ratio, "envelope_prediction_m": envelope, "image_width_height_ratio": photo_ratio, "envelope_class": "transferred_bechtold_dbh" if is_finite(predicted) else str(photo.evidence_class), "local_error": "unknown"}

static func bechtold_crown_radius_m(dbh_m: float) -> float:
	if not is_finite(dbh_m) or dbh_m <= 0.0:
		return NAN
	var model: Dictionary = metadata().get("display_envelope_model", {})
	if model.is_empty():
		return NAN
	var diameter := dbh_m / 0.0254
	if diameter < float(model.dbh_range_in[0]) or diameter > float(model.dbh_range_in[1]):
		return NAN
	var c: Array = model.coefficients
	var width: float = float(c[0]) + float(c[1]) * diameter + float(c[2]) * diameter * diameter
	return width * 0.3048 * 0.5 if width > 0.0 else NAN

static func cutout_texture(filename: String) -> Texture2D:
	if _texture_cache.has(filename):
		return _texture_cache[filename]
	var image := cutout_image(filename)
	if image == null:
		return null
	var texture := ImageTexture.create_from_image(image)
	texture.resource_name = filename
	_texture_cache[filename] = texture
	return texture

static func cutout_image(filename: String) -> Image:
	var entry: Variant = metadata().get("cutout_mips", {}).get(filename)
	if not entry is Dictionary or metadata().get("billboard_mips_pending", true):
		push_error("Lodgepole coverage-preserving mips are missing: " + filename)
		return null
	var path := ASSET_ROOT + str(entry.path)
	if str(entry.path).get_file() != str(entry.path) or not FileAccess.file_exists(path) or FileAccess.get_sha256(path) != str(entry.sha256) or FileAccess.get_sha256(ASSET_ROOT + filename) != str(entry.source_sha256):
		push_error("Lodgepole cutout mip source or buffer differs: " + filename)
		return null
	var bytes := FileAccess.get_file_as_bytes(path)
	if bytes.size() != int(entry.bytes):
		push_error("Lodgepole cutout mip buffer size differs")
		return null
	var image := Image.create_from_data(int(entry.width),int(entry.height),true,Image.FORMAT_RGBA8,bytes)
	if image.is_empty() or not image.has_mipmaps():
		push_error("Lodgepole cutout image requires complete mip levels")
		return null
	return image

static func bind_cutout_materials(assets: Array, frozen_wind: bool = false) -> bool:
	for asset: Array in assets:
		var mesh: Mesh = asset[0]
		if not mesh is ArrayMesh:
			continue
		for surface: int in range(mesh.get_surface_count()):
			var original: Material = mesh.surface_get_material(surface)
			if original is StandardMaterial3D and original.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR:
				var texture := cutout_texture(original.albedo_texture.resource_path.get_file())
				if texture == null:
					return false
				var leaves := ShaderMaterial.new()
				leaves.shader = load("res://shaders/foliage.gdshader")
				leaves.set_shader_parameter("albedo_texture", texture)
				leaves.set_shader_parameter("alpha_cutoff", 0.32)
				leaves.set_shader_parameter("use_texture", true)
				leaves.set_shader_parameter("tint", Vector3(0.86, 0.92, 0.82))
				leaves.set_shader_parameter("wind_strength", 0.14)
				if frozen_wind:
					leaves.set_shader_parameter("wind_vector", Vector2.ZERO)
				mesh.surface_set_material(surface, leaves)
	return true

static func bind_instance_lods(asset: Array) -> void:
	var mesh: Mesh = asset[0]
	for surface: int in mesh.get_surface_count():
		var original: Material = mesh.surface_get_material(surface)
		var material: ShaderMaterial
		if original is StandardMaterial3D:
			material = ShaderMaterial.new()
			material.shader = load("res://shaders/tree_bark.gdshader")
			material.set_shader_parameter("albedo_texture", original.albedo_texture)
			material.set_shader_parameter("bark_color", original.albedo_color)
			material.set_shader_parameter("bark_roughness", original.roughness)
		else:
			material = original as ShaderMaterial
		assert(material != null, "Tree LOD requires a supported material")
		material.set_shader_parameter("instance_lod", true)
		material.set_shader_parameter("lod_begin_m", float(asset[2]))
		material.set_shader_parameter("lod_end_m", float(asset[3]))
		if mesh is PrimitiveMesh:
			mesh.material = material
		else:
			mesh.surface_set_material(surface, material)

static func _collect_meshes(node: Node, parent: Transform3D, result: Array, level: int) -> bool:
	var transform: Transform3D = parent * node.transform if node is Node3D else parent
	var valid := true
	if node is MeshInstance3D:
		var part := str(node.name)
		if not part in PARTS or part == "Billboard" or node.mesh == null:
			push_error("Unsupported lodgepole mesh part: %s" % node.name)
			return false
		result.append([node.mesh, transform, LOD_RANGES[level][0], LOD_RANGES[level][1], part])
	for child: Node in node.get_children():
		valid = _collect_meshes(child, transform, result, level) and valid
	return valid

static func load_billboard(name: String, variant: int) -> Array:
	var key := "impostor:%s:%d" % [name, posmod(variant, 4)]
	if _asset_cache.has(key):
		return _asset_cache[key]
	var entries: Array = metadata().get("variant_billboards", {}).get(name, [])
	if entries.size() != 4:
		push_error("Variant-specific impostors are missing for " + name)
		return []
	var entry: Dictionary = entries[posmod(variant, 4)]
	var material := ShaderMaterial.new()
	material.shader = load("res://shaders/tree_impostor.gdshader")
	for view: int in range(4):
		var texture := cutout_texture(str(entry.views[view]))
		if texture == null:
			return []
		material.set_shader_parameter("view_%d" % view, texture)
	var mesh := QuadMesh.new()
	mesh.size = Vector2(float(entry.width_m), float(entry.height_m))
	mesh.material = material
	var asset := [mesh, Transform3D(Basis.IDENTITY, Vector3(0.0, float(entry.center_y_m), 0.0)), LOD_RANGES[3][0], LOD_RANGES[3][1], "Billboard"]
	_asset_cache[key] = asset
	return asset

static func load_billboard_batch(name: String, build_textures: bool = true) -> Array:
	var key := "impostor_batch:%s:%s" % [name, str(build_textures)]
	if _asset_cache.has(key):
		return _asset_cache[key]
	var entries: Array = metadata().get("variant_billboards", {}).get(name, [])
	if entries.size() != 4:
		push_error("Batched impostors require four complete variants: " + name)
		return []
	var images: Array[Image] = []
	var frame: Dictionary = entries[0]
	for entry: Dictionary in entries:
		if entry.width_m != frame.width_m or entry.height_m != frame.height_m or entry.center_y_m != frame.center_y_m or entry.views.size() != 4:
			push_error("Batched impostors require matching physical frames: " + name)
			return []
		if build_textures:
			for filename: String in entry.views:
				var image := cutout_image(filename)
				if image == null:
					return []
				images.append(image)
	var material := ShaderMaterial.new()
	material.shader = load("res://shaders/tree_impostor.gdshader")
	material.set_meta("impostor_form", name)
	if build_textures:
		var layers := Texture2DArray.new()
		if layers.create_from_images(images) != OK:
			push_error("Batched impostor texture layers disagree: " + name)
			return []
		material.set_shader_parameter("view_layers", layers)
	material.set_shader_parameter("use_view_layers", true)
	var mesh := QuadMesh.new()
	mesh.size = Vector2(float(frame.width_m), float(frame.height_m))
	mesh.material = material
	var asset := [mesh, Transform3D(Basis.IDENTITY, Vector3(0.0, float(frame.center_y_m), 0.0)), LOD_RANGES[3][0], LOD_RANGES[3][1], "Billboard"]
	_asset_cache[key] = asset
	return asset

static func bind_billboard_batch(material: ShaderMaterial) -> bool:
	if not material.has_meta("impostor_form"):
		return false
	var bound: Texture2DArray = material.get_shader_parameter("view_layers")
	if bound != null and bound.get_layers() == 16:
		return true
	var asset := load_billboard_batch(str(material.get_meta("impostor_form")))
	if asset.is_empty():
		return false
	material.set_shader_parameter("view_layers", asset[0].material.get_shader_parameter("view_layers"))
	return true

static func _billboard(info: Dictionary, name: String, view: int) -> Array:
	var entry: Variant = info.get("billboards", {}).get(name, null)
	if not entry is Dictionary or entry.get("views", []).size() != 4:
		push_error("Lodgepole %s requires four billboard views in metadata" % name)
		return []
	if entry.get("azimuth_degrees", []) != [0.0, 90.0, 180.0, 270.0]:
		push_error("Lodgepole %s billboard azimuths must be 0, 90, 180, 270 degrees" % name)
		return []
	var width := _positive_number(entry.get("width_m"), "billboard width_m", name)
	var height := _positive_number(entry.get("height_m"), "billboard height_m", name)
	var center: Variant = entry.get("center_y_m")
	if not _numeric(center) or not is_finite(float(center)) or not is_finite(width) or not is_finite(height):
		push_error("Lodgepole %s billboard center_y_m must be finite" % name)
		return []
	var filename := str(entry.views[view])
	if filename.get_file() != filename or filename.get_extension() != "png":
		push_error("Lodgepole %s billboard view requires a PNG basename: %s" % [name, filename])
		return []
	var path := ASSET_ROOT + filename
	if not ResourceLoader.exists(path):
		push_error("Lodgepole billboard is missing or unimported: %s" % path)
		return []
	var texture: Variant = cutout_texture(filename)
	if not texture is Texture2D:
		push_error("Lodgepole billboard requires a Texture2D: %s" % path)
		return []
	var material := StandardMaterial3D.new()
	material.albedo_texture = texture
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	material.alpha_scissor_threshold = 0.32
	material.billboard_mode = BaseMaterial3D.BILLBOARD_FIXED_Y
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var mesh := QuadMesh.new()
	mesh.size = Vector2(width, height)
	mesh.material = material
	return [mesh, Transform3D(Basis.IDENTITY, Vector3(0.0, float(center), 0.0)), LOD_RANGES[3][0], LOD_RANGES[3][1], "Billboard"]

static func local_transform(record: Dictionary, part: String) -> Transform3D:
	if not part in PARTS:
		push_error("Unknown lodgepole transform part: %s" % part)
		return _invalid_transform()
	var name := archetype(record)
	var base: Variant = metadata().get("archetypes", {}).get(name, null)
	if not base is Dictionary:
		push_error("Lodgepole metadata lacks dimensions for %s" % name)
		return _invalid_transform()
	var base_height := _positive_number(base.get("height_m"), "authored height_m", name)
	var base_dbh := _positive_number(base.get("dbh_m"), "authored dbh_m", name)
	var base_radius := _positive_number(base.get("crown_radius_m"), "authored crown_radius_m", name)
	var base_ratio := _ratio(base.get("crown_ratio"), name == "snag", "authored crown_ratio", name)
	var identity := str(record.get("stable_id", record.get("id", name)))
	var height: float
	if record.has("height_m"):
		height = _positive_number(record.height_m, "height_m", identity)
	else:
		height = base_height * _positive_number(record.get("scale", 1.0), "scale", identity)
	var height_scale := height / base_height
	var display := display_dimensions(record)
	if display.is_empty():
		return _invalid_transform()
	var radius := float(display.crown_radius_m)
	var dbh := float(display.dbh_m)
	var ratio := float(display.crown_ratio)
	if not is_finite(base_height + base_dbh + base_radius + base_ratio + height + radius + dbh + ratio):
		return _invalid_transform()
	var size := Vector3(radius / base_radius, height_scale, radius / base_radius)
	var origin := Vector3.ZERO
	if part == "Bole":
		var diameter: float = _bole_diameter(name, 1.3 / height_scale) if record.has("dbh_m") else base_dbh
		if record.has("dbh_m") and height <= 1.3:
			push_error("Lodgepole %s height_m must exceed breast height for explicit dbh_m" % identity)
			return _invalid_transform()
		if not is_finite(diameter) or diameter <= 0.0:
			return _invalid_transform()
		size.x = dbh / diameter
		size.z = dbh / diameter
	elif part != "Billboard" and name != "snag":
		size.y = height * ratio / (base_height * base_ratio)
		origin.y = height * (1.0 - ratio) - base_height * (1.0 - base_ratio) * size.y
	return Transform3D(Basis.from_scale(size), origin)

static func _bole_diameter(name: String, source_height: float) -> float:
	for row: Dictionary in metadata().get("lods", []):
		if str(row.get("archetype", "")) != name or int(row.get("lod", -1)) != 0:
			continue
		var profile: Array = row.get("bole_profile_m", [])
		for index: int in range(1, profile.size()):
			var left: Array = profile[index - 1]
			var right: Array = profile[index]
			if source_height >= float(left[0]) and source_height <= float(right[0]):
				var weight: float = (source_height - float(left[0])) / (float(right[0]) - float(left[0]))
				return 2.0 * lerpf(float(left[1]), float(right[1]), weight)
	push_error("Lodgepole %s bole profile does not cover breast-height section" % name)
	return NAN

static func _numeric(value: Variant) -> bool:
	return typeof(value) == TYPE_INT or typeof(value) == TYPE_FLOAT

static func _positive_number(value: Variant, field: String, identity: String) -> float:
	if _numeric(value) and is_finite(float(value)) and float(value) > 0.0:
		return float(value)
	push_error("Lodgepole %s %s must be a finite positive number; got %s" % [identity, field, str(value)])
	return NAN

static func _ratio(value: Variant, snag: bool, field: String, identity: String) -> float:
	if _numeric(value) and is_finite(float(value)):
		var ratio := float(value)
		if (snag and ratio == 0.0) or (not snag and ratio > 0.0 and ratio <= 1.0):
			return ratio
	push_error("Lodgepole %s %s requires %s; got %s" % [identity, field, "0 for snag" if snag else "a number in (0, 1]", str(value)])
	return NAN

static func _invalid_transform() -> Transform3D:
	return Transform3D(Basis.from_scale(Vector3(NAN, NAN, NAN)), Vector3(NAN, NAN, NAN))
