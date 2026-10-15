class_name YellowstoneWaterPolygonCut
extends RefCounted

const AREA_EPSILON := 0.00000001

static func signed_area(polygon: PackedVector2Array) -> float:
	var area := 0.0
	for index: int in range(1, polygon.size() - 1):
		area += (polygon[index] - polygon[0]).cross(polygon[index + 1] - polygon[0]) * 0.5
	return area

static func bounds(polygon: PackedVector2Array) -> Rect2:
	var result := Rect2(polygon[0], Vector2.ZERO)
	for point: Vector2 in polygon:
		result = result.expand(point)
	return result

static func _clean(polygon: PackedVector2Array) -> PackedVector2Array:
	var result := PackedVector2Array()
	for point: Vector2 in polygon:
		if result.is_empty() or point.distance_squared_to(result[-1]) > 0.000000000001:
			result.append(point)
	if result.size() > 1 and result[0].distance_squared_to(result[-1]) <= 0.000000000001:
		result.resize(result.size() - 1)
	return result

static func _half_plane(subject: PackedVector2Array, a: Vector2, b: Vector2, inside: bool) -> PackedVector2Array:
	var result := PackedVector2Array()
	var direction := b - a
	var previous := subject[-1]
	var previous_side: float = direction.cross(previous - a)
	var previous_kept: bool = previous_side >= 0.0 if inside else previous_side <= 0.0
	for point: Vector2 in subject:
		var side: float = direction.cross(point - a)
		var kept: bool = side >= 0.0 if inside else side <= 0.0
		if kept != previous_kept:
			var fraction: float = previous_side / (previous_side - side)
			result.append(previous.lerp(point, clampf(fraction, 0.0, 1.0)))
		if kept:
			result.append(point)
		previous = point
		previous_side = side
		previous_kept = kept
	return _clean(result)

static func subtract_convex(subject: PackedVector2Array, clip: PackedVector2Array) -> Array[PackedVector2Array]:
	var remaining := subject
	var outside: Array[PackedVector2Array] = []
	var oriented := clip.duplicate()
	if signed_area(oriented) < 0.0:
		oriented.reverse()
	for index: int in oriented.size():
		if remaining.size() < 3:
			break
		var a := oriented[index]
		var b := oriented[(index + 1) % oriented.size()]
		var piece := _half_plane(remaining, a, b, false)
		if piece.size() >= 3 and absf(signed_area(piece)) > AREA_EPSILON:
			outside.append(piece)
		remaining = _half_plane(remaining, a, b, true)
	return outside

static func prepare_regions(pools: Array) -> Dictionary:
	var regions: Array[Dictionary] = []
	for pool: Dictionary in pools:
		if not bool(pool.get("thermal", false)):
			continue
		var polygon := PackedVector2Array()
		for point: Array in pool.get("ring", []):
			if point.size() != 2:
				return {"ok": false, "reason": "A water coordinate requires two components"}
			var position := Vector2(float(point[0]), float(point[1]))
			if not position.is_finite():
				return {"ok": false, "reason": "A water coordinate is non-finite"}
			polygon.append(position)
		polygon = _clean(polygon)
		if polygon.size() < 3:
			continue
		var triangulated := Geometry2D.triangulate_polygon(polygon)
		if triangulated.size() != (polygon.size() - 2) * 3:
			return {"ok": false, "reason": "A water polygon cannot be triangulated"}
		var triangles: Array[Dictionary] = []
		for start: int in range(0, triangulated.size(), 3):
			var triangle := PackedVector2Array([polygon[triangulated[start]], polygon[triangulated[start + 1]], polygon[triangulated[start + 2]]])
			triangles.append({"polygon": triangle, "bounds": bounds(triangle)})
		var water_y := NAN
		var center: Variant = pool.get("center")
		if center is Array and center.size() >= 2:
			water_y = float(center[1])
			if not is_finite(water_y):
				return {"ok": false, "reason": "A water surface elevation is non-finite"}
		regions.append({"polygon": polygon, "bounds": bounds(polygon), "triangles": triangles, "water_y": water_y})
	return {"ok": true, "regions": regions}

static func subtract_regions(subject: PackedVector2Array, regions: Array[Dictionary]) -> Array[PackedVector2Array]:
	var pieces: Array[PackedVector2Array] = [subject]
	for region: Dictionary in regions:
		if not bounds(subject).intersects(region.bounds, true):
			continue
		for clip: Dictionary in region.triangles:
			var next: Array[PackedVector2Array] = []
			for piece: PackedVector2Array in pieces:
				if bounds(piece).intersects(clip.bounds, true):
					next.append_array(subtract_convex(piece, clip.polygon))
				else:
					next.append(piece)
			pieces = next
			if pieces.is_empty():
				return pieces
	return pieces

class MeshBuilder extends RefCounted:
	var source: Array
	var vertices: PackedVector3Array
	var normals: PackedVector3Array
	var uv: PackedVector2Array
	var uv2: PackedVector2Array
	var colors: PackedColorArray
	var tangents: PackedFloat32Array
	var indices := PackedInt32Array()

	func _init(arrays: Array) -> void:
		source = arrays
		vertices = arrays[Mesh.ARRAY_VERTEX].duplicate()
		if arrays[Mesh.ARRAY_NORMAL] != null:
			normals = arrays[Mesh.ARRAY_NORMAL].duplicate()
		if arrays[Mesh.ARRAY_TEX_UV] != null:
			uv = arrays[Mesh.ARRAY_TEX_UV].duplicate()
		if arrays[Mesh.ARRAY_TEX_UV2] != null:
			uv2 = arrays[Mesh.ARRAY_TEX_UV2].duplicate()
		if arrays[Mesh.ARRAY_COLOR] != null:
			colors = arrays[Mesh.ARRAY_COLOR].duplicate()
		if arrays[Mesh.ARRAY_TANGENT] != null:
			tangents = arrays[Mesh.ARRAY_TANGENT].duplicate()

	func clear_output() -> void:
		vertices.clear()
		normals.clear()
		uv.clear()
		uv2.clear()
		colors.clear()
		tangents.clear()

	func append_copy(index: int, position: Vector3) -> int:
		var result := vertices.size()
		vertices.append(position)
		if source[Mesh.ARRAY_NORMAL] != null:
			normals.append(normals[index])
		if source[Mesh.ARRAY_TEX_UV] != null:
			uv.append(uv[index])
		if source[Mesh.ARRAY_TEX_UV2] != null:
			uv2.append(uv2[index])
		if source[Mesh.ARRAY_COLOR] != null:
			colors.append(colors[index])
		if source[Mesh.ARRAY_TANGENT] != null:
			tangents.append_array(tangents.slice(index*4, index*4 + 4))
		return result

	func append_vertex(point: Vector2, triangle: PackedVector2Array, corners: PackedInt32Array) -> int:
		var denominator: float = (triangle[1] - triangle[0]).cross(triangle[2] - triangle[0])
		var weights := Vector3((triangle[1] - point).cross(triangle[2] - point),
			(triangle[2] - point).cross(triangle[0] - point), 0) / denominator
		weights.z = 1.0 - weights.x - weights.y
		var a: Vector3 = source[Mesh.ARRAY_VERTEX][corners[0]]
		var position: Vector3 = a + (source[Mesh.ARRAY_VERTEX][corners[1]] - a) * weights.y + (source[Mesh.ARRAY_VERTEX][corners[2]] - a) * weights.z
		var normal := Vector3.ZERO
		var texture_uv := Vector2.ZERO
		var texture_uv2 := Vector2.ZERO
		var color := Color(0, 0, 0, 0)
		var tangent := Vector3.ZERO
		var handedness := 0.0
		for index: int in 3:
			var corner: int = corners[index]
			var weight: float = weights[index]
			if source[Mesh.ARRAY_NORMAL] != null:
				normal += source[Mesh.ARRAY_NORMAL][corner] * weight
			if source[Mesh.ARRAY_TEX_UV] != null:
				texture_uv += source[Mesh.ARRAY_TEX_UV][corner] * weight
			if source[Mesh.ARRAY_TEX_UV2] != null:
				texture_uv2 += source[Mesh.ARRAY_TEX_UV2][corner] * weight
			if source[Mesh.ARRAY_COLOR] != null:
				color += source[Mesh.ARRAY_COLOR][corner] * weight
			if source[Mesh.ARRAY_TANGENT] != null:
				var packed: PackedFloat32Array = source[Mesh.ARRAY_TANGENT]
				tangent += Vector3(packed[corner*4], packed[corner*4 + 1], packed[corner*4 + 2]) * weight
				handedness += packed[corner*4 + 3] * weight
		var result := vertices.size()
		vertices.append(position)
		if source[Mesh.ARRAY_NORMAL] != null:
			normals.append(normal.normalized())
		if source[Mesh.ARRAY_TEX_UV] != null:
			uv.append(texture_uv)
		if source[Mesh.ARRAY_TEX_UV2] != null:
			uv2.append(texture_uv2)
		if source[Mesh.ARRAY_COLOR] != null:
			colors.append(color)
		if source[Mesh.ARRAY_TANGENT] != null:
			tangent = tangent.normalized()
			tangents.append_array(PackedFloat32Array([tangent.x, tangent.y, tangent.z, -1.0 if handedness < 0 else 1.0]))
		return result

	func output() -> Array:
		var result: Array = []
		result.resize(Mesh.ARRAY_MAX)
		result[Mesh.ARRAY_VERTEX] = vertices
		result[Mesh.ARRAY_INDEX] = indices
		for pair: Array in [[Mesh.ARRAY_NORMAL, normals], [Mesh.ARRAY_TEX_UV, uv], [Mesh.ARRAY_TEX_UV2, uv2], [Mesh.ARRAY_COLOR, colors], [Mesh.ARRAY_TANGENT, tangents]]:
			if not pair[1].is_empty():
				result[pair[0]] = pair[1]
		return result

static func _append_shoreline_segment(builder: MeshBuilder, a: Vector2, b: Vector2, water_y: float,
		triangle: PackedVector2Array, corners: PackedInt32Array, transform: Transform3D, seen: Dictionary) -> void:
	var key_a := "%.4f:%.4f" % [a.x, a.y]
	var key_b := "%.4f:%.4f" % [b.x, b.y]
	var key := (key_a + ":" + key_b if key_a < key_b else key_b + ":" + key_a) + ":%.4f" % water_y
	if seen.has(key):
		return
	seen[key] = a.distance_to(b)
	var top_a := builder.append_vertex(a, triangle, corners)
	var top_b := builder.append_vertex(b, triangle, corners)
	var position_a: Vector3 = transform * builder.vertices[top_a]
	var position_b: Vector3 = transform * builder.vertices[top_b]
	position_a.y = water_y
	position_b.y = water_y
	var inverse := transform.affine_inverse()
	var bottom_a := builder.append_copy(top_a, inverse * position_a)
	var bottom_b := builder.append_copy(top_b, inverse * position_b)
	for face: PackedInt32Array in [PackedInt32Array([top_a, bottom_a, top_b]), PackedInt32Array([top_b, bottom_a, bottom_b])]:
		var normal := (builder.vertices[face[1]] - builder.vertices[face[0]]).cross(builder.vertices[face[2]] - builder.vertices[face[0]])
		if normal.length_squared() > 0.000000000001:
			builder.indices.append_array(face)
			builder.indices.append_array(PackedInt32Array([face[0], face[2], face[1]]))

static func _append_shoreline_edges(builder: MeshBuilder, pieces: Array[PackedVector2Array], triangle: PackedVector2Array,
		corners: PackedInt32Array, regions: Array[Dictionary], transform: Transform3D, seen: Dictionary) -> void:
	for piece: PackedVector2Array in pieces:
		for edge: int in piece.size():
			var a := piece[edge]
			var b := piece[(edge + 1) % piece.size()]
			var direction := b - a
			var length2 := direction.length_squared()
			if length2 < 0.00000001:
				continue
			for region: Dictionary in regions:
				if not is_finite(region.water_y) or not region.bounds.grow(.0002).intersects(bounds(PackedVector2Array([a, b])), true):
					continue
				var ring: PackedVector2Array = region.polygon
				for index: int in ring.size():
					var start := ring[index]
					var end := ring[(index + 1) % ring.size()]
					var shore_direction := end - start
					if absf(shore_direction.cross(a - start)) > .0002*shore_direction.length() or absf(shore_direction.cross(b - start)) > .0002*shore_direction.length():
						continue
					var t0 := (start - a).dot(direction) / length2
					var t1 := (end - a).dot(direction) / length2
					var low := maxf(0, minf(t0, t1))
					var high := minf(1, maxf(t0, t1))
					if (high - low)*sqrt(length2) > .0001:
						_append_shoreline_segment(builder, a + direction*low, a + direction*high, region.water_y, triangle, corners, transform, seen)

static func cut(source: ArrayMesh, transform: Transform3D, pools: Array) -> Dictionary:
	if source.get_surface_count() != 1 or source.surface_get_primitive_type(0) != Mesh.PRIMITIVE_TRIANGLES or source.get_blend_shape_count() != 0 or source.shadow_mesh != null:
		return {"ok": false, "reason": "Water cut requires one indexed triangle surface without auxiliary geometry"}
	var stored: Variant = source.get("_surfaces")
	if stored is Array and stored.size() == 1 and stored[0].get("lods") != null:
		return {"ok": false, "reason": "Water cut requires source LODs to be clipped separately"}
	if not transform.origin.is_finite() or not transform.basis.x.is_finite() or not transform.basis.y.is_finite() or not transform.basis.z.is_finite():
		return {"ok": false, "reason": "Water cut transform is non-finite"}
	if absf(transform.basis.determinant()) < 0.000000001:
		return {"ok": false, "reason": "Water cut transform is singular"}
	var arrays := source.surface_get_arrays(0)
	var projected := PackedVector2Array()
	for vertex: Vector3 in arrays[Mesh.ARRAY_VERTEX]:
		var world: Vector3 = transform * vertex
		if not vertex.is_finite() or not world.is_finite():
			return {"ok": false, "reason": "Water cut source coordinates are non-finite"}
		projected.append(Vector2(world.x, world.z))
	for attribute: int in [Mesh.ARRAY_BONES, Mesh.ARRAY_WEIGHTS, Mesh.ARRAY_CUSTOM0, Mesh.ARRAY_CUSTOM1, Mesh.ARRAY_CUSTOM2, Mesh.ARRAY_CUSTOM3]:
		if arrays[attribute] != null and not arrays[attribute].is_empty():
			return {"ok": false, "reason": "Water cut encounters unsupported vertex attributes"}
	var original: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	if original.is_empty() or original.size() % 3 != 0:
		return {"ok": false, "reason": "Water cut requires complete indexed triangles"}
	var prepared := prepare_regions(pools)
	if not prepared.ok:
		return prepared
	var regions: Array[Dictionary] = prepared.regions
	var builder := MeshBuilder.new(arrays)
	var shoreline := MeshBuilder.new(arrays)
	shoreline.clear_output()
	var shoreline_segments: Dictionary = {}
	var removed := 0
	var split := 0
	var roundoff_winding_corrections := 0
	var source_area := 0.0
	var retained_area := 0.0
	for start: int in range(0, original.size(), 3):
		var corners := PackedInt32Array([original[start], original[start + 1], original[start + 2]])
		var triangle := PackedVector2Array()
		for corner: int in corners:
			triangle.append(projected[corner])
		var area: float = absf(signed_area(triangle))
		source_area += area
		var candidate := false
		var inside := false
		var triangle_bounds := bounds(triangle)
		for region: Dictionary in regions:
			if not triangle_bounds.intersects(region.bounds, true):
				continue
			candidate = true
			if Geometry2D.is_point_in_polygon(triangle[0], region.polygon) and Geometry2D.is_point_in_polygon(triangle[1], region.polygon) and Geometry2D.is_point_in_polygon(triangle[2], region.polygon) and Geometry2D.clip_polygons(triangle, region.polygon).is_empty():
				inside = true
				break
		if inside:
			removed += 1
			continue
		if not candidate or area <= AREA_EPSILON:
			builder.indices.append_array(corners)
			retained_area += area
			continue
		var pieces := subtract_regions(triangle, regions)
		_append_shoreline_edges(shoreline, pieces, triangle, corners, regions, transform, shoreline_segments)
		var remaining_area := 0.0
		for piece: PackedVector2Array in pieces:
			remaining_area += absf(signed_area(piece))
		if absf(remaining_area - area) < 0.000001:
			builder.indices.append_array(corners)
			retained_area += area
			continue
		if pieces.is_empty():
			removed += 1
			continue
		split += 1
		for piece: PackedVector2Array in pieces:
			var mapped := PackedInt32Array()
			for point: Vector2 in piece:
				mapped.append(builder.append_vertex(point, triangle, corners))
			for index: int in range(1, piece.size() - 1):
				var emitted := PackedVector2Array()
				for vertex_index: int in [mapped[0], mapped[index], mapped[index + 1]]:
					var world_vertex: Vector3 = transform * builder.vertices[vertex_index]
					emitted.append(Vector2(world_vertex.x, world_vertex.z))
				var emitted_signed_area: float = signed_area(emitted)
				var piece_area: float = absf(emitted_signed_area)
				if piece_area > AREA_EPSILON:
					if emitted_signed_area * signed_area(triangle) < 0.0:
						roundoff_winding_corrections += 1
						builder.indices.append_array(PackedInt32Array([mapped[0], mapped[index + 1], mapped[index]]))
					else:
						builder.indices.append_array(PackedInt32Array([mapped[0], mapped[index], mapped[index + 1]]))
					retained_area += piece_area
	var mesh := ArrayMesh.new()
	if not builder.indices.is_empty():
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, builder.output())
		mesh.surface_set_material(0, source.surface_get_material(0))
	var shoreline_mesh := ArrayMesh.new()
	if not shoreline.indices.is_empty():
		shoreline_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, shoreline.output())
		shoreline_mesh.surface_set_material(0, source.surface_get_material(0))
	var shoreline_length := 0.0
	for length: float in shoreline_segments.values():
		shoreline_length += length
	return {"ok": true, "mesh": mesh, "shoreline_mesh": shoreline_mesh,
		"shoreline_closure_length_m": shoreline_length,
		"shoreline_closure_segments": shoreline_segments.size(), "shoreline_closure_triangles": int(shoreline.indices.size()/3),
		"shoreline_closure_scope": "authored vertical render interface between interpolated source edge and mapped flat water elevation; no bathymetry or collision modification",
		"removed_triangles": removed, "split_boundary_triangles": split,
		"retained_triangles": int(builder.indices.size()/3), "added_boundary_vertices": builder.vertices.size() - arrays[Mesh.ARRAY_VERTEX].size(),
		"roundoff_winding_corrections": roundoff_winding_corrections,
		"source_vertices_preserved": builder.vertices.slice(0, arrays[Mesh.ARRAY_VERTEX].size()) == arrays[Mesh.ARRAY_VERTEX],
		"source_xz_area_m2": source_area, "retained_xz_area_m2": retained_area, "removed_xz_area_m2": source_area - retained_area,
		"policy": "subtract triangulated mapped water polygons with convex half-plane partitions and barycentric attributes",
		"collision_scope": "unchanged source surface-elevation proxy; submerged bathymetry unavailable"}
