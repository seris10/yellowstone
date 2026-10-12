"""Conservative one-dimensional river-temperature transport.

Scientific scope
----------------
Fixed channel geometry and water volumes; prescribed downstream discharge;
lateral inflows; longitudinal dispersion; optional Newton surface exchange;
and an additional prescribed surface heat flux.

Numerical method
----------------
Finite-volume spatial discretization.
First-order upwind advection.
Centered dispersion with harmonic interface conductance.
Backward Euler time integration.
O(n) tridiagonal solution.

Boundary conditions
-------------------
Upstream: prescribed advective temperature, zero dispersive flux.
Downstream: advective export, zero dispersive flux.

Limitations
-----------
Not a momentum, stage, evaporation-mass, phase-change, or 2-D plume solver.
Surface exchange is still a reduced model, not a complete meteorological
energy balance. Large timesteps are stable but can smear thermal fronts.
Parameters and geometry require independent scientific calibration.

Energy is sensible energy relative to 0 degrees Celsius, with constant
volumetric heat capacity. It is not absolute thermodynamic internal energy.

Standalone demo:
    python river_transport.py --demo --out derived/river_demo.json

Run a JSON configuration:
    python river_transport.py --config configs/river_transport.json \
        --out derived/river_replay.json
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .surface_flux import (
    BudgetParams,
    MetState,
    flux_at,
    linearized,
)

RHO_CP_J_M3_K = 4.186e6
ENERGY_REFERENCE_C = 0.0
SCHEMA = "yellowstone.river_transport.v1"

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

def positive(value: Any, name: str) -> float:
    result = finite(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result

@dataclass(frozen=True)
class Series:
    """Right-continuous, piecewise-constant forcing.

    Example:
        Series((0, 600, 1800), (62, 80, 62))

    The first value applies from t=0. The final value remains active
    indefinitely. Integration steps are split at every change time.
    """

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

    volume_m3 / length_m gives mean wetted cross-sectional area.
    width_m * length_m gives exposed water-surface area.

    These quantities describe the numerical channel, not automatically
    surveyed channel geometry.
    """

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
    """Lateral water inflow assigned to a cell.

    Flow is constant in this first version; temperature may be scheduled.
    The water addition increases all downstream face discharges.

    Assigning an outfall to one cell is a discretization decision, not a
    claim that the real outfall is fully mixed at that location.
    """

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

    Met series share the solver clock; air temperature still comes from
    the River's own air_c series. When a River carries a SurfaceBudget,
    per-cell exchange_w_m2_k coefficients are ignored (documented in the
    replay) so heat is not double-counted.
    """

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
        if not isinstance(self.params, BudgetParams):
            raise ValueError("budget params must be BudgetParams")

    def met_at(self, time_s: float, air_c: float) -> MetState:
        return MetState(
            air_c=air_c, rh=self.rh.at(time_s),
            wind_mps=self.wind_mps.at(time_s),
            shortwave_w_m2=self.shortwave_w_m2.at(time_s),
            cloud=self.cloud.at(time_s))

    def to_dict(self) -> dict[str, Any]:
        return {
            "rh": {"times_s": list(self.rh.times_s),
                   "values": list(self.rh.values)},
            "wind_mps": {"times_s": list(self.wind_mps.times_s),
                         "values": list(self.wind_mps.values)},
            "shortwave_w_m2": {
                "times_s": list(self.shortwave_w_m2.times_s),
                "values": list(self.shortwave_w_m2.values)},
            "cloud": {"times_s": list(self.cloud.times_s),
                      "values": list(self.cloud.values)},
            "params": {
                "albedo": self.params.albedo,
                "emissivity": self.params.emissivity,
                "c_h": self.params.c_h, "c_e": self.params.c_e,
                "pressure_kpa": self.params.pressure_kpa},
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
) -> list[float]:
    """Thomas algorithm.

    The transport matrix has nonpositive off-diagonals and positive
    pivots. A singular steady problem, such as a completely closed
    channel without heat exchange, is rejected rather than fabricated.
    """
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
            raise ArithmeticError(
                f"singular or invalid matrix pivot at cell {i}"
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
        boundary_m3_s: float,
        boundary_c: Any,
        sources: tuple[Source, ...] | list[Source] = (),
        air_c: Any = 7.0,
        net_heat_flux_w_m2: Any = 0.0,
        rho_cp_j_m3_k: float = RHO_CP_J_M3_K,
        surface_budget: Any = None,
        cell_heat_w: dict[str, Any] | None = None,
    ) -> None:
        self.cells = tuple(cells)
        self.sources = tuple(sources)
        if not self.cells:
            raise ValueError("at least one river cell is required")

        self.rho_cp = positive(
            rho_cp_j_m3_k, "volumetric heat capacity"
        )
        self.boundary_m3_s = finite(
            boundary_m3_s, "boundary flow", 0.0
        )
        self.boundary_c = Series.parse(boundary_c)
        self.air_c = Series.parse(air_c)

        # Positive means energy entering the water.
        # This is ADDITIONAL to Newton exchange.
        self.net_heat_flux = Series.parse(net_heat_flux_w_m2)

        self.surface_budget = (
            None if surface_budget is None
            else SurfaceBudget.parse(surface_budget)
        )

        # Per-cell heat power in watts. Positive values add energy.
        # Covered by the same budget accounting as other heat terms.
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

        # n cells have n+1 faces.
        q = [self.boundary_m3_s]
        for lateral_q in self._lateral_q:
            q.append(
                finite(
                    math.fsum((q[-1], lateral_q)),
                    "derived face discharge",
                    0.0,
                )
            )
        self.face_flow_m3_s = tuple(q)

        # Dispersive conductance, in m3/s, at each face:
        #
        # G = 1 / [Li/(2 Di Ai) + Lj/(2 Dj Aj)]
        #
        # This is a harmonic resistance calculation. Internal fluxes
        # are shared exactly by neighboring cells.
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

        self._forcing = (
            self.boundary_c,
            self.air_c,
            self.net_heat_flux,
            *(s.temperature_c for s in self.sources),
            *(s for s in self._cell_heat if s is not None),
        )

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

    def _system(
        self,
        time_s: float,
        dt_s: float | None = None,
    ) -> tuple[list[float], list[float], list[float], list[float]]:
        """Build transport equations in temperature-volume units."""
        n = len(self.cells)
        q = self.face_flow_m3_s
        g = self.face_dispersion_m3_s
        source_qt = self._source_qt(time_s)
        cell_heat = self._cell_heat_at(time_s)
        air = self.air_c.at(time_s)
        extra_flux = self.net_heat_flux.at(time_s)

        lower = [0.0] * n
        diagonal = [0.0] * n
        upper = [0.0] * n
        rhs = [0.0] * n

        for i, cell in enumerate(self.cells):
            area = cell.surface_area_m2
            if self.surface_budget is None:
                exchange = (
                    cell.exchange_w_m2_k
                    * area
                    / self.rho_cp
                )
                surface_rhs = exchange * air
            else:
                # Explicit budget replaces the lumped coefficient so heat
                # is not double-counted. Linearized implicitly for stability:
                # F(T_new) ~= F0 + dF/dT * (T_new - T_old).
                met = self.surface_budget.met_at(time_s, air)
                flux0, slope = linearized(
                    self._temperature_c[i], met,
                    self.surface_budget.params)
                exchange = -slope * area / self.rho_cp
                surface_rhs = (
                    (flux0 - slope * self._temperature_c[i])
                    * area / self.rho_cp
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

    def steady_temperatures(
        self,
        time_s: float = 0.0,
    ) -> tuple[float, ...]:
        """Steady solution with forcing frozen at the specified time.

        Does not mutate the river. A closed, unforced domain can have
        no unique steady temperature and will raise ArithmeticError.
        """
        time_s = finite(time_s, "steady forcing time", 0.0)
        return tuple(
            solve_tridiagonal(*self._system(time_s))
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

        new = solve_tridiagonal(
            *self._system(start_s, dt_s)
        )

        q = self.face_flow_m3_s
        g = self.face_dispersion_m3_s
        source_qt = self._source_qt(start_s)
        cell_heat = self._cell_heat_at(start_s)
        air = self.air_c.at(start_s)
        extra_flux = self.net_heat_flux.at(start_s)

        # Advective + dispersive face fluxes, in m3*C/s.
        faces = [q[0] * self.boundary_c.at(start_s)]
        for j in range(1, len(self.cells)):
            faces.append(
                q[j] * new[j - 1]
                + g[j] * (new[j - 1] - new[j])
            )
        faces.append(q[-1] * new[-1])

        surface_power_w = [
            cell.surface_area_m2 * (
                extra_flux
                + cell.exchange_w_m2_k * (air - temperature)
            )
            for cell, temperature in zip(self.cells, new)
        ]
        if self.surface_budget is None:
            component_power_w: dict[str, list[float]] | None = None
        else:
            # Accounting uses the flux at the NEW temperature, so closure
            # measures actual energy change, not the linearized estimate.
            met_now = self.surface_budget.met_at(start_s, air)
            fluxes = [flux_at(temperature, met_now,
                              self.surface_budget.params)
                      for temperature in new]
            surface_power_w = [
                cell.surface_area_m2 * parts["net"] + area_extra
                for cell, parts, area_extra in zip(
                    self.cells, fluxes,
                    (cell.surface_area_m2 * extra_flux
                     for cell in self.cells))
            ]
            component_power_w = {
                name: [parts[name] * cell.surface_area_m2
                       for cell, parts in zip(self.cells, fluxes)]
                for name in ("shortwave", "longwave",
                             "sensible", "latent")
            }

        increments = {
            "boundary_input_j": self.rho_cp * dt_s * faces[0],
            "lateral_input_j": (
                self.rho_cp * dt_s * math.fsum(source_qt)
            ),
            "outlet_export_j": self.rho_cp * dt_s * faces[-1],
            "surface_exchange_j": dt_s * math.fsum(surface_power_w),
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

        return {
            **increments,
            "dt_s": dt_s,
            "storage_change_j": storage_change_j,
            "heat_residual_j": residual_j,
            "max_cell_heat_residual_j": max(cell_residuals),
        }

    def budget(self) -> dict[str, float | int]:
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
                    "cell_heat_j",
                )
            ),
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
            "max_advective_courant": self.max_advective_courant,
            "max_diffusive_number": self.max_diffusive_number,
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

        Includes the starting state and exact final state. Sample times
        also split integration intervals; choose sample_s as a multiple
        of dt_s when comparing numerical runs.

        A zero-duration run returns one snapshot.
        """
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
        "surface_budget",
        "duration_s", "dt_s", "sample_s", "initialize_steady",
        "status", "parameter_notes",
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

    explicit_budget = "surface_budget" in config
    limitations = [
        "Fixed geometry and prescribed discharge.",
        "No hydraulic momentum or changing water stage.",
        "No evaporation mass loss or phase change.",
        "No cross-channel plume or bathymetry reconstruction.",
        ("Explicit shortwave/longwave/sensible/latent budget with "
         "illustrative coefficients, not fitted meteorology."
         if explicit_budget else
         "Surface exchange is a reduced approximation."),
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
            "energy_reference_c": ENERGY_REFERENCE_C,
            "rho_cp_j_m3_k": river.rho_cp,
            "surface_flux_sign": "positive into water",
            "boundary_conditions": (
                "Advective inflow/outflow; zero dispersive boundary flux."
            ),
            "limitations": limitations,
        },
        "parameter_notes": config.get("parameter_notes", {}),
        "forcing": {
            "boundary_m3_s": river.boundary_m3_s,
            "boundary_c": asdict(river.boundary_c),
            "air_c": asdict(river.air_c),
            "additional_heat_flux_w_m2": asdict(river.net_heat_flux),
            "surface_budget": (river.surface_budget.to_dict()
                               if river.surface_budget is not None else None),
            "sources": [asdict(source) for source in river.sources],
        },
        "cells": river.geometry_records(),
        "face_flow_m3_s": list(river.face_flow_m3_s),
        "face_dispersion_m3_s": list(river.face_dispersion_m3_s),
        "frames": frames,
        "final_budget": budget,
        "numerical_checks": {
            "passed": (
                budget["heat_relative_residual"] <= 1e-9
                and budget["water_relative_residual"] <= 1e-12
            ),
            "heat_relative_tolerance": 1e-9,
            "water_relative_tolerance": 1e-12,
            "meaning": (
                "Floating-point budget closure only; "
                "not calibration or environmental accuracy."
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