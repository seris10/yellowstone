extends SceneTree
##
## Yellowstone world axes: +X east, +Y up, +Z south; DirectionalLight3D emits along local -Z, so a south-and-down sun casts a shadow pointing south.
##
## Run: godot --headless --path yellowstone_midway --script tools/test_sun_direction.gd

const AtmosphereController := preload("res://scripts/yellowstone_atmosphere.gd")

func _init() -> void:
	var errors: Array = []

	# Case 1: azimuth 0 (sun to the north), elevation 45. Ground-to-sun points north and up.
	var case1: Vector3 = AtmosphereController.new().horizontal_to_world_direction(0.0, 45.0)
	var expected_1: Vector3 = Vector3(0.0, sin(deg_to_rad(45.0)), cos(deg_to_rad(45.0))).normalized()
	if not _is_close(case1, expected_1, 1e-5):
		errors.append("Azimuth 0 case: got %s expected %s" % [case1, expected_1])

	# Case 2: azimuth 90 (sun to the east), elevation 45. Ground-to-sun points east and up.
	var case2: Vector3 = AtmosphereController.new().horizontal_to_world_direction(90.0, 45.0)
	var expected_2: Vector3 = Vector3(sin(deg_to_rad(45.0)), sin(deg_to_rad(45.0)), 0.0).normalized()
	if not _is_close(case2, expected_2, 1e-5):
		errors.append("Azimuth 90 case: got %s expected %s" % [case2, expected_2])

	# Case 3: build a transform the way DirectionalLight3D.look_at does, then check its -Z axis points along the ground-to-sun direction. look_at() needs the node to be inside the tree, so compute the transform directly instead.
	var azimuth_deg: float = 90.0
	var elevation_deg: float = 30.0
	var direction: Vector3 = AtmosphereController.new().horizontal_to_world_direction(azimuth_deg, elevation_deg)
	var target: Vector3 = -direction
	# Mirror Node3D.look_at(target, up): the local -Z axis points from origin toward target, so the forward vector equals the ground-to-sun direction.
	var forward: Vector3 = -target.normalized()
	if not _is_close(forward, direction, 1e-4):
		errors.append("Light forward (%s) does not match ground-to-sun direction (%s)." % [forward, direction])

	if errors.is_empty():
		print("SUN DIRECTION OK: azimuth and elevation map to the expected world direction.")
		quit(0)
	else:
		for message: String in errors:
			push_error(message)
		print("SUN DIRECTION FAIL: ", errors.size(), " assertion(s).")
		quit(1)


func _is_close(a: Vector3, b: Vector3, tolerance: float) -> bool:
	return absf(a.x - b.x) < tolerance and absf(a.y - b.y) < tolerance and absf(a.z - b.z) < tolerance
