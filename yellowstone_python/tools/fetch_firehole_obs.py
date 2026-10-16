"""Command-line entry point for firehole observation data."""
from __future__ import annotations

from yellowstone_python.river.obs_model import UPSTREAM_GAUGE, DOWNSTREAM_GAUGE
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from yellowstone_python.observations.firehole import *

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

    upstream = SITES[UPSTREAM_GAUGE]
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
