"""Applicable numerical benchmarks for the declared equation level."""
from __future__ import annotations
from yellowstone_python.common.io import sha256_file

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from yellowstone_python.river.river_transport import Cell, RHO_CP_J_M3_K, River, Source, Series

SCHEMA = "yellowstone.numerics_benchmarks.v1"

NOT_APPLICABLE = [
    {
        "benchmark": "lake_at_rest_over_variable_bed",
        "reason": "requires unsteady momentum with well-balanced bed terms; "
                  "declared level solves no momentum equation",
    },
    {
        "benchmark": "dam_break_transient",
        "reason": "requires conservation-law momentum plus wetting and "
                  "drying; declared level uses prescribed discharge",
    },
]


def _max_abs_diff(a: Any, b: Any) -> float:
    """Maximum absolute pairwise gap; rejects empty or mismatched inputs."""
    a_list, b_list = list(a), list(b)
    if not a_list or not b_list:
        raise ValueError("_max_abs_diff requires nonempty sequences")
    if len(a_list) != len(b_list):
        raise ValueError(
            f"_max_abs_diff requires equal lengths, "
            f"got {len(a_list)} and {len(b_list)}"
        )
    return max(abs(x - y) for x, y in zip(a_list, b_list))


def benchmark_restart_equivalence() -> dict[str, Any]:
    """Split run equals continuous run on identical forcing."""
    def make() -> River:
        # Fresh cells per River so no state carries between runs.
        cells = [
            Cell(f"c{i}", 50.0, 22.0, 50.0 * 22.0 * 1.1, 15.0,
                 dispersion_m2_s=1.0, exchange_w_m2_k=12.0)
            for i in range(5)
        ]
        return River(
            cells, boundary_m3_s=8.0, boundary_c=17.5, air_c=9.0,
            sources=[Source("lat", "c2", 0.25, 60.0)],
        )

    whole = make()
    whole.run(600.0, dt_s=10.0, sample_s=600.0)
    split = make()
    split.run(300.0, dt_s=10.0, sample_s=300.0)
    split.run(300.0, dt_s=10.0, sample_s=300.0)
    gap = _max_abs_diff(whole.temperature_c, split.temperature_c)

    mid = make()
    mid.run(300.0, dt_s=10.0, sample_s=300.0)
    resumed = River(
        [Cell(f"c{i}", 50.0, 22.0, 50.0 * 22.0 * 1.1, t,
              dispersion_m2_s=1.0, exchange_w_m2_k=12.0)
         for i, t in enumerate(mid.temperature_c)],
        boundary_m3_s=8.0, boundary_c=17.5, air_c=9.0,
        sources=[Source("lat", "c2", 0.25, 60.0)],
    )
    resumed.run(300.0, dt_s=10.0, sample_s=300.0)
    fresh_gap = _max_abs_diff(whole.temperature_c, resumed.temperature_c)

    tolerance = 1e-9
    return {
        "name": "restart_equivalence",
        "split_run_gap_c": gap,
        "fresh_object_gap_c": fresh_gap,
        "tolerance_c": tolerance,
        "passed": gap <= tolerance and fresh_gap <= tolerance,
        "scope": "constant forcing; time-varying forcing needs clock-offset "
                 "restart support before a matching claim",
    }


def benchmark_closed_thermal() -> dict[str, Any]:
    """Isolated cells relax without energy drift."""
    cells = [
        Cell("a", 10.0, 1.0, 10.0, 10.0, dispersion_m2_s=2.0),
        Cell("b", 30.0, 1.0, 30.0, 30.0, dispersion_m2_s=2.0),
    ]
    river = River(cells, 0.0, 0.0)
    start_mean = math.fsum(
        c.volume_m3 * t for c, t in zip(cells, river.temperature_c)
    ) / math.fsum(c.volume_m3 for c in cells)
    river.run(3600.0, dt_s=60.0, sample_s=3600.0)
    end_mean = math.fsum(
        c.volume_m3 * t for c, t in zip(cells, river.temperature_c)
    ) / math.fsum(c.volume_m3 for c in cells)
    budget = river.budget()
    drift = abs(end_mean - start_mean)
    tolerance = 1e-9
    # Closed domain: zero boundary inflow and zero outlet export.
    boundary_j = abs(budget["boundary_input_j"])
    outlet_j = abs(budget["outlet_export_j"])
    return {
        "name": "closed_thermal_system",
        "start_volume_mean_c": start_mean,
        "end_volume_mean_c": end_mean,
        "drift_c": drift,
        "heat_relative_residual": budget["heat_relative_residual"],
        "boundary_input_j": budget["boundary_input_j"],
        "outlet_export_j": budget["outlet_export_j"],
        "tolerance_c": tolerance,
        "passed": (
            drift <= tolerance
            and budget["heat_relative_residual"] <= 1e-9
            and boundary_j == 0.0
            and outlet_j == 0.0
        ),
    }


def benchmark_two_stream_mixing() -> dict[str, Any]:
    """Steady cell matches the analytic flow-weighted mixture."""
    q1, t1 = 8.0, 10.0
    q2, t2 = 2.0, 30.0
    river = River(
        [Cell("c", 100.0, 10.0, 100.0, 12.0)],
        boundary_m3_s=q1, boundary_c=t1,
        sources=[Source("trib", "c", q2, t2)],
    )
    (steady,) = river.steady_temperatures()
    expected = (q1 * t1 + q2 * t2) / (q1 + q2)
    gap = abs(steady - expected)
    tolerance = 1e-9
    return {
        "name": "two_stream_mixing",
        "steady_c": steady,
        "expected_c": expected,
        "gap_c": gap,
        "tolerance_c": tolerance,
        "passed": gap <= tolerance,
        "scope": "equal heat capacity, no surface exchange",
    }


def benchmark_conservative_tracer() -> dict[str, Any]:
    """Pulse centroid advects with the mean flow; budget closes."""
    n = 20
    length_m = 2000.0
    dx = length_m / n
    width_m, depth_m = 22.0, 1.1
    discharge = 8.0
    background = 15.0
    duration_s = 600.0
    centers = [(i + 0.5) * dx for i in range(n)]
    middle = length_m / 2.0
    cells = [
        Cell(f"u_{i:03d}", dx, width_m, dx * width_m * depth_m,
             background + 5.0 * math.exp(
                 -((x - middle) ** 2) / (2.0 * 150.0 ** 2)))
        for i, x in enumerate(centers)
    ]
    river = River(cells, boundary_m3_s=discharge,
                  boundary_c=background)
    volumes = [c.volume_m3 for c in cells]

    def centroid(temps: Any) -> float:
        anomalies = [max(0.0, t - background) for t in temps]
        mass = math.fsum(v * a for v, a in zip(volumes, anomalies))
        if mass <= 0.0:
            raise ArithmeticError("tracer pulse left the domain")
        return math.fsum(v * a * x for v, a, x in zip(
            volumes, anomalies, centers)) / mass

    start = centroid(river.temperature_c)
    river.run(duration_s, dt_s=5.0, sample_s=duration_s)
    advected = centroid(river.temperature_c) - start
    expected = discharge / (width_m * depth_m) * duration_s
    error_pct = 100.0 * (advected - expected) / expected
    budget = river.budget()
    # Pulse retention: anomaly mass in the downstream-most 10% of cells stays below 1%.
    tail_cells = max(1, n // 10)
    end_temps = list(river.temperature_c)
    anomalies_end = [max(0.0, t - background) for t in end_temps]
    tail_mass = math.fsum(
        v * a for v, a in zip(
            volumes[-tail_cells:], anomalies_end[-tail_cells:]))
    total_mass = math.fsum(v * a for v, a in zip(volumes, anomalies_end))
    tail_fraction = tail_mass / total_mass if total_mass > 0.0 else 0.0
    pulse_off_outlet = tail_fraction < 0.01
    passed = (budget["heat_relative_residual"] <= 1e-9
              and abs(error_pct) <= 5.0
              and pulse_off_outlet)
    return {
        "name": "conservative_tracer",
        "advected_m": advected,
        "expected_m": expected,
        "advection_error_pct": error_pct,
        "heat_relative_residual": budget["heat_relative_residual"],
        "outlet_tail_mass_fraction": tail_fraction,
        "outlet_tail_cell_count": tail_cells,
        "pulse_off_outlet": pulse_off_outlet,
        "passed": passed,
    }


def _observed_rates(errors: list[float]) -> list[float]:
    """Pairwise log2 error ratios for successive halving refinements."""
    if len(errors) < 2:
        raise ValueError("at least two errors are required")
    for e in errors:
        if not math.isfinite(e) or e < 0:
            raise ValueError("errors must be finite and nonnegative")
    rates = []
    for coarse, fine in zip(errors, errors[1:]):
        if fine == 0.0:
            rates.append(math.inf if coarse > 0.0 else 0.0)
        elif coarse == 0.0:
            rates.append(-math.inf)
        else:
            rates.append(math.log2(coarse / fine))
    return rates


def benchmark_temporal_convergence() -> dict[str, Any]:
    """Backward Euler rate on a single-cell relaxation with exact solution."""
    exact = 20.0 - 10.0 * math.exp(-1.0)
    dts = [2.0, 1.0, 0.5]
    errors = []
    for dt in dts:
        river = River([Cell("c", 10.0, 1.0, 10.0, 10.0)],
                      boundary_m3_s=1.0, boundary_c=20.0)
        river.run(10.0, dt_s=dt, sample_s=10.0)
        errors.append(abs(river.temperature_c[0] - exact))
    rates = _observed_rates(errors)
    passed = all(0.7 <= r <= 1.3 for r in rates)
    return {
        "name": "temporal_convergence",
        "method": "backward Euler with direct tridiagonal solve",
        "expected_order": 1.0,
        "rate_tolerance": [0.7, 1.3],
        "dt_s": dts,
        "errors_c": errors,
        "observed_rates": rates,
        "passed": passed,
    }


def benchmark_spatial_convergence() -> dict[str, Any]:
    """Upwind advection rate against an exponential steady profile."""
    discharge, upstream, air = 2.0, 20.0, 5.0
    width, coef, length = 20.0, 100.0, 3000.0
    decay = coef * width / RHO_CP_J_M3_K / discharge

    def analytic(x: float) -> float:
        return air + (upstream - air) * math.exp(-decay * x)

    counts = [15, 30, 60]
    errors = []
    for n in counts:
        dx = length / n
        cells = [Cell(f"c{i}", dx, width, dx * width * 1.1, 12.0,
                      exchange_w_m2_k=coef) for i in range(n)]
        river = River(cells, boundary_m3_s=discharge,
                      boundary_c=upstream, air_c=air)
        steady = river.steady_temperatures()
        errors.append(max(abs(t - analytic((i + 0.5) * dx))
                          for i, t in enumerate(steady)))
    rates = _observed_rates(errors)
    passed = all(0.7 <= r <= 1.3 for r in rates)
    return {
        "name": "spatial_convergence",
        "method": "first-order upwind steady solve",
        "expected_order": 1.0,
        "rate_tolerance": [0.7, 1.3],
        "n_cells": counts,
        "errors_c": errors,
        "observed_rates": rates,
        "passed": passed,
    }


def _danckwerts_analytic(discharge: float, width: float,
                          depth: float, coef: float, length: float,
                          upstream: float, air: float,
                          disp: float) -> tuple:
    """Closed-form steady profile for feed inlet plus zero-flux outlet."""
    area = width * depth
    exchange = coef * width / RHO_CP_J_M3_K
    da = disp * area
    disc = math.sqrt(discharge * discharge + 4.0 * da * exchange)
    rp = (discharge + disc) / (2.0 * da)
    rm = (discharge - disc) / (2.0 * da)
    dtemp = upstream - air
    factor = math.exp((rm - rp) * length)
    c2 = (-discharge * dtemp / exchange) / (1.0 / rm - (rm / rp / rp) * factor)
    c1 = -c2 * (rm / rp) * factor

    def analytic(x: float) -> float:
        return air + c1 * math.exp(rp * x) + c2 * math.exp(rm * x)

    return analytic, 1.0 / rp, -1.0 / rm


def benchmark_spatial_convergence_dispersive() -> dict[str, Any]:
    """Upwind rate with nonzero dispersion at production coefficients."""
    cases = []
    for disp, discharge, coef in ((1.0, 0.05, 10.0), (85.0, 2.0, 100.0)):
        width, depth, length = 20.0, 1.1, 3000.0
        upstream, air = 20.0, 5.0
        analytic, diffusive_m, decay_m = _danckwerts_analytic(
            discharge, width, depth, coef, length, upstream, air, disp)
        counts = [15, 30, 60]
        errors = []
        for n in counts:
            dx = length / n
            area = width * depth
            cells = [Cell(f"c{i}", dx, width, dx * area, 12.0,
                          dispersion_m2_s=disp, exchange_w_m2_k=coef)
                     for i in range(n)]
            river = River(cells, boundary_m3_s=discharge,
                          boundary_c=upstream, air_c=air)
            steady = river.steady_temperatures()
            errors.append(max(abs(t - analytic((i + 0.5) * dx))
                              for i, t in enumerate(steady)))
        rates = _observed_rates(errors)
        cases.append({
            "dispersion_m2_s": disp,
            "discharge_m3_s": discharge,
            "exchange_w_m2_k": coef,
            "diffusive_length_m": diffusive_m,
            "decay_length_m": decay_m,
            "n_cells": counts,
            "errors_c": errors,
            "observed_rates": rates,
        })
    passed = all(0.7 <= r <= 1.3
                 for case in cases for r in case["observed_rates"])
    return {
        "name": "spatial_convergence_dispersive",
        "method": "first-order upwind steady solve with centered "
                  "harmonic dispersion",
        "expected_order": 1.0,
        "cases": cases,
        "passed": passed,
    }


def benchmark_diffusive_decay() -> dict[str, Any]:
    """Centered dispersion order from Neumann cosine decay at zero discharge."""
    width, depth, length = 20.0, 1.1, 1000.0
    disp, coef, air = 1.0, 12.0, 5.0
    area = width * depth
    lam = coef / (RHO_CP_J_M3_K * depth)
    wave = math.pi / length
    beta = disp * wave * wave + lam
    amp = 5.0

    def exact(x: float, t: float) -> float:
        return air + amp * math.exp(-beta * t) * math.cos(wave * x)

    def run_decay(n: int, dt: float, duration: float) -> float:
        dx = length / n
        cells = [Cell(f"d{i}", dx, width, dx * area,
                      exact((i + 0.5) * dx, 0.0),
                      dispersion_m2_s=disp, exchange_w_m2_k=coef)
                 for i in range(n)]
        river = River(cells, boundary_m3_s=0.0, boundary_c=air, air_c=air)
        river.run(duration, dt_s=dt, sample_s=duration)
        return max(abs(t - exact((i + 0.5) * dx, duration))
                   for i, t in enumerate(river.temperature_c))

    day = 86400.0
    counts = [15, 30, 60]
    spatial_errors = [run_decay(n, 5.0, day) for n in counts]
    spatial_rates = _observed_rates(spatial_errors)
    dts = [480.0, 240.0, 120.0]
    temporal_errors = [run_decay(120, dt, 2.0 * day) for dt in dts]
    temporal_rates = _observed_rates(temporal_errors)
    passed = (all(1.5 <= r <= 2.5 for r in spatial_rates)
              and all(0.7 <= r <= 1.3 for r in temporal_rates))
    return {
        "name": "diffusive_decay",
        "method": "backward Euler with centered harmonic dispersion",
        "expected_spatial_order": 2.0,
        "expected_temporal_order": 1.0,
        "n_cells": counts,
        "spatial_errors_c": spatial_errors,
        "spatial_rates": spatial_rates,
        "dt_s": dts,
        "temporal_errors_c": temporal_errors,
        "temporal_rates": temporal_rates,
        "passed": passed,
    }


def _mms_wave_run(n: int, dt: float, duration: float) -> tuple:
    """Traveling sine against its analytic source; error plus budget."""
    length, width, depth = 3000.0, 20.0, 1.1
    discharge, disp, coef = 2.0, 1.0, 12.0
    air, amp = 5.0, 5.0
    area = width * depth
    vel = discharge / area
    wave = 2.0 * math.pi / length
    lam = coef / (RHO_CP_J_M3_K * depth)
    src = lam + disp * wave * wave

    def exact(x: float, t: float) -> float:
        return air + amp * math.sin(wave * (x - vel * t))

    dx = length / n
    vol = dx * area
    nsteps = int(round(duration / dt))
    knots = [i * dt for i in range(nsteps + 1)]
    heat = {}
    for i in range(n):
        x = (i + 0.5) * dx
        heat[f"m{i}"] = {
            "times_s": knots,
            "values": [src * (exact(x, t) - air) * vol * RHO_CP_J_M3_K
                       for t in knots],
        }
    cells = [Cell(f"m{i}", dx, width, vol, exact((i + 0.5) * dx, 0.0),
                  dispersion_m2_s=disp, exchange_w_m2_k=coef)
             for i in range(n)]
    river = River(
        cells, boundary_m3_s=discharge,
        boundary_c={"times_s": knots,
                    "values": [exact(0.0, t) for t in knots]},
        air_c=air, cell_heat_w=heat)
    river.run(duration, dt_s=dt, sample_s=duration)
    error = max(abs(t - exact((i + 0.5) * dx, duration))
                for i, t in enumerate(river.temperature_c)
                if 0 < i < n - 1)
    return error, river.budget()["heat_relative_residual"]


def benchmark_mms_traveling_wave() -> dict[str, Any]:
    """Full unsteady operator rate from a manufactured traveling wave."""
    hour = 3600.0
    counts = [15, 30, 60]
    spatial_errors = [run[0] for run in
                      (_mms_wave_run(n, 30.0, 3.0 * hour) for n in counts)]
    spatial_rates = _observed_rates(spatial_errors)
    dts = [1440.0, 720.0, 360.0]
    temporal_runs = [_mms_wave_run(480, dt, 6.0 * hour) for dt in dts]
    temporal_errors = [run[0] for run in temporal_runs]
    temporal_rates = _observed_rates(temporal_errors)
    budget_residual = max(run[1] for run in temporal_runs)
    passed = (all(0.7 <= r <= 1.3 for r in spatial_rates)
              and all(0.7 <= r <= 1.3 for r in temporal_rates)
              and budget_residual <= 1e-9)
    return {
        "name": "mms_traveling_wave",
        "method": "backward Euler with upwind advection, centered "
                  "harmonic dispersion, and per-cell analytic source",
        "expected_order": 1.0,
        "n_cells": counts,
        "spatial_errors_c": spatial_errors,
        "spatial_rates": spatial_rates,
        "dt_s": dts,
        "temporal_errors_c": temporal_errors,
        "temporal_rates": temporal_rates,
        "heat_relative_residual": budget_residual,
        "passed": passed,
    }


def benchmark_live_step_sizes(config: dict, duration_s: float = 7200.,
                              sample_s: float = 60.) -> dict:
    """Measure timestep temperature error and downstream thermal-front arrival."""
    import copy
    import time
    from yellowstone_python.river.river_transport import make_replay
    candidates = (1., 2., 5., 10., 20., 40.)
    results = []
    for model in ("newton_lumped", "explicit_budget"):
        base = copy.deepcopy(config)
        if model == "newton_lumped":
            base.pop("surface_budget", None)
        elif base.get("surface_budget") is None:
            from yellowstone_python.river.surface_flux import spec_from_series
            base["surface_budget"] = spec_from_series(.45, 2., 700., .16)
        value = float(Series.parse(base["boundary_c"]).at(0.))
        base["boundary_c"] = {"times_s": [0., 600.], "values": [value, value + 2.]}
        base.update(duration_s=duration_s, sample_s=sample_s, initialize_steady=False)
        docs = {}
        timing = {}
        for step in candidates:
            started = time.perf_counter()
            docs[step] = make_replay({**base, "dt_s": step})
            timing[step] = time.perf_counter() - started
        reference = docs[1.]["frames"]
        cell_index = min(len(reference[0]["temperature_c"]) - 1, len(reference[0]["temperature_c"]) // 3)
        threshold = reference[0]["temperature_c"][cell_index] + .5
        def arrival(frames):
            return next((frame["t_s"] for frame in frames if frame["temperature_c"][cell_index] >= threshold), None)
        ref_arrival = arrival(reference)
        for step in candidates:
            frames = docs[step]["frames"]
            error = max(abs(a - b) for ref, frame in zip(reference, frames)
                        for a, b in zip(ref["temperature_c"], frame["temperature_c"]))
            observed_arrival = arrival(frames)
            arrival_error = (abs(observed_arrival - ref_arrival)
                             if ref_arrival is not None and observed_arrival is not None else None)
            passed = bool(error < .05 and arrival_error is not None and arrival_error < sample_s)
            budget = docs[step]["final_budget"]
            results.append({"model": model, "dt_s": step, "max_error_c": error,
                            "arrival_error_s": arrival_error, "arrival_reference_s": ref_arrival,
                            "arrival_cell_index": cell_index, "wall_s": timing[step],
                            "wall_ms_per_step": timing[step] * 1000. / budget["steps"],
                            "passed": passed})
    approved = [step for step in candidates if all(row["passed"] for row in results if row["dt_s"] == step)]
    if not approved:
        raise ArithmeticError("live timestep sweep has no approved timestep")
    return {"name": "live_step_sizes", "results": results, "max_dt_s": max(approved),
            "temperature_tolerance_c": .05, "arrival_tolerance_s": sample_s,
            "duration_s": duration_s, "sample_s": sample_s, "passed": True}


BENCHMARKS = (
    benchmark_restart_equivalence,
    benchmark_closed_thermal,
    benchmark_two_stream_mixing,
    benchmark_conservative_tracer,
    benchmark_temporal_convergence,
    benchmark_spatial_convergence,
    benchmark_spatial_convergence_dispersive,
    benchmark_diffusive_decay,
    benchmark_mms_traveling_wave,
)


def run_all_benchmarks() -> dict[str, Any]:
    """Run applicable benchmarks; record momentum exclusions."""
    results = [fn() for fn in BENCHMARKS]
    return {
        "schema": SCHEMA,
        "status": "numerical_verification_not_field_validation",
        "code_sha256": sha256_file(Path(__file__)),
        "results": results,
        "not_applicable": NOT_APPLICABLE,
        "passed": all(r["passed"] for r in results),
    }
