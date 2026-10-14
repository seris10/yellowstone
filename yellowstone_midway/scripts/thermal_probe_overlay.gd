extends Node3D

## Fixed temperature scale for the buffered river field.

@export var ecosystem_path: NodePath
@export var temperature_min_c: float = 17.0
@export var temperature_max_c: float = 22.0

var _ecosystem: Node
var _markers: Array[MeshInstance3D] = []
@export var ribbon_offset_m: float = 0.5
var _ribbon: MeshInstance3D
var _ribbon_material: StandardMaterial3D

func _ready() -> void:
	visible = false
	if ecosystem_path.is_empty():
		push_warning("Thermal overlay has no ecosystem_path; markers will stay hidden.")
	if temperature_max_c <= temperature_min_c:
		push_error("Thermal overlay requires increasing temperature bounds.")
		set_process(false)
		return
	# Ecosystem node created at runtime by world.gd; resolve lazily in _process.

func _process(_delta: float) -> void:
	if not visible:
		return
	if _ecosystem == null:
		_ecosystem = get_node_or_null(ecosystem_path)
		if _ecosystem == null:
			return
		if not _ecosystem.has_method("thermal_probe_records"):
			push_error("Thermal overlay ecosystem has no probe records.")
			_ecosystem = null
			set_process(false)
			return

	var records: Array = _ecosystem.call("thermal_probe_records")
	_update_ribbon(records)
	if _markers.size() != records.size():
		for marker: MeshInstance3D in _markers:
			marker.queue_free()
		_markers.clear()

		var mesh: SphereMesh = SphereMesh.new()
		mesh.radius = 0.22
		mesh.height = 0.44
		mesh.radial_segments = 8
		mesh.rings = 4

		for record: Dictionary in records:
			var marker: MeshInstance3D = MeshInstance3D.new()
			marker.mesh = mesh
			var material: StandardMaterial3D = StandardMaterial3D.new()
			material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			marker.material_override = material
			marker.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			var xyz: Array = record["position_xyz"]
			marker.position = to_local(
				Vector3(float(xyz[0]), float(xyz[1]) + 0.45, float(xyz[2]))
			)
			add_child(marker)
			_markers.append(marker)

	for i: int in range(records.size()):
		var temperature: float = float(records[i]["temperature_c"])
		var fraction: float = clampf(
			(temperature - temperature_min_c)
			/ (temperature_max_c - temperature_min_c),
			0.0, 1.0
		)
		var material: StandardMaterial3D = _markers[i].material_override
		material.albedo_color = Color(0.15, 0.45, 1.0).lerp(
			Color(1.0, 0.18, 0.08), fraction
		)
		_markers[i].set_meta("simulated_temperature_c", temperature)
		_markers[i].set_meta("cell_id", records[i]["cell_id"])
func _temperature_color(temperature: float) -> Color:
	var fraction: float = clampf((temperature - temperature_min_c) / (temperature_max_c - temperature_min_c), 0.0, 1.0)
	return Color(0.15, 0.45, 1.0).lerp(Color(1.0, 0.18, 0.08), fraction)

func _update_ribbon(records: Array) -> void:
	if records.size() < 2:
		return
	if _ribbon == null:
		_ribbon = MeshInstance3D.new()
		_ribbon.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var material: StandardMaterial3D = StandardMaterial3D.new()
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.vertex_color_use_as_albedo = true
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		_ribbon_material = material
		add_child(_ribbon)
	var vertices: PackedVector3Array = PackedVector3Array()
	var colors: PackedColorArray = PackedColorArray()
	for i: int in range(records.size() - 1):
		var pa: Array = records[i].position_xyz
		var pb: Array = records[i + 1].position_xyz
		var a: Vector3 = Vector3(float(pa[0]), float(pa[1]) + 0.2, float(pa[2]))
		var b: Vector3 = Vector3(float(pb[0]), float(pb[1]) + 0.2, float(pb[2]))
		var tangent: Vector3 = Vector3(b.x - a.x, 0.0, b.z - a.z).normalized()
		var side: Vector3 = Vector3(-tangent.z, 0.0, tangent.x)
		a += side * ribbon_offset_m
		b += side * ribbon_offset_m
		var width: Vector3 = side * 0.45
		for index: int in [0, 1, 2, 0, 2, 3]:
			var point: Vector3 = [a - width, a + width, b + width, b - width][index]
			vertices.append(to_local(point))
			colors.append(_temperature_color(float(records[i if index < 2 else i + 1].temperature_c)))
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_COLOR] = colors
	var mesh: ArrayMesh = ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, _ribbon_material)
	_ribbon.mesh = mesh
