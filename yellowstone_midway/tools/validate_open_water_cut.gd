extends SceneTree
## Conservative mapped-water cuts and source preservation.

const Core = preload("res://scripts/core_terrain.gd")
var failures: Array[String] = []

func check(value: bool, message: String) -> void:
	if not value:
		failures.append(message)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var core := Core.new()
	root.add_child(core)
	var vertices := PackedVector3Array([Vector3(0.2, 0, 0.2), Vector3(0.8, 0, 0.2), Vector3(0.2, 0, 0.8), Vector3(3, 0, 3), Vector3(4, 0, 3), Vector3(3, 0, 4), Vector3(0.5, 0, 0.5), Vector3(3.5, 0, 0.5), Vector3(0.5, 0, 3.5)])
	var indices := PackedInt32Array([0, 1, 2, 3, 4, 5, 6, 7, 8])
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var node := MeshInstance3D.new()
	node.mesh = mesh
	core.add_child(node)
	core._tile_mesh_instance = node
	var pools: Array = [{"thermal": true, "name": "concave fixture", "ring": [[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]]}]
	var report := core.cut_open_water(pools)
	check(int(report.removed_triangles) == 1, "Interior triangle is not removed")
	check(node.mesh.surface_get_arrays(0)[Mesh.ARRAY_INDEX] == PackedInt32Array([3, 4, 5, 6, 7, 8]), "Dry or concavity-crossing triangle is removed")
	check(node.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX] == vertices, "Source vertices change")
	check(mesh.surface_get_arrays(0)[Mesh.ARRAY_INDEX] == indices, "Source mesh mutates")
	check(core.cut_open_water(pools) == report, "Repeated cut accumulates changes")
	core.cut_open_water([])
	check(node.mesh.surface_get_arrays(0)[Mesh.ARRAY_INDEX] == indices, "Empty water selection cannot restore the source")
	node.position.x = 10.0
	check(int(core.cut_open_water(pools).removed_triangles) == 0, "World-space cut ignores the mesh transform")
	node.position.x = 0.0
	core.cut_open_water(pools)
	check(node.mesh.surface_get_arrays(0)[Mesh.ARRAY_INDEX] == PackedInt32Array([3, 4, 5, 6, 7, 8]), "Restored source cannot be recut")
	print("OPEN_WATER_CUT ", JSON.stringify({"ok": failures.is_empty(), "cases": 8, "failures": failures}))
	quit(0 if failures.is_empty() else 1)
