extends SceneTree

var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, message: String) -> void:
	if not value:
		failures.append(message)
		push_error(message)

func run() -> void:
	ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:18878")
	var world: Node = load("res://scenes/main.tscn").instantiate()
	root.add_child(world)
	var deadline: int = Time.get_ticks_msec() + 10000
	while not world.live_client.live and Time.get_ticks_msec() < deadline:
		await create_timer(0.01).timeout
	check(world.live_client.live, "World creates the local Python client")
	world.simulation_panel.visible = true
	await create_timer(0.4).timeout
	var schema: Dictionary = world.live_client.schema
	var expected_sliders: int = 0
	var expected_bools: int = 0
	for entry: Dictionary in schema.get("controls", []):
		if entry.get("min") != null and entry.get("max") != null:
			expected_sliders += 1
		if str(entry.get("type", "")) == "boolean":
			expected_bools += 1
	var sliders: int = 0
	var bools: int = 0
	var stack: Array[Node] = [world.simulation_panel]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		sliders += 1 if node is HSlider else 0
		bools += 1 if node is CheckButton else 0
		for child: Node in node.get_children():
			stack.append(child)
	check(sliders == expected_sliders and bools == expected_bools, "Conditions controls reflect schema types")
	var status: String = world.simulation_status_text()
	check(status.contains("live Python") and status.contains("buffer") and status.contains("x"), "HUD names mode, scale and headroom")
	check(world.simulation_panel.model_notes().contains("advection-dispersion"), "Field notes identify the river component")
	check(world.simulation_panel.model_notes().contains("temperature_c |"), "Field notes name each quantity from the component mapping")
	for stage: String in ["solar", "soil", "runoff"]:
		var source: Dictionary = world.simulation_panel.call("_model_for", stage, "unresolved")
		var relative: String = str(source.get("source_file", ""))
		var absolute: String = ProjectSettings.globalize_path("res://../yellowstone_python/yellowstone_python/").path_join(relative.trim_prefix("yellowstone_python/"))
		check(not relative.is_empty() and FileAccess.file_exists(absolute), "Stage source link resolves: " + stage)
	var probe: String = world.simulation_panel.probe_text({"cell_id": "test", "temperature_c": 17.0, "depth_m": 1.0, "velocity_mps": 0.5, "oxygen_mg_l": 8.0, "shading_factor": 0.5, "trout_suitability_u": 0.2, "refuge_drive": 0.0})
	check(probe.contains("17.000 C") and probe.contains("8.000 mg/L") and probe.contains("advection-dispersion"), "Probe displays frame units and component source")
	var headers: Array = [{"t_s": 0.0, "epoch_unix": 1784052000.0, "temperature_c": [15.0, 15.0, 15.0], "trout": {"s_m": 10.0, "feeding": 1.0}}, {"t_s": 600.0, "epoch_unix": 1784052600.0, "temperature_c": [16.0, 17.0, 18.0], "trout": {"s_m": 10.0, "feeding": 1.0}}]
	world.process_mode = Node.PROCESS_MODE_DISABLED
	world.capture_comparison_origins()
	var marked_id: String = str(world.get("_comparison_origins").keys()[0])
	var marked_actor: Node3D = world.get_node(NodePath(marked_id))
	marked_actor.chainage_m = 1234.0
	world.capture_comparison_origins()
	marked_actor.chainage_m = 2000.0
	world.apply_comparison({"a_frames": headers, "metrics": {"refuge_shift_m": 0}})
	check(world.get("_ghost_trout").size() == 4 and world.has_node("ComparisonRibbon"), "A branch creates ghost trout and split ribbon")
	for ghost: Node3D in world.get("_ghost_trout"):
		if str(ghost.record.id) == marked_id:
			check(ghost.chainage_m == 1234.0, "Ghost motion starts at the marked chainage rather than later B motion")
	world.reset_comparison()
	world.capture_comparison_origins()
	check(world.get("_ghost_trout").is_empty() and not world.has_node("ComparisonRibbon"), "A new mark clears the old ghost branch")
	world.apply_comparison({"a_frames": headers, "metrics": {"refuge_shift_m": 0}})
	check(world.get("_ghost_trout").size() == 4 and world.has_node("ComparisonRibbon"), "A new mark rebuilds the ghost branch")
	var buffered: Array = world.ecosystem.get("_frames")
	var adopted_time: float = minf(float(buffered[0].t_s) + 1.0, float(buffered[-1].t_s))
	var current: Dictionary = {"time_scale": 60.0, "paused": true, "clock_held": false, "computing": false, "timings": {"river": 1.2}, "run_mode": "scenario"}
	world.call("_python_frames", {"frames": [], "player_t_s": adopted_time, "header": current})
	check(world.ecosystem.elapsed == adopted_time and world.ecosystem.time_scale == 60.0 and world.ecosystem.paused, "Renderer adopts the authoritative Python clock")
	check(world.ecosystem.frame_header.timings.river == 1.2, "Historical frame metadata preserves the current computation header")
	var held: Dictionary = {"time_scale": 600.0, "paused": false, "clock_held": true, "computing": true, "clock_debt_s": 120.0}
	var held_position: Vector3 = marked_actor.get("_world_position")
	for i: int in range(5):
		world.call("_python_frames", {"frames": [], "player_t_s": adopted_time, "header": held})
		world.ecosystem._process(0.25)
		marked_actor._process(0.25)
		check(world.ecosystem.elapsed == adopted_time and marked_actor.get("_world_position") == held_position, "Repeated held API payload preserves the world clock and actor position")
	check(world.ecosystem.clock_held and not world.ecosystem.paused, "World distinguishes backend hold from user pause")
	world.ecosystem.paused = false
	world.step_simulation()
	check(world.ecosystem.paused, "One-frame stepping leaves the renderer paused")
	world.get("_overlays").call("reload", world, world.get("_plume_field_summary"), world.get("_geochemistry_summary"), world.get("_overland_summary"), world.get("_groundwater_summary"))
	world.queue_free()
	await process_frame
	print("INTERFACE_VALIDATION ", "PASS" if failures.is_empty() else "FAIL", " sliders=", sliders, " booleans=", bools, " failures=", failures)
	quit(0 if failures.is_empty() else 1)
