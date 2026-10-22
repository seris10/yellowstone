extends Node
## Pages placement, canopy and forest-floor layers onto resident streamed leaf tiles.
signal foliage_attached(key: String, materials: Array)
signal foliage_detached(key: String, materials: Array)
signal prepared

const TileVegetation = preload("res://scripts/park_runtime/tile_vegetation.gd")
const CanopySurface = preload("res://scripts/canopy_surface.gd")
const ForestFloor = preload("res://scripts/forest_floor.gd")
const Lodgepole = preload("res://scripts/lodgepole_library.gd")
const TileVisual = preload("res://scripts/park_runtime/tile_visual.gd")
const CANOPY_PATH := "res://data/lidar_canopy/unresolved_render_canopy.json"

## Ground sampler over a tile's height samples in absolute site coordinates; worker-safe.
class HeightsGround extends RefCounted:
    var descriptor: Dictionary
    var heights: PackedFloat32Array

    func _init(tile_descriptor: Dictionary, tile_heights: PackedFloat32Array) -> void:
        descriptor = tile_descriptor
        heights = tile_heights

    func sample(x: float, z: float) -> float:
        return TileVisual.sample_heights(descriptor, heights, x, z)

## Plain inputs of one leaf tile and its planned layers; run() executes on a worker thread.
class PlanJob extends RefCounted:
    var key: String
    var tile_id: int
    var descriptor: Dictionary
    var heights: PackedFloat32Array
    var records: Dictionary
    var task_id: int = -1
    var plan: Dictionary = {}
    var plan_ms: float = 0.0

    func _init(tile_key: String, tile: Node3D) -> void:
        key = tile_key
        tile_id = tile.get_instance_id()
        descriptor = tile.descriptor.duplicate(true)
        heights = tile.heights
        records = tile.vegetation_records

    func run() -> void:
        var started: int = Time.get_ticks_usec()
        plan = _plan()
        plan_ms = float(Time.get_ticks_usec() - started) / 1000.0

    func _plan() -> Dictionary:
        if not str(records.get("error", "")).is_empty():
            return {"error": "Vegetation page read failed for %s: %s" % [key, str(records.error)]}
        var x0 := float(descriptor.origin_x_m)
        var z0 := float(descriptor.origin_z_m)
        var size := float(descriptor.size_m)
        var x1 := x0 + size
        var z1 := z0 + size
        var owned: Array = []
        var hosts: Array = []
        for record: Dictionary in records.get("vegetation", []):
            if str(record.get("kind", "")) == "pine":
                hosts.append(record)
            var p: Array = record.position
            if p[0] >= x0 and p[0] < x1 and p[2] >= z0 and p[2] < z1:
                owned.append(record)
        var floor_owned: Array = []
        for record: Dictionary in records.get("forest_floor", []):
            var p: Array = record.position
            if p[0] >= x0 and p[0] < x1 and p[2] >= z0 and p[2] < z1:
                floor_owned.append(record)
        # Canopy supports attach to tile boles plus the halo pages around the tile.
        return {"trees": TileVegetation.plan_tile(owned, descriptor) if not owned.is_empty() else {},
            "canopy": CanopySurface.plan_window(CANOPY_PATH, Rect2(x0, z0, size, size), hosts, HeightsGround.new(descriptor, heights)),
            "floor": ForestFloor.plan_window(floor_owned, descriptor)}

@export var max_builds_per_frame: int = 1
@export var max_plans_in_flight: int = 2
var _streamer: Node3D
var _features: Dictionary = {}
var _tile_materials: Dictionary = {}
var _queue: Array[String] = []
var _jobs: Dictionary = {}
var _orphans: Array[PlanJob] = []
var _totals: Dictionary = {"tiles": 0, "trees": 0, "canopy_cells": 0, "floor_records": 0, "build_ms_max": 0.0, "build_ms_total": 0.0,
    "trees_ms_total": 0.0, "canopy_ms_total": 0.0, "floor_ms_total": 0.0, "plan_ms_max": 0.0, "plan_ms_total": 0.0,
    "prepare_ms": -1.0, "prepare_step_ms_max": 0.0}
# Shared asset preparation; the static asset caches belong to these tasks until preparation settles.
var _prepared: bool = false
var _preparation_error: String = ""
var _prepare_started: int = 0
var _forms: Array[String] = []
var _image_task: int = -1
var _images: Dictionary = {}
var _canopy_task: int = -1
var _canopy_data: Dictionary = {}
var _canopy_installed: bool = false
var _ground_ready: bool = false

func configure(streamer: Node3D) -> bool:
    _streamer = streamer
    _features = streamer.feature_source()
    if _features.is_empty():
        # Catalogs without a feature index carry no vegetation pages.
        _prepared = true
        return true
    streamer.tile_committed.connect(_on_tile_committed)
    streamer.tile_retiring.connect(_on_tile_retiring)
    _begin_preparation()
    return true

func stats() -> Dictionary:
    return _totals.duplicate()

## True once shared assets are installed or their preparation has failed with an error.
func is_settled() -> bool:
    return _prepared or not _preparation_error.is_empty()

func preparation_error() -> String:
    return _preparation_error

## Worker reads, then one bounded main-thread install per frame.
func _begin_preparation() -> void:
    _prepare_started = Time.get_ticks_usec()
    # Metadata caches on the main thread before any worker reads it.
    if Lodgepole.metadata().is_empty():
        _fail_preparation("lodgepole metadata")
        return
    # Mesh scenes load on the main thread inside the install steps.
    _forms.assign(Lodgepole.ARCHETYPES)
    _canopy_task = WorkerThreadPool.add_task(_read_canopy)
    _image_task = WorkerThreadPool.add_task(_read_images.bind(_forms[0], true))

func _read_canopy() -> void:
    _canopy_data = CanopySurface.prepare_window_data(CANOPY_PATH)

## Verified cutout images of one form; unreadable files fall back to the main-thread reader.
func _read_images(form: String, include_needles: bool) -> void:
    var images: Dictionary = {}
    for filename: String in Lodgepole.metadata().get("cutout_mips", {}):
        if filename.begins_with(form + "_") or (include_needles and filename.begins_with("needle_")):
            var image: Image = Lodgepole.read_cutout_image(filename)
            if image != null:
                images[filename] = image
    _images = images

func _advance_preparation() -> void:
    if not _preparation_error.is_empty():
        return
    var started: int = Time.get_ticks_usec()
    if not _forms.is_empty() and WorkerThreadPool.is_task_completed(_image_task):
        WorkerThreadPool.wait_for_task_completion(_image_task)
        _image_task = -1
        var form: String = _forms.pop_front()
        Lodgepole.stage_cutout_images(_images)
        # Floor snags copy the snag meshes before tree binding; the baked floor keeps source materials.
        var ok: bool = (form != "snag" or ForestFloor.prewarm()) and TileVegetation.prewarm_form(form)
        Lodgepole.stage_cutout_images({})
        _images = {}
        if not ok:
            _fail_preparation("tree form " + form)
            return
        if not _forms.is_empty():
            _image_task = WorkerThreadPool.add_task(_read_images.bind(_forms[0], false))
    elif not _ground_ready:
        _ground_ready = TileVegetation.prewarm_ground_cover()
        if not _ground_ready:
            _fail_preparation("ground cover")
            return
    elif not _canopy_installed and WorkerThreadPool.is_task_completed(_canopy_task):
        WorkerThreadPool.wait_for_task_completion(_canopy_task)
        _canopy_task = -1
        _canopy_installed = not CanopySurface.install_window_source(CANOPY_PATH, _canopy_data).is_empty()
        _canopy_data = {}
        CanopySurface.prewarm_supports()
        if not _canopy_installed:
            _fail_preparation("canopy source")
            return
    else:
        return
    _totals.prepare_step_ms_max = maxf(float(_totals.prepare_step_ms_max), float(Time.get_ticks_usec() - started) / 1000.0)
    if _forms.is_empty() and _ground_ready and _canopy_installed:
        _prepared = true
        _totals.prepare_ms = float(Time.get_ticks_usec() - _prepare_started) / 1000.0
        prepared.emit()

## Outstanding worker tasks finish before the pager they report to is freed.
func _exit_tree() -> void:
    for task: int in [_image_task, _canopy_task]:
        if task >= 0:
            WorkerThreadPool.wait_for_task_completion(task)
    _image_task = -1
    _canopy_task = -1
    for job: PlanJob in _jobs.values() + _orphans:
        WorkerThreadPool.wait_for_task_completion(job.task_id)
    _jobs.clear()
    _orphans.clear()

func _fail_preparation(what: String) -> void:
    _preparation_error = what
    push_error("Vegetation asset preparation failed: " + what)

## Leaf tiles waiting for their batches: queued, planning or planned.
func pending_count() -> int:
    return _queue.size() + _jobs.size()

## Only leaf tiles carry vegetation; coarser tiles keep terrain, water and routes.
func _on_tile_committed(key: String) -> void:
    var tile: Node3D = _streamer.resident.get(key)
    if tile == null or int(tile.descriptor.lod) != 0 or _queue.has(key) or _jobs.has(key):
        return
    _queue.append(key)

## Plans run on workers; installs run outside the streamer commit loop, a bounded number per frame.
func _process(_delta: float) -> void:
    if not _prepared:
        _advance_preparation()
        return
    _orphans.assign(_orphans.filter(_settle_orphan))
    while not _queue.is_empty() and _jobs.size() < max_plans_in_flight:
        var key: String = _queue.pop_front()
        var tile: Node3D = _streamer.resident.get(key)
        if tile == null:
            continue
        var job := PlanJob.new(key, tile)
        job.task_id = WorkerThreadPool.add_task(job.run)
        _jobs[key] = job
    var built: int = 0
    for key: String in _jobs.keys():
        if built >= max_builds_per_frame:
            break
        var job: PlanJob = _jobs[key]
        if not WorkerThreadPool.is_task_completed(job.task_id):
            continue
        WorkerThreadPool.wait_for_task_completion(job.task_id)
        _jobs.erase(key)
        _totals.plan_ms_max = maxf(float(_totals.plan_ms_max), job.plan_ms)
        _totals.plan_ms_total = float(_totals.plan_ms_total) + job.plan_ms
        var started: int = Time.get_ticks_usec()
        if _install(job):
            built += 1
            var build_ms: float = float(Time.get_ticks_usec() - started) / 1000.0
            _totals.build_ms_max = maxf(float(_totals.build_ms_max), build_ms)
            _totals.build_ms_total = float(_totals.build_ms_total) + build_ms

## Keep retired jobs until their task completes; a finished task is waited once and dropped.
func _settle_orphan(job: PlanJob) -> bool:
    if not WorkerThreadPool.is_task_completed(job.task_id):
        return true
    WorkerThreadPool.wait_for_task_completion(job.task_id)
    return false

## Install one planned leaf tile; false when the tile left residency during planning.
func _install(job: PlanJob) -> bool:
    var key: String = job.key
    var tile: Node3D = _streamer.resident.get(key)
    if tile == null or tile.get_instance_id() != job.tile_id:
        return false
    var plan: Dictionary = job.plan
    if plan.has("error"):
        push_error(str(plan.error))
        return true
    var started: int = Time.get_ticks_usec()
    var trees: Dictionary = plan.trees
    if trees.has("error"):
        push_error("Vegetation batch build failed for %s: %s" % [key, str(trees.error)])
        return true
    if not trees.is_empty():
        _totals.trees += int(TileVegetation.install_tile(tile, trees).trees)
    started = _phase("trees_ms_total", started)
    var canopy: Dictionary = CanopySurface.install_window(tile, CANOPY_PATH, plan.canopy)
    if not canopy.is_empty():
        _totals.canopy_cells += int(canopy.active_cells)
    started = _phase("canopy_ms_total", started)
    var floor_plan: Dictionary = plan.floor
    if floor_plan.has("error"):
        push_error("Forest-floor batch build failed for %s: %s" % [key, str(floor_plan.error)])
        return true
    if not floor_plan.is_empty():
        _totals.floor_records += int(ForestFloor.install_window(tile, floor_plan).records)
    _phase("floor_ms_total", started)
    _totals.tiles += 1
    var materials: Array = []
    _collect_foliage(tile, materials)
    _tile_materials[key] = materials
    if not materials.is_empty():
        foliage_attached.emit(key, materials)
    return true

## Add the elapsed layer time to its total and return the current tick.
func _phase(total: String, started: int) -> int:
    var now: int = Time.get_ticks_usec()
    _totals[total] = float(_totals[total]) + float(now - started) / 1000.0
    return now

func _on_tile_retiring(key: String) -> void:
    _queue.erase(key)
    if _jobs.has(key):
        _orphans.append(_jobs[key])
        _jobs.erase(key)
    var materials: Array = _tile_materials.get(key, [])
    _tile_materials.erase(key)
    if not materials.is_empty():
        foliage_detached.emit(key, materials)

## Foliage materials of the tile batches; the filter matches world.gd collect_foliage_materials.
func _collect_foliage(node: Node, into: Array) -> void:
    if node is MultiMeshInstance3D and node.multimesh != null and node.multimesh.mesh != null:
        var mesh: Mesh = node.multimesh.mesh
        for surface: int in mesh.get_surface_count():
            var mat: Material = mesh.surface_get_material(surface)
            if mat is ShaderMaterial and mat.shader != null and mat.shader.resource_path.ends_with("foliage.gdshader") and not mat in into:
                into.append(mat)
    for child: Node in node.get_children():
        _collect_foliage(child, into)
