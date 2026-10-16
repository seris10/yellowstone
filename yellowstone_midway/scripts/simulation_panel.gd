class_name YellowstoneSimulationPanel
extends PanelContainer

var world: Node
var client: YellowstoneLivePythonClient
var ecosystem: Node
var _rows: VBoxContainer
var _status: Label
var _work: RichTextLabel
var _probe: RichTextLabel
var _comparison: Label
var _measured: Label
var _chart: Control
var _schema: Dictionary = {}
var _hold_cell: String = ""
var _hold_seconds: float = 0.0
var _compare_elapsed: float = 0.0
var _marked: bool = false
var _probe_enabled: bool = false
var _sample_values: Array[Vector2] = []
var _observed_values: Array[Vector2] = []
var _models: Dictionary = {}
var _root_path: String = ""
var _observation_epoch: float = NAN
var _chart_epoch_origin: float = NAN
var _last_error: String = ""
var _jump_button: Button
var _mark_button: Button

func bind(owner: Node, live_client: YellowstoneLivePythonClient, state: Node) -> void:
	world = owner
	client = live_client
	ecosystem = state
	_root_path = ProjectSettings.globalize_path("res://../yellowstone_python")
	client.schema_received.connect(_build_schema)
	client.mode_selected.connect(func(live: bool):
		if _jump_button != null:
			_jump_button.disabled = not live
		if _mark_button != null:
			_mark_button.disabled = not live)
	client.response_received.connect(_response)
	client.failed.connect(func(message: String):
		_last_error = message
		_status.text = message)
	position = Vector2(640, 140)
	custom_minimum_size = Vector2(610, 660)
	add_theme_stylebox_override("panel", world.panel_style(0.94))
	var scroll: ScrollContainer = ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(550, 610)
	add_child(scroll)
	_rows = VBoxContainer.new()
	_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_rows.add_theme_constant_override("separation", 10)
	scroll.add_child(_rows)
	_status = world.text_label("Baked Python build. Live controls require the local Python service.", 14)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_rows.add_child(_status)
	_build_time_controls()
	_comparison = world.text_label("A/B: mark the current state, then change conditions.", 14)
	_rows.add_child(_comparison)
	_mark_button = world.make_button("Mark A", func(): world.mark_comparison())
	_mark_button.disabled = not client.live
	_rows.add_child(_mark_button)
	_probe = RichTextLabel.new()
	_probe.bbcode_enabled = true
	_probe.fit_content = true
	_probe.custom_minimum_size = Vector2(500, 60)
	_rows.add_child(_probe)
	_chart = Control.new()
	_chart.custom_minimum_size = Vector2(500, 110)
	_chart.draw.connect(_draw_chart)
	_rows.add_child(_chart)
	_measured = world.text_label("Measured downstream gauge: 06036905. Discharge and upstream temperature are prescribed forcing.", 13)
	_measured.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_rows.add_child(_measured)
	_work = RichTextLabel.new()
	_work.bbcode_enabled = true
	_work.fit_content = true
	_work.custom_minimum_size = Vector2(500, 80)
	_work.meta_clicked.connect(_open_source)
	_rows.add_child(_work)
	visible = false
	if not client.schema.is_empty():
		_build_schema(client.schema)

func _build_time_controls() -> void:
	var buttons: HBoxContainer = HBoxContainer.new()
	_rows.add_child(buttons)
	for rate: int in [1, 60, 600, 3600]:
		var button: Button = Button.new()
		button.text = "%dx" % rate
		button.pressed.connect(func(): world.set_time_scale(float(rate)))
		buttons.add_child(button)
	var pause_button: Button = Button.new()
	pause_button.text = "Pause / resume"
	pause_button.pressed.connect(func(): world.toggle_pause())
	buttons.add_child(pause_button)
	var step_button: Button = Button.new()
	step_button.text = "Step"
	step_button.pressed.connect(func(): world.step_simulation())
	buttons.add_child(step_button)
	var jump_row: HBoxContainer = HBoxContainer.new()
	_rows.add_child(jump_row)
	var date: LineEdit = LineEdit.new()
	date.placeholder_text = "YYYY-MM-DD"
	date.custom_minimum_size.x = 160
	jump_row.add_child(date)
	var hour: SpinBox = SpinBox.new()
	hour.min_value = 0
	hour.max_value = 23.99
	hour.step = 0.25
	hour.value = ecosystem.clock_hour
	jump_row.add_child(hour)
	var jump: Button = Button.new()
	_jump_button = jump
	jump.disabled = not client.live
	jump.text = "Jump to date / hour"
	jump.pressed.connect(func():
		var changes: Dictionary = {"clock_hour": hour.value}
		if not date.text.is_empty():
			changes["snow.as_of_date"] = date.text
		client.control(changes))
	jump_row.add_child(jump)

func _build_schema(schema: Dictionary) -> void:
	_schema = schema
	for child: Node in _rows.get_children():
		if child.has_meta("schema_row"):
			child.queue_free()
	for entry: Dictionary in schema.get("controls", []):
		var key: String = str(entry.key)
		var group: String = str(entry.get("group", "Conditions"))
		var row: VBoxContainer = VBoxContainer.new()
		row.set_meta("schema_row", true)
		_rows.add_child(row)
		var label: Label = world.text_label("%s: %s [%s], default %s (%s)" % [group, entry.get("label", key), entry.get("unit", ""), str(entry.get("default", "")), entry.get("provenance", "unknown")], 13)
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.tooltip_text = str(entry.get("bound_source", ""))
		row.add_child(label)
		if entry.get("min") != null and entry.get("max") != null:
			var slider: HSlider = HSlider.new()
			slider.min_value = float(entry.min)
			slider.max_value = float(entry.max)
			slider.step = 1.0 if str(entry.get("type", "")) == "integer" else (slider.max_value - slider.min_value) / 200.0
			slider.value = float(entry.default) if entry.get("default") is float or entry.get("default") is int else slider.min_value
			slider.value_changed.connect(func(value: float): label.text = "%s: %.3f %s (%s)" % [entry.get("label", key), value, entry.get("unit", ""), entry.get("provenance", "unknown")])
			slider.drag_ended.connect(func(changed: bool):
				if changed:
					client.control({key: int(slider.value) if str(entry.get("type", "")) == "integer" else slider.value}))
			slider.gui_input.connect(func(event: InputEvent):
				if event.is_action_released("ui_accept"):
					client.control({key: int(slider.value) if str(entry.get("type", "")) == "integer" else slider.value}))
			row.add_child(slider)
		elif str(entry.get("type", "")) in ["boolean", "bool"]:
			var checkbox: CheckButton = CheckButton.new()
			checkbox.text = str(entry.get("label", key))
			checkbox.button_pressed = bool(entry.get("default", false))
			checkbox.toggled.connect(func(enabled: bool): client.control({key: enabled}))
			row.add_child(checkbox)
		elif entry.get("default") is Array and entry.default.size() == 2:
			for component: int in range(2):
				var wind_component: SpinBox = SpinBox.new()
				wind_component.min_value = float(entry.get("component_min", 0.0))
				wind_component.max_value = float(entry.get("component_max", 0.0))
				wind_component.value = float(entry.default[component])
				wind_component.value_changed.connect(func(value: float):
					var vector: Array = entry.default.duplicate()
					vector[component] = value
					entry["default"] = vector
					client.control({key: vector}))
				row.add_child(wind_component)
	for preset: Dictionary in schema.get("presets", []):
		var button: Button = world.make_button(str(preset.get("description", preset.name)), func(): client.command("preset", {"name": preset.name}))
		button.tooltip_text = str(preset.get("expected_response", ""))
		button.set_meta("schema_row", true)
		_rows.add_child(button)
	var dates: Array = schema.get("measured_dates", schema.get("observation_dates", []))
	if not dates.is_empty():
		var picker: OptionButton = OptionButton.new()
		picker.set_meta("schema_row", true)
		for date: Variant in dates:
			picker.add_item(str(date))
		picker.item_selected.connect(func(index: int): client.command("measured", {"date": picker.get_item_text(index)}))
		_rows.add_child(picker)

func _response(kind: String, payload: Dictionary) -> void:
	if kind not in ["frames", "schema"]:
		_last_error = ""
	if kind == "clock" and payload.get("time_scale") != null:
		world.adopt_python_clock(payload, float(payload.player_t_s) if payload.get("player_t_s") != null else NAN)
	if kind == "mark":
		world.reset_comparison()
		_marked = true
		_comparison.text = "A marked. Change conditions to compare."
	elif kind == "compare":
		var metrics: Dictionary = payload.get("metrics", payload.get("comparison", {}))
		_comparison.text = "A/B: " + JSON.stringify(metrics)
		world.apply_comparison(payload)
	elif kind == "measured":
		_marked = false
		world.reset_comparison()
		_reset_chart()
		_measured.text = "Observed replay: downstream gauge 06036905; upstream temperature and discharge are prescribed forcing."

func _process(delta: float) -> void:
	if world == null:
		return
	if visible:
		_status.text = world.simulation_status_text() + (" | computing" if client.computing else "") + (" | " + _last_error if not _last_error.is_empty() else "")
		update_computation()
	if _marked:
		_compare_elapsed += delta
		if _compare_elapsed >= 1.0:
			_compare_elapsed = 0.0
			client.command("compare", {"t_s": ecosystem.elapsed})
	if _probe_enabled:
		_update_probe(delta)

func toggle_probe() -> void:
	_probe_enabled = not _probe_enabled
	_reset_chart()
	visible = _probe_enabled or visible
	if not _probe_enabled:
		_probe.text = ""

func _reset_chart() -> void:
	_sample_values.clear()
	_observed_values.clear()
	_observation_epoch = NAN
	_chart_epoch_origin = NAN
	_chart.queue_redraw()

func _update_probe(delta: float) -> void:
	var camera: Camera3D = world.player.camera
	var start: Vector3 = camera.global_position
	var finish: Vector3 = start - camera.global_basis.z * 350.0
	var query: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(start, finish)
	query.exclude = [world.player]
	var hit: Dictionary = world.get_world_3d().direct_space_state.intersect_ray(query)
	var at: Vector3 = hit.get("position", finish)
	var state: Dictionary = ecosystem.river_state_at_position(at, str(ecosystem.get("_features").keys()[0]) if not ecosystem.get("_features").is_empty() else "", "player_probe")
	if str(state.get("id", "unavailable")) == "unavailable":
		state = _ground_probe(at)
	var id: String = str(state.get("cell_id", state.get("id", "ground")))
	_hold_seconds = _hold_seconds + delta if id == _hold_cell else 0.0
	_hold_cell = id
	_probe.text = probe_text(state)
	_sample_values.clear()
	if _hold_seconds >= 0.5:
		for frame: Dictionary in ecosystem.get("_frames"):
			if not frame.get("cells") is Array:
				for i: int in range(ecosystem.get("_cells").size()):
					if str(ecosystem.get("_cells")[i].id) == id:
						_sample_values.append(Vector2(float(frame.t_s), float(frame.temperature_c[i])))
			for row: Dictionary in frame.get("cells", []):
				if str(row.get("cell_id", row.get("id", ""))) == id:
					_sample_values.append(Vector2(float(frame.t_s), float(row.temperature_c)))
	_chart.queue_redraw()

func _ground_probe(at: Vector3) -> Dictionary:
	var patches: Array = ecosystem.patches
	var best: Dictionary = {}
	var distance: float = INF
	for patch: Dictionary in patches:
		var center: Variant = patch.get("center_xz", patch.get("center", [0.0, 0.0]))
		if center is Array and center.size() >= 2:
			var d: float = Vector2(at.x - float(center[0]), at.z - float(center[-1])).length_squared()
			if d < distance:
				distance = d
				best = patch.duplicate(true)
	var ecology: Dictionary = ecosystem.current_frame.get("ecology", {})
	if ecology.get("snow") is Dictionary:
		best["snow_mm"] = ecology.snow.get("swe_mm", best.get("snow_mm", 0.0))
	if ecology.get("soil") is Dictionary:
		best["soil_temperature_c"] = ecology.soil.get("temperature_c", best.get("soil_temperature_c", 0.0))
	return best

func probe_text(state: Dictionary) -> String:
	var lines: PackedStringArray = PackedStringArray(["[b]Probe: %s[/b]" % state.get("cell_id", state.get("id", "ground"))])
	for entry: Array in [["temperature_c", "C", "river_transport"], ["depth_m", "m", "river_hydraulics"], ["velocity_mps", "m/s", "river_hydraulics"], ["oxygen_mg_l", "mg/L", "river_oxygen"], ["shading_factor", "fraction", "river_shading"], ["trout_suitability_u", "relative", "fish_refuge"], ["refuge_drive", "fraction", "fish_thermal_performance"], ["snow_mm", "mm SWE", "snow_degree_day"], ["soil_temperature_c", "C", "soil_temperature"], ["biomass", "relative", "vegetation"]]:
		if state.get(entry[0]) != null:
			var model: Dictionary = _model_for(str(entry[0]), str(entry[2]))
			lines.append("%s: %.3f %s | %s | %s" % [entry[0], float(state[entry[0]]), entry[1], model.get("provenance", "illustrative"), model.get("component_id", model.get("equation_component", entry[2]))])
	return "\n".join(lines)

func _model_for(quantity: String, fallback: String) -> Dictionary:
	var components: Variant = ecosystem.frame_header.get("model_components", {})
	var aliases: Dictionary = {"river": "temperature_c", "oxygen": "oxygen_mg_l", "hydraulics": "depth_m", "vegetation": "biomass", "insects": "foodweb", "solar": "weather", "soil": "soil_temperature_c", "runoff": "runoff_mm"}
	quantity = str(aliases.get(quantity, quantity))
	if components is Dictionary:
		return components.get(quantity, {"component_id": fallback})
	if components is Array:
		for entry: Dictionary in components:
			if quantity in entry.get("quantities", []) or str(entry.get("quantity", "")) == quantity:
				return entry
	return {"component_id": fallback}

func model_notes() -> String:
	var components: Variant = ecosystem.frame_header.get("model_components", {})
	var lines: PackedStringArray = PackedStringArray(["\n[b]Model sources[/b]"])
	var entries: Array = components if components is Array else []
	if components is Dictionary:
		for quantity: String in components:
			var entry: Dictionary = components[quantity].duplicate(true)
			entry["quantity"] = entry.get("quantity", quantity)
			entries.append(entry)
	for entry: Variant in entries:
		if entry is Dictionary:
			lines.append("%s | %s | %s | %s" % [entry.get("quantity", entry.get("label", "quantity")), entry.get("module", ""), entry.get("component_id", entry.get("equation_component", entry.get("id", ""))), entry.get("provenance", "illustrative")])
	if entries.is_empty():
		var inventory: Dictionary = world.get("_sidecar_data").get("equations.json", {})
		for row: Dictionary in inventory.get("components", []):
			lines.append("%s | %s | %s" % [row.get("module", ""), row.get("component", ""), row.get("validation_status", "")])
	lines.append("Trout sustained speed: %.2f body lengths/s (authored). Tailbeat: Bainbridge (1958), transferred to trout; below 5 Hz extrapolated." % float(ecosystem.params.get("fish_sustained_swim_bl_s", 1.5)))
	return "\n".join(lines)

func update_computation() -> void:
	var header: Dictionary = ecosystem.frame_header
	var timings: Variant = header.get("timings", {})
	var lines: PackedStringArray = PackedStringArray(["[b]What Python just did[/b]"])
	var stages: Array = header.get("dirty_stages", [])
	for stage: Variant in stages:
		var name: String = str(stage)
		var timing: Variant = timings.get(name, "not separately timed") if timings is Dictionary else "not separately timed"
		var model: Dictionary = _model_for(name, name)
		var source: String = str(model.get("source_file", str(model.get("module", name)).trim_prefix("yellowstone_python.").replace(".", "/") + ".py"))
		lines.append("[url=%s]%s[/url]: %s ms | %s" % [source, name, str(timing), model.get("component_id", model.get("equation_component", name))])
	for stage: String in timings if timings is Dictionary else {}:
		if stage not in stages:
			lines.append("%s: %s ms" % [stage, str(timings[stage])])
	lines.append("Solver dt %.3f s, max dt %.3f s | %s" % [float(header.get("dt_s", 0.0)), float(header.get("max_dt_s", 0.0)), JSON.stringify(ecosystem.current_frame.get("health", {}))])
	_work.text = "\n".join(lines)
	var observation: Dictionary = ecosystem.current_frame.get("observations", ecosystem.current_frame.get("observation", ecosystem.current_frame.get("measured", {})))
	if not observation.is_empty():
		_measured.text = "Gauge 06036905: model %.2f C, observed %s C, RMSE so far %s C. Discharge: prescribed forcing." % [float(observation.get("modeled_c", 0.0)), str(observation.get("observed_c", "unavailable")), str(observation.get("rmse_c", "unavailable"))]
		var epoch: float = float(observation.get("epoch_unix", ecosystem.elapsed))
		if not _probe_enabled and epoch != _observation_epoch:
			_observation_epoch = epoch
			if is_nan(_chart_epoch_origin):
				_chart_epoch_origin = epoch
			var relative_s: float = epoch - _chart_epoch_origin
			_sample_values.append(Vector2(relative_s, float(observation.get("modeled_c", 0.0))))
			if observation.get("observed_c") != null:
				_observed_values.append(Vector2(relative_s, float(observation.observed_c)))
			while _sample_values.size() > 512:
				_sample_values.pop_front()
			while _observed_values.size() > 512:
				_observed_values.pop_front()
			_chart.queue_redraw()

func _open_source(meta: Variant) -> void:
	var source: String = str(meta)
	if source.contains("..") or source.contains(":"):
		return
	var path: String = _root_path.path_join("yellowstone_python").path_join(source.trim_prefix("yellowstone_python/"))
	if FileAccess.file_exists(path):
		OS.shell_open(path)

func _draw_chart() -> void:
	if _sample_values.size() < 2:
		return
	var lo: float = INF
	var hi: float = -INF
	for point: Vector2 in _sample_values + _observed_values:
		lo = minf(lo, point.y)
		hi = maxf(hi, point.y)
	var start: float = _sample_values[0].x
	var span: float = maxf(_sample_values[-1].x - start, 1.0)
	for pair: Array in [[_sample_values, Color(0.4, 0.7, 1.0)], [_observed_values, Color(1.0, 0.7, 0.3)]]:
		var points: PackedVector2Array = PackedVector2Array()
		for point: Vector2 in pair[0]:
			points.append(Vector2((point.x - start) / span * _chart.size.x, _chart.size.y - (point.y - lo) / maxf(hi - lo, 0.1) * _chart.size.y))
		if points.size() >= 2:
			_chart.draw_polyline(points, pair[1], 2.0)
