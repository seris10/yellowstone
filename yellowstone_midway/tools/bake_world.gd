extends SceneTree
## Offline authored-world scene and asset baking.
const HeightField = preload("res://scripts/height_field.gd")
const LodgepoleLibrary = preload("res://scripts/lodgepole_library.gd")
const CanopySurface = preload("res://scripts/canopy_surface.gd")
const ForestFloor = preload("res://scripts/forest_floor.gd")
var height_field: RefCounted
var spec: Dictionary
var scene_root: Node3D
var terrain_mat: ShaderMaterial
var wood_mat: ShaderMaterial
var asphalt_mat: StandardMaterial3D
var gravel_mat: ShaderMaterial
var stone_mat: StandardMaterial3D
var bark_mat: StandardMaterial3D
var deck_mat: ShaderMaterial
var timber_post_mat: ShaderMaterial
var timber_beam_mat: ShaderMaterial
var timber_stringer_mat: ShaderMaterial
var materials: Dictionary = {}
var mesh_library: Dictionary = {}
# Statistics from the latest river ribbon for the bake receipt.
var ribbon_stats: Dictionary = {}

func _initialize() -> void:
	call_deferred("bake")

func material(color: Color, rough := 0.9) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = rough
	return m

func own(node: Node, parent: Node = null) -> void:
	if parent == null:
		parent = scene_root
	parent.add_child(node)
	node.owner = scene_root

func make_materials() -> void:
	terrain_mat = ShaderMaterial.new()
	terrain_mat.shader = load("res://shaders/terrain.gdshader")
	terrain_mat.set_shader_parameter("ground_albedo", load("res://assets/textures/forest_ground_04_diff_1k.jpg"))
	terrain_mat.set_shader_parameter("ground_normal", load("res://assets/textures/forest_ground_04_nor_gl_1k.jpg"))
	terrain_mat.set_shader_parameter("ground_wetness", .12)
	terrain_mat.set_shader_parameter("rock_albedo", load("res://assets/textures/rock_boulder_dry_diff_1k.jpg"))
	terrain_mat.set_shader_parameter("biome_map", load("res://assets/textures/habitat_mask.png"))
	terrain_mat.set_shader_parameter("macro_albedo", load("res://assets/textures/midway_macro.jpg"))
	terrain_mat.set_shader_parameter("detail_map", load("res://assets/textures/detail.png"))
	terrain_mat.set_shader_parameter("trail_mask", load("res://assets/textures/trail_mask.png"))
	ResourceSaver.save(terrain_mat,"res://assets/materials/terrain.tres")
	wood_mat = ShaderMaterial.new()
	wood_mat.shader = load("res://shaders/boardwalk.gdshader")
	wood_mat.set_shader_parameter("grain",load("res://assets/textures/pine_bark_diff_1k.jpg"))
	ResourceSaver.save(wood_mat,"res://assets/materials/boardwalk.tres")
	asphalt_mat = material(Color(0.105,0.112,0.106))
	gravel_mat = ShaderMaterial.new()
	gravel_mat.shader = load("res://shaders/trail.gdshader")
	gravel_mat.set_shader_parameter("ground_detail",load("res://assets/textures/forest_ground_04_diff_1k.jpg"))
	stone_mat = material(Color(0.65,0.63,0.55))
	stone_mat.albedo_texture = load("res://assets/textures/rock_boulder_dry_diff_1k.jpg")
	bark_mat = material(Color(0.64,0.60,0.48))
	bark_mat.albedo_texture = load("res://assets/textures/pine_bark_diff_1k.jpg")
	bark_mat.normal_enabled = true
	bark_mat.normal_texture = load("res://assets/textures/pine_bark_nor_gl_1k.jpg")
	deck_mat = wood_mat.duplicate()
	deck_mat.set_shader_parameter("world_planks", 1.0)
	ResourceSaver.save(deck_mat,"res://assets/materials/overlook_deck.tres")
	timber_post_mat = timber_material(Vector3.UP, "timber_post")
	timber_beam_mat = timber_material(Vector3.BACK, "timber_beam")
	timber_stringer_mat = timber_material(Vector3.RIGHT, "timber_stringer")

func timber_material(axis: Vector3, file_name: String) -> ShaderMaterial:
	# Milled timber with grain along the member's long object-space axis.
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/timber.gdshader")
	m.set_shader_parameter("grain_axis", axis)
	ResourceSaver.save(m,"res://assets/materials/%s.tres" % file_name)
	return m

func append_instance(buffer: PackedFloat32Array, xf: Transform3D, extra: Color) -> void:
	# Serialize three row-major transform rows, followed by color or custom data.
	if buffer.size() > 1_000_000:
		push_error("Instance buffer exceeded safety limit; abort.")
		return
	buffer.append_array(PackedFloat32Array([
		xf.basis.x.x,xf.basis.y.x,xf.basis.z.x,xf.origin.x,
		xf.basis.x.y,xf.basis.y.y,xf.basis.z.y,xf.origin.y,
		xf.basis.x.z,xf.basis.y.z,xf.basis.z.z,xf.origin.z,
		extra.r,extra.g,extra.b,extra.a]))

func make_mesh(vertices: PackedVector3Array, normals: PackedVector3Array, uvs: PackedVector2Array, indices: PackedInt32Array, mat: Material, colors: PackedColorArray = PackedColorArray()) -> ArrayMesh:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	if not colors.is_empty():
		arrays[Mesh.ARRAY_COLOR] = colors
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0,mat)
	return mesh

func bake() -> void:
	var start := Time.get_ticks_msec()
	if "--vegetation-only" in OS.get_cmdline_user_args():
		bake_vegetation_only(start)
		return
	DirAccess.make_dir_recursive_absolute("res://scenes/baked")
	DirAccess.make_dir_recursive_absolute("res://assets/meshes/terrain")
	spec = JSON.parse_string(FileAccess.get_file_as_string("res://data/world.json"))
	height_field = HeightField.new()
	scene_root = Node3D.new()
	scene_root.name = "AuthoredMidway"
	get_root().add_child(scene_root)
	make_materials()
	make_terrain()
	print("Terrain baked")
	make_routes()
	print("Routes baked")
	make_water()
	print("Water baked")
	if not make_vegetation():
		quit(1)
		return
	print("Vegetation baked")
	make_overlook()
	var packed := PackedScene.new()
	packed.pack(scene_root)
	# Save the binary scene for the runtime and the text scene for tooling.
	var error := ResourceSaver.save(packed,"res://scenes/authored_world.scn")
	if error == OK:
		error = ResourceSaver.save(packed,"res://scenes/authored_world.tscn")
	print("WORLD_BAKE ",error," ",(Time.get_ticks_msec()-start)/1000.0," seconds")
	quit(error)

func make_terrain() -> void:
	var group := Node3D.new()
	group.name = "TerrainTiles"
	own(group)
	for tz in 16:
		for tx in 16:
			var vertices := PackedVector3Array()
			var normals := PackedVector3Array()
			var uvs := PackedVector2Array()
			var indices := PackedInt32Array()
			var elevation := PackedFloat32Array()
			for z in 65:
				for x in 65:
					var ix := tx*64+x
					var iz := tz*64+z
					var y: float = height_field.values[iz*1025+ix]
					vertices.append(Vector3(x*4.0,y,z*4.0))
					normals.append(height_field.normal_at(ix,iz))
					uvs.append(Vector2(ix/1024.0,iz/1024.0))
					elevation.append(y/4.0)
			for z in 64:
				for x in 64:
					var a := z*65+x
					indices.append_array(PackedInt32Array([a,a+1,a+65,a+1,a+66,a+65]))
			var mesh := make_mesh(vertices,normals,uvs,indices,terrain_mat)
			var mesh_path := "res://assets/meshes/terrain/tile_%02d_%02d.res" % [tx,tz]
			ResourceSaver.save(mesh,mesh_path,ResourceSaver.FLAG_COMPRESS)
			var tile := MeshInstance3D.new()
			tile.name = "Terrain_%02d_%02d" % [tx,tz]
			tile.mesh = mesh
			tile.position = Vector3(tx*256.0-2048.0,0,tz*256.0-2048.0)
			own(tile,group)
			var body := StaticBody3D.new()
			body.name = "Ground"
			own(body,tile)
			var col := CollisionShape3D.new()
			var hm := HeightMapShape3D.new()
			hm.map_width = 65
			hm.map_depth = 65
			hm.map_data = elevation
			col.name = "TerrainShape"
			col.shape = hm
			col.position = Vector3(128,0,128)
			col.scale = Vector3.ONE*4.0
			own(col,body)

func points_of(values: Array) -> PackedVector3Array:
	var out := PackedVector3Array()
	for p: Array in values:
		out.append(Vector3(p[0],p[1],p[2]))
	return out

func ribbon(points: PackedVector3Array, width: float, mat: Material, closed := false, tint := false) -> ArrayMesh:
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var colors := PackedColorArray()
	var indices := PackedInt32Array()
	var arc := 0.0
	for i in points.size():
		var before := maxi(i-1,0)
		var after := mini(i+1,points.size()-1)
		var tangent := (points[after]-points[before]).normalized()
		var side := Vector3(-tangent.z,0,tangent.x).normalized()
		if i>0:
			arc += points[i].distance_to(points[i-1])
		var fraction := float(i) / float(maxi(1, points.size() - 1))
		for s in 2:
			vertices.append(points[i]+side*(float(s)-0.5)*width)
			normals.append(side.cross(tangent).normalized())
			uvs.append(Vector2(float(s),arc))
			# Vertex color red stores the source-to-mouth fraction.
			colors.append(Color(1.0 - fraction if tint else 1.0, 1, 1))
		if i>0:
			var a := (i-1)*2
			indices.append_array(PackedInt32Array([a,a+2,a+1,a+1,a+2,a+3]))
	return make_mesh(vertices,normals,uvs,indices,mat,colors)

# --- River surface ---
const WATER_MARGIN_FRACTION := 0.23
const WATER_MARGIN_MIN_M := 0.8
const WATER_MARGIN_MAX_M := 5.0
const WATER_END_FADE_M := 8.0
const WATER_JUNCTION_TOLERANCE_M := 1.5
const WATER_SMOOTH_PASSES := 4
const WATER_FOLD_SAFETY := 0.85
const WATER_MIN_REACH_FRACTION := 0.30
const WATER_RESAMPLE_STEP_M := 2.0
const WATER_CAP_SEGMENTS := 20

func water_margin_m(width: float) -> float:
	return clampf(width * WATER_MARGIN_FRACTION, WATER_MARGIN_MIN_M, WATER_MARGIN_MAX_M)

func river_end_is_free(rivers: Array, self_index: int, point: Vector3) -> bool:
	# Keep river junction endpoints solid.
	var limit := WATER_JUNCTION_TOLERANCE_M * WATER_JUNCTION_TOLERANCE_M
	for other_index: int in rivers.size():
		if other_index == self_index:
			continue
		for other: Array in rivers[other_index].points:
			var dx: float = float(other[0]) - point.x
			var dz: float = float(other[2]) - point.z
			if dx * dx + dz * dz <= limit:
				return false
	return true

func resample_polyline(points: PackedVector3Array, step := WATER_RESAMPLE_STEP_M) -> PackedVector3Array:
	# Use uniform station spacing and a 0.25 m endpoint tolerance.
	var out := PackedVector3Array([points[0]])
	var carry := 0.0
	for i: int in range(1, points.size()):
		var a := points[i - 1]
		var b := points[i]
		var seg := a.distance_to(b)
		if seg < 0.0001:
			continue
		while carry + seg >= step:
			var t := (step - carry) / seg
			var p := a.lerp(b, t)
			out.append(p)
			a = p
			seg = a.distance_to(b)
			carry = 0.0
		carry += seg
	if out[out.size() - 1].distance_to(points[points.size() - 1]) > 0.25:
		out.append(points[points.size() - 1])
	return out

func smooth_plan_view(points: PackedVector3Array) -> PackedVector3Array:
	# Smooth plan-view kinks while retaining heights and endpoints.
	var result := points.duplicate()
	for pass_index: int in WATER_SMOOTH_PASSES:
		var source := result.duplicate()
		for i: int in range(1, points.size() - 1):
			result[i] = Vector3((source[i - 1].x + 2.0 * source[i].x + source[i + 1].x) * 0.25, source[i].y,
				(source[i - 1].z + 2.0 * source[i].z + source[i + 1].z) * 0.25)
	return result

func snap_water_junctions(rivers: Array, tolerance := WATER_JUNCTION_TOLERANCE_M) -> void:
	# Snap clustered endpoints to their shared centroid.
	var ends: Array = []
	for ri: int in rivers.size():
		ends.append([ri, 0])
		ends.append([ri, rivers[ri].points.size() - 1])
	var used := {}
	for e: Array in ends:
		if used.has(e):
			continue
		var group := [e]
		var p: Array = rivers[e[0]].points[e[1]]
		for o: Array in ends:
			if o == e or used.has(o):
				continue
			var q: Array = rivers[o[0]].points[o[1]]
			if Vector2(p[0] - q[0], p[2] - q[2]).length() <= tolerance:
				group.append(o)
		if group.size() < 2:
			continue
		var centroid := Vector3.ZERO
		for g: Array in group:
			var gp: Array = rivers[g[0]].points[g[1]]
			centroid += Vector3(gp[0], gp[1], gp[2])
		centroid /= group.size()
		for g: Array in group:
			rivers[g[0]].points[g[1]] = [centroid.x, centroid.y, centroid.z]
			used[g] = true

func river_ribbon(points_in: PackedVector3Array, width: float, mat: Material, free_start: bool, free_end: bool, tint := false) -> ArrayMesh:
	var points := smooth_plan_view(resample_polyline(points_in))
	var visual_half := width * 0.5 + water_margin_m(width)
	var count := points.size()
	var directions := PackedVector3Array()
	var curvature := PackedFloat32Array()
	var curvature_minus := PackedFloat32Array()
	var arcs := PackedFloat32Array()
	directions.resize(count)
	curvature.resize(count)
	curvature_minus.resize(count)
	arcs.resize(count)
	var arc := 0.0
	for i: int in count:
		var before := maxi(i - 1, 0)
		var after := mini(i + 1, count - 1)
		var flat := Vector3(points[after].x - points[before].x, 0.0, points[after].z - points[before].z).normalized()
		directions[i] = flat
		if i > 0:
			arc += points[i].distance_to(points[i - 1])
		arcs[i] = arc
	# Signed plan-view curvature in 1/m; positive bends toward the +side offset.
	var raw := PackedFloat32Array()
	raw.resize(count)
	for i: int in range(1, count - 1):
		var a := Vector2(points[i].x - points[i - 1].x, points[i].z - points[i - 1].z)
		var b := Vector2(points[i + 1].x - points[i].x, points[i + 1].z - points[i].z)
		var mean_length := 0.5 * (a.length() + b.length())
		if mean_length > 0.0001 and a.length() > 0.0001 and b.length() > 0.0001:
			raw[i] = asin(clampf(a.normalized().cross(b.normalized()), -1.0, 1.0)) / mean_length
	for i: int in count:
		var strongest_plus := 0.0
		var strongest_minus := 0.0
		for k: int in range(-3, 4):
			var j := clampi(i + k, 0, count - 1)
			strongest_plus = maxf(strongest_plus, raw[j])
			strongest_minus = maxf(strongest_minus, -raw[j])
		curvature[i] = strongest_plus
		curvature_minus[i] = strongest_minus
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var colors := PackedColorArray()
	var tangents := PackedFloat32Array()
	var indices := PackedInt32Array()
	var centers := PackedVector3Array()
	centers.resize(count)
	var min_half := visual_half
	var total_arc := arcs[count - 1]
	for i: int in count:
		var direction := directions[i]
		var side := Vector3(-direction.z, 0.0, direction.x)
		var before := maxi(i - 1, 0)
		var after := mini(i + 1, count - 1)
		var sloped := (points[after] - points[before]).normalized()
		var normal := side.cross(sloped).normalized()
		var reach_plus := visual_half
		var reach_minus := visual_half
		if curvature[i] > 0.0001:
			reach_plus = clampf(minf(reach_plus, WATER_FOLD_SAFETY / curvature[i]), visual_half * WATER_MIN_REACH_FRACTION, visual_half)
		if curvature_minus[i] > 0.0001:
			reach_minus = clampf(minf(reach_minus, WATER_FOLD_SAFETY / curvature_minus[i]), visual_half * WATER_MIN_REACH_FRACTION, visual_half)
		# The outer side absorbs lost width around the mapped centerline.
		var center := points[i]
		var deficit_plus := visual_half - reach_plus
		var deficit_minus := visual_half - reach_minus
		if deficit_plus > 0.0:
			reach_minus += deficit_plus
		if deficit_minus > 0.0:
			reach_plus += deficit_minus
		centers[i] = center
		min_half = minf(min_half, minf(reach_plus, reach_minus))
		var fraction := arcs[i] / maxf(total_arc, 0.001)
		var fade := 1.0
		if free_start:
			fade = minf(fade, arcs[i] / WATER_END_FADE_M)
		if free_end:
			fade = minf(fade, (total_arc - arcs[i]) / WATER_END_FADE_M)
		for s: int in 2:
			vertices.append(center + side * (reach_plus if s == 1 else -reach_minus))
			normals.append(normal)
			uvs.append(Vector2(float(s), arcs[i]))
			# Red carries the outflow fraction; blue carries the end fade.
			colors.append(Color(1.0 - fraction if tint else 1.0, 1.0, clampf(fade, 0.0, 1.0)))
			tangents.append_array(PackedFloat32Array([direction.x, 0.0, direction.z, 1.0]))
		if i > 0:
			var a := (i - 1) * 2
			indices.append_array(PackedInt32Array([a, a + 2, a + 1, a + 1, a + 2, a + 3]))
	# Close junction wedges with round caps and feather their rims.
	var cap_ends: Array[int] = []
	if not free_start:
		cap_ends.append(0)
	if not free_end:
		cap_ends.append(count - 1)
	for end_index: int in cap_ends:
		var hub := vertices.size()
		var cap_tangent := PackedFloat32Array([directions[end_index].x, 0.0, directions[end_index].z, 1.0])
		var cap_red := (1.0 - arcs[end_index] / maxf(total_arc, 0.001)) if tint else 1.0
		vertices.append(centers[end_index])
		normals.append(Vector3.UP)
		uvs.append(Vector2(0.5, arcs[end_index]))
		colors.append(Color(cap_red, 1.0, 1.0))
		tangents.append_array(cap_tangent)
		for step: int in WATER_CAP_SEGMENTS:
			var angle := TAU * float(step) / float(WATER_CAP_SEGMENTS)
			vertices.append(centers[end_index] + Vector3(cos(angle), 0.0, sin(angle)) * visual_half)
			normals.append(Vector3.UP)
			uvs.append(Vector2(1.0, arcs[end_index]))
			colors.append(Color(cap_red, 1.0, 0.0))
			tangents.append_array(cap_tangent)
		for step: int in WATER_CAP_SEGMENTS:
			indices.append_array(PackedInt32Array([hub, hub + 1 + step, hub + 1 + (step + 1) % WATER_CAP_SEGMENTS]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TANGENT] = tangents
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, mat)
	ribbon_stats = {"stations": count, "min_half_width_m": min_half, "visual_half_m": visual_half}
	return mesh

func river_material(width: float, flow_mps: float) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/river_water.gdshader")
	m.set_shader_parameter("ripple", load("res://assets/textures/water_normal.png"))
	m.set_shader_parameter("flow_speed", flow_mps)
	m.set_shader_parameter("width_m", (width * 0.5 + water_margin_m(width)) * 2.0)
	m.set_shader_parameter("core_width_m", width)
	# Firehole DEM-transect mean depth: 0.512-0.53 m (configs/cross_sections.json).
	m.set_shader_parameter("channel_depth_m", 0.53 if width > 8.0 else 0.45)
	return m

func add_geometry(mesh: Mesh, name: String, parent: Node, collision := false) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	node.mesh = mesh
	node.name = name
	own(node,parent)
	if collision:
		var body := StaticBody3D.new()
		own(body,node)
		var shape := CollisionShape3D.new()
		shape.shape = mesh.create_trimesh_shape()
		own(shape,body)
	return node

func make_routes() -> void:
	var group := Node3D.new()
	group.name = "RoadsAndTrails"
	own(group)
	var paint := material(Color(0.80,0.60,0.19))
	for r: Dictionary in spec.routes:
		var points := points_of(r.points)
		var mat: Material = asphalt_mat if r.kind=="road" or r.surface=="Asphalt" else gravel_mat
		if r.surface=="Wood":
			mat = wood_mat
		elif r.kind=="trail" and mat == gravel_mat:
			# Set per-ribbon trail width for meter-based feathering.
			mat = gravel_mat.duplicate()
			(mat as ShaderMaterial).set_shader_parameter("width_m", float(r.width))
		if r.kind=="trail" and r.surface=="Native":
			# Bridge spans retain deck height; dirt tread follows terrain.
			var bridged := {}
			for span: Array in r.get("bridge_spans", []):
				for k in range(int(span[0]), int(span[1]) + 1):
					bridged[k] = true
			for i in points.size():
				if not bridged.has(i):
					points[i].y = height_field.sample(points[i].x, points[i].z) + 0.035
		var route: MeshInstance3D = null
		if r.kind == "trail" and r.surface != "Wood":
			# Lift deck spans above gaps over 0.35 m; use 0.55 m step-up skirts.
			var keep := {}
			for span: Array in r.get("bridge_spans", []):
				for k in range(maxi(0, int(span[0]) - 2), mini(points.size(), int(span[1]) + 3)):
					keep[k] = true
			for i in points.size():
				if points[i].y - height_field.sample(points[i].x, points[i].z) > 0.35:
					keep[i] = true
			var run := PackedVector3Array()
			var runs: Array = []
			for i in points.size():
				if keep.has(i):
					run.append(points[i])
				elif run.size() > 0:
					runs.append(run)
					run = PackedVector3Array()
			if run.size() > 0:
				runs.append(run)
			for deck_points in runs:
				if deck_points.size() < 2:
					continue
				var deck := add_geometry(ribbon(deck_points, r.width, mat), r.id, group, true)
				if route == null:
					route = deck
				make_skirts(deck_points, float(r.width), group, gravel_mat)
				make_endcaps(deck_points, float(r.width), group, gravel_mat)
		else:
			route = add_geometry(ribbon(points, r.width, mat), r.id, group, true)
		if route != null:
			route.set_meta("source_name",r.name)
			route.set_meta("source_object_id",r.source_id)
		if r.name=="Grand Loop Road":
			for offset in [-0.14,0.14]:
				var center := PackedVector3Array()
				for i in points.size():
					var d := (points[mini(i+1,points.size()-1)]-points[maxi(i-1,0)]).normalized()
					center.append(points[i]+Vector3(-d.z,0,d.x)*offset+Vector3.UP*0.015)
				add_geometry(ribbon(center,.08,paint),"CenterLine",group)
		if r.surface=="Wood":
			# Mesh supports and endcaps at fixed path stations.
			for i in range(0,points.size(),3):
				var top := points[i]
				var ground: float = height_field.sample(top.x,top.z)
				var mesh := BoxMesh.new()
				mesh.size = Vector3(1.8,maxf(top.y-ground,0.25),0.13)
				mesh.material = timber_stringer_mat
				var support := add_geometry(mesh,"Stringer",group)
				support.position = Vector3(top.x,top.y-mesh.size.y*.5-.05,top.z)
			make_skirts(points,float(r.width),group,wood_mat)

		if r.get("has_bridge",false):
			for span: Array in r.get("bridge_spans",[]):
				make_bridge_rails(points.slice(int(span[0]),int(span[1])+1),float(r.width),group)

func make_endcaps(points: PackedVector3Array, width: float, group: Node, mat: Material) -> void:
	# Close both ribbon ends with quads dropping to ground.
	for end in [0, points.size() - 1]:
		var p: Vector3 = points[end]
		var q: Vector3 = points[1] if end == 0 else points[end - 1]
		var tangent: Vector3 = (p - q).normalized()
		if tangent.length_squared() < 0.000001:
			continue
		var side := Vector3(-tangent.z, 0, tangent.x).normalized() * width * 0.5
		var gy: float = height_field.sample(p.x, p.z) - 0.12
		var verts := PackedVector3Array([p - side, p + side,
			Vector3(p.x + side.x, gy, p.z + side.z),
			Vector3(p.x - side.x, gy, p.z - side.z)])
		var normals := PackedVector3Array()
		var uvs := PackedVector2Array()
		for k in 4:
			normals.append(-tangent if end == points.size() - 1 else tangent)
			uvs.append(Vector2(k % 2, k / 2))
		add_geometry(make_mesh(verts, normals, uvs,
			PackedInt32Array([0, 1, 2, 0, 2, 3]), mat),
		"TrailEndcap", group, false)

func make_skirts(points: PackedVector3Array, width: float, group: Node, mat: Material) -> void:
	# Drop both deck edges to ground so the boardwalk has sides.
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	var count := 0
	for i in range(0, points.size() - 1, 2):
		var a := points[i]
		var b := points[mini(i + 1, points.size() - 1)]
		var tangent: Vector3 = (b - a).normalized()
		if tangent.length_squared() < 0.000001:
			continue
		var side := Vector3(-tangent.z, 0, tangent.x).normalized()
		for sign_value: float in [-1.0, 1.0]:
			var offset: Vector3 = side * (width * 0.5 * sign_value)
			var top_a := a + offset
			var top_b := b + offset
			var low_a := Vector3(top_a.x, height_field.sample(top_a.x, top_a.z) - 0.12, top_a.z)
			var low_b := Vector3(top_b.x, height_field.sample(top_b.x, top_b.z) - 0.12, top_b.z)
			var base := vertices.size()
			vertices.append_array(PackedVector3Array([top_a, top_b, low_b, low_a]))
			var n := (top_b - top_a).cross(low_a - top_a).normalized()
			for k in 4:
				normals.append(n)
				uvs.append(Vector2(k % 2, k / 2))
			indices.append_array(PackedInt32Array([base, base + 2, base + 1, base, base + 3, base + 2]))
			count += 1
	if count > 0:
		add_geometry(make_mesh(vertices, normals, uvs, indices, mat), "TrailSkirt", group, false)

func beam_between(a: Vector3, b: Vector3, thickness: float, parent: Node, collision := true) -> void:
	var beam:=BoxMesh.new()
	beam.size=Vector3(thickness,thickness,a.distance_to(b))
	beam.material=timber_beam_mat
	var node:=add_geometry(beam,"TimberRail",parent,collision)
	node.position=(a+b)*.5
	node.look_at_from_position(node.position,b,Vector3.UP)

func make_bridge_rails(points: PackedVector3Array, width: float, parent: Node) -> void:
	if points.size()<2:return
	# Miter swept rail profiles in a shared joint plane.
	for sign_value in [-1.0,1.0]:
		var edge:=PackedVector3Array()
		for i in points.size():
			var tangent: Vector3=(points[mini(i+1,points.size()-1)]-points[maxi(0,i-1)]).normalized()
			var side:=Vector3(-tangent.z,0,tangent.x).normalized()
			edge.append(points[i]+side*(width*.5+.065)*float(sign_value))
		swept_beam(edge,1.05,.12,.12,parent)
		swept_beam(edge,.53,.08,.08,parent)
		swept_beam(edge,-.05,.20,.05,parent,false)
		# Space posts uniformly along each deck edge.
		var spacing:=1.8
		var next:=0.0
		var arc:=0.0
		for i in range(1,edge.size()):
			var seg:=edge[i].distance_to(edge[i-1])
			while next<=arc+seg:
				var t:=(next-arc)/maxf(seg,.001)
				var p:=edge[i-1].lerp(edge[i],t)
				var post:=BoxMesh.new()
				post.size=Vector3(.12,1.12,.12)
				post.material=timber_post_mat
				var node:=add_geometry(post,"BridgePost",parent,true)
				node.position=p+Vector3.UP*.55
				next+=spacing
			arc+=seg

func swept_beam(centerline: PackedVector3Array, y_off: float, height: float, depth: float, parent: Node, collision := true) -> void:
	# Scale each joint profile by 1/cos(half-angle) in the bend plane.
	var n:=centerline.size()
	if n<2:return
	var vertices:=PackedVector3Array()
	var normals:=PackedVector3Array()
	var indices:=PackedInt32Array()
	for i in n:
		var dir_prev: Vector3=(centerline[i]-centerline[maxi(i-1,0)]).normalized() if i>0 else (centerline[1]-centerline[0]).normalized()
		var dir_next: Vector3=(centerline[mini(i+1,n-1)]-centerline[i]).normalized() if i<n-1 else dir_prev
		var tangent: Vector3=dir_prev+dir_next
		tangent=tangent.normalized() if tangent.length_squared()>.0001 else dir_next
		var side:=Vector3(-tangent.z,0.0,tangent.x)
		side=side.normalized() if side.length_squared()>.0001 else Vector3.RIGHT
		var up: Vector3=side.cross(tangent).normalized()
		var miter:=1.0/maxf(tangent.dot(dir_next),.5)
		var c: Vector3=centerline[i]+Vector3.UP*y_off
		var hh:=height*.5
		var hd:=depth*.5*miter
		var corners: Array[Vector3]=[
			c+up*hh+side*hd,c+up*hh-side*hd,
			c-up*hh-side*hd,c-up*hh+side*hd]
		var corner_normals: Array[Vector3]=[up,up,-up,-up]
		for k in 4:
			vertices.append(corners[k])
			normals.append(corner_normals[k])
		if i>0:
			var a:=(i-1)*4
			var b:=i*4
			for face in 4:
				var f2:=(face+1)%4
				indices.append_array(PackedInt32Array([a+face,b+face,b+f2,a+face,b+f2,a+f2]))
	var arrays:=[]
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX]=vertices
	arrays[Mesh.ARRAY_NORMAL]=normals
	arrays[Mesh.ARRAY_INDEX]=indices
	var mesh:=ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
	mesh.surface_set_material(0,timber_beam_mat)
	add_geometry(mesh,"BridgeRailSwept",parent,collision)

func make_rails(points: PackedVector3Array, width: float, group: Node) -> void:
	for i in range(0,points.size()-1,2):
		var p := points[i]
		var d := (points[i+1]-p).normalized()
		var side := Vector3(-d.z,0,d.x)
		for sign_value in [-1.0,1.0]:
			var post := BoxMesh.new()
			post.size = Vector3(.13,1.05,.13)
			post.material = bark_mat
			var post_node := add_geometry(post,"RailPost",group)
			post_node.position = p+side*width*.5*sign_value+Vector3.UP*.5
			var beam_points := PackedVector3Array([p+side*width*.5*sign_value+Vector3.UP,points[mini(i+2,points.size()-1)]+side*width*.5*sign_value+Vector3.UP])
			var beam := add_geometry(ribbon(beam_points,.12,bark_mat),"Rail",group)

func water_material(thermal := false) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/water.gdshader")
	m.set_shader_parameter("ripple",load("res://assets/textures/water_normal.png"))
	if thermal:
		m.set_shader_parameter("pool",1.0)
		m.set_shader_parameter("shallow_color",Vector3(.10,.64,.62))
		m.set_shader_parameter("deep_color",Vector3(.012,.29,.48))
		m.set_shader_parameter("flow_speed",.03)
		m.set_shader_parameter("roughness",.20)
	return m

func make_water() -> void:
	var group := Node3D.new()
	group.name = "ConnectedWater"
	own(group)
	snap_water_junctions(spec.rivers)
	var pinch_report: Array = []
	for river_index: int in spec.rivers.size():
		var r: Dictionary = spec.rivers[river_index]
		if not bool(r.get("thermal",false)) and str(r.get("id","")) != "authored_excelsior_outflow_01":
			var river_points := points_of(r.points)
			var river_mat := river_material(float(r.width), float(r.flow_mps))
			var river_mesh := river_ribbon(river_points, float(r.width), river_mat,
				river_end_is_free(spec.rivers, river_index, river_points[0]),
				river_end_is_free(spec.rivers, river_index, river_points[river_points.size() - 1]))
			var surface := add_geometry(river_mesh, r.id, group)
			surface.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			surface.add_to_group("river_surfaces",true)
			surface.set_meta("river_name",r.name)
			surface.set_meta("sample_z",r.points[r.points.size()/2][2])
			surface.set_meta("station_count", int(ribbon_stats.stations))
			surface.set_meta("min_half_width_m", ribbon_stats.min_half_width_m)
			pinch_report.append({"id": r.id, "min_half_width_m": ribbon_stats.min_half_width_m, "visual_half_m": ribbon_stats.visual_half_m})
			continue
		var mat := water_material(bool(r.get("thermal",false)))
		mat.set_shader_parameter("flow_speed",r.flow_mps)
		mat.set_shader_parameter("width_m",float(r.width))
		# Use thermal tint on flowing outfall ribbons.
		mat.set_shader_parameter("pool",0.0)
		if bool(r.get("thermal",false)):
			mat.set_shader_parameter("shallow_color",Vector3(.34,.43,.32))
			mat.set_shader_parameter("deep_color",Vector3(.15,.32,.25))
			mat.set_shader_parameter("roughness",.32)
			mat.set_shader_parameter("cascade",1.0)
		var is_outflow := str(r.get("id",""))=="authored_excelsior_outflow_01"
		if is_outflow:
			# Advect outflow ripples; red carries the cooling and foam fraction.
			mat.set_shader_parameter("flow_speed",2.2)
		var water: MeshInstance3D
		if is_outflow:
			# Build the outflow with river smoothing and junction caps.
			var outflow_points := points_of(r.points)
			var outflow_mesh := river_ribbon(outflow_points, float(r.width), mat, true,
				river_end_is_free(spec.rivers, river_index, outflow_points[outflow_points.size() - 1]), true)
			water = add_geometry(outflow_mesh, r.id, group)
			water.set_meta("station_count", int(ribbon_stats.stations))
			water.set_meta("min_half_width_m", ribbon_stats.min_half_width_m)
			pinch_report.append({"id": r.id, "min_half_width_m": ribbon_stats.min_half_width_m, "visual_half_m": ribbon_stats.visual_half_m})
		else:
			water = add_geometry(ribbon(points_of(r.points),r.width,mat,false,false),r.id,group)
		water.add_to_group("river_surfaces",true)
		water.set_meta("river_name",r.name)
		water.set_meta("sample_z",r.points[r.points.size()/2][2])
	# Measure each snapped endpoint against neighboring reach vertices.
	var junction_report: Array = []
	for ri: int in spec.rivers.size():
		var pts: Array = spec.rivers[ri].points
		for end_index: int in [0, pts.size() - 1]:
			var p: Array = pts[end_index]
			var best := INF
			for oi: int in spec.rivers.size():
				if oi == ri:
					continue
				for q: Array in spec.rivers[oi].points:
					best = minf(best, Vector2(p[0] - q[0], p[2] - q[2]).length())
			if best <= WATER_JUNCTION_TOLERANCE_M:
				junction_report.append({"id": spec.rivers[ri].id, "end": end_index, "gap_m": best})
	print("RIVER_PINCH ", JSON.stringify(pinch_report))
	print("RIVER_JUNCTIONS ", JSON.stringify(junction_report))
	for p: Dictionary in spec.pools:
		var vertices := PackedVector3Array()
		var normals := PackedVector3Array()
		var uvs := PackedVector2Array()
		var colors := PackedColorArray()
		var indices := PackedInt32Array()
		var center := Vector3(p.center[0],p.center[1],p.center[2])
		vertices.append(center)
		normals.append(Vector3.UP)
		uvs.append(Vector2(.5,.5))
		colors.append(Color(1,1,1))
		var n: int = p.ring.size()
		for k in 4:
			var fraction := float(k+1)/4.0
			for pair: Array in p.ring:
				var v := center.lerp(Vector3(pair[0],center.y,pair[1]),fraction)
				vertices.append(v)
				normals.append(Vector3.UP)
				uvs.append(Vector2(v.x-center.x,v.z-center.z)/100.0+Vector2(.5,.5))
				colors.append(Color(1.0-fraction,1,1))
		for i in n:
			indices.append_array(PackedInt32Array([0,1+(i+1)%n,1+i]))
		for k in 3:
			for i in n:
				var a := 1+k*n+i
				var b := 1+k*n+(i+1)%n
				var c := a+n
				var d := b+n
				indices.append_array(PackedInt32Array([a,b,c,b,d,c]))
		if not p.thermal:
		# Ear-clip the saved polygon for a concave shoreline.
			var outline:=PackedVector2Array()
			vertices=PackedVector3Array()
			normals=PackedVector3Array()
			uvs=PackedVector2Array()
			colors=PackedColorArray()
			for pair: Array in p.ring:
				outline.append(Vector2(pair[0],pair[1]))
				vertices.append(Vector3(pair[0],center.y,pair[1]))
				normals.append(Vector3.UP)
				uvs.append(Vector2(pair[0],pair[1])/100.0)
				colors.append(Color(.7,1,1))
			indices=Geometry2D.triangulate_polygon(outline)
		var mat := water_material(p.thermal)
		mat.set_shader_parameter("pool",1.0)
		mat.set_shader_parameter("temperature_c",float(p.temperature_c))
		# Bind Python-authored pigment ramps.
		if p.thermal and FileAccess.file_exists("res://data/pool_shells.json"):
			var ramp_path := "res://assets/textures/pool_ramps/%s.png" % str(p.id)
			if ResourceLoader.exists(ramp_path):
				mat.set_shader_parameter("band_ramp",load(ramp_path))
				mat.set_shader_parameter("ramp_mix",1.0)
		var mesh := make_mesh(vertices,normals,uvs,indices,mat,colors)
		var pool := add_geometry(mesh,p.id,group)
		pool.set_meta("feature_name",p.name)
		if p.thermal:
			pool.add_to_group("thermal_surfaces",true)
			make_steam(p,group)

func make_steam(p: Dictionary, group: Node) -> void:
	var node := MultiMeshInstance3D.new()
	node.name = "Steam_"+p.id
	node.set_meta("surface_c",float(p.temperature_c))
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_custom_data = true
	var quad := QuadMesh.new()
	quad.size = Vector2(15,8)
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/steam.gdshader")
	mat.set_shader_parameter("cloud_texture",load("res://assets/textures/detail.png"))
	quad.material = mat
	mm.mesh = quad
	mm.instance_count = 45 if p.source_id==1034 or p.source_id==1030 else 10
	var center := Vector3(p.center[0],p.center[1],p.center[2])
	var instance_buffer:=PackedFloat32Array()
	var cloud_bounds:=AABB(center-Vector3.ONE*5,Vector3.ONE*10)
	for i in mm.instance_count:
		var rim: Array = p.ring[(i*17)%p.ring.size()]
		var radial := Vector3(rim[0],center.y,rim[1])-center
		var factor := 0.18+0.64*fposmod(float(i)*.618033,1.0)
		var basis := Basis(Vector3.UP,float(i)*2.399)
		var xf:=Transform3D(basis,center+radial*factor+Vector3.UP*2.5)
		append_instance(instance_buffer,xf,Color(fposmod(float(i)*.618033,1.0),0,0,0))
		cloud_bounds=cloud_bounds.merge(xf*quad.get_aabb())
	mm.buffer=instance_buffer
	mm.custom_aabb=cloud_bounds.grow(18.0)
	assert(mm.buffer.size()==mm.instance_count*16,"Steam instance data lost")
	node.multimesh = mm
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.extra_cull_margin = 18
	own(node,group)
	node.add_to_group("steam",true)

func make_overlook() -> void:
	var group := Node3D.new()
	group.name = "OverlookDeck"
	own(group)
	var x := -252.0
	var z := 159.0
	var y: float = height_field.sample(x,z)+.32
	var deck := BoxMesh.new()
	deck.size = Vector3(6.5,.18,4.5)
	deck.material = deck_mat
	var node := add_geometry(deck,"ViewingPlatform",group,true)
	node.position = Vector3(x,y,z)
	# Connect the eastern spur to the raised deck.
	var ramp_z:=160.05
	var ramp_start:=Vector3(x+5.0,height_field.sample(x+5.0,ramp_z)+.08,ramp_z)
	var nearest:=INF
	for route: Dictionary in spec.routes:
		for point: Array in route.points:
			var d:=Vector2(float(point[0])-ramp_start.x,float(point[2])-ramp_z).length()
			if d<nearest:
				nearest=d
				ramp_start.y=float(point[1])+.002
	var ramp_end:=Vector3(x+3.15,y+.092,ramp_z)
	add_geometry(ribbon(PackedVector3Array([ramp_start,ramp_end]),1.9,wood_mat),"OverlookEntryRamp",group,true)
	# Explicit timber members with an open southern approach.
	var corners:=PackedVector3Array([Vector3(x-3.13,y+.09,z+2.05),Vector3(x-3.13,y+.09,z-2.05),Vector3(x+3.13,y+.09,z-2.05),Vector3(x+3.13,y+.09,z-.1)])
	for i in range(corners.size()-1):
		var a:=corners[i]
		var b:=corners[i+1]
		var count:=int(ceil(a.distance_to(b)/1.6))
		for j in range(count+1):
			var base:=a.lerp(b,float(j)/float(count))
			var post:=BoxMesh.new()
			post.size=Vector3(.12,1.08,.12)
			post.material=timber_post_mat
			var post_node:=add_geometry(post,"OverlookPost",group,true)
			post_node.position=base+Vector3.UP*.54
		beam_between(a+Vector3.UP*1.04,b+Vector3.UP*1.04,.12,group)
		beam_between(a+Vector3.UP*.52,b+Vector3.UP*.52,.09,group)

func collect_meshes(node: Node, transform := Transform3D.IDENTITY) -> Array:
	var meshes: Array = []
	var xf := transform
	if node is Node3D:
		xf = transform*node.transform
	if node is MeshInstance3D:
		meshes.append([node.mesh,xf])
	for child in node.get_children():
		meshes.append_array(collect_meshes(child,xf))
	return meshes

func bind_foliage_materials(assets: Array, kind: String) -> bool:
	if kind in ["pine", "snag"]:
		return LodgepoleLibrary.bind_cutout_materials(assets)
	for asset: Array in assets:
		var mesh: Mesh=asset[0]
		if not mesh is ArrayMesh:
			continue
		for surface in mesh.get_surface_count():
			var original: Material=mesh.surface_get_material(surface)
			if original is StandardMaterial3D and original.transparency==BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR:
				var leaves:=ShaderMaterial.new()
				leaves.shader=load("res://shaders/foliage.gdshader")
				var texture: Texture2D = original.albedo_texture
				if kind in ["pine", "snag"]:
					texture = LodgepoleLibrary.cutout_texture(texture.resource_path.get_file())
					if texture == null:
						return false
				leaves.set_shader_parameter("albedo_texture",texture)
				leaves.set_shader_parameter("alpha_cutoff",.40 if kind == "grass" else .32)
				leaves.set_shader_parameter("use_texture",true)
				leaves.set_shader_parameter("tint",Vector3(.96,1.00,.90))
				leaves.set_shader_parameter("wind_strength",.045 if kind=="grass" else .14)
				mesh.surface_set_material(surface,leaves)
	return true

func make_vegetation() -> bool:
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/placements.json"))
	var overrides: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/placement_overrides.json"))
	var canopy_header: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/lidar_canopy/unresolved_render_canopy.json"))
	if not canopy_header is Dictionary:
		push_error("Tree detail bounds require canopy metadata")
		return false
	var canopy_cell_m: float = float(canopy_header.cell_size_m)
	var detail_origin := Vector2(float(canopy_header.first_cell_x_m), float(canopy_header.first_cell_z_m)) - Vector2.ONE * canopy_cell_m * .5
	var detail_bounds := Rect2(detail_origin, Vector2(float(canopy_header.width), float(canopy_header.height)) * canopy_cell_m)
	var group := Node3D.new()
	group.name = "AuthoredVegetation"
	own(group)
	var records: Array = []
	for category in ["trees","grass","logs","rocks"]:
		records.append_array(data[category])
	records.append_array(overrides.get("add",[]))
	var bins: Dictionary = {}
	var support_records: Array = []
	for record: Dictionary in records:
		var identity: String = str(record.get("id", record.get("stable_id", "")))
		if identity in overrides.get("remove",[]):
			continue
		var r: Dictionary = overrides.get("replace",{}).get(identity,record)
		if r.kind == "pine":
			support_records.append(r)
		var p: Array = r.position
		var variant: int = 0 if r.kind in ["pine", "snag"] else int(r.get("variant",0))
		var form: String = LodgepoleLibrary.archetype(r) if r.kind in ["pine", "snag"] else ""
		var cell_size_m: float = 64.0 if r.kind in ["pine", "snag"] and detail_bounds.has_point(Vector2(p[0], p[2])) else 256.0
		var key := "%s_%s_%d_%d_%d_%d" % [r.kind,form,variant,int(cell_size_m),int(floor(p[0]/cell_size_m)),int(floor(p[2]/cell_size_m))]
		if not bins.has(key):
			bins[key] = []
		bins[key].append(r)
	for key: String in bins:
		var entries: Array = bins[key]
		var exemplar: Dictionary = entries[0]
		var variant: int = 0 if exemplar.kind in ["pine", "snag"] else int(exemplar.get("variant",0))
		var form: String = LodgepoleLibrary.archetype(exemplar) if exemplar.kind in ["pine", "snag"] else ""
		var asset_key := "%s_%s_%d" % [exemplar.kind,form,variant]
		if not mesh_library.has(asset_key):
			var assets: Array = []
			if exemplar.kind=="grass":
				var files := ["grass_tall_a","grass_tall_b","grass_small_a","grass_small_b"]
				var path := "res://assets/imported/grass_medium_01/%s.gltf" % files[int(exemplar.variant)%4]
				if ResourceLoader.exists(path):
					var source: Node = load(path).instantiate()
					assets = collect_meshes(source)
					source.free()
			elif exemplar.kind in ["pine", "snag"]:
				assets = LodgepoleLibrary.load_assets(form, variant)
				if assets.is_empty():
					push_error("Required lodgepole assets are unavailable: " + form)
					return false
			if assets.is_empty():
				var mesh: Mesh
				if exemplar.kind=="rock":
					var rock := SphereMesh.new()
					rock.radial_segments = 7
					rock.rings = 4
					rock.radius = 1.4
					rock.height = 1.7
					rock.material = stone_mat
					mesh = rock
				elif exemplar.kind=="log":
					var log_mesh := CylinderMesh.new()
					log_mesh.top_radius=.17
					log_mesh.bottom_radius=.25
					log_mesh.height=6.2
					log_mesh.radial_segments=7
					log_mesh.material=bark_mat
					mesh=log_mesh
				else:
					var grass := PrismMesh.new()
					grass.size=Vector3(.24,.7,.04)
					grass.material=material(Color(.27,.33,.12))
					mesh=grass
				var xf := Transform3D.IDENTITY
				if exemplar.kind=="log":
					xf=Transform3D(Basis(Vector3.FORWARD,PI/2),Vector3(0,.20,0))
				assets=[[mesh,xf]]
			if not bind_foliage_materials(assets, str(exemplar.kind)):
				return false
			mesh_library[asset_key]=assets
		var asset_batches: Array = []
		for source_asset: Array in mesh_library[asset_key]:
			if exemplar.kind in ["pine", "snag"] and str(source_asset[4]) in ["Branches", "NeedleCards"]:
				var architecture_lod: int = 0 if float(source_asset[2]) == 0.0 else (1 if float(source_asset[2]) == 18.0 else 2)
				for architecture_variant: int in range(4):
					var variant_entries: Array = []
					for record: Dictionary in entries:
						if int(LodgepoleLibrary.variation_key(record)) == architecture_variant:
							variant_entries.append(record)
					if variant_entries.is_empty():
						continue
					var architecture_assets := LodgepoleLibrary.load_architecture(form, architecture_variant, architecture_lod)
					if not bind_foliage_materials(architecture_assets, str(exemplar.kind)):
						return false
					if architecture_assets.is_empty():
						return false
					for architecture_asset: Array in architecture_assets:
						if str(architecture_asset[4]) == str(source_asset[4]):
							asset_batches.append([architecture_asset, variant_entries, architecture_variant])
			elif exemplar.kind in ["pine", "snag"] and str(source_asset[4]) == "Billboard":
				var view_asset := LodgepoleLibrary.load_billboard_batch(form, false)
				if view_asset.is_empty():
					return false
				asset_batches.append([view_asset, entries, -2])
			else:
				asset_batches.append([source_asset, entries, -1])
		var tree_meshes: Array[MultiMeshInstance3D] = []
		var tree_bin_bounds := AABB()
		for batch: Array in asset_batches:
			var asset: Array = batch[0]
			var render_entries: Array = batch[1]
			var mm := MultiMesh.new()
			mm.transform_format=MultiMesh.TRANSFORM_3D
			mm.use_colors=true
			var is_tree: bool = exemplar.kind in ["pine", "snag"]
			mm.use_custom_data=is_tree
			mm.mesh=asset[0]
			if is_tree:
				LodgepoleLibrary.bind_instance_lods(asset)
			mm.instance_count=render_entries.size()
			var batch_cell_m: float = 64.0 if exemplar.kind in ["pine", "snag"] and detail_bounds.has_point(Vector2(exemplar.position[0], exemplar.position[2])) else 256.0
			var center := Vector3((floor(float(exemplar.position[0])/batch_cell_m)+0.5)*batch_cell_m,0,(floor(float(exemplar.position[2])/batch_cell_m)+0.5)*batch_cell_m)
			var instance_buffer:=PackedFloat32Array()
			var instance_bounds:=AABB()
			for i in render_entries.size():
				var r: Dictionary=render_entries[i]
				var p := Vector3(r.position[0],r.position[1],r.position[2])
				var basis := Basis(Vector3.UP,float(r.yaw))
				var local: Transform3D = LodgepoleLibrary.local_transform(r, str(asset[4])) if r.kind in ["pine", "snag"] else Transform3D(Basis.from_scale(Vector3.ONE * float(r.scale)), Vector3.ZERO)
				var xf: Transform3D=Transform3D(basis,p-center)*local*asset[1]
				if not xf.is_finite():
					push_error("Vegetation transform is nonfinite: " + str(r.get("id", r.get("stable_id", "unknown"))))
					return false
				var color := Color(float(LodgepoleLibrary.variation_key(r)) / 3.0, 1.0, 1.0, 1.0) if int(batch[2]) == -2 else Color.WHITE
				append_instance(instance_buffer,xf,color)
				if is_tree:
					var height_m: float = float(LodgepoleLibrary.display_dimensions(r).height_m)
					instance_buffer.append_array(PackedFloat32Array([p.x, p.y + height_m * 0.5, p.z, 1.0]))
				var bounds: AABB=xf*mm.mesh.get_aabb()
				instance_bounds=bounds if i==0 else instance_bounds.merge(bounds)
			mm.buffer=instance_buffer
			mm.custom_aabb=instance_bounds.grow(.7)
			assert(mm.buffer.size()==render_entries.size()*(20 if is_tree else 16),"Vegetation instance data lost")
			var node := MultiMeshInstance3D.new()
			node.name=key + "_%s_%d" % [str(asset[4]), int(asset[2])] if exemplar.kind in ["pine", "snag"] else key
			if int(batch[2]) >= 0:
				node.name += "_variant%d" % int(batch[2]) if str(asset[4]) != "Billboard" else "_view%d" % int(batch[2])
			if int(batch[2]) == -2:
				node.set_meta("packed_impostor_variants", 4)
			node.set_meta("vegetation_kind", str(exemplar.kind))
			if exemplar.kind in ["pine", "snag"]:
				node.set_meta("tree_archetype", form)
				node.set_meta("tree_part", str(asset[4]))
				node.set_meta("display_envelope_class", "transferred_or_photo_authored_unknown_local_error")
				if float(asset[2]) == 0.0 and str(asset[4]) != "Bole":
					node.set_meta("architecture_variant", int(batch[2]))
				node.set_meta("lod_begin_m", float(asset[2]))
				tree_bin_bounds = instance_bounds if tree_meshes.is_empty() else tree_bin_bounds.merge(instance_bounds)
				tree_meshes.append(node)
			node.multimesh=mm
			node.position=center
			node.visibility_range_end=150.0 if exemplar.kind=="grass" else 2800.0
			if asset.size()>2:
				node.visibility_range_begin=asset[2]
				node.visibility_range_end=asset[3]
				if float(asset[2]) >= float(LodgepoleLibrary.LOD_RANGES[2][0]):
					node.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			if exemplar.kind=="grass":
				node.cast_shadow=GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			own(node,group)
		for tree_mesh: MultiMeshInstance3D in tree_meshes:
			tree_mesh.multimesh.custom_aabb = tree_bin_bounds.grow(.7)
			var radius_m: float = tree_mesh.multimesh.custom_aabb.size.length() * 0.5
			var begin_padding_m: float = radius_m + clampf(tree_mesh.visibility_range_begin * 0.1, 2.0, 18.0)
			var end_padding_m: float = radius_m + clampf(tree_mesh.visibility_range_end * 0.1, 2.0, 18.0)
			tree_mesh.set_meta("instance_lod", true)
			tree_mesh.set_meta("lod_batch_padding_m", [begin_padding_m, end_padding_m])
			tree_mesh.visibility_range_begin = maxf(0.0, tree_mesh.visibility_range_begin - begin_padding_m)
			tree_mesh.visibility_range_end += end_padding_m
		# Place trunk colliders at tree-mesh origins.
		if exemplar.kind in ["pine", "snag"]:
			for r: Dictionary in entries:
				if absf(r.position[0])>750 or absf(r.position[2])>1250:
					continue
				var tree_transform: Transform3D = LodgepoleLibrary.local_transform(r, "Bole")
				var tree_form: String = LodgepoleLibrary.archetype(r)
				var tree_height: float = float(LodgepoleLibrary.metadata().archetypes[tree_form].height_m) * tree_transform.basis.y.length()
				var collision_height: float = minf(3.0, tree_height)
				var body := StaticBody3D.new()
				body.position=Vector3(r.position[0],r.position[1]+collision_height*.5,r.position[2])
				body.set_meta("tree_height_m", tree_height)
				own(body,group)
				var col := CollisionShape3D.new()
				var cylinder := CylinderShape3D.new()
				cylinder.radius=float(LodgepoleLibrary.metadata().archetypes[tree_form].dbh_m) * tree_transform.basis.x.length() * 0.5
				cylinder.height=collision_height
				col.shape=cylinder
				own(col,body)
	if not CanopySurface.build(scene_root, "res://data/lidar_canopy/unresolved_render_canopy.json", 128.0, support_records):
		return false
	return ForestFloor.build(scene_root, "res://data/forest_floor.json")

func bake_vegetation_only(start: int) -> void:
	spec = JSON.parse_string(FileAccess.get_file_as_string("res://data/world.json"))
	height_field = HeightField.new()
	# Load the binary bake when present; the text scene is the fallback.
	var world_path := "res://scenes/authored_world.scn"
	if not ResourceLoader.exists(world_path):
		world_path = "res://scenes/authored_world.tscn"
	scene_root = load(world_path).instantiate()
	get_root().add_child(scene_root)
	var previous: Node = scene_root.get_node_or_null("AuthoredVegetation")
	if previous != null:
		previous.free()
	stone_mat = material(Color(0.65,0.63,0.55))
	stone_mat.albedo_texture = load("res://assets/textures/rock_boulder_dry_diff_1k.jpg")
	bark_mat = material(Color(0.64,0.60,0.48))
	bark_mat.albedo_texture = load("res://assets/textures/pine_bark_diff_1k.jpg")
	if not make_vegetation():
		quit(1)
		return
	if "--water" in OS.get_cmdline_user_args():
		var water: Node = scene_root.get_node_or_null("ConnectedWater")
		if water != null:
			water.free()
		make_water()
	var packed := PackedScene.new()
	var error: int = packed.pack(scene_root)
	if error == OK:
		error = ResourceSaver.save(packed,"res://scenes/authored_world.scn")
	if error == OK:
		error = ResourceSaver.save(packed,"res://scenes/authored_world.tscn")
	print("VEGETATION_BAKE ",error," ",(Time.get_ticks_msec()-start)/1000.0," seconds")
	quit(error)
