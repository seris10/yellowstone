class_name YellowstoneCanopySurface
extends RefCounted
## Observed residual canopy with an authored continuous display skin.

const Lodgepole = preload("res://scripts/lodgepole_library.gd")
const Support = preload("res://scripts/canopy_support.gd")
const SCHEMA := "yellowstone.unresolved_canopy_render.v1"
const TEXTURE_PATH := "res://assets/imported/lodgepole/needle_supported.png"
const SHADER_PATH := "res://shaders/canopy_surface.gdshader"
const GROUP_NAME := "AuthoredCanopySurface"
const DISPLAY_SMOOTHING_RADIUS_M := 5.0
const CLUSTER_LIVE_CROWN_RATIO := 0.70
const CLUSTER_TOP_WIDTH_RATIO := 0.22
const CLUSTER_UNIT_DEPTH_M := 1.0
const SHOOT_CARD_SIZE_M := 0.40
const PATCH_DEPTH_CAP_M := 2.0
const CLUSTER_LODS := [[0.0, 45.0, 64], [45.0, 120.0, 16], [120.0, 350.0, 0]]
const CLUSTER_TILE_M := 64.0
const ARTIFACTS := ["canopy_top_scene_y", "ground_scene_y", "unresolved_cells", "cover_fraction", "valid_fraction", "unresolved_render_mask", "valid_support"]

static func build(parent: Node3D, data_path: String, tile_size_m: float = 128.0, support_records: Array = []) -> bool:
	var source := read_source(data_path)
	if source.is_empty() or parent == null:
		return false
	var cell_size: float = source.cell_size_m
	_prepare_surface(source)
	if not is_finite(tile_size_m) or tile_size_m < cell_size or not is_equal_approx(tile_size_m / cell_size, round(tile_size_m / cell_size)):
		return _error("Canopy tile size requires a positive whole number of cells")
	if not ResourceLoader.exists(TEXTURE_PATH) or not ResourceLoader.exists(SHADER_PATH):
		return _error("Canopy material requires the authored needle texture and canopy shader")
	var material := ShaderMaterial.new()
	material.shader = load(SHADER_PATH)
	var needle_texture := Lodgepole.cutout_texture(TEXTURE_PATH.get_file())
	if needle_texture == null:
		return false
	material.set_shader_parameter("albedo_texture", needle_texture)
	material.set_shader_parameter("coverage_texture", source.mask_texture)
	material.set_shader_parameter("support_texture", source.support_texture)
	material.set_shader_parameter("mask_origin_m", Vector2(source.first_cell_x_m - cell_size * 0.5, source.first_cell_z_m - cell_size * 0.5))
	material.set_shader_parameter("mask_extent_m", Vector2(source.width * cell_size, source.height * cell_size))
	material.set_shader_parameter("needle_repeat_m", SHOOT_CARD_SIZE_M)
	material.set_shader_parameter("cluster_mode", false)
	var group := Node3D.new()
	group.name = GROUP_NAME
	group.set_meta("source_sha256", FileAccess.get_sha256(data_path))
	group.set_meta("source_artifacts", source.artifacts)
	group.set_meta("evidence_class", "derived_not_field_validated")
	group.set_meta("representation", "observed_residual_coverage_continuous_skin")
	group.set_meta("height_aggregation", "source_2m_cell_mean")
	group.set_meta("height_aggregation_class", "authored_display_aggregation")
	group.set_meta("top_elevation_class", "measured_derived_display_smoothed")
	group.set_meta("ground_elevation_class", "measured_derived")
	group.set_meta("footprint_class", "measured_derived_native_mask")
	group.set_meta("shell_thickness_class", "authored_display_geometry")
	group.set_meta("shell_thickness_m", source.highres_mask_cell_size_m)
	group.set_meta("surface_smoothing", "coverage_weighted_radial_mean_of_observed_canopy_elevations")
	group.set_meta("surface_smoothing_class", "authored_display_interpolation")
	group.set_meta("surface_smoothing_uncertainty", "unknown")
	group.set_meta("display_smoothing_radius_m", DISPLAY_SMOOTHING_RADIUS_M)
	group.set_meta("display_smoothing_radius_class", "authored_display_parameter")
	group.set_meta("masked_inactive_geometry", "ground_supported_skin_with_zero_coverage")
	group.set_meta("closure", "continuous_layer_outer_extent")
	group.set_meta("near_fade_begin_m", 0.0)
	group.set_meta("near_fade_end_m", 0.0)
	group.set_meta("near_fade_class", "authored_display_lod")
	group.set_meta("skin_fade_m", [180.0, 260.0])
	group.set_meta("cluster_live_crown_ratio", CLUSTER_LIVE_CROWN_RATIO)
	group.set_meta("cluster_depth_rule", "min(0.70*(source_top_y-source_ground_y),2m)")
	group.set_meta("cluster_base_rule", "source_top_y-min(0.70*(source_top_y-source_ground_y),2m)")
	group.set_meta("cluster_depth_class", "authored_display_volume")
	group.set_meta("cluster_top_width_ratio", CLUSTER_TOP_WIDTH_RATIO)
	group.set_meta("cluster_yaw_class", "seeded_authored_display_orientation")
	group.set_meta("cluster_radius_m", cell_size / sqrt(2.0))
	group.set_meta("cluster_geometry_class", "authored_display_geometry")
	group.set_meta("cluster_representation", "connected_metric_shoots_on_grounded_display_scaffolds")
	group.set_meta("support_geometry_class", "authored_display_geometry")
	group.set_meta("support_root_rule", "rendered_bole_centerline_or_matched_source_ground_minus_0.04m")
	group.set_meta("patch_depth_cap_m", PATCH_DEPTH_CAP_M)
	group.set_meta("cluster_lods", CLUSTER_LODS)
	group.set_meta("shoot_card_size_m", SHOOT_CARD_SIZE_M)
	group.set_meta("cluster_triangles", [328, 88, 14])
	group.set_meta("cluster_top_class", "source_2m_cell_mean")
	group.set_meta("cluster_rendered_coverage", "unknown")
	group.set_meta("cluster_count_claim", "display_cells_only")
	group.set_meta("near_mask_rule", "whole_metric_shoot_center_sample")
	group.set_meta("near_mask_support_radius_m", 0.20)
	group.set_meta("stem_count_claim", "none")
	group.set_meta("uncertainty", "unknown")
	group.set_meta("scientific_acceptance", "not_yet_accepted")
	var tile_cells := int(round(tile_size_m / cell_size))
	var active_cells := 0
	var represented_area := 0.0
	for row: int in range(0, source.height, tile_cells):
		for column: int in range(0, source.width, tile_cells):
			var result := _tile(source, column, row, tile_cells, material)
			if result.is_empty():
				continue
			var node: MeshInstance3D = result.node
			group.add_child(node)
			active_cells += int(result.active_cells)
			represented_area += float(result.represented_area_m2)
	group.set_meta("active_cells", active_cells)
	group.set_meta("represented_area_m2", represented_area)
	group.set_meta("cell_size_m", cell_size)
	group.set_meta("tile_size_m", tile_size_m)
	_build_clusters(group, source, material, Support.prepare(support_records))
	var previous := parent.get_node_or_null(NodePath(GROUP_NAME))
	if previous != null:
		previous.free()
	parent.add_child(group)
	_set_owner(group, parent)
	return true

static func _build_clusters(group: Node3D, source: Dictionary, skin_material: ShaderMaterial, hosts: Dictionary) -> void:
	var material: ShaderMaterial = skin_material.duplicate()
	material.set_shader_parameter("cluster_mode", true)
	var meshes: Array = []
	for lod: Array in CLUSTER_LODS:
		var lod_material: ShaderMaterial = material.duplicate()
		lod_material.set_shader_parameter("near_shoot_mode", int(lod[2]) > 0)
		meshes.append(_shoot_mesh(source.cell_size_m / sqrt(2.0), int(lod[2]), lod_material) if int(lod[2]) > 0 else _cluster_mesh(source.cell_size_m / sqrt(2.0), lod_material))
	var bins: Dictionary = {}
	var origin := Vector2(source.first_cell_x_m, source.first_cell_z_m)
	for row: int in source.height:
		for column: int in source.width:
			var index: int = row * source.width + column
			if source.unresolved_cells[index] == 0:
				continue
			var position: Vector2 = origin + Vector2(column, row) * source.cell_size_m
			var key := Vector2i(int(floor(position.x / CLUSTER_TILE_M)), int(floor(position.y / CLUSTER_TILE_M)))
			if not bins.has(key):
				bins[key] = []
			bins[key].append(index)
	var total := 0
	var attached := 0
	for key: Vector2i in bins:
		var center := Vector3((key.x + 0.5) * CLUSTER_TILE_M, 0.0, (key.y + 0.5) * CLUSTER_TILE_M)
		var buffer := PackedFloat32Array()
		var bounds := AABB()
		var indices := PackedInt32Array()
		for index: int in bins[key]:
			var column: int = index % source.width
			var row: int = int(index / source.width)
			var position := Vector3(source.first_cell_x_m + column * source.cell_size_m, source.canopy_top_scene_y[index], source.first_cell_z_m + row * source.cell_size_m) - center
			var depth: float = (source.canopy_top_scene_y[index] - source.ground_scene_y[index]) * CLUSTER_LIVE_CROWN_RATIO
			var seed: int = (index * 1103515245 + 12345) & 0x7fffffff
			var yaw := float(seed) / 2147483647.0 * TAU
			var basis := Basis(Vector3.UP, yaw).scaled_local(Vector3(1.0, depth / CLUSTER_UNIT_DEPTH_M, 1.0))
			var transform := Transform3D(basis, position)
			buffer.append_array(PackedFloat32Array([basis.x.x, basis.y.x, basis.z.x, position.x, basis.x.y, basis.y.y, basis.z.y, position.y, basis.x.z, basis.y.z, basis.z.z, position.z]))
			var connection := Support.connection(position + center, source.ground_scene_y[index], hosts)
			var root: Vector3 = basis.inverse() * (connection.point - position - center)
			buffer.append_array(PackedFloat32Array([root.x, root.y, root.z, 1.0 if connection.attached else 0.0]))
			attached += 1 if connection.attached else 0
			var instance_bounds := transform * AABB(Vector3(-source.cell_size_m, -1.0 / CLUSTER_LIVE_CROWN_RATIO, -source.cell_size_m), Vector3(source.cell_size_m * 2.0, 1.0 / CLUSTER_LIVE_CROWN_RATIO, source.cell_size_m * 2.0))
			instance_bounds = instance_bounds.merge(AABB(connection.point - center - Vector3.ONE * 0.1, Vector3.ONE * 0.2))
			bounds = instance_bounds if indices.is_empty() else bounds.merge(instance_bounds)
			indices.append(index)
		for lod: int in CLUSTER_LODS.size():
			var multimesh := MultiMesh.new()
			multimesh.transform_format = MultiMesh.TRANSFORM_3D
			multimesh.use_custom_data = true
			multimesh.mesh = meshes[lod]
			multimesh.instance_count = indices.size()
			multimesh.buffer = buffer
			multimesh.custom_aabb = bounds.grow(0.25)
			var node := MultiMeshInstance3D.new()
			node.name = "CanopyClusters_%d_%d_lod%d" % [key.x, key.y, lod]
			node.position = center
			node.multimesh = multimesh
			node.visibility_range_begin = CLUSTER_LODS[lod][0]
			node.visibility_range_end = CLUSTER_LODS[lod][1]
			node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			node.set_meta("canopy_part", "source_grounded_needle_volume")
			node.set_meta("source_indices", indices)
			node.set_meta("cluster_lod", lod)
			node.set_meta("shoot_count", CLUSTER_LODS[lod][2])
			node.set_meta("display_count", indices.size())
			group.add_child(node)
		total += indices.size()
	group.set_meta("cluster_display_count", total)
	group.set_meta("cluster_tile_size_m", CLUSTER_TILE_M)
	group.set_meta("patches_attached_to_rendered_boles", attached)
	group.set_meta("patches_with_grounded_display_support", total - attached)

static func _shoot_mesh(radius: float, count: int, material: Material) -> ArrayMesh:
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var anchors := PackedVector2Array()
	var colors := PackedColorArray()
	var indices := PackedInt32Array()
	for shoot: int in count:
		var quantized: float = floor((float(shoot) + 0.5) / count * 255.0)
		var encoded: float = quantized / 255.0
		var fraction: float = encoded
		var angle := float(shoot) * 2.3999632297
		var reach: float = radius * (0.28 + 0.72 * fraction) * sqrt(fmod(float(shoot) * 0.61803398875 + 0.37, 1.0))
		var center := Vector3(cos(angle) * reach, -fraction, sin(angle) * reach)
		for plane: int in range(2):
			var yaw := angle + plane * PI * 0.5
			var across := Vector3(cos(yaw), 0.0, sin(yaw))
			var normal := Vector3.UP.cross(across).normalized()
			var half := SHOOT_CARD_SIZE_M * 0.5
			var offset := vertices.size()
			vertices.append_array(PackedVector3Array([center - across * half + Vector3.UP * half, center + across * half + Vector3.UP * half, center + across * half - Vector3.UP * half, center - across * half - Vector3.UP * half]))
			normals.append_array(PackedVector3Array([normal, normal, normal, normal]))
			uvs.append_array(PackedVector2Array([Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)]))
			for vertex: int in 4:
				anchors.append(Vector2(center.x, center.z))
			colors.append_array(PackedColorArray([Color(encoded, 0, 0, 1), Color(encoded, 0, 0, 1), Color(encoded, 0, 0, 1), Color(encoded, 0, 0, 1)]))
			indices.append_array(PackedInt32Array([offset, offset + 2, offset + 1, offset, offset + 3, offset + 2]))
		var across := Vector3(-sin(angle), 0.0, cos(angle)) * 0.014
		var start := Vector3(0.0, -fraction - 0.04, 0.0)
		var offset := vertices.size()
		vertices.append_array(PackedVector3Array([start - across, start + across, center]))
		var normal := (vertices[offset + 1] - vertices[offset]).cross(vertices[offset + 2] - vertices[offset]).normalized()
		normals.append_array(PackedVector3Array([normal, normal, normal]))
		uvs.append_array(PackedVector2Array([Vector2.ZERO, Vector2.ZERO, Vector2(0.0, SHOOT_CARD_SIZE_M * (fraction - 1.0))]))
		anchors.append_array(PackedVector2Array([Vector2.ZERO, Vector2.ZERO, Vector2.ZERO]))
		colors.append_array(PackedColorArray([Color(0, 1, 0, 1), Color(0, 1, 0, 1), Color(0, 1, 0, 1)]))
		indices.append_array(PackedInt32Array([offset, offset + 2, offset + 1]))
	_add_support_stem(vertices, normals, uvs, colors, indices)
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	anchors.resize(vertices.size())
	arrays[Mesh.ARRAY_TEX_UV2] = anchors
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, material)
	return mesh

static func _add_support_stem(vertices: PackedVector3Array, normals: PackedVector3Array, uvs: PackedVector2Array, colors: PackedColorArray, indices: PackedInt32Array) -> void:
	for plane: int in 2:
		var across := Vector3.RIGHT if plane == 0 else Vector3.FORWARD
		var normal := Vector3.UP.cross(across)
		var offset := vertices.size()
		vertices.append_array(PackedVector3Array([-across * 0.006, across * 0.006, across * 0.025 - Vector3.UP * 1.05, -across * 0.025 - Vector3.UP * 1.05]))
		normals.append_array(PackedVector3Array([normal, normal, normal, normal]))
		uvs.append_array(PackedVector2Array([Vector2.ZERO, Vector2.ZERO, Vector2.ZERO, Vector2.ZERO]))
		colors.append_array(PackedColorArray([Color(0, 1, 0, 1), Color(0, 1, 0, 1), Color(0, 1, 0, 1), Color(0, 1, 0, 1)]))
		indices.append_array(PackedInt32Array([offset, offset + 2, offset + 1, offset, offset + 3, offset + 2]))
	for plane: int in 2:
		var across := Vector3.RIGHT if plane == 0 else Vector3.FORWARD
		var normal := Vector3.UP.cross(across)
		var offset := vertices.size()
		vertices.append_array(PackedVector3Array([-across * 0.006, across * 0.006, across * 0.035 - Vector3.UP / CLUSTER_LIVE_CROWN_RATIO, -across * 0.035 - Vector3.UP / CLUSTER_LIVE_CROWN_RATIO]))
		normals.append_array(PackedVector3Array([normal, normal, normal, normal]))
		uvs.append_array(PackedVector2Array([Vector2(0, plane), Vector2(0, plane), Vector2(1, plane), Vector2(1, plane)]))
		colors.append_array(PackedColorArray([Color(0, 1, 1, 1), Color(0, 1, 1, 1), Color(0, 1, 1, 1), Color(0, 1, 1, 1)]))
		indices.append_array(PackedInt32Array([offset, offset + 2, offset + 1, offset, offset + 3, offset + 2]))

static func _cluster_mesh(radius: float, material: Material) -> ArrayMesh:
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var colors := PackedColorArray()
	var indices := PackedInt32Array()
	for plane: int in range(3):
		var angle := TAU * plane / 6.0
		var across := Vector3(cos(angle), 0.0, sin(angle))
		var normal := Vector3.UP.cross(across).normalized()
		var offset := vertices.size()
		vertices.append_array(PackedVector3Array([-across * radius * CLUSTER_TOP_WIDTH_RATIO, across * radius * CLUSTER_TOP_WIDTH_RATIO, across * radius - Vector3.UP * CLUSTER_UNIT_DEPTH_M, -across * radius - Vector3.UP * CLUSTER_UNIT_DEPTH_M]))
		normals.append_array(PackedVector3Array([normal, normal, normal, normal]))
		uvs.append_array(PackedVector2Array([Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)]))
		colors.append_array(PackedColorArray([Color.BLACK, Color.BLACK, Color.BLACK, Color.BLACK]))
		indices.append_array(PackedInt32Array([offset, offset + 2, offset + 1, offset, offset + 3, offset + 2]))
	_add_support_stem(vertices, normals, uvs, colors, indices)
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, material)
	return mesh

static func read_source(data_path: String) -> Dictionary:
	if not FileAccess.file_exists(data_path):
		_error("Canopy metadata is missing: %s" % data_path)
		return {}
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(data_path))
	if not value is Dictionary or value.get("schema", "") != SCHEMA:
		_error("Canopy metadata requires schema %s" % SCHEMA)
		return {}
	var source: Dictionary = value.duplicate(true)
	for key: String in ["width", "height"]:
		if not _number(source.get(key)) or float(source[key]) <= 0.0 or float(source[key]) != floor(float(source[key])):
			_error("Canopy %s requires a positive integer" % key)
			return {}
		source[key] = int(source[key])
	for key: String in ["cell_size_m", "first_cell_x_m", "first_cell_z_m", "row_step_z_m", "column_step_x_m", "highres_mask_cell_size_m"]:
		if not _number(source.get(key)):
			_error("Canopy %s requires a finite number" % key)
			return {}
		source[key] = float(source[key])
	if source.cell_size_m <= 0.0 or source.highres_mask_cell_size_m <= 0.0 or source.row_step_z_m != source.cell_size_m or source.column_step_x_m != source.cell_size_m:
		_error("Canopy grid requires positive equal X and Z cell spacing")
		return {}
	var subdivisions: float = source.cell_size_m / source.highres_mask_cell_size_m
	if not is_equal_approx(subdivisions, round(subdivisions)):
		_error("Canopy mask spacing must divide grid spacing")
		return {}
	if not source.get("artifacts") is Dictionary:
		_error("Canopy metadata requires artifact records")
		return {}
	var paths: Dictionary = {}
	for key: String in ARTIFACTS:
		var record: Variant = source.artifacts.get(key)
		if not record is Dictionary:
			_error("Canopy artifact record is missing: %s" % key)
			return {}
		var relative := str(record.get("path", ""))
		if relative.is_empty() or relative.is_absolute_path() or relative.contains(":") or ".." in relative.split("/"):
			_error("Canopy artifact paths require local relative paths: %s" % key)
			return {}
		var path := data_path.get_base_dir().path_join(relative)
		if not FileAccess.file_exists(path):
			_error("Canopy artifact is missing: %s" % path)
			return {}
		var bytes := FileAccess.get_file_as_bytes(path)
		if not _number(record.get("bytes")) or bytes.size() != int(record.bytes) or str(record.get("sha256", "")) != FileAccess.get_sha256(path):
			_error("Canopy artifact size or SHA-256 differs: %s" % key)
			return {}
		paths[key] = path
	var count: int = source.width * source.height
	for key: String in ["canopy_top_scene_y", "ground_scene_y", "cover_fraction", "valid_fraction"]:
		var bytes := FileAccess.get_file_as_bytes(paths[key])
		if bytes.size() != count * 4:
			_error("Canopy float32 grid length differs: %s" % key)
			return {}
		source[key] = bytes.to_float32_array()
	source.unresolved_cells = FileAccess.get_file_as_bytes(paths.unresolved_cells)
	if source.unresolved_cells.size() != count:
		_error("Canopy cell mask length differs")
		return {}
	for index: int in count:
		var active: int = source.unresolved_cells[index]
		var cover: float = source.cover_fraction[index]
		var valid: float = source.valid_fraction[index]
		if not is_finite(source.ground_scene_y[index]):
			_error("Continuous canopy display topology requires matched ground at %d" % index)
			return {}
		if active not in [0, 1] or not is_finite(cover) or not is_finite(valid) or cover < 0.0 or valid < 0.0 or valid > 1.0 or cover > valid or (active == 1) != (cover > 0.0):
			_error("Canopy cell mask and cover fraction disagree at %d" % index)
			return {}
		if active == 1:
			var top: float = source.canopy_top_scene_y[index]
			var ground: float = source.ground_scene_y[index]
			if not is_finite(top) or not is_finite(ground) or top <= ground:
				_error("Canopy active cell requires finite top above ground at %d" % index)
				return {}
	var mask := Image.new()
	var support := Image.new()
	var mask_error := mask.load_png_from_buffer(FileAccess.get_file_as_bytes(paths.unresolved_render_mask))
	var support_error := support.load_png_from_buffer(FileAccess.get_file_as_bytes(paths.valid_support))
	var dimensions := Vector2i(source.width * int(round(subdivisions)), source.height * int(round(subdivisions)))
	if mask_error != OK or support_error != OK or Vector2i(mask.get_width(), mask.get_height()) != dimensions or Vector2i(support.get_width(), support.get_height()) != dimensions:
		_error("Canopy mask image dimensions differ from grid extent")
		return {}
	mask.convert(Image.FORMAT_R8)
	support.convert(Image.FORMAT_R8)
	var mask_bytes := mask.get_data()
	var support_bytes := support.get_data()
	for index: int in mask_bytes.size():
		if mask_bytes[index] not in [0, 255] or support_bytes[index] not in [0, 255] or (mask_bytes[index] == 255 and support_bytes[index] == 0):
			_error("Canopy mask requires binary coverage within valid support at %d" % index)
			return {}
	var subdivision_count := int(round(subdivisions))
	for row: int in source.height:
		for column: int in source.width:
			var observed_pixels := 0
			var supported_pixels := 0
			for z: int in subdivision_count:
				for x: int in subdivision_count:
					var pixel: int = (row * subdivision_count + z) * dimensions.x + column * subdivision_count + x
					if mask_bytes[pixel] == 255:
						observed_pixels += 1
					if support_bytes[pixel] == 255:
						supported_pixels += 1
			var expected: float = float(observed_pixels) / float(subdivision_count * subdivision_count)
			if absf(source.cover_fraction[row * source.width + column] - expected) > 0.000001:
				_error("Canopy cover fraction differs from the source mask at %d,%d" % [column, row])
				return {}
			var expected_valid: float = float(supported_pixels) / float(subdivision_count * subdivision_count)
			if absf(source.valid_fraction[row * source.width + column] - expected_valid) > 0.000001:
				_error("Canopy valid fraction differs from the support mask at %d,%d" % [column, row])
				return {}
	source.mask_image = mask
	source.support_image = support
	source.mask_texture = ImageTexture.create_from_image(mask)
	source.support_texture = ImageTexture.create_from_image(support)
	return source

static func _prepare_surface(source: Dictionary) -> void:
	var width: int = source.width + 1
	var count: int = width * (source.height + 1)
	var upper := PackedFloat32Array()
	var lower := PackedFloat32Array()
	var normals := PackedVector3Array()
	upper.resize(count)
	lower.resize(count)
	normals.resize(count)
	for row: int in range(source.height + 1):
		for column: int in width:
			var top_sum := 0.0
			var ground_sum := 0.0
			var weight_sum := 0.0
			var all_ground_sum := 0.0
			var all_neighbors := 0
			for z: int in range(maxi(0, row - 1), mini(source.height, row + 1)):
				for x: int in range(maxi(0, column - 1), mini(source.width, column + 1)):
					var at: int = z * source.width + x
					all_ground_sum += source.ground_scene_y[at]
					all_neighbors += 1
			var search_cells: int = int(ceil(DISPLAY_SMOOTHING_RADIUS_M / source.cell_size_m))
			var radius_squared := DISPLAY_SMOOTHING_RADIUS_M * DISPLAY_SMOOTHING_RADIUS_M
			for z: int in range(maxi(0, row - search_cells), mini(source.height, row + search_cells)):
				for x: int in range(maxi(0, column - search_cells), mini(source.width, column + search_cells)):
					var at: int = z * source.width + x
					if source.unresolved_cells[at] == 0:
						continue
					var distance_squared: float = pow((x + 0.5 - column) * source.cell_size_m, 2) + pow((z + 0.5 - row) * source.cell_size_m, 2)
					if distance_squared >= radius_squared:
						continue
					var weight: float = (1.0 - distance_squared / radius_squared) * source.cover_fraction[at]
					top_sum += source.canopy_top_scene_y[at] * weight
					ground_sum += source.ground_scene_y[at] * weight
					weight_sum += weight
			var corner: int = row * width + column
			upper[corner] = top_sum / weight_sum if weight_sum > 0.0 else all_ground_sum / all_neighbors + source.highres_mask_cell_size_m
			lower[corner] = maxf(ground_sum / weight_sum, upper[corner] - source.highres_mask_cell_size_m) if weight_sum > 0.0 else all_ground_sum / all_neighbors
	for row: int in source.height:
		for column: int in source.width:
			var corners := [row * width + column, row * width + column + 1, (row + 1) * width + column + 1, (row + 1) * width + column]
			for face: Array in [[0, 1, 2], [0, 2, 3]]:
				var a := _corner_position(corners[face[0]], upper, width, source.cell_size_m)
				var b := _corner_position(corners[face[1]], upper, width, source.cell_size_m)
				var c := _corner_position(corners[face[2]], upper, width, source.cell_size_m)
				var normal := -(b - a).cross(c - a)
				for vertex: int in face:
					normals[corners[vertex]] += normal
	for index: int in count:
		if is_finite(upper[index]):
			normals[index] = normals[index].normalized()
	source.corner_upper = upper
	source.corner_lower = lower
	source.corner_normals = normals

static func _corner_position(index: int, elevations: PackedFloat32Array, width: int, cell_size: float) -> Vector3:
	return Vector3((index % width) * cell_size, elevations[index], int(index / width) * cell_size)

static func _tile(source: Dictionary, column: int, row: int, tile_cells: int, material: ShaderMaterial) -> Dictionary:
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	var cell_size: float = source.cell_size_m
	var origin := Vector3(source.first_cell_x_m + column * cell_size - cell_size * 0.5, 0.0, source.first_cell_z_m + row * cell_size - cell_size * 0.5)
	var active_cells := 0
	var area := 0.0
	var corners: Dictionary = {}
	var boundary_edges := 0
	var surface_cells := 0
	var corner_width: int = source.width + 1
	for z: int in range(row, mini(row + tile_cells, source.height)):
		for x: int in range(column, mini(column + tile_cells, source.width)):
			var at: int = z * source.width + x
			var cell_corners := [z * corner_width + x, z * corner_width + x + 1, (z + 1) * corner_width + x + 1, (z + 1) * corner_width + x]
			var top_indices: Array[int] = []
			var bottom_indices: Array[int] = []
			for corner: int in cell_corners:
				if not corners.has(corner):
					var offset := vertices.size()
					var top := _corner_position(corner, source.corner_upper, corner_width, cell_size)
					var bottom := _corner_position(corner, source.corner_lower, corner_width, cell_size)
					var normal: Vector3 = source.corner_normals[corner]
					var uv := Vector2(top.x / (source.width * cell_size), top.z / (source.height * cell_size))
					vertices.append_array(PackedVector3Array([top - Vector3(column * cell_size, 0.0, row * cell_size), bottom - Vector3(column * cell_size, 0.0, row * cell_size)]))
					normals.append_array(PackedVector3Array([normal, -normal]))
					uvs.append_array(PackedVector2Array([uv, uv]))
					corners[corner] = offset
				top_indices.append(corners[corner])
				bottom_indices.append(int(corners[corner]) + 1)
			indices.append_array(PackedInt32Array([top_indices[0], top_indices[1], top_indices[2], top_indices[0], top_indices[2], top_indices[3], bottom_indices[0], bottom_indices[2], bottom_indices[1], bottom_indices[0], bottom_indices[3], bottom_indices[2]]))
			for edge: Array in [[0, 1, x, z - 1, Vector3.FORWARD], [1, 2, x + 1, z, Vector3.RIGHT], [2, 3, x, z + 1, Vector3.BACK], [3, 0, x - 1, z, Vector3.LEFT]]:
				var neighbor_x: int = edge[2]
				var neighbor_z: int = edge[3]
				if neighbor_x >= 0 and neighbor_x < source.width and neighbor_z >= 0 and neighbor_z < source.height:
					continue
				var offset := vertices.size()
				for corner: int in [top_indices[edge[0]], bottom_indices[edge[0]], bottom_indices[edge[1]], top_indices[edge[1]]]:
					var point := vertices[corner]
					vertices.append(point)
					normals.append(edge[4])
					uvs.append(uvs[corner])
				indices.append_array(PackedInt32Array([offset, offset + 1, offset + 2, offset, offset + 2, offset + 3]))
				boundary_edges += 1
			surface_cells += 1
			active_cells += int(source.unresolved_cells[at])
			area += source.cover_fraction[at] * cell_size * cell_size
	if surface_cells == 0:
		return {}
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, material)
	var node := MeshInstance3D.new()
	node.name = "Canopy_%d_%d" % [column, row]
	node.position = origin
	node.mesh = mesh
	node.custom_aabb = mesh.get_aabb()
	node.visibility_range_end = 3000.0
	node.set_meta("active_cells", active_cells)
	node.set_meta("represented_area_m2", area)
	node.set_meta("cell_column", column)
	node.set_meta("cell_row", row)
	node.set_meta("boundary_edges", boundary_edges)
	node.set_meta("surface_corners", corners.size())
	node.set_meta("surface_cells", surface_cells)
	return {"node": node, "active_cells": active_cells, "represented_area_m2": area}

static func _set_owner(node: Node, owner_node: Node) -> void:
	node.owner = owner_node
	for child: Node in node.get_children():
		_set_owner(child, owner_node)

static func _number(value: Variant) -> bool:
	return (typeof(value) == TYPE_INT or typeof(value) == TYPE_FLOAT) and is_finite(float(value))

static func _error(message: String) -> bool:
	push_error(message)
	return false
