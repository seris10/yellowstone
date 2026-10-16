"""Stages thermal build operations."""
from __future__ import annotations

from yellowstone_python.pipeline.shared import OUTFLOW_SITE_ALTITUDE_M, Path, SITE_LAT_DEG, SITE_LON_DEG, json, math

def _run_outflow_chain(world_root, air_c, wcfg, start_epoch_s,
                       epoch_source="explicit_argument"):
    """Load the model outflow network and run model's temperature chain at start_epoch_s (UTC seconds)."""
    import datetime
    import numpy as np
    network_dir = Path(world_root) / "data" / "outflow_network"
    network_path = network_dir / "outflow_network.json"
    if not network_path.is_file():
        return None
    network = json.loads(network_path.read_text(encoding="utf-8"))
    spring_discharges_path = network_dir / "spring_discharges.json"
    discharges_doc = json.loads(spring_discharges_path.read_text(encoding="utf-8"))
    discharges = {pid: float(entry["discharge_m3_s"])
                  for pid, entry in discharges_doc.get("springs", {}).items()}
    source_temps = {
        "pool_1030_0": 88.7,
        "pool_1034_0": 70.0,
        "pool_1028_0": 62.0,
        "pool_1029_0": 60.0,
    }
    river_frac = {}
    for spring in network.get("springs", []):
        pid = spring.get("pool_id")
        rfrac = spring.get("river_inflow_fraction")
        if pid is not None and rfrac is not None:
            river_frac[pid] = float(rfrac)
    rasters_meta = network.get("rasters", {}) or {}
    network_rasters = {}
    for key in ("spring_index", "flow_length_m", "flow_fraction", "wet_mask"):
        entry = rasters_meta.get(key)
        if not isinstance(entry, dict):
            continue
        path_rel = entry.get("path") or ""
        if not path_rel:
            continue
        raster_path = network_dir / path_rel
        if not raster_path.is_file():
            continue
        dtype = entry.get("dtype", "float32")
        np_dtype = {"int16": "<i2", "float32": "<f4",
                    "<i2": "<i2", "<f4": "<f4"}.get(dtype, "<f4")
        raw = np.frombuffer(raster_path.read_bytes(), dtype=np_dtype)
        from yellowstone_python.thermal_features.outflow_thermal import CORE_GRID_SIZE
        network_rasters[key] = raw.reshape((CORE_GRID_SIZE, CORE_GRID_SIZE))
    if not {"spring_index", "flow_length_m", "flow_fraction"}.issubset(
            network_rasters):
        return None
    from yellowstone_python.thermal_features.outflow_thermal import graph_sweep_outflow_temperature, load_dem_core_tif, write_outflow_temperature
    from yellowstone_python.river.surface_flux import BudgetParams, MetState
    from yellowstone_python.thermal_features.microbial_mats import instantaneous_shortwave_w_m2
    cloud = float(wcfg.get("cloud", 0.16))
    shortwave = instantaneous_shortwave_w_m2(
        float(start_epoch_s), SITE_LAT_DEG, SITE_LON_DEG,
        cloud, altitude_m=OUTFLOW_SITE_ALTITUDE_M)
    shortwave.update({
        "epoch_source": epoch_source,
        "epoch_utc": datetime.datetime.fromtimestamp(
            float(start_epoch_s), tz=datetime.timezone.utc).isoformat(),
        "latitude_deg": SITE_LAT_DEG,
        "longitude_deg": SITE_LON_DEG,
        "altitude_m": OUTFLOW_SITE_ALTITUDE_M,
        "cloud_source": "weather.cloud at the simulation start",
    })
    met = MetState(
        air_c=float(air_c),
        rh=float(wcfg.get("humidity", 0.45)),
        wind_mps=float(math.hypot(*(wcfg.get("wind_xz_mps", [1.8, 0.6])[:2]))),
        shortwave_w_m2=shortwave["all_sky_w_m2"],
        cloud=cloud)
    dem_path = Path(world_root) / "references" / "dem_1m_core.tif"
    if not dem_path.is_file():
        return None
    dem = load_dem_core_tif(str(dem_path))
    world_json_path = Path(world_root) / "data" / "world.json"
    world_doc = json.loads(world_json_path.read_text(encoding="utf-8"))
    spring_names = {str(s.get("name")) for s in network.get("springs", [])
                    if s.get("name")}
    world_pools = [p for p in world_doc.get("pools", []) or []
                   if p.get("name") in spring_names]
    sweep = graph_sweep_outflow_temperature(
        network, network_rasters, dem, world_pools,
        discharges, source_temps, met,
        budget_params=BudgetParams(),
        forcing_epoch_utc=float(start_epoch_s),
    )
    temperature = sweep["temperature"]
    sidecar = sweep["sidecar"]
    sidecar["shortwave_forcing"] = shortwave
    sidecar.setdefault("grid", {
        "origin_xz_m": [-640.0, -640.0],
        "cell_size_m": 1.0,
        "nx": 1280,
        "nz": 1280,
        "row_order": "north_to_south",
    })
    sidecar.setdefault("units", "degC")
    sidecar.setdefault("nodata", "NaN")
    result = {"raster": temperature,
              "sidecar": sidecar,
              "wet_mask_bool": sweep["wet_mask"]}
    from yellowstone_python.thermal_features.microbial_mats import build_mat_state, daily_mean_insolation_w_m2
    sim_date_utc = datetime.datetime.fromtimestamp(
        float(start_epoch_s), tz=datetime.timezone.utc).date().isoformat()
    insolation = daily_mean_insolation_w_m2(
        sim_date_utc, latitude=SITE_LAT_DEG,
        longitude=SITE_LON_DEG, daily_cloud_fraction=cloud,
        altitude_m=OUTFLOW_SITE_ALTITUDE_M)
    insolation["date_utc"] = sim_date_utc
    insolation["date_source"] = epoch_source
    daily_sw = insolation["all_sky_mean_w_m2"]
    mat = build_mat_state(result["raster"],
                          daily_mean_shortwave_w_m2=daily_sw,
                          dt_days=1.0, ph=8.0)
    return {
        "network": network,
        "network_rasters": network_rasters,
        "dem": dem,
        "outflow_raster": result["raster"],
        "outflow_sidecar": result["sidecar"],
        "mat_state": mat,
        "insolation": insolation,
        "shortwave_forcing": shortwave,
        "forcing_epoch_utc": float(start_epoch_s),
        "discharges_m3_s": discharges,
        "spring_temps_c": source_temps,
        "river_inflow_fraction_by_pool": river_frac,
        "network_dir": str(network_dir),
    }


def _outflow_mean_wet_temperature_c(outflow_raster, wet_mask):
    """Mean outflow temperature across wet cells; returns (mean_c, wet_area_m2)."""
    import numpy as np
    if outflow_raster is None or wet_mask is None:
        return None, 0.0
    arr = np.asarray(outflow_raster, dtype="float64")
    mask = (np.asarray(wet_mask, dtype="int16") == 1) & np.isfinite(arr)
    if not mask.any():
        return None, 0.0
    mean_c = float(arr[mask].mean())
    wet_area_m2 = float(mask.sum())
    return mean_c, wet_area_m2


def _excelsior_lateral_override(outflow_chain):
    """Discharge-weighted river-entry lateral override for the Excelsior reach."""
    import numpy as np
    if outflow_chain is None:
        return None
    network = outflow_chain.get("network") or {}
    rasters = outflow_chain.get("network_rasters") or {}
    spring_index = rasters.get("spring_index")
    outflow = outflow_chain.get("outflow_raster")
    if spring_index is None or outflow is None:
        return None
    arr = np.asarray(outflow, dtype="float64")
    si = np.asarray(spring_index, dtype="int16")
    discharges = outflow_chain.get("discharges_m3_s") or {}
    river_fracs = outflow_chain.get("river_inflow_fraction_by_pool") or {}
    per_spring = []
    total_q = 0.0
    total_qt = 0.0
    for spring in network.get("springs", []):
        pid = spring.get("pool_id")
        idx = int(spring.get("index"))
        q_spring = float(discharges.get(pid, 0.0))
        frac = float(river_fracs.get(pid, 1.0))
        share = q_spring * frac
        mask = (si == idx) & np.isfinite(arr)
        if not mask.any():
            per_spring.append({"pool_id": pid, "spring_index": idx,
                               "share_m3_s": share,
                               "mean_t_c": None, "wet_cell_count": 0})
            continue
        mean_t = float(arr[mask].mean())
        per_spring.append({"pool_id": pid, "spring_index": idx,
                           "discharge_m3_s": q_spring,
                           "river_inflow_fraction": frac,
                           "share_m3_s": share,
                           "mean_t_c": mean_t,
                           "wet_cell_count": int(mask.sum())})
        total_q += share
        total_qt += share * mean_t
    if total_q <= 0.0:
        return None
    mean_t_weighted = total_qt / total_q
    return {
        "flow_m3s": total_q,
        "temperature_c": mean_t_weighted,
        "status": "outflow_chain_override",
        "provenance": {
            "source": "WP-A outflow_network river_inflow_fraction times "
                      "spring_discharges.json, weighted by WP-B outflow "
                      "temperature mean over each spring's wet cells",
            "per_spring": per_spring,
        },
    }


def _run_outflow_foodweb(outflow_chain, build_dir):
    """Run outflow food web on the real mat and outflow rasters, write sidecar.
Returns the report dict (empty when the outflow chain did not run)."""
    if outflow_chain is None:
        return {}
    from yellowstone_python.thermal_features.outflow_foodweb import outflow_foodweb_from_files
    mat_state_path = str(build_dir / "mat_state.json")
    outflow_temp_path = str(build_dir / "outflow_temperature.json")
    discharge_cv = 0.20
    mat_biomass_g_per_m2 = 100.0
    report = outflow_foodweb_from_files(
        mat_state_json_path=mat_state_path,
        outflow_temp_json_path=outflow_temp_path,
        outflow_discharge_cv=discharge_cv,
        mat_biomass_g_per_m2=mat_biomass_g_per_m2)
    from yellowstone_python.common.io import sha256_file
    report["inputs"].update({
        "mat_state_json": "mat_state.json",
        "outflow_temperature_json": "outflow_temperature.json",
        "mat_state_sha256": sha256_file(mat_state_path),
        "outflow_temperature_sha256": sha256_file(outflow_temp_path),
    })
    report.setdefault("schema", "yellowstone.outflow_foodweb.v1")
    report["status"] = report.get("status",
                                   "transferred_structure_authored_rates")
    report["authored_inputs"] = {
        "outflow_discharge_cv": discharge_cv,
        "outflow_discharge_cv_status": "authored",
        "mat_biomass_g_per_m2": mat_biomass_g_per_m2,
        "mat_biomass_status": "authored",
        "note": ("authored because no measured discharge variance or mat "
                 "biomass density is available for the baseline window"),
    }
    return report


def _run_mat_validation(outflow_chain, world_root):
    """Confusion matrix of the modeled mat classes against the NAIP orthophoto.
Returns the validation block for BUILD.json; empty when the orthophoto is absent."""
    import numpy as np
    if outflow_chain is None:
        return {}
    ortho_path = world_root / "references" / "midway_orthophoto_detail.jpg"
    header_path = world_root / "references" / "midway_orthophoto_detail.json"
    if not ortho_path.is_file() or not header_path.is_file():
        return {"status": "no_orthophoto",
                "note": "midway_orthophoto_detail.jpg or .json absent"}
    try:
        from PIL import Image
    except ImportError:
        return {"status": "pillow_unavailable"}
    from yellowstone_python.thermal_features.mat_validation import validate_mats
    from yellowstone_python.thermal_features.outflow_network import Grid, thermal_proximity_mask
    network = outflow_chain.get("network") or {}
    mat_state = outflow_chain.get("mat_state")
    if mat_state is None:
        return {"status": "no_mat_state"}
    img = Image.open(str(ortho_path)).convert("RGB").resize((1280, 1280))
    observed_rgb = np.asarray(img, dtype=np.uint8)
    grid = Grid(size=1280, cell_m=1.0, half_m=640.0)
    thermal_radius = float(network.get("method", {}).get(
        "thermal_mask_radius_m", 220.0))
    pool_centers = []
    for spring in network.get("springs", []):
        rim = spring.get("rim_xz") or []
        if not rim:
            continue
        xs = [float(p[0]) for p in rim]
        zs = [float(p[1]) for p in rim]
        pool_centers.append((sum(xs) / len(xs), sum(zs) / len(zs)))
    thermal_mask = thermal_proximity_mask(grid, pool_centers,
                                          radius_m=thermal_radius)
    modeled = np.asarray(mat_state.community_class)
    block = validate_mats(
        observed_rgb=observed_rgb,
        thermal_mask=thermal_mask,
        modeled_class_map=modeled,
        modeled_legend=mat_state.legend,
        observed_pixel_area_m2=1.0,
        modeled_pixel_area_m2=1.0,
        status="validation",
        sources=[
            "yellowstone_midway/references/midway_orthophoto_detail.jpg",
            "yellowstone_midway/data/outflow_network/outflow_network.json",
        ])
    block["thermal_mask_radius_m"] = thermal_radius
    block["thermal_mask_cells"] = int(np.sum(thermal_mask))
    return block


from yellowstone_python.pipeline.shared import POOL_GRAND, _find
from yellowstone_python.pipeline.stages.river import resolve_replay_start_epoch
from yellowstone_python.pipeline.stages.thermal import _run_outflow_chain

READS = ('air0', 'hour0', 'wcfg', 'world', 'world_root')
WRITES = ('_excluded', 'ground_heat_field', 'outflow_chain', 'shells', 'substrate_failures')

def run(state: dict, cfg: dict) -> dict:
    """Advance the thermal stage and return its state."""
    air0 = state['air0']
    hour0 = state['hour0']
    wcfg = state['wcfg']
    world = state['world']
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

    # --- shells ---
    shells = build_shells(world["pools"])
    _find(shells, "id", POOL_GRAND, "pool shell")
    substrate_failures = check_midway_shells(shells)

    # Ground heat field for snow melt and tree suitability inputs.
    ground_heat_field = heat_flux_mask_field(shells, size=320)
    _ = tree_thermal_suitability  # imported for symmetry with soil_temperature consumers

    outflow_epoch_s, outflow_epoch_source = resolve_replay_start_epoch(
        cfg, hour0)
    outflow_chain = _run_outflow_chain(world_root, air0, wcfg,
                                       outflow_epoch_s, outflow_epoch_source)

    def _excluded(x: float, z: float) -> bool:
        return any(_in_apron(x, z, s) for s in shells)


    state.update({'_excluded': _excluded, 'ground_heat_field': ground_heat_field, 'outflow_chain': outflow_chain, 'shells': shells, 'substrate_failures': substrate_failures})
    return state
