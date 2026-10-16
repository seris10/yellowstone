extends SceneTree
## Compare authored floor anchors with runtime terrain loaders and triangle planes.

const Core = preload("res://scripts/core_terrain.gd")
const HeightField = preload("res://scripts/height_field.gd")
const RenderedGround = preload("res://scripts/rendered_ground.gd")
var core := Core.new()
var master := HeightField.new()
var checks := 0
var core_anchors := 0
var log_samples := 0
var maximum_error_m := 0.0
var failures: Array[String] = []
var plane_samples := 0
var maximum_plane_residual_m := 0.0

func _initialize() -> void:
	call_deferred("verify")

func verify() -> void:
	var source_path := "res://data/forest_floor.json"
	var output_path := "res://work/floor-contact-validation.json"
	var arguments := OS.get_cmdline_user_args()
	for at: int in arguments.size():
		if arguments[at] == "--data" and at + 1 < arguments.size(): source_path = arguments[at + 1]
		if arguments[at] == "--out" and at + 1 < arguments.size(): output_path = arguments[at + 1]
	if not core._load_metadata() or not core._load_heights() or master.values.is_empty():
		push_error("Runtime floor contact terrain could not load")
		core.free()
		quit(2)
		return
	var rendered := RenderedGround.new()
	if not rendered.valid():
		failures.append("Production rendered-ground sampler failed to load")
	var source: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(source_path))
	if source.get("terrain_contact", {}).get("core_mesh_decimation", -1) != Core.MESH_DECIMATION:
		failures.append("Floor producer and runtime core mesh decimation differ")
	for record: Dictionary in source.records:
		var x: float = record.position[0]
		var z: float = record.position[2]
		compare(record.position[1], height_at(x, z), str(record.id))
		compare(rendered.sample(x, z), height_at(x, z), str(record.id) + " production sampler")
		if record.kind in ["understory_card", "litter"]:
			validate_plane(record)
		if inside_core(x, z): core_anchors += 1
		if record.kind == "log":
			for sample: Array in record.ground_profile_m:
				compare(sample[1], height_at(x + sin(record.yaw) * sample[0], z + cos(record.yaw) * sample[0]), str(record.id) + " log profile")
				log_samples += 1
	var report := {"ok": failures.is_empty(), "checks": checks, "core_anchors": core_anchors, "log_profile_samples": log_samples, "maximum_contact_error_m": maximum_error_m, "plane_samples": plane_samples, "maximum_plane_residual_m": maximum_plane_residual_m, "tolerance_m": 0.00001, "core_mesh_decimation": Core.MESH_DECIMATION, "runtime_height_loader": "MidwayCoreTerrain._load_heights", "source_sha256": FileAccess.get_sha256(source_path), "failures": failures}
	var file := FileAccess.open(output_path, FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "  "))
	file.close()
	print("FLOOR_CONTACT_VALIDATION ", JSON.stringify(report))
	core.free()
	quit(0 if failures.is_empty() else 1)

func compare(authored: float, rendered: float, label: String) -> void:
	checks += 1
	var error := absf(authored - rendered)
	maximum_error_m = maxf(maximum_error_m, error)
	if error > 0.00001 and failures.size() < 20:
		failures.append("%s differs from runtime terrain by %.9f m" % [label, error])

func inside_core(x: float, z: float) -> bool:
	return x >= core._x_min_m and x <= core._x_max_m and z >= core._z_min_m and z <= core._z_max_m

func height_at(x: float, z: float) -> float:
	if not inside_core(x, z): return master.sample(x, z)
	var spacing: float = Core.MESH_DECIMATION * core._cell_m
	var gx: float = (x - core._x_min_m) / spacing
	var gz: float = (z - core._z_min_m) / spacing
	var i := mini(floori(gx), int((core._nx - 1) / Core.MESH_DECIMATION) - 1)
	var j := mini(floori(gz), int((core._nz - 1) / Core.MESH_DECIMATION) - 1)
	var fx := gx - i
	var fz := gz - j
	var corners: Array = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]] if fx + fz <= 1.0 else [[1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
	var heights: Array[float] = []
	for corner: Array in corners:
		heights.append(core._heights_full[(j + int(corner[1])) * Core.MESH_DECIMATION * core._nx + (i + int(corner[0])) * Core.MESH_DECIMATION])
	var a: Array = corners[0]
	var b: Array = corners[1]
	var c: Array = corners[2]
	var denominator: float = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
	var wa: float = ((b[1] - c[1]) * (fx - c[0]) + (c[0] - b[0]) * (fz - c[1])) / denominator
	var wb: float = ((c[1] - a[1]) * (fx - c[0]) + (a[0] - c[0]) * (fz - c[1])) / denominator
	return heights[0] * wa + heights[1] * wb + heights[2] * (1.0 - wa - wb) + Core.CORE_RENDER_LIFT_M

func validate_plane(record: Dictionary) -> void:
	var radius: float = float(record.size[0]) * 0.5
	var x: float = record.position[0]
	var z: float = record.position[2]
	var normal: Array = record.ground_normal
	var residual := 0.0
	for fraction: float in [0.5, 1.0]:
		for step_index: int in 16:
			var angle := TAU * step_index / 16.0
			var dx := radius * fraction * cos(angle)
			var dz := radius * fraction * sin(angle)
			var plane: float = record.position[1] - (float(normal[0]) * dx + float(normal[2]) * dz) / float(normal[1])
			residual = maxf(residual, absf(height_at(x + dx, z + dz) - plane))
			plane_samples += 1
	maximum_plane_residual_m = maxf(maximum_plane_residual_m, residual)
	compare(record.plane_error_m, residual, str(record.id) + " independently sampled plane")
	if residual > 0.00801 and failures.size() < 20:
		failures.append(str(record.id) + " exceeds the sampled 8mm floor-plane contact bound")
