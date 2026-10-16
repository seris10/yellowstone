extends SceneTree

const ECO = preload("res://scripts/ecosystem.gd")
const ACTOR = preload("res://scripts/wildlife_actor.gd")
const TERRAIN = preload("res://scripts/height_field.gd")
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, note: String) -> void:
	if not condition:
		failures.append(note)
		push_error(note)

func run() -> void:
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/ecosystem.json"))
	var series: Array = [{"t_s": 0, "epoch_unix": 1784052000, "weather": {"air_temperature_c": 15, "wind_xz_mps": [2, 1]}, "patches": [{"id": "north_meadow", "biomass": 0.8}]}, {"t_s": 3600, "epoch_unix": 1784055600, "weather": {"air_temperature_c": 19, "wind_xz_mps": [3, 2]}, "patches": [{"id": "north_meadow", "biomass": 0.6}]}]
	var published: Dictionary = config.duplicate(true)
	published["python_series"] = series
	published["frame_header"] = {"run_mode": "scenario", "model_components": {"temperature_c": {"component_id": "1-D advection-dispersion replay"}}}
	var model: Node = ECO.new()
	check(model.configure(published), "Published ecosystem validates")
	check(model.frame_header.model_components.temperature_c.component_id == "1-D advection-dispersion replay", "Baked top-level frame header reaches the runtime reader")
	model.step(1800)
	check(model.elapsed == 1800 and model.air_c == 17.0, "Weather interpolates Python series")
	check(absf(float(model.patch("north_meadow").biomass) - 0.7) < 0.000001, "Biomass interpolates Python series")
	model.set_grazer_activity("bison", "north_meadow", true, 0.1)
	model.step(1800)
	check(absf(float(model.patch("north_meadow").biomass) - 0.6) < 0.000001, "Godot actor registration leaves Python biomass authoritative")
	var changed: Dictionary = published.duplicate(true)
	changed["boundary_m3s"] = 4.0
	model.configure(changed)
	check(model.elapsed == 3600 and model.params.boundary_m3s == 4.0, "Hot configure preserves clock and boundary")
	model.live_mode = true
	model.apply_python_frame({"epoch_unix": 1784055600, "weather": {"air_c": 23.0}, "header": {"run_mode": "live_test"}})
	model.configure(changed)
	check(model.air_c == 23.0 and model.frame_header.run_mode == "live_test", "Live hot configure preserves the current Python frame and header")
	model.step(60)
	check(model.elapsed == 3600 and model.air_c == 23.0, "Live frame owns time and weather")
	var host: Node3D = Node3D.new()
	root.add_child(host)
	var state: Node = ECO.new()
	host.add_child(state)
	state.set_process(false)
	var terrain: RefCounted = TERRAIN.new()
	var actor_count: int = 0
	for record: Dictionary in state.params.get("wildlife", []):
		var actor: Node3D = ACTOR.new()
		actor.setup(record, terrain, state)
		host.add_child(actor)
		actor.set_process(false)
		check(bool(actor.get("_valid")), "Saved actor route: " + str(record.id))
		check(actor.get_node_or_null("ArticulatedProxy") != null, "Actor art: " + str(record.id))
		actor._process(0.1)
		check(actor.get("_world_position").is_finite(), "Actor position finite")
		actor_count += 1
	check(actor_count == config.get("wildlife", []).size(), "Actor roster cardinality")
	var report: Dictionary = {"scope": "Python-state consumption and authored actor presentation", "godot": Engine.get_version_info().string, "actor_count": actor_count, "passed": failures.is_empty(), "failures": failures, "ecosystem_sha256": FileAccess.get_sha256("res://data/ecosystem.json")}
	var file: FileAccess = FileAccess.open("res://tests/ecology_validation.json", FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(report, "\t") + "\n")
		file.close()
	host.free()
	model.free()
	print("ECO_VERIFICATION_", "PASS" if failures.is_empty() else "FAIL", " actors=", actor_count, " failures=", failures.size())
	quit(0 if failures.is_empty() else 1)
