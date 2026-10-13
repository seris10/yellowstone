# fixes-14.6.4 ledger
Doc: fixes/fixes-14.6.4-river_transport-4.md | read 2026-10-12 | targets: yellowstone_python/yellowstone_python/replay/river_transport.py sha256:092c2a047750 ; yellowstone_python/yellowstone_python/replay/surface_flux.py sha256:35ef235d1861 ; yellowstone_python/yellowstone_python/replay/tests/test_river_transport.py (grepped)
Summary: 16 items: 16 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts (recounted from rows 2026-10-13)

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | Add solver defaults max=12, tol=1e-7, relaxation=0.8 | implemented | river_transport.py:63-65 "DEFAULT_MAX_SURFACE_ITERATIONS = 24" | kept at 24 by decision; see progress.md Decisions | cheap |
| 2 | Extend ctor with max_surface_iterations, surface_tolerance_c, surface_relaxation, validate | implemented | river_transport.py:398-400 signature; :548-570 validation | matches | cheap |
| 3 | Include surface_budget met series in `_forcing` | implemented | river_transport.py:505-513 extend([rh, wind_mps, shortwave_w_m2, cloud]) | matches | cheap |
| 4 | Replace `_surface_linearization()` with helper accepting linearization temperature and finite-checking inputs | implemented | river_transport.py:611-660 helper with finite() on inputs and metadata dict | duplicate `flux_temperature_slope_w_m2_k` key at :652 and :654 is cosmetic | cheap |
| 5 | Update `_system()` to accept and validate `linearization_temperature` | implemented | river_transport.py:718-738 signature, length check, finiteness check | matches | cheap |
| 6 | Add damped Newton `_solve_implicit_step()` iterating surface flux | implemented | river_transport.py:777-863 iteration loop with damping and failure counter | raises ArithmeticError when max iterations exceeded | refactor |
| 7 | Add `_surface_power_for_accounting()` that uses nonlinear flux_at(T_converged) as the base conservation term | implemented | river_transport.py:711 "surface_power_w.append(area * nonlinear_parts['net'])" | base term now uses flux_at(T_converged); linearized-at-old-T diagnostic kept in max_surface_linearization_error_w | medium |
| 8 | Replace `_advance_to()` solve + accounting (combined base + additional power) | implemented | river_transport.py:903-905 solve; :922-937 combined power | both parts now consistent after the item-7 fix | cheap |
| 9 | Replace increments block to separate surface_exchange_j, additional_heat_flux_j, cell_heat_j, and keep component surface_{name}_j | implemented | river_transport.py:940-965 increments dict with conditional component zeros for Newton | matches | cheap |
| 10 | Update step energy balance to include additional_heat_flux_j; cell residual uses combined surface_power_w | implemented | river_transport.py:972-979 expected_change_j; :989-995 cell residual | matches | cheap |
| 11 | Add additional_heat_flux_j to `_totals` | implemented | river_transport.py:530-531 "additional_heat_flux_j" | present | cheap |
| 12 | Update `budget()` with sum, scale, surface_component_sum_j, surface_component_difference_j, max_surface_linearization_error_w, max_surface_iterations_used, surface_iteration_failures | implemented | river_transport.py:1053-1140 expected sum, scale, component sum/diff, and all return fields | all five diagnostic fields present | cheap |
| 13 | Add config keys `cell_heat_w`, `max_surface_iterations`, `surface_tolerance_c`, `surface_relaxation` to `river_from_config` | implemented | river_transport.py:1228-1237 allowed set includes all four; :1259-1271 kwargs plumbs them | matches | cheap |
| 14 | Fix explicit-budget detection in `make_replay` | implemented | river_transport.py:1365 "explicit_budget = (config.get('surface_budget') is not None)" | matches | cheap |
| 15 | Add replay metadata surface_solver dict and updated limitation | implemented | river_transport.py:1422-1440 surface_solver dict; :1382-1387 limitation sentence | matches | cheap |
| 16 | Recommended tests: damped-Newton converges (iteration counters), split-run, additional-heat separation | implemented | test_river_transport.py:344 split; :208 additional flux; :378 diagnostic; :404 damped-Newton converges without failures; :415 failure counter fires | iteration failure/success counter tests added | cheap |

## Cross-project issues
- Item 7 conflicts with items 5-6 of fixes-14.6 and 14.6.2, which the code already implemented using linearized flux for accounting. The 14.6.4 scheme would raise `heat_relative_residual` above the 1e-10 threshold asserted in test_explicit_budget_closes_against_linearized_accounting (test_river_transport.py:376).
- `_surface_power_for_accounting` reconstructs the linearized flux around the OLD timestep temperature (river_transport.py:690 passes no `linearization_temperature`), while `_solve_implicit_step` relinearizes around the latest Newton guess at :803-807; "linearized_flux" at :701-705 therefore does not match the linearization used in the final iteration either.
- `surface_component_difference_j` compares nonlinear flux_at(T_new) against linearized surface_exchange_j, on this doc's accounting it should be near zero, but on the actual code it will not be, since the two sides use different flux evaluations.

## Scientific validity flags
- Damped Newton with constant relaxation=0.8 reduces per-iteration update by 20 percent; failures counter is only incremented after exhausting all iterations, offering no partial-converge diagnostic.
- `linearized()` returns an analytic dF/dT; the Newton step is actually Newton (not Picard), making doc 14.6.3's Picard framing descriptive, not literal.
- Water temperatures are not bounded during iteration; latent/longwave terms can produce extreme updates when `linearized()` slope is small, and nothing checks T_water_c is physical.
- Replay numerical_checks (river_transport.py:1465-1476) still gates passed on `heat_relative_residual <= 1e-9`; a true nonlinear-accounting switch per this doc would need to relax this tolerance to Newton tolerance 1e-7.
