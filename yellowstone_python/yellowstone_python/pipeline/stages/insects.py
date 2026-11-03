"""Insects simulation stage."""
from __future__ import annotations

from yellowstone_python.pipeline.shared import PATCH_RIPARIAN, RIVER_FIREHOLE, _find, math

READS = ('air0', 'aquatic_foodweb', 'baseline', 'bridge', 'foodweb_shear_disturb_pa', 'hour0', 'patches1', 'replay_doc', 'sim_s', 'weather_frag', 'wind_mag')
WRITES = ('act0', 'benthic_grid', 'fh_landscape_cells', 'flowering', 'prey_ledger', 'wildlife1')

def run(state: dict, cfg: dict) -> dict:
    """Advance the insects stage and return its state."""
    air0 = state['air0']
    aquatic_foodweb = state['aquatic_foodweb']
    baseline = state['baseline']
    bridge = state['bridge']
    foodweb_shear_disturb_pa = state['foodweb_shear_disturb_pa']
    hour0 = state['hour0']
    patches1 = state['patches1']
    replay_doc = state['replay_doc']
    sim_s = state['sim_s']
    weather_frag = state['weather_frag']
    wind_mag = state['wind_mag']
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

    # insects: activity and compartments.
    icfg = cfg.get("insects", {})
    flowering = float(icfg.get("flowering_stage", 0.6))
    riparian = _find(patches1, "id", PATCH_RIPARIAN, "patch")
    sun0 = max(0.0, math.sin((hour0 - 6.0) * math.pi / 12.0))
    act0 = insect_activity(
        sun=sun0, air_c=air0, cloud=weather_frag.get("cloud", 0.16),
        moisture=riparian.get("moisture", 0.85),
        resource=riparian.get("insect_resource", 0.8),
        wind_mps=wind_mag, flowering=flowering)
    for p in patches1:
        if p["id"] == PATCH_RIPARIAN:
            p["insect_resource"] = step_resource(
                float(p.get("insect_resource", 0.8)),
                float(p.get("insect_recovery_per_hour", 0.06)),
                sun=sun0, moisture=float(p.get("moisture", 0.85)),
                consumed=0.0, dt_s=sim_s)
    wildlife1 = update_wildlife(baseline.get("wildlife", []),
                                {PATCH_RIPARIAN: act0})
    # One insect patch shares thermal forcing from a Firehole bridge replay cell.
    from yellowstone_python.aquatic.aquatic_foodweb import shear_to_disturbance
    foodweb_landscape = thermal_landscape(replay_doc)
    bridge_cells = [c for c in foodweb_landscape
                    if c.get("river_id") == RIVER_FIREHOLE]
    bridge_cell = bridge_cells[-1] if bridge_cells else foodweb_landscape[-1]
    bridge_cell_id = bridge_cell.get("id")
    bridge_cell_water_c = float(bridge_cell.get("temperature_c",
                                                bridge.get("temperature_c",
                                                           18.0)))
    bridge_cell_shear_pa = bridge_cell.get("shear_pa")
    bridge_disturbance = shear_to_disturbance(bridge_cell_shear_pa,
                                              foodweb_shear_disturb_pa)
    prey = dict(icfg.get("initial", {"Nt": 0.5, "Nb": 0.5, "Ne": 0.2}))
    prey_ledgers = []
    _t = 0.0
    while _t < sim_s - 1e-9:
        _h = min(60.0, sim_s - _t)
        prey, _pl = step_compartments(
            prey, {"sun": sun0, "air_c": air0,
                   "cloud": weather_frag.get("cloud", 0.16),
                   "moisture": riparian.get("moisture", 0.85),
                   "wind_mps": wind_mag, "flowering": flowering,
                   "water_c": bridge_cell_water_c,
                   "cell_id": bridge_cell_id,
                   "disturbance": bridge_disturbance},
            dt_s=_h, consumers=diets_with_aerial_insectivores())
        prey_ledgers.append(_pl)
        _t += _h
    aerial_diets = diets_with_aerial_insectivores()
    prey_ledger = {"emergence_total": round(sum(l["emergence"] for l in prey_ledgers), 6),
                   "consumed_total": {k: round(sum(l["consumed_by"].get(k, 0.0) for l in prey_ledgers), 6)
                                      for k in aerial_diets},
                   "final": prey,
                   "forcing_cell_id": bridge_cell_id,
                   "forcing_water_c": round(bridge_cell_water_c, 3),
                   "forcing_disturbance": round(float(bridge_disturbance), 4),
                   "forcing_shear_pa": (round(float(bridge_cell_shear_pa), 4)
                                        if bridge_cell_shear_pa is not None
                                        else None),
                   "forcing_shear_disturb_pa": float(foodweb_shear_disturb_pa),
                   "forcing_source": "foodweb_shear_to_disturbance_shared"}
    # Per-cell benthic development across every Firehole cell, driven by the replay thermal landscape.
    from yellowstone_python.insects_birds import develop_benthic_grid
    fh_landscape_cells = [c for c in foodweb_landscape
                          if c.get("river_id") == RIVER_FIREHOLE]
    benthic_grid = None
    if fh_landscape_cells and sim_s > 0.0:
        nb_init = [0.5] * len(fh_landscape_cells)
        water_c_cells = [float(c["temperature_c"])
                         for c in fh_landscape_cells]
        try:
            grid_result = develop_benthic_grid(
                nb_init, water_c_cells, dt_s=sim_s,
                disturbance=float(bridge_disturbance))
            benthic_grid = {
                "cell_ids": [c["id"] for c in fh_landscape_cells],
                "water_c_cells": water_c_cells,
                "nb_init": nb_init,
                "nb": grid_result["nb"],
                "emergence": grid_result["emergence"],
                "disturbance_loss": grid_result["disturbance_loss"],
                "dt_s": sim_s,
                "forcing_source": "replay_thermal_landscape_firehole_cells",
            }
        except (ValueError, KeyError) as benthic_exc:
            benthic_grid = {"status": "input_invalid",
                            "reason": str(benthic_exc)}
    rates = {k: v / max(1e-9, sim_s / 3600.0)
             for k, v in prey_ledger["consumed_total"].items()}
    # Dipper intake uses the trout refuge cell's replay food web; raven uses the compartment ledger.
    fw_dipper = aquatic_foodweb.get("dipper", {})
    intake_basis = {k: "insect_compartments" for k in rates}
    if "intake_per_day" in fw_dipper:
        rates["dipper"] = float(fw_dipper["intake_per_day"]) / 24.0
        intake_basis["dipper"] = "replay_foodweb"
    wildlife1 = update_wildlife_from_intake(wildlife1, rates, intake_basis)


    state.update({'act0': act0, 'benthic_grid': benthic_grid, 'fh_landscape_cells': fh_landscape_cells, 'flowering': flowering, 'prey_ledger': prey_ledger, 'wildlife1': wildlife1})
    return state
