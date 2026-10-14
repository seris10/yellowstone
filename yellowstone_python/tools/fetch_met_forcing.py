"""Command-line entry point for met observations."""
import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from yellowstone_python.observations.met import *

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--vars", default=",".join(MET_VARS))
    args = parser.parse_args(argv)
    if args.days < 1 or args.days > 16:
        parser.error("--days must be in [1, 16]")
    variables = tuple(args.vars.split(","))
    if len(variables) != len(MET_VARS):
        # v1 row width is 6 (consumer indices); other widths belong under a v2 schema.
        parser.error(f"--vars must list exactly {len(MET_VARS)} variables "
                     f"for {SCHEMA_MET}")
    try:
        result, model_meta = fetch_met_forcing_with_meta(
            args.lat, args.lon, args.days, variables)
    except (RuntimeError, ValueError) as exc:
        print(exc)
        return 1
    precip = result.get("precipitation_mm")
    precip_status = ("model_output_not_observation" if precip is not None
                     else "not_available")
    bundle = {
        "schema": SCHEMA_MET,
        "status": "measured_remote_not_calibrated",
        "kind": "model_forcing",
        "role": "surface_budget_forcing",
        "components": {
            "hourly": {"kind": "model_forcing",
                       "status": "model_output_not_observation"},
            "precipitation_mm": {"kind": "model_forcing",
                                 "status": precip_status},
        },
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider_grid_point": result.get("provider_grid_point"),
        "request": {"lat": args.lat, "lon": args.lon, "days": args.days,
                    "vars": list(variables), "url": result["url"]},
        "columns": list(MET_COLUMNS),
        "units": {"air_C": "degC", "rh_0_1": "fraction",
                  "wind_mps": "m/s", "sw_Wm2": "W/m2",
                  "cloud_0_1": "fraction",
                  "precipitation_mm": "mm_per_hour_step"},
        "normalized_units": {"temperature_2m": "degC",
                             "relative_humidity_2m": "fraction",
                             "wind_speed_10m": "m/s",
                             "shortwave_radiation": "W/m2",
                             "cloud_cover": "fraction",
                             "precipitation": "mm"},
        "provider_units": {"temperature_2m": "degC",
                           "relative_humidity_2m": "percent",
                           "wind_speed_10m": "km/h",
                           "shortwave_radiation": "W/m2",
                           "cloud_cover": "percent",
                           "precipitation": "mm"},
        "provider_timezone": "UTC",
        "model_meta": model_meta,
        "generation_time_ms": model_meta.get("generationtime_ms"),
        "provenance_note": ("Open-Meteo NWP blend; model run captured "
                            "via generation_time_ms and model_meta. "
                            "Forcing for the surface budget."),
        "elevation_m": result["elevation_m"],
        "hourly_origin_epoch_s": result.get("hourly_origin_epoch_s"),
        "hourly": result["hourly"],
        "precipitation_mm": precip,
    }
    try:
        atomic_write_json(args.out, bundle)
    except OSError as exc:
        print(f"bundle-unwritable: {args.out}: {exc}")
        return 1
    print(f"met: n={len(result['hourly'])} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
