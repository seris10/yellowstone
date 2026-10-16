extends SceneTree
## Focused collision integration test: the player class supplies its capsule, floor angle, snap and safe margin, and acceleration and gravity follow deterministic waypoint input. Run: godot --headless --fixed-fps 60 --path . --script tools/validate_walk.gd
const PHYSICS_HZ: int = 60
const ARRIVAL_RADIUS_M: float = 0.17
var spec: Dictionary = {}
var authored_world: Node3D
var report: Dictionary = {
	"scope":"Focused native-collision walks: two bridges in both directions, upper overlook approach, one boardwalk junction, plus two must-fail controls (settle gate outside the world, straight steering through the solid overlook deck).",
	"limitations":["Not the complete overlook-to-boardwalk route or all park routes.","Ideal centerline steering; no manual-controller or visual-quality certification.","Independent cases have an initial placement and settling period; positions are never corrected within a walk.","Water/swimming, vehicles, side-of-deck railing impacts, arbitrary off-trail traversal, and hardware performance are outside this test.","Controls prove the instrument can fail: the deck control accepts any walk-failure reason and prints it for review."],
	"physics_hz":PHYSICS_HZ,
	"jump_enabled":false,
	"flight_enabled":false,
	"teleports_within_walk":0,
	"cases":[],
	"failures":[]
}

class WalkingProbe:
	extends "res://scripts/player.gd"
	var commanded: bool = false
	var target_point: Vector3 = Vector3.ZERO
	var movement_calls: int = 0
	func _physics_process(delta: float) -> void:
		var direction: Vector3 = Vector3.ZERO
		if commanded:
			direction = Vector3(target_point.x - global_position.x, 0.0, target_point.z - global_position.z).normalized()
			if direction.length_squared() > 0.001:
				rotation.y = atan2(-direction.x,-direction.z)
		# Match player.gd walking.
		velocity.x = move_toward(velocity.x,direction.x * walk_speed,delta * 7.0)
		velocity.z = move_toward(velocity.z,direction.z * walk_speed,delta * 7.0)
		if not is_on_floor():
			velocity.y -= 9.81 * delta
		move_and_slide()
		movement_calls += 1

func _initialize() -> void:
	Engine.physics_ticks_per_second = PHYSICS_HZ
	call_deferred("run")

func route(id: String) -> Dictionary:
	for item: Dictionary in spec.get("routes", []):
		if str(item.id) == id:
			return item
	return {}

func route_points(id: String, first: int, last: int) -> PackedVector3Array:
	var found: Dictionary = route(id)
	var result: PackedVector3Array = PackedVector3Array()
	if found.is_empty():
		return result
	var points: Array = found.points
	var direction: int = 1 if last >= first else -1
	for i: int in range(first,last + direction,direction):
		if i < 0 or i >= points.size():
			return PackedVector3Array()
		var p: Array = points[i]
		result.append(Vector3(float(p[0]),float(p[1]),float(p[2])))
	return result

func bridge_cases(id: String, name: String) -> Array[Dictionary]:
	var found: Dictionary = route(id)
	var spans: Array = found.get("bridge_spans", [])
	if spans.is_empty():
		report.failures.append("Missing exact bridge_spans for " + id)
		return []
	var span: Array = spans[0]
	var first: int = maxi(0,int(span[0]) - 4)
	var last: int = mini(found.points.size() - 1,int(span[1]) + 4)
	var forward: PackedVector3Array = route_points(id,first,last)
	var reverse: PackedVector3Array = route_points(id,last,first)
	var provenance: Dictionary = {"route_id":id,"bridge_span_indices":span,"approach_margin_points":4,"selected_indices":[first,last]}
	var reverse_provenance: Dictionary = provenance.duplicate(true)
	reverse_provenance.selected_indices = [last,first]
	return [{"id":name + "_forward","points":forward,"parts":[provenance],"width_m":float(found.width)},{"id":name + "_reverse","points":reverse,"parts":[reverse_provenance],"width_m":float(found.width)}]

func run() -> void:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/world.json"))
	if not parsed is Dictionary:
		report.failures.append("Missing/invalid world.json")
		finish()
		return
	spec = parsed
	var scene: PackedScene = load("res://scenes/authored_world.tscn")
	if scene == null:
		report.failures.append("Could not load native authored world.")
		finish()
		return
	authored_world = scene.instantiate()
	root.add_child(authored_world)
	if ResourceLoader.exists("res://scenes/handcrafted_details.tscn"):
		root.add_child(load("res://scenes/handcrafted_details.tscn").instantiate())
	# Install the core and its matching master triangle collisions.
	report["core_terrain"] = install_core_terrain()
	if not bool(report.core_terrain.get("collision_complete", false)):
		report.failures.append("Core collision cut incomplete; walking fixture cannot certify the live terrain.")
		finish()
		return
	# Allow static collision shapes to register.
	for tick: int in range(3):
		await physics_frame
	var cases: Array[Dictionary] = []
	cases.append_array(bridge_cases("trail_3226_0","midway_bridge"))
	cases.append_array(bridge_cases("trail_3321_0","fairy_falls_bridge"))
	var upper: PackedVector3Array = route_points("trail_3454_0",12,0)
	var spur_end: int = route("trail_3455_0").get("points", []).size() - 1
	var spur: PackedVector3Array = route_points("trail_3455_0",1,spur_end)
	upper.append_array(spur)
	cases.append({"id":"overlook_upper_approach_and_spur","points":upper,"width_m":2.3,"parts":[{"route_id":"trail_3454_0","selected_indices":[12,0]},{"route_id":"trail_3455_0","selected_indices":[1,spur_end]}]})
	var boardwalk_a: int = route("trail_3228_0").get("points", []).size() - 1
	var joint: PackedVector3Array = route_points("trail_3228_0",boardwalk_a - 7,boardwalk_a)
	joint.append_array(route_points("trail_3230_0",1,9))
	cases.append({"id":"boardwalk_3228_to_3230_junction","points":joint,"width_m":2.1,"parts":[{"route_id":"trail_3228_0","selected_indices":[boardwalk_a - 7,boardwalk_a]},{"route_id":"trail_3230_0","selected_indices":[1,9]}]})
	# Core-crossing boardwalk case: a boardwalk span whose points sit over the thermal-core tile.
	cases.append(core_crossing_case())
	# Negative controls: probe aimed where walking must fail.
	cases.append({"id":"control_settle_outside_world","points":PackedVector3Array([Vector3(3000,0,3000),Vector3(3001,0,3000)]),"width_m":2.0,"parts":[{"control":"settle gate; spawn has no collision"}],"control_expect":"Could not settle on intended start surface."})
	var hf: RefCounted = load("res://scripts/height_field.gd").new()
	var deck_west := Vector3(-260,hf.sample(-260.0,159.0),159)
	var deck_east := Vector3(-244,hf.sample(-244.0,159.0),159)
	cases.append({"id":"control_blocked_by_overlook_deck","points":PackedVector3Array([deck_west,deck_east]),"width_m":6.0,"parts":[{"control":"must fail; straight steering through the solid overlook deck at x=-252 z=159"}],"control_expect":"Blocked for more than four seconds; no jump or correction permitted."})
	for test: Dictionary in cases:
		var result: Dictionary = await walk_case(test)
		if test.has("control_expect"):
			var expected: String = str(test.control_expect)
			var control_ok: bool = not bool(result.pass)
			result["control_expect"] = expected
			result["control_pass"] = control_ok
			print("WALK ",result.id," ","CONTROL-PASS" if control_ok else "CONTROL-FAIL"," failure=",result.failure," expected=",expected)
			report.cases.append(result)
			if not control_ok:
				report.failures.append(str(result.id) + ": control walked through; expected failure: " + expected)
			continue
		report.cases.append(result)
		if not bool(result.pass):
			report.failures.append(str(result.id) + ": " + str(result.failure))
		print("WALK ",result.id," ","PASS" if result.pass else "FAIL"," distance_m=",snappedf(float(result.walked_horizontal_m),0.01)," max_cross_track_m=",snappedf(float(result.max_cross_track_m),0.001)," failure=",result.failure)
	finish()

func walk_case(test: Dictionary) -> Dictionary:
	var points: PackedVector3Array = test.points
	var result: Dictionary = {"id":test.id,"source_parts":test.parts,"pass":false,"failure":"","walked_horizontal_m":0.0,"max_cross_track_m":0.0,"max_airborne_seconds":0.0,"minimum_height_over_centerline_m":null,"maximum_height_over_centerline_m":null,"wall_contacts":[],"trace_each_second":[]}
	if points.size() < 2:
		result.failure = "Missing or insufficient source points."
		return result
	var cumulative: PackedFloat64Array = PackedFloat64Array([0.0])
	for i: int in range(1,points.size()):
		cumulative.append(cumulative[i - 1] + Vector2(points[i].x - points[i - 1].x,points[i].z - points[i - 1].z).length())
	var total_m: float = cumulative[cumulative.size() - 1]
	result["planned_horizontal_m"] = total_m
	var probe: WalkingProbe = WalkingProbe.new()
	probe.name = "WalkingValidationProbe"
	# One initial placement for this case.
	probe.position = points[0] + Vector3.UP * 0.55
	root.add_child(probe)
	var capsule: CapsuleShape3D = null
	for child: Node in probe.get_children():
		if child is CollisionShape3D and child.shape is CapsuleShape3D:
			capsule = child.shape
	if capsule == null:
		result.failure = "Actual player did not create its capsule."
		probe.queue_free()
		await physics_frame
		return result
	result["controller"] = {"source":"res://scripts/player.gd inherited _ready capsule; ordinary 7m/s² acceleration and 9.81m/s² gravity reproduced without player input","speed_mps":probe.walk_speed,"capsule_radius_m":capsule.radius,"capsule_height_m":capsule.height,"floor_snap_m":probe.floor_snap_length,"safe_margin_m":probe.safe_margin,"floor_max_angle_degrees":rad_to_deg(probe.floor_max_angle)}
	for tick: int in range(120):
		await physics_frame
	if not probe.is_on_floor() or probe.position.y < points[0].y - 0.65:
		result.failure = "Could not settle on intended start surface."
		result["start_position_m"] = vector_array(probe.position)
		probe.queue_free()
		await physics_frame
		return result
	result["settled_start_m"] = vector_array(probe.position)
	var target_index: int = 1
	probe.target_point = points[target_index]
	probe.commanded = true
	var previous: Vector3 = probe.position
	var maximum_ticks: int = int(ceil((total_m / float(probe.walk_speed) * 3.0 + 12.0) * float(PHYSICS_HZ)))
	var airborne: float = 0.0
	var stagnant: float = 0.0
	var checkpoint_progress: float = 0.0
	var wall_seen: Dictionary = {}
	var ticks_walked: int = 0
	for tick: int in range(maximum_ticks):
		await physics_frame
		ticks_walked += 1
		var position: Vector3 = probe.position
		result.walked_horizontal_m = float(result.walked_horizontal_m) + Vector2(position.x - previous.x,position.z - previous.z).length()
		previous = position
		var nearest: Dictionary = nearest_centerline(position,points)
		var height_above: float = position.y - float(nearest.height)
		result.max_cross_track_m = maxf(float(result.max_cross_track_m),float(nearest.distance))
		result.minimum_height_over_centerline_m = height_above if result.minimum_height_over_centerline_m == null else minf(float(result.minimum_height_over_centerline_m),height_above)
		result.maximum_height_over_centerline_m = height_above if result.maximum_height_over_centerline_m == null else maxf(float(result.maximum_height_over_centerline_m),height_above)
		airborne = 0.0 if probe.is_on_floor() else airborne + 1.0 / float(PHYSICS_HZ)
		result.max_airborne_seconds = maxf(float(result.max_airborne_seconds),airborne)
		var remaining_to_target: float = Vector2(position.x - points[target_index].x,position.z - points[target_index].z).length()
		var progress: float = cumulative[target_index] - remaining_to_target
		if progress > checkpoint_progress + 0.08:
			checkpoint_progress = progress
			stagnant = 0.0
		else:
			stagnant += 1.0 / float(PHYSICS_HZ)
		for collision_index: int in range(probe.get_slide_collision_count()):
			var collision: KinematicCollision3D = probe.get_slide_collision(collision_index)
			if collision.get_normal().dot(Vector3.UP) < cos(probe.floor_max_angle):
				var collider: Object = collision.get_collider()
				var path: String = str(collider.get_path()) if collider is Node else str(collider)
				if not wall_seen.has(path):
					wall_seen[path] = true
					result.wall_contacts.append({"collider":path,"normal":vector_array(collision.get_normal()),"position_m":vector_array(position),"contact_point_m":vector_array(collision.get_position()),"target_index":target_index})
		if tick % PHYSICS_HZ == 0:
			result.trace_each_second.append({"seconds":float(tick) / float(PHYSICS_HZ),"position_m":vector_array(position),"on_floor":probe.is_on_floor(),"target_index":target_index})
		if height_above < -0.65:
			result.failure = "Fell below the intended route/bridge deck."
		elif height_above > 0.8:
			result.failure = "Body rode terrain/obstruction above the intended route."
		elif airborne > 0.8:
			result.failure = "Sustained floor loss while ordinary walking."
		elif float(nearest.distance) > float(test.width_m) * 0.5 - capsule.radius + 0.12:
			result.failure = "Left the centerline corridor while following ordinary walking input."
		elif stagnant > 4.0:
			result.failure = "Blocked for more than four seconds; no jump or correction permitted."
		if not str(result.failure).is_empty():
			break
		if remaining_to_target <= ARRIVAL_RADIUS_M:
			if target_index == points.size() - 1:
				result.pass = true
				break
			target_index += 1
			probe.target_point = points[target_index]
	if not bool(result.pass) and str(result.failure).is_empty():
		result.failure = "Timed out before reaching every waypoint."
	probe.commanded = false
	result["simulation_seconds"] = float(ticks_walked) / float(PHYSICS_HZ)
	result["reached_waypoint_index"] = target_index
	result["waypoint_count"] = points.size()
	result["final_position_m"] = vector_array(probe.position)
	result["final_velocity_mps"] = vector_array(probe.velocity)
	result["final_on_floor"] = probe.is_on_floor()
	result["movement_calls_including_settle"] = probe.movement_calls
	probe.queue_free()
	await physics_frame
	return result

func nearest_centerline(position: Vector3, points: PackedVector3Array) -> Dictionary:
	var at: Vector2 = Vector2(position.x,position.z)
	var best: float = INF
	var height: float = points[0].y
	for i: int in range(1,points.size()):
		var a: Vector2 = Vector2(points[i - 1].x,points[i - 1].z)
		var b: Vector2 = Vector2(points[i].x,points[i].z)
		var closest: Vector2 = Geometry2D.get_closest_point_to_segment(at,a,b)
		var distance: float = at.distance_to(closest)
		if distance < best:
			best = distance
			var fraction: float = a.distance_to(closest) / maxf(0.00001,a.distance_to(b))
			height = lerpf(points[i - 1].y,points[i].y,fraction)
	return {"distance":best,"height":height}

func vector_array(vector: Vector3) -> Array[float]:
	return [vector.x,vector.y,vector.z]

func install_core_terrain() -> Dictionary:
	# Mirror world.gd.build_core_terrain for the walk-collision context.
	var info: Dictionary = {"built": false, "cut_tiles": 0}
	if not ResourceLoader.exists("res://scripts/core_terrain.gd") or not ResourceLoader.exists("res://scripts/mat_surface.gd"):
		info["reason"] = "scripts absent"
		return info
	var mat_surface_script: Script = load("res://scripts/mat_surface.gd")
	var mat_surface: RefCounted = mat_surface_script.new()
	mat_surface.load_outflow()
	mat_surface.load_pigment()
	var core_script: Script = load("res://scripts/core_terrain.gd")
	var core: Node3D = core_script.new()
	core.name = "CoreTerrain"
	root.add_child(core)
	var ok: bool = core.build(mat_surface)
	if not ok:
		info["reason"] = "core.build returned false"
		return info
	info["built"] = true
	info["extent_rect"] = core.extent_rect()
	info["heights_minmax"] = core.heights_minmax()
	var authored_scene: Node = authored_world
	if authored_scene != null:
		info["cut_tiles"] = core.cut_master_tiles(authored_scene)
	info["cut_report"] = core.render_cut_status()
	info["collision_complete"] = bool(info.cut_report.get("collision_complete", false))
	info["core_script_sha256"] = FileAccess.get_sha256("res://scripts/core_terrain.gd")
	return info

func core_crossing_case() -> Dictionary:
	# A boardwalk span through the Grand Prismatic approach, selected because every point lies in the core tile.
	var crossing_route_id: String = "trail_3321_0"
	var found: Dictionary = route(crossing_route_id)
	if found.is_empty() or not found.has("points"):
		return {"id": "core_crossing_route_missing", "points": PackedVector3Array(), "width_m": 2.0, "parts": [{"route_id": crossing_route_id}]}
	var all_points: Array = found["points"]
	# Clip to a contiguous run whose xz is inside the core footprint.
	var core_x_min: float = -340.0
	var core_x_max: float = 260.0
	var core_z_min: float = -380.0
	var core_z_max: float = 220.0
	var first: int = -1
	var last: int = -1
	for i: int in range(all_points.size()):
		var p: Array = all_points[i]
		var x: float = float(p[0])
		var z: float = float(p[2])
		var inside: bool = x >= core_x_min and x <= core_x_max and z >= core_z_min and z <= core_z_max
		if inside and first == -1:
			first = i
		if inside:
			last = i
		if not inside and first != -1:
			break
	if first == -1 or last - first < 3:
		return {"id": "core_crossing_route_outside_extent", "points": PackedVector3Array(), "width_m": 2.0, "parts": [{"route_id": crossing_route_id}]}
	var pts: PackedVector3Array = PackedVector3Array()
	for i: int in range(first, last + 1):
		var p: Array = all_points[i]
		pts.append(Vector3(float(p[0]), float(p[1]), float(p[2])))
	return {"id": "core_crossing_boardwalk", "points": pts, "width_m": float(found.get("width", 2.1)), "parts": [{"route_id": crossing_route_id, "selected_indices": [first, last]}]}

func finish() -> void:
	# Count: the fixed test cases plus the new core-crossing case.
	report["pass"] = report.failures.is_empty() and report.cases.size() == 9
	report["godot"] = Engine.get_version_info().string
	report["native_scene_sha256"] = FileAccess.get_sha256("res://scenes/authored_world.tscn")
	report["world_data_sha256"] = FileAccess.get_sha256("res://data/world.json")
	report["terrain_sha256"] = FileAccess.get_sha256("res://data/terrain.f32")
	report["player_script_sha256"] = FileAccess.get_sha256("res://scripts/player.gd")
	DirAccess.make_dir_recursive_absolute("res://tests")
	var file: FileAccess = FileAccess.open("res://tests/walking_validation.json",FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(report,"\t") + "\n")
		file.close()
	else:
		report.pass = false
		push_error("Could not save walking validation report.")
	print("WALKING_VALIDATION ","PASS" if report.pass else "FAIL"," cases=",report.cases.size()," failures=",report.failures)
	quit(0 if report.pass else 1)
