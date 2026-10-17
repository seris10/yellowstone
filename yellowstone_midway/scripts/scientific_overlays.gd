extends Node3D
## World-space overlays for published scientific fields.

var world: Node3D
var _plume_overlay: MeshInstance3D
var _geochem_root: Node3D
var _overland_overlay: MeshInstance3D
var _groundwater_overlay: MeshInstance3D
var _plume_doc: Dictionary = {}
var _geochem_doc: Dictionary = {}
var _overland_doc: Dictionary = {}
var _groundwater_doc: Dictionary = {}

const PLUME_Y_LIFT_M: float = 0.6
const OVERLAY_Y_LIFT_M: float = 0.35
const GEOCHEM_MARKER_HEIGHT_M: float = 1.6

func bind(parent: Node3D, plume: Dictionary, geochem: Dictionary, overland: Dictionary, groundwater: Dictionary) -> void:
	world = parent
	_plume_doc = plume
	_geochem_doc = geochem
	_overland_doc = overland
	_groundwater_doc = groundwater
	if not _plume_doc.is_empty():
		_build_plume_overlay()
	if not _geochem_doc.is_empty():
		_build_geochemistry_markers()
	if not _overland_doc.is_empty():
		_build_overland_overlay()
	if not _groundwater_doc.is_empty():
		_build_groundwater_overlay()

func reload(parent: Node3D, plume: Dictionary, geochem: Dictionary, overland: Dictionary, groundwater: Dictionary) -> void:
	var visible_before: Array[bool] = []
	for node: Node3D in [_plume_overlay, _geochem_root, _overland_overlay, _groundwater_overlay]:
		visible_before.append(node != null and node.visible)
		if node != null:
			remove_child(node)
			node.queue_free()
	_plume_overlay = null
	_geochem_root = null
	_overland_overlay = null
	_groundwater_overlay = null
	bind(parent, plume, geochem, overland, groundwater)
	var nodes: Array = [_plume_overlay, _geochem_root, _overland_overlay, _groundwater_overlay]
	for i: int in range(nodes.size()):
		if nodes[i] != null:
			nodes[i].visible = visible_before[i]

func _build_plume_overlay() -> void:
	# Map the temperature grid onto the plume footprint.
	var grid: Variant = _plume_doc.get("temperature_grid_c")
	if not grid is Array or (grid as Array).is_empty():
		return
	var rows: Array = grid
	var nz: int = rows.size()
	var nx: int = (rows[0] as Array).size()
	if nx <= 0:
		return
	var image: Image = Image.create(nx, nz, false, Image.FORMAT_RF)
	# Missing temperature cells use the river temperature.
	var hot_c: float = float(_plume_doc.get("hot_source_c", 85.0))
	var cool_c: float = float(_plume_doc.get("river_c", 15.0))
	for j: int in nz:
		var row: Array = rows[j]
		for i: int in nx:
			var v: float = float(row[i]) if i < row.size() else cool_c
			image.set_pixel(i, j, Color(v, 0.0, 0.0, 0.0))
	var texture: ImageTexture = ImageTexture.create_from_image(image)
	var axes_x: Array = _plume_doc.get("axes_x_m", [])
	var axes_z: Array = _plume_doc.get("axes_z_m", [])
	var x_min: float = -300.0
	var x_max: float = 300.0
	var z_min: float = -300.0
	var z_max: float = 300.0
	if axes_x is Array and axes_x.size() >= 2:
		x_min = float(axes_x[0])
		x_max = float(axes_x[axes_x.size() - 1])
	if axes_z is Array and axes_z.size() >= 2:
		z_min = float(axes_z[0])
		z_max = float(axes_z[axes_z.size() - 1])
	var origin_xz: Array = _plume_doc.get("origin_xz", [0.0, -60.0])
	var cx: float = float(origin_xz[0]) if origin_xz.size() > 0 else 0.0
	var cz: float = float(origin_xz[1]) if origin_xz.size() > 1 else -60.0
	var size_x: float = x_max - x_min
	var size_z: float = z_max - z_min
	var quad: QuadMesh = QuadMesh.new()
	quad.size = Vector2(size_x, size_z)
	quad.orientation = PlaneMesh.FACE_Y
	var shader: Shader = Shader.new()
	shader.code = """
		shader_type spatial;
		render_mode cull_disabled, unshaded, depth_draw_opaque;
		uniform sampler2D temperature : filter_linear, repeat_disable;
		uniform float hot_c = 85.0;
		uniform float cool_c = 15.0;
		uniform float alpha_floor = 0.0;
		void fragment() {
			float t = texture(temperature, UV).r;
			float warmth = clamp((t - cool_c) / max(hot_c - cool_c, 0.001), 0.0, 1.0);
			vec3 cool_rgb = vec3(0.10, 0.26, 0.60);
			vec3 mid_rgb = vec3(0.90, 0.73, 0.14);
			vec3 hot_rgb = vec3(0.95, 0.26, 0.12);
			vec3 color = mix(cool_rgb, mid_rgb, smoothstep(0.0, 0.5, warmth));
			color = mix(color, hot_rgb, smoothstep(0.5, 1.0, warmth));
			ALBEDO = color;
			ALPHA = max(alpha_floor, 0.45 + warmth * 0.35);
		}
	"""
	var mat: ShaderMaterial = ShaderMaterial.new()
	mat.shader = shader
	mat.set_shader_parameter("temperature", texture)
	mat.set_shader_parameter("hot_c", hot_c)
	mat.set_shader_parameter("cool_c", cool_c)
	var instance: MeshInstance3D = MeshInstance3D.new()
	instance.name = "PlumeFieldOverlay"
	instance.mesh = quad
	instance.material_override = mat
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	instance.position = Vector3(cx, PLUME_Y_LIFT_M, cz)
	instance.visible = false
	add_child(instance)
	_plume_overlay = instance

func _build_geochemistry_markers() -> void:
	var cells: Variant = _geochem_doc.get("cells")
	if not cells is Array or (cells as Array).is_empty():
		return
	var positions: Dictionary = {}
	var replay_cells: Variant = world.ecosystem.get("_cells") if world != null and world.ecosystem != null else []
	if not replay_cells is Array:
		return
	for cell: Dictionary in replay_cells:
		var point: Variant = cell.get("position_xyz")
		if point is Array and point.size() == 3:
			positions[str(cell.id)] = Vector3(point[0], point[1], point[2])
	var root: Node3D = Node3D.new()
	root.name = "GeochemistryMarkers"
	root.visible = false
	add_child(root)
	_geochem_root = root
	var n: int = (cells as Array).size()
	# Limit the overlay to 128 markers.
	var step_i: int = maxi(1, int(ceil(float(n) / 128.0)))
	for k: int in range(0, n, step_i):
		var cell_dict: Variant = (cells as Array)[k]
		if not cell_dict is Dictionary:
			continue
		var si: Variant = cell_dict.get("silica_saturation_index")
		var temp_c: float = float(cell_dict.get("temperature_c", 0.0))
		var identity := str(cell_dict.get("cell", ""))
		if not positions.has(identity):
			push_warning("Geochemistry cell has no published position: " + identity)
			continue
		var pos: Vector3 = positions[identity] + Vector3.UP * GEOCHEM_MARKER_HEIGHT_M * 0.5
		var marker: MeshInstance3D = MeshInstance3D.new()
		var cyl: CylinderMesh = CylinderMesh.new()
		cyl.top_radius = 0.08
		cyl.bottom_radius = 0.08
		cyl.height = GEOCHEM_MARKER_HEIGHT_M
		cyl.radial_segments = 6
		marker.mesh = cyl
		var mat: StandardMaterial3D = StandardMaterial3D.new()
		mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		if si == null:
			mat.albedo_color = Color(0.55, 0.55, 0.55, 0.80)
		else:
			var si_val: float = float(si)
			# Map saturation index -1 to blue and +1 to orange.
			var warm: float = clampf(si_val, -1.0, 1.0) * 0.5 + 0.5
			var color_cold: Color = Color(0.20, 0.42, 0.86, 0.85)
			var color_hot: Color = Color(0.90, 0.52, 0.12, 0.85)
			mat.albedo_color = color_cold.lerp(color_hot, warm)
		marker.material_override = mat
		marker.position = pos
		marker.set_meta("cell_id", str(cell_dict.get("cell", "")))
		marker.set_meta("silica_saturation_index", si)
		marker.set_meta("temperature_c", temp_c)
		marker.visibility_range_end = 420.0
		marker.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		root.add_child(marker)

func _build_overland_overlay() -> void:
	# Display basin-scale runoff depth on the authored footprint.
	var sr: Variant = _overland_doc.get("surface_runoff")
	var depth: float = 0.0
	if sr is Dictionary:
		depth = float(sr.get("max_depth_m", 0.0))
	elif _overland_doc.has("max_depth_m"):
		depth = float(_overland_doc.get("max_depth_m", 0.0))
	var instance: MeshInstance3D = MeshInstance3D.new()
	instance.name = "OverlandFieldOverlay"
	var quad: QuadMesh = QuadMesh.new()
	quad.size = Vector2(4096.0, 4096.0)
	quad.orientation = PlaneMesh.FACE_Y
	instance.mesh = quad
	instance.position = Vector3(0.0, OVERLAY_Y_LIFT_M, 0.0)
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var mat: StandardMaterial3D = StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	# Scale blue tint with maximum depth.
	var intensity: float = clampf(depth / 0.5, 0.05, 1.0)
	mat.albedo_color = Color(0.26, 0.58, 0.80, 0.08 + 0.25 * intensity)
	instance.material_override = mat
	instance.visible = false
	add_child(instance)
	_overland_overlay = instance

func _build_groundwater_overlay() -> void:
	# Scale groundwater display opacity by aggregate head.
	var payload: Variant = _groundwater_doc.get("payload")
	var head_m: float = 0.0
	if payload is Dictionary:
		head_m = float(payload.get("aggregate_head_m", payload.get("mean_head_m", 0.0)))
	var instance: MeshInstance3D = MeshInstance3D.new()
	instance.name = "GroundwaterFieldOverlay"
	var quad: QuadMesh = QuadMesh.new()
	quad.size = Vector2(4096.0, 4096.0)
	quad.orientation = PlaneMesh.FACE_Y
	instance.mesh = quad
	instance.position = Vector3(0.0, OVERLAY_Y_LIFT_M * 0.5, 0.0)
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var mat: StandardMaterial3D = StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	var intensity: float = clampf(abs(head_m) / 10.0, 0.05, 1.0)
	mat.albedo_color = Color(0.40, 0.60, 0.42, 0.06 + 0.18 * intensity)
	instance.material_override = mat
	instance.visible = false
	add_child(instance)
	_groundwater_overlay = instance

func toggle_plume() -> bool:
	if _plume_overlay == null:
		return false
	_plume_overlay.visible = not _plume_overlay.visible
	return _plume_overlay.visible

func toggle_geochemistry() -> bool:
	if _geochem_root == null:
		return false
	_geochem_root.visible = not _geochem_root.visible
	return _geochem_root.visible

func toggle_overland() -> bool:
	if _overland_overlay == null:
		return false
	_overland_overlay.visible = not _overland_overlay.visible
	return _overland_overlay.visible

func toggle_groundwater() -> bool:
	if _groundwater_overlay == null:
		return false
	_groundwater_overlay.visible = not _groundwater_overlay.visible
	return _groundwater_overlay.visible

func legend_lines() -> Array:
	# Return overlay legend text with units.
	var out: Array = []
	if _plume_overlay != null:
		out.append("P plume field (deg C): blue cool, yellow 20-50, orange above 70; grid %dx%d" % [int(_plume_doc.get("nx", 0)), int(_plume_doc.get("nz", 0))])
	if _geochem_root != null:
		out.append("G geochemistry (silica saturation index, log10): blue undersaturated, orange oversaturated")
	if _overland_overlay != null:
		out.append("J overland (depth m): sheet tint intensity scales with max_depth_m")
	if _groundwater_overlay != null:
		out.append("L groundwater: tint intensity scales with aggregate head magnitude")
	return out
