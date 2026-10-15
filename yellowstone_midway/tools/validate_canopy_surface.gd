extends SceneTree
## Validate residual canopy geometry, support, and failure paths.

const Canopy := preload("res://scripts/canopy_surface.gd")
const Support := preload("res://scripts/canopy_support.gd")
var failures: Array[String] = []
var checks := 0
var cells := 0
var triangles := 0
var tiles := 0
var represented_area := 0.0
var minimum_retained_shoots := [40, 16]
var support_only_clusters := [0, 0]
var rendered_ground: RefCounted

func _initialize() -> void:
	call_deferred("verify")

func check(condition: bool, detail: String) -> void:
	checks += 1
	if not condition:
		failures.append(detail)

func verify() -> void:
	var started := Time.get_ticks_msec()
	var arguments := OS.get_cmdline_user_args()
	var data_path := ""
	var output_path := "user://canopy_surface_validation.json"
	var negative := "--negative" in arguments
	var baked := "--baked" in arguments
	validate_support_connections()
	for index: int in range(arguments.size()):
		if arguments[index] == "--data" and index + 1 < arguments.size():
			data_path = arguments[index + 1]
		if arguments[index] == "--out" and index + 1 < arguments.size():
			output_path = arguments[index + 1]
	var fixture := make_fixture()
	if fixture.is_empty():
		quit(2)
		return
	var parent := Node3D.new()
	get_root().add_child(parent)
	check(Canopy.build(parent, fixture, 128.0, [], false), "Fixture build fails")
	var group := parent.get_node_or_null("AuthoredCanopySurface")
	check(group != null, "Fixture canopy group is missing")
	if group != null:
		validate_group(group, Canopy.read_source(fixture))
		check(int(group.get_meta("active_cells", -1)) == 3, "Fixture requires three active2m cells")
		check(is_equal_approx(float(group.get_meta("represented_area_m2", -1.0)), 8.25), "Fixture exact residual area differs")
		check(group.owner == parent and group.get_child(0).owner == parent, "Canopy nodes require scene ownership")
		var packed := PackedScene.new()
		check(packed.pack(parent) == OK, "Canopy fixture does not pack")
		var restored := packed.instantiate()
		check(restored.get_node_or_null("AuthoredCanopySurface") != null, "Packed canopy group is missing")
		restored.free()
	parent.free()
	var fixture_geometry := {"active_cells": cells, "triangles": triangles, "tiles": tiles, "represented_area_m2": represented_area}
	if negative:
		validate_negative(fixture)
	if not data_path.is_empty():
		cells = 0
		triangles = 0
		tiles = 0
		represented_area = 0.0
		var source := Canopy.read_source(data_path)
		check(not source.is_empty(), "Observed canopy source fails validation")
		if not source.is_empty():
			var observed: Node3D = load("res://scenes/authored_world.tscn").instantiate() if baked else Node3D.new()
			get_root().add_child(observed)
			if not baked:
				check(Canopy.build(observed, data_path), "Observed canopy build fails")
			var observed_group := observed.get_node_or_null("AuthoredCanopySurface")
			if observed_group != null:
				Canopy.refresh_geometry(observed_group)
				validate_group(observed_group, source)
			observed.free()
	var report := {"ok": failures.is_empty(), "engine": Engine.get_version_info().string, "checks": checks, "active_cells": cells, "triangles": triangles, "tiles": tiles, "represented_area_m2": represented_area, "fixture_geometry": fixture_geometry, "runtime_geometry_revision": Canopy.GEOMETRY_REVISION, "baked_runtime_upgrade": baked, "minimum_retained_shoots_by_lod": minimum_retained_shoots, "support_only_clusters_by_lod": support_only_clusters, "source_sha256": FileAccess.get_sha256(data_path) if not data_path.is_empty() else "fixture", "negative_controls": negative, "geometry_class": "authored", "height_evidence_class": "derived_not_field_validated", "footprint_evidence_class": "derived_not_field_validated", "shell_thickness_class": "authored_display_geometry", "stem_count_claim": "none", "scientific_acceptance": "not_yet_accepted", "elapsed_seconds": (Time.get_ticks_msec() - started) / 1000.0, "failures": failures}
	var output := FileAccess.open(output_path, FileAccess.WRITE)
	if output == null:
		push_error("Cannot write canopy validation report: %s" % output_path)
		quit(2)
		return
	output.store_string(JSON.stringify(report, "  "))
	output.close()
	print("CANOPY_VALIDATION ok=", report.ok, " checks=", checks, " cells=", cells, " triangles=", triangles, " area_m2=", represented_area, " seconds=", report.elapsed_seconds)
	for failure: String in failures:
		push_error(failure)
	quit(0 if failures.is_empty() else 1)

func validate_group(group: Node3D, source: Dictionary) -> void:
	check(str(group.get_meta("evidence_class", "")) == "derived_not_field_validated", "Canopy evidence class differs")
	check(str(group.get_meta("stem_count_claim", "")) == "none", "Canopy must carry no stem-count claim")
	check(str(group.get_meta("shell_thickness_class", "")) == "authored_display_geometry", "Canopy thickness provenance differs")
	check(str(group.get_meta("surface_smoothing_class", "")) == "authored_display_interpolation", "Canopy smoothing provenance differs")
	check(str(group.get_meta("near_fade_class", "")) == "authored_display_lod", "Canopy near fade provenance differs")
	check(float(group.get_meta("display_smoothing_radius_m", -1.0)) == 5.0 and group.get_meta("surface_smoothing_uncertainty", "") == "unknown", "Canopy display smoothing radius or uncertainty differs")
	check(group.get_meta("cluster_geometry_class", "") == "authored_display_geometry" and group.get_meta("cluster_rendered_coverage", "") == "unknown", "Canopy clusters require authored geometry and unknown rendered coverage")
	check(group.get_meta("near_fade_begin_m", -1.0) == 0.0 and group.get_meta("near_fade_end_m", -1.0) == 0.0, "Source-grounded foliage must remain visible at near distances")
	check(group.get_meta("cluster_live_crown_ratio", -1.0) == 0.70 and group.get_meta("cluster_depth_class", "") == "authored_display_volume", "Residual volume depth provenance differs")
	check(group.get_meta("support_geometry_class", "") == "authored_display_geometry", "Reconstructed supports require explicit authored provenance")
	check(group.get_meta("cluster_anchor_class", "") == "authored_display_placement" and group.get_meta("guaranteed_origin_shoot", false) == true, "Covered canopy anchors require authored provenance and an origin shoot")
	check(group.get_meta("cluster_anchor_rule", "") == "nearest_covered_native_pixel_center_within_original_source_cell" and group.get_meta("cluster_anchor_height_rule", "") == "unchanged_source_cell_top_and_ground", "Canopy anchor rule must preserve source cell identity and elevations")
	check(is_equal_approx(float(group.get_meta("cluster_anchor_max_offset_m", -1.0)), (source.cell_size_m - source.highres_mask_cell_size_m) / sqrt(2.0)), "Canopy anchor displacement bound differs")
	rendered_ground = Canopy.Ground.new() if group.get_meta("support_root_rule", "").contains("rendered_terrain") else null
	if rendered_ground != null:
		check(rendered_ground.valid(), "Rendered canopy support terrain is valid")
	var mask: Image = source.mask_image
	var support: Image = source.support_image
	var mask_bytes := mask.get_data()
	var support_bytes := support.get_data()
	var observed_pixels := 0
	var invalid_pixels := 0
	var nonbinary_pixels := 0
	for index: int in mask_bytes.size():
		if mask_bytes[index] != 0 and mask_bytes[index] != 255:
			nonbinary_pixels += 1
		if support_bytes[index] != 0 and support_bytes[index] != 255:
			nonbinary_pixels += 1
		if mask_bytes[index] == 255:
			observed_pixels += 1
			if support_bytes[index] == 0:
				invalid_pixels += 1
	check(invalid_pixels == 0, "Residual canopy extends into missing support")
	check(nonbinary_pixels == 0, "Coverage and support masks require binary values")
	var expected_area: float = observed_pixels * source.highres_mask_cell_size_m * source.highres_mask_cell_size_m
	check(is_equal_approx(float(group.get_meta("represented_area_m2", -1.0)), expected_area), "Grid fractions differ from exact mask area")
	var expected_cells := 0
	var expected_boundaries: int = 2 * source.width + 2 * source.height
	for z: int in source.height:
		for x: int in source.width:
			var at: int = z * source.width + x
			if source.unresolved_cells[at] == 0:
				continue
			expected_cells += 1
	var mesh_cells := 0
	var actual_boundaries := 0
	var surface_edges: Dictionary = {}
	var top_cells: Dictionary = {}
	var bottom_cells: Dictionary = {}
	var cluster_cells: Array[Dictionary] = [{}, {}, {}]
	var cluster_mesh_checked: Array[bool] = [false, false, false]
	for node: Node in group.get_children():
		if node is MultiMeshInstance3D:
			var lod: int = node.get_meta("cluster_lod", -1)
			check(lod >= 0 and lod < 3, "Residual foliage LOD is invalid")
			if lod >= 0 and lod < 3:
				validate_clusters(node, source, cluster_cells[lod], not cluster_mesh_checked[lod])
				cluster_mesh_checked[lod] = true
			continue
		check(node is MeshInstance3D and node.mesh is ArrayMesh, "Canopy tile requires native ArrayMesh")
		if not node is MeshInstance3D or not node.mesh is ArrayMesh:
			continue
		tiles += 1
		var mesh: ArrayMesh = node.mesh
		check(mesh.get_surface_count() == 1 and mesh.surface_get_primitive_type(0) == Mesh.PRIMITIVE_TRIANGLES, "Canopy tile requires one triangle surface")
		var arrays := mesh.surface_get_arrays(0)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		var count: int = node.get_meta("active_cells", -1)
		var boundaries: int = node.get_meta("boundary_edges", -1)
		var corners: int = node.get_meta("surface_corners", -1)
		var surface_cells: int = node.get_meta("surface_cells", -1)
		check(vertices.size() == corners * 2 + boundaries * 4 and normals.size() == vertices.size() and uvs.size() == vertices.size() and indices.size() == surface_cells * 12 + boundaries * 6, "Canopy shared-surface topology differs")
		var material := mesh.surface_get_material(0)
		check(material is ShaderMaterial and material.shader.resource_path == Canopy.SHADER_PATH, "Canopy material shader differs")
		if material is ShaderMaterial:
			check(material.get_shader_parameter("albedo_texture") is Texture2D and material.get_shader_parameter("coverage_texture") is ImageTexture and material.get_shader_parameter("support_texture") is ImageTexture, "Canopy material textures are missing")
		var box: AABB = node.custom_aabb
		for index: int in vertices.size():
			var point := vertices[index]
			check(point.is_finite() and normals[index].is_finite() and uvs[index].is_finite(), "Canopy vertex arrays require finite values")
			check(absf(normals[index].length() - 1.0) < 0.00001, "Canopy normals require unit length")
			check(box.grow(0.0001).has_point(point), "Canopy vertex exceeds explicit culling bounds")
			var world: Vector3 = node.position + point
			var column := int(round((world.x - source.first_cell_x_m + source.cell_size_m * 0.5) / source.cell_size_m))
			var row := int(round((world.z - source.first_cell_z_m + source.cell_size_m * 0.5) / source.cell_size_m))
			check_corner(world.y, source, column, row)
		for triangle: int in range(0, indices.size(), 3):
			var a: Vector3 = node.position + vertices[indices[triangle]]
			var b: Vector3 = node.position + vertices[indices[triangle + 1]]
			var c: Vector3 = node.position + vertices[indices[triangle + 2]]
			var cross := (b - a).cross(c - a)
			check(cross.length() > 0.000001, "Canopy triangle is degenerate")
			var normal := normals[indices[triangle]]
			if absf(cross.y) > 0.000001:
				check(cross.y * normal.y < 0.0, "Canopy surface winding and upward/downward normal disagree")
				var center := (a + b + c) / 3.0
				var column := int(floor((center.x - source.first_cell_x_m + source.cell_size_m * 0.5) / source.cell_size_m))
				var row := int(floor((center.z - source.first_cell_z_m + source.cell_size_m * 0.5) / source.cell_size_m))
				var at: int = row * source.width + column
				var target: Dictionary = top_cells if cross.y < 0.0 else bottom_cells
				target[at] = int(target.get(at, 0)) + 1
			else:
				check(cross.dot(normal) < 0.0, "Canopy boundary winding and normal disagree")
			for pair: Array in [[a, b], [b, c], [c, a]]:
				var key: String = "%s|%s" % [str(pair[0]), str(pair[1])] if str(pair[0]) < str(pair[1]) else "%s|%s" % [str(pair[1]), str(pair[0])]
				surface_edges[key] = int(surface_edges.get(key, 0)) + 1
		mesh_cells += count
		actual_boundaries += boundaries
		triangles += indices.size() / 3
	for at: int in top_cells:
		check(int(top_cells[at]) == 2 and int(bottom_cells.get(at, 0)) == 2, "Canopy active cell requires paired top/bottom quads")
	for multiplicity: int in surface_edges.values():
		check(multiplicity == 2, "Canopy continuous skin has an open or nonmanifold edge")
	check(top_cells.size() == source.width * source.height and bottom_cells.size() == source.width * source.height, "Canopy continuous skin omits grid cells")
	check(actual_boundaries == expected_boundaries, "Canopy walls require the continuous layer outer boundary")
	check(mesh_cells == expected_cells, "Canopy mesh omits or adds an active cell")
	check(int(group.get_meta("active_cells", -1)) == expected_cells, "Canopy group active-cell metadata differs")
	for lod_cells: Dictionary in cluster_cells:
		check(lod_cells.size() == expected_cells, "Disjoint foliage LOD omits or duplicates source cells")
	check(int(group.get_meta("cluster_display_count", -1)) == expected_cells, "Canopy source-cell display count differs")
	cells += mesh_cells
	represented_area += expected_area

func validate_clusters(node: MultiMeshInstance3D, source: Dictionary, seen: Dictionary, inspect_mesh: bool) -> void:
	var multimesh := node.multimesh
	check(multimesh != null and multimesh.mesh is ArrayMesh, "Canopy clusters require native instanced mesh")
	if multimesh == null or not multimesh.mesh is ArrayMesh:
		return
	check(node.cast_shadow == GeometryInstance3D.SHADOW_CASTING_SETTING_OFF, "Canopy clusters require disabled shadows")
	var lod: int = node.get_meta("cluster_lod", -1)
	var padding := multimesh.custom_aabb.size.length() * 0.5
	check(is_equal_approx(node.visibility_range_begin, maxf(0.0, Canopy.CLUSTER_LODS[lod][0] - 8.0 - padding)) and is_equal_approx(node.visibility_range_end, Canopy.CLUSTER_LODS[lod][1] + padding), "Canopy coarse bounds violate the per-root triangle inequality")
	var material: Material = multimesh.mesh.surface_get_material(0)
	check(material is ShaderMaterial and material.get_shader_parameter("cluster_mode") == true, "Canopy cluster material mode differs")
	check(material.get_shader_parameter("lod_begin_m") == Canopy.CLUSTER_LODS[lod][0] and material.get_shader_parameter("lod_end_m") == Canopy.CLUSTER_LODS[lod][1] and material.get_shader_parameter("lod_dither_invert") == (lod % 2 == 1), "Per-cluster canopy LOD shader contract differs")
	var source_indices: PackedInt32Array = node.get_meta("source_indices", PackedInt32Array())
	var buffer := multimesh.buffer
	check(source_indices.size() == multimesh.instance_count and buffer.size() == multimesh.instance_count * 16 and multimesh.use_custom_data, "Canopy source indices or saved attachment buffer differs")
	var shape_bounds := multimesh.mesh.get_aabb()
	var radius: float = source.cell_size_m / sqrt(2.0)
	var near_shoots: bool = int(Canopy.CLUSTER_LODS[lod][2]) > 0
	var mesh_anchors: PackedVector2Array = multimesh.mesh.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV2] if near_shoots else PackedVector2Array()
	check(material.get_shader_parameter("near_shoot_mode") == near_shoots, "Metric foliage material mode differs")
	check(material.get_shader_parameter("needle_repeat_m") == Canopy.SHOOT_CARD_SIZE_M and material.get_shader_parameter("shoot_envelope_m") == Canopy.SHOOT_ENVELOPE_M, "Residual needle texture physical scale differs")
	if not near_shoots:
		check(absf(shape_bounds.end.y) < 0.00001 and absf(shape_bounds.position.y + 1.0 / Canopy.CLUSTER_LIVE_CROWN_RATIO) < 0.00001, "Far support top or ground depth differs")
		check(absf(shape_bounds.size.x - radius * 2.0) < 0.00001 and absf(shape_bounds.size.z - radius * sqrt(3.0)) < 0.00001, "Far foliage proxy footprint differs")
	for instance: int in source_indices.size():
		var at := instance * 16
		var index: int = source_indices[instance]
		check(index >= 0 and index < source.width * source.height and source.unresolved_cells[index] == 1 and not seen.has(index), "Canopy cluster source index is inactive or duplicated")
		var transform := Transform3D(Basis(Vector3(buffer[at], buffer[at + 4], buffer[at + 8]), Vector3(buffer[at + 1], buffer[at + 5], buffer[at + 9]), Vector3(buffer[at + 2], buffer[at + 6], buffer[at + 10])), Vector3(buffer[at + 3], buffer[at + 7], buffer[at + 11]))
		var world := node.transform * transform
		var position := Vector3(source.first_cell_x_m + (index % source.width) * source.cell_size_m, source.canopy_top_scene_y[index], source.first_cell_z_m + int(index / source.width) * source.cell_size_m)
		var depth: float = (source.canopy_top_scene_y[index] - source.ground_scene_y[index]) * Canopy.CLUSTER_LIVE_CROWN_RATIO
		check(world.is_finite() and absf(world.basis.x.length() - 1.0) < 0.00001 and absf(world.basis.z.length() - 1.0) < 0.00001 and absf(world.basis.y.length() - depth) < 0.00001, "Canopy volume basis changes source-grounded dimensions")
		check(absf(world.basis.x.dot(world.basis.z)) < 0.00001 and world.basis.y.normalized().distance_to(Vector3.UP) < 0.00001, "Canopy volume orientation is tilted or nonorthogonal")
		var bottom := world * Vector3(0.0, -minf(depth, 2.0) / depth, 0.0)
		var expected_base: float = source.canopy_top_scene_y[index] - minf(depth, 2.0)
		check(absf(bottom.y - expected_base) < 0.00001 and bottom.y > source.ground_scene_y[index], "Canopy volume lower foliage is detached from its authored source-grounded crown interval")
		validate_anchor(world.origin, position, source)
		if near_shoots:
			var retained := 0
			for shoot: int in int(Canopy.CLUSTER_LODS[lod][2]):
				var anchor := mesh_anchors[shoot * Canopy.SHOOT_VERTICES]
				var at_world := world * Vector3(anchor.x, 0.0, anchor.y)
				retained += 1 if covered(at_world, source) else 0
			minimum_retained_shoots[lod] = mini(minimum_retained_shoots[lod], retained)
			support_only_clusters[lod] += 1 if retained == 0 else 0
			check(retained > 0, "Canopy support retains zero foliage shoots after the native coverage mask")
		var root := world * Vector3(buffer[at + 12], buffer[at + 13], buffer[at + 14])
		var ground_y: float = rendered_ground.sample(world.origin.x, world.origin.z) if rendered_ground != null else source.ground_scene_y[index]
		check(root.is_finite() and (buffer[at + 15] == 1.0 or absf(root.y - ground_y + 0.04) < 0.00004), "Unattached display support does not reach rendered ground")
		if buffer[at + 15] != 1.0:
			check(Vector2(root.x - world.origin.x, root.z - world.origin.z).length() < 0.00004, "Unattached support remains at the old uncovered cell center")
		check(multimesh.custom_aabb.grow(0.0001).has_point(root - node.position), "Woody connection exceeds batch culling bounds")
		var volume_bounds := AABB(Vector3(-source.cell_size_m, -1.0 / Canopy.CLUSTER_LIVE_CROWN_RATIO, -source.cell_size_m), Vector3(source.cell_size_m * 2.0, 1.0 / Canopy.CLUSTER_LIVE_CROWN_RATIO, source.cell_size_m * 2.0))
		check(multimesh.custom_aabb.grow(0.0001).encloses(transform * volume_bounds), "Shader-deformed foliage volume exceeds explicit culling bounds")
		seen[index] = true
	if not inspect_mesh:
		return
	var arrays := multimesh.mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var count: int = Canopy.CLUSTER_LODS[lod][2]
	var quads: int = count * 2 if near_shoots else 3
	check(vertices.size() == (count * Canopy.SHOOT_VERTICES + 20 if near_shoots else 32) and indices.size() == (count * 30 + 60 if near_shoots else 78), "Connected foliage geometry differs from its LOD budget")
	var colors: PackedColorArray = arrays[Mesh.ARRAY_COLOR]
	var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	check(colors.size() == vertices.size(), "Foliage and support vertices require material attributes")
	for vertex: int in vertices.size():
		check(vertices[vertex].is_finite() and normals[vertex].is_finite() and absf(normals[vertex].length() - 1.0) < 0.00001, "Canopy cluster vertex or normal is invalid")
		if near_shoots and colors[vertex].g < 0.5:
			check(colors[vertex].r > 0.0 and colors[vertex].r < 1.0 and absf(vertices[vertex].y + colors[vertex].r) <= Canopy.SHOOT_ENVELOPE_M * 0.5 + 0.003, "Metric foliage vertex differs from its authored center and physical size")
		elif not near_shoots and colors[vertex].g < 0.5 and absf(vertices[vertex].y) < 0.00001:
			check(Vector2(vertices[vertex].x, vertices[vertex].z).length() <= radius * Canopy.CLUSTER_TOP_WIDTH_RATIO + 0.00001, "Canopy upper volume taper differs")
	if near_shoots:
		var anchors: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV2]
		check(anchors.size() == vertices.size(), "Whole-shoot mask anchors are missing")
		check(anchors[0].length() < 0.000001, "Near and middle LOD require a guaranteed origin shoot")
		for shoot: int in count:
			var base := shoot * Canopy.SHOOT_VERTICES
			var center_point := (vertices[base] + vertices[base + 2]) * 0.5
			var center_xz := Vector2(center_point.x, center_point.z)
			for corner: int in Canopy.SHOOT_VERTICES:
				check(anchors[base + corner].distance_to(center_xz) < 0.000001, "Canopy mask clips a shoot independently of its attachment center")
			check(colors[base + 10].g > 0.5 and colors[base].g < 0.5, "Twig and needle material classes disagree")
			for depth: float in [0.07, 0.7, 7.0, 21.0, 70.0]:
				var crown_depth := minf(depth, 2.0)
				var scale := minf(1.0, crown_depth / Canopy.SHOOT_ENVELOPE_M)
				var center := (vertices[base + 2] + vertices[base + 3]) * 0.5
				var fraction := colors[base].r
				center.y = -lerpf(Canopy.SHOOT_ENVELOPE_M * 0.5 * scale, crown_depth - Canopy.SHOOT_ENVELOPE_M * 0.5 * scale, fraction) + (center.y + fraction) * scale
				var tip := (vertices[base + 9] + vertices[base + 11] + vertices[base + 13]) / 3.0
				tip.y = -lerpf(Canopy.SHOOT_ENVELOPE_M * 0.5 * scale, crown_depth - Canopy.SHOOT_ENVELOPE_M * 0.5 * scale, fraction) + (tip.y + fraction) * scale
				check(center.distance_to(tip) < 0.00001, "Needle base and woody twig disconnect after nonuniform height scaling")
			var twig_root := (vertices[base + 8] + vertices[base + 10] + vertices[base + 12]) / 3.0
			check(Vector2(twig_root.x, twig_root.z).length() < 0.000001 and twig_root.y >= -1.05 and twig_root.y <= 0.0, "Twig root misses central support")
			var shoot_axis := ((vertices[base] + vertices[base + 1]) * 0.5 - (vertices[base + 2] + vertices[base + 3]) * 0.5).normalized()
			check(shoot_axis.y >= cos(deg_to_rad(100.0)) - 0.00001 and shoot_axis.y <= cos(deg_to_rad(65.0)) + 0.00001, "Bough orientation is outside its lateral authored range")
	var edges: Dictionary = {}
	for triangle: int in range(0, indices.size(), 3):
		var a := vertices[indices[triangle]]
		var b := vertices[indices[triangle + 1]]
		var c := vertices[indices[triangle + 2]]
		var normal := normals[indices[triangle]] + normals[indices[triangle + 1]] + normals[indices[triangle + 2]]
		check((b - a).cross(c - a).length() > 0.000001 and (b - a).cross(c - a).dot(normal) < 0.0, "Canopy cluster triangle or winding is invalid")
		for edge: Vector2i in [Vector2i(indices[triangle], indices[triangle + 1]), Vector2i(indices[triangle + 1], indices[triangle + 2]), Vector2i(indices[triangle + 2], indices[triangle])]:
			var key := Vector2i(mini(edge.x, edge.y), maxi(edge.x, edge.y))
			edges[key] = int(edges.get(key, 0)) + 1
	for multiplicity: int in edges.values():
		check(multiplicity in [1, 2], "Needle card edge is nonmanifold")
	check(edges.values().count(1) == quads * 4 + count * 6 + 20 and edges.values().count(2) == quads + count * 6 + 20, "Needle, twig and support edge counts differ")

func covered(position: Vector3, source: Dictionary) -> bool:
	var origin: Vector2 = Vector2(source.first_cell_x_m, source.first_cell_z_m) - Vector2.ONE * source.cell_size_m * 0.5
	var pixel: Vector2 = (Vector2(position.x, position.z) - origin) / source.highres_mask_cell_size_m
	var mask: Image = source.mask_image
	var x := floori(pixel.x)
	var z := floori(pixel.y)
	if x < 0 or x >= mask.get_width() or z < 0 or z >= mask.get_height():
		return false
	return mask.get_pixel(x, z).r > 0.5 and source.support_image.get_pixel(x, z).r > 0.5

func validate_anchor(actual: Vector3, source_center: Vector3, source: Dictionary) -> void:
	var delta := Vector2(actual.x - source_center.x, actual.z - source_center.z)
	var half_cell: float = source.cell_size_m * 0.5
	var half_pixel: float = source.highres_mask_cell_size_m * 0.5
	check(absf(actual.y - source_center.y) < 0.00001, "Canopy anchor changes measured-derived source top elevation")
	check(absf(delta.x) <= half_cell - half_pixel + 0.00001 and absf(delta.y) <= half_cell - half_pixel + 0.00001, "Canopy anchor leaves its original source cell interior")
	check(covered(actual, source), "Canopy anchor is outside observed supported coverage")
	var nearest := INF
	var subdivisions := int(round(source.cell_size_m / source.highres_mask_cell_size_m))
	for z: int in subdivisions:
		for x: int in subdivisions:
			var candidate := source_center + Vector3((x + 0.5) * source.highres_mask_cell_size_m - half_cell, 0.0, (z + 0.5) * source.highres_mask_cell_size_m - half_cell)
			if covered(candidate, source):
				nearest = minf(nearest, Vector2(candidate.x - source_center.x, candidate.z - source_center.z).length_squared())
	check(absf(delta.length_squared() - nearest) < 0.00001, "Canopy anchor is not the nearest covered native pixel center")
	var local_pixel: Vector2 = (delta + Vector2.ONE * half_cell) / source.highres_mask_cell_size_m - Vector2.ONE * 0.5
	check(local_pixel.distance_to(local_pixel.round()) < 0.00001, "Canopy anchor must sit inside a covered pixel, away from a shader sampling boundary")

func validate_support_connections() -> void:
	var host := {"base": Vector3(1, 30, 0), "top_y": 40.0, "transform": Transform3D(Basis.IDENTITY, Vector3(1, 30, 0)), "profile": PackedVector3Array([Vector3.ZERO, Vector3(1, 10, 0)])}
	var bins := {Vector2i.ZERO: [host]}
	var actual := Support.connection(Vector3(3, 38, 0), 30.0, bins)
	check(actual.attached and actual.point.distance_to(Vector3(1.578, 35.78, 0)) < 0.00001, "Canopy support misses the independently specified leaning bole")
	actual = Support.connection(Vector3(30, 38, 0), 30.0, bins)
	check(not actual.attached and actual.point.distance_to(Vector3(30, 29.96, 0)) < 0.00001, "Out-of-range canopy support must use matched ground")
	actual = Support.connection(Vector3(4, 38, 0), 30.0, bins)
	check(not actual.attached and Support.SEARCH_M == 2.0, "Residual support cannot span more than 2m to a distant bole")
	actual = Support.connection(Vector3(3, 44, 0), 30.0, bins)
	check(not actual.attached, "Short neighboring tree cannot support a higher canopy patch")
	var rendered := Support.prepare([{"id": "support_fixture", "kind": "pine", "archetype": "dense", "position": [0, 30, 0], "yaw": 0.0, "height_m": 18.0, "dbh_m": 0.26, "crown_r_m": 2.5, "crown_ratio": 0.7}])
	check(not rendered.is_empty(), "Rendered bole profile cannot be reconstructed")
	actual = Support.connection(Vector3(1, 45, 0), 30.0, rendered)
	check(actual.attached and actual.point.is_finite() and absf(actual.point.y - 42.78) < 0.00001, "Rendered bole support height or source profile is invalid")

func check_corner(height: float, source: Dictionary, column: int, row: int) -> void:
	var upper_sum := 0.0
	var ground_sum := 0.0
	var minimum := INF
	var maximum := -INF
	var weight_sum := 0.0
	var all_ground_sum := 0.0
	var all_adjacent := 0
	for z: int in range(maxi(0, row - 1), mini(source.height, row + 1)):
		for x: int in range(maxi(0, column - 1), mini(source.width, column + 1)):
			all_ground_sum += source.ground_scene_y[z * source.width + x]
			all_adjacent += 1
	var radius := Canopy.DISPLAY_SMOOTHING_RADIUS_M
	var search_cells: int = int(ceil(radius / source.cell_size_m))
	for z: int in range(maxi(0, row - search_cells), mini(source.height, row + search_cells)):
		for x: int in range(maxi(0, column - search_cells), mini(source.width, column + search_cells)):
			var at: int = z * source.width + x
			if source.unresolved_cells[at] == 0:
				continue
			var distance_squared: float = pow((x + 0.5 - column) * source.cell_size_m, 2) + pow((z + 0.5 - row) * source.cell_size_m, 2)
			if distance_squared >= radius * radius:
				continue
			var top: float = source.canopy_top_scene_y[at]
			var weight: float = (1.0 - distance_squared / (radius * radius)) * source.cover_fraction[at]
			upper_sum += top * weight
			ground_sum += source.ground_scene_y[at] * weight
			minimum = minf(minimum, top)
			maximum = maxf(maximum, top)
			weight_sum += weight
	if weight_sum == 0.0:
		var ground := all_ground_sum / all_adjacent
		check(absf(height - ground) < 0.00001 or absf(height - ground - source.highres_mask_cell_size_m) < 0.00001, "Masked canopy topology differs from matched ground support")
		return
	var upper := upper_sum / weight_sum
	var ground := ground_sum / weight_sum
	var lower := maxf(ground, upper - source.highres_mask_cell_size_m)
	if absf(height - upper) < 0.00001:
		check(height >= minimum - 0.00001 and height <= maximum + 0.00001, "Canopy smoothing exceeds observed neighbor elevations")
	else:
		check(absf(height - lower) < 0.00001 and height >= ground - 0.00001, "Canopy lower skin differs or lies below matched ground")

func make_fixture() -> String:
	var directory := "user://canopy_surface_fixture"
	DirAccess.make_dir_recursive_absolute(directory)
	var top := PackedFloat32Array([41.0, 42.0, NAN, 44.0])
	var ground := PackedFloat32Array([30.0, 31.0, 32.0, 43.0])
	var active := PackedByteArray([1, 1, 0, 1])
	var cover := PackedFloat32Array([1.0, 1.0, 0.0, 0.0625])
	var valid := PackedFloat32Array([1.0, 1.0, 1.0, 1.0])
	var data := {"schema": Canopy.SCHEMA, "width": 2, "height": 2, "cell_size_m": 2.0, "first_cell_x_m": -1.0, "first_cell_z_m": -1.0, "row_step_z_m": 2.0, "column_step_x_m": 2.0, "highres_mask_cell_size_m": 0.5, "artifacts": {}}
	for entry: Array in [["canopy_top_scene_y", top.to_byte_array()], ["ground_scene_y", ground.to_byte_array()], ["cover_fraction", cover.to_byte_array()], ["valid_fraction", valid.to_byte_array()], ["unresolved_cells", active]]:
		var filename: String = str(entry[0]) + ".bin"
		var file := FileAccess.open(directory.path_join(filename), FileAccess.WRITE)
		if file == null:
			push_error("Cannot write canopy fixture")
			return ""
		file.store_buffer(entry[1])
		file.close()
		data.artifacts[entry[0]] = artifact(directory, filename)
	var mask := Image.create(8, 8, false, Image.FORMAT_R8)
	mask.fill(Color.BLACK)
	for y: int in range(4):
		for x: int in range(8):
			mask.set_pixel(x, y, Color.WHITE)
	mask.set_pixel(4, 4, Color.WHITE)
	var support := Image.create(8, 8, false, Image.FORMAT_R8)
	support.fill(Color.WHITE)
	for entry: Array in [["unresolved_render_mask", mask], ["valid_support", support]]:
		var filename: String = str(entry[0]) + ".png"
		check(entry[1].save_png(directory.path_join(filename)) == OK, "Canopy fixture PNG write fails")
		data.artifacts[entry[0]] = artifact(directory, filename)
	var path := directory.path_join("canopy.json")
	var output := FileAccess.open(path, FileAccess.WRITE)
	output.store_string(JSON.stringify(data))
	output.close()
	return path

func artifact(directory: String, filename: String) -> Dictionary:
	var path := directory.path_join(filename)
	return {"path": filename, "sha256": FileAccess.get_sha256(path), "bytes": FileAccess.get_file_as_bytes(path).size()}

func validate_negative(fixture: String) -> void:
	var parsed: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(fixture))
	var parent := Node3D.new()
	get_root().add_child(parent)
	check(Canopy.build(parent, fixture, 128.0, [], false), "Negative-control setup fails")
	var original := parent.get_node("AuthoredCanopySurface")
	for mutation: Dictionary in [{"schema": "unknown"}, {"width": 2.5}, {"cell_size_m": 0.0}, {"row_step_z_m": -2.0}, {"highres_mask_cell_size_m": 0.3}, {"artifacts": {}}]:
		var invalid := parsed.duplicate(true)
		invalid.merge(mutation, true)
		check_rejected(parent, fixture, invalid, str(mutation))
		check(parent.get_node("AuthoredCanopySurface") == original, "Failed canopy build alters previous geometry")
	for mutation: Dictionary in [{"sha256": "wrong"}, {"bytes": 1}, {"path": "../outside.bin"}, {"path": "missing.bin"}]:
		var invalid := parsed.duplicate(true)
		invalid.artifacts.canopy_top_scene_y.merge(mutation, true)
		check_rejected(parent, fixture, invalid, str(mutation))
		check(parent.get_node("AuthoredCanopySurface") == original, "Failed canopy artifact build alters previous geometry")
	for entry: Array in [["canopy_top_scene_y", PackedFloat32Array([NAN, 42.0, NAN, 44.0]).to_byte_array()], ["ground_scene_y", PackedFloat32Array([50.0, 31.0, 32.0, 43.0]).to_byte_array()], ["cover_fraction", PackedFloat32Array([0.5, 1.0, 0.0, 0.0625]).to_byte_array()], ["valid_fraction", PackedFloat32Array([0.5, 1.0, 1.0, 1.0]).to_byte_array()], ["unresolved_cells", PackedByteArray([0, 1, 0, 1])]]:
		var invalid := parsed.duplicate(true)
		var filename: String = "invalid_" + str(entry[0]) + ".bin"
		var file := FileAccess.open(fixture.get_base_dir().path_join(filename), FileAccess.WRITE)
		file.store_buffer(entry[1])
		file.close()
		invalid.artifacts[entry[0]] = artifact(fixture.get_base_dir(), filename)
		check_rejected(parent, fixture, invalid, str(entry[0]))
		check(parent.get_node("AuthoredCanopySurface") == original, "Failed canopy grid build alters previous geometry")
	for key: String in ["valid_support", "unresolved_render_mask"]:
		var invalid := parsed.duplicate(true)
		var image := Image.load_from_file(fixture.get_base_dir().path_join(str(parsed.artifacts[key].path)))
		image.set_pixel(0, 0, Color.BLACK if key == "valid_support" else Color(0.5, 0.5, 0.5))
		var filename := "invalid_" + key + ".png"
		image.save_png(fixture.get_base_dir().path_join(filename))
		invalid.artifacts[key] = artifact(fixture.get_base_dir(), filename)
		check_rejected(parent, fixture, invalid, key)
		check(parent.get_node("AuthoredCanopySurface") == original, "Failed canopy image build alters previous geometry")
	check(not Canopy.build(parent, fixture, 3.0), "Fractional-cell tile size is accepted")
	check(parent.get_node("AuthoredCanopySurface") == original, "Failed canopy tile build alters previous geometry")
	parent.free()

func check_rejected(parent: Node3D, fixture: String, invalid: Dictionary, detail: String) -> void:
	var path := fixture.get_base_dir().path_join("invalid.json")
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(invalid))
	file.close()
	check(not Canopy.build(parent, path), "Invalid canopy input is accepted: %s" % detail)
