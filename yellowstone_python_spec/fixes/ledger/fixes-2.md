# fixes-2 ledger
Doc: fixes/fixes-2.md | read 2026-10-12 | targets: yellowstone_python/yellowstone_python/coupling.py sha256:358e7d4f55a0 ; yellowstone_python/yellowstone_python/equations.py sha256:ddffa6ae4249 ; yellowstone_python/yellowstone_python/compare.py sha256:0c9388ac0755 ; yellowstone_python/yellowstone_python/claims.py sha256:e9534e55ba4f
Summary: 17 items: 17 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | reconcile Newton flux sign convention with equation text | implemented | equations.py:62-64 | `Newton: Phi = h(T_air - T)` matches `positive into water` contract in coupling.py | cheap |
| 2 | rename `d_heat_throughput` to `d_heat_budget_error` (or report both) | implemented | compare.py:225-229 | output `heat_budget` block reports residual per side plus `delta_residual_j` | cheap |
| 3 | compare_builds reports structural ID adds/removes instead of KeyError | implemented | compare.py:145-147,156-158,180-182 | `_index_records` + `common/only-A/only-B` sets replace raw indexing | medium |
| 4 | reorder the pocket-collision check so it is reachable | implemented | coupling.py:349-357 | tributary-labeled solver cells raise `pocket ... collides with a solver cell id` before the mapped-cell continue | cheap |
| 5 | coupling duration uses frames[-1].t_s - frames[0].t_s and validates monotonicity | implemented | coupling.py:308-316 | `frame_times` built via `_finite_float`; strict-increase check gates the duration | cheap |
| 6 | validate_contract / validate_inventory use .get() to avoid KeyError | implemented | coupling.py:174-200 ; equations.py:181-203 | id lists built with `.get()` and skip rows where id is missing | cheap |
| 7 | claims.validate_claim adds list/string schema validation | implemented | claims.py:27-47,278-294 | `LIST_FIELDS` and `STRING_FIELDS` enforced by isinstance checks | medium |
| 8 | artifact path validation prevents traversal via `resolve().relative_to(base)` | implemented | claims.py:248-252 | `full.relative_to(base)` rejects paths that escape the project root | cheap |
| 9 | split_artifact_id tightens delimiter and validates split value | implemented | claims.py:62-63,220-228 | `VALID_SPLITS` enforced with a listed error message | cheap |
| 10 | check_coupling validates list/dict shape before indexing cells/sources/inventory | implemented | coupling.py:203-220,254-272 | `_records_with_ids` guards lists and dicts for cells, sources, inventory | medium |
| 11 | finite-number validation on `lateral_input_m3` and related budget values | implemented | coupling.py:223-231,330-339 | `_finite_float` guards budget and source flows; `actual is None` branch records a failure | cheap |
| 12 | distinguish absent-vs-empty for inventory and budget checks | implemented | coupling.py:258-266,273-294,311-329 | missing forcing, forcing.sources, hydraulics_summary, thermal_inventory, final_budget, frames each emit a named failure distinct from the empty case | cheap |
| 13 | validate_inventory enforces non-empty strings, module paths, allowed model_levels | implemented | equations.py:181-199 | per-field presence and non-empty-string check, optional module-on-disk check via `root` | medium |
| 14 | tighten dimensional language (Qout = Qin + Qhot; d(ViTi)/dt enthalpy) | implemented | equations.py:15-19,28,52 | equations state `rho*cp*d(V_i*T_i)/dt`, `Q_l` instead of `Q_hot`; `rho and cp constant` recorded in both assumptions | cheap |
| 15 | compare._load wraps FileNotFound and JSONDecodeError with path context | implemented | compare.py:24-32 | both exceptions re-raised with the full `path` in the message | cheap |
| 16 | compare_builds verifies build model/version/replay-window comparability | implemented | compare.py:67-111,122-142 | `_load_build_manifest` + `_compatibility_report`; refuses incompatible pairs unless `--allow-incompatible` | medium |
| 17 | trout `relocated` compares final location, not just start_point_index | implemented | compare.py:114-116,169-171 | `_refuge_location` compares reach_id, end_point_index, refuge_s_m, start_point_index | cheap |

## Cross-project issues
- Fix 4 (pocket-collision reachability) interacts with the landscape-cell loop that also handles mapped solver cells; `aquatic_foodweb.append_tributary_cells` IDs (trib_rabbit_creek, trib_mallard_creek) must not clash with any `cell["id"]` from `build_mapped_replay`.
- Fix 5 (duration) must align with `replay/river_transport.py` frame times and with `build.py` manifest `grid_and_time_step.replay_duration_s`.
- Fix 8 (path traversal) must stay compatible with claim seed datasets listed in claims.py:47-85 which already use project-relative paths with `:train`/`:holdout` splits.
- Fix 17 (relocated) relies on fields the current `fish.py` build writes (`reach_id`, `end_point_index`); schema already carries them per build.py:1086-1093.

## Scientific validity flags
- Even after fix 1, `coupling.EXCHANGES[surface_newton]` claims the lumped Newton exchange is a `"conserved"` quantity (coupling.py:93), but the method itself is dissipative at the air-water interface; label is contractually convenient, not thermodynamic.
- `d(V_i T_i)/dt` in equations.py:21 is dimensionally temperature-volume-per-time, not enthalpy; `rho c_p` factor is implicit and never stated.
- `thermal_inventory` set-equality against sources (coupling.py:209-212) assumes one solver `Source` per ecosystem lateral, which depends on `river_transport` not merging duplicate chainage attachments.
- `compare.py` reports `d_insect_activity` and `d_snow_mm` without any check that both builds used the same forcing window or run_mode, so A/B deltas may be apples-to-oranges even once fix 16 lands.
