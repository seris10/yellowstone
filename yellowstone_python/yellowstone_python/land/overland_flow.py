"""overland_flow: rainfall, infiltration, runoff on the midway grid.
Runs hydrosim and writes derived/<build>/overland_flow.json; illustrative."""
from __future__ import annotations

from pathlib import Path

from yellowstone_python.common.checks import finite as _finite, nonnegative as _nonnegative, positive as _positive, positive_int as _positive_int

import math
from yellowstone_python.land.hydrosim_loader import import_hydrosim as _import_hydrosim

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

from yellowstone_python.land.vegetation import load_terrain

GRID = 1025
STEP = 4.0
HALF = 2048.0

# Authored illustrative scenario defaults.
DEFAULT_RAIN_MM_H = 2.0
DEFAULT_SOIL = "sandy_loam"
DEFAULT_DT_S = 60.0
DEFAULT_SIM_S = 600.0
DEFAULT_GRID = 256
DEFAULT_CELL_M = 8.0

SCHEMA = "yellowstone.overland_flow.v1"
RUNOFF_SERIES_SCHEMA = "yellowstone.runoff_series.v1"

# Edge names accepted for open boundaries; must match hydrosim.HydroConfig.
VALID_EDGES = frozenset({"left", "right", "top", "bottom"})

# Numerical slack for the duration loop, in seconds.
_EPS_S = 1e-9










def _open_edges(value) -> tuple:
    """Validate open-edge names and return a de-duplicated tuple."""
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise ValueError("open_edges must be a sequence of edge names, "
                         "not a string")
    try:
        edges = list(value)
    except TypeError as exc:
        raise ValueError(
            "open_edges must be a sequence of edge names") from exc
    if any(not isinstance(e, str) for e in edges):
        raise ValueError("open_edges entries must be strings")
    unknown = set(edges) - VALID_EDGES
    if unknown:
        raise ValueError(f"unknown open edges: {sorted(unknown)}")
    return tuple(dict.fromkeys(edges))


class _RainSchedule:
    """Piecewise-constant, right-continuous rain rate in mm/h."""

    def __init__(self, times, values, mode):
        self.times = times
        self.values = values
        self.mode = mode

    @classmethod
    def parse(cls, rain, dt_s):
        if isinstance(rain, (str, bytes)):
            raise ValueError(
                "rain_mm_h must be numeric, a schedule mapping or a "
                "sequence of numbers")
        if isinstance(rain, dict):
            if "times_s" not in rain or "values" not in rain:
                raise ValueError(
                    "rain_mm_h mapping needs 'times_s' and 'values'")
            times = [_finite("rain times_s", t) for t in rain["times_s"]]
            values = [_nonnegative("rain_mm_h", v) for v in rain["values"]]
            mode = "piecewise_constant"
        elif isinstance(rain, (list, tuple, np.ndarray)):
            values = [_nonnegative("rain_mm_h", v) for v in rain]
            times = [i * dt_s for i in range(len(values))]
            mode = "per_step"
        else:
            return cls([0.0], [_nonnegative("rain_mm_h", rain)], "constant")
        if not values or len(times) != len(values):
            raise ValueError(
                "rain schedule needs matching nonempty times_s and values")
        if times[0] != 0.0:
            raise ValueError("rain schedule must start at time zero")
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError(
                "rain schedule times must be strictly increasing")
        return cls(times, values, mode)

    def at(self, t):
        index = 0
        for i, start in enumerate(self.times):
            if start <= t + _EPS_S:
                index = i
        return self.values[index]

    def next_break(self, t):
        for start in self.times:
            if start > t + _EPS_S:
                return start
        return math.inf

    def mean(self, duration):
        if duration <= 0.0:
            return self.values[0]
        total = 0.0
        for i, start in enumerate(self.times):
            end = (self.times[i + 1] if i + 1 < len(self.times)
                   else math.inf)
            lo, hi = start, min(end, duration)
            if hi > lo:
                total += self.values[i] * (hi - lo)
        return total / duration


def _downsample(field, src: int, dst: int) -> np.ndarray:
    """Block-mean a src x src grid to dst x dst (full-extent coverage)."""
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


def run_overland(world_root, *, rain_mm_h=DEFAULT_RAIN_MM_H, soil=DEFAULT_SOIL,
                 dt_s=DEFAULT_DT_S, sim_s=DEFAULT_SIM_S, grid=DEFAULT_GRID,
                 cell_m=DEFAULT_CELL_M, open_edges=(),
                 boundary_role="upstream_inflow"):
    """Drive hydrosim on the midway terrain and return a renderable field."""
    if not _HAS_NUMPY:
        return {"schema": SCHEMA, "field": [], "grid": int(grid),
                "cell_m": float(cell_m),
                "rain_mm_h": float(rain_mm_h) if isinstance(
                    rain_mm_h, (int, float)) else None,
                "soil": soil, "seconds": float(sim_s),
                "status": "not_available",
                "provenance": ("numpy not installed; overland_flow degrades "
                               "the same way as hydrosim")}
    dt = _positive("dt_s", dt_s)
    sim_seconds = _nonnegative("sim_s", sim_s)
    schedule = _RainSchedule.parse(rain_mm_h, dt)
    grid = _positive_int("grid", grid)
    cell = _positive("cell_m", cell_m)
    if not isinstance(soil, str):
        raise ValueError("soil must be a string")
    edges = _open_edges(open_edges)
    if boundary_role not in ("upstream_inflow", "lateral_source"):
        raise ValueError(
            "boundary_role must be 'upstream_inflow' or 'lateral_source'")
    if grid > GRID:
        raise ValueError(f"grid must not exceed the source DEM ({GRID})")
    rain_report = (schedule.values[0] if schedule.mode == "constant"
                   else schedule.mean(sim_seconds))

    hs, hs_prov = _import_hydrosim()
    if hs is None:
        return {"schema": SCHEMA, "field": [], "grid": grid, "cell_m": cell,
                "rain_mm_h": rain_report, "soil": soil,
                "seconds": sim_seconds, "status": "not_available",
                "provenance": hs_prov}
    if soil not in hs.SOILS:
        raise ValueError(f"unknown soil type {soil!r}; "
                         f"have {sorted(hs.SOILS)}")

    z = load_terrain(str(world_root / "data" / "terrain.f32"))

    # Coarse the 1025-cell 4 m DEM onto the sim grid; block-mean preserves basin scale.
    zc = _downsample(z.reshape(-1), GRID, grid)

    # Uniform soil map so the requested texture reaches the solver.
    smap = np.zeros(zc.shape, dtype=int)
    names = [soil]

    cfg = hs.HydroConfig(infiltration="green_ampt", open_edges=edges,
                         enable_et=True, perc_factor=1.0,
                         manning_overland=0.08, max_substeps=40)
    sim = hs.HydroSim(zc, cell, soil_map=smap, soil_names=names,
                      rain=hs.RainField((grid, grid), cell, mode="uniform"),
                      config=cfg, climate=hs.Climate(), init_wetness=0.5)

    elapsed = 0.0
    previous_outflow_m3 = 0.0
    step_start_s: list[float] = []
    step_dt_s: list[float] = []
    step_outflow_m3_s: list[float] = []
    cfl_exceeded_count = 0
    boundary_condition: str | None = None
    outflow_slope: float | None = None
    while sim_seconds - elapsed > _EPS_S:
        step = min(dt, sim_seconds - elapsed,
                   schedule.next_break(elapsed) - elapsed)
        info = sim.step(step, schedule.at(elapsed))
        if isinstance(info, dict):
            cfl_exceeded_count += int(info.get("cfl_exceeded_count", 0))
            if info.get("boundary_condition") is not None:
                boundary_condition = str(info["boundary_condition"])
            if info.get("outflow_slope") is not None:
                outflow_slope = float(info["outflow_slope"])
        cumulative = float(sim.balance()["outflow"])
        step_start_s.append(elapsed)
        step_dt_s.append(step)
        step_outflow_m3_s.append(
            max(0.0, cumulative - previous_outflow_m3) / step)
        previous_outflow_m3 = cumulative
        elapsed += step

    field = np.asarray(sim.depth_map(), dtype=np.float64).reshape(-1)
    b = sim.balance()
    balance = {"rain_m3": round(float(b["rain"]), 3),
               "outflow_m3": round(float(b["outflow"]), 3),
               "et_m3": round(float(b["et_surface"] + b["et_soil"]), 3),
               "rel_error": float(b["rel_error"])}
    rain_schedule = {"times_s": list(schedule.times),
                     "values_mm_h": list(schedule.values),
                     "mode": schedule.mode}
    outflow_series = {"times_s": step_start_s, "dt_s": step_dt_s,
                      "outflow_m3_s": step_outflow_m3_s,
                      "semantics": "interval_mean_right_continuous"}
    boundary_mode = "open_edges" if edges else "closed_domain"
    solver_diagnostics = {"cfl_exceeded_count": cfl_exceeded_count,
                          "boundary_condition": boundary_condition,
                          "outflow_slope": outflow_slope}
    if not all(math.isfinite(v) for v in balance.values()):
        return {"schema": SCHEMA,
                "field": [float(v) for v in field], "grid": grid,
                "cell_m": cell, "rain_mm_h": rain_report, "soil": soil,
                "rain_schedule": rain_schedule,
                "seconds": elapsed, "status": "balance_invalid",
                "balance": balance,
                "solver_diagnostics": solver_diagnostics,
                "configuration": {
                    "soil": soil, "soil_map": "uniform_requested_soil",
                    "infiltration": cfg.infiltration,
                    "manning_overland": cfg.manning_overland,
                    "enable_et": cfg.enable_et,
                    "perc_factor": cfg.perc_factor,
                    "init_wetness": 0.5,
                    "max_substeps": cfg.max_substeps,
                    "open_edges": list(edges),
                    "runoff_boundary_mode": boundary_mode,
                    "boundary_role": boundary_role,
                    "source_dem_cells": [GRID, GRID],
                    "source_cell_m": STEP,
                    "sim_grid": grid, "sim_cell_m": cell,
                    "downsampling": "block_mean_full_extent",
                    "hydrosim": hs_prov},
                "provenance": "hydrosim water balance produced a non-finite "
                              "value; field published, balance rejected"}
    nonzero = int(np.count_nonzero(field))
    surface = {"nonzero_cells": nonzero,
               "max_depth_m": (round(float(field.max()), 9)
                               if field.size else 0.0),
               "outflow_m3": balance["outflow_m3"],
               "carries_runoff_signal": (nonzero > 0
                                         and balance["outflow_m3"] > 0.0)}
    if not surface["carries_runoff_signal"]:
        surface["note"] = (
            "no water left the domain, so the field holds no runoff "
            "signal for patches or the river shader" if not edges else
            "no depth or outflow was produced for this forcing, so the "
            "field holds no runoff signal")
    status = "illustrative_not_calibrated"

    runoff_series = None
    if edges:
        runoff_series = {
            "schema": RUNOFF_SERIES_SCHEMA,
            "time": {"start_epoch_unix": None, "times_s": step_start_s,
                     "dt_s": step_dt_s, "n": len(step_start_s),
                     "semantics": "interval_mean_right_continuous"},
            "forcing": {"precipitation_mm_h": rain_schedule,
                        "soil": soil, "antecedent_wetness": 0.5},
            "discharge": {"m3_s": step_outflow_m3_s, "source": "hydrosim",
                          "routing": "none"},
            "temperature": {
                "values_c": None,
                "status": "not_provided_not_usable_for_heat_transport"},
            "uncertainty": {"type": "none_estimated",
                            "coverage_claim": None},
            "spatial": {"grid": grid, "cell_m": cell,
                        "surface_depth_field": "see top-level 'field'",
                        "outflow_m3": balance["outflow_m3"]},
            "provenance": {"status": status,
                           "boundary_mode": boundary_mode,
                           "boundary_role": boundary_role,
                           "open_edges": list(edges)},
        }

    return {"schema": SCHEMA,
            "field": [float(v) for v in field], "grid": grid,
            "cell_m": cell, "rain_mm_h": rain_report, "soil": soil,
            "rain_schedule": rain_schedule,
            "seconds": elapsed, "status": status,
            "balance": balance,
            "surface_runoff": surface,
            "outflow_series": outflow_series,
            "outflow_mapping_status": "not_available",
            "solver_diagnostics": solver_diagnostics,
            "runoff_series": runoff_series,
            "configuration": {
                "soil": soil, "soil_map": "uniform_requested_soil",
                "infiltration": cfg.infiltration,
                "manning_overland": cfg.manning_overland,
                "enable_et": cfg.enable_et, "perc_factor": cfg.perc_factor,
                "init_wetness": 0.5, "max_substeps": cfg.max_substeps,
                "open_edges": list(edges),
                "runoff_boundary_mode": boundary_mode,
                "boundary_role": boundary_role,
                "source_dem_cells": [GRID, GRID], "source_cell_m": STEP,
                "sim_grid": grid, "sim_cell_m": cell,
                "downsampling": "block_mean_full_extent",
                "hydrosim": hs_prov},
            "provenance": ("hydrosim local-inertial shallow water on a "
                           "block-mean of terrain.f32; authored rain/soil; "
                           "no calibration, no bathymetry")}
