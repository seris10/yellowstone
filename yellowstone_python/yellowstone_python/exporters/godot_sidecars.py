"""Producers for Godot-side sidecar files from a published build directory.
Each producer writes JSON with schema id, units and status, or raises MissingSourceError on absent inputs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..common.provenance import CONTRACT_VERSION, WORLD_ID


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
SITE_LATITUDE_DEG = 44.459333
SITE_LONGITUDE_DEG = -110.822272

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
    if not path.is_file():
        raise MissingSourceError(f"{label} not found at {path}")
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except json.JSONDecodeError as exc:
        raise MissingSourceError(
            f"{label} at {path} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise MissingSourceError(f"{label} at {path} is not a JSON object")
    return value


def _reach_by_id(reaches: list, rid: str) -> dict | None:
    for r in reaches:
        if r.get("id") == rid:
            return r
    return None


def _write_json(out_path: Path, doc: dict) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(doc, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8")
    return out_path


def write_plume_field_json(build_dir: Path,
                           out_path: Path | None = None) -> Path:
    """Write a 2-D plume field sidecar from the mapped river state.
    Grid matches hydro_thermal.plume_map.png; traces to Excelsior mouth and Firehole bridge temperatures."""
    build_dir = Path(build_dir)
    river_state_path = build_dir / "river_state.json"
    if not river_state_path.is_file():
        raise MissingSourceError(
            f"river_state.json not found at {river_state_path}")
    try:
        with river_state_path.open(encoding="utf-8") as handle:
            river_state_doc = json.load(handle)
    except json.JSONDecodeError as exc:
        raise MissingSourceError(
            f"river_state.json at {river_state_path} is not valid JSON: "
            f"{exc}") from exc
    if isinstance(river_state_doc, list):
        reaches = river_state_doc
    elif isinstance(river_state_doc, dict):
        reaches = river_state_doc.get("river_state") or []
    else:
        raise MissingSourceError(
            "river_state.json must be a list or an object with river_state")
    if not reaches:
        raise MissingSourceError(
            "river_state.json contains no reaches; cannot build plume field")
    hot = _reach_by_id(reaches, EXCELSIOR_REACH_ID)
    cool = _reach_by_id(reaches, BRIDGE_REACH_ID) or reaches[-1]
    if hot is None or "temperature_c" not in hot:
        raise MissingSourceError(
            f"reach {EXCELSIOR_REACH_ID!r} with temperature_c missing from "
            f"river_state.json")
    if "temperature_c" not in cool:
        raise MissingSourceError(
            "bridge reach lacks temperature_c in river_state.json")
    from ..replay.plume2d import solve_steady
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
    Quartz solubility per Fournier 1977 no-steam-loss; cells without SiO2 obs flag no_observation."""
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
    from ..geochemistry import diagnose_replay_frame
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
    """Reach heat fit scalars plus the observed USGS gauge trace.
    Searches derived/ when fit_path or obs_path is absent; trace reduces to the first gauge site's series."""
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
                  "discharge_m3_s": "m^3 s^-1",
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
    """Per-pool thermal state exported for the Godot pool overlay.
    Reads pool_shells.json and emits center and edge temperatures per pool; status labels authored-steady and names the dynamic coupling that will replace it."""
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
    """Per-patch snow_cover_fraction sidecar (fixes-39 item 4 phase 2).
    Prefers the explicit snow_cover_fraction field in season.json; otherwise derives it from snow_depth_m via SNOW_COVER_FULL_DEPTH_M."""
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
    """Schema version 2 weather snapshot for the Godot reader.
    Pulls air, humidity, wind, and cloud from build/weather.json; snow fraction from the microclimate wet-bulb path; solar angles from microclimate.solar_snapshot."""
    import math
    build_dir = Path(build_dir)
    weather_src = build_dir / "weather.json"
    if not weather_src.is_file():
        raise MissingSourceError(
            f"weather.json not found at {weather_src}; build did not run the "
            f"weather module")
    source_doc = _load_json(weather_src, "weather.json")
    weather = source_doc.get("weather") or {}
    air_c = float(weather.get("night_air_c", 7.0))
    rh = float(weather.get("humidity", 0.45))
    cloud = float(weather.get("cloud", 0.16))
    wind_vector = weather.get("wind_xz_mps") or [1.8, 0.6]
    try:
        wx = float(wind_vector[0])
        wz = float(wind_vector[1])
    except (TypeError, ValueError, IndexError):
        wx, wz = 1.8, 0.6
    wind_speed_mps = math.hypot(wx, wz)
    wind_direction_deg = _wind_direction_from_vector(wx, wz)
    met_bundle_flag = bool(weather.get("met_bundle"))
    forcing_mode = ("measured_absolute_temperature" if met_bundle_flag
                    else "authored_defaults")

    # Snow fraction via microclimate wet-bulb path when importable; else zero authored.
    snow_fraction = 0.0
    snow_partition_source = "authored_zero"
    try:
        from ..microclimate import metpy_wet_bulb_temperature
        t_w = metpy_wet_bulb_temperature(air_c, rh)
        snow_partition_source = "metpy_wet_bulb"
    except (ImportError, ValueError):
        t_w = None
    if t_w is None:
        rh_percent = max(0.0, min(100.0, rh * 100.0))
        if (-20.0 <= air_c <= 50.0) and (5.0 <= rh_percent <= 99.0):
            t_w = (
                air_c * math.atan(0.151977
                                  * math.sqrt(rh_percent + 8.313659))
                + math.atan(air_c + rh_percent)
                - math.atan(rh_percent - 1.676331)
                + 0.00391838 * (rh_percent ** 1.5)
                * math.atan(0.023101 * rh_percent)
                - 4.686035)
            snow_partition_source = "stull_2011_wet_bulb"
        else:
            snow_partition_source = (
                "unavailable_outside_stull_2011_validity_range")
    if t_w is not None:
        if t_w <= -1.0:
            snow_fraction = 1.0
        elif t_w >= 3.0:
            snow_fraction = 0.0
        else:
            snow_fraction = (3.0 - t_w) / 4.0

    # Precipitation from the met bundle only; authored modes leave zero and label the status.
    precipitation_rate_mm_h = 0.0
    precipitation_status = "unavailable"
    if met_bundle_flag:
        precipitation_status = "measured_bundle_available_but_hour_not_resolved"

    dewpoint_c = air_c - 20.0 * (1.0 - rh)

    now_unix = int(datetime.now(timezone.utc).timestamp())
    valid_time_unix = now_unix
    simulation_time_unix = now_unix

    solar_block = {
        "source": "unavailable",
        "latitude_deg": SITE_LATITUDE_DEG,
        "longitude_deg": SITE_LONGITUDE_DEG,
    }
    try:
        from ..microclimate import solar_snapshot
        solar_block = solar_snapshot(now_unix,
                                     latitude=SITE_LATITUDE_DEG,
                                     longitude=SITE_LONGITUDE_DEG)
    except (ImportError, ValueError):
        pass

    weather_block = {
        "air_temperature_c": round(air_c, 2),
        "relative_humidity": round(min(max(rh, 0.0), 1.0), 3),
        "wind_speed_mps": round(min(max(wind_speed_mps, 0.0), 65.0), 3),
        "wind_direction_deg": round(wind_direction_deg % 360.0, 1),
        "cloud_fraction": round(min(max(cloud, 0.0), 1.0), 3),
        "precipitation_rate_mm_h": round(precipitation_rate_mm_h, 3),
        "snow_fraction": round(min(max(snow_fraction, 0.0), 1.0), 3),
        "visibility_m": 24000.0,
        "dewpoint_c": round(dewpoint_c, 2),
        "cloud_base_agl_m": 1050.0,
        "cloud_thickness_m": 600.0,
    }
    source_block = {
        "analysis": ("RTMA_proxy_via_open_meteo_bundle" if met_bundle_flag
                     else "authored_defaults"),
        "forecast": None,
        "station_correction": None,
        "forcing_mode": forcing_mode,
        "precipitation_status": precipitation_status,
        "snow_partition_source": snow_partition_source,
        "note": ("weather bundle sourced from build/weather.json. "
                 "precipitation enters only through the met bundle; "
                 "no cloud-to-rain substitution."),
    }
    outdoc = {
        "schema_version": WEATHER_SNAPSHOT_SCHEMA_VERSION,
        "generated_at_unix": now_unix,
        "valid_time_unix": valid_time_unix,
        "simulation_time_unix": simulation_time_unix,
        "source": source_block,
        "weather": weather_block,
        "solar": solar_block,
    }
    # Terrain block emits only measured values and otherwise stays empty.
    terrain_block: dict = {}
    snow_cover_src = build_dir / "snow_cover.json"
    if snow_cover_src.is_file():
        try:
            snow_doc = _load_json(snow_cover_src, "snow_cover.json")
            fractions = [float(row.get("snow_cover_fraction", 0.0))
                         for row in snow_doc.get("patches", [])
                         if isinstance(row, dict)
                         and row.get("snow_cover_fraction") is not None]
            if fractions:
                terrain_block["snow_cover_fraction"] = round(
                    sum(fractions) / len(fractions), 4)
        except (OSError, MissingSourceError):
            pass
    if terrain_block:
        outdoc["terrain"] = terrain_block
    out = Path(out_path) if out_path else build_dir / "weather_snapshot.json"
    return _write_json(out, outdoc)


def validate_weather_snapshot_doc(doc: dict) -> list[str]:
    """Return a list of validation errors; empty means the doc passes the Godot reader's gates.
    Mirrors weather_snapshot_reader.gd checks for schema version, timestamps, required weather fields, and ranges."""
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
                  "outflow_m3": "m^3",
                  "surface_runoff.max_depth_m": "m",
                  "surface_runoff.outflow_m3": "m^3"},
        "provenance": source.get("provenance"),
    }
    out = Path(out_path) if out_path else build_dir / "overland_field.json"
    return _write_json(out, doc)


def write_groundwater_field_json(build_dir: Path,
                                 out_path: Path | None = None) -> Path:
    """Reserved groundwater field producer (fixes-33 item 2).
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
