# Integrating with the existing Yellowstone main world script

The current main world script creates the sun and environment before it instantiates the player and calls `update_environment()` from `_process`. Keep that lifecycle. Apply the edits below rather than introducing a second sun or a second `WorldEnvironment`.

## 1. Add script preloads and variables

Near the other `preload` constants:

```gdscript
const AtmosphereController = preload("res://scripts/yellowstone_atmosphere.gd")
const WeatherSnapshotReader = preload("res://scripts/weather_snapshot_reader.gd")
```

Replace:

```gdscript
var sky_material: ProceduralSkyMaterial
```

with:

```gdscript
var sky_material: PhysicalSkyMaterial
var atmosphere_controller
var weather_snapshot_reader
```

## 2. Change the sky material in `make_environment()`

Keep the existing `sun` and `environment` setup. Replace the block that constructs `ProceduralSkyMaterial` and sets `sky_top_color`, `sky_horizon_color`, `ground_bottom_color`, `ground_horizon_color`, `sun_angle_max` and `sun_curve` with:

```gdscript
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
```

Leave the rest of the existing environment initialization in place. The controller configures weather-responsive values when it is initialized.

## 3. Configure the controller after the player is placed

In `_ready()`, immediately after the initial `go_to_anchor(0)` call, add:

```gdscript
atmosphere_controller = AtmosphereController.new()
atmosphere_controller.name = "YellowstoneAtmosphere"
add_child(atmosphere_controller)
atmosphere_controller.configure(sun, environment, player)
atmosphere_controller.set_simulation_elapsed(ecosystem.elapsed)

# Prefer the replay timestamp when the build supplies one; the local date and
# day of year derive from it.
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

weather_snapshot_reader = WeatherSnapshotReader.new()
weather_snapshot_reader.name = "WeatherSnapshotReader"
add_child(weather_snapshot_reader)
weather_snapshot_reader.bind(atmosphere_controller)
```

This should run before the first call to `update_environment()`. The reader is optional if you want only the visual defaults and simulation-clock sun.

For a replay clock, advance the timestamp each frame and hand the same value to the reader so `simulation_clock` freshness compares against simulated time:

```gdscript
simulation_epoch_unix = simulation_start_epoch_unix + ecosystem.elapsed
atmosphere_controller.set_simulation_elapsed(ecosystem.elapsed)
atmosphere_controller.set_simulation_timestamp(simulation_epoch_unix, -6.0)
weather_snapshot_reader.set_simulation_epoch_unix(simulation_epoch_unix)
```

## 4. Replace `update_environment()`

Replace the existing function, which directly changes `ProceduralSkyMaterial` colors and the sun angle, with:

```gdscript
func update_environment() -> void:
	if atmosphere_controller == null or ecosystem == null:
		return

	# The simulation clock drives fallback solar geometry. A weather snapshot
	# that supplies both solar angles keeps priority until
	# clear_weather_solar_override() is called.
	atmosphere_controller.set_simulation_time(
		ecosystem.clock_hour,
		int(spec.get("day_of_year", 196))
	)

	# Ecosystem wind remains the local wind source until a snapshot updates it.
	# The controller merges partial state dictionaries, so this does not erase
	# cloud/precipitation values supplied by the weather snapshot reader.
	var local_weather: Dictionary = {
		"air_temperature_c": ecosystem.air_c,
		"wind_speed_mps": ecosystem.wind.length()
	}
	if ecosystem.wind.length_squared() > 0.0001:
		# ecosystem.wind is treated here as a world-space flow vector. Convert to
		# meteorological FROM direction for the atmosphere controller's API.
		local_weather["wind_direction_deg"] = fposmod(
			rad_to_deg(atan2(-ecosystem.wind.x, ecosystem.wind.y)),
			360.0
		)
	atmosphere_controller.set_weather_state(local_weather)

	for mat: ShaderMaterial in foliage_materials:
		mat.set_shader_parameter("wind_vector", ecosystem.wind)
```

Do not leave the old `sun.rotation_degrees`, `sun.light_energy`, `sky_material.sky_top_color` or `sky_material.sky_horizon_color` assignments in this function; they would overwrite the solar model and physical sky state.

## 5. Optional hydrology-to-terrain wetness

If your terrain shader gets a `uniform float ground_wetness`, add the terrain mesh instances that use that shader to a group named `weather_wetness`. Supply `ground_wetness_fraction` from the hydrology output. The controller will write that uniform only when the field is supplied. It intentionally does not fabricate soil moisture from rainfall alone.

If materials are created later, call:

```gdscript
atmosphere_controller.refresh_wetness_material_cache()
```

## 6. Smoke checks after merge

1. Start clear weather (`precipitation_rate_mm_h: 0`, `cloud_fraction: 0.05`). The physical sky and sun should move with the simulation clock.
2. Set `cloud_fraction` to `0.9`. Clouds should become broad and dense; daylight and ambient energy should dim.
3. Set `precipitation_rate_mm_h` to `8` and `snow_fraction` to `0`. Rain particles should become visible.
4. Set `snow_fraction` to `1` with a positive precipitation rate. Rain should stop and snow particles should become visible.
5. Set `visibility_m` to `1200`; horizon fog should strengthen.
6. Stop updating the snapshot for longer than `max_snapshot_age_seconds`; the reader should reject stale data and leave the last valid render state in place.
7. Run the existing `--smoke-test` and `--capture` pathways and check Compatibility-renderer output, particularly particle visibility and cloud-shell terrain occlusion.
