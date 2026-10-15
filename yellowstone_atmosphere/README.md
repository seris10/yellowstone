# Yellowstone dynamic atmosphere for Godot 4.5

A small, modular atmosphere renderer designed for the existing Yellowstone scene, including its Compatibility-renderer target. It uses a three-band single-scattering sky shader, a procedural cloud layer, conditional rainbows, camera-following GPU rain/snow particle emitters, and weather-driven distance fog.

## What is included

- `scripts/yellowstone_atmosphere.gd`: atmosphere, solar geometry, clouds, particles, fog and optional ground-wetness material binding.
- `shaders/yellowstone_cloud_shell.gdshader`: four-sample cloud layer with cached 3D noise, directional density shading and sky-depth terrain occlusion.
- `scripts/atmosphere_optics.gd`: shared cloud field, spherical-drop geometry, Fresnel ratios and advected liquid-rain history.
- `shaders/rainbow.gdshader`: primary and weaker reversed secondary scattering constrained to the illuminated liquid curtain.
- `shaders/physical_daylight.gdshader`: linear three-band daylight and night-star rendering.
- `scripts/weather_snapshot_reader.gd`: validates and polls an externally produced weather JSON snapshot. It does not make network requests.
- `examples/latest_weather.example.json`: documented snapshot shape with example values. These are illustrative, not a real observation.
- `docs/integration_patch.md`: precise integration changes for the main world script.

## Simulation clock and weather API

`set_simulation_timestamp(epoch_unix, utc_offset_hours)` is the authoritative clock input. Local date, day of year, and civil hour derive from it, which keeps leap years, month boundaries, and historical replay dates correct. `set_simulation_time(hour, day_of_year, utc_offset)` remains for callers that hold only a clock hour, and `clear_simulation_timestamp()` returns to that path.

- `simulation_utc_offset_hours`: Yellowstone civil offset for the simulated date, UTC-7 in winter and UTC-6 in summer. A supplied offset argument wins.
- `clear_weather_solar_override()`: drop a weather solar override and return to simulated solar geometry.
- `set_weather_state()`: partial states merge into the current weather. Non-finite fields are rejected with a warning, a half-solar state is ignored, and accepted values are clamped to documented ranges.
- `smooth_weather_transitions` / `weather_transition_seconds`: ease cloud geometry, visibility/fog, particle rates and light color with `weather_transition_seconds / time_scale`. Air, wind, wetness and snow-cover values come directly from accepted Python frames. Set `weather_transition_seconds = 0` for immediate visual application.
- `set_simulation_elapsed(seconds)` binds transient cloud/rain history to accepted simulation progress. Call each frame with the replay elapsed time; pause, backend holds and exhausted buffers then freeze history. Backward seeks reset transient history; pass `reset_on_rewind=false` for live-clock corrections that should wait at the consumed watermark. Without this binding, `time_scale` advances the standalone controller.
- `get_render_state()` reports the timestamp, solar override state, and the render values it applied.

## Renderer and scientific scope

The daylight shader integrates a lower scattering column with Rayleigh and aerosol phase functions. An upper ozone column attenuates the incident sunlight. Its RGB radiance remains linear through luminance-based display compression; stars appear at night. Coefficients and display limits are documented in [the surface methods](https://github.com/seris10/yellowstone/blob/main/yellowstone_midway/docs/SURFACE_RENDERING.md). The cloud layer is procedural and artistically shaded, not a full volumetric cloud simulation or radiative-transfer model. The precipitation particles visualize input precipitation rate and phase; they do not calculate those values. The controller intentionally does not infer rain/snow phase from a 0  degrees C cutoff. Feed `snow_fraction` from the meteorological pipeline, ideally using wet-bulb temperature and humidity.

The Midway production project uses Godot's Mobile renderer; Compatibility remains selectable. This package does not enable built-in volumetric fog, which Godot documents as Forward+-only. Procedural clouds and GPU particles are the supported fallback. A true ray-marched volumetric cloud implementation should be a separate Forward+ quality tier, not silently enabled on this renderer.

## Install

Copy the two folders into the Godot project, preserving these exact paths:

```text
res://scripts/yellowstone_atmosphere.gd
res://scripts/atmosphere_optics.gd
res://scripts/weather_snapshot_reader.gd
res://scripts/weather_http_consumer.gd
res://shaders/yellowstone_cloud_shell.gdshader
res://shaders/physical_daylight.gdshader
res://shaders/rainbow.gdshader
```

Apply `docs/integration_patch.md` to the main world script. Keep the project's existing `DirectionalLight3D`, `Environment`, player, terrain, and ecosystem. The controller installs its sky material on the supplied Environment and creates its cloud, rainbow and precipitation nodes.

If the world creates terrain/material instances after the atmosphere controller is configured, call `atmosphere_controller.refresh_wetness_material_cache()` after they enter the scene tree.

## Snapshot contract

The reader polls `user://weather/latest.json` by default. That path resolves to Godot's per-project user data directory. An external Python ingest process should discover or configure that directory explicitly, write a complete temporary JSON file, then atomically replace `latest.json`. Do not let two processes write the same file in place.

Required fields:

```json
{
  "schema_version": 1,
  "generated_at_unix": 1791763200,
  "weather": {
    "air_temperature_c": 6.5,
    "dewpoint_c": 1.2,
    "relative_humidity": 0.68,
    "wind_speed_mps": 4.4,
    "wind_direction_deg": 245.0,
    "cloud_fraction": 0.74,
    "cloud_base_agl_m": 820.0,
    "cloud_thickness_m": 760.0,
    "precipitation_rate_mm_h": 1.8,
    "snow_fraction": 0.0,
    "visibility_m": 11500.0,
    "ground_wetness_fraction": -1.0
  },
  "solar": {
    "solar_azimuth_deg": 221.4,
    "solar_elevation_deg": 32.8
  }
}
```

The timestamp above is an example value only. Use the actual UTC time the normalized snapshot was generated.

### Weather fields

- `air_temperature_c`: near-surface air temperature after local correction.
- `dewpoint_c`, `relative_humidity`: atmospheric moisture inputs.
- `wind_speed_mps`: speed at the selected model level/height represented by the feed.
- `wind_direction_deg`: meteorological direction **from which** the wind blows, degrees clockwise from north.
- `cloud_fraction`: 0 clear to 1 overcast, normalized from the forecast/analysis source.
- `cloud_base_agl_m`, `cloud_thickness_m`: rendering geometry inputs in meters above local ground.
- `precipitation_rate_mm_h`: liquid-equivalent precipitation rate. The renderer maps this to particle density, not a precise drop count.
- `snow_fraction`: fraction from 0 (all rain) to 1 (all snow); calculate outside the renderer.
- `visibility_m`: approximate horizontal visibility used for atmospheric haze/fog.
- `ground_wetness_fraction`: optional hydrology-derived value from 0 to 1. `-1` means omit it and leaves terrain materials untouched.
- `solar_azimuth_deg`, `solar_elevation_deg`: optional, but recommended for live mode. Supply both from the timestamp/park location (for example, a Python `pvlib` calculation). If both are absent, GDScript calculates a fallback solar position from the simulation hour, day of year and configured UTC offset.

The sample `source` metadata is for human provenance only. The reader does not claim a forecast is validated because it contains `HRRR` or `RTMA` in a label.

## Quality and performance notes

- Default particle counts are 1,800 rain and 1,200 snow particles. Reduce those exports on low-end machines.
- One sky-depth quad uses a cached 64x64x64 cloud-density texture and 16 trilinear reads per visible sky fragment. World-space drift follows the supplied wind.
- Cloud altitude is independent of the camera far plane. The retained `cloud_radius_m` export is a legacy scene property and does not bound the analytic layer.
- A second quad renders rainbows only when liquid history and direct sun permit scattering. No rainbow appears at clear startup; weather toggles do not reseed visibility.
- [Atmospheric optics](docs/atmosphere-optics.md) records the authored spatial assumptions and uncalibrated frequency.
- Godot 4.5.1 native fixtures on Apple M4 verify clear/broken clouds, a forced double rainbow, dry/night negatives and opaque foreground occlusion in Mobile and Compatibility. Each active layer adds one draw call and two triangles in that fixture; fragment cost and full-world frame rate require separate profiling.
- Native analytical checks cover 3,236 optical/history/coverage cases, 16 cardinal/light/wind assertions seven canonical file pairs and 25 accepted-clock/live-wind integration cases. Visual acceptance remains a separate review.

## Reference documentation

- [Godot PhysicalSkyMaterial](https://docs.godotengine.org/en/stable/classes/class_physicalskymaterial.html)
- [Godot Environment](https://docs.godotengine.org/en/stable/classes/class_environment.html)
- [Godot GPUParticles3D](https://docs.godotengine.org/en/stable/classes/class_gpuparticles3d.html)
- [Godot renderer feature matrix](https://docs.godotengine.org/en/stable/tutorials/rendering/renderers.html)
