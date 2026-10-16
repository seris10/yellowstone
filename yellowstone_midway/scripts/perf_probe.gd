class_name YellowstonePerfProbe
extends CanvasLayer
## In-game frame-time probe. F4 shows it; Alt+1..9 and Alt+0 switch one cost center off to isolate it.

const WINDOW := 240
const REFRESH_S := 0.25
const SWITCHES: Array[Dictionary] = [
	{"key": KEY_1, "label": "trees", "path": "AuthoredMidway/AuthoredVegetation"},
	{"key": KEY_2, "label": "canopy", "path": "AuthoredMidway/AuthoredCanopySurface"},
	{"key": KEY_3, "label": "forest floor", "path": "AuthoredMidway/AuthoredForestFloor"},
	{"key": KEY_4, "label": "sky and weather", "path": "YellowstoneAtmosphere"},
	{"key": KEY_6, "label": "terrain", "path": "AuthoredMidway/TerrainTiles"},
	{"key": KEY_7, "label": "water", "path": "AuthoredMidway/ConnectedWater"},
]
const MSAA_MODES: Array[int] = [Viewport.MSAA_4X, Viewport.MSAA_2X, Viewport.MSAA_DISABLED]
const SCALES: Array[float] = [1.0, 0.75, 0.5]

var _label: Label
var _frames := PackedFloat32Array()
var _since_refresh := 0.0
var _compaction := true
var _msaa_index := 0
var _scale_index := 0
var _shadows := true

func _ready() -> void:
	layer = 100
	_label = Label.new()
	_label.position = Vector2(16, 120)
	_label.add_theme_font_size_override("font_size", 13)
	_label.add_theme_color_override("font_color", Color(0.95, 0.95, 0.80))
	_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.9))
	_label.add_theme_constant_override("outline_size", 4)
	add_child(_label)
	visible = false
	_msaa_index = maxi(0, MSAA_MODES.find(get_viewport().msaa_3d))

func _unhandled_key_input(event: InputEvent) -> void:
	var key := event as InputEventKey
	if key == null or not key.pressed or key.echo:
		return
	if key.keycode == KEY_F4:
		visible = not visible
		RenderingServer.viewport_set_measure_render_time(get_viewport().get_viewport_rid(), visible)
		_frames.clear()
		return
	if not visible or not key.alt_pressed:
		return
	for entry: Dictionary in SWITCHES:
		if key.physical_keycode == entry.key:
			var node := get_parent().get_node_or_null(NodePath(str(entry.path))) as Node3D
			if node != null:
				node.visible = not node.visible
			_frames.clear()
			return
	match key.physical_keycode:
		KEY_5:
			_shadows = not _shadows
			for light: Node in get_parent().find_children("*", "DirectionalLight3D", true, false):
				(light as DirectionalLight3D).shadow_enabled = _shadows
		KEY_8:
			_compaction = not _compaction
			var submission := get_parent().get_node_or_null("TreeSubmission")
			if submission != null:
				submission.call("set_enabled", _compaction)
		KEY_9:
			_msaa_index = (_msaa_index + 1) % MSAA_MODES.size()
			get_viewport().msaa_3d = MSAA_MODES[_msaa_index] as Viewport.MSAA
		KEY_0:
			_scale_index = (_scale_index + 1) % SCALES.size()
			get_viewport().scaling_3d_scale = SCALES[_scale_index]
		_:
			return
	_frames.clear()

func _process(delta: float) -> void:
	if not visible:
		return
	_frames.append(delta * 1000.0)
	if _frames.size() > WINDOW:
		_frames = _frames.slice(_frames.size() - WINDOW)
	_since_refresh += delta
	if _since_refresh < REFRESH_S:
		return
	_since_refresh = 0.0
	_label.text = _report()

func _report() -> String:
	var sorted := _frames.duplicate()
	sorted.sort()
	var mean := 0.0
	for value: float in _frames:
		mean += value
	mean /= maxf(1.0, float(_frames.size()))
	var p95: float = sorted[int(float(sorted.size() - 1) * 0.95)] if not sorted.is_empty() else 0.0
	var worst: float = sorted[sorted.size() - 1] if not sorted.is_empty() else 0.0
	var rid := get_viewport().get_viewport_rid()
	var lines := PackedStringArray()
	lines.append("FRAME  mean %.1f ms (%.0f fps)  p95 %.1f  worst %.1f  [last %d]" % [mean, 1000.0 / maxf(mean, 0.001), p95, worst, _frames.size()])
	lines.append("RENDER cpu %.1f ms  gpu %.1f ms   script %.1f ms  physics %.1f ms" % [
		RenderingServer.viewport_get_measured_render_time_cpu(rid), RenderingServer.viewport_get_measured_render_time_gpu(rid),
		Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0, Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0])
	lines.append("DRAW   %d calls  %.1f M primitives  %d objects  vram %.0f MB" % [
		int(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)),
		Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME) / 1.0e6,
		int(Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME)),
		Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED) / 1048576.0])
	var vp := get_viewport()
	lines.append("MSAA %s   render scale %.2f   shadows %s   tree compaction %s" % [
		["4x", "2x", "off"][_msaa_index], vp.scaling_3d_scale, "on" if _shadows else "off", "on" if _compaction else "off"])
	var states := PackedStringArray()
	for entry: Dictionary in SWITCHES:
		var node := get_parent().get_node_or_null(NodePath(str(entry.path))) as Node3D
		states.append("%s %s=%s" % [OS.get_keycode_string(entry.key), entry.label, "?" if node == null else ("on" if node.visible else "OFF")])
	lines.append("Alt+  " + "   ".join(states) + "   5 shadows   8 compaction   9 MSAA   0 scale")
	return "\n".join(lines)
