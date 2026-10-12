extends Control
var world: Node
# Cached at ready: _draw runs on every map redraw and must not do I/O.
var _tex: Texture2D
var _style: StyleBox
func _ready() -> void:
	_tex = load("res://assets/textures/midway_macro.jpg") as Texture2D
	if _tex == null:
		push_error("map_view: missing assets/textures/midway_macro.jpg.")
	if world != null:
		_style = world.panel_style(.97)
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
	for r: Dictionary in world.spec.routes:
		var pts:=PackedVector2Array()
		for p: Array in r.points:pts.append(rect.position+(Vector2(p[0],p[2])+Vector2.ONE*2048.0)/4096.0*540.0)
		draw_polyline(pts,Color(.94,.76,.33) if r.kind=="road" else Color(.90,.91,.83),1.5)
	var p: Vector3=world.player.position
	var pt:=rect.position+(Vector2(p.x,p.z)+Vector2.ONE*2048.0)/4096.0*540.0
	draw_circle(pt,5.0,Color.WHITE)
	var direction: Vector3=-world.player.global_basis.z
	draw_line(pt,pt+Vector2(direction.x,direction.z)*18.0,Color.WHITE,2)
	draw_string(font,Vector2(25,632),"N ↑    Gold: road    Ivory: trail    Dot: you",HORIZONTAL_ALIGNMENT_LEFT,-1,15,Color(.87,.89,.81))
	draw_line(Vector2(380,649),Vector2(512,649),Color.WHITE,2)
	draw_string(font,Vector2(406,671),"1 kilometre",HORIZONTAL_ALIGNMENT_LEFT,-1,13,Color.WHITE)
