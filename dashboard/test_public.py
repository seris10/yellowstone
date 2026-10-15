"""Scientific snapshot integrity and public asset boundaries."""

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("public_builder", Path(__file__).with_name("build_public.py"))
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


@pytest.fixture
def model(tmp_path):
    """Create a small model generation with bound artifact hashes."""
    source = tmp_path / "yellowstone_python/yellowstone_python/river"
    source.mkdir(parents=True)
    (source / "surface_flux.py").write_text("heat_flux = 12\n")
    build = tmp_path / "build"
    build.mkdir()
    component = {"component": "surface heat exchange", "module": "river/surface_flux.py",
                 "equations": "Phi = h(Tair - T)", "assumptions": "Ice free.",
                 "limits": "Local calibration unavailable.", "units": "W/m2", "variables": "h: W/m2/K",
                 "model_level": "Lumped surface heat exchange."}
    documents = {
        "equations.json": {"components": [component]},
        "coupling.json": {"exchanges": []},
        "river_replay.json": {"replay": {"cells": [{"center_s_m": 10, "position_xyz": [1, 0, 2]}],
                                          "frames": [{"t_s": 0, "temperature_c": [17.5234567]},
                                                     {"t_s": 600, "temperature_c": [18.654321]}],
                                          "mapping": {"length_m": 20}}},
        "CHECKS.json": {"passed": True}, "claims.json": {"claims": []},
    }
    for name, value in documents.items():
        (build / name).write_text(json.dumps(value))
    manifest = {"build_id": "sample", "checks_passed": True, "run_mode": "illustrative",
                "config": {"simulation": {"start_utc": "2026-06-21T22:12:00+00:00"},
                           "hydro": {"boundary_c": 17.5, "boundary_m3s": 8, "catchment": {"area_m2": None}},
                           "replay": {"energy_budget": False}},
                "output_artifact_hashes": {name: builder.digest(build / name) for name in documents}}
    (build / "BUILD.json").write_text(json.dumps(manifest))
    return tmp_path, build, manifest


def test_export_preserves_model_time_and_temperature(model):
    root, build, _ = model
    public = builder.public_snapshot(build, root)
    assert public["river"]["frames"] == [
        {"t": 0, "temperature": [17.5235]}, {"t": 600, "temperature": [18.6543]}]
    assert public["river"]["cells"] == [{"s": 10, "x": 1, "z": 2}]
    assert public["nodes"][0]["equations"] == "Phi = h(Tair - T)"


def test_corrupt_artifact_prevents_export(model):
    root, build, _ = model
    (build / "river_replay.json").write_text('{"replay": {}}')
    with pytest.raises(ValueError, match="Artifact hash mismatch"):
        builder.public_snapshot(build, root)


def test_failed_checks_prevent_export(model):
    root, build, manifest = model
    (build / "CHECKS.json").write_text('{"passed": false}')
    manifest["output_artifact_hashes"]["CHECKS.json"] = builder.digest(build / "CHECKS.json")
    (build / "BUILD.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Model checks failed"):
        builder.public_snapshot(build, root)


def test_dimension_mismatch_prevents_export(model):
    root, build, manifest = model
    replay = builder.read_json(build / "river_replay.json")
    replay["replay"]["frames"][0]["temperature_c"].append(22)
    (build / "river_replay.json").write_text(json.dumps(replay))
    manifest["output_artifact_hashes"]["river_replay.json"] = builder.digest(build / "river_replay.json")
    (build / "BUILD.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="dimensions differ"):
        builder.public_snapshot(build, root)


def test_private_fields_are_absent_from_public_snapshot(model):
    root, build, manifest = model
    equations = builder.read_json(build / "equations.json")
    equations["components"][0].update({"fixes": "PRIVATE", "evidence": ["/private/path"], "notes": "PRIVATE"})
    (build / "equations.json").write_text(json.dumps(equations))
    manifest["output_artifact_hashes"]["equations.json"] = builder.digest(build / "equations.json")
    (build / "BUILD.json").write_text(json.dumps(manifest))
    public = json.dumps(builder.public_snapshot(build, root))
    assert "PRIVATE" not in public and "/private/" not in public and ".py" not in public


def test_package_contains_only_public_assets(model):
    root, build, _ = model
    destination = root / "site"
    builder.package_site(destination, builder.public_snapshot(build, root))
    assert {str(p.relative_to(destination)) for p in destination.rglob("*") if p.is_file()} == {
        "dashboard/index.html", "dashboard/explorer.js", "dashboard/explorer.css", "dashboard/snapshot.json",
        "dashboard/coverage.js", "dashboard/science.js", "dashboard/systems/index.html",
        "dashboard/results/index.html", "dashboard/methods/index.html",
        "404.html", "_headers", "_redirects", "_worker.js"}
    for route, identity in [("", "overview"), ("systems/", "systems"), ("results/", "results"), ("methods/", "methods")]:
        html = (destination / "dashboard" / route / "index.html").read_text()
        assert f'<body data-page="{identity}">' in html
        assert '<a href="/dashboard/" data-page="overview">' in html
    with pytest.raises(ValueError, match="must be empty"):
        builder.package_site(destination, {})


def test_generation_pointer_cannot_escape_release_directory(tmp_path):
    (tmp_path / "yellowstone_midway/data").mkdir(parents=True)
    (tmp_path / "yellowstone_midway/data/release.json").write_text(
        json.dumps({"manifest": "../private.json", "sha256": "invalid"}))
    with pytest.raises(ValueError, match="outside the generation"):
        builder.selected_build(tmp_path)


def test_world_selected_snapshot_matches_checked_river_frames():
    build = builder.selected_build(builder.ROOT)
    snapshot = builder.public_snapshot(build)
    frames = {frame["t_s"]: frame for frame in builder.read_json(build / "river_replay.json")["replay"]["frames"]}
    for frame in snapshot["river"]["frames"]:
        assert frame["temperature"] == [round(value, 4) for value in frames[frame["t"]]["temperature_c"]]
    ids = {node["id"] for node in snapshot["nodes"]}
    assert all(edge["from"] in ids and edge["to"] in ids for edge in snapshot["edges"])
    assert any(edge["condition"] for edge in snapshot["edges"])
    public = json.dumps(snapshot).lower()
    assert all(token not in public for token in ["fixes-", "ledger", "/users/", ".py\"", "execution_evidence"])
    water = snapshot["ecology"]["water"]
    residual = water["initial_mm"] + water["rain_mm"] + water["accum_mm"] - water["final_mm"] - water["et_mm"] - water["drainage_mm"] - water["runoff_mm"] - water["snow_export_mm"]
    assert abs(residual) < 1e-8
    assert len(snapshot["ecology"]["oxygen"]) == len(snapshot["river"]["cells"])
    assert snapshot["coverage"]["extent"] == 4096
