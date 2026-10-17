"""Downwind microclimate adjustment from hydrothermal plume heat and vapor, with fog and rime."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite, nonnegative as _nonnegative

import math

from yellowstone_python.common.site import SITE_PRESSURE_KPA
from yellowstone_python.atmosphere.microclimate import _es_kpa, dewpoint_c
from yellowstone_python.river.surface_flux import WIND_FLOOR_MPS

SCHEMA = "yellowstone.steam_microclimate.v1"
STATUS = "transferred_structure_authored_rates"

CP_AIR_J_KG_K = 1005.0
L_VAPOR_J_KG = 2.45e6
R_DRY_J_KG_K = 287.058

# Authored bulk-transfer coefficients at 10 m match river.surface_flux defaults.
BULK_TRANSFER_C_H = 1.5e-3
BULK_TRANSFER_C_E = 1.5e-3
BULK_TRANSFER_REFERENCE_HEIGHT_M = 10.0
BULK_TRANSFER_STATUS = "authored_matches_replay_surface_flux_defaults"

# h_i = A*z0*(fetch/z0)**B uses authored A and B; diffusion-model context: Garratt (1990).
IBL_COEFFICIENT_A = 0.4
IBL_COEFFICIENT_A_STATUS = "authored"
IBL_EXPONENT_B = 0.8
IBL_EXPONENT_B_STATUS = "authored_from_diffusion_model_literature"
ROUGHNESS_LENGTH_M = 0.001
ROUGHNESS_STATUS = "authored_general_literature_rough_water_surface"

# The diffusion-type boundary-layer model raises for fetch outside these authored bounds.
FETCH_MIN_M = 10.0
FETCH_MAX_M = 100_000.0
FETCH_RANGE_STATUS = "authored_from_review_coverage_meter_to_hundred_kilometer_scales"

AIR_DENSITY_SITE_KG_M3 = (SITE_PRESSURE_KPA * 1000.0
                           / (R_DRY_J_KG_K * 283.15))

FETCH_SOURCES = [
    "Stull 1988 An Introduction to Boundary Layer Meteorology, "
    "chapter 10 (internal boundary layer growth with fetch over a "
    "surface change)",
    "Garratt 1990 Boundary-Layer Meteorology 50:171 (power-law "
    "internal boundary layer growth h_i = 0.4 * z0 * (fetch/z0)**0.8 "
    "over a surface change) doi:10.1007/BF00120524",
]

FOG_SOURCES = [
    "Pruppacher and Klett 1997 Microphysics of Clouds and "
    "Precipitation (radiation and advection fog form when air cools "
    "to the dew point)",
    "American Meteorological Society Glossary of Meteorology, entry "
    "'rime' (rime deposits on cold surfaces when supercooled fog "
    "droplets freeze on contact)",
]


def internal_boundary_layer_m(fetch_m: float,
                              roughness_length_m: float = ROUGHNESS_LENGTH_M
                              ) -> float:
    """Diffusion-type internal boundary layer depth as reviewed by Garratt (1990) BLM 50:171."""
    fetch = _finite("fetch_m", fetch_m)
    if fetch < FETCH_MIN_M or fetch > FETCH_MAX_M:
        raise ValueError(
            f"fetch_m {fetch_m} outside the authored validity range "
            f"[{FETCH_MIN_M}, {FETCH_MAX_M}] m for the diffusion-type "
            f"internal boundary layer power law")
    z0 = _finite("roughness_length_m", roughness_length_m)
    if z0 <= 0.0:
        raise ValueError("roughness_length_m must be > 0")
    return float(IBL_COEFFICIENT_A * z0 * (fetch / z0) ** IBL_EXPONENT_B)






def _unit(name: str, value) -> float:
    result = _finite(name, value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return result


def plume_sensible_flux_w_m2(surface_c: float, air_c: float,
                             wind_mps: float,
                             c_h: float = BULK_TRANSFER_C_H,
                             pressure_kpa: float = SITE_PRESSURE_KPA
                             ) -> float:
    """Bulk-aerodynamic sensible flux from a hot water surface into the air (W/m2)."""
    surface_c = _finite("surface_c", surface_c)
    air_c = _finite("air_c", air_c)
    wind = max(WIND_FLOOR_MPS, _nonnegative("wind_mps", wind_mps))
    pressure = _finite("pressure_kpa", pressure_kpa)
    rho = pressure * 1000.0 / (R_DRY_J_KG_K * (air_c + 273.15))
    return rho * CP_AIR_J_KG_K * c_h * wind * (surface_c - air_c)


def plume_latent_flux_w_m2(surface_c: float, air_c: float, rh: float,
                           wind_mps: float,
                           c_e: float = BULK_TRANSFER_C_E,
                           pressure_kpa: float = SITE_PRESSURE_KPA
                           ) -> float:
    """Bulk-aerodynamic latent flux from the water surface into the air (W/m2)."""
    surface_c = _finite("surface_c", surface_c)
    air_c = _finite("air_c", air_c)
    rh = _unit("rh", rh)
    wind = max(WIND_FLOOR_MPS, _nonnegative("wind_mps", wind_mps))
    pressure = _finite("pressure_kpa", pressure_kpa)
    es_surf = _es_kpa(surface_c)
    es_air = _es_kpa(air_c)
    ea = rh * es_air
    rho = pressure * 1000.0 / (R_DRY_J_KG_K * (air_c + 273.15))
    q_surf = 0.622 * es_surf / max(1e-9, pressure - 0.378 * es_surf)
    q_air = 0.622 * ea / max(1e-9, pressure - 0.378 * ea)
    return rho * L_VAPOR_J_KG * c_e * wind * (q_surf - q_air)


def downwind_adjustment(air_c: float, rh: float, wind_mps: float,
                        source_area_m2: float,
                        plume_sensible_w_m2: float,
                        plume_latent_w_m2: float,
                        pressure_kpa: float = SITE_PRESSURE_KPA,
                        roughness_length_m: float = ROUGHNESS_LENGTH_M
                        ) -> dict:
    """Downwind air-temperature and humidity adjustment from a plume source."""
    air_c = _finite("air_c", air_c)
    rh = _unit("rh", rh)
    wind = max(WIND_FLOOR_MPS, _nonnegative("wind_mps", wind_mps))
    source_area_m2 = _nonnegative("source_area_m2", source_area_m2)
    pressure = _finite("pressure_kpa", pressure_kpa)
    rho = pressure * 1000.0 / (R_DRY_J_KG_K * (air_c + 273.15))
    fetch_length = math.sqrt(max(0.0, source_area_m2))
    residence_s = fetch_length / wind if wind > 0.0 else 0.0
    ibl_m = internal_boundary_layer_m(fetch_length, roughness_length_m)
    sensible_increment_j_m3 = (float(plume_sensible_w_m2) * residence_s
                                / ibl_m) if residence_s > 0 else 0.0
    latent_increment_j_m3 = (float(plume_latent_w_m2) * residence_s
                              / ibl_m) if residence_s > 0 else 0.0
    delta_t = sensible_increment_j_m3 / (rho * CP_AIR_J_KG_K)
    delta_q = latent_increment_j_m3 / (rho * L_VAPOR_J_KG)
    es_air = _es_kpa(air_c)
    ea = rh * es_air
    q_air = 0.622 * ea / max(1e-9, pressure - 0.378 * ea)
    q_new = max(0.0, q_air + delta_q)
    t_new = air_c + delta_t
    ea_new = pressure * q_new / (0.622 + 0.378 * q_new)
    es_new = _es_kpa(t_new)
    rh_new = min(1.0, max(0.0, ea_new / es_new)) if es_new > 0 else 0.0
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "fetch_length_m": fetch_length,
        "residence_s": residence_s,
        "internal_boundary_layer_m": ibl_m,
        "roughness_length_m": float(roughness_length_m),
        "delta_air_c": delta_t,
        "delta_specific_humidity": delta_q,
        "downwind_air_c": t_new,
        "downwind_rh": rh_new,
        "upwind_air_c": air_c,
        "upwind_rh": rh,
        "pressure_kpa": pressure,
        "sensible_flux_w_m2": float(plume_sensible_w_m2),
        "latent_flux_w_m2": float(plume_latent_w_m2),
        "sources": list(FETCH_SOURCES),
    }


def plume_microclimate_adjustment(air_c: float, rh: float, wind_mps: float,
                                  pool_surface_c: float,
                                  pool_area_m2: float,
                                  outflow_surface_c: float | None = None,
                                  outflow_area_m2: float = 0.0,
                                  pressure_kpa: float = SITE_PRESSURE_KPA,
                                  roughness_length_m: float = ROUGHNESS_LENGTH_M,
                                  latent_flux_outflow_w_m2: float | None = None
                                  ) -> dict:
    """Combined pool and outflow plume adjustment on downwind air temperature and humidity."""
    pool_q_s = plume_sensible_flux_w_m2(pool_surface_c, air_c, wind_mps,
                                         pressure_kpa=pressure_kpa)
    pool_q_e = plume_latent_flux_w_m2(pool_surface_c, air_c, rh, wind_mps,
                                       pressure_kpa=pressure_kpa)
    outflow_q_s = 0.0
    outflow_q_e = 0.0
    if outflow_area_m2 > 0.0 and outflow_surface_c is not None:
        outflow_q_s = plume_sensible_flux_w_m2(outflow_surface_c, air_c,
                                                wind_mps,
                                                pressure_kpa=pressure_kpa)
        if latent_flux_outflow_w_m2 is None:
            outflow_q_e = plume_latent_flux_w_m2(outflow_surface_c, air_c,
                                                   rh, wind_mps,
                                                   pressure_kpa=pressure_kpa)
        else:
            outflow_q_e = _finite("latent_flux_outflow_w_m2",
                                   latent_flux_outflow_w_m2)
    total_area = pool_area_m2 + outflow_area_m2
    if total_area <= 0.0:
        raise ValueError("total plume area must be > 0")
    area_weighted_sensible = (
        pool_q_s * pool_area_m2 + outflow_q_s * outflow_area_m2) / total_area
    area_weighted_latent = (
        pool_q_e * pool_area_m2 + outflow_q_e * outflow_area_m2) / total_area
    adjust = downwind_adjustment(
        air_c=air_c, rh=rh, wind_mps=wind_mps,
        source_area_m2=total_area,
        plume_sensible_w_m2=area_weighted_sensible,
        plume_latent_w_m2=area_weighted_latent,
        pressure_kpa=pressure_kpa,
        roughness_length_m=roughness_length_m)
    adjust["components"] = {
        "pool_area_m2": pool_area_m2,
        "pool_sensible_w_m2": pool_q_s,
        "pool_latent_w_m2": pool_q_e,
        "outflow_area_m2": outflow_area_m2,
        "outflow_sensible_w_m2": outflow_q_s,
        "outflow_latent_w_m2": outflow_q_e,
        "latent_flux_outflow_source": (
            "override" if latent_flux_outflow_w_m2 is not None
            else "bulk_aerodynamic"),
    }
    return adjust


def fog_present(air_c: float, rh: float) -> bool:
    """Fog is present when the air parcel is at or above saturation.
Takes the downwind air temperature and humidity."""
    air_c = _finite("air_c", air_c)
    rh = _unit("rh", rh)
    if rh >= 0.999:
        return True
    dp = dewpoint_c(air_c, max(rh, 1e-9))
    return (air_c - dp) <= 1e-6


def rime_present(air_c: float, rh: float) -> bool:
    """Rime forms when fog is present and air temperature is below freezing."""
    air_c = _finite("air_c", air_c)
    return (air_c < 0.0) and fog_present(air_c, rh)


__all__ = [
    "AIR_DENSITY_SITE_KG_M3",
    "BULK_TRANSFER_C_E",
    "BULK_TRANSFER_C_H",
    "BULK_TRANSFER_REFERENCE_HEIGHT_M",
    "BULK_TRANSFER_STATUS",
    "FETCH_MAX_M",
    "FETCH_MIN_M",
    "FETCH_RANGE_STATUS",
    "FETCH_SOURCES",
    "FOG_SOURCES",
    "IBL_COEFFICIENT_A",
    "IBL_COEFFICIENT_A_STATUS",
    "IBL_EXPONENT_B",
    "IBL_EXPONENT_B_STATUS",
    "ROUGHNESS_LENGTH_M",
    "ROUGHNESS_STATUS",
    "SCHEMA",
    "STATUS",
    "downwind_adjustment",
    "fog_present",
    "internal_boundary_layer_m",
    "plume_latent_flux_w_m2",
    "plume_microclimate_adjustment",
    "plume_sensible_flux_w_m2",
    "rime_present",
]
