"""Stages land build operations."""
from __future__ import annotations

from yellowstone_python.pipeline.shared import math, run_overland

def _compute_overland_field(world_root, cfg, olfg, scfg, met_bundle,
                            run_mode_norm, sim_s):
    """Run the overland solver using the configured rain source, or return a disabled stub."""
    if not olfg.get("enabled", False):
        return ({"schema": "yellowstone.overland_flow.v1",
                 "enabled": False,
                 "overland_flow_role": "diagnostic_not_wired_to_river",
                 "surface_runoff": {"nonzero_cells": 0,
                                    "max_depth_m": 0.0,
                                    "outflow_m3": 0.0,
                                    "carries_runoff_signal": False,
                                    "note": "module disabled; no field "
                                            "computed"},
                 "provenance": "overland disabled; set overland.enabled "
                               "true to compute it"},
                "disabled")
    bundle_precip = (met_bundle.get("precipitation_mm")
                     if isinstance(met_bundle, dict) else None)
    bundle_precip_ok = (isinstance(bundle_precip, list)
                        and len(bundle_precip) > 0)
    if "rain_mm_h" in olfg:
        rain_mm_h = float(olfg["rain_mm_h"])
        rain_source = "overland.rain_mm_h"
    elif (run_mode_norm in ("hindcast", "observed_replay")
          and bundle_precip_ok):
        samples = []
        for value in bundle_precip:
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(v) and v >= 0.0:
                samples.append(v)
        if not samples:
            raise ValueError(
                "overland rain source: met_bundle.precipitation_mm "
                "has no finite non-negative samples; set "
                "overland.rain_mm_h explicitly")
        rain_mm_h = sum(samples) / len(samples)
        rain_source = ("met_bundle.precipitation_mm mean over "
                       f"{len(samples)} hourly samples")
    elif run_mode_norm in ("hindcast", "observed_replay"):
        raise ValueError(
            "overland.rain_mm_h is required in run_mode "
            f"{run_mode_norm!r}; neither an explicit value nor a "
            "met_bundle.precipitation_mm array was available")
    else:
        precip_day = float(scfg.get("precip_mm_d", 2.0))
        rain_mm_h = precip_day / 24.0
        rain_source = ("snow.precip_mm_d converted to mm/h "
                       "(illustrative only)")
    field = run_overland(
        world_root,
        rain_mm_h=rain_mm_h,
        soil=str(olfg.get("soil", "sandy_loam")),
        dt_s=float(olfg.get("dt_s", 60.0)),
        sim_s=float(olfg.get("sim_s", sim_s)),
        grid=int(olfg.get("grid", 256)),
        cell_m=float(olfg.get("cell_m", 8.0)))
    field["rainfall_source"] = rain_source
    return field, rain_source


def _overland_runoff_to_boundary(overland_field, hcfg, sim_s) -> tuple:
    """Convert the overland outlet volume into a mean boundary discharge in m3/s."""
    surface = overland_field.get("surface_runoff", {})
    outflow_m3 = float(surface.get("outflow_m3", 0.0) or 0.0)
    carries = bool(surface.get("carries_runoff_signal", False))
    if not math.isfinite(outflow_m3) or outflow_m3 <= 0.0:
        return (0.0, {"status": "no_outflow",
                      "outflow_m3": outflow_m3,
                      "mean_rate_m3_s": 0.0,
                      "coupling": ("partial: contributing area not "
                                   "delineated; wire outlet runoff only "
                                   "when open_edges deliver outflow")})
    window_s = float(overland_field.get("seconds", overland_field.get("window_s", sim_s)))
    if not math.isfinite(window_s) or window_s <= 0.0:
        raise ValueError("overland outlet volume requires a positive source window")
    if not carries:
        raise ValueError("positive overland outflow requires a declared runoff signal")
    rate = outflow_m3 / window_s
    status = "wired_mean_rate" if carries else "wired_zero_signal"
    return (rate, {"status": status,
                   "outflow_m3": outflow_m3,
                   "window_s": window_s,
                   "river_window_s": float(sim_s),
                   "phase": "liquid",
                   "boundary_application": "uniform_mean_rate_on_source_window_only",
                   "mean_rate_m3_s": rate,
                   "contributing_area_m2": (hcfg.get("catchment", {}) or {})
                                             .get("area_m2"),
                   "coupling": ("partial: outlet volume divided by sim "
                                "window; contributing area not delineated "
                                "from terrain")})


def _overland_boundary_series(baseflow_m3_s, overland_field):
    """Route the source volume once over its declared integration support."""
    rate, report = _overland_runoff_to_boundary(overland_field, {}, 0.0)
    if rate == 0.0:
        return None
    return {"times_s": [0.0, report["window_s"]],
            "values": [float(baseflow_m3_s) + rate, float(baseflow_m3_s)]}


READS = ('_excluded', 'air0', 'clock_info', 'hcfg', 'met_bundle', 'patches1', 'run_mode_norm', 'shells', 'sim_s', 'wcfg', 'wind_mag', 'world_root')
WRITES = ('catchment', 'et_ledger', 'overland_field', 'overland_rain_source', 'overland_runoff_m3_s', 'patches2', 'runoff_m3_s', 'scfg', 'season', 'snow_days', 'snow_ledger', 'soil_t_by_patch', 'thermal_by_patch')

def run(state: dict, cfg: dict) -> dict:
    """Advance the land stage and return its state."""
    _excluded = state['_excluded']
    air0 = state['air0']
    clock_info = state['clock_info']
    hcfg = state['hcfg']
    met_bundle = state['met_bundle']
    patches1 = state['patches1']
    run_mode_norm = state['run_mode_norm']
    shells = state['shells']
    sim_s = state['sim_s']
    wcfg = state['wcfg']
    wind_mag = state['wind_mag']
    world_root = state['world_root']
    from yellowstone_python.land.snow_season import run_season, catchment_runoff_m3_s
    from yellowstone_python.thermal_features.ground_heat import soil_temperature_by_patch, thermal_flux_mm_d_by_patch
    from yellowstone_python.land.evapotranspiration import reference_et0_mm_d, CROP_COEFFICIENTS

    # --- season (before the river so its ledger reaches the boundary) ---
    scfg = cfg.get("snow", {})
    snow_days = int(scfg.get("days", 30))
    snow_air = scfg.get("air_c_by_day", [air0] * snow_days)
    # Per-patch geothermal melt flux feeds run_season; patches outside the thermal mask default to zero.
    thermal_by_patch = thermal_flux_mm_d_by_patch(patches1, shells)
    soil_t_by_patch = soil_temperature_by_patch(patches1, shells, air0)
    patches2, snow_ledger = run_season(
        patches1, days=snow_days, air_c_by_day=snow_air,
        precip_mm_d=float(scfg.get("precip_mm_d", 2.0)),
        thermal_test=_excluded,
        thermal_flux_mm_d_by_patch=thermal_by_patch,
        run_mode=run_mode_norm,
        air_hourly_c=(met_bundle.get("hourly") if met_bundle else None))
    season = clock_info["season"]  # explicit snow.season wins, else clock

    # Reference ET reports atmospheric demand; the soil bucket owns water loss.
    et_params = cfg.get("evapotranspiration", {}) or {}
    et_elev = float(et_params.get("site_elevation_m", 2200.0))
    et_rh_pct = float(wcfg.get("humidity", 0.45)) * 100.0
    et_rn = float(et_params.get("net_radiation_mj_m2_d", 10.0))
    et_tmax = air0 + float(wcfg.get("day_warming_c", 15.0)) * 0.5
    et_tmin = air0 - 1.0
    et_wind_u2 = max(0.1, wind_mag)
    et0_mm_d = reference_et0_mm_d(
        tmax_c=max(et_tmin + 0.1, et_tmax), tmin_c=et_tmin,
        rn_mj_m2_d=et_rn, g_mj_m2_d=0.0,
        u2_m_s=et_wind_u2, elevation_m=et_elev,
        rh_mean_pct=et_rh_pct)
    et_ledger = {"schema": "yellowstone.evapotranspiration.v1", "et0_mm_d": et0_mm_d,
                 "dt_days": 0.0, "total_et_mm": 0.0, "et_by_patch_mm": {},
                 "role": "diagnostic", "stock_owner": "snow_soil_bucket",
                 "interval_start_s": 0.0, "interval_end_s": 0.0,
                 "status": "authored_reference_diagnostic"}
    et_ledger["source_elevation_m"] = et_elev
    et_ledger.setdefault("coefficients_source", str(CROP_COEFFICIENTS))

    # --- snow runoff as a discharge increment over the basin ---
    catchment_area = hcfg.get("catchment", {}).get("area_m2")
    catchment = {"schema": "yellowstone.catchment_runoff.v1",
                 "enabled": catchment_area is not None,
                 "area_m2": catchment_area,
                 "status": "illustrative_not_calibrated",
                 "runoff_state_source":
                     "patches1_post_season_pre_final_output",
                 "boundary_application": {
                     "mode": "constant_scalar_increment",
                     "scientific_status": "illustrative",
                     "not_a_hydrograph": True}}
    if catchment_area is not None:
        runoff = catchment_runoff_m3_s(patches1, snow_ledger,
                                       catchment_area_m2=catchment_area)
        catchment.update(runoff)
    else:
        runoff = {"runoff_m3_s": 0.0}
        catchment["provenance"] = (
            "no catchment area configured; snow hydrology is storage-only "
            "and the river boundary stays at its prescribed baseflow")
    runoff_m3_s = float(runoff["runoff_m3_s"])
    catchment["snow_runoff_m3_s"] = runoff_m3_s

    # Overland flow runs before the river so its outlet runoff can reach the boundary.
    olfg = cfg.get("overland", {}) or {}
    overland_field, overland_rain_source = _compute_overland_field(
        world_root, cfg, olfg, scfg, met_bundle, run_mode_norm, sim_s)
    overland_runoff_m3_s, overland_runoff_report = _overland_runoff_to_boundary(
        overland_field, hcfg, sim_s)
    overland_field["overland_flow_role"] = (
        "wired_to_river_boundary" if overland_runoff_m3_s > 0.0
        else "diagnostic_not_wired_to_river")
    overland_field["boundary_contribution"] = overland_runoff_report


    state.update({'catchment': catchment, 'et_ledger': et_ledger, 'overland_field': overland_field, 'overland_rain_source': overland_rain_source, 'overland_runoff_m3_s': overland_runoff_m3_s, 'patches2': patches2, 'runoff_m3_s': runoff_m3_s, 'scfg': scfg, 'season': season, 'snow_days': snow_days, 'snow_ledger': snow_ledger, 'soil_t_by_patch': soil_t_by_patch, 'thermal_by_patch': thermal_by_patch})
    return state
