"""Fetch a frozen SNOTEL observation bundle for snow + soil-water validation.

Sources (all measured, all remote — nothing authored here):
  - NRCS NWCC AWDB REST: daily WTEQ (in), PRCP (in), SNWD (in),
    TAVG/TMAX/TMIN (degF) for two verified SNOTEL sites:
      609:MT:SNTL Madison Plateau (2350 m, upper-Madison plateau snow
        source ~15 km SE of West Yellowstone, between Firehole/Madison arms)
      924:MT:SNTL West Yellowstone (2036 m, valley floor ~5 km from
        Madison Junction / Firehole confluence)
  - Site selection, element periods-of-record, and the recommended WY2026
    window were verified live by a parallel worker; see
    worker_briefs/snotel_sites.md (cited, not copied: re-verify
    coverage counts below at fetch time).

Values are stored RAW as returned (in / degF) with their storedUnitCode;
unit conversion (x25.4, degF->degC) happens in the consuming validation
with documented factors, so the bundle stays a faithful fetch record.
Null value = missing day, preserved as null. PRCP is a daily accumulation
increment; confirm accumulation-vs-increment semantics in consuming code
before water-balance use (flagged in the site brief).

Output is a timestamped JSON bundle under derived/. This tool never fits
anything.

Usage:
    python3 tools/fetch_snotel_obs.py --out derived/snotel_obs.json
    python3 tools/fetch_snotel_obs.py --out derived/snotel_obs.json \
        --begin 2025-10-01 --end 2026-07-31
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

AWDB_DATA = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
USER_AGENT = "yellowstone-python/0.1 (research calibration fetch)"

ELEMENTS = ("WTEQ", "PRCP", "SNWD", "TAVG", "TMAX", "TMIN")

SITES = {
    "609:MT:SNTL": {
        "name": "Madison Plateau",
        "role": "high_snow_source_between_firehole_and_madison_arms",
        "latitude": 44.58623,
        "longitude": -111.11627,
        "elevation_m": 2350,
        "huc": "100200070204",
    },
    "924:MT:SNTL": {
        "name": "West Yellowstone",
        "role": "valley_floor_near_firehole_confluence",
        "latitude": 44.65866,
        "longitude": -111.09199,
        "elevation_m": 2036,
        "huc": "100200070205",
    },
}


def _get_json(url: str) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_site_daily(triplet: str, begin: str, end: str) -> dict:
    """Daily element series for one station triplet over [begin, end].

    Returns {"url": ..., "days": {date: {element: value-or-None}},
    "units": {element: storedUnitCode}, "coverage": {element: non-null n}}.
    """
    params = urllib.parse.urlencode({
        "stationTriplets": triplet,
        "elements": ",".join(ELEMENTS),
        "duration": "DAILY",
        "beginDate": begin,
        "endDate": end,
    })
    url = f"{AWDB_DATA}?{params}"
    data = _get_json(url)
    if len(data) != 1 or data[0].get("stationTriplet") != triplet:
        raise RuntimeError(f"AWDB: unexpected station envelope for {triplet}")
    days: dict[str, dict] = {}
    units: dict[str, str] = {}
    for block in data[0].get("data", []):
        el = block.get("stationElement", {})
        code = el.get("elementCode")
        if code not in ELEMENTS:
            continue
        units[code] = el.get("storedUnitCode", "unknown")
        for row in block.get("values", []):
            day = row.get("date")
            if not day:
                continue
            days.setdefault(day, {})[code] = row.get("value")
    for day in days:
        for code in ELEMENTS:
            days[day].setdefault(code, None)
    coverage = {code: sum(1 for d in days.values() if d[code] is not None)
                for code in ELEMENTS}
    if not days:
        raise RuntimeError(f"AWDB: no daily rows for {triplet}")
    return {"url": url, "days": days, "units": units, "coverage": coverage}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--begin", default="2025-10-01")
    parser.add_argument("--end", default="2026-07-31")
    args = parser.parse_args()
    begin = date.fromisoformat(args.begin)
    end = date.fromisoformat(args.end)
    if end < begin:
        parser.error("--end precedes --begin")
    if (end - begin).days > 400:
        parser.error("window over 400 days; split the fetch")

    fetched_at = datetime.now(timezone.utc).isoformat()
    sites = {}
    for triplet, info in SITES.items():
        print(f"AWDB {triplet} ({info['name']}) ...")
        result = fetch_site_daily(triplet, args.begin, args.end)
        n_days = len(result["days"])
        print(f"  days={n_days} coverage={result['coverage']}")
        sites[triplet] = {**info, **result}

    bundle = {
        "schema": "yellowstone.snotel_obs.v1",
        "status": "measured_remote_not_calibrated",
        "fetched_at_utc": fetched_at,
        "window": {"begin": args.begin, "end": args.end},
        "site_brief": ("worker_briefs/snotel_sites.md: site "
                       "selection + element POR verified live; "
                       "coverage counts above recomputed at fetch time"),
        "provenance": {
            "awdb": ("NRCS NWCC AWDB REST, provisional and subject to "
                     "revision; values stored raw in reported units, see "
                     "per-site units table"),
            "prcp": ("PRCP is a daily accumulation increment; consuming "
                     "code must confirm accumulation-vs-increment "
                     "semantics before water-balance use"),
            "units": ("WTEQ/PRCP/SNWD in inches (x25.4 -> mm); "
                      "TAVG/TMAX/TMIN in degF ((F-32)x5/9 -> degC)"),
        },
        "sites": sites,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text(json.dumps(bundle, indent=1) + "\n", encoding="utf-8")
    tmp.replace(args.out)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
