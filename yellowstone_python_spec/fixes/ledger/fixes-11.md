# fixes-11 ledger
Doc: fixes/fixes-11.md | read 2026-10-12 | targets: yellowstone_python/replay/benchmarks.py sha256:d4cfc1ebcf1f ; yellowstone_python/replay/calibrate.py sha256:8945bfc98c34
Summary: 29 items: 29 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | construct cells inside make() in benchmark_restart_equivalence | implemented | benchmarks.py:56-67 | cells now constructed inside `make()`; no shared state between River instances | cheap |
| 2 | _max_abs_diff: reject unequal lengths and empty inputs | implemented | benchmarks.py:46-56 | explicit nonempty + equal-length checks before the max | cheap |
| 3 | _observed_rates: validate finite/nonnegative and handle zero errors | implemented | benchmarks.py:206-224 | validates finite/nonnegative; explicit inf/-inf for zero coarse/fine | cheap |
| 4 | record rate_tolerance and expected_order fields | implemented | benchmarks.py:218,254 | `rate_tolerance=[0.7,1.3]` emitted alongside `expected_order` in temporal and spatial convergence (dispersive, diffusive_decay, mms_traveling_wave keep their own tolerance ranges per-case) | cheap |
| 5 | verify conservative tracer pulse stays off outlet | implemented | benchmarks.py:200-230 | `outlet_tail_mass_fraction` reported; `passed` now requires `tail_fraction < 0.01` over the last tenth of cells | cheap |
| 6 | document diffusive_decay as cell-center vs continuous test | implemented | benchmarks.py:365-373 | docstring states cell-center sampling and the resulting observed order semantics | cheap |
| 7 | strengthen MMS boundary statement (which cells excluded, boundary errors) | implemented | benchmarks.py:455-466 | docstring names the excluded interior cells (0 and n-1) and the boundary-closure provenance | cheap |
| 8 | closed_thermal: assert boundary_input_j and outlet_export_j are zero | implemented | benchmarks.py:122-131 | emits `boundary_input_j`/`outlet_export_j`; `passed` requires both to be exactly 0.0 | cheap |
| 9 | pass time-varying upstream discharge into the solver (or label clearly) | implemented | calibrate.py:484-591 | `run_fit_forward(..., boundary_discharge="mean"|"measured_series")`; default stays `"mean"` for comparability (see progress.md Decisions); `"measured_series"` passes `arrays["up_q_series"]` as a scheduled Series into River so face flows follow the measured hydrograph; output records `boundary_discharge`, `boundary_q_source`, `boundary_discharge_mode`, `discharge_variability_ignored` | medium |
| 10 | normalize/sort every input series before continuity checks | implemented | calibrate.py:95-98 | `interp_series` now rejects duplicate / non-strictly-increasing timestamps after sort | cheap |
| 11 | reject duplicate timestamps explicitly | implemented | calibrate.py:128-131 | `check_continuity` explicitly raises `timestamps must be strictly increasing` on `b <= a` | cheap |
| 12 | validate max_gap_s (finite, positive) in check_continuity | implemented | calibrate.py:125-127 | finite + positive check added before `times` sort | cheap |
| 13 | implement documented bin boundaries in resample_bin_mean (floor-based) | implemented | calibrate.py:91 | `index = int(math.floor((epoch - origin) / dt_s + 0.5))` replaces banker's rounding | cheap |
| 14 | validate grid sort/finiteness/spacing in resample_bin_mean | implemented | calibrate.py:75-84 | explicit finite, strictly-increasing, uniform-spacing checks (tol = 1e-6 * dt_s) | cheap |
| 15 | pulse_moments: reject mismatched lengths and nonpositive volumes | implemented | calibrate.py:241-257 | length check across all three sequences; per-volume finite + positive check | cheap |
| 16 | uniform_pulse_run: validate length, dt, duration, dimensions, sigma | implemented | calibrate.py:290-312 | each parameter validated finite and strictly-positive (dispersion nonnegative) and dt_s <= duration_s | cheap |
| 17 | rename pulse_c to pulse_amplitude_c or document warm/cold | implemented | calibrate.py:277-287 | docstring documents signed-anomaly semantics; keyword kept for API continuity | cheap |
| 18 | reach_heat_fit: validate grids, train_frac, spinup | implemented | calibrate.py:604-617 | nonempty + finite checks on each axis grid; train_frac strictly in (0, 1); spinup_s finite + nonnegative | cheap |
| 19 | record at_parameter_boundary diagnostic for champion | implemented | calibrate.py:664-676 | champion carries `at_parameter_boundary[name] = {at_min, at_max, grid_min, grid_max}` for q_lat/t_lat/c_mult | cheap |
| 20 | Null B: refit q_lat/t_lat with c_mult=0 (not reuse champion laterals) | implemented | calibrate.py:739-755 | when `c_mult=0.0` is absent from the grid, run a nested q_lat x t_lat refit at c_mult=0 and emit `mixing_only_c0_refit` | medium |
| 21 | AIC/BIC parameter counts by name, not fixed tuple order | implemented | calibrate.py:1007-1019 | `null_param_counts` dict keyed on the null name replaces the positional `(0, 2, 1)` tuple | cheap |
| 22 | aic_bic: handle rss == 0 without math-domain error | implemented | calibrate.py:736-754 | `rss == 0.0` returns `aic = bic = -math.inf` and still carries n and k; `rss < 0.0` raises | cheap |
| 23 | least_squares_fit: validate x0 inside LS_BOUNDS | implemented | calibrate.py:770-781 | x0 required, finite-checked per knob, and clamped against each LS_BOUNDS[knob] before scipy call | cheap |
| 24 | validate max_nfev before calling scipy | implemented | calibrate.py:767-769 | `max_nfev` typed as int, strictly positive | cheap |
| 25 | ivp_crosscheck: replace `dt_s % step != 0` with tolerant divisibility | implemented | calibrate.py:960-967 | `sub_steps = round(dt_s / step)`; `abs(dt_s - sub_steps * step) > 1e-9 * dt_s` raises | cheap |
| 26 | ivp_crosscheck: pre-grid hold should fall back to first value | implemented | calibrate.py:941-952 | `hold()` returns `values[0]` when searchsorted lands before the first knot, matching Series.at semantics | cheap |
| 27 | rename budget_ok to euler_budget_ok or compute RK45 budget | implemented | calibrate.py:985-1000 | `euler_budget_ok` emitted; `budget_ok` kept for callers but `budget_ok_scope` names it `euler_only` | cheap |
| 28 | assert run_fit_forward produces len(grid) modeled samples | implemented | calibrate.py:531-535 | explicit `len(modeled) == len(grid)` check raises `ArithmeticError` | cheap |
| 29 | validate build_fit_river geometry and fitted parameters | implemented | calibrate.py:382-402 | finite checks on volume_m3, area_m2, lateral_q/t, c_mult, initial_c; positive/nonnegative constraints and required met Series keys | cheap |

## Cross-project issues
- Null B label `mixing_only_c0_refit` is now always what the output name states: when the champion grid lacks `c_mult=0.0`, a nested q_lat x t_lat refit runs at c_mult=0, so `mixing_only_c0_at_champion_laterals` no longer appears.
- `calibrate.resample_bin_mean` signature returns 3 values (`values, coverage, counts`); docstring and type annotation now state this.
- Benchmark `benchmark_restart_equivalence` relies on `River` copying frozen `Cell` state at construction; the fix is defensive but currently the shared-cells pattern survives because Cell is `@dataclass(frozen=True)` (river_transport.py:85).

## Scientific validity flags
- Default `boundary_discharge="mean"` keeps the measured upstream series collapsed to its arithmetic mean (comparability with existing fits, recorded in progress.md Decisions). `boundary_discharge="measured_series"` drives the full scheduled Series through River so face flows and the water budget follow the measured hydrograph.
- `ivp_crosscheck.hold()` returns `values[0]` for pre-grid times, matching the Series.at semantics the River solver uses, and documents the fallback in its docstring.
- `resample_bin_mean` uses floor-based bin membership on the half-shifted axis, so bin edges are deterministic regardless of index parity.
