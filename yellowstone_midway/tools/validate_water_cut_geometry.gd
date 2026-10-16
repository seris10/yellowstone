extends SceneTree
## Independent randomized polygon intersections and emitted winding.

const Cut = preload("res://scripts/water_polygon_cut.gd")
func _init() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 445101
	var worst_area: float = 0.0
	var worst_overlap: float = 0.0
	var flips: int = 0
	var max_flipped_area: float = 0.0
	var flipped_examples: Array = []
	for case: int in range(160):
		var offset := Vector2(rng.randf_range(-700, 700), rng.randf_range(-700, 700))
		var size: float = rng.randf_range(1.0, 24.0)
		var polygon := PackedVector2Array([offset, offset + Vector2(size, 0), offset + Vector2(0, size)])
		if case % 2:
			polygon.reverse()
		var vertices := PackedVector3Array()
		for point: Vector2 in polygon:
			vertices.append(Vector3(point.x, point.x * 0.1 - point.y * 0.2, point.y))
		var arrays: Array = []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = vertices
		arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2])
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		var shift := Vector2(rng.randf_range(-size * 0.2, size * 0.6), rng.randf_range(-size * 0.2, size * 0.6))
		var water := PackedVector2Array()
		for point: Vector2 in [Vector2.ZERO, Vector2(0.7, 0), Vector2(0.7, 0.3), Vector2(0.3, 0.3), Vector2(0.3, 0.7), Vector2(0, 0.7)]:
			water.append(offset + shift + point * size)
		var ring: Array = []
		for point: Vector2 in water:
			ring.append([point.x, point.y])
		var result := Cut.cut(mesh, Transform3D.IDENTITY, [{"thermal": true, "ring": ring}])
		if not result.ok:
			push_error("Valid fixture rejected")
			quit(1)
			return
		var expected: float = absf(Cut.signed_area(polygon))
		for intersection: PackedVector2Array in Geometry2D.intersect_polygons(polygon, water):
			expected -= absf(Cut.signed_area(intersection))
		worst_area = maxf(worst_area, absf(expected - result.retained_xz_area_m2))
		if result.mesh.get_surface_count() == 0:
			continue
		var output: Array = result.mesh.surface_get_arrays(0)
		var positions: PackedVector3Array = output[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = output[Mesh.ARRAY_INDEX]
		for k: int in range(0, indices.size(), 3):
			var triangle := PackedVector2Array()
			for j: int in range(3):
				var position := positions[indices[k+j]]
				triangle.append(Vector2(position.x, position.z))
			if Cut.signed_area(triangle) * Cut.signed_area(polygon) < 0.0:
				flips += 1
				max_flipped_area = maxf(max_flipped_area, absf(Cut.signed_area(triangle)))
				flipped_examples.append({"case": case, "area_m2": Cut.signed_area(triangle), "polygon": str(polygon), "triangle": str(triangle)})
			for overlap: PackedVector2Array in Geometry2D.intersect_polygons(triangle, water):
				worst_overlap = maxf(worst_overlap, absf(Cut.signed_area(overlap)))
	var result := {"cases": 160, "max_area_error_m2": worst_area, "max_retained_triangle_water_overlap_m2": worst_overlap, "winding_flips": flips, "max_flipped_area_m2": max_flipped_area, "flipped_examples": flipped_examples, "source_sha256": FileAccess.get_sha256("res://scripts/water_polygon_cut.gd"), "scope": "randomized independent Clipper intersections at local mapped coordinates", "ok": worst_area < 0.03 and worst_overlap < 0.03 and flips == 0}
	print(JSON.stringify(result))
	var file := FileAccess.open("res://work/water-cut-independent.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(result, "  ") + "\n")
	quit(0 if worst_area < 0.03 and worst_overlap < 0.03 and flips == 0 else 1)
