extends SceneTree
## Capture windowed river views; command and output option: authoring guide, Tool commands.

var world: Node3D
var camera: Camera3D
var output_dir := ""

func _initialize() -> void:
	call_deferred("run")

func river_point(river_id: String, index: int) -> Vector3:
	for river: Dictionary in world.spec.rivers:
		if str(river.id) == river_id:
			var p: Array = river.points[clampi(index, 0, river.points.size() - 1)]
			return Vector3(float(p[0]), float(p[1]), float(p[2]))
	return Vector3.ZERO

func shoot(label: String, position: Vector3, target: Vector3) -> void:
	camera.position = position
	camera.look_at(target)
	for frame: int in 30:
		await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	image.save_png(output_dir.path_join(label + ".png"))
	print("CAPTURE ", label, " draw_calls=", Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME), " primitives=", Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME))

func run() -> void:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			output_dir = argument.trim_prefix("--out=")
	if output_dir.is_empty():
		push_error("capture_river_views requires --out=<absolute directory>")
		quit(2)
		return
	ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:1")
	root.size = Vector2i(1440, 900)
	root.mode = Window.MODE_WINDOWED
	root.show()
	create_timer(240.0).timeout.connect(func(): push_error("River capture timed out."); quit(1))
	world = load("res://scenes/main.tscn").instantiate()
	root.add_child(world)
	current_scene = world
	for frame: int in 20:
		await process_frame
	world.set_process(false)
	world.ecosystem.set_process(false)
	world.player.enabled = false
	world.player.set_physics_process(false)
	world.player.set_process_input(false)
	world.overlay.visible = false
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	camera = Camera3D.new()
	camera.fov = 72.0
	camera.near = 0.08
	camera.far = 2900.0
	world.add_child(camera)
	camera.make_current()
	DirAccess.make_dir_recursive_absolute(output_dir)
	var junction := river_point("river_5872_0", 0)
	world.go_to_anchor(3)
	for frame: int in 5:
		await process_frame
	var start: Vector3 = world.player.global_position + Vector3(0.0, 1.7, 0.0)
	await shoot("trailhead_to_junction", start, junction + Vector3(0.0, 0.5, 0.0))
	await shoot("junction_overhead", junction + Vector3(0.0, 55.0, 1.0), junction)
	var reach := river_point("river_5872_0", 60)
	var downstream := river_point("river_5872_0", 75)
	await shoot("river_along", reach + Vector3(0.0, 4.0, 0.0), downstream)
	await shoot("river_low", reach + Vector3(-6.0, 1.7, 0.0), downstream)
	await shoot("river_across", reach + Vector3(34.0, 3.0, 8.0), reach)
	quit(0)
