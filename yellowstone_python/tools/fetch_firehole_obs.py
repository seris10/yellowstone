"""Fetch a frozen Firehole observation bundle for reach-scale calibration.

Sources (all measured, all remote — nothing authored here):
  - USGS Water Services IV: discharge (00060, ft3/s -> m3/s) and water
    temperature (00010, C) at Firehole gauges 06036805 (Old Faithful,
    upstream of Midway) and 06036905 (near West Yellowstone, downstream
    of all Firehole thermal inflows).
  - Open-Meteo forecast API (NWP blend, no key): hourly air temperature,
    relative humidity, 10-m wind, shortwave radiation, cloud cover at
    the upstream gauge coordinates. Forcing, not observation.

Output is a timestamped JSON bundle under derived/. Re-fetching later
yields a different window — record fetched_at_utc and the exact URLs.
Calibration consumes the bundle; this tool never fits anything.

Usage:
    python3 tools/fetch_firehole_obs.py --out derived/firehole_obs.json
    python3 tools/fetch_firehole_obs.py --out derived/firehole_obs.json --days 7
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USGS_IV = "https://waterservices.usgs.gov/nwis/iv/"
try:
    from tools.fetch_met_forcing import MET_VARS, OPEN_METEO
except ImportError:  # run as a script: sibling module is on the script dir
    from fetch_met_forcing import MET_VARS, OPEN_METEO

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

MET_VARS = MET_VARS  # re-exported from fetch_met_forcing (one-cycle backcompat)
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
    return datetime.fromisoformat(text).timestamp()


def fetch_usgs_series(site: str, days: int) -> dict:
    """IV discharge (m3/s) + water temperature (C) as [epoch, value] pairs."""
    url = (f"{USGS_IV}?sites={site}&parameterCd=00060,00010"
           f"&period=P{days}D&format=json")
    data = _get_json(url)
    out: dict[str, list] = {"discharge_m3_s": [], "temperature_c": []}
    for series in data.get("value", {}).get("timeSeries", []):
        codes = [c.get("value") for c in
                 series.get("variable", {}).get("variableCode", [])]
        values = series.get("values", [{}])[0].get("value", [])
        pairs = []
        for row in values:
            text = (row.get("value") or "").strip()
            if text in ("", "-999999"):
                continue
            try:
                pairs.append([_parse_iso_epoch(row["dateTime"]),
                              float(text)])
            except (ValueError, KeyError):
                continue
        pairs.sort()
        if "00060" in codes:
            out["discharge_m3_s"] = [[t, v * CFS_TO_M3S] for t, v in pairs]
        elif "00010" in codes:
            out["temperature_c"] = pairs
    if not out["discharge_m3_s"] or not out["temperature_c"]:
        raise RuntimeError(
            f"USGS site {site}: missing discharge or temperature series "
            f"(n_q={len(out['discharge_m3_s'])}, "
            f"n_t={len(out['temperature_c'])})")
    return {"url": url, "series": out}


def fetch_met(latitude: float, longitude: float, days: int) -> dict:
    """Thin wrapper over fetch_met_forcing.fetch_met (same shape).

    Kept for one cycle so existing importers keep working; new code
    imports tools.fetch_met_forcing directly.
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
    met = fetch_met(upstream["latitude"], upstream["longitude"], args.days)
    print(f"  hourly n={len(met['hourly'])}, elevation {met['elevation_m']} m")

    bundle = {
        "schema": "yellowstone.firehole_obs.v1",
        "status": "measured_remote_not_calibrated",
        "fetched_at_utc": fetched_at,
        "window_days": args.days,
        "provenance": {
            "usgs": ("USGS Water Services IV, provisional and subject to "
                     "revision; discharge converted ft3/s -> m3/s"),
            "met": ("Open-Meteo NWP blend at upstream gauge coordinates; "
                    "forcing for the surface budget, not an observation "
                    "of Bark Cabin Creek"),
            "use": ("Upstream series are boundary forcing; downstream "
                    "series are the calibration target. Never swap them."),
        },
        "sites": sites,
        "met": met,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text(json.dumps(bundle, indent=1) + "\n", encoding="utf-8")
    tmp.replace(args.out)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
