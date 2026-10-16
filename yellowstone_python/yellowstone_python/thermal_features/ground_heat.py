"""Geothermal ground heat flux and near-surface soil temperature fields."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite, positive as _positive, nonnegative as _nonnegative

import math

SCHEMA = "yellowstone.ground_heat.v1"

GHF_BACKGROUND_W_M2 = 0.30
GHF_APRON_W_M2 = 120.0
GHF_POOL_W_M2 = 500.0
GHF_SOURCE = (
    "Authored within cited ranges. Morgan et al. (1977) J. Geophys. Res. "
    "82 pages 3719-3732 doi:10.1029/JB082i026p03719 reports 100 to 300 "
    "mW/m^2 outside the Yellowstone caldera and 600 to 700 mW/m^2 and "
    "greater inside the caldera from lakebed probes. Hurwitz and "
    "Lowenstern (2014) Rev. Geophys. 52(3) 375-411 "
    "doi:10.1002/2014RG000452 reviews the caldera total heat budget. "
    "Vaughan et al. (2012) J. Volcanol. Geotherm. Res. 233-234 pages 72-89 "
    "doi:10.1016/j.jvolgeores.2012.04.022 estimates total radiant GHF of "
    "~2.0 GW across basin thermal areas from ASTER infrared imagery.")

SOIL_K_W_M_K = 1.3
SOIL_K_SOURCE = (
    "Authored conductivity 1.3 W/m/K within a general 1 to 2 W/m/K range "
    "for silicic rocks and shallow sinter soils; a site-specific "
    "measurement or primary-source value is unverified.")

L_F_J_KG = 334000.0
RHO_WATER_KG_M3 = 1000.0
SECONDS_PER_DAY = 86400.0

LODGEPOLE_SOIL_DIEOFF_C = 35.0
LODGEPOLE_SOIL_DIEOFF_DEPTH_CM = 10.0
LODGEPOLE_SOIL_DIEOFF_SOURCE = (
    "Authored 35 C root-zone threshold; species-specific support is "
    "unverified. The qualitative USGS observation "
    "that lodgepole conifers near thermal ground show normal growth "
    "below about 200 heat-flow units and stunt at 250 to 350 is the "
    "general support; the 35 degC gate is an authored conservative "
    "placeholder.")

SOIL_T_REFERENCE_DEPTH_M = 0.10

# Boiling point of water at Yellowstone-site atmospheric pressure.
BOILING_T_REFERENCE_SITE_M = 2200.0
BOILING_T_P0_KPA = 101.325
BOILING_T_T0_K = 373.15
BOILING_T_L_V_J_PER_MOL = 40660.0
BOILING_T_R_J_PER_MOL_K = 8.314
BOILING_T_SOURCE = (
    "Pressure from Allen et al. (1998) FAO-56 Eq 7 (elevation to pressure "
    "lapse). Boiling point from the Clausius-Clapeyron relation with "
    "L_v = 40660 J/mol and R = 8.314 J/mol/K, standard values "
    "from the CRC Handbook of Chemistry and Physics.")








def heat_flux_at(x: float, z: float, shells: list,
                 background_w_m2: float = GHF_BACKGROUND_W_M2,
                 apron_w_m2: float = GHF_APRON_W_M2,
                 pool_w_m2: float = GHF_POOL_W_M2) -> float:
    """Point sample of geothermal ground heat flux (W/m^2).
Pool water: pool_w_m2. Buffered apron (in_apron): apron_w_m2. Else background."""
    from yellowstone_python.thermal_features.pool_crust import in_apron, in_water
    x = _finite("x", x)
    z = _finite("z", z)
    bg = _nonnegative("background_w_m2", background_w_m2)
    apron = _nonnegative("apron_w_m2", apron_w_m2)
    pool = _nonnegative("pool_w_m2", pool_w_m2)
    for s in shells or []:
        if in_water(x, z, s):
            return pool
    for s in shells or []:
        if in_apron(x, z, s):
            return apron
    return bg


def heat_flux_mask_field(shells: list, size: int,
                         background_w_m2: float = GHF_BACKGROUND_W_M2,
                         apron_w_m2: float = GHF_APRON_W_M2,
                         pool_w_m2: float = GHF_POOL_W_M2) -> dict:
    """Basin-scale heat flux raster keyed to the apron mask grid.
Returns a sidecar dict (schema, grid, values, units, status, provenance)."""
    from yellowstone_python.thermal_features.pool_crust import HALF
    if isinstance(size, bool) or not isinstance(size, int) or size < 2:
        raise ValueError("size must be an integer >= 2")
    bg = _nonnegative("background_w_m2", background_w_m2)
    apron = _nonnegative("apron_w_m2", apron_w_m2)
    pool = _nonnegative("pool_w_m2", pool_w_m2)
    # Build the field by sampling each cell center through heat_flux_at.
    cell = (2.0 * HALF) / size
    values: list[list[float]] = []
    for row in range(size):
        z = -HALF + (row + 0.5) * cell
        row_vals: list[float] = []
        for col in range(size):
            x = -HALF + (col + 0.5) * cell
            row_vals.append(heat_flux_at(x, z, shells, bg, apron, pool))
        values.append(row_vals)
    return {
        "schema": SCHEMA,
        "grid": {"nx": size, "nz": size, "cell_m": cell,
                 "origin_xz_m": [-HALF, -HALF], "row_order": "south_increases"},
        "values_w_m2": values,
        "units": "W/m^2",
        "status": "authored",
        "spatial_pattern": "authored_from_apron_mask",
        "magnitudes_source": GHF_SOURCE,
        "parameters": {
            "background_w_m2": bg,
            "apron_w_m2": apron,
            "pool_w_m2": pool,
        },
    }


def atmospheric_pressure_kpa_from_elevation(elevation_m: float) -> float:
    """FAO-56 Eq 7 (Allen (1998) p 31): pressure from elevation."""
    z = _finite("elevation_m", elevation_m)
    return 101.3 * ((293.0 - 0.0065 * z) / 293.0) ** 5.26


def boiling_point_c(elevation_m: float = BOILING_T_REFERENCE_SITE_M) -> float:
    """Boiling point of water at the local atmospheric pressure.
Clausius-Clapeyron inversion of T0 and P0 to P(z)."""
    p_kpa = atmospheric_pressure_kpa_from_elevation(elevation_m)
    ln_ratio = math.log(p_kpa / BOILING_T_P0_KPA)
    t_b_k = 1.0 / (1.0 / BOILING_T_T0_K
                   - BOILING_T_R_J_PER_MOL_K * ln_ratio / BOILING_T_L_V_J_PER_MOL)
    return t_b_k - 273.15


def soil_temperature_c(air_c: float, heat_flux_w_m2: float,
                       depth_m: float = SOIL_T_REFERENCE_DEPTH_M,
                       conductivity_w_m_k: float = SOIL_K_W_M_K,
                       site_elevation_m: float = BOILING_T_REFERENCE_SITE_M
                       ) -> float:
    """Steady-state conductive soil temperature at depth from a geothermal flux below.
T(z) = T_surface + Q * z / k; capped at the local atmospheric boiling point."""
    air = _finite("air_c", air_c)
    q = _nonnegative("heat_flux_w_m2", heat_flux_w_m2)
    z = _nonnegative("depth_m", depth_m)
    k = _positive("conductivity_w_m_k", conductivity_w_m_k)
    t = air + q * z / k
    return min(boiling_point_c(site_elevation_m), t)


def soil_temperature_field(air_c: float, heat_flux_field: dict,
                           depth_m: float = SOIL_T_REFERENCE_DEPTH_M,
                           conductivity_w_m_k: float = SOIL_K_W_M_K,
                           site_elevation_m: float = BOILING_T_REFERENCE_SITE_M
                           ) -> dict:
    """Soil temperature raster derived from a heat flux field at the stated depth."""
    air = _finite("air_c", air_c)
    k = _positive("conductivity_w_m_k", conductivity_w_m_k)
    z = _nonnegative("depth_m", depth_m)
    if not isinstance(heat_flux_field, dict) or "values_w_m2" not in heat_flux_field:
        raise ValueError("heat_flux_field must be a sidecar dict with values_w_m2")
    t_boil = boiling_point_c(site_elevation_m)
    values: list[list[float]] = []
    for row in heat_flux_field["values_w_m2"]:
        values.append([soil_temperature_c(air, q, z, k, site_elevation_m)
                       for q in row])
    return {
        "schema": "yellowstone.soil_temperature.v1",
        "grid": heat_flux_field.get("grid"),
        "values_c": values,
        "depth_m": z,
        "conductivity_w_m_k": k,
        "conductivity_source": SOIL_K_SOURCE,
        "model": "steady_state_conductive_profile",
        "site_elevation_m": site_elevation_m,
        "boiling_point_c": t_boil,
        "boiling_point_source": BOILING_T_SOURCE,
        "status": "authored",
        "note": ("conductive profile; above the local boiling point the "
                 "profile is physically bounded by the two-phase change of "
                 "state and is set to the boiling temperature, not clamped"),
    }


def thermal_melt_mm_d_from_ghf(heat_flux_w_m2: float) -> float:
    """Snow melt rate (mm water-equivalent per day) from a ground heat flux into the pack.
Energy balance: m = Q * seconds / (rho_water * L_f); unit factor is Q * 0.2587 mm/d per W/m2."""
    q = _nonnegative("heat_flux_w_m2", heat_flux_w_m2)
    # mm/day of water-equivalent melt per W/m2 passed into the pack.
    return q * SECONDS_PER_DAY / (RHO_WATER_KG_M3 * L_F_J_KG) * 1000.0


def tree_thermal_suitability(soil_t_c: float,
                             threshold_c: float = LODGEPOLE_SOIL_DIEOFF_C
                             ) -> float:
    """Lodgepole suitability from soil temperature at the die-off depth.
Returns 1.0 well below the threshold, 0.0 at or above it, linear transition in a 5 C band below."""
    t = _finite("soil_t_c", soil_t_c)
    th = _finite("threshold_c", threshold_c)
    if t >= th:
        return 0.0
    if t <= th - 5.0:
        return 1.0
    return (th - t) / 5.0


def thermal_flux_mm_d_by_patch(patches: list, shells: list,
                               background_w_m2: float = GHF_BACKGROUND_W_M2,
                               apron_w_m2: float = GHF_APRON_W_M2,
                               pool_w_m2: float = GHF_POOL_W_M2) -> dict:
    """Per-patch snow-melt flux (mm/d) from the geothermal ground heat flux at the patch center.
Keyed by patch id; input for run_season's optional per-patch thermal field."""
    out: dict[str, float] = {}
    for p in patches or []:
        pid = p.get("id")
        if pid is None:
            raise ValueError("each patch must have an id to key the output")
        cx, cz = p.get("center_xz", [None, None])
        if cx is None or cz is None:
            raise ValueError(f"patch {pid!r} missing center_xz")
        q = heat_flux_at(float(cx), float(cz), shells,
                         background_w_m2, apron_w_m2, pool_w_m2)
        out[pid] = thermal_melt_mm_d_from_ghf(q)
    return out


def soil_temperature_by_patch(patches: list, shells: list, air_c: float,
                              depth_m: float = SOIL_T_REFERENCE_DEPTH_M,
                              conductivity_w_m_k: float = SOIL_K_W_M_K,
                              background_w_m2: float = GHF_BACKGROUND_W_M2,
                              apron_w_m2: float = GHF_APRON_W_M2,
                              pool_w_m2: float = GHF_POOL_W_M2,
                              site_elevation_m: float = BOILING_T_REFERENCE_SITE_M
                              ) -> dict:
    """Per-patch soil temperature (degC) at the sampling depth, keyed by patch id."""
    out: dict[str, float] = {}
    for p in patches or []:
        pid = p.get("id")
        if pid is None:
            raise ValueError("each patch must have an id to key the output")
        cx, cz = p.get("center_xz", [None, None])
        if cx is None or cz is None:
            raise ValueError(f"patch {pid!r} missing center_xz")
        q = heat_flux_at(float(cx), float(cz), shells,
                         background_w_m2, apron_w_m2, pool_w_m2)
        out[pid] = soil_temperature_c(air_c, q, depth_m,
                                      conductivity_w_m_k, site_elevation_m)
    return out
