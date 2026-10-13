# fixes-12 ledger
Doc: fixes/fixes-12.md | read 2026-10-12 | targets: yellowstone_python/replay/datasets.py sha256:8392c68c3160 ; yellowstone_python/replay/figures.py sha256:567a557d86e4 ; yellowstone_python/replay/hydraulics.py sha256:07f159427f88 ; yellowstone_python/replay/identifiability.py sha256:cb6e466cc053
Summary: 37 items: 36 implemented, 0 shortcut, 0 partial, 0 missing, 1 superseded, 0 conflicts (R-c3 2026-10-12 reverified datasets 1-7, hydraulics 18-27, hydraulics 24 stale Oct 2026 removed, hydraulics 20 superseded by design decision; R-c2 2026-10-12 closed figures items 8-17 and identifiability items 28-32, 36-37)

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | report dataset intervals, not aggregate min/max window | implemented | datasets.py:51-71 | `_bundle_intervals` returns contiguous [epoch,epoch] intervals split at 7-day gap_s | cheap |
| 2 | validate epoch types in bundle series | implemented | datasets.py:24-31 | `_epoch` validates row-shape and `math.isfinite` on numeric epoch | cheap |
| 3 | validate observation row structure in _bundle_range | implemented | datasets.py:24-48 | `_epoch` rejects non-sequence/empty rows; `_collect_epochs` validates sites and met mappings | cheap |
| 4 | distinguish selector-vs-artifact mismatch in role membership | implemented | datasets.py:114-126,147-159 | `_claim_membership` returns present/absent/selector_mismatch/malformed; `role_errors` branches accordingly | cheap |
| 5 | guard get_claim errors in role_errors | implemented | datasets.py:138-142 | try/except around `get_claim` capturing KeyError, ValueError, FileNotFoundError | cheap |
| 6 | cache resolved artifacts between role_errors and window_errors | implemented | datasets.py:74-78,84-98,131-137,173 | `_resolve_cached` with a per-call dict; `window_errors(cache=)` accepts the cache from `role_errors` | cheap |
| 7 | check calibration/development/duplicate role overlaps | implemented | datasets.py:160-171 | records multi-role assignments and within-role duplicate ids | medium |
| 8 | shade holdout (or non-zero train) correctly in fit_holdout_figure | implemented | figures.py:97-99 | `axvspan(hours[holdout_start=train.stop], hours[-1])` shades the holdout span, matching the label | cheap |
| 9 | handle perfect-fit (empty qq) in residual_figure/build_all | implemented | figures.py:155-174,276 | residual_figure validates qq_normal/qq_empirical equal length and shows "Q-Q unavailable" annotation on empty; build_all uses `resid.get("qq") or {}` | cheap |
| 10 | validate series lengths and slice bounds in figure functions | implemented | figures.py:35-43,60-70,81-84 | `_check_sizes` and `_validate_slice` called from fit_holdout_figure; series lengths kept consistent before matplotlib | cheap |
| 11 | convert Sequence inputs to list once per figure | implemented | figures.py:89-94,146-156,165-169,223 | fit_holdout_figure/residual_figure/refuge_profile_figure wrap each Sequence arg in list() once | cheap |
| 12 | document/rename target_holdout contract in bands_figure | implemented | figures.py:112-116,127-128 | bands_figure signature now uses target_holdout and the docstring states the holdout slice has already been applied by the caller | cheap |
| 13 | ridge_figure: use isclose on c_mult membership | implemented | figures.py:184-185 | `math.isclose(r["c_mult"], best_c, rel_tol=0.0, abs_tol=1e-12)` | cheap |
| 14 | ridge_figure: raise clear error on empty row subset | implemented | figures.py:186-187 | `if not pts: raise ValueError(f"no ridge rows found for c_mult={best_c}")` | cheap |
| 15 | derive STATUS_NOTE from artifact status | implemented | figures.py:24-32,247-249 | `_resolve_status_note(uq_doc, lsfit_doc, fit_doc)` returns the first explicit `status` string; build_all sets `STATUS_NOTE` to it; `DEFAULT_STATUS_NOTE` kept as fallback | cheap |
| 16 | use figure.savefig/clf instead of pyplot.close | implemented | figures.py:53-57 | `_save` uses `fig.savefig(...)` + `fig.clf()`, no pyplot global | cheap |
| 17 | tighten CLI error handling (don't catch broad base classes) | implemented | figures.py:329-332 | except catches ValueError, KeyError, IndexError, TypeError, ArithmeticError, OSError and reports the exception class name | cheap |
| 18 | require positive velocity in fischer_dispersion_m2_s | implemented | hydraulics.py:195-199 | `_positive(velocity_m_s, ...)` and `_positive(shear_velocity_m_s_, ...)` both raise on zero | cheap |
| 19 | handle constant-nonzero residuals in residual_diagnostics | implemented | hydraulics.py:421-434 | perfect_fit branch returns `constant_residual: True`; constant nonzero branch returns `constant_residual: True`, empty qq, `max_qq_gap: None` | cheap |
| 20 | reconcile MIN_SLOPE_FOR_MANNING threshold across functions | superseded | hydraulics.py:54-57 | design decision: cell_hydraulics applies the policy noise floor and the low-level helpers accept any positive slope; the module comment at the constant states this contract; recorded as a decision rather than reconciled to a single threshold | medium |
| 21 | normalize slope before storing in cell_hydraulics record | implemented | hydraulics.py:238-239,255 | `grade = None if slope is None else _finite(slope, "slope")` once; record stores `grade` under key `slope` | cheap |
| 22 | document that froude_number allows zero velocity | implemented | hydraulics.py:163-164 | docstring says "Zero velocity returns 0.0 by design; <1 subcritical, =1 critical, >1 supercritical" | cheap |
| 23 | avoid mutating CROSS_SECTION_PROVENANCE global | implemented | hydraulics.py:76-86 | `load_usgs_cross_section` returns a per-call attempt record; no module-global mutation | cheap |
| 24 | remove hard-coded "Oct 2026" future-dated claim | implemented | hydraulics.py:47-49 | stale "Oct 2026 format change" and "REAL DATA STATUS" ALL-CAPS block removed; replaced with factual authored-defaults sentence; `CROSS_SECTION_PROVENANCE.integration_notes` reduced to a neutral `load_usgs_cross_section is the ingestion hook` | cheap |
| 25 | validate scheduled source schema in thermal_inventory | implemented | hydraulics.py:451-475,499 | `_validate_scheduled_source` checks `times_s`/`values` presence, sequence-ness, nonempty, equal length, and finite entries; invoked from `thermal_inventory` for every dict temperature_c | cheap |
| 26 | report scheduled vs constant flow separately | implemented | hydraulics.py:489-525 | returns `n_scheduled_sources`, `total_thermal_flow_m3_s`, `constant_temperature_flow_m3_s`, `scheduled_flow_m3_s` with an explicit `flow_weighted_entry_basis` string | cheap |
| 27 | move optional NumPy/SciPy imports inside functions | implemented | hydraulics.py:371-372,407-408 | numpy and scipy.stats imported inside `skill_scores` and `residual_diagnostics`; module scope stays dependency-light; identifiability.py scope stays with R-c2 | cheap |
| 28 | validate jacobian shape and finiteness in conditioning | implemented | identifiability.py:90-102 | rejects non-2D, empty, nonfinite Jacobians and records `rank_tol` | cheap |
| 29 | validate finite-difference step in jacobian_at_truth | implemented | identifiability.py:73-78 | `step` validated finite and > 0 before use | cheap |
| 30 | validate starts (length and finiteness) in multistart_fit | implemented | identifiability.py:114-142 | validates nonempty starts, matching length, finite values, and inside PARAM_BOUNDS | cheap |
| 31 | handle zero truth in relative-spread calculation | implemented | identifiability.py:153-161 | if `|truth[i]|` is 0.0, uses absolute spread instead of relative | cheap |
| 32 | validate structural_surface_spread parameters | implemented | identifiability.py:168-183 | `duration_s > 0`, `dt_s > 0`, `dt_s <= duration_s`, both finite | cheap |
| 33 | add SALib analyzer compatibility fallback | implemented | identifiability.py:270-277 | TypeError fallback drops `seed` for the analyzer call | cheap |
| 34 | validate sobol_screen parameters | implemented | identifiability.py:220-230 | bool/int checks for n_base, seed, calc_second_order | cheap |
| 35 | document Sobol objective in output | implemented | identifiability.py:283-287 | `"objective"` field describes scalar | cheap |
| 36 | record numerical settings in diagnostics output | implemented | identifiability.py:295-312 | run_diagnostics output records finite_difference_step, rank_tol, param_bounds, truth under `numerical_settings` | cheap |
| 37 | prune or lazy-load unused eager imports | implemented | identifiability.py:16-22,75,93,244 | module scope only imports math + typing; numpy is lazy inside jacobian_at_truth / conditioning / sobol_screen | cheap |

## Cross-project issues
- `figures.build_all` is now robust to perfect fits: `residual_diagnostics` returns `qq: {}` on perfect/constant residuals, and `build_all` guards with `resid.get("qq") or {}` while `residual_figure` renders a "Q-Q unavailable" annotation.
- Figures still reads `uq_doc["bands"]["seed"]` and `uq_doc["holdout_coverage"]["coverage"]` without an explicit schema check; `build_uq_document` now writes both, but a downstream schema validator is still outstanding (candidate for a validation/checks.py addition, E1 territory).
- CROSS_SECTION_PROVENANCE now returns per-call attempt records; the module global is no longer mutated.

## Scientific validity flags
- `fischer_dispersion_m2_s` rejects zero velocity and zero shear velocity; downstream Peclet-like comparisons remain scoped to flow regimes with defined turbulent transfer.
- `residual_diagnostics` returns an explicit `constant_residual: True` entry (perfect or constant-nonzero) with empty qq and `max_qq_gap: None`; JSON serialization no longer carries a silent NaN autocorrelation.
- The stale "Oct 2026 format change" claim is removed; `CROSS_SECTION_PROVENANCE.integration_notes` now describes the ingestion hook without a dated assertion.
