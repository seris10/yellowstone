# fixes-14.6.3 ledger
Doc: fixes/fixes-14.6.3-river_transport-3.md | read 2026-10-12 | targets: yellowstone_python/yellowstone_python/replay/river_transport.py sha256:092c2a047750 ; yellowstone_python/yellowstone_python/replay/tests/test_river_transport.py (grepped)
Summary: 12 items: 12 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts (recounted from rows 2026-10-13)

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | Add defaults DEFAULT_MAX_SURFACE_ITERATIONS=12, DEFAULT_SURFACE_TOLERANCE_C=1e-7, DEFAULT_SURFACE_RELAXATION=0.8 | implemented | river_transport.py:63-65 "DEFAULT_MAX_SURFACE_ITERATIONS = 24" | kept at 24 by decision (test_polish_stays_in_bounds needs it); recorded in progress.md Decisions | cheap |
| 2 | Add constructor parameters max_surface_iterations, surface_tolerance_c, surface_relaxation | implemented | river_transport.py:398-400 ctor signature | matches | cheap |
| 3 | Validate ctor parameters (int+positive iterations, positive tolerance, (0,1] relaxation) | implemented | river_transport.py:548-570 validation block | guards bool, non-int, non-positive, out-of-range | cheap |
| 4 | Core damped Newton solver `_solve_implicit_step()` with iteration + damping + convergence check | implemented | river_transport.py:777-863 "_solve_implicit_step" | one-shot path for Newton-lumped at :789-793; iteration path for explicit budget | refactor |
| 5 | Modify `_system()` to accept linearization_temperature list | implemented | river_transport.py:718-738 signature and validation | validates length and finite values | cheap |
| 6 | Update `_surface_linearization()` to accept per-cell linearization temperature | implemented | river_transport.py:611-660 param `linearization_temperature` | passes value through to flux0, slope and metadata | cheap |
| 7 | Call `_solve_implicit_step()` from `_advance_to()`, replacing direct tridiagonal solve | implemented | river_transport.py:905-907 "new, surface_iterations = self._solve_implicit_step(start_s, dt_s)" | matches | cheap |
| 8 | Track `max_surface_iterations_used` across the run | implemented | river_transport.py:836-839 "self.max_surface_iterations_used = max(...)" | updated on each successful iteration | cheap |
| 9 | Initialize `max_surface_iterations_used = 0` in `__init__` | implemented | river_transport.py:572 "self.max_surface_iterations_used = 0" | present | cheap |
| 10 | Include iteration count in `budget()` output | implemented | river_transport.py:1135-1137 "max_surface_iterations_used" in return dict | also surface_iteration_failures at :1138-1140 | cheap |
| 11 | Accounting after convergence uses nonlinear flux_at(T_converged) for base_surface_power_w | implemented | river_transport.py:711 "surface_power_w.append(area * nonlinear_parts['net'])" | accounting now uses flux_at(T_converged); 14.6/14.6.2 closure test tolerance derived from surface_tolerance_c | medium |
| 12 | Add replay metadata surface_solver dict (method, max_iterations, tolerance, relaxation, usage counters) | implemented | river_transport.py:1422-1440 "surface_solver" dict | includes max_surface_linearization_error_w and iteration_failures | cheap |

## Cross-project issues
- Item 11 conflicts with the accounting choice in fixes-14.6 §5-6 and fixes-14.6.2 §6, which the code follows: using nonlinear flux_at(T_converged) would raise `heat_relative_residual` above the 1e-10 threshold asserted in test_explicit_budget_closes_against_linearized_accounting (test_river_transport.py:376).
- No test asserts `max_surface_iterations_used >= 1` or `surface_iteration_failures == 0`; replay metadata exposes these but regression coverage is nil (grep for `iteration_failures`/`max_surface_iterations_used` in tests returned no hits).
- Damped Newton default relaxation=0.8 means a geometric convergence rate; combined with tolerance 1e-7 and 24 iterations, worst-case iteration-count failures are possible under stiff latent-heat conditions, but no benchmark run documents expected iteration counts.

## Scientific validity flags
- Linearization inside `_surface_linearization` uses `linearized()` from surface_flux.py, which derives dF/dT analytically for the net flux: this makes the Newton iteration a true Newton step, not Picard, despite doc §Picard framing.
- Damped Newton with constant relaxation reduces convergence rate; for strongly nonlinear latent-heat regimes a line search or trust region would be safer, but neither is implemented.
- Code does not guard against nonphysical water temperatures (e.g., T<0 or T>100C) during iteration; `linearized()` and `flux_at()` accept any finite input.
