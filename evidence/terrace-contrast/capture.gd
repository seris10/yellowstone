extends SceneTree
var world: Node3D
var camera: Camera3D
var report := {"scope": "Native frozen-world material comparison; authored display contrast, no measured terrace-height claim", "captures": [], "inputs": {}}
var output := "res://../evidence/terrace-contrast"
func _initialize() -> void:
    call_deferred("run")
func freeze(node: Node) -> void:
    node.set_process(false)
    node.set_physics_process(false)
    if node is GPUParticles3D:
        node.speed_scale = 0.0
    for child: Node in node.get_children():
        freeze(child)
func capture(name: String) -> void:
    for frame: int in 18:
        await process_frame
    await RenderingServer.frame_post_draw
    var image := root.get_texture().get_image()
    var path := output.path_join(name + ".png")
    assert(image.save_png(path) == OK)
    report.captures.append({"id": name, "file": name+".png", "sha256": FileAccess.get_sha256(path), "position": [camera.position.x,camera.position.y,camera.position.z], "basis": [camera.basis.x,camera.basis.y,camera.basis.z], "fov": camera.fov, "projection": camera.projection, "orthogonal_size": camera.size, "image_size": [image.get_width(),image.get_height()], "draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME), "primitives": Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)})
    print("TERRACE_CAPTURE ", name)
func run() -> void:
    assert(DisplayServer.get_name() != "headless")
    create_timer(240).timeout.connect(func(): push_error("Terrace capture timed out"); quit(1))
    ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:1")
    root.size = Vector2i(1440,900)
    root.show()
    world = load("res://scenes/main.tscn").instantiate()
    root.add_child(world)
    current_scene = world
    for frame: int in 12:
        await process_frame
    freeze(world)
    for shader_name: String in ["foliage", "forest_floor_foliage", "water", "steam"]:
        var shader: Shader = load("res://shaders/%s.gdshader" % shader_name)
        shader.code = shader.code.replace("TIME", "0.0")
    world.overlay.hide()
    world.menu.hide()
    world.player.enabled = false
    for material: ShaderMaterial in world.foliage_materials:
        material.set_shader_parameter("wind_vector", Vector2.ZERO)
    var material: ShaderMaterial = world.get_node("CoreTerrain").get_mat_material()
    var revised: Shader = material.shader
    var prior := Shader.new()
    prior.code = FileAccess.get_file_as_string("res://../work/thermal_apron_before.gdshader")
    camera = Camera3D.new()
    camera.near = 0.08
    camera.far = 2900
    world.add_child(camera)
    camera.make_current()
    DirAccess.make_dir_recursive_absolute(output)
    var anchor: Dictionary = {}
    var pool: Dictionary = {}
    for row: Dictionary in world.spec.anchors:
        if row.id == "overlook": anchor = row
    for row: Dictionary in world.spec.pools:
        if row.id == "pool_1034_0": pool = row
    var views := [
        {"id": "wide", "position": Vector3(-242,52,160), "target": Vector3(-213,30,125), "fov":72.0},
        {"id": "overlook40", "position": Vector3(anchor.position[0],anchor.position[1]+1.67,anchor.position[2]), "target": Vector3(pool.center[0],pool.center[1],pool.center[2]), "fov":40.0},
        {"id": "apron", "position": Vector3(-181,28,82), "target": Vector3(-133,16.9,31), "fov":55.0},
        {"id": "overhead", "position": Vector3(pool.center[0],450,pool.center[2]), "target": Vector3(pool.center[0],pool.center[1],pool.center[2]), "fov":55.0}]
    for view: Dictionary in views:
        camera.position = view.position
        camera.projection = Camera3D.PROJECTION_ORTHOGONAL if view.id == "overhead" else Camera3D.PROJECTION_PERSPECTIVE
        camera.size = 360
        camera.fov = view.fov
        camera.look_at(view.target, Vector3.FORWARD if view.id == "overhead" else Vector3.UP)
        material.shader = prior
        await capture(view.id + "-before")
        material.shader = revised
        await capture(view.id + "-after")
    for path: String in ["res://shaders/thermal_apron.gdshader", "res://../work/thermal_apron_before.gdshader", "res://shaders/ground_surface.gdshaderinc", "res://scenes/authored_world.tscn", "res://data/display/prismatic.json", "res://assets/textures/prismatic_terrace_detail.png", "res://assets/textures/prismatic_apron_display.png", "res://assets/textures/mapped_surface_detail.png", "res://data/release.json"]:
        report.inputs[path] = FileAccess.get_sha256(path)
    report.godot = Engine.get_version_info().string
    report.renderer = RenderingServer.get_current_rendering_method()
    report.ok = report.captures.size() == 8
    FileAccess.open(output.path_join("report.json"),FileAccess.WRITE).store_string(JSON.stringify(report,"\t")+"\n")
    print("TERRACE_CAPTURE_PASS")
    quit()
