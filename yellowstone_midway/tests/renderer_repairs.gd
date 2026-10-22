extends "res://tools/bake_world.gd"
## Spatial rendering regression fixtures.

const RiverTerrain := preload("res://scripts/river_terrain.gd")
class ReplayFixture extends RefCounted:
	var _cells: Array = []

class WorldFixture extends Node3D:
	var ecosystem: RefCounted

const Overlays := preload("res://scripts/scientific_overlays.gd")
const Materials := preload("res://scripts/terrain_materials.gd")
const Receipt := preload("res://scripts/verification_receipt.gd")
const Junctions := preload("res://tools/validate_river_junctions.gd")
var checks := 0
var test_failures: Array[String] = []

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		test_failures.append(message)

func _initialize() -> void:
	call_deferred("run_regressions")

func run_regressions() -> void:
	var rivers := [{"id": "fixture", "width": 4.0, "points": [[0.0, 2.0, -10.0], [0.0, 4.0, 10.0]]}]
	var heights := PackedFloat32Array()
	heights.resize(21 * 21)
	heights.fill(10.0)
	var report := RiverTerrain.carve(heights, 21, 21, Vector2(-10, -10), 1.0, rivers)
	check(absf(heights[10 * 21 + 10] - 2.55) < 0.00001, "channel bed has interpolated stage minus authored depth")
	check(heights[10 * 21] == 10.0, "carving preserves distant terrain")
	check(report.changed_vertices > 0 and report.value_class == "authored_render_bed", "carving reports authored provenance")
	var image := RiverTerrain.stage_image(rivers, Vector2(-80, -20), Vector2(160, 40), 1.0)
	check(absf(image.get_pixel(80, 20).r - 3.05) < 0.00001, "stage varies along the reach")
	check(image.get_pixel(0, 20).g == 0.0, "stage has bounded spatial support")
	var thermal := rivers.duplicate(true)
	thermal[0].thermal = true
	check(RiverTerrain.stage_image(thermal, Vector2(-1, -1), Vector2(2, 2), 1.0).get_pixel(0, 0).g == 0.0, "thermal channels do not set river bank stage")
	var spec: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world.json"))
	for ri: int in spec.rivers.size():
		var river: Dictionary = spec.rivers[ri]
		var points := points_of(river.points)
		var mesh := river_ribbon(points, float(river.width), StandardMaterial3D.new(),
			river_end_is_free(spec.rivers, ri, points[0]),
			river_end_is_free(spec.rivers, ri, points[-1]))
		check(mesh != null and mesh.get_surface_count() == 1, str(river.id) + " has ribbon geometry")
		var arrays := mesh.surface_get_arrays(0)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
		var wrong_winding := 0
		for tri: int in range(0, indices.size(), 3):
			var a := vertices[indices[tri]]
			var b := vertices[indices[tri + 1]]
			var c := vertices[indices[tri + 2]]
			if (b.x - a.x) * (c.z - a.z) - (c.x - a.x) * (b.z - a.z) < -0.000002:
				wrong_winding += 1
		check(wrong_winding == 0, str(river.id) + " retains clockwise plan winding")
		if str(river.id) != "river_5933_0":
			continue
		var uncovered := 0
		for i: int in range(1, points.size()):
			for sample: int in range(ceili(points[i].distance_to(points[i - 1]) / 0.1) + 1):
				var point := points[i - 1].lerp(points[i], minf(1.0, float(sample) * 0.1 / points[i].distance_to(points[i - 1])))
				var covered := false
				for tri: int in range(0, indices.size(), 3):
					var a := vertices[indices[tri]]
					var b := vertices[indices[tri + 1]]
					var c := vertices[indices[tri + 2]]
					if Geometry2D.is_point_in_polygon(Vector2(point.x, point.z), PackedVector2Array([Vector2(a.x,a.z), Vector2(b.x,b.z), Vector2(c.x,c.z)])):
						covered = true
						break
				if not covered:
					uncovered += 1
		check(uncovered == 0, "upstream mapped channel stays inside ribbon: " + str(uncovered))
	check_canopy_exclusions()
	check_markers()
	check_stage_frame()
	check_junction_failures()
	check_receipt_failures()
	print("RENDERER_REPAIRS ", JSON.stringify({"ok": test_failures.is_empty(), "checks": checks, "failures": test_failures}))
	quit(0 if test_failures.is_empty() else 1)

func check_canopy_exclusions() -> void:
	var path := "res://data/lidar_canopy/unresolved_render_canopy.json"
	var header: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	var mask_path := path.get_base_dir().path_join(header.artifacts.unresolved_render_mask.path)
	var before := FileAccess.get_sha256(mask_path)
	var source := CanopySurface.read_source(path)
	check(not source.is_empty(), "canopy display source validates")
	if source.is_empty():
		return
	var original := FileAccess.get_file_as_bytes(path.get_base_dir().path_join(header.artifacts.unresolved_cells.path))
	var excluded := FileAccess.get_file_as_bytes(path.get_base_dir().path_join("unresolved_cells_excluded.u8"))
	var cleared := 0
	var residual := 0
	var subdivision := roundi(float(source.cell_size_m) / float(source.highres_mask_cell_size_m))
	for index: int in original.size():
		if original[index] == 0 or excluded[index] != 0:
			continue
		cleared += 1
		check(source.unresolved_cells[index] == 0 and source.cover_fraction[index] == 0.0, "excluded cell clears cluster and cover")
		for z: int in subdivision:
			for x: int in subdivision:
				if source.mask_image.get_pixel((index % source.width) * subdivision + x, int(index / source.width) * subdivision + z).r > 0.0:
					residual += 1
	check(cleared == 658 and residual == 0, "all excluded distant canopy pixels clear")
	check(FileAccess.get_sha256(mask_path) == before, "display filtering preserves source bytes")

func check_markers() -> void:
	var replay: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/river_replay.json"))
	var geochem: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/geochemistry.json"))
	var eco := ReplayFixture.new()
	eco._cells = replay.replay.cells
	var world_fixture := WorldFixture.new()
	world_fixture.ecosystem = eco
	var overlay := Overlays.new()
	world_fixture.add_child(overlay)
	overlay.bind(world_fixture, {}, geochem, {}, {})
	var markers := overlay.get_node("GeochemistryMarkers")
	var positions: Dictionary = {}
	for cell: Dictionary in eco._cells:
		positions[str(cell.id)] = Vector3(cell.position_xyz[0], cell.position_xyz[1], cell.position_xyz[2])
	var step_i := maxi(1, ceili(float(geochem.cells.size()) / 128.0))
	check(markers.get_child_count() == ceili(float(geochem.cells.size()) / step_i), "published cells produce the expected markers")
	for index: int in markers.get_child_count():
		var source: Dictionary = geochem.cells[index * step_i]
		var actual: Vector3 = markers.get_child(index).position - Vector3.UP * Overlays.GEOCHEM_MARKER_HEIGHT_M * 0.5
		check(actual.distance_to(positions[str(source.cell)]) < 0.0001, "marker matches published cell identity")
	world_fixture.free()

func check_stage_frame() -> void:
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/terrain.gdshader")
	check(Materials.set_layer_rect(mat, "water", -2048.0, -2048.0, 4096.0, 4096.0), "water stage binds to geographic frame")
	var point := Vector2(25.0, -300.0)
	var uv: Vector2 = (point - mat.get_shader_parameter("water_level_origin_m")) / mat.get_shader_parameter("water_level_extent_m")
	Materials.set_render_origin(mat, 1024.0, -512.0)
	var rebased: Vector2 = ((point - Vector2(1024.0, -512.0)) - mat.get_shader_parameter("water_level_origin_m")) / mat.get_shader_parameter("water_level_extent_m")
	check(uv.distance_to(rebased) < 0.000001, "stage lookup survives origin rebasing")

func junction_fixture(x: float) -> MeshInstance3D:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(x,0,-1),Vector3(x,0,1),Vector3(x+10,0,-1),Vector3(x+10,0,1)])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2,1,3,2])
	var node := MeshInstance3D.new()
	node.mesh = ArrayMesh.new()
	node.mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	node.set_meta("station_count", 2)
	return node

func check_junction_failures() -> void:
	var validator := Junctions.new()
	var rivers := [{"id":"a","points":[[0,0,0],[10,0,0]]},{"id":"b","points":[[10,0,0],[20,0,0]]}]
	var a := junction_fixture(0)
	var b := junction_fixture(10)
	var joins := validator.validate_junctions(rivers, {"a":a,"b":b})
	check(joins.size() == 2 and validator.failures.is_empty(), "source topology creates two expected directed joins")
	b.position.x += 100.0
	joins = validator.validate_junctions(rivers, {"a":a,"b":b})
	check(joins.size() == 2 and validator.failures.size() == 2, "displaced junctions fail without disappearing")
	validator.failures.clear()
	validator.validate_junctions(rivers, {"a":a})
	check(validator.failures.size() == 2, "missing junction geometry fails")
	a.free()
	b.free()
	validator.free()

func check_receipt_failures() -> void:
	var report := {"schema": Receipt.SCHEMA, "ok":true, "failure_count":0, "actual_instance_slots":1, "expected_instance_slots":1, "source_sha256":Receipt.source_hashes()}
	check(Receipt.valid(report), "matching receipt is accepted")
	report.ok = false
	check(not Receipt.valid(report), "failed receipt is refused")
	report.ok = true
	report.source_sha256[Receipt.scene_path()] = "stale"
	check(not Receipt.valid(report), "stale scene receipt is refused")
