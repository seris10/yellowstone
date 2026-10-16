"""Frozen Firehole observation retrieval for reach-scale calibration."""
from __future__ import annotations

from yellowstone_python.river.obs_model import UPSTREAM_GAUGE, DOWNSTREAM_GAUGE, STATIONS

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USGS_IV = "https://waterservices.usgs.gov/nwis/iv/"
from yellowstone_python.observations.bundles import atomic_write_json, parse_utc_timestamp, validate_time_value_pairs

CHEM_PARAMETERS: dict[str, dict[str, Any]] = {
    "00095": {
        "name": "specific_conductance",
        "normalized_units": "uS/cm_at_25C",
        "value_range": (0.0, 50000.0),
    },
    "00300": {
        "name": "dissolved_oxygen",
        "normalized_units": "mg/L",
        "value_range": (0.0, 25.0),
    },
    "00400": {
        "name": "ph",
        "normalized_units": "std_units",
        "value_range": (0.0, 14.0),
    },
}
CHEM_BUNDLE_SCHEMA = "yellowstone.firehole_chem_obs.v1"

SITES = {
    UPSTREAM_GAUGE: {
        "name": "Firehole River at Old Faithful, YNP",
        "role": "upstream_boundary_above_midway",
        "latitude": STATIONS[UPSTREAM_GAUGE]["latitude"],
        "longitude": STATIONS[UPSTREAM_GAUGE]["longitude"],
    },
    DOWNSTREAM_GAUGE: {
        "name": "Firehole River near West Yellowstone MT",
        "role": "downstream_target_below_all_thermal_inflows",
        "latitude": STATIONS[DOWNSTREAM_GAUGE]["latitude"],
        "longitude": STATIONS[DOWNSTREAM_GAUGE]["longitude"],
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


def fetch_usgs_chem_series(site: str, days: int) -> dict:
    """Chemistry IV series (SC, DO, pH) for a USGS site as [epoch, value] pairs."""
    params = ",".join(CHEM_PARAMETERS.keys())
    url = (f"{USGS_IV}?sites={site}&parameterCd={params}"
           f"&period=P{days}D&format=json")
    data = _get_json(url)
    out: dict[str, list[list[float]]] = {
        spec["name"]: [] for spec in CHEM_PARAMETERS.values()
    }
    qualifiers: dict[str, list[list]] = {
        spec["name"]: [] for spec in CHEM_PARAMETERS.values()
    }
    stats: dict[str, dict] = {}
    status: dict[str, str] = {}
    for series in data.get("value", {}).get("timeSeries", []):
        codes = [c.get("value") for c in
                 series.get("variable", {}).get("variableCode", [])]
        values = series.get("values", [{}])[0].get("value", [])
        for code, spec in CHEM_PARAMETERS.items():
            if code not in codes:
                continue
            name = spec["name"]
            low, high = spec["value_range"]
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
                    value = float(text)
                except ValueError:
                    rejected += 1
                    continue
                if not low <= value <= high:
                    rejected += 1
                    continue
                try:
                    epoch = parse_utc_timestamp(row["dateTime"])
                    pairs.append([epoch, value])
                    series_quals.append(list(row.get("qualifiers") or []))
                except (ValueError, KeyError):
                    rejected += 1
                    continue
            order = sorted(range(len(pairs)), key=lambda i: pairs[i][0])
            pairs = [pairs[i] for i in order]
            series_quals = [series_quals[i] for i in order]
            if not out[name]:
                validated = validate_time_value_pairs(
                    pairs, name=f"{site}:{name}")
                out[name] = validated
                qualifiers[name] = series_quals[:len(validated)]
                stats[name] = {"rows_seen": seen,
                               "rows_retained": len(validated),
                               "rejected": rejected}
    for spec in CHEM_PARAMETERS.values():
        name = spec["name"]
        if not out[name]:
            status[name] = "not_collected_in_window"
            if name not in stats:
                stats[name] = {"rows_seen": 0, "rows_retained": 0,
                               "rejected": 0}
        else:
            status[name] = "retrieved"
    return {
        "url": url,
        "series": out,
        "qualifiers": qualifiers,
        "ingest_stats": stats,
        "series_status": status,
        "parameters": {
            code: {"code": code, **spec}
            for code, spec in CHEM_PARAMETERS.items()
        },
    }


def build_chem_bundle(sites_data: dict, days: int,
                      fetched_at_utc: str) -> dict:
    """Chemistry observation bundle shaped like firehole_obs with chem series."""
    return {
        "schema": CHEM_BUNDLE_SCHEMA,
        "status": "measured_remote_not_calibrated",
        "components": {
            "sites": {
                "kind": "observation",
                "status": "measured_remote_not_calibrated",
            },
        },
        "fetched_at_utc": fetched_at_utc,
        "window_days": days,
        "provenance": {
            "usgs": ("USGS Water Services IV, provisional and subject to "
                     "revision; chemistry parameter codes 00095, 00300 "
                     "and 00400"),
            "finding_policy": ("A parameter absent from the window is "
                               "a finding, not an error; the series "
                               "status label distinguishes "
                               "not_collected_in_window from retrieved."),
        },
        "sites": sites_data,
    }


def fetch_met(latitude: float, longitude: float, days: int) -> dict:
    """Fetch Open-Meteo forcing for the requested grid point."""
    from yellowstone_python.observations.met import fetch_met_forcing
    return fetch_met_forcing(latitude, longitude, days)
