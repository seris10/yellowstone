# fixes-9 ledger
Doc: fixes/fixes-9.md | read 2026-10-12 | targets: yellowstone_python/replay/obs_frame.py sha256:da39d0b7ed52 ; yellowstone_python/replay/obs_model.py sha256:a319a5175cbe ; yellowstone_python/replay/plume2d.py sha256:66379415d8f9
Summary: 24 items: 24 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts (recounted from rows 2026-10-13)

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1.1 | reject leading/trailing gap bridging in to_grid | implemented | obs_frame.py:142 | `limit_area="inside"` plus NaN re-check at 144 | cheap |
| 1.2 | standardize bin labeling between _frame_from_pairs and interval_average | implemented | obs_frame.py:88-94 ; obs_model.py:95-108 | both anchor at first observation and label with left edge of half-open [t0+k*step, t0+(k+1)*step); module docstrings state the shared convention; obs_frame resample explicit label="left"/closed="left"; obs_model returns t0+k*interval_s and test_obs_model updated accordingly | cheap |
| 1.3 | track measured coverage separately from resample bin extent | implemented | obs_frame.py:81-99 ; obs_frame.py:140-154 | _frame_from_pairs and met_frame attach frame.attrs["measured_t_min_s"]/["measured_t_max_s"]/["bin_label_convention"]; gap_report surfaces them alongside bin_label_t_min/max | cheap |
| 1.4 | add finite helpers for step_s, limit, window_steps, dt_s, pair values | implemented | obs_frame.py:68-69,73-79,92-96,186-195 | _finite validates step_s and every pair epoch/value; met_frame validates each cell; rolling_mean validates window_steps and min_periods as >=1 ints | cheap |
| 1.5 | pick one duplicate timestamp policy (reject or average) | implemented | obs_frame.py:84-96 | dedup removed; `resample(...).mean()` averages shared bins | cheap |
| 1.6 | validate met row shape | implemented | obs_frame.py:92-93 | explicit length-6 check with ValueError | cheap |
| 1.7 | correct daily_met_means annotation to list[float] | implemented | obs_frame.py:217 | signature returns `dict[str, list[float]]` | cheap |
| 1.8 | accept upstream_site parameter in aligned_fit_arrays | implemented | obs_frame.py:225-227 | `upstream_site: str = "06036805"` plumbed through | cheap |
| 1.9 | remove calibrate import cycle via shared grid helper | implemented | obs_frame.py:267,282 ; replay/fit_grid.py:1-56 ; calibrate.py:447-453 | new public helper `replay.fit_grid.build_fit_grid(bundle, dt_s, upstream_site)` owns the shared window/grid construction; `obs_frame.aligned_fit_arrays` now imports it instead of `calibrate._fit_forcing_arrays`; `calibrate._fit_forcing_arrays` also routes through `build_fit_grid`, so the two paths share one grid origin by construction; `score_paired_series` is now imported inside each caller in calibrate.py (regime_scores_by_flow, reach_heat_fit, least_squares_fit) to keep .hydraulics off the module-load chain | medium |
| 2.1 | normalize-then-validate before `t0 = min(times)` in interval_average | implemented | obs_model.py:95-105 | pairs validated and normalized before `t0 = min(t for t, _ in pairs)` | cheap |
| 2.2 | preserve empty bins between first and last in interval_average | implemented | obs_model.py:110-117 | iterates `range(k_lo, k_hi + 1)`; absent bins return NaN mean, left-edge label present | cheap |
| 2.3 | validate measurement_error and representativeness in compare | implemented | obs_model.py:120-144 | `_uncertainty` helper + combined_error returned | cheap |
| 2.4 | validate paired-series length and nonempty in compare | implemented | obs_model.py:134-137 | explicit length/empty checks | cheap |
| 2.5 | stronger stage validation (reject negative) | implemented | obs_model.py:76-80 | explicit `stage < 0.0` check | cheap |
| 2.6 | make STATIONS immutable via frozen dataclasses | deferred | obs_model.py:22-67 | still a dict-of-dicts; the file-level provenance note at obs_model.py:24-25 states the mutation contract (treat as immutable, modify via a copy for exploration); callers in replay/calibrate.py and replay/datasets.py never mutate, verified by rg; a frozen-dataclass refactor touches claims.py/datasets.py and is left as a follow-up | medium |
| 3.1 | fix north/south boundary reversal (match docstring) | implemented | plume2d.py:109-115,127-137 | j==nz-1 fixed ambient, j==0 Neumann handled in matrix | cheap |
| 3.2 | document source-vs-boundary precedence | implemented | plume2d.py:155-156 | output records `"boundary_precedence": "source_cells_override_boundary"` | cheap |
| 3.3 | finite+bounds validation on plume params | implemented | plume2d.py:62-83 | finite check and sign checks for extent, D, u, k, source_r | cheap |
| 3.4 | handle k_per_s==0 in plume_metrics without divide-by-zero | implemented | plume2d.py:218-228 | guarded; returns None + status label | cheap |
| 3.5 | check sparse solver output for finiteness | implemented | plume2d.py:144-145 | `np.all(np.isfinite(t))` raise | cheap |
| 3.6 | centerline dimension validation | implemented | plume2d.py:179-183 | explicit nx/nz and length checks | cheap |
| 3.7 | contiguous-segment longest footprint length | implemented | plume2d.py:204-215 | segment loop replaces first/last-index span | cheap |
| 3.8 | handle or reject cold plumes in plume_metrics | implemented | plume2d.py:201-202 | raises if `source_c <= ambient_c` | cheap |
| 3.9 | validate river_m3s and total flow in mixing_rise_c | implemented | plume2d.py:40-46 `_finite` defined; :244-245 validate inputs | module-level `_finite` helper added | cheap |
| 3.10 | label fully-mixed bound as diagnostic anchor | implemented | plume2d.py:298-299 | `"fully_mixed_bound_interpretation"` string emitted | cheap |

## Cross-project issues
- plume2d.mixing_rise_c references `_finite(...)` with no module-level definition; `run_experiment` (and thus the CLI entry) therefore crashes with NameError on first call, this is a real regression introduced by the fix pass.
- aligned_fit_arrays now imports from `replay.fit_grid.build_fit_grid`; the private `calibrate._fit_forcing_arrays` is no longer a cross-module coupling point.
- obs_frame bins at `origin=frame.index[0]` with default left-labels while obs_model.interval_average uses centered labels; cross-module alignment claims in docstrings do not match the code.

## Scientific validity flags
- obs_frame.to_grid uses `limit_direction="forward"` with `limit_area="inside"` and bridges one-sided only; the comment claims interior gaps up to 2x limit fill, but forward-only interpolation does not fill from the trailing side.
- obs_model.interval_average still omits empty bins, so a caller that interprets the output as a regular grid will fuse a gap into the adjacent interval.
- plume2d boundary at j==0 (south, upstream for +z flow) is zero-gradient Neumann; the fix doc flagged this as physically ambiguous for an upstream boundary with positive advection and the current output does not qualify that choice.
