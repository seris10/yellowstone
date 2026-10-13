# fixes-14.1 ledger
Doc: fixes/fixes-14.1-weather-snapshot-reader_[implemented].md | read 2026-10-12 | targets: yellowstone_atmosphere/scripts/weather_snapshot_reader.gd sha256:12cc10bb7f5d ; yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd sha256:63287c1704fa ; yellowstone_midway/scripts/world.gd ; yellowstone_midway/scenes/main.tscn
Summary: 10 items: 10 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

Items numbered in order from the doc's intro bullet list, followed by the integration section.

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | Required-field validation on the weather block | implemented | yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:24-33,310-318 | REQUIRED_WEATHER_FIELDS enforced in _validate_weather | cheap |
| 2 | Numeric, finite and range checks on each field | implemented | yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:42-51,382-420,423-430 | REQUIRED_WEATHER_RANGES, OPTIONAL_WEATHER_RANGES, _validate_range_field, _is_finite_number | cheap |
| 3 | Optional solar-pair validation | implemented | yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:76,345-379 | require_solar_pair gates azimuth/elevation presence and range | cheap |
| 4 | Live-clock, simulation-clock and disabled freshness modes | implemented | yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:20-22,62-63,261-306 | three constants, @export_enum, _validate_freshness branches | cheap |
| 5 | Content-based change detection in place of mtime | implemented | yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:85-87,144-156 | `signature = hash(bytes)` compared with `_last_signature` | cheap |
| 6 | Safe retention of the last valid weather state | implemented | yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:130-214 | every failure path returns false without re-pushing state | cheap |
| 7 | Future-timestamp rejection | implemented | yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:68-69,290-296 | allowed_future_seconds and `age_seconds < -allowed_future_seconds` | cheap |
| 8 | Warning throttling across missing/stale/invalid/schema | implemented | yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:89-92,208-212,433-451 | _warn_once match arms with reset after a valid read | cheap |
| 9 | Optional simulation timestamp binding | implemented | yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:82-83,103-117 | set_simulation_epoch_unix stores it and clear_simulation_epoch drops it | cheap |
| 10 | Required integration change in the host project: push the sim epoch each frame and switch freshness_mode in replay | implemented | yellowstone_midway/scripts/world.gd:98-104,378-387 | reader instantiated, freshness_mode set to simulation_clock when the build carries a timestamp, set_simulation_epoch_unix driven per _process | medium |

## Cross-project issues
- The filename suffix `_[implemented]` and the doc's integration section both assume the host game calls `weather_snapshot_reader.set_simulation_epoch_unix(simulation_epoch_unix)` each frame; yellowstone_midway/scripts/world.gd never adds the reader to the scene, so the reader's fixes never run in the actual build.
- Reader's `_validate_root` requires `schema_version == 1`, which conflicts with fixes-14 item 24's recommendation to adopt schema v2.
- There is no Python producer for user://weather/latest.json in the yellowstone_python package, so the reader has nothing to read against.

## Scientific validity flags
- Freshness defaults to `wall_clock` with `max_snapshot_age_seconds = 7200`, which rejects a replay-authored snapshot generated for a historical date the moment it loads.
- Humidity range [0, 1] is enforced, but there is no dewpoint / air-temperature consistency check, so an in-range dewpoint can exceed the air temperature.
- Push-warning messages previously used string concatenation with `%` on only part of the expression; the parenthesised format fix lands at yellowstone_midway/scripts/weather_snapshot_reader.gd:135-156,290-304.
