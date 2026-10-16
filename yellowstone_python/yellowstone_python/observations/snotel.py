"""Frozen SNOTEL observations for snow and soil-water validation."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from yellowstone_python.observations.bundles import atomic_write_json

AWDB_DATA = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
USER_AGENT = "yellowstone-python/0.1 (research calibration fetch)"

ELEMENTS = ("WTEQ", "PRCP", "SNWD", "TAVG", "TMAX", "TMIN")

EXPECTED_UNITS = {
    "WTEQ": "in", "PRCP": "in", "SNWD": "in",
    "TAVG": "degF", "TMAX": "degF", "TMIN": "degF",
}

ELEMENT_SEMANTICS = {
    "WTEQ": "state",
    "SNWD": "state",
    "PRCP": "accumulation_increment",
    "TAVG": "state",
    "TMAX": "state",
    "TMIN": "state",
}

MAX_WINDOW_DAYS = 400

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


def validate_date_window(begin: str, end: str) -> tuple[date, date]:
    try:
        begin_date = date.fromisoformat(begin)
        end_date = date.fromisoformat(end)
    except ValueError as exc:
        raise ValueError(f"invalid date in window: {exc}") from exc
    if end_date < begin_date:
        raise ValueError("end precedes begin")
    if (end_date - begin_date).days > MAX_WINDOW_DAYS:
        raise ValueError(
            f"window over {MAX_WINDOW_DAYS} days; split the fetch")
    return begin_date, end_date


def _coerce_awdb_value(code: str, raw: object) -> float | None:
    """Return a finite float or None; rejects strings and sentinel values."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if value != value:  # NaN check without math import duplication
        return None
    if value <= -999.0 or value >= 9999.0:
        return None
    if code in ("WTEQ", "SNWD") and value < 0.0:
        return None
    return value


def fetch_site_daily(triplet: str, begin: str, end: str) -> dict:
    """Daily element series for one station triplet over [begin, end], with units, coverage and rejections."""
    begin_date, end_date = validate_date_window(begin, end)
    begin_iso = begin_date.isoformat()
    end_iso = end_date.isoformat()
    params = urllib.parse.urlencode({
        "stationTriplets": triplet,
        "elements": ",".join(ELEMENTS),
        "duration": "DAILY",
        "beginDate": begin_iso,
        "endDate": end_iso,
    })
    url = f"{AWDB_DATA}?{params}"
    data = _get_json(url)
    if len(data) != 1 or data[0].get("stationTriplet") != triplet:
        raise RuntimeError(f"AWDB: unexpected station envelope for {triplet}")
    days: dict[str, dict] = {}
    units: dict[str, str] = {}
    unexpected: dict[str, str] = {}
    rejections: dict[str, dict[str, int]] = {
        code: {"malformed_date": 0, "non_numeric": 0, "sentinel": 0}
        for code in ELEMENTS
    }
    for block in data[0].get("data", []):
        el = block.get("stationElement", {})
        code = el.get("elementCode")
        if code not in ELEMENTS:
            continue
        stored = el.get("storedUnitCode", "unknown")
        units[code] = stored
        if EXPECTED_UNITS.get(code) and stored != EXPECTED_UNITS[code]:
            unexpected[code] = stored
        for row in block.get("values", []):
            day = row.get("date")
            if not isinstance(day, str) or not day:
                rejections[code]["malformed_date"] += 1
                continue
            try:
                date.fromisoformat(day)
            except ValueError:
                rejections[code]["malformed_date"] += 1
                continue
            raw = row.get("value")
            coerced = _coerce_awdb_value(code, raw)
            if coerced is None and raw is not None:
                if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    rejections[code]["sentinel"] += 1
                else:
                    rejections[code]["non_numeric"] += 1
            days.setdefault(day, {})[code] = coerced
    current = begin_date
    while current <= end_date:
        iso = current.isoformat()
        days.setdefault(iso, {})
        for code in ELEMENTS:
            days[iso].setdefault(code, None)
        current = date.fromordinal(current.toordinal() + 1)
    coverage = {code: sum(1 for d in days.values() if d[code] is not None)
                for code in ELEMENTS}
    if not any(coverage.values()):
        raise RuntimeError(f"AWDB: no non-null daily values for {triplet}")
    return {"url": url, "days": days, "units": units,
            "coverage": coverage,
            "rejections": rejections,
            "unexpected_units": unexpected}
