class_name YellowstoneForestFloor
extends RefCounted
## Authored dead wood and illustrative understory instances.

const Lodgepole := preload("res://scripts/lodgepole_library.gd")
const GROUP_NAME := "AuthoredForestFloor"
const SCHEMA := "yellowstone.forest_floor.v1"
const GUILDS := ["grouse_whortleberry", "elk_sedge", "pinegrass", "kinnikinnick"]
const LIMITS := {"understory_card": 4096, "snag": 64, "log": 128}
const BROADLEAF_ROOT := "res://assets/imported/forest_floor/"
const GRASS_TEXTURE := "res://assets/imported/grass_medium_01/textures/grass_medium_01_rgba_1k.png"
const BARK_TEXTURE := "res://assets/imported/pine_tree_01/textures/pine_tree_01_bark_diff_1k.jpg"
const BIN_SIZE_M := 64.0
static var _asset_cache: Dictionary = {}

static func build(parent: Node3D, data_path: String) -> bool:
	var source := read_source(data_path)
	if source.is_empty() or parent == null:
		return false
	var group := Node3D.new()
	group.name = GROUP_NAME
	group.set_meta("source_sha256", FileAccess.get_sha256(data_path))
	group.set_meta("evidence_class", "authored")
	group.set_meta("scientific_acceptance", "not_yet_accepted")
	group.set_meta("uncertainty", "unknown")
	group.set_meta("run_mode", "illustrative")
	group.set_meta("counts", source.counts)
	group.set_meta("dominant_crown_count_included", false)
	group.set_meta("local_species_presence_claim", "none")
	group.set_meta("mortality_class", "authored_illustration")
	group.set_meta("morphology", "illustrative_non_diagnostic")
	group.set_meta("source_context", source.get("sources", []))
	group.set_meta("protected_input_sha256", source.get("protected_input_sha256", {}))
	group.set_meta("log_ground_contact_scope", "source_center")
	var bins: Dictionary = {}
	for record: Dictionary in source.records:
		var position := Vector3(record.position[0], record.position[1], record.position[2])
		var variant := Lodgepole.variation_key(record) if record.kind == "snag" else "0"
		var key := "%s_%s_%s_%d_%d" % [record.kind, str(record.get("guild", "woody")), variant, int(floor(position.x / BIN_SIZE_M)), int(floor(position.z / BIN_SIZE_M))]
		if not bins.has(key):
			bins[key] = []
		bins[key].append(record)
	for key: String in bins:
		var entries: Array = bins[key]
		var first: Dictionary = entries[0]
		var assets := _assets(first)
		if assets.is_empty():
			group.free()
			return _error("Forest-floor assets are unavailable for %s" % key)
		var position := Vector3(first.position[0], first.position[1], first.position[2])
		var center := Vector3((floor(position.x / BIN_SIZE_M) + 0.5) * BIN_SIZE_M, 0.0, (floor(position.z / BIN_SIZE_M) + 0.5) * BIN_SIZE_M)
		for asset: Array in assets:
			var mesh: Mesh = asset[0]
			var instance_buffer := PackedFloat32Array()
			var bounds := AABB()
			var ids: Array[String] = []
			for record: Dictionary in entries:
				var transform := instance_transform(record, str(asset[4]), asset[1])
				transform.origin -= center
				if not transform.is_finite() or transform.basis.determinant() <= 0.0:
					group.free()
					return _error("Forest-floor transform is invalid: %s" % record.id)
				_append_transform(instance_buffer, transform)
				var instance_bounds: AABB = transform * mesh.get_aabb()
				bounds = instance_bounds if ids.is_empty() else bounds.merge(instance_bounds)
				ids.append(record.id)
			var multimesh := MultiMesh.new()
			multimesh.transform_format = MultiMesh.TRANSFORM_3D
			multimesh.mesh = mesh
			multimesh.instance_count = entries.size()
			multimesh.buffer = instance_buffer
			multimesh.custom_aabb = bounds.grow(0.1)
			var node := MultiMeshInstance3D.new()
			node.name = key + "_%s_%d" % [str(asset[4]), int(asset[2])]
			node.position = center
			node.multimesh = multimesh
			node.visibility_range_begin = asset[2]
			node.visibility_range_end = asset[3]
			node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF if first.kind == "understory_card" else GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			node.set_meta("floor_kind", str(first.kind))
			node.set_meta("floor_part", str(asset[4]))
			node.set_meta("guild", str(first.get("guild", "woody")))
			node.set_meta("source_ids", ids)
			node.set_meta("evidence_class", "authored")
			group.add_child(node)
	var previous := parent.get_node_or_null(NodePath(GROUP_NAME))
	if previous != null:
		previous.free()
	parent.add_child(group)
	_set_owner(group, parent)
	return true

static func read_source(data_path: String) -> Dictionary:
	if not FileAccess.file_exists(data_path):
		_error("Forest-floor metadata is missing: %s" % data_path)
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(data_path))
	if not parsed is Dictionary or parsed.get("schema", "") != SCHEMA or parsed.get("status", "") != "authored" or parsed.get("scientific_acceptance", "") != "not_yet_accepted":
		_error("Forest-floor metadata requires authored, unaccepted schema %s" % SCHEMA)
		return {}
	if not parsed.get("records") is Array:
		_error("Forest-floor metadata requires records")
		return {}
	var ids: Dictionary = {}
	var counts := {"understory_card": 0, "snag": 0, "log": 0}
	var choices: Dictionary = {}
	for key: String in ["minimum_valid_fraction", "floor_slope_max_deg", "moderate_cover_low", "moderate_cover_high", "thermal_band_inner_m", "thermal_band_outer_m"]:
		var value: Variant = parsed.get("authoring_choices", {}).get(key)
		if not value is Dictionary or value.get("status", "") != "authored" or not _number(value.get("value")):
			_error("Forest-floor eligibility requires authored choice %s" % key)
			return {}
		choices[key] = float(value.value)
	for value: Variant in parsed.records:
		if not value is Dictionary:
			_error("Forest-floor records require objects")
			return {}
		var record: Dictionary = value
		var id := str(record.get("id", ""))
		var kind := str(record.get("kind", ""))
		if id.is_empty() or ids.has(id) or not LIMITS.has(kind) or record.get("evidence_class", "") != "authored" or record.get("anchor", "") != "ground_contact":
			_error("Forest-floor record requires a unique ID, authored kind, and ground contact: %s" % id)
			return {}
		if not _vector(record.get("position"), false) or not _vector(record.get("size"), true) or not _number(record.get("yaw")):
			_error("Forest-floor position, size, and yaw are invalid: %s" % id)
			return {}
		var support: Variant = record.get("support")
		if not support is Dictionary or not _number(support.get("canopy_cover_fraction")) or not _number(support.get("canopy_valid_fraction")) or not _number(support.get("slope_deg")) or not _number(support.get("apron_distance_m")) or typeof(support.get("thermal_band")) != TYPE_BOOL:
			_error("Forest-floor support fields are invalid: %s" % id)
			return {}
		var cover: float = support.canopy_cover_fraction
		var valid: float = support.canopy_valid_fraction
		if cover < 0.0 or cover > 1.0 or valid <= 0.0 or valid > 1.0 or support.slope_deg < 0.0 or support.slope_deg > 90.0 or support.apron_distance_m < 0.0:
			_error("Forest-floor support fractions or units are invalid: %s" % id)
			return {}
		if not _number(support.get("terrain_y_m")) or not _number(support.get("protected_clearance_m")) or absf(float(record.position[1]) - float(support.terrain_y_m)) > 0.00001:
			_error("Forest-floor terrain anchor or protected clearance is invalid: %s" % id)
			return {}
		if valid < choices.minimum_valid_fraction or cover < choices.moderate_cover_low or support.slope_deg > choices.floor_slope_max_deg:
			_error("Forest-floor support violates its authored eligibility: %s" % id)
			return {}
		if support.thermal_band and (support.apron_distance_m < choices.thermal_band_inner_m or support.apron_distance_m >= choices.thermal_band_outer_m):
			_error("Forest-floor thermal proxy lies outside its authored band: %s" % id)
			return {}
		var radius: float = float(record.size[2]) * 0.5 if kind == "log" else (float(record.crown_radius_m) if kind == "snag" and _number(record.get("crown_radius_m")) else float(record.size[0]) * 0.5)
		if support.protected_clearance_m < radius + 0.5:
			_error("Forest-floor footprint lacks its producer clearance margin: %s" % id)
			return {}
		if kind == "snag":
			if not support.thermal_band or record.get("archetype", "") != "snag" or not _number(record.get("height_m")) or not _number(record.get("dbh_m")) or not _number(record.get("crown_radius_m")) or record.get("crown_ratio") != 0.0:
				_error("Forest-floor snag requires explicit dimensions and authored thermal-band support: %s" % id)
				return {}
			if record.height_m <= 1.3 or record.dbh_m <= 0.0 or record.crown_radius_m <= 0.0 or not is_equal_approx(record.height_m, record.size[1]) or not is_equal_approx(record.dbh_m, record.size[0]) or not is_equal_approx(record.dbh_m, record.size[2]):
				_error("Forest-floor snag dimensions disagree: %s" % id)
				return {}
		elif kind == "log":
			if not is_equal_approx(float(record.size[0]), float(record.size[1])):
				_error("Forest-floor log requires size [diameter,diameter,length]: %s" % id)
				return {}
		elif str(record.get("guild", "")) not in GUILDS or cover > choices.moderate_cover_high or not is_equal_approx(float(record.size[0]), float(record.size[2])):
			_error("Forest-floor understory guild, moderate cover, or square size is invalid: %s" % id)
			return {}
		ids[id] = true
		counts[kind] += 1
		if counts[kind] > LIMITS[kind]:
			_error("Forest-floor authored count exceeds its display budget: %s" % kind)
			return {}
	parsed.counts = counts
	return parsed

static func instance_transform(record: Dictionary, part: String, asset_transform: Transform3D = Transform3D.IDENTITY) -> Transform3D:
	var position := Vector3(record.position[0], record.position[1], record.position[2])
	var size := Vector3(record.size[0], record.size[1], record.size[2])
	var local: Transform3D
	if record.kind == "snag":
		local = Lodgepole.local_transform(record, part)
	elif record.kind == "log":
		local = Transform3D(Basis(Vector3.RIGHT, PI * 0.5) * Basis.from_scale(Vector3(size.x, size.z, size.x)), Vector3(0.0, size.x * 0.5, 0.0))
	else:
		local = Transform3D(Basis.from_scale(size), Vector3.ZERO)
	return Transform3D(Basis(Vector3.UP, float(record.yaw)), position) * local * asset_transform

static func _assets(record: Dictionary) -> Array:
	var variant := Lodgepole.variation_key(record) if record.kind == "snag" else "0"
	var key := "%s:%s:%s" % [record.kind, str(record.get("guild", "woody")), variant]
	if not _asset_cache.has(key):
		var assets := _make_assets(record)
		if assets.is_empty():
			return []
		_asset_cache[key] = assets
	return _asset_cache[key]

static func _make_assets(record: Dictionary) -> Array:
	if record.kind == "snag":
		return Lodgepole.load_assets("snag", int(Lodgepole.variation_key(record)))
	if record.kind == "log":
		if not ResourceLoader.exists(BARK_TEXTURE):
			return []
		var material := StandardMaterial3D.new()
		material.albedo_color = Color(0.64, 0.60, 0.48)
		material.albedo_texture = load(BARK_TEXTURE)
		material.roughness = 0.94
		var mesh := CylinderMesh.new()
		mesh.height = 1.0
		mesh.top_radius = 0.45
		mesh.bottom_radius = 0.5
		mesh.radial_segments = 10
		mesh.rings = 1
		mesh.material = material
		return [[mesh, Transform3D.IDENTITY, 0.0, 600.0, "Log"]]
	var texture: Texture2D
	if str(record.guild) in ["grouse_whortleberry", "kinnikinnick"]:
		var path := BROADLEAF_ROOT + "broadleaf.png"
		var metadata: Variant = JSON.parse_string(FileAccess.get_file_as_string(BROADLEAF_ROOT + "forest_floor_assets.json"))
		if not metadata is Dictionary or metadata.get("schema", "") != "yellowstone.forest_floor_assets.v1" or metadata.get("files", []).size() != 1 or str(metadata.files[0].sha256) != FileAccess.get_sha256(path):
			return []
		var image := Image.new()
		if image.load_png_from_buffer(FileAccess.get_file_as_bytes(path)) != OK:
			return []
		texture = ImageTexture.create_from_image(image)
	else:
		if not ResourceLoader.exists(GRASS_TEXTURE):
			return []
		texture = load(GRASS_TEXTURE)
	var material := ShaderMaterial.new()
	material.shader = load("res://shaders/foliage.gdshader")
	material.set_shader_parameter("albedo_texture", texture)
	material.set_shader_parameter("use_texture", true)
	material.set_shader_parameter("tint", Vector3(0.86, 0.92, 0.82))
	material.set_shader_parameter("wind_strength", 0.045)
	return [[_card_mesh(3, material), Transform3D.IDENTITY, 0.0, 35.0, "Understory"], [_card_mesh(2, material), Transform3D.IDENTITY, 35.0, 110.0, "Understory"]]

static func _card_mesh(planes: int, material: Material) -> ArrayMesh:
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	for plane: int in planes:
		var rotation := Basis(Vector3.UP, PI * plane / planes)
		var normal := rotation * Vector3.BACK
		var offset := vertices.size()
		for point: Vector3 in [Vector3(-0.5, 0.0, 0.0), Vector3(0.5, 0.0, 0.0), Vector3(0.5, 1.0, 0.0), Vector3(-0.5, 1.0, 0.0)]:
			vertices.append(rotation * point)
			normals.append(normal)
		uvs.append_array(PackedVector2Array([Vector2(0, 1), Vector2(1, 1), Vector2(1, 0), Vector2(0, 0)]))
		indices.append_array(PackedInt32Array([offset, offset + 2, offset + 1, offset, offset + 3, offset + 2]))
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, material)
	return mesh

static func _append_transform(buffer: PackedFloat32Array, transform: Transform3D) -> void:
	buffer.append_array(PackedFloat32Array([transform.basis.x.x, transform.basis.y.x, transform.basis.z.x, transform.origin.x, transform.basis.x.y, transform.basis.y.y, transform.basis.z.y, transform.origin.y, transform.basis.x.z, transform.basis.y.z, transform.basis.z.z, transform.origin.z]))

static func _set_owner(node: Node, owner_node: Node) -> void:
	node.owner = owner_node
	for child: Node in node.get_children():
		_set_owner(child, owner_node)

static func _number(value: Variant) -> bool:
	return (typeof(value) == TYPE_INT or typeof(value) == TYPE_FLOAT) and is_finite(float(value))

static func _vector(value: Variant, positive: bool) -> bool:
	if not value is Array or value.size() != 3:
		return false
	for component: Variant in value:
		if not _number(component) or (positive and float(component) <= 0.0):
			return false
	return true

static func _error(message: String) -> bool:
	push_error(message)
	return false
