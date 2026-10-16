extends SceneTree

var findings: Array[String] = []
var report: Dictionary = {}

func _initialize() -> void:
	call_deferred("run")

func require(condition: bool, message: String) -> void:
	if not condition:
		findings.append(message)

func synthetic_mesh() -> ArrayMesh:
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	for z in 3:
		for x in 3:
			vertices.append(Vector3(x * 4, x + z, z * 4))
			normals.append(Vector3.UP)
			uvs.append(Vector2(x * 0.5, z * 0.5))
	for z in 2:
		for x in 2:
			var a: int = z * 3 + x
			indices.append_array(PackedInt32Array([a, a + 1, a + 3, a + 1, a + 4, a + 3]))
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, StandardMaterial3D.new())
	return mesh

func set_bounds(core: Node, x0: float, x1: float, z0: float, z1: float) -> void:
	core.set("_x_min_m", x0)
	core.set("_x_max_m", x1)
	core.set("_z_min_m", z0)
	core.set("_z_max_m", z1)

func check_synthetic(script: Script) -> void:
	var core: Node = script.new()
	var mesh := synthetic_mesh()
	set_bounds(core, 0, 4, 0, 4)
	var result: Dictionary = core._prepare_render_cut(mesh, Transform3D.IDENTITY)
	require(result.ok and result.removed_triangles == 2 and result.retained_triangles == 6, "synthetic cut triangle counts")
	if result.ok:
		var replacement: ArrayMesh = result.mesh
		var original_arrays: Array = mesh.surface_get_arrays(0)
		var arrays: Array = replacement.surface_get_arrays(0)
		for slot: int in [Mesh.ARRAY_VERTEX, Mesh.ARRAY_NORMAL, Mesh.ARRAY_TEX_UV]:
			require(arrays[slot] == original_arrays[slot], "synthetic attribute changed " + str(slot))
		require(replacement.surface_get_material(0) == mesh.surface_get_material(0), "synthetic material changed")
		require(mesh.surface_get_array_index_len(0) == 24, "source mesh changed")
	set_bounds(core, 0, 2, 0, 4)
	require(not core._prepare_render_cut(mesh, Transform3D.IDENTITY).ok, "unaligned bounds accepted")
	set_bounds(core, 0, 4, 0, 4)
	require(not core._prepare_render_cut(BoxMesh.new(), Transform3D.IDENTITY).ok, "unsupported mesh accepted")
	var unsupported_root := Node3D.new()
	var tiles := Node3D.new()
	tiles.name = "TerrainTiles"
	unsupported_root.add_child(tiles)
	var unsupported_tile := MeshInstance3D.new()
	unsupported_tile.mesh = BoxMesh.new()
	tiles.add_child(unsupported_tile)
	root.add_child(unsupported_root)
	core.set("_built", true)
	core.cut_master_tiles(unsupported_root)
	var fallback: Dictionary = core.render_cut_status()
	require(not fallback.complete and not fallback.failures.is_empty(), "unsupported cut did not report fallback")
	var fallback_material := ShaderMaterial.new()
	fallback_material.shader = load("res://shaders/terrain.gdshader")
	core.set_terrain_cut_uniform([fallback_material])
	require(fallback_material.get_shader_parameter("core_cut_active") == 1.0, "unsupported cut disabled fragment fallback")
	unsupported_root.free()
	set_bounds(core, 0, 8, 0, 8)
	result = core._prepare_render_cut(mesh, Transform3D.IDENTITY)
	require(result.ok and result.removed_triangles == 8 and result.mesh.get_surface_count() == 0, "fully covered mesh retains render geometry")
	core.free()
	report["synthetic"] = {"partial_removed": 2, "partial_retained": 6, "complete_removed": 8, "negative_controls": 3, "fallback_reported": true}

func check_real(script: Script) -> void:
	var scene: Node = load("res://scenes/authored_world.tscn").instantiate()
	root.add_child(scene)
	var core: Node = script.new()
	root.add_child(core)
	var mat_surface: RefCounted = load("res://scripts/mat_surface.gd").new()
	mat_surface.load_outflow()
	mat_surface.load_pigment()
	require(core.build(mat_surface), "real core build failed")
	var parent: Node = scene.find_child("TerrainTiles", true, false)
	var originals: Dictionary = {}
	for child: Node in parent.get_children():
		if child is MeshInstance3D:
			originals[child.get_instance_id()] = (child as MeshInstance3D).mesh
	var collision_tiles: int = core.cut_master_tiles(scene)
	var state: Dictionary = core.render_cut_status()
	require(state.complete, "real render cut fell back")
	require(state.tiles.size() == 12 and collision_tiles == 12, "real affected tile counts")
	require(state.removed_triangles == 45000 and state.expected_removed_triangles == 45000, "real removed triangle coverage")
	var removed: int = 0
	var changed: int = 0
	var empty_tiles: int = 0
	for child: Node in parent.get_children():
		if not child is MeshInstance3D:
			continue
		var tile: MeshInstance3D = child as MeshInstance3D
		var original: ArrayMesh = originals[tile.get_instance_id()]
		if tile.mesh == original:
			continue
		changed += 1
		var original_arrays: Array = original.surface_get_arrays(0)
		var original_indices: PackedInt32Array = original_arrays[Mesh.ARRAY_INDEX]
		var vertices: PackedVector3Array = original_arrays[Mesh.ARRAY_VERTEX]
		var expected := PackedInt32Array()
		for k in range(0, original_indices.size(), 3):
			var wholly_inside: bool = true
			for offset in 3:
				var p: Vector3 = tile.global_transform * vertices[original_indices[k + offset]]
				wholly_inside = wholly_inside and p.x >= -340 and p.x <= 260 and p.z >= -380 and p.z <= 220
			if wholly_inside:
				removed += 1
			else:
				expected.append_array(PackedInt32Array([original_indices[k], original_indices[k + 1], original_indices[k + 2]]))
		if expected.is_empty():
			empty_tiles += 1
			require(tile.mesh.get_surface_count() == 0, "covered tile still casts geometry")
		else:
			var arrays: Array = tile.mesh.surface_get_arrays(0)
			require(arrays[Mesh.ARRAY_INDEX] == expected, "outside triangle indices changed")
			for slot: int in [Mesh.ARRAY_VERTEX, Mesh.ARRAY_NORMAL, Mesh.ARRAY_TEX_UV]:
				require(arrays[slot] == original_arrays[slot], "real attribute changed " + str(slot) + " tile " + str(tile.name))
			require(tile.mesh.surface_get_material(0) == original.surface_get_material(0), "real tile material changed")
	require(changed == 12 and removed == 45000 and empty_tiles == 2, "independent real mesh coverage")
	var material: ShaderMaterial = load("res://assets/materials/terrain.tres").duplicate()
	core.set_terrain_cut_uniform([material])
	require(material.get_shader_parameter("core_cut_active") == 0.0, "fragment cut remains after complete mesh cut")
	require(core.cut_master_tiles(scene) == 12, "repeat render cut is not idempotent")
	report["real"] = state
	report["real"]["independently_removed_triangles"] = removed
	report["real"]["empty_tiles"] = empty_tiles
	report["real"]["outside_triangles_and_attributes_unchanged"] = true
	set_bounds(core, -339, 260, -380, 220)
	core.set("_render_cut_complete", false)
	core.set_terrain_cut_uniform([material])
	require(material.get_shader_parameter("core_cut_active") == 1.0, "fallback fragment cut disabled")
	scene.free()
	core.free()

func run() -> void:
	var script: Script = load("res://scripts/core_terrain.gd")
	check_synthetic(script)
	check_real(script)
	report["findings"] = findings
	report["pass"] = findings.is_empty()
	report["godot"] = Engine.get_version_info().string
	var arguments: PackedStringArray = OS.get_cmdline_user_args()
	if arguments.size() == 2 and arguments[0] == "--report-out":
		var file := FileAccess.open(arguments[1], FileAccess.WRITE)
		if file != null:
			file.store_string(JSON.stringify(report, "\t") + "\n")
	print("CORE_RENDER_CUT ", "PASS" if findings.is_empty() else "FAIL", " findings=", findings)
	quit(0 if findings.is_empty() else 1)
