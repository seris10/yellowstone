"""Stages river build operations."""
from __future__ import annotations

from yellowstone_python.pipeline.shared import DEFAULT_TRIBUTARIES, PKG_ROOT, Path, REPLAY_WEATHER_KEYS, build_mapped_replay, copy, epoch_unix_for_local, json, parse_simulation_start

def _prepare_replay_ecosystem(baseline: dict, cfg: dict, hour0: float | None = None,
                              weather: dict | None = None,
                              boundary_m3s=None,
                              excelsior_override: dict | None = None) -> dict:
    """Apply config overrides to a deepcopy of the baseline for the replay solver.
boundary_m3s accepts a scalar or a {"times_s", "values"} Series for a scheduled hydrograph."""
    eco = copy.deepcopy(baseline)
    if excelsior_override is not None:
        for reach in eco.get("river_reaches", []):
            for lat in reach.get("lateral_sources") or []:
                if lat.get("id") == "excelsior_aggregate_outflow":
                    lat["flow_m3s"] = float(excelsior_override["flow_m3s"])
                    lat["temperature_c"] = float(
                        excelsior_override["temperature_c"])
                    lat["status"] = str(excelsior_override.get(
                        "status", "outflow_chain_override"))
                    lat["provenance"] = dict(
                        excelsior_override.get("provenance", {}))
    hcfg = cfg.get("hydro", {})
    chosen_boundary = (hcfg.get("boundary_m3s", baseline["boundary_m3s"])
                       if boundary_m3s is None else boundary_m3s)
    if isinstance(chosen_boundary, dict) and {"times_s", "values"} <= set(
            chosen_boundary):
        eco["boundary_m3s"] = {
            "times_s": list(chosen_boundary["times_s"]),
            "values": [float(v) for v in chosen_boundary["values"]],
        }
    else:
        eco["boundary_m3s"] = float(chosen_boundary)
    eco["boundary_c"] = float(hcfg.get("boundary_c", baseline["boundary_c"]))
    if hour0 is not None:
        eco["clock_hour"] = float(hour0)
    if weather:
        injected = {k: copy.deepcopy(weather[k]) for k in REPLAY_WEATHER_KEYS
                    if k in weather}
        if injected:
            eco["weather"] = {**eco.get("weather", {}), **injected}
    tribs = {**DEFAULT_TRIBUTARIES, **hcfg.get("tributaries", {})}
    by_id = {r["id"]: r for r in eco["river_reaches"]}
    for rid, names in hcfg.get("attach", {}).items():
        if rid not in by_id:
            raise ValueError(f"hydro.attach reach {rid!r} not in chain "
                             f"{list(by_id)}")
        if not isinstance(names, list):
            raise ValueError(
                f"hydro.attach[{rid!r}] must be a list of tributary names")
        for n in names:
            if n not in tribs:
                raise ValueError(
                    f"unknown tributary {n!r}; have {sorted(tribs)}")
            t = tribs[n]
            if t.get("flow_m3s", 0.0) > 0:
                by_id[rid].setdefault("lateral_sources", []).append(
                    {"id": n, **t, "status": "illustrative tributary"})
    return eco


def resolve_replay_start_epoch(cfg: dict, hour0: float | None) -> tuple[float, str]:
    """Epoch seconds for the replay clock, with the date source that set it.
Precedence: simulation group, snow.as_of_date, then system date (mirrors resolve_game_clock)."""
    scfg = cfg.get("simulation", {})
    if "start_epoch_unix" in scfg:
        return (float(scfg["start_epoch_unix"]), "simulation_config_epoch")
    if "start_utc" in scfg:
        start = parse_simulation_start(simulation_start_utc=scfg["start_utc"])
        return (start.timestamp(), "simulation_config_utc")

    hour = hour0 if hour0 is not None else float(cfg.get("clock_hour", 16.2))
    offset = float(scfg.get("utc_offset_hours", -6.0))
    as_of = cfg.get("snow", {}).get("as_of_date")
    if as_of is not None:
        return (epoch_unix_for_local(as_of, hour, offset), "config_date")
    import datetime
    return (
        epoch_unix_for_local(datetime.date.today().isoformat(), hour, offset),
        "system_clock_date",
    )


def run_replay_solver(cfg: dict, baseline: dict, world: dict,
                      hour0: float | None = None,
                      weather: dict | None = None,
                      boundary_m3s: float | None = None,
                      simulation_start_epoch_unix: float | None = None,
                      shortwave_multiplier: dict | None = None,
                      hyporheic_zones: dict | None = None,
                      excelsior_override: dict | None = None,
                      boundary_series: dict | None = None,
                      ) -> dict:
    """Run the 1-D advection-dispersion solver on the Firehole chain.

Returns the full replay document with timestamped frames and budget.
"""
    live = cfg.get("live", {})
    if live.get("solver_config"):
        from yellowstone_python.service.live.engine import run_exported_scenario
        from yellowstone_python.common.io import load_json
        base_path = PKG_ROOT / "derived" / live["build_id"] / "river_replay.json"
        base = load_json(base_path)
        base = base.get("replay", base)
        document = {**base, **run_exported_scenario(live)}
        document["cells"] = base["cells"]
        document["clock_hour0"] = ((float(live["epoch_unix"]) - 6.0 * 3600.0) / 3600.0) % 24.0
        return document
    rcfg = cfg.get("replay", {})
    eco = _prepare_replay_ecosystem(baseline, cfg, hour0=hour0, weather=weather,
                                    boundary_m3s=boundary_m3s,
                                    excelsior_override=excelsior_override)
    if boundary_series is not None:
        eco["boundary_m3s"] = boundary_series
    if simulation_start_epoch_unix is None:
        simulation_start_epoch_unix, start_source = resolve_replay_start_epoch(
            cfg, hour0)
    else:
        start_source = "explicit_argument"
    cross_sections = {}
    if "cross_sections_file" in rcfg:
        cs_path = Path(rcfg["cross_sections_file"])
        if not cs_path.is_absolute():
            cs_path = PKG_ROOT / cs_path
        cross_sections = json.loads(cs_path.read_text())
    hyd = rcfg.get("hydraulics", {})
    intervention = rcfg.get("intervention", {})
    doc = build_mapped_replay(
        world, eco,
        simulation_start_epoch_unix=simulation_start_epoch_unix,
        duration_s=float(rcfg.get("duration_s", 7200.0)),
        maximum_cell_m=float(rcfg.get("max_cell_m", 20.0)),
        depth_m=float(rcfg.get("depth_m", 1.1)),
        dispersion_m2_s=float(rcfg.get("dispersion_m2_s", 1.0)),
        exchange_w_m2_k=float(rcfg.get("exchange_w_m2_k", 12.0)),
        dt_s=float(rcfg.get("dt_s", 2.0)),
        sample_s=float(rcfg.get("sample_s", 10.0)),
        cross_sections=cross_sections if cross_sections else None,
        energy_budget=bool(rcfg.get("energy_budget", False)),
        bank_slope_zh=float(hyd.get("bank_slope_zh", 1.5)),
        manning_n=float(hyd.get("manning_n", 0.035)),
        shortwave_multiplier=shortwave_multiplier,
        hyporheic_zones=hyporheic_zones,
        pulse_source=intervention.get("source_id", ""),
        pulse_start_s=float(intervention.get("start_s", 300.)),
        pulse_end_s=float(intervention.get("end_s", 900.)),
        pulse_delta_c=float(intervention.get("delta_c", 18.)),
    )
    if intervention:
        doc["intervention"] = copy.deepcopy(intervention)
    doc["simulation_time_source"] = start_source
    return doc


def check_cross_sections(cross_sections, world) -> dict:
    """Validate cross-sections against world river features"""
    if not cross_sections:
        return {"status": "no_cross_sections",
                "feature_ids": [], "missing_features": [],
                "unknown_feature_entries": []}
    try:
        from yellowstone_python.river.river_world import parse_cross_sections
        profiles = parse_cross_sections(cross_sections)
    except (ValueError, KeyError) as exc:
        return {"status": "invalid",
                "error": str(exc),
                "feature_ids": sorted(cross_sections.keys())
                if isinstance(cross_sections, dict) else []}
    world_features = set()
    for river in world.get("rivers", []) or []:
        rid = river.get("id")
        if rid:
            world_features.add(rid)
    for pool in world.get("pools", []) or []:
        pid = pool.get("id")
        if pid:
            world_features.add(pid)
    present = set(profiles.keys())
    unknown = sorted(present - world_features)
    missing = sorted(world_features - present) if world_features else []
    return {"status": ("covers" if not unknown and not missing else
                       "partial" if present else "empty"),
            "feature_ids": sorted(present),
            "unknown_feature_entries": unknown,
            "missing_features": missing}


def _river_shading_dict(cells, start_epoch_unix, cfg):
    """Per-cell shortwave multiplier dict and sidecar provenance.
Averages the midday multiplier across the duration; a disabled config returns an empty dict."""
    from datetime import datetime, timezone
    if not cells or cfg.get("enabled", True) is False:
        return {}, {"schema": "yellowstone.river_shading.v1",
                    "status": "disabled",
                    "multiplier_by_cell": {},
                    "provenance": {"note": "shading disabled in config"}}
    try:
        from yellowstone_python.aquatic.river_shading import load_terrain_source, sky_view_factor, shortwave_multiplier as svf_multiplier
    except (ImportError, OSError) as exc:
        return {}, {"schema": "yellowstone.river_shading.v1",
                    "status": "unavailable",
                    "multiplier_by_cell": {},
                    "provenance": {"note": f"river_shading unavailable: {exc}"}}
    try:
        terrain = load_terrain_source()
    except (OSError, ValueError, KeyError) as exc:
        return {}, {"schema": "yellowstone.river_shading.v1",
                    "status": "no_terrain",
                    "multiplier_by_cell": {},
                    "provenance": {"note": f"terrain_source unavailable: {exc}"}}
    noon_epoch = (float(start_epoch_unix) if start_epoch_unix is not None
                  else 0.0) + 43200.0
    noon_dt = datetime.fromtimestamp(noon_epoch, tz=timezone.utc)
    trees: list[dict] = []
    census_path = PKG_ROOT / "derived" / "census.json"
    if census_path.is_file():
        try:
            trees_doc = json.loads(census_path.read_text(encoding="utf-8"))
            if isinstance(trees_doc, dict):
                trees = list(trees_doc.get("trees") or [])
        except (OSError, json.JSONDecodeError):
            trees = []
    multiplier_by_cell: dict[str, float] = {}
    svf_by_cell: dict[str, float] = {}
    for cell in cells:
        cell_id = cell.get("id")
        position = cell.get("position_xyz")
        if cell_id is None or not isinstance(position, (list, tuple)) or len(position) < 3:
            continue
        x = float(position[0])
        z = float(position[2])
        svf = float(sky_view_factor(terrain, x, z))
        result = svf_multiplier(terrain, trees, x, z, noon_dt, svf=svf)
        multiplier_by_cell[cell_id] = float(result["shortwave_multiplier"])
        svf_by_cell[cell_id] = svf
    doc = {
        "schema": "yellowstone.river_shading.v1",
        "status": "authored_illustrative_from_dem_and_census",
        "multiplier_by_cell": multiplier_by_cell,
        "sky_view_factor_by_cell": svf_by_cell,
        "n_trees": len(trees),
        "tree_height_sources": {
            "lidar_records": sum(t.get("method") == "lidar_lmf" and "height_m" in t for t in trees),
            "other_record_heights": sum(t.get("method") != "lidar_lmf" and "height_m" in t for t in trees),
            "authored_default": sum("height_m" not in t for t in trees),
        },
        "units": {"multiplier_by_cell": "dimensionless in [0, 1]"},
        "provenance": {
            "sources": "terrain_source.f32 + derived/census.json",
            "method": ("per-cell midday single-sample shortwave multiplier "
                       "with 0.8 direct and 0.2 diffuse split and canopy "
                       "transmissivity blocking"),
            "note": f"evaluated at noon_utc {noon_dt.isoformat()}",
            "height_method": "per-tree height_m; authored 15 m fallback for missing heights",
            "crown_base_method": "record crown_ratio when available; ground-to-top column otherwise",
        },
    }
    return multiplier_by_cell, doc


def _hyporheic_zones_dict(cells, cfg):
    """Per-cell hyporheic zone dict with authored Bencala and Walters defaults."""
    if not cells or cfg.get("enabled", True) is False:
        return {}
    storage_frac = float(cfg.get("storage_volume_fraction", 0.2))
    alpha_per_s = float(cfg.get("alpha_per_s", 1.0e-4))
    out: dict[str, dict] = {}
    for cell in cells:
        cell_id = cell.get("id")
        volume = float(cell.get("volume_m3", 0.0))
        if cell_id is None or volume <= 0.0:
            continue
        out[cell_id] = {
            "storage_volume_m3": storage_frac * volume,
            "alpha_per_s": alpha_per_s,
            "initial_c": float(cell.get("initial_c", 15.0)),
            "status": "authored_until_measured_bencala_walters_1983",
        }
    return out


def _run_solute_transport(replay_doc):
    """Advance solute transport across replay cells"""
    from yellowstone_python.river.solute_transport import load_hydrothermal_solutes, solute_sources_for_mapped_sources, transport_from_mapped_replay, transport_summary
    forcing = replay_doc.get("forcing", {})
    sources = forcing.get("sources", [])
    data_doc = load_hydrothermal_solutes()
    unmodeled: list[dict] = []
    for feature, record in (data_doc.get("features") or {}).items():
        if not isinstance(record, dict):
            continue
        status_label = (record.get("chloride_mg_l") or {}).get("status")
        value = (record.get("chloride_mg_l") or {}).get("value")
        if status_label == "authored_no_verified_sample" and value is None:
            unmodeled.append({"feature": feature, "reason": status_label})
    mapped_sources = []
    for entry in sources:
        mapped_sources.append({"id": entry["id"],
                               "cell_id": entry["cell_id"],
                               "flow_m3_s": entry["flow_m3_s"]})
    if not mapped_sources:
        return ({"schema": "yellowstone.solute_transport.v1",
                 "status": "no_mapped_sources",
                 "n_sources": 0,
                 "unmodeled_sources": unmodeled,
                 "provenance": "no lateral sources in replay"}, {})
    _solute_sources = list(solute_sources_for_mapped_sources(
        mapped_sources, data_doc))
    _ = _solute_sources
    from yellowstone_python.river.solute_transport import BoundaryConcentrations
    upstream = data_doc["features"]["firehole_upstream_boundary"]
    cl_value = float(upstream["chloride_mg_l"]["value"])
    as_entry = upstream.get("arsenic_ug_l", {}) or {}
    b_entry = upstream.get("boron_mg_l", {}) or {}
    boundary = BoundaryConcentrations(
        chloride_mg_l=cl_value,
        arsenic_ug_l=0.0 if as_entry.get("value") is None
        else float(as_entry["value"]),
        boron_mg_l=0.0 if b_entry.get("value") is None
        else float(b_entry["value"]),
    )
    boundary_provenance = {
        "chloride_mg_l": upstream["chloride_mg_l"].get("status"),
        "arsenic_ug_l": ("authored_zero_baseline_no_wqp_sample"
                         if as_entry.get("value") is None
                         else as_entry.get("status")),
        "boron_mg_l": ("authored_zero_baseline_no_wqp_sample"
                       if b_entry.get("value") is None
                       else b_entry.get("status")),
    }
    transport = transport_from_mapped_replay(
        replay_doc, boundary_concentrations=boundary)
    rcfg_duration = float(replay_doc.get("duration_s") or 7200.0)
    rcfg_dt = float(replay_doc.get("dt_s") or 2.0)
    rcfg_sample = float(replay_doc.get("sample_s") or 10.0)
    transport.run(duration_s=rcfg_duration, dt_s=rcfg_dt,
                  sample_s=rcfg_sample)
    doc = transport_summary(transport)
    doc["unmodeled_sources"] = unmodeled
    doc["boundary_provenance"] = boundary_provenance
    doc["note"] = ("Grand Prismatic, Opal and Turquoise chemistry is null "
                   "in the data file and recorded as unmodeled sources; "
                   "Excelsior drives the only solute input in the baseline")
    by_cell: dict[str, dict[str, float]] = {}
    conc = doc.get("concentrations", {})
    for i, cell_id in enumerate(doc.get("cell_ids", [])):
        by_cell[cell_id] = {
            "chloride_mg_l": float(conc["chloride_mg_l"][i]),
            "arsenic_ug_l": float(conc["arsenic_ug_l"][i]),
            "boron_mg_l": float(conc["boron_mg_l"][i]),
        }
    return doc, by_cell


def _chloride_validation_bound(solute_doc):
    """Modeled source chloride flux as a reach-increment bound.
Returns a dict suitable for BUILD.json validations.solutes; empty when no sources."""
    if not isinstance(solute_doc, dict) or solute_doc.get(
            "status") == "no_mapped_sources":
        return {"status": "no_mapped_sources",
                "note": "no modeled source flux to report as a bound"}
    budget = solute_doc.get("mass_budget", {}) or {}
    solutes_budget = budget.get("solutes", {}) or {}
    chloride_entry = solutes_budget.get("chloride_mg_l") or {}
    time_s = float(solute_doc.get("time_s") or 0.0)
    flux_g_s = None
    if isinstance(chloride_entry, dict) and time_s > 0.0:
        lateral_mass = chloride_entry.get("lateral_input_mass")
        if lateral_mass is not None:
            flux_g_s = float(lateral_mass) / time_s
    return {
        "schema": "yellowstone.chloride_validation.v1",
        "status": "bound_not_match",
        "modeled_source_chloride_flux_g_s": flux_g_s,
        "window_s": time_s,
        "note": ("Midway-only source flux is a bound on the between-gauge "
                 "chloride increment; other basins between the gauges "
                 "are not modeled"),
        "source_data": solute_doc.get("provenance", {}),
    }


def _run_river_oxygen(replay_doc, air_c):
    """One backward-Euler DO advection pass across replay cells.
Returns (sidecar doc, per-cell DO dict mg/L)."""
    from yellowstone_python.aquatic.river_oxygen import OxygenCell, advect_cells, saturation_mg_l
    cells_in = replay_doc.get("cells", []) or []
    frames = replay_doc.get("frames", []) or []
    last_frame = frames[-1] if frames else {}
    temps = last_frame.get("temperature_c") or []
    oxygen_cells: list[OxygenCell] = []
    for i, cell in enumerate(cells_in):
        hydro = cell.get("hydraulics") or {}
        velocity = float(hydro.get("velocity_continuity_m_s")
                         or hydro.get("velocity_rect_m_s") or 0.1)
        temp_c = float(temps[i]) if i < len(temps) else float(air_c)
        oxygen_cells.append(OxygenCell(
            id=str(cell["id"]),
            length_m=float(cell["length_m"]),
            width_m=float(cell["width_m"]),
            depth_m=float(cell.get("depth_m", 1.0)),
            velocity_m_s=max(0.01, velocity),
            temp_c=temp_c,
            do_mg_l=float(saturation_mg_l(temp_c)),
        ))
    if not oxygen_cells:
        return ({"schema": "yellowstone.river_oxygen.v1",
                 "status": "no_cells",
                 "n_cells": 0}, {})
    upstream_do = float(saturation_mg_l(float(air_c)))
    rcfg_dt = max(1.0, float(replay_doc.get("dt_s") or 60.0))
    report = advect_cells(oxygen_cells, upstream_do_mg_l=upstream_do,
                          dt_s=rcfg_dt)
    cells_out = report.get("cells", [])
    by_cell = {oxygen_cells[i].id: float(cells_out[i]["do_mg_l"])
               for i in range(len(cells_out))}
    doc = {
        "schema": "yellowstone.river_oxygen.v1",
        "status": "fitted_not_validated",
        "n_cells": len(cells_out),
        "upstream_do_mg_l": upstream_do,
        "dt_s": rcfg_dt,
        "do_mg_l_by_cell": by_cell,
        "max_advective_courant": report.get("max_advective_courant"),
        "units": {"do_mg_l_by_cell": "mg/L"},
        "provenance": {
            "source": ("river_oxygen.advect_cells backward Euler upwind "
                       "with Covar reaeration regime"),
        },
    }
    return doc, by_cell


def _run_periphyton(replay_doc, weather):
    """Short periphyton development pass per replay cell.
Returns (sidecar doc, per-cell biomass dict mg C/m2)."""
    from yellowstone_python.aquatic.periphyton import PeriphytonParams, step_biomass
    cells_in = replay_doc.get("cells", []) or []
    frames = replay_doc.get("frames", []) or []
    last_frame = frames[-1] if frames else {}
    temps = last_frame.get("temperature_c") or []
    params = PeriphytonParams()
    sw = max(0.0, 1000.0 * (1.0 - float(weather.get("cloud", 0.16))))
    dt_s = 3600.0
    biomass_by_cell: dict[str, float] = {}
    for i, cell in enumerate(cells_in):
        temp_c = float(temps[i]) if i < len(temps) else 15.0
        step = step_biomass(
            biomass_mg_c_m2=50.0,
            shortwave_w_m2=sw,
            temp_c=temp_c,
            grazer_density=0.0,
            dt_s=dt_s,
            params=params)
        biomass_by_cell[str(cell["id"])] = float(step["biomass_mg_c_m2"])
    doc = {
        "schema": "yellowstone.periphyton.v1",
        "status": "illustrative_not_validated",
        "n_cells": len(cells_in),
        "biomass_mg_c_m2_by_cell": biomass_by_cell,
        "dt_s": dt_s,
        "shortwave_w_m2": sw,
        "units": {"biomass_mg_c_m2_by_cell": "mg C/m2"},
        "provenance": {
            "source": ("periphyton.step_biomass with Platt-Jassby light "
                       "response and Eppley Q10 temperature factor"),
            "shortwave_source": "cloud-weighted 1000 W/m2 clear-sky illustrative",
        },
    }
    return doc, biomass_by_cell


from yellowstone_python.pipeline.shared import DEFAULT_TRIBUTARIES, PKG_ROOT, Path, REACH_BRIDGE, _find, copy, json
from yellowstone_python.pipeline.stages.river import _chloride_validation_bound, _hyporheic_zones_dict, _river_shading_dict, _run_periphyton, _run_river_oxygen, _run_solute_transport, check_cross_sections, run_replay_solver
from yellowstone_python.pipeline.stages.thermal import _excelsior_lateral_override

READS = ('air0', 'baseline', 'hcfg', 'hour0', 'met_bundle', 'outflow_chain', 'overland_field', 'overland_runoff_m3_s', 'run_mode_norm', 'runoff_m3_s', 'wcfg', 'weather_frag', 'world')
WRITES = ('baseflow_m3s', 'boundary_m3s', 'bridge', 'budget_mode_source', 'chloride_validation_bound', 'cross_sections_report', 'do_mg_l_by_cell', 'energy_budget_choice', 'excelsior_override', 'hydro_ledger', 'oxygen_doc', 'periphyton_doc', 'reaches_in', 'replay_doc', 'river_shading_doc', 'river_state', 'solute_concentrations_by_cell', 'solute_doc')

def run(state: dict, cfg: dict) -> dict:
    """Advance the river stage and return its state."""
    air0 = state['air0']
    baseline = state['baseline']
    hcfg = state['hcfg']
    hour0 = state['hour0']
    met_bundle = state['met_bundle']
    outflow_chain = state['outflow_chain']
    overland_runoff_m3_s = state['overland_runoff_m3_s']
    run_mode_norm = state['run_mode_norm']
    runoff_m3_s = state['runoff_m3_s']
    wcfg = state['wcfg']
    weather_frag = state['weather_frag']
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

    # hydro.
    tribs = {**DEFAULT_TRIBUTARIES, **hcfg.get("tributaries", {})}
    reaches_in = copy.deepcopy(baseline["river_reaches"])
    by_id = {r["id"]: r for r in reaches_in}
    for rid, names in hcfg.get("attach", {}).items():
        if rid not in by_id:
            raise ValueError(f"hydro.attach reach {rid!r} not in chain "
                             f"{list(by_id)}")
        if not isinstance(names, list):
            raise ValueError(
                f"hydro.attach[{rid!r}] must be a list of tributary names")
        for n in names:
            if n not in tribs:
                raise ValueError(
                    f"unknown tributary {n!r}; have {sorted(tribs)}")
            t = tribs[n]
            if t.get("flow_m3s", 0.0) > 0:
                by_id[rid].setdefault("lateral_sources", []).append(
                    {"id": n, **t, "status": "illustrative tributary"})
    baseflow_m3s = float(hcfg.get("boundary_m3s", baseline["boundary_m3s"]))
    boundary_m3s = baseflow_m3s + runoff_m3_s + overland_runoff_m3_s
    # --- 1-D advection-dispersion replay ---
    replay_cfg_scope = cfg.get("replay", {}) or {}
    energy_budget_default = bool(replay_cfg_scope.get("energy_budget", False))
    full_bundle = bool(
        met_bundle and all(k in wcfg for k in
                           ("night_air_c", "humidity", "cloud", "wind_xz_mps")))
    energy_budget_choice = energy_budget_default
    budget_mode_source = (
        "replay.energy_budget explicit" if "energy_budget" in replay_cfg_scope
        else "replay.energy_budget default (false)")
    if ("energy_budget" not in replay_cfg_scope
            and run_mode_norm in ("hindcast", "observed_replay")
            and full_bundle):
        energy_budget_choice = True
        budget_mode_source = (
            "run_mode=hindcast/observed_replay with full bundle; "
            "explicit energy budget default on")
    cfg_for_replay = copy.deepcopy(cfg)
    cfg_for_replay.setdefault("replay", {})
    cfg_for_replay["replay"]["energy_budget"] = energy_budget_choice
    # Cross-section schema check: parse and compare against world river/pool features.
    cross_sections_doc = None
    cs_file_cfg = replay_cfg_scope.get("cross_sections_file")
    if isinstance(cs_file_cfg, str) and cs_file_cfg:
        cs_path = Path(cs_file_cfg)
        if not cs_path.is_absolute():
            cs_path = PKG_ROOT / cs_path
        try:
            cross_sections_doc = json.loads(cs_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as cs_exc:
            raise ValueError(
                f"replay.cross_sections_file {cs_path} unreadable: {cs_exc}"
            ) from cs_exc
    cross_sections_report = check_cross_sections(cross_sections_doc, world)
    preview_replay = run_replay_solver(cfg_for_replay, baseline, world,
                                        hour0=hour0, weather=weather_frag,
                                        boundary_m3s=boundary_m3s)
    preview_cells = preview_replay.get("cells", [])
    shading_cfg = (cfg.get("replay", {}) or {}).get("shading", {}) or {}
    hyporheic_cfg = (cfg.get("replay", {}) or {}).get("hyporheic", {}) or {}
    shortwave_multiplier_by_cell, river_shading_doc = _river_shading_dict(
        preview_cells, preview_replay.get("simulation_start_epoch_unix"),
        shading_cfg)
    hyporheic_zones_dict = _hyporheic_zones_dict(preview_cells, hyporheic_cfg)
    excelsior_override = _excelsior_lateral_override(outflow_chain)
    from yellowstone_python.pipeline.stages.land import _overland_boundary_series
    overland_series = _overland_boundary_series(boundary_m3s - overland_runoff_m3_s, state["overland_field"])
    replay_doc = run_replay_solver(
        cfg_for_replay, baseline, world,
        hour0=hour0, weather=weather_frag,
        boundary_m3s=boundary_m3s,
        shortwave_multiplier=shortwave_multiplier_by_cell,
        hyporheic_zones=hyporheic_zones_dict,
        excelsior_override=excelsior_override,
        boundary_series=overland_series)
    if overland_series is not None:
        replay_doc["forcing"]["overland_support"] = {"phase": "liquid", "start_s": 0.0,
            "end_s": overland_series["times_s"][-1], "application": "source_volume_routed_once"}
    replay_doc.setdefault("provenance", {})["energy_budget_source"] = (
        budget_mode_source)
    replay_doc["provenance"]["cross_sections_report"] = cross_sections_report

    from yellowstone_python.exporters.runtime_series import reach_summaries
    river_state = reach_summaries(replay_doc, reaches_in)
    budget = replay_doc["final_budget"]
    hydro_ledger = {"heat_budget_error_j": budget["heat_residual_j"],
                    "water_budget_error_m3": budget["water_residual_m3"],
                    "scope": "replay_relative_conservation",
                    "replay_budget": budget}
    bridge = _find(river_state, "id", REACH_BRIDGE, "reach")
    solute_doc, solute_concentrations_by_cell = _run_solute_transport(replay_doc)
    chloride_validation_bound = _chloride_validation_bound(solute_doc)
    oxygen_doc, do_mg_l_by_cell = _run_river_oxygen(replay_doc, air0)
    periphyton_doc, periphyton_by_cell = _run_periphyton(replay_doc, weather_frag)


    state.update({'baseflow_m3s': baseflow_m3s, 'boundary_m3s': boundary_m3s, 'bridge': bridge, 'budget_mode_source': budget_mode_source, 'chloride_validation_bound': chloride_validation_bound, 'cross_sections_report': cross_sections_report, 'do_mg_l_by_cell': do_mg_l_by_cell, 'energy_budget_choice': energy_budget_choice, 'excelsior_override': excelsior_override, 'hydro_ledger': hydro_ledger, 'oxygen_doc': oxygen_doc, 'periphyton_doc': periphyton_doc, 'reaches_in': reaches_in, 'replay_doc': replay_doc, 'river_shading_doc': river_shading_doc, 'river_state': river_state, 'solute_concentrations_by_cell': solute_concentrations_by_cell, 'solute_doc': solute_doc})
    return state
