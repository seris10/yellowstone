"""Grazers simulation stage."""
from __future__ import annotations

from yellowstone_python.pipeline.shared import BISON_DEMO, POOL_GRAND, _find, math
from yellowstone_python.pipeline.stages.thermal import _outflow_mean_wet_temperature_c

READS = ('_excluded', 'air0', 'cell_depth_m', 'outflow_chain', 'patches1', 'patches2', 'shells', 'thermal_by_patch', 'wcfg', 'weather_frag', 'wildlife2', 'wind_mag')
WRITES = ('corridor', 'grazer_blockers', 'piscivore_reports', 'steam_report', 'wildlife3')

def run(state: dict, cfg: dict) -> dict:
    """Advance the grazers stage and return its state."""
    _excluded = state['_excluded']
    air0 = state['air0']
    cell_depth_m = state['cell_depth_m']
    outflow_chain = state['outflow_chain']
    patches1 = state['patches1']
    patches2 = state['patches2']
    shells = state['shells']
    thermal_by_patch = state['thermal_by_patch']
    wcfg = state['wcfg']
    weather_frag = state['weather_frag']
    wildlife2 = state['wildlife2']
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

    # --- grazers ---
    snow_depth_by_patch = {p["id"]: float(p.get("snow_depth_m", 0.0))
                           for p in patches2}
    warm_ground_by_patch = {pid: bool(flux > 1.0)
                            for pid, flux in thermal_by_patch.items()}
    wildlife3 = update_grazers(wildlife2, patches1,
                               snow_depth_by_patch=snow_depth_by_patch,
                               warm_ground_by_patch=warm_ground_by_patch)
    # Piscivore mortality per trout; cell_depth_m comes from the fish-side per-cell depths.
    piscivore_reports = []
    for rec in wildlife3:
        if "trout" not in str(rec.get("id", "")):
            continue
        depth_m = rec.get("refuge_depth_m")
        if depth_m is None and cell_depth_m is not None:
            reach_idx = int(rec.get("start_point_index", 0))
            if 0 <= reach_idx < len(cell_depth_m):
                depth_m = float(cell_depth_m[reach_idx])
        if depth_m is None:
            depth_m = 1.0
        report = predation_over_refuge(
            rec, cell_depth_m=depth_m,
            size_class=str(rec.get("size_class", "adult")))
        rec["piscivore_mortality_per_day"] = report.get(
            "mortality_rate_per_day")
        rec["piscivore_components"] = report.get("components")
        piscivore_reports.append(report)
    pool_shell = _find(shells, "id", POOL_GRAND, "pool shell")
    pool_surface_c = float(pool_shell.get("t_edge_c", 70.0))
    pool_r_water = float(pool_shell.get("r_water_m", 0.0))
    pool_area_m2 = math.pi * pool_r_water * pool_r_water
    outflow_surface_c = None
    outflow_area_m2 = 0.0
    if outflow_chain is not None:
        outflow_surface_c, outflow_area_m2 = _outflow_mean_wet_temperature_c(
            outflow_chain["outflow_raster"],
            outflow_chain["network_rasters"].get("wet_mask"))
    steam_report = plume_microclimate_adjustment(
        air_c=air0, rh=float(wcfg.get("humidity", 0.45)),
        wind_mps=wind_mag,
        pool_surface_c=pool_surface_c,
        pool_area_m2=pool_area_m2,
        outflow_surface_c=outflow_surface_c,
        outflow_area_m2=outflow_area_m2)
    weather_frag["downwind_air_c"] = steam_report.get("downwind_air_c")
    weather_frag["downwind_rh"] = steam_report.get("downwind_rh")
    weather_frag["fog_present"] = bool(fog_present(
        steam_report.get("downwind_air_c", air0),
        steam_report.get("downwind_rh", float(wcfg.get("humidity", 0.45)))))
    weather_frag["rime_present"] = bool(rime_present(
        steam_report.get("downwind_air_c", air0),
        steam_report.get("downwind_rh", float(wcfg.get("humidity", 0.45)))))
    grazer_blockers = check_grazer_routes(wildlife3, shells)
    b1 = _find(wildlife3, "id", BISON_DEMO, "wildlife")
    # Re-walk the bison's authored route segment by segment through the eligibility planner for verification.
    _leg = [tuple(p) for p in b1["path_xz"]]
    _xs = [p[0] for p in _leg]
    _zs = [p[1] for p in _leg]
    _bounds = (min(_xs) - 20, min(_zs) - 20, max(_xs) + 20, max(_zs) + 20)
    _corr = []
    _corr_ok = True
    for _a, _b in zip(_leg, _leg[1:]):
        try:
            _corr += plan_path(_a, _b, _excluded, cell_m=4.0, bounds=_bounds)
        except ValueError:
            _corr_ok = False
            break
    from yellowstone_python.land.grazers import route_length as _rlen
    corridor = {"from": list(_leg[0]), "to": list(_leg[-1]),
                "length_m": round(_rlen(_corr), 1) if _corr else 0.0,
                "waypoints": len(_corr),
                "planner_ok": _corr_ok,
                "note": ("planner re-walk on apron grid over the authored "
                         "route; records not altered")}


    state.update({'corridor': corridor, 'grazer_blockers': grazer_blockers, 'piscivore_reports': piscivore_reports, 'steam_report': steam_report, 'wildlife3': wildlife3})
    return state
