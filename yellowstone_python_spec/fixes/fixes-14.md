Yes. `night.relay70.dev` is a good architectural inspiration, but I would **not embed the site or use it as a runtime weather provider**. Its important idea is that the sky is generated from astronomy and arithmetic:

- catalog stars use right ascension, declination, magnitude, and B–V color;
- positions are transformed using local sidereal time and observer coordinates;
- unresolved stars contribute flux to a Milky Way/background field;
- bright stars use a point-spread function instead of hard circular sprites;
- planets and the Moon are computed separately;
- terrain occludes objects below the horizon.

That approach fits your Yellowstone project well.

Relevant references from the site:

- Canonical model: <https://night.relay70.dev/api/skies/main>
- API overview: <https://night.relay70.dev/api>
- Star catalog: <https://night.relay70.dev/data/catalog.json>
- Project description: <https://night.relay70.dev/llms.txt>

---

# Recommended architecture

Use four independent layers:

```text
Simulation time
    ↓
Astronomy clock ───────→ Sun, Moon, stars, planets
    ↓
Weather snapshot ──────→ clouds, fog, precipitation, wetness, haze
    ↓
Terrain/world state ───→ horizon occlusion, snow, wet ground, pool steam
```

The important distinction is:

- **Astronomy is deterministic** and should not depend on a weather provider.
- **Weather is observational/forecast input** and may come from HRRR, RTMA, Open-Meteo, NWS, SNOTEL, or a local bundle.
- **Rendering should consume normalized snapshots**, not raw provider formats.

Your current scripts already have most of this separation. The largest missing piece is a proper **simulation timestamp**, rather than only:

```gdscript
clock_hour
day_of_year
utc_offset_hours
```

---

# 1. Add a real simulation timestamp

A clock hour and day-of-year are not enough for accurate date handling. They cannot reliably represent:

- leap years,
- month/day transitions,
- daylight-saving changes,
- historical replay dates,
- multi-day simulations,
- UTC conversion,
- sidereal time,
- weather snapshot age relative to simulated time.

Add a Unix timestamp to the simulation state:

```gdscript
var simulation_epoch_unix: float = 0.0
var simulation_rate: float = 1.0
var simulation_paused: bool = false
```

For a live simulation:

```gdscript
simulation_epoch_unix = Time.get_unix_time_from_system()
```

For a replay:

```gdscript
simulation_epoch_unix = Time.get_unix_time_from_datetime_string(
    "2026-07-15T16:20:00",
    true
)
```

Then advance it:

```gdscript
func _process(delta: float) -> void:
    if not simulation_paused:
        simulation_epoch_unix += delta * simulation_rate

    atmosphere_controller.set_simulation_timestamp(
        simulation_epoch_unix
    )
```

Use the timestamp as the authority. Derive local date, UTC date, day-of-year, and civil time from it.

---

# 2. Add a timestamp-based atmosphere API

Keep `set_simulation_time()` for compatibility, but add:

```gdscript
func set_simulation_timestamp(epoch_unix: float) -> void:
    if not is_finite(epoch_unix):
        push_warning("Invalid simulation timestamp.")
        return

    _simulation_epoch_unix = epoch_unix

    var utc := Time.get_datetime_dict_from_unix_time(epoch_unix)
    var day_of_year := _day_of_year_from_datetime(utc)

    var hour := (
        float(utc["hour"])
        + float(utc["minute"]) / 60.0
        + float(utc["second"]) / 3600.0
    )

    _day_of_year = day_of_year
    _clock_hour = hour

    if not _solar_from_weather:
        _update_solar_position_from_timestamp(epoch_unix)

    _apply_solar_position()
```

However, this must account for local time. The best approach is to define the simulation timestamp as UTC and calculate the local solar geometry from:

```text
UTC timestamp
latitude
longitude
```

Do not manually maintain a fixed `utc_offset_hours` if exact historical civil time matters. A fixed offset is acceptable for a simplified solar model, but not for a date-accurate replay around daylight-saving transitions.

---

# 3. Use Python for authoritative astronomy

The current GDScript solar calculation is a reasonable fallback, but your Python pipeline is a better place for authoritative astronomy.

Use one of:

- `pvlib` for solar position;
- `astral` for sunrise/sunset;
- `astropy` for higher-precision astronomy;
- `skyfield` with ephemerides for Moon and planets;
- a custom implementation for sidereal stars.

For a normalized snapshot, add:

```json
{
  "schema_version": 2,
  "simulation_time": {
    "epoch_unix": 1784132400,
    "utc": "2026-07-15T22:20:00Z",
    "timezone": "America/Denver",
    "local": "2026-07-15T16:20:00-06:00"
  },
  "solar": {
    "solar_azimuth_deg": 221.4,
    "solar_elevation_deg": 32.8,
    "sunrise_epoch_unix": 1784091000,
    "sunset_epoch_unix": 1784142600
  }
}
```

Then the Godot controller can use the authoritative angles directly while retaining the local fallback.

---

# 4. Build the star sky locally, inspired by Long Night

Do not use the website itself as a renderer. Port its concepts.

## Star data

Download or vendor a catalog once, such as the site’s catalog:

```text
right_ascension_hours
declination_deg
visual_magnitude
b_minus_v
```

Convert it to a compact project asset:

```text
res://data/stars.bin
```

or JSON during development.

Do not fetch the catalog during gameplay.

## Coordinate transformation

For each star:

1. Convert RA/Dec to a direction in the celestial frame.
2. Compute local sidereal time from the simulation timestamp.
3. Calculate hour angle:

```text
H = LST - RA
```

4. Convert to altitude and azimuth:

```text
sin(alt) =
    sin(dec) sin(lat)
    + cos(dec) cos(lat) cos(H)
```

5. Convert the resulting azimuth/altitude to a Godot world direction.

Your Godot axes are documented as:

```text
+X east
+Y up
+Z south
```

For azimuth measured clockwise from north:

```gdscript
func horizontal_to_world(
    azimuth_deg: float,
    elevation_deg: float
) -> Vector3:
    var az := deg_to_rad(azimuth_deg)
    var el := deg_to_rad(elevation_deg)

    return Vector3(
        sin(az) * cos(el),
        sin(el),
        cos(az) * cos(el)
    ).normalized()
```

This agrees with the direction convention already used in your controller.

## Rendering choices

### Compatibility renderer

Use a `MultiMeshInstance3D` with camera-facing quads or points:

- one instance per visible catalog star;
- a small star texture or procedural shader;
- additive blending;
- magnitude controls brightness and size;
- B–V controls color;
- airmass controls extinction and twinkle.

This is the most practical option for your current renderer.

### Forward+ renderer

Use:

- a star dome;
- a custom shader;
- higher-resolution Milky Way flux texture generated offline;
- optional volumetric clouds and fog.

Do not generate 150,000 individual particles in Compatibility mode. Generate a background flux field offline and render only the brighter stars individually.

---

# 5. Implement star photometry

The Long Night approach is valuable because it avoids uniform random stars.

For each visible star, calculate:

```text
flux = 10^(-0.4 * magnitude)
```

A simple extinction model:

```text
extinction_mag = 0.20 * (airmass - 1)
```

Then:

```text
observed_flux =
    intrinsic_flux * 10^(-0.4 * extinction_mag)
```

Use B–V for color interpolation. A practical Godot-side function:

```gdscript
func star_color_from_bv(bv: float) -> Color:
    var stops := [
        {"bv": -0.30, "color": Color(0.66, 0.77, 1.0)},
        {"bv":  0.00, "color": Color(0.78, 0.86, 1.0)},
        {"bv":  0.65, "color": Color(1.0, 0.96, 0.82)},
        {"bv":  1.20, "color": Color(1.0, 0.72, 0.48)},
        {"bv":  1.80, "color": Color(1.0, 0.48, 0.30)}
    ]

    if bv <= stops[0]["bv"]:
        return stops[0]["color"]
    if bv >= stops[-1]["bv"]:
        return stops[-1]["color"]

    for i in range(stops.size() - 1):
        var a: Dictionary = stops[i]
        var b: Dictionary = stops[i + 1]
        if bv <= b["bv"]:
            var f: float = inverse_lerp(a["bv"], b["bv"], bv)
            return a["color"].lerp(b["color"], f)

    return Color.WHITE
```

For visual quality, use a point-spread function instead of a hard disc. A Moffat-like shader profile is appropriate:

```glsl
float moffat(float radius, float a, float b) {
    return pow(1.0 + (radius * radius) / (a * a), -b);
}
```

Bright stars can receive subtle diffraction spikes, but do not apply them to every star.

---

# 6. Add a Milky Way flux layer

The Long Night design is particularly good here: the Milky Way is not a painted band. It is the aggregate unresolved flux of many stars.

A practical implementation:

1. Generate a galactic-coordinate star population offline.
2. Convert each star to equatorial coordinates.
3. Add unresolved flux into a low-resolution spherical or dome grid.
4. Render that grid as a smooth background.
5. Render brighter stars separately.
6. Fade stars between the point layer and flux layer around the limiting magnitude.

For the Yellowstone game, a 512×256 equirectangular texture or a 6-face cubemap generated offline is enough. It remains arithmetic/data-derived while being efficient at runtime.

Apply dust extinction by reducing flux near the galactic plane in selected longitude bands. This will make the Milky Way more textured than a simple noise gradient.

---

# 7. Important bug in `yellowstone_cloud_shell.gdshader`

The cloud sphere is viewed from the inside, but the shader uses:

```glsl
render_mode blend_mix, depth_draw_never, cull_back, unshaded;
```

A camera inside a sphere generally needs the inward-facing surfaces rendered. `cull_back` can cause the cloud shell to disappear or behave inconsistently.

Change to:

```glsl
render_mode blend_mix, depth_draw_never, cull_front, unshaded;
```

or:

```glsl
render_mode blend_mix, depth_draw_never, cull_disabled, unshaded;
```

Use `cull_front` if the shell is always viewed from inside. Use `cull_disabled` if camera behavior can vary.

---

# 8. The cloud shell is not really volumetric

This is not a flaw if intentional, but it should be understood:

```gdscript
_cloud_shell.scale = Vector3(
    cloud_radius_m,
    cloud_thickness * 0.5,
    cloud_radius_m
)
```

This creates a flattened ellipsoid, not a cloud volume with a cloud base and top. The camera follows the player, so the shell can also appear to move in ways that do not correspond to actual atmospheric structure.

Improve it by:

- using a larger spherical or cylindrical shell;
- sampling world-space noise at multiple vertical levels;
- applying altitude-based density;
- adding a shadow/noise layer;
- keeping cloud world coordinates stable;
- moving only the shell origin, not the noise field.

Your shader already uses world-space position, which is the right direction. Add vertical density:

```glsl
float vertical_density(float y) {
    float base = smoothstep(0.0, 0.15, y);
    float top = 1.0 - smoothstep(0.75, 1.0, y);
    return base * top;
}
```

Then multiply cloud alpha by that density.

---

# 9. Cloud rendering should not use cloud fraction as a direct geometric threshold only

Current shader behavior:

```glsl
float threshold = mix(0.82, 0.30, clamp(cloud_cover, 0.0, 1.0));
```

This makes high cloud fraction reveal more noise, which is visually plausible. But cloud fraction should also affect:

- cloud opacity;
- ambient light;
- sun attenuation;
- shadow softness;
- cloud base and thickness;
- precipitation probability.

The controller already dims ambient and sun light:

```gdscript
var cloud_dim: float = cloud_fraction * default_cloud_ambient_dim
```

Add separate controls rather than forcing one variable to control everything:

```gdscript
_cloud_material.set_shader_parameter(
    "cloud_coverage",
    float(_weather["cloud_fraction"])
)
_cloud_material.set_shader_parameter(
    "cloud_density",
    float(_weather["cloud_fraction"]) *
    cloud_opacity
)
```

This permits broad thin cloud and small dense cloud states.

---

# 10. Fix weather snapshot validation

`weather_snapshot_reader.gd` checks:

- file existence;
- JSON parsing;
- schema version;
- timestamp;
- weather object type.

But it does not validate required weather fields or ranges before passing them to the controller.

The schema requires:

```text
air_temperature_c
relative_humidity
wind_speed_mps
wind_direction_deg
cloud_fraction
precipitation_rate_mm_h
snow_fraction
visibility_m
```

Add validation:

```gdscript
const REQUIRED_WEATHER_FIELDS := [
    "air_temperature_c",
    "relative_humidity",
    "wind_speed_mps",
    "wind_direction_deg",
    "cloud_fraction",
    "precipitation_rate_mm_h",
    "snow_fraction",
    "visibility_m",
]

func _validate_weather(weather: Dictionary) -> bool:
    for key in REQUIRED_WEATHER_FIELDS:
        if not weather.has(key):
            push_warning("Weather snapshot missing '%s'." % key)
            return false

    if not _finite_number(weather["air_temperature_c"]):
        return false
    if float(weather["relative_humidity"]) < 0.0 \
    or float(weather["relative_humidity"]) > 1.0:
        return false
    if float(weather["wind_speed_mps"]) < 0.0:
        return false
    if float(weather["cloud_fraction"]) < 0.0 \
    or float(weather["cloud_fraction"]) > 1.0:
        return false

    return true


func _finite_number(value: Variant) -> bool:
    if not (value is float or value is int):
        return false
    return is_finite(float(value))
```

Do not rely on clamping invalid provider data in the renderer. Clamping is useful for defensive rendering, but invalid input should be rejected and reported.

---

# 11. Fix snapshot freshness for replay mode

Current reader compares:

```gdscript
Time.get_unix_time_from_system() - float(root["generated_at_unix"])
```

That is correct for live weather, but wrong for a simulation replay. A snapshot from 2026 may look stale when the simulation is intentionally replaying 2026.

Add two modes:

```gdscript
@export var freshness_mode: String = "wall_clock"
```

Possible values:

```text
wall_clock
simulation_clock
disabled
```

For simulation mode:

```gdscript
var age_seconds := simulation_epoch_unix - float(root["generated_at_unix"])
```

The reader should receive the simulation timestamp from the world/controller.

---

# 12. Fix file-change detection

Current code uses:

```gdscript
var modified: int = FileAccess.get_modified_time(snapshot_path)
if modified == _last_signature:
    return false
```

This can miss a replacement if two files have the same modification-time resolution.

Use a content signature:

```gdscript
func _file_signature(path: String) -> int:
    var file := FileAccess.open(path, FileAccess.READ)
    if file == null:
        return -1

    var bytes := file.get_buffer(file.get_length())
    file.close()

    return hash(bytes)
```

For larger files, use file size plus modification time, or a SHA-256 hash generated by the Python producer.

The atomic replacement strategy described in the README is good. Retain it.

---

# 13. Reset missing/stale warnings appropriately

The reader resets:

```gdscript
_warned_missing = false
_warned_stale = false
```

after a valid update, which is good. It should also reset the missing warning if a file appears later, even if its modified time is unusual. The current flow does that after a valid read.

Add a separate warning when the snapshot is rejected due to schema or required-field validation, but throttle it to avoid log spam.

---

# 14. Fix HTTP polling overlap

`weather_http_consumer.gd` can start another request while the previous one is still in progress.

Add:

```gdscript
var _request_in_flight: bool = false
```

Then:

```gdscript
func poll_now() -> void:
    if _controller == null or _http == null:
        return
    if _request_in_flight:
        return

    _request_in_flight = true
    var error := _http.request(
        endpoint_url,
        ["Accept: application/json"]
    )

    if error != OK:
        _request_in_flight = false
        push_warning("Weather HTTP request could not start: %s" % error)
```

Reset it in the completion callback:

```gdscript
func _on_request_completed(...):
    _request_in_flight = false
    ...
```

---

# 15. Fix endpoint/snapshot provenance

The HTTP consumer writes:

```gdscript
"generated_at_unix": Time.get_unix_time_from_system()
```

This is the client’s clock, not necessarily the provider or server generation time.

The normalized endpoint should return:

```json
{
  "generated_at_unix": 1784132400,
  "observed_at_unix": 1784132100,
  "valid_until_unix": 1784135700,
  "source": {
    "analysis": "RTMA",
    "forecast": "HRRR"
  }
}
```

Then preserve those fields:

```gdscript
snapshot["generated_at_unix"] = root.get(
    "generated_at_unix",
    Time.get_unix_time_from_system()
)
snapshot["source"] = root.get("source", {})
```

If the endpoint has no trustworthy timestamp, mark the snapshot as client-generated.

---

# 16. Fix the weather endpoint contract

The HTTP consumer currently expects flat fields:

```text
air_c
humidity
cloud
wind_xz_mps
```

The snapshot schema expects nested fields:

```text
weather.air_temperature_c
weather.relative_humidity
weather.cloud_fraction
```

Supporting both is reasonable, but define a single normalized API. I recommend making the endpoint return the same schema as the file:

```json
{
  "schema_version": 1,
  "generated_at_unix": 1784132400,
  "source": {},
  "weather": {},
  "solar": {}
}
```

Then the HTTP consumer can simply validate and pass:

```gdscript
var weather := root.get("weather", {})
var solar := root.get("solar", {})
weather.merge(solar, true)
_controller.set_weather_state(weather)
```

This removes duplicate field conversion logic and avoids divergence between HTTP and file behavior.

---

# 17. Fix solar angle priority behavior

The integration patch calls:

```gdscript
atmosphere_controller.set_simulation_time(...)
```

each time `update_environment()` runs.

The controller correctly keeps weather-provided solar angles when:

```gdscript
_solar_from_weather == true
```

However, there is no explicit way to clear that override if the next snapshot omits solar angles. Once a valid snapshot supplies solar values, the controller remains locked to the old weather angles.

Add:

```gdscript
func clear_weather_solar_override() -> void:
    _solar_from_weather = false
    _update_solar_position()
    _apply_solar_position()
```

When a snapshot arrives without a valid solar pair, either clear the override or leave the previous one intentionally. Make the policy explicit.

---

# 18. Fix `set_weather_state()` handling of partial solar fields

Current code:

```gdscript
if has_solar_azimuth or has_solar_elevation:
    _solar_from_weather = has_solar_azimuth and has_solar_elevation
```

If a state contains only `solar_azimuth_deg`, this sets `_solar_from_weather` to false but does not necessarily restore the calculated angle consistently.

Better:

```gdscript
if has_solar_azimuth != has_solar_elevation:
    push_warning(
        "Solar override requires both azimuth and elevation."
    )
elif has_solar_azimuth:
    _solar_from_weather = true
    ...
```

Do not accept a half-solar state.

---

# 19. Check the current sun rotation empirically

This code is potentially fragile:

```gdscript
_sun.rotation_degrees = Vector3(
    -_solar_elevation_deg,
    _solar_azimuth_deg,
    0.0
)
```

Godot’s `DirectionalLight3D` shines along its local negative Z axis. A simple Euler assignment may not map your azimuth convention correctly.

Use a direction vector and `look_at()` or a tested basis:

```gdscript
func _apply_solar_position() -> void:
    if _sun == null:
        return

    var direction := _sun_direction_vector()

    # DirectionalLight3D points along local -Z.
    _sun.look_at(
        _sun.global_position - direction,
        Vector3.UP
    )
```

The exact sign should be verified with a test scene:

- azimuth north, elevation 45°;
- sun should cast shadows toward south;
- azimuth east, elevation 45°;
- sun should cast shadows toward west.

This is safer than relying on Euler intuition.

---

# 20. Move the cloud shell with the camera, but preserve world coordinates

Your shader uses:

```glsl
world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
```

and the controller sends:

```gdscript
cloud_center
```

The noise itself is sampled using:

```glsl
world_pos.xz * cloud_scale + cloud_offset
```

This is good: cloud patterns should not swim when the shell follows the player.

However, `cloud_offset` is advanced by wind:

```gdscript
_cloud_offset += wind_xz * delta * cloud_drift_multiplier * cloud_scale
```

That is visually correct, but the wind vector should use the same coordinate convention as the weather pipeline. Add an explicit comment and test that meteorological FROM direction produces movement in the expected TO direction.

---

# 21. Improve terrain detail and weather interaction

Your atmosphere system can drive a much richer world if the weather snapshot also controls:

- ground wetness;
- puddle mask;
- mud roughness;
- snow accumulation;
- snow melt;
- vegetation bend;
- steam/condensation;
- pool visibility;
- insect activity;
- river temperature;
- cloud shadow strength.

A useful normalized terrain state:

```json
{
  "terrain": {
    "ground_wetness_fraction": 0.64,
    "snow_water_equivalent_mm": 18.0,
    "snow_cover_fraction": 0.32,
    "soil_temperature_c": 2.1,
    "puddle_fraction": 0.08
  }
}
```

Keep this separate from atmospheric weather. `ground_wetness_fraction` should come from `overland_flow.py` or the soil model, not from rainfall alone.

Your current `overland_flow.py` should eventually export:

```json
{
  "ground_wetness_fraction": 0.64,
  "surface_depth_m": [...],
  "runoff_m3": ...,
  "soil_moisture": [...],
  "timestamp_start_unix": ...,
  "timestamp_end_unix": ...
}
```

Then the weather producer can combine it with the atmospheric snapshot.

---

# 22. Integrate river replay time with the sky

`river_world.py` currently creates weather using:

```python
clock_hour
duration_s
```

but does not establish a full calendar date. Add:

```json
{
  "simulation_start_utc": "2026-07-15T22:20:00Z"
}
```

to the ecosystem or replay configuration.

Then both systems use the same timestamp:

```text
river transport forcing
snow/soil forcing
weather snapshot
sun
stars
Moon
cloud state
```

The replay output should contain:

```json
"simulation_time": {
  "start_epoch_unix": 1784154000,
  "end_epoch_unix": 1784161200,
  "timezone": "America/Denver"
}
```

This prevents the river replay from saying “16.2” while the sky independently assumes a different date.

---

# 23. Make weather changes continuous where appropriate

Current weather snapshots are applied as immediate state changes. For visual stability, interpolate selected fields:

Interpolate:

- air temperature;
- wind speed;
- visibility;
- cloud fraction;
- precipitation intensity;
- wetness.

Do not interpolate across:

- invalid snapshots;
- stale snapshots;
- phase transitions without care;
- discrete provider changes if exact replay fidelity is required.

Example:

```gdscript
var _weather_target: Dictionary
var _weather_blend_seconds := 30.0

func set_weather_state(state: Dictionary) -> void:
    _weather_target = state.duplicate(true)

func _update_weather_blend(delta: float) -> void:
    var f := clampf(delta / _weather_blend_seconds, 0.0, 1.0)

    for key in ["cloud_fraction", "wind_speed_mps",
                "visibility_m", "precipitation_rate_mm_h"]:
        if _weather_target.has(key):
            _weather[key] = lerpf(
                float(_weather[key]),
                float(_weather_target[key]),
                f
            )
```

For scientific replay mode, disable interpolation and apply values at exact timestamps.

---

# 24. Use a versioned common weather schema

Your current system has three related but different formats:

1. `latest_weather.example.json`;
2. `weather_state.schema.json`;
3. flat HTTP endpoint fields.

Unify them. I recommend schema version 2 with:

```json
{
  "schema_version": 2,
  "generated_at_unix": 1784132400,
  "valid_time_unix": 1784132400,
  "simulation_time_unix": 1784132400,
  "source": {
    "analysis": "RTMA",
    "forecast": "HRRR",
    "station_correction": "optional"
  },
  "weather": {},
  "solar": {},
  "terrain": {}
}
```

The renderer should accept only the normalized form. Provider adapters should convert into it.

---

# Suggested implementation phases

## Phase 1: fix current integration

1. Change cloud shell culling from `cull_back`.
2. Add required-field/range validation to the snapshot reader.
3. Prevent overlapping HTTP requests.
4. Unify HTTP and file snapshot schemas.
5. Add `simulation_epoch_unix`.
6. Fix solar override clearing.
7. Verify directional-light orientation with a test scene.

## Phase 2: accurate time and astronomy

1. Add UTC simulation timestamps.
2. Generate solar angles in Python with `pvlib`.
3. Add Moon and planet positions with `skyfield` or `astropy`.
4. Vendor a star catalog.
5. Add local sidereal-time star positioning.
6. Render stars with MultiMesh and magnitude/B–V colors.

## Phase 3: Long Night-style sky

1. Generate unresolved-star flux grid.
2. Add Milky Way structure from galactic-coordinate sampling.
3. Add dust extinction and reddening.
4. Add Moffat star point-spread functions.
5. Add bright-star diffraction spikes.
6. Add terrain/horizon occlusion.

## Phase 4: world/weather coupling

1. Add weather timestamps to river and hydrology outputs.
2. Drive terrain wetness from hydrology.
3. Add snow accumulation and melt visual states.
4. Add cloud shadows and precipitation accumulation.
5. Couple pool steam and condensation to humidity/dew point.
6. Use exact replay mode for scientific scenarios and smoothed live mode for visual play.

---

# Bottom line

The best design is:

```text
Python:
  authoritative date/time
  solar geometry
  weather ingestion
  wet-bulb/snow fraction
  hydrology
  normalized snapshots
  optional star/planet ephemeris

Godot:
  deterministic simulation clock
  physical sky
  local star catalog renderer
  procedural Milky Way flux
  clouds
  fog
  precipitation
  terrain wetness
  visual interpolation
```

Use `night.relay70.dev` as a model for **data-driven astronomical rendering**, especially its catalog coordinates, sidereal positioning, flux aggregation, magnitude-dependent point spread, dust, and terrain occlusion. Do not treat its browser page as a dependency. The Yellowstone game can reproduce the core idea locally and extend it with simulation-controlled dates, weather, snow, geothermal steam, river temperature, and terrain state.