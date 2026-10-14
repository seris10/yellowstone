# Spec: tools/fetch_met_forcing.py — shared Open-Meteo source

Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].
No code written; no deletions. Target: `tools/fetch_met_forcing.py` in `../../yellowstone_python/`.

## 1. Purpose + non-goals

Purpose: extract the ONE embedded Open-Meteo fetcher into a shared, pinned, backcompatible source. Exhaustive grep (verified 2026-10-10) finds exactly ONE live network fetcher: `tools/fetch_firehole_obs.py:29` (`OPEN_METEO`), `:101-122` (`fetch_met`), with `MET_VARS` at `:46-47`; all other `open-meteo` hits are mentions/copies (bundle provenance + URL at `derived/firehole_obs_2026-10-09.json:8,10728`, docstring `calibrate.py:15`, `replay/README.md:115`, brief pointer). Consolidation now is cheap (one fetcher) and prevents the second copy from diverging later.

Non-goals: no change to the row schema consumers read (frozen by `calibrate.py:321-325` indices); no touching the snow path (SNOTEL-driven, `snow_validate.py:42-72` — verified NOT an Open-Meteo consumer); no pinning the NWP model version beyond what the URL records (unverifiable today).

## 2. CLI (`--help` text drafted)

```
usage: fetch_met_forcing.py --lat F --lon F --days N --out PATH
       [--vars CSV] [--schema NAME]

Fetch Open-Meteo hourly forcing to a versioned JSON bundle. Exit 0 on
success. Exit 2 on bad invocation. Network/producer failures exit 1 with
cause (never partial writes).

options:
  --lat F, --lon F     coordinates (required; today: upstream gauge
                       44.459333,-110.822272, fetch_firehole_obs.py:143-145)
  --days N             past days, must be in [1,16] (today's bound,
                       fetch_firehole_obs.py:127-131)
  --out PATH           bundle path (atomic .tmp+replace)
  --vars CSV           hourly vars (default: temperature_2m,relative_humidity_2m,
                       wind_speed_10m,shortwave_radiation,cloud_cover)
  --schema NAME        schema string (default: yellowstone.met_forcing.v1 [AUTHORED])
```

## 3. Inputs / outputs with exact schemas

Request (transferred from `fetch_firehole_obs.py:103-105`): `https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&hourly=<MET_VARS csv>&past_days={days}&forecast_days=1&timezone=UTC`, stdlib `urllib` only (house rule — zero `import requests` repo-wide, verified).

Row schema (FROZEN, exact producer code `fetch_firehole_obs.py:117-119` + authoritative consumer indices `calibrate.py:321-325`):
`[epoch_s_UTC, air_C, rh_0-1, wind_mps, sw_Wm2, cloud_0-1]` = `[epoch, air, rh_pct/100.0, wind_kmh/3.6, sw, cloud_pct/100.0]`.
Live example: `[1790985600.0, 16.8, 0.31, 4.5833, 203.0, 0.0]` (`firehole_obs:10730-10738`). Downstream type `MetState{air_c, rh, wind_mps (floored 0.5), shortwave_w_m2, cloud}` (`surface_flux.py:78-107`); test doubles use the same order (`test_calibrate.py:119-121`, `test_uncertainty.py:41-43`) and must stay compatible.

Output bundle schema `yellowstone.met_forcing.v1` [AUTHORED — superset wrapper, row order unchanged]:
`{schema, status: "measured_remote_not_calibrated", fetched_at_utc, request: {lat, lon, days, vars, url}, elevation_m, hourly: [[epoch, air, rh, wind, sw, cloud]]}`.
Superset provision [AUTHORED]: `request.vars` + `request.url` recorded so future variables (e.g. pressure, snowfall) extend `hourly` width ONLY under a `v2` schema; v1 width is frozen at 6.

## 4. Algorithm / rules in numbered steps

1. Parse args; `--days` outside [1,16] → `parser.error` (today's bound).
2. GET via stdlib `urllib.request` with timeout [AUTHORED: 60 s; no timeout exists today — fetchers block unboundedly]; non-200/JSON-decode failure → exit 1 `met-fetch-failed`.
3. Require `len(col) == len(times)` for every var else `RuntimeError("Open-Meteo: incomplete hourly table")` (today's gate, `fetch_firehole_obs.py:110-111`).
4. Build rows with the EXACT conversions in `fetch_firehole_obs.py:117-119` (copy the expressions, cite the lines).
5. Write bundle atomically (`.tmp` + `replace`, `fetch_snotel_obs.py:152-155` pattern).
6. Migration (backcompat, [AUTHORED]): `fetch_firehole_obs.py` `fetch_met()` becomes a thin wrapper importing the row-builder from the new module (same function name, same return shape `{"url","elevation_m","hourly"}`); `bundle["met"]` layout unchanged so `calibrate.py:308,321-325`, `uncertainty.py`, and both replay tests keep passing unmodified. `MET_VARS`/`OPEN_METEO` constants move to the new module; old import sites keep working via re-export for one cycle (then remove — record removal in code comment).

## 5. Provenance plan

Bundle `status: measured_remote_not_calibrated` (same as today's embedded `met` provenance: "Open-Meteo NWP blend … forcing for the surface budget, not an observation", `firehole_obs:8`). Record the known gap: NWP blend/model run NOT pinned beyond URL + `fetched_at_utc` — add `request.url` verbatim (today's stored URL truncates `past_days=…`, `firehole_obs:10728`; new tool must store the full URL) and note `model-unpinned` in the bundle's `provenance_note` [AUTHORED].

## 6. Error handling

| Failure mode | Exit | Message |
|---|---|---|
| Bad flags | 2 | `parser.error` (incl. `--days` range, cf. `fetch_firehole_obs.py:131`) |
| Network/HTTP/JSON failure | 1 | `met-fetch-failed: <url-host>: <exc>` (no secrets in message — URL has none) |
| Incomplete hourly table | 1 | `Open-Meteo: incomplete hourly table` (today's string, preserved) |
| `--out` unwritable | 1 | `bundle-unwritable: <path>` (nothing written, no partial file — atomicity) |

## 7. Tests (synthetic/offline only, no network)

1. `test_row_builder_conversions` — synthetic Open-Meteo JSON (rh_pct, wind_kmh, cloud_pct) → exact expected rows (pins `/3.6`, `/100.0` conversions).
2. `test_incomplete_table_raises` — ragged columns → `incomplete hourly table`.
3. `test_days_range_rejected` — `--days 0/17` → exit 2 via parser.
4. `test_wrapper_backcompat` — refactored `fetch_firehole_obs.fetch_met` returns identical shape/keys on a stubbed HTTP response (stub `urllib`, no network).
5. `test_consumer_indices_unchanged` — replay synthetic bundle through `_fit_forcing_arrays` with new-module rows → same interpolation result as old rows (guards the frozen index contract).
6. `test_full_url_recorded` — bundle `request.url` contains untruncated `past_days=` (regression for the `…` truncation).

## 8. Acceptance criteria

- [ ] Exactly one fetcher after migration: grep `api.open-meteo` hits only the new module (+ frozen bundle copies).
- [ ] Row order/units byte-compatible with live bundle row (`firehole_obs:10730`); replay tests unmodified and green.
- [ ] Full suite green; no `requests` import (stdlib urllib only).

## 9. Effort + dependencies

Effort: S (extract + wrapper + tests; ~120 lines). Dependencies: none new. Count verified: 1 fetcher, 0 additional copies to migrate — migration risk is minimal by construction.
