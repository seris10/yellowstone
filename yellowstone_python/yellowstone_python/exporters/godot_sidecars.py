"""Producers for Godot-side sidecar files from a published build directory."""
from __future__ import annotations

from yellowstone_python.common.site import SITE_LAT_DEG, SITE_LON_DEG

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from yellowstone_python.common.provenance import CONTRACT_VERSION, WORLD_ID
from yellowstone_python.common.io import load_json, write_json_atomic


PLUME_FIELD_SCHEMA = "yellowstone.plume_field.v1"
GEOCHEMISTRY_SCHEMA = "yellowstone.geochemistry.v1"
CALIBRATION_SUMMARY_SCHEMA = "yellowstone.calibration_summary.v1"
POOLS_STATE_SCHEMA = "yellowstone.pools_state.v1"
SNOW_COVER_SCHEMA = "yellowstone.snow_cover.v1"
OVERLAND_FIELD_SCHEMA = "yellowstone.overland_field.v1"
GROUNDWATER_FIELD_SCHEMA = "yellowstone.groundwater_field.v1"
CENSUS_FIELD_SCHEMA = "yellowstone.census.v1"
WEATHER_SNAPSHOT_SCHEMA_VERSION = 2

# Firehole site centroid shared with llm_backend's solar snapshot.

# Reader-side gates mirrored from yellowstone_midway/scripts/weather_snapshot_reader.gd.
WEATHER_SNAPSHOT_REQUIRED_FIELDS = (
    "air_temperature_c", "relative_humidity", "wind_speed_mps",
    "wind_direction_deg", "cloud_fraction", "precipitation_rate_mm_h",
    "snow_fraction", "visibility_m",
)
WEATHER_SNAPSHOT_REQUIRED_RANGES = {
    "air_temperature_c": (-70.0, 60.0),
    "relative_humidity": (0.0, 1.0),
    "wind_speed_mps": (0.0, 65.0),
    "wind_direction_deg": (0.0, 360.0),  # upper exclusive
    "cloud_fraction": (0.0, 1.0),
    "precipitation_rate_mm_h": (0.0, 250.0),
    "snow_fraction": (0.0, 1.0),
    "visibility_m": (100.0, 100000.0),
}
WEATHER_SNAPSHOT_OPTIONAL_RANGES = {
    "dewpoint_c": (-80.0, 45.0),
    "cloud_base_agl_m": (100.0, 10000.0),
    "cloud_thickness_m": (100.0, 5000.0),
    "ground_wetness_fraction": (-1.0, 1.0),
}
SOLAR_AZIMUTH_RANGE_DEG = (0.0, 360.0)  # upper exclusive
SOLAR_ELEVATION_RANGE_DEG = (-90.0, 90.0)
# Optional terrain fields and inclusive ranges mirrored from the godot weather snapshot reader validation.
WEATHER_SNAPSHOT_TERRAIN_RANGES = {
    "snow_cover_fraction": (0.0, 1.0),
    "snow_water_equivalent_mm": (0.0, 100000.0),
    "puddle_fraction": (0.0, 1.0),
    "soil_temperature_c": (-80.0, 60.0),
    "ground_wetness_fraction": (0.0, 1.0),
    "cloud_shadow_fraction": (0.0, 1.0),
    "steam_intensity": (0.0, 10.0),
    "insect_activity": (0.0, 10.0),
}

PLUME_FIELD_NX = 128
PLUME_FIELD_NZ = 128
PLUME_FIELD_EXTENT_M = 600.0
PLUME_FIELD_ORIGIN_XZ = (0.0, -60.0)

EXCELSIOR_REACH_ID = "excelsior_mixing"
BRIDGE_REACH_ID = "bridge_downstream"


class MissingSourceError(RuntimeError):
    """Raised when the build directory lacks the inputs a producer needs."""


def _load_json(path: Path, label: str) -> dict:
    try:
        return load_json(path, label=label)
    except ValueError as exc:
        raise MissingSourceError(str(exc)) from exc


def _reach_by_id(reaches: list, rid: str) -> dict | None:
    for r in reaches:
        if r.get("id") == rid:
            return r
    return None


def _write_json(out_path: Path, doc: dict) -> Path:
    return write_json_atomic(out_path, doc, indent=2)


def write_plume_field_json(build_dir: Path,
                           out_path: Path | None = None) -> Path:
    """Write a 2-D plume field sidecar from the mapped river state."""
    build_dir = Path(build_dir)
    document = _load_json(build_dir / "river_replay.json", "river_replay.json")
    replay = document.get("replay", document)
    cells = replay.get("cells", [])
    frames = replay.get("frames", [])
    connections = replay.get("source_connections", [])
    source = next((row for row in connections if "excelsior" in row.get("source_id", "")), None)
    bridge = next((row for row in replay.get("legacy_queries", []) if row.get("reach_id") == BRIDGE_REACH_ID), None)
    if not cells or not frames or source is None or bridge is None:
        raise MissingSourceError("plume requires replay cells, frames, Excelsior connection and bridge query")
    def temperature_at(chainage):
        index = min(range(len(cells)), key=lambda i: abs(float(cells[i]["center_s_m"]) - chainage))
        return float(frames[-1]["temperature_c"][index])
    hot = {"temperature_c": temperature_at(float(source["s_m"]))}
    cool = {"temperature_c": temperature_at(float(bridge["s_m"])), "id": BRIDGE_REACH_ID}
    from yellowstone_python.river.plume2d import solve_steady
    sol = solve_steady(nx=PLUME_FIELD_NX, nz=PLUME_FIELD_NZ,
                       extent_m=PLUME_FIELD_EXTENT_M,
                       ambient_c=float(cool["temperature_c"]),
                       source_c=float(hot["temperature_c"]),
                       source_xz=PLUME_FIELD_ORIGIN_XZ)
    nx = int(sol["nx"])
    nz = int(sol["nz"])
    temperature_grid_c = [
        sol["field"][j * nx:(j + 1) * nx] for j in range(nz)
    ]
    doc = {
        "contract_version": CONTRACT_VERSION,
        "world_id": WORLD_ID,
        "schema": PLUME_FIELD_SCHEMA,
        "status": "illustrative",
        "units": {"axes_x_m": "m", "axes_z_m": "m",
                  "temperature_grid_c": "degree_Celsius",
                  "hot_source_c": "degree_Celsius",
                  "river_c": "degree_Celsius"},
        "axes_x_m": [float(v) for v in sol["xs"]],
        "axes_z_m": [float(v) for v in sol["zs"]],
        "origin_xz": [float(PLUME_FIELD_ORIGIN_XZ[0]),
                      float(PLUME_FIELD_ORIGIN_XZ[1])],
        "nx": nx,
        "nz": nz,
        "extent_m": float(sol["extent_m"]),
        "hot_source_c": float(hot["temperature_c"]),
        "river_c": float(cool["temperature_c"]),
        "temperature_grid_c": temperature_grid_c,
        "source": {
            "excelsior_reach_id": EXCELSIOR_REACH_ID,
            "bridge_reach_id": cool.get("id"),
            "model": "replay.plume2d.solve_steady (first-order upwind + Fischer)",
        },
        "discrete_residual_c_s": float(sol.get("discrete_residual_c_s", 0.0)),
    }
    out = Path(out_path) if out_path else build_dir / "plume_field.json"
    return _write_json(out, doc)


def write_geochemistry_json(build_dir: Path,
                            out_path: Path | None = None) -> Path:
    """Per-cell silica saturation diagnostics from the last replay frame.
Quartz solubility per Fournier (1977) no-steam-loss; cells without SiO2 obs flag no_observation."""
    build_dir = Path(build_dir)
    replay_doc = _load_json(build_dir / "river_replay.json",
                            "river_replay.json")
    replay = replay_doc.get("replay") or {}
    cells = replay.get("cells") or []
    frames = replay.get("frames") or []
    if not cells or not frames:
        raise MissingSourceError(
            "river_replay.json has no cells or frames to diagnose")
    last = frames[-1]
    temps = last.get("temperature_c") or []
    if len(temps) != len(cells):
        raise MissingSourceError(
            "temperature frame length does not match cell count")
    from yellowstone_python.thermal_features.geochemistry import diagnose_replay_frame
    cell_inputs = [
        {"id": c.get("id"), "temperature_c": float(t)}
        for c, t in zip(cells, temps)
    ]
    rows = diagnose_replay_frame(cell_inputs, sio2_obs_or_None=None,
                                 phase_rule="quartz")
    def _cell_center_s_m(c: dict) -> float | None:
        if "center_s_m" in c:
            try:
                return float(c["center_s_m"])
            except (TypeError, ValueError):
                return None
        start = c.get("start_s_m")
        end = c.get("end_s_m")
        if start is None or end is None:
            return None
        try:
            return (float(start) + float(end)) / 2.0
        except (TypeError, ValueError):
            return None

    def _cell_xz(c: dict):
        for key_x, key_z in (("x_m", "z_m"), ("center_x_m", "center_z_m")):
            if key_x in c and key_z in c:
                try:
                    return float(c[key_x]), float(c[key_z])
                except (TypeError, ValueError):
                    continue
        pos = c.get("position_xz") or c.get("center_xz")
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            try:
                return float(pos[0]), float(pos[1])
            except (TypeError, ValueError):
                return None
        return None

    doc_cells = []
    for cell, row in zip(cells, rows):
        chainage_m = _cell_center_s_m(cell)
        xz = _cell_xz(cell)
        entry = {
            "cell": row["cell"],
            "temperature_c": row["temperature_c"],
            "phase": row["phase"],
            "equilibrium_mg_L": row["equilibrium_mg_L"],
            "silica_saturation_index": row["si"],
            "sio2_obs_mg_L": row["sio2_obs_mg_L"],
            "reservoir_T_C": row["reservoir_T_C"],
            "flag": row["flag"],
            "chainage_m": chainage_m,
            "x_m": xz[0] if xz is not None else None,
            "z_m": xz[1] if xz is not None else None,
        }
        doc_cells.append(entry)
    doc = {
        "contract_version": CONTRACT_VERSION,
        "world_id": WORLD_ID,
        "schema": GEOCHEMISTRY_SCHEMA,
        "status": "illustrative",
        "units": {"temperature_c": "degree_Celsius",
                  "equilibrium_mg_L": "mg per L SiO2",
                  "sio2_obs_mg_L": "mg per L SiO2",
                  "si": "log10 ratio dimensionless",
                  "reservoir_T_C": "degree_Celsius",
                  "chainage_m": "m",
                  "x_m": "m",
                  "z_m": "m"},
        "phase": "quartz",
        "solubility_reference": "Fournier 1977 no steam loss",
        "frame_t_s": float(last.get("t_s", 0.0)),
        "cells": doc_cells,
    }
    out = Path(out_path) if out_path else build_dir / "geochemistry.json"
    return _write_json(out, doc)


def write_calibration_summary_json(build_dir: Path,
                                   fit_path: Path | None = None,
                                   obs_path: Path | None = None,
                                   out_path: Path | None = None) -> Path:
    """Reach heat fit scalars plus the observed USGS gauge trace."""
    build_dir = Path(build_dir)
    derived_root = build_dir.parent
    fit_candidates = []
    if fit_path is not None:
        fit_candidates.append(Path(fit_path))
    fit_candidates.extend(sorted(derived_root.glob("reach_heat_fit*.json"),
                                 reverse=True))
    fit_file = next((p for p in fit_candidates if p.is_file()), None)
    if fit_file is None:
        raise MissingSourceError(
            "no reach_heat_fit*.json found alongside the build")
    fit_doc = _load_json(fit_file, fit_file.name)
    champion = fit_doc.get("champion") or {}
    if not champion:
        raise MissingSourceError(
            f"{fit_file.name} has no champion fit entry")
    train_rmse = champion.get("train_rmse")
    holdout_rmse = champion.get("holdout_rmse")
    reach_fit = {
        "source_file": fit_file.name,
        "q_lat_m3s": champion.get("q_lat"),
        "t_lat_c": champion.get("t_lat"),
        "c_mult": champion.get("c_mult"),
        "train_rmse_c": train_rmse,
        "holdout_rmse_c": holdout_rmse,
        "train_bias_c": champion.get("train_bias"),
        "holdout_bias_c": champion.get("holdout_bias"),
        "budget_ok": bool(champion.get("budget_ok", False)),
        "status": champion.get("status") or fit_doc.get("status"),
    }
    obs_candidates = []
    if obs_path is not None:
        obs_candidates.append(Path(obs_path))
    obs_candidates.extend([
        derived_root / "firehole_obs_locked_final.json",
        derived_root / "firehole_obs.json",
    ])
    obs_file = next((p for p in obs_candidates if p.is_file()), None)
    gauge_trace: list[dict] = []
    gauge_site_id: str | None = None
    if obs_file is not None:
        obs_doc = _load_json(obs_file, obs_file.name)
        sites = obs_doc.get("sites") or {}
        gauge_site_id = next(iter(sites), None)
        if gauge_site_id is not None:
            series = sites[gauge_site_id].get("series") or {}
            discharge = series.get("discharge_m3_s") or []
            temperature = series.get("temperature_c") or []
            temp_lookup = {float(t): float(v) for t, v in temperature}
            for sample in discharge:
                ts_s = float(sample[0])
                q_m3s = float(sample[1])
                gauge_trace.append({
                    "t_s": ts_s,
                    "discharge_m3_s": q_m3s,
                    "temperature_c": temp_lookup.get(ts_s),
                })
    doc = {
        "contract_version": CONTRACT_VERSION,
        "world_id": WORLD_ID,
        "schema": CALIBRATION_SUMMARY_SCHEMA,
        "status": "illustrative" if gauge_trace else "fit_only",
        "units": {"train_rmse_c": "degree_Celsius",
                  "holdout_rmse_c": "degree_Celsius",
                  "t_s": "seconds since Unix epoch",
                  "discharge_m3_s": "m3/s",
                  "temperature_c": "degree_Celsius"},
        "reach_fit": reach_fit,
        "gauge_trace": {
            "site_id": gauge_site_id,
            "source_file": obs_file.name if obs_file else None,
            "samples": gauge_trace,
        },
    }
    out = Path(out_path) if out_path else build_dir / "calibration_summary.json"
    return _write_json(out, doc)


def write_pools_state_json(build_dir: Path,
                           out_path: Path | None = None) -> Path:
    """Per-pool thermal state exported for the Godot pool overlay."""
    build_dir = Path(build_dir)
    shells_src = build_dir / "pool_shells.json"
    if not shells_src.is_file():
        raise MissingSourceError(
            f"pool_shells.json not found at {shells_src}; cannot emit pools_state")
    doc = _load_json(shells_src, "pool_shells.json")
    shells = doc.get("pool_shells") or doc.get("shells") or []
    if not isinstance(shells, list) or not shells:
        raise MissingSourceError(
            "pool_shells.json has no pool_shells list")
    now = int(datetime.now(timezone.utc).timestamp())
    pools = []
    for shell in shells:
        if not isinstance(shell, dict):
            continue
        pool_id = shell.get("id")
        if pool_id is None:
            continue
        t_center = shell.get("t_center_c")
        t_edge = shell.get("t_edge_c")
        if t_center is None or t_edge is None:
            continue
        pools.append({
            "id": pool_id,
            "name": shell.get("name"),
            "source_id": shell.get("source_id"),
            "t_center_c": float(t_center),
            "t_edge_c": float(t_edge),
            "r_water_m": shell.get("r_water_m"),
            "r_apron_m": shell.get("r_apron_m"),
        })
    if not pools:
        raise MissingSourceError(
            "pool_shells.json carries no shells with t_center_c/t_edge_c")
    outdoc = {
        "contract_version": CONTRACT_VERSION,
        "world_id": WORLD_ID,
        "schema": POOLS_STATE_SCHEMA,
        "status": "authored_steady_pending_dynamic_coupling",
        "generated_at_unix": now,
        "units": {"t_center_c": "degree_Celsius",
                  "t_edge_c": "degree_Celsius",
                  "r_water_m": "m", "r_apron_m": "m"},
        "pools": pools,
        "note": ("pools_state.json carries authored pool temperatures "
                 "sourced from pool_shells; replace with per-step dynamic "
                 "state once a reservoir-coupled thermal model is wired."),
    }
    out = Path(out_path) if out_path else build_dir / "pools_state.json"
    return _write_json(out, outdoc)


SNOW_COVER_FULL_DEPTH_M = 0.10  # authored full-cover threshold


def _snow_cover_fraction_from_depth(depth_m: float) -> float:
    """Linear ramp: zero cover at 0 m SWE-adjusted depth, full at the authored full-cover threshold."""
    try:
        d = float(depth_m)
    except (TypeError, ValueError):
        return 0.0
    if d != d or d <= 0.0:  # NaN or non-positive
        return 0.0
    if d >= SNOW_COVER_FULL_DEPTH_M:
        return 1.0
    return d / SNOW_COVER_FULL_DEPTH_M


def write_snow_cover_sidecar(build_dir: Path,
                             out_path: Path | None = None) -> Path:
    """Per-patch snow_cover_fraction sidecar ( )."""
    build_dir = Path(build_dir)
    season = build_dir / "season.json"
    if not season.is_file():
        raise MissingSourceError("season.json not found; snow cover gap")
    with season.open(encoding="utf-8") as handle:
        season_doc = json.load(handle)
    patches = season_doc.get("patches") or []
    if not patches:
        raise MissingSourceError(
            "season.json carries no patches")
    explicit_fraction = any(
        isinstance(p, dict) and "snow_cover_fraction" in p for p in patches)
    rows = []
    source = ("season.json::patches[].snow_cover_fraction" if explicit_fraction
              else ("derived_from_snow_depth_m via "
                    f"full-cover threshold {SNOW_COVER_FULL_DEPTH_M} m"))
    for p in patches:
        if not isinstance(p, dict):
            continue
        if explicit_fraction and "snow_cover_fraction" in p:
            fraction = float(p.get("snow_cover_fraction") or 0.0)
        else:
            fraction = _snow_cover_fraction_from_depth(
                p.get("snow_depth_m", 0.0))
        rows.append({"id": p.get("id"),
                     "snow_cover_fraction": round(fraction, 4)})
    if not rows:
        raise MissingSourceError(
            "season.json patches lack id/snow_depth_m fields")
    doc = {
        "contract_version": CONTRACT_VERSION,
        "world_id": WORLD_ID,
        "schema": SNOW_COVER_SCHEMA,
        "status": "illustrative",
        "source": source,
        "units": {"snow_cover_fraction": "fraction in [0, 1]"},
        "patches": rows,
    }
    out = Path(out_path) if out_path else build_dir / "snow_cover.json"
    return _write_json(out, doc)


def _wind_direction_from_vector(vx: float, vz: float) -> float:
    """Meteorological from-direction (deg) given a +x east, +z south wind-to vector."""
    import math
    deg = math.degrees(math.atan2(-float(vx), -float(vz)))
    return deg % 360.0


def write_weather_snapshot_json(build_dir: Path,
                                out_path: Path | None = None) -> Path:
    """Write weather evaluated at the build's simulation epoch."""
    from yellowstone_python.atmosphere.microclimate import weather_snapshot
    build_dir = Path(build_dir)
    weather_doc = _load_json(build_dir / "weather.json", "weather.json")
    weather = weather_doc.get("weather") or {}
    replay_path = build_dir / "river_replay.json"
    replay_doc = _load_json(replay_path, "river_replay.json") if replay_path.is_file() else {}
    replay = replay_doc.get("replay", replay_doc)
    epoch = replay.get("simulation_start_epoch_unix", replay.get("simulation_time", {}).get("start_epoch_unix"))
    if epoch is None:
        season_path = build_dir / "season.json"
        season = _load_json(season_path, "season.json") if season_path.is_file() else {}
        epoch = season.get("simulation_epoch_unix", season.get("start_epoch_unix"))
    if epoch is None:
        raise MissingSourceError("weather snapshot requires a simulation epoch")
    doc = weather_snapshot(float(epoch), weather)
    snow_path = build_dir / "snow_cover.json"
    if snow_path.is_file():
        snow = _load_json(snow_path, "snow_cover.json")
        fractions = [float(row["snow_cover_fraction"]) for row in snow.get("patches", [])]
        if fractions:
            doc["terrain"] = {"snow_cover_fraction": sum(fractions) / len(fractions)}
    return _write_json(Path(out_path) if out_path else build_dir / "weather_snapshot.json", doc)


def validate_weather_snapshot_doc(doc: dict) -> list[str]:
    """Return a list of validation errors"""
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["root must be a JSON object"]
    schema = doc.get("schema_version")
    if not isinstance(schema, (int, float)):
        errors.append("schema_version must be numeric")
    elif int(schema) not in (1, 2):
        errors.append(
            f"unsupported schema_version {schema}; expected 1 or 2")
    gen = doc.get("generated_at_unix")
    if not isinstance(gen, (int, float)):
        errors.append("generated_at_unix must be a finite number")
    weather = doc.get("weather")
    if not isinstance(weather, dict):
        errors.append("weather must be an object")
        return errors
    for field in WEATHER_SNAPSHOT_REQUIRED_FIELDS:
        if field not in weather:
            errors.append(f"weather missing required field {field!r}")
    for field, (lo, hi) in WEATHER_SNAPSHOT_REQUIRED_RANGES.items():
        if field not in weather:
            continue
        value = weather[field]
        if not isinstance(value, (int, float)):
            errors.append(f"weather.{field} must be a finite number")
            continue
        v = float(value)
        exclusive_upper = (field == "wind_direction_deg")
        above = v >= hi if exclusive_upper else v > hi
        if v < lo or above:
            errors.append(
                f"weather.{field} out of range [{lo}, {hi}]: {v}")
    for field, (lo, hi) in WEATHER_SNAPSHOT_OPTIONAL_RANGES.items():
        if field not in weather:
            continue
        value = weather[field]
        if value is None:
            continue
        if not isinstance(value, (int, float)):
            errors.append(f"weather.{field} must be a finite number or null")
            continue
        v = float(value)
        if v < lo or v > hi:
            errors.append(
                f"weather.{field} out of range [{lo}, {hi}]: {v}")
    solar = doc.get("solar")
    if isinstance(solar, dict):
        az = solar.get("solar_azimuth_deg")
        el = solar.get("solar_elevation_deg")
        if (az is None) != (el is None):
            errors.append("solar block requires both azimuth and elevation")
        if isinstance(az, (int, float)):
            if float(az) < SOLAR_AZIMUTH_RANGE_DEG[0] or float(
                    az) >= SOLAR_AZIMUTH_RANGE_DEG[1]:
                errors.append(
                    f"solar.solar_azimuth_deg out of range: {az}")
        if isinstance(el, (int, float)):
            if (float(el) < SOLAR_ELEVATION_RANGE_DEG[0]
                    or float(el) > SOLAR_ELEVATION_RANGE_DEG[1]):
                errors.append(
                    f"solar.solar_elevation_deg out of range: {el}")
    terrain = doc.get("terrain")
    if terrain is not None:
        if not isinstance(terrain, dict):
            errors.append("terrain must be an object")
        else:
            for field, (lo, hi) in WEATHER_SNAPSHOT_TERRAIN_RANGES.items():
                if field not in terrain:
                    continue
                value = terrain[field]
                if not isinstance(value, (int, float)):
                    errors.append(
                        f"terrain.{field} must be a finite number")
                    continue
                v = float(value)
                if v < lo or v > hi:
                    errors.append(
                        f"terrain.{field} out of range [{lo}, {hi}]: {v}")
    return errors


def write_overland_field_json(build_dir: Path,
                              out_path: Path | None = None) -> Path:
    """Republish overland_flow.json as overland_field.json for the Godot reader.
Carries synthetic_catchment_predicted_not_validated plus the overland module status."""
    build_dir = Path(build_dir)
    src = build_dir / "overland_flow.json"
    if not src.is_file():
        raise MissingSourceError(
            f"overland_flow.json not found at {src}; build did not run the "
            f"overland module")
    source = _load_json(src, "overland_flow.json")
    doc = {
        "contract_version": CONTRACT_VERSION,
        "world_id": WORLD_ID,
        "schema": OVERLAND_FIELD_SCHEMA,
        "status": "synthetic_catchment_predicted_not_validated",
        "overland_module_status": source.get("status"),
        "enabled": bool(source.get("enabled", False)),
        "surface_runoff": source.get("surface_runoff"),
        "overland_flow_role": source.get("overland_flow_role"),
        "rainfall_source": source.get("rainfall_source"),
        "units": {"max_depth_m": "m",
                  "outflow_m3": "m3",
                  "surface_runoff.max_depth_m": "m",
                  "surface_runoff.outflow_m3": "m3"},
        "provenance": source.get("provenance"),
    }
    out = Path(out_path) if out_path else build_dir / "overland_field.json"
    return _write_json(out, doc)


def write_groundwater_field_json(build_dir: Path,
                                 out_path: Path | None = None) -> Path:
    """Reserved groundwater field producer ().
Writes when groundwater.json exists in the build; else raises MissingSourceError."""
    del out_path
    build_dir = Path(build_dir)
    gw_src = build_dir / "groundwater.json"
    if gw_src.is_file():
        source = _load_json(gw_src, "groundwater.json")
        doc = {
            "contract_version": CONTRACT_VERSION,
            "world_id": WORLD_ID,
            "schema": GROUNDWATER_FIELD_SCHEMA,
            "status": source.get("status", "authored_lateral_not_modeled"),
            "payload": source,
        }
        out = build_dir / "groundwater_field.json"
        return _write_json(out, doc)
    raise MissingSourceError(
        "groundwater_field.json requires a build-side groundwater sidecar; "
        "groundwater_provider.STATUS is authored_lateral_not_modeled and the "
        "build does not run MF6 or a Darcy exchange solve.")


def write_census_sidecar(build_dir: Path,
                         out_path: Path | None = None) -> Path:
    """Copy derived/census.json alongside the build so publish ships it.
Lands in build_dir to keep publish atomic for the Godot census overlay."""
    build_dir = Path(build_dir)
    local = build_dir / "census.json"
    if local.is_file():
        return local
    sibling = build_dir.parent / "census.json"
    if not sibling.is_file():
        raise MissingSourceError(
            f"census.json not found at {sibling} or {local}; run "
            f"canopy_census tooling to produce it")
    source = _load_json(sibling, "census.json")
    doc = {
        "contract_version": CONTRACT_VERSION,
        "world_id": WORLD_ID,
        "schema": CENSUS_FIELD_SCHEMA,
        "status": source.get("status", "illustrative"),
        "payload": source,
    }
    out = Path(out_path) if out_path else build_dir / "census.json"
    return _write_json(out, doc)


PRODUCERS: dict[str, Callable[..., Path]] = {
    "plume_field.json": write_plume_field_json,
    "geochemistry.json": write_geochemistry_json,
    "calibration_summary.json": write_calibration_summary_json,
    "pools_state.json": write_pools_state_json,
    # snow_cover.json lands before weather_snapshot.json so the terrain block can reference its values.
    "snow_cover.json": write_snow_cover_sidecar,
    "weather_snapshot.json": write_weather_snapshot_json,
    "overland_field.json": write_overland_field_json,
    "groundwater_field.json": write_groundwater_field_json,
    "census.json": write_census_sidecar,
}


def produce_all(build_dir: Path) -> tuple[dict[str, Path], list[str]]:
    """Run each producer against build_dir and return written paths and gaps.
Gaps are one-line strings describing why a sidecar was not written."""
    written: dict[str, Path] = {}
    gaps: list[str] = []
    for name, func in PRODUCERS.items():
        try:
            path = func(Path(build_dir))
            written[name] = path
        except MissingSourceError as exc:
            gaps.append(f"{name}: {exc}")
    return written, gaps
