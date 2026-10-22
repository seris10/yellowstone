extends SceneTree
## Visible-renderer boot workload timing with a post-boot frame series.

var world: Node

func _initialize() -> void:
    call_deferred("run")

func option(name: String, fallback: String) -> String:
    for argument: String in OS.get_cmdline_user_args():
        if argument.begins_with("--" + name + "="):
            return argument.substr(name.length() + 3)
    return fallback

func run() -> void:
    DisplayServer.window_move_to_foreground()
    var scene_path: String = option("scene", "res://scenes/main.tscn")
    var t0: int = Time.get_ticks_usec()
    var source: PackedScene = load(scene_path) as PackedScene
    var t_load: int = Time.get_ticks_usec()
    if source == null:
        push_error("Boot benchmark scene could not load")
        quit(1)
        return
    world = source.instantiate()
    var t_instantiate: int = Time.get_ticks_usec()
    root.add_child(world)
    var t_ready: int = Time.get_ticks_usec()
    await process_frame
    var t_first_frame: int = Time.get_ticks_usec()
    var player: Variant = null
    var t_interactive: int = 0
    var t_collision: int = 0
    for _wait: int in 1200:
        var candidate: Variant = world.get("player")
        var stream: Variant = world.get("park_terrain")
        if candidate is CharacterBody3D:
            player = candidate
            if t_collision == 0:
                if stream == null or bool(stream.can_enter(player.global_position, 0.5)):
                    t_collision = Time.get_ticks_usec()
            if bool(player.get("enabled")):
                t_interactive = Time.get_ticks_usec()
                break
        await process_frame
    Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
    var samples: Array[Dictionary] = []
    var previous: int = Time.get_ticks_usec()
    for index: int in int(option("frames", "300")):
        await process_frame
        var now: int = Time.get_ticks_usec()
        var stream: Variant = world.get("park_terrain")
        samples.append({"frame": index, "wall_s": float(now - t0) / 1000000.0,
            "frame_ms": float(now - previous) / 1000.0,
            "cpu_ms": Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0,
            "draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
            "primitives": Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME),
            "static_memory_bytes": Performance.get_monitor(Performance.MEMORY_STATIC),
            "stream": stream.stats.duplicate(true) if stream != null else {}})
        previous = now
    var streamed: bool = bool(ProjectSettings.get_setting("yellowstone/park_streaming/enabled", false))
    var output_path: String = option("out", "user://park_boot_benchmark.json")
    var file := FileAccess.open(output_path, FileAccess.WRITE)
    if file == null:
        push_error("Cannot write boot benchmark output")
        quit(1)
        return
    file.store_string(JSON.stringify({
        "scene": scene_path,
        "mode": "streamed" if streamed else "baked",
        "catalog": str(ProjectSettings.get_setting("yellowstone/park_streaming/catalog", "")),
        "godot": Engine.get_version_info(),
        "renderer": RenderingServer.get_current_rendering_method(),
        "milestones_ms": {
            "scene_load": float(t_load - t0) / 1000.0,
            "instantiate": float(t_instantiate - t_load) / 1000.0,
            "ready_block": float(t_ready - t_instantiate) / 1000.0,
            "first_frame": float(t_first_frame - t0) / 1000.0,
            "collision_ready": float(t_collision - t0) / 1000.0 if t_collision > 0 else -1.0,
            "interactive": float(t_interactive - t0) / 1000.0 if t_interactive > 0 else -1.0,
        },
        "scope": "script-start to interactive boot timing; post-boot render-frame intervals and counters; no GPU timer attribution",
        "samples": samples}, "  "))
    file.close()
    print("PARK_BOOT_BENCHMARK ", ProjectSettings.globalize_path(output_path))
    world.queue_free()
    await process_frame
    quit(0)
