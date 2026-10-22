extends SceneTree
## Walker-driven route benchmark recording frame intervals, counters and streamer state.

var world: Node
var player: CharacterBody3D
var series: Dictionary = {}
var segment_marks: Array = []
var teleport_marks: Array = []
var started: int = 0
var previous: int = 0

func _initialize() -> void:
    call_deferred("run")

func option(name: String, fallback: String) -> String:
    for argument: String in OS.get_cmdline_user_args():
        if argument.begins_with("--" + name + "="):
            return argument.substr(name.length() + 3)
    return fallback

func _wall_s() -> float:
    return float(Time.get_ticks_usec() - started) / 1000000.0

func _local(goal: Vector3) -> Vector3:
    var frame: Variant = world.get("park_frame")
    if frame != null:
        return frame.local_position(goal.x, goal.y, goal.z)
    return goal

func _open_series() -> void:
    for key: String in ["wall_s", "frame_ms", "cpu_ms", "draw_calls", "primitives",
            "static_memory_bytes", "x", "y", "z", "h_speed_mps", "holding", "segment",
            "resident_tiles", "collision_tiles", "inflight", "ready", "commit_ms",
            "plan_ms", "resident_estimate_mib", "stream_failures", "budget_pressure"]:
        series[key] = []

func _record(segment: int, pressing: bool) -> void:
    var now: int = Time.get_ticks_usec()
    var absolute: Vector3 = player.global_position
    var frame: Variant = world.get("park_frame")
    if frame != null:
        var xz: Array = frame.absolute_xz(absolute)
        absolute = Vector3(xz[0], absolute.y, xz[1])
    var velocity: Vector3 = player.get("velocity")
    var h_speed: float = Vector2(velocity.x, velocity.z).length()
    var stream: Variant = world.get("park_terrain")
    var stats: Dictionary = stream.stats if stream != null else {}
    series["wall_s"].append(float(now - started) / 1000000.0)
    series["frame_ms"].append(float(now - previous) / 1000.0)
    series["cpu_ms"].append(Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0)
    series["draw_calls"].append(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
    series["primitives"].append(Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME))
    series["static_memory_bytes"].append(Performance.get_monitor(Performance.MEMORY_STATIC))
    series["x"].append(absolute.x)
    series["y"].append(absolute.y)
    series["z"].append(absolute.z)
    series["h_speed_mps"].append(h_speed)
    series["holding"].append(pressing and h_speed < 0.05)
    series["segment"].append(segment)
    series["resident_tiles"].append(int(stats.get("resident_tiles", 0)))
    series["collision_tiles"].append(int(stats.get("collision_tiles", 0)))
    series["inflight"].append(int(stats.get("inflight", 0)))
    series["ready"].append(int(stats.get("ready", 0)))
    series["commit_ms"].append(float(stats.get("commit_ms", 0.0)))
    series["plan_ms"].append(float(stats.get("plan_ms", 0.0)))
    series["resident_estimate_mib"].append(float(stats.get("resident_estimate_mib", 0.0)))
    series["stream_failures"].append(int(stats.get("failures", 0)))
    series["budget_pressure"].append(bool(stats.get("budget_pressure", false)))
    previous = now

func _collision_ready() -> bool:
    var stream: Variant = world.get("park_terrain")
    if stream == null:
        return true
    return bool(stream.can_enter(player.global_position, 0.5))

func _stream_idle() -> bool:
    var stream: Variant = world.get("park_terrain")
    if stream == null:
        return true
    var stats: Dictionary = stream.stats
    return int(stats.get("inflight", 0)) == 0 and int(stats.get("ready", 0)) == 0

func _teleport_to(goal: Vector3, look_at_point: Vector3) -> void:
    var stream: Variant = world.get("park_terrain")
    if stream != null and player.get("coordinate_frame") != null:
        player.place_at_absolute(goal, look_at_point)
    else:
        player.place_at(goal, look_at_point)

func run() -> void:
    var scene_path: String = option("scene", "res://scenes/main.tscn")
    var source: PackedScene = load(scene_path) as PackedScene
    if source == null:
        push_error("Walker benchmark scene could not load")
        quit(1)
        return
    var route_path: String = option("route", "res://tests/park_runtime/fixtures/midway_anchor_route.json")
    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(route_path))
    if not parsed is Dictionary or not parsed.get("walker_points") is Array:
        push_error("Route must provide walker_points")
        quit(1)
        return
    var waypoints: Array = parsed.walker_points
    DisplayServer.window_move_to_foreground()
    world = source.instantiate()
    root.add_child(world)
    started = Time.get_ticks_usec()
    previous = started
    var waited: int = 0
    while waited < 7200:
        await process_frame
        waited += 1
        var candidate: Variant = world.get("player")
        if candidate is CharacterBody3D:
            player = candidate
            var stream: Variant = world.get("park_terrain")
            if stream == null or bool(stream.can_enter(player.global_position, 0.5)):
                break
    if player == null:
        push_error("Walker did not reach prepared collision")
        quit(1)
        return
    Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
    player.set("enabled", true)
    player.set("fly_mode", false)
    var camera: Camera3D = player.get("camera")
    if camera != null:
        camera.rotation.x = 0.0
    for _settle: int in 120:
        await process_frame
    if "--matrix" in OS.get_cmdline_user_args():
        var failed: int = await run_matrix(waypoints)
        quit(1 if failed > 0 else 0)
        return
    _open_series()
    var escape_angles: Array[float] = [0.9, -0.9, 1.6, -1.6, 2.3, -2.3, 3.0]
    for index: int in range(1, waypoints.size()):
        var target: Array = waypoints[index]
        var goal := Vector3(float(target[0]), float(target[1]), float(target[2]))
        var mark: Dictionary = {"segment": index, "goal": target, "start_wall_s": _wall_s(), "stuck": false, "avoid_events": 0}
        var flat: Vector2 = Vector2.ZERO
        var local_goal: Vector3 = _local(goal)
        var start_flat: float = Vector2(local_goal.x - player.global_position.x, local_goal.z - player.global_position.z).length()
        var frames_left: int = int(start_flat / 1.2 * 60.0) + 3600
        var stall_left: int = 1800
        var stall_best: float = start_flat
        var prog_left: int = 45
        var prog_anchor: Vector3 = player.global_position
        var blocked_run: int = 0
        var avoid_angle: float = 0.0
        Input.action_press("move_forward")
        while frames_left > 0:
            local_goal = _local(goal)
            flat = Vector2(local_goal.x - player.global_position.x, local_goal.z - player.global_position.z)
            if flat.length() < 2.5:
                break
            var dir := Vector3(flat.x, 0.0, flat.y).normalized()
            if avoid_angle != 0.0:
                dir = dir.rotated(Vector3.UP, avoid_angle)
            player.look_at(player.global_position + dir, Vector3.UP)
            await process_frame
            _record(index, true)
            frames_left -= 1
            stall_left -= 1
            prog_left -= 1
            if stall_left <= 0:
                if flat.length() > stall_best - 1.0:
                    frames_left = 0
                else:
                    stall_best = flat.length()
                    stall_left = 1800
            if prog_left <= 0:
                var moved: float = Vector2(player.global_position.x - prog_anchor.x, player.global_position.z - prog_anchor.z).length()
                if moved < 0.15:
                    blocked_run += 1
                    if blocked_run > escape_angles.size() * 3:
                        frames_left = 0
                    else:
                        avoid_angle = escape_angles[(blocked_run - 1) % escape_angles.size()]
                        mark["avoid_events"] = blocked_run
                else:
                    blocked_run = 0
                    avoid_angle = 0.0
                prog_anchor = player.global_position
                prog_left = 45
        Input.action_release("move_forward")
        mark["end_wall_s"] = _wall_s()
        mark["remaining_m"] = flat.length()
        if flat.length() >= 2.5:
            mark["stuck"] = true
            var ahead: Vector3 = goal + Vector3(goal.x - player.global_position.x, 0.0, goal.z - player.global_position.z)
            _teleport_to(goal, ahead)
            for _settle_after: int in 60:
                await process_frame
                _record(index, false)
        segment_marks.append(mark)
    var anchor_count: int = waypoints.size() - 1
    for index: int in anchor_count:
        var target: Array = waypoints[index]
        var look: Array = waypoints[(index + 1) % anchor_count]
        var goal := Vector3(float(target[0]), float(target[1]), float(target[2]))
        var look_at_point := Vector3(float(look[0]), float(look[1]), float(look[2]))
        var mark: Dictionary = {"anchor": target, "start_wall_s": _wall_s()}
        _teleport_to(goal, look_at_point)
        var collision_frame: int = -1
        var idle_frame: int = -1
        for f: int in 900:
            await process_frame
            _record(100 + index, false)
            if collision_frame < 0 and _collision_ready():
                collision_frame = f
            if idle_frame < 0 and _stream_idle():
                idle_frame = f
        mark["end_wall_s"] = _wall_s()
        mark["frames_to_collision"] = collision_frame
        mark["frames_to_stream_idle"] = idle_frame
        teleport_marks.append(mark)
    var streamed: bool = bool(ProjectSettings.get_setting("yellowstone/park_streaming/enabled", false))
    var output_path: String = option("out", "user://park_walker_benchmark.json")
    var file := FileAccess.open(output_path, FileAccess.WRITE)
    if file == null:
        push_error("Cannot write walker benchmark output")
        quit(1)
        return
    file.store_string(JSON.stringify({
        "scene": scene_path,
        "route": route_path,
        "mode": "streamed" if streamed else "baked",
        "catalog": str(ProjectSettings.get_setting("yellowstone/park_streaming/catalog", "")),
        "godot": Engine.get_version_info(),
        "renderer": RenderingServer.get_current_rendering_method(),
        "walk_speed_mps": float(player.get("walk_speed")),
        "scope": "walker-driven route with swept physics; render-frame intervals and counters; no GPU timer attribution",
        "segments": segment_marks,
        "teleports": teleport_marks,
        "series": series}, "  "))
    file.close()
    print("PARK_WALKER_BENCHMARK ", ProjectSettings.globalize_path(output_path))
    world.queue_free()
    await process_frame
    quit(0)

## Matrix cases in the integrated scene; returns the number of failed cases.
func run_matrix(waypoints: Array) -> int:
    var failed: int = 0
    world.resume()
    var stream: Variant = world.get("park_terrain")
    if stream != null:
        failed += await matrix_collision_delay(stream)
    failed += await matrix_overlook_exit(waypoints)
    print("MATRIX_WALKER mode=", "streamed" if stream != null else "baked", " failed=", failed)
    return failed

## Collision delay and teleport: movement holds at each anchor until collision and features commit.
func matrix_collision_delay(stream: Variant) -> int:
    var failed: int = 0
    var anchors: Array = world.spec.anchors
    for step: int in anchors.size():
        var index: int = (step + 1) % anchors.size()
        world.go_to_anchor(index)
        var held_at_teleport: bool = not bool(player.get("enabled")) and bool(world.get("_park_boot_hold"))
        var placed: Vector3 = world.player_site_position()
        var drift: float = 0.0
        var held_frames: int = 0
        var camera_current: bool = true
        var ready_at_release: bool = false
        for _tick: int in 3600:
            await physics_frame
            if bool(player.get("enabled")):
                ready_at_release = _collision_ready()
                break
            held_frames += 1
            drift = maxf(drift, world.player_site_position().distance_to(placed))
            var camera: Camera3D = player.get("camera")
            camera_current = camera_current and camera != null and camera.current
        var features_committed: bool = false
        for key: String in stream.resident:
            var d: Dictionary = stream.resident[key].descriptor
            if int(d.lod) == 0 and placed.x >= float(d.origin_x_m) and placed.x < float(d.origin_x_m) + float(d.size_m) \
                    and placed.z >= float(d.origin_z_m) and placed.z < float(d.origin_z_m) + float(d.size_m):
                features_committed = not stream.tile_group(key).is_empty()
        var passed: bool = held_at_teleport and ready_at_release and drift < 0.01 and camera_current and features_committed
        print("MATRIX collision_delay anchor=", anchors[index].id, " held=", held_at_teleport, " held_frames=", held_frames,
            " drift_m=", drift, " camera_current=", camera_current, " collision_at_release=", ready_at_release,
            " features=", features_committed, " pass=", passed)
        if not passed:
            failed += 1
        for _settle: int in 60:
            await physics_frame
    return failed

## Overlook deck exit: walking toward the boardwalk from the overlook stops at the deck rails.
func matrix_overlook_exit(waypoints: Array) -> int:
    world.go_to_anchor(0)
    for _tick: int in 3600:
        await physics_frame
        if _collision_ready() and bool(player.get("enabled")):
            break
    player.set("enabled", true)
    player.set("fly_mode", false)
    for _settle: int in 120:
        await physics_frame
    var anchor: Vector3 = world.player_site_position()
    var target: Array = waypoints[1]
    var goal := Vector3(float(target[0]), float(target[1]), float(target[2]))
    var first_wall: String = ""
    var wall_distance: float = -1.0
    Input.action_press("move_forward")
    for _tick: int in 900:
        var local_goal: Vector3 = _local(goal)
        var flat := Vector2(local_goal.x - player.global_position.x, local_goal.z - player.global_position.z)
        player.look_at(player.global_position + Vector3(flat.x, 0.0, flat.y).normalized(), Vector3.UP)
        await physics_frame
        for i: int in player.get_slide_collision_count():
            var contact := player.get_slide_collision(i)
            if absf(contact.get_normal().y) < 0.7 and first_wall == "":
                var node := contact.get_collider() as Node
                first_wall = str(node.get_path()) if node != null else "unknown"
                var here: Vector3 = world.player_site_position()
                wall_distance = Vector2(here.x - anchor.x, here.z - anchor.z).length()
        if first_wall != "":
            break
    Input.action_release("move_forward")
    var passed: bool = first_wall.contains("OverlookDeck") and wall_distance >= 0.0 and wall_distance < 5.0
    print("MATRIX overlook_exit start=", anchor, " first_wall=", first_wall, " distance_m=", wall_distance, " pass=", passed)
    return 0 if passed else 1
