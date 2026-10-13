extends Node3D
## Runtime assembles saved authored assets.
const Walker = preload("res://scripts/player.gd")
const HeightField = preload("res://scripts/height_field.gd")
const Ecosystem = preload("res://scripts/ecosystem.gd")
const AtmosphereController = preload("res://scripts/yellowstone_atmosphere.gd")
const WeatherSnapshotReader = preload("res://scripts/weather_snapshot_reader.gd")
## Study scenes set this to a Python replay JSON (see scenes/study.tscn); empty uses the live ecosystem.
@export_file("*.json") var replay_path: String = ""
## Study scenes set this to the comparison replay; C toggles the live run and empty disables the toggle.
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
var hud_visible := true
var map_view: Control
var observation_timer := 0.0
var camera_anchor := 0
var loading: Label
var foliage_materials: Array[ShaderMaterial] = []
var terrain_materials: Array[ShaderMaterial] = []
# Bake-time environment sets; groups assigned once by bake_world.gd.
var _steam_nodes: Array[Node] = []
var _river_nodes: Array[Node] = []
# Steam density multiplier on top of ecosystem.condensation_visibility.
const STEAM_DENSITY_SCALE: float = 0.40
# River flow speed is clamped to this multiplier range around the authored default.
const RIVER_FLOW_RATIO_MIN: float = 0.5
const RIVER_FLOW_RATIO_MAX: float = 2.0
# Firehole illustrative baseline flow in m3/s. Published in ecosystem.boundary_m3s.
const RIVER_FLOW_BASELINE_M3S: float = 8.0
# Baked flow_speed uniform used as the authored default per river material.
var _river_flow_speed_defaults: Dictionary = {}
# Per-pool thermal state from data/pool_shells.json.
var _pool_shell_temperatures: Dictionary = {}
# Last known seasonal snow fields written to terrain materials.
var _snow_amount_from_mean: float = 0.0
var _snow_swe_mm_mean: float = 0.0
# season.json per-patch snow_cover_fraction mean when provided; 1.0 falls back to the painted mask alone.
var _snow_cover_fraction_mean: float = 1.0
# Insect/bird compartment summary read from data/insect_bird.json at ready.
var _insect_bird_summary: Dictionary = {}
# Optional sidecars published by the Python build; each loader tolerates absence and leaves the summary dictionary empty when a file is missing.
var _plume_field_summary: Dictionary = {}
var _geochemistry_summary: Dictionary = {}
var _calibration_summary: Dictionary = {}
var _census_summary: Dictionary = {}
var _pools_state_summary: Dictionary = {}
# Per-step pools_state.json poll: track its mtime to re-read without I/O every frame.
var _pools_state_mtime: int = 0
# Deferred overlay stubs for groundwater and overland fields (fixes-39 item 13).
var _groundwater_summary: Dictionary = {}
var _overland_summary: Dictionary = {}
# Guild diagnostics; the ecosystem.json wildlife list remains the actor roster and these sidecars are consulted only to annotate the field-notes block.
var _grazer_summary: Dictionary = {}
var _fish_summary: Dictionary = {}
# World-space overlays wired to the published sidecars (fixes-39 items 7, 8, 13).
var _overlays: Node3D
var _calibration_panel: Control

func _ready() -> void:
	# Frame cap honors project rendering/limits/fps/max_fps when set.
	var configured_cap: int = int(ProjectSettings.get_setting("rendering/limits/fps/max_fps", 60))
	Engine.max_fps = configured_cap if configured_cap >= 0 else 60
	height_field = HeightField.new()
	if not FileAccess.file_exists("res://data/world.json"):
		push_error("Missing data/world.json: re-extract the complete project.")
		return
	spec = JSON.parse_string(FileAccess.get_file_as_string("res://data/world.json"))
	if not spec is Dictionary or not spec.has("anchors") or not spec.has("routes") or not spec.has("pools"):
		push_error("data/world.json is missing or has no anchors/routes/pools; re-extract the complete project.")
		return
	make_environment()
	if ResourceLoader.exists("res://scenes/authored_world.tscn"):
		var authored: Node = load("res://scenes/authored_world.tscn").instantiate()
		add_child(authored)
		if not authored.has_node("AuthoredVegetation"):
			push_error("authored_world.tscn has no AuthoredVegetation: re-run the offline bake.")
			return
		for item: Node in authored.get_node("AuthoredVegetation").get_children():
			if not item is MultiMeshInstance3D:continue
			if (item as MultiMeshInstance3D).multimesh == null or (item as MultiMeshInstance3D).multimesh.mesh == null:continue
			for surface in item.multimesh.mesh.get_surface_count():
				var mat: Material=item.multimesh.mesh.surface_get_material(surface)
				if mat is ShaderMaterial and mat.shader.resource_path.ends_with("foliage.gdshader") and not mat in foliage_materials:
					foliage_materials.append(mat)
		add_child(load("res://scenes/handcrafted_details.tscn").instantiate())
		if ResourceLoader.exists("res://scenes/botanical_details.tscn"):
			var botany: Node=load("res://scenes/botanical_details.tscn").instantiate()
			add_child(botany)
			collect_foliage_materials(botany)
	else:
		push_error("Missing authored_world.tscn: run the offline bake once, or re-extract the complete project.")
		return
	ecosystem = make_ecosystem()
	ecosystem.name = "Ecosystem"
	add_child(ecosystem)
	player = Walker.new()
	player.name = "Walker"
	add_child(player)
	go_to_anchor(0)
	atmosphere_controller = AtmosphereController.new()
	atmosphere_controller.name = "YellowstoneAtmosphere"
	add_child(atmosphere_controller)
	atmosphere_controller.configure(sun, environment, player)
	# The build's simulation_epoch_unix anchors the simulation clock once; _process adds ecosystem.elapsed seconds to that start.
	if spec.has("simulation_epoch_unix"):
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
	add_child(weather_snapshot_reader)
	weather_snapshot_reader.bind(atmosphere_controller)
	if _has_simulation_epoch:
		weather_snapshot_reader.set("freshness_mode", "simulation_clock")
		weather_snapshot_reader.set_simulation_epoch_unix(_simulation_epoch_unix)
	make_audio()
	make_wildlife()
	collect_terrain_materials(self)
	# Terrain tiles own the ground_wetness uniform the atmosphere controller writes.
	for terrain_tile: Node in get_tree().get_nodes_in_group("terrain_tile"):
		if terrain_tile is MeshInstance3D:
			terrain_tile.add_to_group("weather_wetness")
	refresh_env_caches()
	cache_river_flow_defaults()
	apply_season()
	load_pool_shell_temperatures()
	apply_pool_temperatures()
	load_insect_bird_summary()
	# Optional Python-published sidecars (fixes-39); each loader is a no-op when the file is absent and the HUD reports available sources.
	_plume_field_summary = load_optional_sidecar("res://data/plume_field.json")
	_geochemistry_summary = load_optional_sidecar("res://data/geochemistry.json")
	_calibration_summary = load_optional_sidecar("res://data/calibration_summary.json")
	_census_summary = load_optional_sidecar("res://data/census.json")
	# Guild diagnostics for the field-notes block; ecosystem.json remains the actor source.
	_grazer_summary = load_optional_sidecar("res://data/grazer.json")
	_fish_summary = load_optional_sidecar("res://data/fish.json")
	refresh_pools_state()
	_groundwater_summary = load_optional_sidecar("res://data/groundwater_field.json")
	_overland_summary = load_optional_sidecar("res://data/overland_field.json")
	apply_snow_patch_mask()
	if ResourceLoader.exists("res://scripts/pool_overlay.gd"):
		add_child(load("res://scripts/pool_overlay.gd").new())
	build_scientific_overlays()
	atmosphere_controller.refresh_wetness_material_cache()
	make_interface()
	update_environment()
	if "--smoke-test" in OS.get_cmdline_user_args():
		run_smoke_test()
	if "--capture" in OS.get_cmdline_user_args() or "--capture-all" in OS.get_cmdline_user_args():
		capture_preview()

func make_ecosystem() -> Node:
	# Study scenes play Python-owned thermal replays.
	if not replay_path.is_empty() and ResourceLoader.exists("res://scripts/python_river_replay.gd"):
		var replay: Node = load("res://scripts/python_river_replay.gd").new()
		replay.set("replay_path", replay_path)
		return replay
	return Ecosystem.new()

func collect_foliage_materials(node: Node) -> void:
	if node is MeshInstance3D:
		for surface in node.mesh.get_surface_count():
			var mat: Material=node.mesh.surface_get_material(surface)
			if mat is ShaderMaterial and mat.shader.resource_path.ends_with("foliage.gdshader") and not mat in foliage_materials:
				foliage_materials.append(mat)
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
	# Season switch alters surfaces only: snow cover from season.json.
	if not FileAccess.file_exists("res://data/season.json"):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/season.json"))
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
	# When season.json carries per-patch snow_cover_fraction (fixes-39 item 4 phase 2), its mean becomes the shader cover gate; absence falls back to 1.0 so the pre-pass look is preserved.
	_snow_cover_fraction_mean = cover_sum / float(cover_count) if cover_count > 0 else 1.0
	var mask_path := "res://assets/textures/snow_map.png"
	for mat: ShaderMaterial in terrain_materials:
		mat.set_shader_parameter("snow_amount", _snow_amount_from_mean)
		mat.set_shader_parameter("snow_swe_mm", _snow_swe_mm_mean)
		mat.set_shader_parameter("snow_cover_fraction", _snow_cover_fraction_mean)
		if ResourceLoader.exists(mask_path):
			mat.set_shader_parameter("snow_mask", load(mask_path))
	print("season: snow_amount=%.2f snow_swe_mm=%.1f snow_cover_fraction=%.2f (cover_patches=%d) from %s." % [_snow_amount_from_mean, _snow_swe_mm_mean, _snow_cover_fraction_mean, cover_count, str(parsed.get("season", "unrecorded"))])

func cache_river_flow_defaults() -> void:
	# Record the baked flow_speed per river so runtime scaling has a reference.
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
	if not FileAccess.file_exists("res://data/pool_shells.json"):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/pool_shells.json"))
	if not parsed is Dictionary or not parsed.has("pool_shells"):
		return
	for shell: Dictionary in parsed["pool_shells"]:
		var name: String = str(shell.get("name", shell.get("id", "")))
		if name.is_empty():
			continue
		_pool_shell_temperatures[name] = float(shell.get("t_center_c", 0.0))

func apply_pool_temperatures() -> void:
	# pool_shells.json carries authored static temperatures; apply them per pool.
	if _pool_shell_temperatures.is_empty():
		return
	for node: Node in get_tree().get_nodes_in_group("thermal_surfaces"):
		var mi := node as MeshInstance3D
		if mi == null or mi.mesh == null:
			continue
		var feature: String = str(mi.get_meta("feature_name", ""))
		if feature.is_empty() or not _pool_shell_temperatures.has(feature):
			continue
		var mat := mi.mesh.surface_get_material(0) as ShaderMaterial
		if mat == null:
			continue
		mat.set_shader_parameter("temperature_c", _pool_shell_temperatures[feature])

func load_insect_bird_summary() -> void:
	if not FileAccess.file_exists("res://data/insect_bird.json"):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/insect_bird.json"))
	if parsed is Dictionary:
		_insect_bird_summary = parsed

func load_optional_sidecar(path: String) -> Dictionary:
	# Tolerant reader for Python-published sidecars (fixes-39); returns an empty dictionary when the file is missing, unreadable, or not a JSON object.
	if not FileAccess.file_exists(path):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if parsed is Dictionary:
		return parsed
	push_warning("Optional sidecar is not a JSON object; ignoring: " + path)
	return {}

func refresh_pools_state() -> void:
	# Per-step pools_state.json (fixes-39 item 2 phase 2); re-read on mtime change so a running build keeps the HUD current without per-frame I/O.
	var path := "res://data/pools_state.json"
	if not FileAccess.file_exists(path):
		return
	var mtime: int = FileAccess.get_modified_time(path)
	if mtime == _pools_state_mtime and not _pools_state_summary.is_empty():
		return
	_pools_state_mtime = mtime
	_pools_state_summary = load_optional_sidecar(path)
	# Apply any newly provided per-pool temperatures to thermal_surfaces.
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

func build_scientific_overlays() -> void:
	# Instantiate the shared overlay root (fixes-39 items 7, 8, 13) and hand it the published sidecars.
	if not ResourceLoader.exists("res://scripts/scientific_overlays.gd"):
		return
	var overlays_script: Script = load("res://scripts/scientific_overlays.gd")
	_overlays = overlays_script.new()
	_overlays.name = "ScientificOverlays"
	add_child(_overlays)
	_overlays.call("bind", self, _plume_field_summary, _geochemistry_summary, _overland_summary, _groundwater_summary)

func apply_snow_patch_mask() -> void:
	# Optional per-patch snow mask (fixes-39 item 4 phase 2); the fallback is the scalar snow_amount already written by apply_season.
	var mask_path := "res://data/snow_patch_mask.png"
	if not ResourceLoader.exists(mask_path):
		return
	var mask: Texture2D = load(mask_path)
	for mat: ShaderMaterial in terrain_materials:
		mat.set_shader_parameter("snow_mask", mask)
	print("snow_patch_mask applied from %s" % mask_path)

func make_environment() -> void:
	sun = DirectionalLight3D.new()
	sun.name = "AfternoonSun"
	sun.light_color = Color(1.0,.975,.92)
	sun.light_energy = .8
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 280.0
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.shadow_bias = .03
	sun.shadow_normal_bias = 1.2
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
	# data/ecosystem.json params.wildlife is the authoritative actor roster. data/grazer.json and data/fish.json are per-guild diagnostics derived from the same roster plus planner and refuge rationales that the simulation records but the actor never acts on at runtime. Mirroring either sidecar into make_wildlife would double-spawn each actor and introduce a second ground truth to maintain, so the field notes block cites them from format_sidecar_block when published.
	if not ResourceLoader.exists("res://scripts/wildlife_actor.gd"):
		return
	var script: Script = load("res://scripts/wildlife_actor.gd")
	for record: Dictionary in ecosystem.params.get("wildlife",[]):
		var actor: Node3D = script.new()
		actor.setup(record,height_field,ecosystem)
		add_child(actor)

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
	help_label=text_label("WASD  Walk    Shift  Brisk walk    Mouse  Look    M  Map    I  Field notes    K  Calibration    P  Plume    G  Geochemistry    U  Census  (on map)    J  Overland    L  Groundwater    Ctrl-S  Study mode    Esc  Menu",14)
	help_label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	help_label.position=Vector2(34,-48)
	ui.add_child(help_label)
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
	var rule := HSeparator.new()
	content.add_child(rule)
	content.add_child(text_label("STARTING PLACES",12,Color(.80,.76,.52)))
	for i in spec.anchors.size():
		var index: int = i
		content.add_child(make_button(spec.anchors[i].title,func(): go_to_anchor(index);resume()))
	content.add_child(text_label("F  Photo mode    F3  Fly for authoring    R  Return\nController: left stick walks, right stick looks.",12,Color(.70,.74,.66)))
	info_panel=PanelContainer.new()
	info_panel.position=Vector2(34,140)
	info_panel.custom_minimum_size=Vector2(480,420)
	info_panel.add_theme_stylebox_override("panel",panel_style(.94))
	info_panel.visible=false
	ui.add_child(info_panel)
	info_label=RichTextLabel.new()
	info_label.custom_minimum_size=Vector2(430,370)
	info_label.bbcode_enabled=true
	info_label.fit_content=true
	info_label.add_theme_font_size_override("normal_font_size",17)
	info_panel.add_child(info_label)
	var map_script: Script=load("res://scripts/map_view.gd")
	map_view=Control.new()
	map_view.set_script(map_script)
	map_view.world=self
	map_view.position=Vector2(34,140)
	map_view.size=Vector2(590,680)
	map_view.visible=false
	ui.add_child(map_view)
	# Hand the map view the census trees so the U toggle has data (fixes-39 item 10).
	if not _census_summary.is_empty():
		var census_doc: Variant = _census_summary.get("payload", _census_summary)
		if census_doc is Dictionary:
			var trees: Variant = census_doc.get("trees")
			if trees is Array:
				map_view.call("set_census", trees)
	# Calibration panel for fixes-39 item 12; data/calibration_summary.json drives the content.
	if ResourceLoader.exists("res://scripts/calibration_panel.gd"):
		_calibration_panel = Control.new()
		_calibration_panel.set_script(load("res://scripts/calibration_panel.gd"))
		_calibration_panel.position = Vector2(640, 140)
		_calibration_panel.size = Vector2(560, 480)
		_calibration_panel.visible = false
		ui.add_child(_calibration_panel)
		_calibration_panel.call("set_doc", _calibration_summary)

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
	player.enabled=true
	Input.mouse_mode=Input.MOUSE_MODE_CAPTURED

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		match event.physical_keycode:
			KEY_ESCAPE:
				menus_open=not menus_open
				menu.visible=menus_open
				player.enabled=not menus_open
				Input.mouse_mode=Input.MOUSE_MODE_VISIBLE if menus_open else Input.MOUSE_MODE_CAPTURED
			KEY_I:
				info_panel.visible=not info_panel.visible
				map_view.visible=false
			KEY_M:
				map_view.visible=not map_view.visible
				info_panel.visible=false
			KEY_F:
				hud_visible=not hud_visible
				overlay.visible=hud_visible
			KEY_F3:
				player.fly_mode=not player.fly_mode
			KEY_R:
				go_to_anchor(camera_anchor)
			KEY_T:
				ecosystem.clock_hour=fposmod(ecosystem.clock_hour+2.0,24.0)
				update_environment()
			KEY_C:
				toggle_replay()
			KEY_S:
				# Ctrl-S switches to the study scene when it exists.
				if Input.is_physical_key_pressed(KEY_CTRL) and ResourceLoader.exists("res://scenes/study.tscn"):
					get_tree().change_scene_to_file("res://scenes/study.tscn")
			KEY_K:
				# fixes-39 item 12: toggle the calibration page.
				if _calibration_panel != null:
					_calibration_panel.visible = not _calibration_panel.visible
			KEY_P:
				# fixes-39 item 7: toggle the plume field overlay.
				if _overlays != null:
					_overlays.call("toggle_plume")
			KEY_G:
				# fixes-39 item 8: toggle the geochemistry markers.
				if _overlays != null:
					_overlays.call("toggle_geochemistry")
			KEY_U:
				# fixes-39 item 10: toggle the census canopy overlay on the map (open the map if hidden).
				if map_view != null:
					map_view.census_visible = not map_view.census_visible
					map_view.visible = true
					info_panel.visible = false
					map_view.queue_redraw()
			KEY_J:
				# fixes-39 item 13: toggle the overland field overlay.
				if _overlays != null:
					_overlays.call("toggle_overland")
			KEY_L:
				# fixes-39 item 13: toggle the groundwater field overlay.
				if _overlays != null:
					_overlays.call("toggle_groundwater")

func toggle_replay() -> void:
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
	if ecosystem==null or status_label==null:
		return
	if _has_simulation_epoch and atmosphere_controller != null:
		# Simulation seconds come from ecosystem.elapsed; the ecosystem advances in step() under the day_rate pace.
		_simulation_epoch_unix = _simulation_start_epoch_unix + float(ecosystem.elapsed)
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
		status_label.text="%02d:%02d  ·  %d m elevation  ·  %.0f °C air%s%s" % [hour,minute,int(p.y+2200),ecosystem.air_c,"  ·  Authoring flight" if player.fly_mode else "","  ·  " + replay_run_name if not replay_run_name.is_empty() else ""]
		update_notes()
		if map_view != null and map_view.visible:
			map_view.queue_redraw()
		update_environment()
		refresh_env_caches()
		refresh_pools_state()

func update_environment() -> void:
	if atmosphere_controller == null or ecosystem == null:
		return
	# The simulation clock drives fallback solar geometry; a snapshot that supplies both solar angles keeps priority until the override is cleared.
	atmosphere_controller.set_simulation_time(
		ecosystem.clock_hour,
		int(spec.get("day_of_year", 196))
	)
	# Ecosystem wind remains the local wind source until a snapshot updates it; partial state dictionaries merge, so cloud and precipitation values from the reader are preserved.
	var local_weather: Dictionary = {
		"air_temperature_c": ecosystem.air_c,
		"wind_speed_mps": ecosystem.wind.length()
	}
	if ecosystem.wind.length_squared() > 0.0001:
		# Convert the world-space flow vector to meteorological-source bearing (direction from which the wind originates).
		local_weather["wind_direction_deg"] = fposmod(
			rad_to_deg(atan2(-ecosystem.wind.x, -ecosystem.wind.y)),
			360.0
		)
	atmosphere_controller.set_weather_state(local_weather)
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
		# Condensation model (mirrors yellowstone_python.microclimate): humidity and wind drive the plume.
		mat.set_shader_parameter("density",
				ecosystem.condensation_visibility(
					float(node.get_meta("surface_c",76.0))) * STEAM_DENSITY_SCALE)
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
	info_label.text="[color=#d6c88f][b]OBSERVING MIDWAY[/b][/color]\n\nThe blue centers are deep hot water. Microbial mats occupy cooler edges and runoff. Follow the drainage fingers toward the Firehole.\n\n[b]Environmental model[/b]\nNearby river reach: %.1f °C\nFlow: %.2f m³/s\nWind: %.1f m/s\nRiverbank insects: %s (activity %.2f)\nSnow: %s%s%s\n\nThe temperature and activity values are illustrative simulation states. Geometry follows USGS elevation and NPS mapping; water depth, plants, and wildlife are authored approximations.\n\n[I] Close notes    [T] Advance lighting by 2 h" % [reach.temperature_c,reach.flow_m3s,ecosystem.wind.length(),("hover" if float(bank.get("insect_activity",0.0))>0.035 else "inactive"),float(bank.get("insect_activity",0.0)),("see season sidecar" if FileAccess.file_exists("res://data/season.json") else "summer baseline"),biological_block,sidecar_block]

func format_sidecar_block() -> String:
	# Lists the optional Python-published sidecars (fixes-39) available in this run; an absent sidecar is omitted.
	var lines: Array = []
	if not _plume_field_summary.is_empty():
		lines.append("Plume field: %dx%d grid, Excelsior reach %.1f °C, bridge reach %.1f °C" % [int(_plume_field_summary.get("nx", 0)), int(_plume_field_summary.get("nz", 0)), float(_plume_field_summary.get("hot_source_c", 0.0)), float(_plume_field_summary.get("river_c", 0.0))])
	if not _geochemistry_summary.is_empty():
		var geo_cells: Variant = _geochemistry_summary.get("cells")
		var geo_count: int = 0
		var observed: int = 0
		if geo_cells is Array:
			geo_count = (geo_cells as Array).size()
			for row: Variant in geo_cells:
				if row is Dictionary and str(row.get("flag", "no_observation")) != "no_observation":
					observed += 1
		lines.append("Geochemistry: %d cells, %d with SiO2 observations" % [geo_count, observed])
	if not _calibration_summary.is_empty():
		var fit: Variant = _calibration_summary.get("reach_fit")
		if fit is Dictionary and fit.get("holdout_rmse_c") != null:
			lines.append("Calibration: reach holdout RMSE %.2f °C (%s)" % [float(fit["holdout_rmse_c"]), str(fit.get("status", "unrecorded"))])
		else:
			lines.append("Calibration: holdout RMSE unavailable")
	if not _census_summary.is_empty():
		# census.json is either the raw census or the exporter wrapper carrying it under payload.
		var census_doc: Variant = _census_summary.get("payload", _census_summary)
		var trees: Variant = census_doc.get("trees") if census_doc is Dictionary else null
		lines.append("Census: %d trees" % ((trees as Array).size() if trees is Array else 0))
	if not _pools_state_summary.is_empty():
		var pools: Variant = _pools_state_summary.get("pools")
		var count: int = (pools as Array).size() if pools is Array else 0
		lines.append("Pools live: %d" % count)
	if not _grazer_summary.is_empty():
		var grazers: Variant = _grazer_summary.get("wildlife")
		var g_count: int = (grazers as Array).size() if grazers is Array else 0
		lines.append("Grazer diagnostics: %d records (actor source: ecosystem.json)" % g_count)
	if not _fish_summary.is_empty():
		var fishes: Variant = _fish_summary.get("wildlife")
		var f_count: int = (fishes as Array).size() if fishes is Array else 0
		lines.append("Fish diagnostics: %d records (actor source: ecosystem.json)" % f_count)
	if not _groundwater_summary.is_empty():
		lines.append("Groundwater field: %s" % str(_groundwater_summary.get("status", "available")))
	if not _overland_summary.is_empty():
		lines.append("Overland field: %s" % str(_overland_summary.get("status", "available")))
	if lines.is_empty():
		return ""
	return "\n\n[b]Published sidecars[/b]\n" + "\n".join(lines)

func run_smoke_test() -> void:
	await get_tree().process_frame
	print("SMOKE scene=ready terrain=",get_node("AuthoredMidway/TerrainTiles").get_child_count()," routes=",spec.routes.size()," pools=",spec.pools.size())
	for i in spec.anchors.size():
		go_to_anchor(i)
		player.enabled=true
		for tick in 120:
			await get_tree().physics_frame
		print("SMOKE anchor=",spec.anchors[i].id," floor=",player.is_on_floor()," y=",player.position.y)
	print("SMOKE heat_budget_error=",ecosystem.heat_budget_error)
	report_multimesh_validation()
	get_tree().quit()

func report_multimesh_validation() -> void:
	# Optional surface of the last tools/validate_multimesh.gd report; the file lands after a headless validation run and is not required at runtime.
	var validation_path := "res://tests/multimesh_validation.json"
	if not FileAccess.file_exists(validation_path):
		print("SMOKE multimesh_validation=absent (run tools/validate_multimesh.gd to regenerate)")
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(validation_path))
	if not parsed is Dictionary:
		push_warning("multimesh_validation.json is not a JSON object; ignoring.")
		return
	var ok: bool = bool(parsed.get("ok", false))
	var failure_count: int = int(parsed.get("failure_count", 0))
	var expected_slots: int = int(parsed.get("expected_instance_slots", 0))
	var actual_slots: int = int(parsed.get("actual_instance_slots", 0))
	print("SMOKE multimesh_validation ok=", ok, " slots=", actual_slots, "/", expected_slots, " failures=", failure_count)
	if not ok:
		push_warning("multimesh_validation reports %d failures; see %s" % [failure_count, validation_path])

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
