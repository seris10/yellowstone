extends SceneTree
## Validate lodgepole geometry, dimension records and distance LODs.

const Library = preload("res://scripts/lodgepole_library.gd")
var failures: Array[String] = []
var checked_vertices := 0
var checked_triangles := 0
var triangle_counts: Dictionary = {}
var rejected_records := 0

func _initialize() -> void:
	call_deferred("verify")

func check(condition: bool, detail: String) -> void:
	if not condition:
		failures.append(detail)

func close_to(actual: float, expected: float, tolerance: float, detail: String) -> void:
	check(is_finite(actual) and absf(actual - expected) <= tolerance, "%s: %.6f expected %.6f +/- %.6f" % [detail, actual, expected, tolerance])

func finite_vector(point: Vector3) -> bool:
	return is_finite(point.x) and is_finite(point.y) and is_finite(point.z)

func vertices(asset: Array) -> PackedVector3Array:
	var result := PackedVector3Array()
	var mesh: Mesh = asset[0]
	var transform: Transform3D = asset[1]
	for surface in range(mesh.get_surface_count()):
		var arrays := mesh.surface_get_arrays(surface)
		for point: Vector3 in arrays[Mesh.ARRAY_VERTEX]:
			result.append(transform * point)
	return result

func inspect_mesh(asset: Array, name: String) -> int:
	var mesh: Mesh = asset[0]
	var part := str(asset[4])
	var total := 0
	for surface in range(mesh.get_surface_count()):
		check(mesh.surface_get_primitive_type(surface) == Mesh.PRIMITIVE_TRIANGLES, "%s %s uses triangles" % [name, part])
		var arrays := mesh.surface_get_arrays(surface)
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		check(points.size() > 0 and normals.size() == points.size() and uv.size() == points.size(), "%s %s supplies complete mesh arrays" % [name, part])
		check(indices.size() > 0 and indices.size() % 3 == 0, "%s %s supplies triangle indices" % [name, part])
		for index in range(points.size()):
			check(finite_vector(points[index]) and finite_vector(normals[index]), "%s %s vertex %d is finite" % [name, part, index])
			close_to(normals[index].length(), 1.0, 0.002, "%s %s normal %d" % [name, part, index])
			check(is_finite(uv[index].x) and is_finite(uv[index].y), "%s %s UV %d is finite" % [name, part, index])
		for index in range(0, indices.size(), 3):
			var a := indices[index]
			var b := indices[index + 1]
			var c := indices[index + 2]
			if a < 0 or b < 0 or c < 0 or a >= points.size() or b >= points.size() or c >= points.size():
				check(false, "%s %s triangle has an out-of-range index" % [name, part])
				continue
			check((points[b] - points[a]).cross(points[c] - points[a]).length() > 1e-10, "%s %s triangle %d has area" % [name, part, index / 3])
		if part == "NeedleCards":
			check(points.size() % 4 == 0 and indices.size() == points.size() / 4 * 6, "%s foliage comprises individual two-triangle cards" % name)
			var material: Material = mesh.surface_get_material(surface)
			check(material is StandardMaterial3D, "%s foliage has imported alpha material" % name)
			if material is StandardMaterial3D:
				check(material.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR and material.albedo_texture != null, "%s foliage has a textured alpha cutout" % name)
		total += indices.size() / 3
		checked_vertices += points.size()
	checked_triangles += total
	return total

func bound(points: PackedVector3Array, transform: Transform3D) -> AABB:
	var low := Vector3(INF, INF, INF)
	var high := Vector3(-INF, -INF, -INF)
	for point: Vector3 in points:
		var moved := transform * point
		low = low.min(moved)
		high = high.max(moved)
	return AABB(low, high - low)

func section_diameter(asset: Array, local: Transform3D, height: float) -> float:
	var points: Array[Vector3] = []
	var mesh: Mesh = asset[0]
	var transform: Transform3D = local * asset[1]
	for surface: int in range(mesh.get_surface_count()):
		var arrays: Array = mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		for triangle: int in range(0, indices.size(), 3):
			for edge: int in range(3):
				var left: Vector3 = transform * vertices[indices[triangle + edge]]
				var right: Vector3 = transform * vertices[indices[triangle + (edge + 1) % 3]]
				if absf(left.y - height) < 0.000001:
					points.append(left)
				if (left.y < height and right.y > height) or (left.y > height and right.y < height):
					points.append(left.lerp(right, (height - left.y) / (right.y - left.y)))
	if points.is_empty():
		return NAN
	var lower: Vector3 = points[0]
	var upper: Vector3 = points[0]
	for point: Vector3 in points:
		lower = lower.min(point)
		upper = upper.max(point)
	return maxf(upper.x - lower.x, upper.z - lower.z)

func test_dimensions(assets: Array, name: String, base: Dictionary) -> void:
	var record := {"id": "dimension_test", "archetype": name, "height_m": 25.0, "crown_radius_m": 3.1, "dbh_m": 0.47, "crown_ratio": 0.55, "yaw": 1.7, "position": [900.0, -70.0, 200.0]}
	if name == "sapling":
		record.height_m = 7.0
	if name == "snag":
		record.crown_ratio = 0.0
	var display := Library.display_dimensions(record)
	var crown_base := float(record.height_m) * (1.0 - float(display.crown_ratio))
	var authored_base := float(base.height_m) * (1.0 - float(base.crown_ratio))
	for asset: Array in assets:
		var part := str(asset[4])
		var local: Transform3D = Library.local_transform(record, part)
		check(finite_vector(local.origin) and finite_vector(local.basis.x) and local.basis.determinant() > 0.0, "%s %s has a finite positive dimension transform" % [name, part])
		var ground := local * Vector3.ZERO
		if part == "Bole" or part == "Billboard" or name == "snag":
			check(ground.is_equal_approx(Vector3.ZERO), "%s %s retains the ground pivot without world placement" % [name, part])
		if part == "Bole":
			var extent := bound(vertices(asset), local)
			close_to(extent.position.y, 0.0, 0.0001, "%s bole ground" % name)
			close_to(extent.end.y, float(record.height_m), 0.001, "%s bole height" % name)
			if float(asset[2]) == 0.0:
				close_to(section_diameter(asset, local, 1.3), float(record.dbh_m), 0.002, "%s actual mesh DBH at breast height" % name)
				var short: Dictionary = record.duplicate()
				short.height_m = 2.5
				short.dbh_m = 0.08
				close_to(section_diameter(asset, Library.local_transform(short, "Bole"), 1.3), 0.08, 0.002, "%s independently scaled short-tree DBH" % name)
		elif part == "Billboard":
			var extent := bound(vertices(asset), local)
			var authored_extent := bound(vertices(asset), Transform3D.IDENTITY)
			close_to(extent.size.y / authored_extent.size.y, float(record.height_m) / float(base.height_m), 0.0001, "%s billboard full height" % name)
			close_to(extent.size.x / authored_extent.size.x, float(display.crown_radius_m) / float(base.crown_radius_m), 0.0001, "%s billboard crown width" % name)
		elif name != "snag":
			close_to((local * Vector3(0.0, authored_base, 0.0)).y, crown_base, 0.00001, "%s %s clear bole" % [name, part])
			close_to((local * Vector3(0.0, float(base.height_m), 0.0)).y, float(record.height_m), 0.00001, "%s %s crown top" % [name, part])
			var extent := bound(vertices(asset), local)
			check(extent.position.y >= crown_base - 0.2 and extent.end.y <= float(record.height_m) + 0.2, "%s %s occupies the requested upper crown" % [name, part])
		var target_radius := local * Vector3(float(base.crown_radius_m), 0.0, 0.0) - local * Vector3.ZERO
		if part != "Bole":
			close_to(target_radius.length(), float(display.crown_radius_m), 0.00001, "%s %s independent crown radius" % [name, part])
	var alias := record.duplicate()
	alias.erase("crown_radius_m")
	alias.crown_r_m = record.crown_radius_m
	check(Library.local_transform(alias, "Branches").is_equal_approx(Library.local_transform(record, "Branches")), "%s crown radius alias" % name)
	var scaled := {"archetype": name, "scale": 1.4}
	for part: String in ["Bole", "Branches", "NeedleCards", "Billboard"]:
		var transform: Transform3D = Library.local_transform(scaled, part)
		check(transform.is_finite() and is_equal_approx(transform.basis.y.length(), 1.4), "%s %s scalar record preserves height" % [name, part])

func test_negative() -> void:
	for entry: Dictionary in [{"height_m": 0.0}, {"height_m": -2.0}, {"height_m": "unknown"}, {"height_m": null}, {"height_m": INF}, {"height_m": NAN}, {"scale": false}, {"scale": 0.0}, {"dbh_m": -0.1}, {"dbh_m": "0.3"}, {"crown_r_m": 0.0}, {"crown_ratio": 1.01}, {"crown_ratio": 0.0}, {"crown_ratio": "unknown"}, {"archetype": "snag", "crown_ratio": 0.2}]:
		entry.id = "invalid_record"
		var transform: Transform3D = Library.local_transform(entry, "Bole")
		check(not finite_vector(transform.origin) and not finite_vector(transform.basis.x), "Invalid dimensions fail: %s" % entry)
		rejected_records += 1
	check(not finite_vector(Library.local_transform({}, "SolidCone").origin), "Unsupported part fails")
	check(Library.load_assets("unknown_tree").is_empty(), "Unknown asset archetype fails")

func verify() -> void:
	if "--negative" in OS.get_cmdline_user_args():
		test_negative()
		check(rejected_records == 15, "All invalid-record cases execute")
	else:
		check(Library.archetype({}) in ["dense", "edge"] and Library.archetype({"kind": "snag"}) == "snag", "Default and snag archetypes")
		check(Library.archetype({"archetype": "open", "kind": "pine"}) == "open", "Explicit archetype")
		check(Library.archetype({"archetype": "unrecognized"}) in ["dense", "edge"], "Unrecognized archetype uses an authored default")
		for key: String in ["id", "stable_id", "variation_key"]:
			var record := {key: "tree_123"}
			check(Library.variation_key(record) == Library.variation_key(record.duplicate()), "%s stable variation" % key)
			check(int(Library.variation_key(record)) >= 0 and int(Library.variation_key(record)) < 4, "%s bounded variation" % key)
		check(Library.variation_key({"variant": -1}) == "3" and Library.variation_key({"variant": 6}) == "2", "Variant modulo four")
		var info: Dictionary = Library.metadata()
		for filename: String in info.cutout_mips:
			var texture := Library.cutout_texture(filename)
			check(texture != null and texture.get_image().has_mipmaps(), "Cutout requires actual uploaded mip levels")
			if texture != null:
				var image := texture.get_image()
				var mip_entry: Dictionary = info.cutout_mips[filename]
				check(image.get_data_size() == int(mip_entry.bytes) and image.get_mipmap_count() == mip_entry.levels.size() - 1, "Cutout mip buffer dimensions match metadata")
		for reference: Dictionary in info.display_envelope_reference_cases:
			close_to(Library.bechtold_crown_radius_m(reference.dbh_m), reference.radius_m, 0.0000001, "Python/Godot crown transfer coefficients")
		check(not is_finite(Library.bechtold_crown_radius_m(4.999 * .0254)) and not is_finite(Library.bechtold_crown_radius_m(62.201 * .0254)), "Crown transfer refuses DBH extrapolation")
		var source_record := {"id": "envelope", "height_m": 18., "dbh_m": .254, "crown_radius_m": .8, "crown_ratio": .3}
		var source_copy := source_record.duplicate(true)
		var shown := Library.display_dimensions(source_record)
		check(source_record == source_copy and shown.source_core_radius_m == .8 and shown.source_crown_ratio == .3 and shown.crown_radius_m > .8 and shown.crown_ratio == .3, "Display envelope preserves source dimensions")
		var artistic_record := source_record.duplicate(true)
		artistic_record.display_crown_policy = "photo_floor"
		check(Library.display_dimensions(artistic_record).crown_ratio == .7, "Explicit photographic crown floor")
		for name: String in ["dense", "edge", "open", "sapling", "snag"]:
			var assets: Array = Library.load_assets(name)
			check(assets.size() == (7 if name == "snag" else 10), "%s complete split geometry and billboard" % name)
			if assets.is_empty():
				continue
			var counts := [0, 0, 0]
			for asset: Array in assets:
				check(asset.size() == 5 and asset[0] is Mesh and asset[1] is Transform3D, "%s asset tuple" % name)
				if str(asset[4]) == "Billboard":
					check(float(asset[2]) == 180.0 and float(asset[3]) == 3000.0, "%s far visibility range" % name)
					continue
				var level := 0 if float(asset[2]) == 0.0 else (1 if float(asset[2]) == 18.0 else 2)
				check(float(asset[3]) == [18.0, 65.0, 180.0][level], "%s LOD range has no gaps" % name)
				counts[level] += inspect_mesh(asset, name)
			check(counts[0] > counts[1] and counts[1] > counts[2] and counts[2] > 100, "%s retains branch topology while reducing LOD triangles" % name)
			triangle_counts[name] = counts
			test_dimensions(assets, name, info.archetypes[name])
			var architecture_hashes: Array = []
			for architecture_variant: int in range(4):
				var near_parts := Library.load_architecture(name, architecture_variant)
				check(not near_parts.is_empty(), "Near architecture variant exists")
				for near_part: Array in near_parts:
					if str(near_part[4]) == "Branches":
						architecture_hashes.append(hash(vertices(near_part)))
			check(architecture_hashes.size() == 4 and architecture_hashes[0] != architecture_hashes[1] and architecture_hashes[1] != architecture_hashes[2] and architecture_hashes[2] != architecture_hashes[3], "Near architecture variants have distinct branch geometry")
			var texture_paths: Array = []
			for view in range(4):
				var variant: Array = Library.load_assets(name, view)
				if not variant.is_empty():
					var billboard: QuadMesh = variant.back()[0]
					texture_paths.append(billboard.material.albedo_texture.resource_name)
			check(texture_paths.size() == 4 and texture_paths[0] != texture_paths[1] and texture_paths[1] != texture_paths[2] and texture_paths[2] != texture_paths[3], "%s has four distinct billboard views" % name)
	print(JSON.stringify({"check": "lodgepole_assets", "passed": failures.is_empty(), "negative": "--negative" in OS.get_cmdline_user_args(), "vertices": checked_vertices, "triangles": checked_triangles, "lod_triangles": triangle_counts, "failures": failures}))
	quit(0 if failures.is_empty() else 1)
