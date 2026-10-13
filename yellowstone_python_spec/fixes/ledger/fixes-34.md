# fixes-34 ledger
Doc: fixes/fixes-34-world-environment.md | read 2026-10-12 | targets: yellowstone_midway/scripts/world.gd sha256:bb209ed02ae5 ; yellowstone_midway/scripts/height_field.gd sha256:222fe409957b ; yellowstone_midway/scripts/map_view.gd sha256:57c9cf78c8d9 ; yellowstone_midway/scripts/authored_placement.gd sha256:5103c95d73de ; yellowstone_midway/tools/validate_atmosphere_canonical.gd sha256:eec64b10dfaf
Summary: 6 items: 6 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | Use simulation epoch for atmosphere clock; drop wall-clock delta divergence | implemented | world.gd:24-26 adds `_simulation_start_epoch_unix`; world.gd:110-113 captures it at _ready; world.gd:507-509 computes `_simulation_epoch_unix = _simulation_start_epoch_unix + ecosystem.elapsed` | Simulation seconds now follow ecosystem.step(); the atmosphere clock holds under non-1x pacing. | medium |
| 2 | Terrain wetness: rename uniform and add mesh instances to the weather_wetness group | implemented | world.gd:138-141 adds terrain_tile members to weather_wetness; shaders/terrain.gdshader:9 declares ground_wetness | Paired with fixes-37 item 1. | medium |
| 3 | FPS cap honors rendering/limits/fps/max_fps project setting | implemented | world.gd:63-65 reads ProjectSettings | 60 fallback preserved. | cheap |
| 4 | authored_placement.refresh frees without awaiting | implemented | scripts/authored_placement.gd:18-27 null-and-free then instantiate | Editor-only path. | cheap |
| 5 | map_view redraw gate | implemented | world.gd:524-525 only queues redraw when map_view.visible | Removes per-tick redraw cost when hidden. | cheap |
| 6 | map_view route polyline XZ projection comment | implemented | scripts/map_view.gd:23 "Top-down projection: y component is discarded." | Comment only. | cheap |

## Cross-project issues
- None.

## Scientific validity flags
- Simulation epoch drift resolved: solar geometry and civil hour now follow ecosystem.elapsed, which both the live and replay ecosystems advance consistently with day_rate.

## Decisions

- Atmosphere canonical copy lives in `yellowstone_midway/scripts/` and `yellowstone_midway/shaders/`. The `yellowstone_atmosphere/` package carries the published release docs and keeps script/shader duplicates synced through `tools/validate_atmosphere_canonical.gd`, which hashes each pair and exits non-zero on drift. The validator run at the end of this pass reported OK.
