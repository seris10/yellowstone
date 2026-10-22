extends SceneTree
## Headless checks for the park runtime modules; run with Godot 4.5.1.
const Frame = preload("res://scripts/park_runtime/world_frame.gd")
const Job = preload("res://scripts/park_runtime/terrain_job.gd")
const Planner = preload("res://scripts/park_runtime/demand_planner.gd")
const Tile = preload("res://scripts/park_runtime/tile_visual.gd")
const Streamer = preload("res://scripts/park_runtime/terrain_streamer.gd")
const Batch = preload("res://scripts/park_runtime/vegetation_batch.gd")
const Fields = preload("res://scripts/park_runtime/field_buffer.gd")
const Client = preload("res://scripts/park_runtime/park_client.gd")
const Monitor = preload("res://scripts/park_runtime/runtime_monitor.gd")
const DEMO_DIR := "res://data/park_demo"
const CORRUPT_DIR := "user://park_runtime_corrupt_child"
var failures: int = 0
var checks: int = 0
var stream_errors: Dictionary = {}

## Resident-tile stand-in for planner checks; the ground variant carries a ridge with a 80 m gap.
class FakeTile extends RefCounted:
    var descriptor: Dictionary
    var ridge: bool

    func _init(tile_descriptor: Dictionary, carries_ridge: bool) -> void:
        descriptor = tile_descriptor
        ridge = carries_ridge

    func sample_height(x: float, z: float) -> float:
        if not ridge or absf(z) > 30.0 or absf(x) < 40.0:
            return 0.0
        return 150.0

func _initialize() -> void:
    call_deferred("run")

func check(condition: bool,message: String) -> void:
    checks += 1
    if not condition:
        failures += 1
        push_error(message)

func run() -> void:
    var world := Node3D.new()
    root.add_child(world)
    var frame = Frame.new()
    var observer := Camera3D.new()
    world.add_child(observer)
    observer.make_current()
    observer.position = Vector3(1536.25,50,-1024.5)
    frame.register_root(observer)
    var before: Array[float] = frame.absolute_xz(observer.position)
    check(frame.maybe_rebase(observer),"expected origin rebase")
    var after: Array[float] = frame.absolute_xz(observer.position)
    check(absf(before[0]-after[0])<0.00001 and absf(before[1]-after[1])<0.00001,"absolute coordinates changed after rebase")
    frame.origin_x_m = 0.0
    frame.origin_z_m = 0.0
    observer.position = Vector3(0,20,0)
    observer.rotation = Vector3.ZERO
    await process_frame
    var planner = Planner.new()
    planner.plan([],{},frame,observer,Vector3.ZERO)
    var facing := {"key":"test:0:0:0","origin_x_m":-5.,"origin_z_m":-50.,"size_m":10.,"min_y_m":15.,"max_y_m":25.,"lod":0,"error_m":0.}
    check(planner._in_frustum(facing),"frustum plane orientation rejects forward tile")
    facing.origin_z_m = 40.
    check(not planner._in_frustum(facing),"frustum plane orientation accepts behind-camera tile")
    var catalog_path := "res://data/park_demo/catalog.json"
    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(catalog_path))
    check(parsed is Dictionary,"run tools/prepare_demo.py before Godot tests")
    if parsed is Dictionary:
        var d: Dictionary = parsed.roots[0]
        var job = Job.new()
        job.configure(d,catalog_path.get_base_dir(),str(parsed.dataset_revision))
        job.task_id = WorkerThreadPool.add_task(job.run)
        var deadline: int = Time.get_ticks_msec()+10000
        while not WorkerThreadPool.is_task_completed(job.task_id) and Time.get_ticks_msec()<deadline:
            await process_frame
        if not WorkerThreadPool.is_task_completed(job.task_id):
            job.cancel()
        WorkerThreadPool.wait_for_task_completion(job.task_id)
        check(not job.result.is_empty() and not job.result.has("error"),"tile job failed")
        if not job.result.is_empty() and not job.result.has("error"):
            var data: Dictionary = job.result
            var vertices: PackedVector3Array = data.arrays[Mesh.ARRAY_VERTEX]
            var indices: PackedInt32Array = data.arrays[Mesh.ARRAY_INDEX]
            check(vertices.size()>(int(d.mesh_cells)+1)*(int(d.mesh_cells)+1),"skirts missing")
            check((vertices[indices[1]]-vertices[indices[0]]).cross(vertices[indices[2]]-vertices[indices[0]]).y<0.,"wrong terrain winding")
            var tile = Tile.new()
            tile.install(data,null,frame)
            world.add_child(tile)
            check(is_finite(tile.sample_height(float(d.origin_x_m),float(d.origin_z_m))),"height sample invalid")
        var cancelled = Job.new()
        cancelled.configure(d,catalog_path.get_base_dir(),str(parsed.dataset_revision))
        cancelled.cancel()
        cancelled.run()
        check(cancelled.result.is_empty(),"cancelled work produced a result")
    check_ridge_gap(observer, frame)
    await check_corrupt_child(world)
    print("PARK_GODOT_TESTS checks=",checks," failures=",failures)
    world.queue_free()
    await process_frame
    quit(1 if failures else 0)

## Matrix: a ridge lowers the priority of hidden tiles; a tile seen through the gap keeps full weight.
func check_ridge_gap(observer: Camera3D, frame: RefCounted) -> void:
    observer.position = Vector3(0.0, 20.0, 600.0)
    observer.rotation = Vector3.ZERO
    var ground := {"key":"ridge:0:0:0","origin_x_m":-2048.0,"origin_z_m":-2048.0,"size_m":4096.0,"min_y_m":0.0,"max_y_m":150.0,"lod":0,"error_m":0.0}
    var gap := {"key":"gap:0:0:0","origin_x_m":-16.0,"origin_z_m":-616.0,"size_m":32.0,"min_y_m":0.0,"max_y_m":1.0,"lod":0,"error_m":2.0}
    var hidden := {"key":"hidden:0:0:0","origin_x_m":-416.0,"origin_z_m":-616.0,"size_m":32.0,"min_y_m":0.0,"max_y_m":1.0,"lod":0,"error_m":2.0}
    var resident := {"ridge:0:0:0": FakeTile.new(ground, true), "gap:0:0:0": FakeTile.new(gap, false), "hidden:0:0:0": FakeTile.new(hidden, false)}
    var planner = Planner.new()
    var demand: Dictionary = planner.plan([ground, gap, hidden], resident, frame, observer, Vector3.ZERO)
    var gap_weight: float = planner._occlusion_weight(gap)
    var hidden_weight: float = planner._occlusion_weight(hidden)
    check(is_equal_approx(gap_weight, 1.0), "the tile behind the ridge gap lost visibility weight")
    check(hidden_weight < 1.0, "the ridge did not lower the hidden tile's weight")
    check(demand.requests.has("hidden:0:0:0") and demand.leaves.has("hidden:0:0:0"), "the hidden tile was deleted from demand or cover")
    check(demand.leaves.has("ridge:0:0:0") and demand.leaves.has("gap:0:0:0"), "the ridge skyline or the gap lost cover")
    check(float(demand.requests["gap:0:0:0"].priority) > float(demand.requests["hidden:0:0:0"].priority), "the gap tile does not outrank the hidden tile")
    print("MATRIX ridge_gap gap_weight=", gap_weight, " hidden_weight=", hidden_weight)

func copy_tree(from: String, to: String) -> void:
    DirAccess.make_dir_recursive_absolute(to)
    var dir := DirAccess.open(from)
    for name: String in dir.get_files():
        DirAccess.copy_absolute(from.path_join(name), to.path_join(name))
    for name: String in dir.get_directories():
        copy_tree(from.path_join(name), to.path_join(name))

func remove_tree(path: String) -> void:
    var dir := DirAccess.open(path)
    if dir == null:
        return
    for name: String in dir.get_files():
        DirAccess.remove_absolute(path.path_join(name))
    for name: String in dir.get_directories():
        remove_tree(path.path_join(name))
    DirAccess.remove_absolute(path)

func _on_stream_error(key: String, message: String) -> void:
    stream_errors[key] = message

## Matrix: a corrupt child page errors, the parent keeps the cover, and repair plus retry recovers.
func check_corrupt_child(world: Node3D) -> void:
    remove_tree(CORRUPT_DIR)
    copy_tree(DEMO_DIR, CORRUPT_DIR)
    var child_path := CORRUPT_DIR.path_join("synthetic/2/0_0.f32")
    var original: PackedByteArray = FileAccess.get_file_as_bytes(child_path)
    check(original.size() > 0, "demo child height page missing from the copy")
    var damaged := original.duplicate()
    damaged[0] = damaged[0] ^ 0xff
    var writer := FileAccess.open(child_path, FileAccess.WRITE)
    writer.store_buffer(damaged)
    writer.close()
    var frame = Frame.new()
    var observer := Camera3D.new()
    observer.far = 10000.0
    world.add_child(observer)
    observer.make_current()
    frame.register_root(observer)
    observer.position = Vector3(-256.0, 60.0, -256.0)
    observer.rotation = Vector3(-PI * 0.5, 0.0, 0.0)
    var stream = Streamer.new()
    world.add_child(stream)
    stream.stream_error.connect(_on_stream_error)
    check(stream.configure(CORRUPT_DIR.path_join("catalog.json"), frame, observer), "corrupt-child copy rejected at configure")
    var parent_cover: bool = false
    for _tick: int in 900:
        await process_frame
        if stream_errors.has("synthetic:2:0:0") and stream.resident.has("synthetic:3:0:0"):
            parent_cover = stream.resident["synthetic:3:0:0"].visible
            break
    check(stream_errors.has("synthetic:2:0:0"), "the corrupt child page raised no stream error")
    check(str(stream_errors.get("synthetic:2:0:0", "")).contains("checksum"), "the corrupt child error is not a checksum failure")
    check(parent_cover and not stream.resident.has("synthetic:2:0:0"), "the parent did not keep the cover over the failed child")
    writer = FileAccess.open(child_path, FileAccess.WRITE)
    writer.store_buffer(original)
    writer.close()
    stream.retry_failed()
    var recovered: bool = false
    for _tick: int in 900:
        await process_frame
        if stream.resident.has("synthetic:2:0:0") and not stream.resident["synthetic:3:0:0"].visible:
            recovered = true
            break
    check(recovered, "the repaired child did not replace the parent after retry")
    print("MATRIX corrupt_child error=", stream_errors.get("synthetic:2:0:0", ""), " parent_cover=", parent_cover, " recovered=", recovered)
    stream.queue_free()
    observer.queue_free()
    await process_frame
    remove_tree(CORRUPT_DIR)
