extends SceneTree
## Render each fauna GLB to PNG for orientation and material review: godot --headless --fixed-fps 60 --path . --script tools/render_fauna_preview.gd

const TARGETS: Array[String] = [
	"res://assets/imported/fauna/bison/bison.glb",
	"res://assets/imported/fauna/raven/raven.glb",
	"res://assets/imported/fauna/goose/goose_mallard_base.glb",
	"res://assets/imported/fauna/trout/trout.glb",
	"res://assets/imported/fauna/dipper/dipper_sparrow_base.glb",
	"res://assets/imported/fauna/salmon_alt/salmon.glb",
]

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	for path: String in TARGETS:
		var key: String = path.get_file().get_basename()
		var viewport: SubViewport = SubViewport.new()
		viewport.size = Vector2i(512, 512)
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		root.add_child(viewport)
		var cam: Camera3D = Camera3D.new()
		viewport.add_child(cam)
		var light: DirectionalLight3D = DirectionalLight3D.new()
		light.rotation = Vector3(-0.7, 0.5, 0.0)
		light.shadow_enabled = false
		viewport.add_child(light)
		var env: Environment = Environment.new()
		env.background_mode = Environment.BG_COLOR
		env.background_color = Color(0.55, 0.60, 0.65)
		env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		env.ambient_light_color = Color(0.95, 0.95, 0.95)
		env.ambient_light_energy = 1.0
		cam.environment = env
		var packed: PackedScene = load(path)
		if packed == null:
			print("skip ", path, " load_failed")
			viewport.free()
			continue
		var inst: Node3D = packed.instantiate() as Node3D
		if inst == null:
			print("skip ", path, " instantiate_failed")
			viewport.free()
			continue
		viewport.add_child(inst)
		var aabb: AABB = _combined_aabb(inst)
		var center: Vector3 = aabb.get_center()
		var radius: float = maxf(aabb.size.length() * 0.5, 0.001)
		var views: Array = [
			{"name": "minusZ", "pos": center + Vector3(0, radius * 0.25, -radius * 2.2)},
			{"name": "plusX", "pos": center + Vector3(radius * 2.2, radius * 0.25, 0)},
		]
		for view: Dictionary in views:
			cam.position = view["pos"]
			cam.look_at(center, Vector3.UP)
			await RenderingServer.frame_post_draw
			await RenderingServer.frame_post_draw
			var img: Image = viewport.get_texture().get_image()
			var out: String = "res://assets/imported/fauna/_preview_%s_%s.png" % [key, view["name"]]
			var err: int = img.save_png(out)
			print("saved ", out, " err=", err)
		inst.free()
		viewport.free()
	quit()

func _combined_aabb(node: Node) -> AABB:
	var total: AABB = AABB()
	var first: bool = true
	var stack: Array = [node]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is MeshInstance3D:
			var b: AABB = n.get_aabb()
			if first:
				total = b
				first = false
			else:
				total = total.merge(b)
		for c: Node in n.get_children():
			stack.append(c)
	return total
