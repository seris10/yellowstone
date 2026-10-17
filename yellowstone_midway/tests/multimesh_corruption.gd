extends "res://tools/validate_multimesh.gd"
## Serialized buffer corruption controls for each instance family.

func _initialize() -> void:
	call_deferred("run_controls")

func run_controls() -> void:
	prepare_expectations()
	var world: Node = load(SCENE_PATH).instantiate()
	var targets: Dictionary = {}
	for node: MultiMeshInstance3D in world.find_children("*", "MultiMeshInstance3D", true, false):
		var family := ""
		if str(node.name).begins_with("Steam_"):
			family = "steam"
		elif node.has_meta("canopy_part"):
			family = "canopy"
		elif node.has_meta("floor_kind"):
			family = "floor"
		elif str(node.get_meta("vegetation_kind", "")) == "pine":
			family = "tree"
		elif node.has_meta("vegetation_kind"):
			family = "ordinary"
		if not family.is_empty() and not targets.has(family):
			targets[family] = node
	var controls: Array = []
	var passed := targets.size() == 5 and failure_total == 0
	for family: String in targets:
		var node: MultiMeshInstance3D = targets[family]
		var baseline := failure_total
		validate_node(node, node.transform, family)
		var clean := failure_total == baseline
		var original := node.multimesh.buffer
		var corrupted := original.duplicate()
		corrupted[7] += 1.0
		node.multimesh.buffer = corrupted
		baseline = failure_total
		validate_node(node, node.transform, family)
		var rejected := failure_total > baseline
		passed = passed and clean and rejected
		controls.append({"family":family,"clean_passes":clean,"corrupt_rejected":rejected})
		node.multimesh.buffer = original
	world.free()
	print("MULTIMESH_CORRUPTION ", JSON.stringify({"ok":passed,"controls":controls}))
	quit(0 if passed else 1)
