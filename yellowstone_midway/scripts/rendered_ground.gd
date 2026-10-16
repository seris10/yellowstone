class_name YellowstoneRenderedGround
extends RefCounted
## Sample the visible core triangle surface and outer master terrain.

const Core = preload("res://scripts/core_terrain.gd")
const HeightField = preload("res://scripts/height_field.gd")
var master := HeightField.new()
var heights := PackedFloat32Array()
var nx := 0
var nz := 0
var origin := Vector2.ZERO
var extent := Vector2.ZERO
var step := 0.0
var source_hashes := {}

func _init() -> void:
	var core := Core.new()
	if core._load_metadata() and core._load_heights():
		heights = core._heights_full
		nx = core._nx
		nz = core._nz
		origin = Vector2(core._x_min_m, core._z_min_m)
		extent = Vector2(core._x_max_m, core._z_max_m)
		step = core._cell_m * Core.MESH_DECIMATION
		for path: String in [Core.CORE_JSON, Core.CORE_HEIGHTFIELD, Core.CORE_MICRORELIEF, "res://data/terrain.f32"]:
			source_hashes[path] = FileAccess.get_sha256(path)
	core.free()

func valid() -> bool:
	return not heights.is_empty() and not master.values.is_empty() and step > 0.0

func sample(x: float, z: float) -> float:
	if x < origin.x or z < origin.y or x > extent.x or z > extent.y:
		return master.sample(x, z)
	var gx := (x - origin.x) / step
	var gz := (z - origin.y) / step
	var i := mini(floori(gx), int((nx - 1) / Core.MESH_DECIMATION) - 1)
	var j := mini(floori(gz), int((nz - 1) / Core.MESH_DECIMATION) - 1)
	var fx := gx - i
	var fz := gz - j
	var at := j * Core.MESH_DECIMATION * nx + i * Core.MESH_DECIMATION
	var a := heights[at]
	var b := heights[at + Core.MESH_DECIMATION]
	var c := heights[at + Core.MESH_DECIMATION * nx]
	var d := heights[at + Core.MESH_DECIMATION * (nx + 1)]
	return (a + fx * (b - a) + fz * (c - a) if fx + fz <= 1.0 else d + (1.0 - fx) * (c - d) + (1.0 - fz) * (b - d)) + Core.CORE_RENDER_LIFT_M
