extends SceneTree
## Inspect imported fauna GLBs: combined bounding box, mesh/material inventory. godot --headless --path . --script tools/inspect_fauna_glb.gd

const TARGETS: Array[String] = [
	"res://assets/imported/fauna/bison/bison.glb",
	"res://assets/imported/fauna/raven/raven.glb",
	"res://assets/imported/fauna/goose/goose_mallard_base.glb",
	"res://assets/imported/fauna/trout/trout.glb",
	"res://assets/imported/fauna/dipper/dipper_sparrow_base.glb",
	"res://assets/imported/fauna/salmon_alt/salmon.glb",
]

func _init() -> void:
	for path: String in TARGETS:
		print("=== ", path)
		if not ResourceLoader.exists(path):
			print("  MISSING")
			continue
		var packed: PackedScene = load(path)
		if packed == null:
			print("  LOAD FAILED")
			continue
		var root: Node3D = packed.instantiate() as Node3D
		if root == null:
			print("  INSTANTIATE FAILED")
			continue
		var boxes: Array[AABB] = []
		_collect(root, boxes)
		if boxes.is_empty():
			print("  NO MESHES")
		else:
			var total: AABB = boxes[0]
			for b: AABB in boxes:
				total = total.merge(b)
			print("  AABB pos=", total.position, " size=", total.size)
		root.free()
	quit()

func _collect(node: Node, boxes: Array[AABB]) -> void:
	if node is MeshInstance3D:
		var mi: MeshInstance3D = node
		var aabb: AABB = mi.get_aabb()
		boxes.append(aabb)
		var mats: Array[String] = []
		for i: int in range(mi.mesh.get_surface_count()):
			var m: Material = mi.mesh.surface_get_material(i)
			var desc: String = "null"
			if m is StandardMaterial3D:
				var sm: StandardMaterial3D = m
				desc = "albedo=" + str(sm.albedo_color) + " tex=" + str(sm.albedo_texture != null)
			mats.append(desc)
		print("  mesh=", mi.name, " tris~", mi.mesh.get_faces().size() / 3 if mi.mesh.get_faces().size() > 0 else "n/a", " mats=", mats)
	for child: Node in node.get_children():
		_collect(child, boxes)
