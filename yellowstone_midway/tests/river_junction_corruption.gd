extends "res://tools/validate_river_junctions.gd"
## Saved-reach displacement control for expected junction membership.

func _initialize() -> void:
	call_deferred("run_control")

func run_control() -> void:
	var spec: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/world.json"))
	var world: Node = load("res://scenes/authored_world.tscn").instantiate()
	var nodes: Dictionary = {}
	for river: Dictionary in spec.rivers:
		var node := world.get_node_or_null("ConnectedWater/" + str(river.id)) as MeshInstance3D
		if node != null:
			nodes[str(river.id)] = node
	var before := validate_junctions(spec.rivers, nodes)
	var clean := failures.is_empty() and not before.is_empty()
	(nodes["river_5933_0"] as MeshInstance3D).position.x += 100.0
	var after := validate_junctions(spec.rivers, nodes)
	var passed := clean and after.size() == before.size() and not failures.is_empty()
	world.free()
	print("RIVER_JUNCTION_CORRUPTION ", JSON.stringify({"ok":passed,"expected_joins":before.size(),"displaced_joins":after.size(),"detected_failures":failures}))
	quit(0 if passed else 1)
