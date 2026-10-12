"""FiPy steady 1-D advection plus Newton cooling vs analytic profile."""
from __future__ import annotations

import importlib.util
import math
from typing import Any

from .river_transport import RHO_CP_J_M3_K, Cell, River

HAS_FIPY = importlib.util.find_spec("fipy") is not None

Q_M3_S = 2.0
T0_C = 20.0
TAIR_C = 5.0
H_W_M2_K = 100.0
WIDTH_M = 20.0
DEPTH_M = 1.1
LENGTH_M = 3000.0


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
    # ImplicitSourceTerm holds cooling*T; reference cooling*TAIR is RHS.
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
