"""Explicit surface energy budget for the 1-D river solver (W/m2, positive into water)."""
from __future__ import annotations

import math
from functools import lru_cache
import warnings
from dataclasses import asdict, dataclass
from typing import Any

from yellowstone_python.common.site import SITE_PRESSURE_KPA
from yellowstone_python.common.checks import finite

SIGMA_W_M2_K4 = 5.670374419e-8
R_DRY_J_KG_K = 287.058
CP_AIR_J_KG_K = 1005.0
L_VAPOR_J_KG = 2.45e6
WIND_FLOOR_MPS = 0.5
CLOUD_LONGWAVE_FACTOR_DEFAULT = 0.22

# Diagnostic ceiling for turbulent-transfer coefficients; typical open-water values are 1e-3 to 3e-3.
BULK_COEFFICIENT_HIGH = 1.0e-2

# Radiation multipliers outside [0.1, 2.0] produce diagnostics.
RADIATION_MULTIPLIER_LOW = 0.1
RADIATION_MULTIPLIER_HIGH = 2.0

# Longwave bias is diagnostic when the cloud estimate approaches a large fraction of clear-sky flux.
LONGWAVE_BIAS_SUSPECT_W_M2 = 100.0

MIN_THERMODYNAMIC_C = -80.0
MAX_THERMODYNAMIC_C = 100.0
MIN_PRESSURE_KPA = 40.0
MAX_PRESSURE_KPA = 110.0

_IAPWS_TC_K = 647.096
_IAPWS_PC_KPA = 22064.0
_IAPWS_A = (-7.85951783, 1.84408259, -11.7866497,
            22.6807411, -15.9618719, 1.80122502)

BLEND_T_LOW = 80.0
BLEND_T_HIGH = 90.0

# Provenance labels for the effective surface model (default provenance).
PARAMETER_STATUS = {
    "albedo": "illustrative",
    "emissivity": "literature_or_assumed",
    "c_h": "illustrative_default",
    "c_e": "illustrative_default",
    "pressure_kpa": "derived_from_site_elevation",
    "shortwave_multiplier": "illustrative",
    "longwave_multiplier": "illustrative",
    "longwave_bias_w_m2": "illustrative",
    "cloud_longwave_factor": "illustrative_uncalibrated",
    "a_RH": "identity_default",
    "b_RH": "identity_default",
}


def _temperature_c(value: Any, name: str) -> float:
    return finite(name, value, minimum=MIN_THERMODYNAMIC_C, maximum=MAX_THERMODYNAMIC_C)


def _es_magnus_kpa(t_c: float) -> float:
    """Pure Magnus saturation vapor pressure (kPa) at temperature t_c (C)."""
    denominator = t_c + 243.04
    if denominator <= 1.0:
        raise ValueError("temperature is outside the valid Magnus domain")
    result = 0.61094 * math.exp(17.625 * t_c / denominator)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(
            "saturation vapor pressure is nonfinite or nonpositive")
    return result


def _des_dt_magnus(t_c: float) -> float:
    """Pure Magnus dEs/dT (kPa/K)."""
    return _es_magnus_kpa(t_c) * 17.625 * 243.04 / (t_c + 243.04) ** 2


def es_kpa_wagner_pruss(t_c: float) -> float:
    """Saturation vapor pressure (kPa) from Wagner and Pruss (2002) Eq. 2.5."""
    t_k = float(t_c) + 273.15
    if t_k <= 0.0 or t_k > _IAPWS_TC_K:
        raise ValueError("temperature outside Wagner-Pruss domain")
    theta = 1.0 - t_k / _IAPWS_TC_K
    a = _IAPWS_A
    terms = (a[0] * theta
             + a[1] * theta ** 1.5
             + a[2] * theta ** 3.0
             + a[3] * theta ** 3.5
             + a[4] * theta ** 4.0
             + a[5] * theta ** 7.5)
    pressure_kpa = _IAPWS_PC_KPA * math.exp(_IAPWS_TC_K / t_k * terms)
    if not math.isfinite(pressure_kpa) or pressure_kpa <= 0.0:
        raise ValueError(
            "Wagner-Pruss saturation pressure is nonfinite or nonpositive")
    return pressure_kpa


def _des_dt_wagner_pruss(t_c: float) -> float:
    """Numerical dEs/dT (kPa/K) for the Wagner-Pruss branch."""
    delta = 1.0e-3
    hi = es_kpa_wagner_pruss(t_c + delta)
    lo = es_kpa_wagner_pruss(t_c - delta)
    return (hi - lo) / (2.0 * delta)


def _blend_weight(t_c: float) -> float:
    """0 at or below BLEND_T_LOW, 1 at or above BLEND_T_HIGH, smoothstep between."""
    if t_c <= BLEND_T_LOW:
        return 0.0
    if t_c >= BLEND_T_HIGH:
        return 1.0
    s = (t_c - BLEND_T_LOW) / (BLEND_T_HIGH - BLEND_T_LOW)
    return s * s * (3.0 - 2.0 * s)


def _dblend_weight_dt(t_c: float) -> float:
    """dw/dT for the smoothstep blend; zero at the endpoints."""
    if t_c <= BLEND_T_LOW or t_c >= BLEND_T_HIGH:
        return 0.0
    s = (t_c - BLEND_T_LOW) / (BLEND_T_HIGH - BLEND_T_LOW)
    return 6.0 * s * (1.0 - s) / (BLEND_T_HIGH - BLEND_T_LOW)


def es_kpa(t_c: float) -> float:
    """Saturation vapor pressure (kPa)."""
    t_c = _temperature_c(t_c, "temperature")
    if t_c <= BLEND_T_LOW:
        return _es_magnus_kpa(t_c)
    if t_c >= BLEND_T_HIGH:
        return es_kpa_wagner_pruss(t_c)
    weight = _blend_weight(t_c)
    return ((1.0 - weight) * _es_magnus_kpa(t_c)
            + weight * es_kpa_wagner_pruss(t_c))


def _des_dt(t_c: float) -> float:
    """dEs/dT (kPa/K) consistent with the blended es_kpa branch choice."""
    t_c = _temperature_c(t_c, "temperature")
    if t_c <= BLEND_T_LOW:
        return _des_dt_magnus(t_c)
    if t_c >= BLEND_T_HIGH:
        return _des_dt_wagner_pruss(t_c)
    weight = _blend_weight(t_c)
    dweight_dt = _dblend_weight_dt(t_c)
    e_magnus = _es_magnus_kpa(t_c)
    e_wp = es_kpa_wagner_pruss(t_c)
    return ((1.0 - weight) * _des_dt_magnus(t_c)
            + weight * _des_dt_wagner_pruss(t_c)
            + dweight_dt * (e_wp - e_magnus))


def _check_vapor_pressure(vapor_pressure_kpa: float,
                          pressure_kpa: float) -> float:
    """Return pressure - 0.378 * e, rejecting physically invalid inputs."""
    if not 0.0 <= vapor_pressure_kpa < pressure_kpa:
        raise ValueError(
            "vapor pressure is incompatible with total pressure")
    denominator = pressure_kpa - 0.378 * vapor_pressure_kpa
    if denominator <= 0.0:
        raise ValueError(
            "vapor pressure is incompatible with total pressure")
    return denominator


def _specific_humidity(vapor_pressure_kpa: float,
                       pressure_kpa: float) -> float:
    denominator = _check_vapor_pressure(vapor_pressure_kpa, pressure_kpa)
    result = 0.622 * vapor_pressure_kpa / denominator
    if not math.isfinite(result) or result < 0.0:
        raise ValueError("specific humidity is invalid")
    return result


def _dq_de(pressure_kpa: float, vapor_pressure_kpa: float) -> float:
    denominator = _check_vapor_pressure(vapor_pressure_kpa, pressure_kpa)
    return 0.622 * pressure_kpa / denominator ** 2


def _rho_air_kg_m3(t_c: float, ea_kpa: float,
                   pressure_kpa: float) -> float:
    t_c = _temperature_c(t_c, "air temperature")
    _check_vapor_pressure(ea_kpa, pressure_kpa)
    t_k = t_c + 273.15
    return pressure_kpa * 1000.0 / (R_DRY_J_KG_K * t_k) * (
        1.0 - 0.378 * ea_kpa / pressure_kpa)


def _transfer_wind_mps(wind_mps: float) -> float:
    """Wind used by the bulk-transfer parameterization (floored)."""
    return max(float(wind_mps), WIND_FLOOR_MPS)


def _lw_in_w_m2(air_c: float, rh: float, cloud: float, *,
                cloud_factor: float = CLOUD_LONGWAVE_FACTOR_DEFAULT
                ) -> float:
    """Downwelling longwave radiation (W/m2)."""
    t_c = _temperature_c(air_c, "air temperature")
    rh = float(rh)
    cloud = float(cloud)
    if not 0.0 <= rh <= 1.0:
        raise ValueError("rh must be in [0, 1]")
    if not 0.0 <= cloud <= 1.0:
        raise ValueError("cloud must be in [0, 1]")
    t_k = t_c + 273.15
    ea_hpa = max(rh, 0.01) * es_kpa(t_c) * 10.0
    eps_clear = 0.642 * (ea_hpa / t_k) ** 0.142
    result = (eps_clear * (1.0 + cloud_factor * cloud ** 2)
              * SIGMA_W_M2_K4 * t_k ** 4)
    return finite("incoming longwave", result)


@dataclass(frozen=True)
class MetState:
    """Meteorological forcing at one instant (all validated)."""

    air_c: float
    rh: float  # 0..1
    wind_mps: float
    shortwave_w_m2: float  # downwelling, >= 0
    cloud: float  # 0..1
    longwave_down_w_m2: float | None = None  # measured, >= 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "air_c", _temperature_c(self.air_c, "air_c"))
        shortwave = float(self.shortwave_w_m2)
        if not math.isfinite(shortwave):
            raise ValueError("shortwave_w_m2 must be finite")
        if shortwave < 0.0:
            raise ValueError("shortwave_w_m2 must be >= 0")
        object.__setattr__(self, "shortwave_w_m2", shortwave)
        rh = float(self.rh)
        if not math.isfinite(rh) or not 0.0 <= rh <= 1.0:
            raise ValueError("rh must be in [0, 1]")
        object.__setattr__(self, "rh", rh)
        wind = float(self.wind_mps)
        if not math.isfinite(wind) or wind < 0.0:
            raise ValueError("wind_mps must be >= 0")
        object.__setattr__(self, "wind_mps", wind)
        cloud = float(self.cloud)
        if not math.isfinite(cloud) or not 0.0 <= cloud <= 1.0:
            raise ValueError("cloud must be in [0, 1]")
        object.__setattr__(self, "cloud", cloud)
        if self.longwave_down_w_m2 is not None:
            longwave = float(self.longwave_down_w_m2)
            if not math.isfinite(longwave) or longwave < 0.0:
                raise ValueError(
                    "longwave_down_w_m2 must be finite and >= 0")
            object.__setattr__(self, "longwave_down_w_m2", longwave)


@dataclass(frozen=True)
class BudgetParams:
    """Surface properties with illustrative defaults."""

    albedo: float = 0.08
    emissivity: float = 0.97
    c_h: float = 1.5e-3
    c_e: float = 1.5e-3
    pressure_kpa: float = SITE_PRESSURE_KPA

    shortwave_multiplier: float = 1.0
    longwave_multiplier: float = 1.0
    longwave_bias_w_m2: float = 0.0
    cloud_longwave_factor: float = CLOUD_LONGWAVE_FACTOR_DEFAULT
    # Linear RH calibration before downstream use: rh_effective = clip(a_RH * rh + b_RH, [0, 1]).
    a_RH: float = 1.0
    b_RH: float = 0.0

    def __post_init__(self) -> None:
        for name in ("albedo", "emissivity"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
            object.__setattr__(self, name, value)
            if value in (0.0, 1.0):
                warnings.warn(
                    f"BudgetParams.{name} = {value} is a boundary value;"
                    " confirm the physical choice",
                    UserWarning,
                    stacklevel=2,
                )
        for name in ("c_h", "c_e"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be >= 0")
            object.__setattr__(self, name, value)
            if value > BULK_COEFFICIENT_HIGH:
                warnings.warn(
                    f"BudgetParams.{name} = {value:g} exceeds the typical"
                    f" open-water range (<= {BULK_COEFFICIENT_HIGH:g})",
                    UserWarning,
                    stacklevel=2,
                )
        pressure = float(self.pressure_kpa)
        if not math.isfinite(pressure):
            raise ValueError("pressure_kpa must be finite")
        if not MIN_PRESSURE_KPA <= pressure <= MAX_PRESSURE_KPA:
            raise ValueError(
                f"pressure_kpa must be in "
                f"[{MIN_PRESSURE_KPA}, {MAX_PRESSURE_KPA}]"
            )
        object.__setattr__(self, "pressure_kpa", pressure)
        for name in ("shortwave_multiplier", "longwave_multiplier"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be >= 0")
            object.__setattr__(self, name, value)
            if (value < RADIATION_MULTIPLIER_LOW
                    or value > RADIATION_MULTIPLIER_HIGH):
                warnings.warn(
                    f"BudgetParams.{name} = {value:g} is outside the "
                    f"diagnostic range "
                    f"[{RADIATION_MULTIPLIER_LOW}, "
                    f"{RADIATION_MULTIPLIER_HIGH}]",
                    UserWarning,
                    stacklevel=2,
                )
        offset = float(self.longwave_bias_w_m2)
        if not math.isfinite(offset):
            raise ValueError("longwave_bias_w_m2 must be finite")
        object.__setattr__(self, "longwave_bias_w_m2", offset)
        if abs(offset) > LONGWAVE_BIAS_SUSPECT_W_M2:
            warnings.warn(
                f"BudgetParams.longwave_bias_w_m2 = {offset:g} W/m2 is"
                f" above the diagnostic magnitude"
                f" {LONGWAVE_BIAS_SUSPECT_W_M2} W/m2",
                UserWarning,
                stacklevel=2,
            )
        cloud_factor = float(self.cloud_longwave_factor)
        if not math.isfinite(cloud_factor) or cloud_factor < 0.0:
            raise ValueError("cloud_longwave_factor must be >= 0")
        object.__setattr__(self, "cloud_longwave_factor", cloud_factor)
        a_rh = float(self.a_RH)
        if not math.isfinite(a_rh):
            raise ValueError("a_RH must be finite")
        object.__setattr__(self, "a_RH", a_rh)
        b_rh = float(self.b_RH)
        if not math.isfinite(b_rh):
            raise ValueError("b_RH must be finite")
        object.__setattr__(self, "b_RH", b_rh)


def flux_at(t_water_c: float, met: MetState,
            params: BudgetParams | None = None) -> dict[str, float]:
    """Component fluxes (W/m2, positive into water) at one water temperature."""
    params = params or BudgetParams()
    t_c = _temperature_c(t_water_c, "t_water_c")
    t_k = t_c + 273.15

    rh_effective = min(1.0, max(0.0, params.a_RH * met.rh + params.b_RH))
    ea = rh_effective * es_kpa(met.air_c)
    es_w = es_kpa(t_c)
    rho = _rho_air_kg_m3(met.air_c, ea, params.pressure_kpa)
    q_air = _specific_humidity(ea, params.pressure_kpa)
    q_sat = _specific_humidity(es_w, params.pressure_kpa)
    transfer_wind = _transfer_wind_mps(met.wind_mps)

    shortwave = ((1.0 - params.albedo) * params.shortwave_multiplier
                 * met.shortwave_w_m2)

    if met.longwave_down_w_m2 is None:
        longwave_in = (
            _lw_in_w_m2(met.air_c, rh_effective, met.cloud,
                        cloud_factor=params.cloud_longwave_factor)
            * params.longwave_multiplier
            + params.longwave_bias_w_m2)
        if longwave_in < 0.0:
            raise ValueError(
                "incoming longwave is negative after corrections")
    else:
        longwave_in = met.longwave_down_w_m2
    longwave_out = params.emissivity * SIGMA_W_M2_K4 * t_k ** 4
    longwave = longwave_in - longwave_out

    sensible = (rho * CP_AIR_J_KG_K * params.c_h * transfer_wind
                * (met.air_c - t_c))
    latent = (rho * L_VAPOR_J_KG * params.c_e * transfer_wind
              * (q_air - q_sat))
    net = shortwave + longwave + sensible + latent
    for name, value in (("shortwave", shortwave), ("longwave", longwave),
                        ("sensible", sensible), ("latent", latent),
                        ("net", net)):
        finite(f"{name} flux", value)

    return {
        "shortwave": shortwave,
        "longwave_in": longwave_in,
        "longwave_out": longwave_out,
        "longwave": longwave,
        "sensible": sensible,
        "latent": latent,
        "net": net,
        "air_vapor_pressure_kpa": ea,
        "water_saturation_vapor_pressure_kpa": es_w,
        "air_specific_humidity": q_air,
        "water_saturation_specific_humidity": q_sat,
        "air_density_kg_m3": rho,
        "transfer_wind_mps": transfer_wind,
    }


def linearized(t_water_c: float, met: MetState,
               params: BudgetParams | None = None
               ) -> tuple[float, float]:
    """(F0, dF/dT) of net flux at t_water_c, analytic derivative."""
    params = params or BudgetParams()
    t_c = _temperature_c(t_water_c, "t_water_c")
    parts = flux_at(t_c, met, params)
    t_k = t_c + 273.15
    rho = parts["air_density_kg_m3"]
    transfer_wind = parts["transfer_wind_mps"]
    dq_sat = (_dq_de(params.pressure_kpa,
                     parts["water_saturation_vapor_pressure_kpa"])
              * _des_dt(t_c))
    slope = (-4.0 * params.emissivity * SIGMA_W_M2_K4 * t_k ** 3
             - rho * CP_AIR_J_KG_K * params.c_h * transfer_wind
             - rho * L_VAPOR_J_KG * params.c_e * transfer_wind * dq_sat)
    return parts["net"], finite("flux slope", slope)


def compare_sensible_latent(
    water_c: float, met: MetState, params: BudgetParams | None = None, *,
    observed_sensible_w_m2: float | None = None,
    observed_latent_w_m2: float | None = None,
) -> dict[str, Any]:
    """Compare modeled sensible and latent fluxes against an observation pair."""
    modeled = flux_at(water_c, met, params)
    rows: list[dict[str, Any]] = []
    observations = (
        ("sensible", observed_sensible_w_m2),
        ("latent", observed_latent_w_m2),
    )
    for name, obs in observations:
        row: dict[str, Any] = {
            "channel": name,
            "modeled_w_m2": float(modeled[name]),
            "observed_w_m2": None if obs is None else float(obs),
        }
        if obs is None:
            row["status"] = "no_observation"
            row["residual_w_m2"] = None
        else:
            if not math.isfinite(float(obs)):
                raise ValueError(f"{name} observation must be finite")
            row["status"] = "ok"
            row["residual_w_m2"] = row["modeled_w_m2"] - row["observed_w_m2"]
        rows.append(row)
    return {
        "sign_convention": "positive_into_water",
        "rows": rows,
        "wind_floor_mps": WIND_FLOOR_MPS,
    }


def describe_surface_model(params: BudgetParams | None = None, *,
                           status_overrides: dict[str, str] | None = None
                           ) -> dict:
    """Effective surface model metadata to store beside a replay."""
    params = params or BudgetParams()
    status = dict(PARAMETER_STATUS)
    if params.pressure_kpa != SITE_PRESSURE_KPA:
        status["pressure_kpa"] = "authored_override"
    status.update(status_overrides or {})
    return {
        "method": "explicit_budget",
        "sign_convention": "positive_into_water",
        "parameters": asdict(params),
        "parameter_status": status,
        "not_identified_independently": ["c_h", "c_e"],
        "wind_floor_mps": WIND_FLOOR_MPS,
        "wind_floor_applies_to": "transfer_calculation_only",
    }


BUDGET_PARAM_KEYS = {
    "albedo", "emissivity", "c_h", "c_e", "pressure_kpa",
    "shortwave_multiplier", "longwave_multiplier",
    "longwave_bias_w_m2", "cloud_longwave_factor",
    "a_RH", "b_RH",
}


def _series_dict(series: Any) -> dict:
    return {"times_s": list(series.times_s),
            "values": list(series.values)}


def spec_from_series(rh: Any, wind_mps: Any, shortwave_w_m2: Any,
                     cloud: Any, params: dict | BudgetParams | None = None,
                     *, duration_s: float | None = None) -> dict:
    """Build a River-config surface_budget mapping from Series-ish inputs."""
    from yellowstone_python.river.river_transport import Series

    parsed = {
        "rh": Series.parse(rh),
        "wind_mps": Series.parse(wind_mps),
        "shortwave_w_m2": Series.parse(shortwave_w_m2),
        "cloud": Series.parse(cloud),
    }
    if duration_s is not None:
        duration_s = finite("duration_s", duration_s)
        if duration_s < 0.0:
            raise ValueError("duration_s must be >= 0")
    for name, series in parsed.items():
        times = list(series.times_s)
        if not times:
            raise ValueError(f"{name} series is empty")
        if times[0] != 0.0:
            raise ValueError(f"{name} series must begin at time zero")
        if (duration_s is not None and len(times) > 1
                and times[-1] < duration_s):
            raise ValueError(
                f"{name} series ends at {times[-1]} s, before the "
                f"replay duration {duration_s} s")

    if isinstance(params, BudgetParams):
        params_dict = asdict(params)
    else:
        params_dict = dict(params or {})
        unknown = set(params_dict) - BUDGET_PARAM_KEYS
        if unknown:
            raise ValueError(
                f"spec_from_series: unknown params keys {sorted(unknown)}"
            )
    spec = {name: _series_dict(series) for name, series in parsed.items()}
    spec["params"] = params_dict
    return spec


@lru_cache(maxsize=128)
def _array_met_constants(met: MetState, params: BudgetParams):
    """Cache temperature-independent flux terms for immutable meteorology."""
    rh = min(1.0, max(0.0, params.a_RH * met.rh + params.b_RH))
    ea = rh * es_kpa(met.air_c)
    rho = _rho_air_kg_m3(met.air_c, ea, params.pressure_kpa)
    wind = _transfer_wind_mps(met.wind_mps)
    q_air = _specific_humidity(ea, params.pressure_kpa)
    lw_in = met.longwave_down_w_m2
    if lw_in is None:
        lw_in = (_lw_in_w_m2(met.air_c, rh, met.cloud,
                             cloud_factor=params.cloud_longwave_factor)
                 * params.longwave_multiplier + params.longwave_bias_w_m2)
    if lw_in < 0.0:
        raise ValueError("incoming longwave is negative after corrections")
    return ea, rho, wind, q_air, lw_in


def flux_array(t_water_c, met: MetState, params: BudgetParams | None = None, *,
               shortwave_multiplier=1.0) -> dict:
    """Evaluate surface fluxes over a NumPy cell array in W/m2."""
    import numpy as np
    params = params or BudgetParams()
    t = np.asarray(t_water_c, dtype=float)
    if np.any(~np.isfinite(t)) or np.any((t < MIN_THERMODYNAMIC_C) | (t > MAX_THERMODYNAMIC_C)):
        raise ValueError("t_water_c must be finite and within thermodynamic bounds")
    multipliers = np.broadcast_to(np.asarray(shortwave_multiplier, dtype=float), t.shape)
    if np.any(~np.isfinite(multipliers)) or np.any(multipliers < 0.0):
        raise ValueError("shortwave_multiplier must be finite and nonnegative")
    ea, rho, wind, q_air, lw_in = _array_met_constants(met, params)
    # Magnus evaluates the river-temperature branch; high temperatures use the reference blend.
    es = 0.61094 * np.exp(17.625 * t / (t + 243.04))
    high = t > BLEND_T_LOW
    if np.any(high):
        es[high] = np.asarray([es_kpa(float(value)) for value in t[high]])
    if np.any(es >= params.pressure_kpa):
        raise ValueError("vapor pressure is incompatible with total pressure")
    q_sat = 0.622 * es / (params.pressure_kpa - 0.378 * es)
    sw = (1.0 - params.albedo) * params.shortwave_multiplier * met.shortwave_w_m2 * multipliers
    lw_out = params.emissivity * SIGMA_W_M2_K4 * (t + 273.15) ** 4
    sensible = rho * CP_AIR_J_KG_K * params.c_h * wind * (met.air_c - t)
    latent = rho * L_VAPOR_J_KG * params.c_e * wind * (q_air - q_sat)
    parts = {"shortwave": sw, "longwave_in": np.full_like(t, lw_in),
             "longwave_out": lw_out, "longwave": lw_in - lw_out,
             "sensible": sensible, "latent": latent,
             "air_vapor_pressure_kpa": np.full_like(t, ea),
             "water_saturation_vapor_pressure_kpa": es,
             "air_specific_humidity": np.full_like(t, q_air),
             "water_saturation_specific_humidity": q_sat,
             "air_density_kg_m3": np.full_like(t, rho),
             "transfer_wind_mps": np.full_like(t, wind)}
    parts["net"] = sw + parts["longwave"] + sensible + latent
    if any(np.any(~np.isfinite(value)) for value in parts.values()):
        raise ValueError("surface flux must be finite")
    return parts


def linearized_array(t_water_c, met: MetState, params: BudgetParams | None = None, *,
                     shortwave_multiplier=1.0):
    """Return cell-array net flux and its temperature derivative."""
    import numpy as np
    params = params or BudgetParams()
    t = np.asarray(t_water_c, dtype=float)
    parts = flux_array(t, met, params, shortwave_multiplier=shortwave_multiplier)
    es = parts["water_saturation_vapor_pressure_kpa"]
    derivative = es * 17.625 * 243.04 / (t + 243.04) ** 2
    high = t > BLEND_T_LOW
    if np.any(high):
        derivative[high] = np.asarray([_des_dt(float(value)) for value in t[high]])
    dq = 0.622 * params.pressure_kpa / (params.pressure_kpa - 0.378 * es) ** 2 * derivative
    rho = parts["air_density_kg_m3"]
    wind = parts["transfer_wind_mps"]
    slope = (-4.0 * params.emissivity * SIGMA_W_M2_K4 * (t + 273.15) ** 3
             - rho * CP_AIR_J_KG_K * params.c_h * wind
             - rho * L_VAPOR_J_KG * params.c_e * wind * dq)
    return parts["net"], slope
