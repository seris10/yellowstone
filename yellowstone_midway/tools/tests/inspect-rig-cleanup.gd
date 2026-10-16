extends SceneTree
func _initialize() -> void:
	call_deferred("run")
func run() -> void:
	var scene: PackedScene = load("res://assets/imported/fauna/trout/brown_trout_swim.glb")
	var fish: Array[Node] = []
	var helper: Node = load("res://scripts/wildlife_actor.gd").new()
	for i: int in range(12):
		var instance: Node = scene.instantiate()
		helper.call("_apply_look", instance, Vector3.ONE, null)
		root.add_child(instance)
		fish.append(instance)
		var player: AnimationPlayer = instance.find_child("AnimationPlayer", true, false)
		player.play("Burst_3Hz")
		player.advance(0.1)
	for instance: Node in fish:
		instance.queue_free()
	await process_frame
	helper.free()
	print("IMPORTED_RIG_CLEANUP_COMPLETED")
	quit()
