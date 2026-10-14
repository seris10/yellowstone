"""Cached hydrosim run on Midway terrain.f32 that reports soil wetness from caller rain."""
from __future__ import annotations

from pathlib import Path

from yellowstone_python.common.checks import finite as _finite
from yellowstone_python.land.hydrosim_loader import import_hydrosim

import importlib
import math
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class HydrologySnapshot:
    precipitation_rate_mm_h: float | None
    ground_wetness_fraction: float | None
    state: dict[str, Any]
    status: str
    error: str | None = None


DEFAULT_SOIL = "sandy_loam"
DEFAULT_GRID = 32
DEFAULT_SIM_S = 60.0
SOURCE_CELLS = 1025
SOURCE_CELL_M = 4.0




class HydrologyProvider:
    """Optional cached hydrology service. Independent of HTTP handling."""

    def __init__(
        self,
        *,
        module_name: str = "hydrosim",
        ttl_s: float = 60.0,
        enabled: bool = True,
        terrain=None,
        terrain_dx_m: float = SOURCE_CELL_M,
        soil: str = DEFAULT_SOIL,
        grid: int = DEFAULT_GRID,
        sim_s: float = DEFAULT_SIM_S,
        refuse_on_cfl_overflow: bool = False,
    ):
        self.module_name = module_name
        self.refuse_on_cfl_overflow = bool(refuse_on_cfl_overflow)
        self.ttl_s = _finite("ttl_s", ttl_s)
        if self.ttl_s <= 0.0:
            raise ValueError("ttl_s must be positive")
        self.enabled = bool(enabled)
        if not isinstance(soil, str) or not soil:
            raise ValueError("soil must be a nonempty string")
        self.soil = soil
        self.grid = grid
        if isinstance(grid, bool) or int(grid) != grid or int(grid) <= 0:
            raise ValueError("grid must be a positive integer")
        self.grid = int(grid)
        self.sim_s = _finite("sim_s", sim_s)
        if self.sim_s <= 0.0:
            raise ValueError("sim_s must be positive")
        self.terrain = terrain
        self.terrain_dx_m = _finite("terrain_dx_m", terrain_dx_m)
        if self.terrain_dx_m <= 0.0:
            raise ValueError("terrain_dx_m must be positive")
        self._lock = threading.Lock()
        self._module = None
        self._key: tuple | None = None
        self._snapshot: HydrologySnapshot | None = None
        self._snapshot_time = 0.0

    def _load_module(self):
        if self._module is None:
            if self.module_name == "hydrosim":
                module, _ = import_hydrosim()
                if module is None:
                    raise ImportError("hydrosim not importable")
                self._module = module
            else:
                self._module = importlib.import_module(self.module_name)
        return self._module

    def _rain_for_hour(self, weather: dict, hour: float) -> float | None:
        hourly = weather.get("precipitation_mm_h_hourly")
        if isinstance(hourly, (list, tuple)) and hourly:
            index = int(float(hour)) % len(hourly)
            value = hourly[index]
            return None if value is None else _finite("hourly rain", value)
        raw = weather.get("precipitation_rate_mm_h")
        if raw is None:
            return None
        return _finite("precipitation_rate_mm_h", raw)

    def snapshot(self, *, weather: dict, hour: float) -> HydrologySnapshot:
        if not isinstance(weather, dict):
            raise ValueError("weather must be a mapping")
        hour = _finite("hour", hour)
        now = time.monotonic()
        rain = self._rain_for_hour(weather, hour)
        key = (
            self.enabled,
            self.module_name,
            self.soil,
            self.grid,
            self.sim_s,
            round(float(weather.get("air_c", 7.0)), 3),
            round(float(weather.get("humidity", 0.45)), 4),
            round(float(weather.get("wind_speed_m_s", 2.0)), 3),
            None if rain is None else round(rain, 4),
            round(hour, 2),
        )
        with self._lock:
            if (
                self._snapshot is not None
                and self._key == key
                and now - self._snapshot_time < self.ttl_s
            ):
                return self._snapshot
            if not self.enabled:
                return HydrologySnapshot(
                    precipitation_rate_mm_h=rain,
                    ground_wetness_fraction=None,
                    state={},
                    status="disabled",
                )
            if rain is None:
                return HydrologySnapshot(
                    precipitation_rate_mm_h=None,
                    ground_wetness_fraction=None,
                    state={},
                    status="no_precipitation_input",
                )
            if self.terrain is None:
                return HydrologySnapshot(
                    precipitation_rate_mm_h=rain,
                    ground_wetness_fraction=None,
                    state={},
                    status="no_terrain_input",
                )
            try:
                result = self._compute(weather=weather, hour=hour,
                                       rain_mm_h=rain)
            except (ImportError, OSError, ValueError, AttributeError,
                    TypeError) as exc:
                return HydrologySnapshot(
                    precipitation_rate_mm_h=rain,
                    ground_wetness_fraction=None,
                    state={},
                    status="unavailable",
                    error=f"{type(exc).__name__}: {exc}",
                )
            self._snapshot = result
            self._key = key
            self._snapshot_time = now
            return result

    def _compute(self, *, weather: dict, hour: float,
                 rain_mm_h: float) -> HydrologySnapshot:
        import numpy as np

        hydrosim = self._load_module()
        if self.soil not in hydrosim.SOILS:
            raise ValueError(
                f"unknown soil {self.soil!r}; have "
                f"{sorted(hydrosim.SOILS)}")
        from yellowstone_python.land.overland_flow import _downsample
        elevation = np.asarray(self.terrain, dtype=np.float64)
        side = int(round(float(elevation.size) ** 0.5))
        if side * side != elevation.size:
            raise ValueError("terrain must be a square grid")
        if self.grid > side:
            raise ValueError("sim grid must not exceed terrain grid")
        coarse = _downsample(elevation.reshape(-1), side, self.grid)
        cell_m = self.terrain_dx_m * side / self.grid
        smap = np.zeros(coarse.shape, dtype=int)
        climate = hydrosim.Climate(
            temp_c=float(weather.get("air_c", 7.0)),
            rel_humidity=float(weather.get("humidity", 0.45)) * 100.0,
            wind_u2=float(weather.get("wind_speed_m_s", 2.0)),
        )
        sim = hydrosim.HydroSim(
            coarse, cell_m, soil_map=smap, soil_names=[self.soil],
            rain=hydrosim.RainField(coarse.shape, cell_m, mode="uniform"),
            config=hydrosim.HydroConfig(
                infiltration="green_ampt", open_edges=(),
                enable_et=True, perc_factor=1.0,
                manning_overland=0.08, max_substeps=40),
            climate=climate, init_wetness=0.5)
        elapsed, remaining = 0.0, self.sim_s
        boundary_condition = None
        cfl_exceeded_count = 0
        while remaining > 1e-9:
            step = min(60.0, remaining)
            result = sim.step(step, rain_mm_h)
            if isinstance(result, dict):
                if "boundary_condition" in result:
                    boundary_condition = result["boundary_condition"]
                count = result.get("cfl_exceeded_count")
                if isinstance(count, (int, float)) and math.isfinite(count):
                    cfl_exceeded_count += int(count)
            elapsed += step
            remaining -= step
        wetness = float(np.asarray(sim.soil_saturation()).mean())
        balance = sim.balance()
        state = {
            "sim_grid": self.grid,
            "sim_cell_m": cell_m,
            "sim_seconds": elapsed,
            "soil": self.soil,
            "avg_soil_saturation": wetness,
            "balance_rel_error": float(balance["rel_error"]),
            "hydrosim": "local-inertial shallow water on terrain.f32",
            "boundary_condition": boundary_condition,
            "cfl_exceeded_count": int(cfl_exceeded_count),
        }
        if self.refuse_on_cfl_overflow and cfl_exceeded_count > 0:
            return HydrologySnapshot(
                precipitation_rate_mm_h=float(rain_mm_h),
                ground_wetness_fraction=None,
                state=state,
                status="refused_cfl_exceeded",
                error=f"hydrosim exceeded CFL in {cfl_exceeded_count} substeps",
            )
        return HydrologySnapshot(
            precipitation_rate_mm_h=float(rain_mm_h),
            ground_wetness_fraction=wetness,
            state=state,
            status="ok",
        )
