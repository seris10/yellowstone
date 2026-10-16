extends Node
## Conservative visible-prefix submission for immutable tree instances.

const STRIDE := 20
const MOVE_LIMIT_M := 1.0
const GUARD_M := 2.0

class Batch extends RefCounted:
	var node: MultiMeshInstance3D
	var original: MultiMesh
	var compact: MultiMesh
	var source: PackedFloat32Array
	var centers: PackedVector3Array
	var selected: PackedInt32Array
	var center: Vector3
	var radius_m: float
	var lower_m: float
	var lower_squared: float
	var upper_squared: float
	var upper_m: float

	func select(camera_position: Vector3) -> Dictionary:
		var center_distance := camera_position.distance_to(center)
		if center_distance - radius_m > upper_m or center_distance + radius_m < lower_m:
			compact.visible_instance_count = 0
			return {"selected": 0, "writes": 0, "scanned": 0}
		var wanted := PackedInt32Array()
		for index: int in centers.size():
			var distance_squared := camera_position.distance_squared_to(centers[index])
			if distance_squared >= lower_squared and distance_squared <= upper_squared:
				wanted.append(index)
		var writes := 0
		for slot: int in wanted.size():
			if slot < selected.size() and selected[slot] == wanted[slot]:
				continue
			var at := wanted[slot] * STRIDE
			var basis := Basis(Vector3(source[at], source[at + 4], source[at + 8]), Vector3(source[at + 1], source[at + 5], source[at + 9]), Vector3(source[at + 2], source[at + 6], source[at + 10]))
			compact.set_instance_transform(slot, Transform3D(basis, Vector3(source[at + 3], source[at + 7], source[at + 11])))
			compact.set_instance_color(slot, Color(source[at + 12], source[at + 13], source[at + 14], source[at + 15]))
			compact.set_instance_custom_data(slot, Color(source[at + 16], source[at + 17], source[at + 18], source[at + 19]))
			writes += 1
		selected = wanted
		compact.visible_instance_count = wanted.size()
		return {"selected": wanted.size(), "writes": writes, "scanned": centers.size()}

class Bin extends RefCounted:
	var batches: Array[Batch] = []
	var center: Vector3
	var radius_m: float
	var upper_m := 0.0
	var bounds: AABB
	var active := false

var _bins: Array[Bin] = []
var _batches: Array[Batch] = []
var _enabled := true
var _last_position := Vector3(INF, INF, INF)
var _camera_id := 0
var _metrics: Dictionary = {}

func configure(vegetation: Node) -> void:
	assert(_batches.is_empty(), "Tree submission configures once")
	var bins_by_position: Dictionary = {}
	var source_instances := 0
	for child: Node in vegetation.get_children():
		if not child is MultiMeshInstance3D or not bool(child.get_meta("instance_lod", false)):
			continue
		var begin := float(child.get_meta("lod_begin_m", 180.0))
		if begin >= 180.0:
			continue
		var original: MultiMesh = child.multimesh
		var material := original.mesh.surface_get_material(0) as ShaderMaterial
		assert(material != null and bool(material.get_shader_parameter("instance_lod")), "Tree submission requires distance-aware materials")
		var end := float(material.get_shader_parameter("lod_end_m"))
		var batch := Batch.new()
		batch.node = child
		batch.original = original
		batch.source = original.buffer
		assert(original.use_colors and original.use_custom_data and batch.source.size() == original.instance_count * STRIDE, "Tree submission requires transform/color/custom records")
		batch.compact = original.duplicate(false)
		batch.compact.visible_instance_count = 0
		batch.lower_m = maxf(0.0, begin - clampf(begin * 0.1, 2.0, 18.0) - GUARD_M)
		batch.lower_squared = batch.lower_m * batch.lower_m
		batch.upper_m = end + clampf(end * 0.1, 2.0, 18.0) + GUARD_M
		batch.upper_squared = batch.upper_m * batch.upper_m
		var bin: Bin = bins_by_position.get(child.position)
		if bin == null:
			bin = Bin.new()
			bins_by_position[child.position] = bin
			_bins.append(bin)
		var batch_bounds := AABB()
		for index: int in original.instance_count:
			var at := index * STRIDE + 16
			var center := Vector3(batch.source[at], batch.source[at + 1], batch.source[at + 2])
			batch.centers.append(center)
			batch_bounds = AABB(center, Vector3.ZERO) if index == 0 else batch_bounds.expand(center)
			bin.bounds = AABB(center, Vector3.ZERO) if bin.batches.is_empty() and index == 0 else bin.bounds.expand(center)
		batch.center = batch_bounds.get_center()
		batch.radius_m = batch_bounds.size.length() * 0.5
		bin.batches.append(batch)
		bin.upper_m = maxf(bin.upper_m, batch.upper_m)
		_batches.append(batch)
		child.multimesh = batch.compact
		source_instances += original.instance_count
	for bin: Bin in _bins:
		bin.center = bin.bounds.get_center()
		bin.radius_m = bin.bounds.size.length() * 0.5
	_metrics = {"bins": _bins.size(), "batches": _batches.size(), "source_instances": source_instances, "additional_instance_buffer_capacity_bytes": source_instances * STRIDE * 4, "cached_source_record_bytes": source_instances * STRIDE * 4, "cached_center_bytes": source_instances * 12, "updates": 0}
	RenderingServer.frame_pre_draw.connect(_prepare)
	_prepare()

func set_enabled(value: bool) -> void:
	if _enabled == value:
		return
	_enabled = value
	for batch: Batch in _batches:
		batch.node.multimesh = batch.compact if value else batch.original
	_last_position = Vector3(INF, INF, INF)
	_prepare()

func _prepare() -> void:
	if not _enabled or not is_inside_tree():
		return
	var camera := get_viewport().get_camera_3d()
	if camera == null:
		return
	var changed_camera := camera.get_instance_id() != _camera_id
	_camera_id = camera.get_instance_id()
	refresh(camera.global_position, changed_camera)

func refresh(camera_position: Vector3, force := false) -> void:
	if not _enabled or (not force and camera_position.distance_squared_to(_last_position) <= MOVE_LIMIT_M * MOVE_LIMIT_M):
		return
	var started := Time.get_ticks_usec()
	var scanned := 0
	var writes := 0
	var selected := 0
	var active_bins := 0
	for bin: Bin in _bins:
		var reach := bin.radius_m + bin.upper_m
		if camera_position.distance_squared_to(bin.center) > reach * reach:
			if bin.active:
				for batch: Batch in bin.batches:
					batch.compact.visible_instance_count = 0
				bin.active = false
			continue
		active_bins += 1
		bin.active = true
		for batch: Batch in bin.batches:
			var result := batch.select(camera_position)
			scanned += int(result.scanned)
			writes += int(result.writes)
			selected += int(result.selected)
	_last_position = camera_position
	_metrics.merge({"updates": int(_metrics.get("updates", 0)) + 1, "scanned_instances": scanned, "selected_instances": selected, "changed_slots": writes, "active_bins": active_bins, "update_us": Time.get_ticks_usec() - started}, true)

func metrics() -> Dictionary:
	return _metrics.duplicate()

func _exit_tree() -> void:
	if RenderingServer.frame_pre_draw.is_connected(_prepare):
		RenderingServer.frame_pre_draw.disconnect(_prepare)
