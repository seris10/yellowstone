extends SceneTree
## Smoke exit control with a rejected verification receipt; expect exit 1.

class RejectedWorld extends "res://scripts/world.gd":
	func report_multimesh_validation() -> bool:
		print("SMOKE forced_receipt_rejection=true")
		return false

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var world: Node = load("res://scenes/main.tscn").instantiate()
	world.set_script(RejectedWorld)
	root.add_child(world)
