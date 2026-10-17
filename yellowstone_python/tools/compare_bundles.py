"""Old-vs-refetch drift detection over observation bundles (exact epoch/date alignment)."""

import argparse
import json
import sys
from pathlib import Path
from yellowstone_python.common.io import write_json_atomic as _shared_json_write

SCHEMA_DRIFT = "yellowstone.bundle_drift.v1"

# Defaults exceed bundle step noise: Q upstream 2.9%, downstream 3.1%; temperature 0.4 C.
DEFAULT_Q_REL_TOL = 0.05
DEFAULT_T_ABS_TOL = 0.5
DEFAULT_WTEQ_ABS_TOL_IN = 2.0
DEFAULT_SNWD_ABS_TOL_IN = 12.0
DEFAULT_TEMP_ABS_TOL_F = 15.0


def _build_snow_tols(wteq_abs_tol_in: float, snwd_abs_tol_in: float,
                     temp_abs_tol_f: float) -> dict:
    return {"WTEQ": wteq_abs_tol_in, "PRCP": wteq_abs_tol_in,
            "SNWD": snwd_abs_tol_in, "TAVG": temp_abs_tol_f,
            "TMAX": temp_abs_tol_f, "TMIN": temp_abs_tol_f}


SNOW_TOLS = _build_snow_tols(DEFAULT_WTEQ_ABS_TOL_IN,
                             DEFAULT_SNWD_ABS_TOL_IN,
                             DEFAULT_TEMP_ABS_TOL_F)

PROVENANCE_NOTE = (
    "USGS IV and AWDB bundles carry no source version field; "
    "fetched_at_utc is the only revision identity available. "
    "Revised values with a newer fetched_at_utc are expected, not drift."
)


def _series_delta(old: list, new: list) -> dict | None:
    """Max-abs delta over exact-epoch alignment; None if non-informative."""
    if not old or not new:
        return None
    om = {p[0]: p[1] for p in old}
    nm = {p[0]: p[1] for p in new}
    common = sorted(set(om) & set(nm))
    t_old0 = min(om)
    t_new0 = min(nm)
    window_shift_s = abs(float(t_old0) - float(t_new0))
    if not common:
        return {"overlap": 0, "window_shift_s": window_shift_s,
                "n_old": len(old), "n_new": len(new)}
    deltas = [abs(om[t] - nm[t]) for t in common]
    return {"overlap": len(common), "max_abs": max(deltas),
            "n_old": len(old), "n_new": len(new),
            "window_shift_s": window_shift_s}


def _days_delta(old_days: dict, new_days: dict, code: str, tol: float) -> dict:
    old = {d: v[code] for d, v in old_days.items() if v.get(code) is not None}
    new = {d: v[code] for d, v in new_days.items() if v.get(code) is not None}
    if not old or not new:
        return {"element": code, "informative": False}
    common = sorted(set(old) & set(new))
    if not common:
        return {"element": code, "informative": True, "overlap": 0}
    mx = max(abs(old[d] - new[d]) for d in common)
    return {"element": code, "informative": True, "overlap": len(common),
            "max_abs": mx, "coverage_old": len(old), "coverage_new": len(new),
            "tol": tol, "passed": mx <= tol}


def compare_bundles(old: dict, new: dict, q_rel_tol: float,
                     t_abs_tol: float, snow_tols: dict | None = None) -> dict:
    """Read-only comparison; returns the drift report dict."""
    metrics: list = []
    non_informative: list = []
    tols = snow_tols if snow_tols is not None else SNOW_TOLS
    if old.get("schema") != new.get("schema"):
        return {"schema": SCHEMA_DRIFT,
                "status": "measured_remote_not_calibrated",
                "passed": False,
                "error": f"schema-mismatch: {old.get('schema')!r} vs "
                         f"{new.get('schema')!r}",
                "metrics": metrics, "non_informative": non_informative,
                "provenance_note": PROVENANCE_NOTE}
    schema = old.get("schema")
    if schema == "yellowstone.firehole_obs.v1":
        for site in sorted(set(old.get("sites", {})) |
                           set(new.get("sites", {}))):
            oseries = (old.get("sites", {}).get(site) or {}).get("series", {})
            nseries = (new.get("sites", {}).get(site) or {}).get("series", {})
            q = _series_delta(oseries.get("discharge_m3_s", []),
                              nseries.get("discharge_m3_s", []))
            t = _series_delta(oseries.get("temperature_c", []),
                              nseries.get("temperature_c", []))
            if q is None:
                non_informative.append(f"{site}/discharge_m3_s")
            elif "max_abs" not in q:
                metrics.append({"element": f"{site}/discharge_m3_s",
                                "overlap": 0, "passed": False,
                                "detail": "no-overlap",
                                "window_shift_s": q.get("window_shift_s")})
            else:
                base = max(abs(p[1]) for p in
                           oseries["discharge_m3_s"]) or 1.0
                rel = q["max_abs"] / base
                metrics.append({"element": f"{site}/discharge_m3_s",
                                "max_abs": q["max_abs"], "max_rel": rel,
                                "coverage_old": q["n_old"],
                                "coverage_new": q["n_new"],
                                "window_shift_s": q["window_shift_s"],
                                "tol": q_rel_tol, "passed": rel <= q_rel_tol})
            if t is None:
                non_informative.append(f"{site}/temperature_c")
            elif "max_abs" not in t:
                metrics.append({"element": f"{site}/temperature_c",
                                "overlap": 0, "passed": False,
                                "detail": "no-overlap",
                                "window_shift_s": t.get("window_shift_s")})
            else:
                metrics.append({"element": f"{site}/temperature_c",
                                "max_abs": t["max_abs"],
                                "coverage_old": t["n_old"],
                                "coverage_new": t["n_new"],
                                "window_shift_s": t["window_shift_s"],
                                "tol": t_abs_tol,
                                "passed": t["max_abs"] <= t_abs_tol})
        omet = (old.get("met") or {}).get("hourly", [])
        nmet = (new.get("met") or {}).get("hourly", [])
        for col, name in ((1, "met/air"), (2, "met/rh"), (3, "met/wind"),
                          (4, "met/sw"), (5, "met/cloud")):
            d = _series_delta([[r[0], r[col]] for r in omet if len(r) > col],
                              [[r[0], r[col]] for r in nmet if len(r) > col])
            if d is None:
                non_informative.append(name)
            elif "max_abs" not in d:
                metrics.append({"element": name, "overlap": 0,
                                "passed": False, "detail": "no-overlap",
                                "window_shift_s": d.get("window_shift_s")})
            else:
                metrics.append({"element": name, "max_abs": d["max_abs"],
                                "coverage_old": d["n_old"],
                                "coverage_new": d["n_new"],
                                "window_shift_s": d["window_shift_s"],
                                "tol": t_abs_tol,
                                "passed": d["max_abs"] <= t_abs_tol})
    elif schema == "yellowstone.snotel_obs.v1":
        for triplet in sorted(set(old.get("sites", {})) |
                              set(new.get("sites", {}))):
            odays = (old.get("sites", {}).get(triplet) or {}).get("days", {})
            ndays = (new.get("sites", {}).get(triplet) or {}).get("days", {})
            for code, tol in tols.items():
                m = _days_delta(odays, ndays, code, tol)
                if not m.get("informative", True):
                    non_informative.append(f"{triplet}/{code}")
                elif "max_abs" not in m:
                    metrics.append({"element": f"{triplet}/{code}",
                                    "overlap": 0, "passed": False,
                                    "detail": "no-overlap"})
                else:
                    metrics.append(m)
    else:
        return {"schema": SCHEMA_DRIFT,
                "status": "measured_remote_not_calibrated",
                "passed": False, "error": f"unknown-schema: {schema!r}",
                "metrics": metrics, "non_informative": non_informative,
                "provenance_note": PROVENANCE_NOTE}
    informative = [m for m in metrics if "passed" in m]
    passed = all(m["passed"] for m in informative)
    if not informative:
        verdict = "no-informative-data"
        passed = False
    elif all(m.get("max_abs", 1) == 0 for m in informative):
        verdict = "identical"
    elif passed:
        verdict = "within-tolerance-revision"
    else:
        verdict = "drift-exceeds-tolerance"
    return {"schema": SCHEMA_DRIFT,
            "status": "measured_remote_not_calibrated",
            "old": {"fetched_at_utc": old.get("fetched_at_utc")},
            "new": {"fetched_at_utc": new.get("fetched_at_utc")},
            "passed": passed, "verdict": verdict, "metrics": metrics,
            "non_informative": non_informative,
            "provenance_note": PROVENANCE_NOTE}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--q-rel-tol", type=float, default=DEFAULT_Q_REL_TOL)
    parser.add_argument("--t-abs-tol", type=float, default=DEFAULT_T_ABS_TOL)
    parser.add_argument("--wteq-abs-tol-in", type=float,
                        default=DEFAULT_WTEQ_ABS_TOL_IN,
                        help="SNOTEL WTEQ/PRCP absolute tolerance (inches)")
    parser.add_argument("--snwd-abs-tol-in", type=float,
                        default=DEFAULT_SNWD_ABS_TOL_IN,
                        help="SNOTEL SNWD absolute tolerance (inches)")
    parser.add_argument("--temp-abs-tol-f", type=float,
                        default=DEFAULT_TEMP_ABS_TOL_F,
                        help="SNOTEL TAVG/TMAX/TMIN absolute tolerance (F)")
    args = parser.parse_args()
    try:
        old = json.loads(args.old.read_text())
        new = json.loads(args.new.read_text())
    except (OSError, ValueError) as exc:
        print(f"bundle-unreadable: {exc}")
        return 1
    snow_tols = _build_snow_tols(args.wteq_abs_tol_in, args.snwd_abs_tol_in,
                                 args.temp_abs_tol_f)
    report = compare_bundles(old, new, args.q_rel_tol, args.t_abs_tol,
                             snow_tols=snow_tols)
    report.setdefault("old", {})["path"] = str(args.old)
    report.setdefault("new", {})["path"] = str(args.new)
    if args.out is not None:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            _shared_json_write(args.out, report)
        except OSError as exc:
            print(json.dumps(report, indent=2))
            print(f"report-unwritable: {args.out}: {exc}")
            return 1
    if "error" in report:
        print(f"FAIL {report['error']}")
        return 1
    for m in report["metrics"]:
        if "passed" not in m:
            print(f"FAIL {m['element']}: {m.get('detail')}")
        else:
            print(("PASS" if m["passed"] else "FAIL") +
                  f" {m['element']}: max_abs={m.get('max_abs')} "
                  f"tol={m.get('tol')}")
    for n in report["non_informative"]:
        print(f"SKIP {n}: non-informative")
    print(f"drift: {report['verdict']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
