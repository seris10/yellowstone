# fixes-29 ledger
Doc: fixes/fixes-29-tooling-gates.md | read 2026-10-12, open rows re-verified 2026-10-13 | targets: yellowstone_python/tools/audit_provenance.py sha256:62f952ff090e ; yellowstone_python/tools/compare_bundles.py sha256:7522d4825d6d ; yellowstone_python/tools/validate_obs_bundles.py sha256:7b6101dc62d4 ; yellowstone_python/tools/plot_fit.py sha256:0eb299048bb0 ; yellowstone_python/tools/execute_notebook.py sha256:57d5e9fb2ce0 ; yellowstone_python/tools/build_store.py sha256:19f2c7e150a0
Summary: 8 items: 8 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | plot_fit.py renders spec figure set (grid heat, budget waterfall, peak timing, bands); title carries schema+status | implemented | tools/plot_fit.py:28-37,80-186,208-245,286-332; tests/test_plot_fit.py:40-108 | fig_grid, fig_budget_waterfall, fig_peak_timing, fig_bands added; title tag via new_canvas(doc=...) | medium |
| 2 | compare_bundles.py exposes SNOTEL per-code CLI flags; emits window_shift_s and provenance_note | implemented | tools/compare_bundles.py:26-45,47-62,172-192; tests/test_compare_bundles.py:116-166 | --wteq/--snwd/--temp CLI flags thread snow_tols; window_shift_s is on every firehole series metric; PROVENANCE_NOTE returned on every branch | cheap |
| 3 | validate_obs_bundles.py records bundle_fetched_at_utc on verdict; names unknown-schema rule | implemented | tools/validate_obs_bundles.py:183-192,206-215; tests/test_validate_obs_bundles.py:119-157 | gate_bundle attaches bundle_fetched_at_utc; unknown branch now emits name=unknown-schema | cheap |
| 4 | audit_provenance.py SIDECAR_KEYS reconciled against check_provenance; test pins the list | implemented | tools/audit_provenance.py:35-37; tests/test_audit_provenance.py:103-127 | SIDECAR_KEYS covers the four keys beyond the detector; test asserts each omission raises incomplete-sidecar | cheap |
| 5 | build_store.py translates parse/runtime errors to clean exit; cross-checks source shas vs BUILD.json | implemented | tools/build_store.py:118-141; tests/test_build_store.py:95-131 | wraps JSONDecodeError/OSError/RuntimeError; scans BUILD.json source_shas and deps by basename; warns on unreferenced fit paths | medium |
| 6 | execute_notebook.py docstring describes fail-fast; add opt-in --allow-errors flag | implemented | tools/execute_notebook.py:1-24,33-54; CLI --allow-errors on main | docstring rewritten; execute(allow_errors=True) collects errors in ns["_cell_errors"] | cheap |
| 7 | derived/sinter_grass_cull.json and sinter_tree_cull.json carry status | implemented | derived/sinter_grass_cull.json:2-3; derived/sinter_tree_cull.json:2-3; tests/test_audit_provenance.py:28-42 | status: illustrative_not_calibrated; audit_provenance 0 failures | cheap |
| 8 | comment-style sweep per AGENTS.md section 2 across the six files | implemented | tools/build_store.py:1-2, 24-25, 53-55 | build_store.py docstring is a single line and the helper docstrings describe behavior without AI tells; no em dashes, first person, or temporal references across the six files | cheap |

## Cross-project issues
- Item 5 belongs to E2-a2 ownership (tools/build_store.py). Handoff recorded.
- Items 1 and 2 need no change from other clusters, but a downstream reader of the spec may notice spec-code reconciliation choices documented in the ledger notes.

## Scientific validity flags
- Backfilling sinter_* with illustrative_not_calibrated preserves the honest provenance label; the brightness heuristic is authored and the NAIP ortho source is remotely sensed.
- The provenance_note on compare_bundles.py reports USGS IV and AWDB bundles carry no source version field; fetched_at_utc is the only revision identity available.
