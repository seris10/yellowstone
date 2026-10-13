# fixes-36 ledger
Doc: fixes/fixes-36-wildlife-player.md | read 2026-10-12 | targets: yellowstone_midway/scripts/wildlife_actor.gd sha256:8077f6a69cf3 ; yellowstone_midway/scripts/player.gd sha256:b73b4dab0f1b
Summary: 7 items: 7 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | Player gravity from physics/3d/default_gravity | implemented | scripts/player.gd:81 ProjectSettings.get_setting("physics/3d/default_gravity", 9.81) | Project default still 9.81. | cheap |
| 2 | walk/brisk/step/jump @export_range plus a reference-pace comment | implemented | scripts/player.gd:4-10 @export_range on walk_speed, brisk_speed, step_height, jump_speed, mouse_sensitivity | jump_speed replaces inline 3.8. | cheap |
| 3 | _try_step_up gated on velocity.y <= 0.0 | implemented | scripts/player.gd:88 adds `and velocity.y <= 0.0` guard | Prevents airborne ray cast. | cheap |
| 4 | FAUNA from asset_manifest.json with fallback to hardcoded table | implemented | scripts/wildlife_actor.gd:52-78 add `_manifest_fauna()` and `_resolve_fauna()`; wildlife_actor.gd:116-118 call site uses the resolver | Reader looks for a top-level `wildlife_species_asset_map` block in data/asset_manifest.json; absence falls through to FAUNA. | medium |
| 5 | max_route_length_m is a per-record parameter | implemented | scripts/wildlife_actor.gd:249-253 reads record.max_route_length_m default 200 | Error message now parameterized. | cheap |
| 6 | Fish y clamped to replay water_surface_m per step | implemented | scripts/python_river_replay.gd:140-152 cell state carries water_surface_m; python_river_replay.gd:218-226 interpolates depth and surfaces `water_surface_m = bed_elevation_m + depth`; scripts/wildlife_actor.gd:395-407 clamps `next.y` to `water_surface_m` for river/river_bank | Replay cells seed `water_surface_m` from `position_xyz[1]`; a per-frame surface comes from the optional `depth_m_cells` + `cells[i].bed_elevation_m` pair. See handoff. | medium |
| 7 | _face comment: FAUNA.yaw aligns GLB, body yaw aligns direction | implemented | scripts/wildlife_actor.gd:405-406 two-line comment on the two-step orientation | Documentation only. | cheap |

## Cross-project issues
- Item 4 reader is in place; populating `wildlife_species_asset_map` in data/asset_manifest.json is a separate authoring task. Current manifest has no such block, so the hardcoded FAUNA stays in effect.
- Item 6 plumbing is live and the Python replay now publishes `frames[].depth_m_cells` (array aligned with `cells`) and `cells[].bed_elevation_m` from `replay/river_world.py` (bed = authored centerline y minus the cell's wetted depth; the depth array repeats the authored per-cell depth under the current constant-depth solver). The Godot replay reads both to form a per-cell water surface instead of falling back to the first-frame `position_xyz[1]`. A future dynamic-depth hydraulic model would replace the repeated-array behavior with step-varying depths.

## Scientific validity flags
- Item 6: `frames[].depth_m_cells` now ships, but each frame repeats the authored constant depth under the current solver; a time-varying water surface requires a dynamic-depth hydraulic model. `bed_elevation_m` is derived from the authored centerline y minus the authored wetted depth, not from surveyed bathymetry.
