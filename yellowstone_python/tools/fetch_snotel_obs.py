"""Command-line entry point for snotel observation data."""
from __future__ import annotations
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from yellowstone_python.observations.snotel import *

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--begin", default="2025-10-01")
    parser.add_argument("--end", default="2026-07-31")
    args = parser.parse_args()
    try:
        begin_date, end_date = validate_date_window(args.begin, args.end)
    except ValueError as exc:
        parser.error(str(exc))
    begin_iso = begin_date.isoformat()
    end_iso = end_date.isoformat()

    fetched_at = datetime.now(timezone.utc).isoformat()
    sites = {}
    for triplet, info in SITES.items():
        print(f"AWDB {triplet} ({info['name']}) ...")
        result = fetch_site_daily(triplet, begin_iso, end_iso)
        n_days = len(result["days"])
        print(f"  days={n_days} coverage={result['coverage']}")
        sites[triplet] = {**info, **result}

    bundle = {
        "schema": "yellowstone.snotel_obs.v1",
        "status": "measured_remote_not_calibrated",
        "components": {
            "sites": {"kind": "observation",
                      "status": "measured_remote_not_calibrated"},
        },
        "fetched_at_utc": fetched_at,
        "window": {"begin": begin_iso, "end": end_iso},
        "semantics": dict(ELEMENT_SEMANTICS),
        "expected_units": dict(EXPECTED_UNITS),
        "site_brief": ("NRCS AWDB site metadata and element periods of record; "
                       "coverage counts above recomputed at fetch time"),
        "provenance": {
            "awdb": ("NRCS NWCC AWDB REST, provisional and subject to "
                     "revision; values stored raw in reported units, see "
                     "per-site units table"),
            "prcp": ("PRCP is a daily accumulation increment (semantics "
                     "map labels it accumulation_increment); water balance "
                     "code must sum, not difference"),
            "units": ("WTEQ/PRCP/SNWD in inches (x25.4 -> mm); "
                      "TAVG/TMAX/TMIN in degF ((F-32)x5/9 -> degC)"),
        },
        "sites": sites,
    }
    atomic_write_json(args.out, bundle)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
