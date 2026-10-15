"""One-D river-temperature transport: finite-volume, backward-Euler tridiagonal, upwind advection,."""
from __future__ import annotations
from yellowstone_python.common.io import sha256_file

import copy
import numpy as np
from bisect import bisect_right
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from yellowstone_python.river.surface_flux import BUDGET_PARAM_KEYS, BudgetParams, MetState, describe_surface_model, flux_at, linearized, flux_array, linearized_array
from yellowstone_python.common.checks import finite, positive
from yellowstone_python.atmosphere.time_utils import UTC, timestamp_metadata

RHO_CP_J_M3_K = 4.186e6
ENERGY_REFERENCE_C = 0.0
SCHEMA = "yellowstone.river_transport.v1"

HYPORHEIC_SOURCE = (
    "Bencala and Walters (1983), Water Resources Research 19(3), 718-724, "
    "equations 1 and 2 transient-storage formulation; one main-channel to "
    "storage-zone pair per cell"
)

DEFAULT_MAX_SURFACE_ITERATIONS = 24
DEFAULT_SURFACE_TOLERANCE_C = 1e-7
DEFAULT_SURFACE_RELAXATION = 0.8

# Diagnostic thresholds for the backward-Euler advective and diffusive numbers.
COURANT_WARNING_THRESHOLD = 1.0
DIFFUSIVE_WARNING_THRESHOLD = 1.0

def series_dict(series: "Series") -> dict[str, list[float]]:
    """Normalize a Series to JSON-friendly {times_s, values} with Python lists."""
    return {
        "times_s": list(series.times_s),
        "values": list(series.values),
    }

@dataclass(frozen=True)
class Series:
    """Right-continuous, piecewise-constant forcing (first value from t=0, last extends indefinitely)."""

    times_s: tuple[float, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        times = tuple(
            finite("forcing time", t, minimum=0.0) for t in self.times_s
        )
        values = tuple(
            finite("forcing value", v) for v in self.values
        )

        if not times or len(times) != len(values):
            raise ValueError(
                "forcing times and values must be nonempty "
                "and equal-length"
            )
        if times[0] != 0.0:
            raise ValueError("forcing must begin at t=0")
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("forcing times must be strictly increasing")

        object.__setattr__(self, "times_s", times)
        object.__setattr__(self, "values", values)

    def at(self, time_s: float) -> float:
        time_s = finite("forcing evaluation time", time_s, minimum=0.0)
        return self.values[
            bisect_right(self.times_s, time_s) - 1
        ]

    def next_change(self, time_s: float) -> float:
        index = bisect_right(self.times_s, time_s)
        if index == len(self.times_s):
            return math.inf
        return self.times_s[index]

    @classmethod
    def parse(cls, value: Any) -> Series:
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            if set(value) != {"times_s", "values"}:
                raise ValueError(
                    "forcing objects require only times_s and values"
                )
            return cls(
                tuple(value["times_s"]),
                tuple(value["values"]),
            )
        return cls((0.0,), (finite("constant forcing", value),))

@dataclass(frozen=True)
class Cell:
    """A finite-volume cell in upstream-to-downstream order."""

    id: str
    length_m: float
    width_m: float
    volume_m3: float
    initial_c: float
    dispersion_m2_s: float = 0.0
    exchange_w_m2_k: float = 0.0
    geometry_status: str = "authored_not_measured"

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("cell id must be a nonempty string")

        for name in ("length_m", "width_m", "volume_m3"):
            object.__setattr__(
                self, name, positive(name, getattr(self, name))
            )

        for name in ("dispersion_m2_s", "exchange_w_m2_k"):
            object.__setattr__(
                self, name, finite(name, getattr(self, name), minimum=0.0)
            )

        object.__setattr__(
            self, "initial_c", finite("initial_c", self.initial_c)
        )

    @property
    def cross_section_m2(self) -> float:
        return self.volume_m3 / self.length_m

    @property
    def surface_area_m2(self) -> float:
        return self.width_m * self.length_m

@dataclass(frozen=True)
class Source:
    """Lateral inflow with scheduled discharge and temperature at one cell."""

    id: str
    cell_id: str
    flow_m3_s: Any
    temperature_c: Any
    status: str = "illustrative_not_calibrated"

    def __post_init__(self) -> None:
        for name in ("id", "cell_id"):
            if not isinstance(getattr(self, name), str) or not getattr(
                self, name
            ):
                raise ValueError(f"{name} must be a nonempty string")

        flow = Series.parse(self.flow_m3_s)
        for value in flow.values:
            finite("source flow", value, minimum=0.0)
        object.__setattr__(self, "flow_m3_s", flow)
        object.__setattr__(
            self, "temperature_c", Series.parse(self.temperature_c)
        )

@dataclass(frozen=True)
class SurfaceBudget:
    """Explicit surface energy budget forcing."""

    rh: Series
    wind_mps: Series
    shortwave_w_m2: Series
    cloud: Series
    params: BudgetParams = BudgetParams()

    def __post_init__(self) -> None:
        for series in (self.rh, self.wind_mps, self.shortwave_w_m2,
                       self.cloud):
            if not isinstance(series, Series):
                raise ValueError("budget met inputs must be Series")
        for name, low, high in (("rh", 0.0, 1.0),
                                ("wind_mps", 0.0, None),
                                ("shortwave_w_m2", 0.0, None),
                                ("cloud", 0.0, 1.0)):
            for value in getattr(self, name).values:
                if high is None:
                    finite(f"budget {name}", value, minimum=low)
                elif not low <= value <= high:
                    raise ValueError(
                        f"budget {name} values must be in [{low}, {high}]")
        # Met series may have different end times; the solver splits at each change independently.
        if not isinstance(self.params, BudgetParams):
            raise ValueError("budget params must be BudgetParams")

    def met_at(self, time_s: float, air_c: float) -> MetState:
        return MetState(
            air_c=air_c, rh=self.rh.at(time_s),
            wind_mps=self.wind_mps.at(time_s),
            shortwave_w_m2=self.shortwave_w_m2.at(time_s),
            cloud=self.cloud.at(time_s))

    def to_dict(self) -> dict[str, Any]:
        # Full BudgetParams round-trip via asdict preserves calibrated multipliers and offsets.
        return {
            "rh": series_dict(self.rh),
            "wind_mps": series_dict(self.wind_mps),
            "shortwave_w_m2": series_dict(self.shortwave_w_m2),
            "cloud": series_dict(self.cloud),
            "params": asdict(self.params),
        }

    @classmethod
    def parse(cls, value: Any) -> SurfaceBudget:
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise ValueError("surface_budget must be an object")
        unknown = set(value) - {"rh", "wind_mps", "shortwave_w_m2",
                                "cloud", "params"}
        if unknown:
            raise ValueError(
                f"unknown surface_budget keys: {sorted(unknown)}")
        for key in ("rh", "wind_mps", "shortwave_w_m2", "cloud"):
            if key not in value:
                raise ValueError(f"surface_budget requires {key!r}")
        params = value.get("params", {})
        if not isinstance(params, dict):
            raise ValueError("surface_budget params must be an object")
        unknown_params = set(params) - BUDGET_PARAM_KEYS
        if unknown_params:
            raise ValueError(
                f"unknown surface_budget params: {sorted(unknown_params)}")
        try:
            budget_params = BudgetParams(**params)
        except TypeError as exc:
            raise ValueError(f"bad surface_budget params ({exc})") from exc
        return cls(
            Series.parse(value["rh"]), Series.parse(value["wind_mps"]),
            Series.parse(value["shortwave_w_m2"]),
            Series.parse(value["cloud"]), budget_params)


@dataclass(frozen=True)
class HyporheicZone:
    """Transient storage zone paired with one channel cell."""

    storage_volume_m3: float
    alpha_per_s: float
    initial_c: float | None = None
    status: str = "authored_until_measured"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "storage_volume_m3",
            positive("storage_volume_m3", self.storage_volume_m3))
        object.__setattr__(
            self, "alpha_per_s",
            finite("alpha_per_s", self.alpha_per_s, minimum=0.0))


class _Sum:
    """Compensated accumulation for long-run budget terms."""
    def __init__(self) -> None:
        self.total = 0.0
        self.correction = 0.0

    def add(self, value: float) -> None:
        updated = self.total + value
        if abs(self.total) >= abs(value):
            self.correction += (self.total - updated) + value
        else:
            self.correction += (value - updated) + self.total
        self.total = updated

    @property
    def value(self) -> float:
        return self.total + self.correction

def solve_tridiagonal(
    lower: list[float],
    diagonal: list[float],
    upper: list[float],
    rhs: list[float],
    cell_ids: list[str] | None = None,
) -> list[float]:
    """Thomas algorithm; transport matrix has nonpositive off-diagonals and positive pivots."""
    n = len(diagonal)
    if n == 0 or any(
        len(array) != n for array in (lower, upper, rhs)
    ):
        raise ValueError("invalid tridiagonal system")

    if any(
        not math.isfinite(value)
        for array in (lower, diagonal, upper, rhs)
        for value in array
    ):
        raise ArithmeticError("nonfinite matrix coefficient")

    d = diagonal.copy()
    b = rhs.copy()

    for i in range(n):
        if not math.isfinite(d[i]) or d[i] <= 0.0:
            cell_label = (
                cell_ids[i] if cell_ids and i < len(cell_ids)
                else f"index {i}"
            )
            dump = (
                f"lower={lower[i]:g} diagonal={d[i]:g} "
                f"upper={upper[i]:g} rhs={b[i]:g}"
            )
            raise ArithmeticError(
                f"singular or invalid matrix pivot at cell {cell_label}; "
                f"inputs {dump}"
            )

        if i + 1 < n:
            multiplier = lower[i + 1] / d[i]
            d[i + 1] -= multiplier * upper[i]
            b[i + 1] -= multiplier * b[i]

    result = [0.0] * n
    result[-1] = b[-1] / d[-1]

    for i in range(n - 2, -1, -1):
        result[i] = (
            b[i] - upper[i] * result[i + 1]
        ) / d[i]

    if any(not math.isfinite(value) for value in result):
        raise ArithmeticError("nonfinite temperature solution")

    return result

@dataclass(frozen=True)
class RiverState:
    """Store a solver checkpoint and its forcing schedules."""

    cell_ids: tuple[str, ...]
    time_s: float
    temperature_c: tuple[float, ...]
    hyporheic_t_c: tuple[float, ...]
    initial_c: tuple[float, ...]
    totals: tuple[tuple[str, float, float], ...]
    steps: int
    diagnostics: tuple[tuple[str, float], ...]
    forcing: tuple[Any, ...]


class River:
    """Stateful scientific engine, independent of rendering."""

    def __init__(
        self,
        cells: tuple[Cell, ...] | list[Cell],
        boundary_m3_s: Any,
        boundary_c: Any,
        sources: tuple[Source, ...] | list[Source] = (),
        air_c: Any = 7.0,
        net_heat_flux_w_m2: Any = 0.0,
        rho_cp_j_m3_k: float = RHO_CP_J_M3_K,
        surface_budget: Any = None,
        cell_heat_w: dict[str, Any] | None = None,
        max_surface_iterations: int = DEFAULT_MAX_SURFACE_ITERATIONS,
        surface_tolerance_c: float = DEFAULT_SURFACE_TOLERANCE_C,
        surface_relaxation: float = DEFAULT_SURFACE_RELAXATION,
        shortwave_multiplier: dict[str, float] | None = None,
        hyporheic_zones: dict[str, "HyporheicZone"] | None = None,
    ) -> None:
        self.cells = tuple(cells)
        self._vector_surface = True
        self._areas_m2 = np.asarray([cell.surface_area_m2 for cell in self.cells])
        self._volumes_m3 = np.asarray([cell.volume_m3 for cell in self.cells])
        self._source_qt_cache_time = None
        self._surface_old_linearization = None
        self.sources = tuple(sources)
        if not self.cells:
            raise ValueError("at least one river cell is required")

        self.rho_cp = positive("volumetric heat capacity", rho_cp_j_m3_k)
        # Boundary discharge accepts scalar or Series; face flows recompute each step so water budget closes.
        self._boundary_q_series = Series.parse(boundary_m3_s)
        for value in self._boundary_q_series.values:
            finite("boundary flow", value, minimum=0.0)
        self.boundary_q_series = self._boundary_q_series
        self.boundary_m3_s: float | Series
        if len(self._boundary_q_series.times_s) == 1:
            self.boundary_m3_s = float(
                self._boundary_q_series.values[0]
            )
        else:
            self.boundary_m3_s = self._boundary_q_series
        self.boundary_c = Series.parse(boundary_c)
        self.air_c = Series.parse(air_c)

        # Positive means energy entering the water; additive to Newton exchange.
        self.net_heat_flux = Series.parse(net_heat_flux_w_m2)

        self.surface_budget = (
            None if surface_budget is None
            else SurfaceBudget.parse(surface_budget)
        )

        # Per-cell heat power in watts; positive adds energy; accounted in the full budget.
        parsed_heat: dict[str, Series] = {}
        for cell_id, schedule in (cell_heat_w or {}).items():
            if cell_id not in {cell.id for cell in self.cells}:
                raise ValueError(
                    f"cell_heat_w names unknown cell {cell_id!r}"
                )
            parsed_heat[cell_id] = Series.parse(schedule)
        self._cell_heat = [
            parsed_heat.get(cell.id) for cell in self.cells
        ]

        indices = {cell.id: i for i, cell in enumerate(self.cells)}
        if len(indices) != len(self.cells):
            raise ValueError("duplicate cell ids")
        if len({s.id for s in self.sources}) != len(self.sources):
            raise ValueError("duplicate source ids")

        self._sources_by_cell: list[list[Source]] = [
            [] for _ in self.cells
        ]
        for source in self.sources:
            if source.cell_id not in indices:
                raise ValueError(
                    f"source {source.id!r} names unknown cell "
                    f"{source.cell_id!r}"
                )
            self._sources_by_cell[
                indices[source.cell_id]
            ].append(source)

        self._lateral_q = [
            math.fsum(s.flow_m3_s.at(0.0) for s in group)
            for group in self._sources_by_cell
        ]

        # face_flow_m3_s records t=0 flows for geometry diagnostics; the scheduled series governs the solver.
        self.face_flow_m3_s = self._face_flow_at(0.0)

        # Dispersive conductance (m3/s) per face: G = 1 / [Li/(2 Di Ai) + Lj/(2 Dj Aj)]; harmonic resistance.
        g = [0.0] * (len(self.cells) + 1)
        for j in range(1, len(self.cells)):
            left = self.cells[j - 1]
            right = self.cells[j]
            kl = left.dispersion_m2_s * left.cross_section_m2
            kr = right.dispersion_m2_s * right.cross_section_m2

            if kl > 0.0 and kr > 0.0:
                g[j] = 1.0 / (
                    left.length_m / (2.0 * kl)
                    + right.length_m / (2.0 * kr)
                )
        self.face_dispersion_m3_s = tuple(g)
        self._dispersion_array = np.asarray(g)

        forcing_series: list[Series] = [
            self._boundary_q_series,
            self.boundary_c,
            self.air_c,
            self.net_heat_flux,
        ]
        forcing_series.extend(source.temperature_c for source in self.sources)
        forcing_series.extend(source.flow_m3_s for source in self.sources)
        forcing_series.extend(
            series for series in self._cell_heat if series is not None
        )
        if self.surface_budget is not None:
            # Met schedules change the surface matrix; integrator splits at their change times.
            forcing_series.extend([
                self.surface_budget.rh,
                self.surface_budget.wind_mps,
                self.surface_budget.shortwave_w_m2,
                self.surface_budget.cloud,
            ])
        self._forcing = tuple(forcing_series)

        self._temperature_c = [
            cell.initial_c for cell in self.cells
        ]
        self._initial_c = tuple(self._temperature_c)
        self._time_s = 0.0
        self.steps = 0

        multipliers = [1.0] * len(self.cells)
        multiplier_applied = False
        if shortwave_multiplier is not None:
            indices = {cell.id: i for i, cell in enumerate(self.cells)}
            for cell_id, value in shortwave_multiplier.items():
                if cell_id not in indices:
                    raise ValueError(
                        f"shortwave_multiplier names unknown cell "
                        f"{cell_id!r}")
                scalar = finite(f"shortwave_multiplier[{cell_id!r}]", value, minimum=0.0)
                multipliers[indices[cell_id]] = scalar
                if scalar != 1.0:
                    multiplier_applied = True
        self._cell_shortwave_multiplier = tuple(multipliers)
        self._cell_shortwave_multiplier_applied = multiplier_applied

        self._hyporheic_zones: list[HyporheicZone | None] = [
            None for _ in self.cells
        ]
        self._hyporheic_t_c: list[float] = [0.0 for _ in self.cells]
        self._hyporheic_initial_c: list[float] = [0.0 for _ in self.cells]
        hyporheic_active = False
        if hyporheic_zones is not None:
            indices = {cell.id: i for i, cell in enumerate(self.cells)}
            for cell_id, zone in hyporheic_zones.items():
                if cell_id not in indices:
                    raise ValueError(
                        f"hyporheic_zones names unknown cell "
                        f"{cell_id!r}")
                if not isinstance(zone, HyporheicZone):
                    raise ValueError(
                        f"hyporheic_zones[{cell_id!r}] must be a "
                        f"HyporheicZone instance")
                idx = indices[cell_id]
                self._hyporheic_zones[idx] = zone
                initial = (self.cells[idx].initial_c
                           if zone.initial_c is None
                           else finite(f"hyporheic_zones[{cell_id!r}].initial_c", zone.initial_c))
                self._hyporheic_t_c[idx] = initial
                self._hyporheic_initial_c[idx] = initial
                hyporheic_active = True
        self._hyporheic_active = hyporheic_active

        self._totals = {
            name: _Sum()
            for name in (
                "boundary_input_j",
                "lateral_input_j",
                "outlet_export_j",
                "surface_exchange_j",
                "additional_heat_flux_j",
                "cell_heat_j",
                "surface_shortwave_j",
                "surface_longwave_j",
                "surface_sensible_j",
                "surface_latent_j",
                "boundary_input_m3",
                "lateral_input_m3",
                "outlet_export_m3",
                "hyporheic_exchange_j",
            )
        }

        self.max_step_heat_residual_j = 0.0
        self.max_cell_heat_residual_j = 0.0
        self.max_advective_courant = 0.0
        self.max_diffusive_number = 0.0
        self.max_surface_linearization_error_w = 0.0

        if (
            isinstance(max_surface_iterations, bool)
            or not isinstance(max_surface_iterations, int)
        ):
            raise ValueError(
                "max_surface_iterations must be an integer"
            )
        if max_surface_iterations < 1:
            raise ValueError(
                "max_surface_iterations must be positive"
            )
        self.max_surface_iterations = max_surface_iterations

        self.surface_tolerance_c = positive("surface_tolerance_c", surface_tolerance_c)
        self.surface_relaxation = finite("surface_relaxation", surface_relaxation)
        if not 0.0 < self.surface_relaxation <= 1.0:
            raise ValueError(
                "surface_relaxation must be in the interval (0, 1]"
            )

        self.max_surface_iterations_used = 0
        self.surface_iteration_failures = 0
        self.max_surface_newton_residual_c = 0.0

    @property
    def time_s(self) -> float:
        return self._time_s

    @property
    def temperature_c(self) -> tuple[float, ...]:
        return tuple(self._temperature_c)

    def _rebuild_forcing(self) -> None:
        series = [self._boundary_q_series, self.boundary_c, self.air_c, self.net_heat_flux]
        series.extend(source.temperature_c for source in self.sources)
        series.extend(source.flow_m3_s for source in self.sources)
        series.extend(value for value in self._cell_heat if value is not None)
        if self.surface_budget is not None:
            series.extend(getattr(self.surface_budget, key)
                          for key in ("rh", "wind_mps", "shortwave_w_m2", "cloud"))
        self._forcing = tuple(series)
        self.boundary_q_series = self._boundary_q_series
        self.boundary_m3_s = (self._boundary_q_series.values[0]
                             if len(self._boundary_q_series.values) == 1
                             else self._boundary_q_series)
        self._sources_by_cell = [[source for source in self.sources if source.cell_id == cell.id]
                                 for cell in self.cells]
        self._lateral_q = [math.fsum(source.flow_m3_s.at(0.0) for source in group)
                           for group in self._sources_by_cell]
        self._flow_cache_time = None
        self._source_qt_cache_time = None
        self.face_flow_m3_s = self._face_flow_at(self.time_s)

    def set_forcing(self, name: str, at_s: float, value: Any) -> None:
        """Schedule a forcing change at or after the current solver time."""
        at_s = finite("forcing change time", at_s, minimum=self.time_s)
        def changed(original: Series, lower=None, upper=None) -> Series:
            scalar = finite(name, value, minimum=lower, maximum=upper)
            kept = [(t, v) for t, v in zip(original.times_s, original.values) if t < at_s]
            kept.append((at_s, scalar))
            return Series(tuple(t for t, _ in kept), tuple(v for _, v in kept))
        attrs = {"boundary_m3_s": "_boundary_q_series", "boundary_c": "boundary_c",
                 "air_c": "air_c", "net_heat_flux_w_m2": "net_heat_flux"}
        if name in attrs:
            attr = attrs[name]
            setattr(self, attr, changed(getattr(self, attr), 0.0 if name == "boundary_m3_s" else None))
        elif name.startswith("surface_budget.") or name in ("rh", "wind_mps", "shortwave_w_m2", "cloud"):
            key = name.split(".")[-1]
            if self.surface_budget is None or key not in ("rh", "wind_mps", "shortwave_w_m2", "cloud"):
                raise ValueError(f"unknown surface forcing {name!r}")
            schedule = changed(getattr(self.surface_budget, key), 0.0,
                               1.0 if key in ("rh", "cloud") else None)
            self.surface_budget = replace(self.surface_budget, **{key: schedule})
        elif name.startswith("cell_heat_w."):
            key = name.removeprefix("cell_heat_w.")
            ids = [cell.id for cell in self.cells]
            if key not in ids:
                raise ValueError(f"unknown heat cell {key!r}")
            idx = ids.index(key)
            self._cell_heat[idx] = changed(self._cell_heat[idx] or Series.parse(0.0))
        elif name.startswith("source."):
            _, source_id, field = name.split(".", 2)
            if field not in ("flow_m3_s", "temperature_c"):
                raise ValueError(f"unknown source forcing {name!r}")
            found = False
            sources = []
            for source in self.sources:
                if source.id == source_id:
                    found = True
                    source = replace(source, **{field: changed(getattr(source, field),
                                      0.0 if field == "flow_m3_s" else None)})
                sources.append(source)
            if not found:
                raise ValueError(f"unknown source {source_id!r}")
            self.sources = tuple(sources)
        else:
            raise ValueError(f"unknown forcing {name!r}")
        self._rebuild_forcing()

    def checkpoint(self) -> RiverState:
        """Return an immutable checkpoint with conservation accumulators."""
        names = ("max_step_heat_residual_j", "max_cell_heat_residual_j",
                 "max_advective_courant", "max_diffusive_number",
                 "max_surface_linearization_error_w", "max_surface_iterations_used",
                 "surface_iteration_failures", "max_surface_newton_residual_c")
        return RiverState(tuple(cell.id for cell in self.cells), self.time_s, self.temperature_c,
                          tuple(self._hyporheic_t_c), self._initial_c,
                          tuple((key, value.total, value.correction) for key, value in self._totals.items()),
                          self.steps, tuple((key, getattr(self, key)) for key in names),
                          (self._boundary_q_series, self.boundary_c, self.air_c, self.net_heat_flux,
                           self.sources, self.surface_budget, tuple(self._cell_heat),
                           self._cell_shortwave_multiplier))

    def restore(self, state: RiverState) -> None:
        """Restore a checkpoint belonging to the same cell geometry."""
        if not isinstance(state, RiverState) or state.cell_ids != tuple(cell.id for cell in self.cells):
            raise ValueError("checkpoint cell geometry does not match river")
        self._time_s = state.time_s
        self._temperature_c = list(state.temperature_c)
        self._hyporheic_t_c = list(state.hyporheic_t_c)
        self._initial_c = state.initial_c
        self.steps = state.steps
        for key, total, correction in state.totals:
            self._totals[key].total, self._totals[key].correction = total, correction
        for key, value in state.diagnostics:
            setattr(self, key, value)
        (self._boundary_q_series, self.boundary_c, self.air_c, self.net_heat_flux,
         self.sources, self.surface_budget, heat, self._cell_shortwave_multiplier) = state.forcing
        self._cell_heat = list(heat)
        self._cell_shortwave_multiplier_applied = any(v != 1.0 for v in self._cell_shortwave_multiplier)
        self._rebuild_forcing()

    def _energy(self, temperatures: tuple | list) -> float:
        return self.rho_cp * math.fsum(
            cell.volume_m3 * (temperature - ENERGY_REFERENCE_C)
            for cell, temperature in zip(self.cells, temperatures)
        )

    def _cell_heat_at(self, time_s: float) -> list[float]:
        return [
            series.at(time_s) if series is not None else 0.0
            for series in self._cell_heat
        ]

    def _face_flow_at(self, time_s: float) -> tuple[float, ...]:
        """Face discharges in m3/s at the given time."""
        if getattr(self, "_flow_cache_time", None) == time_s:
            return self._flow_cache
        q = np.full(len(self.cells) + 1, self._boundary_q_series.at(time_s))
        for source in self.sources:
            index = next(i for i, cell in enumerate(self.cells) if cell.id == source.cell_id)
            q[index + 1:] += source.flow_m3_s.at(time_s)
        if np.any(~np.isfinite(q)):
            raise ValueError("derived face discharge must be finite")
        self._flow_cache_time, self._flow_cache = time_s, tuple(q.tolist())
        return self._flow_cache

    def _source_qt(self, time_s: float) -> list[float]:
        if self._source_qt_cache_time == time_s:
            return self._source_qt_cache
        source_qt = [0.] * len(self.cells)
        for source in self.sources:
            index = next(i for i, cell in enumerate(self.cells) if cell.id == source.cell_id)
            source_qt[index] = math.fsum((source_qt[index], source.flow_m3_s.at(time_s)
                                         * source.temperature_c.at(time_s)))
        self._source_qt_cache_time, self._source_qt_cache = time_s, source_qt
        return source_qt

    def _next_change(self) -> float:
        return min(
            series.next_change(self.time_s)
            for series in self._forcing
        )

    def _surface_linearization(
        self,
        cell_index: int,
        time_s: float,
        linearization_temperature: float | None = None,
    ) -> tuple[float, float, dict[str, float] | None]:
        """Surface matrix terms for one cell at the specified time."""
        cell = self.cells[cell_index]
        area = cell.surface_area_m2
        air = self.air_c.at(time_s)

        if self.surface_budget is None:
            exchange = cell.exchange_w_m2_k * area / self.rho_cp
            return exchange, exchange * air, None

        # Explicit budget supplies the surface flux; linearized implicitly F(T_new) ~= F0 + dF/dT * (T_new - T_old).
        met = self.surface_budget.met_at(time_s, air)
        multiplier = self._cell_shortwave_multiplier[cell_index]
        if multiplier != 1.0:
            met = MetState(
                air_c=met.air_c, rh=met.rh, wind_mps=met.wind_mps,
                shortwave_w_m2=multiplier * met.shortwave_w_m2,
                cloud=met.cloud,
                longwave_down_w_m2=met.longwave_down_w_m2)
        if linearization_temperature is None:
            linearization_temperature = self._temperature_c[cell_index]
        linearization_temperature = finite(f"surface linearization temperature cell {cell_index}", linearization_temperature)
        flux0, slope = linearized(
            linearization_temperature, met, self.surface_budget.params
        )
        exchange = -slope * area / self.rho_cp
        surface_rhs = (
            (flux0 - slope * linearization_temperature)
            * area
            / self.rho_cp
        )

        return exchange, surface_rhs, {
            "flux_at_linearization_temperature_w_m2": float(flux0),
            "flux_temperature_slope_w_m2_k": float(slope),
            "linearization_temperature_c": float(linearization_temperature),
            "air_temperature_c": float(air),
            "relative_humidity": float(met.rh),
            "wind_mps": float(met.wind_mps),
            "shortwave_w_m2": float(met.shortwave_w_m2),
            "cloud": float(met.cloud),
        }

    def _surface_power_for_accounting(
        self,
        temperatures: list[float],
        time_s: float,
    ) -> tuple[list[float], dict[str, list[float]] | None]:
        """Surface power at the converged temperature."""
        air = self.air_c.at(time_s)

        if self.surface_budget is None:
            return [
                cell.surface_area_m2 * cell.exchange_w_m2_k * (air - temperature)
                for cell, temperature in zip(self.cells, temperatures)
            ], None

        met = self.surface_budget.met_at(time_s, air)
        parts = flux_array(temperatures, met, self.surface_budget.params,
                           shortwave_multiplier=self._cell_shortwave_multiplier)
        areas = self._areas_m2
        if self._surface_old_linearization is None:
            old_flux, old_slope = linearized_array(self._temperature_c, met,
                                                 self.surface_budget.params,
                                                 shortwave_multiplier=self._cell_shortwave_multiplier)
        else:
            old_flux, old_slope = self._surface_old_linearization
        gap = parts["net"] - old_flux - old_slope * (
            np.asarray(temperatures) - np.asarray(self._temperature_c))
        self.max_surface_linearization_error_w = max(
            self.max_surface_linearization_error_w, float(np.max(np.abs(gap) * areas)))
        return ((areas * parts["net"]).tolist(),
                {name: (areas * parts[name]).tolist()
                 for name in ("shortwave", "longwave", "sensible", "latent")})

    def _system(
        self,
        time_s: float,
        dt_s: float | None = None,
        linearization_temperature: list[float] | None = None,
    ) -> tuple[list[float], list[float], list[float], list[float]]:
        """Build transport equations in temperature-volume units."""
        n = len(self.cells)
        if linearization_temperature is None:
            linearization_temperature = list(self._temperature_c)
        elif len(linearization_temperature) != n:
            raise ValueError(
                "linearization_temperature must have one value per cell"
            )
        if any(
            not math.isfinite(value)
            for value in linearization_temperature
        ):
            raise ValueError(
                "linearization_temperature contains a nonfinite value"
            )
        q = self._face_flow_at(time_s)
        g = self.face_dispersion_m3_s
        source_qt = self._source_qt(time_s)
        cell_heat = self._cell_heat_at(time_s)
        extra_flux = self.net_heat_flux.at(time_s)

        if self.surface_budget is not None and self._vector_surface:
            met = self.surface_budget.met_at(time_s, self.air_c.at(time_s))
            flux, slope = linearized_array(linearization_temperature, met,
                                          self.surface_budget.params,
                                          shortwave_multiplier=self._cell_shortwave_multiplier)
            if self._surface_old_linearization is None:
                self._surface_old_linearization = (flux, slope)
            area = self._areas_m2 / self.rho_cp
            qa, ga = np.asarray(q), self._dispersion_array
            lower = -(qa[:-1] + ga[:-1])
            lower[0] = 0.
            diagonal = qa[1:] + ga[:-1] + ga[1:] - slope * area
            upper = -ga[1:]
            upper[-1] = 0.
            rhs = (np.asarray(source_qt) + (flux - slope * np.asarray(linearization_temperature)) * area
                   + area * extra_flux + np.asarray(cell_heat) / self.rho_cp)
            if dt_s is not None:
                storage = self._volumes_m3 / dt_s
                diagonal += storage
                rhs += storage * np.asarray(self._temperature_c)
            rhs[0] += q[0] * self.boundary_c.at(time_s)
            return lower.tolist(), diagonal.tolist(), upper.tolist(), rhs.tolist()

        lower = [0.0] * n
        diagonal = [0.0] * n
        upper = [0.0] * n
        rhs = [0.0] * n

        vector_terms = None
        if self.surface_budget is not None and self._vector_surface:
            met = self.surface_budget.met_at(time_s, self.air_c.at(time_s))
            flux, slope = linearized_array(linearization_temperature, met,
                                          self.surface_budget.params,
                                          shortwave_multiplier=self._cell_shortwave_multiplier)
            areas = np.asarray([cell.surface_area_m2 for cell in self.cells]) / self.rho_cp
            vector_terms = ((-slope * areas).tolist(),
                            ((flux - slope * np.asarray(linearization_temperature)) * areas).tolist())

        for i, cell in enumerate(self.cells):
            area = cell.surface_area_m2
            if vector_terms is None:
                exchange, surface_rhs, _metadata = self._surface_linearization(
                    i, time_s, linearization_temperature=linearization_temperature[i])
            else:
                exchange, surface_rhs = vector_terms[0][i], vector_terms[1][i]

            lower[i] = -(q[i] + g[i]) if i > 0 else 0.0
            diagonal[i] = q[i + 1] + g[i] + g[i + 1] + exchange
            upper[i] = -g[i + 1] if i + 1 < n else 0.0

            rhs[i] = math.fsum((
                source_qt[i],
                surface_rhs,
                area * extra_flux / self.rho_cp,
                cell_heat[i] / self.rho_cp,
            ))

            if dt_s is not None:
                storage = cell.volume_m3 / dt_s
                diagonal[i] += storage
                rhs[i] += storage * self._temperature_c[i]

        rhs[0] += q[0] * self.boundary_c.at(time_s)
        return lower, diagonal, upper, rhs

    def _solve_system(self, lower, diagonal, upper, rhs):
        """Solve a validated transport matrix with a compiled tridiagonal pass."""
        if self.surface_budget is None or not self._vector_surface:
            return solve_tridiagonal(lower, diagonal, upper, rhs,
                                     cell_ids=[cell.id for cell in self.cells])
        from scipy.linalg import solve_banded
        banded = np.zeros((3, len(self.cells)))
        banded[0, 1:] = np.asarray(upper)[:-1]
        banded[1] = diagonal
        banded[2, :-1] = np.asarray(lower)[1:]
        try:
            result = solve_banded((1, 1), banded, np.asarray(rhs), check_finite=True)
        except (ValueError, np.linalg.LinAlgError) as error:
            raise ArithmeticError(f"invalid surface transport matrix: {error}") from error
        return result.tolist()

    def _solve_implicit_step(
        self,
        start_s: float,
        dt_s: float,
    ) -> tuple[list[float], int, float]:
        """Solve one implicit timestep."""
        if self.surface_budget is None:
            solution = solve_tridiagonal(
                *self._system(start_s, dt_s),
                cell_ids=[cell.id for cell in self.cells],
            )
            return solution, 1, 0.0

        self._surface_old_linearization = None
        old_temperature = list(self._temperature_c)
        guess = old_temperature.copy()
        last_update = math.inf

        for iteration in range(
            1,
            self.max_surface_iterations + 1,
        ):
            lower, diagonal, upper, rhs = self._system(
                start_s,
                dt_s,
                linearization_temperature=guess,
            )

            candidate = self._solve_system(lower, diagonal, upper, rhs)

            if len(candidate) != len(guess):
                raise ArithmeticError(
                    "surface iteration returned the wrong number "
                    "of temperatures"
                )

            if any(
                not math.isfinite(value)
                for value in candidate
            ):
                raise ArithmeticError(
                    "surface iteration produced a nonfinite temperature"
                )

            last_update = max(
                abs(new - previous)
                for new, previous in zip(candidate, guess)
            )

            if last_update <= self.surface_tolerance_c:
                self.max_surface_iterations_used = max(
                    self.max_surface_iterations_used,
                    iteration,
                )
                return candidate, iteration, last_update

            relaxation = self.surface_relaxation
            guess = [
                previous
                + relaxation * (new - previous)
                for previous, new in zip(guess, candidate)
            ]

            if any(
                not math.isfinite(value)
                for value in guess
            ):
                raise ArithmeticError(
                    "surface iteration produced a nonfinite damped guess"
                )

        self.surface_iteration_failures += 1
        raise ArithmeticError(
            "surface-budget Newton iteration did not converge after "
            f"{self.max_surface_iterations} iterations; "
            f"last maximum temperature update was "
            f"{last_update:.6g} C"
        )

    def _apply_hyporheic(self, new: list[float],
                         dt_s: float) -> tuple[float, list[float]]:
        """Analytic two-store exchange for cells with a hyporheic zone."""
        exchange_j = 0.0
        per_cell = [0.0] * len(self.cells)
        for i, zone in enumerate(self._hyporheic_zones):
            if zone is None:
                continue
            cell = self.cells[i]
            v_c = cell.volume_m3
            v_s = zone.storage_volume_m3
            t_c0 = new[i]
            t_s0 = self._hyporheic_t_c[i]
            total_v = v_c + v_s
            t_mix = (v_c * t_c0 + v_s * t_s0) / total_v
            delta0 = t_c0 - t_s0
            k = zone.alpha_per_s * (1.0 + v_c / v_s)
            decay = math.exp(-k * dt_s)
            delta_t = delta0 * decay
            t_c_new = t_mix + delta_t * v_s / total_v
            t_s_new = t_mix - delta_t * v_c / total_v
            cell_j = self.rho_cp * v_c * (t_c_new - t_c0)
            per_cell[i] = cell_j
            exchange_j += cell_j
            new[i] = t_c_new
            self._hyporheic_t_c[i] = t_s_new
        return exchange_j, per_cell

    def steady_temperatures(
        self,
        time_s: float = 0.0,
    ) -> tuple[float, ...]:
        """Steady solution with forcing frozen at the specified time."""
        time_s = finite("steady forcing time", time_s, minimum=0.0)
        return tuple(
            solve_tridiagonal(
                *self._system(time_s),
                cell_ids=[cell.id for cell in self.cells],
            )
        )

    def step(self, dt_s: float) -> dict[str, float]:
        """Advance one interval without crossing a forcing change."""
        dt_s = positive("dt_s", dt_s)
        end_s = finite("step end time", self.time_s + dt_s)

        if end_s <= self.time_s:
            raise ValueError("dt_s is below clock floating-point resolution")
        if end_s > self._next_change():
            raise ValueError(
                "step crosses a forcing change; use run() "
                "or split the interval"
            )

        return self._advance_to(end_s)

    def _advance_to(self, end_s: float) -> dict[str, float]:
        old = self._temperature_c
        start_s = self.time_s
        dt_s = end_s - start_s

        if dt_s <= 0.0 or end_s > self._next_change():
            raise ValueError("invalid integration interval")

        new, surface_iterations, surface_newton_residual_c = (
            self._solve_implicit_step(start_s, dt_s)
        )
        self.max_surface_newton_residual_c = max(
            self.max_surface_newton_residual_c,
            surface_newton_residual_c,
        )

        # Transport and surface fluxes are booked at the implicit-solve temperatures; the exchange split follows.
        transported = list(new)
        hyporheic_exchange_j = 0.0
        hyporheic_per_cell_j = [0.0] * len(self.cells)
        if self._hyporheic_active:
            hyporheic_exchange_j, hyporheic_per_cell_j = (
                self._apply_hyporheic(new, dt_s))

        q = self._face_flow_at(start_s)
        g = self.face_dispersion_m3_s
        source_qt = self._source_qt(start_s)
        cell_heat = self._cell_heat_at(start_s)
        extra_flux = self.net_heat_flux.at(start_s)

        # Advective + dispersive face fluxes, in m3*C/s.
        faces = [q[0] * self.boundary_c.at(start_s)]
        for j in range(1, len(self.cells)):
            faces.append(
                q[j] * transported[j - 1]
                + g[j] * (transported[j - 1] - transported[j])
            )
        faces.append(q[-1] * transported[-1])

        additional_heat_power_w = [
            cell.surface_area_m2 * extra_flux
            for cell in self.cells
        ]

        base_surface_power_w, component_power_w = (
            self._surface_power_for_accounting(transported, start_s)
        )

        surface_power_w = [
            base + additional
            for base, additional in zip(
                base_surface_power_w, additional_heat_power_w
            )
        ]

        increments = {
            "boundary_input_j": self.rho_cp * dt_s * faces[0],
            "lateral_input_j": (
                self.rho_cp * dt_s * math.fsum(source_qt)
            ),
            "outlet_export_j": self.rho_cp * dt_s * faces[-1],
            "surface_exchange_j": dt_s * math.fsum(base_surface_power_w),
            "additional_heat_flux_j": (
                dt_s * math.fsum(additional_heat_power_w)
            ),
            "cell_heat_j": dt_s * math.fsum(cell_heat),
            "hyporheic_exchange_j": hyporheic_exchange_j,
            "boundary_input_m3": dt_s * q[0],
            "lateral_input_m3": dt_s * math.fsum(source.flow_m3_s.at(start_s) for source in self.sources),
            "outlet_export_m3": dt_s * q[-1],
        }
        if component_power_w is not None:
            increments.update({
                f"surface_{name}_j": dt_s * math.fsum(powers)
                for name, powers in component_power_w.items()
            })
        else:
            increments.update({
                f"surface_{name}_j": 0.0
                for name in ("shortwave", "longwave",
                             "sensible", "latent")
            })

        storage_change_j = self.rho_cp * math.fsum(
            cell.volume_m3 * (after - before)
            for cell, before, after in zip(self.cells, old, new)
        )

        expected_change_j = math.fsum((
            increments["boundary_input_j"],
            increments["lateral_input_j"],
            -increments["outlet_export_j"],
            increments["surface_exchange_j"],
            increments["additional_heat_flux_j"],
            increments["cell_heat_j"],
            increments["hyporheic_exchange_j"],
        ))
        residual_j = storage_change_j - expected_change_j

        cell_residuals = []
        for i, cell in enumerate(self.cells):
            observed = (
                self.rho_cp
                * cell.volume_m3
                * (new[i] - old[i])
            )
            expected = self.rho_cp * dt_s * math.fsum((
                faces[i],
                -faces[i + 1],
                source_qt[i],
                surface_power_w[i] / self.rho_cp,
                cell_heat[i] / self.rho_cp,
            )) + hyporheic_per_cell_j[i]
            cell_residuals.append(abs(observed - expected))

        for name, value in increments.items():
            finite(name, value)
            self._totals[name].add(value)

        self.max_step_heat_residual_j = max(
            self.max_step_heat_residual_j, abs(residual_j)
        )
        self.max_cell_heat_residual_j = max(
            self.max_cell_heat_residual_j, max(cell_residuals)
        )

        self.max_advective_courant = max(
            self.max_advective_courant,
            max(
                q[i + 1] * dt_s / cell.volume_m3
                for i, cell in enumerate(self.cells)
            ),
        )
        self.max_diffusive_number = max(
            self.max_diffusive_number,
            max(
                (g[i] + g[i + 1]) * dt_s / cell.volume_m3
                for i, cell in enumerate(self.cells)
            ),
        )

        self._temperature_c = new
        self._time_s = end_s
        self.steps += 1

        # Solver diagnostics: Newton residual plus old/new temperature summary for per-step linearization quality.
        temperature_changes = [abs(a - b) for a, b in zip(new, old)]
        return {
            **increments,
            "dt_s": dt_s,
            "storage_change_j": storage_change_j,
            "heat_residual_j": residual_j,
            "max_cell_heat_residual_j": max(cell_residuals),
            "surface_iterations": surface_iterations,
            "surface_newton_residual_c": surface_newton_residual_c,
            "temperature_old_min_c": min(old),
            "temperature_old_max_c": max(old),
            "temperature_new_min_c": min(new),
            "temperature_new_max_c": max(new),
            "max_cell_temperature_change_c": (
                max(temperature_changes) if temperature_changes else 0.0
            ),
        }

    def budget(self) -> dict[str, Any]:
        totals = {
            name: accumulator.value
            for name, accumulator in self._totals.items()
        }

        initial_j = self._energy(self._initial_c)
        current_j = self._energy(self._temperature_c)

        # Direct differences avoid subtracting two large total energies.
        storage_change_j = self.rho_cp * math.fsum(
            cell.volume_m3 * (current - initial)
            for cell, initial, current in zip(
                self.cells, self._initial_c, self._temperature_c
            )
        )

        expected_change_j = math.fsum((
            totals["boundary_input_j"],
            totals["lateral_input_j"],
            -totals["outlet_export_j"],
            totals["surface_exchange_j"],
            totals["additional_heat_flux_j"],
            totals["cell_heat_j"],
            totals["hyporheic_exchange_j"],
        ))
        residual_j = storage_change_j - expected_change_j

        energy_scale = max(
            1.0,
            abs(initial_j),
            abs(current_j),
            math.fsum(
                abs(totals[name])
                for name in (
                    "boundary_input_j",
                    "lateral_input_j",
                    "outlet_export_j",
                    "surface_exchange_j",
                    "additional_heat_flux_j",
                    "cell_heat_j",
                    "hyporheic_exchange_j",
                )
            ),
        )

        surface_component_sum_j = math.fsum(
            totals[name]
            for name in (
                "surface_shortwave_j",
                "surface_longwave_j",
                "surface_sensible_j",
                "surface_latent_j",
            )
        )

        surface_component_difference_j = (
            surface_component_sum_j
            - totals["surface_exchange_j"]
        )

        water_residual_m3 = math.fsum((
            totals["boundary_input_m3"],
            totals["lateral_input_m3"],
            -totals["outlet_export_m3"],
        ))
        water_scale = max(
            1.0,
            abs(totals["boundary_input_m3"]),
            abs(totals["lateral_input_m3"]),
            abs(totals["outlet_export_m3"]),
        )

        numerical_warnings: list[str] = []
        if self.max_advective_courant > COURANT_WARNING_THRESHOLD:
            numerical_warnings.append(
                "advective Courant number "
                f"{self.max_advective_courant:.3g} exceeds "
                f"{COURANT_WARNING_THRESHOLD}; thermal fronts may be smeared"
            )
        if self.max_diffusive_number > DIFFUSIVE_WARNING_THRESHOLD:
            numerical_warnings.append(
                "diffusive number "
                f"{self.max_diffusive_number:.3g} exceeds "
                f"{DIFFUSIVE_WARNING_THRESHOLD}; dispersive step is coarse"
            )

        hyporheic_block: dict[str, Any] | None = None
        combined_residual_j: float | None = None
        combined_relative_residual: float | None = None
        if self._hyporheic_active:
            storage_energy_change_j = self.rho_cp * math.fsum(
                zone.storage_volume_m3 * (current - initial)
                for zone, initial, current in zip(
                    self._hyporheic_zones,
                    self._hyporheic_initial_c,
                    self._hyporheic_t_c)
                if zone is not None
            )
            combined_storage_change_j = storage_change_j + storage_energy_change_j
            combined_expected_change_j = math.fsum((
                totals["boundary_input_j"],
                totals["lateral_input_j"],
                -totals["outlet_export_j"],
                totals["surface_exchange_j"],
                totals["additional_heat_flux_j"],
                totals["cell_heat_j"],
            ))
            combined_residual_j = (combined_storage_change_j
                                   - combined_expected_change_j)
            combined_relative_residual = (
                abs(combined_residual_j) / energy_scale)
            hyporheic_block = {
                "cells_with_zone": sum(1 for z in self._hyporheic_zones
                                       if z is not None),
                "storage_energy_change_j": storage_energy_change_j,
                "combined_storage_change_j": combined_storage_change_j,
                "combined_expected_change_j": combined_expected_change_j,
                "combined_residual_j": combined_residual_j,
                "combined_relative_residual": combined_relative_residual,
                "storage_temperature_c": [
                    (self._hyporheic_t_c[i]
                     if self._hyporheic_zones[i] is not None else None)
                    for i in range(len(self.cells))
                ],
                "source": HYPORHEIC_SOURCE,
            }

        return {
            **totals,
            "steps": self.steps,
            "initial_sensible_energy_j": initial_j,
            "current_sensible_energy_j": current_j,
            "storage_change_j": storage_change_j,
            "expected_change_j": expected_change_j,
            "heat_residual_j": residual_j,
            "heat_relative_residual": abs(residual_j) / energy_scale,
            "water_residual_m3": water_residual_m3,
            "water_relative_residual": (
                abs(water_residual_m3) / water_scale
            ),
            "hyporheic": hyporheic_block,
            "max_step_heat_residual_j": (
                self.max_step_heat_residual_j
            ),
            "max_cell_heat_residual_j": (
                self.max_cell_heat_residual_j
            ),
            "max_surface_linearization_error_w": (
                self.max_surface_linearization_error_w
            ),
            "surface_component_sum_j": surface_component_sum_j,
            "surface_component_difference_j": (
                surface_component_difference_j
            ),
            "max_advective_courant": self.max_advective_courant,
            "max_diffusive_number": self.max_diffusive_number,
            "courant_warning_threshold": COURANT_WARNING_THRESHOLD,
            "diffusive_warning_threshold": DIFFUSIVE_WARNING_THRESHOLD,
            "numerical_warnings": numerical_warnings,
            "max_surface_iterations_used": (
                self.max_surface_iterations_used
            ),
            "surface_iteration_failures": (
                self.surface_iteration_failures
            ),
            "max_surface_newton_residual_c": (
                self.max_surface_newton_residual_c
            ),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "t_s": self.time_s,
            "temperature_c": list(self.temperature_c),
            "budget": self.budget(),
        }

    def run(
        self,
        duration_s: float,
        dt_s: float = 1.0,
        sample_s: float = 60.0,
    ) -> list[dict[str, Any]]:
        """Advance for duration_s, preserving forcing-change times."""
        duration_s = finite("duration_s", duration_s, minimum=0.0)
        dt_s = positive("dt_s", dt_s)
        sample_s = positive("sample_s", sample_s)

        start_s = self.time_s
        finish_s = finite("run finish time", start_s + duration_s)
        frames = [self.snapshot()]

        if duration_s > 0.0 and finish_s <= start_s:
            raise ValueError("duration is below clock resolution")

        sample_index = 1
        while self.time_s < finish_s:
            target_s = min(
                finish_s,
                start_s + sample_index * sample_s,
            )
            if target_s <= self.time_s:
                raise ArithmeticError("sample clock failed to advance")

            while self.time_s < target_s:
                end_s = min(
                    target_s,
                    self.time_s + dt_s,
                    self._next_change(),
                )
                if end_s <= self.time_s:
                    raise ArithmeticError(
                        "integration clock failed to advance"
                    )
                self._advance_to(end_s)

            frames.append(self.snapshot())
            sample_index += 1

        return frames

    def geometry_records(self) -> list[dict[str, Any]]:
        records = []
        chainage_m = 0.0

        for i, cell in enumerate(self.cells):
            q_out = self.face_flow_m3_s[i + 1]
            records.append({
                **asdict(cell),
                "start_s_m": chainage_m,
                "center_s_m": chainage_m + cell.length_m / 2.0,
                "end_s_m": chainage_m + cell.length_m,
                "cross_section_m2": cell.cross_section_m2,
                "surface_area_m2": cell.surface_area_m2,
                "q_in_m3_s": self.face_flow_m3_s[i],
                "q_out_m3_s": q_out,
                "representative_velocity_m_s": (
                    q_out / cell.cross_section_m2
                ),
                "nominal_residence_s": (
                    cell.volume_m3 / q_out if q_out > 0.0 else None
                ),
            })
            chainage_m += cell.length_m

        return records

def _parse_hyporheic_zones(
    value: Any,
) -> dict[str, HyporheicZone] | None:
    """Convert a mapping of dicts into HyporheicZone values."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("hyporheic_zones must be an object")
    out: dict[str, HyporheicZone] = {}
    for cell_id, record in value.items():
        if not isinstance(cell_id, str) or not cell_id:
            raise ValueError("hyporheic_zones keys must be nonempty strings")
        if isinstance(record, HyporheicZone):
            out[cell_id] = record
            continue
        if not isinstance(record, dict):
            raise ValueError(
                f"hyporheic_zones[{cell_id!r}] must be an object")
        allowed_fields = {"storage_volume_m3", "alpha_per_s",
                          "initial_c", "status"}
        unknown = set(record) - allowed_fields
        if unknown:
            raise ValueError(
                f"hyporheic_zones[{cell_id!r}] has unknown keys: "
                f"{sorted(unknown)}")
        out[cell_id] = HyporheicZone(
            storage_volume_m3=record["storage_volume_m3"],
            alpha_per_s=record["alpha_per_s"],
            initial_c=record.get("initial_c"),
            status=record.get("status", "authored_until_measured"),
        )
    return out


def river_from_config(config: dict[str, Any]) -> River:
    allowed = {
        "cells", "sources", "boundary_m3_s", "boundary_c",
        "air_c", "net_heat_flux_w_m2", "rho_cp_j_m3_k",
            "surface_budget", "cell_heat_w",
            "max_surface_iterations", "surface_tolerance_c",
            "surface_relaxation",
            "duration_s", "dt_s", "sample_s", "initialize_steady",
            "status", "parameter_notes",
            "simulation_start_utc", "simulation_start_epoch_unix",
            "shortwave_multiplier", "hyporheic_zones",
        }
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(
            f"unknown configuration keys: {sorted(unknown)}"
        )

    kwargs = {
        "cells": tuple(Cell(**row) for row in config["cells"]),
        "sources": tuple(
            Source(**row) for row in config.get("sources", [])
        ),
        "boundary_m3_s": config["boundary_m3_s"],
        "boundary_c": config["boundary_c"],
        "air_c": config.get("air_c", 7.0),
        "net_heat_flux_w_m2": config.get(
            "net_heat_flux_w_m2", 0.0
        ),
        "rho_cp_j_m3_k": config.get(
            "rho_cp_j_m3_k", RHO_CP_J_M3_K
        ),
        "surface_budget": config.get("surface_budget"),
        "cell_heat_w": config.get("cell_heat_w"),
        "max_surface_iterations": config.get(
            "max_surface_iterations",
            DEFAULT_MAX_SURFACE_ITERATIONS,
        ),
        "surface_tolerance_c": config.get(
            "surface_tolerance_c",
            DEFAULT_SURFACE_TOLERANCE_C,
        ),
        "surface_relaxation": config.get(
            "surface_relaxation",
            DEFAULT_SURFACE_RELAXATION,
        ),
        "shortwave_multiplier": config.get("shortwave_multiplier"),
        "hyporheic_zones": _parse_hyporheic_zones(
            config.get("hyporheic_zones")),
    }
    river = River(**kwargs)

    initialize_steady = config.get("initialize_steady", False)
    if not isinstance(initialize_steady, bool):
        raise ValueError("initialize_steady must be boolean")

    if initialize_steady:
        equilibrium = river.steady_temperatures()
        kwargs["cells"] = tuple(
            replace(cell, initial_c=temperature)
            for cell, temperature in zip(river.cells, equilibrium)
        )
        river = River(**kwargs)

    return river

def demo_config() -> dict[str, Any]:
    """Synthetic channel and source-temperature pulse."""
    return {
        "status": "synthetic_demonstration_not_calibrated",
        "parameter_notes": {
            "geometry": (
                "Synthetic 3000 m channel; 22 m surface width and "
                "1.1 m mean depth are assumptions, not cross-section data."
            ),
            "boundary": "8 m3/s and 17.5 C are illustrative.",
            "source": (
                "0.252 m3/s is an illustrative assignment near the "
                "descriptive Excelsior discharge reference; not a "
                "measurement of this synthetic outlet."
            ),
            "pulse": (
                "62 -> 80 -> 62 C is a demonstration intervention, "
                "not a recorded thermal event."
            ),
            "dispersion": "1 m2/s is illustrative, not fitted.",
            "exchange": (
                "12 W/(m2 K) is a lumped illustrative coefficient, "
                "not a full surface energy balance."
            ),
        },
        "boundary_m3_s": 8.0,
        "boundary_c": 17.5,
        "air_c": 9.0,
        "net_heat_flux_w_m2": 0.0,
        "duration_s": 14400.0,
        "dt_s": 10.0,
        "sample_s": 60.0,
        "initialize_steady": True,
        "cells": [
            {
                "id": f"channel_{i:03d}",
                "length_m": 50.0,
                "width_m": 22.0,
                "volume_m3": 50.0 * 22.0 * 1.1,
                "initial_c": 17.5,
                "dispersion_m2_s": 1.0,
                "exchange_w_m2_k": 12.0,
                "geometry_status": "synthetic_not_measured",
            }
            for i in range(60)
        ],
        "sources": [
            {
                "id": "illustrative_thermal_inflow",
                "cell_id": "channel_006",
                "flow_m3_s": 0.252,
                "temperature_c": {
                    "times_s": [0.0, 1800.0, 3600.0],
                    "values": [62.0, 80.0, 62.0],
                },
                "status": "synthetic_intervention_not_observed",
            }
        ],
    }

def make_replay(config: dict[str, Any]) -> dict[str, Any]:
    river = river_from_config(config)
    solver_config = json.loads(json.dumps(config, allow_nan=False))
    solver_config["cells"] = [asdict(cell) for cell in river.cells]
    solver_config.update({"initialize_steady": False,
                          "rho_cp_j_m3_k": river.rho_cp,
                          "max_surface_iterations": river.max_surface_iterations,
                          "surface_tolerance_c": river.surface_tolerance_c,
                          "surface_relaxation": river.surface_relaxation})
    frames = river.run(
        duration_s=config.get("duration_s", 600.0),
        dt_s=config.get("dt_s", 1.0),
        sample_s=config.get("sample_s", 60.0),
    )
    budget = river.budget()

    canonical_config = json.dumps(
        config, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")

    explicit_budget = config.get("surface_budget") is not None
    simulation_time: dict[str, Any] = {}
    if "simulation_start_epoch_unix" in config:
        start_epoch = finite("simulation_start_epoch_unix", config["simulation_start_epoch_unix"], minimum=0.0)
        simulation_time = timestamp_metadata(
            datetime.fromtimestamp(start_epoch, tz=UTC),
            finite("duration_s", config.get("duration_s", 0.0), minimum=0.0),
        )
    limitations = [
        "Fixed geometry and prescribed discharge.",
        "No hydraulic momentum or changing water stage.",
        "No evaporation mass loss or phase change.",
        "No cross-channel plume or bathymetry reconstruction.",
        ("Explicit surface budget solved with damped Newton iteration. "
         "The reported heat residual measures convergence and closure "
         "of the nonlinear implicit discretization; it is not "
         "observational validation."
         if explicit_budget else
         "Surface exchange is a reduced Newton approximation."),
        "Stable large steps can still smear thermal fronts.",
        'Mapped cells carry world coordinates for frame playback.',
        "Conservation is not observational validation.",
    ]

    return {
        "schema": SCHEMA,
        "status": config.get(
            "status", "illustrative_not_calibrated"
        ),
        "input_sha256": hashlib.sha256(
            canonical_config
        ).hexdigest(),
        "code_sha256": sha256_file(Path(__file__)),
        "solver_config": solver_config,
        "model": {
            "space": "1-D upstream-to-downstream chainage",
            "time": "physical seconds",
            "advection": "first-order upwind",
            "dispersion": "centered harmonic interface conductance",
            "integration": "backward Euler",
            "surface_flux": ("explicit_budget" if explicit_budget
                             else "newton_lumped"),
            "surface_accounting": {
                "method": ("linearized_implicit_budget"
                           if explicit_budget
                           else "newton_lumped"),
                "additional_heat_flux_separate": True,
                "nonlinear_surface_flux_diagnostic": (
                    "max_surface_linearization_error_w"
                    if explicit_budget else None
                ),
            },
            "surface_solver": {
                "method": (
                    "damped_newton"
                    if explicit_budget
                    else "direct_linear_newton_exchange"
                ),
                "max_iterations": river.max_surface_iterations,
                "temperature_tolerance_c": river.surface_tolerance_c,
                "relaxation": river.surface_relaxation,
                "max_iterations_used": budget[
                    "max_surface_iterations_used"
                ],
                "iteration_failures": budget[
                    "surface_iteration_failures"
                ],
                "max_surface_linearization_error_w": budget[
                    "max_surface_linearization_error_w"
                ],
                "max_surface_newton_residual_c": budget[
                    "max_surface_newton_residual_c"
                ],
            },
            "energy_reference_c": ENERGY_REFERENCE_C,
            "rho_cp_j_m3_k": river.rho_cp,
            "surface_model": (
                describe_surface_model(river.surface_budget.params)
                if river.surface_budget is not None
                else {"method": "newton_lumped",
                      "sign_convention": "positive_into_water"}
            ),
            "boundary_conditions": (
                "Advective inflow/outflow; zero dispersive boundary flux."
            ),
            "limitations": limitations,
        },
        "parameter_notes": config.get("parameter_notes", {}),
        "simulation_time": simulation_time,
        "forcing": {
            "boundary_m3_s": (
                float(river.boundary_m3_s)
                if isinstance(river.boundary_m3_s, (int, float))
                else series_dict(river.boundary_q_series)
            ),
            "boundary_c": series_dict(river.boundary_c),
            "air_c": series_dict(river.air_c),
            "additional_heat_flux_w_m2": series_dict(river.net_heat_flux),
            "surface_budget": (river.surface_budget.to_dict()
                               if river.surface_budget is not None else None),
            "sources": [
                {
                    "id": source.id,
                    "cell_id": source.cell_id,
                    "flow_m3_s": (source.flow_m3_s.values[0] if len(source.flow_m3_s.values) == 1 else series_dict(source.flow_m3_s)),
                    "temperature_c": series_dict(source.temperature_c),
                    "status": source.status,
                }
                for source in river.sources
            ],
            "cell_heat_w": {
                cell.id: series_dict(series)
                for cell, series in zip(river.cells, river._cell_heat)
                if series is not None
            },
        },
        "cells": river.geometry_records(),
        "face_flow_m3_s": list(river.face_flow_m3_s),
        "face_dispersion_m3_s": list(river.face_dispersion_m3_s),
        "frames": frames,
        "final_budget": budget,
        "numerical_checks": {
            "passed": (
                budget["heat_relative_residual"]
                <= (max(1e-9, river.surface_tolerance_c) if explicit_budget else 1e-9)
                and budget["water_relative_residual"] <= 1e-12
                and budget["surface_iteration_failures"] == 0
            ),
            "heat_relative_tolerance": (
                max(1e-9, river.surface_tolerance_c) if explicit_budget else 1e-9
            ),
            "heat_tolerance_source": (
                "surface_tolerance_c for explicit budget; "
                "floating-point 1e-9 for Newton-lumped"
                if explicit_budget else "floating-point 1e-9"
            ),
            "water_relative_tolerance": 1e-12,
            "courant_warning_threshold": COURANT_WARNING_THRESHOLD,
            "diffusive_warning_threshold": DIFFUSIVE_WARNING_THRESHOLD,
            "numerical_warnings": budget["numerical_warnings"],
            "meaning": (
                "Discretized budget closure; "
                "not calibration or environmental accuracy. "
                "Courant/diffusive warnings flag coarse discretization; "
                "they do not block the run."
            ),
        },
    }
