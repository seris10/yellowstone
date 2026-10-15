class_name YellowstoneForestFloorGeometry
extends RefCounted
## Compact opaque blades, leaves and deadwood fragments.

static func plant(guild: String, detailed: bool, material: Material) -> ArrayMesh:
	var data := _data()
	var rng := RandomNumberGenerator.new()
	rng.seed = 5189 + guild.hash()
	if guild in ["elk_sedge", "pinegrass"]:
		var count := 24 if detailed else 12
		for i: int in count:
			var angle := rng.randf() * TAU
			var direction := Vector3(cos(angle), 0.0, sin(angle))
			var side := direction.cross(Vector3.UP)
			var root := direction * rng.randf_range(0.01, 0.12)
			var height := 1.0 if i == 0 else rng.randf_range(0.45, 0.96)
			var reach := rng.randf_range(0.12, 0.31)
			var width := 0.012 if guild == "elk_sedge" else 0.020
			var steps := 4 if detailed else 2
			for segment: int in steps:
				var t0 := float(segment) / steps
				var t1 := float(segment + 1) / steps
				var a := root + direction * reach * t0 * t0 + Vector3.UP * height * (2.0 * t0 - t0 * t0)
				var b := root + direction * reach * t1 * t1 + Vector3.UP * height * (2.0 * t1 - t1 * t1)
				var w0 := width * (1.0 - t0 * 0.92)
				var w1 := width * (1.0 - t1 * 0.92)
				var color := Color("6c7d3e").srgb_to_linear().lerp(Color("9e975d").srgb_to_linear(), rng.randf() * 0.4)
				_quad(data, a - side * w0, a + side * w0, b + side * w1, b - side * w1, color, t0, t1)
	else:
		var stems := 5 if detailed else 3
		for stem: int in stems:
			var angle := rng.randf() * TAU
			var direction := Vector3(cos(angle), 0.0, sin(angle))
			var root := direction * rng.randf_range(0.02, 0.20)
			var height := 1.0 if stem == 0 else rng.randf_range(0.5, 0.9)
			var tip := root + direction * 0.10 + Vector3.UP * height
			var levels := 5 if detailed else 3
			var previous := root
			for level: int in levels:
				var t := 0.2 + float(level) / levels * 0.68
				var anchor := root.lerp(tip, t)
				_tube(data, previous, anchor, 0.005, 0.004, 3, Color("6c623d").srgb_to_linear(), true)
				previous = anchor
				for side: int in [-1, 1]:
					var leaf_dir := direction.rotated(Vector3.UP, side * 1.2 + rng.randf_range(-0.3, 0.3))
					var length := rng.randf_range(0.09, 0.17)
					_leaf(data, anchor, leaf_dir, length, length * 0.42, 0.07, Color("648444").srgb_to_linear(), anchor.y)
			_tube(data, previous, tip, 0.004, 0.001, 3, Color("6c623d").srgb_to_linear(), true)
	return _mesh(data, material)

static func litter(detailed: bool, material: Material) -> ArrayMesh:
	var data := _data()
	var rng := RandomNumberGenerator.new()
	rng.seed = 16049
	_litter_bed(data, detailed)
	for i: int in (96 if detailed else 24):
		var angle := rng.randf() * TAU
		var r := sqrt(rng.randf()) * 0.43
		var start := Vector3(cos(angle) * r, rng.randf_range(0.001, 0.003), sin(angle) * r)
		var direction := Vector3(cos(i * 2.399), 0, sin(i * 2.399))
		var length := rng.randf_range(0.010, 0.026)
		for side: int in [-1, 1]:
			var tip := start + direction.rotated(Vector3.UP, side * 0.12) * length
			var width := direction.cross(Vector3.UP) * 0.0013
			_quad(data, start - width, start + width, tip + Vector3.UP * 0.001, tip, Color("92805c").srgb_to_linear(), 0.0, 0.0)
	for i: int in (5 if detailed else 3):
		var start := Vector3(rng.randf_range(-0.25, 0.25), 0.0065, rng.randf_range(-0.25, 0.25))
		var end := start + Vector3(rng.randf_range(-0.15, 0.15), 0.0015, rng.randf_range(-0.15, 0.15))
		_tube(data, start, end, 0.006, 0.003, 5 if detailed else 3, Color("796956").srgb_to_linear(), false)
		if detailed:
			_tube(data, start.lerp(end, 0.65), end + Vector3(0.07, 0.004, 0.04), 0.003, 0.001, 3, Color("796956").srgb_to_linear(), false)
	for i: int in (8 if detailed else 3):
		var start := Vector3(rng.randf_range(-0.25, 0.25), 0.001, rng.randf_range(-0.25, 0.25))
		var direction := Vector3(cos(i * 1.72), 0, sin(i * 1.72))
		_leaf(data, start, direction, 0.10, 0.025, 0.008, Color("a18c66").srgb_to_linear(), 0.0)
	for vertex: int in data.vertices.size():
		if data.uv2[vertex].y < 0.5:
			var point: Vector3 = data.vertices[vertex]
			point.y += litter_bed_height(Vector2(point.x, point.z), detailed)
			data.vertices[vertex] = point
	for vertex: int in range(0, data.vertices.size(), 3):
		var normal: Vector3 = (data.vertices[vertex + 2] - data.vertices[vertex]).cross(data.vertices[vertex + 1] - data.vertices[vertex]).normalized()
		for offset: int in 3:
			data.normals[vertex + offset] = normal
	var mesh := _mesh(data, material)
	mesh.regen_normal_maps()
	return mesh

static func litter_bed_height(point: Vector2, detailed: bool) -> float:
	var segments := 32 if detailed else 16
	for segment: int in segments:
		var a := _litter_edge(segment, segments)
		var b := _litter_edge(segment + 1, segments)
		var determinant := a.cross(b)
		var weight_a := point.cross(b) / determinant
		var weight_b := a.cross(point) / determinant
		if weight_a >= -0.000001 and weight_b >= -0.000001 and weight_a + weight_b <= 1.000001:
			return 0.004 - 0.003 * (weight_a + weight_b)
	return 0.0

static func litter_bed_area(detailed: bool) -> float:
	var segments := 32 if detailed else 16
	var area := 0.0
	for segment: int in segments:
		area += absf(_litter_edge(segment, segments).cross(_litter_edge(segment + 1, segments))) * 0.5
	return area

static func _litter_edge(segment: int, segments: int) -> Vector2:
	var angle := TAU * segment / segments
	var radius := 0.445 + 0.035 * sin(angle * 5.0) + 0.014 * sin(angle * 11.0)
	return Vector2(cos(angle), sin(angle)) * radius

static func _litter_bed(data: Dictionary, detailed: bool) -> void:
	var segments := 32 if detailed else 16
	var center := Vector3(0.0, 0.004, 0.0)
	for i: int in segments:
		var edge_a := _litter_edge(i, segments)
		var edge_b := _litter_edge(i + 1, segments)
		var a := Vector3(edge_a.x, 0.001, edge_a.y)
		var b := Vector3(edge_b.x, 0.001, edge_b.y)
		_triangle(data, center, b, a, Color.WHITE, 0.0)
		for vertex: int in range(data.vertices.size() - 3, data.vertices.size()):
			var point: Vector3 = data.vertices[vertex]
			data.uv[vertex] = Vector2(point.x + 0.5, point.z + 0.5)
			data.uv2[vertex] = Vector2(0.0, 1.0)
			data.colors[vertex] = Color(1.0, 1.0, 1.0, 1.0 if point == center else 0.0)

static func log_mesh(detailed: bool, material: Material) -> ArrayMesh:
	var data := _data()
	_tube(data, Vector3(0, -0.5, 0), Vector3(0, 0.5, 0), 0.5, 0.5, 10 if detailed else 6, Color.WHITE, false, 1.0, true)
	if detailed:
		for i: int in 4:
			var angle := fposmod(i * 2.399, PI)
			var start := Vector3(0, -0.32 + i * 0.19, 0)
			var end := start + Vector3(cos(angle) * 0.95, 0.025, sin(angle) * 0.95)
			_tube(data, start, end, 0.10, 0.035, 5, Color.WHITE, false, 0.03)
	var mesh := _mesh(data, material)
	mesh.regen_normal_maps()
	return mesh

static func _leaf(data: Dictionary, start: Vector3, direction: Vector3, length: float, width: float, camber: float, color: Color, weight: float) -> void:
	var side := direction.cross(Vector3.UP).normalized() * width
	var middle := start + direction * length * 0.5 + Vector3.UP * camber
	var outline: Array[Vector3] = [start]
	for t: float in [0.25, 0.5, 0.75]:
		outline.append(start + direction * length * t - side * sin(PI * t) + Vector3.UP * camber * 0.35 * sin(PI * t))
	outline.append(start + direction * length + Vector3.UP * camber * 0.15)
	for t: float in [0.75, 0.5, 0.25]:
		outline.append(start + direction * length * t + side * sin(PI * t) + Vector3.UP * camber * 0.35 * sin(PI * t))
	for i: int in outline.size():
		_triangle(data, outline[i], outline[(i + 1) % outline.size()], middle, color, weight)

static func _tube(data: Dictionary, a: Vector3, b: Vector3, r0: float, r1: float, sides: int, color: Color, flexible: bool, radial_y_scale: float = 1.0, cylinder_uv: bool = false) -> void:
	var axis := (b - a).normalized()
	var side := axis.cross(Vector3.FORWARD if absf(axis.z) < 0.9 else Vector3.RIGHT).normalized()
	var other := axis.cross(side).normalized()
	for i: int in sides:
		var t0 := TAU * i / sides
		var t1 := TAU * (i + 1) / sides
		var d0 := side * cos(t0) + other * sin(t0)
		var d1 := side * cos(t1) + other * sin(t1)
		d0.y *= radial_y_scale
		d1.y *= radial_y_scale
		_quad(data, a + d0 * r0, a + d1 * r0, b + d1 * r1, b + d0 * r1, color, maxf(a.y, 0.0) if flexible else 0.0, maxf(b.y, 0.0) if flexible else 0.0)
		if cylinder_uv:
			var offset: int = data.vertices.size() - 6
			var u0 := float(i) / sides
			var u1 := float(i + 1) / sides
			var uv := [Vector2(u0, 0), Vector2(u1, 1), Vector2(u1, 0), Vector2(u0, 0), Vector2(u0, 1), Vector2(u1, 1)]
			for j: int in 6:
				data.uv[offset + j] = uv[j]
				var point: Vector3 = data.vertices[offset + j]
				data.normals[offset + j] = Vector3(point.x, 0, point.z).normalized()
		_triangle(data, a, a + d1 * r0, a + d0 * r0, color, 0.0)
		_triangle(data, b, b + d0 * r1, b + d1 * r1, color, b.y if flexible else 0.0)
		if cylinder_uv:
			for j: int in range(data.vertices.size() - 6, data.vertices.size()):
				var point: Vector3 = data.vertices[j]
				data.uv[j] = Vector2(point.x + 0.5, point.z + 0.5)
				data.uv2[j] = Vector2(0, 1)

static func _quad(data: Dictionary, a: Vector3, b: Vector3, c: Vector3, d: Vector3, color: Color, lower: float, upper: float) -> void:
	_triangle(data, a, b, c, color, lower, lower, upper)
	_triangle(data, a, c, d, color, lower, upper, upper)

static func _triangle(data: Dictionary, a: Vector3, b: Vector3, c: Vector3, color: Color, wa: float, wb: float = -1.0, wc: float = -1.0) -> void:
	var normal := (b - a).cross(c - a).normalized()
	if normal.length_squared() < 0.5:
		return
	data.vertices.append_array(PackedVector3Array([a, c, b]))
	data.normals.append_array(PackedVector3Array([normal, normal, normal]))
	data.colors.append_array(PackedColorArray([color, color, color]))
	data.uv.append_array(PackedVector2Array([Vector2(0, 0), Vector2(1, 0), Vector2(0.5, 1)]))
	data.uv2.append_array(PackedVector2Array([Vector2(wa, 0), Vector2(wc if wc >= 0 else wa, 0), Vector2(wb if wb >= 0 else wa, 0)]))

static func _data() -> Dictionary:
	return {"vertices": PackedVector3Array(), "normals": PackedVector3Array(), "colors": PackedColorArray(), "uv": PackedVector2Array(), "uv2": PackedVector2Array()}

static func _mesh(data: Dictionary, material: Material) -> ArrayMesh:
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = data.vertices
	arrays[Mesh.ARRAY_NORMAL] = data.normals
	arrays[Mesh.ARRAY_COLOR] = data.colors
	arrays[Mesh.ARRAY_TEX_UV] = data.uv
	arrays[Mesh.ARRAY_TEX_UV2] = data.uv2
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, material)
	return mesh
