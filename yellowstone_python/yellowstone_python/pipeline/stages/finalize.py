"""Finalize simulation stage."""
from __future__ import annotations

from yellowstone_python.pipeline.shared import merge_fragments, validate_for_godot

READS = ('act0', 'air0', 'aquatic_foodweb', 'baseflow_m3s', 'baseline', 'benthic_grid', 'boundary_m3s', 'budget_mode_source', 'bundle_select_epoch_s', 'bundle_select_mode', 'bundle_window_check', 'canopy_input', 'canopy_source', 'catchment', 'chloride_validation_bound', 'clock_info', 'corridor', 'cross_sections_report', 'energy_budget_choice', 'et_ledger', 'excelsior_override', 'fh_chainage', 'fh_membership', 'fh_offset', 'firehole', 'flowering', 'grazer_blockers', 'ground_heat_field', 'hcfg', 'hour0', 'hydro_ledger', 'met_bundle', 'met_bundle_source', 'met_path', 'outflow_chain', 'overland_field', 'overland_rain_source', 'overland_runoff_m3_s', 'oxygen_doc', 'patches0', 'patches1', 'patches2', 'periphyton_doc', 'piscivore_reports', 'prey_ledger', 'prop_cfg', 'prop_violations', 'proposals', 'reaches_in', 'replay_doc', 'review_log', 'river_shading_doc', 'river_state', 'run_mode_norm', 'scfg', 'season', 'shells', 'sim_s', 'snow_days', 'snow_ledger', 'soil_t_by_patch', 'solute_doc', 'steam_report', 'substrate_failures', 'tfns', 'thermal_by_patch', 'trout_blockers', 'trout_hydraulics_source', 'trout_position_authority', 'veg_ledger', 'weather_frag', 'weather_provenance', 'wildlife1', 'wildlife2', 'wildlife3', 'wind_mag', 'wind_trace', 'world_root', 'mammal_doc', 'wildlife_mammals', 'mammal_settings', 'mammal_encounters', 'mammal_catalogue')
WRITES = ('result',)

def run(state: dict, cfg: dict) -> dict:
    """Advance the finalize stage and return its state."""
    act0 = state['act0']
    air0 = state['air0']
    aquatic_foodweb = state['aquatic_foodweb']
    baseflow_m3s = state['baseflow_m3s']
    baseline = state['baseline']
    benthic_grid = state['benthic_grid']
    boundary_m3s = state['boundary_m3s']
    budget_mode_source = state['budget_mode_source']
    bundle_select_epoch_s = state['bundle_select_epoch_s']
    bundle_select_mode = state['bundle_select_mode']
    bundle_window_check = state['bundle_window_check']
    canopy_input = state['canopy_input']
    canopy_source = state['canopy_source']
    catchment = state['catchment']
    chloride_validation_bound = state['chloride_validation_bound']
    clock_info = state['clock_info']
    corridor = state['corridor']
    cross_sections_report = state['cross_sections_report']
    energy_budget_choice = state['energy_budget_choice']
    et_ledger = state['et_ledger']
    excelsior_override = state['excelsior_override']
    fh_chainage = state['fh_chainage']
    fh_membership = state['fh_membership']
    fh_offset = state['fh_offset']
    firehole = state['firehole']
    flowering = state['flowering']
    grazer_blockers = state['grazer_blockers']
    ground_heat_field = state['ground_heat_field']
    hcfg = state['hcfg']
    hour0 = state['hour0']
    hydro_ledger = state['hydro_ledger']
    met_bundle = state['met_bundle']
    met_bundle_source = state['met_bundle_source']
    met_path = state['met_path']
    outflow_chain = state['outflow_chain']
    overland_field = state['overland_field']
    overland_rain_source = state['overland_rain_source']
    overland_runoff_m3_s = state['overland_runoff_m3_s']
    oxygen_doc = state['oxygen_doc']
    patches0 = state['patches0']
    patches1 = state['patches1']
    patches2 = state['patches2']
    periphyton_doc = state['periphyton_doc']
    piscivore_reports = state['piscivore_reports']
    prey_ledger = state['prey_ledger']
    prop_cfg = state['prop_cfg']
    prop_violations = state['prop_violations']
    proposals = state['proposals']
    reaches_in = state['reaches_in']
    replay_doc = state['replay_doc']
    review_log = state['review_log']
    river_shading_doc = state['river_shading_doc']
    river_state = state['river_state']
    run_mode_norm = state['run_mode_norm']
    scfg = state['scfg']
    season = state['season']
    shells = state['shells']
    sim_s = state['sim_s']
    snow_days = state['snow_days']
    snow_ledger = state['snow_ledger']
    soil_t_by_patch = state['soil_t_by_patch']
    solute_doc = state['solute_doc']
    steam_report = state['steam_report']
    substrate_failures = state['substrate_failures']
    tfns = state['tfns']
    thermal_by_patch = state['thermal_by_patch']
    trout_blockers = state['trout_blockers']
    trout_hydraulics_source = state['trout_hydraulics_source']
    trout_position_authority = state['trout_position_authority']
    veg_ledger = state['veg_ledger']
    weather_frag = state['weather_frag']
    weather_provenance = state['weather_provenance']
    wildlife1 = state['wildlife1']
    wildlife2 = state['wildlife2']
    wildlife3 = state['wildlife3']
    wind_mag = state['wind_mag']
    wind_trace = state['wind_trace']
    world_root = state['world_root']
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

    # Merge variant.
    variant = merge_fragments(baseline, river_state,
                              {k: v for k, v in weather_frag.items()
                               if k in ("night_air_c", "day_warming_c",
                                        "wind_xz_mps", "gust_mps",
                                        "humidity", "cloud")},
                              clock_hour=hour0,
                              boundary_m3s=boundary_m3s,
                              boundary_c=float(hcfg.get(
                                  "boundary_c", baseline["boundary_c"])))
    variant["patches"] = patches2
    variant["wildlife"] = state["wildlife_mammals"]
    variant["mammals"] = state["mammal_settings"]
    variant["mammal_initial_state"] = state["mammal_doc"]
    from yellowstone_python.exporters.runtime_series import python_series
    variant["python_series"] = python_series(replay_doc, reaches_in, patches2, weather_frag,
        mammals=state["mammal_settings"], actors=state["wildlife_mammals"],
        thermal_flux_mm_d_by_patch=state["thermal_by_patch"])
    variant["simulation_epoch_unix"] = replay_doc["simulation_time"]["start_epoch_unix"]
    variant["run_mode"] = run_mode_norm
    variant["river_model"] = "river.river_transport"
    variant["thermal_curve_form"] = cfg.get("fish", {}).get("thermal_curve_form", "piecewise_linear")
    godot_errors = validate_for_godot(variant)

    timeline = {
        "t0": "identified initial state after snow/soil spin-up",
        "spinup_interval_s": [-snow_days * 86400.0, 0.0],
        "experiment_interval_s": [0.0, float(replay_doc["frames"][-1]["t_s"])],
        "et_owner": "snow_soil_bucket",
        "reference_et_role": "diagnostic",
        "initial_state_preparation": {
            "patch_biomass_window_s": [-sim_s, 0.0],
            "patch_biomass_role": "authored initial-state preparation before snow/soil spin-up",
            "river_geometry_forcing_window_s": [0.0, sim_s],
            "river_geometry_forcing_role": "prescribed mean rates and diagnostic initialization",
            "overland_source_window_s": float(overland_field.get("seconds", cfg.get("overland", {}).get("sim_s", sim_s))),
        },
        "fast_window_s": sim_s,
        "fast_processes": ["river transport", "patch biomass",
                           "insect compartments", "trout refuge",
                           "grazer/bird timing"],
        "season_days": snow_days,
        "slow_processes": ["snowpack", "soil water", "phenology"],
        "wildlife_reference": ("timings from declared hydrology window; snow and soil spin-up precede experiment"),
    }
    result = {"hour0": hour0, "air0": air0, "sim_s": sim_s,
            "clock_info": clock_info, "season": season,
            "weather_frag": weather_frag, "wind_trace": wind_trace,
            "met_bundle": met_bundle, "weather_provenance": weather_provenance,
            "met_bundle_source": met_bundle_source,
            "met_bundle_path": str(met_path),
            "bundle_window_check": bundle_window_check,
            "river_state": river_state, "hydro_ledger": hydro_ledger,
            "replay_doc": replay_doc, "aquatic_foodweb": aquatic_foodweb,
            "shells": shells, "substrate_failures": substrate_failures,
            "patches1": patches1, "veg_ledger": veg_ledger,
            "proposals": proposals, "review_log": review_log,
            "prop_cfg": prop_cfg, "prop_violations": prop_violations,
            "act0": act0, "wind_mag": wind_mag, "flowering": flowering,
            "prey_ledger": prey_ledger, "wildlife1": wildlife1,
            "wildlife2": wildlife2, "trout_blockers": trout_blockers,
            "wildlife3": wildlife3, "grazer_blockers": grazer_blockers,
            "corridor": corridor, "patches2": patches2,
            "snow_ledger": snow_ledger, "scfg": scfg,
            "variant": variant, "godot_errors": godot_errors,
            "mammal_doc": state["mammal_doc"],
            "mammal_catalogue": state["mammal_catalogue"],
            "mammal_encounters": state["mammal_encounters"],
            "timeline": timeline, "tfns": tfns, "patches0": patches0,
            "overland_field": overland_field,
            "overland_runoff_m3_s": overland_runoff_m3_s,
            "overland_rain_source": overland_rain_source,
            "cross_sections_report": cross_sections_report,
            "benthic_grid": benthic_grid,
            "trout_hydraulics_source": trout_hydraulics_source,
            "firehole_points": firehole["points"],
            "fh_membership": fh_membership, "fh_chainage": fh_chainage,
            "fh_chainage_offset_m": fh_offset,
            "catchment": catchment, "baseflow_m3s": baseflow_m3s,
            "boundary_m3s": boundary_m3s,
            "snow_partition_source": "snow_season_air_c_threshold_1C",
            "canopy_source": canopy_source,
            "canopy_fraction_proposal": canopy_input,
            "bundle_select_mode": bundle_select_mode,
            "bundle_select_epoch_s": bundle_select_epoch_s,
            "trout_position_authority": trout_position_authority,
            "budget_mode_source": budget_mode_source,
            "energy_budget_choice": energy_budget_choice,
            "ground_heat_field": ground_heat_field,
            "thermal_by_patch": thermal_by_patch,
            "soil_t_by_patch": soil_t_by_patch,
            "et_ledger": et_ledger,
            "piscivore_reports": piscivore_reports,
            "steam_microclimate": steam_report,
            "river_shading_doc": river_shading_doc,
            "solute_doc": solute_doc,
            "oxygen_doc": oxygen_doc,
            "periphyton_doc": periphyton_doc,
            "chloride_validation_bound": chloride_validation_bound,
            "outflow_chain": outflow_chain,
            "excelsior_override": excelsior_override,
            "world_root": world_root}

    state.update({'result': result})
    return state
