class_name YellowstoneAtmosphereController
extends Node3D

## Yellowstone-facing atmosphere renderer for Godot 4.x.
##
## Responsibilities:
## - Render a Preetham physical sky and animate the sun from park-local solar time.
## - Draw a procedural cloud shell supported by the Compatibility renderer.
## - Render rain and snow using GPU particles whose intensity follows supplied weather.
## - Apply visibility-driven atmospheric fog and optional externally computed wetness.
##
## This script renders meteorology; it does not create the meteorological forecast.
## Feed it corrected station/grid data (or a climatology fallback) through
## set_weather_state(). Snow fraction should be computed by the weather model,
## ideally from wet-bulb temperature/humidity, not inferred here from 0 C alone.

const CLOUD_SHADER: Shader = preload("res://shaders/yellowstone_cloud_shell.gdshader")

@export_group("Solar geometry")
@export var latitude_deg: float = 44.60
@export var longitude_deg: float = -110.50
## Yellowstone civil time varies between UTC-7 and UTC-6. Set the offset that
## corresponds to the simulated date, or supply solar azimuth/elevation directly.
@export_range(-12.0, 14.0, 0.5) var utc_offset_hours: float = -6.0
@export_range(1, 366, 1) var default_day_of_year: int = 196

@export_group("Cloud shell")
@export_range(1000.0, 12000.0, 100.0) var cloud_radius_m: float = 5600.0
@export_range(100.0, 2500.0, 25.0) var default_cloud_base_agl_m: float = 1050.0
@export_range(100.0, 1800.0, 25.0) var default_cloud_thickness_m: float = 600.0
@export_range(0.0002, 0.008, 0.00005) var cloud_scale: float = 0.00125
@export_range(0.0, 1.0, 0.05) var cloud_detail: float = 0.68
@export_range(0.0, 1.0, 0.05) var cloud_opacity: float = 0.78
@export_range(0.0, 1.0, 0.05) var default_cloud_fraction: float = 0.28
@export_range(0.1, 2.5, 0.1) var cloud_drift_multiplier: float = 0.65

@export_group("Precipitation particles")
@export_range(100, 5000, 100) var rain_particle_count: int = 1800
@export_range(100, 5000, 100) var snow_particle_count: int = 1200
@export_range(5.0, 60.0, 1.0) var rain_fall_speed_mps: float = 23.0
@export_range(0.5, 12.0, 0.5) var snow_fall_speed_mps: float = 3.4
@export_range(5.0, 60.0, 1.0) var precipitation_radius_m: float = 28.0
@export_range(5.0, 40.0, 1.0) var emitter_height_m: float = 18.0
@export_range(0.1, 100.0, 0.5) var full_particle_rate_mm_h: float = 18.0

@export_group("Fog and environment")
@export_range(100.0, 50000.0, 100.0) var clear_visibility_m: float = 24000.0
@export_range(0.0, 1.0, 0.05) var default_relative_humidity: float = 0.55
@export_range(0.0, 1.0, 0.05) var default_cloud_ambient_dim: float = 0.48
@export var update_interval_seconds: float = 0.10

var _sun: DirectionalLight3D
var _environment: Environment
var _target: Node3D
var _physical_sky: PhysicalSkyMaterial
var _cloud_shell: MeshInstance3D
var _cloud_material: ShaderMaterial
var _rain: GPUParticles3D
var _snow: GPUParticles3D
var _rain_process: ParticleProcessMaterial
var _snow_process: ParticleProcessMaterial
var _rain_draw_material: StandardMaterial3D
var _snow_draw_material: StandardMaterial3D
var _configured: bool = false
var _solar_from_weather: bool = false
var _clock_hour: float = 16.2
var _day_of_year: int = 196
var _solar_azimuth_deg: float = 210.0
var _solar_elevation_deg: float = 30.0
var _update_elapsed: float = 0.0
var _cloud_offset: Vector2 = Vector2.ZERO
var _wetness_surfaces: Array[ShaderMaterial] = []

const WEATHER_DEFAULTS: Dictionary = {
	"air_temperature_c": 8.0,
	"dewpoint_c": 1.0,
	"relative_humidity": 0.55,
	"wind_speed_mps": 2.0,
	"wind_direction_deg": 270.0,
	"cloud_fraction": 0.28,
	"cloud_base_agl_m": 1050.0,
	"cloud_thickness_m": 600.0,
	"precipitation_rate_mm_h": 0.0,
	"snow_fraction": 0.0,
	"visibility_m": 24000.0,
	"ground_wetness_fraction": -1.0,
	"solar_azimuth_deg": -1.0,
	"solar_elevation_deg": -100.0,
}
var _weather: Dictionary = {}


## Call after the world creates its sun, Environment and player.
func configure(sun_node: DirectionalLight3D, environment_resource: Environment, follow_target: Node3D) -> void:
	if sun_node == null or environment_resource == null or follow_target == null:
		push_error("YellowstoneAtmosphereController.configure requires sun, Environment and a follow target.")
		return
	_sun = sun_node
	_environment = environment_resource
	_target = follow_target
	_weather = WEATHER_DEFAULTS.duplicate(true)
	_weather["cloud_fraction"] = default_cloud_fraction
	_weather["cloud_base_agl_m"] = default_cloud_base_agl_m
	_weather["cloud_thickness_m"] = default_cloud_thickness_m
	_weather["relative_humidity"] = default_relative_humidity
	_weather["visibility_m"] = clear_visibility_m
	_day_of_year = default_day_of_year
	_install_physical_sky()
	_create_cloud_shell()
	_create_precipitation()
	_cache_wetness_materials()
	_configured = true
	_update_solar_position()
	_apply_solar_position()
	_apply_weather_state()
	_update_atmosphere(0.0)


## Set one or more weather fields. Missing fields retain their previous value.
## Units: deg is degrees, m/s is metres/second, mm/h is precipitation rate.
## wind_direction_deg follows meteorological convention: direction wind comes FROM.
## snow_fraction is the fraction of precipitation rendered as snow, in [0, 1].
## solar_azimuth/elevation may be supplied by Python; both values are required.
func set_weather_state(state: Dictionary) -> void:
	var accepted: bool = false
	for key: String in WEATHER_DEFAULTS.keys():
		if state.has(key):
			_weather[key] = state[key]
			accepted = true
	if not accepted:
		return

	_weather["air_temperature_c"] = clampf(float(_weather["air_temperature_c"]), -70.0, 60.0)
	_weather["dewpoint_c"] = clampf(float(_weather["dewpoint_c"]), -80.0, 45.0)
	_weather["relative_humidity"] = clampf(float(_weather["relative_humidity"]), 0.0, 1.0)
	_weather["wind_speed_mps"] = clampf(float(_weather["wind_speed_mps"]), 0.0, 65.0)
	_weather["wind_direction_deg"] = fposmod(float(_weather["wind_direction_deg"]), 360.0)
	_weather["cloud_fraction"] = clampf(float(_weather["cloud_fraction"]), 0.0, 1.0)
	_weather["cloud_base_agl_m"] = clampf(float(_weather["cloud_base_agl_m"]), 100.0, 10000.0)
	_weather["cloud_thickness_m"] = clampf(float(_weather["cloud_thickness_m"]), 100.0, 5000.0)
	_weather["precipitation_rate_mm_h"] = clampf(float(_weather["precipitation_rate_mm_h"]), 0.0, 250.0)
	_weather["snow_fraction"] = clampf(float(_weather["snow_fraction"]), 0.0, 1.0)
	_weather["visibility_m"] = clampf(float(_weather["visibility_m"]), 100.0, 100000.0)
	_weather["ground_wetness_fraction"] = clampf(float(_weather["ground_wetness_fraction"]), -1.0, 1.0)

	var has_solar_azimuth: bool = state.has("solar_azimuth_deg")
	var has_solar_elevation: bool = state.has("solar_elevation_deg")
	if has_solar_azimuth or has_solar_elevation:
		_solar_from_weather = has_solar_azimuth and has_solar_elevation
	if _solar_from_weather:
		_solar_azimuth_deg = fposmod(float(state["solar_azimuth_deg"]), 360.0)
		_solar_elevation_deg = clampf(float(state["solar_elevation_deg"]), -18.0, 90.0)
		_apply_solar_position()
	_apply_weather_state()


## Animate the scene clock. Solar geometry uses Yellowstone coordinates, date and
## civil-time UTC offset. A weather snapshot that supplies solar angles takes priority.
func set_simulation_time(hour: float, day_of_year: int = -1, utc_offset: float = -99.0) -> void:
	_clock_hour = fposmod(hour, 24.0)
	if day_of_year >= 1 and day_of_year <= 366:
		_day_of_year = day_of_year
	if utc_offset >= -12.0 and utc_offset <= 14.0:
		utc_offset_hours = utc_offset
	if not _solar_from_weather:
		_update_solar_position()
		_apply_solar_position()


func _process(delta: float) -> void:
	if not _configured:
		return
	_update_elapsed += delta
	if _update_elapsed < maxf(0.025, update_interval_seconds):
		return
	var elapsed: float = _update_elapsed
	_update_elapsed = 0.0
	_update_atmosphere(elapsed)


func _install_physical_sky() -> void:
	if _environment.sky != null and _environment.sky.sky_material is PhysicalSkyMaterial:
		_physical_sky = _environment.sky.sky_material as PhysicalSkyMaterial
	else:
		_physical_sky = PhysicalSkyMaterial.new()
	_physical_sky.rayleigh_coefficient = 2.0
	_physical_sky.rayleigh_color = Color(0.30, 0.405, 0.60)
	_physical_sky.mie_coefficient = 0.0035
	_physical_sky.mie_color = Color(0.69, 0.73, 0.81)
	_physical_sky.mie_eccentricity = 0.80
	_physical_sky.turbidity = 2.6
	_physical_sky.sun_disk_scale = 1.0
	_physical_sky.use_debanding = true
	_physical_sky.ground_color = Color(0.12, 0.115, 0.085)
	_physical_sky.night_sky = _build_star_texture()
	var sky: Sky = Sky.new()
	sky.sky_material = _physical_sky
	_environment.background_mode = Environment.BG_SKY
	_environment.sky = sky
	_environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_environment.ambient_light_color = Color(0.53, 0.61, 0.70)
	_environment.ambient_light_energy = 0.42
	_environment.ambient_light_sky_contribution = 0.35
	_environment.fog_enabled = true
	_environment.fog_aerial_perspective = 0.12
	_environment.fog_sky_affect = 0.65
	_environment.fog_light_energy = 1.0
	_environment.volumetric_fog_enabled = false # Unsupported in Compatibility renderer.


func _build_star_texture() -> Texture2D:
	# Deterministic, low-cost star panorama for night transitions. These stars are
	# decorative, not a navigational astronomical catalogue.
	const WIDTH: int = 512
	const HEIGHT: int = 256
	var image: Image = Image.create(WIDTH, HEIGHT, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.0, 0.0, 0.0, 1.0))
	var rng: RandomNumberGenerator = RandomNumberGenerator.new()
	rng.seed = 445011
	for i: int in range(720):
		var x: int = rng.randi_range(0, WIDTH - 1)
		var y: int = rng.randi_range(4, HEIGHT - 5)
		var brightness: float = rng.randf_range(0.025, 0.16)
		var tint: Color = Color(0.68, 0.77, 1.0).lerp(Color(1.0, 0.88, 0.68), rng.randf())
		image.set_pixel(x, y, tint * brightness)
		if brightness > 0.145:
			if x > 0:
				image.set_pixel(x - 1, y, tint * brightness * 0.20)
			if x < WIDTH - 1:
				image.set_pixel(x + 1, y, tint * brightness * 0.20)
		var band_center: float = 0.50 + 0.12 * sin((float(x) / WIDTH) * TAU + 0.65)
		var band_distance: float = abs(float(y) / HEIGHT - band_center)
		if band_distance < 0.12 and rng.randf() < 0.15:
			var milky: Color = Color(0.045, 0.052, 0.085, 1.0) * (1.0 - band_distance / 0.12)
			image.set_pixel(x, y, image.get_pixel(x, y) + milky)
	return ImageTexture.create_from_image(image)


func _apply_weather_state() -> void:
	# Apply non-geometric settings immediately; cloud/particle placement is refreshed
	# in _update_atmosphere() on the next render tick.
	_update_environment_from_weather()
	_update_precipitation_amounts()


func _create_cloud_shell() -> void:
	var sphere: SphereMesh = SphereMesh.new()
	sphere.radius = 1.0
	sphere.height = 2.0
	sphere.radial_segments = 64
	sphere.rings = 32
	_cloud_shell = MeshInstance3D.new()
	_cloud_shell.name = "ProceduralCloudShell"
	_cloud_shell.mesh = sphere
	_cloud_shell.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_cloud_shell.extra_cull_margin = 16.0
	_cloud_material = ShaderMaterial.new()
	_cloud_material.shader = CLOUD_SHADER
	_cloud_material.set_shader_parameter("cloud_scale", cloud_scale)
	_cloud_material.set_shader_parameter("cloud_detail", cloud_detail)
	_cloud_material.set_shader_parameter("cloud_opacity", cloud_opacity)
	_cloud_material.set_shader_parameter("cloud_cover", default_cloud_fraction)
	_cloud_shell.material_override = _cloud_material
	add_child(_cloud_shell)


func _create_precipitation() -> void:
	_rain_process = _make_particle_process(false)
	_snow_process = _make_particle_process(true)
	_rain_draw_material = _make_particle_draw_material(Color(0.70, 0.82, 0.94, 0.58))
	_snow_draw_material = _make_particle_draw_material(Color(0.94, 0.97, 1.0, 0.88))
	_rain = _make_particle_emitter("RainParticles", rain_particle_count, 1.25, _rain_process, _rain_draw_material, Vector2(0.018, 0.43))
	_snow = _make_particle_emitter("SnowParticles", snow_particle_count, 4.2, _snow_process, _snow_draw_material, Vector2(0.055, 0.055))
	add_child(_rain)
	add_child(_snow)
	_rain.emitting = false
	_snow.emitting = false


func _make_particle_process(is_snow: bool) -> ParticleProcessMaterial:
	var process: ParticleProcessMaterial = ParticleProcessMaterial.new()
	process.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	process.emission_box_extents = Vector3(precipitation_radius_m, 6.0, precipitation_radius_m)
	process.direction = Vector3(0.0, -1.0, 0.0)
	process.spread = 8.0 if not is_snow else 24.0
	process.gravity = Vector3(0.0, -9.8 if not is_snow else -0.45, 0.0)
	process.initial_velocity_min = 16.0 if not is_snow else 1.2
	process.initial_velocity_max = rain_fall_speed_mps if not is_snow else snow_fall_speed_mps
	process.angular_velocity_min = -0.7 if is_snow else 0.0
	process.angular_velocity_max = 0.7 if is_snow else 0.0
	process.scale_min = 0.7 if not is_snow else 0.65
	process.scale_max = 1.3 if not is_snow else 1.4
	process.damping_min = 0.0
	process.damping_max = 0.0 if not is_snow else 0.6
	return process


func _make_particle_draw_material(color: Color) -> StandardMaterial3D:
	var material: StandardMaterial3D = StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.albedo_color = color
	material.no_depth_test = false
	return material


func _make_particle_emitter(emitter_name: String, amount: int, lifetime: float, process: ParticleProcessMaterial, draw_material: StandardMaterial3D, quad_size: Vector2) -> GPUParticles3D:
	var emitter: GPUParticles3D = GPUParticles3D.new()
	emitter.name = emitter_name
	emitter.amount = amount
	emitter.lifetime = lifetime
	emitter.explosiveness = 0.0
	emitter.randomness = 0.25
	emitter.local_coords = false
	emitter.fixed_fps = 30
	emitter.interpolate = true
	emitter.process_material = process
	emitter.visibility_aabb = AABB(Vector3(-precipitation_radius_m - 12.0, -36.0, -precipitation_radius_m - 12.0), Vector3((precipitation_radius_m + 12.0) * 2.0, 76.0, (precipitation_radius_m + 12.0) * 2.0))
	var quad: QuadMesh = QuadMesh.new()
	quad.size = quad_size
	quad.material = draw_material
	emitter.draw_pass_1 = quad
	return emitter


func _cache_wetness_materials() -> void:
	_wetness_surfaces.clear()
	for node: Node in get_tree().get_nodes_in_group("weather_wetness"):
		if node is MeshInstance3D:
			var mesh_instance: MeshInstance3D = node as MeshInstance3D
			if mesh_instance.mesh == null:
				continue
			for surface: int in range(mesh_instance.mesh.get_surface_count()):
				var material: Material = mesh_instance.get_active_material(surface)
				if material is ShaderMaterial and not _wetness_surfaces.has(material):
					_wetness_surfaces.append(material as ShaderMaterial)


func _update_atmosphere(delta: float) -> void:
	if _target == null:
		return
	var player_position: Vector3 = _target.global_position
	var cloud_base: float = float(_weather["cloud_base_agl_m"])
	var cloud_thickness: float = float(_weather["cloud_thickness_m"])
	_cloud_shell.global_position = Vector3(player_position.x, player_position.y + cloud_base + cloud_thickness * 0.5, player_position.z)
	_cloud_shell.scale = Vector3(cloud_radius_m, cloud_thickness * 0.5, cloud_radius_m)

	var wind_speed: float = float(_weather["wind_speed_mps"])
	var wind_toward: Vector3 = _meteorological_wind_toward(float(_weather["wind_direction_deg"]))
	var wind_xz: Vector2 = Vector2(wind_toward.x, wind_toward.z) * wind_speed
	_cloud_offset += wind_xz * delta * cloud_drift_multiplier * cloud_scale
	_cloud_material.set_shader_parameter("cloud_offset", _cloud_offset)
	_cloud_material.set_shader_parameter("cloud_center", _cloud_shell.global_position)
	_cloud_material.set_shader_parameter("cloud_cover", float(_weather["cloud_fraction"]))
	_cloud_material.set_shader_parameter("cloud_scale", cloud_scale)
	_cloud_material.set_shader_parameter("cloud_detail", cloud_detail)
	_cloud_material.set_shader_parameter("cloud_opacity", cloud_opacity)
	_cloud_material.set_shader_parameter("sun_direction", _sun_direction_vector())
	_cloud_material.set_shader_parameter("sun_tint", Vector3(_sun.light_color.r, _sun.light_color.g, _sun.light_color.b))
	_cloud_material.set_shader_parameter("daylight", _daylight_factor())
	_cloud_shell.visible = float(_weather["cloud_fraction"]) > 0.015

	_rain.global_position = player_position + Vector3(0.0, emitter_height_m, 0.0)
	_snow.global_position = player_position + Vector3(0.0, emitter_height_m, 0.0)
	_update_particle_wind(_rain_process, wind_toward, wind_speed, false)
	_update_particle_wind(_snow_process, wind_toward, wind_speed, true)
	_update_precipitation_amounts()
	_update_environment_from_weather()
	_update_wetness()


func _update_particle_wind(process: ParticleProcessMaterial, wind_toward: Vector3, wind_speed: float, is_snow: bool) -> void:
	var wind_factor: float = 0.42 if not is_snow else 0.78
	process.gravity = Vector3(wind_toward.x * wind_speed * wind_factor, -9.8 if not is_snow else -0.45, wind_toward.z * wind_speed * wind_factor)
	if is_snow:
		process.direction = Vector3(wind_toward.x * 0.16, -1.0, wind_toward.z * 0.16).normalized()
	else:
		process.direction = Vector3(wind_toward.x * 0.09, -1.0, wind_toward.z * 0.09).normalized()
	process.initial_velocity_max = rain_fall_speed_mps if not is_snow else snow_fall_speed_mps


func _update_precipitation_amounts() -> void:
	var rate: float = float(_weather["precipitation_rate_mm_h"])
	var snow_fraction: float = float(_weather["snow_fraction"])
	var strength: float = 0.0
	if rate > 0.01:
		strength = clampf(sqrt(rate / maxf(full_particle_rate_mm_h, 0.1)), 0.045, 1.0)
	var rain_ratio: float = strength * (1.0 - snow_fraction)
	var snow_ratio: float = strength * snow_fraction
	_rain.amount_ratio = rain_ratio
	_snow.amount_ratio = snow_ratio
	_rain.emitting = rain_ratio > 0.005
	_snow.emitting = snow_ratio > 0.005


func _update_environment_from_weather() -> void:
	var humidity: float = float(_weather["relative_humidity"])
	var visibility: float = float(_weather["visibility_m"])
	var cloud_fraction: float = float(_weather["cloud_fraction"])
	var haze: float = 1.0 - clampf((visibility - 1000.0) / 29000.0, 0.0, 1.0)
	_physical_sky.turbidity = clampf(2.2 + haze * 5.5 + maxf(0.0, humidity - 0.7) * 1.6, 2.0, 10.0)
	_physical_sky.mie_coefficient = lerpf(0.0025, 0.012, haze)
	_physical_sky.energy_multiplier = lerpf(0.78, 1.0, _daylight_factor())

	var daylight: float = _daylight_factor()
	var cloud_dim: float = cloud_fraction * default_cloud_ambient_dim
	_environment.ambient_light_color = Color(0.53, 0.61, 0.70).lerp(Color(0.68, 0.70, 0.72), haze * 0.55)
	_environment.ambient_light_energy = lerpf(0.045, 0.48, daylight) * (1.0 - cloud_dim * 0.62)
	_environment.fog_light_color = Color(0.50, 0.59, 0.68).lerp(Color(0.70, 0.72, 0.72), haze * 0.6)
	_environment.fog_density = lerpf(0.000035, 0.0011, pow(haze, 1.55))
	_environment.fog_aerial_perspective = lerpf(0.08, 0.30, haze)
	_environment.fog_sky_affect = lerpf(0.55, 0.88, haze)

	var sun_angle: float = _solar_elevation_deg
	var horizon_factor: float = 1.0 - smoothstep(4.0, 28.0, maxf(0.0, sun_angle))
	var warm_horizon: Color = Color(1.0, 0.66, 0.43)
	var daylight_tint: Color = warm_horizon.lerp(Color(1.0, 0.96, 0.87), 1.0 - horizon_factor)
	_sun.light_color = daylight_tint.lerp(Color(0.62, 0.70, 0.82), cloud_fraction * 0.28)
	_sun.light_energy = 0.92 * daylight * (1.0 - cloud_fraction * 0.52)


func _update_wetness() -> void:
	var wetness: float = float(_weather["ground_wetness_fraction"])
	if wetness < 0.0:
		return # Hydrology should own this value; don't invent soil wetness from weather alone.
	for material: ShaderMaterial in _wetness_surfaces:
		if material.shader != null and _shader_has_parameter(material.shader, &"ground_wetness"):
			material.set_shader_parameter("ground_wetness", wetness)


func _shader_has_parameter(shader: Shader, parameter_name: StringName) -> bool:
	for property: Dictionary in shader.get_shader_uniform_list():
		if StringName(property.get("name", "")) == parameter_name:
			return true
	return false


func _meteorological_wind_toward(direction_from_deg: float) -> Vector3:
	# World axes: +X east and +Z south. Meteorological direction states where wind
	# comes FROM, so the rendered vector points 180 degrees opposite.
	var angle: float = deg_to_rad(direction_from_deg + 180.0)
	return Vector3(sin(angle), 0.0, cos(angle)).normalized()


func _daylight_factor() -> float:
	return smoothstep(-7.0, 8.0, _solar_elevation_deg)


func _sun_direction_vector() -> Vector3:
	var azimuth: float = deg_to_rad(_solar_azimuth_deg)
	var elevation: float = deg_to_rad(_solar_elevation_deg)
	return Vector3(sin(azimuth) * cos(elevation), sin(elevation), cos(azimuth) * cos(elevation)).normalized()


func _update_solar_position() -> void:
	# NOAA-style fractional-year approximation for solar declination/equation of time.
	# For production real-time mode, supplying solar angles from the Python ingest
	# pipeline (e.g. pvlib) avoids ambiguity in timestamp/time-zone handling.
	var gamma: float = TAU / 365.0 * (float(_day_of_year) - 1.0 + (_clock_hour - 12.0) / 24.0)
	var equation_of_time: float = 229.18 * (0.000075 + 0.001868 * cos(gamma) - 0.032077 * sin(gamma) - 0.014615 * cos(2.0 * gamma) - 0.040849 * sin(2.0 * gamma))
	var declination: float = 0.006918 - 0.399912 * cos(gamma) + 0.070257 * sin(gamma) - 0.006758 * cos(2.0 * gamma) + 0.000907 * sin(2.0 * gamma) - 0.002697 * cos(3.0 * gamma) + 0.00148 * sin(3.0 * gamma)
	var time_offset: float = equation_of_time + 4.0 * longitude_deg - 60.0 * utc_offset_hours
	var solar_minutes: float = fposmod(_clock_hour * 60.0 + time_offset, 1440.0)
	var hour_angle: float = deg_to_rad(solar_minutes / 4.0 - 180.0)
	var latitude: float = deg_to_rad(latitude_deg)
	var cosine_zenith: float = clampf(sin(latitude) * sin(declination) + cos(latitude) * cos(declination) * cos(hour_angle), -1.0, 1.0)
	_solar_elevation_deg = 90.0 - rad_to_deg(acos(cosine_zenith))
	var azimuth: float = atan2(sin(hour_angle), cos(hour_angle) * sin(latitude) - tan(declination) * cos(latitude))
	_solar_azimuth_deg = fposmod(rad_to_deg(azimuth) + 180.0, 360.0)


func _apply_solar_position() -> void:
	if _sun == null:
		return
	# DirectionalLight3D local -Z points along light rays; the negative X rotation
	# makes rays descend when the sun is above the horizon.
	_sun.rotation_degrees = Vector3(-_solar_elevation_deg, _solar_azimuth_deg, 0.0)
	_sun.shadow_enabled = true
	_sun.directional_shadow_max_distance = 280.0


func refresh_wetness_material_cache() -> void:
	## Call after generated terrain tiles or materials have been added to the scene.
	_cache_wetness_materials()


func get_render_state() -> Dictionary:
	## Useful for HUD/debug capture. These values are render state, not validation metrics.
	return {
		"solar_azimuth_deg": _solar_azimuth_deg,
		"solar_elevation_deg": _solar_elevation_deg,
		"daylight_factor": _daylight_factor(),
		"cloud_fraction": float(_weather["cloud_fraction"]),
		"precipitation_rate_mm_h": float(_weather["precipitation_rate_mm_h"]),
		"snow_fraction": float(_weather["snow_fraction"]),
		"visibility_m": float(_weather["visibility_m"]),
	}
