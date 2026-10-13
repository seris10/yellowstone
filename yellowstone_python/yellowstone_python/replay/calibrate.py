"""Reach-scale calibration and dispersion experiments for the Firehole.
dispersion_sweep: solver fidelity. reach_heat_fit: lumped budget fit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .hydraulics import score_paired_series
from .river_transport import River, Series
from .surface_flux import BudgetParams
from ..run_mode import (PRESCRIBED_DISCHARGE,
                        PRESCRIBED_UPSTREAM_TEMPERATURE, check_split)

SCHEMA_DISPERSION = "yellowstone.dispersion_sweep.v1"
SCHEMA_FIT = "yellowstone.reach_heat_fit.v1"


def _finite(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def resample_bin_mean(
    pairs: list[list[float]], grid: list[float], dt_s: float
) -> tuple[list[float | None], float, list[int]]:
    """Bin-average irregular pairs onto a uniform grid.
    Returns (values, coverage, counts); missing bins are None and count 0.
    """
    dt_s = _finite(dt_s, "dt_s")
    if dt_s <= 0.0:
        raise ValueError("dt_s must be positive")
    if not grid:
        raise ValueError("grid must be nonempty")
    for i, g in enumerate(grid):
        _finite(g, f"grid[{i}]")
    if any(b <= a for a, b in zip(grid, grid[1:])):
        raise ValueError("grid must be strictly increasing")
    spacing_tol = 1e-6 * dt_s
    for a, b in zip(grid, grid[1:]):
        if abs((b - a) - dt_s) > spacing_tol:
            raise ValueError(
                f"grid spacing must match dt_s ({dt_s:g} s), "
                f"found {b - a:g} s")
    sums = [0.0] * len(grid)
    counts = [0] * len(grid)
    origin = grid[0]
    last_epoch: float | None = None
    for i, (epoch, value) in enumerate(pairs):
        epoch = _finite(epoch, f"pairs[{i}] epoch")
        value = _finite(value, f"pairs[{i}] value")
        if last_epoch is not None and epoch <= last_epoch:
            raise ValueError(
                "pairs epochs must be strictly increasing; "
                f"pairs[{i}] epoch {epoch:g} <= previous {last_epoch:g}")
        last_epoch = epoch
        index = int(math.floor((epoch - origin) / dt_s + 0.5))
        if 0 <= index < len(grid):
            sums[index] += value
            counts[index] += 1
    values = [(sums[i] / counts[i] if counts[i] else None)
              for i in range(len(grid))]
    filled = sum(1 for c in counts if c)
    return values, filled / len(grid), counts


def interp_series(pairs: list[list[float]], times: list[float]) -> list[float]:
    """Piecewise-linear interpolation; endpoints clamp (no extrapolation).

    Rejects duplicate timestamps (keep gap detection in check_continuity).
    """
    if not pairs:
        raise ValueError("pairs must be nonempty")
    clean = sorted(((_finite(t, "time"), _finite(v, "value"))
                    for t, v in pairs))
    if any(t1 <= t0 for (t0, _), (t1, _) in zip(clean, clean[1:])):
        raise ValueError("interpolation times must be strictly increasing")
    out = []
    for t in times:
        t = _finite(t, "query time")
        if t <= clean[0][0]:
            out.append(clean[0][1])
        elif t >= clean[-1][0]:
            out.append(clean[-1][1])
        else:
            for (t0, v0), (t1, v1) in zip(clean, clean[1:]):
                if t0 <= t <= t1:
                    frac = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                    out.append(v0 + frac * (v1 - v0))
                    break
    return out


def check_continuity(pairs: list[list[float]], label: str,
                     max_gap_s: float) -> float:
    """Reject gaps larger than max_gap_s; return the nominal (median) step.
    Raises ValueError naming the gap when any interval exceeds max_gap_s.
    """
    if len(pairs) < 2:
        raise ValueError(f"{label}: need >= 2 points for continuity")
    max_gap_s = _finite(max_gap_s, f"{label} max_gap_s")
    if max_gap_s <= 0.0:
        raise ValueError(f"{label}: max_gap_s must be positive")
    times = sorted(_finite(t, f"{label} time") for t, _ in pairs)
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError(
            f"{label}: timestamps must be strictly increasing"
        )
    for v in pairs:
        _finite(v[1], f"{label} value")
    intervals = [b - a for a, b in zip(times, times[1:])]
    nominal = sorted(intervals)[len(intervals) // 2]
    worst = max(intervals)
    if worst > max_gap_s:
        raise ValueError(
            f"{label}: {worst:.0f} s gap exceeds {max_gap_s:.0f} s "
            f"(nominal {nominal:.0f} s); refusing to bridge")
    return nominal


def estimate_lag(upstream: list[float], downstream: list[float],
                 dt_s: float, max_lag_s: float) -> dict[str, Any]:
    """Advective lag from cross-correlation of demeaned series.
    Lag in seconds (downstream behind upstream) plus peak correlation.
    """
    if len(upstream) != len(downstream) or not upstream:
        raise ValueError("series must be nonempty and equal length")
    dt_s = _finite(dt_s, "dt_s")
    if dt_s <= 0.0:
        raise ValueError("dt_s must be positive")
    max_lag = int(_finite(max_lag_s, "max_lag_s") // dt_s)
    if max_lag < 0:
        raise ValueError("max_lag_s must be >= 0")
    mu = math.fsum(upstream) / len(upstream)
    md = math.fsum(downstream) / len(downstream)
    u = [v - mu for v in upstream]
    d = [v - md for v in downstream]
    if all(v == 0.0 for v in u) or all(v == 0.0 for v in d):
        raise ValueError("series must vary for lag estimation")
    best_lag, best_corr = 0, -math.inf
    for lag in range(0, min(max_lag, len(u) - 1) + 1):
        n = len(u) - lag
        num = math.fsum(a * b for a, b in zip(u[:n], d[lag:]))
        den = math.sqrt(math.fsum(a * a for a in u[:n])
                        * math.fsum(b * b for b in d[lag:]))
        corr = num / den if den > 0 else -math.inf
        if corr > best_corr:
            best_corr, best_lag = corr, lag
    return {"lag_s": best_lag * dt_s, "peak_correlation": best_corr,
            "method": "cross_correlation_of_demeaned_series"}


def regime_scores_by_flow(modeled: list[float], observed: list[float],
                          flows: list[float]) -> dict[str, Any]:
    """Scores split by upstream-flow tercile plus the full window.
    Each tercile reports rmse, bias, n; constant flow yields "all" only.
    """
    if not (len(modeled) == len(observed) == len(flows)) or not modeled:
        raise ValueError("modeled, observed, and flows must be nonempty "
                         "and equal length")
    for v in list(modeled) + list(observed) + list(flows):
        _finite(v, "regime value")
    out: dict[str, Any] = {"all": score_paired_series(modeled, observed)}
    ordered = sorted(flows)
    b1 = ordered[len(ordered) // 3]
    b2 = ordered[2 * len(ordered) // 3]
    if b1 == b2:
        return out
    groups: dict[str, list[tuple[float, float]]] = {
        "low": [], "mid": [], "high": []
    }
    for m, o, q in zip(modeled, observed, flows):
        groups["low" if q < b1 else "high" if q >= b2 else "mid"].append((m, o))
    out["bounds_m3_s"] = [b1, b2]
    for name, pairs in groups.items():
        if pairs:
            ms = [p[0] for p in pairs]
            os = [p[1] for p in pairs]
            out[name] = score_paired_series(ms, os)
        else:
            out[name] = {"n": 0.0, "rmse": None, "bias": None,
                         "mae": None, "max_abs": None}
    return out


# Section 1: Dispersion sweep (method of moments)
def pulse_moments(centers_m: list[float], volume_m3: list[float],
                  temperatures_c: list[float],
                  background_c: float) -> dict[str, float]:
    """Mass, centroid, and spatial variance of a temperature anomaly.
    Warm (positive) anomalies only; flip sign for a cold pulse.
    """
    if not centers_m:
        raise ValueError("centers_m, volume_m3, temperatures_c must be nonempty")
    if not (len(centers_m) == len(volume_m3) == len(temperatures_c)):
        raise ValueError(
            f"length mismatch: centers_m={len(centers_m)}, "
            f"volume_m3={len(volume_m3)}, "
            f"temperatures_c={len(temperatures_c)}")
    for i, v in enumerate(volume_m3):
        v = _finite(v, f"volume_m3[{i}]")
        if v <= 0.0:
            raise ValueError(f"volume_m3[{i}] must be positive")
    for i, x in enumerate(centers_m):
        _finite(x, f"centers_m[{i}]")
    background_c = _finite(background_c, "background_c")
    anomalies = [max(0.0, _finite(t, "temperature") - background_c)
                 for t in temperatures_c]
    mass = math.fsum(v * a for v, a in zip(volume_m3, anomalies))
    if mass <= 0.0:
        raise ValueError("pulse has no positive anomaly mass")
    centroid = math.fsum(v * a * x for v, a, x
                         in zip(volume_m3, anomalies, centers_m)) / mass
    variance = math.fsum(v * a * (x - centroid) ** 2 for v, a, x
                         in zip(volume_m3, anomalies, centers_m)) / mass
    peak = max(temperatures_c)
    return {"mass": mass, "centroid_m": centroid,
            "variance_m2": variance, "peak_c": peak}


def uniform_pulse_run(length_m: float = 3000.0, n_cells: int = 60,
                      width_m: float = 22.0, depth_m: float = 1.1,
                      discharge_m3_s: float = 8.0,
                      background_c: float = 15.0, pulse_c: float = 5.0,
                      pulse_sigma_m: float = 150.0,
                      dispersion_m2_s: float = 1.0,
                      duration_s: float = 3600.0,
                      dt_s: float = 5.0) -> dict[str, Any]:
    """Advect one Gaussian pulse; return moment-derived effective D.
    pulse_c is a signed Celsius anomaly added to the Gaussian pulse.
    """
    from .river_transport import Cell
    length_m = _finite(length_m, "length_m")
    width_m = _finite(width_m, "width_m")
    depth_m = _finite(depth_m, "depth_m")
    discharge_m3_s = _finite(discharge_m3_s, "discharge_m3_s")
    dispersion_m2_s = _finite(dispersion_m2_s, "dispersion_m2_s")
    duration_s = _finite(duration_s, "duration_s")
    dt_s = _finite(dt_s, "dt_s")
    pulse_sigma_m = _finite(pulse_sigma_m, "pulse_sigma_m")
    if n_cells < 8:
        raise ValueError("n_cells must be >= 8 for moment resolution")
    if length_m <= 0.0:
        raise ValueError("length_m must be positive")
    if width_m <= 0.0:
        raise ValueError("width_m must be positive")
    if depth_m <= 0.0:
        raise ValueError("depth_m must be positive")
    if discharge_m3_s <= 0.0:
        raise ValueError("discharge_m3_s must be positive")
    if dispersion_m2_s < 0.0:
        raise ValueError("dispersion_m2_s must be nonnegative")
    if duration_s <= 0.0:
        raise ValueError("duration_s must be positive")
    if dt_s <= 0.0 or dt_s > duration_s:
        raise ValueError("dt_s must be positive and <= duration_s")
    if pulse_sigma_m <= 0.0:
        raise ValueError("pulse_sigma_m must be positive")
    dx = length_m / n_cells
    centers = [(i + 0.5) * dx for i in range(n_cells)]
    middle = length_m / 2.0
    cells = [Cell(id=f"u_{i:03d}", length_m=dx, width_m=width_m,
                  volume_m3=dx * width_m * depth_m,
                  initial_c=(background_c + pulse_c * math.exp(
                      -((x - middle) ** 2) / (2.0 * pulse_sigma_m ** 2))),
                  dispersion_m2_s=dispersion_m2_s)
             for i, x in enumerate(centers)]
    river = River(cells, boundary_m3_s=discharge_m3_s,
                  boundary_c=background_c)
    volumes = [c.volume_m3 for c in cells]
    start = pulse_moments(centers, volumes, list(river.temperature_c),
                          background_c)
    river.run(duration_s, dt_s=dt_s, sample_s=duration_s)
    end = pulse_moments(centers, volumes, list(river.temperature_c),
                        background_c)
    d_eff = (end["variance_m2"] - start["variance_m2"]) / (2.0 * duration_s)
    advected = end["centroid_m"] - start["centroid_m"]
    expected = discharge_m3_s / (width_m * depth_m) * duration_s
    return {"specified_d_m2_s": dispersion_m2_s,
            "effective_d_m2_s": d_eff,
            "numerical_d_m2_s": d_eff - dispersion_m2_s,
            "centroid_advected_m": advected,
            "expected_advection_m": expected,
            "advection_error_pct": 100.0 * (advected - expected) / expected,
            "peak_attenuation": (end["peak_c"] - background_c) / pulse_c,
            "budget": river.budget()}


def dispersion_sweep(d_values: list[float] | None = None,
                     **run_kwargs: Any) -> dict[str, Any]:
    """Run the pulse at each D; summarize fidelity and the D=1-vs-85 gap."""
    d_values = list(d_values) if d_values else [0.0, 1.0, 10.0, 85.0]
    runs = [uniform_pulse_run(dispersion_m2_s=d, **run_kwargs)
            for d in d_values]
    code = Path(__file__).read_bytes()
    return {"schema": SCHEMA_DISPERSION,
            "status": "numerical_experiment_not_field_validation",
            "code_sha256": hashlib.sha256(code).hexdigest(),
            "channel": {"note": ("uniform illustrative channel; isolates "
                                 "solver numerics from Firehole geometry"),
                        **{k: run_kwargs.get(k, d)
                           for k, d in (("length_m", 3000.0),
                                        ("n_cells", 60),
                                        ("discharge_m3_s", 8.0),
                                        ("duration_s", 3600.0))}},
            "runs": runs}


# Section 2: Reach heat-budget fit to measured gauges
SURFACE_SOLVER_OPTIONS = ("damped_newton",)


def build_fit_river(volume_m3: float, area_m2: float,
                    boundary_q_m3_s: Any,
                    boundary_t: Series, lateral_q: float, lateral_t: float,
                    met: dict[str, Series], c_mult: float,
                    initial_c: float,
                    surface_solver: str = "damped_newton",
                    max_surface_iterations: int = 24,
                    surface_tolerance_c: float = 1e-7,
                    surface_relaxation: float = 0.8) -> River:
    """Single well-mixed cell with upstream in, lateral in, surface budget.
    boundary_q_m3_s is a scalar or Series; surface_solver = damped_newton.
    """
    from .river_transport import Cell, Source
    volume_m3 = _finite(volume_m3, "volume_m3")
    area_m2 = _finite(area_m2, "area_m2")
    lateral_q = _finite(lateral_q, "lateral_q")
    lateral_t = _finite(lateral_t, "lateral_t")
    c_mult = _finite(c_mult, "c_mult")
    initial_c = _finite(initial_c, "initial_c")
    if volume_m3 <= 0.0:
        raise ValueError("volume_m3 must be positive")
    if area_m2 <= 0.0:
        raise ValueError("area_m2 must be positive")
    if lateral_q < 0.0:
        raise ValueError("lateral_q must be nonnegative")
    if c_mult < 0.0:
        raise ValueError("c_mult must be nonnegative")
    if surface_solver not in SURFACE_SOLVER_OPTIONS:
        raise ValueError(
            f"surface_solver must be one of {SURFACE_SOLVER_OPTIONS}; "
            f"got {surface_solver!r}")
    if (isinstance(max_surface_iterations, bool)
            or not isinstance(max_surface_iterations, int)):
        raise ValueError("max_surface_iterations must be an integer")
    if max_surface_iterations < 1:
        raise ValueError("max_surface_iterations must be positive")
    surface_tolerance_c = _finite(surface_tolerance_c, "surface_tolerance_c")
    if surface_tolerance_c <= 0.0:
        raise ValueError("surface_tolerance_c must be positive")
    surface_relaxation = _finite(surface_relaxation, "surface_relaxation")
    if not 0.0 < surface_relaxation <= 1.0:
        raise ValueError("surface_relaxation must lie in (0, 1]")
    for key in ("air_c", "rh", "wind_mps", "sw", "cloud"):
        if key not in met:
            raise ValueError(f"met missing required Series: {key}")
    surface_area_m2 = area_m2
    params = BudgetParams(c_h=BudgetParams.c_h * c_mult,
                          c_e=BudgetParams.c_e * c_mult)
    return River(
        [Cell(id="reach_lumped", length_m=1000.0,
              width_m=surface_area_m2 / 1000.0, volume_m3=volume_m3,
              initial_c=initial_c, geometry_status=(
                  "authored_illustrative_effective_mixing_geometry"))],
        boundary_m3_s=boundary_q_m3_s, boundary_c=boundary_t,
        sources=[Source(id="aggregate_lateral", cell_id="reach_lumped",
                        flow_m3_s=lateral_q, temperature_c=lateral_t,
                        status="fitted_not_validated")],
        air_c=met["air_c"],
        surface_budget={"rh": {"times_s": list(met["rh"].times_s),
                               "values": list(met["rh"].values)},
                        "wind_mps": {"times_s": list(met["wind_mps"].times_s),
                                     "values": list(met["wind_mps"].values)},
                        "shortwave_w_m2": {
                            "times_s": list(met["sw"].times_s),
                            "values": list(met["sw"].values)},
                        "cloud": {"times_s": list(met["cloud"].times_s),
                                  "values": list(met["cloud"].values)},
                        "params": {"c_h": params.c_h, "c_e": params.c_e}},
        max_surface_iterations=max_surface_iterations,
        surface_tolerance_c=surface_tolerance_c,
        surface_relaxation=surface_relaxation,
    )


# Shared forcing preparation: one construction, two integrators.
def _fit_forcing_arrays(bundle: dict[str, Any],
                        dt_s: float = 900.0) -> dict[str, Any]:
    """Uniform-grid forcing both integrators share bit for bit.
    Backward-Euler and RK45 use these arrays so trajectory diffs are numerics.
    """
    from .fit_grid import build_fit_grid
    up = bundle["sites"]["06036805"]["series"]
    met_rows = bundle["met"]["hourly"]
    # Gap tolerance 4x nominal step. IV nominal 900 s, met nominal 3600 s.
    check_continuity(up["temperature_c"], "upstream temperature", 3600.0)
    check_continuity(up["discharge_m3_s"], "upstream discharge", 3600.0)
    check_continuity([[r[0], r[1]] for r in met_rows], "met air", 14400.0)
    grid_info = build_fit_grid(bundle, dt_s)
    grid = grid_info["grid"]
    t0 = grid_info["t0"]
    up_t = interp_series(up["temperature_c"], grid)
    up_q = interp_series(up["discharge_m3_s"], grid)
    mean_q = math.fsum(up_q) / len(up_q)
    air = interp_series([[r[0], r[1]] for r in met_rows], grid)
    rh = interp_series([[r[0], r[2]] for r in met_rows], grid)
    wind = interp_series([[r[0], r[3]] for r in met_rows], grid)
    sw = interp_series([[r[0], r[4]] for r in met_rows], grid)
    cloud = interp_series([[r[0], r[5]] for r in met_rows], grid)

    def to_series(values: list[float]) -> Series:
        rel = [g - t0 for g in grid]
        return Series(tuple([0.0] + [r for r in rel[1:]]),
                      tuple(values))

    # Measured discharge Series kept alongside the mean for schedule callers.
    up_q_series = to_series(up_q)
    return {"grid": grid, "t0": t0, "mean_q": mean_q,
            "up_t": up_t, "up_q": up_q, "air": air, "rh": rh,
            "wind": wind, "sw": sw, "cloud": cloud,
            "forcing_window": {
                "start_epoch_unix": t0,
                "end_epoch_unix": grid[-1],
                "dt_s": dt_s,
            },
            "data_window": {
                "start_epoch_unix": grid[0],
                "end_epoch_unix": grid[-1],
                "n_samples": len(grid),
            },
            "up_t_series": to_series(up_t),
            "up_q_series": up_q_series,
            "met_series": {"air_c": to_series(air), "rh": to_series(rh),
                           "wind_mps": to_series(wind),
                           "sw": to_series(sw),
                           "cloud": to_series(cloud)}}


def run_fit_forward(bundle: dict[str, Any], volume_m3: float, area_m2: float,
                    lateral_q: float, lateral_t: float, c_mult: float,
                    dt_s: float = 900.0,
                    backend: str = "pairs",
                    boundary_discharge: str = "mean",
                    surface_solver: str = "damped_newton",
                    max_surface_iterations: int = 24,
                    surface_tolerance_c: float = 1e-7,
                    surface_relaxation: float = 0.8) -> dict[str, Any]:
    """Forward lumped run over the bundle window; returns epoch grid and T.
    backend: pairs or pandas; boundary_discharge: mean or measured_series.
    """
    if backend == "pandas":
        from .obs_frame import aligned_fit_arrays
        arrays = aligned_fit_arrays(bundle, dt_s)
    elif backend == "pairs":
        arrays = _fit_forcing_arrays(bundle, dt_s)
    else:
        raise ValueError(f"backend must be 'pairs' or 'pandas': {backend!r}")
    grid = arrays["grid"]
    if boundary_discharge == "mean":
        boundary_q: Any = arrays["mean_q"]
        boundary_q_source = "mean_of_measured_upstream_series"
        discharge_variability_ignored = True
    elif boundary_discharge == "measured_series":
        boundary_q = arrays["up_q_series"]
        boundary_q_source = "measured_upstream_series_schedule"
        discharge_variability_ignored = False
    else:
        raise ValueError(
            f"boundary_discharge must be 'mean' or 'measured_series': "
            f"{boundary_discharge!r}")
    river = build_fit_river(
        volume_m3, area_m2, boundary_q, arrays["up_t_series"],
        lateral_q, lateral_t, arrays["met_series"], c_mult,
        initial_c=arrays["up_t"][0],
        surface_solver=surface_solver,
        max_surface_iterations=max_surface_iterations,
        surface_tolerance_c=surface_tolerance_c,
        surface_relaxation=surface_relaxation)
    n = len(grid) - 1
    frames = river.run(n * dt_s, dt_s=dt_s, sample_s=dt_s)
    modeled = [f["temperature_c"][0] for f in frames]
    if len(modeled) != len(grid):
        raise ArithmeticError(
            f"run_fit_forward produced {len(modeled)} samples for a "
            f"grid of {len(grid)} points; the integrator did not emit "
            f"one sample per grid point")
    budget = river.budget()
    # 1e-5 relative residual tolerates about 0.001 C at reach volumes near 1e5 m3.
    keep: list[str] = [
        "boundary_input_j", "lateral_input_j", "outlet_export_j",
        "surface_exchange_j", "surface_shortwave_j",
        "surface_longwave_j", "surface_sensible_j", "surface_latent_j",
        "storage_change_j", "expected_change_j", "heat_residual_j",
        "heat_relative_residual",
    ]
    extra_keys = (
        "additional_heat_flux_j", "surface_component_sum_j",
        "surface_component_difference_j", "surface_iteration_failures",
        "max_surface_iterations_used",
        "max_surface_linearization_error_w",
    )
    for key in extra_keys:
        if key in budget:
            keep.append(key)
    budget_totals = {k: budget[k] for k in keep}
    boundary_q_report: Any
    discharge_relative_residual: float = 0.0
    discharge_residual_source = "mean_mode_not_applicable"
    if boundary_discharge == "mean":
        boundary_q_report = arrays["mean_q"]
        mode_doc = (
            "constant mean upstream discharge; measured temporal "
            "variation collapsed to the arithmetic mean. "
            "Set boundary_discharge='measured_series' to drive the "
            "measured hydrograph through River (fixes-33 item 1)."
        )
    else:
        boundary_q_report = {
            "times_s": list(arrays["up_q_series"].times_s),
            "values": list(arrays["up_q_series"].values),
            "mean_m3_s": arrays["mean_q"],
        }
        mode_doc = (
            "scheduled measured upstream discharge; face flows and "
            "water budget follow the measured hydrograph per step "
            "(fixes-33 item 1 piecewise-constant Series semantics)."
        )
        # Modeled downstream Q(t) = boundary_q.at(t) + lateral_q; relative RMSE scores the fit.
        try:
            down_pairs = bundle["sites"]["06036905"]["series"].get(
                "discharge_m3_s")
        except (KeyError, TypeError):
            down_pairs = None
        if down_pairs:
            measured_down = interp_series(down_pairs, grid)
            modeled_down = [
                float(arrays["up_q_series"].at(t - grid[0])) + lateral_q
                for t in grid
            ]
            n_q = len(measured_down)
            residuals = [
                m - o for m, o in zip(modeled_down, measured_down)
            ]
            rmse_q = math.sqrt(
                math.fsum(r * r for r in residuals) / n_q)
            mean_measured = math.fsum(measured_down) / n_q
            scale = max(1e-9, abs(mean_measured))
            discharge_relative_residual = rmse_q / scale
            discharge_residual_source = (
                "modeled_vs_measured_downstream_discharge")
        else:
            discharge_residual_source = (
                "measured_series_mode_no_downstream_discharge_in_bundle")
    calibration_mode = (
        "constant_flow_effective_reach_calibration"
        if boundary_discharge == "mean"
        else "scheduled_boundary_effective_reach_calibration"
    )
    return {"grid": grid, "modeled_c": modeled,
            "boundary_q_m3_s": boundary_q_report,
            "boundary_q_source": boundary_q_source,
            "boundary_discharge_mode": mode_doc,
            "boundary_discharge": boundary_discharge,
            "discharge_variability_ignored": discharge_variability_ignored,
            "discharge_relative_residual": discharge_relative_residual,
            "discharge_residual_source": discharge_residual_source,
            "calibration_mode": calibration_mode,
            "numerical_method": {
                "surface_solver": surface_solver,
                "max_surface_iterations": max_surface_iterations,
                "surface_tolerance_c": surface_tolerance_c,
                "surface_relaxation": surface_relaxation,
            },
            "heat_relative_residual": budget["heat_relative_residual"],
            "budget_ok": (budget["heat_relative_residual"] <= 1e-5
                          and budget.get(
                              "surface_iteration_failures", 0) == 0),
            "budget_totals": budget_totals}


OBJECTIVE_WEIGHTS_DEFAULT = {
    "temperature_rmse": 1.0,
    "temperature_abs_bias": 0.25,
    "heat_residual": 0.1,
    "newton_failure_penalty": 10.0,
    "discharge_residual": 0.0,
}


def composite_score(train_rmse: float, train_bias: float,
                    heat_relative_residual: float,
                    surface_iteration_failures: int,
                    weights: dict[str, float] | None = None,
                    discharge_relative_residual: float = 0.0,
                    ) -> dict[str, float]:
    """Named weighted sum of RMSE, abs bias, heat residual, Newton failures, discharge residual.
    discharge_relative_residual only contributes under boundary_discharge measured_series."""
    if weights is None:
        weights = OBJECTIVE_WEIGHTS_DEFAULT
    temp_term = weights["temperature_rmse"] * float(train_rmse)
    bias_term = weights["temperature_abs_bias"] * abs(float(train_bias))
    energy_term = (
        weights["heat_residual"] * abs(float(heat_relative_residual)))
    newton_term = (
        weights["newton_failure_penalty"]
        * float(max(0, int(surface_iteration_failures))))
    discharge_term = (
        weights.get("discharge_residual", 0.0)
        * abs(float(discharge_relative_residual)))
    score = temp_term + bias_term + energy_term + newton_term + discharge_term
    return {
        "score": score,
        "temperature_rmse_term": temp_term,
        "temperature_abs_bias_term": bias_term,
        "heat_residual_term": energy_term,
        "newton_failure_term": newton_term,
        "discharge_residual_term": discharge_term,
    }


def timestep_convergence(bundle: dict[str, Any], volume_m3: float,
                         area_m2: float, lateral_q: float, lateral_t: float,
                         c_mult: float, dt_s: float) -> dict[str, float]:
    """Run the forward model at dt_s and dt_s/2; report agreement.
    Returns max absolute diff and RMSE on the coarser grid samples.
    """
    coarse = run_fit_forward(bundle, volume_m3, area_m2,
                             lateral_q, lateral_t, c_mult, dt_s)
    fine = run_fit_forward(bundle, volume_m3, area_m2,
                           lateral_q, lateral_t, c_mult, dt_s / 2.0)
    coarse_c = coarse["modeled_c"]
    fine_sampled = fine["modeled_c"][::2]
    n_compare = min(len(coarse_c), len(fine_sampled))
    diffs = [abs(coarse_c[i] - fine_sampled[i]) for i in range(n_compare)]
    max_diff = max(diffs) if diffs else 0.0
    rmse_diff = (math.sqrt(math.fsum(d * d for d in diffs) / n_compare)
                 if n_compare else 0.0)
    return {
        "dt_s": float(dt_s),
        "half_dt_s": float(dt_s / 2.0),
        "n_compared": int(n_compare),
        "max_difference_c": float(max_diff),
        "rmse_difference_c": float(rmse_diff),
    }


def reach_heat_fit(bundle: dict[str, Any], volume_m3: float, area_m2: float,
                   lateral_q_grid: list[float],
                   lateral_t_grid: list[float],
                   c_mult_grid: list[float],
                   spinup_s: float = 86400.0,
                   train_frac: float = 0.7,
                   dt_s: float = 900.0,
                   return_all: bool = False,
                   locked_final_frac: float | None = None,
                   volume_sigma_m3: float | None = None,
                   area_sigma_m2: float | None = None,
                   objective_weights: dict[str, float] | None = None,
                   run_timestep_convergence: bool = False,
                   ) -> dict[str, Any]:
    """Grid-search the lumped budget with train/holdout and three null models.
    Null A persistence, Null B mixing-only refit, Null C train climatology.
    """
    weights = (OBJECTIVE_WEIGHTS_DEFAULT if objective_weights is None
               else dict(objective_weights))
    for key in OBJECTIVE_WEIGHTS_DEFAULT:
        if key not in weights:
            raise ValueError(
                f"objective_weights missing key {key!r}")
        _finite(weights[key], f"objective_weights[{key!r}]")
    for name, g in (("lateral_q_grid", lateral_q_grid),
                    ("lateral_t_grid", lateral_t_grid),
                    ("c_mult_grid", c_mult_grid)):
        if not g:
            raise ValueError(f"{name} must be nonempty")
        for i, v in enumerate(g):
            _finite(v, f"{name}[{i}]")
    if not math.isfinite(train_frac) or not 0.0 < train_frac < 1.0:
        raise ValueError("train_frac must lie strictly between 0 and 1")
    if locked_final_frac is not None:
        locked_final_frac = _finite(locked_final_frac, "locked_final_frac")
        if not 0.0 <= locked_final_frac < 1.0:
            raise ValueError(
                "locked_final_frac must satisfy 0 <= frac < 1")
        if train_frac + locked_final_frac >= 1.0:
            raise ValueError(
                "train_frac + locked_final_frac must leave a holdout")
    for name, sigma in (("volume_sigma_m3", volume_sigma_m3),
                        ("area_sigma_m2", area_sigma_m2)):
        if sigma is not None:
            sigma = _finite(sigma, name)
            if sigma < 0.0:
                raise ValueError(f"{name} must be nonnegative")
    spinup_s = _finite(spinup_s, "spinup_s")
    if spinup_s < 0.0:
        raise ValueError("spinup_s must be nonnegative")
    down = bundle["sites"]["06036905"]["series"]
    check_continuity(down["temperature_c"], "downstream temperature", 3600.0)
    lag_info = None
    results: list[dict[str, Any]] = []

    # Cache one forward run per (q, t, c); Null B reuses the same grid.
    forward_cache: dict[tuple, dict[str, Any]] = {}

    def forward(q: float, t: float, c: float) -> dict[str, Any]:
        key = (q, t, c)
        if key not in forward_cache:
            forward_cache[key] = run_fit_forward(
                bundle, volume_m3, area_m2, q, t, c, dt_s)
        return forward_cache[key]

    # Score masks computed once from the first run's grid.
    probe = forward(lateral_q_grid[0], lateral_t_grid[0], c_mult_grid[0])
    grid = probe["grid"]
    if spinup_s >= grid[-1] - grid[0]:
        raise ValueError("spinup_s covers the whole window; no data left")
    target = interp_series(down["temperature_c"], grid)
    up_t = interp_series(bundle["sites"]["06036805"]["series"]
                         ["temperature_c"], grid)
    up_q = interp_series(bundle["sites"]["06036805"]["series"]
                         ["discharge_m3_s"], grid)
    start = next(i for i, g in enumerate(grid) if g - grid[0] >= spinup_s)
    post_spinup_len = len(grid) - start
    split = start + int(post_spinup_len * train_frac)
    if locked_final_frac is None or locked_final_frac == 0.0:
        locked_final_split = len(grid)
    else:
        locked_final_split = len(grid) - int(
            post_spinup_len * locked_final_frac)
        if locked_final_split <= split:
            raise ValueError(
                "locked_final_frac leaves no holdout between train and "
                "locked_final after indexing")
    train = slice(start, split)
    holdout = slice(split, locked_final_split)
    locked_final = slice(locked_final_split, len(grid))
    locked_final_active = (
        locked_final_split < len(grid) and (locked_final.stop - locked_final.start) > 0)

    lag_probe = estimate_lag(up_t[start:split], target[start:split],
                             dt_s, max_lag_s=86400.0)
    lag_info = lag_probe

    def window_score(modeled: list[float], sl: slice) -> dict[str, float]:
        return score_paired_series(modeled[sl], target[sl])

    for q in lateral_q_grid:
        for t in lateral_t_grid:
            for c in c_mult_grid:
                fwd = forward(q, t, c)
                modeled = fwd["modeled_c"]
                tr = window_score(modeled, train)
                row: dict[str, Any] = {
                    "q_lat": q, "t_lat": t, "c_mult": c,
                    "train_rmse": tr["rmse"],
                    "train_bias": tr["bias"],
                    "holdout_rmse": (
                        window_score(modeled, holdout)["rmse"]
                        if (holdout.stop - holdout.start) > 0 else None),
                    "budget_ok": fwd["budget_ok"],
                    "heat_relative_residual": fwd["heat_relative_residual"],
                    "discharge_relative_residual": fwd.get(
                        "discharge_relative_residual", 0.0),
                    "surface_iteration_failures": fwd["budget_totals"].get(
                        "surface_iteration_failures", 0),
                }
                comp = composite_score(
                    row["train_rmse"], row["train_bias"],
                    row["heat_relative_residual"],
                    row["surface_iteration_failures"], weights,
                    discharge_relative_residual=row[
                        "discharge_relative_residual"],
                )
                row["composite_score"] = comp["score"]
                row["composite_terms"] = comp
                if locked_final_active:
                    row["locked_final_rmse"] = window_score(
                        modeled, locked_final)["rmse"]
                results.append(row)
    # Primary ranking by train_rmse; champion prefers budget_ok, tiebreak composite.
    results.sort(key=lambda r: r["train_rmse"])
    valid = [r for r in results if r["budget_ok"]]
    if valid:
        valid.sort(key=lambda r: r["composite_score"])
        champion_row = valid[0]
        champion_selection = "validity_filtered_composite_score"
    else:
        champion_row = results[0]
        champion_selection = "composite_filter_rejected_all_candidates"
    champion: dict[str, Any] = dict(champion_row)
    champion["selection_rule"] = champion_selection
    champ_forward = forward(champion["q_lat"], champion["t_lat"],
                            champion["c_mult"])
    if (holdout.stop - holdout.start) > 0:
        champion["holdout_bias"] = score_paired_series(
            champ_forward["modeled_c"][holdout],
            target[holdout])["bias"]
    else:
        champion["holdout_bias"] = None
    if locked_final_active:
        locked_scores = score_paired_series(
            champ_forward["modeled_c"][locked_final],
            target[locked_final])
        champion["locked_final_rmse"] = locked_scores["rmse"]
        champion["locked_final_bias"] = locked_scores["bias"]
    champion["budget_ok"] = champ_forward["budget_ok"]
    champion["budget_totals"] = champ_forward["budget_totals"]
    axis_grids = {
        "q_lat": lateral_q_grid,
        "t_lat": lateral_t_grid,
        "c_mult": c_mult_grid,
    }
    champion["at_parameter_boundary"] = {
        name: {
            "at_min": champion[name] == min(axis),
            "at_max": champion[name] == max(axis),
            "grid_min": min(axis),
            "grid_max": max(axis),
        }
        for name, axis in axis_grids.items()
    }
    from .surface_flux import describe_surface_model
    champ_params = BudgetParams(
        c_h=BudgetParams.c_h * champion["c_mult"],
        c_e=BudgetParams.c_e * champion["c_mult"])
    champion["surface_model"] = describe_surface_model(
        champ_params,
        status_overrides={
            "c_h": "scaled_by_calibration",
            "c_e": "scaled_by_calibration",
        },
    )
    champion["calibration_hierarchy"] = {
        "L1_fixed_physics": [
            "RHO_CP_J_M3_K", "sigma_Stefan_Boltzmann",
            "latent_heat_vaporization",
        ],
        "L2_authored_defaults": [
            "albedo", "emissivity", "pressure_kpa",
            "cloud_longwave_factor", "a_RH", "b_RH",
            "shortwave_multiplier", "longwave_multiplier",
            "longwave_bias_w_m2",
        ],
        "L3_fitted_effective": ["q_lat", "t_lat", "c_mult"],
        "L4_derived_outputs": [
            "modeled_downstream_temperature_c",
            "effective_turbulent_transfer_coefficients",
        ],
        "note": (
            "L1 physical constants: unchanged. "
            "L2 authored defaults: not fitted here; override via "
            "BudgetParams before building the river. "
            "L3 fitted parameters: effective, not uniquely identified. "
            "L4 derived outputs: computed from L1 through L3. "
            "c_h and c_e are not identified independently from a single "
            "scalar target (see surface_model.not_identified_independently)."
        ),
    }
    champion["calibrated_parameters"] = {
        "q_lat": {
            "meaning": "effective aggregate lateral discharge",
            "units": "m3/s",
            "status": "fitted_not_validated",
            "hierarchy_level": "L3_fitted_effective",
        },
        "t_lat": {
            "meaning": "effective aggregate lateral temperature",
            "units": "C",
            "status": "fitted_not_validated",
            "hierarchy_level": "L3_fitted_effective",
        },
        "c_mult": {
            "meaning": (
                "common multiplier applied to baseline sensible and "
                "latent transfer coefficients; "
                "effective_turbulent_transfer_multiplier under an "
                "identifiability constraint (c_h and c_e not fit "
                "separately)"
            ),
            "units": "dimensionless",
            "status": "fitted_not_validated",
            "hierarchy_level": "L3_fitted_effective",
        },
    }

    null_a = {"name": "upstream_persistence",
              "train_rmse": score_paired_series(
                  up_t[train], target[train])["rmse"],
              "holdout_rmse": score_paired_series(
                  up_t[holdout], target[holdout])["rmse"]}
    noburn = [r for r in results if r["c_mult"] == 0.0]
    if not noburn:
        for q in lateral_q_grid:
            for t in lateral_t_grid:
                modeled_zero = forward(q, t, 0.0)["modeled_c"]
                tr_zero = window_score(modeled_zero, train)
                noburn.append({
                    "q_lat": q, "t_lat": t, "c_mult": 0.0,
                    "train_rmse": tr_zero["rmse"],
                    "train_bias": tr_zero["bias"],
                    "holdout_rmse": window_score(
                        modeled_zero, holdout)["rmse"],
                })
    pick = min(noburn, key=lambda r: r["train_rmse"])
    null_b = {"name": "mixing_only_c0_refit", **pick}

    clim_mean = math.fsum(target[train]) / len(target[train])
    clim = [clim_mean] * len(grid)
    null_c = {"name": "downstream_climatology",
              "train_rmse": window_score(clim, train)["rmse"],
              "holdout_rmse": window_score(clim, holdout)["rmse"]}

    check_split([PRESCRIBED_DISCHARGE, PRESCRIBED_UPSTREAM_TEMPERATURE],
                ["downstream_temperature"])

    parameter_status_summary = {
        "calibrated_effective": ["q_lat", "t_lat", "c_mult"],
        "assumed_authored": [
            "albedo", "emissivity", "c_h", "c_e",
            "pressure_kpa", "cloud_longwave_factor",
            "a_RH", "b_RH",
            "shortwave_multiplier", "longwave_multiplier",
            "longwave_bias_w_m2",
            "volume_m3", "area_m2",
        ],
        "observed_forcing": [
            "air_c", "rh", "wind_mps",
            "shortwave_w_m2", "cloud_fraction",
            "upstream_discharge_m3_s",
            "upstream_temperature_c",
        ],
        "observed_target": ["downstream_temperature_c"],
        "identifiability_note": (
            "c_h and c_e are fit jointly through c_mult; a single "
            "downstream temperature series cannot separate them. "
            "q_lat and t_lat can compensate for each other and for "
            "errors in volume_m3, area_m2, albedo, emissivity, cloud "
            "longwave factor, humidity bias, and shortwave or longwave "
            "multipliers. Treat fitted values as effective, not "
            "uniquely measured."
        ),
        "sensitivity_flags": [
            "c_mult covaries with area_m2 (surface heating power).",
            "q_lat and t_lat trade off along a ridge; the fit's spread "
            "lies in uncertainty.ridge_members.",
            "Constant mean upstream discharge makes regime_scores_by_flow "
            "diagnostic only, not calibration-informed.",
        ],
    }

    effective_geometry = {
        "volume_m3": volume_m3,
        "area_m2": area_m2,
        "surface_area_m2": area_m2,
        "status": ("authored_illustrative_effective_mixing_volume; "
                   "surface area equals area_m2, not cross-sectional "
                   "area; see fixes-15.2 calibration notes"),
    }
    if volume_sigma_m3 is not None:
        effective_geometry["volume_sigma_m3"] = float(volume_sigma_m3)
        effective_geometry["volume_uncertainty_source"] = (
            "caller_supplied_prior_or_measurement_sigma")
    if area_sigma_m2 is not None:
        effective_geometry["area_sigma_m2"] = float(area_sigma_m2)
        effective_geometry["area_uncertainty_source"] = (
            "caller_supplied_prior_or_measurement_sigma")

    timestep_block: dict[str, Any] | None = None
    if run_timestep_convergence:
        timestep_block = timestep_convergence(
            bundle, volume_m3, area_m2,
            champion["q_lat"], champion["t_lat"], champion["c_mult"], dt_s)

    windows = {
        "spinup_s": spinup_s,
        "train_frac": train_frac,
        "train_indices": [train.start, train.stop],
        "holdout_indices": [holdout.start, holdout.stop],
    }
    if locked_final_frac is not None:
        windows["locked_final_frac"] = float(locked_final_frac)
        windows["locked_final_indices"] = [
            locked_final.start, locked_final.stop]
        windows["locked_final_active"] = bool(locked_final_active)

    artifact = {"schema": SCHEMA_FIT,
                "status": "fitted_not_validated_single_window",
                "fetched_at_utc": bundle.get("fetched_at_utc"),
                "calibration_mode": champ_forward["calibration_mode"],
                "numerical_method": champ_forward["numerical_method"],
                "objective_weights": weights,
                "parameter_status_summary": parameter_status_summary,
                "mode_claim": {"prescribed": [PRESCRIBED_DISCHARGE,
                                              PRESCRIBED_UPSTREAM_TEMPERATURE],
                               "validated": ["downstream_temperature"]},
                "effective_geometry": effective_geometry,
                "grids": {"q_lat": lateral_q_grid,
                          "t_lat": lateral_t_grid,
                          "c_mult": c_mult_grid},
                "spinup_s": spinup_s, "train_frac": train_frac,
                "windows": windows,
                "dt_s": dt_s,
                "measured_lag": lag_info,
                "champion": {**champion,
                             "status": "fitted_not_validated_single_window"},
                "top10_train": results[:10],
                "null_models": [null_a, null_b, null_c],
                "regime_scores": regime_scores_by_flow(
                    champ_forward["modeled_c"][holdout], target[holdout],
                    up_q[holdout])
                if (holdout.stop - holdout.start) > 0 else None,
                "n_grid_points": len(results)}
    if timestep_block is not None:
        artifact["timestep_convergence"] = timestep_block
    if return_all:
        artifact["all_results"] = results
    return artifact


# Section 3: SciPy passes: bounded fit, information criteria, IVP cross-check.
LS_BOUNDS = {"q_lat": (0.5, 8.0), "t_lat": (-10.0, 60.0),
             "c_mult": (0.0, 8.0)}


def aic_bic(rss: float, n: int, k: int) -> dict[str, float]:
    """Akaike and Bayesian information criteria from residual sum of squares.
    AIC = n ln(RSS/n) + 2k, BIC = n ln(RSS/n) + k ln n; lower wins.
    """
    rss = _finite(rss, "rss")
    if rss < 0.0:
        raise ValueError("rss must be nonnegative")
    if n <= 0 or k < 0:
        raise ValueError("need n >= 1 and k >= 0")
    if rss == 0.0:
        return {"aic": -math.inf, "bic": -math.inf,
                "n": float(n), "k": float(k)}
    base = n * math.log(rss / n)
    return {"aic": base + 2.0 * k, "bic": base + k * math.log(n),
            "n": float(n), "k": float(k)}


def least_squares_fit(bundle: dict[str, Any], volume_m3: float,
                      area_m2: float,
                      x0: tuple[float, float, float] | None = None,
                      spinup_s: float = 86400.0,
                      train_frac: float = 0.7,
                      dt_s: float = 900.0,
                      max_nfev: int = 60) -> dict[str, Any]:
    """Bounded least-squares refinement of the grid champion.
    scipy.optimize.least_squares over (Q_lat, T_lat, c_mult) on train window.
    """
    import numpy as np
    from scipy.optimize import least_squares
    if x0 is None:
        raise ValueError("x0 (grid champion) is required")
    if isinstance(max_nfev, bool) or not isinstance(max_nfev, int):
        raise ValueError("max_nfev must be an integer")
    if max_nfev <= 0:
        raise ValueError("max_nfev must be positive")
    knob_order = ("q_lat", "t_lat", "c_mult")
    lower = [LS_BOUNDS[k][0] for k in knob_order]
    upper = [LS_BOUNDS[k][1] for k in knob_order]
    for name, value, lo, hi in zip(knob_order, x0, lower, upper):
        xv = _finite(value, f"x0[{name}]")
        if not lo <= xv <= hi:
            raise ValueError(
                f"x0[{name}]={xv:g} outside LS_BOUNDS[{lo:g}, {hi:g}]")
    arrays = _fit_forcing_arrays(bundle, dt_s)
    grid = arrays["grid"]
    down = bundle["sites"]["06036905"]["series"]
    check_continuity(down["temperature_c"], "downstream temperature", 3600.0)
    target = interp_series(down["temperature_c"], grid)
    start = next(i for i, g in enumerate(grid) if g - grid[0] >= spinup_s)
    split = start + int((len(grid) - start) * train_frac)
    train = slice(start, split)
    holdout = slice(split, len(grid))
    train_target = np.asarray(target[train])

    def residuals(x: Any) -> Any:
        q, t, c = (float(x[0]), float(x[1]), float(x[2]))
        fwd = run_fit_forward(bundle, volume_m3, area_m2, q, t, c, dt_s)
        return np.asarray(fwd["modeled_c"][train]) - train_target

    result = least_squares(residuals, list(x0), bounds=(lower, upper),
                           max_nfev=max_nfev)
    q, t, c = (float(result.x[0]), float(result.x[1]),
               float(result.x[2]))
    fwd = run_fit_forward(bundle, volume_m3, area_m2, q, t, c, dt_s)
    train_rmse = score_paired_series(
        fwd["modeled_c"][train], target[train])["rmse"]
    holdout_rmse = score_paired_series(
        fwd["modeled_c"][holdout], target[holdout])["rmse"]
    return {"q_lat": q, "t_lat": t, "c_mult": c,
            "train_rmse": train_rmse, "holdout_rmse": holdout_rmse,
            "nfev": int(result.nfev), "cost": float(result.cost),
            "success": bool(result.success),
            "status": "fitted_not_validated_single_window"}


def ivp_crosscheck(bundle: dict[str, Any], volume_m3: float, area_m2: float,
                   lateral_q: float, lateral_t: float, c_mult: float,
                   dt_s: float = 900.0,
                   euler_dt_s: float | None = None) -> dict[str, Any]:
    """RK45 integration of the lumped cell versus River backward Euler.
    Diffs measure timestep and integration-method error; repeat at smaller dt_s.
    """
    import numpy as np
    from scipy.integrate import solve_ivp
    from .river_transport import RHO_CP_J_M3_K
    from .surface_flux import MetState, flux_at
    arrays = _fit_forcing_arrays(bundle, dt_s)
    grid = arrays["grid"]
    rel = np.asarray([g - grid[0] for g in grid])
    up_t = np.asarray(arrays["up_t"])
    air = np.asarray(arrays["air"])
    rh = np.asarray(arrays["rh"])
    wind = np.asarray(arrays["wind"])
    sw = np.asarray(arrays["sw"])
    cloud = np.asarray(arrays["cloud"])
    mean_q = arrays["mean_q"]
    params = BudgetParams(c_h=BudgetParams.c_h * c_mult,
                          c_e=BudgetParams.c_e * c_mult)

    def hold(values: Any, t: float) -> float:
        """Zero-order hold matching Series.at (bisect_right, previous knot).
        Pre-grid queries return the first value, matching Series.at semantics.
        """
        index = int(np.searchsorted(rel, t, side="right")) - 1
        if index < 0:
            index = 0
        return float(values[min(index, len(values) - 1)])

    def rhs(t: float, y: Any) -> Any:
        temp = float(y[0])
        met = MetState(air_c=hold(air, t), rh=hold(rh, t),
                       wind_mps=hold(wind, t),
                       shortwave_w_m2=hold(sw, t), cloud=hold(cloud, t))
        flux = flux_at(temp, met, params)["net"]
        dtemp = (mean_q * (hold(up_t, t) - temp)
                 + lateral_q * (lateral_t - temp)
                 + area_m2 * flux / RHO_CP_J_M3_K) / volume_m3
        return [dtemp]

    river = build_fit_river(
        volume_m3, area_m2, mean_q, arrays["up_t_series"], lateral_q,
        lateral_t, arrays["met_series"], c_mult,
        initial_c=arrays["up_t"][0])
    n = len(grid) - 1
    step = euler_dt_s if euler_dt_s is not None else dt_s
    if step <= 0:
        raise ValueError("euler_dt_s must be positive")
    sub_steps = round(dt_s / step)
    if sub_steps < 1 or abs(dt_s - sub_steps * step) > 1e-9 * dt_s:
        raise ValueError(
            f"euler_dt_s={step:g} does not divide dt_s={dt_s:g} to "
            f"float tolerance (nearest ratio {sub_steps})")
    frames = river.run(n * dt_s, dt_s=step, sample_s=dt_s)
    euler_t = np.asarray([f["temperature_c"][0] for f in frames])
    solution = solve_ivp(rhs, (0.0, n * dt_s), [arrays["up_t"][0]],
                         method="RK45", t_eval=np.asarray(
                             [i * dt_s for i in range(n + 1)]),
                         rtol=1e-8, atol=1e-10, max_step=dt_s)
    if not solution.success:
        raise ArithmeticError(
            f"solve_ivp failed: {solution.message}")
    rk_t = solution.y[0]
    diff = np.abs(rk_t - euler_t)
    budget = river.budget()
    euler_budget_ok = (
        budget["heat_relative_residual"] <= 1e-5
        and budget.get("surface_iteration_failures", 0) == 0
    )
    surface_solver_diag = {
        "max_iterations_used": budget.get(
            "max_surface_iterations_used", None
        ),
        "iteration_failures": budget.get(
            "surface_iteration_failures", 0
        ),
        "max_surface_linearization_error_w": budget.get(
            "max_surface_linearization_error_w", None
        ),
    }
    return {"n_steps": n + 1, "rk_nfev": int(solution.nfev),
            "euler_dt_s": step,
            "max_abs_diff_c": float(np.max(diff)),
            "mean_abs_diff_c": float(np.mean(diff)),
            "argmax_s": float(int(np.argmax(diff)) * dt_s),
            "rk_final_c": float(rk_t[-1]),
            "euler_final_c": float(euler_t[-1]),
            "euler_budget_ok": euler_budget_ok,
            "budget_ok": euler_budget_ok,
            "budget_ok_scope": (
                "euler_only; RK45 lacks a closed heat residual here, so "
                "this flag reports the River backward-Euler budget only"
            ),
            "surface_solver": surface_solver_diag}


# CLI
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    disp = sub.add_parser("dispersion", help="method-of-moments D sweep")
    disp.add_argument("--out", type=Path, required=True)
    disp.add_argument("--d", type=float, nargs="+",
                      default=[0.0, 1.0, 10.0, 85.0],
                      help=("dispersions to test; D above ~10 needs a "
                            "longer channel than the 3000 m default to keep "
                            "the pulse off the downstream boundary — use "
                            "the API with length_m=6000.0"))

    fit = sub.add_parser("fit", help="lumped reach fit to an obs bundle")
    fit.add_argument("--obs", type=Path, required=True)
    fit.add_argument("--out", type=Path, required=True)
    fit.add_argument("--volume-m3", type=float, required=True)
    fit.add_argument("--area-m2", type=float, required=True)
    fit.add_argument("--q-lat", type=float, nargs="+",
                     default=[3.5, 4.0, 4.37, 4.75, 5.0])
    fit.add_argument("--t-lat", type=float, nargs="+",
                     default=[5.0, 10.0, 15.0, 19.5, 25.0, 35.0, 50.0])
    fit.add_argument("--c-mult", type=float, nargs="+",
                     default=[0.0, 0.5, 1.0, 2.0, 4.0])
    lsfit = sub.add_parser("lsfit", help="grid fit + least-squares polish"
                                         " + AIC/BIC selection")
    lsfit.add_argument("--obs", type=Path, required=True)
    lsfit.add_argument("--out", type=Path, required=True)
    lsfit.add_argument("--volume-m3", type=float, required=True)
    lsfit.add_argument("--area-m2", type=float, required=True)
    lsfit.add_argument("--q-lat", type=float, nargs="+",
                       default=[3.5, 4.0, 4.37, 4.75, 5.0])
    lsfit.add_argument("--t-lat", type=float, nargs="+",
                       default=[5.0, 10.0, 15.0, 19.5, 25.0, 35.0, 50.0])
    lsfit.add_argument("--c-mult", type=float, nargs="+",
                       default=[0.0, 0.5, 1.0, 2.0, 4.0])
    ivp = sub.add_parser("ivp", help="RK45 cross-check of backward-Euler")
    ivp.add_argument("--obs", type=Path, required=True)
    ivp.add_argument("--volume-m3", type=float, required=True)
    ivp.add_argument("--area-m2", type=float, required=True)
    ivp.add_argument("--q-lat", type=float, required=True)
    ivp.add_argument("--t-lat", type=float, required=True)
    ivp.add_argument("--c-mult", type=float, required=True)
    args = parser.parse_args()

    try:
        if args.command == "dispersion":
            document = dispersion_sweep(args.d)
        elif args.command == "ivp":
            bundle = json.loads(args.obs.read_text(encoding="utf-8"))
            if bundle.get("schema") != "yellowstone.firehole_obs.v1":
                raise ValueError("obs bundle has wrong schema")
            check = ivp_crosscheck(bundle, args.volume_m3, args.area_m2,
                                   args.q_lat, args.t_lat, args.c_mult)
            print(f"RK45 vs backward-Euler over {check['n_steps']} steps "
                  f"({check['rk_nfev']} RHS evals):")
            print(f"  max |Δ| {check['max_abs_diff_c']:.4f} C "
                  f"at t={check['argmax_s']:.0f} s, "
                  f"mean {check['mean_abs_diff_c']:.4f} C")
            print(f"  finals: RK45 {check['rk_final_c']:.3f} C, "
                  f"Euler {check['euler_final_c']:.3f} C, "
                  f"Euler budget_ok={check['budget_ok']}")
            return 0
        elif args.command == "lsfit":
            from .hydraulics import residual_diagnostics, skill_scores
            bundle = json.loads(args.obs.read_text(encoding="utf-8"))
            if bundle.get("schema") != "yellowstone.firehole_obs.v1":
                raise ValueError("obs bundle has wrong schema")
            fit_doc = reach_heat_fit(
                bundle, args.volume_m3, args.area_m2,
                args.q_lat, args.t_lat, args.c_mult)
            champ = fit_doc["champion"]
            polished = least_squares_fit(
                bundle, args.volume_m3, args.area_m2,
                (champ["q_lat"], champ["t_lat"], champ["c_mult"]))
            fwd = run_fit_forward(bundle, args.volume_m3, args.area_m2,
                                  polished["q_lat"], polished["t_lat"],
                                  polished["c_mult"])
            grid = fwd["grid"]
            target = interp_series(
                bundle["sites"]["06036905"]["series"]["temperature_c"],
                grid)
            start = next(i for i, g in enumerate(grid)
                         if g - grid[0] >= 86400.0)
            split = start + int((len(grid) - start) * 0.7)
            train = slice(start, split)
            holdout = slice(split, len(grid))
            n_train = split - start
            rss = sum((m - t) ** 2
                      for m, t in zip(fwd["modeled_c"][train],
                                      target[train]))
            models = [{
                "name": "lumped_fit_k3", **aic_bic(rss, n_train, 3),
                "train_rmse": polished["train_rmse"],
                "holdout_rmse": polished["holdout_rmse"]}]
            null_param_counts = {
                "upstream_persistence": 0,
                "mixing_only_c0_refit": 2,
                "mixing_only_c0_at_champion_laterals": 0,
                "downstream_climatology": 1,
            }
            for null in fit_doc["null_models"]:
                k = null_param_counts[null["name"]]
                rss_n = (null["train_rmse"] ** 2) * n_train
                models.append({"name": null["name"],
                               **aic_bic(rss_n, n_train, k),
                               "train_rmse": null["train_rmse"],
                               "holdout_rmse": null["holdout_rmse"]})
            models.sort(key=lambda m: m["aic"])
            document = {
                "schema": "yellowstone.reach_lsfit.v1",
                "status": "fitted_not_validated_single_window",
                "fetched_at_utc": bundle.get("fetched_at_utc"),
                "effective_geometry": {
                    "volume_m3": args.volume_m3,
                    "area_m2": args.area_m2,
                    "surface_area_m2": args.area_m2,
                    "status": ("authored_illustrative_effective_mixing_volume; "
                               "surface area is area_m2, not cross-sectional; "
                               "see fixes-15.2 calibration notes")},
                "grid_champion": champ, "polished": polished,
                "selection": models,
                "train_skill": skill_scores(fwd["modeled_c"][train],
                                            target[train]),
                "holdout_skill": skill_scores(fwd["modeled_c"][holdout],
                                              target[holdout]),
                "train_residuals": residual_diagnostics(
                    fwd["modeled_c"][train], target[train]),
                "holdout_residuals": residual_diagnostics(
                    fwd["modeled_c"][holdout], target[holdout])}
        else:
            bundle = json.loads(args.obs.read_text(encoding="utf-8"))
            if bundle.get("schema") != "yellowstone.firehole_obs.v1":
                raise ValueError("obs bundle has wrong schema")
            document = reach_heat_fit(
                bundle, args.volume_m3, args.area_m2,
                args.q_lat, args.t_lat, args.c_mult)
        text = json.dumps(document, indent=1, allow_nan=False) + "\n"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_name(args.out.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(args.out)
    except (ValueError, KeyError, ArithmeticError, OSError) as error:
        parser.exit(2, f"calibration failed: {error}\n")

    if args.command == "dispersion":
        for run in document["runs"]:
            print(f"D={run['specified_d_m2_s']:>6}: "
                  f"D_eff={run['effective_d_m2_s']:8.3f} "
                  f"(num {run['numerical_d_m2_s']:+.3f}), "
                  f"adv err {run['advection_error_pct']:+.2f}%, "
                  f"peak {run['peak_attenuation']:.3f}")
    elif args.command == "lsfit":
        pol = document["polished"]
        print(f"polished: Q_lat={pol['q_lat']:.3f} T_lat={pol['t_lat']:.3f} "
              f"c_mult={pol['c_mult']:.3f} ({pol['nfev']} evals)")
        print(f"  train RMSE {pol['train_rmse']:.3f} "
              f"holdout RMSE {pol['holdout_rmse']:.3f}")
        print("selection (AIC):")
        for model in document["selection"]:
            print(f"  {model['name']}: AIC {model['aic']:.1f} "
                  f"BIC {model['bic']:.1f} "
                  f"(train {model['train_rmse']:.3f}, "
                  f"holdout {model['holdout_rmse']:.3f})")
        for window in ("train_skill", "holdout_skill"):
            skill = document[window]
            kge = ("n/a (constant model)" if skill["kge"] is None
                   else f"{skill['kge']:.3f}")
            print(f"  {window}: NSE {skill['nse']:.3f} KGE {kge}")
    else:
        champ = document["champion"]
        print(f"champion: Q_lat={champ['q_lat']} T_lat={champ['t_lat']} "
              f"c_mult={champ['c_mult']}")
        print(f"  train RMSE {champ['train_rmse']:.3f} "
              f"holdout RMSE {champ['holdout_rmse']:.3f}")
        for null in document["null_models"]:
            print(f"  null {null['name']}: train {null['train_rmse']:.3f} "
                  f"holdout {null['holdout_rmse']:.3f}")
        print(f"measured lag: {document['measured_lag']}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
