extends SceneTree
## Solar bearings and meteorological wind in east-up-south world axes.

const Controller = preload("res://scripts/yellowstone_atmosphere.gd")


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var errors: Array[String] = []
	var world := Node3D.new()
	root.add_child(world)
	var sun := DirectionalLight3D.new()
	world.add_child(sun)
	var controller = Controller.new()
	world.add_child(controller)
	controller._sun = sun
	var horizontal: Array[Vector3] = [Vector3.FORWARD, Vector3.RIGHT, Vector3.BACK, Vector3.LEFT]
	for i: int in range(4):
		var bearing: float = float(i) * 90.0
		var expected: Vector3 = (horizontal[i] + Vector3.UP).normalized()
		var actual: Vector3 = controller.horizontal_to_world_direction(bearing, 45.0)
		if actual.distance_to(expected) > 1e-6:
			errors.append("Compass bearing %s differs from fixed cardinal vector" % bearing)
		controller._solar_azimuth_deg = bearing
		controller._solar_elevation_deg = 45.0
		controller._apply_solar_position()
		if sun.global_basis.z.distance_to(expected) > 1e-6:
			errors.append("Directional light ground-to-sun axis differs at bearing %s" % bearing)
		if (-sun.global_basis.z).dot(horizontal[i]) >= 0.0:
			errors.append("Light rays do not travel away from the sun at bearing %s" % bearing)
		if controller._meteorological_wind_toward(bearing).distance_to(-horizontal[i]) > 1e-6:
			errors.append("Meteorological wind points toward its source at bearing %s" % bearing)
	world.queue_free()
	print("SUN DIRECTION: 16 cardinal/light-basis/wind assertions; failures=", errors)
	quit(0 if errors.is_empty() else 1)
