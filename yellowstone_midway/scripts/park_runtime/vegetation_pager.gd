extends Node
## Pages placement, canopy and forest-floor layers onto resident streamed leaf tiles.
signal foliage_attached(key: String, materials: Array)
signal foliage_detached(key: String, materials: Array)

const TileVegetation = preload("res://scripts/park_runtime/tile_vegetation.gd")
const CanopySurface = preload("res://scripts/canopy_surface.gd")
const ForestFloor = preload("res://scripts/forest_floor.gd")
const CANOPY_PATH := "res://data/lidar_canopy/unresolved_render_canopy.json"

## Ground sampler over resident tile heights in absolute site coordinates.
class TileGround extends RefCounted:
    var tile: Node3D

    func _init(source_tile: Node3D) -> void:
        tile = source_tile

    func sample(x: float, z: float) -> float:
        return tile.sample_height(x, z)

@export var max_builds_per_frame: int = 1
var _streamer: Node3D
var _features: Dictionary = {}
var _tile_materials: Dictionary = {}
var _queue: Array[String] = []
var _totals: Dictionary = {"tiles": 0, "trees": 0, "canopy_cells": 0, "floor_records": 0, "build_ms_max": 0.0, "build_ms_total": 0.0}

func configure(streamer: Node3D) -> bool:
    _streamer = streamer
    _features = streamer.feature_source()
    if _features.is_empty():
        # Catalogs without a feature index carry no vegetation pages.
        return true
    streamer.tile_committed.connect(_on_tile_committed)
    streamer.tile_retiring.connect(_on_tile_retiring)
    return true

func stats() -> Dictionary:
    return _totals.duplicate()

## Leaf tiles waiting for their batches, in commit order.
func pending_count() -> int:
    return _queue.size()

## Only leaf tiles carry vegetation; coarser tiles keep terrain, water and routes.
func _on_tile_committed(key: String) -> void:
    var tile: Node3D = _streamer.resident.get(key)
    if tile == null or int(tile.descriptor.lod) != 0 or _queue.has(key):
        return
    _queue.append(key)

## Builds run outside the streamer commit loop, a bounded number per frame.
func _process(_delta: float) -> void:
    var built: int = 0
    while not _queue.is_empty() and built < max_builds_per_frame:
        var key: String = _queue.pop_front()
        var started: int = Time.get_ticks_usec()
        if _build(key):
            built += 1
            var build_ms: float = float(Time.get_ticks_usec() - started) / 1000.0
            _totals.build_ms_max = maxf(float(_totals.build_ms_max), build_ms)
            _totals.build_ms_total = float(_totals.build_ms_total) + build_ms

## Builds one resident leaf tile from the records its terrain job prefetched.
func _build(key: String) -> bool:
    var tile: Node3D = _streamer.resident.get(key)
    if tile == null:
        return false
    var d: Dictionary = tile.descriptor
    var x0 := float(d.origin_x_m)
    var z0 := float(d.origin_z_m)
    var size := float(d.size_m)
    var x1 := x0 + size
    var z1 := z0 + size
    var records: Dictionary = tile.vegetation_records
    if not str(records.get("error", "")).is_empty():
        push_error("Vegetation page read failed for %s: %s" % [key, str(records.error)])
        return true
    var owned: Array = []
    var hosts: Array = []
    for record: Dictionary in records.get("vegetation", []):
        if str(record.get("kind", "")) == "pine":
            hosts.append(record)
        var p: Array = record.position
        if p[0] >= x0 and p[0] < x1 and p[2] >= z0 and p[2] < z1:
            owned.append(record)
    if not owned.is_empty():
        var result: Dictionary = TileVegetation.build_tile(tile, owned, d)
        if result.is_empty():
            push_error("Vegetation batch build failed for " + key)
            return true
        _totals.trees += int(result.trees)
    # Canopy supports attach to tile boles plus the halo pages around the tile.
    var canopy: Dictionary = CanopySurface.build_window(tile, CANOPY_PATH, Rect2(x0, z0, size, size), hosts, TileGround.new(tile))
    if not canopy.is_empty():
        _totals.canopy_cells += int(canopy.active_cells)
    var floor_owned: Array = []
    for record: Dictionary in records.get("forest_floor", []):
        var p: Array = record.position
        if p[0] >= x0 and p[0] < x1 and p[2] >= z0 and p[2] < z1:
            floor_owned.append(record)
    if not floor_owned.is_empty():
        var floor_result: Dictionary = ForestFloor.build_window(tile, floor_owned, d)
        if floor_result.is_empty():
            push_error("Forest-floor batch build failed for " + key)
            return true
        _totals.floor_records += int(floor_result.records)
    _totals.tiles += 1
    var materials: Array = []
    _collect_foliage(tile, materials)
    _tile_materials[key] = materials
    if not materials.is_empty():
        foliage_attached.emit(key, materials)
    return true

func _on_tile_retiring(key: String) -> void:
    _queue.erase(key)
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
