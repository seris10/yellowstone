"""FiPy and MMS references for 1-D advection with Newton cooling."""
from __future__ import annotations

import importlib.util
import math
from typing import Any

from yellowstone_python.river.river_transport import RHO_CP_J_M3_K, Cell, River

# MMS synthetic profile shares the analytic case river parameters.
MMS_AMPLITUDE_C = 15.0

HAS_FIPY = importlib.util.find_spec("fipy") is not None

SYNTHETIC_Q_M3_S = 2.0
SYNTHETIC_T0_C = 20.0
SYNTHETIC_TAIR_C = 5.0
SYNTHETIC_H_W_M2_K = 100.0
SYNTHETIC_WIDTH_M = 20.0
SYNTHETIC_DEPTH_M = 1.1
SYNTHETIC_LENGTH_M = 3000.0
SYNTHETIC_DISPERSION_M2_S = 2.5

# Back-compat aliases for callers that imported the pre-rename names.
Q_M3_S = SYNTHETIC_Q_M3_S
T0_C = SYNTHETIC_T0_C
TAIR_C = SYNTHETIC_TAIR_C
H_W_M2_K = SYNTHETIC_H_W_M2_K
WIDTH_M = SYNTHETIC_WIDTH_M
DEPTH_M = SYNTHETIC_DEPTH_M
LENGTH_M = SYNTHETIC_LENGTH_M


def _require_fipy() -> None:
    """Raise a guided ImportError when fipy is absent."""
    if not HAS_FIPY:
        raise ImportError(
            "fipy is required for the FiPy reference solve: "
            "install with `pip install fipy`"
        )


def _checked_cells(n_cells: int) -> int:
    """Validate a cell count for the reference grid."""
    if isinstance(n_cells, bool) or not isinstance(n_cells, int):
        raise ValueError("n_cells must be an integer")
    if n_cells < 2:
        raise ValueError("n_cells must be at least 2")
    return n_cells


def decay_per_m() -> float:
    """Spatial decay rate of the analytic profile."""
    return H_W_M2_K * WIDTH_M / RHO_CP_J_M3_K / Q_M3_S


def loss_per_s() -> float:
    """Volumetric Newton cooling rate."""
    return H_W_M2_K * WIDTH_M / RHO_CP_J_M3_K / (WIDTH_M * DEPTH_M)


def analytic_temperature_c(x_m: float) -> float:
    """Analytic steady profile at distance downstream."""
    return TAIR_C + (T0_C - TAIR_C) * math.exp(-decay_per_m() * x_m)


def parameters() -> dict[str, Any]:
    """Analytic and grid parameters recorded with each result."""
    return {
        "discharge_m3_s": Q_M3_S,
        "upstream_c": T0_C,
        "air_c": TAIR_C,
        "exchange_w_m2_k": H_W_M2_K,
        "width_m": WIDTH_M,
        "depth_m": DEPTH_M,
        "length_m": LENGTH_M,
        "rho_cp_j_m3_k": RHO_CP_J_M3_K,
        "decay_per_m": decay_per_m(),
        "loss_per_s": loss_per_s(),
    }


def solve_steady(n_cells: int) -> dict[str, Any]:
    """FiPy steady solve at n_cells with error vs analytic profile."""
    _checked_cells(n_cells)
    _require_fipy()
    import fipy
    from fipy import (
        CellVariable,
        FaceVariable,
        Grid1D,
        ImplicitSourceTerm,
        UpwindConvectionTerm,
    )

    dx = LENGTH_M / n_cells
    area = WIDTH_M * DEPTH_M
    velocity = Q_M3_S / area
    cooling = loss_per_s()
    mesh = Grid1D(nx=n_cells, dx=dx)
    temperature = CellVariable(mesh=mesh, value=TAIR_C)
    temperature.constrain(T0_C, mesh.facesLeft)
    # Zero-gradient outflow enters the matrix implicitly.
    temperature.faceGrad.constrain(0.0, mesh.facesRight)
    # Face-centered velocity for the convection coefficient.
    face_velocity = FaceVariable(mesh=mesh, rank=1, value=velocity)
    # ImplicitSourceTerm holds cooling*T; reference cooling*t_air is on RHS.
    source = CellVariable(mesh=mesh, value=cooling * TAIR_C)
    equation = (
        UpwindConvectionTerm(coeff=face_velocity)
        + ImplicitSourceTerm(coeff=cooling)
    ) == source
    equation.solve(var=temperature)
    values = [float(v) for v in temperature.value]
    error = max(
        abs(v - analytic_temperature_c((i + 0.5) * dx))
        for i, v in enumerate(values)
    )
    return {
        "n_cells": n_cells,
        "dx_m": dx,
        "temperatures_c": values,
        "max_abs_error_c": error,
        "outlet_c": values[-1],
        "analytic_outlet_c": analytic_temperature_c(LENGTH_M - dx / 2.0),
        "fipy_version": getattr(fipy, "__version__", "unknown"),
        "parameters": parameters(),
    }


def hand_rolled_error_c(n_cells: int) -> float:
    """Hand-rolled steady error at matched resolution."""
    _checked_cells(n_cells)
    dx = LENGTH_M / n_cells
    cells = [
        Cell(f"c{i}", dx, WIDTH_M, dx * WIDTH_M * DEPTH_M, 12.0,
             exchange_w_m2_k=H_W_M2_K)
        for i in range(n_cells)
    ]
    river = River(cells, boundary_m3_s=Q_M3_S,
                  boundary_c=T0_C, air_c=TAIR_C)
    steady = river.steady_temperatures()
    return max(
        abs(t - analytic_temperature_c((i + 0.5) * dx))
        for i, t in enumerate(steady)
    )


def run_convergence(counts: tuple[int, ...] = (15, 30)) -> dict[str, Any]:
    """FiPy and hand-rolled errors plus observed rate at two resolutions."""
    if len(counts) < 2:
        raise ValueError("counts must hold at least two resolutions")
    results = [solve_steady(n) for n in counts]
    fipy_errors = [r["max_abs_error_c"] for r in results]
    hand_errors = [hand_rolled_error_c(n) for n in counts]
    rates = [math.log2(a / b) for a, b in zip(fipy_errors, fipy_errors[1:])]
    return {
        "n_cells": list(counts),
        "fipy_errors_c": fipy_errors,
        "hand_errors_c": hand_errors,
        "observed_rates": rates,
        "fipy_version": results[0]["fipy_version"],
        "parameters": parameters(),
    }


def mms_analytic_temperature_c(x_m: float) -> float:
    """Manufactured steady profile with zero outflow gradient at x=L."""
    return TAIR_C + MMS_AMPLITUDE_C * math.cos(math.pi * x_m / LENGTH_M)


def _mms_cell_heat_w(a_m: float, b_m: float) -> float:
    """Integrated analytic heat source for the manufactured steady profile."""
    advective = (
        RHO_CP_J_M3_K * Q_M3_S * MMS_AMPLITUDE_C
        * (math.cos(math.pi * b_m / LENGTH_M)
           - math.cos(math.pi * a_m / LENGTH_M))
    )
    newton = (
        H_W_M2_K * WIDTH_M * MMS_AMPLITUDE_C
        * (LENGTH_M / math.pi)
        * (math.sin(math.pi * b_m / LENGTH_M)
           - math.sin(math.pi * a_m / LENGTH_M))
    )
    return advective + newton


def solve_mms(n_cells: int) -> dict[str, Any]:
    """Drive the production solver with the MMS forcing and return errors."""
    _checked_cells(n_cells)
    dx = LENGTH_M / n_cells
    cells = [
        Cell(
            f"mms_cell_{i:04d}", dx, WIDTH_M,
            dx * WIDTH_M * DEPTH_M, TAIR_C,
            exchange_w_m2_k=H_W_M2_K,
        )
        for i in range(n_cells)
    ]
    cell_heat_w = {
        cells[i].id: _mms_cell_heat_w(i * dx, (i + 1) * dx)
        for i in range(n_cells)
    }
    river = River(
        cells,
        boundary_m3_s=Q_M3_S,
        boundary_c=mms_analytic_temperature_c(0.0),
        air_c=TAIR_C,
        cell_heat_w=cell_heat_w,
    )
    temperatures = river.steady_temperatures()
    error = max(
        abs(t - mms_analytic_temperature_c((i + 0.5) * dx))
        for i, t in enumerate(temperatures)
    )
    return {
        "n_cells": n_cells,
        "dx_m": dx,
        "temperatures_c": list(temperatures),
        "max_abs_error_c": error,
        "parameters": {
            **parameters(),
            "mms_amplitude_c": MMS_AMPLITUDE_C,
            "mms_boundary_c": mms_analytic_temperature_c(0.0),
        },
    }


def run_mms_convergence(
    counts: tuple[int, ...] = (30, 60),
) -> dict[str, Any]:
    """MMS errors and the observed convergence rate at two resolutions."""
    if len(counts) < 2:
        raise ValueError("counts must hold at least two resolutions")
    results = [solve_mms(n) for n in counts]
    errors = [r["max_abs_error_c"] for r in results]
    rates = [math.log2(a / b) for a, b in zip(errors, errors[1:])]
    return {
        "n_cells": list(counts),
        "mms_errors_c": errors,
        "observed_rates": rates,
        "parameters": results[0]["parameters"],
    }


def hand_rolled_dispersion_profile_c(
    n_cells: int,
    dispersion_m2_s: float,
) -> list[float]:
    """Hand-rolled steady profile with the dispersion coefficient active."""
    _checked_cells(n_cells)
    if dispersion_m2_s <= 0.0:
        raise ValueError("dispersion_m2_s must be positive")
    dx = LENGTH_M / n_cells
    cells = [
        Cell(
            f"disp_cell_{i:04d}", dx, WIDTH_M,
            dx * WIDTH_M * DEPTH_M, TAIR_C,
            dispersion_m2_s=dispersion_m2_s,
            exchange_w_m2_k=H_W_M2_K,
        )
        for i in range(n_cells)
    ]
    river = River(
        cells, boundary_m3_s=Q_M3_S,
        boundary_c=T0_C, air_c=TAIR_C,
    )
    return list(river.steady_temperatures())


def solve_steady_dispersion(
    n_cells: int,
    dispersion_m2_s: float = SYNTHETIC_DISPERSION_M2_S,
) -> dict[str, Any]:
    """FiPy steady solve with an explicit DiffusionTerm active."""
    _checked_cells(n_cells)
    _require_fipy()
    if dispersion_m2_s <= 0.0:
        raise ValueError("dispersion_m2_s must be positive")
    import fipy
    from fipy import (
        CellVariable,
        DiffusionTerm,
        FaceVariable,
        Grid1D,
        ImplicitSourceTerm,
        UpwindConvectionTerm,
    )

    dx = LENGTH_M / n_cells
    area = WIDTH_M * DEPTH_M
    velocity = Q_M3_S / area
    cooling = loss_per_s()
    mesh = Grid1D(nx=n_cells, dx=dx)
    temperature = CellVariable(mesh=mesh, value=TAIR_C)
    temperature.constrain(T0_C, mesh.facesLeft)
    temperature.faceGrad.constrain(0.0, mesh.facesRight)
    face_velocity = FaceVariable(mesh=mesh, rank=1, value=velocity)
    source = CellVariable(mesh=mesh, value=cooling * TAIR_C)
    equation = (
        UpwindConvectionTerm(coeff=face_velocity)
        - DiffusionTerm(coeff=dispersion_m2_s)
        + ImplicitSourceTerm(coeff=cooling)
    ) == source
    equation.solve(var=temperature)
    values = [float(v) for v in temperature.value]
    hand = hand_rolled_dispersion_profile_c(n_cells, dispersion_m2_s)
    error_vs_hand = max(abs(f - h) for f, h in zip(values, hand))
    error_vs_zero_d = max(
        abs(v - analytic_temperature_c((i + 0.5) * dx))
        for i, v in enumerate(values)
    )
    return {
        "n_cells": n_cells,
        "dx_m": dx,
        "temperatures_c": values,
        "hand_rolled_dispersion_c": hand,
        "max_abs_error_vs_hand_c": error_vs_hand,
        "max_abs_departure_from_zero_dispersion_c": error_vs_zero_d,
        "dispersion_m2_s": dispersion_m2_s,
        "fipy_version": getattr(fipy, "__version__", "unknown"),
        "parameters": parameters(),
    }


def run_dispersion_convergence(
    counts: tuple[int, ...] = (30, 60),
    dispersion_m2_s: float = SYNTHETIC_DISPERSION_M2_S,
) -> dict[str, Any]:
    """FiPy vs hand-rolled dispersion errors and the observed decline."""
    if len(counts) < 2:
        raise ValueError("counts must hold at least two resolutions")
    results = [
        solve_steady_dispersion(n, dispersion_m2_s=dispersion_m2_s)
        for n in counts
    ]
    errors = [r["max_abs_error_vs_hand_c"] for r in results]
    rates = [math.log2(a / b) for a, b in zip(errors, errors[1:])]
    return {
        "n_cells": list(counts),
        "fipy_minus_hand_errors_c": errors,
        "observed_rates": rates,
        "dispersion_m2_s": dispersion_m2_s,
        "fipy_version": results[0]["fipy_version"],
        "parameters": parameters(),
    }
