"""Stages weather build operations."""
from __future__ import annotations



def _check_met_window_covers_replay(hourly, start_epoch_s, duration_s) -> dict:
    """Report whether met_bundle.hourly rows span [start_epoch_s, start_epoch_s + duration_s]."""
    if not isinstance(hourly, list) or not hourly:
        return {"status": "no_hourly_rows"}
    epochs: list[float] = []
    for row in hourly:
        if isinstance(row, (list, tuple)) and row:
            try:
                epochs.append(float(row[0]))
            except (TypeError, ValueError):
                continue
    if not epochs:
        return {"status": "no_hourly_epochs"}
    start = float(start_epoch_s) if start_epoch_s is not None else None
    end = start + float(duration_s) if start is not None else None
    bundle_min = min(epochs)
    bundle_max = max(epochs)
    if start is None:
        return {"status": "no_simulation_start",
                "bundle_min_epoch": bundle_min,
                "bundle_max_epoch": bundle_max}
    if bundle_min <= start and bundle_max >= end:
        return {"status": "covers",
                "simulation_start_epoch": start,
                "simulation_end_epoch": end,
                "bundle_min_epoch": bundle_min,
                "bundle_max_epoch": bundle_max}
    return {"status": "window_not_covered",
            "simulation_start_epoch": start,
            "simulation_end_epoch": end,
            "bundle_min_epoch": bundle_min,
            "bundle_max_epoch": bundle_max}


from yellowstone_python.pipeline.shared import PKG_ROOT, Path, air_temp, default_world_root, math, normalize_run_mode, prevailing_direction, trace
from yellowstone_python.pipeline.stages.river import resolve_replay_start_epoch
from yellowstone_python.pipeline.stages.weather import _check_met_window_covers_replay

READS = ('baseline',)
WRITES = ('air0', 'bundle_select_epoch_s', 'bundle_select_mode', 'bundle_window_check', 'clock_info', 'hcfg', 'hour0', 'met_bundle', 'met_bundle_source', 'met_path', 'run_mode_norm', 'sim_s', 'wcfg', 'weather_frag', 'weather_provenance', 'wind_mag', 'wind_trace', 'world_root')

def run(state: dict, cfg: dict) -> dict:
    """Advance the weather stage and return its state."""
    baseline = state['baseline']
    from yellowstone_python.aquatic.fish import check_trout_clear_of_pools, update_trout
    from yellowstone_python.thermal_features.geochemistry import check_midway_shells
    from yellowstone_python.land.grazers import check_routes as check_grazer_routes, consumed_by_patch_from_grazers, plan_path, route_length as _rlen, update_grazers
    from yellowstone_python.insects_birds import (diets_with_aerial_insectivores, foraging_state,
                                insect_activity, step_compartments,
                                step_resource, update_wildlife,
                                update_wildlife_from_intake)
    from yellowstone_python.thermal_features.pool_crust import build_all as build_shells
    from yellowstone_python.thermal_features.pool_crust import exclusion_violations as apron_violations
    from yellowstone_python.thermal_features.pool_crust import in_apron as _in_apron
    from yellowstone_python.land.snow_season import resolve_game_clock, run_season
    from yellowstone_python.land.vegetation import patch_step, propose_plantings_reviewed
    from yellowstone_python.thermal_features.ground_heat import heat_flux_mask_field, soil_temperature_by_patch, thermal_flux_mm_d_by_patch, tree_thermal_suitability, LODGEPOLE_SOIL_DIEOFF_C
    from yellowstone_python.land.evapotranspiration import reference_et0_mm_d, step_patches_et, CROP_COEFFICIENTS
    from yellowstone_python.aquatic.piscivores import predation_over_refuge, TROUT_DENSITY_DEFAULT_PER_M2_WETTED, RIVER_WETTED_WIDTH_DEFAULT_M
    from yellowstone_python.atmosphere.steam_microclimate import plume_microclimate_adjustment, fog_present, rime_present
    from yellowstone_python.aquatic.river_oxygen import saturation_mg_l as do_saturation_mg_l, fish_suitability as do_fish_suitability

    from yellowstone_python.atmosphere.microclimate import load_weather_bundle, bundle_weather

    from yellowstone_python.atmosphere.microclimate import condensation_potential

    from yellowstone_python.land.snow_season import catchment_runoff_m3_s

    from yellowstone_python.exporters.runtime_series import reach_summaries

    from yellowstone_python.aquatic.aquatic_foodweb import run_foodweb as run_aquatic_foodweb

    from yellowstone_python.aquatic.aquatic_foodweb import thermal_landscape

    from yellowstone_python.aquatic.aquatic_foodweb import shear_to_disturbance

    from yellowstone_python.insects_birds import develop_benthic_grid

    from yellowstone_python.aquatic.fish import build_chainage, place_trout_at_chainage, reach_membership, reach_z_windows

    from yellowstone_python.land.grazers import route_length as _rlen

    from yellowstone_python.exporters.runtime_series import python_series

    world_root = Path(cfg.get("world_root") or default_world_root())
    run_mode_norm = normalize_run_mode(cfg.get("run_mode"))
    wcfg = dict(cfg.get("weather", {}))
    scfg_early = cfg.get("snow", {})
    clock_date = scfg_early.get("as_of_date")
    simulation = cfg.get("simulation", {})
    if clock_date is None and ("start_epoch_unix" in simulation or "start_utc" in simulation):
        import datetime
        epoch, _ = resolve_replay_start_epoch(cfg, cfg.get("clock_hour", baseline.get("clock_hour")))
        zone = datetime.timezone(datetime.timedelta(hours=simulation.get("utc_offset_hours", -6.0)))
        clock_date = datetime.datetime.fromtimestamp(epoch, zone).date().isoformat()
    clock_info = resolve_game_clock(
        season_cfg=scfg_early.get("season"),
        clock_cfg=cfg.get("clock_hour", baseline.get("clock_hour")),
        date_cfg=clock_date)
    hour0 = clock_info["clock_hour"]

    # Model-reanalysis bundle output wins over authored defaults when present; absent bundle keeps scenario values.
    from yellowstone_python.atmosphere.microclimate import load_weather_bundle, bundle_weather
    met_cfg_val = (cfg.get("weather", {}) or {}).get("met_bundle")
    if isinstance(met_cfg_val, str) and met_cfg_val:
        met_path = Path(met_cfg_val)
        if not met_path.is_absolute():
            met_path = PKG_ROOT / met_path
        met_bundle_source = "weather.met_bundle"
    else:
        met_path = PKG_ROOT / "derived" / "met.json"
        met_bundle_source = "default:derived/met.json"
    met_bundle = load_weather_bundle(str(met_path)) if wcfg.get("use_met_bundle", True) else None
    if not wcfg.get("use_met_bundle", True):
        met_bundle_source = "disabled_explicit_scenario_weather"
    bundle_select_epoch_s: float | None = None
    bundle_select_mode = "unused"
    bundle_window_check = {"status": "no_bundle"}
    if met_bundle:
        scfg_sim = cfg.get("simulation", {}) or {}
        if "start_epoch_unix" in scfg_sim or "start_utc" in scfg_sim:
            bundle_select_epoch_s, _ = resolve_replay_start_epoch(cfg, hour0)
            wcfg = {**wcfg,
                    **bundle_weather(met_bundle,
                                     epoch_s_utc=bundle_select_epoch_s)}
            bundle_select_mode = "simulation_start_epoch"
        else:
            import warnings as _warnings
            with _warnings.catch_warnings():
                _warnings.simplefilter("ignore", DeprecationWarning)
                wcfg = {**wcfg,
                        **bundle_weather(met_bundle, hour=hour0)}
            bundle_select_mode = "hour_offset_illustrative"
        # Replay-window coverage check: compare bundle hourly epoch range to the simulation window.
        hourly = met_bundle.get("hourly") if isinstance(met_bundle, dict) else None
        duration_s = float((cfg.get("replay", {}) or {}).get(
            "duration_s", 7200.0))
        bundle_window_check = _check_met_window_covers_replay(
            hourly, bundle_select_epoch_s, duration_s)
        if (run_mode_norm in ("hindcast", "observed_replay")
                and bundle_window_check["status"] != "covers"):
            raise ValueError(
                "met bundle does not cover the replay window in run_mode "
                f"{run_mode_norm!r}: {bundle_window_check}")
    weather_provenance = (
        {"source": "Open-Meteo",
         "role": "meteorological_model_forcing",
         "observation": False,
         "calibration_status": "not_calibrated_locally",
         "label": ("open-meteo hourly bundle; model reanalysis, not a "
                   "local measurement")}
        if met_bundle
        else {"source": "authored",
              "role": "authored_defaults",
              "observation": False,
              "calibration_status": "not_calibrated",
              "label": "authored defaults; no met bundle present"})

    air0 = air_temp(hour0, wcfg.get("night_air_c", 7.0),
                    wcfg.get("day_warming_c", 15.0),
                    wcfg.get("lag_hours", 3.0))
    wind_trace = trace(seconds=60, hour0=hour0,
                       wind_xz_mps=tuple(wcfg.get("wind_xz_mps", [1.8, 0.6])),
                       gust_mps=wcfg.get("gust_mps", 0.45),
                       night_air_c=wcfg.get("night_air_c", 7.0),
                       day_warming_c=wcfg.get("day_warming_c", 15.0),
                       humidity=wcfg.get("humidity", 0.45),
                       cloud=wcfg.get("cloud", 0.16),
                       lag_hours=wcfg.get("lag_hours", 3.0),
                       seed=int(cfg.get("wind_seed", 11)))
    from yellowstone_python.atmosphere.microclimate import condensation_potential
    weather_mode = ("absolute_scheduled_bundle" if met_bundle
                    else "synthetic_diurnal")
    weather_frag = {**wcfg,
                    "weather_provenance": weather_provenance,
                    "met_bundle": bool(met_bundle),
                    "forcing_mode": weather_mode,
                    "prevailing_deg": prevailing_direction(
                        tuple(wcfg.get("wind_xz_mps", [1.8, 0.6]))),
                    "air_c_at_start": air0,
                    "godot_weather_source": "Python frame and published trajectory reader"}
    wx, wz = weather_frag.get("wind_xz_mps", [1.8, 0.6])
    wind_mag = math.hypot(float(wx), float(wz))
    weather_frag["condensation_62C"] = condensation_potential(
        62.0, air0, wcfg.get("humidity", 0.45), wind_mag)

    hcfg = cfg.get("hydro", {})
    sim_s = float(hcfg.get("simulate_seconds", 600.0))


    state.update({'air0': air0, 'bundle_select_epoch_s': bundle_select_epoch_s, 'bundle_select_mode': bundle_select_mode, 'bundle_window_check': bundle_window_check, 'clock_info': clock_info, 'hcfg': hcfg, 'hour0': hour0, 'met_bundle': met_bundle, 'met_bundle_source': met_bundle_source, 'met_path': met_path, 'run_mode_norm': run_mode_norm, 'sim_s': sim_s, 'wcfg': wcfg, 'weather_frag': weather_frag, 'weather_provenance': weather_provenance, 'wind_mag': wind_mag, 'wind_trace': wind_trace, 'world_root': world_root})
    return state
