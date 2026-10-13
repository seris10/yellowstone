"""Build pipeline: runs all modules and writes derived artifacts."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any

from .common.provenance import (CONTRACT_VERSION, WORLD_ID, build_id,
                                 default_world_root, resolve_code_rev,
                                 sha256_file, sha256_json, write_sidecar)
from .validation.checks import (HYDRO_HEAT_LEDGER_TOL_J,
                                HYDRO_WATER_LEDGER_TOL_M3,
                                REPLAY_HEAT_RELATIVE_TOLERANCE,
                                REPLAY_WATER_RELATIVE_TOLERANCE,
                                SNOW_STORAGE_TOL_MM)
from .exporters.to_ecosystem import merge_fragments, validate_for_godot
from .run_mode import (normalize_run_mode, prescribed_quantities,
                       predicted_quantities)
from .hydro_thermal import (DEFAULT_TRIBUTARIES, plume_field,
                              render_plume_png, run_simulation)
from .microclimate import air_temp, prevailing_direction, trace
from .overland_flow import run_overland
from .replay.river_world import build_mapped_replay
from .time_utils import epoch_unix_for_local, parse_simulation_start

PKG_ROOT = Path(__file__).resolve().parents[1]

# Authored topology: named lookups fail loudly (never silent wrong defaults).
REACH_EXCELSIOR = "excelsior_mixing"
REACH_BRIDGE = "bridge_downstream"
RIVER_FIREHOLE = "river_5856_0"
POOL_GRAND = "pool_1034_0"
PATCH_RIPARIAN = "bridge_riparian"
BISON_DEMO = "bison_01"


def _find(items: list, key: str, value: str, what: str) -> dict:
    for it in items:
        if isinstance(it, dict) and it.get(key) == value:
            return it
    have = [str(it.get(key)) for it in items if isinstance(it, dict)][:12]
    raise ValueError(f"{what} {value!r} not found; have {have}")


def load_config(path: Path) -> dict:
    import yaml
    cfg = yaml.safe_load(Path(path).read_text())
    if cfg is None or not isinstance(cfg, dict):
        raise ValueError("configuration root must be a mapping")
    return cfg


def _fraction(name: str, value, lo: float = 0.0, hi: float = 1.0) -> float:
    v = _finite_number(name, value)
    if not (lo <= v <= hi):
        raise ValueError(f"config {name}={value} outside [{lo}, {hi}]")
    return v


def _finite_number(name: str, value) -> float:
    """Finite float that is not a boolean."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must not be boolean")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _nonnegative_number(name: str, value) -> float:
    result = _finite_number(name, value)
    if result < 0:
        raise ValueError(f"{name} must be >= 0")
    return result


def _nonnegative_int(name: str, value) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must not be boolean")
    if not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def _positive_finite(name, value):
    result = _finite_number(name, value)
    if result <= 0:
        raise ValueError(f"{name} must be > 0")
    return result


def normalized_config(cfg: dict) -> dict:
    """Non-mutating normalization used for hashing and simulation."""
    result = copy.deepcopy(cfg)
    result["run_mode"] = normalize_run_mode(result.get("run_mode"))
    result.setdefault("world_root", str(default_world_root()))
    return result


def _nonnegative_finite(name, value):
    result = _finite_number(name, value)
    if result < 0:
        raise ValueError(f"{name} must be >= 0")
    return result


def validate_config(cfg: dict) -> dict:
    """Reject nonphysical config before any simulation. Returns a normalized copy.
    Numeric fields pass through _finite_number so NaN, inf, bool, and string values raise."""
    normalized = normalized_config(cfg)
    if not Path(normalized.get("world_root", "")).is_dir():
        raise ValueError(
            f"world_root {normalized.get('world_root')!r} is not a directory")
    if "clock_hour" in normalized:
        h = _finite_number("clock_hour", normalized["clock_hour"])
        if not (0.0 <= h < 24.0):
            raise ValueError(f"clock_hour {h} outside [0, 24)")
    # Absent clock_hour falls back to the system clock at simulate time via resolve_game_clock.
    hydro = normalized.get("hydro", {}) or {}
    from .common.hydro_units import validate_hydro_units
    validate_hydro_units(hydro)
    _positive_finite("hydro.boundary_m3s", hydro.get("boundary_m3s", 8.0))
    bc = _finite_number("hydro.boundary_c", hydro.get("boundary_c", 17.5))
    if not (-10.0 <= bc <= 45.0):
        raise ValueError("hydro.boundary_c outside [-10, 45] C")
    _nonnegative_finite("hydro.simulate_seconds",
                        hydro.get("simulate_seconds", 600.0))
    weather = normalized.get("weather", {}) or {}
    for key in ("humidity", "cloud"):
        if key in weather:
            _fraction(f"weather.{key}", weather[key])
    if "gust_mps" in weather:
        _nonnegative_finite("weather.gust_mps", weather["gust_mps"])
    if "lag_hours" in weather:
        _finite_number("weather.lag_hours", weather["lag_hours"])
    if "night_air_c" in weather:
        _finite_number("weather.night_air_c", weather["night_air_c"])
    if "day_warming_c" in weather:
        _finite_number("weather.day_warming_c", weather["day_warming_c"])
    w = weather.get("wind_xz_mps", [1.8, 0.6])
    if not isinstance(w, (list, tuple)) or len(w) != 2:
        raise ValueError("weather.wind_xz_mps must be a 2-vector of numbers")
    _finite_number("weather.wind_xz_mps[0]", w[0])
    _finite_number("weather.wind_xz_mps[1]", w[1])
    _fraction("insects.flowering_stage",
              normalized.get("insects", {}).get("flowering_stage", 0.6))
    for key in ("food", "cover"):
        if key in normalized.get("fish", {}):
            _fraction(f"fish.{key}", normalized["fish"][key])
    if "species" in normalized.get("fish", {}):
        from .fish import THERMAL_SPECIES
        if normalized["fish"]["species"] not in THERMAL_SPECIES:
            raise ValueError(
                f"fish.species {normalized['fish']['species']!r} unknown; "
                f"have {sorted(THERMAL_SPECIES)}")
    snow = normalized.get("snow", {}) or {}
    _nonnegative_int("snow.days", int(snow.get("days", 30)))
    _nonnegative_finite("snow.precip_mm_d", snow.get("precip_mm_d", 2.0))
    if snow.get("season") is not None and snow["season"] not in (
            "summer", "autumn", "winter", "spring"):
        raise ValueError(f"unknown snow.season {snow['season']!r}")
    if snow.get("as_of_date") is not None:
        import datetime
        try:
            datetime.date.fromisoformat(str(snow["as_of_date"]))
        except ValueError:
            raise ValueError(f"snow.as_of_date {snow['as_of_date']!r} "
                             f"is not YYYY-MM-DD")
    rcfg = normalized.get("replay", {}) or {}
    if "cross_sections_file" in rcfg and not isinstance(
            rcfg["cross_sections_file"], str):
        raise ValueError("replay.cross_sections_file must be a string path")
    _positive_finite("replay.duration_s", rcfg.get("duration_s", 7200.0))
    _positive_finite("replay.max_cell_m", rcfg.get("max_cell_m", 20.0))
    _positive_finite("replay.depth_m", rcfg.get("depth_m", 1.1))
    _nonnegative_finite("replay.dispersion_m2_s",
                        rcfg.get("dispersion_m2_s", 1.0))
    _nonnegative_finite("replay.exchange_w_m2_k",
                        rcfg.get("exchange_w_m2_k", 12.0))
    _positive_finite("replay.dt_s", rcfg.get("dt_s", 2.0))
    _positive_finite("replay.sample_s", rcfg.get("sample_s", 10.0))
    hyd = rcfg.get("hydraulics", {})
    if not isinstance(hyd, dict):
        raise ValueError("replay.hydraulics must be a mapping")
    _nonnegative_finite("replay.hydraulics.bank_slope_zh",
                        hyd.get("bank_slope_zh", 1.5))
    _positive_finite("replay.hydraulics.manning_n",
                     hyd.get("manning_n", 0.035))
    olfg = normalized.get("overland", {}) or {}
    if olfg.get("enabled", False):
        _nonnegative_finite("overland.rain_mm_h", olfg.get("rain_mm_h", 0.0))
        _positive_finite("overland.dt_s", olfg.get("dt_s", 60.0))
        _nonnegative_finite("overland.sim_s", olfg.get("sim_s", 0.0))
        grid_val = int(olfg.get("grid", 256))
        if grid_val <= 0:
            raise ValueError("overland.grid must be > 0")
        _positive_finite("overland.cell_m", olfg.get("cell_m", 8.0))
    catch = (normalized.get("hydro", {}) or {}).get("catchment", {}) or {}
    if catch.get("area_m2") is not None:
        _positive_finite("hydro.catchment.area_m2", catch["area_m2"])
    sim = normalized.get("simulation", {}) or {}
    if "start_epoch_unix" in sim:
        _finite_number("simulation.start_epoch_unix", sim["start_epoch_unix"])
    if "utc_offset_hours" in sim:
        _finite_number("simulation.utc_offset_hours",
                       sim["utc_offset_hours"])
    if "wind_seed" in normalized:
        _nonnegative_int("wind_seed", int(normalized["wind_seed"]))
    # Measured-mode builds require an explicit simulation start; no system-clock date fallback.
    if normalized["run_mode"] in ("hindcast", "observed_replay"):
        has_explicit = (
            "start_epoch_unix" in sim or "start_utc" in sim
            or snow.get("as_of_date") is not None)
        if not has_explicit:
            raise ValueError(
                "run_mode "
                f"{normalized['run_mode']!r} requires an explicit "
                "simulation start: set simulation.start_epoch_unix, "
                "simulation.start_utc, or snow.as_of_date")
    return normalized


CANOPY_FALLBACK = 0.6


def _canopy_from_census(center_xz: tuple, radius_m: float,
                        census_path: Path) -> tuple[float, str]:
    """Canopy fraction in a circle from census.json crowns, or the fallback.
    Returns (canopy_in_[0,1], source_label); crown-area sum is an upper bound since overlaps are not deducted."""
    try:
        doc = json.loads(census_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CANOPY_FALLBACK, "illustrative_fallback_no_census"
    trees = doc.get("trees") if isinstance(doc, dict) else None
    if not isinstance(trees, list) or not trees:
        return CANOPY_FALLBACK, "illustrative_fallback_empty_census"
    cx, cz = float(center_xz[0]), float(center_xz[1])
    r = float(radius_m)
    if not math.isfinite(r) or r <= 0.0:
        return CANOPY_FALLBACK, "illustrative_fallback_bad_radius"
    r2 = r * r
    area_circle = math.pi * r2
    area_crowns = 0.0
    for t in trees:
        if not isinstance(t, dict):
            continue
        try:
            x = float(t["x"])
            z = float(t["z"])
            cr = float(t.get("crown_r_m", 0.0))
        except (KeyError, TypeError, ValueError):
            continue
        if not (math.isfinite(x) and math.isfinite(z) and math.isfinite(cr)):
            continue
        if cr <= 0.0:
            continue
        if (x - cx) * (x - cx) + (z - cz) * (z - cz) <= (r + cr) * (r + cr):
            area_crowns += math.pi * cr * cr
    fraction = min(1.0, area_crowns / area_circle)
    return fraction, "census_json_crown_area_sum"


def _hash_package_sources() -> tuple[object, str]:
    """SHA-256 of package .py files plus tools, Godot world scripts, and shaders.
    Returns (hash, source) where source names the lister (fd or rglob) and the roots included."""
    import hashlib
    import subprocess
    code_hash = hashlib.sha256()
    world_root = Path(_default_world_root_for_hash())
    roots: list[tuple[Path, tuple[str, ...]]] = [
        (PKG_ROOT / "yellowstone_python", (".py",)),
        (PKG_ROOT / "tools", (".py",)),
        (world_root / "scripts", (".gd",)),
        (world_root / "shaders", (".gdshader", ".gdshaderinc")),
    ]
    sources: list[str] = []
    for root, suffixes in roots:
        if not root.is_dir():
            continue
        tracked: list[Path] = []
        source_tag = "rglob"
        try:
            fd_args = ["fd", "-u", "-0", "-t", "f"]
            for suffix in suffixes:
                fd_args += ["-e", suffix.lstrip(".")]
            fd_args += [".", str(root)]
            proc = subprocess.run(fd_args, capture_output=True, timeout=10,
                                  check=False)
            if proc.returncode == 0 and proc.stdout:
                rows = proc.stdout.split(b"\x00")
                tracked = [Path(r.decode("utf-8")) for r in rows if r]
                source_tag = "fd"
        except (OSError, subprocess.TimeoutExpired):
            tracked = []
        if not tracked:
            for suffix in suffixes:
                tracked.extend(root.rglob(f"*{suffix}"))  # fd-ok
            source_tag = "rglob"
        for p in sorted(tracked):
            if p.is_file():
                # Prefix every file's relative path so moves and renames affect the hash.
                code_hash.update(str(p.relative_to(root.parent)).encode())
                code_hash.update(b"\x00")
                code_hash.update(p.read_bytes())
        sources.append(f"{root.name}:{source_tag}")
    return code_hash, "+".join(sources) if sources else "empty"


def _default_world_root_for_hash() -> Path:
    """World root used by the code hash; honors $YELLOWSTONE_WORLD."""
    import os as _os
    return Path(_os.environ.get("YELLOWSTONE_WORLD")
                or (PKG_ROOT.parent / WORLD_ID))


def _check_met_window_covers_replay(hourly, start_epoch_s, duration_s) -> dict:
    """Report whether met_bundle.hourly rows span [start_epoch_s, start_epoch_s + duration_s]."""
    if not isinstance(hourly, list) or not hourly:
        return {"status": "no_hourly_rows"}
    epochs: list[float] = []
    for row in hourly:
        if isinstance(row, (list, tuple)) and row:
            try:
                epochs.append(float(row[0]))
            except (TypeError, ValueError):
                continue
    if not epochs:
        return {"status": "no_hourly_epochs"}
    start = float(start_epoch_s) if start_epoch_s is not None else None
    end = start + float(duration_s) if start is not None else None
    bundle_min = min(epochs)
    bundle_max = max(epochs)
    if start is None:
        return {"status": "no_simulation_start",
                "bundle_min_epoch": bundle_min,
                "bundle_max_epoch": bundle_max}
    if bundle_min <= start and bundle_max >= end:
        return {"status": "covers",
                "simulation_start_epoch": start,
                "simulation_end_epoch": end,
                "bundle_min_epoch": bundle_min,
                "bundle_max_epoch": bundle_max}
    return {"status": "window_not_covered",
            "simulation_start_epoch": start,
            "simulation_end_epoch": end,
            "bundle_min_epoch": bundle_min,
            "bundle_max_epoch": bundle_max}


def _grazers_input_from_consumed(prev_consumed_by_patch: dict,
                                 dt_s: float) -> dict | None:
    """Convert a previous step's consumed_by_patch into a grazers input for patch_step.
    Empty input returns None so patch_step applies no demand."""
    if not prev_consumed_by_patch or dt_s <= 0.0:
        return None
    out: dict = {}
    for pid, eaten in prev_consumed_by_patch.items():
        try:
            rate = float(eaten) / float(dt_s)
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if rate <= 0.0 or not math.isfinite(rate):
            continue
        out[f"grazing_feedback_{pid}"] = {
            "patch_id": pid, "active": True,
            "rate_per_second": rate,
            "source": "previous_step_consumed_by_patch"}
    return out or None


def _compute_overland_field(world_root, cfg, olfg, scfg, met_bundle,
                            run_mode_norm, sim_s):
    """Run the overland solver using the configured rain source, or return a disabled stub."""
    if not olfg.get("enabled", False):
        return ({"schema": "yellowstone.overland_flow.v1",
                 "enabled": False,
                 "overland_flow_role": "diagnostic_not_wired_to_river",
                 "surface_runoff": {"nonzero_cells": 0,
                                    "max_depth_m": 0.0,
                                    "outflow_m3": 0.0,
                                    "carries_runoff_signal": False,
                                    "note": "module disabled; no field "
                                            "computed"},
                 "provenance": "overland disabled; set overland.enabled "
                               "true to compute it"},
                "disabled")
    bundle_precip = (met_bundle.get("precipitation_mm")
                     if isinstance(met_bundle, dict) else None)
    bundle_precip_ok = (isinstance(bundle_precip, list)
                        and len(bundle_precip) > 0)
    if "rain_mm_h" in olfg:
        rain_mm_h = float(olfg["rain_mm_h"])
        rain_source = "overland.rain_mm_h"
    elif (run_mode_norm in ("hindcast", "observed_replay")
          and bundle_precip_ok):
        samples = []
        for value in bundle_precip:
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(v) and v >= 0.0:
                samples.append(v)
        if not samples:
            raise ValueError(
                "overland rain source: met_bundle.precipitation_mm "
                "has no finite non-negative samples; set "
                "overland.rain_mm_h explicitly")
        rain_mm_h = sum(samples) / len(samples)
        rain_source = ("met_bundle.precipitation_mm mean over "
                       f"{len(samples)} hourly samples")
    elif run_mode_norm in ("hindcast", "observed_replay"):
        raise ValueError(
            "overland.rain_mm_h is required in run_mode "
            f"{run_mode_norm!r}; neither an explicit value nor a "
            "met_bundle.precipitation_mm array was available")
    else:
        precip_day = float(scfg.get("precip_mm_d", 2.0))
        rain_mm_h = precip_day / 24.0
        rain_source = ("snow.precip_mm_d converted to mm/h "
                       "(illustrative only)")
    field = run_overland(
        world_root,
        rain_mm_h=rain_mm_h,
        soil=str(olfg.get("soil", "sandy_loam")),
        dt_s=float(olfg.get("dt_s", 60.0)),
        sim_s=float(olfg.get("sim_s", sim_s)),
        grid=int(olfg.get("grid", 256)),
        cell_m=float(olfg.get("cell_m", 8.0)))
    field["rainfall_source"] = rain_source
    return field, rain_source


def _overland_runoff_to_boundary(overland_field, hcfg, sim_s) -> tuple:
    """Convert the overland outlet volume into a mean boundary discharge in m3/s.
    Returns (rate_m3_s, report); rate_m3_s is 0 when no outflow was produced or sim_s is nonpositive."""
    surface = overland_field.get("surface_runoff", {})
    outflow_m3 = float(surface.get("outflow_m3", 0.0) or 0.0)
    carries = bool(surface.get("carries_runoff_signal", False))
    if sim_s <= 0.0 or not math.isfinite(outflow_m3) or outflow_m3 <= 0.0:
        return (0.0, {"status": "no_outflow",
                      "outflow_m3": outflow_m3,
                      "mean_rate_m3_s": 0.0,
                      "coupling": ("partial: contributing area not "
                                   "delineated; wire outlet runoff only "
                                   "when open_edges deliver outflow")})
    # Mean rate over the sim window as a conservative scalar increment.
    rate = outflow_m3 / float(sim_s)
    status = "wired_mean_rate" if carries else "wired_zero_signal"
    return (rate, {"status": status,
                   "outflow_m3": outflow_m3,
                   "window_s": float(sim_s),
                   "mean_rate_m3_s": rate,
                   "contributing_area_m2": (hcfg.get("catchment", {}) or {})
                                             .get("area_m2"),
                   "coupling": ("partial: outlet volume divided by sim "
                                "window; contributing area not delineated "
                                "from terrain")})


def _per_point_hydraulics_from_cells(fh_chainage, fh_offset,
                                     fh_landscape_cells):
    """Nearest-cell velocity_m_s and depth_m per river_point; returns (velocities, depths) or (None, None)."""
    if not fh_landscape_cells or not fh_chainage:
        return (None, None)
    cell_s = []
    cell_v = []
    cell_d = []
    for c in fh_landscape_cells:
        s = c.get("s_m")
        v = c.get("velocity_m_s")
        d = c.get("depth_m")
        if s is None or v is None or d is None:
            continue
        try:
            cell_s.append(float(s))
            cell_v.append(max(0.0, float(v)))
            cell_d.append(max(1e-6, float(d)))
        except (TypeError, ValueError):
            continue
    if not cell_s:
        return (None, None)
    order = sorted(range(len(cell_s)), key=lambda i: cell_s[i])
    cell_s_sorted = [cell_s[i] for i in order]
    cell_v_sorted = [cell_v[i] for i in order]
    cell_d_sorted = [cell_d[i] for i in order]
    import bisect as _bisect
    out_v: list[float] = []
    out_d: list[float] = []
    for p in fh_chainage:
        target = float(p) + float(fh_offset)
        idx = _bisect.bisect_left(cell_s_sorted, target)
        if idx <= 0:
            pick = 0
        elif idx >= len(cell_s_sorted):
            pick = len(cell_s_sorted) - 1
        elif (target - cell_s_sorted[idx - 1]) <= (cell_s_sorted[idx] - target):
            pick = idx - 1
        else:
            pick = idx
        out_v.append(cell_v_sorted[pick])
        out_d.append(cell_d_sorted[pick])
    return (out_v, out_d)


def check_cross_sections(cross_sections, world) -> dict:
    """Validate cross-sections against world river features; returns a report.
    Status is covers when every ecosystem river feature has a profile; otherwise lists missing/unknown."""
    if not cross_sections:
        return {"status": "no_cross_sections",
                "feature_ids": [], "missing_features": [],
                "unknown_feature_entries": []}
    try:
        from .replay.river_world import parse_cross_sections
        profiles = parse_cross_sections(cross_sections)
    except (ValueError, KeyError) as exc:
        return {"status": "invalid",
                "error": str(exc),
                "feature_ids": sorted(cross_sections.keys())
                if isinstance(cross_sections, dict) else []}
    world_features = set()
    for river in world.get("rivers", []) or []:
        rid = river.get("id")
        if rid:
            world_features.add(rid)
    for pool in world.get("pools", []) or []:
        pid = pool.get("id")
        if pid:
            world_features.add(pid)
    present = set(profiles.keys())
    unknown = sorted(present - world_features)
    missing = sorted(world_features - present) if world_features else []
    return {"status": ("covers" if not unknown and not missing else
                       "partial" if present else "empty"),
            "feature_ids": sorted(present),
            "unknown_feature_entries": unknown,
            "missing_features": missing}


def load_inputs(cfg: dict) -> tuple[dict, dict, dict, object]:
    """(baseline, world, deps, terrain_sample_fns). Content-complete hashes."""
    from .vegetation import load_terrain, terrain_fns
    world_root = Path(cfg.get("world_root") or default_world_root())
    required = [
        world_root / "data" / "ecosystem.json",
        world_root / "data" / "world.json",
        world_root / "data" / "placements.json",
        world_root / "data" / "species_catalogue.json",
        world_root / "data" / "terrain.f32",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            "missing world inputs: " + ", ".join(missing))
    eco_path = world_root / "data" / "ecosystem.json"
    frozen = eco_path.with_suffix(".json.pre-python")
    eco_role = "active_baseline"
    if frozen.exists():
        eco_path = frozen
        eco_role = "frozen_pre_python_baseline"
    try:
        baseline = json.loads(eco_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {eco_path}: {exc}") from exc
    try:
        world = json.loads(
            (world_root / "data" / "world.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in world.json: {exc}") from exc
    code_hash, code_hash_source = _hash_package_sources()
    code_rev, code_rev_source = resolve_code_rev()

    def _external_entry(path: Path) -> dict:
        """Path, size, and content hash so an input change surfaces at a stable build-id."""
        if not path.is_file():
            return {"path": str(path), "exists": False, "sha256": None}
        return {"path": str(path), "exists": True,
                "sha256": sha256_file(path),
                "size": path.stat().st_size}

    rcfg = cfg.get("replay", {}) or {}
    cross_sections_cfg = rcfg.get("cross_sections_file")
    if isinstance(cross_sections_cfg, str) and cross_sections_cfg:
        cs_path = Path(cross_sections_cfg)
        if not cs_path.is_absolute():
            cs_path = PKG_ROOT / cs_path
    else:
        cs_path = None
    wcfg_io = cfg.get("weather", {}) or {}
    met_cfg = wcfg_io.get("met_bundle")
    if isinstance(met_cfg, str) and met_cfg:
        met_candidate = Path(met_cfg)
        if not met_candidate.is_absolute():
            met_candidate = PKG_ROOT / met_candidate
    else:
        met_candidate = PKG_ROOT / "derived" / "met.json"
    external_inputs = {
        "terrain": _external_entry(world_root / "data" / "terrain.f32"),
        "cross_sections": (_external_entry(cs_path) if cs_path is not None
                           else {"path": None, "exists": False,
                                 "sha256": None}),
        "met_bundle": _external_entry(met_candidate),
        "requirements": _external_entry(PKG_ROOT / "requirements.txt"),
    }

    deps = {"ecosystem.json": sha256_file(eco_path),
            "ecosystem_role": eco_role,
            "ecosystem_path": str(eco_path),
            "world.json": sha256_file(world_root / "data" / "world.json"),
            "placements.json": sha256_file(world_root / "data" / "placements.json"),
            "species_catalogue.json": sha256_file(
                world_root / "data" / "species_catalogue.json"),
            "terrain.f32": sha256_file(world_root / "data" / "terrain.f32"),
            "terrain": {"path": str(world_root / "data" / "terrain.f32"),
                        "sha256": sha256_file(
                            world_root / "data" / "terrain.f32")},
            "external_inputs": external_inputs,
            "external_inputs_sha256": sha256_json(external_inputs),
            "code": code_hash.hexdigest()[:16],
            "code_hash_source": code_hash_source,
            "code_rev": code_rev,
            "code_rev_source": code_rev_source,
            "config": sha256_json(cfg)}

    try:
        import sys
        tools_dir = str(PKG_ROOT / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from check_terrain import (DEFAULT_MAX_M, DEFAULT_MIN_M,
                                   guard_terrain)
        kwargs = {
            "expect_sha256": deps["terrain.f32"],
            "min_m": DEFAULT_MIN_M, "max_m": DEFAULT_MAX_M,
        }
        import inspect as _inspect
        sig = _inspect.signature(guard_terrain)
        if "datum_status" in sig.parameters:
            kwargs["datum_status"] = "NAVD88 meters (USGS 3DEP)"
        if "require_datum" in sig.parameters:
            kwargs["require_datum"] = False
        terrain_report = guard_terrain(
            world_root / "data" / "terrain.f32", **kwargs)
    except ImportError:
        terrain_report = {"schema": "yellowstone.terrain_guard.v1",
                          "passed": False,
                          "guards": [{"name": "import", "passed": False,
                                      "detail": ("check_terrain not "
                                                 "importable from tools")}]}
    deps["terrain_guard"] = terrain_report
    critical_names = {"size", "grid", "finite", "range", "hash",
                      "terrain-readable", "import"}
    critical_failures = [
        g.get("detail", g.get("name", "?"))
        for g in terrain_report.get("guards", [])
        if not g.get("passed") and g.get("name") in critical_names]
    if critical_failures:
        raise ValueError(
            "terrain guard failed: " + "; ".join(critical_failures))
    advisory_failures = [
        f"{g.get('name')}: {g.get('detail', '?')}"
        for g in terrain_report.get("guards", [])
        if not g.get("passed") and g.get("name") not in critical_names]
    deps["terrain_guard_advisories"] = advisory_failures

    tfns = terrain_fns(load_terrain(str(world_root / "data" / "terrain.f32")))
    return baseline, world, deps, tfns


REPLAY_WEATHER_KEYS = ("night_air_c", "day_warming_c", "wind_xz_mps",
                       "gust_mps", "humidity", "cloud", "lag_hours")


def _prepare_replay_ecosystem(baseline: dict, cfg: dict, hour0: float | None = None,
                              weather: dict | None = None,
                              boundary_m3s=None) -> dict:
    """Apply config overrides to a deepcopy of the baseline for the replay solver.
    boundary_m3s accepts a scalar or a {"times_s", "values"} Series for a scheduled hydrograph."""
    eco = copy.deepcopy(baseline)
    hcfg = cfg.get("hydro", {})
    chosen_boundary = (hcfg.get("boundary_m3s", baseline["boundary_m3s"])
                       if boundary_m3s is None else boundary_m3s)
    if isinstance(chosen_boundary, dict) and {"times_s", "values"} <= set(
            chosen_boundary):
        eco["boundary_m3s"] = {
            "times_s": list(chosen_boundary["times_s"]),
            "values": [float(v) for v in chosen_boundary["values"]],
        }
    else:
        eco["boundary_m3s"] = float(chosen_boundary)
    eco["boundary_c"] = float(hcfg.get("boundary_c", baseline["boundary_c"]))
    if hour0 is not None:
        eco["clock_hour"] = float(hour0)
    if weather:
        injected = {k: copy.deepcopy(weather[k]) for k in REPLAY_WEATHER_KEYS
                    if k in weather}
        if injected:
            eco["weather"] = {**eco.get("weather", {}), **injected}
    tribs = {**DEFAULT_TRIBUTARIES, **hcfg.get("tributaries", {})}
    by_id = {r["id"]: r for r in eco["river_reaches"]}
    for rid, names in hcfg.get("attach", {}).items():
        if rid not in by_id:
            raise ValueError(f"hydro.attach reach {rid!r} not in chain "
                             f"{list(by_id)}")
        if not isinstance(names, list):
            raise ValueError(
                f"hydro.attach[{rid!r}] must be a list of tributary names")
        for n in names:
            if n not in tribs:
                raise ValueError(
                    f"unknown tributary {n!r}; have {sorted(tribs)}")
            t = tribs[n]
            if t.get("flow_m3s", 0.0) > 0:
                by_id[rid].setdefault("lateral_sources", []).append(
                    {"id": n, **t, "status": "illustrative tributary"})
    return eco


def resolve_replay_start_epoch(cfg: dict, hour0: float | None) -> tuple[float, str]:
    """Epoch seconds for the replay clock, with the date source that set it.
    Precedence: simulation group, snow.as_of_date, then system date (mirrors resolve_game_clock)."""
    scfg = cfg.get("simulation", {})
    if "start_epoch_unix" in scfg:
        return (float(scfg["start_epoch_unix"]), "simulation_config_epoch")
    if "start_utc" in scfg:
        start = parse_simulation_start(simulation_start_utc=scfg["start_utc"])
        return (start.timestamp(), "simulation_config_utc")

    hour = hour0 if hour0 is not None else float(cfg.get("clock_hour", 16.2))
    offset = float(scfg.get("utc_offset_hours", -6.0))
    as_of = cfg.get("snow", {}).get("as_of_date")
    if as_of is not None:
        return (epoch_unix_for_local(as_of, hour, offset), "config_date")
    import datetime
    return (
        epoch_unix_for_local(datetime.date.today().isoformat(), hour, offset),
        "system_clock_date",
    )


def run_replay_solver(cfg: dict, baseline: dict, world: dict,
                      hour0: float | None = None,
                      weather: dict | None = None,
                      boundary_m3s: float | None = None,
                      simulation_start_epoch_unix: float | None = None
                      ) -> dict:
    """Run the 1-D advection-dispersion solver on the Firehole chain.

    Returns the full replay document with timestamped frames and budget.
    """
    rcfg = cfg.get("replay", {})
    eco = _prepare_replay_ecosystem(baseline, cfg, hour0=hour0, weather=weather,
                                    boundary_m3s=boundary_m3s)
    if simulation_start_epoch_unix is None:
        simulation_start_epoch_unix, start_source = resolve_replay_start_epoch(
            cfg, hour0)
    else:
        start_source = "explicit_argument"
    cross_sections = {}
    if "cross_sections_file" in rcfg:
        cs_path = Path(rcfg["cross_sections_file"])
        if not cs_path.is_absolute():
            cs_path = PKG_ROOT / cs_path
        cross_sections = json.loads(cs_path.read_text())
    hyd = rcfg.get("hydraulics", {})
    doc = build_mapped_replay(
        world, eco,
        simulation_start_epoch_unix=simulation_start_epoch_unix,
        duration_s=float(rcfg.get("duration_s", 7200.0)),
        maximum_cell_m=float(rcfg.get("max_cell_m", 20.0)),
        depth_m=float(rcfg.get("depth_m", 1.1)),
        dispersion_m2_s=float(rcfg.get("dispersion_m2_s", 1.0)),
        exchange_w_m2_k=float(rcfg.get("exchange_w_m2_k", 12.0)),
        dt_s=float(rcfg.get("dt_s", 2.0)),
        sample_s=float(rcfg.get("sample_s", 10.0)),
        cross_sections=cross_sections if cross_sections else None,
        energy_budget=bool(rcfg.get("energy_budget", False)),
        bank_slope_zh=float(hyd.get("bank_slope_zh", 1.5)),
        manning_n=float(hyd.get("manning_n", 0.035)),
    )
    doc["simulation_time_source"] = start_source
    return doc


def simulate_all(cfg: dict, baseline: dict, world: dict, tfns) -> dict:
    """Pure scientific simulation: no files, no PNGs, no CLI. Returns state."""
    from .fish import check_trout_clear_of_pools, update_trout
    from .geochemistry import check_midway_shells
    from .grazers import (check_routes as check_grazer_routes, plan_path,
                          route_length as _rlen, update_grazers)
    from .insects_birds import (DEFAULT_DIETS, foraging_state, insect_activity,
                                step_compartments, step_resource,
                                update_wildlife, update_wildlife_from_intake)
    from .pool_crust import build_all as build_shells
    from .pool_crust import exclusion_violations as apron_violations
    from .pool_crust import in_apron as _in_apron
    from .snow_season import resolve_game_clock, run_season
    from .vegetation import (patch_step, propose_plantings_reviewed)

    world_root = Path(cfg.get("world_root") or default_world_root())
    run_mode_norm = normalize_run_mode(cfg.get("run_mode"))
    wcfg = dict(cfg.get("weather", {}))
    scfg_early = cfg.get("snow", {})
    clock_info = resolve_game_clock(
        season_cfg=scfg_early.get("season"),
        clock_cfg=cfg.get("clock_hour", baseline.get("clock_hour")),
        date_cfg=scfg_early.get("as_of_date"))
    hour0 = clock_info["clock_hour"]

    # Model-reanalysis bundle output wins over authored defaults when present; absent bundle keeps scenario values.
    from .microclimate import load_weather_bundle, bundle_weather
    met_cfg_val = (cfg.get("weather", {}) or {}).get("met_bundle")
    if isinstance(met_cfg_val, str) and met_cfg_val:
        met_path = Path(met_cfg_val)
        if not met_path.is_absolute():
            met_path = PKG_ROOT / met_path
        met_bundle_source = "weather.met_bundle"
    else:
        met_path = PKG_ROOT / "derived" / "met.json"
        met_bundle_source = "default:derived/met.json"
    met_bundle = load_weather_bundle(str(met_path))
    bundle_select_epoch_s: float | None = None
    bundle_select_mode = "unused"
    bundle_window_check = {"status": "no_bundle"}
    if met_bundle:
        scfg_sim = cfg.get("simulation", {}) or {}
        if "start_epoch_unix" in scfg_sim or "start_utc" in scfg_sim:
            bundle_select_epoch_s, _ = resolve_replay_start_epoch(cfg, hour0)
            wcfg = {**wcfg,
                    **bundle_weather(met_bundle,
                                     epoch_s_utc=bundle_select_epoch_s)}
            bundle_select_mode = "simulation_start_epoch"
        else:
            import warnings as _warnings
            with _warnings.catch_warnings():
                _warnings.simplefilter("ignore", DeprecationWarning)
                wcfg = {**wcfg,
                        **bundle_weather(met_bundle, hour=hour0)}
            bundle_select_mode = "hour_offset_illustrative"
        # Replay-window coverage check: compare bundle hourly epoch range to the simulation window.
        hourly = met_bundle.get("hourly") if isinstance(met_bundle, dict) else None
        duration_s = float((cfg.get("replay", {}) or {}).get(
            "duration_s", 7200.0))
        bundle_window_check = _check_met_window_covers_replay(
            hourly, bundle_select_epoch_s, duration_s)
        if (run_mode_norm in ("hindcast", "observed_replay")
                and bundle_window_check["status"] != "covers"):
            raise ValueError(
                "met bundle does not cover the replay window in run_mode "
                f"{run_mode_norm!r}: {bundle_window_check}")
    weather_provenance = (
        {"source": "Open-Meteo",
         "role": "meteorological_model_forcing",
         "observation": False,
         "calibration_status": "not_calibrated_locally",
         "label": ("open-meteo hourly bundle; model reanalysis, not a "
                   "local measurement")}
        if met_bundle
        else {"source": "authored",
              "role": "authored_defaults",
              "observation": False,
              "calibration_status": "not_calibrated",
              "label": "authored defaults; no met bundle present"})

    air0 = air_temp(hour0, wcfg.get("night_air_c", 7.0),
                    wcfg.get("day_warming_c", 15.0),
                    wcfg.get("lag_hours", 3.0))
    wind_trace = trace(seconds=60, hour0=hour0,
                       wind_xz_mps=tuple(wcfg.get("wind_xz_mps", [1.8, 0.6])),
                       gust_mps=wcfg.get("gust_mps", 0.45),
                       night_air_c=wcfg.get("night_air_c", 7.0),
                       day_warming_c=wcfg.get("day_warming_c", 15.0),
                       humidity=wcfg.get("humidity", 0.45),
                       cloud=wcfg.get("cloud", 0.16),
                       lag_hours=wcfg.get("lag_hours", 3.0),
                       seed=int(cfg.get("wind_seed", 11)))
    from .microclimate import condensation_potential
    weather_mode = ("absolute_scheduled_bundle" if met_bundle
                    else "synthetic_diurnal")
    weather_frag = {**wcfg,
                    "weather_provenance": weather_provenance,
                    "met_bundle": bool(met_bundle),
                    "forcing_mode": weather_mode,
                    "prevailing_deg": prevailing_direction(
                        tuple(wcfg.get("wind_xz_mps", [1.8, 0.6]))),
                    "air_c_at_start": air0,
                    "godot_divergence_note": (
                        "published night/day params drive ecosystem.gd's "
                        "noon-peaking air; Python analysis uses a "
                        "15:00-lagging curve. Residual documented.")}
    wx, wz = weather_frag.get("wind_xz_mps", [1.8, 0.6])
    wind_mag = math.hypot(float(wx), float(wz))
    weather_frag["condensation_62C"] = condensation_potential(
        62.0, air0, wcfg.get("humidity", 0.45), wind_mag)

    hcfg = cfg.get("hydro", {})
    sim_s = float(hcfg.get("simulate_seconds", 600.0))

    # --- M03 shells ---
    shells = build_shells(world["pools"])
    _find(shells, "id", POOL_GRAND, "pool shell")
    substrate_failures = check_midway_shells(shells)

    def _excluded(x: float, z: float) -> bool:
        return any(_in_apron(x, z, s) for s in shells)

    # --- M04 vegetation + proposals ---
    vcfg = cfg.get("vegetation", {})
    patches0 = copy.deepcopy(baseline.get("patches", []))
    # Grazing feedback: pass the previous step's consumed_by_patch from the grazer module.
    prev_consumed_by_patch = (vcfg.get("prev_consumed_by_patch") or {})
    graz_from_prev = _grazers_input_from_consumed(prev_consumed_by_patch,
                                                  sim_s)
    patches1, veg_ledger = patch_step(patches0, hour0, sim_s,
                                      grazers=graz_from_prev)
    veg_ledger["grazing_feedback_lag_steps"] = 1
    veg_ledger["grazing_feedback_available"] = bool(prev_consumed_by_patch)
    veg_ledger["grazing_feedback_source"] = (
        "grazer_module_previous_step_consumed_by_patch"
        if prev_consumed_by_patch
        else "grazer_module_previous_step_consumed_by_patch (empty for single-step build)")
    veg_ledger["prev_consumed_by_patch"] = dict(prev_consumed_by_patch)
    veg_ledger["coupling_status"] = (
        "partial" if not prev_consumed_by_patch else "wired")
    veg_ledger["config_grazers_ignored"] = (
        "vcfg.grazers no longer feeds patch_step; grazing offtake comes "
        "from the grazer module output with a one-step lag")
    prop_cfg = vcfg.get("proposal", {})
    proposal_center = tuple(prop_cfg.get("center_xz", [-360, 260]))
    proposal_radius_m = float(prop_cfg.get("radius_m", 30))
    canopy_input, canopy_source = _canopy_from_census(
        proposal_center, proposal_radius_m, PKG_ROOT / "derived" / "census.json")
    proposals, review_log = propose_plantings_reviewed(
        prop_cfg.get("guild", "lodgepole_pine"),
        proposal_center,
        proposal_radius_m,
        int(prop_cfg.get("count", 40)), int(prop_cfg.get("seed", 7)),
        habitat_id=prop_cfg.get("habitat_id", "forest_edge"),
        exclusion_test=_excluded, terrain_fn=tfns, patches=patches0,
        canopy=canopy_input,
        suitability_threshold=float(prop_cfg.get("suitability_threshold", 0.12)))
    prop_violations = apron_violations(
        [{"id": r["stable_id"], "x": r["x"], "z": r["z"]} for r in proposals],
        shells)

    # --- M08 season (before the river so its ledger reaches the boundary) ---
    scfg = cfg.get("snow", {})
    snow_days = int(scfg.get("days", 30))
    snow_air = scfg.get("air_c_by_day", [air0] * snow_days)
    patches2, snow_ledger = run_season(
        patches1, days=snow_days, air_c_by_day=snow_air,
        precip_mm_d=float(scfg.get("precip_mm_d", 2.0)),
        thermal_test=_excluded,
        run_mode=run_mode_norm,
        air_hourly_c=(met_bundle.get("hourly") if met_bundle else None))
    season = clock_info["season"]  # explicit snow.season wins, else clock

    # --- M08b snow runoff as a discharge increment over the basin ---
    from .snow_season import catchment_runoff_m3_s
    catchment_area = hcfg.get("catchment", {}).get("area_m2")
    catchment = {"schema": "yellowstone.catchment_runoff.v1",
                 "enabled": catchment_area is not None,
                 "area_m2": catchment_area,
                 "status": "illustrative_not_calibrated",
                 "runoff_state_source":
                     "patches1_post_season_pre_final_output",
                 "boundary_application": {
                     "mode": "constant_scalar_increment",
                     "scientific_status": "illustrative",
                     "not_a_hydrograph": True}}
    if catchment_area is not None:
        runoff = catchment_runoff_m3_s(patches1, snow_ledger,
                                       catchment_area_m2=catchment_area)
        catchment.update(runoff)
    else:
        runoff = {"runoff_m3_s": 0.0}
        catchment["provenance"] = (
            "no catchment area configured; snow hydrology is storage-only "
            "and the river boundary stays at its prescribed baseflow")
    runoff_m3_s = float(runoff["runoff_m3_s"])
    catchment["snow_runoff_m3_s"] = runoff_m3_s

    # Overland flow runs before the river so its outlet runoff can reach the boundary.
    olfg = cfg.get("overland", {}) or {}
    overland_field, overland_rain_source = _compute_overland_field(
        world_root, cfg, olfg, scfg, met_bundle, run_mode_norm, sim_s)
    overland_runoff_m3_s, overland_runoff_report = _overland_runoff_to_boundary(
        overland_field, hcfg, sim_s)
    overland_field["overland_flow_role"] = (
        "wired_to_river_boundary" if overland_runoff_m3_s > 0.0
        else "diagnostic_not_wired_to_river")
    overland_field["boundary_contribution"] = overland_runoff_report

    # M01 hydro.
    tribs = {**DEFAULT_TRIBUTARIES, **hcfg.get("tributaries", {})}
    reaches_in = copy.deepcopy(baseline["river_reaches"])
    by_id = {r["id"]: r for r in reaches_in}
    for rid, names in hcfg.get("attach", {}).items():
        if rid not in by_id:
            raise ValueError(f"hydro.attach reach {rid!r} not in chain "
                             f"{list(by_id)}")
        if not isinstance(names, list):
            raise ValueError(
                f"hydro.attach[{rid!r}] must be a list of tributary names")
        for n in names:
            if n not in tribs:
                raise ValueError(
                    f"unknown tributary {n!r}; have {sorted(tribs)}")
            t = tribs[n]
            if t.get("flow_m3s", 0.0) > 0:
                by_id[rid].setdefault("lateral_sources", []).append(
                    {"id": n, **t, "status": "illustrative tributary"})
    baseflow_m3s = float(hcfg.get("boundary_m3s", baseline["boundary_m3s"]))
    boundary_m3s = baseflow_m3s + runoff_m3_s + overland_runoff_m3_s
    river_state, hydro_ledger = run_simulation(
        reaches_in, boundary_m3s,
        hcfg.get("boundary_c", baseline["boundary_c"]), air0, sim_s)
    if not river_state:
        raise ValueError("river chain is empty after simulation")
    exc = _find(river_state, "id", REACH_EXCELSIOR, "reach")
    bridge = next((r for r in river_state if r["id"] == REACH_BRIDGE),
                  river_state[-1])

    # --- M01b 1-D advection-dispersion replay ---
    replay_cfg_scope = cfg.get("replay", {}) or {}
    energy_budget_default = bool(replay_cfg_scope.get("energy_budget", False))
    full_bundle = bool(
        met_bundle and all(k in wcfg for k in
                           ("night_air_c", "humidity", "cloud", "wind_xz_mps")))
    energy_budget_choice = energy_budget_default
    budget_mode_source = (
        "replay.energy_budget explicit" if "energy_budget" in replay_cfg_scope
        else "replay.energy_budget default (false)")
    if ("energy_budget" not in replay_cfg_scope
            and run_mode_norm in ("hindcast", "observed_replay")
            and full_bundle):
        energy_budget_choice = True
        budget_mode_source = (
            "run_mode=hindcast/observed_replay with full bundle; "
            "explicit energy budget default on")
    cfg_for_replay = copy.deepcopy(cfg)
    cfg_for_replay.setdefault("replay", {})
    cfg_for_replay["replay"]["energy_budget"] = energy_budget_choice
    # Cross-section schema check: parse and compare against world river/pool features.
    cross_sections_doc = None
    cs_file_cfg = replay_cfg_scope.get("cross_sections_file")
    if isinstance(cs_file_cfg, str) and cs_file_cfg:
        cs_path = Path(cs_file_cfg)
        if not cs_path.is_absolute():
            cs_path = PKG_ROOT / cs_path
        try:
            cross_sections_doc = json.loads(cs_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as cs_exc:
            raise ValueError(
                f"replay.cross_sections_file {cs_path} unreadable: {cs_exc}"
            ) from cs_exc
    cross_sections_report = check_cross_sections(cross_sections_doc, world)
    replay_doc = run_replay_solver(cfg_for_replay, baseline, world,
                                   hour0=hour0, weather=weather_frag,
                                   boundary_m3s=boundary_m3s)
    replay_doc.setdefault("provenance", {})["energy_budget_source"] = (
        budget_mode_source)
    replay_doc["provenance"]["cross_sections_report"] = cross_sections_report

    # --- M05b aquatic food web: replay heat -> insect prey -> trout refuge -> dipper intake, 14-day run ---
    from .aquatic_foodweb import run_foodweb as run_aquatic_foodweb
    from .aquatic_foodweb import thermal_landscape
    fcfg_foodweb = cfg.get("fish", {})
    foodweb_species = str(fcfg_foodweb.get("species", "brown_trout"))
    foodweb_cover = float(fcfg_foodweb.get("cover", 0.6))
    foodweb_cfg = cfg.get("foodweb", {})
    foodweb_days = float(foodweb_cfg.get("days", 14.0))
    foodweb_dt_days = float(foodweb_cfg.get("dt_days", 1.0))
    foodweb_ne_turnover_days = float(foodweb_cfg.get("ne_turnover_days", 2.0))
    foodweb_shear_disturb_pa = float(foodweb_cfg.get("shear_disturb_pa", 20.0))
    try:
        aquatic_foodweb = run_aquatic_foodweb(
            thermal_landscape(replay_doc),
            days=foodweb_days,
            dt_days=foodweb_dt_days,
            trout_species=foodweb_species,
            cover=foodweb_cover,
            ne_turnover_days=foodweb_ne_turnover_days,
            shear_disturb_pa=foodweb_shear_disturb_pa)
    except ValueError as exc:
        raise ValueError(f"aquatic foodweb failed: {exc}") from exc

    # M05 insects: activity and compartments.
    icfg = cfg.get("insects", {})
    flowering = float(icfg.get("flowering_stage", 0.6))
    riparian = _find(patches1, "id", PATCH_RIPARIAN, "patch")
    sun0 = max(0.0, math.sin((hour0 - 6.0) * math.pi / 12.0))
    act0 = insect_activity(
        sun=sun0, air_c=air0, cloud=weather_frag.get("cloud", 0.16),
        moisture=riparian.get("moisture", 0.85),
        resource=riparian.get("insect_resource", 0.8),
        wind_mps=wind_mag, flowering=flowering)
    for p in patches1:
        if p["id"] == PATCH_RIPARIAN:
            p["insect_resource"] = step_resource(
                float(p.get("insect_resource", 0.8)),
                float(p.get("insect_recovery_per_hour", 0.06)),
                sun=sun0, moisture=float(p.get("moisture", 0.85)),
                consumed=0.0, dt_s=sim_s)
    wildlife1 = update_wildlife(baseline.get("wildlife", []),
                                {PATCH_RIPARIAN: act0})
    # Insect compartments model one patch; pick a bridge cell from the replay thermal landscape so forcing is shared.
    from .aquatic_foodweb import shear_to_disturbance
    foodweb_landscape = thermal_landscape(replay_doc)
    bridge_cells = [c for c in foodweb_landscape
                    if c.get("river_id") == RIVER_FIREHOLE]
    bridge_cell = bridge_cells[-1] if bridge_cells else foodweb_landscape[-1]
    bridge_cell_id = bridge_cell.get("id")
    bridge_cell_water_c = float(bridge_cell.get("temperature_c",
                                                bridge.get("temperature_c",
                                                           18.0)))
    bridge_cell_shear_pa = bridge_cell.get("shear_pa")
    bridge_disturbance = shear_to_disturbance(bridge_cell_shear_pa,
                                              foodweb_shear_disturb_pa)
    prey = dict(icfg.get("initial", {"Nt": 0.5, "Nb": 0.5, "Ne": 0.2}))
    prey_ledgers = []
    _t = 0.0
    while _t < sim_s - 1e-9:
        _h = min(60.0, sim_s - _t)
        prey, _pl = step_compartments(
            prey, {"sun": sun0, "air_c": air0,
                   "cloud": weather_frag.get("cloud", 0.16),
                   "moisture": riparian.get("moisture", 0.85),
                   "wind_mps": wind_mag, "flowering": flowering,
                   "water_c": bridge_cell_water_c,
                   "cell_id": bridge_cell_id,
                   "disturbance": bridge_disturbance},
            dt_s=_h, consumers=DEFAULT_DIETS)
        prey_ledgers.append(_pl)
        _t += _h
    prey_ledger = {"emergence_total": round(sum(l["emergence"] for l in prey_ledgers), 6),
                   "consumed_total": {k: round(sum(l["consumed_by"].get(k, 0.0) for l in prey_ledgers), 6)
                                      for k in DEFAULT_DIETS},
                   "final": prey,
                   "forcing_cell_id": bridge_cell_id,
                   "forcing_water_c": round(bridge_cell_water_c, 3),
                   "forcing_disturbance": round(float(bridge_disturbance), 4),
                   "forcing_shear_pa": (round(float(bridge_cell_shear_pa), 4)
                                        if bridge_cell_shear_pa is not None
                                        else None),
                   "forcing_shear_disturb_pa": float(foodweb_shear_disturb_pa),
                   "forcing_source": "foodweb_shear_to_disturbance_shared"}
    # Per-cell benthic development across every Firehole cell, driven by the replay thermal landscape.
    from .insects_birds import develop_benthic_grid
    fh_landscape_cells = [c for c in foodweb_landscape
                          if c.get("river_id") == RIVER_FIREHOLE]
    benthic_grid = None
    if fh_landscape_cells and sim_s > 0.0:
        nb_init = [0.5] * len(fh_landscape_cells)
        water_c_cells = [float(c["temperature_c"])
                         for c in fh_landscape_cells]
        try:
            grid_result = develop_benthic_grid(
                nb_init, water_c_cells, dt_s=sim_s,
                disturbance=float(bridge_disturbance))
            benthic_grid = {
                "cell_ids": [c["id"] for c in fh_landscape_cells],
                "water_c_cells": water_c_cells,
                "nb_init": nb_init,
                "nb": grid_result["nb"],
                "emergence": grid_result["emergence"],
                "disturbance_loss": grid_result["disturbance_loss"],
                "dt_s": sim_s,
                "forcing_source": "replay_thermal_landscape_firehole_cells",
            }
        except (ValueError, KeyError) as benthic_exc:
            benthic_grid = {"status": "input_invalid",
                            "reason": str(benthic_exc)}
    rates = {k: v / max(1e-9, sim_s / 3600.0)
             for k, v in prey_ledger["consumed_total"].items()}
    # Dipper intake comes from the replay food web via the shared trout refuge cell; raven stays on the compartment ledger.
    fw_dipper = aquatic_foodweb.get("dipper", {})
    intake_basis = {k: "insect_compartments" for k in rates}
    if "intake_per_day" in fw_dipper:
        rates["dipper"] = float(fw_dipper["intake_per_day"]) / 24.0
        intake_basis["dipper"] = "replay_foodweb"
    wildlife1 = update_wildlife_from_intake(wildlife1, rates, intake_basis)

    # M06 fish.
    fcfg = cfg.get("fish", {})
    firehole = _find(world["rivers"], "id", RIVER_FIREHOLE, "river")
    from .fish import (build_chainage, place_trout_at_chainage,
                       reach_membership, reach_z_windows)
    fh_ordered = reach_z_windows(river_state, river_points=firehole["points"])
    fh_membership = reach_membership(firehole["points"], fh_ordered)
    fh_chainage = build_chainage(firehole["points"])
    fh_features = replay_doc.get("replay", replay_doc).get("river_features", {})
    fh_offset = float(fh_features.get(RIVER_FIREHOLE, {}).get("start_s_m", 0.0))
    # Per-point velocity and depth from the nearest Firehole replay cell; polyline chainage + fh_offset selects the cell.
    cell_velocity_mps, cell_depth_m = _per_point_hydraulics_from_cells(
        fh_chainage, fh_offset, fh_landscape_cells)
    trout_hydraulics_source: str
    if cell_velocity_mps is not None and cell_depth_m is not None:
        wildlife2 = update_trout(wildlife1, river_state, firehole["points"],
                                 weights=fcfg.get("weights"),
                                 food=float(fcfg.get("food", 0.7)),
                                 cover=float(fcfg.get("cover", 0.6)),
                                 cell_velocity_mps=cell_velocity_mps,
                                 cell_depth_m=cell_depth_m)
        trout_hydraulics_source = (
            "per_cell_from_replay_firehole_landscape_nearest_chainage")
    else:
        wildlife2 = update_trout(wildlife1, river_state, firehole["points"],
                                 weights=fcfg.get("weights"),
                                 food=float(fcfg.get("food", 0.7)),
                                 cover=float(fcfg.get("cover", 0.6)))
        trout_hydraulics_source = ("reach_level_fallback_no_firehole_cells")
    # place_trout_at_chainage is the single authority for trout position.
    wildlife2 = place_trout_at_chainage(
        wildlife2, river_state, firehole["points"],
        aquatic_foodweb["trout"], chainage_offset_m=fh_offset)
    trout_position_authority = "fish.place_trout_at_chainage"
    trout_blockers = check_trout_clear_of_pools(wildlife2, firehole["points"],
                                                shells)

    # --- M07 grazers ---
    wildlife3 = update_grazers(wildlife2, patches1)
    grazer_blockers = check_grazer_routes(wildlife3, shells)
    b1 = _find(wildlife3, "id", BISON_DEMO, "wildlife")
    # Re-walk the bison's authored route segment by segment through the eligibility planner for verification.
    _leg = [tuple(p) for p in b1["path_xz"]]
    _xs = [p[0] for p in _leg]
    _zs = [p[1] for p in _leg]
    _bounds = (min(_xs) - 20, min(_zs) - 20, max(_xs) + 20, max(_zs) + 20)
    _corr = []
    _corr_ok = True
    for _a, _b in zip(_leg, _leg[1:]):
        try:
            _corr += plan_path(_a, _b, _excluded, cell_m=4.0, bounds=_bounds)
        except ValueError:
            _corr_ok = False
            break
    from .grazers import route_length as _rlen
    corridor = {"from": list(_leg[0]), "to": list(_leg[-1]),
                "length_m": round(_rlen(_corr), 1) if _corr else 0.0,
                "waypoints": len(_corr),
                "planner_ok": _corr_ok,
                "note": ("planner re-walk on apron grid over the authored "
                         "route; records not altered")}

    # Merge variant.
    variant = merge_fragments(baseline, river_state,
                              {k: v for k, v in weather_frag.items()
                               if k in ("night_air_c", "day_warming_c",
                                        "wind_xz_mps", "gust_mps",
                                        "humidity", "cloud")},
                              clock_hour=hour0,
                              boundary_m3s=boundary_m3s,
                              boundary_c=float(hcfg.get(
                                  "boundary_c", baseline["boundary_c"])))
    variant["patches"] = patches2
    variant["wildlife"] = wildlife3
    godot_errors = validate_for_godot(variant)

    timeline = {
        "t0": "frozen baseline + config",
        "fast_window_s": sim_s,
        "fast_processes": ["river transport", "patch biomass",
                           "insect compartments", "trout refuge",
                           "grazer/bird timing"],
        "season_days": snow_days,
        "slow_processes": ["snowpack", "soil water", "phenology"],
        "wildlife_reference": ("timings from t0+fast conditions; "
                               "snow updates moisture afterwards"),
    }
    return {"hour0": hour0, "air0": air0, "sim_s": sim_s,
            "clock_info": clock_info, "season": season,
            "weather_frag": weather_frag, "wind_trace": wind_trace,
            "met_bundle": met_bundle, "weather_provenance": weather_provenance,
            "met_bundle_source": met_bundle_source,
            "met_bundle_path": str(met_path),
            "bundle_window_check": bundle_window_check,
            "river_state": river_state, "hydro_ledger": hydro_ledger,
            "replay_doc": replay_doc, "aquatic_foodweb": aquatic_foodweb,
            "shells": shells, "substrate_failures": substrate_failures,
            "patches1": patches1, "veg_ledger": veg_ledger,
            "proposals": proposals, "review_log": review_log,
            "prop_cfg": prop_cfg, "prop_violations": prop_violations,
            "act0": act0, "wind_mag": wind_mag, "flowering": flowering,
            "prey_ledger": prey_ledger, "wildlife1": wildlife1,
            "wildlife2": wildlife2, "trout_blockers": trout_blockers,
            "wildlife3": wildlife3, "grazer_blockers": grazer_blockers,
            "corridor": corridor, "patches2": patches2,
            "snow_ledger": snow_ledger, "scfg": scfg,
            "variant": variant, "godot_errors": godot_errors,
            "timeline": timeline, "tfns": tfns, "patches0": patches0,
            "overland_field": overland_field,
            "overland_runoff_m3_s": overland_runoff_m3_s,
            "overland_rain_source": overland_rain_source,
            "cross_sections_report": cross_sections_report,
            "benthic_grid": benthic_grid,
            "trout_hydraulics_source": trout_hydraulics_source,
            "firehole_points": firehole["points"],
            "fh_membership": fh_membership, "fh_chainage": fh_chainage,
            "fh_chainage_offset_m": fh_offset,
            "catchment": catchment, "baseflow_m3s": baseflow_m3s,
            "boundary_m3s": boundary_m3s,
            "snow_partition_source": "snow_season_air_c_threshold_1C",
            "canopy_source": canopy_source,
            "canopy_fraction_proposal": canopy_input,
            "bundle_select_mode": bundle_select_mode,
            "bundle_select_epoch_s": bundle_select_epoch_s,
            "trout_position_authority": trout_position_authority,
            "budget_mode_source": budget_mode_source,
            "energy_budget_choice": energy_budget_choice}


def render_all(res: dict, out: Path, deps: dict, world_root: Path) -> None:
    """Visualization + export: PNGs and JSON sidecars from simulated state."""
    from .hydro_thermal import plume_field, render_plume_png
    from .pool_crust import render_apron_mask, render_apron_tiles, render_ramp
    from .pool_crust import render_cross_section
    from .fish import render_refuge_map
    from .grazers import render_tracks as render_grazer_tracks
    from .snow_season import render_snow_map
    from .vegetation import render_suitability_png
    from .geochemistry import rules_doc as substrate_rules

    river_state, shells = res["river_state"], res["shells"]
    render_refuge_map(river_state, res["wildlife2"],
                      str(out / "refuge_map.png"),
                      river_points=res["firehole_points"], shells=shells)
    render_grazer_tracks(res["wildlife3"], str(out / "grazer_tracks.png"))
    render_snow_map(shells, 256, str(out / "snow_map.png"),
                    snow_m=max((p.get("snow_depth_m", 0.0)
                                for p in res["patches2"]), default=0.0))
    exc = _find(river_state, "id", REACH_EXCELSIOR, "reach")
    river_ref = next(
        (r for r in river_state if r["id"] == REACH_BRIDGE),
        river_state[-1] if river_state else None)
    if river_ref is None:
        raise ValueError("river_state is empty; cannot render plume")
    field = plume_field(nx=128, nz=128, hot_c=float(exc["temperature_c"]),
                        river_c=float(river_ref["temperature_c"]))
    render_plume_png(field, 128, 128, str(out / "plume_map.png"))

    shells_doc = write_sidecar(
        out / "pool_shells.json", {"pool_shells": shells},
        sources=[{"file": "yellowstone_midway/data/world.json",
                  "sha256": deps["world.json"]}],
        params={"recipe": "RECIPES per pool name; depths/colors illustrative",
                "outline": "mapped water polygons preserved"},
        code_rev=deps["code_rev"])
    render_apron_mask(shells, 256, str(out / "apron_mask.png"))
    render_apron_tiles(shells, str(out / "apron_tiles"))
    rampdir = out / "pool_ramps"
    rampdir.mkdir(exist_ok=True)
    for s in shells:
        render_ramp(s, str(rampdir / f"{s['id']}.png"))
    gp = _find(shells, "id", POOL_GRAND, "pool shell")
    render_cross_section(gp, str(out / "pool_cross_section.png"))
    write_sidecar(out / "substrate_rules.json", substrate_rules(),
                  sources=[{"id": "NPS_G4",
                            "url": "https://www.nps.gov/yell/learn/nature/hydrothermal-features.htm"}],
                  params={"midway": "siliceous only; travertine refused"},
                  code_rev=deps["code_rev"])

    prop_cfg, patches0 = res["prop_cfg"], res["patches0"]
    cx0, cz0 = prop_cfg.get("center_xz", [-360, 260])
    _rr = float(prop_cfg.get("radius_m", 30))
    render_suitability_png(prop_cfg.get("guild", "lodgepole_pine"), 128,
                           str(out / "suitability_demo.png"),
                           bbox=(cx0 - _rr, cz0 - _rr, cx0 + _rr, cz0 + _rr),
                           terrain_fn=res["tfns"], patches=patches0,
                           shells=shells)
    return shells_doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(PKG_ROOT / "configs" / "baseline.yaml"))
    ap.add_argument("--out", default=str(PKG_ROOT / "derived"))
    ap.add_argument(
        "--force", action="store_true",
        help=("Reuse the build directory when CHECKS.json already exists. "
              "Default behavior raises so a completed build is never "
              "overwritten in place."))
    args = ap.parse_args()

    cfg_raw = load_config(Path(args.config))
    import os
    if os.environ.get("YELLOWSTONE_WORLD"):
        cfg_raw["world_root"] = os.environ["YELLOWSTONE_WORLD"]
    # Non-mutating validation: cfg is the normalized copy used downstream.
    cfg = validate_config(cfg_raw)
    baseline, world, deps, tfns = load_inputs(cfg)
    bid = build_id(cfg, deps, code_rev=deps["code_rev"])
    out = Path(args.out) / bid
    if (out / "CHECKS.json").is_file() and not args.force:
        raise FileExistsError(
            f"build directory {out} already holds a completed build "
            f"(CHECKS.json present); pass --force to reuse it")
    out.mkdir(parents=True, exist_ok=True)

    res = simulate_all(cfg, baseline, world, tfns)
    shells_doc = render_all(res, out, deps, Path(cfg["world_root"]))
    _write_variant_and_gate(cfg, baseline, deps, res, out, bid,
                            shells_doc is not None)
    return 0 if json.loads((out / "CHECKS.json").read_text())["passed"] else 2


def _package_version(name: str) -> str:
    """Installed distribution version or not_installed."""
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version(name)
    except PackageNotFoundError:
        return "not_installed"


def _code_commit() -> tuple:
    """VCS head hash or (None, reason) outside a checkout."""
    import subprocess
    try:
        out = subprocess.run(
            ["git", "-C", str(PKG_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return out.stdout.strip(), "git_head"
        return None, "no_vcs_checkout"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None, "no_vcs_checkout"


def build_manifest(cfg: dict, deps: dict, res: dict, checks: dict,
                   bid: str, mode: str, prescribed: list,
                   out: Path) -> dict:
    """Spec 10.1 run manifest. Existing keys are preserved."""
    from .claims import CLAIMS
    import os
    import platform

    commit, commit_status = _code_commit()
    lock = PKG_ROOT / "requirements.txt"
    world_label = Path(cfg.get("world_root") or "yellowstone_midway").name
    hydro = cfg.get("hydro", {})
    replay_cfg = cfg.get("replay", {})
    fish_cfg = cfg.get("fish", {})
    snow_cfg = cfg.get("snow", {})
    replay_doc = res.get("replay_doc", {})
    foodweb_cfg = cfg.get("foodweb", {})
    parameter_set = {
        "hydro": {k: hydro.get(k) for k in
                  ("boundary_m3s", "boundary_c", "tributaries",
                   "attach", "catchment")},
        "replay": replay_cfg,
        "fish": {k: fish_cfg.get(k) for k in
                 ("weights", "food", "cover", "species")},
        "snow": {k: snow_cfg.get(k) for k in ("days", "precip_mm_d",
                                              "season", "as_of_date")},
        "foodweb": {k: foodweb_cfg.get(k) for k in
                    ("days", "dt_days", "ne_turnover_days",
                     "shear_disturb_pa")},
        "weather": cfg.get("weather", {}),
        "overland": cfg.get("overland", {}),
        "vegetation": cfg.get("vegetation", {}),
        "insects": cfg.get("insects", {}),
        "wind_seed": cfg.get("wind_seed", 11),
        "simulation": cfg.get("simulation", {}),
    }
    artifacts = {}
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "BUILD.json":
            artifacts[str(path.relative_to(out))] = sha256_file(path)
    return {
        "schema": "yellowstone.build_manifest.v1",
        "run_id": bid,
        "build_id": bid,
        "contract_version": CONTRACT_VERSION,
        "world_id": WORLD_ID,
        "run_mode": mode,
        "prescribed_quantities": prescribed,
        "predicted_quantities": predicted_quantities(cfg),
        "hydrology": {
            "baseflow_m3s": res["baseflow_m3s"],
            "snow_runoff_m3_s": res["catchment"].get("runoff_m3_s", 0.0),
            "effective_boundary_m3s": res["boundary_m3s"],
            "catchment_enabled": res["catchment"]["enabled"],
        },
        "provenance": {
            "snow_partition_source": res.get("snow_partition_source"),
            "canopy_source": res.get("canopy_source"),
            "canopy_fraction_proposal": res.get("canopy_fraction_proposal"),
            "bundle_select_mode": res.get("bundle_select_mode"),
            "bundle_select_epoch_s": res.get("bundle_select_epoch_s"),
            "trout_position_authority": res.get("trout_position_authority"),
            "energy_budget_source": res.get("budget_mode_source"),
            "energy_budget_choice": res.get("energy_budget_choice"),
            "code_hash_source": deps.get("code_hash_source"),
        },
        "claim_ids": [c["claim_id"] for c in CLAIMS],
        "code_commit": commit,
        "code_commit_status": commit_status,
        "code_rev": deps.get("code_rev"),
        "code_rev_source": deps.get("code_rev_source"),
        "code_sha256": deps.get("code"),
        "environment_lock": {
            "file": "requirements.txt",
            "sha256": (sha256_file(lock) if lock.is_file() else None),
            "note": ("requirements.txt carries version ranges; "
                     "external_solver_versions holds the authoritative "
                     "installed versions for this run"),
        },
        "external_solver_versions": {
            "python": platform.python_version(),
            "numpy": _package_version("numpy"),
            "scipy": _package_version("scipy"),
            "matplotlib": _package_version("matplotlib"),
            "pandas": _package_version("pandas"),
            "pyyaml": _package_version("pyyaml"),
            "pillow": _package_version("Pillow"),
            "pint": _package_version("pint"),
            "salib": _package_version("SALib"),
            "xarray": _package_version("xarray"),
            "netcdf4": _package_version("netCDF4"),
        },
        "input_datasets": {
            "ecosystem": {"file": f"{world_label}/data/ecosystem.json",
                          "sha256": deps.get("ecosystem.json")},
            "world": {"file": f"{world_label}/data/world.json",
                      "sha256": deps.get("world.json")},
            "placements": {"file": f"{world_label}/data/placements.json",
                           "sha256": deps.get("placements.json")},
            "species_catalogue": {
                "file": f"{world_label}/data/species_catalogue.json",
                "sha256": deps.get("species_catalogue.json")},
            "terrain": {"file": f"{world_label}/data/terrain.f32",
                        "sha256": deps.get("terrain.f32")},
        },
        "configuration_hash": deps.get("config"),
        "parameter_set": parameter_set,
        "parameter_set_sha256": sha256_json(parameter_set),
        "random_streams": {
            "wind_seed": int(cfg.get("wind_seed", 11)),
            "proposal_seed": int(res.get("prop_cfg", {}).get("seed", 7)),
            "generator": "stdlib random.Random, no global numpy RNG "
                         "in build path",
        },
        "grid_and_time_step": {
            "replay_duration_s": replay_cfg.get("duration_s"),
            "replay_dt_s": replay_cfg.get("dt_s"),
            "replay_sample_s": replay_cfg.get("sample_s"),
            "replay_max_cell_m": replay_cfg.get("max_cell_m"),
            "replay_depth_m": replay_cfg.get("depth_m"),
            "n_cells": len(replay_doc.get("cells", [])),
            "n_frames": len(replay_doc.get("frames", [])),
            "hydro_simulate_seconds": hydro.get("simulate_seconds"),
        },
        "solver_tolerances": {
            "replay_heat_relative": REPLAY_HEAT_RELATIVE_TOLERANCE,
            "replay_water_relative": REPLAY_WATER_RELATIVE_TOLERANCE,
            "hydro_heat_ledger": HYDRO_HEAT_LEDGER_TOL_J,
            "hydro_water_ledger": HYDRO_WATER_LEDGER_TOL_M3,
            "snow_storage_mm": SNOW_STORAGE_TOL_MM,
            "source": "yellowstone_python.validation.checks",
        },
        "model_authority": {
            "thermal_transport": "replay_doc",
            "fish_display": "legacy_hydro_thermal.run_simulation",
            "foodweb": "replay_doc",
            "trout_position": res.get("trout_position_authority",
                                      "fish.place_trout_at_chainage"),
            "legacy_role": (
                "display and bridge temperature only; replay_doc is the "
                "authoritative thermal transport model for the chain"),
        },
        "shared_forcing": {
            "weather_fragment_source": "cfg.weather plus optional "
                                       "met_bundle override",
            "legacy_air_c_at_t0_c": res["air0"],
            "replay_forcing_source": (
                "weather_frag (same wcfg feed as the legacy chain; "
                "replay also records air time series from the resolved "
                "night/day fit)"),
            "forcing_match": (
                "legacy and replay consume the same wcfg; divergence "
                "comes only from the solver (steady mixing vs 1-D "
                "advection-dispersion)"),
        },
        "hydrology_components": {
            "baseflow_m3s": res["baseflow_m3s"],
            "snow_runoff_m3_s": res["catchment"].get("snow_runoff_m3_s", 0.0),
            "overland_runoff_m3_s": res.get("overland_runoff_m3_s", 0.0),
            "effective_boundary_m3s": res["boundary_m3s"],
        },
        "met_bundle_provenance": {
            "source": res.get("met_bundle_source"),
            "path": res.get("met_bundle_path"),
            "window_check": res.get("bundle_window_check"),
            "pool_crust_hot_source": (
                "plume2d uses the Excelsior reach temperature after "
                "pool-to-river mixing, not the pool interior temperature; "
                "pool_crust temperatures stay in pool_shells.json "
                "(illustrative by design)"),
            "surface_budget_wiring": (
                "explicit surface budget runs in hindcast/observed_replay "
                "when the met bundle carries night_air_c, humidity, "
                "cloud, and wind_xz_mps; otherwise Newton stays "
                "(illustrative by design)"),
        },
        "restart": {
            "support": "split-run same process; fresh object under "
                       "constant forcing",
            "benchmark": "restart_equivalence",
        },
        "hardware": {
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "parallelism": "single process",
        },
        "checks_passed": checks["passed"],
        "warnings_and_failures": list(checks["failures"]),
        "output_artifact_hashes": artifacts,
        "deps": deps,
        "timeline": res.get("timeline"),
        "metrics": copy.deepcopy(checks["metrics"]),
    }


def _atomic_json_write(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def _write_variant_and_gate(cfg, baseline, deps, res, out, bid, _ok):
    eco_doc = write_sidecar(
        out / "ecosystem.variant.json", {"ecosystem": res["variant"]},
        sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                  "sha256": deps["ecosystem.json"]}],
        params={"air_c_at_start_C": res["air0"],
                "simulate_seconds": res.get("sim_s", 0.0),
                "heat_ledger": res["hydro_ledger"],
                "timeline": res["timeline"],
                "note": "drop-in replacement for data/ecosystem.json"},
        code_rev=deps["code_rev"])
    _atomic_json_write(out / "ecosystem.godot.json", res["variant"])
    _atomic_json_write(out / "river_state.json", res["river_state"])
    replay_payload = res["replay_doc"]
    replay_payload.setdefault("forcing", {})
    replay_payload["forcing"]["catchment_runoff"] = {
        "baseflow_m3_s": float(res["baseflow_m3s"]),
        "runoff_m3_s": float(res["catchment"].get("runoff_m3_s", 0.0)),
        "effective_boundary_m3_s": float(res["boundary_m3s"]),
        "enabled": bool(res["catchment"].get("enabled", False)),
        "status": res["catchment"].get("status",
                                       "illustrative_not_calibrated"),
    }
    if res["replay_doc"].get("frames"):
        frames = res["replay_doc"]["frames"]
        if "wall_time" not in frames[0]:
            start_epoch = res["replay_doc"].get("simulation_start_epoch_unix")
            if start_epoch is None:
                start_epoch, _ = resolve_replay_start_epoch(cfg,
                                                            res.get("hour0"))
            frames[0]["wall_time"] = float(start_epoch)
    write_sidecar(out / "river_replay.json",
                  {"replay": replay_payload},
                  sources=[{"file": "yellowstone_midway/data/world.json",
                            "sha256": deps["world.json"]}],
                  params={"method": "1-D finite-volume advection-dispersion",
                          "energy_budget": res["replay_doc"].get("model", {}).get("surface_flux", "newton_lumped"),
                          "status": "illustrative, not calibrated"},
                  code_rev=deps["code_rev"])
    if (cfg.get("replay", {}) or {}).get("netcdf", False):
        from .replay.nc_export import write_replay_netcdf
        try:
            write_replay_netcdf(replay_payload["frames"],
                                [c["id"] for c in replay_payload["cells"]],
                                out / "river_replay.nc")
        except (ImportError, ValueError) as exc:
            print(f"netcdf export skipped: {exc}")
    _atomic_json_write(out / "weather.json", {"weather": res["weather_frag"], "wind_trace_60s": res["wind_trace"]})
    if res["met_bundle"]:
        _atomic_json_write(out / "met.json", res["met_bundle"])
    write_sidecar(out / "overland_flow.json", res["overland_field"],
                  sources=[{"file": "yellowstone_midway/data/terrain.f32",
                            "sha256": deps["terrain.f32"]}],
                  params={"method": "hydrosim local-inertial shallow water, "
                          "block-mean of terrain.f32"},
                  code_rev=deps["code_rev"],
                  status=res["overland_field"].get("status",
                                                   "illustrative_not_calibrated"))
    write_sidecar(out / "catchment_runoff.json", res["catchment"],
                  sources=[{"file": "configs/baseline.yaml",
                            "sha256": deps.get("config")}],
                  params={"method": "snow ledger runoff depth scaled to the "
                          "configured catchment area",
                          "baseflow_m3s": res["baseflow_m3s"],
                          "effective_boundary_m3s": res["boundary_m3s"]},
                  code_rev=deps["code_rev"],
                  status=res["catchment"]["status"])
    _write_fragment_sidecars(cfg, baseline, deps, res, out)

    from .validation.checks import run_all
    from .aquatic_foodweb import thermal_landscape
    from .claims import registry_errors as _claims_registry_errors
    from .coupling import check_coupling, validate_contract
    from .equations import validate_inventory
    from .param_registry import registry_errors as _param_registry_errors
    mode = normalize_run_mode(cfg.get("run_mode"))
    prescribed = prescribed_quantities(cfg)
    checks = run_all(river_state=res["river_state"], ledger=res["hydro_ledger"],
                     ecosystem_doc=eco_doc, build_id_a=bid,
                     run_mode=mode, prescribed=prescribed,
                     validated_quantities=(),
                     replay_doc=res["replay_doc"],
                     landscape=thermal_landscape(res["replay_doc"]),
                     membership=res["fh_membership"],
                     chainage=res["fh_chainage"],
                     chainage_offset_m=res["fh_chainage_offset_m"])
    checks["metrics"]["validation_claims"] = []
    # Groundwater exchange: call head_gradient_exchange when per-cell records are authored; coupling partial otherwise.
    gw_cells = (cfg.get("hydro", {}) or {}).get("groundwater", {}).get("cells")
    gw_provenance: dict
    if isinstance(gw_cells, list) and gw_cells:
        from .groundwater_provider import head_gradient_exchange
        try:
            gw_result = head_gradient_exchange(gw_cells)
            gw_provenance = {
                "status": "wired",
                "totals": gw_result["totals"],
                "n_gaining_sources": len(gw_result["sources"]),
                "n_losing_cells": len(gw_result["losing"]),
                "note": ("River.Source accepts only nonnegative flow; losing "
                         "cells are published to groundwater_losing.json"),
            }
            write_sidecar(out / "groundwater_losing.json",
                          {"losing": gw_result["losing"],
                           "totals": gw_result["totals"]},
                          sources=[{"id": "code", "sha256": deps["code"]}],
                          params={"method": "head-gradient conductance "
                                            "C = K W L / b; q = C (h_aq - h_r)"},
                          code_rev=deps["code_rev"],
                          status="authored_not_calibrated")
        except (ValueError, KeyError) as gw_exc:
            gw_provenance = {"status": "input_invalid",
                             "reason": str(gw_exc)}
    else:
        gw_provenance = {
            "status": "partial",
            "reason": ("no hydro.groundwater.cells configured; the "
                       "head-gradient exchange needs per-cell bed "
                       "conductivity, thickness, width, length, aquifer "
                       "and river heads, and an aquifer temperature"),
        }
    # Numerical warnings from the replay solver land in CHECKS.metrics but never fail the build on their own.
    replay_numerical_warnings = (
        res["replay_doc"].get("numerical_checks", {})
                         .get("numerical_warnings", []) or [])
    checks["metrics"]["replay_numerical_warnings"] = list(
        replay_numerical_warnings)
    checks["metrics"]["groundwater_exchange"] = gw_provenance
    # Registry gates: contract vocabulary, equation inventory, claim and parameter registries into the aggregate build gate.
    registry_failures = (
        _claims_registry_errors()
        + validate_contract()
        + validate_inventory(root=PKG_ROOT / "yellowstone_python")
        + _param_registry_errors()
    )
    if registry_failures:
        checks["passed"] = False
        checks["failures"] += [f"registry: {e}" for e in registry_failures]
    checks["metrics"]["registry_failures"] = registry_failures
    # Claim-aligned non-regression gates: reach and SNOTEL holdout rmse against current evidence artifacts.
    from .validation.claims import run_claim_gates
    claim_gate = run_claim_gates()
    checks["metrics"]["claim_gates"] = claim_gate["gates"]
    if not claim_gate["passed"]:
        checks["passed"] = False
        checks["failures"] += [f"claim_gate: {f}"
                               for f in claim_gate["failures"]]
    # Separate coupling_check artifact; coupling.json is the contract, coupling_check.json is the verification result.
    coupling_result = check_coupling(
        res["replay_doc"], thermal_landscape(res["replay_doc"]))
    checks["metrics"]["coupling_check_passed"] = coupling_result["passed"]
    if res["godot_errors"]:
        checks["passed"] = False
        checks["failures"] += ["godot: " + e for e in res["godot_errors"]]
    if res["prop_violations"]:
        checks["passed"] = False
        checks["failures"] += [f"apron: proposal inside exclusion: {v}"
                               for v in res["prop_violations"][:5]]
    if res["trout_blockers"]:
        checks["passed"] = False
        checks["failures"] += [f"refuge: trout route inside apron: {v}"
                               for v in res["trout_blockers"][:5]]
    if res["substrate_failures"]:
        checks["passed"] = False
        checks["failures"] += [f"substrate: {v}" for v in res["substrate_failures"]]
    if not (0.0 <= res["act0"] <= 1.0):
        checks["passed"] = False
        checks["failures"] += [f"insects: activity {res['act0']} out of [0,1]"]
    for p in res["patches1"]:
        if not (0.0 <= float(p["biomass"]) <= float(p.get("capacity", 1.0))):
            checks["passed"] = False
            checks["failures"] += [f"patch {p['id']}: biomass out of bounds"]
    if res["grazer_blockers"]:
        checks["passed"] = False
        checks["failures"] += [f"grazer: route violates habitat: {v}"
                               for v in res["grazer_blockers"][:5]]
    for p in res["patches2"]:
        if float(p.get("snow_mm", 0.0)) < 0:
            checks["passed"] = False
            checks["failures"] += [f"snow: negative storage {p['id']}"]
    snow_ledger = res["snow_ledger"]
    if abs(snow_ledger.get("storage_residual_mm",
                           float("inf"))) > SNOW_STORAGE_TOL_MM:
        checks["passed"] = False
        checks["failures"] += [
            f"snow: storage residual {snow_ledger.get('storage_residual_mm')} mm"]
    checks["metrics"]["n_proposals"] = len(res["proposals"])
    checks["metrics"]["n_shells"] = len(res["shells"])
    rb = res["replay_doc"].get("final_budget", {})
    checks["metrics"]["replay_heat_budget_error"] = rb.get("heat_residual_j", float("inf"))
    checks["metrics"]["replay_water_budget_error_m3"] = rb.get("water_residual_m3", float("inf"))
    checks["metrics"]["replay_n_cells"] = len(res["replay_doc"].get("cells", []))
    checks["metrics"]["replay_n_frames"] = len(res["replay_doc"].get("frames", []))
    hyd_sum = res["replay_doc"].get("hydraulics_summary", {})
    checks["metrics"]["replay_travel_time_s"] = hyd_sum.get("total_travel_time_s")
    checks["metrics"]["replay_manning_median"] = hyd_sum.get(
        "manning_consistency_ratio_median")
    checks["metrics"]["replay_flat_grade_cells"] = hyd_sum.get(
        "n_flat_or_adverse_grade_cells")
    sl = res["aquatic_foodweb"]["trout"]
    checks["metrics"]["foodweb_refuge_s_m"] = sl.get("s_m")
    checks["metrics"]["foodweb_refuge_temp_c"] = sl.get("temperature_c")
    checks["metrics"]["foodweb_refuge_U"] = sl.get("U")
    checks["metrics"]["foodweb_emergence_total"] = res["aquatic_foodweb"][
        "prey_totals"].get("emergence")
    checks["metrics"]["foodweb_dipper_per_day"] = res["aquatic_foodweb"][
        "dipper"].get("intake_per_day")
    if not res["replay_doc"].get("numerical_checks", {}).get("passed", False):
        checks["passed"] = False
        checks["failures"].append("replay: budget closure checks failed")
    from collections import Counter
    checks["metrics"]["phenology"] = dict(Counter(
        p.get("phenology", "?") for p in res["patches2"]))
    checks["metrics"]["substrate_ok"] = not res["substrate_failures"]
    from .replay.identifiability import run_diagnostics
    diagnostics = run_diagnostics()
    checks["metrics"]["identifiability_rank"] = diagnostics[
        "conditioning"]["rank"]
    checks["metrics"]["identifiability_max_cost"] = diagnostics[
        "multistart"]["max_cost"]
    checks["metrics"]["structural_surface_gap_c"] = diagnostics[
        "structural_surface"]["max_abs_gap_c"]
    _atomic_json_write(out / "CHECKS.json", checks)
    from .claims import CLAIMS
    from .coupling import EXCHANGES
    from .equations import COMPONENTS
    from .param_registry import PARAMS
    from .replay.benchmarks import run_all_benchmarks
    write_sidecar(out / "numerics_benchmarks.json",
                  run_all_benchmarks(),
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "identifiability.json",
                  diagnostics,
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "coupling.json",
                  {"schema": "yellowstone.coupling.v1",
                   "exchanges": EXCHANGES},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "coupling_check.json",
                  {"schema": "yellowstone.coupling_check.v1",
                   **coupling_result},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "claims.json",
                  {"schema": "yellowstone.claims.v1", "claims": CLAIMS},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "param_registry.json",
                  {"schema": "yellowstone.param_registry.v1",
                   "params": PARAMS},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "equations.json",
                  {"schema": "yellowstone.equations.v1",
                   "components": COMPONENTS},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    from .exporters.godot_sidecars import produce_all as _produce_sidecars
    sidecar_written, sidecar_gaps = _produce_sidecars(out)
    if sidecar_gaps:
        print("godot sidecar gaps: " + "; ".join(sidecar_gaps))
    _atomic_json_write(
        out / "BUILD.json",
        build_manifest(cfg, deps, res, checks, bid, mode, prescribed, out))
    print(f"build {bid} passed={checks['passed']} → {out}")
    for f in checks["failures"]:
        print("FAIL:", f)


def _write_fragment_sidecars(cfg, baseline, deps, res, out):
    from .fish import THERMAL_SPECIES
    from .insects_birds import foraging_state
    world_root = Path(cfg.get("world_root") or default_world_root())
    write_sidecar(out / "patch_state.json", {"patches": res["patches1"]},
                  sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                            "sha256": deps["ecosystem.json"]}],
                  params={"veg_ledger": res["veg_ledger"],
                          "hours": res.get("sim_s", 0.0) / 3600.0},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "planting_proposal.json",
                  {"proposals": res["proposals"],
                   "review_log": res["review_log"],
                   "review": "merge reviewed rows into placement_overrides.json::{add}; never overwrite placements.json"},
                  sources=[{"file": "yellowstone_midway/data/placements.json",
                            "sha256": deps["placements.json"]}],
                  params={"guild": res["prop_cfg"].get("guild"),
                          "seed": res["prop_cfg"].get("seed"),
                          "n_accepted": len(res["proposals"]),
                          "n_rejected": sum(1 for r in res["review_log"]
                                            if r["decision"] == "reject")},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "insect_bird.json",
                  {"activity": res["act0"],
                   "state": foraging_state(res["act0"]),
                   "wind_mps": res["wind_mag"],
                   "flowering_stage": res["flowering"],
                   "compartments": res["prey_ledger"],
                   "wildlife": [r for r in res["wildlife1"]
                                if r.get("id") in ("dipper_01", "raven_01")]},
                  sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                            "sha256": deps["ecosystem.json"]}],
                  params={"threshold": 0.035,
                          "note": "bird cadence from Holling intake + legacy activity gate"},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "fish.json",
                   {"wildlife": [r for r in res["wildlife2"] if "trout" in r["id"]],
                    "hydraulics": ("V=Q/A_trap trapezoidal diagnostic per "
                                   "replay cell (solver volumes still "
                                   "rectangular); Manning/Froude/Fischer + "
                                   "travel times in river_replay.json "
                                   "hydraulics_summary; illustrative, not "
                                   "calibrated"),
                    "thermal_species": {k: {
                        "t_opt_lo_c": v["t_opt_lo_c"],
                        "t_opt_hi_c": v["t_opt_hi_c"],
                        "t_feed_zero_c": v["t_feed_zero_c"],
                        "t_refuge_c": v["t_refuge_c"],
                        "t_uilt_c": v["t_uilt_c"],
                        "status": v["status"]} for k, v in
                        THERMAL_SPECIES.items()}},
                  sources=[{"file": "yellowstone_midway/data/world.json",
                            "sha256": deps["world.json"]}],
                  params={"weights": cfg.get("fish", {}).get("weights", "defaults"),
                           "activity": "clamp((26-T)/8) visibility only",
                           "refuge": "chainage-window argmax suitability"},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "aquatic_foodweb.json",
                  {"foodweb": res["aquatic_foodweb"]},
                  sources=[{"file": "yellowstone_midway/data/world.json",
                            "sha256": deps["world.json"]}],
                  params={"method": "14-day insect/trout/dipper food web on "
                                    "replay time-mean thermal landscape",
                          "trout_species": res["aquatic_foodweb"].get(
                              "trout_species"),
                          "status": "illustrative, not calibrated"},
                  code_rev=deps["code_rev"])
    if res.get("benthic_grid") is not None:
        write_sidecar(out / "benthic_grid.json",
                      res["benthic_grid"],
                      sources=[{"file": "yellowstone_midway/data/world.json",
                                "sha256": deps["world.json"]}],
                      params={"method": "insects_birds.develop_benthic_grid "
                                        "driven by replay thermal landscape",
                              "trout_hydraulics_source":
                                  res.get("trout_hydraulics_source")},
                      code_rev=deps["code_rev"])
    write_sidecar(out / "grazer.json",
                  {"wildlife": [r for r in res["wildlife3"]
                                if r.get("kind") in ("bison", "elk")],
                   "planner_corridor": res["corridor"]},
                  sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                            "sha256": deps["ecosystem.json"]}],
                  params={"causal_claim": "none_single",
                          "note": "sparse authored loops; not abundance"},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "season.json",
                  {"patches": [{k: p[k] for k in
                                ("id", "snow_mm", "snow_depth_m",
                                 "snow_cover_fraction", "moisture",
                                 "phenology", "pheno_stress", "gdd") if k in p}
                               for p in res["patches2"]],
                   "season": res["season"],
                   "season_source": res["clock_info"]["season_source"],
                   "clock_hour": res["clock_info"]["clock_hour"],
                   "clock_source": res["clock_info"]["clock_source"],
                   "as_of_local_date": res["clock_info"]["as_of_local_date"],
                   "date_source": res["clock_info"]["date_source"],
                   "ledger": res["snow_ledger"]},
                  sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                            "sha256": deps["ecosystem.json"]}],
                  params={"method": "degree-day + soil bucket, verified ledger",
                          "geometry": "frozen; surfaces/phenology only"},
                  code_rev=deps["code_rev"])


if __name__ == "__main__":
    raise SystemExit(main())
