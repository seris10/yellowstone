I’ll start with **`yellowstone_atmosphere.gd`**. Below is a focused rewrite of the controller’s core changes. It preserves your existing cloud, particle, wetness, and environment helpers while adding:

- UTC Unix-timestamp-driven solar geometry.
- Correct local-date/day-of-year handling with a configurable UTC offset.
- Safer solar override behavior.
- Direction-vector-based sun orientation.
- Smoothed weather transitions.
- Precipitation phase/intensity handling.
- Cloud shell vertical-density inputs.
- Compatibility-renderer-safe behavior.

Replace the corresponding sections in your current script.

---

## 1. Add these variables and exports

Add near the existing solar and weather exports:

```gdscript
@export_group("Simulation time")

@export var simulation_utc_offset_hours: float = -6.0

@export var smooth_weather_transitions: bool = true

@export_range(0.0, 300.0, 1.0)
var weather_transition_seconds: float = 20.0

@export var use_weather_solar_override: bool = true

@export_group("Cloud shell")

@export var cloud_world_altitude_mode: bool = true

@export_range(0.0, 1.0, 0.01)
var cloud_vertical_edge_softness: float = 0.18
```

Add these state variables:

```gdscript
var _simulation_epoch_unix: float = 0.0
var _has_simulation_timestamp: bool = false

var _weather_target: Dictionary = {}
var _weather_initialized: bool = false

var _solar_override_active: bool = false
var _solar_override_azimuth_deg: float = 0.0
var _solar_override_elevation_deg: float = 0.0
```

Keep the existing `_weather` dictionary, `_solar_azimuth_deg`, and `_solar_elevation_deg`.

---

## 2. Replace `configure()`

```gdscript
func configure(
	sun_node: DirectionalLight3D,
	environment_resource: Environment,
	follow_target: Node3D
) -> void:
	if sun_node == null:
		push_error(
			"YellowstoneAtmosphereController.configure requires a sun node."
		)
		return

	if environment_resource == null:
		push_error(
			"YellowstoneAtmosphereController.configure requires an Environment."
		)
		return

	if follow_target == null:
		push_error(
			"YellowstoneAtmosphereController.configure requires a target."
		)
		return

	_sun = sun_node
	_environment = environment_resource
	_target = follow_target

	_weather = WEATHER_DEFAULTS.duplicate(true)
	_weather_target = _weather.duplicate(true)
	_weather_initialized = true

	_weather["cloud_fraction"] = default_cloud_fraction
	_weather["cloud_base_agl_m"] = default_cloud_base_agl_m
	_weather["cloud_thickness_m"] = default_cloud_thickness_m
	_weather["relative_humidity"] = default_relative_humidity
	_weather["visibility_m"] = clear_visibility_m

	_weather_target = _weather.duplicate(true)

	_day_of_year = default_day_of_year
	_solar_override_active = false

	_install_physical_sky()
	_create_cloud_shell()
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
```

---

## 3. Add timestamp-driven simulation time

Add these methods:

```gdscript
func set_simulation_timestamp(
	epoch_unix: float,
	utc_offset_hours: float = -99.0
) -> void:
	if not is_finite(epoch_unix):
		push_warning("Simulation timestamp must be finite.")
		return

	_simulation_epoch_unix = epoch_unix
	_has_simulation_timestamp = true

	if utc_offset_hours >= -12.0 and utc_offset_hours <= 14.0:
		simulation_utc_offset_hours = utc_offset_hours

	if not _solar_override_active:
		_update_solar_position_from_timestamp(epoch_unix)
		_apply_solar_position()


func clear_simulation_timestamp() -> void:
	_has_simulation_timestamp = false


func set_simulation_time(
	hour: float,
	day_of_year: int = -1,
	utc_offset: float = -99.0
) -> void:
	if not is_finite(hour):
		push_warning("Simulation hour must be finite.")
		return

	_clock_hour = fposmod(hour, 24.0)

	if day_of_year >= 1 and day_of_year <= 366:
		_day_of_year = day_of_year

	if utc_offset >= -12.0 and utc_offset <= 14.0:
		simulation_utc_offset_hours = utc_offset

	# This legacy API intentionally clears a previous external solar override.
	_solar_override_active = false

	if not _has_simulation_timestamp:
		_update_solar_position()
		_apply_solar_position()
```

The important behavior is that the timestamp API becomes authoritative for replay mode, while the existing hour/day API remains available for compatibility.

---

## 4. Add a date-aware solar calculation

Add:

```gdscript
func _update_solar_position_from_timestamp(epoch_unix: float) -> void:
	var local_epoch := epoch_unix + simulation_utc_offset_hours * 3600.0
	var date := Time.get_datetime_dict_from_unix_time(local_epoch)

	var year: int = int(date["year"])
	var month: int = int(date["month"])
	var day: int = int(date["day"])
	var hour: float = (
		float(date["hour"])
		+ float(date["minute"]) / 60.0
		+ float(date["second"]) / 3600.0
	)

	_clock_hour = hour
	_day_of_year = _day_of_year_for_date(year, month, day)

	_update_solar_position()
```

Add the date helper:

```gdscript
func _day_of_year_for_date(year: int, month: int, day: int) -> int:
	var month_lengths := [
		31, 28, 31, 30, 31, 30,
		31, 31, 30, 31, 30, 31
	]

	var leap := (
		(year % 4 == 0 and year % 100 != 0)
		or year % 400 == 0
	)

	if leap:
		month_lengths[1] = 29

	var result := day

	for index in range(month - 1):
		result += month_lengths[index]

	return result
```

Replace `_update_solar_position()` with:

```gdscript
func _update_solar_position() -> void:
	# NOAA fractional-year approximation. This is a fallback calculation.
	# For production weather/replay snapshots, Python-generated pvlib angles
	# may override this method through set_weather_state().
	var gamma := TAU / 365.0 * (
		float(_day_of_year) - 1.0
		+ (_clock_hour - 12.0) / 24.0
	)

	var equation_of_time := 229.18 * (
		0.000075
		+ 0.001868 * cos(gamma)
		- 0.032077 * sin(gamma)
		- 0.014615 * cos(2.0 * gamma)
		- 0.040849 * sin(2.0 * gamma)
	)

	var declination := (
		0.006918
		- 0.399912 * cos(gamma)
		+ 0.070257 * sin(gamma)
		- 0.006758 * cos(2.0 * gamma)
		+ 0.000907 * sin(2.0 * gamma)
		- 0.002697 * cos(3.0 * gamma)
		+ 0.00148 * sin(3.0 * gamma)
	)

	var time_offset := (
		equation_of_time
		+ 4.0 * longitude_deg
		- 60.0 * simulation_utc_offset_hours
	)

	var solar_minutes := fposmod(
		_clock_hour * 60.0 + time_offset,
		1440.0
	)

	var hour_angle := deg_to_rad(solar_minutes / 4.0 - 180.0)
	var latitude := deg_to_rad(latitude_deg)

	var cosine_zenith := clampf(
		sin(latitude) * sin(declination)
		+ cos(latitude) * cos(declination) * cos(hour_angle),
		-1.0,
		1.0
	)

	_solar_elevation_deg = 90.0 - rad_to_deg(acos(cosine_zenith))

	var azimuth := atan2(
		sin(hour_angle),
		cos(hour_angle) * sin(latitude)
		- tan(declination) * cos(latitude)
	)

	_solar_azimuth_deg = fposmod(
		rad_to_deg(azimuth) + 180.0,
		360.0
	)
```

This remains an approximation. For the most accurate live/replay path, supply solar angles from Python using `pvlib`.

---

## 5. Replace `set_weather_state()`

The original method applies every update immediately. Replace it with:

```gdscript
func set_weather_state(state: Dictionary) -> void:
	if not _weather_initialized:
		_weather = WEATHER_DEFAULTS.duplicate(true)
		_weather_target = _weather.duplicate(true)
		_weather_initialized = true

	var accepted := false

	for key: String in WEATHER_DEFAULTS.keys():
		if state.has(key):
			var value: Variant = state[key]

			if not _is_finite_number(value):
				push_warning(
					"Rejected non-finite weather field '%s'." % key
				)
				continue

			_weather_target[key] = value
			accepted = true

	if not accepted and not (
		state.has("solar_azimuth_deg")
		or state.has("solar_elevation_deg")
	):
		return

	_validate_and_clamp_weather(_weather_target)
	_update_solar_override(state)

	if not smooth_weather_transitions:
		_weather = _weather_target.duplicate(true)
		_apply_weather_state_immediate()
	else:
		_apply_weather_state()
```

Add:

```gdscript
func _validate_and_clamp_weather(values: Dictionary) -> void:
	values["air_temperature_c"] = clampf(
		float(values["air_temperature_c"]),
		-70.0,
		60.0
	)

	values["dewpoint_c"] = clampf(
		float(values["dewpoint_c"]),
		-80.0,
		45.0
	)

	values["relative_humidity"] = clampf(
		float(values["relative_humidity"]),
		0.0,
		1.0
	)

	values["wind_speed_mps"] = clampf(
		float(values["wind_speed_mps"]),
		0.0,
		65.0
	)

	values["wind_direction_deg"] = fposmod(
		float(values["wind_direction_deg"]),
		360.0
	)

	values["cloud_fraction"] = clampf(
		float(values["cloud_fraction"]),
		0.0,
		1.0
	)

	values["cloud_base_agl_m"] = clampf(
		float(values["cloud_base_agl_m"]),
		100.0,
		10000.0
	)

	values["cloud_thickness_m"] = clampf(
		float(values["cloud_thickness_m"]),
		100.0,
		5000.0
	)

	values["precipitation_rate_mm_h"] = clampf(
		float(values["precipitation_rate_mm_h"]),
		0.0,
		250.0
	)

	values["snow_fraction"] = clampf(
		float(values["snow_fraction"]),
		0.0,
		1.0
	)

	values["visibility_m"] = clampf(
		float(values["visibility_m"]),
		100.0,
		100000.0
	)

	values["ground_wetness_fraction"] = clampf(
		float(values["ground_wetness_fraction"]),
		-1.0,
		1.0
	)
```

Add:

```gdscript
func _update_solar_override(state: Dictionary) -> void:
	var has_azimuth := state.has("solar_azimuth_deg")
	var has_elevation := state.has("solar_elevation_deg")

	if not has_azimuth and not has_elevation:
		return

	if has_azimuth != has_elevation:
		push_warning(
			"Solar override requires both azimuth and elevation; "
			+ "ignoring partial override."
		)
		return

	if not use_weather_solar_override:
		return

	var azimuth := float(state["solar_azimuth_deg"])
	var elevation := float(state["solar_elevation_deg"])

	if not is_finite(azimuth) or not is_finite(elevation):
		push_warning("Rejected non-finite solar override.")
		return

	_solar_override_azimuth_deg = fposmod(azimuth, 360.0)
	_solar_override_elevation_deg = clampf(elevation, -18.0, 90.0)
	_solar_override_active = true

	_solar_azimuth_deg = _solar_override_azimuth_deg
	_solar_elevation_deg = _solar_override_elevation_deg

	_apply_solar_position()
```

Add a method for clearing an old weather override:

```gdscript
func clear_weather_solar_override() -> void:
	_solar_override_active = false

	if _has_simulation_timestamp:
		_update_solar_position_from_timestamp(_simulation_epoch_unix)
	else:
		_update_solar_position()

	_apply_solar_position()
```

---

## 6. Add smooth weather interpolation

Replace `_apply_weather_state()` with:

```gdscript
func _apply_weather_state() -> void:
	if not smooth_weather_transitions:
		_weather = _weather_target.duplicate(true)
		_apply_weather_state_immediate()
		return

	var transition := maxf(weather_transition_seconds, 0.0)

	if transition <= 0.0:
		_weather = _weather_target.duplicate(true)
		_apply_weather_state_immediate()
		return

	# The actual interpolation is performed each render update.
	_update_weather_interpolation(0.1)
```

Add:

```gdscript
func _update_weather_interpolation(delta: float) -> void:
	if not _weather_initialized:
		return

	var transition := maxf(weather_transition_seconds, 0.001)
	var factor := clampf(delta / transition, 0.0, 1.0)

	var continuous_fields := [
		"air_temperature_c",
		"dewpoint_c",
		"relative_humidity",
		"wind_speed_mps",
		"wind_direction_deg",
		"cloud_fraction",
		"cloud_base_agl_m",
		"cloud_thickness_m",
		"precipitation_rate_mm_h",
		"snow_fraction",
		"visibility_m",
		"ground_wetness_fraction",
	]

	for key: String in continuous_fields:
		if not _weather_target.has(key):
			continue

		var old_value := float(_weather[key])
		var target_value := float(_weather_target[key])

		if key == "wind_direction_deg":
			var delta_angle := fposmod(
				target_value - old_value + 180.0,
				360.0
			) - 180.0

			_weather[key] = fposmod(
				old_value + delta_angle * factor,
				360.0
			)
		else:
			_weather[key] = lerpf(
				old_value,
				target_value,
				factor
			)

	_apply_weather_state_immediate()
```

Replace the beginning of `_update_atmosphere()`:

```gdscript
func _update_atmosphere(delta: float) -> void:
	if _target == null:
		return

	_update_weather_interpolation(delta)

	var player_position := _target.global_position
```

This prevents cloud cover, fog, wind, and precipitation from visibly snapping between snapshots.

---

## 7. Replace `_apply_solar_position()`

The Euler assignment is ambiguous. Use a direction vector instead:

```gdscript
func _apply_solar_position() -> void:
	if _sun == null:
		return

	var sun_from_ground := _sun_direction_vector()

	# DirectionalLight3D emits light along local -Z. The light rays travel
	# from the sun toward the scene, therefore -Z must point opposite the
	# ground-to-sun vector.
	var target := _sun.global_position - sun_from_ground

	_sun.look_at(target, Vector3.UP)

	_sun.shadow_enabled = true
	_sun.directional_shadow_max_distance = 280.0
```

Retain `_sun_direction_vector()`:

```gdscript
func _sun_direction_vector() -> Vector3:
	var azimuth := deg_to_rad(_solar_azimuth_deg)
	var elevation := deg_to_rad(_solar_elevation_deg)

	return Vector3(
		sin(azimuth) * cos(elevation),
		sin(elevation),
		cos(azimuth) * cos(elevation)
	).normalized()
```

Verify this in a simple test scene with known north/east sun positions. The expected behavior is that shadows project opposite the sun’s horizontal direction.

---

## 8. Improve precipitation handling

Replace `_update_precipitation_amounts()`:

```gdscript
func _update_precipitation_amounts() -> void:
	var rate := maxf(
		float(_weather["precipitation_rate_mm_h"]),
		0.0
	)

	var snow_fraction := clampf(
		float(_weather["snow_fraction"]),
		0.0,
		1.0
	)

	var intensity := 0.0

	if rate > 0.001:
		intensity = clampf(
			sqrt(rate / maxf(full_particle_rate_mm_h, 0.1)),
			0.0,
			1.0
		)

	var rain_ratio := intensity * (1.0 - snow_fraction)
	var snow_ratio := intensity * snow_fraction

	_rain.amount_ratio = clampf(rain_ratio, 0.0, 1.0)
	_snow.amount_ratio = clampf(snow_ratio, 0.0, 1.0)

	_rain.emitting = _rain.amount_ratio > 0.005
	_snow.emitting = _snow.amount_ratio > 0.005

	# A small amount of precipitation should not use full visual density.
	# Keep the particle systems alive only when the normalized rate warrants it.
	if rate <= 0.001:
		_rain.emitting = false
		_snow.emitting = false
```

This assumes the weather provider, not the renderer, determines snow phase.

---

## 9. Improve cloud shell parameters

Inside `_update_atmosphere()`, after setting `cloud_cover`, add:

```gdscript
	var cloud_base := float(_weather["cloud_base_agl_m"])
	var cloud_thickness := float(_weather["cloud_thickness_m"])
	var cloud_top := cloud_base + cloud_thickness

	_cloud_material.set_shader_parameter(
		"cloud_base_agl_m",
		cloud_base
	)

	_cloud_material.set_shader_parameter(
		"cloud_top_agl_m",
		cloud_top
	)

	_cloud_material.set_shader_parameter(
		"cloud_vertical_edge_softness",
		cloud_vertical_edge_softness
	)
```

Use a safe minimum:

```gdscript
	cloud_thickness = maxf(cloud_thickness, 100.0)
```

The shader will need corresponding uniforms:

```glsl
uniform float cloud_base_agl_m = 1000.0;
uniform float cloud_top_agl_m = 1600.0;
uniform float cloud_vertical_edge_softness = 0.18;
```

---

## 10. Add numeric validation helper

```gdscript
func _is_finite_number(value: Variant) -> bool:
	if not (value is int or value is float):
		return false

	return is_finite(float(value))
```

---

## 11. Update integration

Instead of only calling:

```gdscript
atmosphere_controller.set_simulation_time(
	ecosystem.clock_hour,
	int(spec.get("day_of_year", 196))
)
```

prefer:

```gdscript
if spec.has("simulation_epoch_unix"):
	atmosphere_controller.set_simulation_timestamp(
		float(spec["simulation_epoch_unix"]),
		float(spec.get("utc_offset_hours", -6.0))
	)
else:
	atmosphere_controller.set_simulation_time(
		ecosystem.clock_hour,
		int(spec.get("day_of_year", 196)),
		float(spec.get("utc_offset_hours", -6.0))
	)
```

For replay, update the timestamp using the simulation clock:

```gdscript
simulation_epoch_unix += delta * simulation_rate

atmosphere_controller.set_simulation_timestamp(
	simulation_epoch_unix,
	-6.0
)

weather_snapshot_reader.set_simulation_epoch_unix(
	simulation_epoch_unix
)
```

---

## Important compatibility note

The controller’s current `_install_physical_sky()` sets:

```gdscript
_environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
```

That means the environment is not using the physical sky as its ambient source. For a more physically coherent sky, use:

```gdscript
_environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
_environment.ambient_light_sky_contribution = 0.7
```

If Compatibility rendering produces undesirable results, retain `AMBIENT_SOURCE_COLOR` as a renderer-specific fallback.

The next script in the requested sequence should be `yellowstone_cloud_shell.gdshader`, where the matching cloud uniforms and inside-sphere culling can be implemented.