"""Study-mode control schema and labeled scenario presets."""
from __future__ import annotations

import copy
import datetime
import math
from pathlib import Path

from yellowstone_python.registry.run_mode import normalize_run_mode
from yellowstone_python.common.units import TEMPERATURE_RANGE_C

# The schema table below lists the dotted paths a preset may set.
NUMBER = "number"
INTEGER = "integer"
STRING = "string"
WIND_VECTOR = "wind_xz_mps"
ISODATE = "isodate"
DAYLIST = "daylist"
PATCH_LATERALS = "patch_laterals"
SCHEMA = {
    "clock_hour": (NUMBER, 0.0, 24.0, "exclusive"),
    "run_mode": (STRING, None, None),
    "weather.night_air_c": (NUMBER, -40.0, 40.0),
    "weather.day_warming_c": (NUMBER, 0.0, 30.0),
    "weather.wind_xz_mps": (WIND_VECTOR, None, None),
    "weather.gust_mps": (NUMBER, 0.0, 30.0),
    "weather.precip_mm_h": (NUMBER, 0.0, 20.0),
    "weather.wind_speed_mps": (NUMBER, 0.0, 30.0),
    "weather.wind_direction_deg": (NUMBER, 0.0, 360.0),
    "weather.humidity": (NUMBER, 0.0, 1.0),
    "weather.cloud": (NUMBER, 0.0, 1.0),
    "weather.lag_hours": (NUMBER, 0.0, 6.0),
    "hydro.boundary_m3s": (NUMBER, 2.5, 8.0),
    "hydro.boundary_c": (NUMBER, *TEMPERATURE_RANGE_C),
    "hydro.simulate_seconds": (NUMBER, 0.0, 86400.0),
    # hydro.attach and hydro.tributaries are populated by apply_preset via patch_laterals.
    "hydro.attach": (PATCH_LATERALS, None, None),
    "hydro.tributaries": (PATCH_LATERALS, None, None),
    "insects.flowering_stage": (NUMBER, 0.0, 1.0),
    "fish.food": (NUMBER, 0.0, 1.0),
    "fish.cover": (NUMBER, 0.0, 1.0),
    "snow.season": (STRING, None, None),
    "snow.as_of_date": (ISODATE, None, None),
    "snow.days": (INTEGER, 1, 365),
    "snow.precip_mm_d": (NUMBER, 0.0, 100.0),
    "snow.air_c_by_day": (DAYLIST, None, None),
    "thermal.excelsior_enabled": ("boolean", None, None),
    "thermal.excelsior_c": (NUMBER, 0.0, 93.0),
    "aquatic.tributary_pockets": ("boolean", None, None),
    "aquatic.pocket_temperature_c": (NUMBER, 0.0, 30.0),
    "river.shade": ("shade", None, None),
    "grazing.bison_count": (INTEGER, 0, 100),
}
ALLOWED_PREFIXES = ("weather.", "hydro.", "insects.", "fish.", "snow.", "clock_hour",
                     "run_mode", "thermal.", "aquatic.", "river.", "grazing.")
# Lateral source records carry their own fields; only these may be set.
LATERAL_FIELDS = ("flow_m3s", "temperature_c")


CONTROL_GROUPS = {"weather": "Sky", "hydro": "River", "thermal": "Thermal sources",
                  "snow": "Time", "fish": "Ecology", "insects": "Ecology",
                  "aquatic": "Ecology", "river": "Interventions", "grazing": "Interventions"}
CONTROL_UNITS = {"clock_hour": "h", "weather.night_air_c": "C", "weather.day_warming_c": "C",
                 "weather.lag_hours": "h", "weather.gust_mps": "m/s",
                 "weather.wind_xz_mps": "m/s", "weather.wind_speed_mps": "m/s",
                 "weather.wind_direction_deg": "deg", "weather.precip_mm_h": "mm/h",
                 "hydro.boundary_m3s": "m3/s", "hydro.boundary_c": "C",
                 "hydro.simulate_seconds": "s", "thermal.excelsior_c": "C",
                 "aquatic.pocket_temperature_c": "C", "snow.precip_mm_d": "mm/day",
                 "snow.days": "days"}
for _key, _entry in tuple(SCHEMA.items()):
    _type, _lo, _hi = _entry[:3]
    _bound_source = "authored scenario envelope"
    if _key == "hydro.boundary_m3s":
        _bound_source = "fixed-depth geometry scenario envelope: baseline 8 and hot low flow 2.5 m3/s"
    elif _key == "hydro.boundary_c":
        _bound_source = "common.units.TEMPERATURE_RANGE_C ingestion envelope for ice-free river water"
    SCHEMA[_key] = {"type": _type, "min": _lo, "max": _hi,
                    "exclusive_max": len(_entry) == 4,
                    "unit": CONTROL_UNITS.get(_key, "fraction" if _type == NUMBER else ""),
                    "label": _key.split(".")[-1].replace("_", " "),
                    "group": CONTROL_GROUPS.get(_key.split(".")[0], "Time"),
                    "provenance": "authored", "bound_source": _bound_source}
SCHEMA["weather.wind_xz_mps"].update(component_min=-30.0, component_max=30.0)
for _key in ("weather.night_air_c", "weather.day_warming_c", "weather.lag_hours"):
    SCHEMA[_key]["group"] = "Air"
SCHEMA["weather.precip_mm_h"]["group"] = "Precipitation"
SCHEMA["clock_hour"].update(label="Display lighting hour", operation="display_only")
SCHEMA["snow.as_of_date"].update(label="Reset scenario date", operation="scenario_reset")


def control_schema(config: dict) -> list[dict]:
    """Return controls with bounds, provenance and the current config defaults."""
    rows = []
    for key, metadata in SCHEMA.items():
        value = config
        for part in key.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        rows.append({"key": key, **metadata, "default": value})
    return rows


def _prefix_allowed(dotted: str) -> bool:
    """True only for the reviewed control keys in the schema."""
    return dotted in SCHEMA


def _validate(dotted: str, value) -> None:
    if dotted not in SCHEMA:
        raise ValueError(f"preset key {dotted!r} is not an approved slider "
                         f"(choose from {sorted(SCHEMA)})")
    if not _prefix_allowed(dotted):
        raise ValueError(f"preset key {dotted!r} is outside the allowed "
                         f"prefixes {list(ALLOWED_PREFIXES)}")
    entry = SCHEMA[dotted]
    typ, lo, hi = entry["type"], entry["min"], entry["max"]
    flag = "exclusive" if entry["exclusive_max"] else None
    if typ == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{dotted} must be boolean")
        return
    if typ == "shade":
        if not isinstance(value, dict) or set(value) != {"cell_ids", "multiplier"}:
            raise ValueError("river.shade requires cell_ids and multiplier")
        if not isinstance(value["cell_ids"], list) or not value["cell_ids"] or not all(
                isinstance(cell, str) and cell for cell in value["cell_ids"]):
            raise ValueError("river.shade cell_ids must be a nonempty string list")
        from yellowstone_python.common.checks import fraction
        fraction("river.shade multiplier", value["multiplier"])
        return
    if typ == PATCH_LATERALS:
        raise ValueError(
            f"preset key {dotted!r} is managed by apply_preset through "
            f"patch_laterals and may not be set directly")
    if typ == ISODATE:
        if not isinstance(value, str):
            raise ValueError(f"{dotted!r} must be YYYY-MM-DD str")
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            raise ValueError(f"{dotted!r}={value!r} is not a valid "
                             f"YYYY-MM-DD date")
        return
    if typ == DAYLIST:
        if (not isinstance(value, (list, tuple)) or not (1 <= len(value) <= 366)
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and -60.0 <= v <= 45.0
                           for v in value)):
            raise ValueError(f"{dotted!r} must be 1 to 366 daily C in [-60, 45]")
        return
    if typ == WIND_VECTOR:
        if (not isinstance(value, (list, tuple)) or len(value) != 2
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                           for v in value)
                or not all(math.isfinite(float(v)) and -30 <= v <= 30 for v in value)):
            raise ValueError(f"{dotted!r} must be a 2-vector of finite numbers")
        return
    if typ == STRING:
        if not isinstance(value, str):
            raise ValueError(f"{dotted!r} must be str")
        if dotted == "snow.season" and value not in ("summer", "autumn",
                                                     "winter", "spring"):
            raise ValueError(f"unknown season {value!r}")
        if dotted == "run_mode":
            normalize_run_mode(value)
            return
        return
    if typ == INTEGER:
        if isinstance(value, bool):
            raise ValueError(f"{dotted!r} must not be boolean")
        if not isinstance(value, int):
            raise ValueError(f"{dotted!r} must be an integer, "
                             f"got {type(value).__name__}")
        number = int(value)
        below = lo is not None and number < lo
        above = (hi is not None and (number >= hi if flag == "exclusive"
                                     else number > hi))
        if below or above:
            close = ")" if flag == "exclusive" else "]"
            raise ValueError(
                f"{dotted!r}={value} outside [{lo}, {hi}{close}")
        return
    if typ == NUMBER:
        if isinstance(value, bool):
            raise ValueError(f"{dotted!r} must not be boolean")
        if not isinstance(value, (int, float)):
            raise ValueError(f"{dotted!r} must be a number, "
                             f"got {type(value).__name__}")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{dotted!r}={value} must be finite")
        below = lo is not None and number < lo
        above = (hi is not None and (number >= hi if flag == "exclusive"
                                     else number > hi))
        if below or above:
            close = ")" if flag == "exclusive" else "]"
            raise ValueError(
                f"{dotted!r}={value} outside [{lo}, {hi}{close}")
        return
    raise ValueError(
        f"preset key {dotted!r} has unknown schema type {typ!r}")


def _validate_lateral(rid: str, lateral: dict) -> dict:
    """Validate one lateral source record and return its tributary entry."""
    if not isinstance(lateral, dict):
        raise ValueError(f"lateral for {rid!r} must be an object")
    lat_id = lateral.get("id")
    if not isinstance(lat_id, str) or not lat_id.strip():
        raise ValueError(f"lateral for {rid!r} needs a nonempty id")
    entry = {}
    for field in LATERAL_FIELDS:
        if field not in lateral:
            raise ValueError(f"lateral {lat_id!r} is missing {field!r}")
        value = lateral[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"lateral {lat_id!r} {field} must be a number")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError(f"lateral {lat_id!r} {field} must be finite")
        if field == "flow_m3s" and value < 0.0:
            raise ValueError(f"lateral {lat_id!r} flow_m3s must be >= 0")
        entry[field] = value
    return entry


def preset_errors() -> list:
    """Validate every preset: slider keys, prefix rules, lateral records."""
    errors = []
    for name, preset in PRESETS.items():
        for dotted, value in preset.get("set", {}).items():
            try:
                _validate(dotted, value)
            except ValueError as exc:
                errors.append(f"preset {name}: {exc}")
        for rid, lats in preset.get("patch_laterals", {}).items():
            if not isinstance(lats, list) or not lats:
                errors.append(f"preset {name}: laterals for {rid!r} must "
                              "be a nonempty list")
                continue
            for lat in lats:
                try:
                    _validate_lateral(rid, lat)
                except ValueError as exc:
                    errors.append(f"preset {name}: {exc}")
    return errors

PRESETS = {
    "hot_surge": {
        "about": "Excelsior flow doubles; watch the warm pulse travel downstream.",
        "units": "flow m3/s, temp C",
        "uncertainty": "illustrative multiplier, not a monitored event",
        "set": {},
        "patch_laterals": {"excelsior_mixing": [
            {"id": "excelsior_surge", "flow_m3s": 0.26,
             "temperature_c": 62.0, "status": "illustrative surge"}]},
    },
    "cold_snap": {
        "about": "Night air -6 C and overcast; insect activity falls.",
        "units": "air C, cloud fraction",
        "uncertainty": "single-day scenario, not a forecast",
        "set": {"weather.night_air_c": -6.0, "weather.day_warming_c": 6.0,
                "weather.cloud": 0.85, "clock_hour": 10.0},
    },
    "low_flow": {
        "about": "Upstream Q halved: slower dilution, plume relatively stronger.",
        "units": "discharge m3/s",
        "uncertainty": "boundary scenario, not a gauge reading",
        "set": {"hydro.boundary_m3s": 4.0},
    },
    "warm_air_cold_water": {
        "about": "Air warms by 6 C with steady discharge; compare the delayed river response. "
                 "Short-term river response follows residence time and forcing, not air alone.",
        "units": "air C vs water C",
        "uncertainty": "illustrates decoupled drivers within this model; over longer periods surface exchange matters strongly",
        "set": {"weather.night_air_c": 13.0, "weather.day_warming_c": 15.0},
    },
    "winter_week": {
        "about": "Seven sub-zero days with precip: snow accumulates, thermal stays bare.",
        "units": "air C, mm/day",
        "uncertainty": "degree-day demo, not a snow survey",
        "set": {"snow.season": "winter", "snow.days": 7,
                "snow.precip_mm_d": 6.0,
                "snow.air_c_by_day": [-6.0] * 7},
    },
}

PRESETS["hot_low_flow"] = {
    "about": "Hot low flow: watch warm exposure suppress trout feeding.",
    "set": {"hydro.boundary_m3s": 2.5, "hydro.boundary_c": 26.0},
    "expected_response": "Mainstem cells warm above the chronic refuge threshold."}
PRESETS["tributary_cold_refuge"] = {
    "about": "Open authored Rabbit and Mallard Creek holding pockets.",
    "set": {"hydro.boundary_m3s": 2.5, "hydro.boundary_c": 26.0,
            "aquatic.tributary_pockets": True},
    "expected_response": "Trout can move upstream to the Mallard Creek pocket."}
PRESETS["measured_weather_day"] = {
    "about": "Play a frozen measured boundary and weather forcing day.", "set": {},
    "expected_response": "Compare modeled downstream temperature with the gauge."}


def _set_path(cfg: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    node = cfg
    for p in parts[:-1]:
        if p not in node:
            node[p] = {}
        if not isinstance(node[p], dict):
            raise ValueError(f"config path {dotted!r} is not a mapping")
        node = node[p]
    node[parts[-1]] = value


def apply_preset(baseline: dict, name: str,
                 run_mode: str = "scenario") -> dict:
    """Return a new config; baseline never mutated. Geography unreachable."""
    if name not in PRESETS:
        raise KeyError(f"unknown preset {name!r}; choose from {sorted(PRESETS)}")
    if not isinstance(baseline, dict):
        raise ValueError("baseline config must be a mapping")
    _validate("run_mode", run_mode)
    cfg = copy.deepcopy(baseline)
    for dotted, value in PRESETS[name].get("set", {}).items():
        _validate(dotted, value)
        _set_path(cfg, dotted, copy.deepcopy(value))
    if "patch_laterals" in PRESETS[name]:
        hydro = cfg.setdefault("hydro", {})
        attach = hydro.setdefault("attach", {})
        for rid, lats in PRESETS[name]["patch_laterals"].items():
            if not isinstance(lats, list) or not lats:
                raise ValueError(f"preset {name}: laterals for {rid!r} must "
                                 "be a nonempty list")
            trib = hydro.setdefault("tributaries", {})
            links = attach.setdefault(rid, [])
            if not isinstance(links, list):
                raise ValueError(f"preset {name}: hydro.attach.{rid} must "
                                 "be a list")
            for lat in lats:
                entry = _validate_lateral(rid, lat)
                existing = trib.get(lat["id"])
                if existing is not None and existing != entry:
                    raise ValueError(
                        f"preset {name}: tributary {lat['id']!r} already "
                        f"defined as {existing}; preset would overwrite it")
                trib[lat["id"]] = entry
                # Idempotent insert: applying twice must not double-count.
                if lat["id"] not in links:
                    links.append(lat["id"])
    cfg.setdefault("study", {})["preset"] = name
    cfg["study"]["about"] = PRESETS[name]["about"]
    cfg["run_mode"] = run_mode
    return cfg


def diff_configs(a: dict, b: dict, prefix: str = "") -> list:
    out = []
    _MISSING = object()
    for k in sorted(set(a) | set(b)):
        pa = f"{prefix}{k}"
        va = a.get(k, _MISSING)
        vb = b.get(k, _MISSING)
        if isinstance(va, dict) and isinstance(vb, dict):
            out += diff_configs(va, vb, pa + ".")
        elif isinstance(va, dict) and vb is _MISSING:
            out += diff_configs(va, {}, pa + ".")
        elif isinstance(vb, dict) and va is _MISSING:
            out += diff_configs({}, vb, pa + ".")
        elif va != vb:
            out.append({"path": pa, "A": None if va is _MISSING else va,
                        "B": None if vb is _MISSING else vb,
                        "added_in_A": va is not _MISSING and vb is _MISSING,
                        "added_in_B": vb is not _MISSING and va is _MISSING})
    return out


def main() -> int:
    """Run the study-mode command-line interface."""
    from yellowstone_python.cli.study_mode import main as cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
