extends SceneTree
## Native geometry closeup of authored floor assets at metric scale.

const Floor := preload("res://scripts/forest_floor.gd")
var output_path := "user://floor-detail.png"
var frames := 0

func _initialize() -> void:
	call_deferred("setup")

func setup() -> void:
	var args := OS.get_cmdline_user_args()
	for i: int in args.size():
		if args[i] == "--out" and i + 1 < args.size():
			output_path = args[i + 1]
	root.size = Vector2i(1280, 800)
	var scene := Node3D.new()
	root.add_child(scene)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("7395b5")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("c4d3dc")
	environment.environment.ambient_light_energy = 0.5
	scene.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-48, -25, 0)
	light.light_energy = 1.8
	light.shadow_enabled = true
	scene.add_child(light)
	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(18, 18)
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("68694d")
	material.roughness = 1.0
	plane.material = material
	ground.mesh = plane
	scene.add_child(ground)
	for i: int in Floor.GUILDS.size():
		add_record(scene, {"id": "plant%d" % i, "kind": "understory_card", "guild": Floor.GUILDS[i], "position": [(i - 1.5) * 1.0, 0, -0.5], "size": [1, 0.36, 1], "ground_normal": [0, 1, 0], "yaw": 0.57 * i})
	for i: int in 8:
		add_record(scene, {"id": "litter%d" % i, "kind": "litter", "position": [(i % 4 - 1.5) * 1.05, 0, (i / 4) * 0.95 + 0.4], "size": [1, 0.025, 1], "ground_normal": [0, 1, 0], "yaw": i * 1.73})
	add_record(scene, {"id": "log", "kind": "log", "position": [0, 0, -1.7], "size": [0.22, 0.22, 4.5], "yaw": PI / 2, "axis_end_positions": [[-2.25, 0.11, -1.7], [2.25, 0.11, -1.7]]})
	var camera := Camera3D.new()
	camera.position = Vector3(2.7, 1.8, 3.7)
	scene.add_child(camera)
	camera.look_at(Vector3(0, 0.1, 0))
	camera.fov = 57
	camera.current = true

func add_record(scene: Node3D, record: Dictionary) -> void:
	var assets := Floor._assets(record)
	var asset: Array = assets[0]
	var node := MeshInstance3D.new()
	node.mesh = asset[0]
	node.transform = Floor.instance_transform(record, str(asset[4]), asset[1])
	scene.add_child(node)

func _process(_delta: float) -> bool:
	frames += 1
	if frames == 30:
		capture.call_deferred()
	return false

func capture() -> void:
	await RenderingServer.frame_post_draw
	var error := root.get_texture().get_image().save_png(output_path)
	print("FLOOR_DETAIL_CAPTURE ", output_path, " error=", error)
	quit(0 if error == OK else 1)
