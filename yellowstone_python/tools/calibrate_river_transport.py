"""Staged reach-scale calibrator for the 1-D river-transport solver (stages A..D)."""
from __future__ import annotations

from yellowstone_python.river.obs_model import UPSTREAM_GAUGE, DOWNSTREAM_GAUGE

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from yellowstone_python.river.calibrate import SCHEMA_FIT, candidate_numerically_valid, check_continuity, estimate_lag, interp_series, least_squares_fit, reach_heat_fit, run_fit_forward
from yellowstone_python.common.provenance import sha256_json
from yellowstone_python.river.river_transport import Cell, River, Series, Source
from yellowstone_python.river.surface_flux import BUDGET_PARAM_KEYS, BudgetParams, describe_surface_model
from yellowstone_python.river.uncertainty import DEFAULT_BAND_LEVEL, DEFAULT_N_BOOTSTRAP, ENSEMBLE_SEED, band_coverage, ensemble_bands
from yellowstone_python.river.hydraulics import score_paired_series

SCHEMA_STAGED = "yellowstone.staged_calibration.v1"

OBSERVATION_HIERARCHY = {
    "meteorology": {
        "air_c": "met.hourly[*][1]",
        "rh": "met.hourly[*][2]",
        "wind_mps": "met.hourly[*][3]",
        "shortwave_w_m2": "met.hourly[*][4]",
        "cloud_fraction": "met.hourly[*][5]",
        "longwave_down_w_m2": "met.optional.longwave_down_w_m2",
        "dewpoint_c": "met.optional.dewpoint_c",
        "pressure_kpa": "met.optional.pressure_kpa",
    },
    "hydraulics": {
        "upstream_discharge_m3_s": "sites.06036805.series.discharge_m3_s",
        "downstream_discharge_m3_s": "sites.06036905.series.discharge_m3_s",
        "stage_m": "sites.*.series.stage_m",
        "velocity_m_s": "sites.*.series.velocity_m_s",
        "cross_section_m2": "sites.*.series.cross_section_m2",
    },
    "water_temperature": {
        "upstream_temperature_c": "sites.06036805.series.temperature_c",
        "downstream_temperature_c": "sites.06036905.series.temperature_c",
        "intermediate_temperature_c": "sites.*.series.temperature_c",
    },
    "surface_flux": {
        "net_radiometer_w_m2": "flux_station.net",
        "longwave_down_w_m2": "flux_station.longwave_down",
        "sensible_w_m2": "flux_station.sensible",
        "latent_w_m2": "flux_station.latent",
    },
}

STAGE_PLAN = (
    ("A", "hydraulics_and_travel_time",
     "Fix effective geometry and verify travel-time against observed lag."),
    ("B", "longitudinal_dispersion",
     "Fit D from pulse width or mark not identifiable in a lumped cell."),
    ("C", "boundary_and_lateral_sources",
     "Fit effective q_lat and t_lat with the surface budget held at "
     "defaults."),
    ("D", "surface_energy_budget",
     "Fit BudgetParams fields that the obs set can constrain; report "
     "the others as not identified."),
)

SURFACE_IDENTIFIABILITY: dict[str, tuple[tuple[str, ...], ...]] = {
    "shortwave_multiplier": (("surface_flux.net_radiometer_w_m2",),
                             ("meteorology.station_shortwave_w_m2",)),
    "longwave_multiplier": (("surface_flux.longwave_down_w_m2",),
                            ("meteorology.longwave_down_w_m2",)),
    "longwave_bias_w_m2": (("surface_flux.longwave_down_w_m2",),
                           ("meteorology.longwave_down_w_m2",)),
    "cloud_longwave_factor": (("surface_flux.longwave_down_w_m2",),
                              ("meteorology.longwave_down_w_m2",)),
    "a_RH": (("meteorology.dewpoint_c",),),
    "b_RH": (("meteorology.dewpoint_c",),),
}

SURFACE_DEFAULTS = {
    "shortwave_multiplier": (1.0, 0.1, 2.0),
    "longwave_multiplier": (1.0, 0.1, 2.0),
    "longwave_bias_w_m2": (0.0, -100.0, 100.0),
    "cloud_longwave_factor": (BudgetParams.cloud_longwave_factor,
                              0.0, 1.0),
    "a_RH": (1.0, 0.1, 2.0),
    "b_RH": (0.0, -0.3, 0.3),
}

Q_LAT_BOUNDS = (0.0, 10.0)
T_LAT_BOUNDS = (-5.0, 60.0)


from yellowstone_python.common.checks import finite


def _series_from(times_s: Sequence[float],
                 values: Sequence[float]) -> Series:
    """Build a Series starting at t=0 from a monotone epoch grid."""
    if not times_s:
        raise ValueError("times_s must be nonempty")
    t0 = float(times_s[0])
    rel = [float(t) - t0 for t in times_s]
    return Series(tuple(rel), tuple(float(v) for v in values))


def _bundle_channels(bundle: dict[str, Any]) -> dict[str, bool]:
    """Flag which hierarchy channels appear in the bundle, by dotted key."""
    sites = bundle.get("sites", {})
    met = bundle.get("met", {})
    hourly = met.get("hourly") if isinstance(met, dict) else None
    optional = met.get("optional", {}) if isinstance(met, dict) else {}
    flux = bundle.get("flux_station", {})
    present: dict[str, bool] = {}
    columns = len(hourly[0]) if hourly else 0
    present["meteorology.air_c"] = columns >= 2
    present["meteorology.rh"] = columns >= 3
    present["meteorology.wind_mps"] = columns >= 4
    present["meteorology.shortwave_w_m2"] = columns >= 5
    present["meteorology.station_shortwave_w_m2"] = (columns >= 5 and
        met.get("shortwave_source") in ("station", "station_data", "measured_station"))
    present["meteorology.cloud_fraction"] = columns >= 6
    present["meteorology.longwave_down_w_m2"] = bool(
        optional.get("longwave_down_w_m2"))
    present["meteorology.dewpoint_c"] = bool(optional.get("dewpoint_c"))
    present["meteorology.pressure_kpa"] = bool(optional.get("pressure_kpa"))
    up = sites.get(UPSTREAM_GAUGE, {}).get("series", {})
    down = sites.get(DOWNSTREAM_GAUGE, {}).get("series", {})
    present["hydraulics.upstream_discharge_m3_s"] = bool(
        up.get("discharge_m3_s"))
    present["hydraulics.downstream_discharge_m3_s"] = bool(
        down.get("discharge_m3_s"))
    present["hydraulics.stage_m"] = bool(up.get("stage_m")) or bool(
        down.get("stage_m"))
    present["hydraulics.velocity_m_s"] = bool(up.get("velocity_m_s")) or bool(
        down.get("velocity_m_s"))
    present["hydraulics.cross_section_m2"] = bool(
        up.get("cross_section_m2")) or bool(down.get("cross_section_m2"))
    present["water_temperature.upstream_temperature_c"] = bool(
        up.get("temperature_c"))
    present["water_temperature.downstream_temperature_c"] = bool(
        down.get("temperature_c"))
    present["water_temperature.intermediate_temperature_c"] = any(
        site_id not in (UPSTREAM_GAUGE, DOWNSTREAM_GAUGE)
        and bool(payload.get("series", {}).get("temperature_c"))
        for site_id, payload in sites.items())
    present["surface_flux.net_radiometer_w_m2"] = bool(flux.get("net"))
    present["surface_flux.longwave_down_w_m2"] = bool(
        flux.get("longwave_down"))
    present["surface_flux.sensible_w_m2"] = bool(flux.get("sensible"))
    present["surface_flux.latent_w_m2"] = bool(flux.get("latent"))
    return present


def observation_hierarchy_report(bundle: dict[str, Any]) -> dict[str, Any]:
    """Enumerate which obs channels the bundle carries, per hierarchy."""
    present = _bundle_channels(bundle)
    by_category: dict[str, dict[str, bool]] = {}
    for category, channels in OBSERVATION_HIERARCHY.items():
        by_category[category] = {
            name: present.get(f"{category}.{name}", False)
            for name in channels}
    identifiable: list[str] = []
    not_identifiable: dict[str, str] = {}
    for field, alternatives in SURFACE_IDENTIFIABILITY.items():
        satisfied = False
        for required in alternatives:
            if all(present.get(key, False) for key in required):
                satisfied = True
                break
        if satisfied:
            identifiable.append(field)
        else:
            needed = [list(alt) for alt in alternatives]
            not_identifiable[field] = (
                f"missing_any_of_channel_sets: {needed}")
    return {
        "by_category": by_category,
        "eligible_parameters_from_channels": identifiable,
        "ineligible_parameters_from_channels": not_identifiable,
        "identifiability": {"status": "unassessed", "reason": "channel_presence_only"},
    }


@dataclass(frozen=True)
class StageAResult:
    """Effective hydraulic geometry, status, and travel-time check."""

    volume_m3: float
    area_m2: float
    status: str
    travel_time_s_from_lag: float | None
    travel_time_s_from_geometry: float
    travel_time_relative_difference: float | None
    water_budget_closure_m3_s: float | None
    uncertainty: dict[str, Any]


def stage_a_hydraulics(bundle: dict[str, Any], volume_m3: float,
                       area_m2: float, dt_s: float = 900.0,
                       volume_sigma_frac: float = 0.2) -> StageAResult:
    """Stage A per effective volume_m3 and area_m2 with travel-time check."""
    volume_m3 = finite("volume_m3", volume_m3)
    area_m2 = finite("area_m2", area_m2)
    if volume_m3 <= 0.0:
        raise ValueError("volume_m3 must be positive")
    if area_m2 <= 0.0:
        raise ValueError("area_m2 must be positive")
    if not 0.0 < volume_sigma_frac < 1.0:
        raise ValueError("volume_sigma_frac must be in (0, 1)")
    sites = bundle.get("sites", {})
    up = sites.get(UPSTREAM_GAUGE, {}).get("series", {})
    down = sites.get(DOWNSTREAM_GAUGE, {}).get("series", {})
    up_t_pairs = up.get("temperature_c")
    up_q_pairs = up.get("discharge_m3_s")
    down_t_pairs = down.get("temperature_c")
    down_q_pairs = down.get("discharge_m3_s")
    if not up_q_pairs:
        raise ValueError("upstream discharge required for stage A")
    check_continuity(up_q_pairs, "upstream discharge", 3600.0)
    mean_q = math.fsum(v for _, v in up_q_pairs) / len(up_q_pairs)
    tau_geo = volume_m3 / mean_q if mean_q > 0.0 else math.inf
    tau_lag: float | None = None
    tau_rel: float | None = None
    if up_t_pairs and down_t_pairs:
        check_continuity(up_t_pairs, "upstream temperature", 3600.0)
        check_continuity(down_t_pairs, "downstream temperature", 3600.0)
        grid_t0 = max(up_t_pairs[0][0], down_t_pairs[0][0])
        grid_tN = min(up_t_pairs[-1][0], down_t_pairs[-1][0])
        if grid_tN - grid_t0 > 2.0 * dt_s:
            n = int((grid_tN - grid_t0) // dt_s)
            grid = [grid_t0 + i * dt_s for i in range(n + 1)]
            up_t = interp_series(up_t_pairs, grid)
            down_t = interp_series(down_t_pairs, grid)
            try:
                lag_info = estimate_lag(up_t, down_t, dt_s,
                                        max_lag_s=min(86400.0,
                                                      0.4 * (grid_tN -
                                                             grid_t0)))
                tau_lag = float(lag_info["lag_s"])
                if tau_geo > 0.0:
                    tau_rel = (tau_lag - tau_geo) / tau_geo
            except ValueError:
                tau_lag = None
    budget_closure: float | None = None
    if down_q_pairs:
        down_mean_q = math.fsum(v for _, v in down_q_pairs) / len(down_q_pairs)
        budget_closure = down_mean_q - mean_q
    status = "authored_or_measured_prior_not_fitted_against_temperature"
    if tau_rel is not None and abs(tau_rel) > 0.5:
        status = status + "; travel_time_check_flagged"
    uncertainty = {
        "method": "authored_prior_window",
        "volume_m3_sigma": volume_m3 * volume_sigma_frac,
        "volume_m3_window_1sigma": [
            volume_m3 * (1.0 - volume_sigma_frac),
            volume_m3 * (1.0 + volume_sigma_frac),
        ],
        "note": (
            "section 3: geometry stays as a prior in this stage; "
            "stage D sensitivity reports geometry leverage"),
    }
    return StageAResult(
        volume_m3=volume_m3,
        area_m2=area_m2,
        status=status,
        travel_time_s_from_lag=tau_lag,
        travel_time_s_from_geometry=tau_geo,
        travel_time_relative_difference=tau_rel,
        water_budget_closure_m3_s=budget_closure,
        uncertainty=uncertainty,
    )


@dataclass(frozen=True)
class StageBResult:
    """Dispersion identifiability for the lumped single-cell model."""

    dispersion_m2_s: float | None
    status: str
    reason: str
    uncertainty: dict[str, Any]


def stage_b_dispersion(bundle: dict[str, Any],
                       stage_a: StageAResult) -> StageBResult:
    """Stage B per lumped single-cell; dispersion reported as not identified."""
    tracer = bundle.get("tracer_pulse")
    if tracer:
        return StageBResult(
            dispersion_m2_s=None, status="deferred",
            reason=("tracer_pulse channel present; multi-cell dispersion "
                    "fit requires a channel-geometry pipeline the "
                    "lumped calibrator does not provide"),
            uncertainty={"method": "deferred_pending_multi_cell_pipeline"})
    _ = stage_a
    return StageBResult(
        dispersion_m2_s=None,
        status="not_identified_lumped_single_cell",
        reason=("The lumped single-cell reach model "
                "has no explicit dispersion coefficient. Use "
                "replay.calibrate.dispersion_sweep on a multi-cell "
                "channel to characterize solver fidelity."),
        uncertainty={"method": "not_applicable_single_cell"},
    )


@dataclass(frozen=True)
class StageCResult:
    """Fitted lateral discharge and lateral temperature with intervals."""

    q_lat: float
    t_lat: float
    train_rmse: float
    holdout_rmse: float
    method: str
    status: str
    uncertainty: dict[str, Any]
    c_mult: float = 1.0
    evaluated_model: dict[str, Any] = field(default_factory=dict)
    optimizer_attempts: list[dict[str, Any]] = field(default_factory=list)
    numerical_validity: str = "unavailable"


def _stage_c_grid(q_lat_grid: Sequence[float] | None,
                  t_lat_grid: Sequence[float] | None
                  ) -> tuple[list[float], list[float]]:
    q_grid = list(q_lat_grid) if q_lat_grid is not None else [
        1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    t_grid = list(t_lat_grid) if t_lat_grid is not None else [
        5.0, 15.0, 20.0, 25.0, 35.0, 50.0]
    for name, g in (("q_lat_grid", q_grid), ("t_lat_grid", t_grid)):
        if not g:
            raise ValueError(f"{name} must be nonempty")
        for v in g:
            finite(name, v)
    if min(q_grid) < 0:
        raise ValueError("Lateral discharge search bounds cannot be negative")
    return q_grid, t_grid


def stage_c_sources(bundle: dict[str, Any], stage_a: StageAResult,
                    q_lat_grid: Sequence[float] | None = None,
                    t_lat_grid: Sequence[float] | None = None,
                    dt_s: float = 900.0,
                    spinup_s: float = 86400.0,
                    train_frac: float = 0.7,
                    de_popsize: int = 8,
                    de_maxiter: int = 20,
                    de_seed: int = ENSEMBLE_SEED,
                    skip_de: bool = False,
                    skip_polish: bool = False,
                    tol_frac: float = 0.10,
                    min_members: int = 5,
                    band_level: float = DEFAULT_BAND_LEVEL,
                    n_bootstrap: int = DEFAULT_N_BOOTSTRAP) -> StageCResult:
    """Stage C per fits (q_lat, t_lat) at surface identity defaults (c_mult=1.0)."""
    from scipy.optimize import differential_evolution
    q_grid, t_grid = _stage_c_grid(q_lat_grid, t_lat_grid)
    grid_doc = reach_heat_fit(
        bundle, stage_a.volume_m3, stage_a.area_m2,
        lateral_q_grid=q_grid, lateral_t_grid=t_grid,
        c_mult_grid=[1.0], spinup_s=spinup_s, train_frac=train_frac,
        dt_s=dt_s, return_all=True)
    champ = grid_doc["champion"]
    if not candidate_numerically_valid(champ):
        raise ValueError("Stage C has no numerically valid grid candidate")
    best_q = float(champ["q_lat"])
    best_t = float(champ["t_lat"])
    best_train = float(champ["train_rmse"])
    best_holdout = float(champ["holdout_rmse"])
    method = "grid"
    attempts = []
    bounds = [(min(q_grid), max(q_grid)), (min(t_grid), max(t_grid))]
    down = bundle["sites"][DOWNSTREAM_GAUGE]["series"]
    probe = run_fit_forward(
        bundle, stage_a.volume_m3, stage_a.area_m2,
        best_q, best_t, 1.0, dt_s)
    grid = probe["grid"]
    target = interp_series(down["temperature_c"], grid)
    start = next(i for i, g in enumerate(grid) if g - grid[0] >= spinup_s)
    split = start + int((len(grid) - start) * train_frac)
    train = slice(start, split)
    holdout = slice(split, len(grid))
    train_target = target[train]
    if not skip_de:

        def rmse(x: Sequence[float]) -> float:
            fwd = run_fit_forward(
                bundle, stage_a.volume_m3, stage_a.area_m2,
                float(x[0]), float(x[1]), 1.0, dt_s)
            if not candidate_numerically_valid(fwd):
                return 1e12
            diffs = [m - t for m, t in zip(fwd["modeled_c"][train],
                                           train_target)]
            return math.sqrt(math.fsum(d * d for d in diffs) / len(diffs))

        de = differential_evolution(
            rmse, bounds, seed=de_seed, maxiter=de_maxiter,
            popsize=de_popsize, polish=False, init="halton", tol=1e-5)
        attempts.append({"method": "differential_evolution", "converged": bool(de.success),
                         "termination_reason": str(de.message), "nfev": int(de.nfev),
                         "effective_bounds": bounds})
        if de.success and de.fun < best_train:
            best_q = float(de.x[0])
            best_t = float(de.x[1])
            best_train = float(de.fun)
            method = "differential_evolution"
            fwd = run_fit_forward(bundle, stage_a.volume_m3,
                                  stage_a.area_m2, best_q, best_t, 1.0, dt_s)
            best_holdout = score_paired_series(
                fwd["modeled_c"][holdout], target[holdout])["rmse"]
    if not skip_polish:
        polished = least_squares_fit(
            bundle, stage_a.volume_m3, stage_a.area_m2,
            (best_q, best_t, 1.0), spinup_s=spinup_s,
            train_frac=train_frac, dt_s=dt_s,
            free_parameters=("q_lat", "t_lat"), frozen_parameters={"c_mult": 1.0},
            parameter_bounds={"q_lat": bounds[0], "t_lat": bounds[1]})
        attempts.append({"method": "least_squares", **polished["optimizer"],
                         "effective_bounds": polished["effective_bounds"], "nfev": polished["nfev"]})
        if polished["success"] and polished["budget_ok"] and polished["train_rmse"] < best_train:
            best_q = float(polished["q_lat"])
            best_t = float(polished["t_lat"])
            best_train = float(polished["train_rmse"])
            best_holdout = float(polished["holdout_rmse"])
            method = "least_squares_polish"
    final = run_fit_forward(bundle, stage_a.volume_m3, stage_a.area_m2,
                            best_q, best_t, 1.0, dt_s)
    if not candidate_numerically_valid(final):
        raise ValueError("Serialized Stage C model failed numerical checks")
    best_train = score_paired_series(final["modeled_c"][train], target[train])["rmse"]
    best_holdout = score_paired_series(final["modeled_c"][holdout], target[holdout])["rmse"]
    uncertainty = _stage_c_intervals(
        grid_doc["all_results"], best_train, tol_frac, min_members,
        band_level=band_level, n_bootstrap=n_bootstrap, seed=de_seed,
        bundle=bundle, stage_a=stage_a, dt_s=dt_s,
        spinup_s=spinup_s, train_frac=train_frac)
    return StageCResult(
        q_lat=best_q, t_lat=best_t, train_rmse=best_train,
        holdout_rmse=best_holdout, method=method,
        status="fitted_not_validated_single_window",
        uncertainty=uncertainty,
        c_mult=1.0, numerical_validity="passed", optimizer_attempts=attempts,
        evaluated_model={"parameters": {"q_lat": best_q, "t_lat": best_t, "c_mult": 1.0,
            "volume_m3": stage_a.volume_m3, "area_m2": stage_a.area_m2},
            "free_parameters": ["q_lat", "t_lat"], "frozen_parameters": {"c_mult": 1.0},
            "effective_bounds": {"q_lat": list(bounds[0]), "t_lat": list(bounds[1])},
            "forcing_sha256": sha256_json(bundle), "forcing_bundle": bundle,
            "numerical_policy": {"dt_s": dt_s, "spinup_s": spinup_s, "train_frac": train_frac}},
    )


def _stage_c_intervals(all_results: list[dict[str, Any]],
                       champion_train_rmse: float,
                       tol_frac: float, min_members: int,
                       *, band_level: float, n_bootstrap: int,
                       seed: int, bundle: dict[str, Any],
                       stage_a: StageAResult, dt_s: float,
                       spinup_s: float, train_frac: float
                       ) -> dict[str, Any]:
    """Ridge ensemble intervals for Stage C per."""
    from yellowstone_python.river.uncertainty import fit_masks, member_trajectories, ridge_members
    members = ridge_members(all_results, champion_train_rmse,
                            tol_frac=tol_frac, min_members=min_members)
    membership = {"requested_members": min_members, "n_members": len(members),
        "membership_rule": "numerical_validity_then_rmse_with_labeled_valid_topn_fallback",
        "fallback_used": any(member["fallback_member"] for member in members),
        "minimum_unavailable": len(members) < min_members,
        "members": members, "rejected_candidate_count": sum(not candidate_numerically_valid(row) for row in all_results)}
    if len(members) < 2:
        return {**membership, "status": "unavailable", "reason": "insufficient_valid_ensemble",
                "method": "authored_sensitivity_not_calibrated_predictive_intervals"}
    trajs = member_trajectories(
        bundle, stage_a.volume_m3, stage_a.area_m2, members, dt_s)
    members = trajs["members"]
    membership.update({"n_members": len(members), "members": members,
                       "rejected_forward_members": trajs["rejected_members"]})
    if len(members) < 2:
        return {**membership, "status": "unavailable", "reason": "insufficient_valid_forward_runs"}
    tail = (1.0 - band_level) / 2.0
    bands = ensemble_bands(trajs["trajectories"],
                           quantiles=(tail, 0.5, 1.0 - tail),
                           seed=seed, n_bootstrap=n_bootstrap)
    _, holdout = fit_masks(trajs["grid"], spinup_s, train_frac)
    down = bundle["sites"][DOWNSTREAM_GAUGE]["series"]
    target = interp_series(down["temperature_c"], trajs["grid"])
    coverage = band_coverage(bands["lo"][holdout], bands["hi"][holdout],
                             target[holdout])
    q_values = [float(m["q_lat"]) for m in members]
    t_values = [float(m["t_lat"]) for m in members]
    return {
        **membership,
        "status": "authored_sensitivity_not_calibrated_predictive_intervals",
        "method": "ridge_ensemble_with_bootstrap_band",
        "tol_frac": tol_frac,
        "n_members": len(members),
        "q_lat_quantiles": _quantile_triplet(q_values, tail, band_level),
        "t_lat_quantiles": _quantile_triplet(t_values, tail, band_level),
        "trajectory_band_width_mean_c": bands["band_width_mean"],
        "holdout_band_coverage": coverage["coverage"],
        "nominal_level": band_level,
        "ridge_rule": {"tol_frac": tol_frac,
                       "min_members": min_members},
    }


def _quantile_triplet(values: list[float], tail_lo: float,
                      band_level: float) -> dict[str, float]:
    """Lo/med/hi order statistics over a short ensemble."""
    import numpy as np
    arr = np.asarray(values, dtype=float)
    hi_q = 1.0 - tail_lo
    return {
        "lo": float(np.quantile(arr, tail_lo)),
        "median": float(np.quantile(arr, 0.5)),
        "hi": float(np.quantile(arr, hi_q)),
        "band_level": band_level,
    }


@dataclass(frozen=True)
class StageDResult:
    """Fitted BudgetParams, identifiability map, and intervals."""

    budget_params: dict[str, float]
    c_mult: float
    identified_fields: list[str]
    not_identified_fields: dict[str, str]
    train_rmse: float
    holdout_rmse: float
    status: str
    uncertainty: dict[str, Any]
    eligible_parameters_from_channels: list[str] = field(default_factory=list)
    estimated_parameters: list[str] = field(default_factory=list)
    identifiability: dict[str, Any] = field(default_factory=dict)
    optimizer: dict[str, Any] = field(default_factory=dict)
    objective: dict[str, Any] = field(default_factory=dict)
    numerical_validity: str = "unavailable"


def _stage_d_forward(arrays: dict[str, Any], volume_m3: float,
                     area_m2: float, q_lat: float, t_lat: float,
                     c_mult: float, params: BudgetParams,
                     dt_s: float, *, with_checks: bool = False) -> Any:
    """Forward lumped run with explicit BudgetParams and c_mult scaling."""
    met = arrays["met_series"]
    scaled = BudgetParams(
        albedo=params.albedo, emissivity=params.emissivity,
        c_h=BudgetParams.c_h * c_mult,
        c_e=BudgetParams.c_e * c_mult,
        pressure_kpa=params.pressure_kpa,
        shortwave_multiplier=params.shortwave_multiplier,
        longwave_multiplier=params.longwave_multiplier,
        longwave_bias_w_m2=params.longwave_bias_w_m2,
        cloud_longwave_factor=params.cloud_longwave_factor,
        a_RH=params.a_RH, b_RH=params.b_RH)
    cell = Cell(id="reach_lumped", length_m=1000.0,
                width_m=area_m2 / 1000.0, volume_m3=volume_m3,
                initial_c=arrays["up_t"][0],
                geometry_status=(
                    "authored_illustrative_effective_mixing_geometry"))
    surface_budget = {
        "rh": {"times_s": list(met["rh"].times_s),
               "values": list(met["rh"].values)},
        "wind_mps": {"times_s": list(met["wind_mps"].times_s),
                     "values": list(met["wind_mps"].values)},
        "shortwave_w_m2": {
            "times_s": list(met["sw"].times_s),
            "values": list(met["sw"].values)},
        "cloud": {"times_s": list(met["cloud"].times_s),
                  "values": list(met["cloud"].values)},
        "params": asdict(scaled),
    }
    river = River(
        [cell], boundary_m3_s=arrays["mean_q"],
        boundary_c=arrays["up_t_series"],
        sources=[Source(id="aggregate_lateral", cell_id="reach_lumped",
                        flow_m3_s=q_lat, temperature_c=t_lat,
                        status="fitted_not_validated")],
        air_c=met["air_c"],
        surface_budget=surface_budget,
    )
    n = len(arrays["grid"]) - 1
    frames = river.run(n * dt_s, dt_s=dt_s, sample_s=dt_s)
    temperatures = [f["temperature_c"][0] for f in frames]
    budget = river.budget()
    if with_checks:
        return {"modeled_c": temperatures, "budget_ok": bool(budget["heat_relative_residual"] <= 1e-5
                and budget.get("surface_iteration_failures", 0) == 0), "budget": budget}
    return temperatures


from yellowstone_python.river.calibrate import fit_forcing_arrays


def stage_d_surface(bundle: dict[str, Any], stage_a: StageAResult,
                    stage_c: StageCResult,
                    identifiable: Sequence[str] | None = None,
                    not_identifiable: dict[str, str] | None = None,
                    dt_s: float = 900.0,
                    spinup_s: float = 86400.0,
                    train_frac: float = 0.7,
                    c_mult_bounds: tuple[float, float] = (0.0, 8.0),
                    lhs_samples: int = 24,
                    lhs_seed: int = ENSEMBLE_SEED,
                    band_level: float = DEFAULT_BAND_LEVEL,
                    n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
                    tol_frac: float = 0.10,
                    min_members: int = 5,
                    skip_polish: bool = False) -> StageDResult:
    """Stage D per fits c_mult plus identifiable BudgetParams fields."""
    import numpy as np
    from scipy.optimize import least_squares
    report = observation_hierarchy_report(bundle)
    identifiable = list(identifiable) if identifiable is not None else list(
        report["eligible_parameters_from_channels"])
    not_identifiable = dict(not_identifiable) if not_identifiable is not None \
        else dict(report["ineligible_parameters_from_channels"])
    if len(set(identifiable)) != len(identifiable) or set(identifiable) - set(SURFACE_DEFAULTS):
        raise ValueError("Unknown or duplicate eligible surface parameters")
    arrays = fit_forcing_arrays(bundle, dt_s)
    grid = arrays["grid"]
    down = bundle["sites"][DOWNSTREAM_GAUGE]["series"]
    target = interp_series(down["temperature_c"], grid)
    start = next(i for i, g in enumerate(grid) if g - grid[0] >= spinup_s)
    split = start + int((len(grid) - start) * train_frac)
    train = slice(start, split)
    holdout = slice(split, len(grid))
    train_target = np.asarray(target[train])
    knob_names = ["c_mult"] + list(identifiable)
    knob_defaults = {"c_mult": 1.0}
    knob_bounds = {"c_mult": c_mult_bounds}
    for name in identifiable:
        default, lo, hi = SURFACE_DEFAULTS[name]
        knob_defaults[name] = default
        knob_bounds[name] = (lo, hi)
    x0 = [knob_defaults[n] for n in knob_names]

    def params_from(x: Sequence[float]) -> tuple[float, BudgetParams]:
        c_mult = float(x[0])
        overrides: dict[str, float] = {}
        for i, name in enumerate(identifiable, start=1):
            overrides[name] = float(x[i])
        base = asdict(BudgetParams())
        base.update(overrides)
        return c_mult, BudgetParams(**base)

    def residuals(x: Sequence[float]) -> np.ndarray:
        c_mult, params = params_from(x)
        forward = _stage_d_forward(
            arrays, stage_a.volume_m3, stage_a.area_m2,
            stage_c.q_lat, stage_c.t_lat, c_mult, params, dt_s, with_checks=True)
        if not candidate_numerically_valid(forward):
            return np.full(len(train_target), 1e12)
        return np.asarray(forward["modeled_c"][train]) - train_target

    lower = [knob_bounds[name][0] for name in knob_names]
    upper = [knob_bounds[name][1] for name in knob_names]
    if any(not math.isfinite(lo) or not math.isfinite(hi) or lo >= hi for lo, hi in zip(lower, upper)):
        raise ValueError("Surface fit bounds must be finite and strictly ordered")
    if lower[0] < 0:
        raise ValueError("Surface multiplier bounds cannot be negative")
    x0 = [value if lo <= value <= hi else (lo + hi) / 2 for value, lo, hi in zip(x0, lower, upper)]
    best_x = list(x0)
    method = "identity_defaults"
    optimizer = {"converged": None, "termination_reason": "not_requested"}
    if not skip_polish:
        result = least_squares(residuals, x0, bounds=(lower, upper),
                               max_nfev=max(30, 6 * len(x0)))
        best_x = [float(v) for v in result.x]
        method = "least_squares"
        optimizer = {"converged": bool(result.success), "termination_reason": str(result.message),
                     "termination_code": int(result.status), "nfev": int(result.nfev),
                     "active_bounds": dict(zip(knob_names, map(int, result.active_mask)))}
    from yellowstone_python.river.identifiability import conditioning
    spans = np.asarray(upper) - np.asarray(lower)
    columns = []
    for index, span in enumerate(spans):
        left, right = np.array(best_x), np.array(best_x)
        delta = max(1e-7, 1e-5 * span)
        left[index] = max(lower[index], left[index] - delta)
        right[index] = min(upper[index], right[index] + delta)
        columns.append((residuals(right) - residuals(left)) / (right[index] - left[index]) * span)
    condition = conditioning(np.column_stack(columns), rank_tol=1e-6, param_names=knob_names)
    full_rank = condition["rank"] == len(knob_names)
    condition.update({"status": "locally_full_rank" if full_rank else "locally_confounded",
        "column_scaling": "effective_parameter_bound_span", "scope": "local_temperature_objective_jacobian; global and field identifiability unassessed"})
    c_mult_hat, params_hat = params_from(best_x)
    final_forward = _stage_d_forward(
        arrays, stage_a.volume_m3, stage_a.area_m2,
        stage_c.q_lat, stage_c.t_lat, c_mult_hat, params_hat, dt_s, with_checks=True)
    if not candidate_numerically_valid(final_forward):
        raise ValueError("Final surface fit failed numerical checks")
    modeled_full = final_forward["modeled_c"]
    train_score = score_paired_series(modeled_full[train], target[train])
    holdout_score = score_paired_series(modeled_full[holdout],
                                        target[holdout])
    best_train = float(train_score["rmse"])
    holdout_rmse = float(holdout_score["rmse"])
    uncertainty = _stage_d_intervals(
        arrays, stage_a, stage_c, knob_names, lower, upper,
        best_train, lhs_samples=lhs_samples, lhs_seed=lhs_seed,
        band_level=band_level, n_bootstrap=n_bootstrap,
        tol_frac=tol_frac, min_members=min_members,
        train=train, holdout=holdout, target=target, dt_s=dt_s)
    return StageDResult(
        budget_params=asdict(params_hat),
        c_mult=c_mult_hat,
        identified_fields=list(identifiable) if full_rank and optimizer.get("converged") else [],
        not_identified_fields={**not_identifiable, **({name: "local_objective_confounded_or_not_converged" for name in identifiable}
                                                     if not full_rank or not optimizer.get("converged") else {})},
        train_rmse=best_train,
        holdout_rmse=holdout_rmse,
        status=("fitted_not_validated_single_window; "
                f"optimizer={method}"),
        uncertainty=uncertainty,
        eligible_parameters_from_channels=list(identifiable), estimated_parameters=knob_names,
        identifiability=condition, optimizer=optimizer,
        numerical_validity="passed",
        objective={"residual_channels": ["downstream_temperature_c"], "units": "C", "weight": 1.0,
                   "alignment": "shared_absolute_forcing_grid; training_window_only",
                   "other_channels_role": "parameter_eligibility_only; not direct objective constraints"},
    )


def _stage_d_intervals(arrays: dict[str, Any], stage_a: StageAResult,
                       stage_c: StageCResult, knob_names: list[str],
                       lower: list[float], upper: list[float],
                       champion_train_rmse: float,
                       *, lhs_samples: int, lhs_seed: int,
                       band_level: float, n_bootstrap: int,
                       tol_frac: float, min_members: int,
                       train: slice, holdout: slice,
                       target: list[float],
                       dt_s: float) -> dict[str, Any]:
    """Latin hypercube ensemble bands over the fitted knobs."""
    import numpy as np
    from scipy.stats import qmc
    sampler = qmc.LatinHypercube(d=len(knob_names), seed=lhs_seed)
    samples = qmc.scale(sampler.random(n=max(min_members, lhs_samples)),
                        lower, upper)
    train_target = np.asarray(target[train])
    rows: list[dict[str, Any]] = []
    for row in samples:
        c_mult = float(row[0])
        overrides: dict[str, float] = {}
        for i, name in enumerate(knob_names[1:], start=1):
            overrides[name] = float(row[i])
        base = asdict(BudgetParams())
        base.update(overrides)
        params = BudgetParams(**base)
        forward = _stage_d_forward(
            arrays, stage_a.volume_m3, stage_a.area_m2,
            stage_c.q_lat, stage_c.t_lat, c_mult, params, dt_s, with_checks=True)
        modeled = forward["modeled_c"]
        diffs = np.asarray(modeled[train]) - train_target
        rmse = float(math.sqrt(float(np.dot(diffs, diffs)) /
                               max(1, len(diffs))))
        rows.append({"x": [float(v) for v in row], "train_rmse": rmse,
                     "modeled": modeled, "budget_ok": candidate_numerically_valid(forward)})
    rows.sort(key=lambda r: r["train_rmse"])
    rejected = [row for row in rows if not candidate_numerically_valid(row)]
    rows = [row for row in rows if candidate_numerically_valid(row)]
    cutoff = champion_train_rmse * (1.0 + tol_frac)
    members = [r for r in rows if r["train_rmse"] <= cutoff]
    fallback = False
    if len(members) < min_members:
        members = rows[:min_members]
        fallback = True
    if len(members) < 2:
        return {"status": "unavailable", "reason": "insufficient_valid_ensemble", "n_members": len(members),
                "requested_members": min_members, "rejected_numerical_candidates": rejected,
                "fallback_to_topn": fallback}
    member_trajs = [m["modeled"] for m in members]
    tail = (1.0 - band_level) / 2.0
    bands = ensemble_bands(member_trajs, quantiles=(tail, 0.5, 1.0 - tail),
                           seed=lhs_seed, n_bootstrap=n_bootstrap)
    coverage = band_coverage(bands["lo"][holdout], bands["hi"][holdout],
                             target[holdout])
    per_param: dict[str, dict[str, float]] = {}
    arr = np.asarray([m["x"] for m in members], dtype=float)
    for i, name in enumerate(knob_names):
        values = arr[:, i].tolist()
        per_param[name] = _quantile_triplet(values, tail, band_level)
    return {
        "method": "latin_hypercube_prior_with_ridge_filter",
        "status": "authored_sensitivity_not_calibrated_predictive_intervals",
        "n_samples": len(rows),
        "n_members": len(members),
        "fallback_to_topn": fallback,
        "requested_members": min_members, "minimum_unavailable": len(members) < min_members,
        "rejected_numerical_candidates": rejected,
        "membership_rule": "numerical_validity_then_rmse_with_labeled_valid_topn_fallback",
        "members": [{"parameters": dict(zip(knob_names, row["x"])), "budget_ok": True,
                     "inclusion_reason": "valid_within_tolerance" if row["train_rmse"] <= cutoff else "valid_topn_outside_tolerance"}
                    for row in members],
        "ridge_rule": {"tol_frac": tol_frac,
                       "min_members": min_members},
        "band_level": band_level,
        "trajectory_band_width_mean_c": bands["band_width_mean"],
        "holdout_band_coverage": coverage["coverage"],
        "per_param_quantiles": per_param,
    }


@dataclass(frozen=True)
class StagedConfig:
    """Staged calibrator configuration."""

    volume_m3: float
    area_m2: float
    dt_s: float = 900.0
    spinup_s: float = 86400.0
    train_frac: float = 0.7
    q_lat_grid: tuple[float, ...] | None = None
    t_lat_grid: tuple[float, ...] | None = None
    skip_de: bool = False
    skip_polish_c: bool = False
    skip_polish_d: bool = False
    lhs_samples: int = 24
    seed: int = ENSEMBLE_SEED
    band_level: float = DEFAULT_BAND_LEVEL
    tol_frac: float = 0.10
    min_members: int = 5
    n_bootstrap: int = DEFAULT_N_BOOTSTRAP


def _result_to_dict(result: Any) -> dict[str, Any]:
    """asdict for a frozen dataclass stage result."""
    if hasattr(result, "__dataclass_fields__"):
        return asdict(result)
    return dict(result)


def run_staged(bundle: dict[str, Any],
               config: StagedConfig) -> dict[str, Any]:
    """Run stages A through D and assemble the staged document."""
    if bundle.get("schema") != "yellowstone.firehole_obs.v1":
        raise ValueError("obs bundle has wrong schema")
    report = observation_hierarchy_report(bundle)
    stage_a = stage_a_hydraulics(
        bundle, config.volume_m3, config.area_m2, dt_s=config.dt_s)
    stage_b = stage_b_dispersion(bundle, stage_a)
    stage_c = stage_c_sources(
        bundle, stage_a,
        q_lat_grid=list(config.q_lat_grid) if config.q_lat_grid else None,
        t_lat_grid=list(config.t_lat_grid) if config.t_lat_grid else None,
        dt_s=config.dt_s, spinup_s=config.spinup_s,
        train_frac=config.train_frac,
        de_seed=config.seed, skip_de=config.skip_de,
        skip_polish=config.skip_polish_c,
        tol_frac=config.tol_frac, min_members=config.min_members,
        band_level=config.band_level, n_bootstrap=config.n_bootstrap)
    stage_d = stage_d_surface(
        bundle, stage_a, stage_c,
        identifiable=report["eligible_parameters_from_channels"],
        not_identifiable=report["ineligible_parameters_from_channels"],
        dt_s=config.dt_s, spinup_s=config.spinup_s,
        train_frac=config.train_frac,
        lhs_samples=config.lhs_samples, lhs_seed=config.seed,
        band_level=config.band_level, n_bootstrap=config.n_bootstrap,
        tol_frac=config.tol_frac, min_members=config.min_members,
        skip_polish=config.skip_polish_d)
    champ_params = BudgetParams(
        **{k: v for k, v in stage_d.budget_params.items()
           if k in BUDGET_PARAM_KEYS})
    scaled = BudgetParams(
        **{**asdict(champ_params),
           "c_h": BudgetParams.c_h * stage_d.c_mult,
           "c_e": BudgetParams.c_e * stage_d.c_mult})
    status_overrides = {"c_h": "scaled_by_calibration",
                        "c_e": "scaled_by_calibration"}
    for name in stage_d.identified_fields:
        status_overrides[name] = "fitted_not_validated_single_window"
    for name in stage_d.not_identified_fields:
        status_overrides[name] = "not_identified_by_current_observations"
    surface_model = describe_surface_model(scaled,
                                           status_overrides=status_overrides)
    document = {
        "schema": SCHEMA_STAGED,
        "status": "fitted_not_validated_single_window",
        "fetched_at_utc": bundle.get("fetched_at_utc"),
        "fit_schema_source": SCHEMA_FIT,
        "stage_plan": [
            {"id": sid, "name": name, "intent": intent}
            for sid, name, intent in STAGE_PLAN
        ],
        "observation_hierarchy": {
            "categories": OBSERVATION_HIERARCHY,
            "report": report,
        },
        "sequence": _recommended_sequence(),
        "effective_geometry": {
            "volume_m3": config.volume_m3,
            "area_m2": config.area_m2,
            "surface_area_m2": config.area_m2,
            "status": stage_a.status,
        },
        "stage_a": _result_to_dict(stage_a),
        "stage_b": _result_to_dict(stage_b),
        "stage_c": _result_to_dict(stage_c),
        "stage_d": _result_to_dict(stage_d),
        "surface_model": surface_model,
        "config": {
            "dt_s": config.dt_s, "spinup_s": config.spinup_s,
            "train_frac": config.train_frac,
            "seed": config.seed, "band_level": config.band_level,
            "tol_frac": config.tol_frac,
            "min_members": config.min_members,
            "n_bootstrap": config.n_bootstrap,
            "lhs_samples": config.lhs_samples,
        },
    }
    return document


def _recommended_sequence() -> list[str]:
    """"""
    return [
        "Fit effective geometry against stage and discharge.",
        "Fit Manning roughness against velocity or travel time.",
        "Fit dispersion using tracer or thermal-pulse width.",
        "Fit source mixing and source temperatures.",
        "Fit effective exchange c_mult during periods of weak "
        "radiation uncertainty.",
        "Add explicit radiation budget.",
        "Fit radiation correction factors when a radiometer is available.",
        "Fit turbulent transfer multipliers when flux observations exist.",
        "Validate against held-out weather events.",
        "Quantify uncertainty with ensemble intervals.",
    ]


from yellowstone_python.common.io import write_json_atomic as _write_json


def write_stage_files(document: dict[str, Any],
                      stage_dir: Path) -> dict[str, Path]:
    """Write per-stage artifacts to stage_dir and return their paths."""
    paths: dict[str, Path] = {}
    for sid, _name, _intent in STAGE_PLAN:
        key = f"stage_{sid.lower()}"
        payload = {
            "schema": f"{SCHEMA_STAGED}.{key}",
            "status": document["status"],
            "stage_id": sid,
            "result": document[key],
        }
        path = stage_dir / f"stage_{sid.lower()}.json"
        _write_json(path, payload)
        paths[sid] = path
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stage-dir", type=Path, required=False,
                        help="per-stage artifacts; defaults next to --out")
    parser.add_argument("--volume-m3", type=float, required=True)
    parser.add_argument("--area-m2", type=float, required=True)
    parser.add_argument("--dt-s", type=float, default=900.0)
    parser.add_argument("--spinup-s", type=float, default=86400.0)
    parser.add_argument("--train-frac", type=float, default=0.7)
    parser.add_argument("--q-lat", type=float, nargs="+", default=None)
    parser.add_argument("--t-lat", type=float, nargs="+", default=None)
    parser.add_argument("--skip-de", action="store_true")
    parser.add_argument("--skip-polish-c", action="store_true")
    parser.add_argument("--skip-polish-d", action="store_true")
    parser.add_argument("--lhs-samples", type=int, default=24)
    parser.add_argument("--seed", type=int, default=ENSEMBLE_SEED)
    parser.add_argument("--band-level", type=float,
                        default=DEFAULT_BAND_LEVEL)
    parser.add_argument("--tol-frac", type=float, default=0.10)
    parser.add_argument("--min-members", type=int, default=5)
    parser.add_argument("--n-bootstrap", type=int,
                        default=DEFAULT_N_BOOTSTRAP)
    args = parser.parse_args(argv)
    try:
        bundle = json.loads(args.obs.read_text(encoding="utf-8"))
        config = StagedConfig(
            volume_m3=args.volume_m3, area_m2=args.area_m2,
            dt_s=args.dt_s, spinup_s=args.spinup_s,
            train_frac=args.train_frac,
            q_lat_grid=tuple(args.q_lat) if args.q_lat else None,
            t_lat_grid=tuple(args.t_lat) if args.t_lat else None,
            skip_de=args.skip_de,
            skip_polish_c=args.skip_polish_c,
            skip_polish_d=args.skip_polish_d,
            lhs_samples=args.lhs_samples, seed=args.seed,
            band_level=args.band_level,
            tol_frac=args.tol_frac, min_members=args.min_members,
            n_bootstrap=args.n_bootstrap,
        )
        document = run_staged(bundle, config)
        _write_json(args.out, document)
        stage_dir = args.stage_dir or args.out.parent / (
            args.out.stem + "_stages")
        write_stage_files(document, stage_dir)
    except (ValueError, KeyError, ArithmeticError, OSError) as error:
        parser.exit(2, f"staged calibration failed: {error}\n")
    print(f"stage A: volume={document['stage_a']['volume_m3']:.0f} m3, "
          f"area={document['stage_a']['area_m2']:.0f} m2, "
          f"status={document['stage_a']['status']}")
    print(f"stage B: {document['stage_b']['status']}")
    sc = document["stage_c"]
    print(f"stage C: Q_lat={sc['q_lat']:.3f} T_lat={sc['t_lat']:.3f} "
          f"({sc['method']}): train RMSE {sc['train_rmse']:.3f} C "
          f"holdout RMSE {sc['holdout_rmse']:.3f} C")
    sd = document["stage_d"]
    identified = sd["identified_fields"]
    print(f"stage D: c_mult={sd['c_mult']:.3f}; "
          f"identified={identified or 'none beyond c_mult'}; "
          f"not_identified={sorted(sd['not_identified_fields'])}; "
          f"train RMSE {sd['train_rmse']:.3f} C "
          f"holdout RMSE {sd['holdout_rmse']:.3f} C")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
