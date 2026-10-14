"""River periphyton compartment: biomass driven by light, temperature and nutrients, with grazing."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite

import math
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA = "yellowstone.periphyton.v1"

PHOTOSYNTHETIC_QUOTIENT = 1.2
O2_PER_C_MASS = (32.0 / 12.0) * PHOTOSYNTHETIC_QUOTIENT
PQ_SOURCE = (
    "authored_representative_freshwater_photosynthetic_quotient of 1.2; "
    "common assumption in aquatic metabolism studies and Standard Methods"
)

EPPLEY_A_PER_C = 0.0633
EPPLEY_SOURCE = (
    "Eppley (1972), Temperature and phytoplankton growth in the sea, "
    "Fishery Bulletin 70(4), 1063-1085; Q10 reported as 1.88 so ln(Q10)/10 "
    "equals 0.0633 1/degC"
)

LIGHT_SOURCE = (
    "authored_platt_jassby_tanh_form; Jassby and Platt (1976), "
    "Limnology and Oceanography 21, 540-547, present a hyperbolic "
    "tangent light response for marine phytoplankton that is widely "
    "adopted for periphyton"
)

PAR_FRACTION_DEFAULT = 0.45
PAR_SOURCE = (
    "authored_representative_PAR_fraction of 0.45 of global shortwave; "
    "commonly adopted convention in aquatic primary production modeling"
)

I_K_DEFAULT_W_M2 = 100.0
I_K_SOURCE = (
    "authored_representative_half_saturation_PAR for benthic stream "
    "biofilm; the published range runs from a few W/m2 for deep-shade "
    "communities to a few hundred W/m2 for sun-adapted ones"
)

P_MAX_SPECIFIC_PER_DAY_DEFAULT = 1.2
P_MAX_SOURCE = (
    "authored_representative_maximum_specific_growth of 1.2 1/d at 20 "
    "degC for benthic biofilm; order-of-magnitude value common in "
    "stream-ecosystem models until site measurements exist"
)




@dataclass(frozen=True)
class PeriphytonParams:
    """Parameters for the periphyton compartment with cited defaults."""

    p_max_specific_per_day: float = P_MAX_SPECIFIC_PER_DAY_DEFAULT
    i_k_w_m2: float = I_K_DEFAULT_W_M2
    eppley_a_per_c: float = EPPLEY_A_PER_C
    reference_temp_c: float = 20.0
    respiration_rate_per_day: float = 0.15
    grazing_rate_per_day: float = 0.1
    nutrient_factor: float = 0.6
    biomass_saturation_mg_c_m2: float = 10000.0
    min_biomass_mg_c_m2: float = 1.0
    par_fraction: float = PAR_FRACTION_DEFAULT
    status: str = "illustrative"
    nutrient_source: str = "authored_until_measured"

    def __post_init__(self) -> None:
        for name in ("p_max_specific_per_day", "i_k_w_m2",
                     "respiration_rate_per_day", "grazing_rate_per_day",
                     "biomass_saturation_mg_c_m2",
                     "min_biomass_mg_c_m2"):
            value = _finite(name, getattr(self, name), minimum=0.0)
            object.__setattr__(self, name, value)
        object.__setattr__(
            self, "eppley_a_per_c",
            _finite("eppley_a_per_c", self.eppley_a_per_c))
        object.__setattr__(
            self, "reference_temp_c",
            _finite("reference_temp_c", self.reference_temp_c))
        for name in ("nutrient_factor", "par_fraction"):
            value = _finite(name, getattr(self, name), minimum=0.0)
            if value > 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
            object.__setattr__(self, name, value)
        if self.i_k_w_m2 <= 0.0:
            raise ValueError("i_k_w_m2 must be positive")
        if self.biomass_saturation_mg_c_m2 <= 0.0:
            raise ValueError("biomass_saturation_mg_c_m2 must be positive")


def temperature_factor(temp_c: float, params: PeriphytonParams) -> float:
    """Eppley exponential temperature scaling."""
    t = _finite("temp_c", temp_c)
    return math.exp(params.eppley_a_per_c * (t - params.reference_temp_c))


def light_factor(shortwave_w_m2: float, params: PeriphytonParams) -> float:
    """Hyperbolic tangent light saturation on PAR, bounded in [0, 1]."""
    swin = _finite("shortwave_w_m2", shortwave_w_m2, minimum=0.0)
    i_par = params.par_fraction * swin
    return math.tanh(i_par / params.i_k_w_m2)


def self_shading_factor(biomass_mg_c_m2: float,
                        params: PeriphytonParams) -> float:
    """Saturating self-shading factor K / (B + K)."""
    b = _finite("biomass_mg_c_m2", biomass_mg_c_m2, minimum=0.0)
    k = params.biomass_saturation_mg_c_m2
    return k / (b + k)


def gpp_mg_c_m2_s(biomass_mg_c_m2: float, shortwave_w_m2: float,
                  temp_c: float, params: PeriphytonParams) -> float:
    """Gross primary production in mg C per m2 per second."""
    b = _finite("biomass_mg_c_m2", biomass_mg_c_m2, minimum=0.0)
    p_per_s = params.p_max_specific_per_day / 86400.0
    return (p_per_s * b * light_factor(shortwave_w_m2, params)
            * temperature_factor(temp_c, params)
            * params.nutrient_factor
            * self_shading_factor(b, params))


def respiration_mg_c_m2_s(biomass_mg_c_m2: float, temp_c: float,
                          params: PeriphytonParams) -> float:
    """Autotrophic respiration in mg C per m2 per second."""
    b = _finite("biomass_mg_c_m2", biomass_mg_c_m2, minimum=0.0)
    r_per_s = params.respiration_rate_per_day / 86400.0
    return r_per_s * b * temperature_factor(temp_c, params)


def grazing_loss_mg_c_m2_s(biomass_mg_c_m2: float, grazer_density: float,
                           params: PeriphytonParams) -> float:
    """First-order grazing loss g * grazer_density * B."""
    b = _finite("biomass_mg_c_m2", biomass_mg_c_m2, minimum=0.0)
    density = _finite("grazer_density", grazer_density, minimum=0.0)
    g_per_s = params.grazing_rate_per_day / 86400.0
    return g_per_s * density * b


def net_o2_production_mg_o2_m2_s(biomass_mg_c_m2: float,
                                 shortwave_w_m2: float, temp_c: float,
                                 params: PeriphytonParams
                                 ) -> dict[str, float]:
    """Oxygen mass fluxes from the carbon-based photosynthesis and respiration."""
    gpp_c = gpp_mg_c_m2_s(biomass_mg_c_m2, shortwave_w_m2, temp_c, params)
    r_c = respiration_mg_c_m2_s(biomass_mg_c_m2, temp_c, params)
    return {
        "gpp_mg_o2_m2_s": gpp_c * O2_PER_C_MASS,
        "respiration_mg_o2_m2_s": r_c * O2_PER_C_MASS,
        "net_mg_o2_m2_s": (gpp_c - r_c) * O2_PER_C_MASS,
    }


def step_biomass(biomass_mg_c_m2: float, shortwave_w_m2: float, temp_c: float,
                 grazer_density: float, dt_s: float,
                 params: PeriphytonParams) -> dict[str, float]:
    """Explicit Euler step of the biomass budget by dt_s seconds."""
    dt = _finite("dt_s", dt_s, minimum=0.0)
    if dt <= 0.0:
        raise ValueError("dt_s must be positive")
    b0 = _finite("biomass_mg_c_m2", biomass_mg_c_m2, minimum=0.0)
    gpp = gpp_mg_c_m2_s(b0, shortwave_w_m2, temp_c, params)
    resp = respiration_mg_c_m2_s(b0, temp_c, params)
    graze = grazing_loss_mg_c_m2_s(b0, grazer_density, params)
    b1 = b0 + dt * (gpp - resp - graze)
    if b1 < params.min_biomass_mg_c_m2:
        b1 = params.min_biomass_mg_c_m2
    return {
        "biomass_mg_c_m2": b1,
        "gpp_mg_c_m2_s": gpp,
        "respiration_mg_c_m2_s": resp,
        "grazing_mg_c_m2_s": graze,
        "delta_biomass_mg_c_m2": b1 - b0,
    }


def describe_model(params: PeriphytonParams | None = None) -> dict[str, Any]:
    """Model metadata and source citations suitable for a sidecar JSON."""
    params = params or PeriphytonParams()
    return {
        "schema": SCHEMA,
        "status": params.status,
        "parameters": asdict(params),
        "sources": {
            "light": LIGHT_SOURCE,
            "temperature": EPPLEY_SOURCE,
            "par_fraction": PAR_SOURCE,
            "p_max": P_MAX_SOURCE,
            "i_k": I_K_SOURCE,
            "photosynthetic_quotient": PQ_SOURCE,
            "nutrient_factor": params.nutrient_source,
        },
    }
