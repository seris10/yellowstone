extends SceneTree
## Mapped-water subtraction and barycentric source preservation.

const Core = preload("res://scripts/core_terrain.gd")
const Cut = preload("res://scripts/water_polygon_cut.gd")
var failures: Array[String] = []
var checks := 0
var actual_core: Dictionary = {}

func check(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures.append(message)

func _initialize() -> void:
	call_deferred("run")

func mesh_for(points: PackedVector2Array, indices: PackedInt32Array) -> ArrayMesh:
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uv := PackedVector2Array()
	var uv2 := PackedVector2Array()
	var colors := PackedColorArray()
	var tangents := PackedFloat32Array()
	for point: Vector2 in points:
		vertices.append(Vector3(point.x, 2*point.x + .5*point.y + 3, point.y))
		normals.append(Vector3(-2, 1, -.5).normalized())
		uv.append(Vector2(point.x*3, point.y*2))
		uv2.append(point)
		colors.append(Color((point.x + 10)/20, .4, (point.y + 10)/20, 1))
		tangents.append_array(PackedFloat32Array([1, 0, 0, 1]))
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uv
	arrays[Mesh.ARRAY_TEX_UV2] = uv2
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_TANGENT] = tangents
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh

func verify_geometry(mesh: ArrayMesh, pools: Array, expected_area: float, source: ArrayMesh, transform := Transform3D.IDENTITY, winding: float = 1.0) -> void:
	var actual_area := 0.0
	if mesh.get_surface_count() == 0:
		check(expected_area == 0, "Empty output loses dry area")
		return
	var arrays := mesh.surface_get_arrays(0)
	var source_arrays := source.surface_get_arrays(0)
	var source_vertices: PackedVector3Array = source_arrays[Mesh.ARRAY_VERTEX]
	var source_indices: PackedInt32Array = source_arrays[Mesh.ARRAY_INDEX]
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	for vertex: Vector3 in vertices:
		check(vertex.is_finite() and absf(vertex.y - (2*vertex.x + .5*vertex.z + 3)) < .00001, "Boundary height leaves the source plane")
	for index: int in vertices.size():
		var vertex := vertices[index]
		check(arrays[Mesh.ARRAY_TEX_UV][index].distance_to(Vector2(vertex.x*3, vertex.z*2)) < .0001, "Boundary UV interpolation is incorrect")
		check(arrays[Mesh.ARRAY_TEX_UV2][index].distance_to(Vector2(vertex.x, vertex.z)) < .0001, "Boundary secondary UV interpolation is incorrect")
		var color: Color = arrays[Mesh.ARRAY_COLOR][index]
		# Decoded source colors allow one UNORM8 output quantization step.
		var source_color_found := false
		for start: int in range(0, source_indices.size(), 3):
			var a := source_vertices[source_indices[start]]
			var b := source_vertices[source_indices[start + 1]]
			var c := source_vertices[source_indices[start + 2]]
			var p := Vector2(vertex.x - a.x, vertex.z - a.z)
			var ab := Vector2(b.x - a.x, b.z - a.z)
			var ac := Vector2(c.x - a.x, c.z - a.z)
			var denominator := ab.cross(ac)
			var weights := Vector3(0, p.cross(ac)/denominator, ab.cross(p)/denominator)
			weights.x = 1 - weights.y - weights.z
			if minf(weights.x, minf(weights.y, weights.z)) < -.00001:
				continue
			var expected := Color(0, 0, 0, 0)
			for corner: int in 3:
				expected += source_arrays[Mesh.ARRAY_COLOR][source_indices[start + corner]] * weights[corner]
			source_color_found = true
			check(absf(color.r - expected.r) <= 1.0/255 + .000001 and absf(color.b - expected.b) <= 1.0/255 + .000001, "Boundary color differs from the decoded source field")
			break
		check(source_color_found, "Boundary vertex leaves all source triangles")
		check(absf(arrays[Mesh.ARRAY_NORMAL][index].length() - 1) < .0001, "Boundary normal is not unit length")
		check(absf(arrays[Mesh.ARRAY_TANGENT][index*4 + 3] - 1) < .0001, "Boundary tangent handedness changes")
	for start: int in range(0, indices.size(), 3):
		var triangle := PackedVector2Array()
		for corner: int in 3:
			var point: Vector3 = transform * vertices[indices[start + corner]]
			triangle.append(Vector2(point.x, point.z))
		var signed_area := Cut.signed_area(triangle)
		check(signed_area * winding > 0, "Output winding differs from the source triangle")
		var area := absf(signed_area)
		check(area > 0.00000001, "A degenerate boundary triangle remains")
		actual_area += area
		for pool: Dictionary in pools:
			if not pool.get("thermal", false):
				continue
			var polygon := PackedVector2Array()
			for point: Array in pool.ring:
				polygon.append(Vector2(point[0], point[1]))
			for overlap: PackedVector2Array in Geometry2D.intersect_polygons(triangle, polygon):
				check(absf(Cut.signed_area(overlap)) < .00002, "A retained triangle overlaps mapped water")
	check(absf(actual_area - expected_area) < .0002, "Dry-area conservation fails: %.9f != %.9f" % [actual_area, expected_area])

func verify_shoreline(result: Dictionary, expected_length: float, water_y: float, transform := Transform3D.IDENTITY) -> void:
	var mesh: ArrayMesh = result.shoreline_mesh
	check(mesh.get_surface_count() == 1, "The mapped water interface has no render surface")
	if mesh.get_surface_count() == 0:
		return
	var arrays := mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var length := 0.0
	for start: int in range(0, vertices.size(), 4):
		var a: Vector3 = transform * vertices[start]
		var b: Vector3 = transform * vertices[start + 1]
		var lower_a: Vector3 = transform * vertices[start + 2]
		var lower_b: Vector3 = transform * vertices[start + 3]
		length += Vector2(a.x, a.z).distance_to(Vector2(b.x, b.z))
		for corner: int in 2:
			var top: Vector3 = vertices[start + corner]
			check(absf(top.y - (2*top.x + .5*top.z + 3)) < .00001, "Shoreline top leaves its original terrain triangle")
			for attribute: int in [Mesh.ARRAY_COLOR, Mesh.ARRAY_TEX_UV, Mesh.ARRAY_TEX_UV2, Mesh.ARRAY_NORMAL]:
				check(arrays[attribute][start + corner].is_equal_approx(arrays[attribute][start + corner + 2]), "Shoreline attributes differ along the vertical interface")
		check(absf(lower_a.y - water_y) < .00001 and absf(lower_b.y - water_y) < .00001, "Shoreline interface does not reach the water plane")
		check(Vector2(a.x, a.z).distance_to(Vector2(lower_a.x, lower_a.z)) < .00001 and Vector2(b.x, b.z).distance_to(Vector2(lower_b.x, lower_b.z)) < .00001, "Shoreline interface moves the mapped horizontal boundary")
	check(absf(length - expected_length) < .0001, "Shoreline interface loses or duplicates a mapped boundary segment: %.8f != %.8f" % [length, expected_length])
	check(result.source_vertices_preserved, "Shoreline interface changes original terrain vertices")

func run() -> void:
	var source := mesh_for(PackedVector2Array([Vector2(.2, .2), Vector2(.8, .2), Vector2(.2, .8), Vector2(3, 3), Vector2(4, 3), Vector2(3, 4), Vector2(.5, .5), Vector2(3.5, .5), Vector2(.5, 3.5)]), PackedInt32Array([0, 1, 2, 3, 4, 5, 6, 7, 8]))
	var source_arrays := source.surface_get_arrays(0)
	var core := Core.new()
	root.add_child(core)
	var node := MeshInstance3D.new()
	node.mesh = source
	core.add_child(node)
	core._tile_mesh_instance = node
	var body := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	shape.shape = BoxShape3D.new()
	body.add_child(shape)
	core.add_child(body)
	core._tile_collision_body = body
	var collision_id := shape.shape.get_instance_id()
	var pools: Array = [{"thermal": true, "name": "concave fixture", "ring": [[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]]}]
	var report := core.cut_open_water(pools)
	check(report.ok and report.removed_triangles == 1 and report.split_boundary_triangles == 1, "Interior and partial triangles are not classified")
	verify_geometry(node.mesh, pools, 2.5, source)
	check(source.surface_get_arrays(0) == source_arrays, "Source mesh mutates")
	check(report.source_vertices_preserved, "Original vertex prefix changes")
	check(shape.shape.get_instance_id() == collision_id and not shape.disabled, "Collision changes during a render cut")
	check(core.cut_open_water(pools) == report, "Repeated cuts accumulate changes")
	core.cut_open_water([])
	check(node.mesh.surface_get_arrays(0) == source_arrays, "Empty water selection cannot restore the source")
	node.position.x = 10
	var transformed := core.cut_open_water(pools)
	check(transformed.removed_triangles == 0 and transformed.split_boundary_triangles == 0, "World-space cut ignores translation")
	node.position.x = 0
	check(core.cut_open_water(pools) == report, "Restored source cannot be recut")
	var large := mesh_for(PackedVector2Array([Vector2(-5, -5), Vector2(5, -5), Vector2(0, 5)]), PackedInt32Array([0, 1, 2]))
	var hole: Array = [{"thermal": true, "ring": [[-1, -1], [1, -1], [1, 1], [-1, 1]]}]
	var result := Cut.cut(large, Transform3D.IDENTITY, hole)
	check(result.ok, "Enclosed pool subtraction fails")
	verify_geometry(result.mesh, hole, 46, large)
	hole.append({"thermal": true, "ring": [[0, -1], [2, -1], [2, 1], [0, 1]]})
	result = Cut.cut(large, Transform3D.IDENTITY, hole)
	verify_geometry(result.mesh, hole, 44, large)
	var reversed := mesh_for(PackedVector2Array([Vector2(-5, -5), Vector2(5, -5), Vector2(0, 5)]), PackedInt32Array([2, 1, 0]))
	result = Cut.cut(reversed, Transform3D.IDENTITY, hole)
	verify_geometry(result.mesh, hole, 44, reversed, Transform3D.IDENTITY, -1.0)
	var covering: Array = [{"thermal": true, "ring": [[-10, -10], [10, -10], [10, 10], [-10, 10]]}]
	result = Cut.cut(large, Transform3D.IDENTITY, covering)
	check(result.ok and result.mesh.get_surface_count() == 0, "A wholly submerged source still renders vertices")
	var transform := Transform3D(Basis(Vector3.UP, .41).scaled(Vector3(1.2, 1, .8)), Vector3(17, 4, -9))
	var transformed_hole: Array = [{"thermal": true, "ring": []}]
	for point: Array in covering[0].ring:
		var p := transform * Vector3(point[0], 0, point[1])
		transformed_hole[0].ring.append([p.x, p.z])
	result = Cut.cut(large, transform, transformed_hole)
	check(result.ok and result.mesh.get_surface_count() == 0, "Rotated and scaled mesh cut ignores its transform")
	var transformed_inner: Array = [{"thermal": true, "ring": []}]
	for point: Array in hole[0].ring:
		var p := transform * Vector3(point[0], 0, point[1])
		transformed_inner[0].ring.append([p.x, p.z])
	result = Cut.cut(large, transform, transformed_inner)
	verify_geometry(result.mesh, transformed_inner, 46 * .96, large, transform)
	var edged_hole: Array = [{"thermal": true, "ring": hole[0].ring, "center": [0, 3, 0]}]
	result = Cut.cut(large, Transform3D.IDENTITY, edged_hole)
	verify_shoreline(result, 8, 3)
	var scaled_edge: Array = [{"thermal": true, "ring": transformed_inner[0].ring, "center": [17, 7, -9]}]
	result = Cut.cut(large, transform, scaled_edge)
	var mapped_perimeter := 0.0
	for index: int in 4:
		var a: Array = scaled_edge[0].ring[index]
		var b: Array = scaled_edge[0].ring[(index + 1) % 4]
		mapped_perimeter += Vector2(a[0], a[1]).distance_to(Vector2(b[0], b[1]))
	verify_shoreline(result, mapped_perimeter, 7, transform)
	var singular := Transform3D.IDENTITY
	singular.basis.x = Vector3.ZERO
	check(not Cut.cut(large, singular, edged_hole).ok, "Singular transform reaches the shoreline inverse")
	var nonthermal: Array = [{"thermal": false, "ring": covering[0].ring}]
	result = Cut.cut(large, Transform3D.IDENTITY, nonthermal)
	verify_geometry(result.mesh, nonthermal, 50, large)
	var grazing: Array = [{"thermal": true, "ring": [[-5, -7], [5, -7], [5, -5], [-5, -5]]}]
	result = Cut.cut(large, Transform3D.IDENTITY, grazing)
	verify_geometry(result.mesh, grazing, 50, large)
	var lod_mesh := ArrayMesh.new()
	var lod_arrays := mesh_for(PackedVector2Array([Vector2(-5, -5), Vector2(5, -5), Vector2(5, 5), Vector2(-5, 5)]), PackedInt32Array([0, 1, 2, 0, 2, 3])).surface_get_arrays(0)
	lod_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, lod_arrays, [], {10.0: PackedInt32Array([0, 1, 2])})
	check(not Cut.cut(lod_mesh, Transform3D.IDENTITY, hole).ok, "Unclipped source LODs are silently discarded")
	var invalid_transform := Transform3D.IDENTITY
	invalid_transform.origin.x = NAN
	check(not Cut.cut(large, invalid_transform, hole).ok, "A non-finite transform reaches polygon clipping")
	var invalid_pool: Array = [{"thermal": true, "ring": [[0, 0], [INF, 0], [0, 1]]}]
	check(not Cut.cut(large, Transform3D.IDENTITY, invalid_pool).ok, "A non-finite pool reaches polygon triangulation")
	if "--world" in OS.get_cmdline_user_args():
		verify_actual_core()
	var receipt := {"ok": failures.is_empty(), "cases": checks, "failures": failures, "actual_core": actual_core, "source_sha256": FileAccess.get_sha256("res://scripts/water_polygon_cut.gd")}
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			var file := FileAccess.open(argument.trim_prefix("--out="), FileAccess.WRITE)
			file.store_string(JSON.stringify(receipt, "\t") + "\n")
			file.close()
	print("OPEN_WATER_CUT ", JSON.stringify(receipt))
	quit(0 if failures.is_empty() else 1)

func verify_actual_core() -> void:
	var core := Core.new()
	root.add_child(core)
	check(core.build(null), "Actual core terrain does not build")
	if not core.built():
		return
	var world: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world.json"))
	var started := Time.get_ticks_msec()
	actual_core = core.cut_open_water(world.pools)
	actual_core["elapsed_ms"] = Time.get_ticks_msec() - started
	var extent: Dictionary = core.extent_rect()
	var rectangle := PackedVector2Array([Vector2(extent.x_min_m, extent.z_min_m), Vector2(extent.x_max_m, extent.z_min_m), Vector2(extent.x_max_m, extent.z_max_m), Vector2(extent.x_min_m, extent.z_max_m)])
	var expected := 0.0
	var perimeter := 0.0
	var all_boundaries_inside := true
	for pool: Dictionary in world.pools:
		if not pool.thermal:
			continue
		var polygon := PackedVector2Array()
		for point: Array in pool.ring:
			polygon.append(Vector2(point[0], point[1]))
		for index: int in polygon.size():
			perimeter += polygon[index].distance_to(polygon[(index + 1) % polygon.size()])
			all_boundaries_inside = all_boundaries_inside and Geometry2D.is_point_in_polygon(polygon[index], rectangle)
		for overlap: PackedVector2Array in Geometry2D.intersect_polygons(rectangle, polygon):
			expected += absf(Cut.signed_area(overlap))
	if all_boundaries_inside:
		actual_core["independent_mapped_perimeter_m"] = perimeter
		check(absf(actual_core.shoreline_closure_length_m - perimeter) < .001, "Actual closure loses or duplicates shoreline length")
	actual_core["independent_clipper_intersection_area_m2"] = expected
	actual_core["area_error_m2"] = absf(actual_core.removed_xz_area_m2 - expected)
	actual_core["world_sha256"] = FileAccess.get_sha256("res://data/world.json")
	actual_core["heightfield_sha256"] = FileAccess.get_sha256("res://data/core_terrain/core_heightfield.f32")
	check(actual_core.ok and actual_core.area_error_m2 < .05, "Actual core removed area differs from independent polygon intersections")
