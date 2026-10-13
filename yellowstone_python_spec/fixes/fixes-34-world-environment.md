# fixes-34: world and environment
Scope: yellowstone_midway/scripts/world.gd sha256:5833122c042a ; yellowstone_midway/scripts/height_field.gd sha256:222fe409957b ; yellowstone_midway/scripts/map_view.gd sha256:467a3bbf68e7 ; yellowstone_midway/scripts/authored_placement.gd sha256:820ac7735dca
Callers read: yellowstone_midway/scenes/main.tscn ; yellowstone_midway/scenes/study.tscn ; yellowstone_midway/scripts/ecosystem.gd ; yellowstone_midway/scripts/yellowstone_atmosphere.gd ; yellowstone_midway/scripts/weather_snapshot_reader.gd ; yellowstone_midway/scripts/python_river_replay.gd

## Main problems

### 1. simulation epoch advance is wall-clock delta, not simulation seconds
world.gd:380-387 advances `_simulation_epoch_unix += float(delta)` each frame when a replay supplies the epoch. python_river_replay.step advances `elapsed` from frame times already carried by the replay (python_river_replay.gd:172-175,181). The atmosphere clock and the replay clock therefore diverge unless the replay is 1x real-time. The replay also sets `clock_hour` from `_replay["clock_hour0"]`, which `update_environment()` then feeds back into the controller via `set_simulation_time`, so the sun jumps between the per-frame timestamp path and the civil-hour path.
### Fix
When a replay is loaded (ecosystem.has_method("thermal_probe_records") == true), take the authoritative time from `ecosystem.elapsed` and the replay start epoch:
```gdscript
if _has_simulation_epoch and atmosphere_controller != null:
	var replay_elapsed: float = float(ecosystem.get("elapsed"))
	atmosphere_controller.set_simulation_timestamp(
		_simulation_start_epoch_unix + replay_elapsed, -6.0)
```
Store `_simulation_start_epoch_unix` once at _ready instead of mutating `_simulation_epoch_unix`. Drop the fallback `set_simulation_time` inside `update_environment` when a timestamp path is active. Primary source: the controller docstring (yellowstone_midway/scripts/yellowstone_atmosphere.gd:11-14) states the timestamp path is authoritative and the hour path is a legacy fallback.
### Test
`tools/validate_atmosphere_clock.gd`: load a replay with known `simulation_start_epoch_unix`, advance ecosystem one step, assert `atmosphere_controller.get_render_state().simulation_epoch_unix == start + ecosystem.elapsed`.

### 2. terrain wetness uniform is unreachable
world.gd creates and tracks `terrain_materials` (world.gd:34,110-118) but never adds any `MeshInstance3D` using those materials to the `weather_wetness` group that `_cache_wetness_materials` scans (yellowstone_atmosphere.gd:478-488). Separately, terrain.gdshader declares `uniform float wetness` while the controller probes `&"ground_wetness"` (yellowstone_atmosphere.gd:583-589), so even if a mesh joined the group the uniform name would not match.
### Fix
After `collect_terrain_materials(self)` in world.gd _ready, add each owner `MeshInstance3D` to the group:
```gdscript
for mi: MeshInstance3D in get_tree().get_nodes_in_group("terrain_tile"):
	mi.add_to_group("weather_wetness")
```
and rename terrain.gdshader `uniform float wetness` to `ground_wetness`, updating bake_world.gd:37 to set the same key. Keep the default `0.12` so unbaked terrain still reads a flat value. See fixes-37 item 2.
### Test
`tests/multimesh_validation.json` already asserts terrain material lookup; add a line that calls `atmosphere_controller.set_weather_state({"ground_wetness_fraction": 0.6})` then reads `terrain_mat.get_shader_parameter("ground_wetness")` and compares.

### 3. Engine.max_fps hard-coded at 60
world.gd:42 pins `Engine.max_fps = 60`. The comment says "Compatibility renderer cooks laptops" but a user running on a desktop or at a different display rate loses that choice.
### Fix
Read `rendering/limits/fps/max_fps` from project settings or expose an exported variable; fall back to 60 only when unset.
### Test
Headless `--check-only` plus a `--quit-after 300` run with `rendering/limits/fps/max_fps=0` (uncapped) in project settings: assert Engine.max_fps remains 0.

### 4. authored_placement.refresh frees without awaiting
authored_placement.gd:18-22 calls `remove_child(preview); preview.queue_free()` then immediately instantiates and adds a new preview. In the @tool context (editor) this is fine, but at runtime a reload during the same frame can leave two orphan instances if an incoming asset is also being queued.
### Fix
```gdscript
if is_instance_valid(preview):
	preview.queue_free()
	preview = null
if asset == null:
	return
preview = asset.instantiate() as Node3D
if preview != null:
	preview.name = "AssetPreview"
	add_child(preview)
```
### Test
Not applicable at runtime; this is editor-only. Document as cheap.

### 5. map_view redraws unconditionally in _draw
map_view.gd:12 does `if not visible or world==null:return` which is correct, but world.gd:391 calls `map_view.queue_redraw()` on every 0.3 s observation tick regardless of `map_view.visible`. On a 60 Hz Compat GPU the redraw is cheap, but a hidden map should not be queued.
### Fix
```gdscript
if map_view != null and map_view.visible:
	map_view.queue_redraw()
```
### Test
Not applicable (performance). Mark as cheap.

### 6. map_view route polyline uses point XZ only
map_view.gd:22-25 builds polylines from `Vector2(p[0], p[2])`. Routes with vertical gain still render as a flat polyline; the Y column of each `points` entry is dropped. This is correct for a top-down map but the comment should state it.
### Fix
Add a one-line comment: `# Top-down projection: y component is discarded.`
### Test
None (comment).

# Wiring and rendering
- world.gd owns the full scene composition: terrain tiles, authored vegetation, wildlife actors, UI, atmosphere, snapshot reader, player, and ecosystem.
- height_field.gd is consumed by wildlife_actor._ground_height, bake_botany.gd, and bake_world.gd. Its triangle diagonal (`fx + fz <= 1.0`) must match the rendered + collision diagonal in bake_world.gd. NOT VERIFIED against the current bake.
- authored_placement.gd only runs in the editor (`@tool`). No runtime consumer.
- map_view.gd reads `world.spec.routes` and `world.player` only; it draws into a `Control` and is independent of ecosystem or atmosphere state.
- The atmosphere controller owns sky/sun/fog; world.gd no longer reads `sky_material.sky_top_color` or sets `sun.rotation_degrees`. Compatibility renderer: PhysicalSkyMaterial renders on Compat per Godot docs.

# Comment-style violations
| file:line | text | rule |
| yellowstone_midway/scripts/world.gd:41 | `# Cap frame rate: uncapped Compatibility renderer cooks laptops.` | hypothetical-failure narrative ("cooks") |
| yellowstone_midway/scripts/world.gd:36 | `# Bake-time environment sets; groups assigned once by bake_world.gd.` | passable, "once" borders on temporal |
| yellowstone_midway/scripts/map_view.gd:3 | `# Cached at ready: _draw runs on every map redraw and must not do I/O.` | hypothetical-failure narrative ("must not") |
| yellowstone_midway/scripts/height_field.gd:3 | `## Shared terrain authority, row zero is north. Triangle interpolation matches rendered/collision diagonals.` | "authority" passable; otherwise OK |
| yellowstone_midway/scripts/authored_placement.gd:4 | `## Add this node in handcrafted_details.tscn, choose a PackedScene, and position it normally.` | addresses reader ("choose", "position") |

# Priority order
1. item 2 (terrain wetness) - medium
2. item 1 (simulation epoch divergence) - medium
3. item 3 (max_fps policy) - cheap
4. item 5 (map_view redraw gate) - cheap
5. item 4 (authored_placement reload) - cheap
6. item 6 (comment on XZ projection) - cheap

# Decisions

- Atmosphere canonical copy: `yellowstone_midway/scripts/{yellowstone_atmosphere.gd, weather_snapshot_reader.gd, weather_http_consumer.gd}` and `yellowstone_midway/shaders/yellowstone_cloud_shell.gdshader`. The `yellowstone_atmosphere/` package tree carries the published release documentation (README, docs, examples) and its scripts/shaders are kept in sync by `yellowstone_midway/tools/validate_atmosphere_canonical.gd`, which exits non-zero on hash drift. The validator is run after any edit that touches an atmosphere file. Rationale: Godot's `preload("res://scripts/...")` and group-based wetness cache resolve against the midway tree at runtime; the external package is a release artifact, not an engine load path.
