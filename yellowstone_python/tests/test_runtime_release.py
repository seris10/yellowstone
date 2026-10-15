"""Actual Godot replay consumption and malformed-field rejection."""
import shutil
import subprocess

import pytest

from yellowstone_python.common.io import load_json, sha256_file, write_json_atomic
from yellowstone_python.publish import publish_generation, FILES
from tests.test_release_generations import build_fixture


def test_actual_godot_reader_consumes_generation_and_rejects_missing_field(repo_root, tmp_path):
    godot = shutil.which("godot")
    if not godot:
        pytest.skip("Godot executable unavailable")
    world = tmp_path / "world"
    (world / "data").mkdir(parents=True)
    (world / "scripts").mkdir()
    (world / "project.godot").write_text("config_version=5\n")
    (world / "scripts/reader.gd").write_text("extends Node\n")
    write_json_atomic(world / "data/consumers.json", {"consumers": {
        target: ["scripts/reader.gd"] for _, target, _ in FILES}})
    build = build_fixture(tmp_path, "valid", optional=False)
    publish_generation(build, world)
    pointer_a = world / "data/pointer-a.json"
    pointer_a.write_bytes((world / "data/release.json").read_bytes())
    with_optional = build_fixture(tmp_path, "with-optional", optional=True)
    publish_generation(with_optional, world)
    pointer_a.write_bytes((world / "data/release.json").read_bytes())
    publish_generation(build, world)
    pointer_b = world / "data/pointer-b.json"
    pointer_b.write_bytes((world / "data/release.json").read_bytes())
    script_world = repo_root.parent / "yellowstone_midway"
    command = [godot, "--headless", "--path", str(script_world), "--script",
               "tools/validate_release_generation.gd", "--", "--pointer=" + str(world / "data/release.json")]
    good = subprocess.run(command, text=True, capture_output=True, timeout=30.)
    assert good.returncode == 0 and "RELEASE_VALIDATION PASS" in good.stdout, good.stdout + good.stderr
    candidate = build_fixture(tmp_path, "invalid", optional=False)
    replay = load_json(candidate / "river_replay.json")
    replay["frames"][0]["display_temperature"] = replay["frames"][0].pop("temperature_c")
    write_json_atomic(candidate / "river_replay.json", replay)
    manifest = load_json(candidate / "BUILD.json")
    checks = load_json(candidate / "CHECKS.json")
    checks["assessment"]["artifact_hashes"]["river_replay.json"] = sha256_file(candidate / "river_replay.json")
    write_json_atomic(candidate / "CHECKS.json", checks)
    manifest["output_artifact_hashes"].update(checks["assessment"]["artifact_hashes"])
    manifest["output_artifact_hashes"]["CHECKS.json"] = sha256_file(candidate / "CHECKS.json")
    write_json_atomic(candidate / "BUILD.json", manifest)
    publish_generation(candidate, world)
    bad = subprocess.run(command + ["--expect-refused"], text=True, capture_output=True, timeout=30.)
    assert bad.returncode == 0 and "RELEASE_VALIDATION refused" in bad.stdout, bad.stdout + bad.stderr
    reload = subprocess.run([godot, "--headless", "--path", str(script_world), "--script",
        "tools/validate_release_reload.gd", "--", "--a=" + str(pointer_a), "--b=" + str(pointer_b),
        "--bad=" + str(world / "data/release.json")], text=True, capture_output=True, timeout=30.)
    assert reload.returncode == 0 and "RELEASE_RELOAD PASS" in reload.stdout, reload.stdout + reload.stderr
    assert "SCRIPT ERROR" not in reload.stderr, reload.stderr
