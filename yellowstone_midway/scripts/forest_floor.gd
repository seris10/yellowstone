class_name YellowstoneForestFloor
extends RefCounted
## Authored dead wood and illustrative understory instances.

const Geometry := preload("res://scripts/forest_floor_geometry.gd")
const Lodgepole := preload("res://scripts/lodgepole_library.gd")
const GROUP_NAME := "AuthoredForestFloor"
const SCHEMA := "yellowstone.forest_floor.v1"
const GUILDS := ["grouse_whortleberry", "elk_sedge", "pinegrass", "kinnikinnick"]
const LIMITS := {"understory_card": 18000, "snag": 64, "log": 1600, "litter": 24000}
const BARK_NORMAL := "res://assets/imported/pine_tree_01/textures/pine_tree_01_bark_nor_gl_1k.jpg"
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
	group.set_meta("log_ground_contact_scope", "sampled_profile_with_bounded_clearance")
	var litter_area := Vector2.ZERO
	var litter_projected_square_area := 0.0
	var bins: Dictionary = {}
	for record: Dictionary in source.records:
		if record.kind == "litter":
			litter_projected_square_area += float(record.size[0]) * float(record.size[0]) * float(record.ground_normal[1])
		var position := Vector3(record.position[0], record.position[1], record.position[2])
		var variant := Lodgepole.variation_key(record) if record.kind == "snag" else "0"
		var key := "%s_%s_%s_%d_%d" % [record.kind, str(record.get("guild", "woody")), variant, int(floor(position.x / BIN_SIZE_M)), int(floor(position.z / BIN_SIZE_M))]
		if not bins.has(key):
			bins[key] = []
		bins[key].append(record)
	for lod: int in 2:
		litter_area[lod] = Geometry.litter_bed_area(lod == 0) * litter_projected_square_area
	group.set_meta("litter_bed_nominal_horizontal_area_sum_m2", [litter_area.x, litter_area.y])
	group.set_meta("litter_bed_area_scope", "authored_summed_projected_footprints_before_overlap_edge_feather_and_occlusion")
	group.set_meta("litter_bed_footprint_fraction", [Geometry.litter_bed_area(true), Geometry.litter_bed_area(false)])
	group.set_meta("litter_field_cover_fraction", "unknown")
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
				if first.kind in ["understory_card", "litter"]:
					instance_bounds = instance_bounds.expand(transform.origin)
				bounds = instance_bounds if ids.is_empty() else bounds.merge(instance_bounds)
				ids.append(record.id)
			var multimesh := MultiMesh.new()
			multimesh.transform_format = MultiMesh.TRANSFORM_3D
			multimesh.mesh = mesh
			multimesh.instance_count = entries.size()
			multimesh.buffer = instance_buffer
			multimesh.custom_aabb = bounds.grow(0.30)
			var node := MultiMeshInstance3D.new()
			node.name = key + "_%s_%d" % [str(asset[4]), int(asset[2])]
			node.position = center
			node.multimesh = multimesh
			node.visibility_range_begin = float(asset[2]) if first.kind == "log" else maxf(0.0, float(asset[2]) - 8.0)
			node.visibility_range_end = asset[3]
			if first.kind in ["understory_card", "litter"]:
				var padding := multimesh.custom_aabb.size.length() * 0.5
				node.visibility_range_begin = maxf(0.0, float(asset[2]) - 8.0 - padding)
				node.visibility_range_end = float(asset[3]) + padding
				node.set_meta("root_visibility_range", [float(asset[2]), float(asset[3])])
				node.set_meta("batch_visibility_padding_m", padding)
			node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF if first.kind in ["understory_card", "litter"] else GeometryInstance3D.SHADOW_CASTING_SETTING_ON
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
	var counts := {"understory_card": 0, "snag": 0, "log": 0, "litter": 0}
	var choices: Dictionary = {}
	for key: String in ["minimum_valid_fraction", "floor_slope_max_deg", "moderate_cover_low", "moderate_cover_high", "thermal_band_inner_m", "thermal_band_outer_m", "maximum_log_gap_m", "maximum_floor_plane_error_m"]:
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
		if not _vector(record.get("ground_normal"), false) or not _number(record.get("plane_error_m")):
			_error("Forest-floor terrain normal is missing: %s" % id)
			return {}
		var normal := Vector3(record.ground_normal[0], record.ground_normal[1], record.ground_normal[2])
		if normal.y <= 0.0 or absf(normal.length() - 1.0) > 0.00001 or record.plane_error_m < 0.0 or (kind in ["understory_card", "litter"] and record.plane_error_m > choices.maximum_floor_plane_error_m):
			_error("Forest-floor terrain plane is invalid: %s" % id)
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
			if not is_equal_approx(float(record.size[0]), float(record.size[1])) or not _log_contact_valid(record, choices.maximum_log_gap_m):
				_error("Forest-floor log requires size [diameter,diameter,length]: %s" % id)
				return {}
		elif kind == "understory_card" and (str(record.get("guild", "")) not in GUILDS or cover > choices.moderate_cover_high or not is_equal_approx(float(record.size[0]), float(record.size[2]))):
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
		var ends: Array = record.axis_end_positions
		var a := Vector3(ends[0][0], ends[0][1], ends[0][2])
		var b := Vector3(ends[1][0], ends[1][1], ends[1][2])
		var axis := (b - a).normalized()
		var across := axis.cross(Vector3.UP).normalized()
		var up := across.cross(axis).normalized()
		return Transform3D(Basis(across * size.x, axis * a.distance_to(b), up * size.x), (a + b) * 0.5) * asset_transform
	else:
		var normal := Vector3(record.ground_normal[0], record.ground_normal[1], record.ground_normal[2]).normalized()
		var across := Vector3.RIGHT.slide(normal).normalized()
		var normal_rotation := Basis(across, normal, across.cross(normal))
		if record.kind == "litter":
			size.y = size.x
		return Transform3D(normal_rotation * Basis(Vector3.UP, float(record.yaw)) * Basis.from_scale(size), position) * asset_transform
	return Transform3D(Basis(Vector3.UP, float(record.yaw)), position) * local * asset_transform

static func _log_contact_valid(record: Dictionary, maximum_gap: float) -> bool:
	if not record.get("axis_end_positions") is Array or record.axis_end_positions.size() != 2 or not record.get("end_positions") is Array or record.end_positions.size() != 2:
		return false
	for point: Variant in record.axis_end_positions + record.end_positions:
		if not _vector(point, false):
			return false
	if not record.get("contact_clearance_m") is Array or record.contact_clearance_m.size() < 9:
		return false
	var minimum := INF
	for gap: Variant in record.contact_clearance_m:
		if not _number(gap) or float(gap) < -0.00000001 or float(gap) > maximum_gap + 0.00000001:
			return false
		minimum = minf(minimum, float(gap))
	var a: Array = record.axis_end_positions[0]
	var b: Array = record.axis_end_positions[1]
	var dx := float(b[0]) - float(a[0])
	var dy := float(b[1]) - float(a[1])
	var dz := float(b[2]) - float(a[2])
	var horizontal := sqrt(dx * dx + dz * dz)
	if horizontal < 0.01 or not is_equal_approx(horizontal, float(record.size[2])) or not record.get("ground_profile_m") is Array or record.ground_profile_m.size() != record.contact_clearance_m.size():
		return false
	var vertical_radius := float(record.size[0]) * 0.5 * horizontal / sqrt(dx * dx + dy * dy + dz * dz)
	for index: int in record.ground_profile_m.size():
		var point: Variant = record.ground_profile_m[index]
		if not point is Array or point.size() != 2 or not _number(point[0]) or not _number(point[1]):
			return false
		var t := float(point[0]) / horizontal + 0.5
		var gap := lerpf(float(a[1]), float(b[1]), t) - vertical_radius - float(point[1])
		if t < -0.000001 or t > 1.000001 or absf(gap - float(record.contact_clearance_m[index])) > 0.00001:
			return false
	var center_dx := (float(a[0]) + float(b[0])) * 0.5 - float(record.position[0])
	var center_dz := (float(a[2]) + float(b[2])) * 0.5 - float(record.position[2])
	if sqrt(center_dx * center_dx + center_dz * center_dz) > 0.00001:
		return false
	return minimum < 0.000001

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
		var isolated: Array = []
		for asset: Array in Lodgepole.load_assets("snag", int(Lodgepole.variation_key(record))):
			var entry: Array = asset.duplicate()
			var mesh: Mesh = asset[0].duplicate()
			for surface: int in mesh.get_surface_count():
				var material: Material = mesh.surface_get_material(surface).duplicate()
				if material is ShaderMaterial:
					material.set_shader_parameter("instance_lod", false)
				if mesh is PrimitiveMesh:
					mesh.material = material
				else:
					mesh.surface_set_material(surface, material)
			entry[0] = mesh
			isolated.append(entry)
		return isolated
	if record.kind == "log":
		if not ResourceLoader.exists(BARK_TEXTURE) or not ResourceLoader.exists(BARK_NORMAL):
			return []
		var material := ShaderMaterial.new()
		material.shader = load("res://shaders/forest_floor_wood.gdshader")
		material.set_shader_parameter("bark_albedo", load(BARK_TEXTURE))
		material.set_shader_parameter("bark_normal", load(BARK_NORMAL))
		return [[Geometry.log_mesh(true, material), Transform3D.IDENTITY, 0.0, 85.0, "Log"], [Geometry.log_mesh(false, material), Transform3D.IDENTITY, 85.0, 600.0, "Log"]]
	var assets: Array = []
	for detailed: bool in [true, false]:
		var begin := 0.0 if detailed else 28.0
		var end := 28.0 if detailed else (65.0 if record.kind == "litter" else 110.0)
		var material := ShaderMaterial.new()
		material.shader = load("res://shaders/forest_floor_foliage.gdshader")
		material.set_shader_parameter("flexibility", 0.0 if record.kind == "litter" else 0.018)
		material.set_shader_parameter("fade_begin", begin)
		material.set_shader_parameter("fade_end", end)
		if record.kind == "litter":
			material.set_shader_parameter("use_litter_texture", true)
			material.set_shader_parameter("litter_albedo", load("res://assets/textures/forrest_ground_03_diff_1k.jpg"))
			material.set_shader_parameter("litter_normal", load("res://assets/textures/forrest_ground_03_nor_gl_1k.jpg"))
		var mesh := Geometry.litter(detailed, material) if record.kind == "litter" else Geometry.plant(str(record.guild), detailed, material)
		assets.append([mesh, Transform3D.IDENTITY, begin, end, "Litter" if record.kind == "litter" else "Understory"])
	return assets

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
