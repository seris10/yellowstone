# fixes-36: wildlife and player
Scope: yellowstone_midway/scripts/wildlife_actor.gd sha256:fc27b8ece6b4 ; yellowstone_midway/scripts/player.gd sha256:02137d8742db
Callers read: yellowstone_midway/scripts/world.gd ; yellowstone_midway/scripts/ecosystem.gd ; yellowstone_midway/scripts/python_river_replay.gd ; yellowstone_midway/tools/validate_walk.gd ; yellowstone_midway/tools/validate_ecology.gd

## Main problems

### 1. player gravity uses hardcoded 9.81, physics setting ignored
player.gd:78 `velocity.y -= 9.81 * delta` ignores `3d/default_gravity` from project.godot. The project sets it to `9.81` so no divergence today, but validate_walk.gd sets `Engine.physics_ticks_per_second = PHYSICS_HZ` without touching gravity; a later project.godot change would silently drift.
### Fix
`velocity.y -= float(ProjectSettings.get_setting("physics/3d/default_gravity", 9.81)) * delta`. Keep the clamp at `delta` scope so slow frames do not accumulate a free-fall debt greater than terminal.
### Test
`validate_walk.gd`: set `ProjectSettings.set_setting("physics/3d/default_gravity", 4.9)` and assert the free-fall time to drop 1 m increases by about sqrt(2).

### 2. jump velocity 3.8 and brisk 6.5 are magic numbers
player.gd:68,80. No source for `walk_speed=3.0`, `brisk_speed=6.5`, `jump v_y=3.8`. The export group lacks @export_range so an authoring value of 50 would also apply.
### Fix
Add `@export_range(0.5, 10.0) var walk_speed := 3.0` etc, plus a one-line comment: `# Reference pace from NPS boardwalk signage, 3 mph brisk walk.`
### Test
Scene-smoke: assert `player.walk_speed <= 10.0` on `_ready`.

### 3. _try_step_up re-samples the floor collider every step while on floor and on wall
player.gd:40-52,82-85. Every physics tick where the player presses against a wall AND is on floor, a raycast runs. The ray starts at `global_position + dir * 0.45 + UP * (step_height + 0.9)` and tests downward 1.6 m. For a wall taller than 1.5 m this ray never returns a usable step, but is cast anyway. For a Compat GPU this is a cheap test but still wasteful under heavy wildlife counts.
### Fix
Gate the ray on `rise_possible = flat.length() > 0.04 and not fly_mode and velocity.y <= 0.0`. Current check includes the first two; add the third.
### Test
No functional change required; cheap.

### 4. wildlife_actor FAUNA table hard-codes species-to-asset mapping
wildlife_actor.gd:40-47 keys on `_kind` strings. Adding a species requires editing GDScript. The authored ecosystem JSON could carry an `asset_manifest_id` referencing `data/asset_manifest.json`.
### Fix
Load `data/asset_manifest.json` once in `setup()` and consult it before the hardcoded FAUNA table. Keep FAUNA as the fallback.
### Test
`validate_ecology.gd`: temporarily remove `rainbow_trout` from FAUNA, assert the asset still loads from the manifest.

### 5. wildlife_actor._build_route rejects routes longer than 200 m
wildlife_actor.gd:250-252 `if length_m > 200.0: push_error(... "exceeds authored 200m scope"); _route.clear()`. The 200 m threshold is scope policy from the ecosystem file; the limit should be a parameter so a future longer trail does not require a code edit.
### Fix
Read `max_route_length_m` from `record` with default 200. Record source in a one-line comment.
### Test
`validate_ecology.gd`: build a route of 205 m with `max_route_length_m: 300`, assert `_valid`.

### 6. _move_toward_target advances river routes without reassigning y from water elevation
wildlife_actor.gd:381-401. River media reuse saved water elevation at route construction time (lines 229-231) and interpolate linearly between saved points. If upstream Python replay changes the water surface over the simulated day, the fish height does not update.
### Fix
When `_medium in ["river", "river_bank"]`, call `_ecosystem.river_state_at_position(next, _river_id)` and clamp `next.y` to `water_surface_m` for `river` and to `max(bank_m, water_surface_m)` for `river_bank`. Requires `river_state_at_position` to return `water_surface_m` (python_river_replay already carries point y but does not surface it per-cell).
### Test
`validate_ecology.gd` under replay: assert fish y-position changes when the replay carries a varying water elevation column.

### 7. wildlife_actor._face reads `-direction.x, -direction.z` for the yaw target
wildlife_actor.gd:403-407. For a direction `(1, 0, 0)` (east), `atan2(-1, 0) = -PI/2`, so the body rotates to face +Z local. The convention is "model forward is -Z" per Godot default, so yaw aligns the model's -Z with the direction vector. The negatives are correct, but the comment "yaw PI turns them to Godot-forward (-Z)" in FAUNA block (line 37) implies yaw PI, which is only applied to the asset instance (line 130), not to _face. Document the two-step: FAUNA.yaw aligns the GLB forward, _face rotates the body node.
### Fix
Add comment at wildlife_actor.gd:403:
```gdscript
# Body yaw aligns the local -Z axis with the direction vector; FAUNA.yaw
# rotates the GLB first so its mesh forward also lines up.
```
### Test
None, documentation.

# Wiring and rendering
- wildlife_actor.gd is instantiated by world.make_wildlife() for each record in `ecosystem.params.wildlife`.
- It calls `ecosystem.patch()` for habitat state, `ecosystem.river_state_at_position()` or `reach_at()` for fish state, `set_grazer_activity` / `set_insect_forager_activity` for feeding, and `unregister_actor` on exit.
- Rendered assets: GLBs under `assets/imported/fauna/` plus a shape-proxy fallback.
- player.gd is loaded as `Walker` by world.gd; it owns the camera, pitch, step-up, and the "catch-all teleport-home at world edge" fallback (lines 86-88).

# Comment-style violations
| file:line | text | rule |
| yellowstone_midway/scripts/player.gd:3 | `## Distances in meters, velocities in meters/second. Camera does not bob by default.` | "does not bob by default" is a what-it-does-not statement |
| yellowstone_midway/scripts/player.gd:41 | `# Probe head height ahead, then down.` | passable |
| yellowstone_midway/scripts/player.gd:82 | `# Step-up assist for boardwalk lips and deck edges: snap alone pulls downward.` | borderline, "snap alone pulls" is a hypothetical-failure |
| yellowstone_midway/scripts/wildlife_actor.gd:3-5 | `## Articulated shape proxies at approximate real dimensions. Routes and counts authored in JSON. Actors never sample new habitat at runtime.` | "never" is a hypothetical-failure |
| yellowstone_midway/scripts/wildlife_actor.gd:37-39 | `## Licensed third-party fauna models. Models face +Z as shipped; yaw PI turns them to Godot-forward (-Z). "ground" places the AABB bottom at y=0; "center" centers vertically (fish). Per-individual tint from record.individual.tint_rgb.` | multi-line docstring; "turns them to" addresses reader |
| yellowstone_midway/scripts/wildlife_actor.gd:84 | `# Licensed model instantiated.` | passable |
| yellowstone_midway/scripts/wildlife_actor.gd:108 | `## Instantiate the licensed model, normalize to the record's body length, apply individual tint. Returns false when asset or record length missing.` | borderline, long docstring |
| yellowstone_midway/scripts/wildlife_actor.gd:207 | `# No fallbacks to thermal pools or unknown tributaries.` | hypothetical-failure |
| yellowstone_midway/scripts/wildlife_actor.gd:397 | `# River routes interpolate saved water elevations.` | passable |
| yellowstone_midway/scripts/wildlife_actor.gd:432 | `# Asset-backed model has no tail node; whole-body roll.` | passable |
| yellowstone_midway/scripts/wildlife_actor.gd:559-561 | `# Mesh construction has a 0.31m beak-to-tail envelope before scaling. Species sizes: 0.20m dipper, 0.55m raven.` | multi-line; borderline |
| yellowstone_midway/scripts/wildlife_actor.gd:600 | `# Offsets recorded individually.` | passable |

# Priority order
1. item 1 (gravity from ProjectSettings) - cheap
2. item 3 (step-up ray gate) - cheap
3. item 5 (route length param) - cheap
4. item 2 (walk/brisk @export_range) - cheap
5. item 7 (face/FAUNA.yaw comment) - cheap
6. item 4 (FAUNA from asset_manifest.json) - medium
7. item 6 (river actor y from replay) - medium; depends on fixes-35 item 4
