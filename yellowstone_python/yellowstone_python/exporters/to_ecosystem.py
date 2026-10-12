"""M11 to_ecosystem: merge Python fragments into schema-v1 ecosystem.json."""
from __future__ import annotations

import copy
import json


def merge_fragments(baseline: dict, river_state: list | None = None,
                    weather: dict | None = None,
                    clock_hour: float | None = None) -> dict:
    """Return a new ecosystem dict; baseline never mutated.

    river_state: list of {id, temperature_c} (or full reach dicts).
    weather: {night_air_c, day_warming_c, wind_xz_mps, gust_mps, ...}.
    """
    out = copy.deepcopy(baseline)
    if river_state:
        by_id = {r["id"]: r for r in river_state}
        for r in out.get("river_reaches", []):
            if r["id"] in by_id:
                upd = by_id[r["id"]]
                for k in ("temperature_c", "volume_m3", "cooling_seconds",
                           "lateral_sources"):
                    if k in upd:
                        r[k] = copy.deepcopy(upd[k])
    if weather:
        out["weather"] = {**out.get("weather", {}), **copy.deepcopy(weather)}
        for k in ("humidity", "cloud"):
            if k in weather:
                out[k] = weather[k]
    if clock_hour is not None:
        out["clock_hour"] = float(clock_hour)
    return out


def validate_for_godot(doc: dict) -> list[str]:
    from ..common.validate import check_reach_chain
    errors = check_reach_chain(doc.get("river_reaches", []))
    if doc.get("schema_version") != 1:
        errors.append(f"schema_version must be 1 (got {doc.get('schema_version')!r}); ecosystem.gd reads the v1 layout")
    if not doc.get("patches"):
        errors.append("patches must be non-empty")
    if float(doc.get("boundary_m3s", 0)) <= 0:
        errors.append("boundary_m3s must be > 0")
    return errors
