"""to_ecosystem: merge Python fragments into schema-v1 ecosystem.json."""
from __future__ import annotations

import copy


REQUIRED_PATCH_KEYS = ("id", "biomass", "capacity", "moisture",
                       "growth_per_hour", "insect_resource",
                       "insect_recovery_per_hour")
REQUIRED_WEATHER_KEYS = ("night_air_c", "day_warming_c", "wind_xz_mps",
                         "gust_mps")
REQUIRED_SOURCE_KEYS = ("flow_m3s", "temperature_c")


def merge_fragments(baseline: dict, river_state: list | None = None,
                    weather: dict | None = None,
                    clock_hour: float | None = None,
                    boundary_m3s: float | None = None,
                    boundary_c: float | None = None) -> dict:
    """Return a deep-copied ecosystem dict with fragments merged in."""
    out = copy.deepcopy(baseline)
    if river_state:
        by_id = {r["id"]: r for r in river_state if "id" in r}
        for r in out.get("river_reaches", []):
            if r.get("id") in by_id:
                upd = by_id[r["id"]]
                for k in (
                        "temperature_c", "volume_m3",
                        "cooling_seconds", "lateral_sources"):
                    if k in upd:
                        r[k] = copy.deepcopy(upd[k])
    if weather:
        out["weather"] = {**out.get("weather", {}), **copy.deepcopy(weather)}
        for k in ("humidity", "cloud"):
            if k in weather:
                out[k] = weather[k]
    if clock_hour is not None:
        out["clock_hour"] = float(clock_hour)
    if boundary_m3s is not None:
        out["boundary_m3s"] = float(boundary_m3s)
    if boundary_c is not None:
        out["boundary_c"] = float(boundary_c)
    return out


def validate_for_godot(doc: dict) -> list[str]:
    """List contract violations ecosystem.json would hit in Godot."""
    from yellowstone_python.validation.contracts import check_reach_chain
    errors = check_reach_chain(doc.get("river_reaches", []))
    if doc.get("schema_version") != 1:
        errors.append(
            f"schema_version must be 1 (got {doc.get('schema_version')!r}); "
            f"ecosystem.gd reads the v1 layout")
    for reach in doc.get("river_reaches", []):
        rid = reach.get("id")
        if float(reach.get("cooling_seconds", 0.0)) <= 0.0:
            errors.append(
                f"reach {rid!r}: cooling_seconds must be > 0")
        for source in reach.get("lateral_sources", []) or []:
            for key in REQUIRED_SOURCE_KEYS:
                if key not in source:
                    errors.append(
                        f"reach {rid!r}: lateral source missing {key!r}")
    for patch in doc.get("patches", []):
        pid = patch.get("id")
        for key in REQUIRED_PATCH_KEYS:
            if key not in patch:
                errors.append(f"patch {pid!r}: missing {key!r}")
    weather = doc.get("weather", {})
    if not isinstance(weather, dict):
        errors.append("weather must be a mapping")
    else:
        for key in REQUIRED_WEATHER_KEYS:
            if key not in weather:
                errors.append(f"weather missing {key!r}")
        wind = weather.get("wind_xz_mps", [])
        if not (isinstance(wind, (list, tuple)) and len(wind) == 2):
            errors.append("weather.wind_xz_mps must be a 2-array")
    for key in ("humidity", "cloud", "boundary_c"):
        if key not in doc:
            errors.append(f"missing top-level {key!r}")
    if float(doc.get("boundary_m3s", 0)) <= 0:
        errors.append("boundary_m3s must be > 0")
    if not doc.get("patches"):
        errors.append("patches must be non-empty")
    return errors
