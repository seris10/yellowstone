"""Release integrity, optional absence and interrupted activation."""
import json
import shutil
import subprocess
import sys

import pytest
from PIL import Image

from yellowstone_python.common.io import sha256_file, write_json_atomic
from yellowstone_python.common.provenance import CONTRACT_VERSION, WORLD_ID, sha256_json
from yellowstone_python.publish import FILES, publish_generation, verify_build, release_plan


def build_fixture(root, name="fixture", optional=True):
    build = root / name
    build.mkdir()
    eco = {"schema_version": 1, "river_reaches": [{"id": "a", "volume_m3": 200.,
        "temperature_c": 15., "cooling_seconds": 600., "upstream_id": ""}],
        "patches": [{"id": "p", "biomass": .5, "capacity": 1., "moisture": .5,
            "growth_per_hour": .01, "insect_resource": .5, "insect_recovery_per_hour": .1}],
        "weather": {"night_air_c": 7., "day_warming_c": 0., "wind_xz_mps": [0., 2.], "gust_mps": 0.},
        "humidity": .45, "cloud": .16, "boundary_c": 15., "boundary_m3s": 5.}
    write_json_atomic(build / "ecosystem.godot.json", eco)
    write_json_atomic(build / "world.runtime.json", {"anchors": [], "routes": [], "pools": [],
                     "simulation_epoch_unix": 1782064800. if name != "valid" else 1782151200.})
    world_hash = sha256_file(build / "world.runtime.json")
    replay = {"schema": "yellowstone.mapped_river_replay.v1", "numerical_checks": {"passed": True},
        "input_files": {"world": {"sha256": world_hash}},
        "cells": [{"id": "a", "river_id": "river", "start_s_m": 0., "end_s_m": 20.,
                   "position_xyz": [0., 0., 10.], "volume_m3": 200., "q_out_m3_s": 5.}],
        "frames": [{"t_s": 0., "temperature_c": [15.]}, {"t_s": 10., "temperature_c": [16.]}],
        "river_features": {"river": {"points_xyz": [[0., 0., 0.], [0., 0., 20.]],
                                      "point_s_m": [0., 20.], "width_m": 10.}}}
    write_json_atomic(build / "river_replay.json", replay)
    if optional:
        write_json_atomic(build / "overland_field.json", {"enabled": True, "value": 1.})
        (build / "pool_ramps").mkdir()
        Image.new("RGB", (1, 1), (64, 128, 255)).save(build / "pool_ramps/ramp.png")
    hashes = {str(path.relative_to(build)): sha256_file(path) for path in build.rglob("*") if path.is_file()}
    checks = {"passed": True, "assessment": {"build_id": name, "model_variant_id": "mapped_fv_newton",
                                            "input_identity": sha256_json({"fixture": name}), "artifact_hashes": hashes}}
    write_json_atomic(build / "CHECKS.json", checks)
    manifest = {"build_id": name, "model_variant_id": "mapped_fv_newton", "scenario_id": name,
        "portable_identity": {"fixture": name}, "input_identity": sha256_json({"fixture": name}),
        "contract_version": CONTRACT_VERSION, "world_id": WORLD_ID,
        "output_artifact_hashes": {**hashes, "CHECKS.json": sha256_file(build / "CHECKS.json")}}
    write_json_atomic(build / "BUILD.json", manifest)
    return build


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "world"
    (root / "data").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "project.godot").write_text("config_version=5\n")
    (root / "scripts/reader.gd").write_text("extends Node\n")
    write_json_atomic(root / "data/consumers.json", {"consumers": {
        target: ["scripts/reader.gd"] for _, target, _ in FILES}})
    return root


def test_missing_optional_files_and_directory_members_cannot_reuse_previous_release(tmp_path, project):
    first = publish_generation(build_fixture(tmp_path, "a"), project)
    second = publish_generation(build_fixture(tmp_path, "b", optional=False), project)
    pointer = json.loads((project / "data/release.json").read_text())
    assert pointer["release_id"] == second["release_id"]
    assert second["artifacts"]["data/overland_field.json"]["state"] == "unavailable"
    assert second["artifacts"]["assets/textures/pool_ramps/"]["state"] == "unavailable"
    assert (project / "data/releases" / first["release_id"] / "data/overland_field.json").is_file()
    assert not (project / "data/releases" / second["release_id"] / "data/overland_field.json").exists()


@pytest.mark.parametrize("artifact", ["ecosystem.godot.json", "pool_ramps/ramp.png", "CHECKS.json"])
def test_post_check_tampering_refuses_activation(tmp_path, project, artifact):
    build = build_fixture(tmp_path)
    path = build / artifact
    if path.suffix == ".json":
        document = json.loads(path.read_text())
        document["additional_valid_value"] = 1
        write_json_atomic(path, document)
    else:
        path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="checked artifact changed"):
        publish_generation(build, project)
    assert not (project / "data/release.json").exists()


def test_manifest_input_substitution_refuses_activation(tmp_path, project):
    build = build_fixture(tmp_path)
    path = build / "BUILD.json"
    document = json.loads(path.read_text())
    document["portable_identity"]["fixture"] = "substituted_input"
    write_json_atomic(path, document)
    with pytest.raises(ValueError, match="effective inputs differ"):
        publish_generation(build, project)
    assert not (project / "data/release.json").exists()


def test_interruption_at_each_copy_boundary_keeps_complete_active_generation(tmp_path, project):
    first = publish_generation(build_fixture(tmp_path, "a"), project)
    candidate = build_fixture(tmp_path, "b")
    manifest, checks = verify_build(candidate)
    _, files = release_plan(candidate, manifest, checks)
    for boundary in range(len(files)):
        calls = 0
        def interrupted_copy(source, target):
            nonlocal calls
            if calls == boundary:
                raise OSError("injected interruption")
            calls += 1
            return shutil.copy2(source, target)
        with pytest.raises(OSError, match="injected interruption"):
            publish_generation(candidate, project, copy_file=interrupted_copy)
        pointer = json.loads((project / "data/release.json").read_text())
        assert pointer["release_id"] == first["release_id"]
        generation = project / pointer["manifest"]
        assert generation.is_file()
        assert sha256_file(generation) == pointer["sha256"]
    second = publish_generation(candidate, project)
    assert json.loads((project / "data/release.json").read_text())["release_id"] == second["release_id"]


def test_process_exit_during_staging_keeps_generation_valid_after_restart(tmp_path, project):
    first = publish_generation(build_fixture(tmp_path, "a"), project)
    candidate = build_fixture(tmp_path, "b")
    manifest, checks = verify_build(candidate)
    _, files = release_plan(candidate, manifest, checks)
    program = '''import os, shutil, sys
from pathlib import Path
from yellowstone_python.publish import publish_generation
boundary = int(sys.argv[3])
calls = 0
def copier(source, target):
    global calls
    if calls == boundary:
        os._exit(77)
    calls += 1
    return shutil.copy2(source, target)
publish_generation(Path(sys.argv[1]), Path(sys.argv[2]), copy_file=copier)
'''
    for boundary in range(len(files)):
        process = subprocess.run([sys.executable, "-c", program, str(candidate), str(project), str(boundary)], timeout=30.)
        assert process.returncode == 77
        pointer = json.loads((project / "data/release.json").read_text())
        assert pointer["release_id"] == first["release_id"]
        assert sha256_file(project / pointer["manifest"]) == pointer["sha256"]
    publish_generation(candidate, project)
