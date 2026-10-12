extends SceneTree

const ECO = preload("res://scripts/ecosystem.gd")
const ACTOR = preload("res://scripts/wildlife_actor.gd")
const TERRAIN = preload("res://scripts/height_field.gd")
var failures: Array[String] = []
var report: Dictionary = {
	"scope":"Reduced ecosystem and authored animal proxy verification; no ecological calibration claim.",
	"godot":Engine.get_version_info().string,
	"checks":["source-flow continuity", "whole-domain heat budget", "uniform-temperature invariance", "physical-time accounting", "step partition equivalence", "forage and insect debits", "all authored actor states", "aquatic route confinement", "fish clearance above terrain bed"]
}

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, note: String) -> void:
	if not condition:
		failures.append(note)
		push_error(note)

func run() -> void:
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/ecosystem.json"))
	var model: Node = ECO.new()
	check(model.configure(config), "Authored ecosystem configuration must be valid.")
	model.set_grazer_activity("test_bison", "north_meadow", true, 0.0000015)
	model.set_insect_forager_activity("test_dipper", "bridge_riparian", true, 0.000008)
	model.step(3600.0)
	check(absf(float(model.elapsed) - 3600.0) < 0.000001, "Elapsed time must remain physical seconds.")
	check(absf(float(model.river[2].flow_m3s) - 8.0) < 0.000000001, "Upstream reaches must carry exactly boundary flow.")
	check(absf(float(model.river[5].flow_m3s) - 8.26) < 0.000000001, "Source water must be added once and passed downstream.")
	check(float(model.heat_budget_error) < 0.0000001, "Whole-domain heat residual must be < 1e-7 m3*C.")
	check(float(model.water_budget_error_m3) < 0.000000001, "Whole-domain and reach water residuals must vanish.")
	var grazed: Dictionary = model.patch("north_meadow")
	check(absf(float(grazed.grazed) - 0.0054) < 0.000000001, "Grazing consumption must equal active registered demand.")
	check(float(grazed.plant_budget_error) < 0.000000000001, "Plant mass-index budget must balance.")
	check(float(model.patch("bridge_riparian").insects_consumed) > 0.0287, "Registered dipper must consume shared insect resource.")
	check(float(model.patch("unknown").biomass) == 0.0, "Missing habitat must not silently map to another patch.")
	for r: Dictionary in model.river:
		check(is_finite(float(r.temperature_c)) and float(r.temperature_c) >= 7.0 and float(r.temperature_c) <= 62.0, "Thermal solution must remain finite and inside input bounds.")
	print("ECO one_hour heat_residual=",model.heat_budget_error," water_residual=",model.water_budget_error_m3," grazed=",grazed.grazed)
	report["one_hour_max_heat_residual_m3_degC"] = float(model.heat_budget_error)
	report["one_hour_water_residual_m3"] = float(model.water_budget_error_m3)
	report["one_hour_registered_grazing_index"] = float(grazed.grazed)
	model.free()

	var uniform: Dictionary = config.duplicate(true)
	uniform.boundary_c = 20.0
	uniform.weather.night_air_c = 20.0
	uniform.weather.day_warming_c = 0.0
	for r: Dictionary in uniform.river_reaches:
		r.temperature_c = 20.0
		for source: Dictionary in r.get("lateral_sources", []):
			source.temperature_c = 20.0
	var constant_model: Node = ECO.new()
	constant_model.configure(uniform)
	constant_model.step(3600.0)
	for r: Dictionary in constant_model.river:
		check(absf(float(r.temperature_c) - 20.0) < 0.0000000001, "Uniform temperature must be exactly preserved despite a lateral water source.")
	print("ECO uniform20C heat_residual=",constant_model.heat_budget_error)
	report["uniform_20c_heat_residual_m3_degC"] = float(constant_model.heat_budget_error)
	constant_model.free()

	var batch: Node = ECO.new()
	var serial: Node = ECO.new()
	batch.configure(config)
	serial.configure(config)
	batch.step(100.75)
	for i: int in range(100):
		serial.step(1.0)
	serial.step(0.75)
	for i: int in range(batch.river.size()):
		check(absf(float(batch.river[i].temperature_c) - float(serial.river[i].temperature_c)) < 0.0000000001, "Large request and equivalent stable substeps must match.")
	batch.free()
	serial.free()

	var host: Node3D = Node3D.new()
	root.add_child(host)
	var live: Node = ECO.new()
	host.add_child(live)
	live.set_process(false)
	var terrain: RefCounted = TERRAIN.new()
	var actors: Array[Node3D] = []
	for record: Dictionary in live.params.wildlife:
		var actor: Node3D = ACTOR.new()
		actor.setup(record, terrain, live)
		host.add_child(actor)
		actor.set_process(false)
		check(bool(actor.get("_valid")), "Actor route must be valid: " + str(record.id))
		check(actor.get_node_or_null("ArticulatedProxy") != null, "Actor art must construct: " + str(record.id))
		actors.append(actor)
	var states_seen: Dictionary = {}
	for i: int in range(1800):
		if i % 10 == 0:
			live.step(1.0)
		for actor: Node3D in actors:
			actor._process(0.1)
			states_seen[str(actor.record.id) + ":" + str(actor.state)] = true
			var pos: Vector3 = actor.get("_world_position")
			check(pos.is_finite(), "Actor position must remain finite.")
			if str(actor.record.medium) == "river":
				var route: PackedVector3Array = actor.get("_route")
				var minimum: float = INF
				for j: int in range(1, route.size()):
					minimum = minf(minimum, pos.distance_to(Geometry3D.get_closest_point_to_segment(pos, route[j - 1], route[j])))
				check(minimum < 0.002, "Aquatic actor must remain on saved water elevation route: " + str(actor.record.id))
				if str(actor.record.kind).contains("trout"):
					check(pos.y - float(terrain.sample(pos.x, pos.z)) > 0.08, "Fish must remain clear of carved bed: " + str(actor.record.id))
	check(actors.size() == 12, "Exact authored actor count must be respected.")
	check(states_seen.has("bison_01:graze") and states_seen.has("bison_01:walk"), "Bison must graze and walk.")
	check(states_seen.has("dipper_01:perch") and states_seen.has("dipper_01:forage") and states_seen.has("dipper_01:return"), "Dipper must perch, forage and return.")
	check(states_seen.has("raven_01:return"), "Raven must complete its authored foraging circuit.")
	check(states_seen.has("trout_01:swim") and states_seen.has("trout_01:hold"), "Trout must alternate holding and swimming.")
	check(float(live.patch("north_meadow").grazed) > 0.0, "Visible bison grazing must debit patch forage.")
	check(float(live.patch("bridge_riparian").insects_consumed) > 0.0, "Visible aquatic foraging must debit shared insect resource.")
	print("ECO actors=",actors.size()," states_seen=",states_seen.keys()," graze_index=",live.patch("north_meadow").grazed," insects_consumed=",live.patch("bridge_riparian").insects_consumed)
	report["actor_count"] = actors.size()
	report["actor_simulation_seconds"] = 180.0
	report["actor_states_seen"] = states_seen.keys()
	report["visible_grazing_index_consumed"] = float(live.patch("north_meadow").grazed)
	report["visible_insect_index_consumed"] = float(live.patch("bridge_riparian").insects_consumed)
	host.free()
	report["pass"] = failures.is_empty()
	report["failures"] = failures
	report["ecosystem_data_sha256"] = FileAccess.get_sha256("res://data/ecosystem.json")
	report["world_data_sha256"] = FileAccess.get_sha256("res://data/world.json")
	report["terrain_sha256"] = FileAccess.get_sha256("res://data/terrain.f32")
	DirAccess.make_dir_recursive_absolute("res://tests")
	var file: FileAccess = FileAccess.open("res://tests/ecology_validation.json", FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(report, "\t") + "\n")
		file.close()
	else:
		failures.append("Could not save tests/ecology_validation.json")
	if failures.is_empty():
		print("ECO_VERIFICATION_PASS")
		quit(0)
	else:
		print("ECO_VERIFICATION_FAILURES=",failures.size())
		quit(1)
