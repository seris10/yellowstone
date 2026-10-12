"""M12 overland_flow: rainfall / infiltration / runoff on the midway grid.

Runs the standalone hydrosim model (rainfall -> infiltration -> overland
flow -> drainage) and writes the surface-water field to
derived/<build>/overland_flow.json. Baseline behaviour is unchanged when the
module is disabled.

Measured result on this terrain: the water balance closes and the surface
field stays at zero depth at every plausible rain rate, because the soil
takes the applied rain and no water leaves the domain edges (balance
outflow_m3 is 0.0 up to 80 mm/h). The field therefore carries no runoff
signal to drive patches or the Godot river shader, and nothing consumes it.
Snow hydrology supplies the runoff that does reach the boundary; see
snow_season.catchment_runoff_m3_s.

Status: illustrative. No calibrated hydrology, no bathymetry, no measured
runoff. Every coefficient is authored and labelled as such.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

from .vegetation import load_terrain

GRID = 1025
STEP = 4.0
HALF = 2048.0

# Authored defaults (illustrative). Rain on the Firehole is light and summer;
# these numbers are a scenario, not a measurement.
DEFAULT_RAIN_MM_H = 2.0
DEFAULT_SOIL = "sandy_loam"
DEFAULT_DT_S = 60.0
DEFAULT_SIM_S = 600.0
DEFAULT_GRID = 256
DEFAULT_CELL_M = 8.0

# Numerical slack for the duration loop, in seconds.
_EPS_S = 1e-9


def _finite(name: str, value) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, not boolean")
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _nonnegative(name: str, value) -> float:
    value = _finite(name, value)
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def _positive(name: str, value) -> float:
    value = _finite(name, value)
    if value <= 0:
        raise ValueError(f"{name} must be > 0")
    return value


def _positive_int(name: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    grid = int(value)
    if grid <= 0:
        raise ValueError(f"{name} must be > 0")
    return grid


def _downsample(field, src: int, dst: int) -> np.ndarray:
    """Block-mean a src x src grid to dst x dst.

    Source bounds are computed per destination cell (r0 = r * src // dst);
    every source cell contributes and non-divisible sizes cover the whole
    extent, trailing rows and columns included.
    """
    src = int(src)
    dst = int(dst)
    if src <= 0 or dst <= 0:
        raise ValueError("src and dst must be positive")
    if dst > src:
        raise ValueError("dst must not exceed src")
    arr = np.asarray(field, dtype=np.float64)
    if arr.size != src * src:
        raise ValueError("field size does not match the src grid")
    arr = arr.reshape(src, src)
    out = np.empty((dst, dst), dtype=np.float64)
    for r in range(dst):
        r0, r1 = r * src // dst, (r + 1) * src // dst
        for c in range(dst):
            c0, c1 = c * src // dst, (c + 1) * src // dst
            out[r, c] = arr[r0:r1, c0:c1].mean()
    return out


def _import_hydrosim():
    """Return (hydrosim module, provenance) or (None, reason).

    The module is picked up from the sibling hydrology checkout when it is
    not installed as a package; the path list is checked for duplicates so
    repeated calls cannot grow sys.path.
    """
    try:
        import hydrosim
        return hydrosim, "installed package"
    except ImportError:
        pass
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for d in (here, os.path.join(here, "..", "hydrology")):
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "hydrosim.py")):
            if d not in sys.path:
                sys.path.insert(0, d)
            break
    try:
        import hydrosim
        return hydrosim, f"sibling checkout at {d}"
    except ImportError:
        return None, "hydrosim not on the import path; surface field omitted"


def run_overland(world_root, *, rain_mm_h=DEFAULT_RAIN_MM_H, soil=DEFAULT_SOIL,
                 dt_s=DEFAULT_DT_S, sim_s=DEFAULT_SIM_S, grid=DEFAULT_GRID,
                 cell_m=DEFAULT_CELL_M):
    """Drive hydrosim on the midway terrain and return a renderable field.

    Returns {field, grid, cell_m, rain_mm_h, soil, seconds, status,
    configuration, provenance}. The field is surface-water depth in metres,
    dst x dst, row-major, suitable for a float texture. Empty when hydrosim
    is absent. seconds is the time actually simulated: a trailing partial
    step absorbs any remainder of sim_s / dt_s.
    """
    rain = _nonnegative("rain_mm_h", rain_mm_h)
    dt = _positive("dt_s", dt_s)
    sim_seconds = _nonnegative("sim_s", sim_s)
    grid = _positive_int("grid", grid)
    cell = _positive("cell_m", cell_m)
    if not isinstance(soil, str):
        raise ValueError("soil must be a string")

    hs, hs_prov = _import_hydrosim()
    if hs is None:
        return {"field": [], "grid": grid, "cell_m": cell,
                "rain_mm_h": rain, "soil": soil, "seconds": sim_seconds,
                "status": "not_available", "provenance": hs_prov}
    if soil not in hs.SOILS:
        raise ValueError(f"unknown soil type {soil!r}; "
                         f"have {sorted(hs.SOILS)}")
    if grid > GRID:
        raise ValueError(f"grid must not exceed the source DEM ({GRID})")

    z = load_terrain(str(world_root / "data" / "terrain.f32"))

    # Coarse the 1025-cell 4 m DEM onto the sim grid so the model sees real
    # relief instead of a synthetic bump. Block-mean preserves basin scale.
    zc = _downsample(z.reshape(-1), GRID, grid)

    # A uniform soil map for the requested texture: the elevation-banded
    # default map would silently ignore the soil argument.
    smap = np.zeros(zc.shape, dtype=int)
    names = [soil]

    cfg = hs.HydroConfig(infiltration="green_ampt", open_edges=(),
                         enable_et=True, perc_factor=1.0,
                         manning_overland=0.08, max_substeps=40)
    sim = hs.HydroSim(zc, cell, soil_map=smap, soil_names=names,
                      rain=hs.RainField((grid, grid), cell, mode="uniform"),
                      config=cfg, climate=hs.Climate(), init_wetness=0.5)

    elapsed = 0.0
    remaining = sim_seconds
    while remaining > _EPS_S:
        step = min(dt, remaining)
        sim.step(step, rain)
        elapsed += step
        remaining -= step

    field = np.asarray(sim.depth_map(), dtype=np.float64).reshape(-1)
    b = sim.balance()
    balance = {"rain_m3": round(float(b["rain"]), 3),
               "outflow_m3": round(float(b["outflow"]), 3),
               "et_m3": round(float(b["et_surface"] + b["et_soil"]), 3),
               "rel_error": float(b["rel_error"])}
    if not all(math.isfinite(v) for v in balance.values()):
        return {"schema": "yellowstone.overland_flow.v1",
                "field": [float(v) for v in field], "grid": grid,
                "cell_m": cell, "rain_mm_h": rain, "soil": soil,
                "seconds": elapsed, "status": "balance_invalid",
                "balance": balance,
                "provenance": "hydrosim water balance produced a non-finite "
                              "value; field published, balance rejected"}
    nonzero = sum(1 for v in field if v != 0.0)
    surface = {"nonzero_cells": nonzero,
               "max_depth_m": round(float(max(field)), 9) if len(field) else 0.0,
               "outflow_m3": balance["outflow_m3"],
               "carries_runoff_signal": nonzero > 0
               and balance["outflow_m3"] > 0.0}
    if not surface["carries_runoff_signal"]:
        surface["note"] = ("no water left the domain, so the field holds no "
                           "runoff signal for patches or the river shader")
    return {"schema": "yellowstone.overland_flow.v1",
            "field": [float(v) for v in field], "grid": grid,
            "cell_m": cell, "rain_mm_h": rain, "soil": soil,
            "seconds": elapsed, "status": "illustrative_not_calibrated",
            "balance": balance,
            "surface_runoff": surface,
            "configuration": {
                "soil": soil, "soil_map": "uniform_requested_soil",
                "infiltration": cfg.infiltration,
                "manning_overland": cfg.manning_overland,
                "enable_et": cfg.enable_et, "perc_factor": cfg.perc_factor,
                "init_wetness": 0.5, "max_substeps": cfg.max_substeps,
                "open_edges": list(cfg.open_edges),
                "source_dem_cells": [GRID, GRID], "source_cell_m": STEP,
                "sim_grid": grid, "sim_cell_m": cell,
                "downsampling": "block_mean_full_extent",
                "hydrosim": hs_prov},
            "provenance": ("hydrosim local-inertial shallow water on a "
                           "block-mean of terrain.f32; authored rain/soil; "
                           "no calibration, no bathymetry")}
