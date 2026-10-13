"""Fetch a frozen Firehole observation bundle for reach-scale calibration.
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USGS_IV = "https://waterservices.usgs.gov/nwis/iv/"
try:
    from tools.observation_io import (atomic_write_json, parse_utc_timestamp,
                                      validate_time_value_pairs)
except ImportError:  # run as a script: sibling module is on the script dir
    from observation_io import (atomic_write_json, parse_utc_timestamp,
                                validate_time_value_pairs)

SITES = {
    "06036805": {
        "name": "Firehole River at Old Faithful, YNP",
        "role": "upstream_boundary_above_midway",
        "latitude": 44.459333,
        "longitude": -110.822272,
    },
    "06036905": {
        "name": "Firehole River near West Yellowstone MT",
        "role": "downstream_target_below_all_thermal_inflows",
        "latitude": 44.620183,
        "longitude": -110.863503,
    },
}

CFS_TO_M3S = 0.028316846592
USER_AGENT = "yellowstone-python/0.1 (research calibration fetch)"


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_iso_epoch(text: str) -> float:
    """Parse an ISO timestamp to UTC epoch. Rejects naive values."""
    return parse_utc_timestamp(text)


def fetch_usgs_series(site: str, days: int) -> dict:
    """IV discharge (m3/s) + water temperature (C) as [epoch, value] pairs."""
    url = (f"{USGS_IV}?sites={site}&parameterCd=00060,00010"
           f"&period=P{days}D&format=json")
    data = _get_json(url)
    out: dict[str, list] = {"discharge_m3_s": [], "temperature_c": []}
    qualifiers: dict[str, list[list]] = {
        "discharge_m3_s": [], "temperature_c": []}
    stats: dict[str, dict[str, int]] = {}
    candidates: dict[str, int] = {"00060": 0, "00010": 0}
    for series in data.get("value", {}).get("timeSeries", []):
        codes = [c.get("value") for c in
                 series.get("variable", {}).get("variableCode", [])]
        values = series.get("values", [{}])[0].get("value", [])
        pairs = []
        series_quals = []
        seen = 0
        rejected = 0
        for row in values:
            seen += 1
            text = (row.get("value") or "").strip()
            if text in ("", "-999999"):
                rejected += 1
                continue
            try:
                epoch = parse_utc_timestamp(row["dateTime"])
                pairs.append([epoch, float(text)])
                series_quals.append(list(row.get("qualifiers") or []))
            except (ValueError, KeyError):
                rejected += 1
                continue
        order = sorted(range(len(pairs)), key=lambda i: pairs[i][0])
        pairs = [pairs[i] for i in order]
        series_quals = [series_quals[i] for i in order]
        if "00060" in codes:
            candidates["00060"] += 1
            if not out["discharge_m3_s"]:
                converted = [[t, v * CFS_TO_M3S] for t, v in pairs]
                validated = validate_time_value_pairs(
                    converted, name=f"{site}:discharge")
                out["discharge_m3_s"] = validated
                qualifiers["discharge_m3_s"] = series_quals[:len(validated)]
                stats["discharge_m3_s"] = {"rows_seen": seen,
                                           "rows_retained": len(validated),
                                           "rejected": rejected}
        elif "00010" in codes:
            candidates["00010"] += 1
            if not out["temperature_c"]:
                validated = validate_time_value_pairs(
                    pairs, name=f"{site}:temperature")
                out["temperature_c"] = validated
                qualifiers["temperature_c"] = series_quals[:len(validated)]
                stats["temperature_c"] = {"rows_seen": seen,
                                          "rows_retained": len(validated),
                                          "rejected": rejected}
    if not out["discharge_m3_s"] or not out["temperature_c"]:
        raise RuntimeError(
            f"USGS site {site}: missing discharge or temperature series "
            f"(n_q={len(out['discharge_m3_s'])}, "
            f"n_t={len(out['temperature_c'])})")
    return {
        "url": url, "series": out, "qualifiers": qualifiers,
        "ingest_stats": stats,
        "series_selection": {"candidate_count": dict(candidates),
                             "policy": "first_matching_timeSeries"},
    }


def fetch_met(latitude: float, longitude: float, days: int) -> dict:
    """Thin wrapper over fetch_met_forcing.fetch_met with the same shape.
    """
    from tools.fetch_met_forcing import fetch_met as _fetch
    try:
        return _fetch(latitude, longitude, days)
    except ImportError:
        from fetch_met_forcing import fetch_met as _fetch_script
        return _fetch_script(latitude, longitude, days)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    if args.days < 1 or args.days > 16:
        parser.error("--days must be in [1, 16]")

    fetched_at = datetime.now(timezone.utc).isoformat()
    sites = {}
    for site, info in SITES.items():
        print(f"USGS {site} ({info['name']}) ...")
        result = fetch_usgs_series(site, args.days)
        n_q = len(result["series"]["discharge_m3_s"])
        n_t = len(result["series"]["temperature_c"])
        print(f"  discharge n={n_q}, temperature n={n_t}")
        sites[site] = {**info, **result}

    upstream = SITES["06036805"]
    print(f"Open-Meteo ({upstream['latitude']}, {upstream['longitude']}) ...")
    met_data = fetch_met(float(upstream["latitude"]),  # type: ignore[arg-type]
                         float(upstream["longitude"]),  # type: ignore[arg-type]
                         args.days)
    met: dict[str, Any] = {
        **met_data,
        "kind": "model_forcing",
        "role": "surface_budget_forcing",
        "location_role": "upstream_boundary_proxy",
        "measurement_status": "not_a_direct_observation",
        "observation_status": "model_output",
    }
    print(f"  hourly n={len(met['hourly'])}, elevation {met['elevation_m']} m")

    bundle = {
        "schema": "yellowstone.firehole_obs.v1",
        "status": "measured_remote_not_calibrated",
        "components": {
            "sites": {"kind": "observation",
                      "status": "measured_remote_not_calibrated"},
            "met": {"kind": "model_forcing",
                    "status": "model_output_not_observation"},
        },
        "fetched_at_utc": fetched_at,
        "window_days": args.days,
        "provenance": {
            "usgs": ("USGS Water Services IV, provisional and subject to "
                     "revision; discharge converted ft3/s -> m3/s"),
            "met": ("Open-Meteo NWP blend at upstream gauge coordinates; "
                    "forcing for the surface budget. Reach-wide "
                    "applicability is only a proxy."),
            "use": ("Upstream series are boundary forcing; downstream "
                    "series are the calibration target."),
        },
        "sites": sites,
        "met": met,
    }
    atomic_write_json(args.out, bundle)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
