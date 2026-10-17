extends CanvasLayer
## Bounded rolling frame statistics; reports estimates separately from engine memory metrics.
var streamer: Node
var client: Node
var title: String = "PARK RUNTIME"
var _label: Label
var _samples: Array[float] = []
var _elapsed: float = 0.0

func _ready() -> void:
    layer = 50
    _label = Label.new()
    _label.position = Vector2(18,18)
    _label.add_theme_font_size_override("font_size",15)
    _label.add_theme_color_override("font_color",Color(0.90,0.95,0.89))
    _label.add_theme_color_override("font_shadow_color",Color(0.05,0.08,0.07))
    _label.add_theme_constant_override("shadow_offset_x",1)
    _label.add_theme_constant_override("shadow_offset_y",1)
    add_child(_label)

func _process(delta: float) -> void:
    _samples.append(delta*1000.0)
    if _samples.size()>600:
        _samples.pop_front()
    _elapsed += delta
    if _elapsed<0.5 or streamer==null:
        return
    _elapsed = 0.0
    var ordered: Array[float] = _samples.duplicate()
    ordered.sort()
    var p95: float = ordered[int((ordered.size()-1)*0.95)]
    var p99: float = ordered[int((ordered.size()-1)*0.99)]
    var s: Dictionary = streamer.stats
    var clock_text: String = "Python disconnected: terrain remains interactive"
    if client!=null and not client.packet.is_empty():
        clock_text = "Physical t %.2f s | revision %d | stale %s" % [client.presentation_time_s(),client.revision,str(client.stale)]
    _label.text = "%s\nWASD + Q/E flight | Shift faster | right-drag look\nVisible %d / resident %d | jobs %d | estimated %.1f MiB\nFrame p95 %.2f / p99 %.2f ms | commit %.2f / plan %.2f ms\nCollision %d | failures %d\n%s" % [
        title,int(s.get("visible_tiles",0)),int(s.get("resident_tiles",0)),int(s.get("inflight",0)),
        float(s.get("resident_estimate_mib",0)),p95,p99,float(s.get("commit_ms",0)),
        float(s.get("plan_ms",0)),int(s.get("collision_tiles",0)),int(s.get("failures",0)),clock_text]

func report() -> Dictionary:
    var ordered: Array[float] = _samples.duplicate()
    ordered.sort()
    return {"frame_samples_ms":_samples.duplicate(),"streamer":streamer.stats.duplicate(true) if streamer!=null else {},
        "draw_calls":Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
        "objects":Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME),
        "primitives":Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME),
        "static_memory_bytes":Performance.get_monitor(Performance.MEMORY_STATIC)}
