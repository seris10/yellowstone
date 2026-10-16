extends SceneTree
## Visible-renderer benchmark recording frame intervals and render counters along a route.
var world: Node
var camera: Camera3D
var samples: Array[Dictionary] = []
var route: Array = []
var failures: int = 0

func _initialize() -> void:
    call_deferred("run")

func option(name: String,fallback: String) -> String:
    for argument: String in OS.get_cmdline_user_args():
        if argument.begins_with("--"+name+"="):
            return argument.substr(name.length()+3)
    return fallback

func run() -> void:
    var scene_path: String = option("scene","res://scenes/park_streaming_demo.tscn")
    var source: PackedScene = load(scene_path) as PackedScene
    if source==null:
        push_error("Benchmark scene could not load")
        quit(1)
        return
    var route_path: String = option("route","")
    if not route_path.is_empty():
        var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(route_path))
        if not parsed is Dictionary or not parsed.get("points") is Array:
            push_error("Route must be an object containing points")
            quit(1)
            return
        route = parsed.points
    else:
        route = [[-160.,65.,150.],[-110.,60.,-130.],[110.,85.,-130.],[220.,105.,50.],[-160.,65.,150.]]
    if route.size()<2:
        quit(1)
        return
    world = source.instantiate()
    root.add_child(world)
    for _warmup: int in 180:
        await process_frame
    camera = root.get_camera_3d()
    if camera==null:
        push_error("Benchmark scene has no active camera")
        quit(1)
        return
    var native_player: Variant = world.get("player")
    if native_player is Node:
        native_player.set("enabled",false)
    var count: int = int(option("frames","1800"))
    var duration: float = float(option("duration","30"))
    if count<=0 or count>18000 or duration<=0.0:
        quit(1)
        return
    var started: int = Time.get_ticks_usec()
    var previous: int = started
    for index: int in count:
        var elapsed: float = float(Time.get_ticks_usec()-started)/1000000.0
        var position_t: float = minf(0.999999,elapsed/duration)*float(route.size()-1)
        var segment: int = mini(int(position_t),route.size()-2)
        var a: Array = route[segment]
        var b: Array = route[segment+1]
        var p0 := Vector3(a[0],a[1],a[2])
        var p1 := Vector3(b[0],b[1],b[2])
        var point: Vector3 = p0.lerp(p1,position_t-segment)
        var frame: Variant = world.get("park_frame")
        if frame==null:
            frame = world.get("frame")
        var local: Vector3 = frame.local_position(float(point.x),float(point.y),float(point.z)) if frame!=null else point
        camera.global_position = local
        if p1.distance_to(p0)>0.001:
            camera.look_at(local+(p1-p0),Vector3.UP)
        await process_frame
        var now: int = Time.get_ticks_usec()
        var stream: Variant = world.get("park_terrain")
        if stream==null:
            stream = world.get("stream")
        samples.append({"frame":index,"wall_s":float(now-started)/1000000.0,"frame_ms":float(now-previous)/1000.0,
            "draw_calls":Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
            "primitives":Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME),
            "static_memory_bytes":Performance.get_monitor(Performance.MEMORY_STATIC),
            "stream":stream.stats.duplicate(true) if stream!=null else {}})
        previous = now
    var output_path: String = option("out","user://park_benchmark.json")
    var file := FileAccess.open(output_path,FileAccess.WRITE)
    if file==null:
        push_error("Cannot write benchmark output")
        quit(1)
        return
    file.store_string(JSON.stringify({"scene":scene_path,"godot":Engine.get_version_info(),
        "renderer":RenderingServer.get_current_rendering_method(),"display_server":DisplayServer.get_name(),
        "scope":"render-frame intervals and counters; no GPU timer attribution","samples":samples},"  "))
    file.close()
    print("PARK_BENCHMARK ",ProjectSettings.globalize_path(output_path))
    world.queue_free()
    await process_frame
    quit(0)
