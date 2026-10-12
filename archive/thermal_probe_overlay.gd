extends Node3D

## Optional simulated-temperature markers.
## Fixed color scale supports comparison between control and pulse runs.
## Not a natural water-color shader and not a visitor-safety instrument.

@export var ecosystem_path: NodePath
@export var temperature_min_c: float = 17.0
@export var temperature_max_c: float = 22.0

var _ecosystem: Node
var _markers: Array[MeshInstance3D] = []

func _ready() -> void:
	_ecosystem = get_node_or_null(ecosystem_path)
	visible = false
	if _ecosystem == null:
		push_error("Thermal overlay has no ecosystem node.")
		set_process(false)
		return
	if temperature_max_c <= temperature_min_c:
		push_error("Thermal overlay requires increasing temperature bounds.")
		set_process(false)
		return
	if not _ecosystem.has_method("thermal_probe_records"):
		set_process(false)

func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey:
		if event.pressed and not event.echo and event.physical_keycode == KEY_H:
			visible = not visible

func _process(_delta: float) -> void:
	if not visible:
		return

	var records: Array = _ecosystem.call("thermal_probe_records")
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