extends SceneTree
## Independent opaque floor geometry and slope-contact checks.

const Geometry := preload("res://scripts/forest_floor_geometry.gd")
const Floor := preload("res://scripts/forest_floor.gd")
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("verify")

func check(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures.append(label)

func verify() -> void:
	var triangles: Dictionary = {}
	var material := ShaderMaterial.new()
	material.shader = load("res://shaders/forest_floor_foliage.gdshader")
	for guild: String in Floor.GUILDS + ["litter"]:
		var counts: Array = []
		for detailed: bool in [true, false]:
			var mesh := Geometry.litter(detailed, material) if guild == "litter" else Geometry.plant(guild, detailed, material)
			var arrays := mesh.surface_get_arrays(0)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
			var wind: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV2]
			counts.append(vertices.size() / 3)
			check(vertices.size() > 36 and vertices.size() == normals.size() and vertices.size() == wind.size(), "Solid arrays exist for " + guild)
			var anchored := 0
			var moving := 0
			var z_extent := 0.0
			for index: int in vertices.size():
				var point := vertices[index]
				check(point.is_finite() and normals[index].is_finite() and absf(normals[index].length() - 1.0) < 0.00001, "Finite vertices and unit normals")
				check(Vector2(point.x, point.z).length() < 0.501 and point.y >= -0.001 and point.y <= 1.01, "Mesh fits its footprint and height")
				check(wind[index].x >= 0.0 and wind[index].x <= 1.01, "Finite bounded wind weights")
				if point.y < 0.00001:
					anchored += 1
					check(wind[index].x < 0.00001, "Root vertices remain fixed in wind")
				if wind[index].x > 0.2:
					moving += 1
				z_extent = maxf(z_extent, absf(point.z))
			check(z_extent > 0.1, "Geometry occupies depth")
			if guild != "litter":
				check(anchored > 0 and moving > 0, "Live plant has anchored roots and flexible tips")
			else:
				check(moving == 0, "Litter stays on the ground")
				var area := 0.0
				for i: int in range(0, vertices.size(), 3):
					if wind[i].y < 0.5: continue
					var a := Vector2(vertices[i].x, vertices[i].z)
					var b := Vector2(vertices[i + 1].x, vertices[i + 1].z)
					var c := Vector2(vertices[i + 2].x, vertices[i + 2].z)
					area += absf((b - a).cross(c - a)) * 0.5
				check(area >= 0.60 and area <= 0.64, "Litter bed occupies the authored 60-64 percent of its square footprint")
				check(absf(area - Geometry.litter_bed_area(detailed)) < 0.000001, "Reported bed footprint matches independent projected triangle area")
				check(not arrays[Mesh.ARRAY_TANGENT].is_empty(), "Human litter normal map requires tangents")
				for vertex: int in vertices.size():
					if wind[vertex].y < 0.5:
						check(vertices[vertex].y >= Geometry.litter_bed_height(Vector2(vertices[vertex].x, vertices[vertex].z), detailed) - 0.000001, "Three-dimensional debris remains above the litter bed")
		check(counts[1] < counts[0], "Distant geometry reduces triangle count")
		triangles[guild] = counts
	var record := {"kind": "understory_card", "position": [5, 2, 3], "size": [1.2, 0.4, 1.2], "yaw": 1.23, "ground_normal": [0.0, 0.8, 0.6]}
	var transform := Floor.instance_transform(record, "Understory")
	check(transform.origin == Vector3(5, 2, 3) and transform.basis.y.normalized().distance_to(Vector3(0, 0.8, 0.6)) < 0.00001, "Plane-aligned plant preserves position and sampled normal")
	check(transform.basis.determinant() > 0.0, "Terrain transform preserves handedness")
	for angle: float in [0.0, 0.0001, 0.0002, 0.0003, 0.001, 0.66]:
		var normal := Vector3(sin(angle), cos(angle), 0.0)
		record.ground_normal = [normal.x, normal.y, normal.z]
		transform = Floor.instance_transform(record, "Understory")
		check(transform.basis.y.normalized().distance_to(normal) < 0.00001, "Small terrain slopes retain their sampled normal")
		check(transform.basis.determinant() > 0.0, "Small terrain slopes preserve handedness")
	validate_log_contact_precision()
	validate_snag_material_isolation()
	var litter_transform := Floor.instance_transform({"kind": "litter", "position": [0, 0, 0], "size": [1.6, 0.04, 1.6], "yaw": 0.4, "ground_normal": [0, 1, 0]}, "Litter")
	check(is_equal_approx(litter_transform.basis.x.length(), litter_transform.basis.y.length()) and is_equal_approx(litter_transform.basis.z.length(), litter_transform.basis.y.length()), "Litter preserves round twig sections with uniform scale")
	var wood := Geometry.log_mesh(true, StandardMaterial3D.new())
	var wood_vertices: PackedVector3Array = wood.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	for stub: int in 4:
		var anchor := -0.32 + stub * 0.19
		for i: int in range(120 + stub * 60, 120 + (stub + 1) * 60):
			check(wood_vertices[i].y >= anchor - 0.004 and wood_vertices[i].y <= anchor + 0.030, "Log stub root avoids axial scaling spikes")
	var report := {"ok": failures.is_empty(), "checks": checks, "triangles_near_mid": triangles, "failures": failures, "performance_scope": "geometry counts only; frame time requires native world benchmark"}
	var args := OS.get_cmdline_user_args()
	var output := "user://floor_geometry_validation.json"
	for i: int in args.size():
		if args[i] == "--out" and i + 1 < args.size():
			output = args[i + 1]
	var file := FileAccess.open(output, FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "  "))
	file.close()
	print("FLOOR_GEOMETRY_VALIDATION ", JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)

func validate_log_contact_precision() -> void:
	for coordinate: float in [-639.4559362352, 0.0, 639.4559362352]:
		var length_m := 4.1152187394
		var diameter := 0.2826613795
		var dx := sin(3.3588776966) * length_m * 0.5
		var dz := cos(3.3588776966) * length_m * 0.5
		var record := {"position": [coordinate, 12.0, coordinate], "size": [diameter, diameter, length_m], "axis_end_positions": [[coordinate - dx, 12.0 + diameter * 0.5, coordinate - dz], [coordinate + dx, 12.0 + diameter * 0.5, coordinate + dz]], "end_positions": [[coordinate - dx, 12.0, coordinate - dz], [coordinate + dx, 12.0, coordinate + dz]], "ground_profile_m": [], "contact_clearance_m": []}
		for i: int in 18:
			record.ground_profile_m.append([-length_m * 0.5 + i * length_m / 17.0, 12.0])
			record.contact_clearance_m.append(0.0)
		check(Floor._log_contact_valid(record, 0.24), "Double-precision source contact remains valid near map boundaries")
		record.ground_profile_m[8][1] = 11.5
		check(not Floor._log_contact_valid(record, 0.24), "Corrupted interior contact remains invalid at every map location")

func validate_snag_material_isolation() -> void:
	Floor._asset_cache.clear()
	for variant: int in 4:
		var tree_assets: Array = Floor.Lodgepole.load_assets("snag", variant)
		check(tree_assets.size() == 7, "Snag asset library supplies three woody LOD pairs and one billboard")
		if tree_assets.is_empty(): continue
		for asset: Array in tree_assets:
			Floor.Lodgepole.bind_instance_lods(asset)
		var floor_assets: Array = Floor._assets({"kind": "snag", "variant": variant})
		check(floor_assets.size() == tree_assets.size(), "Floor snag retains all tree asset parts")
		for i: int in floor_assets.size():
			var floor_mesh: Mesh = floor_assets[i][0]
			var tree_mesh: Mesh = tree_assets[i][0]
			check(floor_mesh != tree_mesh, "Floor snag mesh is isolated from the tree cache")
			for surface: int in floor_mesh.get_surface_count():
				var floor_material: Material = floor_mesh.surface_get_material(surface)
				var tree_material: Material = tree_mesh.surface_get_material(surface)
				check(floor_material != tree_material, "Floor snag material is isolated from the tree cache")
				if floor_material is ShaderMaterial:
					check(floor_material.get_shader_parameter("instance_lod") == false, "Floor snag does not read absent custom LOD data")
					check(tree_material.get_shader_parameter("instance_lod") == true, "Floor isolation preserves tree per-instance LOD")
