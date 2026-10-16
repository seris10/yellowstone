class_name MidwayHeightField
extends RefCounted
## Shared terrain authority, row zero is north. Triangle interpolation matches rendered/collision diagonals.
const GRID := 1025
const STEP := 4.0
const HALF := 2048.0
var values := PackedFloat32Array()

func _init(path: String = "res://data/terrain.f32") -> void:
	if FileAccess.file_exists(path):
		values = FileAccess.get_file_as_bytes(path).to_float32_array()
	if values.size() != GRID * GRID:
		push_error("Missing/invalid fixed elevation raster (%s: got %d floats, need %d); heights read 0." % [path, values.size(), GRID * GRID])
		values = PackedFloat32Array()

func sample(x: float, z: float) -> float:
	if values.is_empty():
		return 0.0
	var gx := clampf((x + HALF) / STEP, 0.0, float(GRID - 1) - 0.00001)
	var gz := clampf((z + HALF) / STEP, 0.0, float(GRID - 1) - 0.00001)
	var ix := int(floor(gx))
	var iz := int(floor(gz))
	var fx := gx - ix
	var fz := gz - iz
	var a := values[iz * GRID + ix]
	var b := values[iz * GRID + ix + 1]
	var c := values[(iz + 1) * GRID + ix]
	var d := values[(iz + 1) * GRID + ix + 1]
	if fx + fz <= 1.0:
		return a + fx * (b - a) + fz * (c - a)
	return d + (1.0 - fx) * (c - d) + (1.0 - fz) * (b - d)

func normal_at(ix: int, iz: int) -> Vector3:
	if values.is_empty():
		return Vector3.UP
	var left := maxi(ix - 1, 0)
	var right := mini(ix + 1, GRID - 1)
	var top := maxi(iz - 1, 0)
	var bottom := mini(iz + 1, GRID - 1)
	var dx := (values[iz * GRID + right] - values[iz * GRID + left]) / (float(right - left) * STEP)
	var dz := (values[bottom * GRID + ix] - values[top * GRID + ix]) / (float(bottom - top) * STEP)
	return Vector3(-dx, 1.0, -dz).normalized()
