"""One-D river-temperature transport: finite-volume, backward-Euler tridiagonal, upwind advection, centered dispersion.
Newton surface exchange plus prescribed flux. Sensible energy vs 0 degC, constant volumetric heat capacity."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .surface_flux import (
    BUDGET_PARAM_KEYS,
    BudgetParams,
    MetState,
    describe_surface_model,
    flux_at,
    linearized,
)
from ..time_utils import UTC, timestamp_metadata

RHO_CP_J_M3_K = 4.186e6
ENERGY_REFERENCE_C = 0.0
SCHEMA = "yellowstone.river_transport.v1"

DEFAULT_MAX_SURFACE_ITERATIONS = 24
DEFAULT_SURFACE_TOLERANCE_C = 1e-7
DEFAULT_SURFACE_RELAXATION = 0.8

# Diagnostic thresholds for the backward-Euler advective and diffusive numbers.
COURANT_WARNING_THRESHOLD = 1.0
DIFFUSIVE_WARNING_THRESHOLD = 1.0

def finite(
    value: Any,
    name: str,
    minimum: float | None = None,
) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def series_dict(series: "Series") -> dict[str, list[float]]:
    """Normalize a Series to JSON-friendly {times_s, values} with Python lists."""
    return {
        "times_s": list(series.times_s),
        "values": list(series.values),
    }

def positive(value: Any, name: str) -> float:
    result = finite(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result

@dataclass(frozen=True)
class Series:
    """Right-continuous, piecewise-constant forcing (first value from t=0, last extends indefinitely).
    Integration steps split at every change time. Example: Series((0, 600, 1800), (62, 80, 62))."""

    times_s: tuple[float, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        times = tuple(
            finite(t, "forcing time", 0.0) for t in self.times_s
        )
        values = tuple(
            finite(v, "forcing value") for v in self.values
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
        time_s = finite(time_s, "forcing evaluation time", 0.0)
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
        return cls((0.0,), (finite(value, "constant forcing"),))

@dataclass(frozen=True)
class Cell:
    """A finite-volume cell in upstream-to-downstream order.
    volume_m3/length_m is mean wetted cross-section; width_m*length_m is water surface area."""

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
                self, name, positive(getattr(self, name), name)
            )

        for name in ("dispersion_m2_s", "exchange_w_m2_k"):
            object.__setattr__(
                self, name, finite(getattr(self, name), name, 0.0)
            )

        object.__setattr__(
            self, "initial_c", finite(self.initial_c, "initial_c")
        )

    @property
    def cross_section_m2(self) -> float:
        return self.volume_m3 / self.length_m

    @property
    def surface_area_m2(self) -> float:
        return self.width_m * self.length_m

@dataclass(frozen=True)
class Source:
    """Lateral water inflow assigned to a cell: constant flow, optional scheduled temperature.
    Added water raises all downstream face discharges; one-cell outfall placement is a discretization choice."""

    id: str
    cell_id: str
    flow_m3_s: float
    temperature_c: Any
    status: str = "illustrative_not_calibrated"

    def __post_init__(self) -> None:
        for name in ("id", "cell_id"):
            if not isinstance(getattr(self, name), str) or not getattr(
                self, name
            ):
                raise ValueError(f"{name} must be a nonempty string")

        object.__setattr__(
            self,
            "flow_m3_s",
            finite(self.flow_m3_s, "source flow", 0.0),
        )
        object.__setattr__(
            self, "temperature_c", Series.parse(self.temperature_c)
        )

@dataclass(frozen=True)
class SurfaceBudget:
    """Explicit surface energy budget forcing (replaces Newton exchange).
    Met series share the solver clock; air_c from River; per-cell exchange_w_m2_k ignored to avoid double-counting."""

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
                    finite(value, f"budget {name}", low)
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
    """Thomas algorithm; transport matrix has nonpositive off-diagonals and positive pivots.
    Singular steady problems raise ArithmeticError; cell_ids names rows in the pivot error."""
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
    ) -> None:
        self.cells = tuple(cells)
        self.sources = tuple(sources)
        if not self.cells:
            raise ValueError("at least one river cell is required")

        self.rho_cp = positive(
            rho_cp_j_m3_k, "volumetric heat capacity"
        )
        # Boundary discharge accepts scalar or Series; face flows recompute each step so water budget closes.
        self._boundary_q_series = Series.parse(boundary_m3_s)
        for value in self._boundary_q_series.values:
            finite(value, "boundary flow", 0.0)
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
            math.fsum(s.flow_m3_s for s in group)
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

        forcing_series: list[Series] = [
            self._boundary_q_series,
            self.boundary_c,
            self.air_c,
            self.net_heat_flux,
        ]
        forcing_series.extend(
            source.temperature_c for source in self.sources
        )
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

        self.surface_tolerance_c = positive(
            surface_tolerance_c, "surface_tolerance_c"
        )
        self.surface_relaxation = finite(
            surface_relaxation, "surface_relaxation"
        )
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
        """Face discharges in m3/s at the given time.
        Face 0 is the scheduled boundary inflow; downstream faces add lateral source flows cumulatively."""
        q = [float(self._boundary_q_series.at(time_s))]
        for lateral_q in self._lateral_q:
            q.append(
                finite(
                    math.fsum((q[-1], lateral_q)),
                    "derived face discharge",
                    0.0,
                )
            )
        return tuple(q)

    def _source_qt(self, time_s: float) -> list[float]:
        return [
            math.fsum(
                source.flow_m3_s
                * source.temperature_c.at(time_s)
                for source in group
            )
            for group in self._sources_by_cell
        ]

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
        """Surface matrix terms for one cell at the specified time.
        Returns (temperature coefficient, constant contribution, linearization details or None in Newton mode)."""
        cell = self.cells[cell_index]
        area = cell.surface_area_m2
        air = self.air_c.at(time_s)

        if self.surface_budget is None:
            exchange = cell.exchange_w_m2_k * area / self.rho_cp
            return exchange, exchange * air, None

        # Explicit budget replaces lumped coefficient; linearized implicitly F(T_new) ~= F0 + dF/dT * (T_new - T_old).
        met = self.surface_budget.met_at(time_s, air)
        if linearization_temperature is None:
            linearization_temperature = self._temperature_c[cell_index]
        linearization_temperature = finite(
            linearization_temperature,
            f"surface linearization temperature cell {cell_index}",
        )
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
        """Surface power at the converged temperature.
        Base is area*flux_at(T_converged); linearized flux at old T is kept as a nonlinear/linear-gap diagnostic."""
        air = self.air_c.at(time_s)

        if self.surface_budget is None:
            return [
                cell.surface_area_m2 * cell.exchange_w_m2_k * (air - temperature)
                for cell, temperature in zip(self.cells, temperatures)
            ], None

        surface_power_w: list[float] = []
        component_power_w: dict[str, list[float]] = {
            name: []
            for name in ("shortwave", "longwave", "sensible", "latent")
        }

        met = self.surface_budget.met_at(time_s, air)
        for i, (cell, temperature) in enumerate(zip(self.cells, temperatures)):
            area = cell.surface_area_m2
            _exchange, _rhs, metadata = self._surface_linearization(i, time_s)
            if metadata is None:
                raise AssertionError(
                    "surface budget metadata unexpectedly missing"
                )

            nonlinear_parts = flux_at(
                temperature, met, self.surface_budget.params
            )
            old_temperature = self._temperature_c[i]
            linearized_flux_old = (
                metadata["flux_at_linearization_temperature_w_m2"]
                + metadata["flux_temperature_slope_w_m2_k"]
                * (temperature - old_temperature)
            )

            self.max_surface_linearization_error_w = max(
                self.max_surface_linearization_error_w,
                abs(nonlinear_parts["net"] - linearized_flux_old) * area,
            )

            surface_power_w.append(area * nonlinear_parts["net"])
            for name in component_power_w:
                component_power_w[name].append(nonlinear_parts[name] * area)

        return surface_power_w, component_power_w

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

        lower = [0.0] * n
        diagonal = [0.0] * n
        upper = [0.0] * n
        rhs = [0.0] * n

        for i, cell in enumerate(self.cells):
            area = cell.surface_area_m2
            exchange, surface_rhs, _metadata = self._surface_linearization(
                i, time_s,
                linearization_temperature=linearization_temperature[i],
            )

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

    def _solve_implicit_step(
        self,
        start_s: float,
        dt_s: float,
    ) -> tuple[list[float], int, float]:
        """Solve one implicit timestep.
        Explicit budget relinearizes until |dT|_inf <= tolerance; returns (temps, iters, residual_c)."""
        if self.surface_budget is None:
            solution = solve_tridiagonal(
                *self._system(start_s, dt_s),
                cell_ids=[cell.id for cell in self.cells],
            )
            return solution, 1, 0.0

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

            candidate = solve_tridiagonal(
                lower,
                diagonal,
                upper,
                rhs,
                cell_ids=[cell.id for cell in self.cells],
            )

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

    def steady_temperatures(
        self,
        time_s: float = 0.0,
    ) -> tuple[float, ...]:
        """Steady solution with forcing frozen at the specified time.
        Does not mutate the river. Closed, unforced domains raise ArithmeticError."""
        time_s = finite(time_s, "steady forcing time", 0.0)
        return tuple(
            solve_tridiagonal(
                *self._system(time_s),
                cell_ids=[cell.id for cell in self.cells],
            )
        )

    def step(self, dt_s: float) -> dict[str, float]:
        """Advance one interval without crossing a forcing change.

        Use run() to split automatically at forcing and sample times.
        """
        dt_s = positive(dt_s, "dt_s")
        end_s = finite(self.time_s + dt_s, "step end time")

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

        q = self._face_flow_at(start_s)
        g = self.face_dispersion_m3_s
        source_qt = self._source_qt(start_s)
        cell_heat = self._cell_heat_at(start_s)
        extra_flux = self.net_heat_flux.at(start_s)

        # Advective + dispersive face fluxes, in m3*C/s.
        faces = [q[0] * self.boundary_c.at(start_s)]
        for j in range(1, len(self.cells)):
            faces.append(
                q[j] * new[j - 1]
                + g[j] * (new[j - 1] - new[j])
            )
        faces.append(q[-1] * new[-1])

        additional_heat_power_w = [
            cell.surface_area_m2 * extra_flux
            for cell in self.cells
        ]

        base_surface_power_w, component_power_w = (
            self._surface_power_for_accounting(new, start_s)
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
            "boundary_input_m3": dt_s * q[0],
            "lateral_input_m3": dt_s * math.fsum(self._lateral_q),
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
            ))
            cell_residuals.append(abs(observed - expected))

        for name, value in increments.items():
            finite(value, name)
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
        """Advance for duration_s, preserving forcing-change times.
        Includes starting and final state; sample times split integration intervals; zero-duration returns one row."""
        duration_s = finite(duration_s, "duration_s", 0.0)
        dt_s = positive(dt_s, "dt_s")
        sample_s = positive(sample_s, "sample_s")

        start_s = self.time_s
        finish_s = finite(start_s + duration_s, "run finish time")
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
    """Synthetic channel and source-temperature pulse.

    This is not mapped Firehole geometry or an observed Yellowstone event.
    """
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
        start_epoch = finite(
            config["simulation_start_epoch_unix"],
            "simulation_start_epoch_unix",
            0.0,
        )
        simulation_time = timestamp_metadata(
            datetime.fromtimestamp(start_epoch, tz=UTC),
            finite(config.get("duration_s", 0.0), "duration_s", 0.0),
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
        "No world-coordinate mapping or Godot playback yet.",
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
        "code_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
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
                    "flow_m3_s": source.flow_m3_s,
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
                <= max(1e-9, river.surface_tolerance_c)
                and budget["water_relative_residual"] <= 1e-12
                and budget["surface_iteration_failures"] == 0
            ),
            "heat_relative_tolerance": max(1e-9, river.surface_tolerance_c),
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

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true")
    mode.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        config = (
            demo_config()
            if args.demo
            else json.loads(args.config.read_text(encoding="utf-8"))
        )
        if not isinstance(config, dict):
            raise ValueError("configuration must be a JSON object")

        document = make_replay(config)
        text = json.dumps(
            document, indent=2, allow_nan=False
        ) + "\n"

        args.out.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.out.with_name(args.out.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(args.out)

    except (
        ValueError, TypeError, KeyError, ArithmeticError, OSError
    ) as error:
        parser.exit(2, f"river transport failed: {error}\n")

    budget = document["final_budget"]
    passed = document["numerical_checks"]["passed"]

    print(f"Replay: {args.out}")
    print(
        f"Cells: {len(document['cells'])}; "
        f"frames: {len(document['frames'])}; "
        f"steps: {budget['steps']}"
    )
    print(
        f"Heat residual: {budget['heat_residual_j']:.6g} J; "
        f"relative: {budget['heat_relative_residual']:.3g}"
    )
    print(
        f"Water residual: {budget['water_residual_m3']:.6g} m3"
    )
    print(
        f"Maximum advective Courant number: "
        f"{budget['max_advective_courant']:.3g}"
    )
    print(f"Numerical budget checks passed: {passed}")
    print("Synthetic/illustrative model; not a Yellowstone forecast.")

    return 0 if passed else 2

if __name__ == "__main__":
    raise SystemExit(main())