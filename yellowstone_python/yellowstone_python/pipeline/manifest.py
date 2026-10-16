"""Manifest build operations."""
from __future__ import annotations

from yellowstone_python.common.provenance import portable_identity_payload
from yellowstone_python.pipeline.shared import CONTRACT_VERSION, HYDRO_HEAT_LEDGER_TOL_J, HYDRO_WATER_LEDGER_TOL_M3, PKG_ROOT, Path, REPLAY_HEAT_RELATIVE_TOLERANCE, REPLAY_WATER_RELATIVE_TOLERANCE, SNOW_STORAGE_TOL_MM, WORLD_ID, copy, predicted_quantities, sha256_file, sha256_json

def _package_version(name: str) -> str:
    """Installed distribution version or not_installed."""
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version(name)
    except PackageNotFoundError:
        return "not_installed"


def _code_commit() -> tuple:
    """VCS head hash or (None, reason) outside a checkout."""
    import subprocess
    try:
        out = subprocess.run(
            ["git", "-C", str(PKG_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return out.stdout.strip(), "git_head"
        return None, "no_vcs_checkout"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None, "no_vcs_checkout"


def build_manifest(cfg: dict, deps: dict, res: dict, checks: dict,
                   bid: str, mode: str, prescribed: list,
                   out: Path) -> dict:
    """Spec 10.1 run manifest. Existing keys are preserved."""
    from yellowstone_python.registry.claims import CLAIMS
    import os
    import platform

    commit, commit_status = _code_commit()
    lock = PKG_ROOT / "requirements-reference.lock"
    world_label = Path(cfg.get("world_root") or "yellowstone_midway").name
    hydro = cfg.get("hydro", {})
    replay_cfg = cfg.get("replay", {})
    fish_cfg = cfg.get("fish", {})
    snow_cfg = cfg.get("snow", {})
    replay_doc = res.get("replay_doc", {})
    foodweb_cfg = cfg.get("foodweb", {})
    parameter_set = {
        "hydro": {k: hydro.get(k) for k in
                  ("boundary_m3s", "boundary_c", "tributaries",
                   "attach", "catchment")},
        "replay": replay_cfg,
        "fish": {k: fish_cfg.get(k) for k in
                 ("weights", "food", "cover", "species")},
        "snow": {k: snow_cfg.get(k) for k in ("days", "precip_mm_d",
                                              "season", "as_of_date")},
        "foodweb": {k: foodweb_cfg.get(k) for k in
                    ("days", "dt_days", "ne_turnover_days",
                     "shear_disturb_pa")},
        "weather": cfg.get("weather", {}),
        "overland": cfg.get("overland", {}),
        "vegetation": cfg.get("vegetation", {}),
        "insects": cfg.get("insects", {}),
        "wind_seed": cfg.get("wind_seed", 11),
        "simulation": cfg.get("simulation", {}),
    }
    artifacts = {}
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "BUILD.json":
            artifacts[str(path.relative_to(out))] = sha256_file(path)
    return {
        "schema": "yellowstone.build_manifest.v1",
        "run_id": bid,
        "build_id": bid,
        "scenario_id": bid,
        "model_variant_id": "mapped_fv_explicit" if res.get("energy_budget_choice") else "mapped_fv_newton",
        "input_identity": sha256_json(portable_identity_payload(cfg, deps)),
        "river_model": "river.river_transport",
        "thermal_curve_form": cfg.get("fish", {}).get("thermal_curve_form", "piecewise_linear"),
        "config": {key: value for key, value in cfg.items() if key != "world_root"},
        "live": {"max_dt_s": 2.0, "tau_exposure_h": 1.0, "delta_u_switch": 0.1,
                 "movement_cost_per_m": 0.00001, "foodweb_interval_s": 3600.0},
        "contract_version": CONTRACT_VERSION,
        "world_id": WORLD_ID,
        "run_mode": mode,
        "prescribed_quantities": prescribed,
        "predicted_quantities": predicted_quantities(cfg),
        "hydrology": {
            "baseflow_m3s": res["baseflow_m3s"],
            "snow_runoff_m3_s": res["catchment"].get("runoff_m3_s", 0.0),
            "effective_boundary_m3s": res["boundary_m3s"],
            "catchment_enabled": res["catchment"]["enabled"],
        },
        "provenance": {
            "snow_partition_source": res.get("snow_partition_source"),
            "canopy_source": res.get("canopy_source"),
            "canopy_fraction_proposal": res.get("canopy_fraction_proposal"),
            "bundle_select_mode": res.get("bundle_select_mode"),
            "bundle_select_epoch_s": res.get("bundle_select_epoch_s"),
            "trout_position_authority": res.get("trout_position_authority"),
            "energy_budget_source": res.get("budget_mode_source"),
            "energy_budget_choice": res.get("energy_budget_choice"),
            "code_hash_source": deps.get("code_hash_source"),
        },
        "claim_ids": [c["claim_id"] for c in CLAIMS],
        "code_commit": commit,
        "code_commit_status": commit_status,
        "code_rev": deps.get("code_rev"),
        "code_rev_source": deps.get("code_rev_source"),
        "code_sha256": deps.get("code"),
        "environment_lock": {
            "file": "requirements-reference.lock",
            "sha256": (sha256_file(lock) if lock.is_file() else None),
            "note": "Exact reference dependencies; installed backend versions recorded separately",
        },
        "external_solver_versions": {
            "python": platform.python_version(),
            "numpy": _package_version("numpy"),
            "scipy": _package_version("scipy"),
            "matplotlib": _package_version("matplotlib"),
            "pandas": _package_version("pandas"),
            "pyyaml": _package_version("pyyaml"),
            "pillow": _package_version("Pillow"),
            "pint": _package_version("pint"),
            "salib": _package_version("SALib"),
            "xarray": _package_version("xarray"),
            "netcdf4": _package_version("netCDF4"),
            "pvlib": _package_version("pvlib"),
            "metpy": _package_version("metpy"),
            "pyproj": _package_version("pyproj"),
            "rasterio": _package_version("rasterio"),
            "shapely": _package_version("shapely"),
            "fipy": _package_version("fipy"),
            "laspy": _package_version("laspy"),
            "lazrs": _package_version("lazrs"),

        },
        "input_datasets": {
            "ecosystem": {"file": f"{world_label}/data/ecosystem.json",
                          "sha256": deps.get("ecosystem.json")},
            "world": {"file": f"{world_label}/data/world.json",
                      "sha256": deps.get("world.json")},
            "placements": {"file": f"{world_label}/data/placements.json",
                           "sha256": deps.get("placements.json")},
            "species_catalogue": {
                "file": f"{world_label}/data/species_catalogue.json",
                "sha256": deps.get("species_catalogue.json")},
            "terrain": {"file": f"{world_label}/data/terrain.f32",
                        "sha256": deps.get("terrain.f32")},
        },
        "configuration_hash": deps.get("config"),
        "portable_identity": portable_identity_payload(cfg, deps),
        "execution_receipt": {"world_root": cfg.get("world_root"),
                              "input_paths": {key: value.get("path") for key, value in deps.get("external_inputs", {}).items()},
                              "source_discovery": deps.get("code_hash_source")},
        "parameter_set": parameter_set,
        "parameter_set_sha256": sha256_json(parameter_set),
        "random_streams": {
            "wind_seed": int(cfg.get("wind_seed", 11)),
            "proposal_seed": int(res.get("prop_cfg", {}).get("seed", 7)),
            "generator": "stdlib random.Random, no global numpy RNG "
                         "in build path",
        },
        "grid_and_time_step": {
            "replay_duration_s": replay_cfg.get("duration_s"),
            "replay_dt_s": replay_cfg.get("dt_s"),
            "replay_sample_s": replay_cfg.get("sample_s"),
            "replay_max_cell_m": replay_cfg.get("max_cell_m"),
            "replay_depth_m": replay_cfg.get("depth_m"),
            "n_cells": len(replay_doc.get("cells", [])),
            "n_frames": len(replay_doc.get("frames", [])),
            "hydro_simulate_seconds": hydro.get("simulate_seconds"),
        },
        "solver_tolerances": {
            "replay_heat_relative": REPLAY_HEAT_RELATIVE_TOLERANCE,
            "replay_water_relative": REPLAY_WATER_RELATIVE_TOLERANCE,
            "hydro_heat_ledger": HYDRO_HEAT_LEDGER_TOL_J,
            "hydro_water_ledger": HYDRO_WATER_LEDGER_TOL_M3,
            "snow_storage_mm": SNOW_STORAGE_TOL_MM,
            "source": "yellowstone_python.validation.checks",
        },
        "model_authority": {
            "thermal_transport": "replay_doc",
            "fish_display": "river.river_transport",
            "foodweb": "replay_doc",
            "trout_position": res.get("trout_position_authority",
                                      "fish.place_trout_at_chainage"),
            "reach_summary": "flow-weighted mapped replay cells",
        },
        "shared_forcing": {
            "weather_fragment_source": "cfg.weather plus optional "
                                       "met_bundle override",
            "air_c_at_t0_c": res["air0"],
            "replay_forcing_source": (
                "weather_frag with the resolved air time series"),
            "forcing_match": (
                "reach summaries and ecology consume mapped replay forcing"),
        },
        "hydrology_components": {
            "baseflow_m3s": res["baseflow_m3s"],
            "snow_runoff_m3_s": res["catchment"].get("snow_runoff_m3_s", 0.0),
            "overland_runoff_m3_s": res.get("overland_runoff_m3_s", 0.0),
            "effective_boundary_m3s": res["boundary_m3s"],
        },
        "met_bundle_provenance": {
            "source": res.get("met_bundle_source"),
            "path": res.get("met_bundle_path"),
            "window_check": res.get("bundle_window_check"),
            "pool_crust_hot_source": (
                "plume2d uses the Excelsior reach temperature after "
                "pool-to-river mixing, not the pool interior temperature; "
                "pool_crust temperatures stay in pool_shells.json "
                "(illustrative by design)"),
            "surface_budget_wiring": (
                "explicit surface budget runs in hindcast/observed_replay "
                "when the met bundle carries night_air_c, humidity, "
                "cloud, and wind_xz_mps; otherwise Newton stays "
                "(illustrative by design)"),
        },
        "restart": {
            "support": "split-run same process; fresh object under "
                       "constant forcing",
            "benchmark": "restart_equivalence",
        },
        "hardware": {
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "parallelism": "single process",
        },
        "checks_passed": checks["passed"],
        "warnings_and_failures": list(checks["failures"]),
        "output_artifact_hashes": artifacts,
        "deps": deps,
        "timeline": res.get("timeline"),
        "land_thermal_flux_mm_d_by_patch": res.get("thermal_by_patch", {}),
        "land_stock_owner": "snow_soil_bucket",
        "land_model_variant": "degree_day_soil_bucket_solid_export",
        "metrics": copy.deepcopy(checks["metrics"]),
    }
