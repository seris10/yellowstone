# fixes-43: live Python simulation service (compute ahead of the player)

Scope: what it takes for Python to run beside the game, compute river, fish, insect, snow and weather state ahead of the player, and recompute when the player changes a condition, so the world moves toward the new state through the model's own dynamics under compressed time. Python side only; the Godot side is fixes-44 and the controls are fixes-45. Audit 2026-10-13 at the request of KJR.
Method: read `replay/river_transport.py`, `replay/river_world.py` and `aquatic_foodweb.py` end to end; read the entry points of `fish.py`, `study_mode.py`, `llm_backend.py` and the `simulate_all` stage order in `build.py`; timed each model on build 2a8c8948128c (276 replay cells, 721 frames over 7200 s) with `.venv/bin/python` on this machine. Timing scripts: session scratchpad `time_models.py`, `time_budget.py`, `time_energy.py`; each rerun gave the same figures within 10 percent.

## Current state

Python runs offline. `build.py simulate_all` computes a fixed 7200 s replay and a 14-day foodweb, writes JSON, and `publish.py` copies it into `yellowstone_midway/data/`. Godot reads the files once at startup (fixes-44 item 1). The player cannot change any condition that Python sees.

The published build runs the river with the lumped Newton surface exchange (`river_replay.json` `model.surface_flux: newton_lumped`) and hyporheic zones on. The explicit shortwave, longwave, sensible and latent budget runs only when `replay.energy_budget` is set or a measured run mode selects it (`build.py:1714-1731`). Under the lumped exchange, cloud, humidity and wind do not reach river temperature at all.

Measured cost per call (best of several):

| model | call | wall ms | simulated span |
|---|---|---|---|
| River construct, 276 cells | `river_from_config` | 0.5 | |
| River step, lumped exchange | `River.step(2.0)` | 0.5 | 2 s |
| River run, lumped exchange | `River.run(600, 2, 10)` | 150 | 600 s |
| River run, lumped exchange | `River.run(7200, 2, 10)` | 1850 | 7200 s |
| mapped replay, lumped exchange | `build_mapped_replay(duration_s=600)` | 160 | 600 s |
| mapped replay, explicit budget | `build_mapped_replay(duration_s=600, energy_budget=True)` | 2740 (9.1 per step, up to 5 Newton iterations) | 600 s |
| thermal landscape, all frames | `thermal_landscape` | 14 | |
| thermal landscape, last 60 s | `thermal_landscape(t_min_s, t_max_s)` | 4 | |
| foodweb | `run_foodweb(days=1)` | 1.5 | 1 d |
| foodweb | `run_foodweb(days=14)` | 18 | 14 d |
| snow, one day | `snow_season.step_snow` | 0.001 | 1 d |
| snow, 30 days, 3 patches | `run_season` | 0.25 | 30 d |
| insects | `insects_birds.step_compartments(dt=60)` | 0.006 | 60 s |
| 6-reach chain | `hydro_thermal.run_simulation(600, dt=1)` | 16 | 600 s |

Reading the table: with the lumped exchange the river advances about 4,000 simulated seconds per wall second on one core at dt 2 s. With the explicit budget, which the weather controls need, it advances about 220. Ecology models are negligible next to the river. Raster models (`outflow_thermal`, `microbial_mats`, mat pigment, terrain, census) were not timed and stay offline in this plan. The maximum advective Courant number at dt 2 s is 0.047, so the step can grow about twentyfold before reaching 1.

## Items

### 1. River forcing cannot change after construction
`River.__init__` parses `boundary_m3_s`, `boundary_c`, `air_c`, `net_heat_flux_w_m2`, per-cell heat and the surface-budget series once into `self._forcing` (`replay/river_transport.py:394-490`). `River.step` refuses to cross a forcing change (`:957-961`). Lateral source flows are constants (`Source.flow_m3_s`, `:165-190`), summed once into `self._lateral_q` (`:447-450`). A player change mid-run therefore needs a rebuild from t=0.
### Fix
Add `River.set_forcing(name, at_s, value)` for `boundary_m3_s`, `boundary_c`, `air_c`, `net_heat_flux_w_m2`, the four surface-budget series and per-cell heat. It requires `at_s >= self.time_s`, truncates the series after `at_s`, appends a breakpoint at `at_s`, and rebuilds `self._forcing`. Values pass the same parse and bound checks as construction. Lateral source flow becomes a `Series` like source temperature, with `_lateral_q` evaluated per step in `_face_flow_at`, so a surge can switch on and off (the stale guard and message at `river_world.py:97-102` then go).
### Test
A run with a change set mid-run equals, to 1e-12 C per cell, a fresh run built with the same piecewise schedule. Heat and water budgets close across the change at the existing tolerances. A change with `at_s < time_s` raises. A source flow schedule closes the water budget.
### Cost
Cheap to medium (source flow schedule touches face-flow and accounting code).

### 2. No checkpoint and restore for the river state
The state is `_time_s`, `_temperature_c`, `_hyporheic_t_c`, the running totals in `_totals`, `steps`, `_initial_c` (the budget reference) and the diagnostic maxima. `step` and `_advance_to` do no file I/O. Nothing exposes the state as a value.
### Fix
`River.checkpoint() -> RiverState` (frozen dataclass of those fields, with `_Sum` totals copied as their two floats) and `River.restore(state)`. The live engine keeps a checkpoint at the player's current time so a control change recomputes from that point.
### Test
Restore at t, run to t+600 s, and compare with an uninterrupted run: identical temperatures, hyporheic temperatures and budget.
### Cost
Cheap.

### 3. Lookahead buffer: compute ahead, discard on change
This is the "rendered ahead of the player" mechanism.
### Fix
New module `yellowstone_python/live/engine.py` with class `LiveEngine`. It holds one `River`, the foodweb stocks, the insect, snow and oxygen state, a forcing timeline, and a frame buffer covering `[t_player, t_player + H]`. A worker thread keeps the buffer at horizon H (default 600 simulated seconds, declared in config). On a control event at simulated time `t_c`: restore the checkpoint at or below `t_c`, apply `set_forcing` at `t_c`, drop buffered frames after `t_c`, and recompute. Frames carry the fields the Godot replay reader already consumes (`t_s`, `temperature_c`, and `q_cells_m3s` and `depth_m_cells` only when they change; `river_world.py:1395-1401` repeats both arrays in every frame although they are constant).
### Test
After a control event the first frame after `t_c` reflects the new forcing; frames before `t_c` are unchanged. At the target time scale the buffer never empties over a 5-minute soak; headroom is logged.
### Cost
Medium.

### 4. Transitions must come from the model, not from visual easing
The request is that the world reacts instead of snapping to a new state. With items 1 to 3 the transition is physical: a change in upstream temperature travels down the chain at the advective velocity and relaxes toward equilibrium at the surface-exchange rate, and trout respond on the foodweb step. Time compression makes it watchable: at 600x, a 50-minute travel time plays in 5 s of wall time.
### Fix
Time compression is a service parameter `time_scale` (simulated seconds per wall second; presets 1, 60, 600, 3600). The service advances simulated time; Godot interpolates between computed frames only. Simulated state is never eased on the Godot side (fixes-44 item 6 lists the visual-only exceptions). The engine records `time_scale` per segment in the session log (item 11).
### Test
At 600x, the arrival time of a step change at a downstream cell, measured from streamed frames, equals the arrival time in an offline `make_replay` with the same schedule, within one frame interval.
### Cost
Cheap once item 3 exists.

### 5. Step size under compressed time
Required throughput is `time_scale / dt_s` steps per wall second. Lumped exchange at dt 2 s: 600x needs 300 steps (0.15 s CPU per wall second), 3600x needs 1800 steps (0.9 s, no headroom). Explicit budget at dt 2 s: 600x needs 2.7 s CPU per wall second, which one core cannot deliver; the ceiling is about 100x. The solver is backward Euler and stable at large steps; `COURANT_WARNING_THRESHOLD` and `DIFFUSIVE_WARNING_THRESHOLD` (`river_transport.py:40-41`) are warnings only. Accuracy at larger steps is unmeasured.
### Fix
Measure first: run the baseline mapped replay at dt 1, 2, 5, 10, 20 and 40 s, lumped and explicit, and report the maximum cell difference against dt 1 s plus the arrival-time error of a step change. Set `live.max_dt_s` to the largest step with error below 0.05 C and arrival error below one sample interval, register it in `param_registry` as a numerical setting, and choose `dt_s = min(max_dt_s, time_scale / target_steps_per_second)` at run time. Stream `max_advective_courant`, `max_surface_iterations_used` and `surface_iteration_failures` as frame health fields.
### Test
The dt sweep is a benchmark in `replay/benchmarks.py` with the 0.05 C bound asserted. A forced surface-iteration failure surfaces in the frame health field.
### Cost
Cheap.

### 6. The explicit surface budget is too slow for live weather control
The explicit budget costs 9.1 ms per step against 0.5 ms for the lumped exchange. Per step, `_system` calls `_surface_linearization` once per cell per Newton iteration (`river_transport.py:793-798`), and `_surface_power_for_accounting` calls `_surface_linearization` and `flux_at` again for every cell (`:722-742`). All of it is scalar Python over 276 cells. Without the explicit budget, cloud, humidity and wind controls have no effect on the river, so the live demo needs it.
### Fix
Profile one explicit step, then vectorize `surface_flux.flux_at` and `linearized` over a cell array with numpy (same equations, same `BudgetParams`), and reuse the converged linearization in accounting instead of recomputing it. Keep the scalar functions as the reference implementation and test the vector path against them.
### Test
Vector and scalar fluxes agree to 1e-12 W/m2 over a grid of temperatures and met states; a mapped replay with the explicit budget gives identical frames to 1e-10 C; the per-step cost is recorded in the benchmark (target under 2 ms per step on this machine).
### Cost
Medium.

### 7. The trout refuge choice uses a whole-window mean and has no movement cost
`thermal_landscape` gives each cell the mean temperature over the selected frames (`aquatic_foodweb.py:440-466`). `run_foodweb` scores every cell each step and takes the best (`:713-714`); its own provenance records `movement_cost: not modeled` (`:852`). Two cells with nearly equal suitability can alternate between steps, which live play would show as a trout jumping back and forth across kilometers.
### Fix
Online exposure temperature per cell is an exponentially weighted mean with time constant `tau_exposure_h`, updated from each frame (one multiply-add per cell). `tau_exposure_h` is authored until a source is found and registered with `authored` provenance; the refuge drive in `fish.thermal_performance` uses Kaya et al. 1977 thresholds, which describe chronic exposure. Add a movement rule: switching cells requires a gain in U above `delta_u_switch` plus a cost per meter traveled, both authored and registered. Offline `run_foodweb` takes the same two terms with defaults of zero, so published results do not change until a build opts in.
### Test
With a constant landscape the chosen cell does not change. A step change that makes a cold pocket better by more than `delta_u_switch` moves the trout once. The offline build with defaults reproduces the 2a8c8948128c refuge cell.
### Cost
Cheap.

### 8. Foodweb stepping is locked inside one function
`run_foodweb` steps in days with hourly eating substeps, and its step body (`aquatic_foodweb.py:653-769`) cannot be called alone. Stocks live in a local list.
### Fix
Extract the body into `step_foodweb(state, landscape, step_days, settings) -> report`, with `run_foodweb` looping over it. `LiveEngine` steps insects every frame and the foodweb at a declared interval (default 1 simulated hour), carrying state between calls. The nested `_positive_finite` inside `run_foodweb` (`:617-623`) moves to the shared helper module (fixes-46).
### Test
Fourteen calls of `step_foodweb` at 1 day equal `run_foodweb(days=14)` exactly.
### Cost
Cheap to medium.

### 9. Recompute graph per control
`simulate_all` runs every stage in a fixed order. The engine needs to know which state a control invalidates.
### Fix
Declare a dependency table in `live/engine.py`, taken from the `simulate_all` stage order:

| control | recomputed from the change time |
|---|---|
| air temperature (night air, day warming, lag) | weather trace, river surface exchange, insects, snow and soil, oxygen saturation, periphyton, foodweb |
| cloud, humidity, wind | explicit surface budget, insects, snow |
| precipitation | snow season, soil bucket, catchment runoff into the boundary discharge |
| clock hour, date | solar position and shortwave, air curve phase, snow state by date (season spin-up from 1 October with `run_season`, under 1 ms) |
| upstream discharge | face flows, travel time, oxygen reaeration, foodweb hydraulic terms |
| upstream temperature | river boundary and everything downstream |
| lateral source on or off (Excelsior surge, tributary pockets) | river sources, solutes, foodweb |

Stages that keep their published values during a live session: terrain, census, outflow network and mat rasters, pool shells, geochemistry, calibration artifacts. The frame header names them as `static_from_build: <build_id>`.
### Test
One unit test per row: changing the control marks exactly the listed state dirty.
### Cost
Cheap.

### 10. Date-blind shortwave and averaged upstream discharge
The explicit budget's fallback shortwave is `sw_noon * max(0, sin((hour - 6) * pi / 12)) ** 1.2` (`river_world.py:915-921`): the same curve on every date. A date or season control would then change nothing in the river's radiation. `microbial_mats.instantaneous_shortwave_w_m2` already computes clear-sky shortwave from pvlib for a date and time. Separately, a predicted upstream hydrograph is collapsed to its window mean (`river_world.py:1146-1158`) although `River` accepts a scheduled boundary.
### Fix
Use the pvlib clear-sky shortwave at the replay epoch, reduced by cloud with a cited cloud transmission factor, as the fallback in `energy_met_series`; record `shortwave_source` per run. Pass the predicted hydrograph through as a `Series` and keep the mean only as a reported diagnostic.
### Test
Shortwave at 13:00 local on 21 June exceeds 21 December at the site latitude; a scheduled upstream hydrograph reproduces its own volume in the water budget.
### Cost
Cheap.

### 11. A live session must stay reproducible and labeled
A player session is a scenario whose forcing schedule is decided at run time. Without a record it cannot be reproduced or compared.
### Fix
The engine appends each control event `(wall_utc, t_s, key, value)` to a session log `derived/live/<session-id>.jsonl` (append-only). `python -m yellowstone_python.live --export-scenario <session>` writes a `configs/experiments/` scenario config with `run_mode: scenario`. Every frame header carries `run_mode`, `build_id`, `session_id` and the base build's claim ids at `not_yet_accepted`. The Godot HUD shows the run mode (fixes-44 item 8).
### Test
Export a session log, run it through `build.py`, and compare the final river state with the session's last frame: equal to solver tolerance.
### Cost
Cheap.

### 12. Service process and transport
`llm_backend.py` runs a `ThreadingHTTPServer` on 127.0.0.1:8765 with JSON routing and CORS (`llm_backend.py:901-1069`) and holds no solver state. Godot has a threaded HTTP client, `weather_http_consumer.gd`, that nothing instantiates and that targets port 8001 (fixes-44 item 2).
### Fix
New entry point `python -m yellowstone_python.live --build derived/<id> --port 8765`. Share the request handler base with `llm_backend` (one server module, two route tables). Endpoints:
- `GET /api/live/schema`: controls, bounds, units and provenance class, generated from `study_mode.SCHEMA` (`study_mode.py:21-45`) so Godot hardcodes no bound.
- `POST /api/live/control`: `{key, value, at_s}`, validated by `study_mode`.
- `POST /api/live/clock`: `{time_scale, paused}`.
- `POST /api/live/preset`: a `study_mode.PRESETS` name.
- `GET /api/live/frames?after_t_s=`: buffered frames after a time, as one chunk (276 cells by 4 float fields is about 4.5 kB per frame).
One `LiveEngine` per process, owned by the worker thread; request threads read published immutable frame chunks under a lock. Polling at 2 to 5 Hz is enough because Godot interpolates within the buffer, so no WebSocket server is needed for this payload.
### Test
An in-process test starts the server on a free port, posts a control, polls frames and sees the change after `at_s`. A malformed control returns 400 with the validator message.
### Cost
Medium.

### 13. Fallback when the service is absent
The game has to stay playable from the published build when Python is not running.
### Fix
Godot probes `/api/live/schema` at startup with a 1 s timeout. Absent: baked replay as today, HUD label `baked build <id>`. Present: live mode. The mode does not change inside a session.
### Test
Godot headless with no server reaches baked mode and logs it; with the server running it reaches live mode.
### Cost
Cheap (Godot side in fixes-44 item 2).

### 14. Three river heat models
`build.py:1703` runs `hydro_thermal.run_simulation` (6 lumped reaches, explicit Euler) for the HUD and the fish display (`build.py:2340` labels it `legacy_hydro_thermal.run_simulation`); `build.py:1746-1757` runs the replay solver for every science model; Godot's `ecosystem.gd` steps a third 6-reach chain every frame (fixes-44 item 7). A reader has to work out which of the three is the science.
### Fix
Make the replay solver the single river authority. Derive the six reach summaries for the HUD from replay cells (flow-weighted mean temperature over each reach's chainage, using `legacy_queries` from `build_mapped_replay`). Keep `hydro_thermal.py` only as an analytical benchmark if a test uses it that way; otherwise remove it and its tests. Record `river_model: replay.river_transport` in `BUILD.json`.
### Test
Derived reach summaries equal the replay cell means; outside benchmarks the build no longer imports `hydro_thermal`.
### Cost
Medium.

### 15. Two trout thermal performance implementations
`fish.thermal_performance` uses authored piecewise-linear shapes between literature anchor points (`fish.py:370-371`). `thermal_curves.py` fits split-Gaussian curves per endpoint to cited anchors (Elliott and Hurley 1999 and others) with scipy; only its own test imports it (`replay/tests/test_thermal_curves.py`). The better-documented curves do not drive the model.
### Fix
Wire `thermal_curves` into `fish.thermal_performance` behind a `thermal_curve_form` setting (`piecewise_linear` default until reviewed), compare refuge outcomes for both forms in the baseline and hot low-flow scenarios, and record the form in the build. Retire whichever form loses. Move `test_thermal_curves.py` to `tests/`, since thermal curves are not part of the replay package.
### Test
Both forms agree at the shared anchor points within 0.02; the build records which form ran.
### Cost
Cheap to medium.

## Order
Items 1, 2, 5 and 6 first (solver API, step-size measurement, explicit-budget speed), then 7, 8 and 10 (ecology stepping and date-aware forcing), then 3, 9, 11, 12 and 13 (engine and service), then 4 (verifying physical transitions). Items 14 and 15 are independent; 14 lands before fixes-44 item 7.

## Not tested in this audit
Raster model costs (outflow thermal, mats); explicit-budget cost after vectorization; CPU headroom with Godot running on the same machine; service behavior on Windows or Linux.
