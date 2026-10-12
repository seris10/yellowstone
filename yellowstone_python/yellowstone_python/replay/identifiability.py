"""Identifiability diagnostics for hydraulic knobs + structural alternative.

Hydraulics: roughness, bank slope, and depth compensate in the Manning
consistency ratio, so a good fit does not prove each value is real.
Diagnostics here are Jacobian conditioning, linearized parameter
correlation, multi-start consistency, and synthetic recovery, all on
authored scenarios. No field data is fitted.

Dependence policy: manning_n, bank_slope_zh, and depth_m vary over
independent authored ranges because each carries separate provenance
(Chow literature, authored banks, DEM-derived depth). Correlated
quantities (shared reach slope, shared meteorology, width/depth from
one profile) stay fixed. A SALib Sobol workflow joins only under this
formulation or a dependence-aware method; scipy covers current needs.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from .hydraulics import cell_hydraulics
from .river_transport import Cell, River, Series

SCHEMA = "yellowstone.identifiability.v1"

PARAM_NAMES = ("manning_n", "bank_slope_zh", "depth_m")
PARAM_BOUNDS = {"manning_n": (0.02, 0.06),
                "bank_slope_zh": (0.5, 3.0),
                "depth_m": (0.4, 2.5)}
TRUTH = {"manning_n": 0.035, "bank_slope_zh": 1.5, "depth_m": 1.1}
SCENARIOS = ({"discharge_m3_s": 2.0, "slope": 0.008},
             {"discharge_m3_s": 8.0, "slope": 0.003},
             {"discharge_m3_s": 20.0, "slope": 0.0015})
CHANNEL_WIDTH_M = 22.0
CHANNEL_LENGTH_M = 20.0

DEPENDENCE_POLICY = {
    "varied_independently": {
        "manning_n": "Chow 1959 literature range, authored",
        "bank_slope_zh": "authored banks; survey status unsurveyed",
        "depth_m": "DEM-derived estimate; bathymetry absent",
    },
    "held_fixed": ("reach slope shared per feature", "meteorology shared",
                   "width and depth from one profile"),
    "salib_gate": "independent-input formulation above, or a "
                  "dependence-aware method with documented interpretation",
}


def _ratio(params: Sequence[float],
           scenarios: Sequence[dict] = SCENARIOS) -> list[float]:
    """Manning consistency ratio per scenario for (n, z, d)."""
    n, z, d = (float(v) for v in params)
    out = []
    for scenario in scenarios:
        record = cell_hydraulics(
            length_m=CHANNEL_LENGTH_M, top_width_m=CHANNEL_WIDTH_M,
            depth_m=d, discharge_m3_s=scenario["discharge_m3_s"],
            slope=scenario["slope"], bank_slope_zh=z, manning_n=n)
        ratio = record["manning_consistency_ratio"]
        if ratio is None:
            raise ArithmeticError("Manning undefined on a scenario")
        out.append(ratio)
    return out


def residual_against_truth(params: Sequence[float]) -> list[float]:
    """Ratio gaps to the synthetic truth. Zero at truth by construction."""
    truth = [TRUTH[name] for name in PARAM_NAMES]
    return [a - b for a, b in zip(_ratio(params), _ratio(truth))]


def jacobian_at_truth(step: float = 1e-6) -> list[list[float]]:
    """Central-difference Jacobian of residuals at truth."""
    truth = np.array([TRUTH[name] for name in PARAM_NAMES])
    cols = []
    for i in range(len(PARAM_NAMES)):
        delta = np.zeros_like(truth)
        delta[i] = step * max(1.0, abs(truth[i]))
        up = np.array(residual_against_truth(truth + delta))
        down = np.array(residual_against_truth(truth - delta))
        cols.append((up - down) / (2.0 * delta[i]))
    return np.column_stack(cols).tolist()


def conditioning(jacobian: Sequence[Sequence[float]],
                   rank_tol: float = 1e-8) -> dict[str, Any]:
    """SVD rank, null directions, and identified combination."""
    jac = np.asarray(jacobian, dtype=float)
    _, singular, vt = np.linalg.svd(jac)
    singular = singular.tolist()
    cutoff = max(singular) * rank_tol
    rank = sum(1 for s in singular if s > cutoff)
    return {"singular_values": singular,
            "rank": rank,
            "n_params": jac.shape[1],
            "null_directions": vt[rank:].tolist(),
            "identified_direction": vt[0].tolist(),
            "param_names": list(PARAM_NAMES)}


def multistart_fit(
        starts: Sequence[Sequence[float]] | None = None,
        max_nfev: int = 200) -> dict[str, Any]:
    """Least-squares recovery of truth from several starts."""
    from scipy.optimize import least_squares
    if starts is None:
        starts = [(0.025, 1.0, 0.7), (0.05, 2.0, 0.8),
                  (0.03, 2.5, 2.0), (0.055, 0.8, 1.8)]
    bounds = ([PARAM_BOUNDS[name][0] for name in PARAM_NAMES],
              [PARAM_BOUNDS[name][1] for name in PARAM_NAMES])
    runs = []
    for start in starts:
        result = least_squares(residual_against_truth, list(start),
                               bounds=bounds, max_nfev=max_nfev)
        runs.append({"start": list(start),
                     "solution": [float(v) for v in result.x],
                     "cost": float(result.cost),
                     "success": bool(result.success),
                     "nfev": int(result.nfev)})
    truth = [TRUTH[name] for name in PARAM_NAMES]
    spreads = [max(abs(r["solution"][i] - truth[i]) / truth[i]
                   for r in runs) for i in range(len(PARAM_NAMES))]
    return {"runs": runs,
            "max_cost": max(r["cost"] for r in runs),
            "relative_spread": dict(zip(PARAM_NAMES, spreads)),
            "truth": dict(zip(PARAM_NAMES, truth))}


def structural_surface_spread(duration_s: float = 3600.0,
                              dt_s: float = 10.0) -> dict[str, Any]:
    """Newton vs explicit-budget trajectories on one synthetic channel.

    Same geometry, discharge, and air series; only the surface
    formulation differs. The gap is model-form spread, used for
    comparison. It is not a calibrated prediction interval.
    """
    n = 10
    dx = 100.0
    width, depth = 20.0, 1.1
    air = Series((0.0,), (9.0,))

    def constant(values: tuple[float, ...]) -> dict[str, Any]:
        return {"times_s": [0.0], "values": list(values)}

    cells = [Cell(f"s_{i:02d}", dx, width, dx * width * depth, 15.0,
                  dispersion_m2_s=1.0, exchange_w_m2_k=12.0)
             for i in range(n)]
    newton = River(cells, boundary_m3_s=8.0, boundary_c=17.5, air_c=air)
    explicit = River(
        cells, boundary_m3_s=8.0, boundary_c=17.5, air_c=air,
        surface_budget={"rh": constant((0.5,)),
                        "wind_mps": constant((2.0,)),
                        "shortwave_w_m2": constant((200.0,)),
                        "cloud": constant((0.2,)),
                        "params": {}})
    newton_frames = newton.run(duration_s, dt_s=dt_s,
                               sample_s=duration_s)
    explicit_frames = explicit.run(duration_s, dt_s=dt_s,
                                   sample_s=duration_s)
    gaps = [abs(a - b)
            for fa, fb in zip(newton_frames, explicit_frames)
            for a, b in zip(fa["temperature_c"], fb["temperature_c"])]
    newton_ok = newton.budget()["heat_relative_residual"] <= 1e-9
    explicit_ok = explicit.budget()["heat_relative_residual"] <= 1e-9
    return {"formulations": ("newton_lumped", "explicit_budget"),
            "n_cells": n,
            "max_abs_gap_c": max(gaps),
            "mean_abs_gap_c": math.fsum(gaps) / len(gaps),
            "budgets_ok": newton_ok and explicit_ok,
            "status": "model_form_comparison_not_prediction_interval"}


def sobol_screen(n_base: int = 512, seed: int = 11,
                 calc_second_order: bool = True) -> dict[str, Any]:
    """Saltelli/Sobol screening of the Manning ratio residual."""
    if isinstance(n_base, bool) or not isinstance(n_base, int):
        raise ValueError("n_base must be an integer")
    if n_base <= 0:
        raise ValueError("n_base must be positive")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if not isinstance(calc_second_order, bool):
        raise ValueError("calc_second_order must be boolean")
    try:
        from SALib.analyze import sobol
        try:
            from SALib.sample import sobol as sampler
            sampler_method = "SALib.sample.sobol"
        except ImportError:
            from SALib.sample import saltelli as sampler
            sampler_method = "SALib.sample.saltelli"
    except ImportError as exc:
        raise ImportError(
            "identifiability.sobol_screen needs SALib: install it "
            "(pip install SALib) or use conditioning and multistart_fit "
            "on the scipy path") from exc
    import numpy as np
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version
    try:
        salib_version = _pkg_version("SALib")
    except PackageNotFoundError:
        salib_version = "unknown"
    problem = {"num_vars": len(PARAM_NAMES),
               "names": list(PARAM_NAMES),
               "bounds": [[PARAM_BOUNDS[name][0], PARAM_BOUNDS[name][1]]
                          for name in PARAM_NAMES]}
    try:
        sample = sampler.sample(problem, n_base,
                                calc_second_order=calc_second_order,
                                seed=seed)
    except TypeError:
        # Older sampler without a seed keyword. Local generator only.
        saved = np.random.get_state()
        try:
            np.random.seed(seed)
            sample = sampler.sample(problem, n_base,
                                    calc_second_order=calc_second_order)
        finally:
            np.random.set_state(saved)
    values = np.array([math.fsum(v * v for v in residual_against_truth(p))
                       for p in sample])
    try:
        indices = sobol.analyze(problem, values,
                                calc_second_order=calc_second_order,
                                print_to_console=False, seed=seed)
    except TypeError:
        indices = sobol.analyze(problem, values,
                                calc_second_order=calc_second_order,
                                print_to_console=False)
    return {"param_names": list(PARAM_NAMES),
            "n_base": n_base,
            "n_eval": int(len(sample)),
            "sampler_method": sampler_method,
            "salib_version": salib_version,
            "seed": seed,
            "objective": "sum of squared Manning-ratio residual gaps "
                         "to synthetic truth over 3 scenarios, "
                         "unweighted, unnormalized; screening only",
            "independence_basis": DEPENDENCE_POLICY,
            "S1": [float(v) for v in indices["S1"]],
            "ST": [float(v) for v in indices["ST"]],
            "S1_conf": [float(v) for v in indices["S1_conf"]],
            "ST_conf": [float(v) for v in indices["ST_conf"]],
            "status": "screening_not_calibration"}


def run_diagnostics() -> dict[str, Any]:
    """Full Phase D diagnostic document."""
    jac = jacobian_at_truth()
    return {
        "schema": SCHEMA,
        "status": "diagnostic_not_field_validation",
        "conditioning": conditioning(jac),
        "multistart": multistart_fit(),
        "structural_surface": structural_surface_spread(),
        "dependence_policy": DEPENDENCE_POLICY,
    }
