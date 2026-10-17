extends SceneTree
## Saved river junction, bank width, outflow, and bridge-rail validation.

# Match river_ribbon's margin and clamp constants.
const MARGIN_FRACTION := 0.23
const MARGIN_MIN_M := 0.8
const MARGIN_MAX_M := 5.0
const MIN_REACH_FRACTION := 0.30
const JUNCTION_TOLERANCE_M := 1.5

var failures: Array[String] = []

func visual_half(river: Dictionary) -> float:
	# Include the bank margin on thermal outflow.
	return float(river.width) * 0.5 + clampf(float(river.width) * MARGIN_FRACTION, MARGIN_MIN_M, MARGIN_MAX_M)

func station_midpoint(vertices: PackedVector3Array, station: int) -> Vector3:
	return (vertices[station * 2] + vertices[station * 2 + 1]) * 0.5

func saved_centers(node: MeshInstance3D) -> PackedVector3Array:
	var result := PackedVector3Array()
	if node.mesh == null or node.mesh.get_surface_count() == 0:
		return result
	var vertices: PackedVector3Array = node.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var stations := int(node.get_meta("station_count", 0))
	if stations < 2 or vertices.size() < stations * 2:
		return result
	for station: int in stations:
		result.append(node.transform * station_midpoint(vertices, station))
	return result

func validate_junctions(rivers: Array, nodes: Dictionary) -> Array:
	var junctions: Array = []
	var centers: Dictionary = {}
	for id: String in nodes:
		centers[id] = saved_centers(nodes[id])
	for river: Dictionary in rivers:
		for end: int in [0, river.points.size() - 1]:
			var source: Array = river.points[end]
			var endpoint := Vector2(source[0], source[2])
			var source_gap := INF
			var receiver := ""
			for other: Dictionary in rivers:
				if other.id == river.id:
					continue
				for point: Array in other.points:
					var gap := endpoint.distance_to(Vector2(point[0], point[2]))
					if gap < source_gap:
						source_gap = gap
						receiver = str(other.id)
			if source_gap > JUNCTION_TOLERANCE_M:
				continue
			var a: PackedVector3Array = centers.get(str(river.id), PackedVector3Array())
			var b: PackedVector3Array = centers.get(receiver, PackedVector3Array())
			if a.is_empty() or b.is_empty():
				failures.append("missing saved junction geometry %s -> %s" % [river.id, receiver])
				junctions.append({"id": river.id, "end": end, "other": receiver, "gap_m": null})
				continue
			var mid := a[0 if end == 0 else a.size() - 1]
			var gap := INF
			for index: int in range(1, b.size()):
				var closest := Geometry2D.get_closest_point_to_segment(Vector2(mid.x, mid.z), Vector2(b[index - 1].x, b[index - 1].z), Vector2(b[index].x, b[index].z))
				gap = minf(gap, closest.distance_to(Vector2(mid.x, mid.z)))
			junctions.append({"id": river.id, "end": end, "other": receiver, "gap_m": gap})
			if gap > JUNCTION_TOLERANCE_M:
				failures.append("saved junction %s -> %s gap %.3f exceeds %.3f m" % [river.id, receiver, gap, JUNCTION_TOLERANCE_M])
	return junctions

func run() -> void:
	var started := Time.get_ticks_msec()
	var spec: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world.json"))
	var world: Node = load("res://scenes/authored_world.tscn").instantiate()
	var water: Node = world.get_node_or_null("ConnectedWater")
	if water == null:
		failures.append("missing ConnectedWater node")
		report(started, {}, [], {}, 0, 0)
		return
	var geometry := preload("res://tools/bake_world.gd").new()
	geometry.snap_water_junctions(spec.rivers)
	var nodes: Dictionary = {}
	for river: Dictionary in spec.rivers:
		var node := water.get_node_or_null(NodePath(str(river.id))) as MeshInstance3D
		if node != null:
			nodes[river.id] = node
	# Measure saved bank widths from the mapped centerline.
	var pinch: Dictionary = {}
	for river: Dictionary in spec.rivers:
		if not nodes.has(river.id):
			failures.append("missing river node " + str(river.id))
			continue
		var node: MeshInstance3D = nodes[river.id]
		var half := visual_half(river)
		var vertices: PackedVector3Array = node.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		var stations := int(node.get_meta("station_count", 0))
		var min_half := INF
		if stations < 2 or vertices.size() < stations * 2:
			failures.append("%s lacks station geometry" % river.id)
			continue
		var centers: PackedVector3Array = geometry.smooth_plan_view(geometry.resample_polyline(geometry.points_of(river.points)))
		if centers.size() != stations:
			failures.append("%s saved station count differs from mapped centerline" % river.id)
			continue
		for station: int in stations:
			for side: int in 2:
				min_half = minf(min_half, centers[station].distance_to(node.transform * vertices[station * 2 + side]))
		pinch[river.id] = {"minimum_saved_half_width_m": min_half, "visual_half_m": half}
		if min_half < half * MIN_REACH_FRACTION - 0.001:
			failures.append("%s saved half-width %.3f below the pinch floor %.3f" % [river.id, min_half, half * MIN_REACH_FRACTION])
	var junctions := validate_junctions(spec.rivers, nodes)
	# Check outflow tangents, cap feathering, and mouth position.
	var outflow: Dictionary = {}
	var outflow_node := water.get_node_or_null("authored_excelsior_outflow_01") as MeshInstance3D
	if outflow_node == null:
		failures.append("missing authored_excelsior_outflow_01 node")
	else:
		var arrays: Array = outflow_node.mesh.surface_get_arrays(0)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var colors: PackedColorArray = arrays[Mesh.ARRAY_COLOR]
		var stations := int(outflow_node.get_meta("station_count", 0))
		var feathered := 0
		for c: Color in colors:
			if c.b < 0.001:
				feathered += 1
		var mouth := station_midpoint(vertices, stations - 1) if stations >= 2 else Vector3.ZERO
		var mouth_gap := INF
		for river: Dictionary in spec.rivers:
			if str(river.id) == "river_5856_0":
				for q: Array in river.points:
					mouth_gap = minf(mouth_gap, Vector2(mouth.x - float(q[0]), mouth.z - float(q[2])).length())
		outflow = {"has_tangents": arrays[Mesh.ARRAY_TANGENT] != null, "feathered_rim_vertices": feathered, "mouth_gap_m": mouth_gap}
		if arrays[Mesh.ARRAY_TANGENT] == null:
			failures.append("outflow mesh lacks tangents; not built by river_ribbon")
		if feathered < 20:
			failures.append("outflow mouth cap rim is not feathered")
		if mouth_gap > JUNCTION_TOLERANCE_M:
			failures.append("outflow mouth gap %.3f m exceeds junction tolerance" % mouth_gap)
	# Detect anonymously named swept rails by ring topology.
	var swept := 0
	var posts := 0
	var timber_rails := 0
	var roads: Node = world.get_node_or_null("RoadsAndTrails")
	if roads == null:
		failures.append("missing RoadsAndTrails node")
	for child: Node in world.find_children("*", "MeshInstance3D", true, true):
		var mi := child as MeshInstance3D
		if mi.mesh == null:
			continue
		if "TimberRail" in child.name:
			timber_rails += 1
		if mi.mesh is BoxMesh:
			var size: Vector3 = (mi.mesh as BoxMesh).size
			if is_equal_approx(size.x, 0.12) and is_equal_approx(size.y, 1.12) and is_equal_approx(size.z, 0.12):
				posts += 1
			continue
		if roads == null or not (mi.mesh is ArrayMesh) or not roads.is_ancestor_of(mi):
			continue
		var arrays: Array = mi.mesh.surface_get_arrays(0)
		var ring_vertices := (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
		var triangles := (arrays[Mesh.ARRAY_INDEX] as PackedInt32Array).size() / 3
		if ring_vertices % 4 != 0 or ring_vertices < 8 or triangles != (ring_vertices / 4 - 1) * 8:
			continue
		swept += 1
	if swept != 54:
		failures.append("expected 54 swept bridge rails, found %d" % swept)
	geometry.free()
	world.free()
	report(started, pinch, junctions, outflow, swept, posts, timber_rails)

func report(started: int, pinch: Dictionary, junctions: Array, outflow: Dictionary, swept: int, posts: int, timber_rails := 0) -> void:
	print("RIVER_JUNCTION_VALIDATION ", JSON.stringify({"ok": failures.is_empty(), "failures": failures,
		"pinch": pinch, "junctions": junctions, "outflow": outflow,
		"swept_rails": swept, "bridge_posts": posts, "timber_rail_boxes": timber_rails,
		"seconds": (Time.get_ticks_msec() - started) / 1000.0}))
	quit(0 if failures.is_empty() else 1)

func _initialize() -> void:
	call_deferred("run")
