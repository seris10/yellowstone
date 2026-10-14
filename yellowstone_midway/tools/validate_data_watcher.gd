extends SceneTree

const Watcher = preload("res://scripts/data_watcher.gd")
const Ecosystem = preload("res://scripts/ecosystem.gd")
var applied: bool = false

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var path: String = "res://tests/watcher_ecosystem_fixture.json"
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/ecosystem.json"))
	config["python_series"] = []
	var file: FileAccess = FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(config))
	file.close()
	var model: Node = Ecosystem.new()
	model.configure(config)
	model.elapsed = 600.0
	model.set_process(false)
	var watcher: Node = Watcher.new()
	watcher.watch(path, func(changed: String):
		model.configure(JSON.parse_string(FileAccess.get_file_as_string(changed)))
		applied = true)
	root.add_child(watcher)
	var before: int = Time.get_ticks_msec()
	config["boundary_m3s"] = 4.25
	config.river_reaches[0]["flow_m3s"] = 4.25
	file = FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(config))
	file.close()
	while not applied and Time.get_ticks_msec() - before < 2100:
		await create_timer(0.01).timeout
	var seconds: float = float(Time.get_ticks_msec() - before) / 1000.0
	var passed: bool = applied and seconds < 2.0 and model.params.boundary_m3s == 4.25 and model.elapsed == 600.0
	watcher.queue_free()
	model.free()
	print("DATA_WATCHER_VALIDATION ", "PASS" if passed else "FAIL", " applied_s=", seconds)
	quit(0 if passed else 1)
