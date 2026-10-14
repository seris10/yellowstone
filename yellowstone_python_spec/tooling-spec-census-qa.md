# Spec: Census QA (`--qa` + `detect_v2` decision)

Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].
No code written; no deletions. Target: `yellowstone_python/canopy_census.py` + `yellowstone_python/census_validate.py`.

## 1. Purpose + non-goals

Purpose: resolve the two known census gaps — (a) the docstring advertises `--qa derived/census.json --overlay out.png` (`yellowstone_python/canopy_census.py:16-18`) but the parser has NO `--qa` flag (`canopy_census.py:227-233`: only `--detail/--out/--overlay/--stats`), so the documented command errors; (b) `detect_v2` (`canopy_census.py:310-362`) + `calibrate_lone_trees` (`canopy_census.py:273-307`) are implemented yet unwired (never called by `main`, `canopy_census.py:227-266`) and untested (`tests/test_census.py:1-63` imports only v1 functions; zero `detect_v2`/`calibrate_lone` hits in any test file).

Non-goals: no change to v1 detection thresholds; no re-running the live census; no completing human annotation (that is a people-task, `validation/reference_points.json` is `[]` today); no torch/GUI work (`census_validate.py:1` notes none needed).

## 2. CLI (`--help` text drafted)

Two decisions packaged as one spec; implementing session picks option A or B for `--qa` and separately ships the v2 gate:

```
# Option A (recommended): --qa becomes a thin alias into the existing validator
python -m yellowstone_python.canopy_census --qa derived/census.json [--overlay out.png]
  -> runs census_validate evaluate+difference-estimator read path over the
     frozen census; exit 0 on report, 1 with cause otherwise.

# Option B: --qa becomes a self-check (no human data needed)
python -m yellowstone_python.canopy_census --qa derived/census.json
  -> checks: schema==yellowstone.canopy_census.v1, n==len(trees),
     confidence values in {high,medium,low}, crown_r_m<=6.0 cap,
     splitting_basis present iff v2; prints counts; exit 0/1.
```

Parser keeps `--detail/--out/--overlay/--stats`; adds `--qa PATH` (+ `--tolerances` passthrough only under Option A). Bad input → `parser.error` (exit 2, house pattern).

## 3. Inputs / outputs with exact schemas

Inputs:
- `derived/census.json`: `schema=yellowstone.canopy_census.v1`, `n=33764`, `trees[]` each `{confidence, crown_r_m, evidence_class, peak_exg, stable_id, x, z}`; top `status="detection unreviewed; pool-rim artifacts excluded; not a placement authority"`, `dropped_rim=23`, `source={image, acquired:2022-07-19, agency, px_m:0.625}`, `density` 5 zones. Measured: confidence `high=32620 (96.61%), medium=406, low=738`; `crown_r_m` min 0.61 / median 2.87 / max 6.0 (cap matches `canopy_census.py:100`); `splitting_basis` absent on all 33764 (confirms v1 artifact).
- `validation/` dir state today: `census_frozen.json` (n_automated=33764, `status=frozen_before_review`), `sampling_plan.json` (`population_cells=64, sample_cells=12, cell_px=256, seed=42`), `sample.json` (`reference_count=""` ×12), `reference_points.json=[]`, NO `validation_report.json` (evaluate not run).

Outputs:
- Option A: `validation/validation_report.json` (schema already defined by `census_validate.py:342-426`: per-tolerance `tp/fp/fn/precision/recall/f1/matched_rmse_px` at default tolerances `[4.0,6.0,10.0]` (`census_validate.py:440`), main tolerance 6 px, `corrected_total` + `approx_95_interval`).
- Option B: stdout counts + exit code; optional `--overlay` PNG (2048², cf. live `derived/census_overlay.png` 2048×2048, 8,475,544 bytes; source ortho `../../yellowstone_midway/references/midway_orthophoto_detail.jpg` 2048×2048).
- v2 promotion artifact: `derived/census_v2.json` (same schema string + `splitting_basis` per tree, `calibration: {n_lone, median_area_px, p95_area_px, median_crown_r_m}` header) [AUTHORED].

## 4. Algorithm / rules in numbered steps

`--qa` fix:
1. Pick Option A if any `validation/validation_report.json` exists at implement time, else ship Option B self-check now and leave Option A wired to the same flag (flag stable, backend chosen by data availability) [AUTHORED recommendation].
2. Option B checks in order: parse JSON → schema string → `n == len(trees)` → per-tree field/values → cap `crown_r_m <= 6.0` → `splitting_basis ∈ {peak, area_topup}` iff present → density zones sum ≤ n. First failure → exit 1 naming rule + tree id.
3. Fix the docstring (`canopy_census.py:16-18`) to describe the shipped behavior verbatim.

`detect_v2` decision:
4. Measure the real calibration input: run `calibrate_lone_trees(load_detail())` offline; record `n_lone`. Proxy measurement on shipped `census.json` (nearest-neighbour ≥10 m on world x,z): **133 lone trees ≥ required 10** (`canopy_census.py:301-302` refuses if `<10`) — minimum satisfied on the proxy; the pixel-component count must still be recorded from the real run.
5. v1-vs-v2 delta methodology: run `detect` and `detect_v2(calibration)` on the same 2048² ortho; report count Δ, per-zone Δ (reuse the 5 shipped density zones + `detail_full` box from `--stats`, `canopy_census.py:249-256`), and a spot-overlay protocol: render both overlays at 2048², blind-sample 12 cells at `cell_px=256/seed=42` (mirroring `sampling_plan.json`) for human adjudication.
6. Quantitative promotion gates for v2 (no vibes-based merges) [AUTHORED thresholds, to be ratified by the numbers in step 5]: merge v2 iff ALL hold — (a) `|count Δ| ≤ 5%` of 33,764 unless adjudicated cells show v1 misses; (b) per-zone Δ ≤ 10% in every zone; (c) `calibrate_lone_trees` `n_lone ≥ 10` on the real ortho; (d) full test suite green including 3+ new v2 tests; (e) `validation_report.json` F1 at 6 px does not regress vs v1 baseline. If any gate lacks its input (e.g. no validation report yet), the gate is BLOCKED, not waived.

## 5. Provenance plan

`derived/census_v2.json` (if promoted) carries `status` starting from the v1 string and appending `; v2 area-topup, <calibration n_lone>, <evaluate F1@6px or 'unvalidated'>` — never silently keeps the v1-only status. QA outputs (`validation_report.json`) keep `status=frozen_before_review` lineage from `manifest.json` (`census_validate.py:59-65`). Spec text itself marks transferred numbers (this section's counts) vs authored thresholds (§4.6, §6).

## 6. Error handling

| Failure mode | Exit | Message |
|---|---|---|
| `--qa` on missing/unparseable file | 1 | `qa-unreadable: <path>` |
| Self-check rule violation | 1 | `qa-rule: <rule> at <stable_id>` |
| Option A with `reference_points.json==[]` | 1 | `qa-not-annotated: run annotate first` (mirrors evaluate's existing refusal) |
| `calibrate_lone_trees` n_lone < 10 | 1 | the existing `ValueError` text (`canopy_census.py:302`), surfaced, not swallowed |
| Bad flags | 2 | `parser.error` |

## 7. Tests (synthetic/offline only)

1. `test_qa_selfcheck_passes_on_v1_fixture` — 20-tree synthetic census → exit 0.
2. `test_qa_catches_count_mismatch` — `n` ≠ len(trees) → exit 1 naming rule.
3. `test_qa_catches_bad_confidence` — confidence `ultra` → exit 1 with stable_id.
4. `test_qa_catches_cap_violation` — `crown_r_m` 9.0 → exit 1.
5. `test_calibrate_refuses_few_lone` — <10 isolated components → ValueError (pins `canopy_census.py:301-302`).
6. `test_detect_v2_topup_shape` — synthetic two-blob image: v2 output trees carry `splitting_basis` and calibration header keys.
7. `test_docstring_matches_parser` — `--help` text contains every flag the docstring advertises (regression for this exact bug).
8. `test_live_census_qa_status` — read-only run of Option B over live `census.json`; record result (passes or fails with cause — either is informative given the file-vs-code divergence in §3).

## 8. Acceptance criteria

- [ ] `--qa` exists in parser; docstring lines 16-18 rewritten to match shipped behavior.
- [ ] Real-ortho `n_lone` measured and recorded (not the 133 proxy).
- [ ] v1-vs-v2 delta (count Δ, per-zone Δ, 12-cell spot protocol) reported with numbers.
- [ ] All five promotion gates evaluated numerically; any unevaluable gate marked BLOCKED.
- [ ] Suite green; `detect_v2`/`calibrate_lone_trees` imported by tests (ends zero-coverage state).

## 9. Effort + dependencies

Effort: M (parser + self-check small; v2 delta run + adjudication protocol medium). Dependencies: none new (scipy already required; `KDTree-or-brute` fallback at `canopy_census.py:288-297` covers no-scipy). Note the file-vs-code divergence: live `census.json` lacks `extent_m` and `detail_full` that current `main` writes (`canopy_census.py:238-256`) — implementing session must not "fix" the artifact; record the divergence.
