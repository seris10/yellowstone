extends Control

var doc: Dictionary = {}
var _font: Font

func _ready() -> void:
	_font = ThemeDB.fallback_font
	set_process(false)

func set_doc(d: Dictionary) -> void:
	doc = d
	queue_redraw()

func _draw() -> void:
	if not visible:
		return
	if doc.is_empty():
		var style_empty: StyleBoxFlat = StyleBoxFlat.new()
		style_empty.bg_color = Color(0.063, 0.086, 0.075, 0.92)
		style_empty.set_border_width_all(1)
		style_empty.border_color = Color(0.39, 0.47, 0.36, 0.7)
		style_empty.set_corner_radius_all(6)
		draw_style_box(style_empty, Rect2(Vector2.ZERO, size))
		draw_string(_font, Vector2(24, 40), "CALIBRATION", HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color(0.93, 0.92, 0.80))
		draw_string(_font, Vector2(24, 72), "calibration_summary.json not published this build.", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(0.86, 0.87, 0.78))
		return
	var style: StyleBoxFlat = StyleBoxFlat.new()
	style.bg_color = Color(0.063, 0.086, 0.075, 0.94)
	style.set_border_width_all(1)
	style.border_color = Color(0.39, 0.47, 0.36, 0.70)
	style.set_corner_radius_all(6)
	draw_style_box(style, Rect2(Vector2.ZERO, size))
	draw_string(_font, Vector2(24, 36), "REACH HEAT FIT  calibration ground truth", HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color(0.93, 0.92, 0.80))
	var fit: Dictionary = doc.get("reach_fit", {})
	var y: float = 68.0
	var line_h: float = 20.0
	var fields: Array = [
		["Source", str(fit.get("source_file", "n/a"))],
		["Status", str(fit.get("status", "unrecorded"))],
		["q_lat (m3/s)", "%.3f" % float(fit.get("q_lat_m3s", 0.0))],
		["T_lat (deg C)", "%.2f" % float(fit.get("t_lat_c", 0.0))],
		["c_mult", "%.3f" % float(fit.get("c_mult", 1.0))],
		["Train RMSE (deg C)", "%.3f" % float(fit.get("train_rmse_c", 0.0))],
		["Holdout RMSE (deg C)", "%.3f" % float(fit.get("holdout_rmse_c", 0.0))],
		["Train bias", "%.3f" % float(fit.get("train_bias_c", 0.0))],
		["Holdout bias", "%.3f" % float(fit.get("holdout_bias_c", 0.0))],
		["Budget ok", str(fit.get("budget_ok", false))]
	]
	for row: Array in fields:
		draw_string(_font, Vector2(24, y), str(row[0]), HORIZONTAL_ALIGNMENT_LEFT, 180, 14, Color(0.80, 0.82, 0.74))
		draw_string(_font, Vector2(210, y), str(row[1]), HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(0.95, 0.94, 0.85))
		y += line_h
	y += 10.0
	draw_string(_font, Vector2(24, y), "USGS GAUGE TRACE  seconds since epoch vs discharge m3/s and water temperature deg C", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(0.80, 0.82, 0.74))
	y += 16.0
	# Chart.
	var samples: Array = []
	var gauge: Dictionary = doc.get("gauge_trace", {})
	if gauge is Dictionary and gauge.has("samples"):
		samples = gauge["samples"]
	if samples.is_empty():
		draw_string(_font, Vector2(24, y + 20), "No gauge samples in sidecar.", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(0.86, 0.87, 0.78))
		return
	var chart_rect: Rect2 = Rect2(Vector2(24, y + 10), Vector2(size.x - 48, max(140.0, size.y - y - 30.0)))
	draw_rect(chart_rect, Color(0.03, 0.05, 0.04, 0.9), true)
	draw_rect(chart_rect, Color(0.52, 0.56, 0.44, 1.0), false, 1.0)
	# Determine ranges.
	var t_min: float = INF
	var t_max: float = -INF
	var q_min: float = INF
	var q_max: float = -INF
	var tc_min: float = INF
	var tc_max: float = -INF
	for s: Dictionary in samples:
		var ts: float = float(s.get("t_s", 0.0))
		if ts < t_min: t_min = ts
		if ts > t_max: t_max = ts
		var q: float = float(s.get("discharge_m3_s", 0.0))
		if q < q_min: q_min = q
		if q > q_max: q_max = q
		var tc_v: Variant = s.get("temperature_c")
		if tc_v != null:
			var tc_f: float = float(tc_v)
			if tc_f < tc_min: tc_min = tc_f
			if tc_f > tc_max: tc_max = tc_f
	if not is_finite(tc_min):
		tc_min = 0.0
		tc_max = 1.0
	var discharge_points: PackedVector2Array = PackedVector2Array()
	var temp_points: PackedVector2Array = PackedVector2Array()
	for s: Dictionary in samples:
		var ts: float = float(s.get("t_s", 0.0))
		var tn: float = (ts - t_min) / maxf(t_max - t_min, 1.0)
		var q: float = float(s.get("discharge_m3_s", 0.0))
		var qn: float = (q - q_min) / maxf(q_max - q_min, 0.001)
		discharge_points.append(Vector2(chart_rect.position.x + tn * chart_rect.size.x, chart_rect.position.y + chart_rect.size.y - qn * chart_rect.size.y))
		var tc_v: Variant = s.get("temperature_c")
		if tc_v != null:
			var tc_f: float = float(tc_v)
			var tcn: float = (tc_f - tc_min) / maxf(tc_max - tc_min, 0.001)
			temp_points.append(Vector2(chart_rect.position.x + tn * chart_rect.size.x, chart_rect.position.y + chart_rect.size.y - tcn * chart_rect.size.y))
	if discharge_points.size() >= 2:
		draw_polyline(discharge_points, Color(0.56, 0.80, 0.90, 0.95), 1.4)
	if temp_points.size() >= 2:
		draw_polyline(temp_points, Color(0.95, 0.68, 0.33, 0.95), 1.4)
	# Legend.
	draw_rect(Rect2(chart_rect.position + Vector2(6, 6), Vector2(10, 10)), Color(0.56, 0.80, 0.90, 0.95), true)
	draw_string(_font, chart_rect.position + Vector2(22, 16), "discharge m3/s [%.2f, %.2f]" % [q_min, q_max], HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.85, 0.86, 0.78))
	draw_rect(Rect2(chart_rect.position + Vector2(6, 22), Vector2(10, 10)), Color(0.95, 0.68, 0.33, 0.95), true)
	draw_string(_font, chart_rect.position + Vector2(22, 32), "water deg C [%.2f, %.2f]" % [tc_min, tc_max], HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.85, 0.86, 0.78))
	var span_hours: float = (t_max - t_min) / 3600.0
	draw_string(_font, chart_rect.position + Vector2(chart_rect.size.x - 240, 16), "span %.1f h  n=%d" % [span_hours, samples.size()], HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.85, 0.86, 0.78))
