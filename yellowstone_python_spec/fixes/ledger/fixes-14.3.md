# fixes-14.3 ledger
Doc: fixes/fixes-14.3-yellowstone_atmosphere.md | read 2026-10-12, open rows re-verified 2026-10-13 | targets: yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd ; yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader ; yellowstone_atmosphere/docs/integration_patch.md sha256:d46ee264453e ; yellowstone_midway/scripts/yellowstone_atmosphere.gd ; yellowstone_midway/shaders/yellowstone_cloud_shell.gdshader ; yellowstone_midway/scripts/world.gd
Summary: 15 items: 14 implemented, 0 shortcut, 1 partial, 0 missing, 0 superseded, 0 conflicts

Items follow the doc's own numbered sections 1 through 11.

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | Add simulation-time exports and state (utc_offset, smoothing, solar override state) | implemented | yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:24-47,81-90,109-124 | all named vars present, _solar_override_* and _weather_target wired | cheap |
| 2 | Replace configure() to initialize weather, defaults and timestamp path | implemented | yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:130-158 | sets WEATHER_DEFAULTS, _weather_target, and chooses timestamp or hour path | cheap |
| 3 | Add timestamp-driven set_simulation_timestamp / clear and keep legacy set_simulation_time | implemented | yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:163-196 | timestamp API coexists with hour/day API, override cleared on legacy call | cheap |
| 4 | Date-aware solar calculation (local epoch -> date -> day_of_year, NOAA fallback) | implemented | yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:624-661 | _update_solar_position_from_timestamp + _day_of_year_for_date + NOAA gamma series | cheap |
| 5 | Replace set_weather_state to validate, clamp, override solar and update targets | implemented | yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:204-227,310-351 | iterates WEATHER_DEFAULTS keys, rejects non-finite, _validate_and_clamp_weather, _update_solar_override | cheap |
| 6 | Smooth weather interpolation with wind-angle shortest path | implemented | yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:360-381,494 | _update_weather_interpolation runs each _update_atmosphere delta, wind_direction uses `(dt + 180) mod 360 - 180` | cheap |
| 7 | Replace _apply_solar_position with direction-vector look_at | implemented | yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:618-672 | look_at(global_position - sun_from_ground, Vector3.UP) | cheap |
| 8 | Precipitation handling: snow_fraction partitions, intensity from sqrt(rate/full) | implemented | yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:545-556 | matches doc body line-for-line | cheap |
| 9 | Cloud shell: push cloud_base, cloud_top, cloud_vertical_edge_softness uniforms with safe min thickness | implemented | yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:497-520 | thickness clamped to >= 100, uniforms sent each frame and in _create_cloud_shell | cheap |
| 10 | _is_finite_number helper | implemented | yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:601-604 | returns is_finite(float(value)) after int/float type check | cheap |
| 11 | Integration update in the host project (spec.simulation_epoch_unix, utc_offset, replay feed) | implemented | yellowstone_midway/scripts/world.gd:4-5,80-104,378-387,397-422 | integration applied: AtmosphereController + WeatherSnapshotReader instantiated, PhysicalSkyMaterial, update_environment delegates to controller, simulation epoch advanced per frame | medium |

Additional notes against the doc that are not numbered items:

| sub | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 2a | configure() uses AMBIENT_SOURCE_SKY in compat note | partial | yellowstone_midway/scripts/yellowstone_atmosphere.gd:252 | still `_environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR` (doc flagged this as acceptable renderer-specific fallback) | cheap |
| 5a | _apply_weather_state immediate path | implemented | yellowstone_midway/scripts/yellowstone_atmosphere.gd:354-362 | smoothed branch now calls _apply_weather_state_immediate so the first push does not wait a tick | cheap |
| 6a | _update_atmosphere starts with _update_weather_interpolation(delta) | implemented | yellowstone_midway/scripts/yellowstone_atmosphere.gd:530-533 | duplicate _update_precipitation_amounts / _update_environment_from_weather calls removed, interpolation path owns both | cheap |
| 9a | Cloud shell scale uses `maxf(cloud_thickness, 100.0)` guard | implemented | yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:498,502 | `cloud_thickness: float = maxf(float(_weather["cloud_thickness_m"]), 100.0)` | cheap |

## Cross-project issues
- Section 11's integration code (`atmosphere_controller.set_simulation_timestamp(...)` / `set_simulation_time(...)`) is not called from yellowstone_midway/scripts/world.gd; the controller sits in a sibling folder that project.godot's main scene never loads.
- Doc section 9 instructs the shader to accept `cloud_density`, which the controller sets (yellowstone_atmosphere.gd:514), but the shader uses `cloud_density` only as an alpha multiplier (gdshader:157); separation of coverage, opacity and density is partial, consistent with fixes-14 item 9.
- The doc's `simulation_epoch_unix` consumer `spec.has("simulation_epoch_unix")` requires the ecosystem spec to carry it; yellowstone_python/yellowstone_python/replay/river_world.py exports `simulation_start_epoch_unix` and `simulation_time.start_epoch_unix` but not under the key the integration doc expects.

## Scientific validity flags
- NOAA fallback at yellowstone_atmosphere.gd:647-661 passes `_clock_hour` into the equation of time correction as civil time, then adds `-60 * simulation_utc_offset_hours`; the input is already local, so the correction double-shifts around DST transitions.
- `_update_solar_position_from_timestamp` adds `simulation_utc_offset_hours * 3600` to the epoch (line 625) and feeds the shifted epoch to `Time.get_datetime_dict_from_unix_time`, which Godot documents as UTC: the resulting "date" is already offset, so day-of-year rolls at local midnight rather than UTC midnight. Consistent with the fallback but inconsistent with the schema's UTC-authoritative framing.
- `_validate_and_clamp_weather` silently clamps every field (lines 340-351) without flagging that the input left the physical range, so a provider that ships `relative_humidity = 1.4` renders as 1.0 with no provenance note.
