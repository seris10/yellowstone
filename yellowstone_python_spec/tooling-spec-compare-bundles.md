# Spec: tools/compare_bundles.py — old-vs-refetch drift detection

Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].
No code written; no deletions. Target: `tools/compare_bundles.py` in `/Users/kreed/Downloads/yellowstone_python/`.

## 1. Purpose + non-goals

Purpose: detect when a refetch has drifted from the frozen bundle before fits silently consume revised numbers. Both sources are provisional and subject to revision (USGS IV: `tools/fetch_firehole_obs.py:154-155`; AWDB: `tools/fetch_snotel_obs.py:141-143`) with NO version field in any bundle — re-fetching later yields a different window/values (`fetch_firehole_obs.py:12-13` comment) and overwrites the named file in place (atomic tmp+replace, no versioning). Consumers pin only `fetched_at_utc` (`calibrate.py:462,745`; `snow_validate.py:220`). There is no drift metric anywhere today.

Non-goals: no automatic refetching; no deciding which bundle is "right" (USGS/AWDB revision wins by definition — tool reports, human or a later policy decides); no touching `derived/usgs_06036805.json` semantics (that file is currently all-empty lists — 382 bytes — and must be treated as non-informative, NOT zero).

## 2. CLI (`--help` text drafted)

```
usage: compare_bundles.py --old PATH --new PATH [--out PATH]
       [--q-rel-tol F] [--t-abs-tol F]

Compare two bundles of the same schema. Exit 0: drift within tolerance.
Exit 1: drift exceeds tolerance or incomparable (report still written to
--out when given). Exit 2: bad invocation.

options:
  --old PATH, --new PATH   bundles to compare (required)
  --out PATH               write drift report JSON (atomic .tmp+replace)
  --q-rel-tol F            discharge relative tolerance (default: 0.05)
  --t-abs-tol F            temperature absolute tolerance °C (default: 0.5)
```

## 3. Inputs / outputs with exact schemas

Inputs: any two bundles sharing one schema (`yellowstone.firehole_obs.v1` or `yellowstone.snotel_obs.v1`; schemas in tooling-spec-validate-obs-bundles §3).

Drift metrics per element [AUTHORED, justified from live-bundle variability in §4]:
- Firehole series (`discharge_m3_s`, `temperature_c` per site): `max_abs_delta` over epoch-aligned points + `coverage_delta` (n_old vs n_new) + `window_shift_s` (|t0_old − t0_new|).
- SNOTEL days: per-code `max_abs_delta` over date-aligned days + `coverage_delta` per code + null-count delta.
- Met hourly (firehole only): same as firehole series per column.

Tolerance defaults from the frozen bundles' own variability (transferred measurements):
- Upstream Q std 0.0187 on mean 1.0709 (1.7%), max step-to-step 0.0311 (2.9%); downstream Q std 0.0433 on 5.4416 (0.8%), max step 0.1699 (3.1%) → `--q-rel-tol 0.05` sits above worst observed step noise [AUTHORED].
- Temp (both sites) max step 0.4 °C, p95 0.3 °C → `--t-abs-tol 0.5` sits above worst observed step [AUTHORED].
- SNOTEL: daily steps reach 1.5 in WTEQ/PRCP, 12 in SNWD, ~30 °F TMIN at 924 (transferred) — SNOTEL defaults need wider per-code tolerances; spec REQUIRES per-code flags with defaults `wteq_abs_tol_in=2.0, snwd_abs_tol_in=12.0, temp_abs_tol_f=15.0` [AUTHORED, set at/above observed max steps so refetch noise doesn't page].

Output report schema `yellowstone.bundle_drift.v1` [AUTHORED]: `{schema, status, old: {path, fetched_at_utc}, new: {path, fetched_at_utc}, passed: bool, metrics: [{element, max_abs_delta, coverage_old, coverage_new, tol, passed}]}`. Report `status`: `measured_remote_not_calibrated` (comparison of two measured bundles; no calibration claimed).

## 4. Algorithm / rules in numbered steps

1. Load both; require equal `schema` else fail `schema-mismatch` (a firehole-vs-snotel comparison is a user error, not drift).
2. Align: firehole series on exact epoch match (no interpolation — interpolation would hide revision); SNOTEL on ISO-date match. Report `n_overlap`; zero overlap → `no-overlap` failure (expected when windows don't intersect — refetch windows slide).
3. Per element compute `max_abs_delta` + coverages; compare to tol; collect per-element pass/fail.
4. Revision-awareness rule [AUTHORED]: values changed but `fetched_at_utc` newer is EXPECTED revision — verdict `passed` iff within tol; verdict text distinguishes `within-tolerance-revision` from `identical`.
5. Empty-source rule: any series/day-list empty on either side (cf. `usgs_06036805.json` all-`[]`) → element marked `non-informative`, excluded from pass/fail, listed separately. Never compare empty to empty as "no drift."
6. Write report atomically; exit 0 iff all informative elements within tol.

## 5. Provenance plan

Report carries `measured_remote_not_calibrated` + both bundles' `fetched_at_utc` (the only revision identity available — there is no source version field; record this limitation in the report's `provenance_note` [AUTHORED]).

## 6. Error handling

| Failure mode | Exit | Message |
|---|---|---|
| Bad flags | 2 | `parser.error` |
| Schema mismatch | 1 | `schema-mismatch: <old-schema> vs <new-schema>` |
| No overlap | 1 | `no-overlap: <element>` (informational — windows slid) |
| Drift over tol | 1 | `drift: <element> max_abs <v> > tol <t>` |
| Unreadable input | 1 | `bundle-unreadable: <path>` |

## 7. Tests (synthetic/offline only)

1. `test_identical_passes` — bundle vs itself → exit 0, verdict `identical`.
2. `test_small_revision_passes` — Q shifted +2%, T +0.2 °C → exit 0 `within-tolerance-revision`.
3. `test_q_drift_fails` — Q shifted +10% → exit 1 naming element + values.
4. `test_schema_mismatch_fails` — firehole vs snotel → `schema-mismatch`, exit 1.
5. `test_empty_is_noninformative` — empty series vs populated → excluded, listed, exit 0 if rest pass.
6. `test_no_overlap_fails_informatively` — disjoint epochs → `no-overlap`.
7. `test_live_self_comparison` — live firehole bundle vs itself → exit 0 (read-only fixture use).

## 8. Acceptance criteria

- [ ] Default tolerances cite the §3 measured step statistics (no magic numbers).
- [ ] SNOTEL per-code tolerances present with live-data justification.
- [ ] Empty-means-non-informative rule implemented + tested (the `usgs_06036805.json` trap).
- [ ] Suite green; no fetcher/consumer modified.

## 9. Effort + dependencies

Effort: S (~130 lines + tests; stdlib + numpy already required). Dependencies: none new. Open: USGS/AWDB revision lag/qualifier semantics beyond "provisional" — unresolvable from bundled data; would need provider docs.
