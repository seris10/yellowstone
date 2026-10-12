extends Node3D
## Runtime assembles saved authored assets.
const Walker = preload("res://scripts/player.gd")
const HeightField = preload("res://scripts/height_field.gd")
const Ecosystem = preload("res://scripts/ecosystem.gd")
## Study scenes set this to a Python replay JSON (see scenes/study.tscn).
## Empty uses the live ecosystem.
@export_file("*.json") var replay_path: String = ""
## Study scenes set this to the comparison replay. C toggles the live run.
## Empty disables the toggle.
@export_file("*.json") var replay_path_alt: String = ""
var replay_run_name := ""
var player: CharacterBody3D
var ecosystem: Node
var height_field: RefCounted
var spec: Dictionary
var sun: DirectionalLight3D
var environment: Environment
var sky_material: ProceduralSkyMaterial
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

func _ready() -> void:
	# Cap frame rate: uncapped Compatibility renderer cooks laptops.
	Engine.max_fps = 60
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
	make_audio()
	make_wildlife()
	collect_terrain_materials(self)
	refresh_env_caches()
	apply_season()
	if ResourceLoader.exists("res://scripts/pool_overlay.gd"):
		add_child(load("res://scripts/pool_overlay.gd").new())
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
	var depth := 0.0
	for p: Dictionary in parsed["patches"]:
		depth = maxf(depth, float(p.get("snow_depth_m", 0.0)))
	var amount := clampf(depth / 0.3, 0.0, 1.0)
	var mask_path := "res://assets/textures/snow_map.png"
	for mat: ShaderMaterial in terrain_materials:
		mat.set_shader_parameter("snow_amount", amount)
		if ResourceLoader.exists(mask_path):
			mat.set_shader_parameter("snow_mask", load(mask_path))
	print("season: snow_amount=%.2f from %s." % [amount, str(parsed.get("season", "unrecorded"))])

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
	sky_material = ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color(.18,.37,.54)
	sky_material.sky_horizon_color = Color(.72,.80,.82)
	sky_material.ground_bottom_color = Color(.24,.25,.18)
	sky_material.ground_horizon_color = Color(.70,.77,.76)
	sky_material.sun_angle_max = 2.0
	sky_material.sun_curve = .12
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
	help_label=text_label("WASD  Walk    Shift  Brisk walk    Mouse  Look    M  Map    I  Field notes    Esc  Menu",14)
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
		map_view.queue_redraw()
		update_environment()

func update_environment() -> void:
	var hour: float=ecosystem.clock_hour if ecosystem else 16.2
	var elevation:=maxf(.04,sin((hour-6.0)*PI/12.0))
	sun.rotation_degrees=Vector3(-maxf(6.0,elevation*62.0),-62.0+(hour-16.0)*12.0,0)
	sun.light_energy=maxf(.015,elevation*.85)
	var daylight:=clampf((sin((hour-6.0)*PI/12.0)+.08)*2.5,0,1)
	sky_material.sky_top_color=Color(.008,.016,.034).lerp(Color(.18,.37,.54),daylight)
	sky_material.sky_horizon_color=Color(.035,.045,.065).lerp(Color(.72,.80,.82),daylight)
	environment.ambient_light_energy=lerpf(.035,.50,daylight)
	environment.fog_light_color=Color(.025,.04,.055).lerp(Color(.59,.70,.76),daylight)
	for mat: ShaderMaterial in foliage_materials:
		mat.set_shader_parameter("wind_vector",ecosystem.wind)
func refresh_env_caches() -> void:
	_steam_nodes.assign(get_tree().get_nodes_in_group("steam"))
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
					float(node.get_meta("surface_c",76.0))) * .40)
	for node in _river_nodes:
		if str(node.get_meta("river_name","")).to_upper()!="FIREHOLE RIVER":continue
		var mi := node as MeshInstance3D
		if mi == null or mi.mesh == null:continue
		var mat := mi.mesh.surface_get_material(0) as ShaderMaterial
		if mat == null:continue
		mat.set_shader_parameter("temperature_c",ecosystem.reach_at(float(node.get_meta("sample_z",0.0))).temperature_c)

func update_notes() -> void:
	if not info_panel.visible:
		return
	var reach: Dictionary=ecosystem.reach_at(player.position.z)
	var bank: Dictionary=ecosystem.patch("bridge_riparian")
	info_label.text="[color=#d6c88f][b]OBSERVING MIDWAY[/b][/color]\n\nThe blue centers are deep hot water. Microbial mats occupy cooler edges and runoff. Follow the drainage fingers toward the Firehole.\n\n[b]Environmental model[/b]\nNearby river reach: %.1f °C\nFlow: %.2f m³/s\nWind: %.1f m/s\nRiverbank insects: %s (activity %.2f)\nSnow: %s\n\nThe temperature and activity values are illustrative simulation states. Geometry follows USGS elevation and NPS mapping; water depth, plants, and wildlife are authored approximations.\n\n[I] Close notes    [T] Advance lighting by 2 h" % [reach.temperature_c,reach.flow_m3s,ecosystem.wind.length(),("hover" if float(bank.get("insect_activity",0.0))>0.035 else "inactive"),float(bank.get("insect_activity",0.0)),("see season sidecar" if FileAccess.file_exists("res://data/season.json") else "summer baseline")]

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
	get_tree().quit()

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
