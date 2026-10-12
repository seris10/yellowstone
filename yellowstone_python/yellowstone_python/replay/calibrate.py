"""Reach-scale calibration and dispersion experiments for the Firehole.

Two independent analyses, both labeled, both reproducible:

1. dispersion_sweep -- method-of-moments check of the 1-D solver.
   A Gaussian temperature pulse advects down a uniform channel at
   several specified dispersions D. Spatial variance growth gives an
   EFFECTIVE dispersion D_eff = (s2 - s1) / (2 dt); comparing D_eff
   against specified D separates solver fidelity from the physical
   question of which D the Firehole needs. Pure numerics, no
   observations required.

2. reach_heat_fit -- lumped reach heat budget fitted to MEASURED data.
   Upstream USGS gauge (06036805) supplies boundary discharge and
   temperature; Open-Meteo supplies surface-budget forcing; the
   downstream USGS gauge (06036905) is the calibration target. The
   single-cell River (conservation-tested machinery from
   river_transport) fits lateral inflow (Q_lat, T_lat) and a turbulent
   exchange multiplier, train/holdout split, against two null models:
   upstream persistence and pure mixing without surface exchange.

Status discipline: fitted parameters are labeled fitted_not_validated
until an independent window confirms them; geometry they depend on
(effective volume/area) is authored_illustrative unless stated.
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


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _finite(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def resample_bin_mean(pairs: list[list[float]], grid: list[float],
                      dt_s: float) -> tuple[list[float | None], float]:
    """Bin-average irregular [epoch, value] pairs onto a uniform grid.

    Returns (values, coverage) where missing bins are None and coverage
    is the fraction of filled bins. Bin i covers
    [grid[0] + (i - 0.5) * dt, grid[0] + (i + 0.5) * dt).
    Callers must branch on None/coverage — averaging over Nones or
    treating them as zeros fabricates data.
    """
    dt_s = _finite(dt_s, "dt_s")
    if dt_s <= 0.0:
        raise ValueError("dt_s must be positive")
    if not grid:
        raise ValueError("grid must be nonempty")
    sums = [0.0] * len(grid)
    counts = [0] * len(grid)
    origin = grid[0]
    for epoch, value in pairs:
        epoch = _finite(epoch, "epoch")
        value = _finite(value, "pair value")
        index = int(round((epoch - origin) / dt_s))
        if 0 <= index < len(grid):
            sums[index] += value
            counts[index] += 1
    values = [(sums[i] / counts[i] if counts[i] else None)
              for i in range(len(grid))]
    filled = sum(1 for c in counts if c)
    return values, filled / len(grid)


def interp_series(pairs: list[list[float]], times: list[float]) -> list[float]:
    """Piecewise-linear interpolation; endpoints clamp (no extrapolation).

    Deliberately dumb: gap detection is the caller's job (see
    check_continuity). Never use this to silently bridge instrument gaps.
    """
    if not pairs:
        raise ValueError("pairs must be nonempty")
    clean = sorted(((_finite(t, "time"), _finite(v, "value"))
                    for t, v in pairs))
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
    """Reject instrument gaps instead of interpolating across them.

    Returns the nominal step (median interval). Raises ValueError naming
    the gap if any consecutive interval exceeds max_gap_s. Call before
    interp_series on every ingested series — a bridged multi-day outage
    looks like data and fits to it are fiction.
    """
    if len(pairs) < 2:
        raise ValueError(f"{label}: need >= 2 points for continuity")
    times = sorted(_finite(t, f"{label} time") for t, _ in pairs)
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

    Returns the lag (seconds, downstream behind upstream) maximizing
    correlation, plus the peak correlation. Both series must be equal
    length, uniformly spaced, and non-constant.
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
    """Holdout scores split by upstream-flow tercile plus the full window.

    Aggregate RMSE hides regime failure, so each tercile reports its own
    rmse, bias, and n. Constant flow collapses to the "all" entry only.
    Near-constant flow still emits all three groups; empty groups carry
    n 0 and null scores.
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
    groups = {"low": [], "mid": [], "high": []}
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


# ---------------------------------------------------------------------------
# 1. Dispersion sweep (method of moments)
# ---------------------------------------------------------------------------

def pulse_moments(centers_m: list[float], volume_m3: list[float],
                  temperatures_c: list[float],
                  background_c: float) -> dict[str, float]:
    """Mass, centroid, and spatial variance of a temperature anomaly.

    Negative anomalies are clipped to zero: this measures HEAT pulses.
    A cold pulse needs the sign flipped by the caller, explicitly.
    """
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
    """Advect one Gaussian pulse; return moment-derived effective D."""
    from .river_transport import Cell
    if n_cells < 8:
        raise ValueError("n_cells must be >= 8 for moment resolution")
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


# ---------------------------------------------------------------------------
# 2. Reach heat-budget fit to measured gauges
# ---------------------------------------------------------------------------

def build_fit_river(volume_m3: float, area_m2: float,
                    boundary_q_m3_s: float,
                    boundary_t: Series, lateral_q: float, lateral_t: float,
                    met: dict[str, Series], c_mult: float,
                    initial_c: float) -> River:
    """Single well-mixed cell: measured upstream in, fitted lateral in,
    explicit surface budget with scaled turbulent coefficients."""
    from .river_transport import Cell, Source
    params = BudgetParams(c_h=BudgetParams.c_h * c_mult,
                          c_e=BudgetParams.c_e * c_mult)
    return River(
        [Cell(id="reach_lumped", length_m=1000.0,
              width_m=area_m2 / 1000.0, volume_m3=volume_m3,
              initial_c=initial_c)],
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
    )


# ---------------------------------------------------------------------------
# Shared forcing preparation (one construction, two integrators)
# ---------------------------------------------------------------------------

def _fit_forcing_arrays(bundle: dict[str, Any],
                        dt_s: float = 900.0) -> dict[str, Any]:
    """Uniform-grid forcing both integrators share, bit for bit.

    run_fit_forward (River backward-Euler) and ivp_crosscheck (SciPy
    RK45) build their forcing from these arrays, so trajectory
    differences measure integrator numerics.
    """
    from ..common.hydro_units import validate_usgs_bundle
    validate_usgs_bundle(bundle)
    up = bundle["sites"]["06036805"]["series"]
    met_rows = bundle["met"]["hourly"]
    # Gap tolerance 4x nominal step: a few missed transmissions pass, an
    # outage refuses. IV nominal 900 s, met nominal 3600 s.
    check_continuity(up["temperature_c"], "upstream temperature", 3600.0)
    check_continuity(up["discharge_m3_s"], "upstream discharge", 3600.0)
    check_continuity([[r[0], r[1]] for r in met_rows], "met air", 14400.0)
    t0 = max(up["temperature_c"][0][0], met_rows[0][0])
    t1 = min(up["temperature_c"][-1][0], met_rows[-1][0])
    n = int((t1 - t0) // dt_s)
    grid = [t0 + i * dt_s for i in range(n + 1)]
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

    return {"grid": grid, "t0": t0, "mean_q": mean_q,
            "up_t": up_t, "up_q": up_q, "air": air, "rh": rh,
            "wind": wind, "sw": sw, "cloud": cloud,
            "up_t_series": to_series(up_t),
            "met_series": {"air_c": to_series(air), "rh": to_series(rh),
                           "wind_mps": to_series(wind),
                           "sw": to_series(sw),
                           "cloud": to_series(cloud)}}


def run_fit_forward(bundle: dict[str, Any], volume_m3: float, area_m2: float,
                    lateral_q: float, lateral_t: float, c_mult: float,
                    dt_s: float = 900.0,
                    backend: str = "pairs") -> dict[str, Any]:
    """Forward lumped run over the bundle window; returns epoch grid + T.

    backend="pairs" is the hand-rolled alignment (default: no new
    dependencies); backend="pandas" routes through replay.obs_frame
    (explicit gaps/coverage, same grid convention). The two agree to
    float noise on gap-free data (parity test); the default flips when
    pandas is installed on the project interpreter.
    """
    if backend == "pandas":
        from .obs_frame import aligned_fit_arrays
        arrays = aligned_fit_arrays(bundle, dt_s)
    elif backend == "pairs":
        arrays = _fit_forcing_arrays(bundle, dt_s)
    else:
        raise ValueError(f"backend must be 'pairs' or 'pandas': {backend!r}")
    grid = arrays["grid"]
    river = build_fit_river(
        volume_m3, area_m2, arrays["mean_q"], arrays["up_t_series"],
        lateral_q, lateral_t, arrays["met_series"], c_mult,
        initial_c=arrays["up_t"][0])
    n = len(grid) - 1
    frames = river.run(n * dt_s, dt_s=dt_s, sample_s=dt_s)
    modeled = [f["temperature_c"][0] for f in frames]
    budget = river.budget()
    # Scale-aware closure: reach volumes (~1e5 m3) carry ~1e13-1e14 J, so
    # the solver's 1e-9 demo tolerance is pure float noise here (a 1e-5
    # relative residual is ~0.001 C temperature error). Raw value and
    # component totals are reported for inspection.
    keep = ("boundary_input_j", "lateral_input_j", "outlet_export_j",
            "surface_exchange_j", "surface_shortwave_j",
            "surface_longwave_j", "surface_sensible_j", "surface_latent_j",
            "storage_change_j", "expected_change_j", "heat_residual_j",
            "heat_relative_residual")
    return {"grid": grid, "modeled_c": modeled,
            "boundary_q_m3_s": arrays["mean_q"],
            "heat_relative_residual": budget["heat_relative_residual"],
            "budget_ok": budget["heat_relative_residual"] <= 1e-5,
            "budget_totals": {k: budget[k] for k in keep}}


def reach_heat_fit(bundle: dict[str, Any], volume_m3: float, area_m2: float,
                   lateral_q_grid: list[float],
                   lateral_t_grid: list[float],
                   c_mult_grid: list[float],
                   spinup_s: float = 86400.0,
                   train_frac: float = 0.7,
                   dt_s: float = 900.0,
                   return_all: bool = False) -> dict[str, Any]:
    """Grid-search the lumped budget; train/holdout + null-model comparison.

    Null A (persistence): downstream == upstream now. Null B (mixing
    only): same model with c_mult = 0, Q_lat/T_lat refit on train.
    Null C (climatology): downstream == train-window mean, one estimated
    parameter for selection scoring.

    return_all=True adds every grid row under "all_results" (needed by
    the ridge ensemble in uncertainty.py); the default artifact keeps
    top10 only.
    """
    down = bundle["sites"]["06036905"]["series"]
    check_continuity(down["temperature_c"], "downstream temperature", 3600.0)
    lag_info = None
    best: dict[str, Any] | None = None
    results = []

    # Cache one forward run per (q, t, c) — reuse Null B from the same grid.
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
    split = start + int((len(grid) - start) * train_frac)
    train = slice(start, split)
    holdout = slice(split, len(grid))

    lag_probe = estimate_lag(up_t[start:split], target[start:split],
                             dt_s, max_lag_s=86400.0)
    lag_info = lag_probe

    def window_score(modeled: list[float], sl: slice) -> dict[str, float]:
        return score_paired_series(modeled[sl], target[sl])

    for q in lateral_q_grid:
        for t in lateral_t_grid:
            for c in c_mult_grid:
                modeled = forward(q, t, c)["modeled_c"]
                tr = window_score(modeled, train)
                results.append({"q_lat": q, "t_lat": t, "c_mult": c,
                                "train_rmse": tr["rmse"],
                                "train_bias": tr["bias"],
                                "holdout_rmse": window_score(
                                    modeled, holdout)["rmse"]})
    results.sort(key=lambda r: r["train_rmse"])
    champion = dict(results[0])
    champ_forward = forward(champion["q_lat"], champion["t_lat"],
                            champion["c_mult"])
    champion["holdout_bias"] = score_paired_series(
        champ_forward["modeled_c"][holdout],
        target[holdout])["bias"]
    champion["budget_ok"] = champ_forward["budget_ok"]
    champion["budget_totals"] = champ_forward["budget_totals"]

    null_a = {"name": "upstream_persistence",
              "train_rmse": score_paired_series(
                  up_t[train], target[train])["rmse"],
              "holdout_rmse": score_paired_series(
                  up_t[holdout], target[holdout])["rmse"]}
    noburn = [r for r in results if r["c_mult"] == 0.0]
    if not noburn:
        zero = forward(champion["q_lat"], champion["t_lat"], 0.0)["modeled_c"]
        null_b = {"name": "mixing_only_c0_at_champion_laterals",
                  "train_rmse": window_score(zero, train)["rmse"],
                  "holdout_rmse": window_score(zero, holdout)["rmse"]}
    else:
        pick = min(noburn, key=lambda r: r["train_rmse"])
        null_b = {"name": "mixing_only_c0_refit", **pick}

    clim_mean = math.fsum(target[train]) / len(target[train])
    clim = [clim_mean] * len(grid)
    null_c = {"name": "downstream_climatology",
              "train_rmse": window_score(clim, train)["rmse"],
              "holdout_rmse": window_score(clim, holdout)["rmse"]}

    check_split([PRESCRIBED_DISCHARGE, PRESCRIBED_UPSTREAM_TEMPERATURE],
                ["downstream_temperature"])

    return {"schema": SCHEMA_FIT,
            "status": "fitted_not_validated_single_window",
            "fetched_at_utc": bundle.get("fetched_at_utc"),
            "mode_claim": {"prescribed": [PRESCRIBED_DISCHARGE,
                                          PRESCRIBED_UPSTREAM_TEMPERATURE],
                           "validated": ["downstream_temperature"]},
            "effective_geometry": {
                "volume_m3": volume_m3, "area_m2": area_m2,
                "status": ("authored_illustrative_effective_mixing_volume; "
                           "see sensitivity in parameter_notes")},
            "grids": {"q_lat": lateral_q_grid, "t_lat": lateral_t_grid,
                      "c_mult": c_mult_grid},
            "spinup_s": spinup_s, "train_frac": train_frac,
            "measured_lag": lag_info,
            "champion": {**champion,
                         "status": "fitted_not_validated_single_window"},
            "top10_train": results[:10],
            "null_models": [null_a, null_b, null_c],
            "regime_scores": regime_scores_by_flow(
                champ_forward["modeled_c"][holdout], target[holdout],
                up_q[holdout]),
            "n_grid_points": len(results),
            **({"all_results": results} if return_all else {})}


# ---------------------------------------------------------------------------
# 3. SciPy passes (A2): bounded fit, information criteria, IVP cross-check
# ---------------------------------------------------------------------------

LS_BOUNDS = {"q_lat": (0.5, 8.0), "t_lat": (-10.0, 60.0),
             "c_mult": (0.0, 8.0)}


def aic_bic(rss: float, n: int, k: int) -> dict[str, float]:
    """Akaike / Bayesian information criteria from a residual sum of squares.

    AIC = n ln(RSS/n) + 2k, BIC = n ln(RSS/n) + k ln n. Lower wins.
    k counts process parameters. The residual variance term is omitted
    uniformly, so relative rankings match the full K convention.
    """
    rss = _finite(rss, "rss")
    if rss <= 0.0:
        raise ValueError("rss must be positive")
    if n <= 0 or k < 0:
        raise ValueError("need n >= 1 and k >= 0")
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

    scipy.optimize.least_squares over (Q_lat, T_lat, c_mult) against the
    train window, starting at the grid champion (or x0). Residuals are
    raw train errors, so the optimum matches the grid's RMSE scale.
    max_nfev caps forward runs (each costs one); the grid stays the
    global search, this is local polish — not a replacement.
    """
    import numpy as np
    from scipy.optimize import least_squares
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

    if x0 is None:
        raise ValueError("x0 (grid champion) is required")
    lower = [LS_BOUNDS[k][0] for k in ("q_lat", "t_lat", "c_mult")]
    upper = [LS_BOUNDS[k][1] for k in ("q_lat", "t_lat", "c_mult")]
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
    """Independent RK45 integration of the lumped cell vs backward-Euler.

    Same volume, area, laterals, and the shared forcing arrays — the
    only difference is the integrator: adaptive RK45 on the NONLINEAR
    surface budget vs River's backward-Euler on step-frozen linearized
    forcing. At the fit's dt the two differ by first-order truncation
    (tenths of a °C on fast transients — measured, not assumed), so the
    verification is CONVERGENCE: halve euler_dt_s and the max gap must
    roughly halve. euler_dt_s defaults to dt_s and must divide it; both
    trajectories are compared at the dt_s sample times.
    """
    import numpy as np
    from scipy.integrate import solve_ivp
    from .river_transport import RHO_CP_J_M3_K
    from .surface_flux import BudgetParams, MetState, flux_at
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
        """Zero-order hold matching Series.at (bisect_right, previous knot)."""
        index = int(np.searchsorted(rel, t, side="right")) - 1
        if index < 0:
            index = len(values) - 1
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
    if step <= 0 or dt_s % step != 0:
        raise ValueError("euler_dt_s must be positive and divide dt_s")
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
    return {"n_steps": n + 1, "rk_nfev": int(solution.nfev),
            "euler_dt_s": step,
            "max_abs_diff_c": float(np.max(diff)),
            "mean_abs_diff_c": float(np.mean(diff)),
            "argmax_s": float(int(np.argmax(diff)) * dt_s),
            "rk_final_c": float(rk_t[-1]),
            "euler_final_c": float(euler_t[-1]),
            "budget_ok": river.budget()["heat_relative_residual"] <= 1e-5}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
            for null, k in zip(fit_doc["null_models"], (0, 2, 1)):
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
                    "status": ("authored_illustrative_effective_"
                               "mixing_volume")},
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
