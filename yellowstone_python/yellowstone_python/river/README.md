# Replay engine .  1-D finite-volume river temperature + mapped Firehole replays

The finite-volume solver maps the Firehole chain, transports heat, and records conservative budgets. The build and live service use its physical state; Godot renders and interpolates published results.

## Layout

- `river_transport.py` .  conservative 1-D transport (upwind advection,
  centered harmonic dispersion, backward Euler, Thomas solver), Series
  forcing, compensated budgets, replay export with input + code hashes.
- `river_world.py` .  maps the solver onto the saved Firehole chain
  (endpoint-node topology, chainage, source connection at the authored
  Excelsior outlet vertex 398, pulse interventions). Builds from the frozen
  `ecosystem.json.pre-python` for idempotence.
- `tests/river/` .  numerical verification (transport) + mapping tests (world).
  `python -m pytest tests/river/`.

## Regenerate

```bash
python3 -m yellowstone_python.river.river_world \
  --world ../yellowstone_midway/data/world.json \
  --ecosystem ../yellowstone_midway/data/ecosystem.json.pre-python \
  --out derived/firehole_control.json
python3 -m yellowstone_python.river.river_world --world ... --ecosystem ... \
  --pulse-source excelsior_aggregate_outflow --pulse-start 300 --pulse-end 900 \
  --pulse-delta-c 18 --out derived/firehole_pulse.json
```

Copy results to `yellowstone_midway/data/firehole_{control,pulse}.json`
Publishing copies the selected replay pair into the world data directory.

## Cross-section profiles

Research stage: P0.

Cell volumes default to `length x authored_width x --depth-m` (1.1 m,
assumed). A per-feature profile file replaces the depth where supplied:

```json
{
  "river_5856_0": {"depth_m": 1.4, "status": "authored_estimate",
                   "source": "hand profile A-A', Oct 2026"},
  "river_5872_0": {"depth_m": 0.9, "status": "authored_estimate"}
}
```

```bash
python3 -m yellowstone_python.river.river_world --world ... --ecosystem ... \
  --cross-sections derived/firehole_sections.json --out derived/firehole_profiled.json
```

Rules: `depth_m` must be positive; `status` is required and explicit
(supplied profiles are never labeled "assumed"); unknown feature ids are
rejected; profiled cells carry `geometry_status`
`mapped_centerline_authored_width_profile_depth` plus `depth_m` /
`depth_status` / `depth_source` in the mapping records. Representative
velocity (`Q/A`) then follows each cell's profiled depth.

## Trapezoidal hydraulics diagnostics

Research step: 1.

Solver volumes stay rectangular (`length x width x depth`, baseline
preserved). Each replay cell additionally carries `hydraulics/`:

- Trapezoid from top width + depth + authored bank slope `z`
  (`--bank-slope`, default 1.5 H:V): `A=(W-z*d)*d`, `P`, `R`, `H`,
  plus `rectangular_bias_pct` quantifying the old assumption's error.
- Mapped grade, reach-averaged per river feature (total elevation drop /
  total length .  cell-scale drops are vertex/DEM noise, not energy slope).
  Flat, adverse, or sub-noise-floor grades (<1e-4, authored floor) leave
  Manning/shear/Fischer `None` with warning
  `flat_or_adverse_grade_manning_undefined` .  never an invented slope.
- Manning velocity (`--manning-n`, default 0.035) vs continuity `Q/A`
  as `manning_consistency_ratio`; Froude for both; bed shear; reach
  travel times; Fischer `D` as an order-of-magnitude check on the
  illustrative `dispersion_m2_s`.
- `hydraulics_summary/`: total travel time, median/range Manning ratio,
  median Fischer D vs solver D, flat-cell count, and a
  `thermal_inventory/` (total thermal flow + flow-weighted entry T).

Provenance: top width authored, depth per-profile/assumed, bank slope +
Manning authored illustrative, slope mapped-where-positive. Calibrate
with `python -m tools.usgs_nwis` fetches + `hydraulics.score_paired_series`
(RMSE/bias/MAE) .  the scorer never supplies observations.

## Dispersion audit (`calibrate.py dispersion`)

Method-of-moments on a Gaussian pulse in a uniform channel
(`derived/dispersion_sweep.json`):

| specified D | effective D | verdict |
|---|---|---|
| 0 | 8.5 | numerical diffusion floor (upwind theory V*dx/2 = 8.25 passes) |
| 1 (replay value) | 9.5 | **configured D is swamped ~9x by the solver's own diffusion** |
| 10 | 18.5 | additive floor + specified |
| 85 (Fischer est.) | 86.1 | solver transports high-D faithfully |

Findings: (1) the solver is verified .  effective minus specified D is a
constant floor that halves with dx (4.4 at dx=25 m), budget closure
~1e-14; (2) at mapped-chain resolution (Vabout 0.73 m/s, dxabout 20 m) the floor is
about 7 m2/s, so every replay to date ran at effective Dabout 8 regardless of the
configured 1.0 .  thermal fronts spread ~8x faster than the config
claims; (3) the Fischer estimate (~85) is a further ~10x above that.
Follow-ups in order: set solver D from the Fischer diagnostic, refine
dx, or move to higher-order advection. Status: numerical experiment,
not field validation.

## Reach heat-budget fit (`calibrate.py fit`)

`python -m tools.fetch_firehole_obs` froze a 7-day measured bundle
(`derived/firehole_obs.json`): USGS discharge + water
temperature at 06036805 (upstream, Qabout 1.07 m3/s, T 7.6 to 13.6  deg C) and
06036905 (downstream, Qabout 5.44 m3/s, T 14.5 to 21.2  deg C), plus Open-Meteo
hourly forcing at the upstream gauge. A single well-mixed cell using the
conservation-tested `River` integrator fits aggregate
lateral inflow + turbulent-exchange multiplier against the downstream
gauge, 5-day train / 2-day holdout, vs persistence, mixing-only,
and climatology nulls, with holdout scores split by flow tercile.

Model-free arithmetic first (no fit): water balance gives lateral
Q = 4.37 m3/s; adiabatic heat balance gives aggregate lateral
T about  19.5  deg C .  a lower bound, since fall surface exchange is net
cooling. The fitted champions (V = 1.5/3/6e5 m3 effective volume)
land at (Q, T) = (3.5, 25) / (3.5, 30) / (4.5, 35) with c_mult = 1.0
everywhere: train RMSE 0.52 to 0.63  deg C, holdout within 0.06, vs 7.0
(persistence) and 0.84 to 1.07 (mixing-only). Robust conclusions: large
lateral heat load is required; textbook exchange coefficients suffice
unscaled. Unidentified: the Q-vs-T split rides a ridge driven by the
authored effective volume/area (surface cooling scales with area), so
fitted T_lat 25 to 35 deg C depends on those authored assumptions and remains
unmeasured. Breaking the
ridge needs surveyed reach geometry or a third gauge. Status on every
fitted number: `fitted_not_validated_single_window`.

## Uncertainty quantification

Tool: `uncertainty.py`. Research stage: A1.

`derived/reach_ensemble_uq_v300k.json`: the 10%-ridge around the
V300k champion admits 5 members spanning the tradeoff line
(3.5,30)->(4.75,25) at c_mult 0.5 to 1.0 .  the joint distribution the
figures pass will plot. Equal-weight 90% bands (seeded bootstrap,
seed 20261010): mean width 0.54  deg C, but holdout coverage is 0.34 at
nominal 0.90 (n=172). The bands describe fit ambiguity and they fail
to cover holdout .  the dominant uncertainty is structural
(single-window bias: fresh holdout bias +0.30  deg C scale), not
parametric. The ridge rule stays fixed during coverage evaluation;
tuning it to repair coverage would launder bias into spread. Fresh grid rerun reproduces the recorded
champion identity (train 0.497 vs recorded 0.529 .  minor code drift
since Oct 9, self-consistent within this artifact). Champion q_lat=3.5
sits on the grid floor: the ridge may extend below it.
OAT ranking (|deltaholdout RMSE|, stated moves): area x2//2 (+/-~3) >
c_mult x2//2 (+/-~2) > t_lat +/-5 (+/-~1.8) > volume x2//2 (+/-0.3 to 0.7) >
q_lat +0.25 (+0.2). Geometry area is 2xV (0.5 m effective depth,
authored); recorded fit artifacts do not store area .  provenance gap,
not backfilled. Downstream knobs on the recorded build landscape:
Manning n dominates bank z on the consistency ratio (+/-0.21 vs +/-0.014,
median 0.736 vs recorded 0.74, n=273 fixed); ne_turnover_days moves
dipper intake +29% over 1->4 d with emergence invariant by
construction; REFUGE_WEIGHT moves no refuge selection on ambient or
synthetic-hot landscapes (near-tie cluster shifts as a block).
Status: `fitted_not_validated_single_window` throughout.

## SciPy passes

Commands: `calibrate lsfit` and `calibrate ivp`. Research stage: A2.

Three surgical uses; the solver is untouched. (a) Bounded
least-squares polish (`scipy.optimize.least_squares`, 18 evals) from
the V300k grid champion moves along the ridge to (2.21, 38.76, 1.11):
train 0.497->0.465, holdout 0.466->0.504 .  train improves while holdout
degrades, the ridge signature, independently confirming A1. The polish
exits below the grid floor (q=2.21 < 3.5): the ridge extends past the
searched range. AIC/BIC selection is unambiguous: fit -606, mixing-only
-12, persistence +1561. (b) `solve_ivp` RK45 on the nonlinear budget
vs backward-Euler: max 0.048  deg C at dt=900 on real forcing, halving
exactly with the step (0.0239, 0.0120; ratios 1.99, 1.99) .  first-order
truncation converging to the same trajectory, which verifies the
solver. Debug note: `Series.at` is zero-order hold, not linear
interpolation .  the cross-check replicates it exactly. (c) Skill:
NSE 0.944 train / 0.915 holdout, KGE 0.80 / 0.77. Residuals keep slow
structure (lag-1 about  0.99 both windows, Q-Q gap ~0.7 to 0.8): errors are a
drifting bias, not white noise, so RMSE bands understate .  same story
as A1's coverage miss. Artifact:
`derived/reach_polished_fit_v300k.json`.

## Figures and executable notebook

Tool: `figures.py`. Research stage: A3.

The figure tools generate five diagnostics rendered headless (Agg)
from frozen artifacts: fit/holdout vs persistence null, ridge-ensemble
bands, residuals + Q-Q, the Q-T joint distribution with champion star
and off-grid polish X, and the refuge thermal profile with the Kaya
24  deg C line. `notebooks/reach_fit.ipynb` reproduces the trail end to
end on a coarse 27-point grid (a few seconds): frozen bundle -> grid
fit -> polish -> AIC/BIC -> skill -> bands -> figures. Stored with cleared
outputs; validated two ways .  stdlib `python -m tools.execute_notebook`
(unit-tested on a synthetic bundle) and real `nbconvert --execute`
(6 cells, 0 errors, contained venv since system python is
externally-managed). Coarse-grid caveat, printed by the notebook
itself: its fallback top-5 spans distant fits, so its wide bands
cover easily (0.93) .  the production tight ridge under-covers (A1).
Notebook execution requires Jupyter; figure rendering uses matplotlib.

## SymPy Jacobian check

Test module: `test_surface_flux.py`. Research stage: A4.

The hand-derived `dF/dT` in `surface_flux.linearized()` against SymPy
differentiation of the documented flux over water -5 to 45  deg C x met grid x
2 param sets (1728 comparisons): worst relative error < 1e-6, flux
values equal too. No sign error. SymPy is test-only and the test skips
where it is absent The science dependency group includes SymPy.

## Pandas obs alignment (`obs_frame.py`)

Fetch->fit alignment through DatetimeIndex frames: resample-mean bins
at the nominal step (bins anchored at the first observation),
explicit gap runs + coverage per series, bridge limit recorded
(4x-nominal, same rule as `check_continuity`), grid endpoints required
inside measured coverage .  no silent endpoint clamp. The fit takes
`backend="pairs"|"pandas"` (default pairs until pandas is installed on
the project interpreter); on the frozen bundle both backends agree to
float noise end to end (bit-identical trajectories, coverage 1.0, zero
gaps). Solver stays dependency-light: pandas is imported in
`obs_frame.py` and nowhere else. The science dependency group includes pandas.

## 2-D thermal plume (`plume2d.py`)

`plume_field` in `thermal_features/plume.py` solves steady 2-D
advection-diffusion over the Excelsior mixing zone:
u.dT/dz = Dx.d2T/dx2 + Dz.d2T/dz2 - k.(T - ambient),
implicit upwind/centered solve (scipy.sparse) on a 128x128 grid over
600 m, source cells fixed at the modeled mixing-reach temperature.
Velocity 0.73 m/s (mapped chain representative), longitudinal D 84.7
m2/s (mapped Fischer median), transverse D 0.12 m2/s (0.15 H u form,
authored depth 1.1 m), surface rate 1/18000 s (chain cooling time).
Overlay path and extent unchanged (`plume_map.png`).

At build temperatures (19.1 source, 17.8 ambient): discrete residual
1.3e-13, peak anomaly 1.3 C, +1 C footprint 468 m, e-folding 28 km
(surface exchange is slow next to the 14-minute transit: u/k = 13 km).
Peak sits below the fully mixed Excelsior bound (0.255 m3/s at 93 C
into 8 m3/s gives +2.3 C). Artifact
`derived/plume2d_excelsior.json`. Status
`illustrative_not_calibrated`.
IR gradient-zone check vs Burkhalter 1979 Unevaluated (zone
coordinates not digitized). Offline tests: `test_plume2d.py` (closure,
bounds, symmetry, decay, grid agreement).

## Aquatic food web (`aquatic_foodweb.py`)

Replay heat -> insect prey -> trout -> dipper in one runner over the
time-mean thermal landscape (multirate doctrine: 2 h hydraulics is
quasi-steady next to 14-day ecology). Per cell: EPT vs dipteran benthos
(`INSECT_GROUPS`, transferred structure) -> emergence -> one trout
selects its refuge by species literature suitability (`THERMAL_SPECIES`:
brown/rainbow optima, Firehole-measured 24  deg C refuge drive) with
mapped-hydraulics velocity and local food -> trout + dipper compete
pro-rata at the refuge cell. Every build writes `aquatic_foodweb.json`.

Illustrative intervention (`derived/aquatic_intervention.json`,
+2  deg C upstream boundary): refuge cell_00145 -> cell_00146 (+20 m,
17.37 -> 19.33 deg C, feeding 0.66 -> 0.17 .  a food-vs-heat tradeoff
that selects warmer water); reach emergence +98 (dipteran boom); dipper intake
+0.15 (pro-rata share of the boom). Brown vs rainbow control refuges
sit 218 m apart .  the species table moves fish. A 10-minute Excelsior
+18  deg C pulse moves nothing: the trout already holds upstream of the
inlet and the pulse decays within ~1 km .  a correct null, recorded not
hidden. Known gaps: no emergent drift, no molluscs (warm food
underestimated per Kaeding & Kaya 1978), single fish/bird, no
mortality simulation.

## Study scene in the Godot 4.5.1 editor

Duplicate the main scene, swap the ecosystem node's script to
`scripts/python_river_replay.gd`, set `replay_path` to a replay JSON, add
`scripts/thermal_probe_overlay.gd` with the ecosystem path, press H in
play. The fish-query hook in `wildlife_actor.gd` calls
`river_state_at_position` when present, else the legacy `reach_at`.
