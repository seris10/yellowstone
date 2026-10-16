"""Stages foodweb build operations."""
from __future__ import annotations



def _predation_rate_by_cell(landscape):
    """Per-cell piscivore mortality rate (1/day) for the fish stressor path."""
    from yellowstone_python.aquatic.piscivores import refuge_predation_risk
    out: dict[str, float] = {}
    for cell in landscape:
        cell_id = cell.get("id")
        depth_m = cell.get("depth_m")
        if cell_id is None or depth_m is None:
            continue
        out[str(cell_id)] = float(refuge_predation_risk(
            cell_depth_m=float(depth_m), size_class="adult"))
    return out


from yellowstone_python.pipeline.stages.foodweb import _predation_rate_by_cell

READS = ('do_mg_l_by_cell', 'replay_doc', 'solute_concentrations_by_cell')
WRITES = ('aquatic_foodweb', 'foodweb_shear_disturb_pa')

def run(state: dict, cfg: dict) -> dict:
    """Advance the foodweb stage and return its state."""
    do_mg_l_by_cell = state['do_mg_l_by_cell']
    replay_doc = state['replay_doc']
    solute_concentrations_by_cell = state['solute_concentrations_by_cell']
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

    # --- aquatic food web: replay heat -> insect prey -> trout refuge -> dipper intake, 14-day run ---
    from yellowstone_python.aquatic.aquatic_foodweb import run_foodweb as run_aquatic_foodweb
    from yellowstone_python.aquatic.aquatic_foodweb import thermal_landscape
    fcfg_foodweb = cfg.get("fish", {})
    foodweb_species = str(fcfg_foodweb.get("species", "brown_trout"))
    foodweb_cover = float(fcfg_foodweb.get("cover", 0.6))
    foodweb_cfg = cfg.get("foodweb", {})
    foodweb_days = float(foodweb_cfg.get("days", 14.0))
    foodweb_dt_days = float(foodweb_cfg.get("dt_days", 1.0))
    foodweb_ne_turnover_days = float(foodweb_cfg.get("ne_turnover_days", 2.0))
    foodweb_shear_disturb_pa = float(foodweb_cfg.get("shear_disturb_pa", 20.0))
    predation_rate_by_cell = _predation_rate_by_cell(
        thermal_landscape(replay_doc))
    aquatic_foodweb = run_aquatic_foodweb(
        thermal_landscape(replay_doc),
        days=foodweb_days,
        dt_days=foodweb_dt_days,
        trout_species=foodweb_species,
        thermal_curve_form=fcfg_foodweb.get("thermal_curve_form", "piecewise_linear"),
        cover=foodweb_cover,
        ne_turnover_days=foodweb_ne_turnover_days,
        shear_disturb_pa=foodweb_shear_disturb_pa,
        solute_concentrations=solute_concentrations_by_cell,
        do_mg_l_by_cell=do_mg_l_by_cell,
        predation_rate_by_cell=predation_rate_by_cell,
        predation_window_days=1.0)


    state.update({'aquatic_foodweb': aquatic_foodweb, 'foodweb_shear_disturb_pa': foodweb_shear_disturb_pa})
    return state
