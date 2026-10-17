extends SceneTree
## Saved river ribbon and vegetation clearance validation.

# Mirrors the margin rule in tools/bake_world.gd.
const MARGIN_FRACTION := 0.23
const MARGIN_MIN_M := 0.8
const MARGIN_MAX_M := 5.0
const CLEARANCE_M := 0.3
const CELL_M := 32.0

var failures: Array[String] = []
var cells: Dictionary = {}
var segments: Array[Dictionary] = []

func _initialize() -> void:
	call_deferred("run")

func visual_half(river: Dictionary) -> float:
	var half := float(river.width) * 0.5
	if bool(river.get("thermal", false)):
		return half
	return half + clampf(float(river.width) * MARGIN_FRACTION, MARGIN_MIN_M, MARGIN_MAX_M)

func plan_area(a: Vector3, b: Vector3, c: Vector3) -> float:
	return ((b.x - a.x) * (c.z - a.z) - (c.x - a.x) * (b.z - a.z)) * 0.5

func check_ribbon(river: Dictionary, node: MeshInstance3D) -> Dictionary:
	var arrays := node.mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var colors: PackedColorArray = arrays[Mesh.ARRAY_COLOR]
	var non_finite := 0
	for vertex: Vector3 in vertices:
		if not vertex.is_finite():
			non_finite += 1
	var positive := 0
	var negative := 0
	for start: int in range(0, indices.size(), 3):
		var area := plan_area(vertices[indices[start]], vertices[indices[start + 1]], vertices[indices[start + 2]])
		if area > 0.000001:
			positive += 1
		elif area < -0.000001:
			negative += 1
	var folded := negative
	if positive == 0:
		failures.append("%s has no clockwise river faces" % river.id)
	var first_fade := colors[0].b
	var last_fade := colors[colors.size() - 1].b
	if non_finite > 0:
		failures.append("%s has %d non-finite vertices" % [river.id, non_finite])
	if folded > 0:
		failures.append("%s has %d triangles with reversed plan winding" % [river.id, folded])
	return {"id": river.id, "vertices": vertices.size(), "triangles": indices.size() / 3, "reversed_triangles": folded, "start_fade": first_fade, "end_fade": last_fade}

func index_segments(rivers: Array) -> void:
	for river: Dictionary in rivers:
		var reach := visual_half(river) + CLEARANCE_M
		var points: Array = river.points
		for i: int in range(points.size() - 1):
			var a := Vector2(float(points[i][0]), float(points[i][2]))
			var b := Vector2(float(points[i + 1][0]), float(points[i + 1][2]))
			var segment_index := segments.size()
			segments.append({"a": a, "b": b, "reach": reach, "name": river.name})
			var lo := Vector2(minf(a.x, b.x), minf(a.y, b.y)) - Vector2.ONE * reach
			var hi := Vector2(maxf(a.x, b.x), maxf(a.y, b.y)) + Vector2.ONE * reach
			for cx: int in range(int(floor(lo.x / CELL_M)), int(floor(hi.x / CELL_M)) + 1):
				for cz: int in range(int(floor(lo.y / CELL_M)), int(floor(hi.y / CELL_M)) + 1):
					var key := Vector2i(cx, cz)
					if not cells.has(key):
						cells[key] = []
					cells[key].append(segment_index)

func in_water(x: float, z: float) -> String:
	var found: Array = cells.get(Vector2i(int(floor(x / CELL_M)), int(floor(z / CELL_M))), [])
	var p := Vector2(x, z)
	for segment_index: int in found:
		var segment: Dictionary = segments[segment_index]
		var closest := Geometry2D.get_closest_point_to_segment(p, segment.a, segment.b)
		if p.distance_to(closest) <= float(segment.reach):
			return str(segment.name)
	return ""

func run() -> void:
	var started := Time.get_ticks_msec()
	var spec: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world.json"))
	var world: Node = load("res://scenes/authored_world.tscn").instantiate()
	var water := world.get_node_or_null("ConnectedWater")
	var ribbons: Array[Dictionary] = []
	for river: Dictionary in spec.rivers:
		var node := water.get_node_or_null(NodePath(str(river.id))) as MeshInstance3D if water != null else null
		if node == null:
			failures.append("missing river node " + str(river.id))
			continue
		var material := node.mesh.surface_get_material(0) as ShaderMaterial
		if not bool(river.get("thermal", false)) and (material == null or not material.shader.resource_path.ends_with("river_water.gdshader")):
			failures.append("%s does not use river_water.gdshader" % river.id)
		ribbons.append(check_ribbon(river, node))
	index_segments(spec.rivers)
	var inside: Dictionary = {}
	var checked := 0
	var vegetation := world.get_node_or_null("AuthoredVegetation")
	for child: Node in vegetation.get_children():
		var batch := child as MultiMeshInstance3D
		if batch == null or batch.multimesh == null:
			continue
		var mm := batch.multimesh
		var stride := 12 + (4 if mm.use_colors else 0) + (4 if mm.use_custom_data else 0)
		var buffer := mm.buffer
		for index: int in mm.instance_count:
			var at := index * stride
			var x := buffer[at + 3] + batch.position.x
			var z := buffer[at + 11] + batch.position.z
			checked += 1
			var name := in_water(x, z)
			if name != "":
				inside[name] = int(inside.get(name, 0)) + 1
	var total_inside := 0
	for name: String in inside:
		total_inside += int(inside[name])
	if total_inside > 0:
		failures.append("%d vegetation instance records lie inside river water" % total_inside)
	world.free()
	print("RIVER_SURFACE_VALIDATION ", JSON.stringify({"ok": failures.is_empty(), "failures": failures, "ribbons": ribbons,
		"vegetation_records_checked": checked, "records_in_water": inside, "seconds": (Time.get_ticks_msec() - started) / 1000.0}))
	quit(0 if failures.is_empty() else 1)
