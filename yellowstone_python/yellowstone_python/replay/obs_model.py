"""Observation model: map scientific state to expected measurements.

y = H(x) + e. H covers spatial mapping (station chainage), temporal
aggregation (model step to sensor interval), and datum reconciliation
(stage to elevation). e splits into measurement error and
representativeness error (point sensor against cross-section mean).
"""
from __future__ import annotations

import math
from typing import Any

from .hydraulics import score_paired_series

UNKNOWN = "unknown"

STATIONS = {
    "06036805": {
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
    "06036905": {
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
    return stage + float(info["datum_ft_navd88"])


def interval_average(times: list[float], values: list[float],
                     interval_s: float) -> tuple:
    """Bin-mean irregular samples onto interval centers from the first time."""
    if interval_s <= 0.0:
        raise ValueError("interval_s must be positive")
    if len(times) != len(values) or not times:
        raise ValueError("times and values must be nonempty and equal length")
    t0 = min(times)
    bins: dict = {}
    for t, v in zip(times, values):
        t = float(t)
        v = float(v)
        if not math.isfinite(t) or not math.isfinite(v):
            raise ValueError("times and values must be finite")
        bins.setdefault(int((t - t0) // interval_s), []).append(v)
    centers = [t0 + (k + 0.5) * interval_s for k in sorted(bins)]
    means = [math.fsum(bins[k]) / len(bins[k]) for k in sorted(bins)]
    return centers, means


def compare(modeled: list[float], observed: list[float],
            measurement_error: Any = 0.2,
            representativeness: Any = 0.6) -> dict:
    """Paired scores plus the recorded error decomposition.

    Defaults match the station table. Both values pass through unmodified.
    """
    scores = score_paired_series(modeled, observed)
    return {**scores,
            "measurement_error": measurement_error,
            "representativeness": representativeness}
