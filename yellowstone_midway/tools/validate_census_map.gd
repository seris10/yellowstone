extends SceneTree
## Validate unmeasured ExG values and the census map color state.

const MapView := preload("res://scripts/map_view.gd")
var failures: Array[String] = []
var checks := 0

func _initialize() -> void:
	call_deferred("verify")

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		push_error(message)

func verify() -> void:
	var map := MapView.new()
	root.add_child(map)
	map.set_census([{"peak_exg": null}, {}, {"peak_exg": "0.25"}, {"peak_exg": NAN}, "invalid row"])
	check(not map._has_exg_quartiles, "Unmeasured ExG must not create numeric quartiles")
	check(is_nan(map._exg_value(null)) and is_nan(map._exg_value("0.25")), "Null and text ExG must remain unmeasured")
	check(is_nan(map._exg_value(INF)), "Infinite ExG must remain unmeasured")
	var neutral: Color = map._crown_color(NAN)
	check(neutral == map._crown_color(0.0), "A dataset without ExG uses the neutral color")
	map.set_census([{"peak_exg": -.2}, {"peak_exg": 0}, {"peak_exg": .3}, {"peak_exg": .9}, {"peak_exg": null}])
	check(map._has_exg_quartiles, "Four finite samples define quartiles")
	check(map._exg_quartiles == PackedFloat32Array([0.0, .3, .9]), "Missing ExG must not alter the finite-sample quartiles")
	check(map._exg_value(0) == 0.0, "Measured zero ExG remains numeric")
	check(map._crown_color(NAN) == neutral and map._crown_color(.5) != neutral, "Unmeasured values remain distinct from measured color classes")
	map.set_census([{"peak_exg": null}])
	check(not map._has_exg_quartiles and map._crown_color(NAN) == neutral, "A new unmeasured dataset clears prior numeric color state")
	var census: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/census.json"))
	var payload: Dictionary = census.get("payload", census)
	var rows: Array = payload.get("trees", [])
	check(not rows.is_empty(), "Published census rows exist")
	var before := JSON.stringify(rows).sha256_text()
	map.set_census(rows)
	check(JSON.stringify(rows).sha256_text() == before, "Map setup must preserve published census measurements")
	print("CENSUS_MAP_", "PASS" if failures.is_empty() else "FAIL", " checks=", checks, " rows=", rows.size(), " failures=", failures)
	map.free()
	await process_frame
	quit(0 if failures.is_empty() else 1)
