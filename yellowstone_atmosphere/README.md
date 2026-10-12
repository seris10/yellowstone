# Yellowstone dynamic atmosphere for Godot 4.x

A small, modular atmosphere renderer designed for the existing Yellowstone scene, including its Compatibility-renderer target. It uses Godot's `PhysicalSkyMaterial`, a procedural transparent cloud shell, camera-following GPU rain/snow particle emitters, and weather-driven distance fog.

## What is included

- `scripts/yellowstone_atmosphere.gd`: atmosphere, solar geometry fallback, clouds, particles, fog and optional ground-wetness material binding.
- `shaders/yellowstone_cloud_shell.gdshader`: world-space procedural cloud field on an ellipsoidal shell. It avoids ray marching and volumetric-fog requirements.
- `scripts/weather_snapshot_reader.gd`: validates and polls an externally produced weather JSON snapshot. It does not make network requests.
- `examples/latest_weather.example.json`: documented snapshot shape with example values. These are illustrative, not a real observation.
- `docs/integration_patch.md`: precise integration changes for the main world script.

## Renderer and scientific scope

`PhysicalSkyMaterial` uses Godot's Preetham analytic daylight model. The cloud layer is procedural and artistically shaded, not a full volumetric cloud simulation or radiative-transfer model. The precipitation particles visualize input precipitation rate and phase; they do not calculate those values. The controller intentionally does not infer rain/snow phase from a 0 °C cutoff. Feed `snow_fraction` from the meteorological pipeline, ideally using wet-bulb temperature and humidity.

The project currently uses Godot's Compatibility renderer. This package therefore does not enable built-in volumetric fog, which Godot documents as Forward+-only. Procedural clouds and GPU particles are the supported fallback. A true ray-marched volumetric cloud implementation should be a separate Forward+ quality tier, not silently enabled on this renderer.

## Install

Copy the two folders into the Godot project, preserving these exact paths:

```text
res://scripts/yellowstone_atmosphere.gd
res://scripts/weather_snapshot_reader.gd
res://shaders/yellowstone_cloud_shell.gdshader
```

Apply `docs/integration_patch.md` to the main world script. Keep the project's existing `DirectionalLight3D`, `Environment`, player, terrain, and ecosystem. The controller reuses the existing physical sky material when possible and owns only the cloud shell and precipitation emitters it creates.

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
- `cloud_base_agl_m`, `cloud_thickness_m`: rendering geometry inputs in metres above local ground.
- `precipitation_rate_mm_h`: liquid-equivalent precipitation rate. The renderer maps this to particle density, not a precise drop count.
- `snow_fraction`: fraction from 0 (all rain) to 1 (all snow); calculate outside the renderer.
- `visibility_m`: approximate horizontal visibility used for atmospheric haze/fog.
- `ground_wetness_fraction`: optional hydrology-derived value from 0 to 1. `-1` means omit it and leaves terrain materials untouched.
- `solar_azimuth_deg`, `solar_elevation_deg`: optional, but recommended for live mode. Supply both from the timestamp/park location (for example, a Python `pvlib` calculation). If both are absent, GDScript calculates a fallback solar position from the simulation hour, day of year and configured UTC offset.

The sample `source` metadata is for human provenance only. The reader does not claim a forecast is validated because it contains `HRRR` or `RTMA` in a label.

## Quality and performance notes

- Default particle counts are 1,800 rain and 1,200 snow particles. Reduce those exports on low-end machines.
- A player-following cloud shell avoids loading a cloud mesh per map tile. The shader uses world-space noise so the cloud field does not slide when the shell recenters.
- The current world has a 4 km authored extent. Tune `cloud_radius_m` and visibility values to the camera scale and terrain boundaries.
- This code has not been run through the project's Godot editor in this environment, because a Godot executable/project directory was not available here. Treat the included integration patch as an implementation draft, then run the project's editor import and smoke test before merging to the working branch.

## Reference documentation

- [Godot PhysicalSkyMaterial](https://docs.godotengine.org/en/stable/classes/class_physicalskymaterial.html)
- [Godot Environment](https://docs.godotengine.org/en/stable/classes/class_environment.html)
- [Godot GPUParticles3D](https://docs.godotengine.org/en/stable/classes/class_gpuparticles3d.html)
- [Godot renderer feature matrix](https://docs.godotengine.org/en/stable/tutorials/rendering/renderers.html)
