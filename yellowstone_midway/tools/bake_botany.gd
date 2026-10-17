extends SceneTree
## Bake fixed-ID JSON clumps into genus/guild proxies; see the authoring guide, Tool commands.
const HEIGHT_FIELD = preload("res://scripts/height_field.gd")
const GOLDEN_ANGLE: float = 2.399963229728653
var terrain: RefCounted
var scene: Node3D
var world: Dictionary = {}
var current_record: Dictionary = {}
var current_origin: Vector3
var current_yaw: float = 0.0
var leaf_material: ShaderMaterial
var wood_material: StandardMaterial3D
var stem_material: ShaderMaterial
var flower_material: ShaderMaterial
var leaf_tool: SurfaceTool
var wood_tool: SurfaceTool
var stem_tool: SurfaceTool
var flower_tool: SurfaceTool
var leaf_triangles: int = 0
var wood_triangles: int = 0
var stem_triangles: int = 0
var flower_triangles: int = 0
var report: Dictionary = {"scope":"Fixed botanical proxy bake; structural genus/guild forms, not a botanical survey.","records":[],"failures":[]}

func _initialize() -> void:
	call_deferred("bake")

func foliage_material() -> ShaderMaterial:
	var mat: ShaderMaterial = ShaderMaterial.new()
	mat.shader = load("res://shaders/foliage.gdshader")
	mat.set_shader_parameter("tint", Vector3.ONE)
	mat.set_shader_parameter("wind_strength", 0.025)
	mat.set_shader_parameter("use_texture", false)
	# Overwritten by world.update_environment at runtime.
	mat.set_shader_parameter("wind_vector", Vector2(1.8, 0.6))
	return mat

func begin_surface() -> SurfaceTool:
	var st: SurfaceTool = SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	return st

func bake() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/botanical_placements.json"))
	if not parsed is Dictionary:
		push_error("Missing botanical placements; no scene written.")
		quit(1)
		return
	var data: Dictionary = parsed
	world = JSON.parse_string(FileAccess.get_file_as_string("res://data/world.json"))
	terrain = HEIGHT_FIELD.new()
	leaf_material = foliage_material()
	stem_material = foliage_material()
	flower_material = foliage_material()
	wood_material = StandardMaterial3D.new()
	wood_material.albedo_color = Color.WHITE
	wood_material.vertex_color_use_as_albedo = true
	wood_material.roughness = 0.94
	wood_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	scene = Node3D.new()
	scene.name = "AuthoredBotanicalDetails"
	scene.set_meta("art_status", data.art_status)
	scene.set_meta("season", data.season)
	scene.set_meta("license", "Original botanical geometry and records: project MIT license; reference pages are citations only.")
	scene.set_meta("placement_source", "res://data/botanical_placements.json")
	root.add_child(scene)
	var ids: Dictionary = {}
	for record: Dictionary in data.get("records", []):
		var id: String = str(record.get("id", ""))
		if id.is_empty() or ids.has(id):
			report.failures.append("Missing or duplicate ID: " + id)
			continue
		ids[id] = true
		current_record = record
		current_yaw = float(record.get("yaw_radians", 0.0))
		var p: Array = record.position_xz
		current_origin = Vector3(float(p[0]), float(terrain.sample(float(p[0]), float(p[1]))), float(p[1]))
		if not validate_placement(record):
			continue
		leaf_tool = begin_surface()
		wood_tool = begin_surface()
		stem_tool = begin_surface()
		flower_tool = begin_surface()
		leaf_triangles = 0
		wood_triangles = 0
		stem_triangles = 0
		flower_triangles = 0
		match str(record.kind):
			"willow": make_willow(record)
			"sedge": make_sedge(record)
			"lupine": make_lupine(record)
			_:
				report.failures.append("Unknown botanical kind: " + str(record.kind))
				continue
		var mesh: ArrayMesh = ArrayMesh.new()
		if wood_triangles > 0:
			wood_tool.set_material(wood_material)
			wood_tool.commit(mesh)
		if stem_triangles > 0:
			stem_tool.set_material(stem_material)
			stem_tool.commit(mesh)
		if leaf_triangles > 0:
			leaf_tool.set_material(leaf_material)
			leaf_tool.commit(mesh)
		if flower_triangles > 0:
			flower_tool.set_material(flower_material)
			flower_tool.commit(mesh)
		var node: MeshInstance3D = MeshInstance3D.new()
		node.name = id
		node.mesh = mesh
		node.position = current_origin
		node.rotation.y = current_yaw
		node.visibility_range_end = 180.0 if str(record.kind) == "willow" else 85.0
		node.visibility_range_end_margin = 10.0
		node.set_meta("art_status", "Original botanical form proxy; species/local occurrence unverified")
		node.set_meta("placement_id", id)
		node.set_meta("catalogue_candidate", record.catalogue_candidate)
		node.set_meta("habitat", record.habitat)
		node.set_meta("evidence", record.evidence)
		scene.add_child(node)
		node.owner = scene
		report.records.append({"id":id,"kind":record.kind,"origin_m":[current_origin.x,current_origin.y,current_origin.z],"height_parameter_m":record.height_m,"triangles":leaf_triangles + wood_triangles + stem_triangles + flower_triangles,"aabb_size_m":[mesh.get_aabb().size.x,mesh.get_aabb().size.y,mesh.get_aabb().size.z]})
	if not report.failures.is_empty():
		push_error("Botanical placement validation failed; scene was not replaced: " + str(report.failures))
		save_report(false)
		scene.free()
		quit(1)
		return
	var packed: PackedScene = PackedScene.new()
	var packed_result: Error = packed.pack(scene)
	var save_result: Error = ERR_CANT_CREATE
	if packed_result == OK:
		DirAccess.make_dir_recursive_absolute("res://scenes")
		save_result = ResourceSaver.save(packed, "res://scenes/botanical_details.tscn")
	var success: bool = packed_result == OK and save_result == OK
	if not success:
		report.failures.append("Could not pack/save botanical scene.")
	save_report(success)
	print("BOTANY_BAKE ", "PASS" if success else "FAIL", " clumps=", report.records.size(), " triangles=", total_triangles(), " scene=res://scenes/botanical_details.tscn")
	scene.free()
	quit(0 if success else 1)

func save_report(success: bool) -> void:
	report["pass"] = success
	report["total_triangles"] = total_triangles()
	report["terrain_sha256"] = FileAccess.get_sha256("res://data/terrain.f32")
	report["world_sha256"] = FileAccess.get_sha256("res://data/world.json")
	DirAccess.make_dir_recursive_absolute("res://tests")
	var file: FileAccess = FileAccess.open("res://tests/botany_bake.json", FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(report, "\t") + "\n")
		file.close()

func total_triangles() -> int:
	var total: int = 0
	for item: Dictionary in report.records:
		total += int(item.triangles)
	return total

func validate_placement(record: Dictionary) -> bool:
	var point: Vector2 = Vector2(current_origin.x, current_origin.z)
	var radius: float = float(record.height_m) * (0.56 if str(record.kind) == "willow" else 0.45)
	for pool: Dictionary in world.get("pools", []):
		if not bool(pool.get("thermal", false)):
			continue
		var ring: PackedVector2Array = PackedVector2Array()
		for q: Array in pool.get("ring", []):
			ring.append(Vector2(float(q[0]), float(q[1])))
		if Geometry2D.is_point_in_polygon(point, ring):
			report.failures.append(str(record.id) + " lies in thermal water.")
			return false
		for i: int in range(ring.size()):
			if point.distance_to(Geometry2D.get_closest_point_to_segment(point, ring[i], ring[(i + 1) % ring.size()])) < radius + 8.0:
				report.failures.append(str(record.id) + " violates the authored pool-edge exclusion.")
				return false
	for route: Dictionary in world.get("routes", []):
		var points: Array = route.get("points", [])
		var clearance: float = float(route.get("width", 0.0)) * 0.5 + radius + 0.5
		for i: int in range(1, points.size()):
			var a: Vector2 = Vector2(float(points[i - 1][0]), float(points[i - 1][2]))
			var b: Vector2 = Vector2(float(points[i][0]), float(points[i][2]))
			if point.distance_to(Geometry2D.get_closest_point_to_segment(point, a, b)) < clearance:
				report.failures.append(str(record.id) + " overlaps an authored road/trail corridor.")
				return false
	return true

func base_at(x: float, z: float) -> Vector3:
	# Bake stem bases on the same triangle terrain as walking.
	var rotated: Vector3 = Vector3(x, 0.0, z).rotated(Vector3.UP, current_yaw)
	var y: float = float(terrain.sample(current_origin.x + rotated.x, current_origin.z + rotated.z)) - current_origin.y
	return Vector3(x, y + 0.004, z)

func triangle(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, color: Color, channel: String) -> void:
	var normal: Vector3 = (b - a).cross(c - a).normalized()
	for p: Vector3 in [a, b, c]:
		st.set_normal(normal)
		st.set_color(color)
		st.set_uv(Vector2(p.x, p.y))
		st.add_vertex(p)
	match channel:
		"leaf": leaf_triangles += 1
		"wood": wood_triangles += 1
		"stem": stem_triangles += 1
		"flower": flower_triangles += 1

func tube(st: SurfaceTool, a: Vector3, b: Vector3, radius_a: float, radius_b: float, color: Color, channel: String, sides: int = 6) -> void:
	var axis: Vector3 = (b - a).normalized()
	var side: Vector3 = axis.cross(Vector3.FORWARD).normalized()
	if side.length_squared() < 0.1:
		side = axis.cross(Vector3.RIGHT).normalized()
	var other: Vector3 = axis.cross(side).normalized()
	for i: int in range(sides):
		var first: float = TAU * float(i) / float(sides)
		var second: float = TAU * float(i + 1) / float(sides)
		var n1: Vector3 = side * cos(first) + other * sin(first)
		var n2: Vector3 = side * cos(second) + other * sin(second)
		triangle(st, a + n1 * radius_a, b + n2 * radius_b, b + n1 * radius_b, color, channel)
		triangle(st, a + n1 * radius_a, a + n2 * radius_a, b + n2 * radius_b, color, channel)

func lanceolate(st: SurfaceTool, base: Vector3, direction: Vector3, width: float, color: Color, channel: String = "leaf") -> void:
	var side: Vector3 = direction.normalized().cross(Vector3.UP).normalized()
	if side.length_squared() < 0.1:
		side = Vector3.RIGHT
	var middle: Vector3 = base + direction * 0.43
	var ridge: Vector3 = middle + Vector3.UP * width * 0.13
	var tip: Vector3 = base + direction
	var left: Vector3 = middle + side * width * 0.5
	var right: Vector3 = middle - side * width * 0.5
	triangle(st, base, left, ridge, color, channel)
	triangle(st, left, tip, ridge, color.lightened(0.025), channel)
	triangle(st, tip, right, ridge, color.darkened(0.035), channel)
	triangle(st, right, base, ridge, color, channel)

func make_willow(record: Dictionary) -> void:
	var height: float = float(record.height_m)
	var variant: int = int(record.get("variant", 0))
	var stem_offsets: Array[Vector2] = [Vector2(-0.12,0.02),Vector2(0.09,-0.10),Vector2(0.05,0.12),Vector2(-0.03,-0.13),Vector2(0.14,0.04),Vector2(-0.11,-0.09),Vector2.ZERO]
	var greens: Array[Color] = [Color(0.28,0.40,0.18),Color(0.32,0.44,0.23),Color(0.30,0.41,0.22)]
	for s: int in range(stem_offsets.size()):
		var origin: Vector3 = base_at(stem_offsets[s].x * height, stem_offsets[s].y * height)
		var theta: float = GOLDEN_ANGLE * float(s) + float(variant) * 0.4
		var outward: Vector3 = Vector3(cos(theta),0,sin(theta))
		var top: Vector3 = origin + outward * height * (0.19 if s < 6 else 0.06) + Vector3.UP * height * (0.75 + float((s + variant) % 4) * 0.08)
		var elbow: Vector3 = origin.lerp(top,0.52) - outward * height * 0.04
		tube(wood_tool,origin - Vector3.UP * 0.035,elbow,0.016 * height,0.010 * height,Color(0.38,0.33,0.23),"wood")
		tube(wood_tool,elbow,top,0.010 * height,0.002 * height,Color(0.46,0.41,0.29),"wood")
		for branch: int in range(4):
			var fraction: float = 0.28 + float(branch) * 0.17
			var attach: Vector3 = origin.lerp(elbow,fraction / 0.52) if fraction <= 0.52 else elbow.lerp(top,(fraction - 0.52) / 0.48)
			var branch_angle: float = theta + (1.4 if branch % 2 == 0 else -1.3)
			var direction: Vector3 = Vector3(cos(branch_angle),0.4,sin(branch_angle))
			var tip: Vector3 = attach + direction * height * (0.24 - float(branch) * 0.022)
			tube(wood_tool,attach,tip,0.0048 * height,0.0009 * height,Color(0.43,0.39,0.25),"wood",5)
			for leaf: int in range(9):
				var t: float = 0.12 + float(leaf) * 0.094
				var root_point: Vector3 = attach.lerp(tip,t)
				var side_angle: float = branch_angle + (1.2 if leaf % 2 == 0 else -1.2)
				var length_m: float = height * (0.078 + float((leaf + s) % 3) * 0.010)
				var leaf_direction: Vector3 = Vector3(cos(side_angle),0.12 - t * 0.18,sin(side_angle)) * length_m
				lanceolate(leaf_tool,root_point,leaf_direction,length_m * 0.25,greens[(s + leaf + variant) % greens.size()])
		for leaf: int in range(8):
			var t: float = 0.55 + float(leaf) * 0.056
			var angle: float = theta + float(leaf) * GOLDEN_ANGLE
			var direction: Vector3 = Vector3(cos(angle),0.30,sin(angle)) * height * 0.075
			lanceolate(leaf_tool,elbow.lerp(top,(t - 0.52) / 0.48),direction,height * 0.019,greens[(leaf + s) % greens.size()])

func make_sedge(record: Dictionary) -> void:
	var height: float = float(record.height_m)
	var variant: int = int(record.get("variant", 0))
	for blade: int in range(38):
		var angle: float = float(blade) * GOLDEN_ANGLE + float(variant) * 0.6
		var radial: Vector3 = Vector3(cos(angle),0,sin(angle))
		var radius: float = height * float(blade % 4) * 0.028
		var origin: Vector3 = base_at(radial.x * radius, radial.z * radius)
		var length_m: float = height * (0.55 + float((blade * 7) % 11) * 0.041)
		var width: float = 0.006 + float(blade % 3) * 0.0015
		var side: Vector3 = radial.cross(Vector3.UP).normalized()
		var color: Color = Color(0.29,0.38,0.16).lightened(float((blade + variant) % 5) * 0.014)
		var previous: Vector3 = origin
		for piece: int in range(1,7):
			var t: float = float(piece) / 6.0
			var point: Vector3 = origin + radial * length_m * 0.55 * t * t + Vector3.UP * length_m * (t - 0.34 * pow(t,3.0))
			var old_width: float = width * (1.0 - float(piece - 1) / 6.0) * 0.5
			var new_width: float = width * (1.0 - t) * 0.5
			triangle(leaf_tool,previous - side * old_width,point - side * new_width,point + side * new_width,color,"leaf")
			triangle(leaf_tool,previous - side * old_width,point + side * new_width,previous + side * old_width,color,"leaf")
			previous = point
	for stem: int in range(5):
		var angle: float = float(stem) * GOLDEN_ANGLE
		var origin: Vector3 = base_at(cos(angle) * 0.04,sin(angle) * 0.04)
		var top: Vector3 = origin + Vector3(cos(angle) * 0.06,height * (0.78 + float(stem % 3) * 0.075),sin(angle) * 0.06)
		tube(stem_tool,origin,top,0.003,0.0012,Color(0.31,0.38,0.18),"stem",3)
		for spike: int in range(3):
			var base: Vector3 = origin.lerp(top,0.72 + float(spike) * 0.105)
			tube(flower_tool,base,base + Vector3(0.007,0.035,0.005),0.005,0.003,Color(0.39,0.29,0.15),"flower",5)

func palmate_leaf(center: Vector3, scale_m: float, phase: float) -> void:
	for leaflet: int in range(7):
		var angle: float = TAU * float(leaflet) / 7.0 + phase
		var length_m: float = scale_m * (0.8 + 0.18 * cos(float(leaflet)))
		var direction: Vector3 = Vector3(cos(angle),0.16 - float(leaflet % 3) * 0.09,sin(angle)) * length_m
		lanceolate(leaf_tool,center,direction,length_m * 0.31,Color(0.22,0.37,0.22).lightened(float(leaflet % 3) * 0.012))

func lupine_flower(center: Vector3, radial: Vector3, size: float, color: Color) -> void:
	var across: Vector3 = radial.cross(Vector3.UP).normalized()
	# Banner, two wing petals, and a pale keel form a pea-like flower.
	lanceolate(flower_tool,center,(Vector3.UP * 0.015 + radial * 0.010) * size,0.017 * size,color.lightened(0.13),"flower")
	lanceolate(flower_tool,center + across * 0.003 * size,(radial * 0.015 + across * 0.006 - Vector3.UP * 0.003) * size,0.008 * size,color,"flower")
	lanceolate(flower_tool,center - across * 0.003 * size,(radial * 0.015 - across * 0.006 - Vector3.UP * 0.003) * size,0.008 * size,color,"flower")
	lanceolate(flower_tool,center,(radial * 0.010 + Vector3.UP * 0.003) * size,0.006 * size,Color(0.76,0.76,0.85),"flower")

func make_lupine(record: Dictionary) -> void:
	var height: float = float(record.height_m)
	var variant: int = int(record.get("variant", 0))
	var offsets: Array[Vector2] = [Vector2(-0.10,0.015),Vector2(0.07,-0.065),Vector2(0.075,0.08)]
	var colors: Array[Color] = [Color(0.38,0.40,0.70),Color(0.42,0.41,0.75),Color(0.34,0.42,0.65)]
	for s: int in range(offsets.size()):
		var origin: Vector3 = base_at(offsets[s].x,offsets[s].y)
		var stem_height: float = height * (1.0 - float((s + variant) % 3) * 0.11)
		var top: Vector3 = origin + Vector3(0.015 * float(s - 1),stem_height,0.018 * float(s % 2))
		tube(stem_tool,origin,top,0.0042,0.0014,Color(0.31,0.41,0.24),"stem",6)
		for leaf: int in range(4):
			var t: float = 0.12 + float(leaf) * 0.13
			var attach: Vector3 = origin.lerp(top,t)
			var angle: float = float(leaf) * GOLDEN_ANGLE + float(s) * 1.5
			var palm: Vector3 = attach + Vector3(cos(angle),0.13,sin(angle)) * (0.065 + height * 0.055)
			tube(stem_tool,attach,palm,0.0014,0.0007,Color(0.28,0.39,0.21),"stem",4)
			palmate_leaf(palm,height * (0.13 - t * 0.04),angle)
		for ring: int in range(10):
			var t: float = 0.64 + float(ring) * 0.033
			var ring_size: float = (1.0 - float(ring) * 0.04) * (0.9 + height * 0.2)
			var center: Vector3 = origin.lerp(top,t)
			for flower: int in range(5):
				var angle: float = TAU * float(flower) / 5.0 + float(ring) * 0.65
				var radial: Vector3 = Vector3(cos(angle),0,sin(angle))
				lupine_flower(center + radial * 0.007,radial,ring_size,colors[(variant + s) % colors.size()])
