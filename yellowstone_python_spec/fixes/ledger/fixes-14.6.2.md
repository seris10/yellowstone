# fixes-14.6.2 ledger
Doc: fixes/fixes-14.6.2-river_transport-2.md | read 2026-10-12 | targets: yellowstone_python/yellowstone_python/replay/river_transport.py sha256:092c2a047750 ; yellowstone_python/yellowstone_python/replay/surface_flux.py sha256:35ef235d1861 ; yellowstone_python/yellowstone_python/replay/tests/test_river_transport.py (grepped)
Summary: 16 items: 16 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts (recounted from rows 2026-10-13)

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | Add `max_surface_linearization_error_w = 0.0` diagnostic in `__init__` | implemented | river_transport.py:546 "self.max_surface_linearization_error_w = 0.0" | present | cheap |
| 2 | Extend `_forcing` with surface_budget met series | implemented | river_transport.py:505-513 extend([rh, wind_mps, shortwave, cloud]) | matches | cheap |
| 3 | Add `additional_heat_flux_j` to `_totals` | implemented | river_transport.py:530-531 "additional_heat_flux_j" in totals tuple | present | cheap |
| 4 | Add shared `_surface_linearization()` helper with metadata, finite checks | implemented | river_transport.py:611-660 helper returns exchange, rhs, metadata | duplicate `flux_temperature_slope_w_m2_k` key at :652,:654 is cosmetic | cheap |
| 5 | Use helper in `_system()` loop | implemented | river_transport.py:751-767 "exchange, surface_rhs, _metadata = self._surface_linearization(...)" | matches | cheap |
| 6 | Add `_surface_power_for_accounting()` using linearized flux for closure + nonlinear components as diagnostics | implemented | river_transport.py:662-716 surface_power_w uses linearized_flux; component_power_w uses nonlinear parts | tracks max_surface_linearization_error_w per-cell | cheap |
| 7 | Replace surface handling in `_advance_to()` with helper, split base and additional powers | implemented | river_transport.py:924-938 base_surface_power_w, additional_heat_power_w, combined surface_power_w | matches cleaner form | cheap |
| 8 | Replace increments dict with new surface_exchange_j, additional_heat_flux_j and component diagnostics | implemented | river_transport.py:940-965 increments dict + conditional surface_{name}_j zeros for Newton | matches | cheap |
| 9 | Update step energy balance to include `additional_heat_flux_j`; keep cell residual using combined surface_power_w | implemented | river_transport.py:972-979 expected_change_j; :989-995 cell expected uses surface_power_w[i]/rho_cp | matches | cheap |
| 10 | Update `budget()` sum, energy_scale, and add max_surface_linearization_error_w | implemented | river_transport.py:1053-1077 expected and scale include additional_heat_flux_j; :1126-1128 diagnostic | matches | cheap |
| 11 | Add `surface_component_sum_j` and `surface_component_difference_j` to `budget()` | implemented | river_transport.py:1080-1093 compute both; :1129-1132 return them | matches | cheap |
| 12 | Add `cell_heat_w` to `river_from_config()` allowed and kwargs | implemented | river_transport.py:1231 allowed set, :1259 kwargs | matches | cheap |
| 13 | Fix explicit-budget detection to `is not None` | implemented | river_transport.py:1365 "explicit_budget = (config.get('surface_budget') is not None)" | matches | cheap |
| 14 | Add surface_accounting metadata and updated explicit-budget limitation in `make_replay()` | implemented | river_transport.py:1412-1421 surface_accounting dict; :1382-1387 limitations | matches | cheap |
| 15 | Add 5 regression tests (forcing split, closure+diagnostic, additional-flux separation, null-budget metadata, cell_heat_w config round-trip) | implemented | test_river_transport.py:344,367,378,208,406,443 all 5 present | cell_heat_w round-trip through `make_replay` added at :443 | cheap |
| 16 | Documented interpretation: heat_relative_residual vs linearization error vs component difference | implemented | river_transport.py:1126-1132 reports linearization error + component diff; :1382-1387 limitations state linearized closure | reporting matches doc's interpretation guidance | cheap |

## Cross-project issues
- Same accounting mismatch as 14.6: `_surface_power_for_accounting` reconstructs linearized flux around OLD timestep temperature while `_solve_implicit_step` (14.6.3/14.6.4 Newton) relinearizes around the current guess.
- `surface_component_difference_j` compares nonlinear flux_at(T_new) with linearized-at-OLD-T; a converged Newton solution does not make this term small, because the comparison baseline is still the old-T linearization.
- cell_heat_w test coverage uses only direct constructor path (test_river_transport.py:94), leaving `river_from_config` config-path regression unverified.

## Scientific validity flags
- Component totals (surface_shortwave_j etc.) are evaluated at `t=start_s` met and `T=new_temperature`; they are not time-integrated nonlinearly across the step and sum does not equal the linearized surface_exchange_j by construction.
- `max_surface_linearization_error_w` is in watts (instantaneous per-cell), not joules; it is not directly commensurate with `surface_component_difference_j`.
- Explicit budget still carries illustrative coefficients (surface_flux.py defaults); numerical closure is not physical calibration.
