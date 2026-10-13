"""Tests for the spec 10.1 run manifest in BUILD.json."""
import json

from yellowstone_python.build import build_manifest

MANIFEST_FIELDS = (
    "run_id", "run_mode", "code_commit", "environment_lock_hash",
    "external_solver_versions", "input_dataset_ids_and_hashes",
    "configuration_hash", "parameter_set_id", "random_stream_configuration",
    "grid_and_time_step_configuration", "solver_tolerances",
    "restart_information", "hardware_and_parallel_settings", "claim_ids",
    "warnings_and_failures", "output_artifact_hashes",
)

FIELD_MAP = {
    "run_id": "run_id",
    "run_mode": "run_mode",
    "code_commit": "code_commit",
    "environment_lock_hash": "environment_lock",
    "external_solver_versions": "external_solver_versions",
    "input_dataset_ids_and_hashes": "input_datasets",
    "configuration_hash": "configuration_hash",
    "parameter_set_id": "parameter_set_sha256",
    "random_stream_configuration": "random_streams",
    "grid_and_time_step_configuration": "grid_and_time_step",
    "solver_tolerances": "solver_tolerances",
    "restart_information": "restart",
    "hardware_and_parallel_settings": "hardware",
    "claim_ids": "claim_ids",
    "warnings_and_failures": "warnings_and_failures",
    "output_artifact_hashes": "output_artifact_hashes",
}


def _inputs(tmp_path):
    (tmp_path / "CHECKS.json").write_text(json.dumps({"passed": True}))
    cfg = {"hydro": {"boundary_m3s": 8.0, "boundary_c": 17.5,
                     "simulate_seconds": 600.0, "tributaries": {},
                     "attach": {}},
           "replay": {"duration_s": 7200.0, "dt_s": 1.0,
                      "sample_s": 10.0, "max_cell_m": 20.0,
                      "depth_m": 1.1},
           "fish": {"weights": None, "food": 0.7, "cover": 0.6},
           "snow": {"days": 30, "precip_mm_d": 2.0},
           "wind_seed": 11}
    deps = {"code": "abc", "config": "def", "ecosystem.json": "e",
            "world.json": "w", "placements.json": "p",
            "species_catalogue.json": "s", "terrain.f32": "t"}
    res = {"timeline": {"fast_window_s": 600.0},
           "prop_cfg": {"seed": 7},
           "replay_doc": {"cells": [{}, {}], "frames": [{}, {}, {}]},
           "catchment": {"enabled": False, "status": "storage_only",
                         "runoff_m3_s": 0.0},
           "baseflow_m3s": 8.0,
           "boundary_m3s": 8.0,
           "air0": 12.0}
    checks = {"passed": True, "failures": ["note: example"],
              "metrics": {}}
    return cfg, deps, res, checks


def test_manifest_covers_spec_fields(tmp_path):
    cfg, deps, res, checks = _inputs(tmp_path)
    manifest = build_manifest(cfg, deps, res, checks, "bid123",
                              "illustrative", ["discharge"], tmp_path)
    for spec_field in MANIFEST_FIELDS:
        assert FIELD_MAP[spec_field] in manifest, spec_field
    assert manifest["run_id"] == "bid123"
    assert manifest["build_id"] == "bid123"
    assert manifest["run_mode"] == "illustrative"
    assert manifest["claim_ids"]
    assert manifest["warnings_and_failures"] == ["note: example"]


def test_manifest_records_seeds_grid_and_versions(tmp_path):
    cfg, deps, res, checks = _inputs(tmp_path)
    manifest = build_manifest(cfg, deps, res, checks, "bid123",
                              "illustrative", [], tmp_path)
    assert manifest["random_streams"]["wind_seed"] == 11
    assert manifest["random_streams"]["proposal_seed"] == 7
    grid = manifest["grid_and_time_step"]
    assert (grid["n_cells"], grid["n_frames"]) == (2, 3)
    assert grid["replay_dt_s"] == 1.0
    assert manifest["external_solver_versions"]["numpy"] != "not_installed"
    assert manifest["external_solver_versions"]["scipy"] != "not_installed"
    assert manifest["output_artifact_hashes"]["CHECKS.json"]
    assert "BUILD.json" not in manifest["output_artifact_hashes"]


def test_manifest_is_deterministic(tmp_path):
    args = _inputs(tmp_path)
    first = build_manifest(*args, "bid123", "illustrative", [], tmp_path)
    second = build_manifest(*args, "bid123", "illustrative", [], tmp_path)
    assert first == second


def test_manifest_labels_follow_world_root(tmp_path):
    cfg, deps, res, checks = _inputs(tmp_path)
    cfg["world_root"] = "/data/other_midway"
    manifest = build_manifest(cfg, deps, res, checks, "bid123",
                              "illustrative", [], tmp_path)
    assert manifest["input_datasets"]["world"]["file"] == \
        "other_midway/data/world.json"
