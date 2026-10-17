extends SceneTree
## Recolor CC-BY mallard textures as Canada geese; palette and command: authoring guide, Tool commands.

const SRC_GLB: String = "res://assets/imported/fauna/goose/goose_mallard_base.glb"
const OUT_PNG: String = "res://assets/imported/fauna/goose/canada_goose_texture.png"
const OUT_MAT: String = "res://assets/imported/fauna/goose/canada_goose_material.tres"
# Hue ranges on [0, 1] for the mallard-base source texture.
const GREEN_HUE_RANGE: Vector2 = Vector2(0.22, 0.48)
const ORANGE_HUE_LOW_RANGE: Vector2 = Vector2(0.0, 0.10)
const ORANGE_HUE_HIGH_RANGE: Vector2 = Vector2(0.93, 1.0)
const GREEN_SAT_MIN: float = 0.35
const ORANGE_SAT_MIN: float = 0.55
const GRAY_BROWN_SAT_MAX: float = 0.35
const GRAY_BROWN_VAL_RANGE: Vector2 = Vector2(0.25, 0.75)

func _init() -> void:
	var packed: PackedScene = load(SRC_GLB)
	if packed == null:
		push_error("cannot load " + SRC_GLB)
		quit(1)
		return
	var inst: Node3D = packed.instantiate()
	var tex: Texture2D = _first_texture(inst)
	if tex == null:
		push_error("no texture found in " + SRC_GLB)
		quit(1)
		return
	var img: Image = tex.get_image()
	if img == null:
		push_error("texture has no image")
		quit(1)
		return
	if img.is_compressed():
		img.decompress()
	img.convert(Image.FORMAT_RGBA8)
	var changed: int = 0
	for y: int in range(img.get_height()):
		for x: int in range(img.get_width()):
			var c: Color = img.get_pixel(x, y)
			var h: float = c.h
			var s: float = c.s
			var v: float = c.v
			var out: Color = c
			if s > GREEN_SAT_MIN and h > GREEN_HUE_RANGE.x and h < GREEN_HUE_RANGE.y:
				# Green head -> near-black head/neck.
				out = Color(0.035, 0.038, 0.035, c.a)
				changed += 1
			elif s > ORANGE_SAT_MIN and ((h >= ORANGE_HUE_LOW_RANGE.x and h < ORANGE_HUE_LOW_RANGE.y) or h > ORANGE_HUE_HIGH_RANGE.x):
				# Orange bill/feet -> dark.
				out = Color(0.05, 0.045, 0.04, c.a)
				changed += 1
			elif s <= GRAY_BROWN_SAT_MAX and v > GRAY_BROWN_VAL_RANGE.x and v < GRAY_BROWN_VAL_RANGE.y:
				# Gray-brown body -> Canada brown-gray.
				out = Color(v * 1.05, v * 0.94, v * 0.78, c.a)
				changed += 1
			img.set_pixel(x, y, out)
	var err: int = img.save_png(OUT_PNG)
	if err != OK:
		push_error("save_png failed: " + str(err))
		quit(1)
		return
	var mat: StandardMaterial3D = StandardMaterial3D.new()
	mat.albedo_texture = load(OUT_PNG)
	mat.roughness = 0.9
	var serr: int = ResourceSaver.save(mat, OUT_MAT)
	print("recolored_pixels=", changed, " saved=", OUT_PNG, " material_err=", serr)
	inst.free()
	quit()

func _first_texture(node: Node) -> Texture2D:
	var stack: Array = [node]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is MeshInstance3D:
			for s: int in range(n.mesh.get_surface_count()):
				var m: Material = n.mesh.surface_get_material(s)
				if m is StandardMaterial3D and m.albedo_texture != null:
					return m.albedo_texture
		for c: Node in n.get_children():
			stack.append(c)
	return null
