extends SceneTree
## Independent clamped sampling and source-refresh checks.

const Filter = preload("res://scripts/outflow_filter.gd")
const Core = preload("res://scripts/core_terrain.gd")
var failures: Array[String] = []
var checks := 0
var maximum_error := 0.0

class Fields extends RefCounted:
	var wet_mask_tex: Texture2D
	var flow_fraction_tex: Texture2D
	var in_pool_tex: Texture2D

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, detail: String) -> void:
	checks += 1
	if not condition:
		failures.append(detail)

func sample(image: Image, uv: Vector2) -> float:
	var position := uv * Vector2(image.get_width(), image.get_height()) - Vector2(0.5, 0.5)
	var x := int(floor(position.x))
	var y := int(floor(position.y))
	var fraction := position - Vector2(x, y)
	var west := clampi(x, 0, image.get_width() - 1)
	var east := clampi(x + 1, 0, image.get_width() - 1)
	var north := clampi(y, 0, image.get_height() - 1)
	var south := clampi(y + 1, 0, image.get_height() - 1)
	return lerpf(lerpf(image.get_pixel(west, north).r, image.get_pixel(east, north).r, fraction.x), lerpf(image.get_pixel(west, south).r, image.get_pixel(east, south).r, fraction.x), fraction.y)

func run() -> void:
	for shape: Vector2i in [Vector2i(1, 1), Vector2i(3, 7), Vector2i(8, 5)]:
		for fixture: int in 3:
			var image := Image.create(shape.x, shape.y, false, Image.FORMAT_RF)
			for y: int in shape.y:
				for x: int in shape.x:
					var value := 0.37 if fixture == 0 else (1.0 if x == 0 and y == 0 else 0.0) if fixture == 1 else float((x * 17 + y * 23) % 31) / 31.0
					image.set_pixel(x, y, Color(value, 0, 0))
			var before := image.get_data()
			var filtered := Filter.prefilter(image)
			check(image.get_data() == before, "Filtering mutates the source field")
			check(filtered.get_size() == shape + Vector2i(2, 2), "Filter guard dimensions disagree")
			var step := Vector2.ONE / Vector2(shape)
			for row: int in range(-4, 25):
				for column: int in range(-4, 25):
					var uv := Vector2(column, row) / 20.0
					var expected := 0.4 * sample(image, uv) + 0.15 * (sample(image, uv + Vector2(step.x, 0)) + sample(image, uv - Vector2(step.x, 0)) + sample(image, uv + Vector2(0, step.y)) + sample(image, uv - Vector2(0, step.y)))
					var actual := sample(filtered, (uv * Vector2(shape) + Vector2.ONE) / Vector2(filtered.get_size()))
					var error := absf(actual - expected)
					maximum_error = maxf(maximum_error, error)
					check(error < 0.0000003, "Prefilter differs from five shifted clamped bilinear samples")
	var core := Core.new()
	var fields := Fields.new()
	var image := Image.create(3, 3, false, Image.FORMAT_RF)
	image.fill(Color(0.1, 0, 0))
	fields.wet_mask_tex = ImageTexture.create_from_image(image)
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/thermal_apron.gdshader")
	check(core._bind_outflow_layers(fields, mat), "Initial filter binding fails")
	var first: Texture2DArray = mat.get_shader_parameter("outflow_layers")
	check(core._bind_outflow_layers(fields, mat) and mat.get_shader_parameter("outflow_layers") == first, "Unchanged field rebuilds the filtered array")
	image.fill(Color(0.9, 0, 0))
	fields.wet_mask_tex = ImageTexture.create_from_image(image)
	check(core._bind_outflow_layers(fields, mat) and mat.get_shader_parameter("outflow_layers") != first, "Reloaded field retains a stale filtered array")
	check(mat.get_shader_parameter("outflow_source_size") == Vector2(3, 3), "Filtered binding changes source coordinates")
	core.free()
	var report := {"ok": failures.is_empty(), "checks": checks, "maximum_absolute_error": maximum_error, "clamped_edges_included": true, "source_refresh_checked": true, "failures": failures}
	var output := "res://work/outflow_filter_report.json"
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--out="):
			output = arg.trim_prefix("--out=")
	var file := FileAccess.open(output, FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t") + "\n")
	print("OUTFLOW_FILTER ", JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
