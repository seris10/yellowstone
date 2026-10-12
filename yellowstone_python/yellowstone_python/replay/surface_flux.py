"""Explicit surface energy budget for the 1-D river-temperature solver.

Replaces the lumped Newton coefficient with four textbook terms, all
positive INTO the water (W/m2):

    shortwave = (1 - albedo) * SW_down
    longwave  = LW_in - emissivity * sigma * T_water^4
    sensible  = rho_air * cp_air * C_H * U * (T_air - T_water)
    latent    = rho_air * L_v * C_E * U * (q_air - q_sat(T_water))

Form choices (illustrative defaults, not fitted parameters):

- Saturation vapor pressure: Magnus form, the same convention as
  microclimate (kept local so replay/ stays dependency-free).
- Incoming longwave: Brutsaert clear-sky emissivity from vapor pressure
  with a Crawford-Duchon-style cloud factor. Needs cloud fraction input.
- Turbulent fluxes: neutral bulk-aerodynamic form with equal heat/moisture
  coefficients and a 0.5 m/s wind floor (avoids a zero-transfer
  singularity; calm-day exchange is parameterized, not resolved).
- Air density from site pressure (~77.8 kPa at 2215 m, same barometric
  formula as microclimate) with a moist-air correction.

The solver linearizes F(T_water) analytically around the old temperature
and treats it implicitly, so large timesteps stay stable:

    F(T_new) ~= F0 + dF/dT * (T_new - T_old)

Use linearized() for the matrix and flux_at() with the NEW temperature
for budget accounting, so closure measures the actual energy change.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

SIGMA_W_M2_K4 = 5.670374419e-8
R_DRY_J_KG_K = 287.058
CP_AIR_J_KG_K = 1005.0
L_VAPOR_J_KG = 2.45e6
SITE_PRESSURE_KPA = 77.8  # ~2215 m via the barometric formula
WIND_FLOOR_MPS = 0.5


def es_kpa(t_c: float) -> float:
    """Saturation vapor pressure, Magnus form (kPa)."""
    return 0.61094 * math.exp(17.625 * t_c / (t_c + 243.04))


def _des_dt(t_c: float) -> float:
    es = es_kpa(t_c)
    return es * 17.625 * 243.04 / (t_c + 243.04) ** 2


def _specific_humidity(es: float, pressure_kpa: float) -> float:
    return 0.622 * es / (pressure_kpa - 0.378 * es)


def _dq_de(pressure_kpa: float, es: float) -> float:
    return 0.622 * pressure_kpa / (pressure_kpa - 0.378 * es) ** 2


def _rho_air_kg_m3(t_c: float, ea_kpa: float,
                   pressure_kpa: float) -> float:
    t_k = t_c + 273.15
    return pressure_kpa * 1000.0 / (R_DRY_J_KG_K * t_k) * (
        1.0 - 0.378 * ea_kpa / pressure_kpa)


def _lw_in_w_m2(air_c: float, rh: float, cloud: float) -> float:
    """Incoming longwave: Brutsaert emissivity + cloud factor."""
    t_k = air_c + 273.15
    ea_hpa = max(rh, 0.01) * es_kpa(air_c) * 10.0
    eps_clear = 0.642 * (ea_hpa / t_k) ** 0.142
    return eps_clear * (1.0 + 0.22 * cloud ** 2) * SIGMA_W_M2_K4 * t_k ** 4


@dataclass(frozen=True)
class MetState:
    """Meteorological forcing at one instant (all validated)."""

    air_c: float
    rh: float  # 0..1
    wind_mps: float
    shortwave_w_m2: float  # downwelling, >= 0
    cloud: float  # 0..1

    def __post_init__(self) -> None:
        for name in ("air_c", "shortwave_w_m2"):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, value)
        rh = float(self.rh)
        if not math.isfinite(rh) or not 0.0 <= rh <= 1.0:
            raise ValueError("rh must be in [0, 1]")
        object.__setattr__(self, "rh", rh)
        wind = float(self.wind_mps)
        if not math.isfinite(wind) or wind < 0.0:
            raise ValueError("wind_mps must be >= 0")
        object.__setattr__(self, "wind_mps", max(wind, WIND_FLOOR_MPS))
        cloud = float(self.cloud)
        if not math.isfinite(cloud) or not 0.0 <= cloud <= 1.0:
            raise ValueError("cloud must be in [0, 1]")
        object.__setattr__(self, "cloud", cloud)
        if self.shortwave_w_m2 < 0.0:
            raise ValueError("shortwave_w_m2 must be >= 0")


@dataclass(frozen=True)
class BudgetParams:
    """Surface properties (defaults illustrative, not fitted)."""

    albedo: float = 0.08
    emissivity: float = 0.97
    c_h: float = 1.5e-3
    c_e: float = 1.5e-3
    pressure_kpa: float = SITE_PRESSURE_KPA

    def __post_init__(self) -> None:
        for name in ("albedo", "emissivity"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
            object.__setattr__(self, name, value)
        for name in ("c_h", "c_e"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be >= 0")
            object.__setattr__(self, name, value)
        pressure = float(self.pressure_kpa)
        if not math.isfinite(pressure) or pressure <= 0.0:
            raise ValueError("pressure_kpa must be positive")
        object.__setattr__(self, "pressure_kpa", pressure)


def flux_at(t_water_c: float, met: MetState,
            params: BudgetParams | None = None) -> dict[str, float]:
    """Component fluxes (W/m2, positive into water) at one water temperature."""
    params = params or BudgetParams()
    t_c = float(t_water_c)
    if not math.isfinite(t_c):
        raise ValueError("t_water_c must be finite")
    t_k = t_c + 273.15
    ea = met.rh * es_kpa(met.air_c)
    rho = _rho_air_kg_m3(met.air_c, ea, params.pressure_kpa)
    q_air = _specific_humidity(ea, params.pressure_kpa)
    q_sat = _specific_humidity(es_kpa(t_c), params.pressure_kpa)

    shortwave = (1.0 - params.albedo) * met.shortwave_w_m2
    longwave = (_lw_in_w_m2(met.air_c, met.rh, met.cloud)
                - params.emissivity * SIGMA_W_M2_K4 * t_k ** 4)
    sensible = (rho * CP_AIR_J_KG_K * params.c_h * met.wind_mps
                * (met.air_c - t_c))
    latent = (rho * L_VAPOR_J_KG * params.c_e * met.wind_mps
              * (q_air - q_sat))
    return {"shortwave": shortwave, "longwave": longwave,
            "sensible": sensible, "latent": latent,
            "net": shortwave + longwave + sensible + latent}


def linearized(t_water_c: float, met: MetState,
               params: BudgetParams | None = None
               ) -> tuple[float, float]:
    """(F0, dF/dT) of net flux at t_water_c, analytic derivative."""
    params = params or BudgetParams()
    parts = flux_at(t_water_c, met, params)
    t_k = float(t_water_c) + 273.15
    ea = met.rh * es_kpa(met.air_c)
    rho = _rho_air_kg_m3(met.air_c, ea, params.pressure_kpa)
    es_w = es_kpa(float(t_water_c))
    dq_sat = _dq_de(params.pressure_kpa, es_w) * _des_dt(float(t_water_c))
    slope = (-4.0 * params.emissivity * SIGMA_W_M2_K4 * t_k ** 3
             - rho * CP_AIR_J_KG_K * params.c_h * met.wind_mps
             - rho * L_VAPOR_J_KG * params.c_e * met.wind_mps * dq_sat)
    return parts["net"], slope


def spec_from_series(rh: Any, wind_mps: Any, shortwave_w_m2: Any,
                     cloud: Any, params: dict | None = None) -> dict:
    """Build a River-config "surface_budget" mapping from Series-ish inputs."""
    from .river_transport import Series
    return {
        "rh": {"times_s": list(Series.parse(rh).times_s),
               "values": list(Series.parse(rh).values)},
        "wind_mps": {"times_s": list(Series.parse(wind_mps).times_s),
                     "values": list(Series.parse(wind_mps).values)},
        "shortwave_w_m2": {
            "times_s": list(Series.parse(shortwave_w_m2).times_s),
            "values": list(Series.parse(shortwave_w_m2).values)},
        "cloud": {"times_s": list(Series.parse(cloud).times_s),
                  "values": list(Series.parse(cloud).values)},
        "params": dict(params or {}),
    }
