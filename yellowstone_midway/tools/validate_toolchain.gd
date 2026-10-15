extends SceneTree

const Actor = preload("res://scripts/wildlife_actor.gd")

class RiverFixture extends Node:
	var elapsed: float = 10.0
	var paused: bool = false
	var clock_held: bool = false
	var params: Dictionary = {}
	var current_mps: float = 1.0
	var target_m: float = 4.0
	func river_state_at_position(_position: Vector3, _river: String, _actor: String) -> Dictionary:
		return {"velocity_mps": current_mps, "feeding": 1.0}
	func trout_state(_actor: String) -> Dictionary:
		return {"refuge_s_m": target_m}
	func position_at_s(chainage: float, _river: String) -> Vector3:
		return Vector3(0.0, 0.0, chainage)

func _initialize() -> void:
	var cases: Array = [[4.0, 0.4, 1.0, 0.6], [-4.0, 0.4, 1.0, 1.4],
		[0.0, 0.4, 1.0, 1.0], [100.0, 1.0, 1.0, 0.0], [4.0, 0.4, 0.0, 0.4], [2.0, 0.4, 1.0, 0.8]]
	for values: Array in cases:
		var ecosystem := RiverFixture.new()
		ecosystem.target_m = float(values[0])
		ecosystem.current_mps = float(values[2])
		var actor := Actor.new()
		actor._ecosystem = ecosystem
		actor.record = {"river_id": "fixture", "approx_dimensions_m": {"body_length": 1.0},
			"sustained_swim_bl_s": float(values[1])}
		actor.chainage_m = 0.0
		actor._last_sim_time = 0.0
		actor._update_fish(0.1)
		if not is_equal_approx(float(actor.get_meta("water_relative_speed_mps")), float(values[3])):
			push_error("Fish ground displacement and water-relative speed disagree")
			quit(1)
			return
		var before: Vector3 = actor._world_position
		ecosystem.paused = true
		actor._process(1.0)
		if not actor._world_position.is_equal_approx(before):
			quit(1)
			return
		actor.free()
		ecosystem.free()
	print("TOOLCHAIN_FISH PASS signed upstream downstream holding drift zero-flow arrival pause")
	quit(0)
