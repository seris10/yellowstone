# fixes-14.6 ledger
Doc: fixes/fixes-14.6-river_transport-1.md | read 2026-10-12, open rows re-verified 2026-10-13 | targets: yellowstone_python/yellowstone_python/replay/river_transport.py sha256:092c2a047750 ; yellowstone_python/yellowstone_python/replay/surface_flux.py sha256:35ef235d1861 ; yellowstone_python/yellowstone_python/replay/tests/test_river_transport.py sha256:read via grep
Summary: 16 items: 15 implemented, 0 shortcut, 0 partial, 1 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | Add rh/wind/shortwave/cloud to `_forcing` so run() splits at met changes | implemented | river_transport.py:505-513 "if self.surface_budget is not None: forcing_series.extend([...])" | matches doc exactly | cheap |
| 2 | Validate met series share end times or grids in `SurfaceBudget.__post_init__` | missing | river_transport.py:200 "Met series may have different end times; the solver splits at each change independently." | code declines; doc itself recommends not applying it | cheap |
| 3 | Add `_surface_linearization()` helper returning exchange, rhs, metadata | implemented | river_transport.py:611-660 "def _surface_linearization" | duplicate `flux_temperature_slope_w_m2_k` key at 652 and 654 is cosmetic | cheap |
| 4 | Replace surface branch inside `_system()` with the helper | implemented | river_transport.py:751-767 "exchange, surface_rhs, _metadata = self._surface_linearization(...)" | matches intended refactor | cheap |
| 5 | Add `_surface_power_for_accounting()` using linearized flux consistent with solver | implemented | river_transport.py:662-716 "surface_power_w.append(area * linearized_flux)" | linearization anchor is old-T; matches doc #5 | cheap |
| 6 | Replace surface accounting in `_advance_to()` with helper | implemented | river_transport.py:929-931 "self._surface_power_for_accounting(new, start_s)" | matches | cheap |
| 7 | Separate `additional_heat_flux_j` from surface budget components | implemented | river_transport.py:924-938, 946-948 "surface_exchange_j": dt_s*fsum(base_surface_power_w); "additional_heat_flux_j": dt_s*fsum(additional_heat_power_w) | component totals exclude extra flux | cheap |
| 8 | Add `additional_heat_flux_j` to `_totals` initialization | implemented | river_transport.py:530-531 "additional_heat_flux_j" | present | cheap |
| 9 | Update increments dict in `_advance_to()` with new terms | implemented | river_transport.py:940-965 "increments = { ... 'additional_heat_flux_j': ... }" | matches | cheap |
| 10 | Keep cell residual using combined `surface_power_w[i]/rho_cp` | implemented | river_transport.py:989-995 "expected = self.rho_cp * dt_s * math.fsum((... surface_power_w[i]/self.rho_cp ...))" | combined base+additional | cheap |
| 11 | Add `additional_heat_flux_j` to `budget()` expected sum and energy_scale | implemented | river_transport.py:1053-1077 "totals['additional_heat_flux_j']" in expected_change_j and energy_scale fsum | matches | cheap |
| 12 | Fix `make_replay()` explicit-budget detection and allow `cell_heat_w` | implemented | river_transport.py:1365 "explicit_budget = (config.get('surface_budget') is not None)"; 1231,1259 cell_heat_w in allowed and kwargs | both parts done | cheap |
| 13 | Track `max_surface_linearization_error_w` and expose in `budget()` | implemented | river_transport.py:546 "self.max_surface_linearization_error_w = 0.0"; 707-710 max update; 1126-1128 in budget | reports per-cell max | cheap |
| 14 | Consider Picard/nonlinear iteration for higher physical accuracy | implemented | river_transport.py:777-863 `_solve_implicit_step` damped-Newton loop | exceeds doc "consider" scope by shipping damped Newton | refactor |
| 15 | Add regression tests for forcing splits, closure, additional-flux separation, null-budget detection | implemented | test_river_transport.py:344 split; :367 closure; :208 additional flux; :406 null-budget metadata | equivalent coverage with different names | cheap |
| 16 | Add surface_accounting metadata and updated limitations in `make_replay()` | implemented | river_transport.py:1412-1421 "surface_accounting": {method, additional_heat_flux_separate, nonlinear_surface_flux_diagnostic}; 1382-1387 limitations | matches | cheap |

## Cross-project issues
- Default `DEFAULT_MAX_SURFACE_ITERATIONS=24` (river_transport.py:63) differs from doc #14's suggested 8; also from fixes-14.6.3/14.6.4's suggested 12.
- `_surface_power_for_accounting` reconstructs linearized_flux around the OLD timestep temperature (line 690 passes no `linearization_temperature`), but `_solve_implicit_step` relinearizes around the current Newton guess at each iteration; the "linearized" flux reported for accounting is therefore not the linearization that the final Newton iteration used.
- test_prescribed_surface_power_changes_storage (test_river_transport.py:208) covers doc's "test_additional_heat_flux_has_separate_budget_term" but with different field assertions (storage_change_j vs heat_relative_residual).

## Scientific validity flags
- Explicit-budget accounting uses a one-sided linearization anchored at the old timestep temperature, so reported `surface_exchange_j` is not the nonlinear F(T_converged); `max_surface_linearization_error_w` is a diagnostic, not a corrective term.
- Component totals (shortwave/longwave/sensible/latent) are evaluated via nonlinear `flux_at(T_new, met_at_start_s)` while the accounting net uses linearized flux: `surface_component_difference_j` can be nonzero even when `heat_relative_residual` is near machine precision, by construction.
- WIND_FLOOR_MPS=0.5 (surface_flux.py:42) and other coefficients remain illustrative; closure of the discretized equation does not imply physical validity.
