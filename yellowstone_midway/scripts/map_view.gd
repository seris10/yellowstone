extends Control
var world: Node
# Cached at ready: _draw runs on every map redraw and must not do I/O.
var _tex: Texture2D
var _style: StyleBox
# Census canopy overlay (fixes-39 item 10): true draws crown disks on the map from data/census.json.
var census_visible: bool = false
# Cached crown samples: Array of {x, z, radius_m, exg}; set by world.gd after reading data/census.json.
var _census_rows: Array = []
# Quartile cutoffs on peak_exg for crown color mapping; computed when the census is first set.
var _exg_quartiles: PackedFloat32Array = PackedFloat32Array([0.0, 0.0, 0.0])
func _ready() -> void:
	_tex = load("res://assets/textures/midway_macro.jpg") as Texture2D
	if _tex == null:
		push_error("map_view: missing assets/textures/midway_macro.jpg.")
	if world != null:
		_style = world.panel_style(.97)

func set_census(rows: Array) -> void:
	# Cache subset of census tree rows for the map overlay; 33k rows cap at a stride that keeps _draw cheap.
	_census_rows = rows
	# Compute peak_exg quartiles from the full set so the color key matches the full-data distribution.
	var exg_values: Array = []
	for row: Dictionary in rows:
		if row.has("peak_exg"):
			exg_values.append(float(row["peak_exg"]))
	exg_values.sort()
	if exg_values.size() >= 4:
		_exg_quartiles = PackedFloat32Array([float(exg_values[exg_values.size() / 4]), float(exg_values[exg_values.size() / 2]), float(exg_values[3 * exg_values.size() / 4])])
	queue_redraw()
func _draw() -> void:
	if not visible or world==null:return
	if _style == null:
		_style = world.panel_style(.97)
	draw_style_box(_style,Rect2(Vector2.ZERO,size))
	var rect:=Rect2(25,64,540,540)
	if _tex != null:
		draw_texture_rect(_tex,rect,false,Color(.74,.78,.70))
	var font:=ThemeDB.fallback_font
	draw_string(font,Vector2(25,38),"MIDWAY / FIELD MAP",HORIZONTAL_ALIGNMENT_LEFT,-1,20,Color(.93,.92,.80))
	if census_visible and not _census_rows.is_empty():
		# Draw crown disks on the map colored by peak_exg quartile; crowns under 0.3 m are omitted so canopies read as patches.
		var stride: int = maxi(1, int(ceil(float(_census_rows.size()) / 4000.0)))
		var scale: float = 540.0 / 4096.0
		for i: int in range(0, _census_rows.size(), stride):
			var row: Variant = _census_rows[i]
			if not row is Dictionary:
				continue
			var rx: float = float(row.get("x", 0.0))
			var rz: float = float(row.get("z", 0.0))
			var r_m: float = float(row.get("crown_r_m", 0.0))
			if r_m < 0.3:
				continue
			var exg: float = float(row.get("peak_exg", 0.0))
			var color: Color = _crown_color(exg)
			var center: Vector2 = rect.position + (Vector2(rx, rz) + Vector2.ONE * 2048.0) * scale
			var radius_px: float = maxf(1.2, r_m * scale)
			draw_circle(center, radius_px, color)
	for r: Dictionary in world.spec.routes:
		var pts:=PackedVector2Array()
		# Top-down projection: y component is discarded.
		for p: Array in r.points:pts.append(rect.position+(Vector2(p[0],p[2])+Vector2.ONE*2048.0)/4096.0*540.0)
		draw_polyline(pts,Color(.94,.76,.33) if r.kind=="road" else Color(.90,.91,.83),1.5)
	var p: Vector3=world.player.position
	var pt:=rect.position+(Vector2(p.x,p.z)+Vector2.ONE*2048.0)/4096.0*540.0
	draw_circle(pt,5.0,Color.WHITE)
	var direction: Vector3=-world.player.global_basis.z
	draw_line(pt,pt+Vector2(direction.x,direction.z)*18.0,Color.WHITE,2)
	var legend: String = "N ↑    Gold: road    Ivory: trail    Dot: you"
	if census_visible:
		legend += "    U: canopy (peak_exg q1-q4)"
	draw_string(font,Vector2(25,632),legend,HORIZONTAL_ALIGNMENT_LEFT,-1,15,Color(.87,.89,.81))
	draw_line(Vector2(380,649),Vector2(512,649),Color.WHITE,2)
	draw_string(font,Vector2(406,671),"1 kilometre",HORIZONTAL_ALIGNMENT_LEFT,-1,13,Color.WHITE)

func _crown_color(exg: float) -> Color:
	# Four-step quartile color ramp on peak_exg: pale yellow, light green, mid green, dark green.
	if _exg_quartiles.size() < 3:
		return Color(0.55, 0.72, 0.42, 0.68)
	if exg < _exg_quartiles[0]:
		return Color(0.84, 0.80, 0.44, 0.55)
	if exg < _exg_quartiles[1]:
		return Color(0.64, 0.80, 0.44, 0.60)
	if exg < _exg_quartiles[2]:
		return Color(0.37, 0.63, 0.33, 0.68)
	return Color(0.20, 0.44, 0.24, 0.75)
