"""FAO-56 Penman-Monteith reference ET and crop coefficients.
Reference: Allen, Pereira, Raes, Smith (1998), FAO Irrigation and Drainage Paper 56."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite, nonnegative as _nonnegative

import math

SCHEMA = "yellowstone.evapotranspiration.v1"

FAO56_CITATION = (
    "Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998). Crop "
    "evapotranspiration: Guidelines for computing crop water requirements. "
    "FAO Irrigation and Drainage Paper 56. "
    "http://www.fao.org/3/x0490e/x0490e00.htm")

# Mid-season Kc per patch type, from Allen et al. (1998) Tables 12 and 17.
CROP_COEFFICIENTS = {
    "dry_meadow": 1.00,
    "wet_meadow": 1.15,
    "river_bank": 1.15,
    "cold_wetland": 1.20,
    "forest_lodgepole": 0.90,
    "forest_moist": 0.95,
    "forest_edge": 0.90,
    "sinter_dry": 0.10,
    "thermal_core": 0.05,
    "thermal_outflow_hot": 0.05,
    "river_pool": 1.05,
    "river_riffle": 1.05,
    "unsuitable_matrix": 0.20,
}
CROP_COEFFICIENT_SOURCE = (
    "Allen et al. 1998 FAO-56 Table 12 (crop coefficients) and Table 17 "
    "(natural vegetation and standing water). Mid-season Kc from the "
    "published bands; mapping to patch types is authored.")






def saturation_vapor_pressure_kpa(t_c: float) -> float:
    """Saturation vapor pressure e0(T) in kPa. Allen (1998) Eq 11 page 36."""
    t = _finite("t_c", t_c)
    return 0.6108 * math.exp(17.27 * t / (t + 237.3))


def slope_svp_kpa_c(t_c: float) -> float:
    """Slope of the saturation vapor pressure curve. Allen (1998) Eq 13 page 37."""
    t = _finite("t_c", t_c)
    return (4098.0 * (0.6108 * math.exp(17.27 * t / (t + 237.3)))
            / (t + 237.3) ** 2)


def atmospheric_pressure_kpa(elevation_m: float) -> float:
    """Atmospheric pressure from elevation. Allen (1998) Eq 7 page 31."""
    z = _finite("elevation_m", elevation_m)
    return 101.3 * ((293.0 - 0.0065 * z) / 293.0) ** 5.26


def psychrometric_constant_kpa_c(pressure_kpa: float) -> float:
    """Psychrometric constant from pressure. Allen (1998) Eq 8 page 32."""
    p = _nonnegative("pressure_kpa", pressure_kpa)
    return 0.665e-3 * p


def saturation_vapor_from_tmax_tmin(tmax_c: float, tmin_c: float) -> float:
    """Mean of e0(Tmax) and e0(Tmin) as the daily es. Allen (1998) Eq 12 page 36."""
    return 0.5 * (saturation_vapor_pressure_kpa(tmax_c)
                  + saturation_vapor_pressure_kpa(tmin_c))


def actual_vapor_pressure_kpa(tmax_c: float, tmin_c: float,
                              rh_max_pct: float | None = None,
                              rh_min_pct: float | None = None,
                              rh_mean_pct: float | None = None,
                              tdew_c: float | None = None) -> float:
    """ea with FAO-56 precedence: Tdew (Eq 14), else RHmax/RHmin (Eq 17), else RHmean (Eq 19)."""
    if tdew_c is not None:
        return saturation_vapor_pressure_kpa(tdew_c)
    if rh_max_pct is not None and rh_min_pct is not None:
        rhmax = _nonnegative("rh_max_pct", rh_max_pct)
        rhmin = _nonnegative("rh_min_pct", rh_min_pct)
        if rhmax > 100.0 or rhmin > 100.0:
            raise ValueError("relative humidity must be in [0, 100]")
        return 0.5 * (saturation_vapor_pressure_kpa(tmin_c) * rhmax / 100.0
                      + saturation_vapor_pressure_kpa(tmax_c) * rhmin / 100.0)
    if rh_mean_pct is not None:
        rhmean = _nonnegative("rh_mean_pct", rh_mean_pct)
        if rhmean > 100.0:
            raise ValueError("relative humidity must be in [0, 100]")
        es = saturation_vapor_from_tmax_tmin(tmax_c, tmin_c)
        return rhmean / 100.0 * es
    raise ValueError(
        "actual_vapor_pressure needs Tdew, RHmax+RHmin or RHmean")


def reference_et0_mm_d(tmax_c: float, tmin_c: float,
                       rn_mj_m2_d: float, g_mj_m2_d: float,
                       u2_m_s: float, elevation_m: float,
                       rh_max_pct: float | None = None,
                       rh_min_pct: float | None = None,
                       rh_mean_pct: float | None = None,
                       tdew_c: float | None = None) -> float:
    """Daily reference ET0 for a short grass surface, mm/day. Allen (1998) Eq 6 page 24."""
    tmax = _finite("tmax_c", tmax_c)
    tmin = _finite("tmin_c", tmin_c)
    if tmax < tmin:
        raise ValueError("tmax_c must be >= tmin_c")
    rn = _finite("rn_mj_m2_d", rn_mj_m2_d)
    g = _finite("g_mj_m2_d", g_mj_m2_d)
    u2 = _nonnegative("u2_m_s", u2_m_s)
    tmean = 0.5 * (tmax + tmin)
    delta = slope_svp_kpa_c(tmean)
    p = atmospheric_pressure_kpa(elevation_m)
    gamma = psychrometric_constant_kpa_c(p)
    es = saturation_vapor_from_tmax_tmin(tmax, tmin)
    ea = actual_vapor_pressure_kpa(tmax, tmin, rh_max_pct, rh_min_pct,
                                   rh_mean_pct, tdew_c)
    numerator = (0.408 * delta * (rn - g)
                 + gamma * (900.0 / (tmean + 273.0)) * u2 * (es - ea))
    denominator = delta + gamma * (1.0 + 0.34 * u2)
    return max(0.0, numerator / denominator)


def crop_coefficient_for(patch_type: str) -> float:
    """Return Kc for a patch habitat type; raises on unknown types."""
    if not isinstance(patch_type, str):
        raise ValueError("patch_type must be a string")
    if patch_type not in CROP_COEFFICIENTS:
        raise ValueError(
            f"no crop coefficient for patch_type {patch_type!r}; "
            f"known types: {sorted(CROP_COEFFICIENTS)}")
    return CROP_COEFFICIENTS[patch_type]


def actual_et_mm_d(et0_mm_d: float, kc: float,
                   soil_water_fraction: float = 1.0) -> float:
    """ETc = Kc * ET0 scaled by relative soil water. Allen (1998) Chapter 7 Ks concept."""
    e0 = _nonnegative("et0_mm_d", et0_mm_d)
    k = _nonnegative("kc", kc)
    s = _finite("soil_water_fraction", soil_water_fraction)
    if not 0.0 <= s <= 1.0:
        raise ValueError("soil_water_fraction must be in [0, 1]")
    return k * e0 * s


def step_patch_soil_water(soil_mm: float, soil_cap_mm: float,
                          et0_mm_d: float, kc: float,
                          dt_days: float = 1.0) -> tuple[float, float]:
    """Deplete the soil-water bucket by Kc * ET0 over dt_days. Returns (new_soil_mm, actual_et_mm)."""
    s = _nonnegative("soil_mm", soil_mm)
    cap = _nonnegative("soil_cap_mm", soil_cap_mm)
    if cap <= 0.0:
        raise ValueError("soil_cap_mm must be > 0")
    e0 = _nonnegative("et0_mm_d", et0_mm_d)
    k = _nonnegative("kc", kc)
    dt = _nonnegative("dt_days", dt_days)
    fraction = min(1.0, s / cap)
    demand = k * e0 * dt
    draw = min(s, demand * fraction)
    return (s - draw, draw)


def step_patches_et(patches: list, et0_mm_d: float, dt_days: float = 1.0,
                    soil_cap_mm: float = 120.0) -> tuple[list, dict]:
    """Advance per-patch soil water by Kc * ET0 for one dt_days step; mutates in place."""
    cap = _nonnegative("soil_cap_mm", soil_cap_mm)
    if cap <= 0.0:
        raise ValueError("soil_cap_mm must be > 0")
    total_et = 0.0
    by_patch: dict[str, float] = {}
    for p in patches:
        pid = p.get("id")
        if pid is None:
            raise ValueError("patches must have an id")
        hab = p.get("habitat")
        if hab is None:
            raise ValueError(f"patch {pid!r} missing habitat")
        kc = crop_coefficient_for(hab)
        if "soil_mm" in p:
            soil = _nonnegative(f"patch {pid!r} soil_mm", p["soil_mm"])
        else:
            moist = _finite(f"patch {pid!r} moisture", p.get("moisture", 0.0))
            if not 0.0 <= moist <= 1.0:
                raise ValueError(
                    f"patch {pid!r} moisture {moist} outside [0, 1]")
            soil = moist * cap
        new_soil, et = step_patch_soil_water(soil, cap, et0_mm_d, kc, dt_days)
        p["soil_mm"] = round(new_soil, 3)
        p["moisture"] = round(min(1.0, new_soil / cap), 4)
        total_et += et
        by_patch[pid] = round(et, 4)
    return patches, {
        "schema": SCHEMA,
        "et0_mm_d": et0_mm_d,
        "dt_days": dt_days,
        "soil_cap_mm": cap,
        "total_et_mm": round(total_et, 4),
        "et_by_patch_mm": by_patch,
        "method": ("FAO-56 Penman-Monteith reference ET0 with Kc per patch; "
                   "Ks linear from relative soil water"),
        "source": FAO56_CITATION,
        "coefficients_source": CROP_COEFFICIENT_SOURCE,
        "status": "authored",
    }
