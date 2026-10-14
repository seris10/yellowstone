# fixes-45: player controls for manipulating the simulation

Scope: what the player can change today, what should be added so the game demonstrates the Python science, and what each addition requires on the Python side (fixes-43) and the Godot side (fixes-44). Audit 2026-10-13 at the request of KJR.
Method: input handlers in `yellowstone_midway/scripts/world.gd:628-697`, `player.gd`, `thermal_probe_overlay.gd`; `project.godot` input map; `yellowstone_python/study_mode.py` schema and presets read in full where cited.

## Current state

`project.godot` has no `[input]` section; every binding is a raw keycode in `world._unhandled_input` (`world.gd:628-684`). Viewing keys: Esc menu, I field notes, M map, F hide HUD, F3 fly, R return to anchor, K calibration panel, P plume, G geochemistry, U census, J overland, L groundwater, H thermal probes (study scene only, `thermal_probe_overlay.gd:22-25`). Keys that change the simulation: T adds 2 h to the clock (`world.gd:649-651`, undone in replay mode by `python_river_replay.gd:175-177`) and C swaps the pulse and control replays (`world.gd:686-697`). No sliders, menus or time-scale control exist.

Python already defines the control vocabulary. `study_mode.SCHEMA` (`study_mode.py:21-45`) lists bounded keys: `clock_hour`, `weather.night_air_c`, `weather.day_warming_c`, `weather.wind_xz_mps`, `weather.gust_mps`, `weather.humidity`, `weather.cloud`, `weather.lag_hours`, `hydro.boundary_m3s`, `hydro.boundary_c`, `hydro.simulate_seconds`, `insects.flowering_stage`, `fish.food`, `fish.cover`, `snow.season`, `snow.as_of_date`, `snow.days`, `snow.precip_mm_d`, `snow.air_c_by_day`, plus lateral-source patches. `study_mode.PRESETS` (`:192`) defines `hot_surge`, `cold_snap`, `low_flow`, `warm_air_cold_water` and `winter_week`. None of this reaches the game.

## Items

### 1. Named input actions
Raw keycodes cannot be remapped, shown in a help screen, or bound to a gamepad.
### Fix
Add an `[input]` section to `project.godot` with named actions for every binding above and the new controls below; `_unhandled_input` matches actions. A help overlay (F1) lists actions and bindings from `InputMap`.
### Test
A tool script asserts every action has a key and a gamepad binding and that no handler compares raw keycodes.
### Cost
Cheap.

### 2. Conditions panel (Tab)
The core of the request: the player sets temperature, weather, flow and time, and watches the world respond.
### Fix
A panel with sliders generated from `GET /api/live/schema` (fixes-43 item 12), so bounds, units and labels come from `study_mode.SCHEMA` and nothing is hardcoded in GDScript. Groups:
- Air: night minimum, daytime warming, lag (shifts the daily peak).
- Sky: cloud fraction, humidity, wind speed and direction, gust.
- Precipitation: rate (needs a `weather.precip_mm_h` key; the schema has only a daily snow total).
- River: upstream discharge, upstream temperature.
- Thermal sources: Excelsior outflow on or off and its temperature (`hot_surge` uses `patch_laterals`).
Each slider shows its provenance class and the default from the build. Releasing a slider sends one control event at the current simulated time; the panel shows "computing" until the first frame after the change arrives.
### Requires
fixes-43 items 1, 3, 6 (explicit surface budget fast enough for sky controls), 9 and 12; fixes-44 items 2 and 3. Without fixes-43 item 6, cloud, humidity and wind controls change only the sky, because the published river uses the lumped exchange.
### Test
Scripted: move the upstream temperature slider; within the lookahead horizon the frames show the change at the boundary cell first and downstream cells later in order of chainage.
### Cost
Medium.

### 3. Time controls
The accelerated transition the request describes is time compression.
### Fix
Actions: pause, step forward one frame, and time scales 1x, 60x, 600x, 3600x (capped by the measured `live.max_dt_s` and CPU headroom from fixes-43 item 5). A "jump to" control for clock hour and date that Python treats as a control event (season spin-up for snow from 1 October, fixes-43 item 9). The HUD shows the simulated date, time and scale. T keeps its +2 h meaning as a jump.
### Requires
fixes-43 items 4 and 5; fixes-44 items 3 and 9.
### Test
At 600x for 10 real seconds the simulated clock advances 6000 s within one frame interval; pause holds every frame value.
### Cost
Cheap once the buffer exists.

### 4. Presets and scenarios
A guided entry point for players who do not know which slider matters.
### Fix
A preset menu fed by `POST /api/live/preset` with the five `study_mode.PRESETS` plus the documented scenarios: hot low flow (2.5 m3/s, 26 C boundary, from `tools/scenario_constants.py`), tributary cold refuge (Rabbit and Mallard Creek pockets), and a measured-weather day (item 6). Each preset carries a one-line description and the expected response the player should watch for ("trout move upstream to the Mallard Creek pocket"), written from the documented results in `yellowstone_python/README.md`.
### Test
Selecting `hot_low_flow` reproduces, in live mode at 600x, the refuge cell recorded in `derived/aquatic_hot_lowflow.json` within the declared exposure window.
### Cost
Cheap.

### 5. Branch and compare (A/B)
The study scene's C toggle is the seed of the most persuasive demonstration: the same river under two conditions.
### Fix
"Mark A" snapshots the current session state (river checkpoint, ecology state, forcing). Changing conditions then runs B while the engine also advances A from the mark (two engines, or A as a cached run). Godot shows A as ghost trout and a split temperature ribbon along the river; a panel shows `compare.py` metrics (refuge shift, emergence change, dipper intake change) live.
### Requires
fixes-43 items 2 and 11; a second engine instance (CPU budget doubles).
### Test
With identical forcing, A and B frames are equal; after one change, the reported refuge shift equals `aquatic_foodweb.compare_runs` on the two frame sets.
### Cost
Medium.

### 6. Measured-weather mode
The strongest scientific demonstration is the model against observations.
### Fix
A date picker limited to the frozen bundles (`derived/firehole_obs.json`, `derived/snotel_obs.json` windows). Selecting a date runs the engine with measured met forcing and the measured upstream boundary (`run_mode: observed_replay`), and the HUD plots modeled against observed downstream temperature at gauge 06036905 with the RMSE so far. Prescribed boundary quantities are labeled as forcing, not validation (`run_mode.check_split`).
### Requires
fixes-43 item 10 (scheduled boundary), the bundles already in `derived/`.
### Test
For the bundle window, the in-game modeled series equals the offline `run_fit_forward` with the same parameters; the HUD labels discharge as prescribed.
### Cost
Medium.

### 7. Probe tool
The H thermal-probe overlay exists only in the study scene.
### Fix
A global probe action: aim at water to read the cell's temperature, depth, velocity, oxygen, shading factor, trout suitability U and refuge drive; aim at ground for snow water equivalent, soil temperature and vegetation biomass. Each value shows its unit, provenance class and the `equations.py` component id. Holding the probe on a cell opens a strip chart of that cell over the buffered window.
### Requires
Per-cell fields in frames (fixes-43 item 3); published oxygen and shading (fixes-44 item 10).
### Test
The probed values equal the frame values at the player's simulated time.
### Cost
Medium.

### 8. "What Python just did" panel
The request is to demonstrate Python. The player should see the computation, not only its result.
### Fix
After each control event, a panel lists the stages Python recomputed (from the dependency table, fixes-43 item 9), their wall time, the solver step size and health (Courant number, surface iterations), and the governing equation per stage from `equations.py`. A link opens the source file path for each stage.
### Requires
fixes-43 items 5 and 9 (timings and health in frame headers).
### Test
After an upstream temperature change the panel lists the river, oxygen and foodweb stages and none of the snow stages.
### Cost
Cheap.

### 9. Interventions in the world
Physical actions the player can take in place, each mapped to an existing model input:
- Shade a reach (place riparian canopy): per-cell `shortwave_multiplier` (`River` already accepts it, `river_transport.py:499-513`).
- Divert or restore a hot spring outflow: lateral source on or off (needs source flow schedules, fixes-43 item 1).
- Open a tributary pocket: `aquatic_foodweb.append_tributary_cells` with the pocket temperature as a control.
- Change grazing pressure: bison count on a patch (`grazers` input).
Each intervention is a control event with a location; the session log records it (fixes-43 item 11).
### Test
Shading a reach lowers the shortwave term in its cells' surface budget and lowers their afternoon temperature relative to an unshaded run.
### Cost
Medium (each intervention is cheap once the control path exists).

### 10. Schema bounds that need review before they become sliders
`hydro.boundary_c` allows -5 C (`study_mode.py:32`); liquid river water below 0 C is not physical at this scale, and the solver has no ice. `weather.gust_mps` caps at 5 m/s. `hydro.boundary_m3s` allows 0.1 to 60 m3/s, far outside the range of the reach-averaged geometry (single assumed depth, `river_world.py:1043-1049`), so extreme flows produce velocities and travel times the fixed-depth geometry cannot represent.
### Fix
Set `hydro.boundary_c` minimum to 0.0; derive the discharge bounds from the range over which the geometry assumption is stated (or add a stage-discharge relation before widening it); record each bound's source in the schema entry, which the conditions panel shows.
### Test
Schema tests assert the new bounds and that each entry carries a `bound_source`.
### Cost
Cheap.

## Order
Item 1 first, then 3 and 2 (the core experience), then 4, 7 and 8 (explanation), then 6, 5 and 9. Item 10 lands before item 2 exposes the bounds.
