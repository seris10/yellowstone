# fixes-29: tooling gates (audit_provenance, build_store, compare_bundles, validate_obs_bundles, plot_fit, execute_notebook)
Scope:
- yellowstone_python/tools/audit_provenance.py (sha256: 62f952ff090e)
- yellowstone_python/tools/build_store.py (sha256: 19f2c7e150a0)
- yellowstone_python/tools/compare_bundles.py (sha256: 7522d4825d6d)
- yellowstone_python/tools/validate_obs_bundles.py (sha256: 7b6101dc62d4)
- yellowstone_python/tools/plot_fit.py (sha256: 0eb299048bb0)
- yellowstone_python/tools/execute_notebook.py (sha256: 57d5e9fb2ce0)

Specs read:
- yellowstone_python_spec/tooling-spec-audit-provenance.md
- yellowstone_python_spec/tooling-spec-compare-bundles.md
- yellowstone_python_spec/tooling-spec-validate-obs-bundles.md
- yellowstone_python_spec/tooling-spec-plot-fit.md
(census-qa, fetch-met-forcing, channel-geometry-pinning-test, cross-sections-deletion, check-terrain target other modules outside this scope and are left to the fixes docs that cover those modules.)

Callers read: yellowstone_python/AGENTS.md (section 4 and 7), yellowstone_python/yellowstone_python/analysis_store.py (build_file, build_con, ingest_*), yellowstone_python/yellowstone_python/replay/calibrate.py (check_continuity, lines 111-120, 310-317, 690-691), yellowstone_python/yellowstone_python/snow_validate.py (SPLIT_DATE, MAX_FILL_DAYS, in_to_mm, lines 29-79, 158-159), yellowstone_python/yellowstone_python/build.py (zero references to any of these tools), yellowstone_python/notebooks/reach_fit.ipynb and yellowstone_python/notebooks/census_explorer.ipynb (consumers of execute_notebook), yellowstone_python/tests/test_audit_provenance.py, tests/test_compare_bundles.py, tests/test_validate_obs_bundles.py, tests/test_plot_fit.py, tests/test_reach_notebook.py.

Pre-audit state: `python3 tools/audit_provenance.py --dir derived` exits 1 with two failures (sinter_grass_cull.json and sinter_tree_cull.json, both missing `status`). `python3 -m pytest tests/test_audit_provenance.py tests/test_compare_bundles.py tests/test_validate_obs_bundles.py tests/test_plot_fit.py -q` is green (32 passed).

Decision on the two audit failures: the artifacts are wrong, the tool is right. `derived/sinter_grass_cull.json` and `derived/sinter_tree_cull.json` carry a `schema` string (`yellowstone.sinter_grass_cull.v1`, `yellowstone.sinter_tree_cull.v1`) but no `status` field at all. Every other hand-authored artifact in `derived/` carries a `status` from the 8-string vocabulary measured in tooling-spec-audit-provenance.md section 3. These two are the single-authored exception that the spec itself flags in section 3 ("Known-missing today (will fail until backfilled)") and section 8 ("Follow-up (NOT this tool): backfill `status` into `sinter_*`"). Fix: backfill the artifacts; this is covered as a finding below, not as a tool bug.

## Main problems

### 1. plot_fit.py renders a different figure set than its spec

tooling-spec-plot-fit.md section 3 names three reach_heat figures (`grid_holdout_rmse` as a heat strip over q_lat x t_lat at champion c_mult with a marker, `champion_vs_nulls`, and `budget_waterfall` as a J bar chart over `budget_totals`), two snow_snotel figures per site (`holdout_vs_nulls` and `peak_timing`), and for reach_uq a `bands` figure (median + 0.05/0.95 ribbon with coverage annotation) plus `oat_ranking`. The implementation produces:
- `fig_reach_heat` (tools/plot_fit.py:70-93): `<stem>_top10_rmse.png` (bars over `top10_train` train vs holdout) and `<stem>_champion_vs_nulls.png`. The spec's heat-strip grid is missing; the top10 bar chart is a substitute the spec did not call for; `budget_waterfall` is absent, so the stored `champion.budget_totals` 12 keys (including `heat_relative_residual 2.28e-06`) never surface in a figure.
- `fig_snow` (tools/plot_fit.py:96-115): produces only `<stem>_<triplet>_nulls.png`. The spec's `peak_timing` figure (per-site peak_timing_error_days visualization) is absent; peak timing surfaces only as an annotation line on the nulls figure.
- `fig_uq` (tools/plot_fit.py:132-151): produces `<stem>_coverage.png` as two bars (`coverage` vs `nominal`), not the spec's `bands` figure that reads `members[5]` or `bands.quantiles` to draw a median + 0.05/0.95 ribbon. The honest coverage miss (`holdout_coverage.coverage=0.343` against `nominal=0.9`) is reduced to a two-bar card and never shown as a ribbon-vs-truth figure.

Also tools/plot_fit.py:35 titles each figure with `stem + figure name` and leaves schema+status to the footer. Spec section 4 step 2 says: "title embeds `schema + status` (provenance visible ON the figure)".

### Fix
In `fig_reach_heat`: add `fig_grid(doc, out_dir, stem)` that reads `doc["grids"]["q_lat"]` and `doc["grids"]["t_lat"]` with `doc["champion"]["c_mult"]` fixed, slices `doc["top10_train"]` plus any available `grid_rmse` into a 7x7 Pillow heat-strip (ImageDraw rectangles colored by `holdout_rmse` quantile), draws a white marker at `(champion.q_lat, champion.t_lat)`, and writes `<stem>_grid_holdout_rmse.png`. Refuse with `missing-panel-data: grids` on artifacts that only carry `top10_train` and no `grids` block (test fixtures must cover both branches).

Add `fig_budget_waterfall(doc, out_dir, stem)` that iterates `doc["champion"]["budget_totals"].items()` as `bar_groups` with each term labeled in J; annotate `heat_relative_residual`. Keep the existing `_top10_rmse.png` as a secondary panel or drop it; the spec does not require it.

In `fig_snow`: add `fig_peak_timing(doc, out_dir, stem)` that writes a per-site figure showing `peak_timing_error_days` as a bar plus `ledger_residual_mm` and `forcing_gaps.tavg_filled` as annotations.

In `fig_uq`: replace `fig_uq`'s coverage-bars output with `fig_bands` that draws a median line and a 0.05/0.95 ribbon in a 1200x600 panel by reading `doc["members"]` (five trajectories) or `doc["bands"]["quantiles"]`. Annotate "coverage 0.343 vs nominal 0.9" directly on the ribbon so the miss is visible. Keep `oat_ranking` as-is.

Update `new_canvas` to accept and render `title=f"{stem} grid_holdout_rmse  schema={doc['schema']} status={doc['status']}"` so provenance is on the figure, not only in the footer.

### Test
Add to tests/test_plot_fit.py:
- `test_reach_heat_grid_figure_present`: synthetic fixture with `grids={"q_lat":[1,2,3,4,5,6,7],"t_lat":[10,15,20,25,30,35,40],"c_mult":[1.0]}` plus `top10_train`; expect `<stem>_grid_holdout_rmse.png` AND `<stem>_budget_waterfall.png` in the manifest, each >10 KB.
- `test_reach_heat_grid_refuses_without_grids`: fixture with `top10_train` but no `grids` -> `missing-panel-data: grids`.
- `test_snow_peak_timing_figure`: snow fixture -> both `_nulls.png` and `_peak_timing.png` produced per site.
- `test_uq_bands_figure`: synthetic uq fixture with `members` list -> `_bands.png` produced; width-vs-height of the ribbon rect sanity-checked by sampling the saved PNG via Pillow.
- `test_live_v300k_renders_grid`: run `render(LIVE/"reach_heat_fit_v300k.json", ...)`; expect `_grid_holdout_rmse.png` and `_budget_waterfall.png` present. (reach_heat_fit_v3e5.json and reach_polished_fit_v300k.json lack `top10_train`; keep the existing refuse-cleanly contract for those two artifacts.)

Severity: medium. The tool runs, but the figures it produces do not match what the spec says the fit diagnostics should show, so a reader of these PNGs is seeing a different story than the spec commissioned.

---

### 2. compare_bundles.py omits spec-required per-code SNOTEL CLI flags and the provenance_note on reports

tooling-spec-compare-bundles.md section 3 says: "SNOTEL defaults need wider per-code tolerances; spec REQUIRES per-code flags with defaults `wteq_abs_tol_in=2.0, snwd_abs_tol_in=12.0, temp_abs_tol_f=15.0`". The implementation defines these constants (tools/compare_bundles.py:19-24) and uses them in `SNOW_TOLS` (tools/compare_bundles.py:25-27) but does not expose them on the argparse surface (tools/compare_bundles.py:181-188 only accepts `--q-rel-tol` and `--t-abs-tol`). Overriding a per-code SNOTEL tolerance from the command line is impossible today, so a SNOTEL comparison with higher noise cannot be relaxed without editing the source.

Second gap: spec section 5 says the report must carry "`provenance_note` [AUTHORED]" documenting the limitation that USGS/AWDB bundles carry no source version field, so `fetched_at_utc` is the only revision identity. The `compare_bundles` return dict (tools/compare_bundles.py:138-144) emits `schema, status, old, new, passed, verdict, metrics, non_informative` and no `provenance_note` of any kind.

Third gap: spec section 3 names `window_shift_s` as a per-element metric ("firehole series ... `max_abs_delta` over epoch-aligned points + `coverage_delta` (n_old vs n_new) + `window_shift_s` (|t0_old - t0_new|)"). `_series_delta` (tools/compare_bundles.py:32-43) returns `overlap, max_abs, n_old, n_new` only; no `window_shift_s`. The report cannot distinguish "same points, revised values" from "window slid by two hours".

### Fix
Add to the argparse block:

```python
parser.add_argument("--wteq-abs-tol-in", type=float,
                    default=DEFAULT_WTEQ_ABS_TOL_IN)
parser.add_argument("--snwd-abs-tol-in", type=float,
                    default=DEFAULT_SNWD_ABS_TOL_IN)
parser.add_argument("--temp-abs-tol-f", type=float,
                    default=DEFAULT_TEMP_ABS_TOL_F)
```

Thread these through `compare_bundles(...)` as a `snow_tols` dict argument and build `SNOW_TOLS` from them inside the SNOTEL branch instead of reading the module-level constant.

Extend `_series_delta` to return `window_shift_s = abs(old[0] - new[0])` where `old[0]` and `new[0]` are the sorted first epochs after intersection. Emit it as a sibling key next to `max_abs` on each firehole metric.

Add to both `compare_bundles` return branches:

```python
"provenance_note": (
    "USGS IV and AWDB bundles carry no source version field; "
    "fetched_at_utc is the only revision identity available. "
    "Revised values with a newer fetched_at_utc are expected, not drift."
),
```

Cite the two source comments the spec names (tools/fetch_firehole_obs.py:154-155 and tools/fetch_snotel_obs.py:141-143) in a one-line docstring addition. USGS IV revision policy reference: https://help.waterdata.usgs.gov/faq/about-provisional-data (provisional data subject to revision). AWDB equivalent: https://www.nrcs.usda.gov/wps/portal/wcc/home/dataAccessHelp/ (SNOTEL data provisional).

### Test
Add to tests/test_compare_bundles.py:
- `test_snotel_cli_tolerances_override`: subprocess call with `--wteq-abs-tol-in 0.5` and a 1.0-inch WTEQ delta -> exit 1 naming the WTEQ element; same inputs with default 2.0 -> exit 0.
- `test_window_shift_reported`: two firehole bundles with the same values but new window shifted by 7200 s on upstream temperature -> metric for `06036805/temperature_c` carries `window_shift_s=7200.0`.
- `test_report_carries_provenance_note`: identical bundles -> report dict has `provenance_note` and its string contains `fetched_at_utc`.

Severity: medium. The vocabulary and the math are right; the knobs and the self-documenting note the spec required are not reachable from the CLI or the report.

---

### 3. validate_obs_bundles.py verdict does not record the bundle timestamp its spec requires

tooling-spec-validate-obs-bundles.md section 5 says: "Verdict records `bundle` path + `bundle_fetched_at_utc` mirroring the convention in `snow_validate.py:220` and `calibrate.py:462,745`." The implementation (tools/validate_obs_bundles.py:195-205 and 211-217) attaches `bundle` (path string) but never records `bundle_fetched_at_utc`. A downstream consumer looking at the verdict JSON cannot tell which fetch of the bundle produced this verdict without opening the bundle again.

Spec section 4 step 1 also says: "Firehole branch requires `schema == 'yellowstone.firehole_obs.v1'` (same gate as `calibrate.py:690-691`); snow branch requires `yellowstone.snotel_obs.v1`." The code at tools/validate_obs_bundles.py:49-54 and 95-100 does enforce this per-consumer, but the `gate_bundle(..., consumer="unknown")` branch (tools/validate_obs_bundles.py:170-173) emits a `schema` check with `name="schema"` and no `rule`-labeled unknown-schema; the resulting verdict passes the schema name through unchanged but calls the check `schema` rather than `unknown-schema`. Spec section 6 lists `unknown-schema` as the stable error label; a downstream scraper matching on that label will miss it.

### Fix
In `gate_bundle` and in the `all` branch of `main`, set:

```python
verdict["bundle_fetched_at_utc"] = bundle.get("fetched_at_utc")
```

right after the `bundle` key is attached (tools/validate_obs_bundles.py:211 and tools/validate_obs_bundles.py:201 inside the dict literal). For the `all` consumer, also propagate it onto each per-consumer verdict in `verdicts`.

Replace the unknown-schema branch (tools/validate_obs_bundles.py:170-173) with:

```python
else:
    _check("unknown-schema", False,
           f"schema {schema!r} is neither {SCHEMA_FIREHOLE!r} nor "
           f"{SCHEMA_SNOTEL!r}", checks)
    passed = False
```

so the stable rule name matches the spec's error label.

### Test
Add to tests/test_validate_obs_bundles.py:
- `test_verdict_records_bundle_fetched_at_utc`: synthetic firehole bundle with `fetched_at_utc="2026-10-10T00:00:00+00:00"` -> `verdict["bundle_fetched_at_utc"]` equals that string on pass and on fail.
- `test_unknown_schema_label`: bundle with `schema="yellowstone.something.v1"` under `consumer="auto"` -> verdict has a check with `name="unknown-schema"`.

Severity: low. The gate is sound; the audit trail on the verdict is thin.

---

### 4. audit_provenance.py SIDECAR_KEYS is 4 names, the spec cites 6, and the stale-pointer rule contradicts the spec's own prose

Spec section 4 step 5 says: "if file carries `contract_version`, require all of `world_id, code_rev, parameter_provenance, sources` (the six keys `check_provenance` enforces, `common/validate.py:45-51`)". The implementation (tools/audit_provenance.py:33-34) declares `SIDECAR_KEYS = ("contract_version", "world_id", "code_rev", "parameter_provenance", "sources")` and then checks the four non-detector keys. Count mismatch: spec says six, implementation checks four. Either the spec arithmetic is wrong or `check_provenance` requires `generated_utc` and one more key the audit misses. Without reading `common/validate.py:45-51` under this audit's read-only scope, the mismatch stands as an unverified gap.

Spec section 4 step 6 contains two contradictory sentences in sequence: "Cross-check `fetched_at_utc` pointers where applicable (informational, never failing): ... Mismatch -> `stale-bundle-pointer` failure [AUTHORED]." The implementation treats mismatch as a failure (tools/audit_provenance.py:112-115), which matches the second sentence and contradicts the first. Operationally defensible; spec text is inconsistent.

Spec section 4 step 4 says `--strict` should "also apply steps 2-4 to every nested status". The implementation (tools/audit_provenance.py:81-87) applies only step 4 (vocabulary match) to nested statuses, not step 2 (missing-schema) or step 3 (missing-status). Nested dicts without a `schema` are the common case (they are not independent artifacts), so a literal reading of the spec would false-positive. Impl is defensible; spec needs tightening.

### Fix
Resolve by reading `yellowstone_python/common/validate.py:45-51` and either:
(a) add the two missing names to `SIDECAR_KEYS` and extend tests, or
(b) correct the spec from "six keys" to "four keys" (the five-tuple minus the detector `contract_version`).

Record the stale-pointer semantics explicitly in the spec: pick "failure" (what the code does, what the live derived/ already satisfies) and strike the "informational, never failing" phrase. No code change required.

Record `--strict` semantics in the spec: nested statuses are checked for vocabulary match only; nested dicts are not treated as independent artifacts for schema/presence rules. No code change required.

### Test
Add `test_sidecar_rule_matches_check_provenance`: construct a document with `contract_version` set and every key `check_provenance` enforces present; `audit_file` returns `[]`. Omit each key in turn; each omission produces exactly one `incomplete-sidecar` failure. Fixture pins the key list to whatever `check_provenance` currently requires, so a future spec rewrite does not drift.

Severity: low. The audit vocabulary and the live-dir behavior are correct; the sidecar rule is under-specified.

---

### 5. build_store.py does not catch non-FileExists errors and does not cross-check source shas against the build

The command (tools/build_store.py:63-70) catches only `FileExistsError`. If the build dir's `river_replay.json` is malformed JSON, if any `--reach-fit` is unparseable, or if the installed SQLite lacks the R-tree module (analysis_store.py:52-62 raises `RuntimeError`), the user sees a traceback rather than a clean parser.error or exit-1 message. The AGENTS.md section 4 contract says "Missing inputs fail loudly" but is silent on parse errors; the user-facing failure mode today is a stack trace.

Second gap: AGENTS.md section 4 says "Record `source_shas` from the build output; the store carries them in `meta`." The tool hashes whatever paths are passed on the CLI (tools/build_store.py:68-74 via `_sha256` inside `build_file`). It does not verify that the hashed artifacts are the ones listed in `derived/<build-id>/BUILD.json`. A user who passes `--reach-fit derived/reach_heat_fit_v150k.json` to a `--build derived/<id>` whose `BUILD.json` names `reach_heat_fit_v300k.json` will build a store with mismatched fits and no error. The provenance in `meta.notes` will not catch it.

### Fix
Wrap the `build_file` call to translate parse/runtime errors to clean exits:

```python
try:
    summary = build_file(...)
except FileExistsError as exc:
    ap.error(str(exc))
except (json.JSONDecodeError, OSError, RuntimeError) as exc:
    print(f"build-failed: {exc}", file=sys.stderr)
    return 1
```

Add a cross-check against `BUILD.json`. In `main`, after resolving `build_dir`, read `build_dir/"BUILD.json"` (if present) and extract the `source_shas` block for `reach_fit` and `snow_fit`. Compare each `--reach-fit` / `--snow-fit` path's sha256 against the sha256 recorded for the file with the same basename in `BUILD.json`. Mismatch -> `ap.error(f"source-sha-mismatch: {path} does not match BUILD.json entry")`. If `BUILD.json` has no entry for that basename, pass with a one-line warning on stdout naming the file as "not referenced by BUILD.json" (an advisory to the human: either the fit is intentionally external, or the build was rebuilt and the fit is stale).

Also fix the misleading argparse snippets at tools/build_store.py:54-56:

```python
*[(f"--reach-fit", f) for f in args.reach_fits],
*[(f"--snow-fit", f) for f in args.snow_fits]):
```

The `f""` prefix has no interpolation; drop it (ASCII literal). Minor.

### Test
Add tests/test_build_store.py:
- `test_malformed_fit_clean_exit`: fit file with truncated JSON -> subprocess exit 1 with `build-failed:` and no `Traceback` in stdout/stderr.
- `test_sha_mismatch_against_build_json`: fixture build dir with `BUILD.json` listing sha X for `reach_heat_fit.json`; pass a different `reach_heat_fit.json` -> `source-sha-mismatch` exit 2.
- `test_unreferenced_fit_warns_but_passes`: fixture build dir with `BUILD.json` not listing `reach_polished_fit_v300k.json`; pass that path -> exit 0 with `not referenced by BUILD.json` in stdout.

Severity: medium. The store itself is sound; the CLI's safety is weaker than AGENTS.md implies.

---

### 6. execute_notebook.py docstring advertises `--allow-errors` behavior that the tool does not provide

The docstring (tools/execute_notebook.py:11-13) says:

```
Human equivalent (requires jupyter):
    jupyter nbconvert --to notebook --execute notebooks/census_explorer.ipynb \
        --output census_explorer.executed.ipynb --allow-errors
```

The `execute()` function raises `RuntimeError` on the first failing cell (tools/execute_notebook.py:40-44). The nbconvert `--allow-errors` equivalent would continue past failures and store the error output on the cell. The two behaviors differ, and the docstring presents them as equivalents. A user porting a notebook that depends on `--allow-errors` semantics (e.g. a cell that intentionally raises to document a failure) will get a different outcome.

Also tools/execute_notebook.py:4 says "nbformat/nbconvert are NOT installed here" with `NOT` in ALL CAPS, which AGENTS.md section 2 forbids.

### Fix
Rewrite the docstring to describe fail-fast semantics without the nbconvert comparison:

```python
"""Stdlib notebook smoke-executor: runs a .ipynb's code cells in order,
raising on the first failing cell.

The notebook JSON is read with stdlib json and each code cell is exec'd
in a shared namespace. Markdown and raw cells are skipped. Environment
overrides (ANALYSIS_STORE, FIG_DIR, ...) pass through os.environ.

Usage:
    python3 tools/execute_notebook.py notebooks/census_explorer.ipynb
"""
```

If `--allow-errors` behavior is wanted, add an opt-in flag:

```python
ap.add_argument("--allow-errors", action="store_true",
                help="continue past failing cells; print the exception "
                     "and the cell index for each failure.")
```

and route it into `execute(path, *, allow_errors=False)`.

### Test
Add tests/test_execute_notebook.py (new file):
- `test_fail_fast_default`: notebook with a cell `raise ValueError("x")` -> `execute(path)` raises `RuntimeError` naming cell index.
- `test_allow_errors_continues`: same notebook under `execute(path, allow_errors=True)` -> returns namespace, prints `cell #<i> failed:` lines; subsequent cells run.
- `test_docstring_no_allcaps`: `rg -n "\\bNOT\\b|\\bALL\\b|\\bEVERY\\b" tools/execute_notebook.py` returns zero hits (regression against AGENTS section 2).

Severity: low. Documentation defect plus a convention violation.

---

### 7. Backfill `status` on derived/sinter_grass_cull.json and derived/sinter_tree_cull.json

Not a tool bug; the audit is right. Both files (sha256 681290dee0bc and 951f97e54440) carry `schema` plus `method`, `source_image_sha256`, `n_removed`, and `removed` but no `status`. Spec section 3 flags both as "will fail until backfilled". Every peer artifact in `derived/` carries a status from the 8-string vocabulary.

### Fix
Backfill with `illustrative_not_calibrated` (both files are hand-authored geometry culls derived from a single ortho, not calibrated against field measurement; the aquatic artifacts use the same label for similar provenance). Add the key at the top of each file next to `schema`. Example for `sinter_grass_cull.json`:

```json
{
  "schema": "yellowstone.sinter_grass_cull.v1",
  "status": "illustrative_not_calibrated",
  "date": "2026-10-09",
  ...
}
```

If the authored intent is "numerical procedure, not field validation" (closer to a dispersion sweep), use `numerical_experiment_not_field_validation` instead. The decision rests on how the removed-list is consumed: if a scenario or published artifact leans on the geometry removal as a measurement, use `measured_remote_not_calibrated`; if the cull is a procedural filter on authored placements, `illustrative_not_calibrated` is the honest label. The authored source image (`source_image_sha256` present) is the NAIP ortho, which is remotely sensed, but the brightness-gate heuristic is authored; `illustrative_not_calibrated` fits that mix.

### Test
Re-run `python3 tools/audit_provenance.py --dir derived` after the backfill: exit 0, 0 failures across all 34 files. Add a `test_sinter_cull_has_status` fixture that loads both artifacts from `derived/` and asserts `status in STATUS_VOCABULARY`.

Severity: low. One-line edit per file; the audit is already catching it.

---

# Wiring and rendering

- `audit_provenance.py` is referenced from AGENTS.md section 7 as a verify-before-reporting-done step. It is not called from `yellowstone_python/build.py` (rg returned zero hits). It writes `derived/<name>.json` when `--out` is passed; nothing in the repo consumes that output file (no reader of `yellowstone.provenance_audit.v1`). The audit is a human-run gate, not a build-time one. Godot does not render it.
- `build_store.py` wraps `yellowstone_python.analysis_store.build_file`. The store is consumed by `yellowstone_python.analysis_store.query` (allow-listed read-only API) and by `yellowstone_python.llm_backend` (which exposes HTTP endpoints `/api/snapshot`, `/api/density`, `/api/compare` per AGENTS section 4). Build pipeline (`build.py`) does not call `build_store`; the operator runs it after a build. Godot does not read the SQLite store.
- `compare_bundles.py` has no consumer in the repo. It is a human-run drift detector. The verdict JSON `yellowstone.bundle_drift.v1` is not read by any module. Godot does not render it.
- `validate_obs_bundles.py` has no consumer in the repo. `check_continuity` from `replay/calibrate.py` is called at line 59 of this tool. The verdict `yellowstone.obs_bundle_verdict.v1` is not read by any module. The gate is a pre-fit human-run guard, not a fit-time one; `calibrate.py:690-691` still enforces its own schema gate at fit time (the gate here does not replace that).
- `plot_fit.py` writes PNGs that are not referenced by Godot or by any other Python module. The PNGs are human-facing diagnostics. The `_footer` string carries `status` and `fetched_at_utc` so a PNG that leaves the directory still carries its provenance tag.
- `execute_notebook.py` is called by `tests/test_reach_notebook.py` (test_notebook_executes_on_synthetic_bundle). The CLI entry point has no production caller.

Gaps: no tool here is wired into `build.py` as a gate. `audit_provenance.py` and `validate_obs_bundles.py` could reasonably be invoked by `build.py` before `write_sidecar` emits the final `BUILD.json`; today they are human-run, so a build with a stale `fetched_at_utc` pointer or an unknown status string ships silently and the audit catches it only when a human runs the AGENTS section 7 steps. The spec for `audit_provenance` section 1 explicitly says "no warning level" and treats the audit as reporting-only; wiring it into the build gate is a follow-up decision for a separate fixes doc, not within this audit's scope.

# Comment-style violations

| file:line | text | rule |
|---|---|---|
| tools/plot_fit.py:1 | `"""Diagnostic PNGs from fit artifacts (Pillow only, no matplotlib).` | em dash (AGENTS section 2 bullet 1) |
| tools/plot_fit.py:3-5 | `Every figure carries the source artifact's status + timestamp as footer text / so figures never circulate unlabeled.` | `Every` comprehensiveness claim and hypothetical-failure narrative (`never circulate unlabeled`) (AGENTS section 2 bullets 4, 6) |
| tools/plot_fit.py:4-5 | `Panels render stored summaries only; nothing is interpolated or invented` | hypothetical-failure framing (AGENTS section 2 bullet 4) |
| tools/audit_provenance.py:1-2 | `"""Mechanical standing-rules check over derived/ provenance labels.` and the following line | fine on its own, but line 4 follows with a `X, not Y` structure |
| tools/audit_provenance.py:4 | `tooling-spec-audit-provenance.md); reports, never rewrites, artifacts.` | `X, never Y` contrast and `never` hypothetical-failure (AGENTS section 2 bullets 3, 4) |
| tools/audit_provenance.py:16 | `# Exact vocabulary measured across derived/*.json (28 occurrences, 2026-10-10).` | temporal/date reference (AGENTS section 2 bullet 5) |
| tools/audit_provenance.py:30 | `# Files with no schema/status contract (legacy, allowlisted not failed).` | temporal reference `legacy` and `X, not Y` structure (AGENTS section 2 bullets 3, 5) |
| tools/build_store.py:2-5 | `Derived artifacts are history: the default output is a NEW file per build / (derived/analysis_<buildid>.sqlite), never an overwrite of an existing / store. Pass --out explicitly to choose another path.` | ALL-CAPS `NEW` and hypothetical-failure narrative with `never` (AGENTS section 2 bullets 4, 6) |
| tools/build_store.py:38-39 | `"repeatable; empty -> fits tables empty with a meta note, never an error"` | `X, never Y` contrast and `never` (AGENTS section 2 bullets 3, 4). Arrow `->` is ASCII, acceptable. |
| tools/compare_bundles.py:3-5 | `Compares two bundles of the same schema on exact-epoch/date alignment (no / interpolation: interpolation would hide revision). Empty series are / non-informative, never zero.` | hypothetical-failure (`interpolation would hide revision`) plus `X, never Y` (`non-informative, never zero`) (AGENTS section 2 bullets 3, 4) |
| tools/validate_obs_bundles.py:3-4 | `Calls (never copies) check_continuity from replay.calibrate and mirrors the / snow coverage rules in snow_validate (SPLIT_DATE, MAX_FILL_DAYS, spin-up).` | `X (never Y)` contrast + `never` (AGENTS section 2 bullets 3, 4) |
| tools/execute_notebook.py:4 | `No jupyter dependency (nbformat/nbconvert are NOT installed here): the` | ALL-CAPS emphasis `NOT` (AGENTS section 2 bullet 6) |
| tools/execute_notebook.py:5-6 | `notebook JSON is read with stdlib json and each code cell is exec'd in a / shared namespace. Markdown cells are skipped.` | fine (facts, not contrasts) |

No first-person pronouns were found in any of the six files. No reader-address pronouns were found. No file carries a dated filename (AGENTS section 3). The `rg '_2026-10|_2026_10|WY2025_2026'` scan over all six files returns zero hits.

# Priority order

1. Problem 7 - backfill `status` on the two sinter cull artifacts (cheap, one-line edit per file; clears the live audit red immediately).
2. Problem 1 - plot_fit.py figure set alignment with the spec (medium; three new figure functions plus title changes plus five tests).
3. Problem 2 - compare_bundles.py SNOTEL CLI flags, `provenance_note`, and `window_shift_s` (cheap for the flags and the note, medium for `window_shift_s` because `_series_delta` consumers change).
4. Problem 5 - build_store.py error handling and sha cross-check against BUILD.json (medium; the BUILD.json cross-check is where most of the work sits).
5. Problem 3 - validate_obs_bundles.py `bundle_fetched_at_utc` plus `unknown-schema` rule label (cheap; two-line surgical fix each).
6. Problem 6 - execute_notebook.py docstring rewrite and optional `--allow-errors` flag (cheap for the docstring, medium if the flag ships).
7. Problem 4 - audit_provenance.py SIDECAR_KEYS reconciliation plus two spec clarifications (cheap; one read of `common/validate.py` and either a code or a spec edit).
8. Comment-style sweep across all six files (cheap; rewrites listed verbatim in the table above).

NOT VERIFIED: the exact key list that `yellowstone_python/common/validate.py:45-51` enforces (problem 4) was not read under this audit's read-only scope; the spec says six, the code checks four.
