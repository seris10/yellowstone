"""Observation model y = H(x) + e: spatial mapping, temporal aggregation, datum reconciliation."""
from __future__ import annotations

UPSTREAM_GAUGE = "06036805"
DOWNSTREAM_GAUGE = "06036905"

import math
from typing import Any


UNKNOWN = "unknown"

STATIONS = {
    # Station metadata is provenance-critical and immutable; copy for exploration.
    UPSTREAM_GAUGE: {
        "latitude": 44.459333, "longitude": -110.822272,
        "name": "Firehole River at Old Faithful",
        "role": "upstream_boundary_above_midway",
        "datum_ft_navd88": 7339.88,
        "datum_note": "station metadata",
        "drainage_sq_mi": 39.5,
        "drainage_note": "station metadata",
        "temp_record_start": "2011-10-01",
        "discharge_record_start": "2007-10-01",
        "interval_s": 900.0,
        "provisional": True,
        "temp_accuracy_c": 0.2,
        "temp_accuracy_note": "USGS NFM A6.1 field standard against traceable sensor",
        "representativeness_c": 0.6,
        "representativeness_note": "USGS tolerance interval for point probe against section mean",
        "discharge_grade": "unknown",
        "discharge_note": "Sauer and Meyer component error method; station grade unrecorded",
    },
    DOWNSTREAM_GAUGE: {
        "latitude": 44.620183, "longitude": -110.863503,
        "name": "Firehole River near West Yellowstone",
        "role": "downstream_target_below_all_thermal_inflows",
        "datum_ft_navd88": 7056.08,
        "datum_note": "current GNSS survey +-0.13 ft; older topo record 7050 ft +-10 ft",
        "datum_superseded_ft": 7050.0,
        "drainage_sq_mi": 261.0,
        "drainage_note": "secondary aggregator; confirm against USGS record",
        "temp_record_start": "2011-10-01",
        "discharge_record_start": "1994-10-01",
        "stage_record_start": "2007-10-01",
        "interval_s": 900.0,
        "provisional": True,
        "temp_accuracy_c": 0.2,
        "temp_accuracy_note": "USGS NFM A6.1 field standard against traceable sensor",
        "representativeness_c": 0.6,
        "representativeness_note": "USGS tolerance interval for point probe against section mean",
        "discharge_grade": "unknown",
        "discharge_note": "Sauer and Meyer component error method; station grade unrecorded",
    },
}


def stage_to_elevation_ft_navd88(stage_ft: float, station: str) -> float:
    """Gauge stage to absolute elevation with the current datum."""
    info = STATIONS.get(station)
    if info is None:
        raise KeyError(f"unknown station {station!r}")
    stage = float(stage_ft)
    if not math.isfinite(stage):
        raise ValueError("stage_ft must be finite")
    if stage < 0.0:
        raise ValueError("stage_ft must be >= 0")
    return stage + float(info["datum_ft_navd88"])


def interval_average(times: list[float], values: list[float],
                     interval_s: float) -> tuple[list[float], list[float]]:
    """Bin-mean irregular samples onto left-edge labels from the first time."""
    if interval_s <= 0.0 or not math.isfinite(interval_s):
        raise ValueError("interval_s must be a positive finite number")
    if len(times) != len(values) or not times:
        raise ValueError("times and values must be nonempty and equal length")
    pairs: list[tuple[float, float]] = []
    for t, v in zip(times, values):
        tf = float(t)
        vf = float(v)
        if not math.isfinite(tf) or not math.isfinite(vf):
            raise ValueError("times and values must be finite")
        pairs.append((tf, vf))
    t0 = min(t for t, _ in pairs)
    bins: dict[int, list[float]] = {}
    for t, v in pairs:
        bins.setdefault(int((t - t0) // interval_s), []).append(v)
    if not bins:
        return [], []
    k_lo, k_hi = min(bins), max(bins)
    lefts = [t0 + k * interval_s for k in range(k_lo, k_hi + 1)]
    means: list[float] = [
        math.fsum(bins[k]) / len(bins[k]) if k in bins else math.nan
        for k in range(k_lo, k_hi + 1)
    ]
    return lefts, means


def _uncertainty(name: str, value) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and >= 0")
    return value


def compare(modeled: list[float], observed: list[float],
            measurement_error: Any = 0.2,
            representativeness: Any = 0.6) -> dict:
    """Paired scores plus the recorded error decomposition."""
    if len(modeled) != len(observed):
        raise ValueError("modeled and observed must have equal length")
    if not modeled:
        raise ValueError("modeled and observed must be nonempty")
    measurement_error = _uncertainty("measurement_error", measurement_error)
    representativeness = _uncertainty("representativeness", representativeness)
    from yellowstone_python.river.hydraulics import score_paired_series
    scores = score_paired_series(modeled, observed)
    return {**scores,
            "measurement_error": measurement_error,
            "representativeness": representativeness,
            "combined_error": math.hypot(measurement_error, representativeness)}
