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
        "river_replay.json": {"replay": {"cells": [{"id":"cell_001", "center_s_m": 10, "position_xyz": [1, 0, 2], "start_s_m":0, "end_s_m":20, "river_id":"channel", "width_m":10, "depth_m":0.5}],
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
        {"t": 0, "temperature": [17.5234567]}, {"t": 600, "temperature": [18.654321]}]
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
    expected = {
        "dashboard/index.html", "dashboard/explorer.js", "dashboard/explorer.css", "dashboard/snapshot.json",
        "dashboard/coverage.js", "dashboard/science.js", "dashboard/systems/index.html",
        "dashboard/results/index.html", "dashboard/methods/index.html", "dashboard/workspace.js",
        "dashboard/workspace-model.js", "dashboard/workspace.css",
        "dashboard/data-model.js", "dashboard/workbench.js", "dashboard/workbench.css", "dashboard/analyze/index.html",
        "dashboard/analysis.js", "dashboard/analysis.css", "dashboard/systems-model.js",
        "dashboard/systems-workbench.js", "dashboard/systems-workbench.css", "dashboard/process-data.js",
        "404.html", "_headers", "_redirects", "_worker.js"}
    expected.update(f"dashboard/systems/{slug}/index.html" for slug in builder.DOMAIN_SLUGS.values())
    assert {str(p.relative_to(destination)) for p in destination.rglob("*") if p.is_file()} == expected
    for route, identity in [("", "overview"), ("systems/", "systems"), ("results/", "results"), ("methods/", "methods")]:
        html = (destination / "dashboard" / route / "index.html").read_text()
        assert f'<body data-page="{identity}">' in html
        assert '<a href="/dashboard/" data-page="overview"' in html
    for domain in builder.DOMAINS:
        html = (destination / "dashboard/systems" / domain["slug"] / "index.html").read_text()
        assert f'data-page="systems" data-domain="{domain["id"]}"' in html
        assert f'{domain["label"]} | Yellowstone' in html
    with pytest.raises(ValueError, match="must be empty"):
        builder.package_site(destination, {})


def test_generation_pointer_cannot_escape_release_directory(tmp_path):
    (tmp_path / "yellowstone_midway/data").mkdir(parents=True)
    (tmp_path / "yellowstone_midway/data/release.json").write_text(
        json.dumps({"manifest": "../private.json", "sha256": "invalid"}))
    with pytest.raises(ValueError, match="outside the generation"):
        builder.selected_build(tmp_path)


def test_map_raster_rejects_terrain_from_another_build(model):
    root, build, manifest = model
    terrain = root / "yellowstone_midway/data/terrain.f32"
    terrain.parent.mkdir(parents=True)
    terrain.write_bytes(b"changed terrain")
    manifest["input_datasets"] = {"terrain": {"sha256": "different"}}
    (build / "BUILD.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Terrain input hash differs"):
        builder.map_assets(build, root / "site", root)


def test_bundled_snapshot_matches_native_river_frames():
    snapshot, files = builder.bundled_inputs()
    native = json.loads(files["data/" + Path(snapshot["datasets"]["river"]["url"]).name])
    frames = {frame["t"]: frame for frame in native["river"]["frames"]}
    for frame in snapshot["river"]["frames"]:
        assert frame["temperature"] == frames[frame["t"]]["temperature"]
    ids = {node["id"] for node in snapshot["nodes"]}
    assert all(edge["from"] in ids and edge["to"] in ids for edge in snapshot["edges"])
    assert any(edge["condition"] for edge in snapshot["edges"])
    water = snapshot["ecology"]["water"]
    residual = water["initial_mm"] + water["rain_mm"] + water["accum_mm"] - water["final_mm"] - water["et_mm"] - water["drainage_mm"] - water["runoff_mm"] - water["snow_export_mm"]
    assert abs(residual) < 1e-8
    assert len(snapshot["ecology"]["oxygen"]) == len(snapshot["river"]["cells"])
    assert snapshot["coverage"]["extent"] == 4096


def test_bundled_analytics_retain_independent_support():
    snapshot, _ = builder.bundled_inputs()
    analytics = snapshot["analytics"]
    assert analytics["weather"]["trace"][0]["t"] == 0
    assert analytics["weather"]["trace"][-1]["t"] == 60
    assert len(analytics["shading"]) == len(snapshot["river"]["cells"])
    assert all(0 <= value <= 1 for value in analytics["shading"])
    assert analytics["pools"]


def test_native_dataset_retains_support_and_source_precision(model):
    root, build, manifest = model
    native = builder.river_dataset(build)
    assert native["river"]["cells"][0]["id"] == "cell_001"
    assert native["river"]["cells"][0]["bounds_m"] == [0, 20]
    assert native["river"]["frames"][0]["temperature"] == [17.5234567]
    assert native["source_sha256"] == manifest["output_artifact_hashes"]["river_replay.json"]
    snapshot = builder.public_snapshot(build, root)
    path, payload = builder.attach_river_dataset(snapshot, native)
    site = root / "native-site"
    builder.package_site(site, snapshot, {path: payload})
    assert builder.digest(site / "dashboard" / path) == snapshot["datasets"]["river"]["sha256"]
    worker = (site / "_worker.js").read_text()
    assert snapshot["datasets"]["river"]["url"] in worker
    assert "/dashboard/analyze/" in worker
    assert "/dashboard/build_public.py" not in worker


def test_optional_diagnostics_export_independently(model):
    root, build, manifest = model
    doc = {"do_mg_l_by_cell":{"cell_001":7.123456789}, "dt_s":5}
    (build / "river_oxygen.json").write_text(json.dumps(doc))
    manifest["output_artifact_hashes"]["river_oxygen.json"] = builder.digest(build / "river_oxygen.json")
    (build / "BUILD.json").write_text(json.dumps(manifest))
    public = builder.public_snapshot(build, root)
    assert public["ecology"]["oxygen"] == [7.123456789]
    assert "periphyton" not in public["ecology"]
    (build / "river_oxygen.json").write_text("{}")
    with pytest.raises(ValueError, match="Artifact hash mismatch"):
        builder.public_snapshot(build, root)


def test_bundled_native_river_has_saved_sample_identity():
    snapshot, files = builder.bundled_inputs()
    native = json.loads(files["data/" + Path(snapshot["datasets"]["river"]["url"]).name])
    assert len(native["river"]["frames"]) == 721
    assert len(native["river"]["cells"]) == 276
    assert native["river"]["frames"][0]["t"] == 0
    assert native["river"]["frames"][-1]["t"] == 7200
    assert native["river"]["cells"][0]["id"] == "firehole_cell_00000"
    assert native["river"]["cells"][-1]["id"] == "firehole_cell_00275"
    text = json.dumps(native).lower()
    assert all(token not in text for token in ["fixes-", "/users/", ".py\"", "execution_evidence"])


def test_bundled_site_rebuild_preserves_all_public_bytes(tmp_path):
    destination = tmp_path / "site"
    builder.build_bundled(destination)
    published = builder.HERE / "public"
    expected = {p.relative_to(published) for p in published.rglob("*") if p.is_file()}
    assert {p.relative_to(destination) for p in destination.rglob("*") if p.is_file()} == expected
    for name in expected:
        assert (destination / name).read_bytes() == (published / name).read_bytes()


def test_bundled_input_corruption_prevents_site_creation(tmp_path):
    import shutil
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    shutil.copyfile(builder.HERE / "input-manifest.json", bundle / "input-manifest.json")
    shutil.copytree(builder.HERE / "data", bundle / "data")
    shutil.copytree(builder.HERE / "assets", bundle / "assets")
    (bundle / "data/snapshot.json").write_text("{}")
    with pytest.raises(ValueError, match="Public input hash mismatch"):
        builder.build_bundled(tmp_path / "site", bundle)
    assert not (tmp_path / "site").exists()


def test_public_input_manifest_cannot_escape_bundle(tmp_path):
    (tmp_path / "input-manifest.json").write_text(json.dumps({"schema": "yellowstone.public-inputs.v1", "files": {"../outside.json": "x"}}))
    with pytest.raises(ValueError, match="outside the bundle"):
        builder.bundled_inputs(tmp_path)
