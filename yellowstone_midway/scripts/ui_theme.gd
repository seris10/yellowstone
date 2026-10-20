class_name YellowstoneUiTheme
extends RefCounted

## Light routed-wood sign theme for menus and panels.
const FONT_PATH: String = "res://assets/fonts/national-park-variable.ttf"
const WOOD := Color("e2cda3")
const WOOD_LIGHT := Color("efe3c6")
const WOOD_DARK := Color("c8aa78")
const PLANK := Color("f3e9d2")
const PLANK_HOVER := Color("fbf5e6")
const PLANK_PRESSED := Color("d9c297")
const EDGE := Color("6b4627")
const INK := Color("3b2715")
const INK_SOFT := Color("6e5334")
const FOREST := Color("2f5130")
# Recessed fill of an engraved key box; keeps green text above the contrast floor.
const KEY_RECESS := Color("d6bd90")
# Texture margin of the sign frame in texture pixels.
const FRAME_MARGIN: int = 14
# Drop-shadow band around a sign panel, in texture pixels.
const SHADOW_PAD: int = 14
# Drop-shadow band around a plank or key box, in texture pixels.
const RELIEF_PAD: int = 10
# Plate size of a plank or key box texture before its shadow band.
const RELIEF_SIZE := Vector2i(48, 36)

static var _theme: Theme
static var _fonts: Dictionary = {}
static var _sign: StyleBoxTexture
static var _relief: Dictionary = {}

static func font(weight: int = 500) -> Font:
	if _fonts.has(weight):
		return _fonts[weight]
	var variation := FontVariation.new()
	if ResourceLoader.exists(FONT_PATH):
		variation.base_font = load(FONT_PATH)
		variation.variation_opentype = {TextServerManager.get_primary_interface().name_to_tag("wght"): weight}
	else:
		variation.base_font = ThemeDB.fallback_font
	_fonts[weight] = variation
	return variation

static func theme() -> Theme:
	if _theme != null:
		return _theme
	var t := Theme.new()
	t.default_font = font(500)
	t.default_font_size = 16
	t.set_stylebox("panel", "PanelContainer", sign_box())
	t.set_stylebox("panel", "TooltipPanel", flat(PLANK, EDGE, 1, 3, 10, 6))
	t.set_color("font_color", "TooltipLabel", INK)
	t.set_color("font_color", "Label", INK)
	t.set_color("default_color", "RichTextLabel", INK)
	for type: String in ["Button", "CheckButton", "CheckBox", "OptionButton", "MenuButton"]:
		t.set_color("font_color", type, INK)
		t.set_color("font_hover_color", type, FOREST)
		t.set_color("font_focus_color", type, INK)
		t.set_color("font_pressed_color", type, INK)
		t.set_color("font_hover_pressed_color", type, FOREST)
		t.set_color("font_disabled_color", type, Color(INK_SOFT, 0.55))
		t.set_font("font", type, font(600))
	for type: String in ["Button", "OptionButton", "MenuButton"]:
		t.set_stylebox("normal", type, relief_box(PLANK, Color(EDGE, 0.55), true, true))
		t.set_stylebox("hover", type, relief_box(PLANK_HOVER, FOREST, true, true))
		t.set_stylebox("pressed", type, relief_box(PLANK_PRESSED, EDGE, false, false))
		t.set_stylebox("hover_pressed", type, relief_box(PLANK_PRESSED, FOREST, false, false))
		t.set_stylebox("disabled", type, flat(Color(PLANK, 0.5), Color(EDGE, 0.25), 1, 3, 14, 7))
		var focus := flat(Color.TRANSPARENT, FOREST, 2, 3, 0, 0)
		focus.draw_center = false
		t.set_stylebox("focus", type, focus)
	for type: String in ["CheckButton", "CheckBox"]:
		var clear := StyleBoxEmpty.new()
		clear.content_margin_top = 4
		clear.content_margin_bottom = 4
		for state: String in ["normal", "hover", "pressed", "hover_pressed", "focus", "disabled"]:
			t.set_stylebox(state, type, clear)
	t.set_icon("checked", "CheckButton", _switch_icon(true))
	t.set_icon("unchecked", "CheckButton", _switch_icon(false))
	t.set_icon("checked", "CheckBox", _switch_icon(true))
	t.set_icon("unchecked", "CheckBox", _switch_icon(false))
	var field := flat(PLANK, Color(EDGE, 0.55), 1, 3, 10, 6)
	t.set_stylebox("normal", "LineEdit", field)
	t.set_stylebox("focus", "LineEdit", flat(PLANK_HOVER, FOREST, 2, 3, 10, 6))
	t.set_stylebox("read_only", "LineEdit", field)
	for name: String in ["font_color", "caret_color", "font_uneditable_color"]:
		t.set_color(name, "LineEdit", INK)
	t.set_color("font_placeholder_color", "LineEdit", Color(INK_SOFT, 0.6))
	var line := StyleBoxLine.new()
	line.color = Color(EDGE, 0.4)
	line.thickness = 1
	t.set_stylebox("separator", "HSeparator", line)
	t.set_constant("separation", "HSeparator", 6)
	var track := flat(WOOD_DARK, Color.TRANSPARENT, 0, 3, 0, 2)
	t.set_stylebox("slider", "HSlider", track)
	t.set_stylebox("grabber_area", "HSlider", flat(FOREST, Color.TRANSPARENT, 0, 3, 0, 2))
	t.set_stylebox("grabber_area_highlight", "HSlider", flat(FOREST, Color.TRANSPARENT, 0, 3, 0, 2))
	t.set_icon("grabber", "HSlider", _dot_icon(FOREST))
	t.set_icon("grabber_highlight", "HSlider", _dot_icon(FOREST.lightened(0.2)))
	for type: String in ["VScrollBar", "HScrollBar"]:
		t.set_stylebox("scroll", type, flat(Color(WOOD_DARK, 0.35), Color.TRANSPARENT, 0, 4, 4, 4))
		t.set_stylebox("grabber", type, flat(Color(EDGE, 0.55), Color.TRANSPARENT, 0, 4, 4, 4))
		t.set_stylebox("grabber_highlight", type, flat(Color(EDGE, 0.75), Color.TRANSPARENT, 0, 4, 4, 4))
		t.set_stylebox("grabber_pressed", type, flat(EDGE, Color.TRANSPARENT, 0, 4, 4, 4))
	_theme = t
	return t

## Sign-board panel style: grained light wood inside a routed frame, raised on a drop shadow.
static func sign_box(margin_h: int = 28, margin_v: int = 24) -> StyleBoxTexture:
	if _sign == null:
		_sign = StyleBoxTexture.new()
		_sign.texture = _sign_texture()
		for side: Side in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]:
			_sign.set_texture_margin(side, SHADOW_PAD + FRAME_MARGIN)
			# The shadow draws outside the control rect and leaves layout alone.
			_sign.set_expand_margin(side, SHADOW_PAD)
	var box: StyleBoxTexture = _sign.duplicate()
	box.content_margin_left = margin_h
	box.content_margin_right = margin_h
	box.content_margin_top = margin_v
	box.content_margin_bottom = margin_v
	return box

static func flat(fill: Color, border: Color, width: int, radius: int, margin_h: int, margin_v: int) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = fill
	box.border_color = border
	box.set_border_width_all(width)
	box.set_corner_radius_all(radius)
	box.content_margin_left = margin_h
	box.content_margin_right = margin_h
	box.content_margin_top = margin_v
	box.content_margin_bottom = margin_v
	return box

## Plank or key-box style: a raised plate over a drop shadow, or an engraved recess.
static func relief_box(fill: Color, border: Color, raised: bool, shadow: bool, margin_h: int = 14, margin_v: int = 7) -> StyleBoxTexture:
	var key: String = "%s|%s|%d%d" % [fill.to_html(), border.to_html(), int(raised), int(shadow)]
	if not _relief.has(key):
		var pad: int = RELIEF_PAD if shadow else 0
		var cached := StyleBoxTexture.new()
		cached.texture = _relief_texture(fill, border, raised, pad)
		for side: Side in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]:
			cached.set_texture_margin(side, pad + 10)
			cached.set_expand_margin(side, pad)
		_relief[key] = cached
	var box: StyleBoxTexture = _relief[key].duplicate()
	box.content_margin_left = margin_h
	box.content_margin_right = margin_h
	box.content_margin_top = margin_v
	box.content_margin_bottom = margin_v
	return box

## Routed groove: a dark line over a light line, in place of a flat rule.
static func groove(gap: int = 8) -> Control:
	var wrap := MarginContainer.new()
	wrap.add_theme_constant_override("margin_top", maxi(gap / 2, 1))
	wrap.add_theme_constant_override("margin_bottom", maxi(gap / 2, 1))
	var lines := VBoxContainer.new()
	lines.add_theme_constant_override("separation", 0)
	wrap.add_child(lines)
	for color: Color in [Color(EDGE, 0.55), Color(PLANK_HOVER, 0.85)]:
		var line := ColorRect.new()
		line.color = color
		line.custom_minimum_size.y = 1
		line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		lines.add_child(line)
	return wrap

## Row band for a dense list; odd rows carry a faint tint, even rows stay bare board.
static func row_tint(index: int, margin_h: int = 8, margin_v: int = 3) -> StyleBox:
	if index % 2 == 1:
		return flat(Color(WOOD_DARK, 0.22), Color.TRANSPARENT, 0, 2, margin_h, margin_v)
	var bare := StyleBoxEmpty.new()
	bare.content_margin_left = margin_h
	bare.content_margin_right = margin_h
	bare.content_margin_top = margin_v
	bare.content_margin_bottom = margin_v
	return bare

static func heading(text: String, size: int = 13) -> Label:
	var label := Label.new()
	label.text = text.to_upper()
	label.add_theme_font_override("font", font(700))
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", FOREST)
	label.add_theme_constant_override("line_spacing", 0)
	return label

static func _sign_texture() -> ImageTexture:
	var bw: int = 256
	var bh: int = 384
	var w: int = bw + SHADOW_PAD * 2
	var h: int = bh + SHADOW_PAD * 2
	var image := Image.create(w, h, false, Image.FORMAT_RGBA8)
	var streaks := FastNoiseLite.new()
	streaks.seed = 7
	streaks.frequency = 0.012
	var fibers := FastNoiseLite.new()
	fibers.seed = 19
	fibers.frequency = 0.08
	var radius: float = 5.0
	var cast := Rect2(SHADOW_PAD + 2, SHADOW_PAD + 4, bw, bh)
	for y: int in h:
		for x: int in w:
			var bx: int = x - SHADOW_PAD
			var by: int = y - SHADOW_PAD
			var edge_x: float = minf(bx, bw - 1 - bx)
			var edge_y: float = minf(by, bh - 1 - by)
			var edge: float = minf(edge_x, edge_y)
			var off_board: bool = bx < 0 or by < 0 or bx >= bw or by >= bh
			if off_board or (edge_x < radius and edge_y < radius and Vector2(radius - edge_x, radius - edge_y).length() > radius):
				image.set_pixel(x, y, _shadow_pixel(Vector2(x, y), cast, 9.0, 0.34))
				continue
			if edge < 3.0:
				image.set_pixel(x, y, EDGE)
				continue
			var grain: float = 0.5 + 0.55 * streaks.get_noise_2d(bx * 0.4, by * 7.0) + 0.12 * fibers.get_noise_2d(bx * 0.5, by * 9.0)
			var wood: Color = WOOD_LIGHT.lerp(WOOD_DARK, clampf(grain, 0.0, 1.0) * 0.45)
			if edge >= 7.0 and edge < 8.0:
				wood = wood.lerp(INK_SOFT, 0.45)
			elif edge < 5.0:
				wood = wood.lerp(EDGE, 0.18)
			elif by >= 8 and by < 12 and edge_x >= 8.0:
				# Lit bevel along the top edge, shaded along the bottom: the board sits proud.
				wood = wood.lerp(PLANK_HOVER, 0.5)
			elif by >= bh - 12 and by < bh - 8 and edge_x >= 8.0:
				wood = wood.lerp(EDGE, 0.3)
			image.set_pixel(x, y, wood)
	return ImageTexture.create_from_image(image)

static func _relief_texture(fill: Color, border: Color, raised: bool, pad: int) -> ImageTexture:
	var pw: int = RELIEF_SIZE.x
	var ph: int = RELIEF_SIZE.y
	var image := Image.create(pw + pad * 2, ph + pad * 2, false, Image.FORMAT_RGBA8)
	var radius: float = 3.0
	var cast := Rect2(pad, pad + 2, pw, ph)
	for y: int in ph + pad * 2:
		for x: int in pw + pad * 2:
			var px: int = x - pad
			var py: int = y - pad
			var edge_x: float = minf(px, pw - 1 - px)
			var edge_y: float = minf(py, ph - 1 - py)
			var off_plate: bool = px < 0 or py < 0 or px >= pw or py >= ph
			if off_plate or (edge_x < radius and edge_y < radius and Vector2(radius - edge_x, radius - edge_y).length() > radius):
				image.set_pixel(x, y, _shadow_pixel(Vector2(x, y), cast, 6.0, 0.3) if pad > 0 else Color.TRANSPARENT)
				continue
			var down: float = float(py) / float(ph - 1)
			var plate: Color = fill.lightened(0.07).lerp(fill.darkened(0.06), down)
			if not raised:
				plate = fill.darkened(0.08).lerp(fill.lightened(0.06), down)
			if minf(edge_x, edge_y) < 1.0:
				plate = border if border.a > 0.0 else plate.lerp(EDGE, 0.4)
			elif py < 3 or px < 2:
				# A raised plate takes the light on top and left; a recess takes it on the far side.
				plate = plate.lerp(PLANK_HOVER, 0.45) if raised else plate.lerp(EDGE, 0.38)
			elif py >= ph - 3 or px >= pw - 2:
				plate = plate.lerp(EDGE, 0.32) if raised else plate.lerp(PLANK_HOVER, 0.45)
			image.set_pixel(x, y, plate)
	return ImageTexture.create_from_image(image)

## Soft cast shadow for the band outside a board or plate.
static func _shadow_pixel(point: Vector2, plate: Rect2, spread: float, strength: float) -> Color:
	var nearest := Vector2(clampf(point.x, plate.position.x, plate.end.x - 1.0),
		clampf(point.y, plate.position.y, plate.end.y - 1.0))
	var fade: float = clampf(1.0 - point.distance_to(nearest) / spread, 0.0, 1.0)
	return Color(0.1, 0.07, 0.04, strength * pow(fade, 1.7))

static func _switch_icon(on: bool) -> ImageTexture:
	var w: int = 40
	var h: int = 22
	var image := Image.create(w, h, false, Image.FORMAT_RGBA8)
	var track: Color = FOREST if on else WOOD_DARK
	var knob_x: float = w - h * 0.5 if on else h * 0.5
	var r: float = h * 0.5
	for y: int in h:
		for x: int in w:
			var p := Vector2(x + 0.5, y + 0.5)
			var cx: float = clampf(p.x, r, w - r)
			var in_track: float = clampf(r - p.distance_to(Vector2(cx, r)) + 0.5, 0.0, 1.0)
			var in_knob: float = clampf(r - 3.0 - p.distance_to(Vector2(knob_x, r)) + 0.5, 0.0, 1.0)
			var color := Color(track, in_track)
			if in_knob > 0.0:
				color = color.lerp(PLANK_HOVER, in_knob)
			image.set_pixel(x, y, color)
	return ImageTexture.create_from_image(image)

static func _dot_icon(color: Color) -> ImageTexture:
	var s: int = 18
	var image := Image.create(s, s, false, Image.FORMAT_RGBA8)
	for y: int in s:
		for x: int in s:
			var d: float = Vector2(x + 0.5, y + 0.5).distance_to(Vector2(s * 0.5, s * 0.5))
			var fill: float = clampf(s * 0.5 - d + 0.5, 0.0, 1.0)
			var ring: float = clampf(s * 0.5 - 3.0 - d + 0.5, 0.0, 1.0)
			image.set_pixel(x, y, Color(PLANK_HOVER.lerp(color, ring), fill))
	return ImageTexture.create_from_image(image)
