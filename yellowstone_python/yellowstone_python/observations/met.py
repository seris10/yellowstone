"""Shared Open-Meteo forcing source (stdlib urllib only)."""

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from yellowstone_python.common.checks import finite

from yellowstone_python.observations.bundles import atomic_write_json, parse_utc_timestamp

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
MET_VARS = ("temperature_2m", "relative_humidity_2m", "wind_speed_10m",
            "shortwave_radiation", "cloud_cover")
MET_COLUMNS = ("epoch_s_UTC", "air_C", "rh_0_1", "wind_mps",
               "sw_Wm2", "cloud_0_1")
# Open-Meteo precipitation uses a separate mm/step sidecar, preserving width-6 hourly rows.
PRECIP_VAR = "precipitation"
USER_AGENT = "yellowstone-python/0.1 (research calibration fetch)"
TIMEOUT_S = 60
LAT_RANGE = (-90.0, 90.0)
LON_RANGE = (-180.0, 180.0)
DAYS_RANGE = (1, 16)

SCHEMA_MET = "yellowstone.met_forcing.v1"

# MET_COLUMNS fixes the v1 width-6 order for _fit_forcing_arrays; extra columns require schema v2.


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_openmeteo_stamp(stamp: str) -> float:
    """Parse an Open-Meteo hourly timestamp to UTC epoch seconds."""
    text = stamp.strip()
    try:
        return parse_utc_timestamp(text)
    except ValueError:
        # Open-Meteo UTC responses omit the Z; attach +00:00.
        return parse_utc_timestamp(text + "+00:00")


def build_met_rows(data: dict, variables=MET_VARS) -> dict:
    """Pure row builder: Open-Meteo JSON into {elevation_m, hourly, hourly_origin_epoch_s,."""
    if tuple(variables) != MET_VARS:
        raise RuntimeError(
            f"build_met_rows requires the canonical v1 variable set "
            f"{MET_VARS}, got {tuple(variables)}")
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    cols = [hourly.get(var, []) for var in variables]
    if not times or any(len(col) != len(times) for col in cols):
        raise RuntimeError("Open-Meteo: incomplete hourly table")
    precip_raw = hourly.get(PRECIP_VAR)
    precipitation_mm: list[float] | None
    if precip_raw is None:
        precipitation_mm = None
    elif len(precip_raw) != len(times):
        raise RuntimeError(
            "Open-Meteo: precipitation column length does not match hourly "
            "time axis")
    else:
        try:
            precipitation_mm = [finite("precipitation", v, minimum=0.0) for v in precip_raw]
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Open-Meteo: non-finite precipitation value: {exc}"
            ) from exc
    rows = []
    for i, stamp in enumerate(times):
        epoch = _parse_openmeteo_stamp(stamp)
        try:
            air, rh_pct, wind_kmh, sw, cloud = (
                finite(f"{MET_VARS[j]} row {i}", cols[j][i]) for j in range(5))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Open-Meteo: non-finite row {i} ({stamp}): {exc}") from exc
        rows.append([epoch, air, rh_pct / 100.0, wind_kmh / 3.6, sw,
                     cloud / 100.0])
    origin = rows[0][0] if rows else None
    return {"elevation_m": data.get("elevation"),
            "provider_grid_point": {"latitude": data.get("latitude"), "longitude": data.get("longitude")},
            "hourly": rows,
            "hourly_origin_epoch_s": origin,
            "precipitation_mm": precipitation_mm}


def _check_lat_lon_days(latitude: float, longitude: float, days: int) -> None:
    latitude = finite("latitude", latitude)
    longitude = finite("longitude", longitude)
    if not LAT_RANGE[0] <= latitude <= LAT_RANGE[1]:
        raise ValueError(
            f"latitude must be in {LAT_RANGE}, got {latitude}")
    if not LON_RANGE[0] <= longitude <= LON_RANGE[1]:
        raise ValueError(
            f"longitude must be in {LON_RANGE}, got {longitude}")
    if not isinstance(days, int) or isinstance(days, bool):
        raise ValueError(f"days must be an int, got {type(days).__name__}")
    if not DAYS_RANGE[0] <= days <= DAYS_RANGE[1]:
        raise ValueError(f"days must be in {DAYS_RANGE}, got {days}")


def _model_meta_from_response(data: dict) -> dict:
    return {k: data[k] for k in
            ("utc_offset_seconds", "timezone",
             "timezone_abbreviation", "generationtime_ms")
            if data.get(k) is not None}


def _hourly_vars_with_precip(variables) -> str:
    """Append the precipitation query var without extending the row width."""
    names = list(variables)
    if PRECIP_VAR not in names:
        names.append(PRECIP_VAR)
    return ",".join(names)


def fetch_met_forcing(latitude: float, longitude: float, days: int,
                      variables=MET_VARS) -> dict:
    """Fetch + build; returns {url, elevation_m, hourly, hourly_origin_epoch_s, precipitation_mm}."""
    _check_lat_lon_days(latitude, longitude, days)
    url = (f"{OPEN_METEO}?latitude={latitude}&longitude={longitude}"
           f"&hourly={_hourly_vars_with_precip(variables)}"
           f"&past_days={days}&forecast_days=1&timezone=UTC")
    try:
        data = _get_json(url)
    except Exception as exc:
        raise RuntimeError(f"met-fetch-failed: {OPEN_METEO}: {exc}") from exc
    return {"url": url, **build_met_rows(data, variables)}


def fetch_met_forcing_with_meta(latitude: float, longitude: float, days: int,
                                variables=MET_VARS) -> tuple[dict, dict]:
    """Variant that also returns Open-Meteo model-run metadata."""
    _check_lat_lon_days(latitude, longitude, days)
    url = (f"{OPEN_METEO}?latitude={latitude}&longitude={longitude}"
           f"&hourly={_hourly_vars_with_precip(variables)}"
           f"&past_days={days}&forecast_days=1&timezone=UTC")
    try:
        data = _get_json(url)
    except Exception as exc:
        raise RuntimeError(f"met-fetch-failed: {OPEN_METEO}: {exc}") from exc
    core = {"url": url, **build_met_rows(data, variables)}
    return core, _model_meta_from_response(data)


def fetch_met(latitude: float, longitude: float, days: int) -> dict:
    """Backcompat alias: same name/shape as the former embedded fetcher."""
    return fetch_met_forcing(latitude, longitude, days)
