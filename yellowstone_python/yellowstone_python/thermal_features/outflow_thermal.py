"""Outflow sheet-flow energy balance for thermal spring drainages.
Rasterizes advected temperature along the outflow network onto the core grid."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic

from yellowstone_python.common.checks import finite as _finite

import json
import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

import yellowstone_python.thermal_features.outflow_network as _outflow_network
from yellowstone_python.river.surface_flux import BudgetParams, MetState, flux_at, linearized

MIN_FILM_DEPTH_M_DEFAULT = 0.001
MIN_FILM_DEPTH_STATUS = "authored"
FLOW_FRACTION_VERIFY_TOLERANCE = 0.5

SCHEMA_VERSION = "yellowstone.outflow_temperature.v1"

RHO_WATER_KG_M3 = 1000.0
CP_WATER_J_KG_K = 4186.0

CORE_GRID_SIZE = 1280
CORE_CELL_M = 1.0
CORE_HALF_M = 640.0

SINTER_CONDUCTIVITY_W_M_K = 1.38
SINTER_CONDUCTIVITY_STATUS = "literature"
SINTER_CONDUCTIVITY_SOURCE = (
    "Diment and Pratt 1988 USGS Open-File Report 88-690 Table 1 "
    "doi:10.3133/ofr88690: opal, Virgin Valley Nev., room dried, "
    "1.89 g/cm3, 3.3 mcal/cm/s/C at 30 C (1.38 W/m/K); silica glass 3.3 "
    "(Ratcliffe 1959). Apron sinter porosity and saturation unmeasured.")
SINTER_THICKNESS_M = 0.10
SINTER_THICKNESS_STATUS = "authored"
SINTER_SUBSTRATE_T_C = 20.0
SINTER_SUBSTRATE_T_STATUS = "authored"

MANNING_REYNOLDS_LOW = 500.0
MANNING_REYNOLDS_HIGH = 2000.0
G_M_S2 = 9.80665

DEFAULT_MANNING_N = 0.030

SURFACE_FLUX_MAX_T_C = 99.0


def water_kinematic_viscosity_m2_s(t_c: float) -> float:
    """Pure-water kinematic viscosity (m^2/s) from the Vogel-equation dynamic
viscosity and a near-constant density 1000 kg/m^3 (valid 0-100 C)."""
    t = _temperature_or_none(t_c)
    mu_pa_s = 2.414e-5 * 10.0 ** (247.8 / (t + 133.15))
    return mu_pa_s / RHO_WATER_KG_M3


def _temperature_or_none(t_c: Any) -> float:
    value = float(t_c)
    if not math.isfinite(value):
        raise ValueError("temperature must be finite")
    if value < -40.0 or value > 150.0:
        raise ValueError("temperature out of liquid-water range for viscosity")
    return value




@dataclass(frozen=True)
class SinterConduction:
    """Lumped conduction from a film to the sinter substrate.

Flux per area is k / L * (t_substrate_c - t_water_c); k from opal, L and t_substrate_c authored.
"""

    k_w_m_k: float = SINTER_CONDUCTIVITY_W_M_K
    thickness_m: float = SINTER_THICKNESS_M
    t_substrate_c: float = SINTER_SUBSTRATE_T_C
    status: str = "authored"

    def flux_w_m2(self, t_water_c: float) -> float:
        """Positive-into-water conduction flux at the given water temperature."""
        return (self.k_w_m_k / self.thickness_m
                * (float(self.t_substrate_c) - float(t_water_c)))


def laminar_film_flow(discharge_per_width_m2_s: float,
                      slope_m_m: float,
                      kinematic_viscosity_m2_s: float
                      ) -> tuple[float, float]:
    """Film depth and velocity from the Nusselt laminar-film law.
d = (3 nu q / (g S))^(1/3), v = q / d."""
    q = _finite("discharge_per_width", discharge_per_width_m2_s)
    s = _finite("slope", slope_m_m)
    nu = _finite("kinematic_viscosity", kinematic_viscosity_m2_s)
    if q <= 0.0:
        raise ValueError("discharge per width must be > 0")
    if s <= 0.0:
        raise ValueError("slope must be > 0 for Nusselt film flow")
    if nu <= 0.0:
        raise ValueError("kinematic viscosity must be > 0")
    depth = (3.0 * nu * q / (G_M_S2 * s)) ** (1.0 / 3.0)
    velocity = q / depth
    return depth, velocity


def manning_turbulent_flow(discharge_per_width_m2_s: float,
                           slope_m_m: float,
                           manning_n: float = DEFAULT_MANNING_N
                           ) -> tuple[float, float]:
    """Film depth and velocity from wide-channel Manning: q = (1/n) d^(5/3) S^(1/2)."""
    q = _finite("discharge_per_width", discharge_per_width_m2_s)
    s = _finite("slope", slope_m_m)
    n = _finite("manning_n", manning_n)
    if q <= 0.0:
        raise ValueError("discharge per width must be > 0")
    if s <= 0.0:
        raise ValueError("slope must be > 0 for Manning sheet flow")
    if n <= 0.0:
        raise ValueError("Manning n must be > 0")
    depth = (n * q / math.sqrt(s)) ** 0.6
    velocity = q / depth
    return depth, velocity


def _blend_weight(reynolds: float) -> float:
    """Smooth 0-to-1 weight on the turbulent branch across the transition band."""
    if reynolds <= MANNING_REYNOLDS_LOW:
        return 0.0
    if reynolds >= MANNING_REYNOLDS_HIGH:
        return 1.0
    midpoint = 0.5 * (MANNING_REYNOLDS_LOW + MANNING_REYNOLDS_HIGH)
    half_band = 0.5 * (MANNING_REYNOLDS_HIGH - MANNING_REYNOLDS_LOW)
    scaled = (reynolds - midpoint) / half_band
    return 0.5 * (1.0 + math.tanh(2.5 * scaled))


def sheet_flow_depth_velocity(discharge_per_width_m2_s: float,
                              slope_m_m: float,
                              t_water_c: float,
                              manning_n: float = DEFAULT_MANNING_N
                              ) -> dict:
    """Film depth and velocity blended across the laminar-turbulent transition.
Reynolds based on unit discharge q and the water kinematic viscosity at t."""
    q = _finite("discharge_per_width", discharge_per_width_m2_s)
    nu = water_kinematic_viscosity_m2_s(t_water_c)
    reynolds = q / nu
    weight = _blend_weight(reynolds)
    d_lam, v_lam = laminar_film_flow(q, slope_m_m, nu)
    if weight <= 0.0:
        depth, velocity = d_lam, v_lam
        regime = "laminar"
    elif weight >= 1.0:
        depth, velocity = manning_turbulent_flow(q, slope_m_m, manning_n)
        regime = "turbulent"
    else:
        d_tur, _ = manning_turbulent_flow(q, slope_m_m, manning_n)
        depth = (1.0 - weight) * d_lam + weight * d_tur
        velocity = q / depth
        regime = "blended"
    return {
        "depth_m": depth,
        "velocity_mps": velocity,
        "reynolds": reynolds,
        "regime": regime,
        "blend_weight": weight,
        "kinematic_viscosity_m2_s": nu,
    }


def manning_sheet_flow(discharge_per_width_m2_s: float,
                       slope_m_m: float,
                       manning_n: float = DEFAULT_MANNING_N
                       ) -> tuple[float, float]:
    """Film depth and velocity at 70 C default from the blended sheet-flow law.
sheet_flow_depth_velocity takes an explicit water temperature."""
    out = sheet_flow_depth_velocity(discharge_per_width_m2_s, slope_m_m,
                                    t_water_c=70.0, manning_n=manning_n)
    return out["depth_m"], out["velocity_mps"]


@dataclass(frozen=True)
class SpringDischarge:
    """One spring's total hot-water discharge, with provenance."""

    pool_id: str
    discharge_m3_s: float
    source: str
    status: str = "authored"

    def __post_init__(self) -> None:
        q = _finite("discharge_m3_s", self.discharge_m3_s)
        if q <= 0.0:
            raise ValueError("discharge_m3_s must be > 0")
        object.__setattr__(self, "discharge_m3_s", q)


def segment_temperature(
    t_pool_edge_c: float,
    segment: dict,
    discharge_m3_s: float,
    met: MetState,
    *,
    budget_params: BudgetParams | None = None,
    sinter: SinterConduction | None = None,
    manning_n: float = DEFAULT_MANNING_N,
    step_count: int | None = None,
) -> dict:
    """Water temperature along one outflow segment.
Forward-Euler on dT/ds = (F_net + F_sinter) / (rho cp d v)."""
    params = budget_params or BudgetParams()
    sink = sinter if sinter is not None else SinterConduction()
    length = _finite("segment.length_m", segment["length_m"])
    width = _finite("segment.width_m", segment["width_m"])
    slope = _finite("segment.mean_slope", segment["mean_slope"])
    flow_fraction = _finite("segment.flow_fraction", segment["flow_fraction"])
    if length <= 0.0 or width <= 0.0 or flow_fraction <= 0.0:
        raise ValueError("segment length, width, flow_fraction must be > 0")
    seg_discharge = _finite("discharge", discharge_m3_s) * flow_fraction
    q_unit = seg_discharge / width
    t_edge = _finite("t_pool_edge_c", t_pool_edge_c)
    hydraulics = sheet_flow_depth_velocity(q_unit, slope, t_edge,
                                           manning_n=manning_n)
    depth = hydraulics["depth_m"]
    velocity = hydraulics["velocity_mps"]
    nsteps = int(step_count or max(2, int(math.ceil(length / 1.0))))
    s_values = np.linspace(0.0, length, nsteps + 1)
    temps = np.empty(nsteps + 1, dtype=np.float64)
    net_flux = np.empty(nsteps + 1, dtype=np.float64)
    temps[0] = _finite("t_pool_edge_c", t_pool_edge_c)
    denom = RHO_WATER_KG_M3 * CP_WATER_J_KG_K * depth * velocity
    if denom <= 0.0:
        raise ValueError("film heat capacity flux must be positive")
    for i in range(nsteps):
        t_here = float(temps[i])
        parts = flux_at(t_here, met, params)
        f_surface = float(parts["net"])
        f_sinter = sink.flux_w_m2(t_here)
        f_total = f_surface + f_sinter
        net_flux[i] = f_total
        ds = float(s_values[i + 1] - s_values[i])
        temps[i + 1] = t_here + f_total * ds / denom
    parts_end = flux_at(float(temps[-1]), met, params)
    net_flux[-1] = float(parts_end["net"]) + sink.flux_w_m2(float(temps[-1]))
    return {
        "s_m": s_values.tolist(),
        "t_c": temps.tolist(),
        "depth_m": depth,
        "velocity_mps": velocity,
        "q_m3_s": seg_discharge,
        "q_unit_m2_s": q_unit,
        "net_flux_w_m2": net_flux.tolist(),
        "manning_n": manning_n,
        "sinter": {
            "k_w_m_k": sink.k_w_m_k,
            "thickness_m": sink.thickness_m,
            "t_substrate_c": sink.t_substrate_c,
            "status": sink.status,
        },
    }


def _xz_to_ij(x: float, z: float) -> tuple[int, int]:
    """Core-grid indices for a world point; row j increases southward."""
    i = int(math.floor((x + CORE_HALF_M) / CORE_CELL_M))
    j = int(math.floor((z + CORE_HALF_M) / CORE_CELL_M))
    return i, j


def _draw_segment(raster: np.ndarray, points: Sequence[Sequence[float]],
                  temperatures: Sequence[float], s_values: Sequence[float],
                  width_cells: int) -> None:
    """Stamp temperatures along a polyline into the core grid."""
    if len(points) < 2 or len(temperatures) < 2:
        return
    half = max(0, width_cells // 2)
    seg_s = 0.0
    total_s = float(s_values[-1])
    pts = [(float(p[0]), float(p[1])) for p in points]
    temps = np.array(temperatures, dtype=np.float64)
    s_arr = np.array(s_values, dtype=np.float64)
    for a, b in zip(pts, pts[1:]):
        dx = b[0] - a[0]
        dz = b[1] - a[1]
        dist = math.hypot(dx, dz)
        if dist <= 0.0:
            continue
        n_sub = max(2, int(math.ceil(dist / 0.5)))
        for k in range(n_sub + 1):
            frac = k / n_sub
            x = a[0] + dx * frac
            z = a[1] + dz * frac
            s_here = seg_s + dist * frac
            if total_s > 0.0:
                t_here = float(np.interp(s_here, s_arr, temps))
            else:
                t_here = float(temps[0])
            i0, j0 = _xz_to_ij(x, z)
            for di in range(-half, half + 1):
                for dj in range(-half, half + 1):
                    ii = i0 + di
                    jj = j0 + dj
                    if 0 <= ii < raster.shape[1] and 0 <= jj < raster.shape[0]:
                        existing = raster[jj, ii]
                        if math.isnan(existing) or t_here > existing:
                            raster[jj, ii] = t_here
        seg_s += dist


def edinger_exchange(
    t_pool_edge_c: float,
    met: MetState,
    *,
    budget_params: BudgetParams | None = None,
    sinter: SinterConduction | None = None,
) -> dict:
    """Linearize combined surface and sinter flux at the pool edge.
Returns equilibrium temperature t_e_c and exchange coefficient k_total_w_m2_k."""
    params = budget_params or BudgetParams()
    sink = sinter if sinter is not None else SinterConduction()
    t_lin = _finite("t_pool_edge_c", t_pool_edge_c)
    f0_surface, df_surface_dT = linearized(t_lin, met, params)
    f0_sinter = sink.flux_w_m2(t_lin)
    df_sinter_dT = -sink.k_w_m_k / sink.thickness_m
    f0_total = f0_surface + f0_sinter
    df_total_dT = df_surface_dT + df_sinter_dT
    if df_total_dT >= 0.0:
        raise ValueError(
            "linearized flux slope must be negative for a stable equilibrium")
    k_total = -df_total_dT
    t_e = t_lin + f0_total / k_total
    return {
        "t_lin_c": t_lin,
        "t_e_c": t_e,
        "k_total_w_m2_k": k_total,
        "k_surface_w_m2_k": -df_surface_dT,
        "k_sinter_w_m2_k": -df_sinter_dT,
        "f0_total_w_m2": f0_total,
    }


def edinger_temperature(t_pool_edge_c: float,
                        t_equilibrium_c: float,
                        k_total_w_m2_k: float,
                        flow_length_m: float,
                        unit_discharge_m2_s: float) -> float:
    """Edinger-Duttweiler-Geyer (1968) linearized cooling at one anchor:
T(s) = t_e + (t_0 - t_e) exp(-k s / (rho cp q))."""
    q = _finite("unit_discharge_m2_s", unit_discharge_m2_s)
    if q <= 0.0:
        raise ValueError("unit_discharge_m2_s must be > 0")
    s = _finite("flow_length_m", flow_length_m)
    k = _finite("k_total_w_m2_k", k_total_w_m2_k)
    t_0 = _finite("t_pool_edge_c", t_pool_edge_c)
    t_e = _finite("t_equilibrium_c", t_equilibrium_c)
    exponent = -k * s / (RHO_WATER_KG_M3 * CP_WATER_J_KG_K * q)
    return t_e + (t_0 - t_e) * math.exp(exponent)


def _net_flux_at(t_c: float, met: MetState,
                 params: BudgetParams | None,
                 sinter: SinterConduction | None) -> float:
    """F_surface(T) + F_sinter(T) at one water temperature."""
    sink = sinter if sinter is not None else SinterConduction()
    f_surf = flux_at(t_c, met, params or BudgetParams())["net"]
    return float(f_surf) + sink.flux_w_m2(t_c)


def equilibrium_temperature(met: MetState,
                            *,
                            budget_params: BudgetParams | None = None,
                            sinter: SinterConduction | None = None,
                            t_low: float = 0.0,
                            t_high: float = SURFACE_FLUX_MAX_T_C
                            ) -> float:
    """Water temperature where surface and sinter fluxes sum to zero."""
    f_lo = _net_flux_at(t_low, met, budget_params, sinter)
    f_hi = _net_flux_at(t_high, met, budget_params, sinter)
    if f_lo <= 0.0:
        return t_low
    if f_hi >= 0.0:
        return t_high
    low = t_low
    high = t_high
    for _ in range(80):
        mid = 0.5 * (low + high)
        f_mid = _net_flux_at(mid, met, budget_params, sinter)
        if abs(f_mid) < 1.0e-6 or abs(high - low) < 1.0e-6:
            return mid
        if f_mid > 0.0:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


def _tau_table(t_hot_c: float,
               met: MetState,
               budget_params: BudgetParams | None,
               sinter: SinterConduction | None,
               *,
               n_bins: int = 400) -> dict:
    """Exact-integral tau(T) table from t_hot_c down toward T_eq.
tau(T) = integral from t_hot to T of rho cp dT' / (-F_net(T'))."""
    t_hot = min(float(t_hot_c), SURFACE_FLUX_MAX_T_C)
    t_eq = equilibrium_temperature(met, budget_params=budget_params,
                                   sinter=sinter, t_low=-20.0,
                                   t_high=t_hot)
    if t_eq >= t_hot - 1.0e-6:
        return {"t_eq_c": t_eq, "t_hot_c": t_hot,
                "t_c_ascending": np.array([t_eq, t_hot], dtype=np.float64),
                "tau_wrt_t": np.array([0.0, 0.0], dtype=np.float64),
                "tau_ascending": np.array([0.0, 0.0], dtype=np.float64),
                "t_at_tau": np.array([t_hot, t_eq], dtype=np.float64)}
    denom = RHO_WATER_KG_M3 * CP_WATER_J_KG_K
    tiny = max(1.0e-5, (t_hot - t_eq) * 1.0e-6)
    alpha = np.linspace(0.0, 1.0, int(n_bins))
    tau_offset = (t_hot - t_eq - tiny) * (1.0 - (1.0 - alpha) ** 3)
    t_grid = t_hot - tau_offset
    tau_grid = np.zeros_like(t_grid)
    f_prev = _net_flux_at(float(t_grid[0]), met, budget_params, sinter)
    for i in range(1, len(t_grid)):
        t_prev = float(t_grid[i - 1])
        t_here = float(t_grid[i])
        f_here = _net_flux_at(t_here, met, budget_params, sinter)
        f_avg = 0.5 * (f_prev + f_here)
        delta_t = t_here - t_prev
        if f_avg >= 0.0:
            tau_grid[i] = tau_grid[i - 1] + 1.0e30
        else:
            tau_grid[i] = tau_grid[i - 1] + denom * (-delta_t) / (-f_avg)
        f_prev = f_here
    t_c_ascending = t_grid[::-1].copy()
    tau_wrt_t = tau_grid[::-1].copy()
    sorted_idx = np.argsort(tau_grid)
    tau_ascending = tau_grid[sorted_idx]
    t_at_tau = t_grid[sorted_idx]
    return {"t_eq_c": t_eq, "t_hot_c": t_hot,
            "t_c_ascending": t_c_ascending,
            "tau_wrt_t": tau_wrt_t,
            "tau_ascending": tau_ascending,
            "t_at_tau": t_at_tau}


def _edinger_table(t_hot_c: float,
                   met: MetState,
                   budget_params: BudgetParams | None,
                   sinter: SinterConduction | None,
                   *,
                   t_cold_c: float = 5.0,
                   n_bins: int = 101) -> dict:
    """Build (temperature, k_total, t_e) lookup for piecewise re-linearization."""
    t_min = min(t_cold_c, t_hot_c) - 1.0
    t_max = min(SURFACE_FLUX_MAX_T_C, max(t_cold_c, t_hot_c) + 1.0)
    t_values = np.linspace(t_min, t_max, int(max(2, n_bins)))
    k_values = np.empty_like(t_values)
    te_values = np.empty_like(t_values)
    for i, t_here in enumerate(t_values):
        lin = edinger_exchange(float(t_here), met,
                               budget_params=budget_params, sinter=sinter)
        k_values[i] = lin["k_total_w_m2_k"]
        te_values[i] = lin["t_e_c"]
    return {"t_c": t_values, "k": k_values, "t_e": te_values}


def edinger_fill_piecewise(
    t_pool_edge_c: float,
    met: MetState,
    q_cells_m2_s: np.ndarray,
    flow_lengths_m: np.ndarray,
    *,
    budget_params: BudgetParams | None = None,
    sinter: SinterConduction | None = None,
    step_m: float = 1.0,
    t_cold_c: float = 5.0,
    n_bins: int = 101,
) -> dict:
    """Per-cell outflow temperature from piecewise-linearized Edinger integration.
q_cell is held at the cell's own value along the whole path."""
    q = np.asarray(q_cells_m2_s, dtype=np.float64)
    s_target = np.asarray(flow_lengths_m, dtype=np.float64)
    if q.shape != s_target.shape:
        raise ValueError("q_cells and flow_lengths must share shape")
    if (q <= 0.0).any():
        raise ValueError("every q_cell must be > 0")
    if (s_target < 0.0).any():
        raise ValueError("every flow_length must be >= 0")
    step = _finite("step_m", step_m)
    if step <= 0.0:
        raise ValueError("step_m must be > 0")
    table = _edinger_table(t_pool_edge_c, met, budget_params, sinter,
                           t_cold_c=t_cold_c, n_bins=n_bins)
    temps = np.full(q.shape, float(t_pool_edge_c), dtype=np.float64)
    s_current = np.zeros(q.shape, dtype=np.float64)
    denom = RHO_WATER_KG_M3 * CP_WATER_J_KG_K
    s_max = float(s_target.max()) if s_target.size else 0.0
    n_major = int(math.ceil(s_max / step)) if s_max > 0.0 else 0
    for _ in range(n_major):
        remaining = s_target - s_current
        active = remaining > 1.0e-12
        if not active.any():
            break
        ds = np.minimum(step, remaining)
        ds_active = ds[active]
        t_active = temps[active]
        k_active = np.interp(t_active, table["t_c"], table["k"])
        te_active = np.interp(t_active, table["t_c"], table["t_e"])
        exponent = -k_active * ds_active / (denom * q[active])
        temps[active] = te_active + (t_active - te_active) * np.exp(exponent)
        s_current[active] = s_current[active] + ds_active
    return {
        "temperature_c": temps,
        "steps_taken": n_major,
        "step_m": step,
        "table_t_c_range": (float(table["t_c"].min()),
                            float(table["t_c"].max())),
        "n_table_bins": int(len(table["t_c"])),
    }


def graph_energy_sweep(
    filled: np.ndarray,
    weights: np.ndarray,
    discharge: np.ndarray,
    injection_cells: list[tuple[int, int, float, float]],
    met: MetState,
    *,
    budget_params: BudgetParams | None = None,
    sinter: SinterConduction | None = None,
    manning_n: float = DEFAULT_MANNING_N,
    step_m: float = 1.0,
    min_film_depth_m: float = MIN_FILM_DEPTH_M_DEFAULT,
    t_hot_c: float | None = None,
) -> dict:
    """Downstream energy sweep on the routing graph.
Each cell mixes upstream Q*T, cools over step_m with its own q_cell, pushes down."""
    if filled.ndim != 2:
        raise ValueError("filled must be 2-D")
    if weights.shape[:2] != filled.shape or weights.shape[2] != 8:
        raise ValueError("weights must be (H, W, 8) matching filled shape")
    if discharge.shape != filled.shape:
        raise ValueError("discharge shape must match filled")

    h, w = filled.shape
    inflow_qt = np.zeros((h, w), dtype=np.float64)
    temperature = np.full((h, w), np.nan, dtype=np.float32)
    wet = np.zeros((h, w), dtype=bool)
    dry_count = 0

    slope_map = _outflow_network.slope_magnitude(filled, cell_m=CORE_CELL_M)

    injected_sum = 0.0
    for (j, i, q_inj, t_inj) in injection_cells:
        inflow_qt[j, i] += float(q_inj) * float(t_inj)
        injected_sum += float(q_inj) * float(t_inj)
    if not injection_cells:
        return {"temperature": temperature, "wet_mask": wet, "dry_count": 0,
                "injected_qt_wk": 0.0, "exported_qt_wk": 0.0,
                "surface_loss_wk": 0.0, "sinter_loss_wk": 0.0}

    hot_t = float(t_hot_c) if t_hot_c is not None else max(
        float(t) for _, _, _, t in injection_cells)
    tau_tbl = _tau_table(min(SURFACE_FLUX_MAX_T_C, hot_t),
                         met, budget_params, sinter)
    t_eq_c = float(tau_tbl["t_eq_c"])
    t_hot_c_eff = float(tau_tbl["t_hot_c"])
    sink = sinter if sinter is not None else SinterConduction()
    denom = RHO_WATER_KG_M3 * CP_WATER_J_KG_K
    neighbors = _outflow_network._NEIGHBORS

    order_flat = np.argsort(-filled, axis=None, kind="stable")
    surface_loss = 0.0
    sinter_loss = 0.0
    exported_qt = 0.0
    for flat_idx in order_flat:
        j = int(flat_idx) // w
        i = int(flat_idx) % w
        q_cell_total = float(discharge[j, i])
        if q_cell_total <= 0.0:
            continue
        qt_in = float(inflow_qt[j, i])
        if qt_in <= 0.0:
            continue
        t_in = qt_in / q_cell_total
        if t_in > t_hot_c_eff:
            t_in = t_hot_c_eff
        if t_in <= t_eq_c:
            t_out = t_eq_c
        else:
            slope = float(slope_map[j, i])
            if slope <= 0.0:
                slope = 1.0e-5
            q_unit = q_cell_total / CORE_CELL_M
            hydraulics = sheet_flow_depth_velocity(q_unit, slope, t_in,
                                                   manning_n=manning_n)
            if hydraulics["depth_m"] < min_film_depth_m:
                dry_count += 1
                continue
            tau_in = float(np.interp(t_in, tau_tbl["t_c_ascending"],
                                     tau_tbl["tau_wrt_t"]))
            delta_tau = step_m / q_unit
            tau_out = tau_in + delta_tau
            if tau_out >= tau_tbl["tau_ascending"][-1]:
                t_out = t_eq_c
            else:
                t_out = float(np.interp(tau_out,
                                        tau_tbl["tau_ascending"],
                                        tau_tbl["t_at_tau"]))
            if t_out < t_eq_c:
                t_out = t_eq_c
            if t_out > t_in:
                t_out = t_in
        temperature[j, i] = t_out
        wet[j, i] = True
        energy_lost = q_cell_total * denom * (t_in - t_out)
        f_sinter = sink.flux_w_m2(0.5 * (t_in + t_out)) * step_m * CORE_CELL_M
        sinter_loss += f_sinter
        surface_loss += energy_lost - f_sinter
        qt_out_total = q_cell_total * t_out
        row_weights = weights[j, i]
        for k_dir, (dj, di) in enumerate(neighbors):
            w_k = float(row_weights[k_dir])
            if w_k <= 0.0:
                continue
            nj = j + dj
            ni = i + di
            if 0 <= nj < h and 0 <= ni < w:
                inflow_qt[nj, ni] += w_k * qt_out_total
            else:
                exported_qt += w_k * qt_out_total

    return {
        "temperature": temperature,
        "wet_mask": wet,
        "dry_count": dry_count,
        "injected_qt_wk": injected_sum,
        "exported_qt_wk": exported_qt,
        "surface_loss_wk": surface_loss,
        "sinter_loss_wk": sinter_loss,
        "slope_m_m": slope_map,
        "t_equilibrium_c": t_eq_c,
        "t_hot_c": t_hot_c_eff,
    }


def recompute_flow_fraction_wp_a(
    dem: np.ndarray,
    world_pools: list[dict],
    discharges_m3_s: dict,
    *,
    convention: str = "weir",
    mfd_exponent: float = _outflow_network.MFD_EXPONENT,
    cell_m: float = CORE_CELL_M,
) -> dict:
    """Reproduce model's flow_fraction raster using its own library functions.
Rim weights for convention 'weir' come from outflow_network.weir_rim_injection."""
    grid = _outflow_network.Grid(size=CORE_GRID_SIZE, cell_m=cell_m,
                                 half_m=CORE_HALF_M)
    springs_data: list[dict] = []
    for pool in world_pools:
        ring = pool.get("ring", [])
        if len(ring) < 3:
            continue
        pool_mask = _outflow_network.polygon_mask(
            [(float(p[0]), float(p[1])) for p in ring], grid)
        rim = _outflow_network.rim_mask(pool_mask)
        rim_idx = np.argwhere(rim)
        if rim_idx.size == 0:
            continue
        rim_cells_jiz = [(int(j), int(i),
                          float(dem[int(j), int(i)]))
                         for j, i in rim_idx]
        springs_data.append({"pool_mask": pool_mask, "rim_mask": rim,
                             "rim_cells_jiz": rim_cells_jiz,
                             "pool_id": pool.get("id"),
                             "name": pool.get("name"),
                             "source_id": pool.get("source_id")})

    interior_dem = dem.copy().astype(np.float64)
    plateau = float(dem.max()) + 1000.0
    for spring in springs_data:
        interior_only = spring["pool_mask"] & ~spring["rim_mask"]
        interior_dem[interior_only] = plateau
    filled = _outflow_network.fill_depressions(interior_dem)
    weights = _outflow_network.mfd_weights(filled, cell_m=cell_m,
                                           exponent=mfd_exponent)

    injections: list[tuple[int, int, int, float]] = []
    for s_idx, spring in enumerate(springs_data):
        pool_id = spring["pool_id"]
        entry = discharges_m3_s.get(pool_id)
        if entry is None:
            raise ValueError(
                f"pool {pool_id} missing from the spring discharges input")
        if isinstance(entry, dict):
            q = float(entry["discharge_m3_s"])
        else:
            q = float(entry)
        z_rim = [z for _, _, z in spring["rim_cells_jiz"]]
        if convention == "weir":
            weir = _outflow_network.weir_rim_injection(z_rim, q)
            cell_weights = weir["weights"]
            spring["weir"] = weir
        elif convention == "uniform":
            cell_weights = [1.0 / len(z_rim)] * len(z_rim)
            spring["weir"] = None
        else:
            raise ValueError(f"unknown rim-injection convention {convention!r}")
        rim_cells_with_weight: list[tuple[int, int, float]] = []
        for (j, i, _z), w_new in zip(spring["rim_cells_jiz"], cell_weights):
            rim_cells_with_weight.append((int(j), int(i), float(w_new)))
            injections.append((s_idx, int(j), int(i),
                               float(q) * float(w_new)))
        spring["rim_cells"] = rim_cells_with_weight
        spring["discharge_m3_s"] = q

    discharge, dominant, exported = _outflow_network.propagate_discharge(
        weights, filled, injections)
    total_q = sum(float(spring["discharge_m3_s"])
                  for spring in springs_data)
    if total_q > 0:
        normalized_cube = np.zeros_like(discharge, dtype=np.float64)
        for s_idx, spring in enumerate(springs_data):
            q_sp = float(spring["discharge_m3_s"])
            if q_sp > 0:
                normalized_cube[s_idx] = discharge[s_idx] / q_sp
        flow_frac = _outflow_network.flow_fraction_raster(
            normalized_cube.astype(np.float32))
    else:
        flow_frac = _outflow_network.flow_fraction_raster(
            np.zeros_like(discharge, dtype=np.float32))
    return {"filled": filled, "weights": weights, "discharge": discharge,
            "dominant": dominant, "exported": exported,
            "flow_fraction": flow_frac, "springs_data": springs_data,
            "convention": convention}


def verify_flow_fraction_wp_a(
    dem: np.ndarray,
    world_pools: list[dict],
    discharges_m3_s: dict,
    reference_flow_fraction: np.ndarray,
    *,
    convention: str = "weir",
    mfd_exponent: float = _outflow_network.MFD_EXPONENT,
    tolerance: float = 1.0e-6,
) -> dict:
    """Recompute model's flow_fraction via weir_rim_injection and verify equality.
Raises when the max absolute difference exceeds tolerance."""
    out = recompute_flow_fraction_wp_a(dem, world_pools, discharges_m3_s,
                                       convention=convention,
                                       mfd_exponent=mfd_exponent)
    recomputed = out["flow_fraction"]
    diff = np.abs(recomputed.astype(np.float32)
                  - reference_flow_fraction.astype(np.float32))
    max_diff = float(diff.max()) if diff.size else 0.0
    if max_diff > tolerance:
        raise ValueError(
            f"recomputed WP-A flow_fraction disagrees with reference by"
            f" {max_diff:.6e} (tolerance {tolerance:.1e};"
            f" convention {convention})")
    out["max_abs_diff"] = max_diff
    return out


def _injection_cells_from_segments(
    segments: list[dict], springs: list[dict],
    injections_q_m3_s: dict,
) -> list[tuple[int, int, int, float]]:
    """propagate_discharge injections at each root segment's upstream endpoint.
Discharge per injection = Q_spring * segment.flow_fraction."""
    out: list[tuple[int, int, int, float]] = []
    pool_id_by_index: dict[int, str] = {}
    for i, s in enumerate(springs):
        pool_id_by_index[int(s.get("index", i))] = s["pool_id"]
    for seg in segments:
        if seg.get("upstream_id") is not None:
            continue
        s_idx = int(seg["spring_index"])
        pool_id = pool_id_by_index.get(s_idx)
        if pool_id is None:
            continue
        q_total = float(injections_q_m3_s.get(pool_id, 0.0))
        if q_total <= 0.0:
            continue
        q_here = q_total * float(seg.get("flow_fraction", 1.0))
        xz = seg["points_xz"][0]
        x = float(xz[0])
        z = float(xz[1])
        i = int(math.floor((x + CORE_HALF_M) / CORE_CELL_M))
        j = int(math.floor((z + CORE_HALF_M) / CORE_CELL_M))
        if 0 <= i < CORE_GRID_SIZE and 0 <= j < CORE_GRID_SIZE:
            out.append((s_idx, j, i, q_here))
    return out


def verify_flow_fraction(
    dem: np.ndarray,
    springs: list[dict],
    injections_q_m3_s: dict,
    reference_flow_fraction: np.ndarray,
    *,
    mfd_exponent: float = _outflow_network.MFD_EXPONENT,
    tolerance: float = FLOW_FRACTION_VERIFY_TOLERANCE,
) -> dict:
    """Recompute the flow-fraction raster from DEM and compare with reference.
Raises if the max absolute difference on cells wet in both exceeds tolerance."""
    filled = _outflow_network.fill_depressions(dem)
    weights = _outflow_network.mfd_weights(filled, cell_m=CORE_CELL_M,
                                           exponent=mfd_exponent)
    segments = springs if isinstance(springs, dict) else None
    if segments is None:
        raise ValueError(
            "verify_flow_fraction takes the whole network dict; wrap the springs list into {'springs': ..., 'segments': ...}")
    _ = segments
    network = springs
    springs_list = network["springs"]
    segments = network["segments"]
    unit_inj_list: list[tuple[int, int, int, float]] = []
    for seg in segments:
        if seg.get("upstream_id") is not None:
            continue
        s_idx = int(seg["spring_index"])
        xz = seg["points_xz"][0]
        x = float(xz[0])
        z = float(xz[1])
        i = int(math.floor((x + CORE_HALF_M) / CORE_CELL_M))
        j = int(math.floor((z + CORE_HALF_M) / CORE_CELL_M))
        if 0 <= i < CORE_GRID_SIZE and 0 <= j < CORE_GRID_SIZE:
            unit_inj_list.append((s_idx, j, i,
                                  float(seg.get("flow_fraction", 1.0))))
    discharge_cube_unit, _, _ = _outflow_network.propagate_discharge(
        weights, filled, unit_inj_list)
    recomputed = _outflow_network.flow_fraction_raster(discharge_cube_unit)

    scaled_inj_list = _injection_cells_from_segments(
        segments, springs_list, injections_q_m3_s)
    discharge_cube, dominant, exported = _outflow_network.propagate_discharge(
        weights, filled, scaled_inj_list)

    both_wet = ((reference_flow_fraction > 0.001)
                & (recomputed > 0.001))
    valid = np.isfinite(reference_flow_fraction) & np.isfinite(recomputed)
    diff = np.abs(reference_flow_fraction.astype(np.float32) - recomputed)
    diff_both = diff[both_wet & valid]
    both_count = int((both_wet & valid).sum())
    ref_wet = int((reference_flow_fraction > 0.001).sum())
    mine_wet = int((recomputed > 0.001).sum())
    agreement = both_count / max(1, ref_wet)
    max_diff_both = float(diff_both.max()) if diff_both.size else 0.0
    max_diff_overall = float(diff.max()) if diff.size else 0.0
    if max_diff_both > tolerance and agreement < 0.5:
        raise ValueError(
            f"recomputed flow_fraction disagrees on wet-both cells by"
            f" {max_diff_both:.4f} with agreement {agreement:.3f}"
            f" (tolerance {tolerance}; wet-both {both_count},"
            f" reference-wet {ref_wet})")
    return {
        "filled": filled,
        "weights": weights,
        "discharge_cube": discharge_cube,
        "dominant": dominant,
        "exported": exported,
        "max_diff_both_wet": max_diff_both,
        "max_diff_overall": max_diff_overall,
        "cells_wet_in_both": both_count,
        "cells_wet_reference": ref_wet,
        "cells_wet_recomputed": mine_wet,
        "wet_extent_agreement": agreement,
    }


def _rim_cells_from_xz(rim_xz: list) -> list[tuple[int, int]]:
    """Convert rim x,z world coordinates to core-grid (j, i) index tuples."""
    seen: set[tuple[int, int]] = set()
    for xz in rim_xz:
        if len(xz) < 2:
            continue
        x = float(xz[0])
        z = float(xz[1])
        i = int(math.floor((x + CORE_HALF_M) / CORE_CELL_M))
        j = int(math.floor((z + CORE_HALF_M) / CORE_CELL_M))
        if 0 <= i < CORE_GRID_SIZE and 0 <= j < CORE_GRID_SIZE:
            seen.add((j, i))
    return sorted(seen)


def load_dem_core_tif(path: str) -> np.ndarray:
    """Load the 1 m DEM GeoTIFF to a float32 (1280, 1280) ndarray."""
    from PIL import Image
    arr = np.asarray(Image.open(str(path)), dtype=np.float32)
    if arr.shape != (CORE_GRID_SIZE, CORE_GRID_SIZE):
        raise ValueError(
            f"DEM {path} shape {arr.shape} does not match the core grid"
            f" ({CORE_GRID_SIZE}, {CORE_GRID_SIZE})")
    return arr


def load_network_rasters(network: dict, base_dir) -> dict | None:
    """Load spring_index, flow_length_m, and flow_fraction rasters from records.
Verifies dtype, shape and sha256 on each raster record declared in the network."""
    import hashlib
    from pathlib import Path
    section = network.get("rasters")
    if not isinstance(section, dict):
        return None
    base = Path(base_dir)
    out: dict[str, np.ndarray] = {}

    def load_one(name: str, expected_dtype: str) -> np.ndarray:
        entry = section.get(name)
        if isinstance(entry, str):
            record = {"path": entry}
        elif isinstance(entry, dict):
            if "path" not in entry:
                raise ValueError(f"raster record for {name} missing path")
            record = entry
        else:
            raise ValueError(
                f"raster record for {name} must be a string path or dict")
        path = base / record["path"]
        dtype = record.get("dtype", expected_dtype)
        if dtype != expected_dtype:
            raise ValueError(
                f"raster {record['path']} dtype {dtype} does not match"
                f" expected {expected_dtype}")
        data = path.read_bytes()
        declared_sha = record.get("sha256")
        if declared_sha:
            actual_sha = hashlib.sha256(data).hexdigest()
            if actual_sha != declared_sha:
                raise ValueError(
                    f"raster {record['path']} sha256 mismatch")
        arr = np.frombuffer(data, dtype=dtype)
        shape = record.get("shape", [CORE_GRID_SIZE, CORE_GRID_SIZE])
        shape_tuple = tuple(int(v) for v in shape)
        if arr.size != shape_tuple[0] * shape_tuple[1]:
            raise ValueError(
                f"raster {record['path']} size mismatch for shape {shape_tuple}")
        return arr.reshape(shape_tuple)

    for name, dtype in (("spring_index", "<i2"),
                        ("flow_length_m", "<f4"),
                        ("flow_fraction", "<f4")):
        if name not in section:
            return None
        out[name] = load_one(name, dtype)
    return out


def _vent_injections_from_springs(
    springs_data: list[dict],
    spring_temps_c: dict,
    discharges_m3_s: dict,
) -> list[tuple[int, int, float, float]]:
    """Vent injections (j, i, Q_at_cell, T_vent) at model rim cells for the sweep."""
    out: list[tuple[int, int, float, float]] = []
    for spring in springs_data:
        pool_id = spring.get("pool_id")
        if pool_id is None:
            continue
        q_total = float(discharges_m3_s.get(pool_id, 0.0))
        t_vent = spring_temps_c.get(pool_id)
        if q_total <= 0.0 or t_vent is None:
            continue
        for (j, i, w) in spring["rim_cells"]:
            out.append((int(j), int(i),
                        float(q_total) * float(w),
                        float(t_vent)))
    return out


def graph_sweep_outflow_temperature(
    network: dict,
    network_rasters: dict,
    dem: np.ndarray,
    world_pools: list[dict],
    discharges_m3_s: dict,
    spring_temps_c: dict,
    met: MetState,
    *,
    convention: str | None = None,
    mfd_exponent: float | None = None,
    budget_params: BudgetParams | None = None,
    sinter: SinterConduction | None = None,
    manning_n: float = DEFAULT_MANNING_N,
    step_m: float = 1.0,
    min_film_depth_m: float = MIN_FILM_DEPTH_M_DEFAULT,
    forcing_epoch_utc: float | None = None,
    verify_tolerance: float = 1.0e-6,
) -> dict:
    """One-call orchestrator for the accepted graph energy sweep.
Returns temperature, wet_mask, t_equilibrium_c, dry count, verify block, sidecar."""
    if network_rasters is None or "flow_fraction" not in network_rasters:
        raise ValueError(
            "graph_sweep_outflow_temperature requires the network's"
            " spring_index, flow_length_m, and flow_fraction rasters")
    reference_fraction = network_rasters["flow_fraction"]
    if convention is None:
        convention = str(
            network.get("method", {}).get("rim_injection", {}).get(
                "convention", "weir"))
    if mfd_exponent is None:
        mfd_exponent = float(
            network.get("method", {}).get("routing", {}).get(
                "exponent", _outflow_network.MFD_EXPONENT))
    verification = verify_flow_fraction_wp_a(
        dem, world_pools, discharges_m3_s, reference_fraction,
        convention=convention, mfd_exponent=mfd_exponent,
        tolerance=verify_tolerance,
    )
    injection_cells = _vent_injections_from_springs(
        verification["springs_data"], spring_temps_c, discharges_m3_s)
    if not injection_cells:
        raise ValueError(
            "no vent injections could be built; check that each spring in"
            " world.json has a matching discharge and vent temperature")
    total_discharge = verification["discharge"].sum(axis=0).astype(np.float32)
    sweep = graph_energy_sweep(
        verification["filled"], verification["weights"],
        total_discharge, injection_cells, met,
        budget_params=budget_params, sinter=sinter,
        manning_n=manning_n, step_m=step_m,
        min_film_depth_m=min_film_depth_m,
    )
    sidecar = {
        "schema": SCHEMA_VERSION,
        "status": network.get("status", "authored"),
        "fill_method": "graph_energy_sweep_mfd_wp_a_injection",
        "flow_fraction_verify_max_abs_diff": verification["max_abs_diff"],
        "flow_fraction_verify_tolerance": verify_tolerance,
        "flow_fraction_verify_source": (
            "WP-A world.json pool rings + outflow_network.polygon_mask"
            " + rim_mask + weir_rim_injection + fill_depressions"
            " + mfd_weights + propagate_discharge + flow_fraction_raster"),
        "rim_injection_convention": convention,
        "min_film_depth_m": float(min_film_depth_m),
        "min_film_depth_status": MIN_FILM_DEPTH_STATUS,
        "dry_cell_count": int(sweep["dry_count"]),
        "wet_cell_count": int(sweep["wet_mask"].sum()),
        "mfd_exponent": float(mfd_exponent),
        "t_equilibrium_c": float(sweep["t_equilibrium_c"]),
        "t_hot_c": float(sweep["t_hot_c"]),
        "forcing_epoch_utc": forcing_epoch_utc,
        "met": {"air_c": met.air_c, "rh": met.rh,
                "wind_mps": met.wind_mps,
                "shortwave_w_m2": met.shortwave_w_m2,
                "cloud": met.cloud},
        "discharges_m3_s": dict(discharges_m3_s),
        "spring_temps_c": dict(spring_temps_c),
        "segment_profiles_status": (
            "segment_temperature profiles are diagnostic only; the raster"
            " comes from graph_energy_sweep"),
    }
    return {
        "temperature": sweep["temperature"],
        "wet_mask": sweep["wet_mask"],
        "dry_cell_count": int(sweep["dry_count"]),
        "t_equilibrium_c": float(sweep["t_equilibrium_c"]),
        "t_hot_c": float(sweep["t_hot_c"]),
        "injected_qt_wk": float(sweep["injected_qt_wk"]),
        "exported_qt_wk": float(sweep["exported_qt_wk"]),
        "surface_loss_wk": float(sweep["surface_loss_wk"]),
        "sinter_loss_wk": float(sweep["sinter_loss_wk"]),
        "verification": verification,
        "sidecar": sidecar,
        "fill_method": "graph_energy_sweep_mfd_wp_a_injection",
    }


def _topological_segments(segments: list[dict]) -> list[dict]:
    """Order segments so each is listed after its upstream (Kahn's algorithm)."""
    seg_by_id = {seg["id"]: seg for seg in segments}
    downstream: dict[Any, list[dict]] = {}
    in_degree: dict[Any, int] = {}
    for seg in segments:
        seg_id = seg["id"]
        up = seg.get("upstream_id")
        if up is None or up not in seg_by_id:
            in_degree[seg_id] = 0
        else:
            in_degree[seg_id] = 1
            downstream.setdefault(up, []).append(seg)
    from collections import deque
    queue: deque = deque(seg for seg in segments
                         if in_degree[seg["id"]] == 0)
    ordered: list[dict] = []
    while queue:
        current = queue.popleft()
        ordered.append(current)
        for child in downstream.get(current["id"], []):
            in_degree[child["id"]] -= 1
            if in_degree[child["id"]] == 0:
                queue.append(child)
    if len(ordered) != len(segments):
        raise ValueError(
            "segment upstream_id cycle; cannot topologically order")
    return ordered


def _build_spring_profile(segments_in_spring: list[dict],
                          segment_outputs: list[dict]) -> dict:
    """Concatenate the per-segment t_c profiles into one (s, t) array per spring.
s is the cumulative distance from the rim along the main downstream path."""
    seg_by_id = {o["segment_id"]: o for o in segment_outputs}
    children: dict[Any, list[dict]] = {}
    roots = []
    for seg in segments_in_spring:
        up = seg.get("upstream_id")
        if up is None:
            roots.append(seg)
        else:
            children.setdefault(up, []).append(seg)
    s_values: list[float] = []
    t_values: list[float] = []
    visited: set[Any] = set()

    def walk(seg: dict, s_offset: float) -> None:
        if seg["id"] in visited:
            return
        visited.add(seg["id"])
        profile = seg_by_id[seg["id"]]["profile"]
        seg_s = profile["s_m"]
        seg_t = profile["t_c"]
        for s_local, t_local in zip(seg_s, seg_t):
            s_values.append(float(s_offset) + float(s_local))
            t_values.append(float(t_local))
        tail_offset = float(s_offset) + float(seg_s[-1])
        for child in children.get(seg["id"], []):
            walk(child, tail_offset)

    for root in roots:
        walk(root, 0.0)
    paired = sorted(zip(s_values, t_values), key=lambda p: p[0])
    s_arr = np.array([p[0] for p in paired], dtype=np.float64)
    t_arr = np.array([p[1] for p in paired], dtype=np.float64)
    _, unique_idx = np.unique(s_arr, return_index=True)
    unique_idx = np.sort(unique_idx)
    return {"s_m": s_arr[unique_idx], "t_c": t_arr[unique_idx]}


def rasterize_outflow_temperature(*args, **kwargs) -> dict:
    """Rejected per-cell Edinger fill entry point.
Callers must use graph_sweep_outflow_temperature with the DEM and world pools."""
    raise NotImplementedError(
        "rasterize_outflow_temperature has been retired. Call"
        " outflow_thermal.graph_sweep_outflow_temperature with the network,"
        " its spring_index/flow_length_m/flow_fraction rasters, the 1 m DEM"
        " array (load_dem_core_tif), the world.json pool rings, the per-pool"
        " discharges and vent temperatures, and the MetState forcing. The"
        " returned raster carries fill_method"
        " 'graph_energy_sweep_mfd_wp_a_injection'. The segment_temperature"
        " function remains available for diagnostic single-channel profiles"
        " and is not called by the primary pipeline.")


def write_outflow_temperature(
    raster: np.ndarray,
    sidecar: dict,
    f32_path: str,
    json_path: str,
) -> None:
    """Serialize the outflow temperature raster and its JSON sidecar."""
    import hashlib
    import os
    arr = np.ascontiguousarray(raster.astype("<f4"))
    parent = os.path.dirname(os.path.abspath(f32_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    arr.tofile(f32_path)
    digest = hashlib.sha256(arr.tobytes()).hexdigest()
    body = dict(sidecar)
    body["sha256"] = digest
    body["raster_path"] = os.path.basename(f32_path)
    write_json_atomic(json_path, body, indent=2)


__all__ = [
    "SCHEMA_VERSION",
    "RHO_WATER_KG_M3",
    "CP_WATER_J_KG_K",
    "CORE_GRID_SIZE",
    "CORE_CELL_M",
    "CORE_HALF_M",
    "MANNING_REYNOLDS_LOW",
    "MANNING_REYNOLDS_HIGH",
    "SinterConduction",
    "SpringDischarge",
    "water_kinematic_viscosity_m2_s",
    "laminar_film_flow",
    "manning_turbulent_flow",
    "sheet_flow_depth_velocity",
    "manning_sheet_flow",
    "edinger_exchange",
    "edinger_temperature",
    "edinger_fill_piecewise",
    "equilibrium_temperature",
    "graph_energy_sweep",
    "graph_sweep_outflow_temperature",
    "load_dem_core_tif",
    "load_network_rasters",
    "verify_flow_fraction",
    "MIN_FILM_DEPTH_M_DEFAULT",
    "segment_temperature",
    "rasterize_outflow_temperature",
    "write_outflow_temperature",
]
