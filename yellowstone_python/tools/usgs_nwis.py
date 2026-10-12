"""Fetch USGS field measurements and time-series data for Firehole River sites.

Uses the USGS National Water Information System (NWIS) API via stdlib urllib.
No external dependencies beyond numpy/pandas.

Field measurements include cross-section data (width, area, velocity, discharge)
collected by USGS technicians using current-meter methods. These are the real-world
channel geometry observations that the 1-D solver needs.

Usage:
    python tools/usgs_nwis.py --site 06036805 --out derived/usgs_06036805.json

Flags: --site (required), --out (required), --period-days (default 30).
NOTE: earlier docstring versions advertised --measurements/--daily; those
flags never existed in main() and are not supported. The RDB limb
(_fetch_rdb) returns [] since waterdata.usgs.gov moved to JS/HTML
(Oct 2026); IV via waterservices works.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta

BASE_URL = "https://nwis.waterdata.usgs.gov/usa/nwis"
# Modern Water Services endpoint for instantaneous values. The legacy
# /usa/nwis/iv/ JSON path stopped returning data (Oct 2026: HTML/error);
# waterservices returns the same WaterML-JSON timeSeries schema.
IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
SITES = {
    "06036805": {
        "name": "Firehole River at Old Faithful, YNP",
        "drainage_area_sqmi": 39.5,
        "latitude": 44.459333,
        "longitude": -110.822272,
        "altitude_ft": 7339.88,
        "notes": "Upstream of Midway Geyser Basin; Upper Geyser Basin inflows only",
    },
    "06036905": {
        "name": "Firehole River near West Yellowstone MT",
        "drainage_area_sqmi": 261.0,
        "latitude": 44.620183,
        "longitude": -110.863503,
        "altitude_ft": 7056.08,
        "notes": "Downstream of all Firehole thermal inflows; below Firehole Falls",
    },
}

# USGS parameter codes
PARAM_DISCHARGE = "000060"   # Actually 00060
PARAM_TEMP = "00010"         # Water temperature
PARAM_GAGE_HEIGHT = "00065"  # Gage height
PARAM_WIDTH = "00066"        # Stream width
PARAM_AREA = "00067"         # Cross-section area
PARAM_VELOCITY = "00068"     # Velocity

PARAM_CODES = {
    "00060": "discharge_cfs",
    "00010": "temperature_c",
    "00065": "gage_height_ft",
    "00066": "width_ft",
    "00067": "area_sqft",
    "00068": "velocity_fps",
}


def _fetch_rdb(site_no: str, begin_date: str = "", end_date: str = "",
               parameter_cd: str = "") -> list[dict]:
    """Fetch RDB-format data from NWIS. Returns list of dicts.

    NOTE (Oct 2026): waterdata.usgs.gov serves the measurements page as
    JS/HTML now, so this returns [] for field-measurement queries.
    Machine-readable cross-section surveys (width/area/velocity) are
    currently unfetchable — that is why channel geometry still leans on
    DEM transects. IV (discharge/temperature) via waterservices works.
    """
    parts = [f"{BASE_URL}/measurements?site_no={site_no}&format=rdb&agency_cd=USGS"]
    if begin_date:
        parts.append(f"begin_date={begin_date}")
    if end_date:
        parts.append(f"end_date={end_date}")
    if parameter_cd:
        parts.append(f"parameter_cd={parameter_cd}")
    url = "&".join(parts)

    req = urllib.request.Request(url, headers={"User-Agent": "yellowstone-python/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        raise RuntimeError(f"NWIS request failed: {e}") from e

    lines = raw.strip().split("\n")
    header_line = None
    data_start = None
    for i, line in enumerate(lines):
        if line.startswith("#"):
            continue
        if header_line is None:
            header_line = line.split("\t")
            data_start = i + 1
            # Skip units line
            if data_start < len(lines) and not lines[data_start].startswith("#"):
                col_line = lines[data_start]
                if col_line.split("\t")[0].strip() in ("5s", "15s", "20s"):
                    data_start += 1
            break

    if header_line is None:
        return []

    results = []
    for line in lines[data_start:]:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < len(header_line):
            fields.extend([""] * (len(header_line) - len(fields)))
        row = {}
        for key, val in zip(header_line, fields):
            key = key.strip()
            val = val.strip()
            if key == "agency_cd" or key == "site_no":
                continue
            if key == "measurement_dt":
                row["date"] = val
            elif key in PARAM_CODES:
                row[PARAM_CODES[key]] = _safe_float(val)
            else:
                row[key] = val
        results.append(row)
    return results


def _fetch_iv(site_no: str, parameter_cd: str, period_days: int = 30) -> list[dict]:
    """Fetch instantaneous values via Water Services (WaterML JSON)."""
    url = (f"{IV_URL}?sites={site_no}&parameterCd={parameter_cd}"
           f"&period=P{period_days}D&format=json")
    req = urllib.request.Request(url, headers={"User-Agent": "yellowstone-python/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        raise RuntimeError(f"NWIS IV request failed: {e}") from e

    series = data.get("value", {}).get("timeSeries", [])
    if not series:
        return []

    values = series[0].get("values", [{}])[0].get("value", [])
    results = []
    for v in values:
        results.append({
            "datetime": v.get("dateTime", ""),
            "value": _safe_float(v.get("value", "")),
            "qualifiers": v.get("qualifiers", []),
        })
    return results


def _safe_float(val: str) -> float | None:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def fetch_all(site_no: str, out_path: Path, period_days: int = 30) -> dict:
    """Fetch measurements, discharge IV, and temperature IV for a site."""
    if site_no not in SITES:
        raise ValueError(f"Unknown site {site_no}; have {list(SITES)}")

    site_info = SITES[site_no]
    result = {
        "site": site_info,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "measurements": [],
        "discharge_iv": [],
        "temperature_iv": [],
    }

    print(f"Fetching field measurements for {site_info['name']}...")
    try:
        result["measurements"] = _fetch_rdb(site_no)
        print(f"  {len(result['measurements'])} measurements")
    except RuntimeError as e:
        print(f"  WARNING: {e}")

    print(f"Fetching discharge (last {period_days} days)...")
    try:
        result["discharge_iv"] = _fetch_iv(site_no, "00060", period_days)
        print(f"  {len(result['discharge_iv'])} IV values")
    except RuntimeError as e:
        print(f"  WARNING: {e}")

    print(f"Fetching temperature (last {period_days} days)...")
    try:
        result["temperature_iv"] = _fetch_iv(site_no, "00010", period_days)
        print(f"  {len(result['temperature_iv'])} IV values")
    except RuntimeError as e:
        print(f"  WARNING: {e}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"Wrote {out_path}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, choices=list(SITES))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--period-days", type=int, default=30)
    args = parser.parse_args()
    fetch_all(args.site, args.out, args.period_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
