extends SceneTree

const Replay = preload("res://scripts/python_river_replay.gd")
var failures: int = 0

func _initialize() -> void:
	call_deferred("run")

func full_projection(at: Vector3, feature: Dictionary) -> float:
	var best: float = INF
	var projected: float = 0.0
	var points: Array = feature.points_xyz
	var chainage: Array = feature.point_s_m
	var position: Vector2 = Vector2(at.x, at.z)
	for i: int in range(points.size() - 1):
		var a: Vector2 = Vector2(float(points[i][0]), float(points[i][2]))
		var b: Vector2 = Vector2(float(points[i + 1][0]), float(points[i + 1][2]))
		var segment: Vector2 = b - a
		var weight: float = clampf((position - a).dot(segment) / segment.length_squared(), 0.0, 1.0)
		var distance: float = position.distance_squared_to(a + segment * weight)
		if distance < best:
			best = distance
			projected = lerpf(float(chainage[i]), float(chainage[i + 1]), weight)
	return projected

func run() -> void:
	var points: Array = []
	var chainage: Array = []
	for i: int in range(1001):
		points.append([sin(float(i) / 30.0) * 15.0, 1.0, float(i) * 5.0])
		chainage.append(float(i) * 5.0)
	var feature: Dictionary = {"points_xyz": points, "point_s_m": chainage, "width_m": 50.0}
	var model: Node = Replay.new()
	model.begin_live({"cells": [{"id": "cell", "start_s_m": 0.0, "end_s_m": 5000.0, "position_xyz": [0, 1, 2500]}], "river_features": {"test": feature}})
	var positions: Array[Vector3] = []
	var rng: RandomNumberGenerator = RandomNumberGenerator.new()
	rng.seed = 2213
	for i: int in range(1000):
		positions.append(model.position_at_s(rng.randf_range(0, 5000), "test") + Vector3(rng.randf_range(-5, 5), 0, 0))
	var expected: Array[float] = []
	var before: int = Time.get_ticks_usec()
	for at: Vector3 in positions:
		expected.append(full_projection(at, feature))
	var full_us: int = Time.get_ticks_usec() - before
	model.river_state_at_position(positions[0], "test", "trout")
	before = Time.get_ticks_usec()
	for i: int in range(positions.size()):
		var state: Dictionary = model.river_state_at_position(positions[i], "test", "trout")
		if absf(float(state.projected_s_m) - expected[i]) > 0.000001:
			failures += 1
	var cached_us: int = Time.get_ticks_usec() - before
	model.free()
	print("PROJECTION_VALIDATION ", "PASS" if failures == 0 else "FAIL", " samples=1000 full_ms=", float(full_us) / 1000.0, " cached_ms=", float(cached_us) / 1000.0)
	quit(0 if failures == 0 else 1)
