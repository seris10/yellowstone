# fixes-44: Godot consumption of live Python state, and transitions the player can watch

Scope: the Godot side of the live simulation in fixes-43, plus the Python exporters that decide what Godot shows. Targets `yellowstone_midway/scripts/` (`world.gd`, `ecosystem.gd`, `python_river_replay.gd`, `wildlife_actor.gd`, `weather_http_consumer.gd`, `weather_snapshot_reader.gd`), `yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd`, and `yellowstone_python/exporters/godot_sidecars.py` and `llm_backend.py`. Audit 2026-10-13 at the request of KJR.
Method: read-only survey of the Godot scripts with file:line evidence (spot-checked: no Godot script references `refuge`; the T key handler at `world.gd:649`; `weather_http_consumer.gd` is referenced only by itself and `tools/validate_atmosphere_canonical.gd`); `godot_sidecars.py` read end to end. Headless runs were not part of this audit.

## Current state

Godot reads `ecosystem.json`, `world.json`, `season.json`, the replay pair and the optional sidecars once at startup (`ecosystem.gd:31-41`, `world.gd:100`, `world.gd:173-182`, `world.gd:224`). Three paths poll while running: `pools_state.json` every 0.3 s by mtime (`world.gd:312-332`), `mat_pigment.png` every frame by mtime with a 3 s cross-fade (`world.gd:366-393`), and the weather snapshot every 15 s (`weather_snapshot_reader.gd:54`). Nothing else updates during play. `ecosystem.gd` steps its own 6-reach heat chain and 3 patches every 1 s (`ecosystem.gd:5-6`, `:100-232`). The study scene plays a fixed 7200 s replay at 1 simulated second per real second and stops at the last frame (`python_river_replay.gd:167-185`).

## Items

### 1. No reload path for Python output
`yellowstone_python/README.md:32` says Godot hot-loads the published files at F5. No script handles F5 or reloads `ecosystem.json`; F5 only means "run" in the editor.
### Fix
Generalize the existing mtime poll (`world.gd:312-332`) into one `DataWatcher` node: a list of published files, each with a reader callback, polled at 1 Hz, applied at the next frame boundary. `ecosystem.json` reload calls `MidwayEcosystem.configure()` with the current clock preserved. Correct the README line to describe what the code does.
### Test
Headless: publish a changed `ecosystem.json` while a scene runs; the ecosystem reports the new boundary flow within 2 s and the clock does not reset.
### Cost
Cheap.

### 2. The HTTP client exists but is never created, and targets the wrong port
`YellowstoneWeatherHttpConsumer` (threaded `HTTPRequest`, 5 s timeout, `weather_http_consumer.gd:104-107`) is never instantiated by `world.gd` (`:152-158` creates only the snapshot reader). It defaults to `127.0.0.1:8001/api/weather` (`:8`, `:74-81`); `llm_backend` serves on 8765 (`llm_backend.py:1060`).
### Fix
New node `LivePythonClient` built on the same `HTTPRequest` pattern: probe `GET /api/live/schema` at startup (1 s timeout) to pick live or baked mode (fixes-43 item 13); poll `GET /api/live/frames?after_t_s=` at 4 Hz; send controls with `POST`. Port and host from one project setting (`yellowstone/live_url`, default `http://127.0.0.1:8765`). Either retire `weather_http_consumer.gd` or point it at the same setting; one HTTP client per project.
### Test
`tools/validate_live_client.gd` runs against a stub server and checks mode selection, frame append and control round trip.
### Cost
Medium.

### 3. Replay playback cannot extend, truncate or speed up
`python_river_replay.gd` loads all frames once, clamps elapsed time at the last frame and sets `replay_finished` (`:167-185`); playback is 1 simulated second per real second through the parent's accumulator (`:172-181`).
### Fix
Turn the frame list into a ring buffer: `append_frames(chunk)` adds frames after the current end, `truncate_after(t_s)` drops frames after a control time, and the interpolator reads `[t_player, t_player + H]` (`:187-226` already interpolates between frames). The player clock advances at `time_scale` simulated seconds per real second; when the buffer runs dry the clock holds and the HUD shows "computing". Baked mode keeps the current behavior.
### Test
A scripted sequence (append, advance, truncate, append) yields monotonic times and interpolated temperatures equal to the frame values at frame times.
### Cost
Medium.

### 4. Trout never act on the refuge Python chooses
`ecosystem.json` trout records carry `refuge_cell_id`, `refuge_chainage_m`, `refuge_rendered_s_m`, `suitability_U` and `thermal_performance`; no Godot script reads them (`world.gd:486` says so). Trout ping-pong along a fixed polyline slice (`wildlife_actor.gd:243-277`, `:414-423`) at `walk_mps * max(0.08, activity)` (`:400`). `fish.json` gives trout_01 polyline points 354 to 357 while `ecosystem.json` gives 374 to 377.
### Fix
In live mode each frame header carries `trout: [{id, refuge_cell_id, refuge_s_m, U, feeding, refuge_drive}]` (fixes-43 items 7 and 8). `wildlife_actor._update_fish` (`:383`) gets a `target_s_m`; the actor rebuilds its route between its current chainage and the target with `river_state_at_position` (`python_river_replay.gd:269`) and swims at a speed from a sustained-swimming value per body length (authored, registered in `param_registry`, shown in field notes). On arrival it holds with the existing hold state. Resolve the 354 versus 374 point-range mismatch at the exporter so one file is the actor authority.
### Test
Headless: feed frames whose refuge moves from s=2873 m to s=35 m; the actor's chainage decreases monotonically and ends within one cell of the target; arrival time equals distance over swim speed within 5 percent.
### Cost
Medium.

### 5. Fish activity is a proxy unrelated to the Python thermal curves
Godot computes `fish_activity = clamp((26 - T) / 8)` (`ecosystem.gd:183`, `python_river_replay.gd:216`). Python computes species-specific `feeding`, `stress` and `refuge_drive` (`fish.thermal_performance`). A player who warms the river sees trout slow down by a line that has no source.
### Fix
Python publishes per-cell `feeding` for the actor species in each frame (or the curve breakpoints once per session so Godot evaluates them locally); the actor swim speed and the feeding flag (`wildlife_actor.gd:495-496`) read it. Delete the `(26 - T) / 8` expressions.
### Test
At a cell where Python reports feeding 0.0, the actor's activity is 0.0; the published curve and the Godot evaluation agree at 10 sample temperatures.
### Cost
Cheap.

### 6. Which properties may be eased in Godot
The request is a reacting world. Simulated state must change only as Python computes it (fixes-43 item 4); some visual state has no dynamics and needs easing so it does not pop.
### Fix
Write the rule into `world.gd` and the atmosphere controller: river temperature, discharge, depth, oxygen, snow cover and actor targets come from frames and are interpolated only between frames. Cloud geometry, fog density, particle rates and light color ease toward the target with `weather_transition_seconds` (`yellowstone_atmosphere.gd:20-21`, `:577-598`), scaled by `1 / time_scale` so a fast clock gives fast weather. Each eased property is listed in one constant array with its time constant.
### Test
At time scale 600 a cloud change reaches 95 percent of its target within 3 real seconds; a river temperature read at a frame time equals the frame value exactly.
### Cost
Cheap.

### 7. Godot runs its own copy of the physics
`ecosystem.gd` steps a 6-reach explicit-Euler heat chain with Newton exchange (`:156-197`), a logistic patch model (`:199-232`), a noon-peaking air curve `sin((clock_hour - 6) * pi / 12)` (`:150-151`, against the Python curve that peaks near 15:00 with `lag_hours`, `microclimate.py:106-109`) and a wind gust formula copied from `microclimate.py:112-115`. In replay mode `world.update_environment` pushes these values into the atmosphere every 0.3 s (`world.gd:743-753`), overwriting the weather snapshot.
### Fix
In live mode `ecosystem.gd` stops stepping physics and becomes a reader of the current frame (air, wind, reach temperatures derived from cells, patch states). In baked mode it plays published Python series instead of recomputing them: publish the hourly air and wind series and patch trajectories from the build, and delete the duplicated equations. `world.update_environment` takes weather from the frame (live) or the snapshot (baked).
### Test
In both modes the HUD air temperature at a given simulated time equals the Python series value at that time; a grep for the copied formulas in `ecosystem.gd` returns nothing.
### Cost
Medium.

### 8. The HUD does not say what is simulated or how
A demonstration of Python science needs the player to see the run mode and the source of each number.
### Fix
A HUD line: mode (`live Python` or `baked build <id>`), `run_mode`, time scale, simulated date and time, and buffer headroom. Field notes (I) gain a "model" panel: per visible quantity, the Python module, the `equations.py` component id and the provenance class from `param_registry` (measured, fitted, authored, illustrative), read from the frame header and the published registries.
### Test
Headless capture of the HUD text in both modes; the field-notes model panel lists the component id for river temperature.
### Cost
Cheap.

### 9. The clock: one authority, a real date, and a T key that holds
The authoritative clock is `ecosystem.elapsed`. `world.json` has `simulation_epoch_unix` null, so the epoch path is off (`world.gd:138-145`) and day of year is hardcoded 196 with UTC offset -6 (`world.gd:149-150`). T adds 2 h (`world.gd:649-651`), which replay mode undoes on the next step (`python_river_replay.gd:175-177`). Season is applied once (`world.gd:222-252`).
### Fix
Live mode: Python owns simulated time and every frame carries `epoch_unix`; Godot derives date, day of year and local hour from it with the site offset. Baked mode: publish `simulation_epoch_unix` in `world.json` from the build's replay start. Time controls go through fixes-45 item 3, so a jump is a control event Python recomputes from.
### Test
After a jump of 2 h the sun elevation and the river frames both refer to the new time; day of year matches the build date.
### Cost
Cheap to medium.

### 10. Published sidecars that no script reads
Never read by Godot: `outflow_foodweb`, `periphyton`, `piscivores`, `river_oxygen`, `river_shading`, `solute_transport`, `ground_heat`, `evapotranspiration`, `snow_cover`, `soil_temperature`, `steam_microclimate`, `substrate_rules`, `winter_grazing`, `outflow_to_replay_lateral`, `species_catalogue` (keyword search over `yellowstone_midway/scripts`). `publish.py:37-59` ships most of them.
### Fix
For each: either a visible consumer (probe overlay value, field-notes line, shader input) or removal from the publish list with the build keeping it as a build artifact. Recommended consumers for the demo: oxygen and shading in the river probe (fixes-45 item 7), piscivore presence as a field-notes line, steam microclimate as fog density near the pools.
### Test
`publish.py` refuses a file in its list that no consumer names in a manifest `data/consumers.json`, which a Godot tool test checks against the scripts.
### Cost
Cheap per file.

### 11. The published weather snapshot reports the night minimum as the air temperature
`write_weather_snapshot_json` sets `air_c = weather.get("night_air_c", 7.0)` (`godot_sidecars.py:498`), estimates dew point as `air_c - 20 * (1 - rh)` (`:551`) while `microclimate.dewpoint_c` (Magnus) exists, stamps `valid_time_unix` and the solar block with the wall clock (`:553-566`) instead of the simulation time, and hardcodes visibility and cloud base (`:578-581`). `llm_backend.py:427-506` repeats the same logic, including a second copy of the Stull (2011) wet-bulb formula (`:464`, `godot_sidecars.py:526`).
### Fix
One function `microclimate.weather_snapshot(epoch_unix, weather_cfg, met_bundle=None)` that evaluates the air curve at the simulation time, uses `dewpoint_c` and `metpy_wet_bulb_temperature` (or the Stull form in one place, cited), and takes solar angles at the simulation time; both the exporter and `llm_backend` call it. Visibility and cloud base carry `authored` status in the snapshot source block.
### Test
At a simulated 16:00 the snapshot air equals `microclimate.air_temp(16.0, ...)`, not `night_air_c`; dew point matches `dewpoint_c` to 0.01 C; one definition of the wet-bulb formula remains in the package.
### Cost
Cheap.

### 12. The plume sidecar follows the 6-reach chain
`write_plume_field_json` reads `river_state.json` (the `hydro_thermal` chain) for the Excelsior and bridge temperatures (`godot_sidecars.py:105-139`).
### Fix
Take both temperatures from replay cells at the Excelsior source cell and the bridge chainage, after fixes-43 item 14.
### Test
The plume source and ambient temperatures equal the replay cell temperatures at those chainages.
### Cost
Cheap.

### 13. Per-frame cost of the river lookup
Each trout projects onto the whole Firehole polyline about twice per frame (`python_river_replay.gd:285-298`, called from `wildlife_actor.gd:386` and `:443`).
### Fix
Cache each actor's last segment index and search outward from it; fall back to the full scan only when the actor jumps.
### Test
Results equal the full scan for 1,000 random positions; profiler time for `river_state_at_position` drops.
### Cost
Cheap.

### 14. Rigged swimming trout from `fish_swim_project`
Candidate asset outside the repository: `~/Downloads/cutthroat-fish_swim_animated.glb` (59 MB; one mesh of 100,282 vertices; three embedded JPEG textures of 40.4, 10.1 and 1.5 MB; a 15-joint spine skin; clips `Hold_1Hz`, `Cruise_2Hz`, `Burst_3Hz`; forward +Z; no physical length, `reference_length_m` null) and the generator `~/Downloads/fish_swim_project/` (`fish_swim.py`, `render_preview.py`, `godot/FishSwimController.gd`, unittest tests). The game's trout today are `assets/imported/fauna/trout/trout.glb` (562 vertices, no skin, no animation) rolled as a whole body (`wildlife_actor.gd:485-486`). The project README and `validation_report.json` state the motion is an illustrative traveling-wave kinematic model, not fitted to trout data, and untested in Godot.
### Fix
- Species: the model is a Yellowstone cutthroat; the simulation's trout are brown and rainbow, and `fish-spec.md:12` records no evidence of cutthroat in the modeled reach. Use the rig as the body for brown and rainbow trout with their own textures, and add cutthroat only with a `THERMAL_SPECIES` profile (fixes-41 Part B item 4) and placement where the species occurs.
- Gait from the model: drive clip and playback rate from the swim speed the actor gets in item 4. Tail-beat frequency follows speed relative to the water (ground speed plus the cell's current velocity, so a trout holding station in flow still beats its tail) and body length (Bainbridge 1958, J. Exp. Biol. 35:109-133, U = L(3f - 4)/4, fitted for tail-beat frequencies above about 5 Hz; lower frequencies are an extrapolation and labeled so). `AnimationPlayer.speed_scale = f_required / f_clip`, clip chosen by nearest preset. Record the relation in `param_registry` as literature, transferred to trout.
- Asset budget: decimate to a few thousand vertices with LODs and resize textures to 1024 or 2048 px before import; set physical length per species through the existing `asset_manifest.json` `wildlife_species_asset_map` (`length_axis: "z"`, yaw), and record source and license (the mesh came from a generator; the README calls it AI geometry) in the manifest.
- Code: fold the clip selection into `wildlife_actor._make_fish` and `_update_fish` (tabs, project style) instead of a second controller script; place `fish_swim.py` as an asset-authoring tool (`yellowstone_midway/tools/` or the `authoring/` subpackage of fixes-47 item 7) and bring it to the house style (fixes-49: semicolon-joined statements, `assert` in library code, `main() -> None`) and pytest (fixes-50 item 3).
### Test
Godot headless import of the decimated GLB finds the AnimationPlayer and three clips; at a commanded speed of 0.5 m/s for a 0.35 m trout the playback frequency equals the Bainbridge value within 5 percent; frame time with 12 actors stays within the current budget.
### Cost
Medium.

## Order
Item 14 after item 4. Items 2 and 3 (client and buffer), then 4, 5 and 7 (trout behavior and one physics authority), then 6, 9 and 8 (transitions, clock, HUD), then 1, 10, 11, 12 and 13. Items 11 and 12 are Python-only and can land first.

## Not tested in this audit
Headless Godot runs; frame-time cost of the proposed buffer; Godot 4.5.1 bake effects of any script change.
