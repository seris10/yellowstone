class_name MidwayWildlifeActor
extends Node3D
## Wildlife presentation at authored body dimensions.
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
var chainage_m: float = NAN
var target_s_m: float = NAN
var swim_speed_mps: float = 0.0
var tailbeat_hz: float = 0.0
var _last_sim_time: float = 0.0
var _animation_player: AnimationPlayer
var _swim_clips: Dictionary = {}
var _motion: MidwayWildlifeMotionController
var _mammal_elapsed: float = 0.0
var _mammal_behavior: String = "rest"

## Fauna dimensions and orientation from the asset manifest.
const FAUNA: Dictionary = {
	"bison": {"path": "res://assets/imported/fauna/bison/bison.glb", "mode": "ground", "yaw": PI, "tint": Vector3(1.0, 1.0, 1.0)},
	"goose": {"path": "res://assets/imported/fauna/goose/goose_mallard_base.glb", "mode": "ground", "yaw": PI, "tint": Vector3(1.0, 1.0, 1.0), "material": "res://assets/imported/fauna/goose/canada_goose_material.tres"},
	"raven": {"path": "res://assets/imported/fauna/raven/raven.glb", "mode": "ground", "yaw": PI, "tint": Vector3(1.0, 1.0, 1.0)},
	"dipper": {"path": "res://assets/imported/fauna/dipper/dipper_sparrow_base.glb", "mode": "ground", "yaw": PI, "tint": Vector3(0.42, 0.46, 0.55)},
	"rainbow_trout": {"path": "res://assets/imported/fauna/trout/trout.glb", "mode": "center", "yaw": PI, "tint": Vector3(1.0, 1.0, 1.0)},
	"brown_trout": {"path": "res://assets/imported/fauna/trout/trout.glb", "mode": "center", "yaw": PI, "tint": Vector3(1.08, 0.92, 0.62)},
}

## Species geometry and per-asset orientation overrides.
static var _manifest_fauna_cache: Dictionary = {}
static var _manifest_fauna_loaded: bool = false

static func _manifest_fauna() -> Dictionary:
	if _manifest_fauna_loaded:
		return _manifest_fauna_cache
	_manifest_fauna_loaded = true
	for path: String in ["res://data/wildlife_motion_assets.json", "res://data/asset_manifest.json"]:
		if not FileAccess.file_exists(path):
			continue
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		if parsed is Dictionary:
			var mapping: Variant = parsed.get("wildlife_species_asset_map", {})
			if mapping is Dictionary:
				_manifest_fauna_cache.merge(mapping, true)
	return _manifest_fauna_cache

func _resolve_fauna(kind: String) -> Dictionary:
	var mapping: Dictionary = _manifest_fauna()
	if mapping.has(kind) and mapping[kind] is Dictionary:
		var merged: Dictionary = {}
		if FAUNA.has(kind):
			merged = (FAUNA[kind] as Dictionary).duplicate(true)
		for key: String in (mapping[kind] as Dictionary).keys():
			merged[key] = (mapping[kind] as Dictionary)[key]
		return merged
	if FAUNA.has(kind):
		return FAUNA[kind]
	return {}

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
	_last_sim_time = float(_ecosystem.elapsed)
	_mammal_elapsed = float(_ecosystem.elapsed)
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
	var resolved_fauna: Dictionary = _resolve_fauna(_kind)
	if not resolved_fauna.is_empty() and _build_asset_visual(resolved_fauna):
		pass
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

## Normalize asset geometry to the authored body length.
func _build_asset_visual(spec: Dictionary) -> bool:
	var path: String = str(spec.get("path", ""))
	if not ResourceLoader.exists(path):
		push_warning("Fauna asset missing, using shape proxy: " + path)
		return false
	var dims: Dictionary = record.get("approx_dimensions_m", {})
	var target_len: float = float(dims.get("length", dims.get("body_length", 0.0)))
	if not is_finite(target_len) or target_len <= 0.0:
		push_warning("Fauna asset actor lacks authored body length, using shape proxy: " + _id)
		return false
	var packed: PackedScene = load(path)
	if packed == null:
		push_warning("Fauna asset failed to load, using shape proxy: " + path)
		return false
	var imported: Node3D = packed.instantiate()
	var inst: Node3D = Node3D.new()
	inst.name = "NormalizedAsset"
	inst.add_child(imported)
	var aabb: AABB = _combined_aabb(inst)
	# Select the body-length axis in the imported coordinate frame.
	var length_axis: String = str(spec.get("length_axis", "z")).to_lower()
	var length_size: float = aabb.size.z
	if length_axis == "x":
		length_size = aabb.size.x
	elif length_axis == "y":
		length_size = aabb.size.y
	if not is_finite(length_size) or length_size <= 0.0:
		inst.free()
		return false
	var norm: float = target_len / length_size
	inst.scale = Vector3.ONE * norm
	inst.rotation.y = float(spec.get("yaw", 0.0))
	if str(spec.get("mode", "ground")) == "center":
		inst.position.y = -(aabb.position.y + aabb.size.y * 0.5) * norm
	else:
		inst.position.y = -aabb.position.y * norm
	var center: Vector3 = aabb.position + aabb.size * 0.5
	var rotated_center: Vector3 = Basis(Vector3.UP, inst.rotation.y) * Vector3(center.x, 0.0, center.z)
	inst.position.x = -rotated_center.x * norm
	inst.position.z = -rotated_center.z * norm
	# Decode the manifest tint.
	var raw_tint: Variant = spec.get("tint", Vector3.ONE)
	var tint: Vector3 = Vector3.ONE
	if raw_tint is Vector3:
		tint = raw_tint
	elif raw_tint is Array and (raw_tint as Array).size() == 3:
		var a: Array = raw_tint
		tint = Vector3(float(a[0]), float(a[1]), float(a[2]))
	var indiv: Dictionary = record.get("individual", {})
	if indiv.has("tint_rgb"):
		var t: Array = indiv["tint_rgb"]
		if t.size() == 3:
			tint *= Vector3(float(t[0]), float(t[1]), float(t[2]))
	var override_material: Material = null
	if spec.has("material") and ResourceLoader.exists(str(spec["material"])):
		override_material = load(str(spec["material"]))
	_apply_look(inst, tint, override_material)
	var range_end: float = 270.0 if _is_mammal() else 135.0
	_set_visibility_range(inst, range_end)
	_body.add_child(inst)
	_asset_backed = true
	if _kind.contains("trout"):
		_find_swim_animations(inst)
	if _is_mammal() and spec.has("clip_manifest"):
		var clip_path: String = str(spec.clip_manifest)
		var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(clip_path)) if FileAccess.file_exists(clip_path) else null
		if manifest is Dictionary:
			_motion = MidwayWildlifeMotionController.new()
			if not _motion.configure(inst, manifest, norm * _body.scale.x, _phase):
				push_warning("Mammal clip contract unavailable: " + _id)
				_motion = null
	set_meta("art_status", spec.get("art_status", "third_party_asset"))
	set_meta("geometry_rights", spec.get("geometry_rights", "asset_manifest"))
	return true

func _combined_aabb(node: Node) -> AABB:
	var total: AABB = AABB()
	var first: bool = true
	var stack: Array = [[node, Transform3D.IDENTITY]]
	while not stack.is_empty():
		var entry: Array = stack.pop_back()
		var current: Node = entry[0]
		var transform: Transform3D = entry[1]
		if current is Node3D:
			transform = transform * current.transform
		if current is MeshInstance3D and current.mesh != null:
			var bounds: AABB = transform * current.get_aabb()
			total = bounds if first else total.merge(bounds)
			first = false
		for child: Node in current.get_children():
			stack.append([child, transform])
	return total

func _apply_look(node: Node, tint: Vector3, override_material: Material) -> void:
	var stack: Array = [node]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		if n is MeshInstance3D:
			var mi: MeshInstance3D = n
			if mi.mesh == null:
				continue
			mi.mesh = mi.mesh.duplicate()
			for s: int in range(mi.mesh.get_surface_count()):
				var base: Material = mi.get_active_material(s)
				var mat: StandardMaterial3D
				if override_material != null:
					mat = override_material.duplicate()
				elif base is StandardMaterial3D:
					mat = base.duplicate()
				else:
					mat = StandardMaterial3D.new()
				if bool(record.get("ghost", false)):
					mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
					mat.albedo_color.a = 0.3
				mat.albedo_color = Color(mat.albedo_color.r * tint.x, mat.albedo_color.g * tint.y, mat.albedo_color.b * tint.z, mat.albedo_color.a)
				mi.mesh.surface_set_material(s, mat)
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
		if _medium == "land" and _crosses_thermal_pool(_route[i - 1], _route[i], world):
			push_error("Rejected land route crossing a thermal pool: " + _id)
			_route.clear()
			return
		length_m += _route[i - 1].distance_to(_route[i])
	# Bound the authored route length in meters.
	var max_route_length_m: float = float(record.get("max_route_length_m", 200.0))
	if length_m > max_route_length_m:
		push_error("Local wildlife route exceeds authored %sm scope: %s" % [max_route_length_m, _id])
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

func _crosses_thermal_pool(a: Vector3, b: Vector3, world: Dictionary) -> bool:
	var start: Vector2 = Vector2(a.x, a.z)
	var end: Vector2 = Vector2(b.x, b.z)
	for pool: Dictionary in world.get("pools", []):
		if not bool(pool.get("thermal", false)):
			continue
		var polygon: Array = pool.get("ring", [])
		for index: int in range(polygon.size()):
			var p: Array = polygon[index]
			var q: Array = polygon[(index + 1) % polygon.size()]
			if Geometry2D.segment_intersects_segment(start, end, Vector2(float(p[0]), float(p[1])), Vector2(float(q[0]), float(q[1]))) != null:
				return true
	return false

func _ground_height(x: float, z: float) -> float:
	return float(_terrain.call("sample", x, z))

func _process(delta: float) -> void:
	if _ecosystem != null and (bool(_ecosystem.get("paused")) or bool(_ecosystem.get("clock_held"))):
		if _animation_player != null:
			_animation_player.speed_scale = 0.0
		return
	if not _valid or _body == null:
		return
	if _is_mammal():
		_process_mammal()
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

func _is_mammal() -> bool:
	return record.has("mammal_guild") or _kind in ["bison", "elk", "bobcat", "grizzly", "badger", "wolf", "deer", "gray_wolf", "mule_deer", "american_badger", "black_bear", "canada_lynx", "canadian_lynx"]

func _process_mammal() -> void:
	var current_time: float = float(_ecosystem.elapsed)
	if not is_finite(current_time):
		push_error("Mammal simulation time is nonfinite: " + _id)
		return
	var dt: float = maxf(0.0, current_time - _mammal_elapsed)
	_mammal_elapsed = current_time
	var ecology: Dictionary = {}
	if _ecosystem.has_method("mammal_state"):
		ecology = _ecosystem.call("mammal_state", _id, _kind, _world_position)
	visible = bool(ecology.get("active", true))
	var activity: float = float(ecology.get("activity_index", 1.0))
	var speed_multiplier: float = float(ecology.get("speed_multiplier", 1.0))
	if not is_finite(activity) or not is_finite(speed_multiplier) or speed_multiplier < 0.0:
		push_error("Mammal ecological controls are invalid: " + _id)
		visible = false
		state = "rest"
		_sync_feeding()
		return
	_activity = clampf(activity, 0.0, 1.0)
	if not visible:
		state = "rest"
		_sync_feeding()
		return
	var desired: String = str(ecology.get("behavior", ""))
	var remaining: float = dt
	while remaining > 0.0:
		var step: float = minf(1.0, remaining)
		remaining -= step
		_time += step
		_state_age += step
		_moving = false
		var previous: Vector3 = _world_position
		if not desired.is_empty():
			if state != desired:
				_set_state(desired)
			if desired in ["walk", "forage", "flee"]:
				if _move_toward_target(step, float(record.get("walk_mps", 0.6)) * speed_multiplier):
					_next_target()
		elif _kind == "bison" or _kind == "elk":
			_update_ungulate(step, _ecosystem.call("patch", _patch_id))
		else:
			if state in ["rest", "alert"] and _state_age >= float(record.get("rest_seconds", 18.0)):
				_set_state("walk")
			elif state == "walk" and _move_toward_target(step, float(record.get("walk_mps", 0.6)) * speed_multiplier):
				_next_target()
				_set_state("rest")
		var travel: float = Vector2(_world_position.x - previous.x, _world_position.z - previous.z).length()
		if _motion != null:
			_motion.advance(state, step, travel, bool(record.get("ghost", false)))
		_body.position = _world_position - position
		if _motion == null:
			_animate(step)
	set_meta("mammal_activity", _activity)
	set_meta("motion_clip", _motion.last_clip if _motion != null else "static_or_shape_proxy")
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
	var river_id: String = str(record.get("river_id", ""))
	var reach: Dictionary = _ecosystem.call("river_state_at_position", _world_position, river_id, _id) if _ecosystem.has_method("river_state_at_position") else _ecosystem.call("reach_at", _world_position.z)
	_activity = float(reach.get("feeding_by_species", {}).get(_kind, reach.get("feeding", reach.get("fish_activity", 0.0))))
	var trout: Dictionary = _ecosystem.call("trout_state", _id) if _ecosystem.has_method("trout_state") else {}
	if not trout.is_empty():
		if not reach.get("feeding_by_species", {}).has(_kind) and not reach.has("feeding"):
			_activity = float(trout.get("feeding", _activity))
		var next_target: float = float(trout.get("refuge_s_m", trout.get("s_m", NAN)))
		if is_finite(next_target):
			target_s_m = next_target
	if not is_finite(chainage_m):
		chainage_m = float(reach.get("projected_s_m", reach.get("s_m", NAN)))
	var physical_dt: float = maxf(0.0, float(_ecosystem.elapsed) - _last_sim_time)
	_last_sim_time = maxf(_last_sim_time, float(_ecosystem.elapsed))
	var actual_ground_velocity_mps: float = 0.0
	var relative_speed_available: bool = true
	if is_finite(target_s_m) and is_finite(chainage_m) and _ecosystem.has_method("position_at_s"):
		var length: float = float(record.get("approx_dimensions_m", {}).get("body_length", 0.35))
		var sustained: float = float(record.get("sustained_swim_bl_s", _ecosystem.params.get("fish_sustained_swim_bl_s", 1.5)))
		var refuge_drive: float = float(reach.get("refuge_drive", trout.get("refuge_drive", 0.0)))
		swim_speed_mps = length * sustained * maxf(0.08, maxf(_activity, refuge_drive))
		var previous_s: float = chainage_m
		chainage_m = move_toward(chainage_m, target_s_m, swim_speed_mps * physical_dt)
		actual_ground_velocity_mps = (chainage_m - previous_s) / physical_dt if physical_dt > 0.0 else 0.0
		var next: Vector3 = _ecosystem.call("position_at_s", chainage_m, river_id)
		next.y += float(record.get("water_offset_m", 0.0))
		_face(next - _world_position, 1.0)
		_world_position = next
		_moving = chainage_m != previous_s
		state = "hold" if is_equal_approx(chainage_m, target_s_m) else "swim"
		if state == "hold":
			swim_speed_mps = 0.0
	else:
		var previous_position: Vector3 = _world_position
		swim_speed_mps = float(record.get("walk_mps", 0.2)) * maxf(0.08, _activity)
		if state == "hold":
			if _state_age > float(record.get("hold_seconds", 9.0)):
				_set_state("swim")
		elif state == "swim" and _move_toward_target(physical_dt, swim_speed_mps):
			_next_target()
			_set_state("hold")
		relative_speed_available = previous_position.is_equal_approx(_world_position)
	var downstream_current_mps: float = float(reach.get("velocity_mps", 0.0))
	if relative_speed_available:
		_update_swim_clip(water_relative_speed(actual_ground_velocity_mps, downstream_current_mps))
	set_meta("actual_ground_velocity_mps", actual_ground_velocity_mps if relative_speed_available else null)
	set_meta("water_relative_speed_status", "available_signed_chainage" if relative_speed_available else "unavailable_flow_direction")
	set_meta("feeding", _activity)
	set_meta("chainage_m", chainage_m)
	set_meta("target_s_m", target_s_m)

static func water_relative_speed(actual_ground_velocity_mps: float, downstream_current_mps: float) -> float:
	return absf(actual_ground_velocity_mps - downstream_current_mps)

static func required_tailbeat_hz(relative_speed_mps: float, length_m: float) -> float:
	# Bainbridge (1958) relation transferred to trout; below 5 Hz is extrapolated.
	return 4.0 / 3.0 * (maxf(0.0, relative_speed_mps) / maxf(length_m, 0.001) + 1.0)

func _find_swim_animations(node: Node) -> void:
	if node is AnimationPlayer:
		_animation_player = node
		for clip: StringName in _animation_player.get_animation_list():
			for pair: Array in [["Hold_1Hz", 1.0], ["Cruise_2Hz", 2.0], ["Burst_3Hz", 3.0]]:
				if str(clip).contains(pair[0]):
					_swim_clips[str(clip)] = pair[1]
					_animation_player.get_animation(clip).loop_mode = Animation.LOOP_LINEAR
	for child: Node in node.get_children():
		_find_swim_animations(child)

func _update_swim_clip(relative_speed_mps: float) -> void:
	var length: float = float(record.get("approx_dimensions_m", {}).get("body_length", 0.35))
	tailbeat_hz = required_tailbeat_hz(relative_speed_mps, length)
	set_meta("water_relative_speed_mps", relative_speed_mps)
	set_meta("tailbeat_hz", tailbeat_hz)
	set_meta("tailbeat_basis", "Bainbridge 1958 transferred to trout; sub-5 Hz extrapolation")
	set_meta("tailbeat_clock_policy", "presentation_seconds_at_simulated_relative_speed; frozen_while_paused")
	if _animation_player == null or _swim_clips.is_empty():
		return
	var chosen: String = ""
	var distance: float = INF
	for clip: String in _swim_clips:
		var d: float = absf(tailbeat_hz - float(_swim_clips[clip]))
		if d < distance:
			distance = d
			chosen = clip
	if _animation_player.current_animation != chosen:
		_animation_player.play(chosen, 0.12)
	_animation_player.speed_scale = tailbeat_hz / float(_swim_clips[chosen])

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
	elif (_medium == "river" or _medium == "river_bank") and _ecosystem != null and _ecosystem.has_method("river_state_at_position"):
		# Resample river surface elevation at each step.
		var reach_state: Dictionary = _ecosystem.call("river_state_at_position", next, str(record.get("river_id", "")), _id)
		var surface: float = float(reach_state.get("water_surface_m", NAN))
		if is_finite(surface):
			if _medium == "river":
				next.y = surface + float(record.get("water_offset_m", 0.0))
			else:
				next.y = maxf(_ground_height(next.x, next.z) + 0.015, surface + 0.015)
	_world_position = next
	_face(difference, minf(1.0, dt * 3.0))
	_moving = true
	return step_distance >= distance - 0.001

func _face(direction: Vector3, weight: float) -> void:
	# Align the local forward axis to travel.
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
		elif _animation_player == null:
			# Unrigged asset roll.
			_body.rotation.z = lerpf(_body.rotation.z, sin(_time * (3.5 if _moving else 1.6)) * 0.07, minf(1.0, dt * 3.0))
		_body.position.y += sin(_time * 1.3) * 0.012

func _sync_feeding() -> void:
	if _ecosystem == null or not is_instance_valid(_ecosystem):
		return
	if _kind == "bison" or _kind == "elk":
		_ecosystem.call("set_grazer_activity", _id, _patch_id, visible and state == "graze", float(record.get("grazing_index_per_second", 0.0000015)))
	elif _kind == "dipper" or _kind == "rainbow_trout" or _kind == "brown_trout":
		var feeding: bool = (state == "forage" and not _moving) if _kind == "dipper" else (state == "hold" and _activity > 0.0)
		_ecosystem.call("set_insect_forager_activity", _id, _patch_id, feeding, float(record.get("insect_index_per_second", 0.000003)))

func _exit_tree() -> void:
	if _motion != null:
		_motion.stop()
	if is_instance_valid(_animation_player):
		_animation_player.stop()
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
	# Scale the authored 0.31 m bird envelope.
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
