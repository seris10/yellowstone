"""Stages fish build operations."""
from __future__ import annotations



def _per_point_hydraulics_from_cells(fh_chainage, fh_offset,
                                     fh_landscape_cells):
    """Nearest-cell velocity_m_s and depth_m per river_point; returns (velocities, depths) or (None, None)."""
    if not fh_landscape_cells or not fh_chainage:
        return (None, None)
    cell_s = []
    cell_v = []
    cell_d = []
    for c in fh_landscape_cells:
        s = c.get("s_m")
        v = c.get("velocity_m_s")
        d = c.get("depth_m")
        if s is None or v is None or d is None:
            continue
        try:
            cell_s.append(float(s))
            cell_v.append(max(0.0, float(v)))
            cell_d.append(max(1e-6, float(d)))
        except (TypeError, ValueError):
            continue
    if not cell_s:
        return (None, None)
    order = sorted(range(len(cell_s)), key=lambda i: cell_s[i])
    cell_s_sorted = [cell_s[i] for i in order]
    cell_v_sorted = [cell_v[i] for i in order]
    cell_d_sorted = [cell_d[i] for i in order]
    import bisect as _bisect
    out_v: list[float] = []
    out_d: list[float] = []
    for p in fh_chainage:
        target = float(p) + float(fh_offset)
        idx = _bisect.bisect_left(cell_s_sorted, target)
        if idx <= 0:
            pick = 0
        elif idx >= len(cell_s_sorted):
            pick = len(cell_s_sorted) - 1
        elif (target - cell_s_sorted[idx - 1]) <= (cell_s_sorted[idx] - target):
            pick = idx - 1
        else:
            pick = idx
        out_v.append(cell_v_sorted[pick])
        out_d.append(cell_d_sorted[pick])
    return (out_v, out_d)


from yellowstone_python.pipeline.shared import RIVER_FIREHOLE, _find
from yellowstone_python.pipeline.stages.fish import _per_point_hydraulics_from_cells

READS = ('aquatic_foodweb', 'fh_landscape_cells', 'replay_doc', 'river_state', 'shells', 'wildlife1', 'world')
WRITES = ('cell_depth_m', 'fh_chainage', 'fh_membership', 'fh_offset', 'firehole', 'trout_blockers', 'trout_hydraulics_source', 'trout_position_authority', 'wildlife2')

def run(state: dict, cfg: dict) -> dict:
    """Advance the fish stage and return its state."""
    aquatic_foodweb = state['aquatic_foodweb']
    fh_landscape_cells = state['fh_landscape_cells']
    replay_doc = state['replay_doc']
    river_state = state['river_state']
    shells = state['shells']
    wildlife1 = state['wildlife1']
    world = state['world']
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

    # Trout refuge placement.
    fcfg = cfg.get("fish", {})
    firehole = _find(world["rivers"], "id", RIVER_FIREHOLE, "river")
    from yellowstone_python.aquatic.fish import build_chainage, place_trout_at_chainage, reach_membership, reach_z_windows
    fh_ordered = reach_z_windows(river_state, river_points=firehole["points"])
    fh_membership = reach_membership(firehole["points"], fh_ordered)
    fh_chainage = build_chainage(firehole["points"])
    fh_features = replay_doc.get("replay", replay_doc).get("river_features", {})
    fh_offset = float(fh_features.get(RIVER_FIREHOLE, {}).get("start_s_m", 0.0))
    # Per-point velocity and depth from the nearest Firehole replay cell; polyline chainage + fh_offset selects the cell.
    cell_velocity_mps, cell_depth_m = _per_point_hydraulics_from_cells(
        fh_chainage, fh_offset, fh_landscape_cells)
    trout_hydraulics_source: str
    if cell_velocity_mps is not None and cell_depth_m is not None:
        wildlife2 = update_trout(wildlife1, river_state, firehole["points"],
                                 weights=fcfg.get("weights"),
                                 food=float(fcfg.get("food", 0.7)),
                                 cover=float(fcfg.get("cover", 0.6)),
                                 cell_velocity_mps=cell_velocity_mps,
                                 cell_depth_m=cell_depth_m)
        trout_hydraulics_source = (
            "per_cell_from_replay_firehole_landscape_nearest_chainage")
    else:
        wildlife2 = update_trout(wildlife1, river_state, firehole["points"],
                                 weights=fcfg.get("weights"),
                                 food=float(fcfg.get("food", 0.7)),
                                 cover=float(fcfg.get("cover", 0.6)))
        trout_hydraulics_source = ("reach_level_fallback_no_firehole_cells")
    # place_trout_at_chainage is the single authority for trout position.
    wildlife2 = place_trout_at_chainage(
        wildlife2, river_state, firehole["points"],
        aquatic_foodweb["trout"], chainage_offset_m=fh_offset)
    trout_position_authority = "fish.place_trout_at_chainage"
    trout_blockers = check_trout_clear_of_pools(wildlife2, firehole["points"],
                                                shells)


    state.update({'cell_depth_m': cell_depth_m, 'fh_chainage': fh_chainage, 'fh_membership': fh_membership, 'fh_offset': fh_offset, 'firehole': firehole, 'trout_blockers': trout_blockers, 'trout_hydraulics_source': trout_hydraulics_source, 'trout_position_authority': trout_position_authority, 'wildlife2': wildlife2})
    return state
