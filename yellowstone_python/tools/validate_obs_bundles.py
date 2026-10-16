"""Observation bundle schema, continuity, and coverage validation."""

from yellowstone_python.river.obs_model import UPSTREAM_GAUGE, DOWNSTREAM_GAUGE

import argparse
import json
import sys
from pathlib import Path
from yellowstone_python.common.io import write_json_atomic as _shared_json_write

from yellowstone_python.river.calibrate import check_continuity
from yellowstone_python.land.snow_validate import MAX_FILL_DAYS, SPLIT_DATE, in_to_mm

SCHEMA_FIREHOLE = "yellowstone.firehole_obs.v1"
SCHEMA_FIREHOLE_CHEM = "yellowstone.firehole_chem_obs.v1"
SCHEMA_SNOTEL = "yellowstone.snotel_obs.v1"
SCHEMA_VERDICT = "yellowstone.obs_bundle_verdict.v1"

# Gap tolerances from calibrate.fit_forcing_arrays: 4x nominal step (IV nominal 900 s, met nominal 3600 s).
GAP_USGS_S = 3600.0
GAP_MET_S = 14400.0

SNOW_CODES = ("WTEQ", "PRCP", "SNWD", "TAVG")


def _check(name: str, passed: bool, detail: str, checks: list) -> None:
    checks.append({"name": name, "passed": passed, "detail": detail})


def _continuity(pairs, label: str, max_gap_s: float, checks: list,
                nominal_steps: dict) -> bool:
    try:
        nominal = check_continuity(pairs, label, max_gap_s)
    except ValueError as exc:
        _check(f"continuity:{label}", False, str(exc), checks)
        return False
    times = sorted(p[0] for p in pairs)
    worst = max(b - a for a, b in zip(times, times[1:])) if len(times) > 1 else 0.0
    nominal_steps[label] = {"nominal_s": nominal, "worst_s": worst,
                            "max_gap_s": max_gap_s}
    _check(f"continuity:{label}", True,
           f"nominal {nominal:.0f} s, worst {worst:.0f} s within {max_gap_s:.0f} s",
           checks)
    return True


def _gate_firehole(bundle: dict, checks: list, nominal_steps: dict) -> bool:
    ok = True
    if bundle.get("schema") != SCHEMA_FIREHOLE:
        _check("schema", False, f"expected {SCHEMA_FIREHOLE}, found "
               f"{bundle.get('schema')!r}", checks)
        return False
    _check("schema", True, SCHEMA_FIREHOLE, checks)
    sites = bundle.get("sites", {})
    for site in (UPSTREAM_GAUGE, DOWNSTREAM_GAUGE):
        series = (sites.get(site) or {}).get("series", {})
        for key, label in (("temperature_c", f"{site} temperature"),
                           ("discharge_m3_s", f"{site} discharge")):
            pairs = series.get(key, [])
            if len(pairs) < 2:
                _check(f"presence:{label}", False, f"need >= 2 points, found "
                       f"{len(pairs)}", checks)
                ok = False
                continue
            _check(f"presence:{label}", True, f"n={len(pairs)}", checks)
            ok = _continuity(pairs, label, GAP_USGS_S, checks,
                             nominal_steps) and ok
    met_rows = (bundle.get("met") or {}).get("hourly", [])
    bad_rows = [i for i, r in enumerate(met_rows) if len(r) != 6]
    if bad_rows:
        _check("presence:met hourly", False,
               f"{len(bad_rows)} rows without 6 columns", checks)
        ok = False
    elif len(met_rows) < 2:
        _check("presence:met hourly", False, "need >= 2 rows", checks)
        ok = False
    else:
        _check("presence:met hourly", True, f"n={len(met_rows)}", checks)
        ok = _continuity([[r[0], r[1]] for r in met_rows], "met air",
                         GAP_MET_S, checks, nominal_steps) and ok
    if ok:
        up = sites[UPSTREAM_GAUGE]["series"]
        t0 = max(min(p[0] for p in up["temperature_c"]),
                 min(r[0] for r in met_rows))
        t1 = min(max(p[0] for p in up["temperature_c"]),
                 max(r[0] for r in met_rows))
        if t1 > t0:
            _check("window", True, f"overlap {(t1 - t0) / 3600:.2f} h", checks)
        else:
            _check("window", False, "empty forcing overlap", checks)
            ok = False
    return ok


def _gate_snow(bundle: dict, checks: list, nominal_steps: dict) -> bool:
    ok = True
    if bundle.get("schema") != SCHEMA_SNOTEL:
        _check("schema", False, f"expected {SCHEMA_SNOTEL}, found "
               f"{bundle.get('schema')!r}", checks)
        return False
    _check("schema", True, SCHEMA_SNOTEL, checks)
    sites = bundle.get("sites", {})
    if not sites:
        _check("presence:sites", False, "no sites", checks)
        return False
    _check("presence:sites", True, f"{sorted(sites)}", checks)
    for triplet, site in sites.items():
        days = site.get("days", {})
        if not days:
            _check(f"presence:{triplet} days", False, "zero days", checks)
            ok = False
            continue
        dates = sorted(days)
        missing = [c for c in SNOW_CODES
                   if any(c not in days[d] for d in dates)]
        if missing:
            _check(f"presence:{triplet} codes", False,
                   f"codes missing on some days: {missing}", checks)
            ok = False
        else:
            _check(f"presence:{triplet} codes", True,
                   f"n_days={len(dates)}", checks)
        day0 = days[dates[0]].get("WTEQ")
        if day0 is not None and day0 > 0 and in_to_mm(day0) > in_to_mm(0.04):
            _check(f"snow-coverage:{triplet} spinup", False,
                   f"day-0 SWE {in_to_mm(day0):.2f} mm nonzero, needs spin-up",
                   checks)
            ok = False
        else:
            _check(f"snow-coverage:{triplet} spinup", True,
                   "day-0 SWE at/below 0.04 in", checks)
        gap = 0
        filled = 0
        failed = False
        for d in dates:
            v = days[d].get("TAVG")
            if v is None:
                gap += 1
                if gap > MAX_FILL_DAYS:
                    failed = True
                    break
                filled += 1
            else:
                gap = 0
        if failed or (days[dates[0]].get("TAVG") is None):
            _check(f"snow-coverage:{triplet} tavg-fill", False,
                   "TAVG gap exceeds imputable range "
                   f"(MAX_FILL_DAYS={MAX_FILL_DAYS})", checks)
            ok = False
        else:
            _check(f"snow-coverage:{triplet} tavg-fill", True,
                   f"tavg_filled={filled}", checks)
        try:
            idx = next(i for i, d in enumerate(dates) if d >= SPLIT_DATE)
            if idx == 0 or idx >= len(dates):
                raise StopIteration
            _check(f"snow-coverage:{triplet} holdout-span", True,
                   f"train {idx}, holdout {len(dates) - idx}", checks)
        except StopIteration:
            _check(f"snow-coverage:{triplet} holdout-span", False,
                   f"window does not span SPLIT_DATE={SPLIT_DATE}", checks)
            ok = False
    return ok


def _gate_firehole_chem(bundle: dict, checks: list) -> bool:
    """Chemistry bundle gate; empty series are recorded as findings."""
    if bundle.get("schema") != SCHEMA_FIREHOLE_CHEM:
        _check("schema", False, f"expected {SCHEMA_FIREHOLE_CHEM}, found "
               f"{bundle.get('schema')!r}", checks)
        return False
    _check("schema", True, SCHEMA_FIREHOLE_CHEM, checks)
    sites = bundle.get("sites", {})
    if not sites:
        _check("presence:sites", False, "no sites", checks)
        return False
    _check("presence:sites", True, f"{sorted(sites)}", checks)
    for site_id, site in sites.items():
        series = site.get("series", {})
        series_status = site.get("series_status", {})
        for name in ("specific_conductance", "dissolved_oxygen", "ph"):
            n = len(series.get(name, []))
            status = series_status.get(name, "unknown")
            _check(
                f"series:{site_id}:{name}", True,
                f"n={n} status={status}", checks,
            )
    return True


def gate_bundle(bundle: dict, consumer: str) -> dict:
    """Read-only gate; returns the verdict dict (no I/O)."""
    checks: list = []
    nominal_steps: dict = {}
    schema = bundle.get("schema")
    if consumer == "auto":
        if schema == SCHEMA_FIREHOLE:
            consumer = "firehole"
        elif schema == SCHEMA_SNOTEL:
            consumer = "snow"
        elif schema == SCHEMA_FIREHOLE_CHEM:
            consumer = "firehole_chem"
        else:
            consumer = "unknown"
    if consumer == "firehole":
        passed = _gate_firehole(bundle, checks, nominal_steps)
    elif consumer == "snow":
        passed = _gate_snow(bundle, checks, nominal_steps)
    elif consumer == "firehole_chem":
        passed = _gate_firehole_chem(bundle, checks)
    else:
        _check("unknown-schema", False,
               f"schema {schema!r} is not one of {SCHEMA_FIREHOLE!r}, "
               f"{SCHEMA_SNOTEL!r} or {SCHEMA_FIREHOLE_CHEM!r}", checks)
        passed = False
    return {"schema": SCHEMA_VERDICT,
            "status": bundle.get("status", "measured_remote_not_calibrated"),
            "bundle_schema": schema,
            "bundle_fetched_at_utc": bundle.get("fetched_at_utc"),
            "consumer": consumer,
            "passed": passed, "checks": checks,
            "nominal_steps": nominal_steps}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--consumer", default="auto",
                        choices=("firehole", "snow", "firehole_chem",
                                 "all", "auto"))
    args = parser.parse_args()
    try:
        bundle = json.loads(args.bundle.read_text())
    except (OSError, ValueError) as exc:
        print(f"bundle-unreadable: {args.bundle}: {exc}")
        return 1
    if args.consumer == "all":
        verdicts = {c: gate_bundle(bundle, c) for c in ("firehole", "snow")}
        for v in verdicts.values():
            v["bundle"] = str(args.bundle)
        passed = any(v["passed"] for v in verdicts.values())
        verdict = {"schema": SCHEMA_VERDICT,
                   "status": bundle.get("status",
                                        "measured_remote_not_calibrated"),
                   "bundle": str(args.bundle),
                   "bundle_schema": bundle.get("schema"),
                   "bundle_fetched_at_utc": bundle.get("fetched_at_utc"),
                   "consumer": "all", "passed": passed,
                   "verdicts": verdicts}
    else:
        verdict = gate_bundle(bundle, args.consumer)
        verdict["bundle"] = str(args.bundle)
        passed = verdict["passed"]
    if args.out is not None:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            _shared_json_write(args.out, verdict)
        except OSError as exc:
            print(json.dumps(verdict, indent=2))
            print(f"verdict-unwritable: {args.out}: {exc}")
            return 1
    for c in (verdict.get("checks") or
              [c for v in verdict.get("verdicts", {}).values()
               for c in v["checks"]]):
        print(("PASS" if c["passed"] else "FAIL") + f" {c['name']}: {c['detail']}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
