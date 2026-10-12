"""M01 hydro_thermal: Firehole 6-reach mixing + tributaries + plume viz.

Paper equations (Yellowstone_Research_and_Future_Directions.md Pt.1 §5):
    d(ViTi)/dt = ΣQjiTj + Qhot,iThot,i − Qout,iTi + Vi(Tair−Ti)/τi
    Qout = ΣQin + Qhot            (constant-volume reaches)
    Tmixed = (Q1T1 + Q2T2)/(Q1+Q2)
Centerline cooling profile (viz only):
    T(x) = Ta + (T0−Ta)·exp(−he·b·x / ρcpQ)

Mirrors scripts/ecosystem.gd::_derive_flows/_advance_heat exactly, then adds:
(a) optional cold tributary laterals (default 0 → baseline preserved),
(b) 1-D profile helper, (c) 2-D illustrative plume field for map overlay.

All params illustrative. Density*heat-capacity cancel in mixing form; they
must return for real power/evaporation/phase-change work (see spec).
"""
from __future__ import annotations

import copy
import math

RHO_CP = 4.186e6  # J/(m3·K), water; used ONLY in profile helper, not mixing step


def derive_flows(reaches: list, boundary_m3s: float) -> list:
    """Attach q_in/flow/thermal/source_heat like ecosystem.gd::_derive_flows."""
    out = copy.deepcopy(reaches)
    q = float(boundary_m3s)
    for r in out:
        r["q_in_m3s"] = q
        sq = sum(max(0.0, float(s.get("flow_m3s", 0.0)))
                 for s in r.get("lateral_sources", []))
        sqt = sum(max(0.0, float(s.get("flow_m3s", 0.0))) *
                  float(s.get("temperature_c", 0.0))
                  for s in r.get("lateral_sources", []))
        q += sq
        r["flow_m3s"] = q
        r["thermal_m3s"] = sq
        r["source_heat_m3_c_per_s"] = sqt
        r["source_c"] = (sqt / sq) if sq > 0 else 0.0
    return out


def stable_dt(reaches: list, cap: float = 1.0) -> float:
    dt = float(cap)
    for r in reaches:
        rate = float(r["flow_m3s"]) / float(r["volume_m3"])
        rate += 1.0 / max(1.0, float(r.get("cooling_seconds", 18000.0)))
        dt = min(dt, 0.45 / max(rate, 1e-6))
    return dt


def mixing_check(q1: float, t1: float, q2: float, t2: float) -> float:
    if q1 + q2 <= 0:
        raise ValueError("mixing_check: total flow must be > 0")
    return (q1 * t1 + q2 * t2) / (q1 + q2)


def step_heat(reaches: list, boundary_m3s: float, boundary_c: float,
              air_c: float, dt: float) -> tuple[list, dict]:
    """Advance heat one dt with substeps; returns (reaches, ledger).

    Ledger mirrors ecosystem.gd heat_ledger (units m3·°C, rho*cp omitted).
    """
    state = derive_flows(reaches, boundary_m3s)
    remaining = float(dt)
    last_dt = min(dt, stable_dt(state))
    heat_err, water_err = 0.0, 0.0
    ledger: dict = {}
    while remaining > 1e-7:
        h = min(remaining, stable_dt(state))
        last_dt = h
        old = [float(r["temperature_c"]) for r in state]
        before = sum(c * float(r["volume_m3"]) for c, r in zip(old, state))
        src_heat = atm_heat = src_flow = 0.0
        for i, r in enumerate(state):
            vol = float(r["volume_m3"])
            up_c = float(boundary_c) if i == 0 else old[i - 1]
            incoming = float(r["q_in_m3s"]) * up_c + float(r["source_heat_m3_c_per_s"])
            outgoing = float(r["flow_m3s"]) * old[i]
            atm = (air_c - old[i]) * vol / max(1.0, float(r.get("cooling_seconds", 18000.0)))
            r["temperature_c"] = old[i] + (incoming - outgoing + atm) * h / vol
            src_heat += float(r["source_heat_m3_c_per_s"])
            src_flow += float(r["thermal_m3s"])
            atm_heat += atm
            water_err = max(water_err, abs(float(r["q_in_m3s"]) + float(r["thermal_m3s"])
                                          - float(r["flow_m3s"])) * h)
            t = float(r["temperature_c"])
            r["fish_activity"] = min(1.0, max(0.0, (26.0 - t) / 8.0))
        after = sum(float(r["temperature_c"]) * float(r["volume_m3"]) for r in state)
        b_heat = float(boundary_m3s) * float(boundary_c)
        exit_heat = float(state[-1]["flow_m3s"]) * old[-1]
        expected = (b_heat + src_heat - exit_heat + atm_heat) * h
        heat_err = max(heat_err, abs((after - before) - expected))
        water_err = max(water_err, abs(float(boundary_m3s) + src_flow
                                      - float(state[-1]["flow_m3s"])) * h)
        ledger = {"units": "m3 * degC (constant rho*cp omitted)",
                  "before": before, "after": after,
                  "boundary_input": b_heat * h, "lateral_input": src_heat * h,
                  "outlet_export": exit_heat * h, "atmosphere_exchange": atm_heat * h,
                  "residual": abs((after - before) - expected),
                  "dt_seconds": h}
        remaining -= h
    ledger["heat_budget_error"] = heat_err
    ledger["water_budget_error_m3"] = water_err
    return state, ledger


def steady_state(reaches: list, boundary_m3s: float, boundary_c: float,
                 air_c: float) -> list:
    """Exact fixed point of the mixing step (audit regression target):
        T*i = (Qin·Tup + ΣQℓTℓ + (V/τ)·Tair) / (Qout + V/τ)
    solved upstream-first (feedforward chain → single pass is exact)."""
    state = derive_flows(reaches, boundary_m3s)
    temps = {}
    for r in state:
        tau = max(1.0, float(r.get("cooling_seconds", 18000.0)))
        vol = float(r["volume_m3"])
        up = float(boundary_c) if not r.get("upstream_id") else temps[r["upstream_id"]]
        num = (float(r["q_in_m3s"]) * up + float(r["source_heat_m3_c_per_s"])
               + (vol / tau) * float(air_c))
        temps[r["id"]] = num / (float(r["flow_m3s"]) + vol / tau)
    return [temps[r["id"]] for r in state]


def run_simulation(reaches: list, boundary_m3s: float, boundary_c: float,
                   air_c: float | callable, seconds: float,
                   dt: float = 1.0) -> tuple[list, dict]:
    """Run fixed-dt transport (physical seconds). air_c may be const or fn(t). Ledger carries full budget history (cumulative in/out/exchange/storage)."""
    if float(boundary_m3s) <= 0:
        raise ValueError(f"boundary_m3s must be > 0, got {boundary_m3s}")
    if float(seconds) < 0 or float(dt) <= 0:
        raise ValueError(f"seconds must be ≥ 0 and dt > 0 "
                         f"(got {seconds}, {dt})")
    state = copy.deepcopy(reaches)
    hist = {"boundary_in": 0.0, "lateral_in": 0.0, "outlet_out": 0.0,
            "atmosphere": 0.0, "storage_0": None, "storage_1": None,
            "heat_budget_error": 0.0, "water_budget_error_m3": 0.0, "steps": 0}
    hist["storage_0"] = sum(float(r["temperature_c"]) * float(r["volume_m3"])
                            for r in state)
    t = 0.0
    while t < seconds - 1e-9:
        h = min(dt, seconds - t)
        a = air_c(t) if callable(air_c) else float(air_c)
        state, led = step_heat(state, boundary_m3s, boundary_c, a, h)
        hist["boundary_in"] += led["boundary_input"]
        hist["lateral_in"] += led["lateral_input"]
        hist["outlet_out"] += led["outlet_export"]
        hist["atmosphere"] += led["atmosphere_exchange"]
        hist["heat_budget_error"] = max(hist["heat_budget_error"],
                                       led["heat_budget_error"])
        hist["water_budget_error_m3"] = max(hist["water_budget_error_m3"],
                                           led["water_budget_error_m3"])
        hist["steps"] += 1
        t += h
    hist["storage_1"] = sum(float(r["temperature_c"]) * float(r["volume_m3"])
                            for r in state)
    hist["closure_residual"] = abs(
        (hist["storage_1"] - hist["storage_0"])
        - (hist["boundary_in"] + hist["lateral_in"] - hist["outlet_out"]
           + hist["atmosphere"]))
    return state, hist


def steady_profile(t0: float, ta: float, x_m: list,
                   he_w_m2k: float = 25.0, width_m: float = 22.0,
                   q_m3s: float = 8.0) -> list:
    """Illustrative exponential cooling along centerline (viz only)."""
    out = []
    for x in x_m:
        out.append(ta + (t0 - ta) * math.exp(-he_w_m2k * width_m * x / (RHO_CP * q_m3s)))
    return out


def plume_field(nx: int = 128, nz: int = 128, extent_m: float = 600.0,
                hot_c: float = 19.1, river_c: float = 17.8,
                sigma_m: float = 90.0) -> list:
    """Steady 2-D advection-diffusion plume at the Excelsior mouth.

    Implicit upwind/centered solve (replay.plume2d) with the mapped
    chain velocity and Fischer diffusivity. Returns nx*nz row-major
    floats in °C. Status illustrative.
    """
    from .replay.plume2d import solve_steady
    sol = solve_steady(nx=nx, nz=nz, extent_m=extent_m,
                       ambient_c=river_c, source_c=hot_c,
                       source_xz=(0.0, -60.0), source_r_m=sigma_m)
    return sol["field"]


def render_plume_png(field: list, nx: int, nz: int, path: str,
                     vmin: float = 17.0, vmax: float = 20.0) -> str:
    """Blue→red ramp PNG, same extent convention as habitat_mask.png."""
    from PIL import Image
    img = Image.new("RGB", (nx, nz))
    px = img.load()
    for iz in range(nz):
        for ix in range(nx):
            t = field[iz * nx + ix]
            f = min(1.0, max(0.0, (t - vmin) / (vmax - vmin)))
            px[ix, iz] = (int(120 + 135 * f), int(150 - 60 * f), int(200 - 150 * f))
    img.save(path)
    return path


DEFAULT_TRIBUTARIES = {
    # Illustrative cold dilutions; 0.0 flow = omitted (baseline preserved).
    "fairy_creek": {"flow_m3s": 0.0, "temperature_c": 12.0},
    "white_creek": {"flow_m3s": 0.0, "temperature_c": 12.0},
    "rabbit_creek": {"flow_m3s": 0.0, "temperature_c": 11.0},
    "mallard_creek": {"flow_m3s": 0.0, "temperature_c": 11.0},
}
