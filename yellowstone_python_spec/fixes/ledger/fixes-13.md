# fixes-13 ledger
Doc: fixes/fixes-13.md | read 2026-10-12 | targets: yellowstone_python/replay/surface_flux.py sha256:35ef235d1861 ; yellowstone_python/replay/uncertainty.py sha256:57ddebb5eabe
Summary: 27 items: 27 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts (recounted from rows 2026-10-13)

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | Magnus temperature-range validation in es_kpa | implemented | surface_flux.py:88-114 | rejects t_c outside [-80, 80] C and nonfinite inputs via _temperature_c | cheap |
| 2 | pressure-domain validation in _specific_humidity | implemented | surface_flux.py:117-139 | _check_vapor_pressure rejects negative and above-total-pressure vapor | cheap |
| 3 | BudgetParams: flag/reject out-of-range coefficients | implemented | surface_flux.py:49-69, 251-343 | UserWarning emitted when albedo or emissivity equals 0 or 1, when c_h/c_e exceed BULK_COEFFICIENT_HIGH=1e-2, when shortwave/longwave multipliers fall outside [0.1, 2.0], when longwave_bias_w_m2 magnitude exceeds 100 W/m2; nonfinite and negative values still raise | cheap |
| 4 | reject air_c below absolute zero in longwave path | implemented | surface_flux.py:166-184,196 | _lw_in_w_m2 calls _temperature_c on air_c; MetState.__post_init__ rejects out-of-range air_c | cheap |
| 5 | validate _lw_in_w_m2 inputs independently | implemented | surface_flux.py:166-184 | _temperature_c on air_c, rh in [0,1], cloud in [0,1] enforced locally | cheap |
| 6 | document longwave cloud correction (not emissivity) | implemented | surface_flux.py:17-23 | module docstring states the cloud factor is a per-cloud multiplier on sky emissivity, effective emissivity can exceed 1 under cloud | cheap |
| 7 | add finite-difference regression test for linearized derivative | implemented | yellowstone_python/replay/tests/test_surface_flux.py:75-84 + SymbolicJacobianTests:88-160 | finite-difference + symbolic Jacobian coverage | cheap |
| 8 | expose linearization quality (residual, old/new T) | implemented | river_transport.py:869-889 (`_solve_implicit_step` returns the final Newton residual), river_transport.py:1061-1079 (step dict carries `surface_newton_residual_c`, `temperature_old_min_c`, `temperature_old_max_c`, `temperature_new_min_c`, `temperature_new_max_c`, `max_cell_temperature_change_c`), river_transport.py:1194-1197 (`budget()` reports `max_surface_newton_residual_c`), river_transport.py:1507-1510 (replay surface_solver block echoes it) | solver-side residual plus old/new T diagnostics are now surfaced through step, budget and replay metadata | cheap |
| 9 | parse each Series once in spec_from_series | implemented | surface_flux.py:385-429 | each series parsed once into a `parsed` dict | cheap |
| 10 | allowlist or validate params keys in spec_from_series | implemented | surface_flux.py:420-429 | restricted to BUDGET_PARAM_KEYS; unknown keys raise ValueError | cheap |
| 11 | thread band_level, seed, tol_frac, n_bootstrap, min_members through build_uq_document and record actuals | implemented | uncertainty.py:488-563,603-646 | build_uq_document takes tol_frac/min_members/n_bootstrap/band_level/seed; CLI exposes --band-level/--tol-frac/--min-members/--n-bootstrap/--seed; uncertainty_provenance built from runtime values via uq_provenance | medium |
| 12 | ridge_members: finite champion_train_rmse, int min_members, nonempty results | implemented | uncertainty.py:72-82 | explicit math.isfinite, int-not-bool, nonempty results guards | cheap |
| 13 | validate candidate rows (NaN train_rmse, missing keys, finite params) | implemented | uncertainty.py:83-98 | required_keys check, nonfinite train_rmse dropped, q_lat/t_lat/c_mult finite-checked | cheap |
| 14 | fit_masks: validate grid/spinup; replace raw StopIteration | implemented | uncertainty.py:118-137 | nonempty grid, finite nonneg spinup, strictly-increasing grid, start_candidates list guard, split > start | cheap |
| 15 | ensemble_bands: validate quantile finiteness, trajectory length, band_width | implemented | uncertainty.py:156-193 | quantile finiteness, int-not-bool n_bootstrap, int-not-bool seed, member length consistency, timestep > 0, finite trajectories | cheap |
| 16 | band_coverage: validate finiteness and lo<=hi | implemented | uncertainty.py:200-218 | finite check per sample, lo<=hi check, interpretation field added | cheap |
| 17 | rename/qualify holdout_coverage as model-ensemble coverage | implemented | uncertainty.py:211-216 | band_coverage output carries an interpretation string stating ensemble-not-predictive | cheap |
| 18 | validate oat_fit perturbation values by knob | implemented | uncertainty.py:231-253,268-271 | _FIT_KNOB_BOUNDS + _validate_knob_value reject non-finite and out-of-range values; volume/area zero rejected | cheap |
| 19 | deduplicate baseline-equal OAT perturbations | implemented | uncertainty.py:649-662,676-690 | _dedup_perturbation strips champion-equal values; singleton_grid_boundary_knobs captures empty sweeps | cheap |
| 20 | refuge_weight_oat: do not require weight 0.6 to be present | implemented | uncertainty.py:300-307,325-329 | DEFAULT_REFUGE_WEIGHT constant with math.isclose match; weights [0,1] finite check; explicit missing-default error | cheap |
| 21 | refuge_weight_oat: validate nonempty landscape | implemented | uncertainty.py:308-320 | empty landscape, missing-key, nonfinite-field rejection | cheap |
| 22 | turnover_oat: validate v > 0 and output schema | implemented | uncertainty.py:340-358 | finite positive values, required output keys (prey_totals/trout/dipper and inner emergence/s_m/intake_total) checked | cheap |
| 23 | manning_oat: handle empty ratio set without NaN | implemented | uncertainty.py:376-432 | median_ratio returns (None, 0) on empty set; _round/_delta skip None; z/n and cell inputs validated finite positive | cheap |
| 24 | verify champion params exist in fit_results | implemented | uncertainty.py:498-508 | build_uq_document raises if champ_key tuple is absent from fit_results (math.isclose per field) | cheap |
| 25 | semantic comparison for reproducibility (math.isclose, include RMSEs) | implemented | uncertainty.py:634-646 | reproduces = params_close AND train_rmse_close AND holdout_rmse_close via math.isclose; separate flags recorded | cheap |
| 26 | reuse fit_config (spinup_s, train_frac, dt_s) in fresh fit | implemented | uncertainty.py:625-630,670-674 | fresh fit uses fit_doc.spinup_s/train_frac and CLI --dt-s; dt_s is not persisted in fit_doc, see cross-project notes | medium |
| 27 | generate UQ_PROVENANCE from runtime values | implemented | uncertainty.py:26-60,541-547 | uq_provenance(settings) builds parameters dict from provided actual values; build_uq_document passes runtime knobs | cheap |

## Cross-project issues
- `build_uq_document` now records actuals (tol_frac, min_members, n_bootstrap, band_level, seed, spinup_s, train_frac) through `uncertainty_provenance`; the static `UQ_PROVENANCE` module constant remains for callers that import it directly, but the artifact uses the per-run value.
- `fit_masks` now raises explicit ValueErrors with named conditions (nonempty grid, strictly increasing, spinup leaves usable data); figures.build_all surfaces these through the tightened CLI except handler.
- `refuge_weight_oat` now accepts any weight tuple that includes `DEFAULT_REFUGE_WEIGHT = 0.6` (match via math.isclose) and raises explicitly when it is absent; downstream `shift_vs_default_m` is still anchored to that default so OAT comparisons remain consistent across runs.
- Reproducibility: calibrate.reach_heat_fit stores `spinup_s` and `train_frac` at the artifact top level but not `dt_s`; the uncertainty CLI accepts `--dt-s` and records it in `reproducibility.fit_config.dt_s`. Full round-trip equivalence requires calibrate.py to persist `dt_s` too (handoff to R-a2).

## Scientific validity flags
- Magnus `es_kpa` has no domain guard; at t_c = -243.04 the denominator is zero. Any upstream value flowing through flux_at that approaches the cold limit will overflow or NaN.
- Specific humidity denominator `pressure_kpa - 0.378 * es` is unguarded; a hot water temperature at a low site pressure can produce negative or infinite humidity before the flux loop sees it.
- Reported `holdout_coverage` carries an explicit `interpretation` string documenting it as model-ensemble coverage, not a calibrated predictive interval; the field name is kept for schema stability.
