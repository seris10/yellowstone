class_name MidwayCoreTerrain
extends Node3D

const GroundMaterials = preload("res://scripts/terrain_materials.gd")
const OutflowFilter = preload("res://scripts/outflow_filter.gd")
const WaterCut = preload("res://scripts/water_polygon_cut.gd")
const RiverTerrain = preload("res://scripts/river_terrain.gd")
const ReleaseData = preload("res://scripts/release_data.gd")

const CORE_JSON := "res://data/core_terrain/core_terrain.json"
const CORE_HEIGHTFIELD := "res://data/core_terrain/core_heightfield.f32"
const CORE_MICRORELIEF := "res://data/core_terrain/core_microrelief.f32"
const CORE_NORMAL := "res://data/core_terrain/core_normal.png"
const STITCH_JSON := "res://data/core_terrain/stitch.json"
const DETAIL_PHOTO := "res://references/midway_orthophoto_detail.jpg"
const DETAIL_PHOTO_JSON := "res://references/midway_orthophoto_detail.json"
const MESH_DECIMATION: int = 2
# Keeps render heights aligned with the collision surface.
const CORE_RENDER_LIFT_M: float = 0.0

var core_meta: Dictionary = {}
var stitch_meta: Dictionary = {}
var _tile_mesh_instance: MeshInstance3D
var _tile_collision_body: StaticBody3D
var _nx: int = 0
var _nz: int = 0
var _cell_m: float = 1.0
var _x_min_m: float = 0.0
var _z_min_m: float = 0.0
var _x_max_m: float = 0.0
var _z_max_m: float = 0.0
var _vertical_origin_m: float = 0.0
var river_bed_report: Dictionary = {}
var _heights_full: PackedFloat32Array
var _mat_material: ShaderMaterial
var _normal_image: Image
var _bound_outflow_ids: Array[int] = []
var _built: bool = false
var _loaded_from_runtime: bool = false
var _render_cut_complete: bool = false
var _render_cut_root_id: int = 0
var _render_cut_report: Dictionary = {}
var _pool_cut_source_mesh: ArrayMesh
var _pool_cut_report: Dictionary = {}
var _shoreline_mesh_instance: MeshInstance3D

func cut_open_water(pools: Array) -> Dictionary:
	if _tile_mesh_instance == null:
		return {}
	if _pool_cut_source_mesh == null:
		_pool_cut_source_mesh = _tile_mesh_instance.mesh
	var result := WaterCut.cut(_pool_cut_source_mesh, _tile_mesh_instance.global_transform, pools)
	if not bool(result.get("ok", false)):
		push_error("core_terrain: water render cut failed: " + str(result.get("reason", "unknown")))
		_pool_cut_report = result
		return result.duplicate(true)
	_tile_mesh_instance.mesh = result.mesh
	if _shoreline_mesh_instance == null:
		_shoreline_mesh_instance = MeshInstance3D.new()
		_shoreline_mesh_instance.name = "MappedWaterRenderInterface"
		_tile_mesh_instance.add_child(_shoreline_mesh_instance)
		_shoreline_mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		_shoreline_mesh_instance.set_meta("value_class", "authored_render_interface")
	_shoreline_mesh_instance.mesh = result.shoreline_mesh
	result.erase("mesh")
	result.erase("shoreline_mesh")
	_pool_cut_report = result
	return _pool_cut_report.duplicate(true)

func open_water_cut_status() -> Dictionary:
	return _pool_cut_report.duplicate(true)

func built() -> bool:
	return _built

func build(mat_surface: Variant) -> bool:
	# Build the core render and collision tiles.
	if _built:
		return true
	if not _load_metadata():
		return false
	if not _load_heights():
		return false
	_mat_material = _make_mat_material(mat_surface)
	if _mat_material == null:
		return false
	_build_mesh_tile()
	_build_collision_tile()
	_mark_terrain_tile_grouping()
	_loaded_from_runtime = true
	_built = true
	return true

func cut_master_tiles(root_scene: Node) -> int:
	if not _built:
		return 0
	if _render_cut_complete and _render_cut_root_id == root_scene.get_instance_id():
		return int(_render_cut_report.get("collision_tiles", 0))
	_render_cut_complete = false
	_render_cut_report = {"complete": false, "collision_complete": false, "tiles": [], "failures": [], "removed_triangles": 0, "collision_tiles": 0, "fallback_exterior_collision_preserved": true}
	var tiles_parent: Node = root_scene.find_child("TerrainTiles", true, false)
	if tiles_parent == null:
		push_warning("core_terrain: AuthoredMidway/TerrainTiles not found; master cut skipped.")
		_render_cut_report.failures.append("TerrainTiles missing")
		return 0
	var prepared: Array[Dictionary] = []
	for tile_node in tiles_parent.get_children():
		if not tile_node is MeshInstance3D:
			continue
		var mi: MeshInstance3D = tile_node as MeshInstance3D
		var tile_x_min: float = mi.position.x
		var tile_z_min: float = mi.position.z
		var tile_x_max: float = tile_x_min + 256.0
		var tile_z_max: float = tile_z_min + 256.0
		if tile_x_max <= _x_min_m or tile_x_min >= _x_max_m:
			continue
		if tile_z_max <= _z_min_m or tile_z_min >= _z_max_m:
			continue
		var result := _prepare_render_cut(mi.mesh, mi.global_transform)
		result["tile"] = str(mi.name)
		if not result.ok:
			_render_cut_report.failures.append(str(mi.name) + ": " + str(result.reason))
		else:
			var collision := _prepare_collision_cut(mi, result.mesh)
			if not collision.ok:
				_render_cut_report.failures.append(str(mi.name) + ": " + str(collision.reason))
			else:
				prepared.append({"instance": mi, "mesh": result.mesh, "collision": collision})
			result["collision"] = {"ok": collision.ok, "retained_triangles": collision.get("retained_triangles", 0), "disabled": collision.get("disabled", false), "reason": collision.get("reason", "")}
			_render_cut_report.removed_triangles += result.removed_triangles
		result.erase("mesh")
		_render_cut_report.tiles.append(result)
	var expected: int = int(round((_x_max_m - _x_min_m) * (_z_max_m - _z_min_m) / 16.0)) * 2
	_render_cut_report["expected_removed_triangles"] = expected
	if int(_render_cut_report.removed_triangles) != expected:
		_render_cut_report.failures.append("render triangle coverage disagrees with the core footprint")
	if _render_cut_report.failures.is_empty() and not prepared.is_empty():
		for entry: Dictionary in prepared:
			(entry.instance as MeshInstance3D).mesh = entry.mesh
			var collision: Dictionary = entry.collision
			var col: CollisionShape3D = collision.node
			if collision.disabled:
				col.disabled = true
			else:
				col.shape = collision.shape
				col.transform = Transform3D.IDENTITY
				col.disabled = false
		_render_cut_complete = true
		_render_cut_root_id = root_scene.get_instance_id()
		_render_cut_report.complete = true
		_render_cut_report.collision_complete = true
		_render_cut_report.collision_tiles = prepared.size()
		_render_cut_report["collision_geometry"] = "retained_render_triangles"
	else:
		push_warning("core_terrain: master cut fallback; original exterior collision preserved: %s" % str(_render_cut_report.failures))
	print("core_terrain: render_cut complete=", _render_cut_complete, " triangles=", _render_cut_report.removed_triangles)
	return int(_render_cut_report.collision_tiles)

func render_cut_status() -> Dictionary:
	return _render_cut_report.duplicate(true)

func _master_cut_grid_aligned() -> bool:
	for value: float in [_x_min_m, _x_max_m, _z_min_m, _z_max_m]:
		if absf(value / 4.0 - round(value / 4.0)) > 0.000001:
			return false
	return _x_max_m > _x_min_m and _z_max_m > _z_min_m

func _inside_core(point: Vector3) -> bool:
	return point.x >= _x_min_m and point.x <= _x_max_m and point.z >= _z_min_m and point.z <= _z_max_m

func _prepare_render_cut(source: Mesh, transform: Transform3D) -> Dictionary:
	if not _master_cut_grid_aligned():
		return {"ok": false, "reason": "core bounds are not aligned to the 4 m master grid"}
	if not transform.basis.is_equal_approx(Basis.IDENTITY):
		return {"ok": false, "reason": "master mesh basis requires canonical world axes"}
	if not source is ArrayMesh:
		return {"ok": false, "reason": "master mesh is not an ArrayMesh"}
	var array_mesh: ArrayMesh = source as ArrayMesh
	if array_mesh.get_surface_count() != 1 or array_mesh.get_blend_shape_count() != 0:
		return {"ok": false, "reason": "master mesh requires one ArrayMesh surface without blend shapes"}
	if array_mesh.shadow_mesh != null:
		return {"ok": false, "reason": "master auxiliary shadow geometry requires a separate cut"}
	if array_mesh.surface_get_primitive_type(0) != Mesh.PRIMITIVE_TRIANGLES:
		return {"ok": false, "reason": "master surface primitive is not triangles"}
	var arrays: Array = source.surface_get_arrays(0).duplicate(true)
	if not arrays[Mesh.ARRAY_VERTEX] is PackedVector3Array or not arrays[Mesh.ARRAY_INDEX] is PackedInt32Array:
		return {"ok": false, "reason": "master surface requires indexed Vector3 vertices"}
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	if indices.is_empty() or indices.size() % 3 != 0:
		return {"ok": false, "reason": "master triangle indices are empty or incomplete"}
	var world_vertices := PackedVector3Array()
	var inside := PackedByteArray()
	world_vertices.resize(vertices.size())
	inside.resize(vertices.size())
	for i in vertices.size():
		var point: Vector3 = transform * vertices[i]
		if not point.is_finite() or absf(point.x / 4.0 - round(point.x / 4.0)) > 0.000001 or absf(point.z / 4.0 - round(point.z / 4.0)) > 0.000001:
			return {"ok": false, "reason": "master vertices are not on the world 4 m grid"}
		world_vertices[i] = point
		inside[i] = 1 if _inside_core(point) else 0
	var retained := PackedInt32Array()
	var removed: int = 0
	for k in range(0, indices.size(), 3):
		var ia: int = indices[k]
		var ib: int = indices[k + 1]
		var ic: int = indices[k + 2]
		if mini(ia, mini(ib, ic)) < 0 or maxi(ia, maxi(ib, ic)) >= vertices.size():
			return {"ok": false, "reason": "master triangle index is outside the vertex array"}
		var a: Vector3 = world_vertices[ia]
		var b: Vector3 = world_vertices[ib]
		var c: Vector3 = world_vertices[ic]
		if maxf(a.x, maxf(b.x, c.x)) - minf(a.x, minf(b.x, c.x)) > 4.000001 or maxf(a.z, maxf(b.z, c.z)) - minf(a.z, minf(b.z, c.z)) > 4.000001:
			return {"ok": false, "reason": "master triangle spans more than one grid cell"}
		if inside[ia] == 1 and inside[ib] == 1 and inside[ic] == 1:
			removed += 1
		else:
			retained.append_array(PackedInt32Array([ia, ib, ic]))
	if retained.is_empty():
		return {"ok": true, "mesh": ArrayMesh.new(), "removed_triangles": removed, "retained_triangles": 0, "original_triangles": indices.size() / 3}
	var stored: Variant = array_mesh.get("_surfaces")
	if not stored is Array or stored.size() != 1:
		return {"ok": false, "reason": "master stored surface buffers are unavailable"}
	var surface: Dictionary = stored[0].duplicate(true)
	if not surface.get("index_data") is PackedByteArray:
		return {"ok": false, "reason": "master stored index buffer is unavailable"}
	var stride: int = surface.index_data.size() / indices.size()
	if stride != 2 and stride != 4:
		return {"ok": false, "reason": "master index buffer stride is unsupported"}
	if surface.get("lods") != null or array_mesh.shadow_mesh != null:
		return {"ok": false, "reason": "master auxiliary render geometry requires a separate cut"}
	var index_data := PackedByteArray()
	index_data.resize(retained.size() * stride)
	for k in retained.size():
		if stride == 2:
			index_data.encode_u16(k * stride, retained[k])
		else:
			index_data.encode_u32(k * stride, retained[k])
	surface.index_data = index_data
	surface.index_count = retained.size()
	var replacement := ArrayMesh.new()
	replacement.set("_surfaces", [surface])
	if replacement.get_surface_count() != 1:
		return {"ok": false, "reason": "master replacement surface could not be created"}
	return {"ok": true, "mesh": replacement, "removed_triangles": removed, "retained_triangles": retained.size() / 3, "original_triangles": indices.size() / 3}

func _prepare_collision_cut(mi: MeshInstance3D, retained_mesh: ArrayMesh) -> Dictionary:
	var body: StaticBody3D = null
	for child in mi.get_children():
		if child is StaticBody3D:
			if body != null:
				return {"ok": false, "reason": "master collision requires one static body"}
			body = child as StaticBody3D
	if body == null or not body.transform.is_equal_approx(Transform3D.IDENTITY):
		return {"ok": false, "reason": "master collision requires a tile-local identity static body"}
	var col: CollisionShape3D = null
	for child in body.get_children():
		if child is CollisionShape3D:
			if col != null:
				return {"ok": false, "reason": "master collision requires one shape"}
			col = child as CollisionShape3D
	if col == null or not col.shape is HeightMapShape3D:
		return {"ok": false, "reason": "master collision source is not a HeightMapShape3D"}
	if retained_mesh.get_surface_count() == 0:
		return {"ok": true, "node": col, "disabled": true, "retained_triangles": 0}
	var shape: ConcavePolygonShape3D = retained_mesh.create_trimesh_shape()
	if shape == null:
		return {"ok": false, "reason": "master retained collision faces could not be created"}
	var faces: PackedVector3Array = shape.get_faces()
	var expected: int = retained_mesh.surface_get_array_index_len(0)
	if faces.size() != expected or faces.is_empty():
		return {"ok": false, "reason": "master retained collision face count disagrees with render indices"}
	for point: Vector3 in faces:
		if not point.is_finite():
			return {"ok": false, "reason": "master retained collision faces contain non-finite coordinates"}
	return {"ok": true, "node": col, "shape": shape, "disabled": false, "retained_triangles": faces.size() / 3}

func set_terrain_cut_uniform(terrain_materials: Array) -> void:
	# Fragment clipping remains available for unsupported master meshes.
	for mat in terrain_materials:
		if not mat is ShaderMaterial:
			continue
		var sm: ShaderMaterial = mat as ShaderMaterial
		sm.set_shader_parameter("core_cut_x_min_m", _x_min_m)
		sm.set_shader_parameter("core_cut_x_max_m", _x_max_m)
		sm.set_shader_parameter("core_cut_z_min_m", _z_min_m)
		sm.set_shader_parameter("core_cut_z_max_m", _z_max_m)
		sm.set_shader_parameter("core_cut_active", 0.0 if _render_cut_complete else 1.0)

func _load_metadata() -> bool:
	if not FileAccess.file_exists(CORE_JSON):
		push_warning("core_terrain: missing %s; core tile skipped." % CORE_JSON)
		return false
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(CORE_JSON))
	if not parsed is Dictionary:
		push_warning("core_terrain: core_terrain.json is not a JSON object.")
		return false
	core_meta = parsed as Dictionary
	var grid: Dictionary = core_meta.get("grid", {})
	_cell_m = float(grid.get("cell_m", 1.0))
	_nx = int(grid.get("nx", 0))
	_nz = int(grid.get("nz", 0))
	_x_min_m = float(grid.get("x_min_m", 0.0))
	_z_min_m = float(grid.get("z_min_m", 0.0))
	_x_max_m = float(grid.get("x_max_m", _x_min_m + float(_nx - 1) * _cell_m))
	_z_max_m = float(grid.get("z_max_m", _z_min_m + float(_nz - 1) * _cell_m))
	_vertical_origin_m = float(core_meta.get("vertical_origin_m", 0.0))
	if _nx <= 1 or _nz <= 1:
		push_warning("core_terrain: zero or 1-cell grid.")
		return false
	if FileAccess.file_exists(STITCH_JSON):
		var sparsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(STITCH_JSON))
		if sparsed is Dictionary:
			stitch_meta = sparsed as Dictionary
	return true

func _load_heights() -> bool:
	if not FileAccess.file_exists(CORE_HEIGHTFIELD):
		push_warning("core_terrain: missing core_heightfield.f32.")
		return false
	var bytes: PackedByteArray = FileAccess.get_file_as_bytes(CORE_HEIGHTFIELD)
	var heights: PackedFloat32Array = bytes.to_float32_array()
	if heights.size() != _nx * _nz:
		push_warning("core_terrain: heightfield size mismatch (%d != %d*%d)" % [heights.size(), _nx, _nz])
		return false
	var micro: PackedFloat32Array = PackedFloat32Array()
	if FileAccess.file_exists(CORE_MICRORELIEF):
		var mbytes: PackedByteArray = FileAccess.get_file_as_bytes(CORE_MICRORELIEF)
		micro = mbytes.to_float32_array()
		if micro.size() != heights.size():
			push_warning("core_terrain: microrelief size mismatch; skipping microrelief.")
			micro = PackedFloat32Array()
	_heights_full = PackedFloat32Array()
	_heights_full.resize(heights.size())
	for k in heights.size():
		var h: float = heights[k]
		if micro.size() == heights.size():
			h += micro[k]
		_heights_full[k] = h
	var world: Variant = JSON.parse_string(ReleaseData.get_file_as_string("res://data/world.json"))
	if not world is Dictionary:
		push_error("Core river beds require world geometry")
		return false
	river_bed_report = RiverTerrain.carve(_heights_full, _nx, _nz, Vector2(_x_min_m, _z_min_m), _cell_m, world.get("rivers", []))
	set_meta("river_bed", river_bed_report)
	return true

func _build_mesh_tile() -> void:
	var step: int = maxi(MESH_DECIMATION, 1)
	var mx: int = int(ceil(float(_nx - 1) / float(step))) + 1
	var mz: int = int(ceil(float(_nz - 1) / float(step))) + 1
	var vcount: int = mx * mz
	var vertices: PackedVector3Array = PackedVector3Array()
	vertices.resize(vcount)
	var normals: PackedVector3Array = PackedVector3Array()
	normals.resize(vcount)
	var uvs: PackedVector2Array = PackedVector2Array()
	uvs.resize(vcount)
	var tcount: int = (mx - 1) * (mz - 1) * 6
	var indices: PackedInt32Array = PackedInt32Array()
	indices.resize(tcount)
	var inv_x: float = 1.0 / (_x_max_m - _x_min_m)
	var inv_z: float = 1.0 / (_z_max_m - _z_min_m)
	var inv_cell_x: float = 1.0 / (float(step) * _cell_m)
	for jj in mz:
		var j: int = mini(jj * step, _nz - 1)
		var jp: int = mini(j + step, _nz - 1)
		var jn: int = maxi(j - step, 0)
		var row_off: int = j * _nx
		var row_up: int = jn * _nx
		var row_down: int = jp * _nx
		var dz_scale: float = 1.0 / (float(maxi(jp - jn, 1)) * _cell_m)
		for ii in mx:
			var i: int = mini(ii * step, _nx - 1)
			var ip: int = mini(i + step, _nx - 1)
			var ne: int = maxi(i - step, 0)
			var h: float = _heights_full[row_off + i] + CORE_RENDER_LIFT_M
			var x: float = _x_min_m + float(i) * _cell_m
			var z: float = _z_min_m + float(j) * _cell_m
			var idx: int = jj * mx + ii
			vertices[idx] = Vector3(x, h, z)
			var dx: float = (_heights_full[row_off + ip] - _heights_full[row_off + ne]) / (float(maxi(ip - ne, 1)) * _cell_m)
			var dzv: float = (_heights_full[row_down + i] - _heights_full[row_up + i]) * dz_scale
			normals[idx] = Vector3(-dx, 1.0, -dzv).normalized()
			uvs[idx] = Vector2((x - _x_min_m) * inv_x, (z - _z_min_m) * inv_z)
	var ti: int = 0
	for jj in (mz - 1):
		for ii in (mx - 1):
			var a: int = jj * mx + ii
			var b: int = a + 1
			var c: int = a + mx
			var d: int = c + 1
			# Match the master terrain winding.
			indices[ti] = a
			indices[ti + 1] = b
			indices[ti + 2] = c
			indices[ti + 3] = b
			indices[ti + 4] = d
			indices[ti + 5] = c
			ti += 6
	var mesh: ArrayMesh = ArrayMesh.new()
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0, _mat_material)
	_tile_mesh_instance = MeshInstance3D.new()
	_tile_mesh_instance.name = "CoreTerrainTile"
	_tile_mesh_instance.mesh = mesh
	add_child(_tile_mesh_instance)

func _sample_normal_from_grid(ix: int, iz: int) -> Vector3:
	# Use central differences on the row-major height grid.
	var left: int = maxi(ix - 1, 0)
	var right: int = mini(ix + 1, _nx - 1)
	var up: int = maxi(iz - 1, 0)
	var down: int = mini(iz + 1, _nz - 1)
	var dx: float = (_heights_full[iz * _nx + right] - _heights_full[iz * _nx + left]) / (float(right - left) * _cell_m)
	var dz: float = (_heights_full[down * _nx + ix] - _heights_full[up * _nx + ix]) / (float(down - up) * _cell_m)
	return Vector3(-dx, 1.0, -dz).normalized()

func _build_collision_tile() -> void:
	# Store unscaled world heights in the collision grid.
	_tile_collision_body = StaticBody3D.new()
	_tile_collision_body.name = "CoreTerrainCollision"
	add_child(_tile_collision_body)
	var col: CollisionShape3D = CollisionShape3D.new()
	var hm: HeightMapShape3D = HeightMapShape3D.new()
	hm.map_width = _nx
	hm.map_depth = _nz
	hm.map_data = _heights_full
	col.shape = hm
	col.position = Vector3(_x_min_m + float(_nx - 1) * 0.5 * _cell_m, 0.0, _z_min_m + float(_nz - 1) * 0.5 * _cell_m)
	col.scale = Vector3(_cell_m, 1.0, _cell_m)
	_tile_collision_body.add_child(col)

func _mark_terrain_tile_grouping() -> void:
	_tile_mesh_instance.add_to_group("terrain_tile")
	_tile_mesh_instance.add_to_group("weather_wetness")

func _make_mat_material(mat_surface: Variant) -> ShaderMaterial:
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/thermal_apron.gdshader")
	if not GroundMaterials.bind_ground_material(mat):
		push_error("core_terrain: shared ground material binding failed.")
		return null
	mat.set_shader_parameter("extent_x_min_m", _x_min_m)
	mat.set_shader_parameter("extent_z_min_m", _z_min_m)
	mat.set_shader_parameter("extent_width_m", _x_max_m - _x_min_m)
	mat.set_shader_parameter("extent_height_m", _z_max_m - _z_min_m)
	_bind_residual_normal(mat)
	if mat_surface != null and mat_surface.has_method("apply"):
		if not mat_surface.apply(mat):
			return null
	if not mat.get_shader_parameter("pigment_layers") is Texture2DArray:
		var pigment: Texture2D = mat_surface.get("pigment_tex") if mat_surface != null else null
		if not GroundMaterials.bind_pigment_layers(mat, pigment, pigment):
			return null
	if not _bind_outflow_layers(mat_surface, mat):
		return null
	return mat

func _bind_residual_normal(mat: ShaderMaterial) -> void:
	mat.set_shader_parameter("normal_map_available", 0.0)
	mat.set_shader_parameter("residual_normal_fade_near_m", 100.0)
	mat.set_shader_parameter("residual_normal_fade_far_m", 220.0)
	var normal_meta: Dictionary = core_meta.get("layers", {}).get("core_normal", {})
	if normal_meta.get("contract", "") != "tangent_residual_mesh_frame.v1":
		return
	if int(normal_meta.get("mesh_decimation", 0)) != MESH_DECIMATION or normal_meta.get("frame_sampling", "") != "mesh_vertex_tbn_barycentric_diagonal_b_c":
		push_error("core_terrain: residual normal frame disagrees with the render mesh.")
		return
	if FileAccess.get_sha256(CORE_NORMAL) != normal_meta.get("sha256", ""):
		push_error("core_terrain: residual normal checksum mismatch.")
		return
	var image := Image.new()
	if image.load_png_from_buffer(FileAccess.get_file_as_bytes(CORE_NORMAL)) != OK or image.get_width() != _nx or image.get_height() != _nz:
		push_error("core_terrain: residual normal raster disagrees with the grid.")
		return
	image.convert(Image.FORMAT_RGB8)
	_normal_image = image
	mat.set_shader_parameter("normal_grid_size", Vector2(_nx, _nz))
	mat.set_shader_parameter("normal_map_available", 1.0)

func _bind_outflow_layers(mat_surface: Variant, mat: ShaderMaterial) -> bool:
	var textures: Array = [null, null, null]
	if mat_surface != null:
		textures = [mat_surface.get("wet_mask_tex"), mat_surface.get("flow_fraction_tex"), mat_surface.get("in_pool_tex")]
	var identities: Array[int] = []
	for texture in textures:
		identities.append(texture.get_instance_id() if texture is Texture2D else 0)
	identities.append(_normal_image.get_instance_id() if _normal_image != null else 0)
	if identities == _bound_outflow_ids and mat.get_shader_parameter("outflow_layers") is Texture2DArray:
		return true
	var source_width: int = 1
	var source_height: int = 1
	for texture in textures:
		if texture is Texture2D:
			source_width = texture.get_width()
			source_height = texture.get_height()
			break
	var width: int = maxi(source_width, _nx if _normal_image != null else 1)
	var height: int = maxi(source_height, _nz if _normal_image != null else 1)
	var images: Array[Image] = []
	for texture in textures:
		var image := Image.create(width, height, false, Image.FORMAT_RF)
		image.fill(Color.BLACK)
		if texture is Texture2D:
			var source_image: Image = texture.get_image()
			if source_image.get_width() != source_width or source_image.get_height() != source_height:
				push_error("core_terrain: outflow layer dimensions disagree.")
				return false
			source_image.convert(Image.FORMAT_RF)
			image.blit_rect(source_image, Rect2i(0, 0, source_width, source_height), Vector2i.ZERO)
		images.append(OutflowFilter.prefilter(image))
	for channel in 2:
		var image := Image.create(width + 2, height + 2, false, Image.FORMAT_RF)
		image.fill(Color(0.5, 0.0, 0.0))
		if _normal_image != null:
			var bytes: PackedByteArray = _normal_image.get_data()
			var values := PackedFloat32Array()
			values.resize(_nx * _nz)
			for k in values.size():
				values[k] = float(bytes[k * 3 + channel]) / 255.0
			var source_image := Image.create_from_data(_nx, _nz, false, Image.FORMAT_RF, values.to_byte_array())
			image.blit_rect(source_image, Rect2i(0, 0, _nx, _nz), Vector2i.ONE)
		images.append(image)
	var layers := Texture2DArray.new()
	if layers.create_from_images(images) != OK:
		push_error("core_terrain: outflow layer creation failed.")
		return false
	mat.set_shader_parameter("outflow_layers", layers)
	mat.set_shader_parameter("outflow_source_size", Vector2(source_width, source_height))
	_bound_outflow_ids = identities
	return true

func refresh_outflow(mat_surface: Variant) -> bool:
	return _mat_material != null and _bind_outflow_layers(mat_surface, _mat_material)

func get_mat_material() -> ShaderMaterial:
	return _mat_material

func extent_rect() -> Dictionary:
	return {
		"x_min_m": _x_min_m,
		"x_max_m": _x_max_m,
		"z_min_m": _z_min_m,
		"z_max_m": _z_max_m,
		"nx": _nx,
		"nz": _nz,
		"cell_m": _cell_m,
		"vertical_origin_m": _vertical_origin_m,
	}

func heights_minmax() -> Array:
	# Return core bounds and grid dimensions.
	var lo: float = INF
	var hi: float = -INF
	for k in _heights_full.size():
		var v: float = _heights_full[k]
		if v < lo:
			lo = v
		if v > hi:
			hi = v
	return [lo, hi]
