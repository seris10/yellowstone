"""River dissolved oxygen on the replay cells."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite

import math
from dataclasses import dataclass
from typing import Any

from yellowstone_python.common.site import SITE_ELEVATION_M, SITE_PRESSURE_KPA
import yellowstone_python.aquatic.periphyton as periphyton
from yellowstone_python.river.river_transport import solve_tridiagonal

SCHEMA = "yellowstone.river_oxygen.v1"
STANDARD_PRESSURE_KPA = 101.325

BK_A1 = -139.34411
BK_A2 = 1.575701e5
BK_A3 = -6.642308e7
BK_A4 = 1.243800e10
BK_A5 = -8.621949e11

PWV_A1 = 11.8571
PWV_A2 = -3840.70
PWV_A3 = -216961.0

THETA_B1 = 0.000975
THETA_B2 = -1.426e-5
THETA_B3 = 6.436e-8

BENSON_KRAUSE_SOURCE = (
    "Benson and Krause (1984), Limnology and Oceanography 29(3), 620-632, "
    "equation 31 for ln(C*) at 1 atm and the pressure correction "
    "that USGS DOTABLES also tabulates"
)
DOTABLES_URL = "https://water.usgs.gov/water-resources/software/DOTABLES/"

OCONNOR_DOBBINS_COEF = 3.93
CHURCHILL_COEF = 5.026
OWENS_COEF = 5.32

OCONNOR_DOBBINS_SOURCE = (
    "O'Connor and Dobbins (1958), Trans. ASCE 123, 641-684; metric form "
    "k2 = 3.93 * V^0.5 / H^1.5 with V in m/s and H in m, 1/d base e, as "
    "collected by Thomann and Mueller (1987), Principles of Surface Water "
    "Quality Modeling and Control, table 6.3"
)
CHURCHILL_SOURCE = (
    "Churchill, Elmore and Buckingham (1962), Journal of the Sanitary "
    "Engineering Division (ASCE) 88(SA4), 1-46; metric form k2 = 5.026 * "
    "V / H^1.67 (Thomann and Mueller 1987, table 6.3)"
)
OWENS_SOURCE = (
    "Owens, Edwards and Gibbs (1964), International Journal of Air and "
    "Water Pollution 8, 469-486; metric form k2 = 5.32 * V^0.67 / H^1.85 "
    "(Thomann and Mueller 1987, table 6.3)"
)
COVAR_SOURCE = (
    "Covar (1976), applicability of selected stream reaeration formulas, "
    "report chapter in U.S. EPA (1976) Simulation of Water Quality in "
    "Streams and Canals; the three-regime rule used here follows the "
    "QUAL2K and InfoWorks ICM form (Chapra, Pelletier and Tao, QUAL2K "
    "manual, reaeration Internal option; Innovyze InfoWorks ICM Dissolved "
    "Oxygen help page): if H < 0.61 m use Owens-Edwards-Gibbs; else if "
    "H > 3.45 * U^2.5 use O'Connor and Dobbins; else use Churchill"
)

COVAR_SHALLOW_DEPTH_M = 0.61
COVAR_DEEP_SLOW_COEF = 3.45
COVAR_DEEP_SLOW_EXPONENT = 2.5

SALMONID_GROWTH_MIN_MG_L = 6.5
SALMONID_ACUTE_MIN_MG_L = 5.0
SALMONID_SURVIVAL_MIN_MG_L = 3.0
SALMONID_SOURCE = (
    "U.S. EPA (1986), Ambient Water Quality Criteria for Dissolved Oxygen "
    "(Freshwater), EPA 440/5-86-003, table 1 cold-water criteria; "
    "authored_ramp between the acute minimum of 3 mg/L and the growth "
    "minimum of 6.5 mg/L"
)

INSECT_SENSITIVE_MIN_MG_L = 4.0
INSECT_LETHAL_MIN_MG_L = 2.0
INSECT_SOURCE = (
    "Davis (1975), J. Fisheries Research Board of Canada 32, 2295-2332, "
    "review of aquatic invertebrate DO responses"
)




def pressure_from_elevation_kpa(elevation_m: float) -> float:
    """Standard atmosphere barometric pressure at the given elevation."""
    h = _finite("elevation_m", elevation_m)
    return STANDARD_PRESSURE_KPA * (1.0 - 2.25577e-5 * h) ** 5.25588


def saturation_mg_l(temp_c: float,
                    pressure_kpa: float | None = None) -> float:
    """Dissolved oxygen solubility at temperature and pressure."""
    t_c = _finite("temp_c", temp_c)
    if t_c < -0.5 or t_c > 50.0:
        raise ValueError(
            'temp_c must lie within the Benson and Krause (1984) valid range of -0.5 to 50 degC')
    p_kpa = (SITE_PRESSURE_KPA if pressure_kpa is None
             else _finite("pressure_kpa", pressure_kpa, minimum=0.0))
    if p_kpa <= 0.0:
        raise ValueError("pressure_kpa must be positive")
    t_k = t_c + 273.15
    ln_c_star = (BK_A1
                 + BK_A2 / t_k
                 + BK_A3 / (t_k * t_k)
                 + BK_A4 / (t_k ** 3)
                 + BK_A5 / (t_k ** 4))
    c_star_1atm = math.exp(ln_c_star)
    p_atm = p_kpa / STANDARD_PRESSURE_KPA
    pwv_atm = math.exp(PWV_A1 + PWV_A2 / t_k + PWV_A3 / (t_k * t_k))
    theta = THETA_B1 + THETA_B2 * t_c + THETA_B3 * t_c * t_c
    numerator = (1.0 - pwv_atm / p_atm) * (1.0 - theta * p_atm)
    denominator = (1.0 - pwv_atm) * (1.0 - theta)
    if denominator <= 0.0:
        raise ValueError(
            "pressure correction denominator is nonpositive")
    correction = p_atm * numerator / denominator
    return c_star_1atm * correction


def oconnor_dobbins_per_day(velocity_m_s: float, depth_m: float) -> float:
    """O'Connor-Dobbins reaeration rate k2 (1/day, base e), metric form."""
    v = _finite("velocity_m_s", velocity_m_s, minimum=0.0)
    h = _finite("depth_m", depth_m)
    if h <= 0.0:
        raise ValueError("depth_m must be positive")
    return OCONNOR_DOBBINS_COEF * math.sqrt(v) / (h ** 1.5)


def churchill_per_day(velocity_m_s: float, depth_m: float) -> float:
    """Churchill reaeration rate k2 (1/day, base e), metric form."""
    v = _finite("velocity_m_s", velocity_m_s, minimum=0.0)
    h = _finite("depth_m", depth_m)
    if h <= 0.0:
        raise ValueError("depth_m must be positive")
    return CHURCHILL_COEF * v / (h ** 1.67)


def owens_per_day(velocity_m_s: float, depth_m: float) -> float:
    """Owens-Edwards-Gibbs reaeration rate k2 (1/day, base e), metric form."""
    v = _finite("velocity_m_s", velocity_m_s, minimum=0.0)
    h = _finite("depth_m", depth_m)
    if h <= 0.0:
        raise ValueError("depth_m must be positive")
    return OWENS_COEF * (v ** 0.67) / (h ** 1.85)


def select_reaeration_formula(velocity_m_s: float, depth_m: float) -> str:
    """Covar (1976) three-regime selection by depth and velocity.
H < 0.61 m: Owens-Gibbs. Else H > 3.45 * U^2.5: O'Connor-Dobbins. Else: Churchill."""
    v = _finite("velocity_m_s", velocity_m_s, minimum=0.0)
    h = _finite("depth_m", depth_m)
    if h <= 0.0:
        raise ValueError("depth_m must be positive")
    if h < COVAR_SHALLOW_DEPTH_M:
        return "owens_edwards_gibbs"
    threshold = COVAR_DEEP_SLOW_COEF * (v ** COVAR_DEEP_SLOW_EXPONENT)
    if h > threshold:
        return "oconnor_dobbins"
    return "churchill"


def reaeration_per_day(velocity_m_s: float, depth_m: float) -> float:
    """Base-e reaeration rate k2 (1/day) selected per Covar (1976)."""
    formula = select_reaeration_formula(velocity_m_s, depth_m)
    if formula == "owens_edwards_gibbs":
        return owens_per_day(velocity_m_s, depth_m)
    if formula == "churchill":
        return churchill_per_day(velocity_m_s, depth_m)
    return oconnor_dobbins_per_day(velocity_m_s, depth_m)


def reaeration_mg_l_per_s(do_mg_l: float, do_sat_mg_l: float,
                          velocity_m_s: float, depth_m: float) -> float:
    """Reaeration flux (DO_sat - DO) * k2 as mg/L/s."""
    k2 = reaeration_per_day(velocity_m_s, depth_m)
    deficit = (_finite("do_sat_mg_l", do_sat_mg_l, minimum=0.0)
               - _finite("do_mg_l", do_mg_l, minimum=0.0))
    return deficit * k2 / 86400.0


def _ramp(value: float, low: float, high: float) -> float:
    """Linear ramp from 0 at low to 1 at high; outside the range the end values."""
    if high <= low:
        raise ValueError("high must be greater than low")
    if value <= low:
        return 0.0
    if value >= high:
        return 1.0
    return (value - low) / (high - low)


def fish_suitability(do_mg_l: float) -> float:
    """Salmonid DO suitability in [0, 1] from EPA (1986) cold-water criteria."""
    do = _finite("do_mg_l", do_mg_l, minimum=0.0)
    return _ramp(do, SALMONID_SURVIVAL_MIN_MG_L, SALMONID_GROWTH_MIN_MG_L)


def insect_survival(do_mg_l: float) -> float:
    """Aquatic insect survival factor in [0, 1] from Davis (1975)."""
    do = _finite("do_mg_l", do_mg_l, minimum=0.0)
    return _ramp(do, INSECT_LETHAL_MIN_MG_L, INSECT_SENSITIVE_MIN_MG_L)


@dataclass(frozen=True)
class OxygenCell:
    """Per-cell state used by the oxygen solver."""

    id: str
    length_m: float
    width_m: float
    depth_m: float
    velocity_m_s: float
    temp_c: float
    do_mg_l: float
    biomass_mg_c_m2: float = 0.0
    shortwave_w_m2: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("id must be a nonempty string")
        for name in ("length_m", "width_m", "depth_m"):
            value = _finite(name, getattr(self, name), minimum=0.0)
            if value <= 0.0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        for name in ("velocity_m_s", "do_mg_l", "biomass_mg_c_m2",
                     "shortwave_w_m2"):
            object.__setattr__(
                self, name, _finite(name, getattr(self, name), minimum=0.0))
        object.__setattr__(
            self, "temp_c", _finite("temp_c", self.temp_c))


def _metabolism_mg_l_s(cell: OxygenCell,
                       params: periphyton.PeriphytonParams | None
                       ) -> dict[str, float]:
    if params is None:
        return {"gpp_mg_l_s": 0.0, "respiration_mg_l_s": 0.0,
                "net_mg_l_s": 0.0}
    fluxes = periphyton.net_o2_production_mg_o2_m2_s(
        cell.biomass_mg_c_m2, cell.shortwave_w_m2, cell.temp_c, params)
    water_depth_l_per_m2 = cell.depth_m * 1000.0
    return {
        "gpp_mg_l_s": fluxes["gpp_mg_o2_m2_s"] / water_depth_l_per_m2,
        "respiration_mg_l_s":
            fluxes["respiration_mg_o2_m2_s"] / water_depth_l_per_m2,
        "net_mg_l_s": fluxes["net_mg_o2_m2_s"] / water_depth_l_per_m2,
    }


def advective_courant(velocity_m_s: float, dt_s: float,
                      length_m: float) -> float:
    """Advective Courant number V * dt / dx."""
    v = _finite("velocity_m_s", velocity_m_s, minimum=0.0)
    dt = _finite("dt_s", dt_s, minimum=0.0)
    dx = _finite("length_m", length_m)
    if dx <= 0.0:
        raise ValueError("length_m must be positive")
    return v * dt / dx


def step_cell(cell: OxygenCell, upstream_do_mg_l: float, dt_s: float,
              pressure_kpa: float | None = None,
              periphyton_params: periphyton.PeriphytonParams | None = None
              ) -> dict[str, Any]:
    """Advance DO for one cell by dt_s using explicit upwind advection.
Raises when the advective Courant number exceeds 1."""
    dt = _finite("dt_s", dt_s, minimum=0.0)
    if dt <= 0.0:
        raise ValueError("dt_s must be positive")
    courant = advective_courant(cell.velocity_m_s, dt, cell.length_m)
    if courant > 1.0:
        raise ValueError(
            f"advective Courant number {courant:.3g} exceeds 1 in cell "
            f"{cell.id!r}; shorten dt_s or use advect_cells for the implicit "
            f"upwind path")
    up = _finite("upstream_do_mg_l", upstream_do_mg_l, minimum=0.0)
    sat = saturation_mg_l(cell.temp_c, pressure_kpa)
    reaer = reaeration_mg_l_per_s(cell.do_mg_l, sat, cell.velocity_m_s,
                                  cell.depth_m)
    metab = _metabolism_mg_l_s(cell, periphyton_params)
    if cell.velocity_m_s > 0.0:
        advection = (up - cell.do_mg_l) * cell.velocity_m_s / cell.length_m
    else:
        advection = 0.0
    delta = dt * (advection + reaer + metab["net_mg_l_s"])
    new_do = cell.do_mg_l + delta
    if new_do < 0.0:
        new_do = 0.0
    return {
        "do_mg_l": new_do,
        "saturation_mg_l": sat,
        "reaeration_mg_l_s": reaer,
        "gpp_mg_l_s": metab["gpp_mg_l_s"],
        "respiration_mg_l_s": metab["respiration_mg_l_s"],
        "metabolism_mg_l_s": metab["net_mg_l_s"],
        "advection_mg_l_s": advection,
        "advective_courant": courant,
        "reaeration_formula": select_reaeration_formula(
            cell.velocity_m_s, cell.depth_m),
    }


def advect_cells(cells: list[OxygenCell], upstream_do_mg_l: float, dt_s: float,
                 pressure_kpa: float | None = None,
                 periphyton_params: periphyton.PeriphytonParams | None = None
                 ) -> dict[str, Any]:
    """Implicit upwind advection pass over an ordered chain of cells.
Backward-Euler solve using the shared tridiagonal operator; stable at any Courant number."""
    dt = _finite("dt_s", dt_s, minimum=0.0)
    if dt <= 0.0:
        raise ValueError("dt_s must be positive")
    if not cells:
        raise ValueError("cells must be nonempty")
    up = _finite("upstream_do_mg_l", upstream_do_mg_l, minimum=0.0)
    n = len(cells)
    diag = [0.0] * n
    lower = [0.0] * n
    upper = [0.0] * n
    rhs = [0.0] * n
    per_cell_sat: list[float] = []
    per_cell_metab: list[dict[str, float]] = []
    per_cell_formula: list[str] = []
    per_cell_reaer_rate_per_s: list[float] = []
    max_courant = 0.0
    for i, cell in enumerate(cells):
        volume_m3 = cell.length_m * cell.width_m * cell.depth_m
        if volume_m3 <= 0.0:
            raise ValueError(f"cell {cell.id!r} has nonpositive volume")
        q_m3_s = cell.velocity_m_s * cell.width_m * cell.depth_m
        courant = advective_courant(cell.velocity_m_s, dt, cell.length_m)
        if courant > max_courant:
            max_courant = courant
        sat = saturation_mg_l(cell.temp_c, pressure_kpa)
        per_cell_sat.append(sat)
        metab = _metabolism_mg_l_s(cell, periphyton_params)
        per_cell_metab.append(metab)
        per_cell_formula.append(select_reaeration_formula(
            cell.velocity_m_s, cell.depth_m))
        k2_per_s = reaeration_per_day(cell.velocity_m_s, cell.depth_m) / 86400.0
        per_cell_reaer_rate_per_s.append(k2_per_s)
        storage = volume_m3 / dt
        diag[i] = storage + q_m3_s + volume_m3 * k2_per_s
        if i == 0:
            lower[i] = 0.0
            rhs[i] = (storage * cell.do_mg_l
                      + q_m3_s * up
                      + volume_m3 * k2_per_s * sat
                      + volume_m3 * metab["net_mg_l_s"])
        else:
            lower[i] = -q_m3_s
            rhs[i] = (storage * cell.do_mg_l
                      + volume_m3 * k2_per_s * sat
                      + volume_m3 * metab["net_mg_l_s"])
        upper[i] = 0.0
    solution = solve_tridiagonal(
        lower, diag, upper, rhs,
        cell_ids=[cell.id for cell in cells])
    rows = []
    inflow = up
    for i, cell in enumerate(cells):
        do_new = solution[i]
        if do_new < 0.0:
            do_new = 0.0
        volume_m3 = cell.length_m * cell.width_m * cell.depth_m
        reaer = per_cell_reaer_rate_per_s[i] * (per_cell_sat[i] - do_new)
        q_m3_s = cell.velocity_m_s * cell.width_m * cell.depth_m
        advection_mg_l_s = (
            q_m3_s * (inflow - do_new) / volume_m3
            if cell.velocity_m_s > 0.0 else 0.0)
        rows.append({
            "do_mg_l": do_new,
            "saturation_mg_l": per_cell_sat[i],
            "reaeration_mg_l_s": reaer,
            "gpp_mg_l_s": per_cell_metab[i]["gpp_mg_l_s"],
            "respiration_mg_l_s": per_cell_metab[i]["respiration_mg_l_s"],
            "metabolism_mg_l_s": per_cell_metab[i]["net_mg_l_s"],
            "advection_mg_l_s": advection_mg_l_s,
            "reaeration_formula": per_cell_formula[i],
            "advective_courant": advective_courant(
                cell.velocity_m_s, dt, cell.length_m),
        })
        inflow = do_new
    return {
        "cells": rows,
        "max_advective_courant": max_courant,
        "method": "implicit_upwind_backward_euler_shared_tridiagonal",
    }


def describe_model(pressure_kpa: float | None = None) -> dict[str, Any]:
    """Model metadata suitable for a sidecar JSON."""
    p = SITE_PRESSURE_KPA if pressure_kpa is None else pressure_kpa
    return {
        "schema": SCHEMA,
        "status": "illustrative",
        "sources": {
            "saturation": BENSON_KRAUSE_SOURCE,
            "dotables_reference": DOTABLES_URL,
            "oconnor_dobbins": OCONNOR_DOBBINS_SOURCE,
            "churchill": CHURCHILL_SOURCE,
            "owens_edwards_gibbs": OWENS_SOURCE,
            "reaeration_selection": COVAR_SOURCE,
            "fish_suitability": SALMONID_SOURCE,
            "insect_survival": INSECT_SOURCE,
        },
        "parameters": {
            "pressure_kpa": p,
            "site_elevation_m": SITE_ELEVATION_M,
            "oconnor_dobbins_coefficient": OCONNOR_DOBBINS_COEF,
            "churchill_coefficient": CHURCHILL_COEF,
            "owens_coefficient": OWENS_COEF,
            "covar_shallow_depth_m": COVAR_SHALLOW_DEPTH_M,
            "covar_deep_slow_coef": COVAR_DEEP_SLOW_COEF,
            "covar_deep_slow_exponent": COVAR_DEEP_SLOW_EXPONENT,
            "salmonid_growth_min_mg_l": SALMONID_GROWTH_MIN_MG_L,
            "salmonid_acute_min_mg_l": SALMONID_ACUTE_MIN_MG_L,
            "salmonid_survival_min_mg_l": SALMONID_SURVIVAL_MIN_MG_L,
            "insect_sensitive_min_mg_l": INSECT_SENSITIVE_MIN_MG_L,
            "insect_lethal_min_mg_l": INSECT_LETHAL_MIN_MG_L,
        },
    }


def score_against_observations(predicted_mg_l: list[float],
                               observed_mg_l: list[float]
                               ) -> dict[str, float]:
    """RMSE, bias and MAE for predicted DO against an observed series."""
    if len(predicted_mg_l) != len(observed_mg_l):
        raise ValueError("predicted and observed series must have the same length")
    if not predicted_mg_l:
        raise ValueError("series must be nonempty")
    residuals = [
        _finite("predicted_mg_l", p) - _finite("observed_mg_l", o)
        for p, o in zip(predicted_mg_l, observed_mg_l)
    ]
    n = len(residuals)
    mse = math.fsum(r * r for r in residuals) / n
    return {
        "n": float(n),
        "rmse_mg_l": math.sqrt(mse),
        "bias_mg_l": math.fsum(residuals) / n,
        "mae_mg_l": math.fsum(abs(r) for r in residuals) / n,
        "max_abs_mg_l": max(abs(r) for r in residuals),
    }
