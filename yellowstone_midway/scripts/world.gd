extends Node3D
const ReleaseData = preload("res://scripts/release_data.gd")
## Runtime assembles saved authored assets.
const Walker = preload("res://scripts/player.gd")
const HeightField = preload("res://scripts/height_field.gd")
const Ecosystem = preload("res://scripts/ecosystem.gd")
const PythonReplay = preload("res://scripts/python_river_replay.gd")
const LiveClient = preload("res://scripts/live_python_client.gd")
const DataWatcher = preload("res://scripts/data_watcher.gd")
const InputHelp = preload("res://scripts/input_help.gd")
const SimulationPanel = preload("res://scripts/simulation_panel.gd")
const AtmosphereController = preload("res://scripts/yellowstone_atmosphere.gd")
const ShadowQuality = preload("res://scripts/shadow_quality.gd")
const TerrainMaterials = preload("res://scripts/terrain_materials.gd")
const LodgepoleLibrary = preload("res://scripts/lodgepole_library.gd")
const TreeSubmission = preload("res://scripts/tree_submission.gd")
const PerfProbe = preload("res://scripts/perf_probe.gd")
const CanopySurface = preload("res://scripts/canopy_surface.gd")
const WeatherSnapshotReader = preload("res://scripts/weather_snapshot_reader.gd")
## Optional published Python replay path.
@export_file("*.json") var replay_path: String = ""
## Optional baked comparison replay.
@export_file("*.json") var replay_path_alt: String = ""
var replay_run_name := ""
var player: CharacterBody3D
var ecosystem: Node
var height_field: RefCounted
var spec: Dictionary
var sun: DirectionalLight3D
var environment: Environment
var sky_material: PhysicalSkyMaterial
var atmosphere_controller: Node3D
var weather_snapshot_reader: Node
var live_client: YellowstoneLivePythonClient
var data_watcher: YellowstoneDataWatcher
var simulation_panel: YellowstoneSimulationPanel
var input_help: YellowstoneInputHelp
var _comparison_ecosystem: Node
var _ghost_trout: Array[Node3D] = []
var _comparison_origins: Dictionary = {}
var _sidecar_data: Dictionary = {}
var _wildlife_nodes: Array[Node3D] = []
var _pool_surface_defaults: Dictionary = {}
var _outflow_enabled: bool = true
var _live_revision: int = -1
const STATE_INTERPOLATION_FIELDS: Array[String] = ["temperature_c", "flow_m3s", "depth_m", "oxygen_mg_l", "snow_cover_fraction", "refuge_s_m"]
const SIDECAR_PATHS: Array[String] = ["outflow_foodweb.json", "periphyton.json", "piscivores.json", "river_oxygen.json", "river_shading.json", "solute_transport.json", "ground_heat.json", "evapotranspiration.json", "snow_cover.json", "soil_temperature.json", "steam_microclimate.json", "substrate_rules.json", "winter_grazing.json", "mammals.json", "mammal_catalogue.json", "outflow_to_replay_lateral.json", "species_catalogue.json", "param_registry.json", "equations.json", "claims.json", "pool_ramps.json"]
var _simulation_start_epoch_unix: float = 0.0
var _simulation_epoch_unix: float = 0.0
var _has_simulation_epoch: bool = false
var overlay: CanvasLayer
var menu: PanelContainer
var info_panel: PanelContainer
var info_label: RichTextLabel
var location_label: Label
var status_label: Label
var help_label: Label
var content: VBoxContainer
var menus_open := true
# HUD cycle: 0 full, 1 minimal (location label only), 2 hidden.
var hud_mode := 0
var map_view: Control
var observation_timer := 0.0
var camera_anchor := 0
var loading: Label
var foliage_materials: Array[ShaderMaterial] = []
var terrain_materials: Array[ShaderMaterial] = []
# Cache bake-assigned environment groups.
var _steam_nodes: Array[Node] = []
var _river_nodes: Array[Node] = []
# Steam multiplier for ecosystem condensation visibility.
const STEAM_DENSITY_SCALE: float = 0.40
# Clamp river speed relative to its baked value.
const RIVER_FLOW_RATIO_MIN: float = 0.5
const RIVER_FLOW_RATIO_MAX: float = 2.0
# Illustrative Firehole flow baseline in m3/s (ecosystem.boundary_m3s).
const RIVER_FLOW_BASELINE_M3S: float = 8.0
# Baked flow_speed uniform used as the authored default per river material.
var _river_flow_speed_defaults: Dictionary = {}
# Per-pool thermal state from data/pool_shells.json.
var _pool_shell_temperatures: Dictionary = {}
# Last known seasonal snow fields written to terrain materials.
var _snow_amount_from_mean: float = 0.0
var _snow_swe_mm_mean: float = 0.0
# Mean published snow cover; 1.0 uses only the painted mask.
var _snow_cover_fraction_mean: float = 1.0
# Insect and bird diagnostics from insect_bird.json.
var _insect_bird_summary: Dictionary = {}
# Missing optional sidecars produce empty summaries.
var _plume_field_summary: Dictionary = {}
var _geochemistry_summary: Dictionary = {}
var _calibration_summary: Dictionary = {}
var _census_summary: Dictionary = {}
var _pools_state_summary: Dictionary = {}
# Poll pool state by mtime.
var _pools_state_mtime: int = 0
var _groundwater_summary: Dictionary = {}
var _overland_summary: Dictionary = {}
# Guild sidecars annotate field notes; ecosystem.json supplies actors.
var _grazer_summary: Dictionary = {}
var _fish_summary: Dictionary = {}
var _overlays: Node3D
var _calibration_panel: Control
var perf_probe: YellowstonePerfProbe
var toast_label: Label
var toast_seconds := 0.0
var _requested_pause := false
var _cursor_released := false
var _water_stage_key := 0
var _water_stage_texture: Texture2D
# Core terrain and thermal mat state.
var _core_terrain: Node3D
var _mat_surface: RefCounted
var _mat_pigment_mtime: int = 0
var _mat_pigment_blend: float = 1.0
var _mat_pigment_blending: bool = false
# Authored pigment cross-fade duration.
const PIGMENT_BLEND_DURATION_S: float = 3.0
# Authored pigment-file poll interval.
const PIGMENT_MTIME_POLL_INTERVAL_S: float = 1.0
# Retain unspent time between mtime polls.
var _mat_pigment_poll_accum_s: float = 0.0

func _ready() -> void:
	if FileAccess.file_exists("res://data/release.json"):
		var generation: Dictionary = _validated_generation()
		if generation.is_empty():
			push_error("Active release failed integrity or runtime contract checks.")
			return
		ReleaseData.activate(generation)
	# Honor the configured frame cap.
	var configured_cap: int = int(ProjectSettings.get_setting("rendering/limits/fps/max_fps", 60))
	Engine.max_fps = configured_cap if configured_cap >= 0 else 60
	height_field = HeightField.new()
	if not ReleaseData.file_exists("res://data/world.json"):
		push_error("Missing data/world.json: re-extract the complete project.")
		return
	spec = JSON.parse_string(ReleaseData.get_file_as_string("res://data/world.json"))
	if not spec is Dictionary or not spec.has("anchors") or not spec.has("routes") or not spec.has("pools"):
		push_error("data/world.json is missing or has no anchors/routes/pools; re-extract the complete project.")
		return
	make_environment()
	# Load the binary bake when present; the text scene is the fallback.
	var authored_path := "res://scenes/authored_world.scn"
	if not ResourceLoader.exists(authored_path):
		authored_path = "res://scenes/authored_world.tscn"
	if ResourceLoader.exists(authored_path):
		var authored: Node = load(authored_path).instantiate()
		add_child(authored)
		CanopySurface.refresh_geometry(authored.get_node_or_null("AuthoredCanopySurface"))
		if not authored.has_node("AuthoredVegetation"):
			push_error(authored_path + " has no AuthoredVegetation: re-run the offline bake.")
			return
		for group_name: String in ["AuthoredVegetation", "AuthoredForestFloor"]:
			var foliage_group := authored.get_node_or_null(NodePath(group_name))
			if foliage_group != null:
				collect_foliage_materials(foliage_group)
		add_child(load("res://scenes/handcrafted_details.tscn").instantiate())
		if ResourceLoader.exists("res://scenes/botanical_details.tscn"):
			var botany: Node=load("res://scenes/botanical_details.tscn").instantiate()
			add_child(botany)
			collect_foliage_materials(botany)
	else:
		push_error("Missing scenes/authored_world (.scn or .tscn): run the offline bake once, or re-extract the complete project.")
		return
	ecosystem = make_ecosystem()
	ecosystem.name = "Ecosystem"
	add_child(ecosystem)
	if not ReleaseData.active.is_empty():
		ecosystem.frame_header["release_id"] = ReleaseData.active.manifest.release_id
	player = Walker.new()
	player.name = "Walker"
	add_child(player)
	go_to_anchor(0)
	var tree_submission := TreeSubmission.new()
	tree_submission.name = "TreeSubmission"
	add_child(tree_submission)
	tree_submission.configure(find_child("AuthoredVegetation", true, false))
	perf_probe = PerfProbe.new()
	add_child(perf_probe)
	atmosphere_controller = AtmosphereController.new()
	atmosphere_controller.name = "YellowstoneAtmosphere"
	add_child(atmosphere_controller)
	atmosphere_controller.configure(sun, environment, player)
	_sync_atmosphere_clock()
	# Anchor model time to simulation_epoch_unix plus ecosystem.elapsed.
	if spec.get("simulation_epoch_unix") != null:
		_simulation_start_epoch_unix = float(spec["simulation_epoch_unix"])
		_simulation_epoch_unix = _simulation_start_epoch_unix + float(ecosystem.elapsed)
		_has_simulation_epoch = true
		atmosphere_controller.set_simulation_timestamp(
			_simulation_epoch_unix,
			float(spec.get("utc_offset_hours", -6.0))
		)
	else:
		atmosphere_controller.set_simulation_time(
			ecosystem.clock_hour,
			int(spec.get("day_of_year", 196)),
			float(spec.get("utc_offset_hours", -6.0))
		)
	weather_snapshot_reader = WeatherSnapshotReader.new()
	weather_snapshot_reader.name = "WeatherSnapshotReader"
	weather_snapshot_reader.snapshot_path = ReleaseData.resolve_path("res://data/weather_snapshot.json")
	add_child(weather_snapshot_reader)
	weather_snapshot_reader.freshness_mode = "disabled"
	weather_snapshot_reader.live_snapshot_path = "" if not ReleaseData.active.is_empty() else weather_snapshot_reader.live_snapshot_path
	weather_snapshot_reader.bind(atmosphere_controller)
	if _has_simulation_epoch:
		weather_snapshot_reader.set("freshness_mode", "simulation_clock")
		weather_snapshot_reader.set_simulation_epoch_unix(_simulation_epoch_unix)
	make_audio()
	make_wildlife()
	collect_terrain_materials(self)
	for material: ShaderMaterial in terrain_materials:
		if not TerrainMaterials.bind_ground_material(material):
			push_error("Terrain ground material binding failed.")
	# Terrain materials own the atmosphere ground_wetness uniform.
	for terrain_tile: Node in get_tree().get_nodes_in_group("terrain_tile"):
		if terrain_tile is MeshInstance3D:
			terrain_tile.add_to_group("weather_wetness")
	refresh_env_caches()
	cache_river_flow_defaults()
	apply_season()
	load_pool_shell_temperatures()
	apply_pool_temperatures()
	load_insect_bird_summary()
	_plume_field_summary = load_optional_sidecar("res://data/plume_field.json")
	_geochemistry_summary = load_optional_sidecar("res://data/geochemistry.json")
	_calibration_summary = load_optional_sidecar("res://data/calibration_summary.json")
	_census_summary = load_optional_sidecar("res://data/census.json")
	_grazer_summary = load_optional_sidecar("res://data/grazer.json")
	_fish_summary = load_optional_sidecar("res://data/fish.json")
	refresh_pools_state()
	_groundwater_summary = load_optional_sidecar("res://data/groundwater_field.json")
	_overland_summary = load_optional_sidecar("res://data/overland_field.json")
	apply_snow_patch_mask()
	if ResourceLoader.exists("res://scripts/pool_overlay.gd"):
		add_child(load("res://scripts/pool_overlay.gd").new())
	build_core_terrain()
	build_scientific_overlays()
	atmosphere_controller.refresh_wetness_material_cache()
	make_interface()
	setup_python_runtime()
	_sync_player_input()
	update_environment()
	if "--smoke-test" in OS.get_cmdline_user_args():
		run_smoke_test()
	if "--capture" in OS.get_cmdline_user_args() or "--capture-all" in OS.get_cmdline_user_args():
		capture_preview()

func make_ecosystem() -> Node:
	var replay: Node = PythonReplay.new()
	var path: String = replay_path if not replay_path.is_empty() else "res://data/river_replay.json"
	if ReleaseData.file_exists(path):
		replay.replay_path = path
	return replay

func setup_python_runtime() -> void:
	data_watcher = DataWatcher.new()
	add_child(data_watcher)
	data_watcher.watch("res://data/release.json", _published_changed)
	for file: String in ["ecosystem.json", "world.json", "season.json", "pools_state.json", "pool_shells.json", "insect_bird.json", "plume_field.json", "geochemistry.json", "calibration_summary.json", "census.json", "grazer.json", "fish.json", "groundwater_field.json", "overland_field.json", "weather_snapshot.json", "river_replay.json"] + SIDECAR_PATHS:
		var path: String = "res://data/" + file
		if ReleaseData.active.is_empty():
			data_watcher.watch(path, _published_changed)
	for file: String in SIDECAR_PATHS:
		_sidecar_data[file] = load_optional_sidecar("res://data/" + file)
	apply_probe_sidecars()
	var manifest: Dictionary = load_optional_sidecar("res://data/consumers.json")
	for published: String in manifest.get("consumers", {}):
		if ReleaseData.active.is_empty() and not DirAccess.dir_exists_absolute("res://" + published):
			data_watcher.watch("res://" + published, _published_changed)
	if ReleaseData.active.is_empty():
		data_watcher.watch("res://data/mat_pigment.png", func(_path: String):
			_mat_pigment_mtime = -1
			_poll_mat_pigment_change(0.0))
	live_client = LiveClient.new()
	if not ReleaseData.active.is_empty():
		live_client.expected_build_id = str(ReleaseData.active.manifest.build_id)
		live_client.expected_model_variant_id = str(ReleaseData.active.manifest.model_variant_id)
	live_client.mode_selected.connect(_python_mode_selected)
	live_client.frames_received.connect(_python_frames)
	live_client.control_received.connect(_python_control)
	add_child(live_client)
	simulation_panel = SimulationPanel.new()
	overlay.add_child(simulation_panel)
	simulation_panel.bind(self, live_client, ecosystem)
	input_help = InputHelp.new()
	overlay.add_child(input_help)
	input_help.add_theme_stylebox_override("panel", panel_style(0.94))
	if not has_node("ThermalProbes"):
		var probes: Node3D = load("res://scripts/thermal_probe_overlay.gd").new()
		probes.name = "ThermalProbes"
		probes.ecosystem_path = NodePath("../Ecosystem")
		add_child(probes)
	help_label.text = build_help_text()

func _published_changed(path: String) -> void:
	if path.get_file() == "release.json":
		_reload_generation()
		return
	if not ReleaseData.active.is_empty():
		return
	match path.get_file():
		"wet_mask.i16", "flow_fraction.f32", "in_pool.i16", "outflow_network.json":
			if _mat_surface != null and _core_terrain != null:
				_mat_surface.load_outflow()
				_mat_surface.apply(_core_terrain.get_mat_material())
				_core_terrain.refresh_outflow(_mat_surface)
		"snow_map.png":
			var image: Image = Image.load_from_file(ProjectSettings.globalize_path(path))
			if image != null:
				var mask: ImageTexture = ImageTexture.create_from_image(image)
				for material: ShaderMaterial in terrain_materials:
					material.set_shader_parameter("snow_mask", mask)
		"outflow_temperature.f32", "outflow_temperature.json", "mat_state.json", "mat_community.i16":
			if _mat_surface != null and _core_terrain != null:
				_mat_surface.load_outflow_temperature()
				_mat_surface.load_pigment()
				_mat_surface.apply(_core_terrain.get_mat_material())
		"ecosystem.json":
			ecosystem.configure(load_optional_sidecar(path))
			apply_probe_sidecars()

		"world.json":
			spec = load_optional_sidecar(path)
			ecosystem.world_data = spec
		"season.json":
			apply_season()
		"pools_state.json":
			_pools_state_mtime = 0
			refresh_pools_state()
		"pool_shells.json":
			load_pool_shell_temperatures()
			apply_pool_temperatures()
		"weather_snapshot.json":
			if not ecosystem.live_mode:
				weather_snapshot_reader.poll_now()
		"river_replay.json":
			if not ecosystem.live_mode:
				ecosystem.configure(ecosystem.params)
				apply_probe_sidecars()
		_:
			if path.get_extension() != "json":
				return
			var file: String = path.get_file()
			var doc: Dictionary = load_optional_sidecar(path)
			_sidecar_data[file] = doc
			var summaries: Dictionary = {"insect_bird.json": "_insect_bird_summary", "plume_field.json": "_plume_field_summary", "geochemistry.json": "_geochemistry_summary", "calibration_summary.json": "_calibration_summary", "census.json": "_census_summary", "grazer.json": "_grazer_summary", "fish.json": "_fish_summary", "groundwater_field.json": "_groundwater_summary", "overland_field.json": "_overland_summary"}
			if summaries.has(file):
				set(summaries[file], doc)
			if file == "calibration_summary.json" and _calibration_panel != null:
				_calibration_panel.call("set_doc", doc)
			if file == "census.json" and map_view != null:
				var census: Dictionary = doc.get("payload", doc)
				map_view.call("set_census", census.get("trees", []))
			if file in ["plume_field.json", "geochemistry.json", "groundwater_field.json", "overland_field.json"] and _overlays != null:
				_overlays.call("reload", self, _plume_field_summary, _geochemistry_summary, _overland_summary, _groundwater_summary)
			apply_probe_sidecars()

func _validated_generation(pointer_path: String = "res://data/release.json") -> Dictionary:
	var candidate: Dictionary = ReleaseData.prepare(pointer_path)
	if candidate.is_empty():
		return {}
	var world: Variant = candidate.parsed.get("data/world.json")
	if not world is Dictionary or not world.has("anchors") or not world.has("routes") or not world.has("pools"):
		return {}
	for collection: String in ["anchors", "routes", "pools"]:
		if not world[collection] is Array:
			return {}
	var epoch: Variant = world.get("simulation_epoch_unix")
	if epoch != null and (not (epoch is float or epoch is int) or not is_finite(float(epoch)) or float(epoch) < 0.0):
		return {}
	var reader: Node = PythonReplay.new()
	reader.replay_path = str(candidate.root).path_join("data/river_replay.json")
	reader.world_path = str(candidate.root).path_join("data/world.json")
	reader.world_data = world
	var valid: bool = reader.configure(candidate.parsed["data/ecosystem.json"])
	reader.free()
	return candidate if valid else {}

func _reload_generation(pointer_path: String = "res://data/release.json") -> bool:
	if ecosystem != null and ecosystem.live_mode:
		push_warning("A release is available; the active live session retains its generation.")
		return false
	var candidate: Dictionary = _validated_generation(pointer_path)
	if candidate.is_empty():
		push_warning("Release activation refused; the complete current generation is retained.")
		return false
	ReleaseData.activate(candidate)
	spec = candidate.parsed["data/world.json"]
	_has_simulation_epoch = spec.get("simulation_epoch_unix") != null
	_simulation_start_epoch_unix = float(spec.get("simulation_epoch_unix", 0.0)) if _has_simulation_epoch else 0.0
	_simulation_epoch_unix = _simulation_start_epoch_unix
	ecosystem.elapsed = 0.0
	ecosystem.world_data = spec
	ecosystem.replay_path = "res://data/river_replay.json"
	ecosystem.configure(candidate.parsed["data/ecosystem.json"])
	ecosystem.frame_header["release_id"] = candidate.manifest.release_id
	reset_comparison()
	for actor: Node3D in _wildlife_nodes:
		remove_child(actor)
		actor.queue_free()
	_wildlife_nodes.clear()
	if height_field != null:
		make_wildlife()
	_sidecar_data.clear()
	for file: String in SIDECAR_PATHS:
		_sidecar_data[file] = load_optional_sidecar("res://data/" + file)
	var summaries: Dictionary = {"insect_bird.json": "_insect_bird_summary", "plume_field.json": "_plume_field_summary", "geochemistry.json": "_geochemistry_summary", "calibration_summary.json": "_calibration_summary", "census.json": "_census_summary", "grazer.json": "_grazer_summary", "fish.json": "_fish_summary", "groundwater_field.json": "_groundwater_summary", "overland_field.json": "_overland_summary", "pools_state.json": "_pools_state_summary"}
	for file: String in summaries:
		set(summaries[file], load_optional_sidecar("res://data/" + file))
	_pool_shell_temperatures.clear()
	_pools_state_mtime = 0
	load_pool_shell_temperatures()
	refresh_pools_state()
	apply_season()
	apply_snow_patch_mask()
	apply_probe_sidecars()
	if _mat_surface != null and _core_terrain != null:
		_mat_surface.load_outflow()
		_mat_surface.load_pigment()
		_mat_surface.load_outflow_temperature()
		_mat_surface.apply(_core_terrain.get_mat_material())
		_core_terrain.refresh_outflow(_mat_surface)
		_core_terrain.cut_open_water(spec.pools)
		_mat_pigment_mtime = ReleaseData.get_modified_time("res://data/mat_pigment.png")
		_mat_pigment_blending = false
	for child: Node in get_children():
		if child is MidwayPoolOverlay:
			child.reload()
	if _overlays != null:
		_overlays.call("reload", self, _plume_field_summary, _geochemistry_summary, _overland_summary, _groundwater_summary)
	if weather_snapshot_reader != null:
		weather_snapshot_reader.snapshot_path = ReleaseData.resolve_path("res://data/weather_snapshot.json")
		weather_snapshot_reader.live_snapshot_path = ""
		weather_snapshot_reader.poll_now()
	if live_client != null:
		live_client.expected_build_id = str(candidate.manifest.build_id)
		live_client.expected_model_variant_id = str(candidate.manifest.model_variant_id)
	if help_label != null:
		help_label.text = build_help_text()
	return true

func apply_probe_sidecars() -> void:
	if ecosystem.live_mode:
		return
	var oxygen: Dictionary = _sidecar_data.get("river_oxygen.json", {}).get("do_mg_l_by_cell", {})
	var shading: Dictionary = _sidecar_data.get("river_shading.json", {}).get("multiplier_by_cell", {})
	for row: Dictionary in ecosystem.get("_spatial_state"):
		row.erase("oxygen_mg_l")
		row.erase("shading_factor")
		var id: String = str(row.get("id", row.get("cell_id", "")))
		if oxygen.has(id):
			row["oxygen_mg_l"] = oxygen[id]
		if shading.has(id):
			row["shading_factor"] = shading[id]

func _python_mode_selected(live: bool) -> void:
	if live:
		ecosystem.begin_live(live_client.schema)
		if atmosphere_controller != null:
			atmosphere_controller.reset_simulation_elapsed(float(ecosystem.elapsed))
		weather_snapshot_reader.set_process(false)
	else:
		ecosystem.live_mode = false
		ecosystem.clock_held = false

func _python_control(payload: Dictionary) -> void:
	if payload.has("truncate_after_t_s"):
		ecosystem.truncate_after(float(payload.truncate_after_t_s))
	_live_revision = int(payload.get("revision", _live_revision))

func _python_frames(payload: Dictionary) -> void:
	if bool(payload.get("reset_required", false)):
		ecosystem.reset_buffer(float(payload.get("retained_after_t_s", ecosystem.elapsed)))
	var revision: int = int(payload.get("revision", _live_revision))
	if _live_revision >= 0 and revision != _live_revision and payload.has("truncate_after_t_s"):
		ecosystem.truncate_after(float(payload.truncate_after_t_s))
	_live_revision = revision
	if not ecosystem.append_frames(payload.get("frames", [])):
		push_error("Python live frame failed validation.")
	adopt_python_clock(payload.get("header", {}), float(payload.player_t_s) if payload.get("player_t_s") != null else NAN)
	ecosystem.frame_header["revision"] = revision

func adopt_python_clock(header: Dictionary, player_t_s: float = NAN) -> void:
	if is_finite(player_t_s) and not ecosystem.get("_frames").is_empty():
		ecosystem.elapsed = clampf(player_t_s, float(ecosystem.get("_frames")[0].t_s), float(ecosystem.get("_frames")[-1].t_s))
		ecosystem.call("_apply_replay", ecosystem.elapsed)
	if not header.is_empty():
		ecosystem.set_clock_header(header)
		if info_panel != null and info_panel.visible:
			ecosystem.paused = true
		live_client.time_scale = ecosystem.time_scale
		var health: Dictionary = header.get("health", {})
		if health.get("worker_error") != null:
			_requested_pause = true
			_apply_pause_state()
			live_client.failed.emit("Python worker stopped: " + str(health.worker_error))

func simulation_status_text() -> String:
	var mode: String = "live Python" if ecosystem.live_mode else "baked build"
	var date: String = Time.get_datetime_string_from_unix_time(ecosystem.epoch_unix + float(spec.get("utc_offset_hours", -6.0)) * 3600.0) if ecosystem.epoch_unix > 0.0 else "%02d:%02d" % [int(ecosystem.clock_hour), int(fmod(ecosystem.clock_hour, 1.0) * 60.0)]
	if not ReleaseData.active.is_empty() and ReleaseData.active.manifest.get("verification", {}).get("status") != "numerical_and_contract_checks_passed":
		mode += " unverified development"
	if perf_probe != null and perf_probe.visible:
		mode += " " + str(ecosystem.params.get("build_id", ecosystem.frame_header.get("build_id", "unrecorded")))
		if not ReleaseData.active.is_empty():
			mode += " release " + str(ReleaseData.active.manifest.release_id).left(12)
		mode += " scenario " + str(ecosystem.frame_header.get("scenario_id", ecosystem.params.get("build_id", "unrecorded"))).left(12)
	return "%s | %s | %.0fx%s | %s | buffer %.0f s%s" % [mode, ecosystem.frame_header.get("run_mode", ecosystem.params.get("run_mode", "illustrative")), ecosystem.time_scale, " paused" if ecosystem.paused else "", date, ecosystem.buffer_headroom_s(), " computing" if ecosystem.computing else ""]

func set_time_scale(rate: float) -> void:
	var capacity: float = float(ecosystem.frame_header.get("max_supported_time_scale", live_client.schema.get("max_supported_time_scale", rate)))
	ecosystem.time_scale = minf(rate, capacity) if ecosystem.live_mode else rate
	live_client.time_scale = ecosystem.time_scale
	live_client.command("clock", {"time_scale": rate, "paused": ecosystem.paused})

func toggle_pause() -> void:
	if info_panel != null and info_panel.visible:
		toast("Playback stays paused while field notes are open")
		return
	_requested_pause = not ecosystem.paused
	_apply_pause_state()

func _apply_pause_state() -> void:
	ecosystem.paused = _requested_pause or (info_panel != null and info_panel.visible)
	live_client.command("clock", {"time_scale": ecosystem.time_scale, "paused": ecosystem.paused})

func step_simulation() -> void:
	_requested_pause = true
	_apply_pause_state()
	if not ecosystem.live_mode:
		ecosystem.step_frame()
	live_client.command("clock", {"step": true, "paused": true})

func reset_comparison() -> void:
	for ghost: Node3D in _ghost_trout:
		remove_child(ghost)
		ghost.queue_free()
	_ghost_trout.clear()
	var ribbon: Node = get_node_or_null("ComparisonRibbon")
	if ribbon != null:
		remove_child(ribbon)
		ribbon.queue_free()
	if _comparison_ecosystem != null:
		remove_child(_comparison_ecosystem)
		_comparison_ecosystem.queue_free()
		_comparison_ecosystem = null

func capture_comparison_origins() -> void:
	_comparison_origins.clear()
	for record: Dictionary in ecosystem.params.get("wildlife", []):
		var actor: Node3D = get_node_or_null(NodePath(str(record.id)))
		if actor != null and str(record.get("kind", "")).contains("trout"):
			_comparison_origins[str(record.id)] = {"position": actor.get("_world_position"), "chainage_m": actor.chainage_m, "target_s_m": actor.target_s_m, "t_s": ecosystem.elapsed}

func mark_comparison() -> void:
	if not ecosystem.live_mode:
		return
	capture_comparison_origins()
	live_client.player_t_s = ecosystem.elapsed
	live_client.command("mark", {})

func apply_comparison(payload: Dictionary) -> void:
	var frames: Array = payload.get("a_frames", payload.get("A", {}).get("frames", []))
	if frames.is_empty():
		return
	if _comparison_ecosystem == null:
		_comparison_ecosystem = PythonReplay.new()
		_comparison_ecosystem.name = "ComparisonEcosystem"
		add_child(_comparison_ecosystem)
		_comparison_ecosystem.world_data = ecosystem.world_data
		_comparison_ecosystem.params = ecosystem.params.duplicate(true)
		_comparison_ecosystem.begin_live({"cells": ecosystem.get("_cells"), "river_features": ecosystem.get("_features")})
		_comparison_ecosystem.set_process(false)
		_comparison_ecosystem.elapsed = ecosystem.elapsed
		for record: Dictionary in ecosystem.params.get("wildlife", []):
			if not str(record.get("kind", "")).contains("trout"):
				continue
			var ghost: Node3D = load("res://scripts/wildlife_actor.gd").new()
			var ghost_record: Dictionary = record.duplicate(true)
			ghost_record["ghost"] = true
			ghost.setup(ghost_record, height_field, _comparison_ecosystem)
			var origin: Dictionary = _comparison_origins.get(str(record.id), {})
			if not origin.is_empty():
				ghost.set("_world_position", origin.position)
				ghost.chainage_m = origin.chainage_m
				ghost.target_s_m = origin.target_s_m
				ghost.set("_last_sim_time", origin.t_s)
			add_child(ghost)
			_ghost_trout.append(ghost)
		var ribbon: Node3D = load("res://scripts/thermal_probe_overlay.gd").new()
		ribbon.name = "ComparisonRibbon"
		ribbon.ecosystem_path = NodePath("../ComparisonEcosystem")
		add_child(ribbon)
		ribbon.set("_ecosystem", _comparison_ecosystem)
		ribbon.visible = true
		ribbon.ribbon_offset_m = -0.5
	_comparison_ecosystem.append_frames(frames)
	_comparison_ecosystem.elapsed = minf(ecosystem.elapsed, float(frames[-1].t_s))
	_comparison_ecosystem.call("_apply_replay", _comparison_ecosystem.elapsed)
	for ghost: Node3D in _ghost_trout:
		ghost.call("_update_fish", 0.0)
	get_node("ThermalProbes").visible = true

func collect_foliage_materials(node: Node) -> void:
	var mesh: Mesh
	if node is MeshInstance3D:
		mesh = node.mesh
	elif node is MultiMeshInstance3D and node.multimesh != null:
		mesh = node.multimesh.mesh
	var geometry := node as GeometryInstance3D
	if mesh != null and geometry != null:
		for surface: int in mesh.get_surface_count():
			var mat: Material = geometry.material_override
			if mat == null:
				mat = node.get_active_material(surface) if node is MeshInstance3D else mesh.surface_get_material(surface)
			if mat is ShaderMaterial and mat.shader != null and mat.shader.resource_path.ends_with("foliage.gdshader") and not mat in foliage_materials:
				foliage_materials.append(mat)
			if mat is ShaderMaterial and mat.has_meta("impostor_form"):
				if not LodgepoleLibrary.bind_billboard_batch(mat):
					push_error("Distant tree texture binding failed")
	for child in node.get_children():collect_foliage_materials(child)

func collect_terrain_materials(node: Node) -> void:
	if node is MeshInstance3D:
		var mesh_instance := node as MeshInstance3D
		if mesh_instance.mesh != null:
			for surface in mesh_instance.mesh.get_surface_count():
				var mat: Material=mesh_instance.mesh.surface_get_material(surface)
				if mat is ShaderMaterial and (mat as ShaderMaterial).shader != null and (mat as ShaderMaterial).shader.resource_path.ends_with("terrain.gdshader") and not mat in terrain_materials:
					terrain_materials.append(mat)
	for child in node.get_children():collect_terrain_materials(child)

func apply_season() -> void:
	_snow_swe_mm_mean = 0.0
	_snow_amount_from_mean = 0.0
	_snow_cover_fraction_mean = 0.0
	for material: ShaderMaterial in terrain_materials:
		material.set_shader_parameter("snow_amount", 0.0)
		material.set_shader_parameter("snow_swe_mm", 0.0)
		material.set_shader_parameter("snow_cover_fraction", 0.0)
		material.set_shader_parameter("snow_mask", null)
	# Season selection updates snow surfaces.
	if not ReleaseData.file_exists("res://data/season.json"):
		return
	var parsed: Variant = JSON.parse_string(ReleaseData.get_file_as_string("res://data/season.json"))
	if not parsed is Dictionary or not parsed.has("patches"):
		return
	var patch_rows: Array = parsed["patches"]
	var depth_sum: float = 0.0
	var swe_sum: float = 0.0
	var cover_sum: float = 0.0
	var cover_count: int = 0
	for p: Dictionary in patch_rows:
		depth_sum += float(p.get("snow_depth_m", 0.0))
		swe_sum += float(p.get("snow_mm", 0.0))
		if p.has("snow_cover_fraction"):
			cover_sum += clampf(float(p["snow_cover_fraction"]), 0.0, 1.0)
			cover_count += 1
	var depth_mean: float = depth_sum / float(maxi(patch_rows.size(), 1))
	_snow_swe_mm_mean = swe_sum / float(maxi(patch_rows.size(), 1))
	_snow_amount_from_mean = clampf(depth_mean / 0.3, 0.0, 1.0)
	_snow_cover_fraction_mean = cover_sum / float(cover_count) if cover_count > 0 else 1.0
	var mask_path := "res://assets/textures/snow_map.png"
	var mask: Texture2D = ReleaseData.texture(mask_path)
	for mat: ShaderMaterial in terrain_materials:
		mat.set_shader_parameter("snow_amount", _snow_amount_from_mean)
		mat.set_shader_parameter("snow_swe_mm", _snow_swe_mm_mean)
		mat.set_shader_parameter("snow_cover_fraction", _snow_cover_fraction_mean)
		if mask != null:
			mat.set_shader_parameter("snow_mask", mask)
	print("season: snow_amount=%.2f snow_swe_mm=%.1f snow_cover_fraction=%.2f (cover_patches=%d) from %s." % [_snow_amount_from_mean, _snow_swe_mm_mean, _snow_cover_fraction_mean, cover_count, str(parsed.get("season", "unrecorded"))])

func cache_river_flow_defaults() -> void:
	# Cache baked river speeds for runtime scaling.
	for node in _river_nodes:
		var mi := node as MeshInstance3D
		if mi == null or mi.mesh == null:
			continue
		var mat := mi.mesh.surface_get_material(0) as ShaderMaterial
		if mat == null:
			continue
		var baked: Variant = mat.get_shader_parameter("flow_speed")
		var baseline: float = float(baked) if baked != null else 0.55
		_river_flow_speed_defaults[mi.get_instance_id()] = baseline

func load_pool_shell_temperatures() -> void:
	_pool_shell_temperatures.clear()
	if not ReleaseData.file_exists("res://data/pool_shells.json"):
		return
	var parsed: Variant = JSON.parse_string(ReleaseData.get_file_as_string("res://data/pool_shells.json"))
	if not parsed is Dictionary or not parsed.has("pool_shells"):
		return
	for shell: Dictionary in parsed["pool_shells"]:
		var name: String = str(shell.get("name", shell.get("id", "")))
		if name.is_empty():
			continue
		_pool_shell_temperatures[name] = float(shell.get("t_center_c", 0.0))

func apply_pool_temperatures() -> void:
	# Apply authored pool-shell temperatures.
	if get_tree() == null:
		return
	for node: Node in get_tree().get_nodes_in_group("thermal_surfaces"):
		var mi := node as MeshInstance3D
		if mi == null or mi.mesh == null:
			continue
		var feature: String = str(mi.get_meta("feature_name", ""))
		if feature.is_empty():
			continue
		var mat := mi.mesh.surface_get_material(0) as ShaderMaterial
		if mat == null:
			continue
		var id: int = mat.get_instance_id()
		if not _pool_surface_defaults.has(id):
			_pool_surface_defaults[id] = mat.get_shader_parameter("temperature_c")
		mat.set_shader_parameter("temperature_c", _pool_shell_temperatures.get(feature, _pool_surface_defaults[id]))

func load_insect_bird_summary() -> void:
	if not ReleaseData.file_exists("res://data/insect_bird.json"):
		return
	var parsed: Variant = JSON.parse_string(ReleaseData.get_file_as_string("res://data/insect_bird.json"))
	if parsed is Dictionary:
		_insect_bird_summary = parsed

func load_optional_sidecar(path: String) -> Dictionary:
	if not ReleaseData.file_exists(path):
		return {}
	var parsed: Variant = JSON.parse_string(ReleaseData.get_file_as_string(path))
	if parsed is Dictionary:
		return parsed
	push_warning("Optional sidecar is not a JSON object; ignoring: " + path)
	return {}

func refresh_pools_state() -> void:
	var path := "res://data/pools_state.json"
	if not ReleaseData.file_exists(path):
		return
	var mtime: int = ReleaseData.get_modified_time(path)
	if mtime == _pools_state_mtime and not _pools_state_summary.is_empty():
		return
	_pools_state_mtime = mtime
	_pools_state_summary = load_optional_sidecar(path)
	# Apply updated shell temperatures to thermal surfaces.
	var rows: Variant = _pools_state_summary.get("pools", null)
	if rows is Array:
		for row: Variant in rows:
			if not row is Dictionary:
				continue
			var pool_name: String = str(row.get("name", row.get("id", "")))
			if pool_name.is_empty():
				continue
			_pool_shell_temperatures[pool_name] = float(row.get("t_center_c", _pool_shell_temperatures.get(pool_name, 0.0)))
	apply_pool_temperatures()

func build_core_terrain() -> void:
	if not ResourceLoader.exists("res://scripts/core_terrain.gd") or not ResourceLoader.exists("res://scripts/mat_surface.gd"):
		return
	var mat_surface_script: Script = load("res://scripts/mat_surface.gd")
	_mat_surface = mat_surface_script.new()
	_mat_surface.load_outflow()
	_mat_surface.load_pigment()
	_mat_surface.load_outflow_temperature()
	var core_script: Script = load("res://scripts/core_terrain.gd")
	var core: Node3D = core_script.new()
	core.name = "CoreTerrain"
	add_child(core)
	var ok: bool = core.build(_mat_surface)
	if not ok:
		core.queue_free()
		_mat_surface = null
		return
	var authored_scene: Node = get_node_or_null("AuthoredMidway")
	if authored_scene == null:
		push_warning("core_terrain: AuthoredMidway scene not found; master cut skipped.")
	else:
		core.cut_master_tiles(authored_scene)
	if not bool(core.render_cut_status().get("collision_complete", false)):
		push_error("core_terrain: collision cut incomplete; original master terrain retained.")
		core.queue_free()
		_mat_surface = null
		return
	_core_terrain = core
	core.cut_open_water(spec.pools)
	core.set_terrain_cut_uniform(terrain_materials)
	var core_material: ShaderMaterial = core.get_mat_material()
	if core_material != null and not core_material in terrain_materials:
		terrain_materials.append(core_material)
	apply_season()
	apply_snow_patch_mask()
	# Seed the pigment-file mtime poll.
	if ReleaseData.file_exists("res://data/mat_pigment.png"):
		_mat_pigment_mtime = ReleaseData.get_modified_time("res://data/mat_pigment.png")
	print(_mat_surface.status_line())
	print("core_terrain: tile built; extent=%s" % str(core.extent_rect()))

func _poll_mat_pigment_change(delta: float) -> void:
	# Poll pigment data and advance its cross-fade.
	if _core_terrain == null or _mat_surface == null:
		return
	var mat_material: ShaderMaterial = _core_terrain.get_mat_material() if _core_terrain.has_method("get_mat_material") else null
	if mat_material == null:
		return
	var path: String = "res://data/mat_pigment.png"
	if ReleaseData.file_exists(path):
		var mtime: int = ReleaseData.get_modified_time(path)
		if _mat_pigment_mtime != mtime:
			# Reload pigment through the raw-PNG loader.
			var reloader_image: Image = Image.new()
			var resolved: String = ReleaseData.resolve_path(path)
			var err: int = reloader_image.load(ProjectSettings.globalize_path(resolved))
			if err != OK:
				err = reloader_image.load(resolved)
			var new_pigment: Texture2D = ImageTexture.create_from_image(reloader_image) if err == OK else null
			if new_pigment != null:
				_mat_surface.start_blend(mat_material, new_pigment)
				_mat_pigment_blend = 0.0
				_mat_pigment_blending = true
				_mat_pigment_mtime = mtime
				print("mat_surface: pigment republish detected; blending over %.1f s." % PIGMENT_BLEND_DURATION_S)
	if _mat_pigment_blending:
		_mat_pigment_blend = clampf(_mat_pigment_blend + delta / PIGMENT_BLEND_DURATION_S, 0.0, 1.0)
		mat_material.set_shader_parameter("mat_pigment_blend", _mat_pigment_blend)
		if _mat_pigment_blend >= 1.0:
			_mat_pigment_blending = false

func build_scientific_overlays() -> void:
	if not ResourceLoader.exists("res://scripts/scientific_overlays.gd"):
		return
	var overlays_script: Script = load("res://scripts/scientific_overlays.gd")
	_overlays = overlays_script.new()
	_overlays.name = "ScientificOverlays"
	add_child(_overlays)
	_overlays.call("bind", self, _plume_field_summary, _geochemistry_summary, _overland_summary, _groundwater_summary)

func apply_snow_patch_mask() -> void:
	var mask_path := "res://data/snow_patch_mask.png"
	if not ReleaseData.file_exists(mask_path):
		return
	var mask: Texture2D = ReleaseData.texture(mask_path)
	for mat: ShaderMaterial in terrain_materials:
		mat.set_shader_parameter("snow_mask", mask)
	print("snow_patch_mask applied from %s" % mask_path)

func make_environment() -> void:
	sun = DirectionalLight3D.new()
	sun.name = "AfternoonSun"
	sun.light_color = Color(1.0,.975,.92)
	sun.light_energy = .8
	ShadowQuality.apply(sun)
	add_child(sun)
	environment = Environment.new()
	environment.background_mode = Environment.BG_SKY
	sky_material = PhysicalSkyMaterial.new()
	sky_material.rayleigh_coefficient = 2.0
	sky_material.rayleigh_color = Color(0.30, 0.405, 0.60)
	sky_material.mie_coefficient = 0.0035
	sky_material.mie_color = Color(0.69, 0.73, 0.81)
	sky_material.mie_eccentricity = 0.80
	sky_material.turbidity = 2.6
	sky_material.sun_disk_scale = 1.0
	sky_material.use_debanding = true
	var sky := Sky.new()
	sky.sky_material = sky_material
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_sky_contribution = 0.0
	environment.ambient_light_color = Color(.66,.72,.78)
	environment.ambient_light_energy = .50
	environment.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	environment.tonemap_exposure = 1.0
	environment.fog_enabled = true
	environment.fog_light_color = Color(.59,.70,.76)
	environment.fog_density = .000045
	environment.fog_aerial_perspective = .12
	environment.ssao_enabled = RenderingServer.get_current_rendering_method()=="forward_plus"
	environment.ssao_radius = 2.0
	environment.ssao_intensity = 1.3
	var world_env := WorldEnvironment.new()
	world_env.environment = environment
	add_child(world_env)

func make_audio() -> void:
	var wind_path := "res://assets/audio/nps_lower_basin_wind.mp3"
	if ResourceLoader.exists(wind_path):
		var wind := AudioStreamPlayer.new()
		wind.stream = load(wind_path)
		wind.stream.loop = true
		wind.volume_db = -26.0
		add_child(wind)
		wind.play()
	var audio_spec := [
		["res://assets/audio/nps_geyser_hill_water.mp3",Vector3(70,12,-165),-12.0,100.0],
		["res://assets/audio/nps_geyser_hill_birds.mp3",Vector3(-355,42,255),-18.0,200.0],
		["res://assets/audio/nps_firehole_dipper_geese.mp3",Vector3(73,7,-263),-22.0,100.0]
	]
	for entry: Array in audio_spec:
		if not ResourceLoader.exists(entry[0]):
			continue
		var voice := AudioStreamPlayer3D.new()
		voice.stream = load(entry[0])
		voice.stream.loop = true
		voice.position = entry[1]
		voice.volume_db = entry[2]
		voice.unit_size = 12.0
		voice.max_distance = entry[3]
		add_child(voice)
		voice.play()

func make_wildlife() -> void:
	# ecosystem.json supplies the actor roster.
	if not ResourceLoader.exists("res://scripts/wildlife_actor.gd"):
		return
	var script: Script = load("res://scripts/wildlife_actor.gd")
	for record: Dictionary in ecosystem.params.get("wildlife",[]):
		var actor: Node3D = script.new()
		actor.setup(record,height_field,ecosystem)
		add_child(actor)
		_wildlife_nodes.append(actor)

func start_portfolio_experiment() -> void:
	var comparison: Dictionary = load_optional_sidecar("res://data/portfolio_comparison.json")
	if comparison.is_empty() or ecosystem.live_mode:
		return
	go_to_anchor(2)
	ecosystem.elapsed = 0.0
	ecosystem.call("_apply_replay", 0.0)
	ecosystem.time_scale = 120.0
	_requested_pause = false
	_apply_pause_state()
	resume()
	set_field_notes_open(true)
	help_label.text = "Guided scenario: Excelsior river-entry temperature +18 C from 600 to 3600 model seconds. H opens the river probe; Q pauses."

func panel_style(alpha := .95) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = Color(.063,.086,.075,alpha)
	style.border_color = Color(.39,.47,.36,.7)
	style.set_border_width_all(1)
	style.set_corner_radius_all(6)
	style.content_margin_left = 30
	style.content_margin_right = 30
	style.content_margin_top = 26
	style.content_margin_bottom = 26
	return style

func text_label(text: String, size: int, color := Color(.89,.90,.83)) -> Label:
	var label := Label.new()
	label.text=text
	label.add_theme_font_size_override("font_size",size)
	label.add_theme_color_override("font_color",color)
	return label

func make_button(text: String, action: Callable) -> Button:
	var button := Button.new()
	button.text=text
	button.alignment=HORIZONTAL_ALIGNMENT_LEFT
	button.custom_minimum_size=Vector2(0,45)
	button.add_theme_font_size_override("font_size",17)
	var normal := StyleBoxFlat.new()
	normal.bg_color=Color(.18,.24,.19)
	normal.set_corner_radius_all(4)
	normal.content_margin_left=16
	var hover := normal.duplicate()
	hover.bg_color=Color(.30,.37,.25)
	button.add_theme_stylebox_override("normal",normal)
	button.add_theme_stylebox_override("hover",hover)
	button.add_theme_stylebox_override("focus",hover)
	button.pressed.connect(action)
	return button

func make_interface() -> void:
	overlay=CanvasLayer.new()
	add_child(overlay)
	var ui := Control.new()
	ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	ui.mouse_filter=Control.MOUSE_FILTER_IGNORE
	overlay.add_child(ui)
	var top := VBoxContainer.new()
	top.position=Vector2(34,28)
	ui.add_child(top)
	top.add_child(text_label("Y E L L O W S T O N E",13,Color(.87,.84,.66)))
	location_label=text_label("MIDWAY GEYSER BASIN",25)
	top.add_child(location_label)
	status_label=text_label("",13,Color(.78,.81,.73))
	top.add_child(status_label)
	help_label=text_label(build_help_text(),14)
	help_label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	help_label.position=Vector2(34,-48)
	ui.add_child(help_label)
	make_toast(ui)
	menu=PanelContainer.new()
	menu.set_anchors_and_offsets_preset(Control.PRESET_CENTER_RIGHT)
	menu.position=Vector2(-492,-285)
	menu.custom_minimum_size=Vector2(448,500)
	menu.add_theme_stylebox_override("panel",panel_style())
	ui.add_child(menu)
	content=VBoxContainer.new()
	content.add_theme_constant_override("separation",14)
	menu.add_child(content)
	content.add_child(text_label("A WALK THROUGH MIDWAY",12,Color(.80,.76,.52)))
	content.add_child(text_label("Grand Prismatic",34))
	var intro := text_label("Follow the boardwalk, watch the river,\nand walk up through the pines.",17)
	content.add_child(intro)
	content.add_child(text_label("4.096 × 4.096 km  ·  distances at actual scale",13,Color(.71,.77,.68)))
	content.add_child(make_button("Begin walking",resume))
	if ReleaseData.file_exists("res://data/portfolio_comparison.json"):
		content.add_child(make_button("Guided river temperature experiment", start_portfolio_experiment))
	var rule := HSeparator.new()
	content.add_child(rule)
	content.add_child(text_label("STARTING PLACES",12,Color(.80,.76,.52)))
	for i in spec.anchors.size():
		var index: int = i
		content.add_child(make_button(spec.anchors[i].title,func(): go_to_anchor(index);resume()))
	content.add_child(text_label("F  HUD cycle    F3  Fly for authoring    R  Return    P  Menu\nController: left stick walks, right stick looks.",12,Color(.70,.74,.66)))
	# Field notes use a ranger notebook panel.
	info_panel=PanelContainer.new()
	info_panel.position=Vector2(34,90)
	info_panel.custom_minimum_size=Vector2(580,680)
	var paper := StyleBoxFlat.new()
	paper.bg_color=Color(0.936,0.910,0.820,0.985)          # parchment
	paper.border_color=Color(0.36,0.29,0.19,0.9)
	paper.set_border_width_all(2)
	paper.set_corner_radius_all(3)
	paper.shadow_color=Color(0,0,0,0.45)
	paper.shadow_size=14
	paper.content_margin_left=44
	paper.content_margin_right=36
	paper.content_margin_top=36
	paper.content_margin_bottom=32
	info_panel.add_theme_stylebox_override("panel",paper)
	info_panel.visible=false
	ui.add_child(info_panel)
	var notes_vbox := VBoxContainer.new()
	notes_vbox.add_theme_constant_override("separation",10)
	info_panel.add_child(notes_vbox)
	var notes_title := text_label("FIELD NOTES — MIDWAY",13,Color(0.42,0.33,0.20))
	notes_vbox.add_child(notes_title)
	var rule2 := HSeparator.new()
	rule2.add_theme_color_override("color",Color(0.55,0.47,0.34))
	notes_vbox.add_child(rule2)
	info_label=RichTextLabel.new()
	info_label.custom_minimum_size=Vector2(500,560)
	info_label.bbcode_enabled=true
	info_label.fit_content=false
	info_label.scroll_active=true
	info_label.add_theme_font_size_override("normal_font_size",16)
	info_label.add_theme_color_override("default_color",Color(0.17,0.14,0.10))
	notes_vbox.add_child(info_label)
	var map_script: Script=load("res://scripts/map_view.gd")
	map_view=Control.new()
	map_view.set_script(map_script)
	map_view.world=self
	map_view.position=Vector2(34,140)
	map_view.size=Vector2(590,680)
	map_view.visible=false
	ui.add_child(map_view)
	if not _census_summary.is_empty():
		var census_doc: Variant = _census_summary.get("payload", _census_summary)
		if census_doc is Dictionary:
			var trees: Variant = census_doc.get("trees")
			if trees is Array:
				map_view.call("set_census", trees)
	if ResourceLoader.exists("res://scripts/calibration_panel.gd"):
		_calibration_panel = Control.new()
		_calibration_panel.set_script(load("res://scripts/calibration_panel.gd"))
		_calibration_panel.position = Vector2(640, 140)
		_calibration_panel.size = Vector2(560, 480)
		_calibration_panel.visible = false
		ui.add_child(_calibration_panel)
		_calibration_panel.call("set_doc", _calibration_summary)

func make_toast(ui: Control) -> void:
	toast_label = text_label("", 15, Color(0.95, 0.90, 0.70))
	toast_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	toast_label.position = Vector2(-300, -90)
	toast_label.custom_minimum_size = Vector2(600, 30)
	toast_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	toast_label.visible = false
	ui.add_child(toast_label)

func toast(text: String) -> void:
	toast_label.text = text
	toast_label.visible = true
	toast_seconds = 2.5

func build_help_text() -> String:
	# The bottom bar lists an overlay shortcut when its sidecar published data.
	var items: PackedStringArray = ["WASD  Walk", "Shift  Brisk walk", "Mouse  Look", "M  Map", "I  Field notes"]
	if not _calibration_summary.is_empty(): items.append("K  Calibration")
	if not _plume_field_summary.is_empty(): items.append("O  Plume")
	if not _geochemistry_summary.is_empty(): items.append("G  Geochemistry")
	if not _census_summary.is_empty(): items.append("U  Census (on map)")
	if not _overland_summary.is_empty(): items.append("J  Overland")
	if not _groundwater_summary.is_empty(): items.append("L  Groundwater")
	items.append("Ctrl-S  Study mode")
	items.append("P  Menu")
	return "    ".join(items)

func cycle_hud() -> void:
	hud_mode = (hud_mode + 1) % 3
	status_label.visible = hud_mode == 0
	help_label.visible = hud_mode == 0
	location_label.visible = hud_mode < 2
	# F leaves the menu, map, notes, help, and simulation panel untouched.

func set_field_notes_open(open: bool) -> void:
	if open == info_panel.visible:
		return
	if open:
		_requested_pause = ecosystem.paused
	info_panel.visible = open
	if open:
		map_view.visible = false
	_apply_pause_state()
	_sync_player_input()

func _modal_open() -> bool:
	return menus_open or info_panel.visible or simulation_panel.visible or input_help.visible or (_calibration_panel != null and _calibration_panel.visible)

func _sync_player_input() -> void:
	var blocked: bool = _modal_open() or _cursor_released
	player.enabled = not blocked
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if blocked else Input.MOUSE_MODE_CAPTURED

func go_to_anchor(index: int) -> void:
	camera_anchor=index
	var a: Dictionary=spec.anchors[index]
	var p: Array=a.position
	var target: Array=a.target.duplicate()
	if a.id=="overlook" or a.id=="boardwalk":
		for pool: Dictionary in spec.pools:
			if pool.source_id==1034:
				target=pool.center.duplicate()
				target[1]+=1.0
	player.place_at(Vector3(p[0],p[1],p[2]),Vector3(target[0],target[1],target[2]))

func resume() -> void:
	menus_open=false
	menu.visible=false
	_cursor_released = false
	_sync_player_input()

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.physical_keycode == KEY_ESCAPE:
		if not _modal_open():
			_cursor_released = not _cursor_released
		_sync_player_input()
		return
	if InputHelp.pressed(event, "menu"):
		menus_open = not menus_open
		menu.visible = menus_open
		if not menus_open:
			_cursor_released = false
		_sync_player_input()
	elif InputHelp.pressed(event, "field_notes"):
		set_field_notes_open(not info_panel.visible)
	elif InputHelp.pressed(event, "map"):
		map_view.visible = not map_view.visible
		set_field_notes_open(false)
	elif InputHelp.pressed(event, "photo_mode"):
		cycle_hud()
	elif InputHelp.pressed(event, "authoring_flight"):
		player.fly_mode = not player.fly_mode
	elif InputHelp.pressed(event, "return_to_anchor"):
		go_to_anchor(camera_anchor)
	elif InputHelp.pressed(event, "jump_two_hours"):
		if ecosystem.live_mode:
			live_client.command("advance_time", {"elapsed_s": 7200.0})
		elif not ecosystem.get("_frames").is_empty():
			var target: float = minf(ecosystem.elapsed + 7200.0, float(ecosystem.get("_frames")[-1].t_s))
			if target <= ecosystem.elapsed:
				toast("Replay has reached its end")
			else:
				ecosystem.elapsed = target
				ecosystem.call("_apply_replay", ecosystem.elapsed)
				update_environment()
		else:
			toast("No replay frames to jump through")
	elif InputHelp.pressed(event, "compare_replay"):
		toggle_replay()
	elif InputHelp.pressed(event, "study_scene"):
		# Toggle the study probe overlay in place.
		var probes: Node3D = get_node("ThermalProbes")
		probes.visible = not probes.visible
		simulation_panel.visible = probes.visible
		_sync_player_input()
		toast("Study mode %s" % ("on" if probes.visible else "off"))
	elif InputHelp.pressed(event, "calibration") and _calibration_panel != null:
		_calibration_panel.visible = not _calibration_panel.visible
		_sync_player_input()
	elif InputHelp.pressed(event, "plume") and _overlays != null:
		if _plume_field_summary.is_empty():
			toast("Plume field not published in this build")
		else:
			toast("Plume overlay %s (Excelsior footprint)" % ("on" if _overlays.toggle_plume() else "off"))
	elif InputHelp.pressed(event, "geochemistry") and _overlays != null:
		if _geochemistry_summary.is_empty():
			toast("Geochemistry not published in this build")
		else:
			toast("Geochemistry overlay %s" % ("on" if _overlays.toggle_geochemistry() else "off"))
	elif InputHelp.pressed(event, "census"):
		if map_view.visible:
			map_view.census_visible = not map_view.census_visible
			map_view.queue_redraw()
		else:
			toast("Open the map first (M), then U toggles the census circles")
	elif InputHelp.pressed(event, "overland") and _overlays != null:
		if _overland_summary.is_empty():
			toast("Overland flow not published in this build")
		else:
			toast("Overland overlay %s" % ("on" if _overlays.toggle_overland() else "off"))
	elif InputHelp.pressed(event, "groundwater") and _overlays != null:
		if _groundwater_summary.is_empty():
			toast("Groundwater field not published in this build")
		else:
			toast("Groundwater overlay %s" % ("on" if _overlays.toggle_groundwater() else "off"))
	elif InputHelp.pressed(event, "help"):
		input_help.visible = not input_help.visible
		_sync_player_input()
	elif InputHelp.pressed(event, "conditions"):
		simulation_panel.visible = not simulation_panel.visible
		_sync_player_input()
	elif InputHelp.pressed(event, "probe"):
		simulation_panel.toggle_probe()
		get_node("ThermalProbes").visible = not get_node("ThermalProbes").visible
		_sync_player_input()
	elif InputHelp.pressed(event, "pause"):
		toggle_pause()
	elif InputHelp.pressed(event, "step_frame"):
		step_simulation()
	else:
		for rate: int in [1, 60, 600, 3600]:
			if InputHelp.pressed(event, "scale_%d" % rate):
				set_time_scale(float(rate))
		for kind: String in ["shade", "outflow", "tributary", "grazing"]:
			if InputHelp.pressed(event, "intervene_" + kind):
				intervene(kind)

func intervene(kind: String) -> void:
	if not ecosystem.live_mode:
		toast("Interventions need a live Python session")
		return
	var state: Dictionary = ecosystem.reach_at(player.position.z)
	var changes: Dictionary = {}
	match kind:
		"shade": changes = {"river.shade": {"cell_ids": [state.get("cell_id", state.get("id", ""))], "multiplier": 0.5}}
		"outflow":
			_outflow_enabled = not _outflow_enabled
			changes = {"thermal.excelsior_enabled": _outflow_enabled}
		"tributary": changes = {"aquatic.tributary_pockets": true, "aquatic.pocket_temperature_c": 11.0}
		"grazing": changes = {"grazing.bison_count": {"patch_id": "bridge_riparian", "count": 2}}
	live_client.control(changes, [player.position.x, player.position.y, player.position.z])
	var marker: MeshInstance3D = MeshInstance3D.new()
	var sphere: SphereMesh = SphereMesh.new()
	sphere.radius = 0.3
	sphere.height = 0.6
	marker.mesh = sphere
	marker.position = player.position - player.global_basis.z * 2.0
	marker.set_meta("intervention", kind)
	add_child(marker)

func toggle_replay() -> void:
	if ecosystem.live_mode:
		mark_comparison()
		return
	if replay_path_alt.is_empty() or ecosystem == null:
		return
	if not ecosystem.has_method("thermal_probe_records"):
		return
	var current: String = str(ecosystem.get("replay_path"))
	var next_path: String = replay_path_alt if current != replay_path_alt else replay_path
	if next_path.is_empty() or next_path == current:
		return
	ecosystem.set("replay_path", next_path)
	ecosystem.call("configure", ecosystem.get("params"))
	replay_run_name = next_path.get_file().get_basename()

func _process(delta: float) -> void:
	_sync_atmosphere_clock()
	if toast_seconds > 0.0:
		toast_seconds -= delta
		if toast_seconds <= 0.0 and toast_label != null:
			toast_label.visible = false
	if ecosystem==null or status_label==null:
		return
	if live_client != null:
		live_client.player_t_s = ecosystem.elapsed
	if ecosystem.epoch_unix > 0.0:
		_simulation_start_epoch_unix = ecosystem.epoch_unix - ecosystem.elapsed
		_has_simulation_epoch = true
	if _has_simulation_epoch and atmosphere_controller != null:
		# Read model time from ecosystem.elapsed.
		_simulation_epoch_unix = _simulation_start_epoch_unix + float(ecosystem.elapsed)
		if not ecosystem.live_mode:
			atmosphere_controller.clear_weather_solar_override()
		atmosphere_controller.set_simulation_timestamp(
			_simulation_epoch_unix, float(spec.get("utc_offset_hours", -6.0))
		)
		if weather_snapshot_reader != null:
			weather_snapshot_reader.set_simulation_epoch_unix(_simulation_epoch_unix)
	observation_timer+=delta
	if observation_timer>.3:
		observation_timer=0
		var p: Vector3=player.global_position
		var nearest: Dictionary=spec.anchors[0]
		var best:=INF
		for a: Dictionary in spec.anchors:
			var d:=Vector2(p.x-a.position[0],p.z-a.position[2]).length()
			if d<best:
				best=d
				nearest=a
		location_label.text=nearest.title.to_upper() if best<180 else "FIREHOLE COUNTRY"
		var hour:=int(ecosystem.clock_hour)
		var minute:=int(fmod(ecosystem.clock_hour,1.0)*60)
		status_label.text = simulation_status_text() + " | %.1f C air | %d m elevation" % [ecosystem.air_c, int(p.y + 2200)]
		update_notes()
		if map_view != null and map_view.visible:
			map_view.queue_redraw()
		update_environment()
		refresh_env_caches()
	if _mat_pigment_blending:
		_poll_mat_pigment_change(delta)

func _sync_atmosphere_clock() -> void:
	if atmosphere_controller == null or ecosystem == null:
		return
	# Sync atmosphere pacing to the simulation clock.
	atmosphere_controller.time_scale = 0.0 if ecosystem.paused or ecosystem.clock_held else maxf(ecosystem.time_scale, 0.0)
	atmosphere_controller.set_simulation_elapsed(float(ecosystem.elapsed), not ecosystem.live_mode)

func update_environment() -> void:
	if atmosphere_controller == null or ecosystem == null:
		return
	_sync_atmosphere_clock()
	if _has_simulation_epoch:
		atmosphere_controller.set_simulation_timestamp(_simulation_epoch_unix, float(spec.get("utc_offset_hours", -6.0)))
	if ecosystem.live_mode:
		var weather: Dictionary = ecosystem.current_frame.get("weather", {}).duplicate(true)
		if weather.get("solar") is Dictionary:
			weather.merge(weather.solar, true)
		weather["air_temperature_c"] = ecosystem.air_c
		weather["relative_humidity"] = ecosystem.humidity
		weather["cloud_fraction"] = ecosystem.cloud
		weather["wind_speed_mps"] = ecosystem.wind.length()
		weather["wind_direction_deg"] = fposmod(rad_to_deg(atan2(-ecosystem.wind.x, ecosystem.wind.y)), 360.0)
		var ecology: Dictionary = ecosystem.current_frame.get("ecology", {})
		var terrain: Dictionary = ecology.get("terrain", {}).duplicate(true)
		if ecology.get("snow") is Dictionary and ecology.snow.get("swe_mm") != null:
			terrain["snow_water_equivalent_mm"] = ecology.snow.swe_mm
		if ecology.get("soil") is Dictionary and ecology.soil.get("temperature_c") != null:
			terrain["soil_temperature_c"] = ecology.soil.temperature_c
		var cover_sum: float = 0.0
		var cover_count: int = 0
		for patch: Dictionary in ecology.get("patches", []):
			if patch.get("snow_cover_fraction") != null:
				cover_sum += float(patch.snow_cover_fraction)
				cover_count += 1
		if cover_count > 0:
			terrain["snow_cover_fraction"] = cover_sum / float(cover_count)
		if not terrain.is_empty():
			weather["terrain"] = terrain
		if weather.get("precip_mm_h") != null:
			weather["precipitation_rate_mm_h"] = weather.precip_mm_h
		atmosphere_controller.set_weather_state(weather)
	var display: Variant = ecosystem.frame_header.get("display_hour")
	if display != null:
		atmosphere_controller.clear_weather_solar_override()
		atmosphere_controller.set_simulation_time(float(display), int(spec.get("day_of_year", 196)), float(spec.get("utc_offset_hours", -6.0)))
	for mat: ShaderMaterial in foliage_materials:
		mat.set_shader_parameter("wind_vector", ecosystem.wind)
func refresh_env_caches() -> void:
	if _steam_nodes.is_empty():
		_steam_nodes.assign(get_tree().get_nodes_in_group("steam"))
	if _river_nodes.is_empty():
		_river_nodes.assign(get_tree().get_nodes_in_group("river_surfaces"))

	for node in _steam_nodes:
		var mmi := node as MultiMeshInstance3D
		if mmi == null or mmi.multimesh == null or mmi.multimesh.mesh == null:continue
		var mat := mmi.multimesh.mesh.material as ShaderMaterial
		if mat == null:continue
		mat.set_shader_parameter("wind",ecosystem.wind)
		# Condensation inputs follow yellowstone_python.microclimate.
		var steam_report: Dictionary = _sidecar_data.get("steam_microclimate.json", {}).get("report", {})
		var near_pool: float = 0.0
		for pool: Dictionary in spec.get("pools", []):
			var center: Array = pool.get("center", [0.0, 0.0, 0.0])
			var distance: float = Vector2(node.position.x - float(center[0]), node.position.z - float(center[2])).length() if node is Node3D else INF
			near_pool = maxf(near_pool, clampf(1.0 - distance / maxf(float(steam_report.get("fetch_length_m", 1.0)), 1.0), 0.0, 1.0))
		var moisture: float = 1.0 + near_pool * maxf(0.0, float(steam_report.get("downwind_rh", ecosystem.humidity)) - ecosystem.humidity)
		mat.set_shader_parameter("density", ecosystem.condensation_visibility(float(node.get_meta("surface_c", 76.0))) * STEAM_DENSITY_SCALE * moisture)
	for node in _river_nodes:
		if str(node.get_meta("river_name","")).to_upper()!="FIREHOLE RIVER":continue
		var mi := node as MeshInstance3D
		if mi == null or mi.mesh == null:continue
		var mat := mi.mesh.surface_get_material(0) as ShaderMaterial
		if mat == null:continue
		var reach: Dictionary = ecosystem.reach_at(float(node.get_meta("sample_z",0.0)))
		mat.set_shader_parameter("temperature_c",reach.temperature_c)
		var baseline: float = float(_river_flow_speed_defaults.get(mi.get_instance_id(), 0.55))
		var reach_flow: float = float(reach.get("flow_m3s", RIVER_FLOW_BASELINE_M3S))
		var ratio: float = clampf(reach_flow / RIVER_FLOW_BASELINE_M3S, RIVER_FLOW_RATIO_MIN, RIVER_FLOW_RATIO_MAX)
		mat.set_shader_parameter("flow_speed", baseline * ratio)
	_update_terrain_water_level()

func _update_terrain_water_level() -> void:
	var rivers: Array = spec.get("rivers", [])
	var extent := float(spec.get("georeference", {}).get("extent", 4096.0))
	var key := hash([rivers, extent])
	if _water_stage_texture == null or key != _water_stage_key:
		var image: Image = preload("res://scripts/river_terrain.gd").stage_image(rivers, Vector2.ONE * -extent * 0.5, Vector2.ONE * extent)
		_water_stage_texture = ImageTexture.create_from_image(image)
		_water_stage_key = key
	for mat: ShaderMaterial in terrain_materials:
		mat.set_shader_parameter("water_level_texture", _water_stage_texture)
		mat.set_shader_parameter("water_level_available", 1.0)
		TerrainMaterials.set_layer_rect(mat, "water", -extent * 0.5, -extent * 0.5, extent, extent)

func update_notes() -> void:
	if not info_panel.visible:
		return
	var reach: Dictionary=ecosystem.reach_at(player.position.z)
	var bank: Dictionary=ecosystem.patch("bridge_riparian")
	var compartments: Dictionary = _insect_bird_summary.get("compartments", {}) if not _insect_bird_summary.is_empty() else {}
	var final: Dictionary = compartments.get("final", {})
	var consumed: Dictionary = compartments.get("consumed_total", {})
	var dipper: float = float(consumed.get("dipper", 0.0))
	var raven: float = float(consumed.get("raven", 0.0))
	var trout: float = float(consumed.get("trout", 0.0))
	var emergence: float = float(compartments.get("emergence_total", 0.0))
	var biological_block: String = ""
	if not final.is_empty():
		biological_block = "\n[b]Biological ledger[/b]\nInsect benthic: %.3f  emergent: %.3f  terrestrial: %.3f\nEmergence rate: %.3f  consumed by dipper %.2f, raven %.2f, trout %.2f" % [float(final.get("Nb", 0.0)), float(final.get("Ne", 0.0)), float(final.get("Nt", 0.0)), emergence, dipper, raven, trout]
	var sidecar_block: String = format_sidecar_block()
	if simulation_panel != null:
		sidecar_block += simulation_panel.model_notes()
	info_label.text="[color=#d6c88f][b]OBSERVING MIDWAY[/b][/color]\n\nThe blue centers are deep hot water. Microbial mats occupy cooler edges and runoff. Follow the drainage fingers toward the Firehole.\n\n[b]Environmental model[/b]\nNearby river reach: %.1f °C\nFlow: %.2f m³/s\nWind: %.1f m/s\nRiverbank insects: %s (activity %.2f)\nSnow: %s%s%s\n\nThe temperature and activity values are illustrative simulation states. Geometry follows USGS elevation and NPS mapping; water depth, plants, and wildlife are authored approximations.\n\n[I] Close notes    [T] Jump simulation by 2 h    [P] Menu" % [reach.temperature_c,reach.flow_m3s,ecosystem.wind.length(),("hover" if float(bank.get("insect_activity",0.0))>0.035 else "inactive"),float(bank.get("insect_activity",0.0)),("see season sidecar" if ReleaseData.file_exists("res://data/season.json") else "summer baseline"),biological_block,sidecar_block]

func format_sidecar_block() -> String:
	# Format diagnostics for field notes.
	var lines: Array = []
	lines.append("[color=#6b5433][b]Published diagnostics (frozen at build)[/b][/color]")
	if not _plume_field_summary.is_empty():
		lines.append("• Thermal plume: %d×%d grid; Excelsior %.1f °C, river %.1f °C" % [
			int(_plume_field_summary.get("nx", 0)), int(_plume_field_summary.get("nz", 0)),
			float(_plume_field_summary.get("hot_source_c", 0.0)), float(_plume_field_summary.get("river_c", 0.0))])
	if not _geochemistry_summary.is_empty():
		var cells: Variant = _geochemistry_summary.get("cells")
		var n: int = (cells as Array).size() if cells is Array else 0
		var observed: int = 0
		if cells is Array:
			for row: Variant in cells:
				if row is Dictionary and row.get("silica_saturation_index") != null:
					observed += 1
		lines.append("• Geochemistry: %d river cells, %d with SiO₂ readings" % [n, observed])
	if not _calibration_summary.is_empty():
		var fit: Variant = _calibration_summary.get("reach_fit")
		if fit is Dictionary and fit.get("holdout_rmse_c") != null:
			lines.append("• River heat calibration: holdout RMSE %.2f °C (%s)" % [
				float(fit["holdout_rmse_c"]), str(fit.get("status", "unrecorded"))])
	if not _census_summary.is_empty():
		var census_doc: Variant = _census_summary.get("payload", _census_summary)
		var trees: Variant = census_doc.get("trees") if census_doc is Dictionary else null
		lines.append("• Tree census: %d trees" % ((trees as Array).size() if trees is Array else 0))
	if not _pools_state_summary.is_empty():
		var pools: Variant = _pools_state_summary.get("pools")
		lines.append("• Pools: %d records" % ((pools as Array).size() if pools is Array else 0))
	if not _grazer_summary.is_empty():
		var g: Variant = _grazer_summary.get("wildlife")
		lines.append("• Grazer diagnostics: %d records" % ((g as Array).size() if g is Array else 0))
	if not _fish_summary.is_empty():
		var f: Variant = _fish_summary.get("wildlife")
		lines.append("• Fish diagnostics: %d records" % ((f as Array).size() if f is Array else 0))
	if not _overland_summary.is_empty():
		lines.append("• Overland flow: %s" % str(_overland_summary.get("status", "available")))
	# Report presence for sidecars without a digest.
	var digested: Array[String] = ["plume_field.json", "geochemistry.json", "calibration_summary.json",
		"census.json", "pools_state.json", "grazer.json", "fish.json", "overland_field.json"]
	for file: String in SIDECAR_PATHS:
		if file in digested:
			continue
		var doc: Dictionary = _sidecar_data.get(file, {})
		if not doc.is_empty():
			lines.append("• %s: recorded" % file.get_basename().capitalize())
	for file: String in ["plume_field.json", "groundwater_field.json", "overland_field.json", "season.json"]:
		if not ReleaseData.file_exists("res://data/" + file):
			lines.append("• %s: unavailable in this generation" % file.get_basename().capitalize())
	return "\n\n" + "\n".join(lines)

func run_smoke_test() -> void:
	await get_tree().process_frame
	print("SMOKE scene=ready terrain=",get_node("AuthoredMidway/TerrainTiles").get_child_count()," routes=",spec.routes.size()," pools=",spec.pools.size())
	var passed := true
	for i in spec.anchors.size():
		go_to_anchor(i)
		player.enabled=true
		for tick in 120:
			await get_tree().physics_frame
		print("SMOKE anchor=",spec.anchors[i].id," floor=",player.is_on_floor()," y=",player.position.y)
		passed = passed and player.is_on_floor() and player.position.is_finite()
	var heat_error: float = ecosystem.heat_budget_error
	print("SMOKE heat_budget_error=", heat_error)
	passed = passed and is_finite(heat_error) and is_zero_approx(heat_error)
	var instances_passed := report_multimesh_validation()
	passed = passed and instances_passed
	print("SMOKE ok=", passed)
	get_tree().quit(0 if passed else 1)

func report_multimesh_validation() -> bool:
	var validation_path := "res://tests/multimesh_validation.json"
	if not FileAccess.file_exists(validation_path):
		print("SMOKE multimesh_validation=absent")
		return false
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(validation_path))
	if not parsed is Dictionary:
		print("SMOKE multimesh_validation=invalid_json")
		return false
	var valid := preload("res://scripts/verification_receipt.gd").valid(parsed)
	print("SMOKE multimesh_validation ok=", valid, " slots=", parsed.get("actual_instance_slots", 0), "/", parsed.get("expected_instance_slots", 0), " failures=", parsed.get("failure_count", -1))
	if not valid:
		print("SMOKE multimesh_validation=failed_or_stale")
	return valid

func capture_preview() -> void:
	resume()
	overlay.visible=false
	var count: int=spec.anchors.size() if "--capture-all" in OS.get_cmdline_user_args() else 1
	var requested:=0
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--capture-index="):
			requested=clampi(int(argument.get_slice("=",1)),0,spec.anchors.size()-1)
	for i in count:
		var index: int=i if count>1 else requested
		go_to_anchor(index)
		for frame in 8:
			await get_tree().process_frame
		await RenderingServer.frame_post_draw
		var shot:=get_viewport().get_texture().get_image()
		shot.save_png("res://docs/preview_%s.png" % spec.anchors[index].id)
		print("CAPTURE saved ",spec.anchors[index].id)
	get_tree().quit()
