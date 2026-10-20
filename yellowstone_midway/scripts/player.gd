class_name MidwayWalker
extends CharacterBody3D
## Distances in meters, velocities in meters/second.

# Reference pace from NPS boardwalk signage, 3 mph brisk walk.
@export_range(0.5, 10.0) var walk_speed := 3.0
@export_range(0.5, 10.0) var brisk_speed := 6.5
@export_range(0.0, 1.5) var step_height := 0.55
# Jump initial velocity in m/s; a 0.72 m hop at g=9.81 m/s2.
@export_range(0.0, 10.0) var jump_speed := 3.8
@export_range(0.0005, 0.01) var mouse_sensitivity := 0.0019
var camera: Camera3D
var enabled := false
var fly_mode := false
var look_invert_y := false
var spawn := Vector3.ZERO
var pitch := 0.0
# Project default sensitivity; the player's preference multiplies it.
var _base_mouse_sensitivity := 0.0

func _ready() -> void:
	floor_snap_length = 0.55
	floor_max_angle = deg_to_rad(48.0)
	safe_margin = 0.035
	var shape := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.29
	capsule.height = 1.72
	shape.shape = capsule
	shape.position.y = 0.88
	add_child(shape)
	camera = Camera3D.new()
	camera.name = "Eyes"
	camera.position.y = 1.67
	camera.fov = 72.0
	camera.near = 0.08
	camera.far = 6500.0
	add_child(camera)
	camera.make_current()

func _unhandled_input(event: InputEvent) -> void:
	if enabled and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and event is InputEventMouseMotion:
		rotate_y(-event.relative.x * mouse_sensitivity)
		var vertical: float = event.relative.y * mouse_sensitivity * (-1.0 if look_invert_y else 1.0)
		pitch = clampf(pitch - vertical, -1.48, 1.48)
		camera.rotation.x = pitch

func _try_step_up(dir: Vector3) -> void:
	# Probe head height ahead, then down.
	var space := get_world_3d().direct_space_state
	var ahead: Vector3 = global_position + dir * 0.45
	var query := PhysicsRayQueryParameters3D.create(
		ahead + Vector3.UP * (step_height + 0.9), ahead + Vector3.DOWN * 1.6)
	query.exclude = [self]
	var hit: Dictionary = space.intersect_ray(query)
	if hit.is_empty():
		return
	var rise: float = float(hit.position.y) - global_position.y
	if rise > 0.04 and rise <= step_height:
		global_position.y = float(hit.position.y) + 0.02

func _physics_process(delta: float) -> void:
	if not enabled:
		return
	var raw: Vector2 = Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var look := Vector2(Input.get_joy_axis(0, JOY_AXIS_RIGHT_X), Input.get_joy_axis(0, JOY_AXIS_RIGHT_Y))
	if look.length() > 0.18:
		rotate_y(-look.x * delta * 1.65)
		var vertical: float = look.y * delta * 1.4 * (-1.0 if look_invert_y else 1.0)
		pitch = clampf(pitch - vertical, -1.48, 1.48)
		camera.rotation.x = pitch
	var direction := global_basis * Vector3(raw.x, 0.0, raw.y)
	var speed := brisk_speed if Input.is_action_pressed("brisk_walk") else walk_speed
	if fly_mode:
		direction = camera.global_basis * Vector3(raw.x, 0.0, raw.y)
		direction.y += float(Input.is_action_pressed("jump")) - float(Input.is_action_pressed("fly_down"))
		velocity = direction.limit_length() * (35.0 if speed == brisk_speed else 12.0)
		global_position += velocity * delta
	else:
		velocity.x = move_toward(velocity.x, direction.x * speed, delta * 7.0)
		velocity.z = move_toward(velocity.z, direction.z * speed, delta * 7.0)
		if not is_on_floor():
			var gravity_mps2: float = float(ProjectSettings.get_setting("physics/3d/default_gravity", 9.81))
			velocity.y -= gravity_mps2 * delta
		elif Input.is_action_pressed("jump"):
			velocity.y = jump_speed
		move_and_slide()
		# Step-up assist for boardwalk lips and deck edges.
		var flat := Vector3(direction.x, 0.0, direction.z)
		if is_on_floor() and is_on_wall() and flat.length_squared() > 0.04 and velocity.y <= 0.0:
			_try_step_up(flat.normalized())
	if absf(position.x) > 2038.0 or absf(position.z) > 2038.0 or position.y < -50.0:
		position = spawn
		velocity = Vector3.ZERO

## Apply the player's look and camera preferences; sensitivity scales the project default.
func set_view_preferences(sensitivity_scale: float, invert_y: bool, fov_degrees: float) -> void:
	if _base_mouse_sensitivity <= 0.0:
		_base_mouse_sensitivity = mouse_sensitivity
	mouse_sensitivity = clampf(_base_mouse_sensitivity * sensitivity_scale, 0.0005, 0.01)
	look_invert_y = invert_y
	if camera != null:
		camera.fov = clampf(fov_degrees, 60.0, 100.0)

func place_at(point: Vector3, look_at_point: Vector3) -> void:
	spawn = point
	global_position = point
	velocity = Vector3.ZERO
	look_at(Vector3(look_at_point.x, point.y, look_at_point.z), Vector3.UP)
	var direction := look_at_point - (point + Vector3.UP * 1.67)
	pitch = atan2(direction.y, Vector2(direction.x, direction.z).length())
	camera.rotation.x = pitch
	reset_physics_interpolation()
