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
# Texture margin of the sign frame in texture pixels.
const FRAME_MARGIN: int = 14

static var _theme: Theme
static var _fonts: Dictionary = {}
static var _sign: StyleBoxTexture

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
		t.set_stylebox("normal", type, flat(PLANK, Color(EDGE, 0.55), 1, 3, 14, 7))
		t.set_stylebox("hover", type, flat(PLANK_HOVER, FOREST, 2, 3, 14, 7))
		t.set_stylebox("pressed", type, flat(PLANK_PRESSED, EDGE, 1, 3, 14, 7))
		t.set_stylebox("hover_pressed", type, flat(PLANK_PRESSED, FOREST, 2, 3, 14, 7))
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

## Sign-board panel style: grained light wood inside a routed frame.
static func sign_box(margin_h: int = 28, margin_v: int = 24) -> StyleBoxTexture:
	if _sign == null:
		_sign = StyleBoxTexture.new()
		_sign.texture = _sign_texture()
		for side: Side in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]:
			_sign.set_texture_margin(side, FRAME_MARGIN)
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

static func heading(text: String, size: int = 13) -> Label:
	var label := Label.new()
	label.text = text.to_upper()
	label.add_theme_font_override("font", font(700))
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", FOREST)
	label.add_theme_constant_override("line_spacing", 0)
	return label

static func _sign_texture() -> ImageTexture:
	var w: int = 256
	var h: int = 384
	var image := Image.create(w, h, false, Image.FORMAT_RGBA8)
	var streaks := FastNoiseLite.new()
	streaks.seed = 7
	streaks.frequency = 0.012
	var fibers := FastNoiseLite.new()
	fibers.seed = 19
	fibers.frequency = 0.08
	var radius: float = 5.0
	for y: int in h:
		for x: int in w:
			var edge_x: float = minf(x, w - 1 - x)
			var edge_y: float = minf(y, h - 1 - y)
			var edge: float = minf(edge_x, edge_y)
			if edge_x < radius and edge_y < radius and Vector2(radius - edge_x, radius - edge_y).length() > radius:
				image.set_pixel(x, y, Color.TRANSPARENT)
				continue
			if edge < 3.0:
				image.set_pixel(x, y, EDGE)
				continue
			var grain: float = 0.5 + 0.55 * streaks.get_noise_2d(x * 0.4, y * 7.0) + 0.12 * fibers.get_noise_2d(x * 0.5, y * 9.0)
			var wood: Color = WOOD_LIGHT.lerp(WOOD_DARK, clampf(grain, 0.0, 1.0) * 0.45)
			if edge >= 7.0 and edge < 8.0:
				wood = wood.lerp(INK_SOFT, 0.45)
			elif edge < 5.0:
				wood = wood.lerp(EDGE, 0.18)
			image.set_pixel(x, y, wood)
	return ImageTexture.create_from_image(image)

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
