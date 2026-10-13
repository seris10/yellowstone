# fixes-14.5 ledger
Doc: fixes/fixes-14.5-riverworld.md | read 2026-10-12 | targets: yellowstone_python/yellowstone_python/replay/river_world.py sha256:b019618031e3 ; yellowstone_python/yellowstone_python/replay/river_transport.py sha256:092c2a047750 ; yellowstone_python/yellowstone_python/time_utils.py sha256:df79cc185697 ; yellowstone_python/yellowstone_python/build.py sha256:65d9b0265537 ; yellowstone_python/yellowstone_python/microclimate.py sha256:0ebbb16da902
Summary: 16 items: 16 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | import datetime/timezone (or equivalent) for timestamp handling | implemented | river_world.py:29, 43-48 | datetime imported; UTC/parse_simulation_start/timestamp_metadata pulled from time_utils | cheap |
| 2 | add timestamp helpers (parse_simulation_start, timestamp_metadata, validate_duration_and_step) | implemented | time_utils.py:31-105, river_world.py:83-101 | helpers factored into time_utils.py; validate_duration_and_step kept in river_world | cheap |
| 3 | add simulation_start_utc / simulation_start_epoch_unix kwargs to build_mapped_replay and validate step/duration | implemented | river_world.py:994-1010 | both kwargs plumbed; parse_simulation_start called after validate_duration_and_step | cheap |
| 4 | validate world and ecosystem inputs with validate_mapped_inputs | implemented | river_world.py:129-171, 1011 | checks rivers list, river_reaches, boundary keys, duplicate reach ids, lateral source records | cheap |
| 5 | support scheduled source temperatures and add_temperature_pulse helper | implemented | river_world.py:208-231, 1138-1155 | add_temperature_pulse inserts breakpoints; builder uses Series.parse(source["temperature_c"]) | cheap |
| 6 | replace physical_weather with scheduled-air-aware generator | implemented | river_world.py:825-889 | reads weather["air_temperature_c"] as scalar or Series, falls back to diurnal curve with lag | cheap |
| 7 | use the same schedule in energy_met_series (humidity, wind, cloud, shortwave) | implemented | river_world.py:783-923 | _forcing_series_from_weather honors relative_humidity, wind_speed_mps, cloud_fraction, shortwave_w_m2 | cheap |
| 8 | write simulation timestamps into the replay config | implemented | river_world.py:1192-1193 | config carries simulation_start_utc and simulation_start_epoch_unix from timestamp_metadata | cheap |
| 9 | include timestamped weather provenance in replay document | implemented | river_world.py:1232-1246, 1432-1471 | parameter_notes.simulation_time + document.simulation_time + weather_forcing records/air_temperature | cheap |
| 10 | update make_replay to emit simulation_time and move helpers out of a circular import | implemented | river_transport.py:1352-1376, time_utils.py:1-105 | make_replay reads config["simulation_start_epoch_unix"] via time_utils UTC + timestamp_metadata | cheap |
| 11 | add --simulation-start-utc / --simulation-start-epoch CLI args, enforce one of them | implemented | river_world.py:1540-1601 | parser.error if neither provided; args passed to build_mapped_replay | cheap |
| 12 | validate feature_at chainage and order feature records explicitly | implemented | river_world.py:583-614 | sorted feature records by start_s_m; feature_at rejects negative or out-of-range s_m | cheap |
| 13 | validate weather ranges and scheduled series before building a solver | implemented | river_world.py:174-205, 1012 | validate_weather_configuration enforces bounds for humidity/cloud/gust/sw_noon and parses schedulable keys | cheap |
| 14 | reject scheduled source flow explicitly rather than silently coerce | implemented | river_world.py:117-125 | validate_source_record raises on dict-valued flow_m3s with explicit message | cheap |
| 15 | add forcing_time_reference and keep forcing times physical-seconds-after-start | implemented | river_world.py:1432-1438 | forcing_time_reference describes start_epoch_unix anchor and meaning | cheap |
| 16 | add tests for timestamp parsing, weather endpoints, scheduled temp, scheduled flow rejection | implemented | tests/test_river_world.py:371-586 | SimulationClockTests, WeatherScheduleTests, SourceForcingTests cover timestamp parsing, _weather_times endpoints, scheduled-air, pulse-on-schedule, scheduled-flow-rejection; pulse tests follow Series right-continuous semantics (decision 2026-10-12) rather than the doc exemplar's values | cheap |

## Cross-project issues
- time_utils.py was factored out exactly as the doc hinted; build.py already consumes parse_simulation_start/epoch_unix_for_local (build.py:22, 242, 271), so any signature change there must stay backward compatible.
- microclimate.py was not modified and still exposes its own air_temp/wind_at used by non-replay callers; fixes-10 asks river_world to consume these, so a future unification touches both files.
- parameter_notes.simulation_time duplicates document.simulation_time and document.forcing_time_reference; downstream Godot/consumer code should be checked for which key it reads.

## Scientific validity flags
- Air schedule is honored while the diurnal fallback keeps its lag_hours offset; a mixed configuration (some weather keys scheduled, some scalar) is permitted and silently blended with the sinusoidal shortwave fallback at river_world.py:795-802.
- clock_hour is clamped to [0, 24), but the fallback diurnal curve derives sun from (hour - 6 - lag) and lets lag drive values well outside daytime; no physical bound on lag_hours.
- Explicit surface budget still enforces heat_relative_residual <= 1e-9 as the pass gate (river_transport.py:1467); with the implicit linearized accounting this closes the linearized problem, not the nonlinear flux.
