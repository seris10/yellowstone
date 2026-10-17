class_name YellowstoneAtmosphereController
extends Node3D

## Weather-driven sky, clouds, precipitation, fog, and surface rendering.

## Weather snapshots supply meteorology and snow fraction.

const CLOUD_SHADER: Shader = preload("res://shaders/yellowstone_cloud_shell.gdshader")
const OPTICS = preload("res://scripts/atmosphere_optics.gd")
const RAINBOW_SHADER: Shader = preload("res://shaders/rainbow.gdshader")

@export_group("Solar geometry")
@export var latitude_deg: float = 44.60
@export var longitude_deg: float = -110.50
@export_range(1, 366, 1) var default_day_of_year: int = 196

@export_group("Simulation time")
## Set the date's UTC offset (-7 or -6) or supply solar angles.
@export_range(-12.0, 14.0, 0.5) var simulation_utc_offset_hours: float = -6.0
@export var use_weather_solar_override: bool = true
## Interpolate continuous weather fields toward the accepted snapshot.
@export var smooth_weather_transitions: bool = true
@export_range(0.0, 300.0, 1.0) var weather_transition_seconds: float = 20.0
var time_scale: float = 1.0
var _visual_weight: float = 1.0

@export_group("Cloud shell")
@export_range(1000.0, 12000.0, 100.0) var cloud_radius_m: float = 5600.0
@export_range(100.0, 2500.0, 25.0) var default_cloud_base_agl_m: float = 1050.0
@export_range(100.0, 1800.0, 25.0) var default_cloud_thickness_m: float = 600.0
@export_range(0.0002, 0.008, 0.00005) var cloud_scale: float = 0.00125
@export_range(0.0, 1.0, 0.05) var cloud_detail: float = 0.68
@export_range(0.0, 1.0, 0.05) var cloud_opacity: float = 0.78
@export_range(0.0, 1.0, 0.05) var default_cloud_fraction: float = 0.16
@export_range(0.1, 2.5, 0.1) var cloud_drift_multiplier: float = 0.65
## Scales cloud optical depth independently of coverage.
@export_range(0.0, 2.0, 0.05) var cloud_density_scale: float = 1.0
@export_range(0.02, 0.5, 0.01) var cloud_vertical_edge_softness: float = 0.18
## Treat cloud_base_agl_m as a world altitude; otherwise it is a height above the follow target.
@export var cloud_world_altitude_mode: bool = false

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

@export_group("Star sky")
## Star fields: right_ascension_hours, declination_deg, visual_magnitude, b_minus_v.
@export_file("*.json","*.bin") var star_catalog_path: String = "res://data/stars.json"
@export_range(2.5, 9.5, 0.1) var star_limiting_magnitude: float = 6.3
## Rebuild the star panorama after this many simulated seconds.
@export_range(60.0, 86400.0, 60.0) var star_rebuild_interval_seconds: float = 900.0

var _sun: DirectionalLight3D
var _environment: Environment
var _target: Node3D
var _physical_sky: ShaderMaterial
var _cloud_shell: MeshInstance3D
var _cloud_material: ShaderMaterial
var _rainbow: MeshInstance3D
var _rainbow_material: ShaderMaterial
var _rain_curtain = OPTICS.new()
var _rainbow_direct_transmission: float = 0.0
var _sky_uniforms: Dictionary = {}
var _rain: GPUParticles3D
var _snow: GPUParticles3D
var _rain_process: ParticleProcessMaterial
var _snow_process: ParticleProcessMaterial
var _rain_draw_material: StandardMaterial3D
var _snow_draw_material: StandardMaterial3D
var _configured: bool = false
var _clock_hour: float = 16.2
var _day_of_year: int = 196
var _solar_azimuth_deg: float = 210.0
var _solar_elevation_deg: float = 30.0
var _simulation_epoch_unix: float = 0.0
var _has_simulation_timestamp: bool = false
var _solar_override_active: bool = false
var _solar_override_azimuth_deg: float = 0.0
var _solar_override_elevation_deg: float = 0.0
var _weather_target: Dictionary = {}
var _weather_initialized: bool = false
var _update_elapsed: float = 0.0
var _cloud_offset: Vector2 = Vector2.ZERO
var _external_elapsed_s: float = NAN
var _pending_physical_seconds: float = 0.0
var _wetness_surfaces: Array[ShaderMaterial] = []
var _star_rebuild_epoch_unix: float = 0.0
var _star_catalog_loaded: bool = false
var _terrain_state: Dictionary = {
	"snow_cover_fraction": -1.0,
	"snow_water_equivalent_mm": -1.0,
	"puddle_fraction": -1.0,
	"soil_temperature_c": -273.15,
	"ground_wetness_fraction": -1.0,
	"cloud_shadow_fraction": -1.0,
	"steam_intensity": -1.0,
	"insect_activity": -1.0,
}

const WEATHER_DEFAULTS: Dictionary = {
	"air_temperature_c": 8.0,
	"dewpoint_c": 1.0,
	"relative_humidity": 0.55,
	"wind_speed_mps": 2.0,
	"wind_direction_deg": 270.0,
	"cloud_fraction": 0.16,
	"cloud_base_agl_m": 1050.0,
	"cloud_thickness_m": 600.0,
	"precipitation_rate_mm_h": 0.0,
	"snow_fraction": 0.0,
	"visibility_m": 24000.0,
	"ground_wetness_fraction": -1.0,
	"solar_azimuth_deg": -1.0,
	"solar_elevation_deg": -100.0,
}

## Visual weather fields use the configured transition time constant.
const EASED_VISUAL_PROPERTIES: Array = [
	{"field": "cloud_fraction", "time_constant": "weather_transition_seconds"},
	{"field": "cloud_base_agl_m", "time_constant": "weather_transition_seconds"},
	{"field": "cloud_thickness_m", "time_constant": "weather_transition_seconds"},
	{"field": "precipitation_rate_mm_h", "time_constant": "weather_transition_seconds"},
	{"field": "visibility_m", "time_constant": "weather_transition_seconds"},
	{"field": "fog_density", "time_constant": "weather_transition_seconds"},
	{"field": "rain_amount_ratio", "time_constant": "weather_transition_seconds"},
	{"field": "snow_amount_ratio", "time_constant": "weather_transition_seconds"},
	{"field": "light_color", "time_constant": "weather_transition_seconds"},
]
const SMOOTHED_WEATHER_FIELDS: Array[String] = ["cloud_fraction", "cloud_base_agl_m", "cloud_thickness_m", "precipitation_rate_mm_h", "visibility_m"]

var _weather: Dictionary = {}


## Bind the world's sun, environment, and follow target.
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
	_weather_target = _weather.duplicate(true)
	_weather_initialized = true
	_day_of_year = default_day_of_year
	_solar_override_active = false
	_install_physical_sky()
	_star_rebuild_epoch_unix = _simulation_epoch_unix
	_create_cloud_shell()
	_create_rainbow()
	_create_precipitation()
	_cache_wetness_materials()
	_configured = true
	if _has_simulation_timestamp:
		_update_solar_position_from_timestamp(_simulation_epoch_unix)
	else:
		_update_solar_position()
	_apply_solar_position()
	_apply_weather_state_immediate()
	_update_atmosphere(0.0)


## Set simulation time in Unix seconds.
func set_simulation_timestamp(epoch_unix: float, utc_offset_hours: float = -99.0) -> void:
	if not is_finite(epoch_unix):
		push_warning("Simulation timestamp must be finite.")
		return
	_simulation_epoch_unix = float(epoch_unix)
	_has_simulation_timestamp = true
	if utc_offset_hours >= -12.0 and utc_offset_hours <= 14.0:
		simulation_utc_offset_hours = utc_offset_hours
	if not _solar_override_active:
		_update_solar_position_from_timestamp(_simulation_epoch_unix)
		_apply_solar_position()


## Bind a new clock origin and clear unavailable transient history.
func reset_simulation_elapsed(elapsed_s: float) -> void:
	if not is_finite(elapsed_s):
		push_warning("Simulation elapsed time must be finite.")
		return
	_external_elapsed_s = elapsed_s
	_pending_physical_seconds = 0.0
	_rain_curtain = OPTICS.new()
	_cloud_offset = Vector2.ZERO
	if _rainbow != null:
		_rainbow.visible = false


## Bind history to accepted elapsed time and reset it after backward seeks.
func set_simulation_elapsed(elapsed_s: float, reset_on_rewind: bool = true) -> void:
	if not is_finite(elapsed_s):
		push_warning("Simulation elapsed time must be finite.")
		return
	if is_finite(_external_elapsed_s):
		if elapsed_s < _external_elapsed_s - 0.000001:
			if not reset_on_rewind:
				return
			reset_simulation_elapsed(elapsed_s)
			return
		else:
			_pending_physical_seconds += maxf(0.0, elapsed_s - _external_elapsed_s)
	_external_elapsed_s = elapsed_s


func _consume_physical_seconds(delta: float) -> float:
	if not is_finite(_external_elapsed_s):
		return maxf(0.0, delta) * maxf(time_scale, 0.0)
	var seconds: float = _pending_physical_seconds
	_pending_physical_seconds = 0.0
	return seconds


## Resume solar geometry from clock hour and day of year.
func clear_simulation_timestamp() -> void:
	_has_simulation_timestamp = false


## Set local simulation time; weather-provided solar angles take priority.
func set_simulation_time(hour: float, day_of_year: int = -1, utc_offset: float = -99.0) -> void:
	if not is_finite(hour):
		push_warning("Simulation hour must be finite.")
		return
	_clock_hour = fposmod(hour, 24.0)
	if day_of_year >= 1 and day_of_year <= 366:
		_day_of_year = day_of_year
	if utc_offset >= -12.0 and utc_offset <= 14.0:
		simulation_utc_offset_hours = utc_offset
	_solar_override_active = false
	if not _has_simulation_timestamp:
		_update_solar_position()
		_apply_solar_position()


## Update supplied weather fields; retain omitted values and source wind bearings.
func set_weather_state(state: Dictionary) -> void:
	if not _weather_initialized:
		_weather = WEATHER_DEFAULTS.duplicate(true)
		_weather_target = _weather.duplicate(true)
		_weather_initialized = true

	var accepted: bool = false
	for key: String in WEATHER_DEFAULTS.keys():
		if not state.has(key):
			continue
		var value: Variant = state[key]
		if not _is_finite_number(value):
			push_warning("Rejected non-finite weather field '%s'." % key)
			continue
		_weather_target[key] = value
		accepted = true

	var has_solar: bool = state.has("solar_azimuth_deg") or state.has("solar_elevation_deg")
	var terrain_variant: Variant = state.get("terrain", null)
	var terrain_present: bool = terrain_variant is Dictionary
	if not accepted and not has_solar and not terrain_present:
		return

	_validate_and_clamp_weather(_weather_target)
	for key: String in WEATHER_DEFAULTS:
		if key not in SMOOTHED_WEATHER_FIELDS:
			_weather[key] = _weather_target[key]
	_update_solar_override(state)
	if terrain_present:
		_apply_terrain_state(terrain_variant as Dictionary)
	_apply_weather_state()


## Drop a weather solar override and return to simulated solar geometry.
func clear_weather_solar_override() -> void:
	_solar_override_active = false
	if _has_simulation_timestamp:
		_update_solar_position_from_timestamp(_simulation_epoch_unix)
	else:
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
	_sky_uniforms.clear()
	_physical_sky = ShaderMaterial.new()
	_physical_sky.shader = load("res://shaders/physical_daylight.gdshader")
	_physical_sky.set_shader_parameter("night_sky", _build_star_texture())
	var sky: Sky = Sky.new()
	sky.sky_material = _physical_sky
	_environment.background_mode = Environment.BG_SKY
	_environment.sky = sky
	# A color ambient source keeps weather-driven dimming under renderer control.
	_environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_environment.ambient_light_color = Color(0.53, 0.61, 0.70)
	_environment.ambient_light_energy = 0.42
	_environment.ambient_light_sky_contribution = 0.35
	_environment.fog_enabled = true
	_environment.fog_aerial_perspective = 0.12
	_environment.fog_sky_affect = 0.0
	_environment.fog_light_energy = 1.0
	_environment.volumetric_fog_enabled = false # Forward+ feature.


func _build_star_texture() -> Texture2D:
	# Project catalog RA/Dec to altitude/azimuth; use a procedural sky if absent.
	var catalog: Array = _load_star_catalog(star_catalog_path)
	if catalog.is_empty():
		_star_catalog_loaded = false
		return _build_painted_panorama_fallback()
	_star_catalog_loaded = true
	return _build_catalog_star_texture(catalog)


## Rebuild the star panorama for the current simulation epoch.
func rebuild_star_sky() -> void:
	if _physical_sky == null:
		return
	_physical_sky.set_shader_parameter("night_sky", _build_star_texture())
	_star_rebuild_epoch_unix = _simulation_epoch_unix


func star_catalog_loaded() -> bool:
	return _star_catalog_loaded


func _load_star_catalog(path: String) -> Array:
	# Accept a star list or a {stars: [...]} catalog.
	if path.is_empty() or not FileAccess.file_exists(path):
		return []
	var text: String = FileAccess.get_file_as_string(path)
	if text.is_empty():
		return []
	var parsed: Variant = JSON.parse_string(text)
	var rows: Array = []
	if parsed is Array:
		rows = parsed
	elif parsed is Dictionary and (parsed as Dictionary).has("stars"):
		var stars_value: Variant = (parsed as Dictionary)["stars"]
		if stars_value is Array:
			rows = stars_value
	var out: Array = []
	for row_variant in rows:
		if not (row_variant is Dictionary):
			continue
		var row: Dictionary = row_variant
		if not row.has("right_ascension_hours") or not row.has("declination_deg") or not row.has("visual_magnitude"):
			continue
		var record: Dictionary = {
			"ra_hours": float(row["right_ascension_hours"]),
			"dec_deg": float(row["declination_deg"]),
			"magnitude": float(row["visual_magnitude"]),
			"b_minus_v": float(row.get("b_minus_v", 0.65)),
		}
		out.append(record)
	return out


func _build_catalog_star_texture(catalog: Array) -> Texture2D:
	const WIDTH: int = 1024
	const HEIGHT: int = 512
	var image: Image = Image.create(WIDTH, HEIGHT, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.0, 0.0, 0.0, 1.0))
	var lst_hours: float = _local_sidereal_time_hours(_simulation_epoch_unix, longitude_deg)
	var latitude_rad: float = deg_to_rad(latitude_deg)
	# Normalize magnitude flux as 10^(-0.4 * (m - 1)), with magnitude 1 near 0.9.
	var reference_magnitude: float = 1.0
	var brightest_intensity: float = 0.92
	var limit: float = star_limiting_magnitude
	# Build the Milky Way from unresolved equatorial flux bins.
	const BAND_WIDTH: int = 128
	const BAND_HEIGHT: int = 64
	var band_flux: PackedFloat32Array = PackedFloat32Array()
	band_flux.resize(BAND_WIDTH * BAND_HEIGHT)
	band_flux.fill(0.0)
	for star_variant in catalog:
		var star: Dictionary = star_variant
		var magnitude: float = float(star["magnitude"])
		var ra_hours: float = fposmod(float(star["ra_hours"]), 24.0)
		var dec_deg: float = clampf(float(star["dec_deg"]), -90.0, 90.0)
		var hour_angle_rad: float = deg_to_rad((lst_hours - ra_hours) * 15.0)
		var dec_rad: float = deg_to_rad(dec_deg)
		var sin_alt: float = sin(dec_rad) * sin(latitude_rad) + cos(dec_rad) * cos(latitude_rad) * cos(hour_angle_rad)
		sin_alt = clampf(sin_alt, -1.0, 1.0)
		var alt_rad: float = asin(sin_alt)
		var az_rad: float = atan2(sin(hour_angle_rad), cos(hour_angle_rad) * sin(latitude_rad) - tan(dec_rad) * cos(latitude_rad))
		var az_deg: float = fposmod(rad_to_deg(az_rad) + 180.0, 360.0)
		var airmass: float = 1.0
		if alt_rad > deg_to_rad(2.0):
			airmass = 1.0 / sin(alt_rad)
		else:
			airmass = 25.0
		var extinction_mag: float = 0.20 * (airmass - 1.0)
		var observed_mag: float = magnitude + extinction_mag
		# Paint resolved stars and bin fainter flux.
		if observed_mag <= limit and alt_rad > deg_to_rad(-0.5):
			var uv: Vector2 = _horizontal_to_panorama_uv(az_deg, rad_to_deg(alt_rad))
			var pixel_x: int = clampi(int(uv.x * float(WIDTH)), 0, WIDTH - 1)
			var pixel_y: int = clampi(int(uv.y * float(HEIGHT)), 0, HEIGHT - 1)
			var flux: float = pow(10.0, -0.4 * (observed_mag - reference_magnitude))
			var intensity: float = clampf(flux * brightest_intensity, 0.0, 1.0)
			var tint: Color = _star_color_from_bv(float(star["b_minus_v"]))
			_paint_star_point(image, pixel_x, pixel_y, tint, intensity)
		else:
			var band_u: int = clampi(int(fposmod(float(star["ra_hours"]) / 24.0, 1.0) * float(BAND_WIDTH)), 0, BAND_WIDTH - 1)
			var band_v: int = clampi(int((0.5 - dec_deg / 180.0) * float(BAND_HEIGHT)), 0, BAND_HEIGHT - 1)
			var flux_contrib: float = pow(10.0, -0.4 * magnitude)
			band_flux[band_v * BAND_WIDTH + band_u] += flux_contrib
	_paint_milky_way_flux(image, band_flux, BAND_WIDTH, BAND_HEIGHT, lst_hours, latitude_rad)
	return ImageTexture.create_from_image(image)


func _build_painted_panorama_fallback() -> Texture2D:
	# Generate a deterministic authored panorama when the catalog is absent.
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


func _paint_star_point(image: Image, pixel_x: int, pixel_y: int, tint: Color, intensity: float) -> void:
	var width: int = image.get_width()
	var height: int = image.get_height()
	# Approximate a Moffat core with four-neighbor wings.
	var core: Color = Color(tint.r * intensity, tint.g * intensity, tint.b * intensity, 1.0)
	image.set_pixel(pixel_x, pixel_y, image.get_pixel(pixel_x, pixel_y).lerp(core, clampf(intensity, 0.0, 1.0)))
	if intensity < 0.14:
		return
	var wing_scale: float = 0.28 * clampf(intensity, 0.0, 1.0)
	var wing: Color = Color(tint.r * wing_scale, tint.g * wing_scale, tint.b * wing_scale, 1.0)
	var offsets: Array[Vector2i] = [Vector2i(-1, 0), Vector2i(1, 0), Vector2i(0, -1), Vector2i(0, 1)]
	for offset: Vector2i in offsets:
		var nx: int = pixel_x + offset.x
		var ny: int = pixel_y + offset.y
		if nx < 0 or nx >= width or ny < 0 or ny >= height:
			continue
		var existing: Color = image.get_pixel(nx, ny)
		image.set_pixel(nx, ny, Color(minf(existing.r + wing.r, 1.0), minf(existing.g + wing.g, 1.0), minf(existing.b + wing.b, 1.0), 1.0))


func _paint_milky_way_flux(image: Image, band_flux: PackedFloat32Array, band_width: int, band_height: int, lst_hours: float, latitude_rad: float) -> void:
	# Project equatorial flux bins to altitude/azimuth and saturate intensity.
	var width: int = image.get_width()
	var height: int = image.get_height()
	var k: float = 0.085
	# Normalize the flux ceiling before saturation.
	var ceiling: float = 0.0
	for value: float in band_flux:
		if value > ceiling:
			ceiling = value
	if ceiling <= 0.0:
		return
	for v: int in range(band_height):
		var dec_deg: float = (0.5 - (float(v) + 0.5) / float(band_height)) * 180.0
		var dec_rad: float = deg_to_rad(dec_deg)
		for u: int in range(band_width):
			var flux: float = band_flux[v * band_width + u]
			if flux <= 0.0:
				continue
			var ra_hours: float = (float(u) + 0.5) / float(band_width) * 24.0
			var hour_angle_rad: float = deg_to_rad((lst_hours - ra_hours) * 15.0)
			var sin_alt: float = sin(dec_rad) * sin(latitude_rad) + cos(dec_rad) * cos(latitude_rad) * cos(hour_angle_rad)
			sin_alt = clampf(sin_alt, -1.0, 1.0)
			var alt_deg: float = rad_to_deg(asin(sin_alt))
			if alt_deg < -1.0:
				continue
			var az_rad: float = atan2(sin(hour_angle_rad), cos(hour_angle_rad) * sin(latitude_rad) - tan(dec_rad) * cos(latitude_rad))
			var az_deg: float = fposmod(rad_to_deg(az_rad) + 180.0, 360.0)
			var uv: Vector2 = _horizontal_to_panorama_uv(az_deg, alt_deg)
			var normalized: float = 1.0 - exp(-k * flux / ceiling)
			var intensity: float = clampf(normalized * 0.22, 0.0, 0.6)
			var pixel_x: int = clampi(int(uv.x * float(width)), 0, width - 1)
			var pixel_y: int = clampi(int(uv.y * float(height)), 0, height - 1)
			var existing: Color = image.get_pixel(pixel_x, pixel_y)
			var band_color: Color = Color(0.09, 0.10, 0.14, 1.0)
			image.set_pixel(pixel_x, pixel_y, Color(minf(existing.r + band_color.r * intensity, 1.0), minf(existing.g + band_color.g * intensity, 1.0), minf(existing.b + band_color.b * intensity, 1.0), 1.0))


func _horizontal_to_panorama_uv(azimuth_deg: float, elevation_deg: float) -> Vector2:
	# Equirectangular sky: u follows compass bearing; v runs zenith (0) to nadir (1).
	var u: float = fposmod(azimuth_deg, 360.0) / 360.0
	var v: float = clampf(0.5 - elevation_deg / 180.0, 0.0, 1.0)
	return Vector2(u, v)


func _star_color_from_bv(bv: float) -> Color:
	# Interpolate blackbody colors across five B-V stops.
	var stops: Array = [
		{"bv": -0.30, "color": Color(0.66, 0.77, 1.0)},
		{"bv": 0.00, "color": Color(0.78, 0.86, 1.0)},
		{"bv": 0.65, "color": Color(1.0, 0.96, 0.82)},
		{"bv": 1.20, "color": Color(1.0, 0.72, 0.48)},
		{"bv": 1.80, "color": Color(1.0, 0.48, 0.30)},
	]
	if bv <= float(stops[0]["bv"]):
		return stops[0]["color"]
	if bv >= float(stops[stops.size() - 1]["bv"]):
		return stops[stops.size() - 1]["color"]
	for index: int in range(stops.size() - 1):
		var a: Dictionary = stops[index]
		var b: Dictionary = stops[index + 1]
		if bv <= float(b["bv"]):
			var factor: float = inverse_lerp(float(a["bv"]), float(b["bv"]), bv)
			return (a["color"] as Color).lerp(b["color"], factor)
	return Color.WHITE


func _local_sidereal_time_hours(epoch_unix: float, observer_longitude_deg: float) -> float:
	# Convert Greenwich sidereal time using east-positive longitude.
	var julian_day: float = epoch_unix / 86400.0 + 2440587.5
	var gmst_hours: float = 18.697374558 + 24.06570982441908 * (julian_day - 2451545.0)
	var lst: float = fposmod(gmst_hours + observer_longitude_deg / 15.0, 24.0)
	return lst


## Return horizontal direction from north-clockwise azimuth and horizon elevation.
func horizontal_to_world_direction(azimuth_deg: float, elevation_deg: float) -> Vector3:
	var az: float = deg_to_rad(azimuth_deg)
	var el: float = deg_to_rad(elevation_deg)
	return Vector3(sin(az) * cos(el), sin(el), -cos(az) * cos(el)).normalized()


func _update_solar_override(state: Dictionary) -> void:
	var has_azimuth: bool = state.has("solar_azimuth_deg")
	var has_elevation: bool = state.has("solar_elevation_deg")

	if not has_azimuth and not has_elevation:
		return

	if has_azimuth != has_elevation:
		push_warning("Solar override requires both azimuth and elevation.")
		return

	if not use_weather_solar_override:
		return

	var azimuth: float = float(state["solar_azimuth_deg"])
	var elevation: float = float(state["solar_elevation_deg"])

	if not _is_finite_number(azimuth) or not _is_finite_number(elevation):
		push_warning("Rejected non-finite solar override.")
		return

	_solar_override_azimuth_deg = fposmod(azimuth, 360.0)
	_solar_override_elevation_deg = clampf(elevation, -18.0, 90.0)
	_solar_override_active = true
	_solar_azimuth_deg = _solar_override_azimuth_deg
	_solar_elevation_deg = _solar_override_elevation_deg
	_apply_solar_position()


func _validate_and_clamp_weather(values: Dictionary) -> void:
	values["air_temperature_c"] = clampf(float(values["air_temperature_c"]), -70.0, 60.0)
	values["dewpoint_c"] = clampf(float(values["dewpoint_c"]), -80.0, 45.0)
	values["relative_humidity"] = clampf(float(values["relative_humidity"]), 0.0, 1.0)
	values["wind_speed_mps"] = clampf(float(values["wind_speed_mps"]), 0.0, 65.0)
	values["wind_direction_deg"] = fposmod(float(values["wind_direction_deg"]), 360.0)
	values["cloud_fraction"] = clampf(float(values["cloud_fraction"]), 0.0, 1.0)
	values["cloud_base_agl_m"] = clampf(float(values["cloud_base_agl_m"]), 100.0, 10000.0)
	values["cloud_thickness_m"] = clampf(float(values["cloud_thickness_m"]), 100.0, 5000.0)
	values["precipitation_rate_mm_h"] = clampf(float(values["precipitation_rate_mm_h"]), 0.0, 250.0)
	values["snow_fraction"] = clampf(float(values["snow_fraction"]), 0.0, 1.0)
	values["visibility_m"] = clampf(float(values["visibility_m"]), 100.0, 100000.0)
	values["ground_wetness_fraction"] = clampf(float(values["ground_wetness_fraction"]), -1.0, 1.0)


func _apply_weather_state() -> void:
	if not smooth_weather_transitions or weather_transition_seconds <= 0.0:
		_visual_weight = 1.0
		_weather = _weather_target.duplicate(true)
		_apply_weather_state_immediate()
	else:
		# Apply validated state before the next frame.
		_apply_weather_state_immediate()


func _update_weather_interpolation(delta: float, physical_seconds: float = -1.0) -> void:
	if not _weather_initialized or not smooth_weather_transitions:
		return

	var seconds: float = physical_seconds if physical_seconds >= 0.0 else maxf(0.0, delta) * maxf(time_scale, 0.0)
	var factor: float = 1.0 - exp(-seconds / maxf(weather_transition_seconds, 0.001))
	_visual_weight = factor

	for key: String in SMOOTHED_WEATHER_FIELDS:
		if not _weather_target.has(key):
			continue
		var old_value: float = float(_weather[key])
		var target_value: float = float(_weather_target[key])

		if key == "ground_wetness_fraction" and old_value < 0.0:
			# Apply published hydrology wetness without interpolation.
			_weather[key] = target_value
		elif key == "wind_direction_deg":
			var angle_delta: float = fposmod(target_value - old_value + 180.0, 360.0) - 180.0
			_weather[key] = fposmod(old_value + angle_delta * factor, 360.0)
		else:
			_weather[key] = lerpf(old_value, target_value, factor)

	_apply_weather_state_immediate()


func _apply_weather_state_immediate() -> void:
	if not _configured:
		return
	_update_environment_from_weather()
	_update_precipitation_amounts()


func _create_cloud_shell() -> void:
	var quad: QuadMesh = QuadMesh.new()
	quad.size = Vector2(2.0, 2.0)
	_cloud_shell = MeshInstance3D.new()
	_cloud_shell.name = "ProceduralCloudShell"
	_cloud_shell.mesh = quad
	_cloud_shell.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_cloud_shell.extra_cull_margin = 16384.0
	_cloud_material = ShaderMaterial.new()
	_cloud_material.shader = CLOUD_SHADER
	_cloud_material.set_shader_parameter("cloud_field", OPTICS.cloud_texture())
	_cloud_material.render_priority = -100
	_cloud_material.set_shader_parameter("cloud_scale", cloud_scale)
	_cloud_material.set_shader_parameter("cloud_detail", cloud_detail)
	_cloud_material.set_shader_parameter("cloud_opacity", cloud_opacity)
	_cloud_material.set_shader_parameter("cloud_cover", default_cloud_fraction)
	_cloud_material.set_shader_parameter("cloud_density", cloud_density_scale)
	_cloud_material.set_shader_parameter("cloud_base_agl_m", default_cloud_base_agl_m)
	_cloud_material.set_shader_parameter("cloud_top_agl_m", default_cloud_base_agl_m + default_cloud_thickness_m)
	_cloud_material.set_shader_parameter("cloud_vertical_edge_softness", cloud_vertical_edge_softness)
	_cloud_shell.material_override = _cloud_material
	add_child(_cloud_shell)


func _create_rainbow() -> void:
	_rain_curtain = OPTICS.new()
	_rainbow_material = ShaderMaterial.new()
	_rainbow_material.shader = RAINBOW_SHADER
	_rainbow_material.render_priority = -90
	_rainbow_material.set_shader_parameter("primary_angles", OPTICS.angles(1))
	_rainbow_material.set_shader_parameter("secondary_angles", OPTICS.angles(2))
	_rainbow_material.set_shader_parameter("secondary_ratio", OPTICS.secondary_ratio())
	var quad: QuadMesh = QuadMesh.new()
	quad.size = Vector2(2.0, 2.0)
	_rainbow = MeshInstance3D.new()
	_rainbow.name = "RainCurtainScattering"
	_rainbow.mesh = quad
	_rainbow.material_override = _rainbow_material
	_rainbow.extra_cull_margin = 16384.0
	_rainbow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_rainbow.visible = false
	add_child(_rainbow)


func _update_rainbow(physical_seconds: float, wind_mps: Vector3, cloud_base_world: float, cloud_thickness: float) -> void:
	_rain_curtain.advance(physical_seconds, _weather, _target.global_position, wind_mps)
	var sun_direction: Vector3 = _sun_direction_vector()
	var sample_origin: Vector3 = Vector3(_rain_curtain.center.x, (_rain_curtain.base_y_m + _rain_curtain.top_y_m) * 0.5, _rain_curtain.center.z)
	_rainbow_direct_transmission = OPTICS.cloud_transmission(sample_origin, sun_direction, cloud_base_world, cloud_thickness, cloud_scale, _cloud_offset, float(_weather["cloud_fraction"]), cloud_detail, cloud_density_scale)
	_rainbow_direct_transmission *= OPTICS.daylight_gate(sun_direction)
	_rainbow.global_position = _target.global_position
	_rainbow.visible = _rain_curtain.optical_depth > 0.001 and _rainbow_direct_transmission > 0.005
	if not _rainbow.visible:
		return
	_rainbow_material.set_shader_parameter("sun_direction", sun_direction)
	_rainbow_material.set_shader_parameter("curtain_center", _rain_curtain.center)
	_rainbow_material.set_shader_parameter("curtain_radius_m", OPTICS.CURTAIN_RADIUS_M)
	_rainbow_material.set_shader_parameter("curtain_base_m", _rain_curtain.base_y_m)
	_rainbow_material.set_shader_parameter("curtain_top_m", _rain_curtain.top_y_m)
	_rainbow_material.set_shader_parameter("drop_optical_depth", _rain_curtain.optical_depth)
	_rainbow_material.set_shader_parameter("direct_transmission", _rainbow_direct_transmission)
	_rainbow_material.set_shader_parameter("sun_tint", Vector3(_sun.light_color.r, _sun.light_color.g, _sun.light_color.b))


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
	process.angular_velocity_min = -0.7 if not is_snow else 0.0
	process.angular_velocity_max = 0.7 if not is_snow else 0.0
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

	var physical_seconds: float = _consume_physical_seconds(delta)
	_update_weather_interpolation(delta, physical_seconds)
	_maybe_rebuild_star_sky()

	var player_position: Vector3 = _target.global_position
	var cloud_base: float = float(_weather["cloud_base_agl_m"])
	var cloud_thickness: float = maxf(float(_weather["cloud_thickness_m"]), 100.0)
	var cloud_top: float = cloud_base + cloud_thickness
	var base_altitude: float = cloud_base if cloud_world_altitude_mode else player_position.y + cloud_base
	_cloud_shell.global_position = player_position

	var wind_speed: float = float(_weather["wind_speed_mps"])
	var wind_toward: Vector3 = _meteorological_wind_toward(float(_weather["wind_direction_deg"]))
	var wind_xz: Vector2 = Vector2(wind_toward.x, wind_toward.z) * wind_speed
	_cloud_offset -= wind_xz * physical_seconds * cloud_drift_multiplier * cloud_scale

	var cloud_fraction: float = float(_weather["cloud_fraction"])

	_cloud_material.set_shader_parameter("cloud_offset", _cloud_offset)
	_cloud_material.set_shader_parameter("cloud_center", Vector3(player_position.x, base_altitude + cloud_thickness * 0.5, player_position.z))
	_cloud_material.set_shader_parameter("cloud_cover", cloud_fraction)
	_cloud_material.set_shader_parameter("cloud_density", cloud_density_scale)
	_cloud_material.set_shader_parameter("cloud_scale", cloud_scale)
	_cloud_material.set_shader_parameter("cloud_detail", cloud_detail)
	_cloud_material.set_shader_parameter("cloud_opacity", cloud_opacity)
	_cloud_material.set_shader_parameter("cloud_base_agl_m", cloud_base)
	_cloud_material.set_shader_parameter("cloud_top_agl_m", cloud_top)
	_cloud_material.set_shader_parameter("cloud_vertical_edge_softness", cloud_vertical_edge_softness)
	_cloud_material.set_shader_parameter("sun_direction", _sun_direction_vector())
	_cloud_material.set_shader_parameter("sun_tint", Vector3(_sun.light_color.r, _sun.light_color.g, _sun.light_color.b))
	_cloud_material.set_shader_parameter("daylight", _daylight_factor())
	_cloud_shell.visible = cloud_fraction > 0.001
	_update_rainbow(physical_seconds, wind_toward * wind_speed, base_altitude, cloud_thickness)

	_rain.global_position = player_position + Vector3(0.0, emitter_height_m, 0.0)
	_snow.global_position = player_position + Vector3(0.0, emitter_height_m, 0.0)
	_update_particle_wind(_rain_process, wind_toward, wind_speed, false)
	_update_particle_wind(_snow_process, wind_toward, wind_speed, true)
	# Apply surface wetness after weather interpolation.
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
	var rate: float = maxf(float(_weather["precipitation_rate_mm_h"]), 0.0)
	var snow_fraction: float = clampf(float(_weather["snow_fraction"]), 0.0, 1.0)
	var cloud_fraction: float = clampf(float(_weather["cloud_fraction"]), 0.0, 1.0)
	# Scale precipitation below 0.6 cloud cover.
	var cover_gate: float = clampf(cloud_fraction / 0.6, 0.0, 1.0)
	var intensity: float = 0.0
	if rate > 0.001:
		intensity = clampf(sqrt(rate / maxf(full_particle_rate_mm_h, 0.1)), 0.0, 1.0)
	intensity *= cover_gate
	var rain_ratio: float = intensity * (1.0 - snow_fraction)
	var snow_ratio: float = intensity * snow_fraction
	_rain.amount_ratio = lerpf(_rain.amount_ratio, clampf(rain_ratio, 0.0, 1.0), _visual_weight)
	_snow.amount_ratio = lerpf(_snow.amount_ratio, clampf(snow_ratio, 0.0, 1.0), _visual_weight)
	_rain.emitting = _rain.amount_ratio > 0.005
	_snow.emitting = _snow.amount_ratio > 0.005


func _set_sky_uniform(key: String, value: float) -> void:
	if not _sky_uniforms.has(key) or absf(float(_sky_uniforms[key]) - value) > 0.0001:
		_sky_uniforms[key] = value
		_physical_sky.set_shader_parameter(key, value)


func _update_environment_from_weather() -> void:
	var humidity: float = float(_weather["relative_humidity"])
	var visibility: float = float(_weather["visibility_m"])
	var cloud_fraction: float = float(_weather["cloud_fraction"])
	var haze: float = clampf(1.0 - visibility / maxf(clear_visibility_m, 100.0), 0.0, 1.0)
	_set_sky_uniform("turbidity", clampf(2.2 + haze * 5.5 + maxf(0.0, humidity - 0.7) * 1.6, 2.0, 10.0))
	_set_sky_uniform("exposure", lerpf(0.78, 1.0, _daylight_factor()))
	_set_sky_uniform("daylight", _daylight_factor())

	var daylight: float = _daylight_factor()
	_environment.ambient_light_color = Color(0.53, 0.61, 0.70).lerp(Color(0.68, 0.70, 0.72), haze * 0.55)
	_environment.ambient_light_energy = lerpf(0.06, 0.55 + cloud_fraction * default_cloud_ambient_dim * 0.35, daylight)
	_environment.fog_light_color = Color(0.50, 0.59, 0.68).lerp(Color(0.70, 0.72, 0.72), haze * 0.6)
	_environment.fog_density = lerpf(_environment.fog_density, lerpf(0.000035, 0.0011, pow(haze, 1.55)), _visual_weight)
	_environment.fog_aerial_perspective = lerpf(0.08, 0.30, haze)
	_environment.fog_sky_affect = 0.55 * haze * haze

	var sun_angle: float = _solar_elevation_deg
	var horizon_factor: float = 1.0 - smoothstep(4.0, 28.0, maxf(0.0, sun_angle))
	var warm_horizon: Color = Color(1.0, 0.66, 0.43)
	var daylight_tint: Color = warm_horizon.lerp(Color(1.0, 0.96, 0.87), 1.0 - horizon_factor)
	_sun.light_color = _sun.light_color.lerp(daylight_tint.lerp(Color(0.62, 0.70, 0.82), cloud_fraction * 0.28), _visual_weight)
	_sun.light_energy = 1.35 * daylight * (1.0 - cloud_fraction * 0.65)


func _update_wetness() -> void:
	var cloud_shadow: float = float(_terrain_state["cloud_shadow_fraction"])
	if cloud_shadow < 0.0:
		cloud_shadow = clampf(float(_weather["cloud_fraction"]), 0.0, 1.0)
	var wetness: float = float(_weather["ground_wetness_fraction"])
	var snow_cover: float = float(_terrain_state["snow_cover_fraction"])
	var puddle: float = float(_terrain_state["puddle_fraction"])
	var soil_temp_c: float = float(_terrain_state["soil_temperature_c"])
	var swe_mm: float = float(_terrain_state["snow_water_equivalent_mm"])
	for material: ShaderMaterial in _wetness_surfaces:
		if material.shader == null:
			continue
		if wetness >= 0.0 and _shader_has_parameter(material.shader, &"ground_wetness"):
			material.set_shader_parameter("ground_wetness", wetness)
		if _shader_has_parameter(material.shader, &"cloud_shadow"):
			material.set_shader_parameter("cloud_shadow", cloud_shadow)
		if snow_cover >= 0.0 and _shader_has_parameter(material.shader, &"snow_cover_fraction"):
			material.set_shader_parameter("snow_cover_fraction", snow_cover)
		if puddle >= 0.0 and _shader_has_parameter(material.shader, &"puddle_fraction"):
			material.set_shader_parameter("puddle_fraction", puddle)
		if soil_temp_c > -273.0 and _shader_has_parameter(material.shader, &"soil_temperature_c"):
			material.set_shader_parameter("soil_temperature_c", soil_temp_c)
		if swe_mm >= 0.0 and _shader_has_parameter(material.shader, &"snow_swe_mm"):
			material.set_shader_parameter("snow_swe_mm", swe_mm)


func _apply_terrain_state(terrain: Dictionary) -> void:
	# Retain prior terrain values when fields are absent.
	for key: String in _terrain_state.keys():
		if not terrain.has(key):
			continue
		var value: Variant = terrain[key]
		if not _is_finite_number(value):
			push_warning("Rejected non-finite terrain field '%s'." % key)
			continue
		_terrain_state[key] = float(value)


func get_terrain_state() -> Dictionary:
	# Return surface state; negative sentinels leave materials unchanged.
	return _terrain_state.duplicate(true)


func set_cloud_shadow_fraction(value: float) -> void:
	if not _is_finite_number(value):
		return
	_terrain_state["cloud_shadow_fraction"] = clampf(value, 0.0, 1.0)


func _shader_has_parameter(shader: Shader, parameter_name: StringName) -> bool:
	for property: Dictionary in shader.get_shader_uniform_list():
		if StringName(property.get("name", "")) == parameter_name:
			return true
	return false


func _is_finite_number(value: Variant) -> bool:
	if not (value is int or value is float):
		return false
	return is_finite(float(value))


func _meteorological_wind_toward(direction_from_deg: float) -> Vector3:
	# +X is east, +Z is south; wind points opposite its source bearing.
	var angle: float = deg_to_rad(direction_from_deg + 180.0)
	return Vector3(sin(angle), 0.0, -cos(angle)).normalized()


func _daylight_factor() -> float:
	return smoothstep(-7.0, 8.0, _solar_elevation_deg)


func _sun_direction_vector() -> Vector3:
	return horizontal_to_world_direction(_solar_azimuth_deg, _solar_elevation_deg)


func _update_solar_position_from_timestamp(epoch_unix: float) -> void:
	var local_epoch: float = epoch_unix + simulation_utc_offset_hours * 3600.0
	var date: Dictionary = Time.get_datetime_dict_from_unix_time(local_epoch)
	_clock_hour = (
		float(date["hour"])
		+ float(date["minute"]) / 60.0
		+ float(date["second"]) / 3600.0
	)
	_day_of_year = _day_of_year_for_date(int(date["year"]), int(date["month"]), int(date["day"]))
	_update_solar_position()


func _day_of_year_for_date(year: int, month: int, day: int) -> int:
	var month_lengths: Array[int] = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
	var leap: bool = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
	if leap:
		month_lengths[1] = 29
	var result: int = day
	for index: int in range(month - 1):
		result += month_lengths[index]
	return result


func _update_solar_position() -> void:
	# Use the NOAA fractional-year approximation for solar declination and equation of time.
	var gamma: float = TAU / 365.0 * (float(_day_of_year) - 1.0 + (_clock_hour - 12.0) / 24.0)
	var equation_of_time: float = 229.18 * (0.000075 + 0.001868 * cos(gamma) - 0.032077 * sin(gamma) - 0.014615 * cos(2.0 * gamma) - 0.040849 * sin(2.0 * gamma))
	var declination: float = 0.006918 - 0.399912 * cos(gamma) + 0.070257 * sin(gamma) - 0.006758 * cos(2.0 * gamma) + 0.000907 * sin(2.0 * gamma) - 0.002697 * cos(3.0 * gamma) + 0.00148 * sin(3.0 * gamma)
	var time_offset: float = equation_of_time + 4.0 * longitude_deg - 60.0 * simulation_utc_offset_hours
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
	# Point local -Z opposite the ground-to-sun vector.
	var sun_from_ground: Vector3 = _sun_direction_vector()
	_sun.look_at(_sun.global_position - sun_from_ground, Vector3.UP)


func refresh_wetness_material_cache() -> void:
	## Bind generated terrain tiles and materials.
	_cache_wetness_materials()


func get_render_state() -> Dictionary:
	## Return display-only state for HUD and captures.
	return {
		"simulation_epoch_unix": _simulation_epoch_unix,
		"has_simulation_timestamp": _has_simulation_timestamp,
		"solar_override_active": _solar_override_active,
		"day_of_year": _day_of_year,
		"solar_azimuth_deg": _solar_azimuth_deg,
		"solar_elevation_deg": _solar_elevation_deg,
		"daylight_factor": _daylight_factor(),
		"cloud_fraction": float(_weather["cloud_fraction"]),
		"rain_curtain_optical_depth": _rain_curtain.optical_depth,
		"rain_curtain_center": _rain_curtain.center,
		"rainbow_direct_transmission": _rainbow_direct_transmission,
		"rainbow_secondary_ratio": OPTICS.secondary_ratio(),
		"precipitation_rate_mm_h": float(_weather["precipitation_rate_mm_h"]),
		"snow_fraction": float(_weather["snow_fraction"]),
		"visibility_m": float(_weather["visibility_m"]),
		"sky_turbidity": _physical_sky.get_shader_parameter("turbidity"),
		"star_visibility": 1.0 - _daylight_factor(),
		"fog_sky_affect": _environment.fog_sky_affect,
		"direct_light_energy": _sun.light_energy,
		"ambient_light_energy": _environment.ambient_light_energy,
		"star_catalog_loaded": _star_catalog_loaded,
		"star_rebuild_epoch_unix": _star_rebuild_epoch_unix,
		"terrain": _terrain_state.duplicate(true),
	}


func _maybe_rebuild_star_sky() -> void:
	if _physical_sky == null or not _star_catalog_loaded:
		return
	var epoch_delta: float = absf(_simulation_epoch_unix - _star_rebuild_epoch_unix)
	if epoch_delta < star_rebuild_interval_seconds:
		return
	rebuild_star_sky()
