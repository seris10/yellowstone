# Spec: tools/plot_fit.py — diagnostic figures from fit artifacts

Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].
No code written; no deletions. Target: `tools/plot_fit.py` in `../../yellowstone_python/`.

## 1. Purpose + non-goals

Purpose: generate diagnostic figures from fit artifacts so holdout skill, grids, and budgets are visible without hand-plotting. No plotting tool exists today (`tools/*.py` has zero matplotlib/PIL imports, verified); the only figure pipeline is census overlays (Pillow) and build PNGs.

Non-goals: no publication graphics; no interactive display; no new runtime dependency without the decision in §9 being recorded in the spec's dependency section (the brief's open question — resolved below with evidence).

## 2. CLI (`--help` text drafted)

```
usage: plot_fit.py --artifact PATH --out-dir DIR [--type {reach_heat,snow_snotel,aquatic_intervention,reach_uq,auto}]

Render diagnostic PNGs from a fit artifact. Exit 0 on success. Exit 1 with
cause on failure. Exit 2 on bad invocation.

options:
  --artifact PATH   fit artifact JSON (required)
  --out-dir DIR     PNG destination (created if missing)
  --type {...}      artifact kind (default: auto, from schema string)
```

## 3. Inputs / outputs with exact schemas

Inputs (transferred schemas/keys):
- `yellowstone.reach_heat_fit.v1`: `grids{q_lat[7],t_lat[7],c_mult[5]}` (245 pts), `champion{q_lat,t_lat,c_mult,train_rmse,train_bias,holdout_rmse,holdout_bias,budget_ok,budget_totals{12 keys incl. heat_relative_residual 2.28e-06},status}`, `top10_train[10]`, `null_models[2]{upstream_persistence, mixing_only_c0_refit}`, `measured_lag{lag_s:900.0, peak_correlation:0.9635}`, `spinup_s 86400.0, train_frac 0.7`. V300000 champion: `{3.5,30.0,1.0, train 0.52906, holdout 0.58829}`.
- `yellowstone.snow_snotel_fit.v1`: `sites{609,924}` each `{n_days 304, train_n 151, holdout_n 153, forcing_gaps, fitted{k_melt, wind_loss}, holdout_swe_mm{n,rmse,bias,mae,max_abs}, null_persistence/null_nomelt rmse, peak_timing_error_days (48/2), depth_check_rmse_mm, ledger_residual_mm, status}`.
- `yellowstone.aquatic_intervention.v1`: `control/pulse{cell_id,s_m,temperature_c,U,feeding,refuge_drive}`, `refuge_shift_m 19.9, emergence_change 98.17, dipper_intake_change 0.1503`, `status: illustrative_not_calibrated`.
- `yellowstone.reach_uq.v1`: `members[5]`, `bands{quantiles [0.05,0.5,0.95], level 0.9, band_width_mean 0.533}`, `holdout_coverage{n:172, n_inside:59, coverage:0.343, nominal:0.9}`, `fit_oat{ranking[10]}`, `reproducibility{fresh vs recorded champion}`.

Outputs: `<out-dir>/<artifact-stem>_<figure>.png` [AUTHORED naming]. Figure list per type [AUTHORED]:
- reach_heat: `grid_holdout_rmse` (heat strip over q_lat×t_lat at champion c_mult + marker), `champion_vs_nulls` (holdout_rmse bars: champion vs 2 nulls), `budget_waterfall` (budget_totals J bars).
- snow_snotel: per-site `holdout_vs_nulls` (rmse bars: holdout vs persistence vs nomelt), `peak_timing` (error days annotated).
- aquatic_intervention: `control_vs_pulse` (6-field side-by-side bars) + `landscape_window` caption rendered as footer text (the field warns short pulses dilute — figure must not crop context).
- reach_uq: `bands` (median + 0.05/0.95 ribbon with coverage `0.343/0.90` annotated — show the miss honestly), `oat_ranking` (top-10 bars).

## 4. Algorithm / rules in numbered steps

1. Load artifact; `--type auto` maps `schema` string → figure set; unknown schema → exit 1 `unknown-schema` (do NOT guess from keys — cf. divergent `reach_fit_V3e5` missing `top10_train` with different `t_lat` grid: figures requiring `top10_train` must refuse cleanly on that file, `missing-panel-data: top10_train`).
2. Render each figure at fixed 1200×800, title embeds `schema + status` (provenance visible ON the figure [AUTHORED]).
3. Footer line on every figure: `status` string + `fetched_at_utc`/`bundle_fetched_at_utc` (figures must not circulate without labels).
4. Write PNGs atomically (`.tmp` + replace); refuse to overwrite a non-PNG file at the target path (`output-exists-not-png`).
5. Print manifest: filenames + byte sizes to stdout.

## 5. Provenance plan

Figures are derived diagnostics: filenames + footers carry the source artifact's `status` verbatim (e.g. `fitted_not_validated_single_window`), never upgraded. The tool adds no `status` of its own beyond the manifest line `plot_fit: <backend>, <artifact schema>` [AUTHORED].

## 6. Error handling

| Failure mode | Exit | Message |
|---|---|---|
| Bad flags / unknown --type | 2 | `parser.error` |
| Unreadable artifact | 1 | `artifact-unreadable: <path>` |
| Unknown schema (auto) | 1 | `unknown-schema: <found>` |
| Missing panel data (e.g. V3e5 top10) | 1 | `missing-panel-data: <key> for <figure>` |
| Backend unavailable | 1 | `backend-unavailable: <backend>: <exc>` |

## 7. Tests (synthetic/offline only)

1. `test_manifest_lists_all_figures` — synthetic reach_heat fixture → expected PNG set listed, files exist, each >10 KB ("non-trivial size" minimum, Agg/Pillow deterministic render).
2. `test_v3e5_refuses_grid_figure` — fixture without `top10_train` → `missing-panel-data`, exit 1 (pins divergent-artifact behavior).
3. `test_footer_carries_status` — (backend exposes text? if Pillow: assert caption string passed to drawer via mock; if Agg: assert `fig.texts` contains status) — backend-dependent assertion chosen at implement time.
4. `test_snow_null_bars` — synthetic snow fixture with known rmses → bar values passed to renderer equal fixture values (mock renderer, no pixel assertion).
5. `test_refuses_overwrite_non_png` — target path occupied by `.json` → exit 1, file untouched.
6. `test_unknown_schema` — `{"schema":"yellowstone.nope.v1"}` → exit 1.

## 8. Acceptance criteria

- [ ] Backend decision recorded with the evidence in §9 (no silent matplotlib addition).
- [ ] All four artifact types render from fixtures; V3e5 handled explicitly.
- [ ] Every PNG carries status + timestamp footer; naming follows §3.
- [ ] Suite green; dependency diff (if any) justified in spec §9.

## 9. Effort + dependencies — the matplotlib question RESOLVED with evidence

Evidence (transferred, verified live 2026-10-10): `requirements.txt:1-7` = numpy, scipy, Pillow, pyyaml, pytest, dataretrieval + comment — matplotlib NOT present. Repo-wide: exactly ONE matplotlib import (`census_validate.py:296-298`, `matplotlib.use("TkAgg")` interactive annotator — NOT Agg); zero `matplotlib.use("Agg")`; Pillow pervasive (10 files, the house image library); `tools/*.py` zero image imports.

Decision [AUTHORED, recommended]: **stay Pillow-only** — bar/ribbon/strip figures needed in §3 are all drawable with `ImageDraw` (bars, lines, text footers); adding matplotlib for four diagnostic panels buys little and adds a heavy dependency against house convention (dependencies need stated reason + bound, `03-python-conventions.md`). If the implementing session finds a panel genuinely needs Agg (e.g. contour rendering — none specified), it must record the justification + pin (`matplotlib>=3.8,<4`) and use `matplotlib.use("Agg")` before `pyplot` (never `TkAgg`), with headless-safe tests. Default: Pillow.

Effort: M (~250 lines + tests, Pillow path). Dependencies: none new under the recommended decision.
