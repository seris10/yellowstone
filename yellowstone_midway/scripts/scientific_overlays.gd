extends Node3D
## World-space overlays for Python-published scientific sidecars. Each overlay is a hidden MeshInstance3D or child container that toggles on a bound key.

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
	# Build an ImageTexture from temperature_grid_c and lay it flat over the plume footprint. Hot-to-cool ramp lives in the shader so the data drives color directly.
	var grid: Variant = _plume_doc.get("temperature_grid_c")
	if not grid is Array or (grid as Array).is_empty():
		return
	var rows: Array = grid
	var nz: int = rows.size()
	var nx: int = (rows[0] as Array).size()
	if nx <= 0:
		return
	var image: Image = Image.create(nx, nz, false, Image.FORMAT_RF)
	# Format_rf is a single-channel float; sentinel out-of-range values clamp to the ambient temperature so the ramp holds the plume shape.
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
	# Translucent albedo path.
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
	# Cells carry id and silica_saturation_index but no x/z; project the sequence uniformly along the mapped Firehole mainline, since the publish side (geochemistry.diagnose_replay_frame) walks the river_replay cells in reach order.
	var cells: Variant = _geochem_doc.get("cells")
	if not cells is Array or (cells as Array).is_empty():
		return
	var rivers: Array = []
	if world != null and world.get("spec") is Dictionary:
		var spec: Dictionary = world.get("spec")
		rivers = spec.get("rivers", [])
	var mainline: Array = []
	for river: Dictionary in rivers:
		if str(river.get("name", "")).to_upper() == "FIREHOLE RIVER":
			mainline = river.get("points", [])
			break
	if mainline.is_empty():
		return
	# Cumulative chainage along mainline.
	var chainage: PackedFloat32Array = PackedFloat32Array()
	chainage.push_back(0.0)
	for i: int in range(1, mainline.size()):
		var a: Array = mainline[i - 1]
		var b: Array = mainline[i]
		var dx: float = float(b[0]) - float(a[0])
		var dz: float = float(b[2]) - float(a[2])
		chainage.push_back(chainage[i - 1] + sqrt(dx * dx + dz * dz))
	var total: float = chainage[chainage.size() - 1]
	var root: Node3D = Node3D.new()
	root.name = "GeochemistryMarkers"
	root.visible = false
	add_child(root)
	_geochem_root = root
	var n: int = (cells as Array).size()
	# Downsample to at most 128 markers so the overlay stays readable on long rivers.
	var step_i: int = maxi(1, int(ceil(float(n) / 128.0)))
	for k: int in range(0, n, step_i):
		var cell_dict: Variant = (cells as Array)[k]
		if not cell_dict is Dictionary:
			continue
		var si: Variant = cell_dict.get("silica_saturation_index")
		var temp_c: float = float(cell_dict.get("temperature_c", 0.0))
		var frac: float = float(k) / float(maxi(n - 1, 1))
		# Walk chainage to find segment at s = frac * total.
		var s: float = frac * total
		var segment: int = 0
		for i: int in range(chainage.size() - 1):
			if chainage[i + 1] >= s:
				segment = i
				break
		var seg_len: float = maxf(chainage[segment + 1] - chainage[segment], 0.001)
		var t: float = clampf((s - chainage[segment]) / seg_len, 0.0, 1.0)
		var pa: Array = mainline[segment]
		var pb: Array = mainline[segment + 1]
		var pos: Vector3 = Vector3(lerpf(float(pa[0]), float(pb[0]), t), lerpf(float(pa[1]), float(pb[1]), t) + GEOCHEM_MARKER_HEIGHT_M * 0.5, lerpf(float(pa[2]), float(pb[2]), t))
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
			# Mapping -1 undersaturated (blue), 0 at equilibrium (gray), +1 oversaturated (orange).
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
	# Overland field today publishes only basin-scale scalars (status, max_depth_m, outflow_m3). A single translucent plane across the authored footprint shows presence and depth magnitude; absence of per-cell data is honest.
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
	# Blue tint deepening with max depth; 0.01 m dusting is faint, 0.5 m is strongly tinted.
	var intensity: float = clampf(depth / 0.5, 0.05, 1.0)
	mat.albedo_color = Color(0.26, 0.58, 0.80, 0.08 + 0.25 * intensity)
	instance.material_override = mat
	instance.visible = false
	add_child(instance)
	_overland_overlay = instance

func _build_groundwater_overlay() -> void:
	# Groundwater field publishes a status string and (eventually) head values. Until per-cell head arrives, visualize as a faint ground-tinted plane with intensity proportional to any available aggregate_head_m.
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
	# Legend lines the HUD may surface alongside the overlay toggle; each line names a unit so the color is bound to measured values.
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
