"""M10 study_mode: labeled A/B experiments, separate from the ordinary walk.

Sliders from Prompt 6: air temperature, shade/cloud, upstream discharge,
thermal source strength. Same parameter authority (M01/M02/M05/M06) drives
every response; geography frozen; reset reproduces the baseline hash;
side-by-side replay via two derived/ builds. Counterexample presets prove
a single variable never determines a whole habitat.

Usage:
    python -m yellowstone_python.study_mode --list
    python -m yellowstone_python.study_mode --write configs/experiments
    python -m yellowstone_python.study_mode --diff configs/baseline.yaml configs/experiments/hot_surge.yaml
"""
from __future__ import annotations

import argparse
import copy
import datetime
import math
from pathlib import Path

from .run_mode import normalize_run_mode

# Overrides are expressed as dotted paths into the build config. Only these
# EXACT keys may change — world geometry, routes, pools, placements are
# unreachable by construction (no key addresses them).
SCHEMA = {
    "clock_hour": (float, 0.0, 24.0, "exclusive"),
    "run_mode": (str, None, None),
    "weather.night_air_c": (float, -40.0, 40.0),
    "weather.day_warming_c": (float, 0.0, 30.0),
    "weather.wind_xz_mps": (list, None, None),
    "weather.gust_mps": (float, 0.0, 5.0),
    "weather.humidity": (float, 0.0, 1.0),
    "weather.cloud": (float, 0.0, 1.0),
    "weather.lag_hours": (float, 0.0, 6.0),
    "hydro.boundary_m3s": (float, 0.1, 60.0),
    "hydro.boundary_c": (float, -5.0, 40.0),
    "hydro.simulate_seconds": (float, 0.0, 86400.0),
    "insects.flowering_stage": (float, 0.0, 1.0),
    "fish.food": (float, 0.0, 1.0),
    "fish.cover": (float, 0.0, 1.0),
    "snow.season": (str, None, None),
    "snow.as_of_date": ("isodate", None, None),
    "snow.days": (int, 1, 365),
    "snow.precip_mm_d": (float, 0.0, 100.0),
    "snow.air_c_by_day": ("daylist", None, None),
}
ALLOWED_PREFIXES = ("weather.", "hydro.", "insects.", "fish.", "snow.", "clock_hour",
                     "run_mode")
# Lateral source records carry their own fields; only these may be set.
LATERAL_FIELDS = ("flow_m3s", "temperature_c")


def _prefix_allowed(dotted: str) -> bool:
    """True when the dotted key sits under an allowed override prefix."""
    for p in ALLOWED_PREFIXES:
        if p.endswith("."):
            if dotted.startswith(p):
                return True
        elif dotted == p or dotted.startswith(p + "."):
            return True
    return False


def _validate(dotted: str, value) -> None:
    if dotted not in SCHEMA:
        raise ValueError(f"preset key {dotted!r} is not an approved slider "
                         f"(choose from {sorted(SCHEMA)})")
    if not _prefix_allowed(dotted):
        raise ValueError(f"preset key {dotted!r} is outside the allowed "
                         f"prefixes {list(ALLOWED_PREFIXES)}")
    entry = SCHEMA[dotted]
    if isinstance(entry, tuple) and len(entry) == 4:
        typ, lo, hi, flag = entry
    else:
        typ, lo, hi = entry
        flag = None
    if typ == "isodate":
        if not isinstance(value, str):
            raise ValueError(f"{dotted!r} must be YYYY-MM-DD str")
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            raise ValueError(f"{dotted!r}={value!r} is not a valid "
                             f"YYYY-MM-DD date")
        return
    if typ == "daylist":
        if (not isinstance(value, (list, tuple)) or not (1 <= len(value) <= 366)
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and -60.0 <= v <= 45.0
                           for v in value)):
            raise ValueError(f"{dotted!r} must be 1–366 daily °C in [-60, 45]")
        return
    if typ is list:
        if (not isinstance(value, (list, tuple)) or len(value) != 2
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                           for v in value)
                or not all(math.isfinite(float(v)) for v in value)):
            raise ValueError(f"{dotted!r} must be a 2-vector of finite numbers")
        return
    if typ is str:
        if not isinstance(value, str):
            raise ValueError(f"{dotted!r} must be str")
        if dotted == "snow.season" and value not in ("summer", "autumn",
                                                     "winter", "spring"):
            raise ValueError(f"unknown season {value!r}")
        if dotted == "run_mode":
            normalize_run_mode(value)
            return
        return
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
        raise ValueError(f"{dotted!r}={value} outside [{lo}, {hi}{close}")


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
        "about": "Excelsior source ×2 within this model. Warmer mixing reach; trout relocate harder.",
        "units": "flow m3/s, temp C",
        "uncertainty": "illustrative multiplier, not a monitored event",
        "set": {},
        "patch_laterals": {"excelsior_mixing": [
            {"id": "excelsior_surge", "flow_m3s": 0.26,
             "temperature_c": 62.0, "status": "illustrative surge"}]},
    },
    "cold_snap": {
        "about": "Night air −6 °C, overcast. Insects collapse, birds perch.",
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
        "about": "COUNTEREXAMPLE (within this model): +6 °C air, same discharge. Trout barely move. "
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


def _set_path(cfg: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    node = cfg
    for p in parts[:-1]:
        if p not in node or not isinstance(node[p], dict):
            raise ValueError(f"config path {dotted!r} is missing or not a mapping")
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
        elif va != vb:
            out.append({"path": pa, "A": None if va is _MISSING else va,
                        "B": None if vb is _MISSING else vb,
                        "added_in_A": va is not _MISSING and vb is _MISSING,
                        "added_in_B": vb is not _MISSING and va is _MISSING})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--write", metavar="DIR")
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"))
    args = ap.parse_args()
    if args.list:
        for name, p in PRESETS.items():
            print(f"{name}: {p['about']}")
        return 0
    if args.write:
        import yaml
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        base = yaml.safe_load(
            (Path(__file__).resolve().parents[1] / "configs" / "baseline.yaml"
             ).read_text())
        d = Path(args.write)
        d.mkdir(parents=True, exist_ok=True)
        for name in PRESETS:
            (d / f"{name}.yaml").write_text(
                yaml.safe_dump(apply_preset(base, name), sort_keys=True))
            print("wrote", d / f"{name}.yaml")
        return 0
    if args.diff:
        import yaml
        a_raw = yaml.safe_load(Path(args.diff[0]).read_text())
        b_raw = yaml.safe_load(Path(args.diff[1]).read_text())
        if not isinstance(a_raw, dict) or not isinstance(b_raw, dict):
            raise ValueError("YAML inputs must be mappings")
        a, b = a_raw, b_raw
        for row in diff_configs(a, b):
            print(f"{row['path']}: {row['A']!r} → {row['B']!r}")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
