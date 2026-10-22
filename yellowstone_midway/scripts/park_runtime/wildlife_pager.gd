extends Node
## Pages wildlife visual actors by resident leaf tiles; identity and state persist across eviction.
signal actor_spawned(id: String)
signal actor_suspended(id: String)

const Actor = preload("res://scripts/wildlife_actor.gd")
const REEVALUATE_INTERVAL_S := 0.5

## Ground sampler preferring resident leaf heights in absolute site coordinates.
class TileGround extends RefCounted:
    var streamer: Node3D
    var fallback: RefCounted

    func _init(source: Node3D, master: RefCounted) -> void:
        streamer = source
        fallback = master

    func sample(x: float, z: float) -> float:
        for key: String in streamer.resident:
            var tile: Node3D = streamer.resident[key]
            var d: Dictionary = tile.descriptor
            if int(d.lod) != 0:
                continue
            if x >= float(d.origin_x_m) and x < float(d.origin_x_m) + float(d.size_m) and z >= float(d.origin_z_m) and z < float(d.origin_z_m) + float(d.size_m):
                return tile.sample_height(x, z)
        return float(fallback.call("sample", x, z))

var _streamer: Node3D
var _frame: RefCounted
var _ecosystem: Node
var _host: Node
var _terrain: RefCounted
var _roster: Dictionary = {}
var _present: Dictionary = {}
var _stores: Dictionary = {}
var _totals: Dictionary = {"spawned": 0, "suspended": 0, "restored": 0}
var _reevaluate_s: float = 0.0

func configure(streamer: Node3D, frame: RefCounted, terrain: RefCounted, ecosystem: Node, host: Node) -> bool:
    if streamer == null or frame == null or terrain == null or ecosystem == null or host == null:
        push_error("Wildlife paging requires a streamer, frame, terrain, ecosystem and host")
        return false
    _streamer = streamer
    _frame = frame
    _terrain = TileGround.new(streamer, terrain)
    _ecosystem = ecosystem
    _host = host
    _build_roster()
    streamer.tile_committed.connect(_on_tile_committed)
    streamer.tile_retiring.connect(_on_tile_retiring)
    return true

func stats() -> Dictionary:
    return _totals.duplicate()

## Ids of actors with live visual nodes.
func present_ids() -> Array:
    return _present.keys()

## Live visual actor for an id; null while suspended.
func present_actor(id: String) -> Node3D:
    return _present.get(id)

## Persistent state captured at suspension; empty while the actor is present.
func stored_state(id: String) -> Dictionary:
    return _stores.get(id, {})

## Validate roster routes once through probe actors; invalid records are skipped.
func _build_roster() -> void:
    _roster.clear()
    for record: Dictionary in _ecosystem.params.get("wildlife", []):
        var id: String = str(record.get("id", ""))
        if id.is_empty():
            push_error("Wildlife roster record lacks an id")
            continue
        var probe: Node3D = Actor.new()
        probe.setup(record, _terrain, _ecosystem)
        if not probe.has_valid_route():
            probe.free()
            continue
        # Records with an encounter probability are decorative encounters; the roster id stays authoritative.
        var decorative: bool = float(record.get("encounter_probability", 0.0)) > 0.0
        _roster[id] = {
            "record": record,
            "anchor": probe.site_position(),
            "persistence": "decorative_encounter" if decorative else "tracked",
        }
        probe.free()

func _on_tile_committed(_key: String) -> void:
    _spawn_covered()

func _on_tile_retiring(_key: String) -> void:
    _suspend_uncovered()

## Periodic pass covers actors whose tiles committed before configure or without a commit event.
func _process(delta: float) -> void:
    _reevaluate_s += delta
    if _reevaluate_s < REEVALUATE_INTERVAL_S:
        return
    _reevaluate_s = 0.0
    _spawn_covered()
    _suspend_uncovered()

## Resident leaf coverage of an absolute site position.
func _covered(at: Vector3) -> bool:
    for key: String in _streamer.resident:
        var tile: Node3D = _streamer.resident[key]
        var d: Dictionary = tile.descriptor
        if int(d.lod) != 0:
            continue
        if at.x >= float(d.origin_x_m) and at.x < float(d.origin_x_m) + float(d.size_m) and at.z >= float(d.origin_z_m) and at.z < float(d.origin_z_m) + float(d.size_m):
            return true
    return false

func _spawn_covered() -> void:
    for id: String in _roster:
        if _present.has(id):
            continue
        var at: Vector3 = stored_state(id).get("world_position", _roster[id].anchor)
        if _covered(at):
            _spawn(id)

func _suspend_uncovered() -> void:
    for id: String in _present.keys():
        var actor: Node3D = _present[id]
        if not _covered(actor.site_position()):
            _suspend(id)

func _spawn(id: String) -> void:
    var entry: Dictionary = _roster[id]
    var actor: Node3D = Actor.new()
    actor.setup(entry.record, _terrain, _ecosystem)
    if not actor.has_valid_route():
        actor.free()
        return
    actor.set_meta("persistence_class", entry.persistence)
    var restored: bool = _stores.has(id)
    if restored:
        actor.restore_state(_stores[id])
    actor.bind_frame(_frame)
    _host.add_child(actor)
    _present[id] = actor
    _totals.spawned += 1
    if restored:
        _totals.restored += 1
    actor_spawned.emit(id)

## Capture persistent state, then release the visual node; ecosystem stores persist.
func _suspend(id: String) -> void:
    var actor: Node3D = _present.get(id)
    if actor == null:
        return
    _stores[id] = actor.capture_state()
    _present.erase(id)
    _host.remove_child(actor)
    actor.queue_free()
    _totals.suspended += 1
    actor_suspended.emit(id)

## Rebuild the roster after a generation reload; stores reset with the ecosystem.
func reload() -> void:
    for id: String in _present.keys():
        _suspend(id)
    _stores.clear()
    _build_roster()
    _spawn_covered()

func _exit_tree() -> void:
    for id: String in _present.keys():
        var actor: Node3D = _present[id]
        _present.erase(id)
        if is_instance_valid(actor):
            actor.queue_free()
