# Spec: tools/validate_obs_bundles.py — observation-bundle gate

Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims are marked [AUTHORED].
No code written; no deletions. Target: `tools/validate_obs_bundles.py` in `../../yellowstone_python/`.

## 1. Purpose + non-goals

Purpose: single bundle-level schema/continuity/coverage gate over `derived/*obs*.json` that fails BEFORE any fit consumes a broken bundle. Today "coverage sufficient to fit" is distributed across `check_continuity` thresholds, `prepare_forcing`/`train_holdout_split`/`spinup` rules, and schema string gates (`yellowstone_python/replay/calibrate.py:311-313,390,690-691`; `yellowstone_python/snow_validate.py:42-79,158-159`) — a broken bundle surfaces as a mid-fit traceback, not a gate verdict.

Non-goals: no refetching (fetchers own that); no fitting; no new warning level (repo has none — `CHECKS.json` carries only `passed/failures`, `yellowstone_python/build.py:571-633`); no changes to `check_continuity` semantics (lift by CALL, not by copy).

## 2. CLI (`--help` text drafted)

```
usage: validate_obs_bundles.py --bundle PATH [--out PATH] [--consumer {firehole,snow,all}]

Gate an observation bundle before fitting. Exit 0: bundle fit for the named
consumer(s). Exit 1: bundle fails (verdict JSON still written to --out when
given). Exit 2: bad invocation (parser.error).

options:
  --bundle PATH        observation bundle to gate (required)
  --out PATH           write machine-readable verdict JSON (atomic .tmp+replace)
  --consumer {firehole,snow,all}
                       which fit contract to check (default: infer from schema)
```

Follows house `tools/` pattern: `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` (`tools/cross_sections.py:23`), `argparse.ArgumentParser(description=__doc__)`, `if __name__ == "__main__": raise SystemExit(main())` (`tools/cross_sections.py:174-175`).

## 3. Inputs / outputs with exact schemas

Input: one bundle file. Supported schemas (exact strings from code):
- `yellowstone.firehole_obs.v1` (`tools/fetch_firehole_obs.py:149`). Top-level keys: `fetched_at_utc, met, provenance, schema, sites, status, window_days`. `sites` keys `06036805, 06036905`, each `{name, role, latitude, longitude, url, series: {discharge_m3_s: [[epoch_s, m3/s]], temperature_c: [[epoch_s, C]]}}` (n=668 each in live bundle). `met: {elevation_m, hourly: [[epoch, air_C, rh_0-1, wind_mps, sw_Wm2, cloud_0-1]], url}` (n=192 live).
- `yellowstone.snotel_obs.v1` (`tools/fetch_snotel_obs.py:133`). Top-level keys: `fetched_at_utc, provenance, schema, site_brief, sites, status, window`. `sites` keys `609:MT:SNTL, 924:MT:SNTL`, each `{coverage, days: {YYYY-MM-DD: {PRCP, SNWD, TAVG, TMAX, TMIN, WTEQ (float-or-null)}}, elevation_m, huc, latitude, longitude, name, role, units, url}`.

Output verdict JSON (new schema `yellowstone.obs_bundle_verdict.v1` [AUTHORED — new string following house `yellowstone.<name>.v1` convention]):
`{schema, status, bundle, bundle_schema, consumer, passed: bool, checks: [{name, passed, detail}], nominal_steps: {series_label: {nominal_s, worst_s, max_gap_s}}}`.
`status` on pass: `measured_remote_not_calibrated` (propagated from bundle, not upgraded — validation does not calibrate).

## 4. Algorithm / rules in numbered steps

1. Load JSON; unknown/missing `schema` → fail verdict `unknown-schema`. Firehole branch requires `schema == "yellowstone.firehole_obs.v1"` (same gate as `calibrate.py:690-691`); snow branch requires `yellowstone.snotel_obs.v1`.
2. Firehole continuity (CALL `check_continuity` from `yellowstone_python.replay.calibrate`, signature `calibrate.py:111-112`): upstream `temperature_c` and `discharge_m3_s` at `max_gap_s=3600.0`, met air column at `14400.0` (thresholds from `calibrate.py:310-313`, comment "Gap tolerance 4x nominal step… IV nominal 900 s, met nominal 3600 s"). Record returned nominal + worst per series. `ValueError` → check failed with the exception text as detail.
3. Firehole presence: both sites present; each series `len >= 2` (the `check_continuity` minimum, `calibrate.py:120`); met `hourly` rows all length 6.
4. Firehole window: grid non-empty — `t0 = max(up_t0, met0)`, `t1 = min(up_t_end, met_end)`, require `t1 > t0` (`calibrate.py:314-317` logic, read-only reuse).
5. Snow coverage: require `days` non-empty (producer refuses zero days, `tools/fetch_snotel_obs.py:105-106`); require codes `WTEQ, PRCP, SNWD, TAVG` present per-day keys (the four codes `validate_site` reads, `snow_validate.py:150-163`); TAVG gap rule mirrored read-only: forward-fill ≤ `MAX_FILL_DAYS=3` else fail (`snow_validate.py:30,42-72`); day-0 SWE must be ≤ `in_to_mm(0.04)` or fail with spin-up message (`snow_validate.py:158-159`); window must span `SPLIT_DATE="2026-03-01"` (`snow_validate.py:29,75-79`) else fail `no-holdout-span`.
6. Write verdict atomically (`.tmp` + `replace`, per `tools/fetch_snotel_obs.py:152-155`). Exit 0 iff all checks pass, else 1.

## 5. Provenance plan

Verdict carries `status: measured_remote_not_calibrated` on pass (transferred from bundle; a gate adds no calibration). On fail, `status: measured_remote_not_calibrated` + `passed: false` — never `illustrative_*` (the bundle is measured data, not authored). Verdict records `bundle` path + `bundle_fetched_at_utc` mirroring the convention in `snow_validate.py:220` and `calibrate.py:462,745`.

## 6. Error handling

| Failure mode | Exit | Message |
|---|---|---|
| Missing `--bundle` / bad `--consumer` | 2 | argparse `parser.error` (house pattern, e.g. `tools/fetch_snotel_obs.py:119`) |
| File not JSON / unreadable | 1 | `bundle-unreadable: <path>: <exc>` (verdict written if `--out` given and writable) |
| Unknown schema | 1 | `unknown-schema: <found>` |
| Continuity gap | 1 | `gap: <check_continuity ValueError text>` |
| Snow spin-up / fill / span violation | 1 | `snow-coverage: <rule>: <detail>` |
| `--out` unwritable | 1 | `verdict-unwritable: <path>` (verdict to stdout instead — [AUTHORED] fallback) |

No explicit `sys.exit(2)` string in repo today (verified: zero hits) — exit 2 comes from argparse only; spec must not claim a tested numeric-code contract.

## 7. Tests (synthetic/offline only, no network)

1. `test_firehole_known_good_passes` — hand-built minimal firehole bundle (2 sites × 3 points at 900 s + 3 met rows at 3600 s) → exit 0, `passed true`.
2. `test_firehole_gap_fails` — one 7200 s gap in upstream temp → exit 1, detail names the gap (mirrors `test_calibrate.py:62-70`).
3. `test_firehole_wrong_schema_fails` — `schema: yellowstone.snotel_obs.v1` content under firehole consumer → `unknown-schema`.
4. `test_snow_spinup_refusal` — day-0 WTEQ 5 mm → `snow-coverage` fail quoting spin-up rule.
5. `test_snow_tavg_long_gap_fails` — 5 consecutive null TAVG → fail (MAX_FILL 3).
6. `test_snow_no_holdout_span_fails` — window entirely before 2026-03-01 → `no-holdout-span`.
7. `test_verdict_atomic_write` — `--out` to tmp dir; assert file exists, parses, carries `yellowstone.obs_bundle_verdict.v1`.
8. `test_live_bundles_pass` — runs gate over the two real `derived/*obs*.json` as FIXTURES (read-only, no network): both must pass (they feed green fits today). [AUTHORED — pins current live state.]

## 8. Acceptance criteria

- [ ] Gate calls (not copies) `check_continuity`; thresholds `3600/3600/14400` cited to `calibrate.py:310-313`.
- [ ] Snow rules cite `snow_validate.py` constants (`SPLIT_DATE`, `MAX_FILL_DAYS`, spin-up) by line.
- [ ] Verdict schema string `yellowstone.obs_bundle_verdict.v1` used; atomic write; exit 0/1/2 per §6.
- [ ] All 8 tests pass offline; suite stays green.
- [ ] No changes to fetchers, `calibrate.py`, or `snow_validate.py`.

## 9. Effort + dependencies

Effort: S (thin orchestration over existing functions; ~150 lines + tests). Dependencies: none new (stdlib + numpy/scipy already required). Note: `resample_bin_mean` coverage tuples (`calibrate.py:54-63`) are deliberately NOT used — no production caller branches on them.
