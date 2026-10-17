"""Sidecars build operations."""
from __future__ import annotations

import logging

from yellowstone_python.pipeline.shared import MAT_IMAGERY_DATE_UTC, OUTFLOW_SITE_ALTITUDE_M, PKG_ROOT, Path, SITE_LAT_DEG, SITE_LON_DEG, SNOW_STORAGE_TOL_MM, default_world_root, json, normalize_run_mode, prescribed_quantities, sha256_file, write_json_atomic, write_sidecar
from yellowstone_python.pipeline.manifest import build_manifest
from yellowstone_python.pipeline.stages.river import resolve_replay_start_epoch
from yellowstone_python.pipeline.stages.thermal import _run_mat_validation, _run_outflow_foodweb

_LOGGER = logging.getLogger(__name__)

def _atomic_json_write(path: Path, obj) -> None:
    write_json_atomic(path, obj, indent=2)


def _write_variant_and_gate(cfg, baseline, deps, res, out, bid, _ok):
    from yellowstone_python.common.io import load_json
    from yellowstone_python.common.provenance import sha256_file
    from yellowstone_python.service.live.engine import MODEL_COMPONENTS
    res["variant"]["frame_header"] = {"run_mode": cfg["run_mode"], "build_id": bid,
                                      "model_components": MODEL_COMPONENTS}
    world = load_json(Path(cfg["world_root"]) / "data" / "world.json")
    world["simulation_epoch_unix"] = res["variant"]["simulation_epoch_unix"]
    _atomic_json_write(out / "world.runtime.json", world)
    res["replay_doc"]["input_files"] = {"world": {"path": "data/world.json",
                                                "sha256": sha256_file(out / "world.runtime.json")}}
    res["variant"]["build_id"] = bid
    import shutil
    for relative in ("outflow_network/outflow_network.json", "outflow_network/wet_mask.i16",
                     "outflow_network/flow_fraction.f32", "outflow_network/in_pool.i16", "snow_patch_mask.png"):
        source = Path(cfg["world_root"]) / "data" / relative
        if source.is_file():
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    eco_doc = write_sidecar(
        out / "ecosystem.variant.json", {"ecosystem": res["variant"]},
        sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                  "sha256": deps["ecosystem.json"]}],
        params={"air_c_at_start_C": res["air0"],
                "simulate_seconds": res.get("sim_s", 0.0),
                "heat_ledger": res["hydro_ledger"],
                "timeline": res["timeline"],
                "note": "drop-in replacement for data/ecosystem.json"},
        code_rev=deps["code_rev"])
    _atomic_json_write(out / "ecosystem.godot.json", res["variant"])
    _atomic_json_write(out / "river_state.json", res["river_state"])
    if res["replay_doc"].get("intervention"):
        from yellowstone_python.exporters.runtime_series import mapped_comparison
        comparison = mapped_comparison(res["replay_doc"])
        comparison["build_id"] = bid
        _atomic_json_write(out / "portfolio_comparison.json", comparison)
    replay_payload = res["replay_doc"]
    replay_payload.setdefault("forcing", {})
    replay_payload["forcing"]["catchment_runoff"] = {
        "baseflow_m3_s": float(res["baseflow_m3s"]),
        "runoff_m3_s": float(res["catchment"].get("runoff_m3_s", 0.0)),
        "effective_boundary_m3_s": float(res["boundary_m3s"]),
        "enabled": bool(res["catchment"].get("enabled", False)),
        "status": res["catchment"].get("status",
                                       "illustrative_not_calibrated"),
    }
    if res["replay_doc"].get("frames"):
        frames = res["replay_doc"]["frames"]
        if "wall_time" not in frames[0]:
            start_epoch = res["replay_doc"].get("simulation_start_epoch_unix")
            if start_epoch is None:
                start_epoch, _ = resolve_replay_start_epoch(cfg,
                                                            res.get("hour0"))
            frames[0]["wall_time"] = float(start_epoch)
    write_sidecar(out / "river_replay.json",
                  {"replay": replay_payload},
                  sources=[{"file": "yellowstone_midway/data/world.json",
                            "sha256": deps["world.json"]}],
                  params={"method": "1-D finite-volume advection-dispersion",
                          "energy_budget": res["replay_doc"].get("model", {}).get("surface_flux", "newton_lumped"),
                          "status": "illustrative, not calibrated"},
                  code_rev=deps["code_rev"])
    if (cfg.get("replay", {}) or {}).get("netcdf", False):
        from yellowstone_python.river.nc_export import write_replay_netcdf
        try:
            write_replay_netcdf(replay_payload["frames"],
                                [c["id"] for c in replay_payload["cells"]],
                                out / "river_replay.nc")
        except (ImportError, ValueError) as exc:
            _LOGGER.warning("netcdf export skipped: %s", exc)
    _atomic_json_write(out / "weather.json", {"weather": res["weather_frag"], "wind_trace_60s": res["wind_trace"]})
    if res["met_bundle"]:
        _atomic_json_write(out / "met.json", res["met_bundle"])
    write_sidecar(out / "overland_flow.json", res["overland_field"],
                  sources=[{"file": "yellowstone_midway/data/terrain.f32",
                            "sha256": deps["terrain.f32"]}],
                  params={"method": "hydrosim local-inertial shallow water, "
                          "block-mean of terrain.f32"},
                  code_rev=deps["code_rev"],
                  status=res["overland_field"].get("status",
                                                   "illustrative_not_calibrated"))
    write_sidecar(out / "catchment_runoff.json", res["catchment"],
                  sources=[{"file": "configs/baseline.yaml",
                            "sha256": deps.get("config")}],
                  params={"method": "snow ledger runoff depth scaled to the "
                          "configured catchment area",
                          "baseflow_m3s": res["baseflow_m3s"],
                          "effective_boundary_m3s": res["boundary_m3s"]},
                  code_rev=deps["code_rev"],
                  status=res["catchment"]["status"])
    _write_fragment_sidecars(cfg, baseline, deps, res, out)
    if res.get("mammal_catalogue", {}).get("enabled") is not False:
        _atomic_json_write(out / "mammal_catalogue.json", res["mammal_catalogue"])
        write_sidecar(out / "mammals.json",
                      {"mammals": res["mammal_doc"],
                       "encounters": res["mammal_encounters"],
                       "temporal_support": "initial state; time-varying states are in ecosystem.python_series and live frames"},
                      sources=[{"file": "yellowstone_python/data/mammal_catalogue.json",
                                "sha256": deps["external_inputs"]["mammal_catalogue"]["sha256"]}],
                      params={"seed": res["variant"]["mammals"]["seed"],
                              "population_basis": "authored relative populations; local abundance unavailable",
                              "encounter_basis": "authored observation layer; not a field sighting frequency"},
                      code_rev=deps["code_rev"], status="illustrative_not_calibrated")

    from yellowstone_python.validation.checks import run_all
    from yellowstone_python.aquatic.aquatic_foodweb import thermal_landscape
    from yellowstone_python.registry.claims import registry_errors as _claims_registry_errors
    from yellowstone_python.registry.coupling import check_coupling, validate_contract
    from yellowstone_python.registry.equations import validate_inventory
    from yellowstone_python.registry.param_registry import registry_errors as _param_registry_errors
    mode = normalize_run_mode(cfg.get("run_mode"))
    prescribed = prescribed_quantities(cfg)
    checks = run_all(river_state=res["river_state"], ledger=res["hydro_ledger"],
                     ecosystem_doc=eco_doc, build_id_a=bid,
                     run_mode=mode, prescribed=prescribed,
                     validated_quantities=(),
                     replay_doc=res["replay_doc"],
                     landscape=thermal_landscape(res["replay_doc"]),
                     membership=res["fh_membership"],
                     chainage=res["fh_chainage"],
                     chainage_offset_m=res["fh_chainage_offset_m"])
    checks["metrics"]["validation_claims"] = []
    # Authored per-cell records enable head_gradient_exchange; absent records leave coupling partial.
    gw_cells = (cfg.get("hydro", {}) or {}).get("groundwater", {}).get("cells")
    gw_provenance: dict
    if isinstance(gw_cells, list) and gw_cells:
        from yellowstone_python.land.groundwater_provider import head_gradient_exchange
        try:
            gw_result = head_gradient_exchange(gw_cells)
            gw_provenance = {
                "status": "wired",
                "totals": gw_result["totals"],
                "n_gaining_sources": len(gw_result["sources"]),
                "n_losing_cells": len(gw_result["losing"]),
                "note": ("River.Source accepts only nonnegative flow; losing "
                         "cells are published to groundwater_losing.json"),
            }
            write_sidecar(out / "groundwater_losing.json",
                          {"losing": gw_result["losing"],
                           "totals": gw_result["totals"]},
                          sources=[{"id": "code", "sha256": deps["code"]}],
                          params={"method": "head-gradient conductance "
                                            "C = K W L / b; q = C (h_aq - h_r)"},
                          code_rev=deps["code_rev"],
                          status="authored_not_calibrated")
        except (ValueError, KeyError) as gw_exc:
            gw_provenance = {"status": "input_invalid",
                             "reason": str(gw_exc)}
    else:
        gw_provenance = {
            "status": "partial",
            "reason": ("no hydro.groundwater.cells configured; the "
                       "head-gradient exchange needs per-cell bed "
                       "conductivity, thickness, width, length, aquifer "
                       "and river heads, and an aquifer temperature"),
        }
    # Replay numerical warnings enter CHECKS.metrics without independently failing the build.
    replay_numerical_warnings = (
        res["replay_doc"].get("numerical_checks", {})
                         .get("numerical_warnings", []) or [])
    checks["metrics"]["replay_numerical_warnings"] = list(
        replay_numerical_warnings)
    checks["metrics"]["groundwater_exchange"] = gw_provenance
    checks["metrics"]["chloride_validation_bound"] = res.get(
        "chloride_validation_bound")
    _mat_val = res.get("mat_validation") or {}
    _outflow_chain_defect = None
    _outflow_chain_meta = res.get("outflow_chain") or {}
    if _outflow_chain_meta:
        pruned = _outflow_chain_meta.get("outflow_sidecar", {}).get(
            "pruned_dangling_upstream_segments", 0)
        if pruned:
            _outflow_chain_defect = {
                "rule": "wp_a_dangling_upstream_segments",
                "count": int(pruned),
                "owner": "wp-a",
                "note": ("WP-A outflow_network.json carries upstream_id "
                         "references to pruned segments; build shim "
                         "rewrites them to None"),
            }
    checks["metrics"]["validations"] = {
        "solutes": res.get("chloride_validation_bound"),
        "mats": _mat_val,
    }
    checks["metrics"]["outflow_chain_defects"] = (
        [_outflow_chain_defect] if _outflow_chain_defect else [])
    # Aggregate contract vocabulary, equation, claim, and parameter registry checks into the build gate.
    registry_failures = (
        _claims_registry_errors()
        + validate_contract()
        + validate_inventory(root=PKG_ROOT / "yellowstone_python")
        + _param_registry_errors()
    )
    if registry_failures:
        checks["passed"] = False
        checks["failures"] += [f"registry: {e}" for e in registry_failures]
    checks["metrics"]["registry_failures"] = registry_failures
    # Reach and SNOTEL gates compare holdout RMSE against evidence artifacts.
    from yellowstone_python.validation.claims import run_claim_gates
    claim_gate = run_claim_gates()
    checks["metrics"]["claim_gates"] = claim_gate["gates"]
    if not claim_gate["passed"]:
        checks["passed"] = False
        checks["failures"] += [f"claim_gate: {f}"
                               for f in claim_gate["failures"]]
    # coupling.json holds the contract; coupling_check.json records its verification result.
    coupling_result = check_coupling(
        res["replay_doc"], thermal_landscape(res["replay_doc"]))
    checks["metrics"]["coupling_check_passed"] = coupling_result["passed"]
    if res["godot_errors"]:
        checks["passed"] = False
        checks["failures"] += ["godot: " + e for e in res["godot_errors"]]
    if res["prop_violations"]:
        checks["passed"] = False
        checks["failures"] += [f"apron: proposal inside exclusion: {v}"
                               for v in res["prop_violations"][:5]]
    if res["trout_blockers"]:
        checks["passed"] = False
        checks["failures"] += [f"refuge: trout route inside apron: {v}"
                               for v in res["trout_blockers"][:5]]
    if res["substrate_failures"]:
        checks["passed"] = False
        checks["failures"] += [f"substrate: {v}" for v in res["substrate_failures"]]
    if not (0.0 <= res["act0"] <= 1.0):
        checks["passed"] = False
        checks["failures"] += [f"insects: activity {res['act0']} out of [0,1]"]
    for p in res["patches1"]:
        if not (0.0 <= float(p["biomass"]) <= float(p.get("capacity", 1.0))):
            checks["passed"] = False
            checks["failures"] += [f"patch {p['id']}: biomass out of bounds"]
    if res["grazer_blockers"]:
        checks["passed"] = False
        checks["failures"] += [f"grazer: route violates habitat: {v}"
                               for v in res["grazer_blockers"][:5]]
    for p in res["patches2"]:
        if float(p.get("snow_mm", 0.0)) < 0:
            checks["passed"] = False
            checks["failures"] += [f"snow: negative storage {p['id']}"]
    snow_ledger = res["snow_ledger"]
    if abs(snow_ledger.get("storage_residual_mm",
                           float("inf"))) > SNOW_STORAGE_TOL_MM:
        checks["passed"] = False
        checks["failures"] += [
            f"snow: storage residual {snow_ledger.get('storage_residual_mm')} mm"]
    checks["metrics"]["n_proposals"] = len(res["proposals"])
    checks["metrics"]["n_shells"] = len(res["shells"])
    rb = res["replay_doc"].get("final_budget", {})
    checks["metrics"]["replay_heat_budget_error"] = rb.get("heat_residual_j", float("inf"))
    checks["metrics"]["replay_water_budget_error_m3"] = rb.get("water_residual_m3", float("inf"))
    checks["metrics"]["replay_n_cells"] = len(res["replay_doc"].get("cells", []))
    checks["metrics"]["replay_n_frames"] = len(res["replay_doc"].get("frames", []))
    hyd_sum = res["replay_doc"].get("hydraulics_summary", {})
    checks["metrics"]["replay_travel_time_s"] = hyd_sum.get("total_travel_time_s")
    checks["metrics"]["replay_manning_median"] = hyd_sum.get(
        "manning_consistency_ratio_median")
    checks["metrics"]["replay_flat_grade_cells"] = hyd_sum.get(
        "n_flat_or_adverse_grade_cells")
    sl = res["aquatic_foodweb"]["trout"]
    checks["metrics"]["foodweb_refuge_s_m"] = sl.get("s_m")
    checks["metrics"]["foodweb_refuge_temp_c"] = sl.get("temperature_c")
    checks["metrics"]["foodweb_refuge_U"] = sl.get("U")
    checks["metrics"]["foodweb_emergence_total"] = res["aquatic_foodweb"][
        "prey_totals"].get("emergence")
    checks["metrics"]["foodweb_dipper_per_day"] = res["aquatic_foodweb"][
        "dipper"].get("intake_per_day")
    if not res["replay_doc"].get("numerical_checks", {}).get("passed", False):
        checks["passed"] = False
        checks["failures"].append("replay: budget closure checks failed")
    from collections import Counter
    checks["metrics"]["phenology"] = dict(Counter(
        p.get("phenology", "?") for p in res["patches2"]))
    checks["metrics"]["substrate_ok"] = not res["substrate_failures"]
    from yellowstone_python.river.identifiability import run_diagnostics
    diagnostics = run_diagnostics()
    checks["metrics"]["identifiability_rank"] = diagnostics[
        "conditioning"]["rank"]
    checks["metrics"]["identifiability_max_cost"] = diagnostics[
        "multistart"]["max_cost"]
    checks["metrics"]["structural_surface_gap_c"] = diagnostics[
        "structural_surface"]["max_abs_gap_c"]
    _atomic_json_write(out / "CHECKS.json", checks)
    from yellowstone_python.registry.claims import CLAIMS
    from yellowstone_python.registry.coupling import EXCHANGES
    from yellowstone_python.registry.equations import COMPONENTS
    from yellowstone_python.registry.param_registry import PARAMS
    from yellowstone_python.river.benchmarks import run_all_benchmarks
    write_sidecar(out / "numerics_benchmarks.json",
                  run_all_benchmarks(),
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "identifiability.json",
                  diagnostics,
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "coupling.json",
                  {"schema": "yellowstone.coupling.v1",
                   "exchanges": EXCHANGES},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "coupling_check.json",
                  {"schema": "yellowstone.coupling_check.v1",
                   **coupling_result},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "claims.json",
                  {"schema": "yellowstone.claims.v1", "claims": CLAIMS},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "param_registry.json",
                  {"schema": "yellowstone.param_registry.v1",
                   "params": PARAMS},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "equations.json",
                  {"schema": "yellowstone.equations.v1",
                   "components": COMPONENTS},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode},
                  code_rev=deps["code_rev"])
    from yellowstone_python.exporters.godot_sidecars import produce_all as _produce_sidecars
    sidecar_written, sidecar_gaps = _produce_sidecars(out)
    if sidecar_gaps:
        _LOGGER.warning("godot sidecar gaps: %s", "; ".join(sidecar_gaps))
    from yellowstone_python.common.io import sha256_file
    strategy = "mapped_fv_explicit" if res.get("energy_budget_choice") else "mapped_fv_newton"
    checks["assessment"] = {
        "build_id": bid, "model_variant_id": strategy,
        "input_identity": _portable_input_identity(cfg, deps),
        "artifact_hashes": {str(path.relative_to(out)): sha256_file(path)
            for path in sorted(out.rglob("*")) if path.is_file() and path.name not in ("BUILD.json", "CHECKS.json")},
        "numerical_targets": ["river_replay.json", "ecosystem.godot.json"],
        "scope": "numerical and contract checks; generated artifact bytes bound at completion"}
    _atomic_json_write(out / "CHECKS.json", checks)
    _atomic_json_write(
        out / "BUILD.json",
        build_manifest(cfg, deps, res, checks, bid, mode, prescribed, out))
    _LOGGER.info("build %s passed=%s to %s", bid, checks["passed"], out)
    for f in checks["failures"]:
        _LOGGER.error("FAIL: %s", f)


def _portable_input_identity(cfg, deps):
    """Identify the effective configuration, logical inputs and model source."""
    from yellowstone_python.common.provenance import portable_identity_payload, sha256_json
    return sha256_json(portable_identity_payload(cfg, deps))


def _write_fragment_sidecars(cfg, baseline, deps, res, out):
    from yellowstone_python.aquatic.fish import THERMAL_SPECIES
    from yellowstone_python.insects_birds import foraging_state
    world_root = Path(cfg.get("world_root") or default_world_root())
    write_sidecar(out / "patch_state.json", {"patches": res["patches1"]},
                  sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                            "sha256": deps["ecosystem.json"]}],
                  params={"veg_ledger": res["veg_ledger"],
                          "hours": res.get("sim_s", 0.0) / 3600.0},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "planting_proposal.json",
                  {"proposals": res["proposals"],
                   "review_log": res["review_log"],
                   "review": "merge reviewed rows into placement_overrides.json::{add}; never overwrite placements.json"},
                  sources=[{"file": "yellowstone_midway/data/placements.json",
                            "sha256": deps["placements.json"]}],
                  params={"guild": res["prop_cfg"].get("guild"),
                          "seed": res["prop_cfg"].get("seed"),
                          "n_accepted": len(res["proposals"]),
                          "n_rejected": sum(1 for r in res["review_log"]
                                            if r["decision"] == "reject")},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "insect_bird.json",
                  {"activity": res["act0"],
                   "state": foraging_state(res["act0"]),
                   "wind_mps": res["wind_mag"],
                   "flowering_stage": res["flowering"],
                   "compartments": res["prey_ledger"],
                   "wildlife": [r for r in res["wildlife1"]
                                if r.get("id") in ("dipper_01", "raven_01")]},
                  sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                            "sha256": deps["ecosystem.json"]}],
                  params={"threshold": 0.035,
                          "note": "bird cadence from Holling intake + legacy activity gate"},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "fish.json",
                   {"wildlife": [r for r in res["variant"]["wildlife"] if "trout" in r["id"]],
                    "hydraulics": ("V=Q/A_trap trapezoidal diagnostic per "
                                   "replay cell (solver volumes still "
                                   "rectangular); Manning/Froude/Fischer + "
                                   "travel times in river_replay.json "
                                   "hydraulics_summary; illustrative, not "
                                   "calibrated"),
                    "thermal_species": {k: {
                        "t_opt_lo_c": v["t_opt_lo_c"],
                        "t_opt_hi_c": v["t_opt_hi_c"],
                        "t_feed_zero_c": v["t_feed_zero_c"],
                        "t_refuge_c": v["t_refuge_c"],
                        "t_uilt_c": v["t_uilt_c"],
                        "status": v["status"]} for k, v in
                        THERMAL_SPECIES.items()}},
                  sources=[{"file": "yellowstone_midway/data/world.json",
                            "sha256": deps["world.json"]}],
                  params={"weights": cfg.get("fish", {}).get("weights", "defaults"),
                           "activity": "fish.thermal_performance feeding by species",
                           "refuge": "chainage-window argmax suitability"},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "aquatic_foodweb.json",
                  {"foodweb": res["aquatic_foodweb"]},
                  sources=[{"file": "yellowstone_midway/data/world.json",
                            "sha256": deps["world.json"]}],
                  params={"method": "14-day insect/trout/dipper food web on "
                                    "replay time-mean thermal landscape",
                          "trout_species": res["aquatic_foodweb"].get(
                              "trout_species"),
                          "status": "illustrative, not calibrated"},
                  code_rev=deps["code_rev"])
    if res.get("benthic_grid") is not None:
        write_sidecar(out / "benthic_grid.json",
                      res["benthic_grid"],
                      sources=[{"file": "yellowstone_midway/data/world.json",
                                "sha256": deps["world.json"]}],
                      params={"method": "insects_birds.develop_benthic_grid "
                                        "driven by replay thermal landscape",
                              "trout_hydraulics_source":
                                  res.get("trout_hydraulics_source")},
                      code_rev=deps["code_rev"])
    write_sidecar(out / "grazer.json",
                  {"wildlife": [r for r in res["wildlife3"]
                                if r.get("kind") in ("bison", "elk")],
                   "planner_corridor": res["corridor"]},
                  sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                            "sha256": deps["ecosystem.json"]}],
                  params={"causal_claim": "none_single",
                          "note": "sparse authored loops; not abundance"},
                  code_rev=deps["code_rev"])
    write_sidecar(out / "season.json",
                  {"patches": [{k: p[k] for k in
                                ("id", "snow_mm", "snow_depth_m",
                                 "snow_cover_fraction", "moisture",
                                 "phenology", "pheno_stress", "gdd") if k in p}
                               for p in res["patches2"]],
                   "season": res["season"],
                   "season_source": res["clock_info"]["season_source"],
                   "clock_hour": res["clock_info"]["clock_hour"],
                   "clock_source": res["clock_info"]["clock_source"],
                   "as_of_local_date": res["clock_info"]["as_of_local_date"],
                   "date_source": res["clock_info"]["date_source"],
                   "ledger": res["snow_ledger"]},
                  sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                            "sha256": deps["ecosystem.json"]}],
                  params={"method": "degree-day + soil bucket, verified ledger",
                          "geometry": "frozen; surfaces/phenology only"},
                  code_rev=deps["code_rev"])
    # integration sidecars from model.
    _write_integration_sidecars(deps, res, out)


def _write_pool_ramps(shells, build_dir, ph=8.0):
    """Produce and write per-pool color ramps as PNG plus JSON per shell."""
    from yellowstone_python.thermal_features.microbial_mats import pool_ramp, write_pool_ramp_png
    out_dir = Path(build_dir) / "pool_ramps"
    out_dir.mkdir(parents=True, exist_ok=True)
    emitted = []
    for shell in shells:
        try:
            ramp = pool_ramp(shell, ph=ph)
        except (ValueError, KeyError):
            continue
        pool_id = str(shell.get("id") or "pool")
        png_path = out_dir / f"ramp_{pool_id}.png"
        json_path = out_dir / f"ramp_{pool_id}.json"
        write_pool_ramp_png(ramp, str(png_path))
        write_json_atomic(json_path, ramp, indent=2)
        emitted.append({"pool_id": pool_id, "png": png_path.name,
                        "json": json_path.name})
    return emitted


def mat_imagery_pigment_ref() -> tuple[float, dict]:
    """Steady pigment index on the NAIP acquisition date under clear sky, with its insolation record."""
    from yellowstone_python.thermal_features.microbial_mats import daily_mean_insolation_w_m2, steady_state_pigment_index
    insolation = daily_mean_insolation_w_m2(
        MAT_IMAGERY_DATE_UTC, SITE_LAT_DEG, SITE_LON_DEG,
        0.0, altitude_m=OUTFLOW_SITE_ALTITUDE_M)
    insolation["date_utc"] = MAT_IMAGERY_DATE_UTC
    return (steady_state_pigment_index(insolation["all_sky_mean_w_m2"]),
            insolation)


def _write_mat_appearance(outflow_chain, world_root, out, deps):
    """Write mat_pigment.png from the mat appearance layer and mat_appearance.json.
Returns the metadata, or None when the imagery, mask, DEM or flow raster is absent."""
    import yellowstone_python.thermal_features.mat_appearance as mat_appearance
    from yellowstone_python.thermal_features.microbial_mats import CORE_GRID_SIZE, CORE_HALF_M
    from yellowstone_python.land.vegetation import HALF as WORLD_HALF_M
    photo_path = Path(world_root) / "references" / "midway_orthophoto_detail.jpg"
    mask_path = Path(world_root) / "assets" / "textures" / "habitat_mask.png"
    dem = outflow_chain.get("dem")
    flow = (outflow_chain.get("network_rasters") or {}).get("flow_fraction")
    if (dem is None or flow is None or not photo_path.is_file()
            or not mask_path.is_file()):
        return None
    size = CORE_GRID_SIZE * mat_appearance.UPSAMPLE
    photo = mat_appearance.load_photo(str(photo_path), size)
    mineral = mat_appearance.load_mineral(str(mask_path), size,
                                          world_half_m=WORLD_HALF_M,
                                          core_half_m=CORE_HALF_M)
    pigment_ref, ref_insolation = mat_imagery_pigment_ref()
    meta = mat_appearance.write_mat_appearance_png(
        outflow_chain["mat_state"], outflow_chain["outflow_raster"], flow,
        dem, photo, mineral, str(out / "mat_pigment.png"),
        pigment_ref=pigment_ref, ph=8.0)
    meta.pop("sources", None)
    meta["pigment_ref_insolation"] = ref_insolation
    meta["pigment_ref_basis"] = (
        "steady_state_pigment_index of the clear-sky daily mean shortwave "
        "on the imagery acquisition date")
    write_sidecar(
        out / "mat_appearance.json", meta,
        sources=[{"file": "yellowstone_midway/references/"
                          "midway_orthophoto_detail.jpg",
                  "sha256": sha256_file(photo_path),
                  "acquired": MAT_IMAGERY_DATE_UTC},
                 {"file": "yellowstone_midway/assets/textures/"
                          "habitat_mask.png",
                  "sha256": sha256_file(mask_path)},
                 {"file": "yellowstone_midway/data/world.json",
                  "sha256": deps["world.json"]}],
        params={"png": "mat_pigment.png",
                "pigment_ref": pigment_ref,
                "upsample": mat_appearance.UPSAMPLE},
        code_rev=deps["code_rev"],
        status=meta["status"])
    return meta


def _write_integration_sidecars(deps, res, out):
    """integration sidecars for the new modules.
Each sidecar carries schema, status, units and provenance per interfaces.md."""
    world_sha = deps["world.json"]
    code_rev = deps["code_rev"]
    ground_field = res.get("ground_heat_field")
    if ground_field:
        write_sidecar(out / "ground_heat.json", ground_field,
                      sources=[{"file": "yellowstone_midway/data/world.json",
                                "sha256": world_sha}],
                      params={"method": "heat_flux_at by apron mask",
                              "status": ground_field.get("status",
                                                         "authored")},
                      code_rev=code_rev,
                      status=ground_field.get("status", "authored"))
    soil_t = res.get("soil_t_by_patch")
    if isinstance(soil_t, dict):
        write_sidecar(out / "soil_temperature.json",
                      {"schema": "yellowstone.soil_temperature.v1",
                       "status": "authored",
                       "values_c_by_patch": soil_t,
                       "depth_m": 0.10,
                       "model": "steady_state_conductive_profile",
                       "units": {"values_c_by_patch": "degree_Celsius",
                                 "depth_m": "m"},
                       "provenance": {
                           "source": "ground_heat.soil_temperature_by_patch",
                           "conductivity_w_m_k": 1.3}},
                      sources=[{"file": "yellowstone_midway/data/world.json",
                                "sha256": world_sha}],
                      params={"depth_m": 0.10},
                      code_rev=code_rev,
                      status="authored")
    et_ledger = res.get("et_ledger") or {}
    if et_ledger:
        write_sidecar(out / "evapotranspiration.json", et_ledger,
                      sources=[{"file": "yellowstone_midway/data/world.json",
                                "sha256": world_sha}],
                      params={"method": et_ledger.get(
                          "method", "FAO-56 reference")},
                      code_rev=code_rev,
                      status=et_ledger.get("status", "authored"))
    thermal_by_patch = res.get("thermal_by_patch") or {}
    if thermal_by_patch:
        write_sidecar(out / "winter_grazing.json",
                      {"schema": "yellowstone.winter_grazing.v1",
                       "status": "authored",
                       "thermal_flux_mm_d_by_patch": thermal_by_patch,
                       "snow_depth_by_patch": {
                           p["id"]: float(p.get("snow_depth_m", 0.0))
                           for p in res["patches2"]},
                       "wildlife_grazers": [r for r in res["wildlife3"]
                                            if r.get("kind") in
                                            ("bison", "elk")],
                       "provenance": {
                           "sources":
                               "ground_heat.thermal_flux_mm_d_by_patch; "
                               "snow_season.run_season patches2"},
                       "units": {"thermal_flux_mm_d_by_patch": "mm/day"}},
                      sources=[{"file": "yellowstone_midway/data/world.json",
                                "sha256": world_sha}],
                      params={"method": "warm_ground_refuge_shift"},
                      code_rev=code_rev,
                      status="authored")
    piscivore_reports = res.get("piscivore_reports") or []
    write_sidecar(out / "piscivores.json",
                  {"schema": "yellowstone.piscivore_predation.v1",
                   "status": "authored_illustrative_not_calibrated",
                   "reports": piscivore_reports,
                   "method": ("sum over piscivores of density * intake * "
                              "share * exp(-depth/scale)"),
                   "provenance": {"source": "piscivores.predation_over_refuge"},
                   "units": {"mortality_rate_per_day": "1/day"}},
                  sources=[{"file": "yellowstone_midway/data/world.json",
                            "sha256": world_sha}],
                  params={"n_trout": len(piscivore_reports)},
                  code_rev=code_rev,
                  status="authored_illustrative")
    steam = res.get("steam_microclimate") or {}
    if steam:
        write_sidecar(out / "steam_microclimate.json",
                      {"schema": "yellowstone.steam_microclimate.v1",
                       "status": steam.get(
                           "status", "transferred_structure_authored_rates"),
                       "report": steam,
                       "units": {"downwind_air_c": "degree_Celsius",
                                 "downwind_rh": "dimensionless"},
                       "provenance": {
                           "source": "steam_microclimate.plume_microclimate_adjustment"}},
                      sources=[{"file": "yellowstone_midway/data/world.json",
                                "sha256": world_sha}],
                      params={"outflow_wired": False,
                              "note": ("outflow_surface_c is None pending "
                                       "WP-B outflow raster; pool plume only")},
                      code_rev=code_rev,
                      status=steam.get("status",
                                       "transferred_structure_authored_rates"))
    shading_doc = res.get("river_shading_doc") or {}
    if shading_doc:
        write_sidecar(out / "river_shading.json", shading_doc,
                      sources=[{"file": "yellowstone_midway/data/world.json",
                                "sha256": world_sha}],
                      params={"method": shading_doc.get("provenance", {}).get("method")},
                      code_rev=code_rev,
                      status=shading_doc.get("status", "authored"))
    oxygen_doc = res.get("oxygen_doc") or {}
    if oxygen_doc:
        write_sidecar(out / "river_oxygen.json", oxygen_doc,
                      sources=[{"file": "yellowstone_midway/data/world.json",
                                "sha256": world_sha}],
                      params={"method": "river_oxygen.advect_cells"},
                      code_rev=code_rev,
                      status=oxygen_doc.get("status", "fitted_not_validated"))
    periphyton_doc = res.get("periphyton_doc") or {}
    if periphyton_doc:
        write_sidecar(out / "periphyton.json", periphyton_doc,
                      sources=[{"file": "yellowstone_midway/data/world.json",
                                "sha256": world_sha}],
                      params={"method": "periphyton.step_biomass"},
                      code_rev=code_rev,
                      status=periphyton_doc.get(
                          "status", "illustrative_not_validated"))
    solute_doc = res.get("solute_doc") or {}
    if solute_doc:
        write_sidecar(out / "solute_transport.json", solute_doc,
                      sources=[{"file": "yellowstone_midway/data/world.json",
                                "sha256": world_sha}],
                      params={"method": solute_doc.get("provenance", {}).get(
                          "transport_scheme")},
                      code_rev=code_rev,
                      status=solute_doc.get(
                          "status", "fitted_not_validated_single_window"))
    outflow_chain = res.get("outflow_chain")
    if outflow_chain is not None:
        from yellowstone_python.thermal_features.outflow_thermal import write_outflow_temperature
        from yellowstone_python.thermal_features.microbial_mats import write_mat_state as _write_mat_state, write_mat_pigment_png as _write_mat_png
        otemp_f32 = out / "outflow_temperature.f32"
        otemp_json = out / "outflow_temperature.json"
        write_outflow_temperature(outflow_chain["outflow_raster"],
                                  outflow_chain["outflow_sidecar"],
                                  str(otemp_f32), str(otemp_json))
        mat = outflow_chain["mat_state"]
        mat_sidecar = mat.to_sidecar(
            forcing_epoch_utc=outflow_chain.get("forcing_epoch_utc"),
            daily_mean_shortwave_w_m2=outflow_chain["insolation"][
                "all_sky_mean_w_m2"],
            daily_cloud_fraction=outflow_chain["insolation"].get(
                "cloud_fraction"),
            ph=8.0,
            insolation_detail=outflow_chain["insolation"])
        _write_mat_state(mat, str(out), sidecar_extra=mat_sidecar)
        appearance = _write_mat_appearance(outflow_chain, res["world_root"],
                                           out, deps)
        if appearance is None:
            _write_mat_png(mat, str(out / "mat_pigment.png"),
                           legend_path=str(out / "mat_pigment.json"))
        res["mat_pigment_png_source"] = (
            "mat_appearance.write_mat_appearance_png" if appearance
            else "microbial_mats.write_mat_pigment_png")
        foodweb_doc = _run_outflow_foodweb(outflow_chain, out)
        res["outflow_foodweb_doc"] = foodweb_doc
        mat_validation = _run_mat_validation(outflow_chain,
                                              res["world_root"])
        res["mat_validation"] = mat_validation
        shells = res.get("shells") or []
        pool_ramps = _write_pool_ramps(shells, out)
        res["pool_ramps"] = pool_ramps
        override = res.get("excelsior_override") or {}
        write_sidecar(out / "outflow_to_replay_lateral.json",
                      {"schema": "yellowstone.outflow_to_replay_lateral.v1",
                       "status": ("outflow_chain_override" if override
                                  else "diagnostic"),
                       "excelsior_lateral_override": override,
                       "river_inflow_fraction_by_pool":
                           outflow_chain["river_inflow_fraction_by_pool"],
                       "spring_discharges_m3_s":
                           outflow_chain["discharges_m3_s"],
                       "spring_temps_c":
                           outflow_chain["spring_temps_c"],
                       "note": ("replay lateral is overridden in-place "
                                "when outflow_chain runs; see "
                                "excelsior_lateral_override.")},
                      sources=[{"file": "yellowstone_midway/data/world.json",
                                "sha256": world_sha}],
                      params={"source": "WP-A outflow_network springs"},
                      code_rev=code_rev,
                      status=("outflow_chain_override" if override
                              else "diagnostic"))
        foodweb_doc = res.get("outflow_foodweb_doc") or {}
        if foodweb_doc:
            write_sidecar(out / "outflow_foodweb.json",
                          foodweb_doc,
                          sources=[{"file": "yellowstone_midway/data/world.json",
                                    "sha256": world_sha}],
                          params={"source":
                                  "outflow_foodweb.outflow_foodweb_from_files"},
                          code_rev=code_rev,
                          status=foodweb_doc.get(
                              "status",
                              "transferred_structure_authored_rates"))
        pool_ramps = res.get("pool_ramps") or []
        if pool_ramps:
            write_sidecar(out / "pool_ramps.json",
                          {"schema": "yellowstone.pool_ramps_index.v1",
                           "status": "authored",
                           "ramps": pool_ramps,
                           "note": "radiative transfer per-pool color ramps"},
                          sources=[{"file": "yellowstone_midway/data/world.json",
                                    "sha256": world_sha}],
                          params={"ph": 8.0, "n_pools": len(pool_ramps)},
                          code_rev=code_rev,
                          status="authored")
