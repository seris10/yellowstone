# Yellowstone Python — what it is and is not

Illustrative scientific modeling for `yellowstone_midway` (v0.1.0 package;
model, data, and calibration versions are tracked separately in sidecars).
Reads frozen inputs, writes `derived/<build-id>/`, validates, publishes a
drop-in `ecosystem.json`. See `../yellowstone_python_spec/03_AUDIT_RESPONSE.md`
for the external audit and what changed because of it.

## What Python simulates (offline, `simulate_all`, no files)

- River heat transport: 6-reach mixing chain with lateral sources, Newton
  surface exchange, stable substeps, full budget history; analytical T*
  regression + convergence tests.
- Patch biomass (logistic + grazing), insect 3-compartment prey
  (terrestrial/benthic/emergent, Holling-II depletion), trout refuge
  selection along river chainage, grazer/bird timing from intake/biomass.
- Degree-day snow + soil bucket (verified storage ledger), per-patch phenology.
- Pool shells (mapped polygons preserved), suitability-gated planting
  proposals, sinter/travertine guardrail, A/B experiment configs + outcomes.

## What Godot simulates (live, every frame)

- `ecosystem.gd`: 1 s-step heat/patch dynamics from the published JSON,
  wind/steam/fish-activity queries; `wildlife_actor.gd` FSM movement;
  `world.gd` sun/sky/fog/foliage/steam/river visuals. Godot owns rendering,
  player movement, and visual interpolation — and its noon-peaking air curve
  is a documented approximation of the Python 15:00-lagging analysis curve.

## Precomputed vs live

- Precomputed by Python: reach temps/flows, patch states, wildlife timing
  parameters, shells, proposals, maps, season. Godot hot-loads them at F5.
- Live in Godot: clock advance, sub-second stepping, actor FSM, gusts,
  insect hover visibility, trout swim scaling. Godot never invents
  placements, species, or terrain.

## Measured / authored / unvalidated

- Measured (source data): DEM, NAIP 2022-07-19, NPS roads/trails/hydro,
  pool polygons, gauge-adjacent references. Never mutated.
- Authored (explicit design): crater profiles, pigment bands, proposal
  positions, exclusion masks, all coefficients — every one labeled with
  provenance and none presented as observation.
- Unvalidated: no calibrated hydrology, no bathymetry, no organism counts,
  no forecast. Every output carries `status: illustrative`.

## Snow validation vs SNOTEL (WY2026, single window)

- Sites (verified live 2026-10-10, frozen in
  `derived/snotel_obs.json`): 609:MT:SNTL Madison Plateau
  (2350 m) + 924:MT:SNTL West Yellowstone (2036 m); daily WTEQ/PRCP/SNWD/
  TAVG from NRCS AWDB REST; window 2025-10-01–2026-07-31, 304 days each.
- Fit (train Oct–Feb, holdout Mar–Jul melt season; joint k_melt ×
  site-effective wind_loss grid; game defaults untouched):
  609 k=1.0/wind=0.0, holdout RMSE 112 mm vs 293 (persistence) / 472
  (no-melt); 924 k=0.75/wind=0.0, holdout RMSE 45 mm vs 179 / 194.
  Beats both nulls; status `fitted_not_validated_single_window`.
- Second window WY2025 (2024-10-01–2025-07-31, fresh bundle
  `derived/snotel_obs_prior_window.json`, 304 d each, full
  coverage; FROZEN WY2026 params, no refit via `--fixed-params` +
  `--split-date 2025-03-01`, artifact
  `derived/snow_degree_day_fit_prior_window.json`): 609 holdout
  RMSE 161 mm vs 284 / 482 (peak err 0 d, was +48 d late); 924
  holdout 90 mm vs 179 / 246 (peak err 9 d, was 2 d). Beats both
   nulls out-of-sample at both sites with ~1.4–2× RMSE degradation
   and the same hold-too-long bias sign — holds directionally, delta
   reported honestly. Status stays `fitted_not_validated_single_window`
   (the status vocabulary has no two-window label; the evidence lives
   in the artifact `beats_both_nulls` fields).
- Energy-balance melt (B3, same bundles/splits, artifact
  `derived/snow_energy_fit.json`): daily TOA insolation +
  diurnal-range cloud + decaying albedo + fitted (s_rad, c_turb).
  609 (0.54, 2.0): holdout RMSE 62 mm vs 112 degree-day / 293 / 472,
  peak err +1 d (was +48 d late); 924 (0.0, 8.0): holdout 14 mm vs
  45 / 179 / 194, peak err +2 d. Radiation drops out at 924
  (turbulent-only wins the train fit). Frozen-param WY2025
  (`derived/snow_energy_fit_prior_window.json`): 609 holdout
  46 mm vs 284 / 482 (peak err −16 d); 924 holdout 55 mm vs 179 /
  246 (peak err −1 d). Beats both nulls out-of-sample at both sites
  and beats frozen degree-day (161 / 90) by ~2–3.5×. Status stays
  `fitted_not_validated_single_window`. Runner
  `yellowstone_python/snow_energy.py`, offline tests
  `tests/test_snow_energy.py`.
- Caveats (not hidden): 609 holds high snow too long (bias +67 mm, peak
  +48 d late — degree-day on TAVG misses plateau melt energy); wind fits
  the 0.0 boundary at both sites (no net seasonal loss at clearings);
  depth factor 3.0 checks out (observed SNWD/WTEQ median 3.2–3.4);
  soil moisture unvalidated (no observations). Method + offline tests:
  `yellowstone_python/snow_validate.py`, `tools/fetch_snotel_obs.py`.

## Game clock (season + time of day)

- Default: the build reads your system clock — season from the local date
  (meteorological, northern hemisphere), time from the local hour — and
  records both plus sources in `season.json`.
- Override in settings: `clock_hour` (0–24), `snow.season`
  (winter/spring/summer/autumn), `snow.as_of_date` (YYYY-MM-DD; season
  derived from your date, clock stays live). Explicit settings always win;
  `study_mode` presets accept all three (`snow.as_of_date` validated).
- `configs/baseline.yaml` pins season summer + 16.2 h deliberately, so
  recorded numbers reproduce bit-for-bit; the live clock applies wherever
  those keys are absent.

## Hot low-flow scenario (backlog A, single run)

- Scenario: Burkhalter 1979 baseflow boundary 2.5 m3/s (measured 2–3)
  with authored 26 C boundary (below the observed 29.5 C max); control is
  the pinned baseline replay (8.0 m3/s, 17.5 C). Chronic full-run means,
  brown trout, 14 d. Runner: `tools/run_hot_lowflow.py`; artifacts
  `derived/hot_lowflow_replay.json` +
  `derived/aquatic_hot_lowflow.json`.
- Result: in-chain water 25.1–28.5 C (mean 26.6) — NO cell below the Kaya
  24 C threshold anywhere in 276 cells. Refuge drive fires (0.0 → 1.0),
  feeding 0.66 → 0.0, U −0.03 → −1.23; trout holds cell_00263 (s=5230 m,
  27.8 C, above the 26 C UILT flag) as least-bad food, shifting +2357 m
  DOWNSTREAM into warmer water — the predicted upstream jump did not
  happen; with no cold cell on the map the model cannot show one.
- Diet (Kaeding & Kaya warm shift): emergent share 0.40 → 0.70.
  Landscape emergence −221 (EPT collapses past its 22 C cutoff) while
  dipper intake +1.85 on local refuge-cell stocks. Compare +2 C run:
  +20 m shift, emergence +98, dipper +0.15, drive silent.
- Limits: food is purely relative (starvation impossible, so a best cell
  always exists); drift, molluscs, mortality unmodeled as before — a
  real fish leaves or dies where this one holds. Cold-refuge pockets
  now exist as of the 2026-10-11 follow-up section above (mainstem-only
  in this section's frozen artifacts). Status illustrative, single
  scenario.

## Tributary cold-refuge pockets (hot low-flow follow-up, 2026-10-11)

- Survey (map-measured, not invented): the baseline has NO active cold
  lateral inflow — every reach has `lateral_sources == []` except
  excelsior_mixing (62 C hot outflow); `DEFAULT_TRIBUTARIES` names
  fairy/white/rabbit/mallard creeks at authored 11–12 C but all at zero
  flow (omitted). Of the mapped creek polylines only two touch the
  replay chain: Rabbit Creek (river_5877_0 end, 10 m off cell_00064 →
  confluence s≈1260 m) and Mallard Creek (river_5938_0 end, 7 m off
  cell_00002 → s≈35 m). Fairy fragments stay >1300 m off-chain; White
  Creek's best fragment ends 85 m off-chain — mapped, not junctions.
- Design (landscape-level, solver untouched): two off-channel
   mouth-pocket cells appended to BOTH landscapes
   (`aquatic_foodweb.append_tributary_cells`; pockets are holding water,
   not transport volumes, so replay heat/water closure is intact).
   Each pocket cell carries conservation `non_conservative` plus
   `tributary_provenance`; the coupling contract (`coupling.json`,
   gated in CHECKS) enforces the label.
  Pocket food scales by authored area ratio 0.05 (22 m² pocket over a
  ~440 m² mainstem cell); shear None → zero disturbance. Runner:
  `tools/run_hot_lowflow_tributary_refuge.py`; artifacts
  `derived/aquatic_hot_lowflow_tributary_refuge.json` +
  `derived/aquatic_tributary_sweep.json`.
- Result: YES, it flips — control holds cell_00145 (s=2873 @17.37 C,
  U −0.025, unchanged) while the pulse takes trib_mallard_creek
  (s=35 @11.0 C, U −0.065, feeding 0.9, drive 0.0): −2837.5 m
  UPSTREAM. Rabbit-only variant flips to s=1260 (U −0.07, −1612.5 m).
- Temperature sweep (7 values @ size 0.05): flips at trib 8–23 C;
  at 26 C it stays mainstem (s=5230, U −1.227) — the flip threshold
  sits inside the 22–24 C refuge-drive ramp. Coldest is not best:
  8 C (U −0.22) scores worse than 14 C (U −0.02, two-sided optimum).
- Size sweep (5 values @ 11 C): flips at EVERY scale including 0.0
  (starved pocket U −0.08 still beats mainstem −1.23) — no size
  un-flip exists while the mainstem sits at 25–28 C; thermal + refuge
  terms dominate. U-math, not tuning.
- Diet/emergence/dipper: pulse diet restores to benthic 0.80 /
  emergent 0.20 (vs 0.30/0.70 hot mainstem); emergence −220.2 (vs
  −221.0 pocket-free); dipper −6.50 (vs +1.85) — the
  shared-foraging-ground assumption strands the dipper at a tiny
  pocket, a stated limitation, not a field prediction. Status
  illustrative throughout.

## Shear-to-disturbance coupling (backlog B)

- `run_foodweb` maps per-cell `bed_shear_pa` into `develop_benthic`
  disturbance: 0 at/below an authored 20 Pa threshold, ramping to 1 at 2×;
  shear-null (Manning-undefined) cells and threshold None both mean zero.
- Null result, stated plainly: mapped shear is reach-averaged and uniform
  (15.08 Pa, 273 cells + 3 null), below the default threshold — so default
  runs are numerically identical to disturbance-free (refuge cell_00145
  @17.37 C holds). The coupling is live infrastructure with no spatial
  contrast until cell-scale hydraulics vary.
- Sensitivity (baseline landscape): threshold 10 → uniform 0.51
  disturbance, emergence −30% (1028 → 720), refuge jumps upstream to
  cell_00024 (s=470); threshold 5 → disturbance 1.0, emergence −51%,
  dipper −27%. Uniform tax still reshuffles refuge via nonlinear
  regrowth, not via spatial contrast. Runner/tests:
  `aquatic_foodweb.shear_to_disturbance`, `test_aquatic_foodweb.py`
  `ShearDisturbanceTests` (offline synthetic).

## Fischer-D replay (stretch C, sensitivity not calibration)

- Solver dispersion 84.7 m2/s (mapped Fischer median; rests on authored
  n=0.035/banks, no bathymetry — sensitivity case only). Runner flags on
  `tools/run_hot_lowflow.py`; artifacts `derived/fischer_D85_replay_*`,
  `derived/aquatic_dispersion_D85_*`, `derived/hot_lowflow_D85_replay_*`,
  `derived/aquatic_hot_lowflow_D85_*` (all 2026-10-10).
- Dispersion alone (D1 vs D85, baseline boundary): refuge moves 636 m
  upstream (s=2873 → 2236, same 17.4 C water, drive silent), emergence
  +1.5, dipper +0.01 — placement shifts, ecology nil.
- Intervention repeated at D85: drive fires, trout holds s=5230 @27.7 C,
  emergence −220, dipper +1.85 — same qualitative outcome as D1
  (+2357 m, −221, +1.85). Conclusion robust: at 2.5 m3/s + 26 C boundary
  the mainstem offers no sub-24 C water at either dispersion.

## Run it

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest tests -q
python3 -m yellowstone_python.build --config configs/baseline.yaml
python3 -m yellowstone_python.publish --build derived/<id> --to ../yellowstone_midway
python3 -m yellowstone_python.study_mode --list
python3 -m yellowstone_python.compare derived/<A> derived/<B>
python3 -m yellowstone_python.review_proposals --proposal derived/<id>/planting_proposal.json --apply
```

Godot 4.5.1: open `yellowstone_midway/project.godot`, F5. I = notes, M = map.
Rebake (consumes `placement_overrides.json`) needs 4.5.1; installed 4.4.1 is
for `--check-only` script validation only — bake deferred.

## Run modes and claims

- Every config declares `run_mode`: `illustrative` (default), `scenario`,
  `hindcast`, or `observed_replay`. `forecast` builds are refused until a
  forecast evaluation exists. Boundary discharge and upstream temperature
  are prescribed forcing; validation covers unprescribed outputs.
- `study_mode` presets stamp `scenario` automatically.
- Each build writes `claims.json` (two seed claims, both `not_yet_accepted`),
  `param_registry.json` (class and evidence per knob; unknown stays unknown),
  and `equations.json` (governing model and limits per component).
  `BUILD.json` records mode, prescribed quantities, and claim ids.

## Peripheral tools (`tools/`, CLIs with `--help`)

- `tools/channel_geometry.py` — sole producer of `configs/cross_sections.json`
  (DEM transects; `--usgs-data` prefers current-meter depth when available).
- Gates: `tools/validate_obs_bundles.py` (bundle schema/continuity/coverage),
  `tools/audit_provenance.py` (status vocabulary over `derived/`),
  `tools/check_terrain.py` (terrain.f32 hash/dims/range vs BUILD deps),
  `tools/compare_bundles.py` (old-vs-refetch drift).
- Fetchers: `tools/fetch_firehole_obs.py`, `tools/fetch_snotel_obs.py`
  (frozen bundles), `tools/fetch_met_forcing.py` (shared Open-Meteo source).
- `tools/plot_fit.py` — Pillow-only diagnostic PNGs from fit artifacts
  (status footers on every figure).

## LLM backend (read-only accuracy API, stdlib only)

Tree observation authority is `derived/census.json` (game-native NAIP canopy
detection, 33,764 crowns). A 2026-10-09 cross-check showed pretrained
DeepForest finding 2–53 crowns where the census finds ~1,175 in the same
knoll crop — generic weights are unfit here, so the backend serves census +
game state, never DeepForest edits.

```bash
python3 -m yellowstone_python.llm_backend --serve --port 8765
python3 -m yellowstone_python.llm_backend --snapshot-out derived/llm_snapshot.json
python3 -m yellowstone_python.llm_backend --compare --x -252 --z 159 --r 120
```

`GET /api/snapshot /api/census/zones /api/density?x=&z=&r= /api/compare?x=&z=&r= /api/placements/summary /api/ecosystem/summary /api/build/latest`, `POST /api/propose` (dry-run planting review, no writes).

Validation: density radii must be in [0.1, 5000] m; `propose` requires a known
`guild`/`habitat_id`, `radius_m`/`count` in (0, 500], `suitability_threshold`
and `canopy` in [0, 1] (all finite, no bools); bodies over 64 KB are rejected
(413) and review logs over 1000 entries truncated. Corrupt data files degrade
only their `/api/snapshot` section (HTTP 500 with file context), never the
whole bundle.
