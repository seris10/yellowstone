"""Analytical six-reach heat benchmark.
Equations and derivation in Yellowstone_Research_and_Future_Directions.md Pt.1 section 5."""
from __future__ import annotations

from yellowstone_python.thermal_features.plume import plume_field, render_plume_png, DEFAULT_TRIBUTARIES

from yellowstone_python.common.checks import finite as _finite, positive as _positive, positive_int as _positive_int

import copy
import math
from pathlib import Path

RHO_CP = 4.186e6  # J/(m3.K), water. Profile helper only; the mixing step cancels it.
DEFAULT_COOLING_S = 18000.0








def _validate_reaches(reaches: list) -> list:
    """Serial-chain reach records with positive volumes and nonnegative laterals."""
    if not reaches:
        raise ValueError("at least one reach is required")
    for i, r in enumerate(reaches):
        if not isinstance(r, dict):
            raise ValueError(f"reach #{i} must be a record")
        rid = r.get("id", i)
        for key in ("volume_m3", "temperature_c"):
            if key not in r:
                raise ValueError(f"reach {rid}: missing {key}")
        vol = _finite(f"reach {rid} volume_m3", r["volume_m3"])
        if vol <= 0.0:
            raise ValueError(f"reach {rid}: volume_m3 must be > 0")
        _finite(f"reach {rid} temperature_c", r["temperature_c"])
        tau = _finite(f"reach {rid} cooling_seconds",
                      r.get("cooling_seconds", DEFAULT_COOLING_S))
        if tau <= 0.0:
            raise ValueError(f"reach {rid}: cooling_seconds must be > 0")
        for s in r.get("lateral_sources", []):
            q = _finite(f"reach {rid} lateral flow_m3s", s.get("flow_m3s", 0.0))
            if q < 0.0:
                raise ValueError(f"reach {rid}: lateral flow_m3s must be >= 0")
            _finite(f"reach {rid} lateral temperature_c", s.get("temperature_c", 0.0))
    return reaches


def derive_flows(reaches: list, boundary_m3s: float) -> list:
    """Attach q_in/flow/thermal/source_heat like ecosystem.gd::_derive_flows."""
    q0 = _finite("boundary_m3s", boundary_m3s)
    if q0 <= 0.0:
        raise ValueError(f"boundary_m3s must be > 0, got {boundary_m3s}")
    out = copy.deepcopy(_validate_reaches(reaches))
    q = q0
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
    dt = _positive("cap", cap)
    for i, r in enumerate(_validate_reaches(reaches)):
        vol = float(r["volume_m3"])
        rate = float(r["flow_m3s"]) / vol
        rate += 1.0 / max(1.0, float(r.get("cooling_seconds", DEFAULT_COOLING_S)))
        dt = min(dt, 0.45 / max(rate, 1e-6))
    return dt


def mixing_check(q1: float, t1: float, q2: float, t2: float) -> float:
    q1, t1 = _finite("q1", q1), _finite("t1", t1)
    q2, t2 = _finite("q2", q2), _finite("t2", t2)
    if q1 < 0.0 or q2 < 0.0:
        raise ValueError("mixing flows must be >= 0")
    if q1 + q2 <= 0.0:
        raise ValueError("mixing_check: total flow must be > 0")
    return (q1 * t1 + q2 * t2) / (q1 + q2)


def step_heat(reaches: list, boundary_m3s: float, boundary_c: float,
              air_c: float, dt: float) -> tuple[list, dict]:
    """Advance heat one dt with substeps; returns (reaches, ledger).

Ledger mirrors ecosystem.gd heat_ledger (units m3* deg C, rho*cp omitted).
"""
    state = derive_flows(reaches, boundary_m3s)
    remaining = float(dt)
    heat_err, water_err = 0.0, 0.0
    initial_storage = sum(float(r["temperature_c"]) * float(r["volume_m3"])
                         for r in state)
    b_heat = float(boundary_m3s) * float(boundary_c)
    ledger: dict = {
        "units": "m3 * degC (constant rho*cp omitted)",
        "before": initial_storage, "after": None,
        "boundary_input": 0.0, "lateral_input": 0.0,
        "outlet_export": 0.0, "atmosphere_exchange": 0.0,
        "residual": 0.0, "dt_seconds": 0.0, "substeps": 0}
    while remaining > 1e-7:
        h = min(remaining, stable_dt(state))
        old = [float(r["temperature_c"]) for r in state]
        before = sum(float(c) * float(r["volume_m3"]) for c, r in zip(old, state))
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
        ledger["boundary_input"] += b_heat * h
        ledger["lateral_input"] += src_heat * h
        ledger["outlet_export"] += exit_heat * h
        ledger["atmosphere_exchange"] += atm_heat * h
        ledger["residual"] += abs((after - before) - expected)
        ledger["dt_seconds"] += h
        ledger["substeps"] += 1
        remaining -= h
    ledger["after"] = sum(float(r["temperature_c"]) * float(r["volume_m3"])
                          for r in state)
    ledger["heat_budget_error_j"] = heat_err
    ledger["water_budget_error_m3"] = water_err
    return state, ledger


def steady_state(reaches: list, boundary_m3s: float, boundary_c: float,
                 air_c: float) -> list:
    """Exact fixed point of the mixing step: T*i = (Qin*Tup + sum QlTl + (V/tau)*Tair) / (Qout + V/tau)."""
    state = derive_flows(reaches, boundary_m3s)
    temps = {}
    for i, r in enumerate(state):
        tau = max(1.0, float(r.get("cooling_seconds", DEFAULT_COOLING_S)))
        vol = float(r["volume_m3"])
        expected_up = None if i == 0 else state[i - 1]["id"]
        declared_up = r.get("upstream_id") or None
        if declared_up is not None and declared_up != expected_up:
            raise ValueError(
                f"reach {r['id']}: branching/gap unsupported "
                f"(upstream {declared_up!r} != previous {expected_up!r})")
        up = float(boundary_c) if i == 0 else temps[state[i - 1]["id"]]
        num = (float(r["q_in_m3s"]) * up + float(r["source_heat_m3_c_per_s"])
               + (vol / tau) * float(air_c))
        temps[r["id"]] = num / (float(r["flow_m3s"]) + vol / tau)
    return [temps[r["id"]] for r in state]


def run_simulation(reaches: list, boundary_m3s: float, boundary_c: float,
                   air_c: float | callable, seconds: float,
                   dt: float = 1.0) -> tuple[list, dict]:
    """Run fixed-dt transport (physical seconds). air_c may be const or fn(t)."""
    boundary_m3s = _finite("boundary_m3s", boundary_m3s)
    if float(boundary_m3s) <= 0:
        raise ValueError(f"boundary_m3s must be > 0, got {boundary_m3s}")
    seconds = _finite("seconds", seconds)
    dt = _finite("dt", dt)
    if float(seconds) < 0.0 or float(dt) <= 0.0:
        raise ValueError(f"seconds must be >= 0 and dt > 0 "
                         f"(got {seconds}, {dt})")
    state = copy.deepcopy(reaches)
    hist = {"boundary_in": 0.0, "lateral_in": 0.0, "outlet_out": 0.0,
            "atmosphere": 0.0, "storage_0": None, "storage_1": None,
            "heat_budget_error_j": 0.0, "water_budget_error_m3": 0.0,
            "steps": 0}
    hist["storage_0"] = sum(float(r["temperature_c"]) * float(r["volume_m3"])
                            for r in state)
    t = 0.0
    while t < seconds - 1e-9:
        h = min(dt, seconds - t)
        a = air_c(t) if callable(air_c) else _finite("air_c", air_c)
        state, led = step_heat(state, boundary_m3s, boundary_c, a, h)
        hist["boundary_in"] += led["boundary_input"]
        hist["lateral_in"] += led["lateral_input"]
        hist["outlet_out"] += led["outlet_export"]
        hist["atmosphere"] += led["atmosphere_exchange"]
        hist["heat_budget_error_j"] = max(hist["heat_budget_error_j"],
                                          led["heat_budget_error_j"])
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
    t0 = _finite("t0", t0)
    ta = _finite("ta", ta)
    he = _finite("he_w_m2k", he_w_m2k)
    width = _finite("width_m", width_m)
    q = _finite("q_m3s", q_m3s)
    if q <= 0.0:
        raise ValueError(f"q_m3s must be > 0, got {q_m3s}")
    if he < 0.0 or width < 0.0:
        raise ValueError("he_w_m2k and width_m must be >= 0")
    xs = [_finite(f"x_m[{i}]", x) for i, x in enumerate(x_m)]
    rate = he * width / (RHO_CP * q)
    return [ta + (t0 - ta) * math.exp(-rate * x) for x in xs]






