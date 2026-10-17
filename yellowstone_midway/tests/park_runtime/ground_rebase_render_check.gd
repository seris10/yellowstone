extends SceneTree
## Windowed ground render checks; options --baseline=<dir> --out=<dir> --scene --scene-only.
const Materials = preload("res://scripts/terrain_materials.gd")
const INCLUDE_LINE := "#include \"res://shaders/ground_surface.gdshaderinc\""
const PATCH_CENTER := Vector3(-100.0, 0.0, 100.0)
const PATCH_SIZE_M := 800.0
const REBASES: Array[Vector2] = [Vector2(512.0, -1024.0), Vector2(-2048.0, 1536.0)]
const REBASE_MEAN_LIMIT := 0.05
const REBASE_PIXEL_FRACTION_LIMIT := 0.002
const SLIDE_MEAN_FLOOR := 1.0
const BASELINE_WORST_LEVELS := 3
const BASELINE_FRACTION_LIMIT := 0.001
var failures: int = 0
var checks: int = 0
var baseline_dir: String = ""
var out_dir: String = "user://ground_rebase"
var report: Dictionary = {}

func _initialize() -> void:
    for arg: String in OS.get_cmdline_user_args():
        if arg.begins_with("--baseline="):
            baseline_dir = arg.trim_prefix("--baseline=")
        elif arg.begins_with("--out="):
            out_dir = arg.trim_prefix("--out=")
    call_deferred("run")

func check(condition: bool, message: String) -> void:
    checks += 1
    if not condition:
        failures += 1
        push_error(message)

func grab() -> Image:
    for _frame: int in 8:
        await process_frame
    await RenderingServer.frame_post_draw
    return root.get_texture().get_image()

## Mean absolute 8-bit channel delta and fraction of pixels differing by over one level.
func compare(a: Image, b: Image) -> Dictionary:
    var total: float = 0.0
    var over: int = 0
    var worst: int = 0
    var size: Vector2i = a.get_size()
    for y: int in size.y:
        for x: int in size.x:
            var ca: Color = a.get_pixel(x, y)
            var cb: Color = b.get_pixel(x, y)
            var d: int = maxi(maxi(absi(ca.r8 - cb.r8), absi(ca.g8 - cb.g8)), absi(ca.b8 - cb.b8))
            total += float(absi(ca.r8 - cb.r8) + absi(ca.g8 - cb.g8) + absi(ca.b8 - cb.b8)) / 3.0
            worst = maxi(worst, d)
            if d > 1:
                over += 1
    var pixels: float = float(size.x * size.y)
    return {"mean_levels": total / pixels, "pixel_fraction_over_one_level": float(over) / pixels, "worst_levels": worst}

func save(image: Image, name: String) -> void:
    DirAccess.make_dir_recursive_absolute(out_dir)
    image.save_png(out_dir.path_join(name + ".png"))

func baseline_shader(name: String, include_text: String) -> Shader:
    var shader := Shader.new()
    shader.code = FileAccess.get_file_as_string(baseline_dir.path_join(name)).replace(INCLUDE_LINE, include_text)
    return shader

func build_patch(parent: Node3D) -> Dictionary:
    var mat := ShaderMaterial.new()
    mat.shader = load("res://shaders/terrain.gdshader")
    check(Materials.bind_ground_material(mat), "Ground material did not bind")
    var plane := MeshInstance3D.new()
    var mesh := PlaneMesh.new()
    mesh.size = Vector2(PATCH_SIZE_M, PATCH_SIZE_M)
    plane.mesh = mesh
    plane.material_override = mat
    plane.position = PATCH_CENTER
    parent.add_child(plane)
    var sun := DirectionalLight3D.new()
    sun.rotation = Vector3(deg_to_rad(-50.0), deg_to_rad(30.0), 0.0)
    sun.shadow_enabled = false
    parent.add_child(sun)
    var environment := Environment.new()
    environment.background_mode = Environment.BG_COLOR
    environment.background_color = Color(0.4, 0.5, 0.7)
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.ambient_light_color = Color(0.5, 0.5, 0.5)
    var world_environment := WorldEnvironment.new()
    world_environment.environment = environment
    parent.add_child(world_environment)
    var camera := Camera3D.new()
    camera.fov = 60.0
    camera.far = 3000.0
    camera.position = Vector3(-100.0, 25.0, 300.0)
    parent.add_child(camera)
    camera.look_at(Vector3(-100.0, 0.0, 60.0))
    camera.make_current()
    return {"material": mat, "camera": camera}

func rebase_patch(parent: Node3D, mat: ShaderMaterial, origin: Vector2, update_material: bool) -> void:
    parent.position = Vector3(-origin.x, 0.0, -origin.y)
    if update_material:
        Materials.set_render_origin(mat, origin.x, origin.y)

func run_rebase_checks() -> void:
    var parent := Node3D.new()
    root.add_child(parent)
    var patch: Dictionary = build_patch(parent)
    var mat: ShaderMaterial = patch.material
    var reference: Image = await grab()
    save(reference, "rebase_reference")
    var rows: Array[Dictionary] = []
    for origin: Vector2 in REBASES:
        rebase_patch(parent, mat, origin, true)
        var moved: Image = await grab()
        var tracked: Dictionary = compare(reference, moved)
        rebase_patch(parent, mat, origin, false)
        Materials.set_render_origin(mat, 0.0, 0.0)
        var untracked_image: Image = await grab()
        var untracked: Dictionary = compare(reference, untracked_image)
        save(moved, "rebase_%d_%d" % [origin.x, origin.y])
        save(untracked_image, "rebase_untracked_%d_%d" % [origin.x, origin.y])
        rows.append({"origin": [origin.x, origin.y], "tracked": tracked, "untracked": untracked})
        check(float(tracked.mean_levels) <= REBASE_MEAN_LIMIT and float(tracked.pixel_fraction_over_one_level) <= REBASE_PIXEL_FRACTION_LIMIT, "Ground detail changed after rebase %s: %s" % [origin, tracked])
        check(float(untracked.mean_levels) >= SLIDE_MEAN_FLOOR, "Unrebased phases should visibly slide the ground for %s: %s" % [origin, untracked])
    Materials.set_render_origin(mat, 0.0, 0.0)
    rebase_patch(parent, mat, Vector2.ZERO, true)
    parent.queue_free()
    report["rebase"] = rows

func run_baseline_comparison() -> void:
    if baseline_dir.is_empty():
        report["baseline"] = "NOT TESTED: pass --baseline=<directory of baseline shader sources>"
        return
    var include_text: String = FileAccess.get_file_as_string(baseline_dir.path_join("ground_surface.gdshaderinc"))
    check(not include_text.is_empty(), "Baseline include is missing")
    var parent := Node3D.new()
    root.add_child(parent)
    var patch: Dictionary = build_patch(parent)
    var mat: ShaderMaterial = patch.material
    var camera: Camera3D = patch.camera
    var views: Array[Dictionary] = [
        {"id": "patch_oblique", "position": Vector3(-100.0, 25.0, 300.0), "target": Vector3(-100.0, 0.0, 60.0)},
        {"id": "patch_ground", "position": Vector3(-100.0, 1.7, 120.0), "target": Vector3(-95.0, 0.0, 100.0)},
        {"id": "patch_overhead", "position": Vector3(-100.0, 120.0, 100.1), "target": Vector3(-100.0, 0.0, 100.0)},
    ]
    var rows: Array[Dictionary] = []
    var updated: Shader = mat.shader
    var baseline: Shader = baseline_shader("terrain.gdshader", include_text)
    for view: Dictionary in views:
        camera.position = view.position
        camera.look_at(view.target)
        mat.shader = updated
        var after: Image = await grab()
        mat.shader = baseline
        var before: Image = await grab()
        save(after, "midway_%s_updated" % view.id)
        save(before, "midway_%s_baseline" % view.id)
        var result: Dictionary = compare(before, after)
        rows.append({"view": view.id, "difference": result})
        check(int(result.worst_levels) <= BASELINE_WORST_LEVELS and float(result.pixel_fraction_over_one_level) <= BASELINE_FRACTION_LIMIT, "Midway frame %s differs from the baseline shader: %s" % [view.id, result])
    parent.queue_free()
    report["baseline"] = rows

func freeze_world(world: Node3D) -> void:
    ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:1")
    for frame: int in 12:
        await process_frame
    world.set_process(false)
    world.ecosystem.set_process(false)
    world.atmosphere_controller.set_process(false)
    world.weather_snapshot_reader.set_process(false)
    world.player.enabled = false
    world.player.set_physics_process(false)
    world.player.set_process_input(false)
    world.overlay.visible = false
    for material: ShaderMaterial in world.foliage_materials:
        material.set_shader_parameter("wind_vector", Vector2.ZERO)
    if world.live_client != null:
        world.live_client.set_process(false)
    if world.data_watcher != null:
        world.data_watcher.set_process(false)

func run_scene_comparison() -> void:
    if baseline_dir.is_empty():
        report["scene"] = "NOT TESTED: pass --baseline=<directory of baseline shader sources>"
        return
    var include_text: String = FileAccess.get_file_as_string(baseline_dir.path_join("ground_surface.gdshaderinc"))
    var world: Node3D = load("res://scenes/main.tscn").instantiate()
    root.add_child(world)
    current_scene = world
    await freeze_world(world)
    Engine.time_scale = 0.0
    var camera := Camera3D.new()
    camera.fov = 72.0
    camera.near = 0.08
    camera.far = 2900.0
    world.add_child(camera)
    camera.make_current()
    var pairs: Array[Dictionary] = []
    for material: ShaderMaterial in world.terrain_materials:
        pairs.append({"material": material, "updated": material.shader, "baseline": baseline_shader("terrain.gdshader", include_text)})
    var core_material: ShaderMaterial = world.get_node("CoreTerrain").get_mat_material()
    pairs.append({"material": core_material, "updated": core_material.shader, "baseline": baseline_shader("thermal_apron.gdshader", include_text)})
    var views: Array[Dictionary] = [
        {"id": "overlook", "position": Vector3(-242.0, 52.0, 160.0), "target": Vector3(-213.0, 30.0, 125.0)},
        {"id": "ground", "position": Vector3(-300.0, world.height_field.sample(-300.0, 140.0) + 1.7, 140.0), "target": Vector3(-290.0, world.height_field.sample(-290.0, 125.0), 125.0)},
        {"id": "core_boundary", "position": Vector3(-346.0, world.height_field.sample(-346.0, 166.0) + 2.0, 166.0), "target": Vector3(-329.0, world.height_field.sample(-329.0, 155.0), 155.0)},
    ]
    var rows: Array[Dictionary] = []
    for view: Dictionary in views:
        camera.position = view.position
        camera.look_at(view.target)
        for pair: Dictionary in pairs:
            pair.material.shader = pair.updated
        var first: Image = await grab()
        var second: Image = await grab()
        for pair: Dictionary in pairs:
            pair.material.shader = pair.baseline
        var before: Image = await grab()
        save(first, "scene_%s_updated" % view.id)
        save(before, "scene_%s_baseline" % view.id)
        var drift: Dictionary = compare(first, second)
        var result: Dictionary = compare(before, first)
        rows.append({"view": view.id, "repeat_noise": drift, "difference": result})
        check(int(result.worst_levels) <= maxi(BASELINE_WORST_LEVELS, int(drift.worst_levels)) and float(result.pixel_fraction_over_one_level) <= BASELINE_FRACTION_LIMIT, "Scene frame %s differs from the baseline shaders beyond repeat noise: %s against %s" % [view.id, result, drift])
    for pair: Dictionary in pairs:
        pair.material.shader = pair.updated
    report["scene"] = rows

func run() -> void:
    if DisplayServer.get_name() == "headless":
        push_error("Render checks need a visible rendering backend.")
        quit(1)
        return
    root.size = Vector2i(1280, 720)
    root.mode = Window.MODE_WINDOWED
    root.show()
    if "--scene-only" not in OS.get_cmdline_user_args():
        await run_rebase_checks()
        await run_baseline_comparison()
    if "--scene" in OS.get_cmdline_user_args() or "--scene-only" in OS.get_cmdline_user_args():
        await run_scene_comparison()
    report["renderer"] = RenderingServer.get_current_rendering_method()
    report["godot"] = Engine.get_version_info().string
    print("GROUND_REBASE_RENDER ", JSON.stringify(report))
    print("GROUND_REBASE_RENDER %d checks; %d failures" % [checks, failures])
    quit(1 if failures > 0 else 0)
