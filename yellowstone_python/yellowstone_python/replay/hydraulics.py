"""Trapezoidal channel hydraulics diagnostics for the 1-D river solver.

Scientific scope
----------------
Replaces the rectangular assumption (A = W*d) with a trapezoidal
cross-section diagnostic, Manning velocity consistency, Froude regime,
bed shear, reach travel times, and a Fischer-style dispersion estimate.
All quantities are DIAGNOSTIC: the solver still integrates rectangular
volumes (baseline preserved) until surveyed bathymetry exists. Each
diagnostic carries explicit provenance — nothing here is calibrated.

Cross-section convention
------------------------
Authored ``width_m`` from world.json is the water-surface (top) width.
With bank slope z (horizontal:vertical) and center depth d::

    bottom width  b = W - 2*z*d        (must stay positive)
    area          A = (W - z*d) * d
    wetted perimeter P = b + 2*d*sqrt(1 + z^2)
    hydraulic radius R = A / P
    hydraulic depth  H = A / W

Rectangular is the z = 0 limit (A = W*d, P = W + 2*d).

Manning velocity V = (1/n) * R^(2/3) * S^(1/2) requires a positive
downstream energy slope S. Flat or adverse grades (S <= 0 from mapped
elevations) leave Manning fields None with an explicit warning — the
diagnostic refuses to invent a slope.

Fischer dispersion D = 0.011 * V^2 * W^2 / (H * u*), u* = sqrt(g*R*S).
Guarded: needs positive velocity, depth, and shear velocity.

Observation scoring compares paired modeled/observed series (RMSE, bias,
MAE). It never supplies observations — those live in caller-provided
files (e.g. USGS NWIS fetches via tools/usgs_nwis.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

G_M_S2 = 9.81
RHO_WATER_KG_M3 = 1000.0

# Illustrative defaults, explicitly authored — not measurements.
# REAL DATA STATUS: USGS field measurements (current-meter surveys,
# bathymetry) unavailable via NWIS web API since Oct 2026 format change.
# Integration point: load_usgs_cross_section(site_no) (see below)
# would connect to machine-readable surveys when available.
DEFAULT_BANK_SLOPE_ZH = 1.5  # vegetated natural banks, authored (not surveyed)
DEFAULT_MANNING_N = 0.035  # gravel-bed stream, authored (Chow 1959 range; uncalibrated)
MIN_SLOPE_FOR_MANNING = 1e-4  # authored noise floor: gentler mapped grades
# are within centerline-elevation noise (sub-cm drops over cell scales),
# so Manning is reported undefined rather than fitted to noise

# --- Real-data integration framework ---
# Cross-section measurements (bank slope, Manning's n, depth profiles)
# should come from USGS field surveys or in-situ bathymetry. Currently
# unavailable via machine-readable NWIS (Oct 2026 format change); this
# framework provides the hook for when surveys are restored or
# directly ingested from survey files.
USGS_NWIS_SITE_MAP = {
    "river_5856_0": "06036805",  # Firehole at Old Faithful
    "river_5872_0": "06036805",
    "river_5913_0": "06036805",
    "river_5933_0": "06036905",  # Firehole near West Yellowstone (downstream)
    "river_5998_0": "06036905",
}
CROSS_SECTION_PROVENANCE = {
    "bank_slope_zh": "authored_default_1_5_not_surveyed",
    "manning_n": "authored_default_0_035_chow_1959_uncalibrated",
    "top_width_m": "world_json_authored_not_surveyed",
    "depth_m": "dem_derived_estimate_not_bathymetry",
    "real_data_available": False,
    "integration_notes": "USGS NWIS measurement pages moved to JS/HTML Oct 2026; "
                           "machine-readable cross-section surveys (width/area/velocity) "
                           "not currently fetchable. Tools/usgs_nwis.py documents gap.",
}


def load_usgs_cross_section(site_no: str, measurement_date: str | None = None) -> dict | None:
    """Integration point for real USGS cross-section surveys.

    When machine-readable NWIS measurement data is available (before
    Oct 2026, or via restored API / direct survey file), this loads
    measured width, area, velocity, and depth for use in place of
    authored DEM-derived estimates.

    Currently returns None with provenance documented; real data
    requires either API restoration or manual survey file ingestion.
    """
    CROSS_SECTION_PROVENANCE["last_integration_attempt"] = {
        "site_no": site_no,
        "date": measurement_date,
        "status": "unavailable_nwis_web_format_changed_oct_2026",
        "fallback": "authored_dem_estimate",
    }
    return None


def _finite(value: Any, name: str, minimum: float | None = None) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _positive(value: Any, name: str) -> float:
    result = _finite(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


@dataclass(frozen=True)
class TrapezoidGeometry:
    """Trapezoidal cross-section from top width, depth, bank slope."""

    top_width_m: float
    depth_m: float
    bank_slope_zh: float = DEFAULT_BANK_SLOPE_ZH

    def __post_init__(self) -> None:
        object.__setattr__(self, "top_width_m",
                           _positive(self.top_width_m, "top_width_m"))
        object.__setattr__(self, "depth_m",
                           _positive(self.depth_m, "depth_m"))
        z = _finite(self.bank_slope_zh, "bank_slope_zh", 0.0)
        object.__setattr__(self, "bank_slope_zh", z)
        if self.bottom_width_m <= 0.0:
            raise ValueError(
                f"banks meet: bottom width {self.bottom_width_m:.3f} m <= 0 "
                f"(W={self.top_width_m}, d={self.depth_m}, z={z}); "
                "reduce depth or bank slope")

    @property
    def bottom_width_m(self) -> float:
        return self.top_width_m - 2.0 * self.bank_slope_zh * self.depth_m

    @property
    def area_m2(self) -> float:
        return (self.top_width_m - self.bank_slope_zh * self.depth_m) \
            * self.depth_m

    @property
    def wetted_perimeter_m(self) -> float:
        return (self.bottom_width_m + 2.0 * self.depth_m
                * math.sqrt(1.0 + self.bank_slope_zh ** 2))

    @property
    def hydraulic_radius_m(self) -> float:
        return self.area_m2 / self.wetted_perimeter_m

    @property
    def hydraulic_depth_m(self) -> float:
        return self.area_m2 / self.top_width_m


def rectangular_area_m2(top_width_m: float, depth_m: float) -> float:
    """Legacy solver assumption, kept for bias reporting."""
    return _positive(top_width_m, "top_width_m") * _positive(depth_m, "depth_m")


def manning_velocity_m_s(hydraulic_radius_m: float, slope: float,
                         manning_n: float = DEFAULT_MANNING_N) -> float:
    """Manning velocity. Requires positive slope and roughness."""
    radius = _positive(hydraulic_radius_m, "hydraulic_radius_m")
    grade = _finite(slope, "slope")
    if grade <= 0.0:
        raise ValueError("slope must be positive for Manning velocity")
    n = _positive(manning_n, "manning_n")
    return (1.0 / n) * radius ** (2.0 / 3.0) * math.sqrt(grade)


def froude_number(velocity_m_s: float, hydraulic_depth_m: float) -> float:
    """Froude number. <1 subcritical, =1 critical, >1 supercritical."""
    velocity = _finite(velocity_m_s, "velocity_m_s", 0.0)
    depth = _positive(hydraulic_depth_m, "hydraulic_depth_m")
    return velocity / math.sqrt(G_M_S2 * depth)


def bed_shear_pa(hydraulic_radius_m: float, slope: float,
                 rho_kg_m3: float = RHO_WATER_KG_M3) -> float:
    """Bed shear stress tau = rho * g * R * S."""
    radius = _positive(hydraulic_radius_m, "hydraulic_radius_m")
    grade = _finite(slope, "slope", 0.0)
    density = _positive(rho_kg_m3, "rho_kg_m3")
    return density * G_M_S2 * radius * grade


def shear_velocity_m_s(hydraulic_radius_m: float, slope: float) -> float:
    """Shear velocity u* = sqrt(g * R * S)."""
    radius = _positive(hydraulic_radius_m, "hydraulic_radius_m")
    grade = _finite(slope, "slope", 0.0)
    return math.sqrt(G_M_S2 * radius * grade)


def fischer_dispersion_m2_s(velocity_m_s: float, top_width_m: float,
                            hydraulic_depth_m: float,
                            shear_velocity_m_s_: float) -> float:
    """Fischer (1979) longitudinal dispersion estimate.

    D = 0.011 * V^2 * W^2 / (H * u*). Order-of-magnitude diagnostic for
    comparing against the solver's illustrative dispersion coefficient —
    not a fitted value.
    """
    velocity = _finite(velocity_m_s, "velocity_m_s", 0.0)
    width = _positive(top_width_m, "top_width_m")
    depth = _positive(hydraulic_depth_m, "hydraulic_depth_m")
    ustar = _finite(shear_velocity_m_s_, "shear_velocity_m_s", 0.0)
    if ustar <= 0.0:
        raise ValueError("shear velocity must be positive for Fischer D")
    return 0.011 * velocity ** 2 * width ** 2 / (depth * ustar)


def travel_time_s(length_m: float, velocity_m_s: float) -> float:
    """Nominal advective transit L / V."""
    length = _positive(length_m, "length_m")
    velocity = _finite(velocity_m_s, "velocity_m_s")
    if velocity <= 0.0:
        raise ValueError("velocity must be positive for travel time")
    return length / velocity


def slope_from_drop(drop_m: float, length_m: float) -> float:
    """Downstream slope from elevation drop over horizontal length."""
    length = _positive(length_m, "length_m")
    return _finite(drop_m, "drop_m") / length


def cell_hydraulics(
    length_m: float,
    top_width_m: float,
    depth_m: float,
    discharge_m3_s: float,
    slope: float | None,
    bank_slope_zh: float = DEFAULT_BANK_SLOPE_ZH,
    manning_n: float = DEFAULT_MANNING_N,
) -> dict[str, Any]:
    """Per-cell hydraulic diagnostics with explicit provenance.

    Solver continuity velocity V = Q / A_trap is always defined for
    positive discharge. Manning, Froude-vs-Manning, shear, and Fischer
    fields are None when the mapped grade is flat/adverse (slope None
    or <= MIN_SLOPE_FOR_MANNING) — the diagnostic reports the gap
    instead of inventing a slope.
    """
    length = _positive(length_m, "length_m")
    discharge = _finite(discharge_m3_s, "discharge_m3_s", 0.0)
    geom = TrapezoidGeometry(top_width_m, depth_m, bank_slope_zh)
    n = _positive(manning_n, "manning_n")

    area_rect = rectangular_area_m2(geom.top_width_m, geom.depth_m)
    area_trap = geom.area_m2
    record: dict[str, Any] = {
        "bank_slope_zh": geom.bank_slope_zh,
        "manning_n": n,
        "area_rect_m2": area_rect,
        "area_trap_m2": area_trap,
        "rectangular_bias_pct": 100.0 * (area_rect - area_trap) / area_trap,
        "volume_rect_m3": area_rect * length,
        "volume_trap_m3": area_trap * length,
        "bottom_width_m": geom.bottom_width_m,
        "wetted_perimeter_m": geom.wetted_perimeter_m,
        "hydraulic_radius_m": geom.hydraulic_radius_m,
        "hydraulic_depth_m": geom.hydraulic_depth_m,
        "slope": slope,
        "warnings": [],
        "provenance": {
            "top_width": "authored_width_from_world_json_not_surveyed_banks",
            "depth": "per-feature profile or assumed default (see depth_status)",
            "bank_slope_zh": "authored_illustrative_not_measured",
            "manning_n": "authored_illustrative_not_calibrated",
            "slope": ("reach-averaged mapped grade over the river feature "
                      "(total elevation drop / total length) where above "
                      "the noise floor; flat/adverse grades reported, "
                      "not replaced"),
        },
    }

    if discharge > 0.0:
        v_rect = discharge / area_rect
        v_trap = discharge / area_trap
        record["velocity_rect_m_s"] = v_rect
        record["velocity_continuity_m_s"] = v_trap
        record["travel_time_s"] = travel_time_s(length, v_trap)
        record["froude_continuity"] = froude_number(
            v_trap, geom.hydraulic_depth_m)
    else:
        record["velocity_rect_m_s"] = 0.0
        record["velocity_continuity_m_s"] = 0.0
        record["travel_time_s"] = None
        record["froude_continuity"] = 0.0
        record["warnings"].append("zero_discharge_velocities_zero")

    for key in ("velocity_manning_m_s", "froude_manning",
                "bed_shear_pa", "fischer_dispersion_m2_s"):
        record[key] = None
    if slope is None or not math.isfinite(slope) \
            or slope <= MIN_SLOPE_FOR_MANNING:
        record["warnings"].append(
            "flat_or_adverse_grade_manning_undefined")
        record["manning_consistency_ratio"] = None
    else:
        v_man = manning_velocity_m_s(geom.hydraulic_radius_m, slope, n)
        ustar = shear_velocity_m_s(geom.hydraulic_radius_m, slope)
        record["velocity_manning_m_s"] = v_man
        record["froude_manning"] = froude_number(
            v_man, geom.hydraulic_depth_m)
        record["bed_shear_pa"] = bed_shear_pa(
            geom.hydraulic_radius_m, slope)
        try:
            record["fischer_dispersion_m2_s"] = fischer_dispersion_m2_s(
                v_man, geom.top_width_m, geom.hydraulic_depth_m, ustar)
        except ValueError as exc:
            record["warnings"].append(f"fischer_undefined: {exc}")
        if discharge > 0.0:
            record["manning_consistency_ratio"] = (
                record["velocity_continuity_m_s"] / v_man)
        else:
            record["manning_consistency_ratio"] = None
        if record.get("froude_manning", 0.0) is not None \
                and record["froude_manning"] >= 1.0:
            record["warnings"].append("manning_froude_supercritical")
    if record.get("froude_continuity", 0.0) >= 1.0 and discharge > 0.0:
        record["warnings"].append("continuity_froude_supercritical")

    return record


def score_paired_series(modeled: Sequence[float],
                        observed: Sequence[float]) -> dict[str, float]:
    """RMSE / bias / MAE / max-abs over paired modeled-observed values.

    Raises on empty, mismatched-length, or nonfinite input. No time
    interpolation — callers align series first and document the method.
    """
    mod = [_finite(v, "modeled value") for v in modeled]
    obs = [_finite(v, "observed value") for v in observed]
    if not mod:
        raise ValueError("paired series must be nonempty")
    if len(mod) != len(obs):
        raise ValueError(
            f"paired series length mismatch: {len(mod)} vs {len(obs)}")
    n = len(mod)
    residuals = [m - o for m, o in zip(mod, obs)]
    mse = math.fsum(r * r for r in residuals) / n
    return {
        "n": float(n),
        "rmse": math.sqrt(mse),
        "bias": math.fsum(residuals) / n,
        "mae": math.fsum(abs(r) for r in residuals) / n,
        "max_abs": max(abs(r) for r in residuals),
    }


def skill_scores(modeled: Sequence[float],
                 observed: Sequence[float]) -> dict[str, Any]:
    """Nash-Sutcliffe + Kling-Gupta skill scores (hydrologist's scale).

    NSE = 1 - RSS/TSS: 1 is perfect, 0 means "as good as the observed
    mean", negative is worse. KGE = 1 - ED(r, alpha, beta) with
    correlation r, variability ratio alpha = std_m/std_o, bias ratio
    beta = mean_m/mean_o. Raises on constant observed series (TSS = 0
    makes NSE undefined) or zero observed mean (beta undefined).
    """
    import numpy as np
    mod = np.asarray([_finite(v, "modeled value") for v in modeled],
                     dtype=float)
    obs = np.asarray([_finite(v, "observed value") for v in observed],
                     dtype=float)
    if mod.size == 0:
        raise ValueError("paired series must be nonempty")
    if mod.shape != obs.shape:
        raise ValueError(
            f"paired series length mismatch: {mod.size} vs {obs.size}")
    n = mod.size
    mean_o = float(np.mean(obs))
    tss = float(np.sum((obs - mean_o) ** 2))
    if tss == 0.0:
        raise ValueError("observed series is constant; NSE undefined")
    rss = float(np.sum((mod - obs) ** 2))
    nse = 1.0 - rss / tss
    std_o = float(np.std(obs))
    std_m = float(np.std(mod))
    if std_o == 0.0:
        raise ValueError("observed series is constant; KGE undefined")
    if mean_o == 0.0:
        raise ValueError("observed mean is zero; KGE beta undefined")
    alpha = std_m / std_o
    beta = float(np.mean(mod)) / mean_o
    if std_m == 0.0:
        # A constant model (e.g. the observed mean) has no correlation
        # by definition; NaN would propagate silently, so KGE is
        # reported missing with an explicit flag instead.
        return {"n": n, "nse": nse, "kge": None, "correlation": None,
                "alpha": alpha, "beta": beta, "constant_modeled": True}
    r = float(np.corrcoef(mod, obs)[0, 1])
    kge = 1.0 - math.sqrt((r - 1.0) ** 2 + (alpha - 1.0) ** 2
                          + (beta - 1.0) ** 2)
    return {"n": n, "nse": nse, "kge": kge, "correlation": r,
            "alpha": alpha, "beta": beta, "constant_modeled": False}


QQ_LEVELS = (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)


def residual_diagnostics(modeled: Sequence[float],
                         observed: Sequence[float],
                         max_lag: int = 5) -> dict[str, Any]:
    """Autocorrelation + normal Q-Q of paired residuals.

    Correlated residuals mean the model missed structure (diurnal
    phase, event response); Q-Q gaps mean non-Gaussian errors that
    RMSE-based bands misstate. Returns lag-1..max_lag autocorrelations
    of demeaned residuals and empirical-vs-normal quantiles at fixed
    levels, with the max Q-Q gap. All-zero residuals (a perfect fit)
    report a flag instead of undefined correlations.
    """
    import numpy as np
    from scipy.stats import norm
    mod = np.asarray([_finite(v, "modeled value") for v in modeled],
                     dtype=float)
    obs = np.asarray([_finite(v, "observed value") for v in observed],
                     dtype=float)
    if mod.size == 0:
        raise ValueError("paired series must be nonempty")
    if mod.shape != obs.shape:
        raise ValueError(
            f"paired series length mismatch: {mod.size} vs {obs.size}")
    if max_lag < 1 or max_lag >= mod.size:
        raise ValueError("max_lag must satisfy 1 <= max_lag < n")
    resid = mod - obs
    if float(np.sum(resid ** 2)) == 0.0:
        return {"n": int(mod.size), "perfect_fit": True,
                "autocorr": {}, "qq": {}, "max_qq_gap": 0.0}
    dev = resid - float(np.mean(resid))
    denom = float(np.sum(dev ** 2))
    autocorr = {}
    for lag in range(1, max_lag + 1):
        autocorr[lag] = float(np.sum(dev[:-lag] * dev[lag:]) / denom)
    std = float(np.std(resid))
    standardized = sorted((resid - float(np.mean(resid))) / std)
    qq = {}
    for level in QQ_LEVELS:
        empirical = float(np.quantile(standardized, level))
        theoretical = float(norm.ppf(level))
        qq[level] = {"empirical": empirical, "normal": theoretical,
                     "gap": empirical - theoretical}
    return {"n": int(mod.size), "perfect_fit": False,
            "autocorr": autocorr, "qq": qq,
            "max_qq_gap": max(abs(row["gap"]) for row in qq.values())}


def thermal_inventory(sources: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Account total thermal inflow and flow-weighted entry temperature.

    Pure bookkeeping over caller-supplied source dicts with flow_m3_s
    and temperature_c. Constant temperatures enter the flow-weighted
    mean; scheduled (Series-dict) temperatures are listed with
    temperature_c None and EXCLUDED from the mean, with an explicit
    count — a scheduled intervention has no single entry temperature.
    Provenance passes through per-source status.
    """
    total_q = 0.0
    total_qt = 0.0
    const_q = 0.0
    n_scheduled = 0
    rows = []
    for source in sources:
        flow = _finite(source.get("flow_m3_s", 0.0), "source flow", 0.0)
        raw_temp = source.get("temperature_c", 0.0)
        total_q += flow
        if isinstance(raw_temp, dict):
            n_scheduled += 1
            temp: float | None = None
        else:
            temp = _finite(raw_temp, "source temperature")
            total_qt += flow * temp
            const_q += flow
        rows.append({
            "id": source.get("id", "?"),
            "flow_m3_s": flow,
            "temperature_c": temp,
            "scheduled": isinstance(raw_temp, dict),
            "status": source.get("status", "unspecified_treat_as_authored"),
        })
    return {
        "n_sources": len(rows),
        "n_scheduled_sources": n_scheduled,
        "total_thermal_flow_m3_s": total_q,
        "flow_weighted_entry_c": (total_qt / const_q if const_q > 0 else None),
        "flow_weighted_entry_basis": (
            "constant-temperature sources only; scheduled interventions "
            "excluded (no single entry temperature)"),
        "total_heat_m3_c_per_s": total_qt,
        "sources": rows,
    }
