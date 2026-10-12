class_name MidwayWildlifeActor
extends Node3D
## Articulated shape proxies at approximate real dimensions.
## Routes and counts authored in JSON.
## Actors never sample new habitat at runtime.
var record: Dictionary = {}
var state: String = "rest"
var _terrain: RefCounted
var _ecosystem: Node
var _kind: String = ""
var _id: String = ""
var _medium: String = "land"
var _patch_id: String = ""
var _route: PackedVector3Array = PackedVector3Array()
var _target_index: int = 1
var _travel_direction: int = 1
var _body: Node3D
var _head: Node3D
var _tail: Node3D
var _legs: Array[Node3D] = []
var _wings: Array[Node3D] = []
var _insects: Array[Node3D] = []
var _insect_offsets: Array[Vector3] = []
var _world_position: Vector3 = Vector3.ZERO
var _state_age: float = 0.0
var _forage_hold_age: float = 0.0
var _time: float = 0.0
var _phase: float = 0.0
var _cycle: int = 0
var _valid: bool = false
var _moving: bool = false
var _activity: float = 1.0
var _perch_height: float = 0.0
var _asset_backed: bool = false

## Licensed third-party fauna models (data/asset_manifest.json).
## Models face +Z as shipped; yaw PI turns them to Godot-forward (-Z).
## "ground" places the AABB bottom at y=0; "center" centers vertically (fish).
## Per-individual tint from record.individual.tint_rgb.
const FAUNA: Dictionary = {
	"bison": {"path": "res://assets/imported/fauna/bison/bison.glb", "mode": "ground", "yaw": PI, "tint": Vector3(1.0, 1.0, 1.0)},
	"goose": {"path": "res://assets/imported/fauna/goose/goose_mallard_base.glb", "mode": "ground", "yaw": PI, "tint": Vector3(1.0, 1.0, 1.0), "material": "res://assets/imported/fauna/goose/canada_goose_material.tres"},
	"raven": {"path": "res://assets/imported/fauna/raven/raven.glb", "mode": "ground", "yaw": PI, "tint": Vector3(1.0, 1.0, 1.0)},
	"dipper": {"path": "res://assets/imported/fauna/dipper/dipper_sparrow_base.glb", "mode": "ground", "yaw": PI, "tint": Vector3(0.42, 0.46, 0.55)},
	"rainbow_trout": {"path": "res://assets/imported/fauna/trout/trout.glb", "mode": "center", "yaw": PI, "tint": Vector3(1.0, 1.0, 1.0)},
	"brown_trout": {"path": "res://assets/imported/fauna/trout/trout.glb", "mode": "center", "yaw": PI, "tint": Vector3(1.08, 0.92, 0.62)},
}

func setup(data: Dictionary, terrain: RefCounted, ecosystem: Node) -> void:
	record = data.duplicate(true)
	_terrain = terrain
	_ecosystem = ecosystem
	_kind = str(record.get("kind", ""))
	_id = str(record.get("id", "wildlife_proxy"))
	_patch_id = str(record.get("patch_id", ""))
	_medium = str(record.get("medium", "land"))
	_phase = float(record.get("phase", 0.0))
	_time = _phase
	_perch_height = float(record.get("perch_stone_height_m", 0.0))
	name = _id
	set_meta("art_status", "Original articulated shape proxy, not a photoreal animal asset")
	set_meta("species_id", record.get("species_id", "unidentified_guild"))
	set_meta("evidence_scope", record.get("evidence_scope", "authoring approximation"))
	var world: Dictionary = _ecosystem.get("world_data")
	_build_route(world)
	_valid = not _route.is_empty()
	if not _valid:
		push_error("Wildlife has no valid authored route: " + _id)
		return
	position = _route[0]
	_world_position = _route[0]
	_target_index = 1 if _route.size() > 1 else 0
	state = str(record.get("initial_state", "graze" if _kind == "bison" or _kind == "elk" else "perch"))

func _ready() -> void:
	if not _valid:
		set_process(false)
		return
	_body = Node3D.new()
	_body.name = "ArticulatedProxy"
	add_child(_body)
	_body.scale = Vector3.ONE * float(record.get("scale", 1.0))
	if FAUNA.has(_kind) and _build_asset_visual(FAUNA[_kind]):
		pass  # Licensed model instantiated.
	else:
		match _kind:
			"bison", "elk":
				_make_ungulate(_kind == "elk")
			"goose":
				_make_goose()
			"dipper", "raven":
				_make_small_bird(_kind == "raven")
			"rainbow_trout", "brown_trout":
				_make_fish(_kind == "brown_trout")
			"insects":
				_make_insects()
			_:
				push_error("Unsupported authored wildlife proxy: " + _kind)
				set_process(false)
				return
	if _perch_height > 0.0:
		var rock: StandardMaterial3D = _material(Color(0.35, 0.34, 0.29))
		_ellipsoid(self, Vector3(0.0, -_perch_height * 0.5, 0.0), Vector3(0.42, _perch_height, 0.37), rock)
	if _route.size() > 1:
		_face(_route[1] - _route[0], 1.0)
	_sync_feeding()

## Instantiate the licensed model, normalize to the record's body length, apply individual tint. Returns false when asset or record length missing.
func _build_asset_visual(spec: Dictionary) -> bool:
	var path: String = str(spec.get("path", ""))
	if not ResourceLoader.exists(path):
		push_warning("Fauna asset missing, using shape proxy: " + path)
		return false
	var dims: Dictionary = record.get("approx_dimensions_m", {})
	var target_len: float = float(dims.get("length", dims.get("body_length", 0.0)))
	if target_len <= 0.0:
		push_warning("Fauna asset actor lacks authored body length, using shape proxy: " + _id)
		return false
	var packed: PackedScene = load(path)
	if packed == null:
		push_warning("Fauna asset failed to load, using shape proxy: " + path)
		return false
	var inst: Node3D = packed.instantiate()
	var aabb: AABB = _combined_aabb(inst)
	if aabb.size.z <= 0.0:
		inst.free()
		return false
	var norm: float = target_len / aabb.size.z
	inst.scale = Vector3.ONE * norm
	inst.rotation.y = float(spec.get("yaw", 0.0))
	if str(spec.get("mode", "ground")) == "center":
		inst.position.y = -(aabb.position.y + aabb.size.y * 0.5) * norm
	else:
		inst.position.y = -aabb.position.y * norm
	inst.position.x = -(aabb.position.x + aabb.size.x * 0.5) * norm
	var tint: Vector3 = spec.get("tint", Vector3.ONE)
	var indiv: Dictionary = record.get("individual", {})
	if indiv.has("tint_rgb"):
		var t: Array = indiv["tint_rgb"]
		if t.size() == 3:
			tint *= Vector3(float(t[0]), float(t[1]), float(t[2]))
	var override_material: Material = null
	if spec.has("material") and ResourceLoader.exists(str(spec["material"])):
		override_material = load(str(spec["material"]))
	_apply_look(inst, tint, override_material)
	var range_end: float = 270.0 if _kind == "bison" or _kind == "elk" else 135.0
	_set_visibility_range(inst, range_end)
	_body.add_child(inst)
	_asset_backed = true
	set_meta("art_status", "Licensed third-party model (asset_manifest.json); per-individual tint from python trait pipeline")
	return true

func _combined_aabb(node: Node) -> AABB:
	var total: AABB = AABB()
	var first: bool = true
	var stack: Array = [node]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is MeshInstance3D:
			var b: AABB = n.get_aabb()
			if first:
				total = b
				first = false
			else:
				total = total.merge(b)
		for c: Node in n.get_children():
			stack.append(c)
	return total

func _apply_look(node: Node, tint: Vector3, override_material: Material) -> void:
	var stack: Array = [node]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is MeshInstance3D:
			var mi: MeshInstance3D = n
			for s: int in range(mi.mesh.get_surface_count()):
				var base: Material = mi.get_active_material(s)
				var mat: StandardMaterial3D
				if override_material != null:
					mat = override_material.duplicate()
				elif base is StandardMaterial3D:
					mat = base.duplicate()
				else:
					mat = StandardMaterial3D.new()
				mat.albedo_color = Color(mat.albedo_color.r * tint.x, mat.albedo_color.g * tint.y, mat.albedo_color.b * tint.z, mat.albedo_color.a)
				mi.set_surface_override_material(s, mat)
		for c: Node in n.get_children():
			stack.append(c)

func _set_visibility_range(node: Node, range_end: float) -> void:
	var stack: Array = [node]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is GeometryInstance3D:
			n.visibility_range_end = range_end
		for c: Node in n.get_children():
			stack.append(c)

func _build_route(world: Dictionary) -> void:
	_route.clear()
	if _medium == "river" or _medium == "river_bank":
		var chosen: Dictionary = {}
		for water: Dictionary in world.get("rivers", []):
			if str(water.get("id", "")) == str(record.get("river_id", "")):
				chosen = water
				break
		# No fallbacks to thermal pools or unknown tributaries.
		if chosen.is_empty() or str(chosen.get("name", "")).to_upper() != "FIREHOLE RIVER":
			push_error("Wildlife water route must name an authored FIREHOLE RIVER feature: " + _id)
			return
		var points: Array = chosen.get("points", [])
		var first: int = int(record.get("start_point_index", 0))
		var last: int = int(record.get("end_point_index", first))
		if first < 0 or last < first or last >= points.size():
			push_error("Invalid authored river point range: " + _id)
			return
		var lateral: float = float(record.get("lateral_offset_m", 0.0))
		var width: float = float(chosen.get("width", 0.0))
		if _medium == "river" and absf(lateral) > width * 0.35:
			push_error("Aquatic actor offset lies outside approved river interior: " + _id)
			return
		for i: int in range(first, last + 1):
			var p: Array = points[i]
			var previous: Array = points[maxi(0, i - 1)]
			var following: Array = points[mini(points.size() - 1, i + 1)]
			var tangent: Vector2 = Vector2(float(following[0]) - float(previous[0]), float(following[2]) - float(previous[2])).normalized()
			var side: Vector2 = Vector2(-tangent.y, tangent.x) * lateral
			var x: float = float(p[0]) + side.x
			var z: float = float(p[2]) + side.y
			var y: float = float(p[1]) + float(record.get("water_offset_m", 0.0))
			if _medium == "river_bank":
				y = maxf(_ground_height(x, z), float(p[1])) + 0.015
				if i == first:
					y += _perch_height
			_route.append(Vector3(x, y, z))
	else:
		for p: Array in record.get("path_xz", []):
			var point: Vector3 = Vector3(float(p[0]), _ground_height(float(p[0]), float(p[1])), float(p[1]))
			point.y += float(record.get("ground_offset_m", 0.0))
			if _route.is_empty():
				point.y += _perch_height
			if _inside_thermal_pool(Vector2(point.x, point.z), world):
				push_error("Rejected land route inside a thermal pool: " + _id)
				_route.clear()
				return
			_route.append(point)
	var length_m: float = 0.0
	for i: int in range(1, _route.size()):
		length_m += _route[i - 1].distance_to(_route[i])
	if length_m > 200.0:
		push_error("Local wildlife route exceeds authored 200m scope: " + _id)
		_route.clear()

func _inside_thermal_pool(point: Vector2, world: Dictionary) -> bool:
	for pool: Dictionary in world.get("pools", []):
		if not bool(pool.get("thermal", false)):
			continue
		var polygon: PackedVector2Array = PackedVector2Array()
		for q: Array in pool.get("ring", []):
			polygon.append(Vector2(float(q[0]), float(q[1])))
		if Geometry2D.is_point_in_polygon(point, polygon):
			return true
	return false

func _ground_height(x: float, z: float) -> float:
	return float(_terrain.call("sample", x, z))

func _process(delta: float) -> void:
	if not _valid or _body == null:
		return
	var dt: float = maxf(0.0, minf(delta, 0.25))
	_time += dt
	_state_age += dt
	_moving = false
	var habitat: Dictionary = _ecosystem.call("patch", _patch_id)
	if _kind == "bison" or _kind == "elk":
		_update_ungulate(dt, habitat)
	elif _kind == "goose":
		_update_goose(dt)
	elif _kind == "dipper" or _kind == "raven":
		_update_bird(dt)
	elif _kind == "rainbow_trout" or _kind == "brown_trout":
		_update_fish(dt)
	elif _kind == "insects":
		_update_insects(habitat)
	_body.position = _world_position - position
	_animate(dt)
	_sync_feeding()

func _set_state(next_state: String) -> void:
	state = next_state
	_state_age = 0.0
	_forage_hold_age = 0.0

func _update_ungulate(dt: float, habitat: Dictionary) -> void:
	if state == "graze":
		if _state_age >= float(record.get("graze_seconds", 24.0)) or float(habitat.get("biomass", 0.0)) < 0.05:
			_set_state("walk")
	elif state == "rest":
		if _state_age >= float(record.get("rest_seconds", 18.0)):
			_set_state("walk")
	elif state == "walk":
		if _move_toward_target(dt, float(record.get("walk_mps", 0.6))):
			_next_target()
			_cycle += 1
			_set_state("rest" if _cycle % 4 == 0 else "graze")

func _update_goose(dt: float) -> void:
	if state == "float":
		if _move_toward_target(dt, float(record.get("walk_mps", 0.12))):
			_next_target()
			_set_state("preen")
	elif _state_age > float(record.get("rest_seconds", 8.0)):
		_set_state("float")

func _update_bird(dt: float) -> void:
	if state == "perch":
		if _state_age > float(record.get("perch_seconds", 12.0)) and _route.size() > 1:
			_target_index = 1
			_set_state("forage")
	elif state == "forage":
		var arrived: bool = _move_toward_target(dt, float(record.get("walk_mps", 0.22)))
		if arrived:
			if _target_index < _route.size() - 1:
				_target_index += 1
			else:
				# Travel time separate from foraging bout.
				_forage_hold_age += dt
				if _forage_hold_age > float(record.get("forage_seconds", 10.0)):
					_target_index = _route.size() - 2
					_set_state("return")
	elif state == "return":
		if _move_toward_target(dt, float(record.get("walk_mps", 0.22))):
			if _target_index > 0:
				_target_index -= 1
			else:
				_set_state("perch")

func _update_fish(dt: float) -> void:
	var reach: Dictionary
	if _ecosystem.has_method("river_state_at_position"):
		reach = _ecosystem.call(
			"river_state_at_position",
			_world_position,
			str(record.get("river_id", ""))
		)
	else:
		reach = _ecosystem.call("reach_at", _world_position.z)
	_activity = float(reach.get("fish_activity", 0.0))
	if state == "hold":
		if _route.size() > 1:
			_face(_route[0] - _route[_route.size() - 1], minf(1.0, dt * 2.0))
		if _state_age > float(record.get("hold_seconds", 9.0)):
			_set_state("swim")
	elif state == "swim":
		if _move_toward_target(dt, float(record.get("walk_mps", 0.2)) * maxf(0.08, _activity)):
			_next_target()
			_set_state("hold")

func _update_insects(habitat: Dictionary) -> void:
	_activity = float(habitat.get("insect_activity", 0.0))
	state = "hover" if _activity > 0.035 else "inactive"
	for i: int in range(_insects.size()):
		var insect: Node3D = _insects[i]
		insect.visible = _activity > 0.035
		var phase: float = _time * (1.7 + float(i) * 0.09) + float(i) * 1.31
		insect.position = _insect_offsets[i] + Vector3(sin(phase) * 0.11, cos(phase * 1.3) * 0.07, cos(phase * 0.8) * 0.12)
		insect.rotation.y = phase

func _next_target() -> void:
	if _route.size() < 2:
		return
	_target_index += _travel_direction
	if _target_index >= _route.size():
		_travel_direction = -1
		_target_index = _route.size() - 2
	elif _target_index < 0:
		_travel_direction = 1
		_target_index = 1

func _move_toward_target(dt: float, speed: float) -> bool:
	if _route.size() < 2:
		return true
	var target: Vector3 = _route[_target_index]
	var difference: Vector3 = target - _world_position
	var distance: float = difference.length()
	if distance <= 0.02:
		_world_position = target
		return true
	var step_distance: float = minf(distance, speed * dt)
	var next: Vector3 = _world_position + difference / distance * step_distance
	if _medium == "land":
		next.y = _ground_height(next.x, next.z) + float(record.get("ground_offset_m", 0.0))
		if _perch_height > 0.0:
			var perch_distance: float = Vector2(next.x - _route[0].x, next.z - _route[0].z).length()
			next.y += _perch_height * clampf(1.0 - perch_distance / 0.4, 0.0, 1.0)
	# River routes interpolate saved water elevations.
	_world_position = next
	_face(difference, minf(1.0, dt * 3.0))
	_moving = true
	return step_distance >= distance - 0.001

func _face(direction: Vector3, weight: float) -> void:
	if _body == null or Vector2(direction.x, direction.z).length_squared() < 0.000001:
		return
	var yaw: float = atan2(-direction.x, -direction.z)
	_body.rotation.y = lerp_angle(_body.rotation.y, yaw, weight)

func _animate(dt: float) -> void:
	if _kind == "bison" or _kind == "elk":
		var stride: float = _time * 3.5
		for i: int in range(_legs.size()):
			var target: float = sin(stride + (0.0 if i == 0 or i == 3 else PI)) * 0.22 if _moving else 0.0
			_legs[i].rotation.x = lerpf(_legs[i].rotation.x, target, minf(1.0, dt * 6.0))
		if _head != null:
			var head_pitch: float = -0.67 + sin(_time * 1.7) * 0.055 if state == "graze" else sin(_time * 0.23) * 0.045
			_head.rotation.x = lerpf(_head.rotation.x, head_pitch, minf(1.0, dt * 1.8))
		_body.position.y += sin(_time * 7.0) * 0.017 if _moving else sin(_time * 0.8) * 0.003
	elif _kind == "goose":
		_body.position.y += sin(_time * 1.1) * 0.012
		if _head != null:
			_head.rotation.y = lerp_angle(_head.rotation.y, 1.8 if state == "preen" else 0.0, minf(1.0, dt * 1.4))
	elif _kind == "dipper" or _kind == "raven":
		if _head != null:
			var nod: float = -0.33 + sin(_time * 4.0) * 0.16 if state == "forage" else sin(_time * 0.7) * 0.05
			_head.rotation.x = lerpf(_head.rotation.x, nod, minf(1.0, dt * 5.0))
		_body.position.y += absf(sin(_time * 8.0)) * 0.013 if _moving else sin(_time * 2.2) * 0.004
	elif _kind == "rainbow_trout" or _kind == "brown_trout":
		if _tail != null:
			_tail.rotation.y = sin(_time * (8.0 if _moving else 3.0)) * (0.3 if _moving else 0.12)
		else:
			# Asset-backed model has no tail node; whole-body roll.
			_body.rotation.z = lerpf(_body.rotation.z, sin(_time * (3.5 if _moving else 1.6)) * 0.07, minf(1.0, dt * 3.0))
		_body.position.y += sin(_time * 1.3) * 0.012

func _sync_feeding() -> void:
	if _ecosystem == null or not is_instance_valid(_ecosystem):
		return
	if _kind == "bison" or _kind == "elk":
		_ecosystem.call("set_grazer_activity", _id, _patch_id, state == "graze", float(record.get("grazing_index_per_second", 0.0000015)))
	elif _kind == "dipper" or _kind == "rainbow_trout" or _kind == "brown_trout":
		var feeding: bool = (state == "forage" and not _moving) if _kind == "dipper" else (state == "hold" and _activity > 0.3)
		_ecosystem.call("set_insect_forager_activity", _id, _patch_id, feeding, float(record.get("insect_index_per_second", 0.000003)))

func _exit_tree() -> void:
	if is_instance_valid(_ecosystem):
		_ecosystem.call("unregister_actor", _id)

func _material(color: Color, two_sided: bool = false) -> StandardMaterial3D:
	var material: StandardMaterial3D = StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.92
	if two_sided:
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
	return material

func _ellipsoid(parent: Node3D, center: Vector3, size: Vector3, material: Material) -> MeshInstance3D:
	var sphere: SphereMesh = SphereMesh.new()
	sphere.radius = 0.5
	sphere.height = 1.0
	sphere.radial_segments = 12
	sphere.rings = 6
	var node: MeshInstance3D = MeshInstance3D.new()
	node.mesh = sphere
	node.material_override = material
	node.position = center
	node.scale = size
	node.visibility_range_end = 270.0 if _kind == "bison" or _kind == "elk" else (22.0 if _kind == "insects" else 135.0)
	if _kind == "insects":
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(node)
	return node

func _segment(parent: Node3D, a: Vector3, b: Vector3, radius_a: float, radius_b: float, material: Material) -> MeshInstance3D:
	var vector: Vector3 = b - a
	var cylinder: CylinderMesh = CylinderMesh.new()
	cylinder.height = vector.length()
	cylinder.bottom_radius = radius_a
	cylinder.top_radius = radius_b
	cylinder.radial_segments = 8
	var node: MeshInstance3D = MeshInstance3D.new()
	node.mesh = cylinder
	node.material_override = material
	node.position = (a + b) * 0.5
	node.quaternion = Quaternion(Vector3.UP, vector.normalized())
	node.visibility_range_end = 230.0 if _kind == "bison" or _kind == "elk" else 115.0
	parent.add_child(node)
	return node

func _fin(parent: Node3D, a: Vector3, b: Vector3, c: Vector3, material: Material) -> void:
	var mesh: ImmediateMesh = ImmediateMesh.new()
	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES, material)
	mesh.surface_set_normal((b - a).cross(c - a).normalized())
	mesh.surface_add_vertex(a)
	mesh.surface_add_vertex(b)
	mesh.surface_add_vertex(c)
	mesh.surface_end()
	var node: MeshInstance3D = MeshInstance3D.new()
	node.mesh = mesh
	node.visibility_range_end = 100.0
	parent.add_child(node)

func _make_ungulate(is_elk: bool) -> void:
	var coat: StandardMaterial3D = _material(Color(0.40, 0.29, 0.16) if is_elk else Color(0.21, 0.12, 0.065))
	var dark: StandardMaterial3D = _material(Color(0.13, 0.075, 0.042))
	var muzzle: StandardMaterial3D = _material(Color(0.09, 0.065, 0.046))
	var horn: StandardMaterial3D = _material(Color(0.58, 0.53, 0.38))
	var eye: StandardMaterial3D = _material(Color(0.028, 0.022, 0.016))
	_ellipsoid(_body, Vector3(0, 1.05, 0.13), Vector3(0.80, 1.04, 1.95), coat)
	if not is_elk:
		_ellipsoid(_body, Vector3(0, 1.45, -0.38), Vector3(0.87, 0.75, 1.05), dark)
		_ellipsoid(_body, Vector3(0, 1.02, -0.63), Vector3(0.88, 1.06, 0.91), dark)
	_head = Node3D.new()
	_head.position = Vector3(0, 1.27 if is_elk else 1.15, -0.78)
	_body.add_child(_head)
	if is_elk:
		_segment(_head, Vector3(0, 0, 0), Vector3(0, 0.48, -0.22), 0.19, 0.13, dark)
		_ellipsoid(_head, Vector3(0, 0.44, -0.4), Vector3(0.34, 0.36, 0.63), dark)
	else:
		_ellipsoid(_head, Vector3(0, -0.08, -0.29), Vector3(0.69, 0.75, 0.79), dark)
		_ellipsoid(_head, Vector3(0, -0.23, -0.60), Vector3(0.46, 0.36, 0.40), muzzle)
		_ellipsoid(_head, Vector3(0, -0.53, -0.27), Vector3(0.28, 0.44, 0.34), dark)
	for side: float in [-1.0, 1.0]:
		_ellipsoid(_head, Vector3(side * 0.28, 0.10, -0.47), Vector3(0.038, 0.038, 0.038), eye)
		_ellipsoid(_head, Vector3(side * 0.39, 0.18, -0.12), Vector3(0.28, 0.12, 0.18), dark)
		if not is_elk:
			_segment(_head, Vector3(side * 0.30, 0.18, -0.22), Vector3(side * 0.52, 0.34, -0.20), 0.052, 0.032, horn)
			_segment(_head, Vector3(side * 0.52, 0.34, -0.20), Vector3(side * 0.55, 0.49, -0.25), 0.032, 0.003, horn)
	for side: float in [-1.0, 1.0]:
		for front: float in [-0.55, 0.69]:
			var leg: Node3D = Node3D.new()
			leg.position = Vector3(side * 0.25, 0.86, front)
			_body.add_child(leg)
			_segment(leg, Vector3.ZERO, Vector3(0, -0.72, 0.01), 0.095, 0.048, dark)
			_ellipsoid(leg, Vector3(0, -0.795, -0.02), Vector3(0.16, 0.13, 0.22), muzzle)
			_legs.append(leg)
	_segment(_body, Vector3(0, 1.25, 0.97), Vector3(0.06, 0.75, 1.18), 0.025, 0.018, dark)
	_ellipsoid(_body, Vector3(0.06, 0.71, 1.18), Vector3(0.10, 0.17, 0.11), dark)

func _make_goose() -> void:
	var coat: StandardMaterial3D = _material(Color(0.38, 0.35, 0.28))
	var wing: StandardMaterial3D = _material(Color(0.22, 0.22, 0.19))
	var black: StandardMaterial3D = _material(Color(0.045, 0.049, 0.043))
	var white: StandardMaterial3D = _material(Color(0.85, 0.84, 0.74))
	_ellipsoid(_body, Vector3(0, 0.16, 0.06), Vector3(0.35, 0.35, 0.71), coat)
	for side: float in [-1.0, 1.0]:
		_ellipsoid(_body, Vector3(side * 0.13, 0.23, 0.12), Vector3(0.10, 0.23, 0.57), wing)
	_head = Node3D.new()
	_head.position = Vector3(0, 0.26, -0.22)
	_body.add_child(_head)
	_segment(_head, Vector3.ZERO, Vector3(0, 0.27, -0.055), 0.052, 0.038, black)
	_ellipsoid(_head, Vector3(0, 0.32, -0.095), Vector3(0.11, 0.14, 0.18), black)
	_segment(_head, Vector3(0, 0.315, -0.15), Vector3(0, 0.30, -0.26), 0.037, 0.023, black)
	for side: float in [-1.0, 1.0]:
		_ellipsoid(_head, Vector3(side * 0.047, 0.295, -0.08), Vector3(0.015, 0.055, 0.087), white)
		_ellipsoid(_head, Vector3(side * 0.05, 0.352, -0.132), Vector3(0.014, 0.014, 0.014), black)
	_ellipsoid(_body, Vector3(0, 0.15, 0.34), Vector3(0.23, 0.15, 0.23), black)

func _make_small_bird(is_raven: bool) -> void:
	# Mesh construction has a 0.31m beak-to-tail envelope before scaling.
	# Species sizes: 0.20m dipper, 0.55m raven.
	var multiplier: float = 1.55 if is_raven else 0.65
	_body.scale *= multiplier
	var feather: StandardMaterial3D = _material(Color(0.06, 0.072, 0.065) if is_raven else Color(0.20, 0.23, 0.22))
	var dark: StandardMaterial3D = _material(Color(0.04, 0.048, 0.04))
	_ellipsoid(_body, Vector3(0, 0.095, 0.02), Vector3(0.105, 0.13, 0.17), feather)
	_head = Node3D.new()
	_head.position = Vector3(0, 0.145, -0.052)
	_body.add_child(_head)
	_ellipsoid(_head, Vector3(0, 0.018, -0.013), Vector3(0.076, 0.078, 0.088), feather)
	_segment(_head, Vector3(0, 0.01, -0.045), Vector3(0, 0.004, -0.098), 0.012, 0.002, dark)
	for side: float in [-1.0, 1.0]:
		_ellipsoid(_head, Vector3(side * 0.035, 0.034, -0.032), Vector3(0.009, 0.009, 0.009), dark)
		_ellipsoid(_body, Vector3(side * 0.044, 0.11, 0.035), Vector3(0.032, 0.09, 0.14), dark)
		_segment(_body, Vector3(side * 0.025, 0.06, 0.005), Vector3(side * 0.025, 0.005, -0.002), 0.006, 0.004, dark)
		_segment(_body, Vector3(side * 0.025, 0.005, -0.002), Vector3(side * 0.025, 0.002, -0.03), 0.004, 0.002, dark)
	_ellipsoid(_body, Vector3(0, 0.08, 0.115), Vector3(0.075, 0.035, 0.09 if not is_raven else 0.17), dark)

func _make_fish(is_brown: bool) -> void:
	var back: StandardMaterial3D = _material(Color(0.40, 0.34, 0.15) if is_brown else Color(0.28, 0.36, 0.31))
	var belly: StandardMaterial3D = _material(Color(0.60, 0.58, 0.39))
	var stripe: StandardMaterial3D = _material(Color(0.65, 0.39, 0.35) if not is_brown else Color(0.57, 0.38, 0.17))
	var fin: StandardMaterial3D = _material(Color(0.28, 0.31, 0.20), true)
	var eye: StandardMaterial3D = _material(Color(0.025, 0.035, 0.025))
	_ellipsoid(_body, Vector3.ZERO, Vector3(0.085, 0.115, 0.40), back)
	_ellipsoid(_body, Vector3(0, -0.023, -0.008), Vector3(0.075, 0.063, 0.34), belly)
	for side: float in [-1.0, 1.0]:
		_ellipsoid(_body, Vector3(side * 0.039, 0, -0.008), Vector3(0.008, 0.019, 0.27), stripe)
		_ellipsoid(_body, Vector3(side * 0.031, 0.015, -0.147), Vector3(0.014, 0.014, 0.014), eye)
		_fin(_body, Vector3(side * 0.032, -0.015, -0.07), Vector3(side * 0.095, -0.04, 0.0), Vector3(side * 0.031, -0.025, 0.05), fin)
	_fin(_body, Vector3(0, 0.035, -0.03), Vector3(0, 0.12, 0.075), Vector3(0, 0.035, 0.12), fin)
	_tail = Node3D.new()
	_tail.position = Vector3(0, 0, 0.17)
	_body.add_child(_tail)
	_fin(_tail, Vector3.ZERO, Vector3(0, 0.075, 0.105), Vector3(0, -0.075, 0.105), fin)

func _make_insects() -> void:
	var body_material: StandardMaterial3D = _material(Color(0.12, 0.13, 0.10))
	var wings_material: StandardMaterial3D = _material(Color(0.64, 0.67, 0.61))
	# Offsets recorded individually.
	for offset: Array in record.get("individual_offsets_m", []):
		var insect: Node3D = Node3D.new()
		_body.add_child(insect)
		var at: Vector3 = Vector3(float(offset[0]), float(offset[1]), float(offset[2]))
		insect.position = at
		_insect_offsets.append(at)
		_insects.append(insect)
		_ellipsoid(insect, Vector3.ZERO, Vector3(0.003, 0.003, 0.006), body_material)
		_ellipsoid(insect, Vector3(0.003, 0.001, 0.0), Vector3(0.006, 0.0007, 0.004), wings_material)
		_ellipsoid(insect, Vector3(-0.003, 0.001, 0.0), Vector3(0.006, 0.0007, 0.004), wings_material)
