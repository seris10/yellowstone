"""Shared Open-Meteo forcing source (stdlib urllib only, no requests).

Owns OPEN_METEO/MET_VARS and the row builder. fetch_firehole_obs.fetch_met
is a thin wrapper over fetch_met_forcing.fetch_met (same name, same return
shape) so existing callers and bundles are unaffected.
See tooling-spec-fetch-met-forcing.md.
"""

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
MET_VARS = ("temperature_2m", "relative_humidity_2m", "wind_speed_10m",
            "shortwave_radiation", "cloud_cover")
USER_AGENT = "yellowstone-python/0.1 (research calibration fetch)"
TIMEOUT_S = 60

SCHEMA_MET = "yellowstone.met_forcing.v1"

# Row schema FROZEN at width 6 (consumer indices in
# replay.calibrate._fit_forcing_arrays). New variables extend width only
# under a v2 schema.
# [epoch_s_UTC, air_C, rh_0-1, wind_mps, sw_Wm2, cloud_0-1]


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_met_rows(data: dict, variables=MET_VARS) -> dict:
    """Pure row builder: Open-Meteo JSON -> {elevation_m, hourly}.

    Conversions (frozen): rh_pct/100, wind_kmh/3.6, cloud_pct/100.
    """
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    cols = [hourly.get(var, []) for var in variables]
    if not times or any(len(col) != len(times) for col in cols):
        raise RuntimeError("Open-Meteo: incomplete hourly table")
    rows = []
    for i, stamp in enumerate(times):
        epoch = datetime.fromisoformat(stamp.replace("Z", "+00:00")
                                       ).replace(tzinfo=timezone.utc
                                                 ).timestamp()
        air, rh_pct, wind_kmh, sw, cloud = (float(cols[j][i]) for j in range(5))
        rows.append([epoch, air, rh_pct / 100.0, wind_kmh / 3.6, sw,
                     cloud / 100.0])
    return {"elevation_m": data.get("elevation"), "hourly": rows}


def fetch_met_forcing(latitude: float, longitude: float, days: int,
                      variables=MET_VARS) -> dict:
    """Fetch + build; returns {url, elevation_m, hourly}."""
    url = (f"{OPEN_METEO}?latitude={latitude}&longitude={longitude}"
           f"&hourly={','.join(variables)}"
           f"&past_days={days}&forecast_days=1&timezone=UTC")
    try:
        data = _get_json(url)
    except Exception as exc:
        raise RuntimeError(f"met-fetch-failed: {OPEN_METEO}: {exc}") from exc
    return {"url": url, **build_met_rows(data, variables)}


def fetch_met(latitude: float, longitude: float, days: int) -> dict:
    """Backcompat alias: same name/shape as the former embedded fetcher."""
    return fetch_met_forcing(latitude, longitude, days)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--vars", default=",".join(MET_VARS))
    args = parser.parse_args()
    if args.days < 1 or args.days > 16:
        parser.error("--days must be in [1, 16]")
    variables = tuple(args.vars.split(","))
    if len(variables) != len(MET_VARS):
        # v1 row width is frozen at 6 (consumer indices); wider/narrower
        # sets need a v2 schema, not a flag.
        parser.error(f"--vars must list exactly {len(MET_VARS)} variables "
                     f"for {SCHEMA_MET}")
    try:
        result = fetch_met_forcing(args.lat, args.lon, args.days, variables)
    except RuntimeError as exc:
        print(exc)
        return 1
    bundle = {
        "schema": SCHEMA_MET,
        "status": "measured_remote_not_calibrated",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "request": {"lat": args.lat, "lon": args.lon, "days": args.days,
                    "vars": list(variables), "url": result["url"]},
        "provenance_note": ("Open-Meteo NWP blend; model run not pinned "
                            "beyond url + fetched_at_utc (model-unpinned); "
                            "forcing for the surface budget, not an "
                            "observation"),
        "elevation_m": result["elevation_m"],
        "hourly": result["hourly"],
    }
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_name(args.out.name + ".tmp")
        tmp.write_text(json.dumps(bundle, indent=1) + "\n", encoding="utf-8")
        tmp.replace(args.out)
    except OSError as exc:
        print(f"bundle-unwritable: {args.out}: {exc}")
        return 1
    print(f"met: n={len(result['hourly'])} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
