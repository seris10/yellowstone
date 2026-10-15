class_name MidwayOutflowFilter
extends RefCounted
## Linear outflow stencil with a clamped one-texel guard.

static func prefilter(image: Image) -> Image:
	if image == null or image.get_format() != Image.FORMAT_RF:
		push_error("outflow_filter: expected a float32 scalar image")
		return null
	var width := image.get_width()
	var height := image.get_height()
	var values := image.get_data().to_float32_array()
	var result := PackedFloat32Array()
	result.resize((width + 2) * (height + 2))
	for row: int in range(-1, height + 1):
		var y := clampi(row, 0, height - 1)
		var north := clampi(row - 1, 0, height - 1)
		var south := clampi(row + 1, 0, height - 1)
		for column: int in range(-1, width + 1):
			var x := clampi(column, 0, width - 1)
			var west := clampi(column - 1, 0, width - 1)
			var east := clampi(column + 1, 0, width - 1)
			result[(row + 1) * (width + 2) + column + 1] = 0.4 * values[y * width + x] + 0.15 * (values[y * width + west] + values[y * width + east] + values[north * width + x] + values[south * width + x])
	return Image.create_from_data(width + 2, height + 2, false, Image.FORMAT_RF, result.to_byte_array())
