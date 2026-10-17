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
var failures: int = 0
var checks: int = 0

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
    print("PARK_GODOT_TESTS checks=",checks," failures=",failures)
    world.queue_free()
    await process_frame
    quit(1 if failures else 0)
