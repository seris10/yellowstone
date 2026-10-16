"""Native system export support, precision, and public data boundaries."""

import hashlib
import importlib.util
import json
import math
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location("domain_data", Path(__file__).with_name("domain_data.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def fixture_build(tmp_path, documents):
    """Create a synthetic generation with bound artifact hashes."""
    build = tmp_path / "synthetic-test-build"
    build.mkdir()
    documents = {"CHECKS.json": {"passed": True}, **documents}
    hashes = {}
    for name, document in documents.items():
        payload = document if isinstance(document, bytes) else json.dumps(document).encode()
        target = build / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        hashes[name] = hashlib.sha256(payload).hexdigest()
    manifest = {"build_id": "synthetic-test-only", "checks_passed": True, "run_mode": "illustrative",
                "config": {"simulation": {"start_utc": "2026-06-21T22:12:00+00:00"}},
                "output_artifact_hashes": hashes}
    (build / "BUILD.json").write_text(json.dumps(manifest))
    return build


def channel():
    """Return synthetic finite-volume support for one test cell."""
    return {"replay": {"cells": [{"id": "native-cell", "start_s_m": 0, "end_s_m": 20,
                                    "center_s_m": 10, "position_xyz": [1.23456789, 0, -9.87654321]}]}}


def test_missing_optional_systems_do_not_create_fake_data(tmp_path):
    build = fixture_build(tmp_path, {})
    assert module.export_systems(build) == {}


def test_independent_checked_oxygen_preserves_ids_and_precision(tmp_path):
    value = 7.123456789012345
    build = fixture_build(tmp_path, {"river_replay.json": channel(),
                                    "river_oxygen.json": {"do_mg_l_by_cell": {"native-cell": value}, "dt_s": 60}})
    result = module.export_systems(build)
    aquatic = result["aquatic"]
    assert set(result) == {"aquatic"}
    assert aquatic["entities"][0]["id"] == "native-cell"
    assert aquatic["entities"][0]["values"] == {"oxygen": value}
    assert aquatic["entities"][0]["x"] == 1.23456789
    assert aquatic["entities"][0]["bounds_m"] == [0, 20]
    assert aquatic["variables"][0]["integration_step_s"] == 60
    assert aquatic["variables"][0]["support"]["time_kind"] == "static"
    assert "interval_s" not in aquatic["variables"][0]["support"]
    assert aquatic["series"] == []


def test_corrupt_optional_artifact_prevents_export(tmp_path):
    build = fixture_build(tmp_path, {"ground_heat.json": {}})
    (build / "ground_heat.json").write_text('{"private": "changed"}')
    with pytest.raises(ValueError, match="Artifact hash mismatch"):
        module.export_systems(build)


def test_failed_checks_prevent_system_export(tmp_path):
    build = fixture_build(tmp_path, {"CHECKS.json": {"passed": False}})
    with pytest.raises(ValueError, match="Model checks failed"):
        module.export_systems(build)


def test_actual_saved_land_and_weather_use_physical_irregular_times(tmp_path):
    frames = []
    values = [0.1234567890123, None, 0.6234567890123]
    for index, time in enumerate([0.0, 7.5, 105.0]):
        frames.append({"t_s": time, "weather": {"air_temperature_c": 10 + index, "wind_xz_mps": [1, 2]},
                       "patches": [{"id": "producer-patch", "center_xz": [5, -4], "biomass": values[index],
                                    "soil_mm": index + 0.111111111111, "snow_mm": 0, "radius_m": 20}]})
    build = fixture_build(tmp_path, {"ecosystem.godot.json": {"python_series": frames}})
    result = module.export_systems(build)
    series = next(row for row in result["land"]["series"] if row["variable_id"] == "biomass")
    assert series["times"] == [0.0, 7.5, 105.0]
    assert series["values"] == values
    assert series["entity_id"] == "producer-patch"
    assert series["support"]["interval_s"] == [0, 105]
    assert result["land"]["entities"][0]["values"]["biomass"] == values[0]
    soil = next(row for row in result["snow"]["series"] if row["variable_id"] == "soil_water")
    assert soil["values"][0] == 0.111111111111
    assert result["atmosphere"]["variables"][0]["role"] == "driver"
    wind = next(row for row in result["atmosphere"]["series"] if row["variable_id"] == "wind_speed")
    assert wind["values"] == [math.hypot(1, 2)] * 3
    assert wind["role"] == "diagnostic"
    assert "hypot" in wind["description"]
    assert result["land"]["entities"][0]["display_radius_m"] == 20
    assert "catchment" in result["land"]["variables"][0]["support"]["space"]


@pytest.mark.parametrize("times", [[0, 0], [10, 5]])
def test_nonmonotonic_ecosystem_times_prevent_export(tmp_path, times):
    build = fixture_build(tmp_path, {"ecosystem.godot.json": {"python_series": [{"t_s": t} for t in times]}})
    with pytest.raises(ValueError, match="times must increase"):
        module.export_systems(build)


def test_epoch_disagreement_prevents_export(tmp_path):
    build = fixture_build(tmp_path, {"ecosystem.godot.json": {"python_series": [{"t_s": 0, "epoch_unix": 0}]}})
    with pytest.raises(ValueError, match="physical times differ"):
        module.export_systems(build)


def test_fully_missing_quantities_are_explicitly_unavailable(tmp_path):
    build = fixture_build(tmp_path, {"steam_microclimate.json": {"report": {"delta_air_c": 0.0}}})
    data = module.export_systems(build)["atmosphere"]
    assert [item["id"] for item in data["variables"]] == ["steam_air_change"]
    assert data["entities"][-1]["values"] == {"steam_air_change": 0.0}
    assert {item["id"] for item in data["unavailable"]} == {"steam_humidity_change", "steam_latent_heat", "steam_sensible_heat"}


def test_native_binary_missing_pixels_and_precision_are_preserved(tmp_path):
    raw = struct.pack("<4f", 34.12345504760742, float("nan"), 19.125, 0.0)
    sha = hashlib.sha256(raw).hexdigest()
    build = fixture_build(tmp_path, {
        "outflow_temperature.f32": raw,
        "outflow_temperature.json": {"sha256": sha, "grid": {"nx": 2, "nz": 2, "cell_size_m": 1,
                                     "origin_xz_m": [-2, -1], "row_order": "north_to_south"}}})
    grid = module.export_systems(build)["thermal"]["grids"][0]
    assert grid["values"] == [34.12345504760742, None, 19.125, 0.0]
    assert grid["grid"] == {"nx": 2, "nz": 2, "cell_m": 1, "origin_xz_m": [-2, -1], "row_order": "z_increasing"}
    assert grid["support"]["time_kind"] == "static"


def test_outflow_metadata_hash_mismatch_prevents_export(tmp_path):
    build = fixture_build(tmp_path, {"outflow_temperature.f32": struct.pack("<f", 10),
                                    "outflow_temperature.json": {"sha256": "0" * 64}})
    with pytest.raises(ValueError, match="metadata hash differs"):
        module.export_systems(build)


def test_grid_dimension_mismatch_prevents_export(tmp_path):
    build = fixture_build(tmp_path, {"ground_heat.json": {"grid": {"nx": 2, "nz": 2, "cell_m": 1,
              "origin_xz_m": [0, 0], "row_order": "south_increases"}, "values_w_m2": [[1, 2]]}})
    with pytest.raises(ValueError, match="dimensions differ"):
        module.export_systems(build)


def test_plume_sample_node_geometry_does_not_become_control_volumes(tmp_path):
    build = fixture_build(tmp_path, {"plume_field.json": {"nx": 2, "nz": 2, "axes_x_m": [-5, 5],
                     "axes_z_m": [-5, 5], "temperature_grid_c": [[10, 12], [14, 16]]}})
    grid = module.export_systems(build)["thermal"]["grids"][0]
    assert grid["grid"]["origin_xz_m"] == [-10, -10]
    assert grid["grid"]["cell_m"] == 10
    assert grid["metadata"]["native_axis_x_m"] == [-5, 5]
    assert grid["metadata"]["sampling"] == "sample_nodes"
    assert "not physical" in grid["support"]["space"]


def test_untrusted_internal_fields_are_not_copied(tmp_path):
    build = fixture_build(tmp_path, {"river_replay.json": channel(),
              "river_oxygen.json": {"do_mg_l_by_cell": {"native-cell": 7}, "fixes": "PRIVATE", "sources": ["/Users/private/path"]}})
    encoded = json.dumps(module.export_systems(build))
    assert "PRIVATE" not in encoded and "/Users/" not in encoded and "fixes" not in encoded


def test_catalog_preserves_river_and_binds_exact_dataset_bytes(tmp_path):
    build = fixture_build(tmp_path, {"river_replay.json": channel(),
                                    "river_oxygen.json": {"do_mg_l_by_cell": {"native-cell": 7}}})
    snapshot = {"snapshot": "synthetic-test-only", "datasets": {"river": {"sha256": "river-reference"}}}
    files = module.attach_system_datasets(snapshot, module.export_systems(build))
    assert snapshot["datasets"]["river"] == {"sha256": "river-reference"}
    descriptor = snapshot["datasets"]["systems"][0]
    path, payload = next(iter(files.items()))
    assert descriptor["url"] == "/dashboard/" + path
    assert descriptor["sha256"] == hashlib.sha256(payload).hexdigest()
    assert descriptor["sha256"] in path
    assert descriptor["bytes"] == len(payload)
    assert json.loads(payload)["schema"] == "yellowstone.system.v1"


def test_catalog_hashes_do_not_depend_on_python_hash_seed(tmp_path):
    build = fixture_build(tmp_path, {
        "ecosystem.godot.json": {"python_series": [{"t_s": 0, "weather": {"air_temperature_c": 10, "wind_xz_mps": [1, 2]}}]},
        "steam_microclimate.json": {"report": {"delta_air_c": 0, "latent_flux_w_m2": 100, "sensible_flux_w_m2": 30}}})
    script = (
        "import importlib.util,json,sys;from pathlib import Path;"
        "s=importlib.util.spec_from_file_location('exporter',sys.argv[1]);"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        "d=m.export_systems(Path(sys.argv[2]));p={'snapshot':'synthetic-test-only'};"
        "m.attach_system_datasets(p,d);"
        "print(json.dumps([(x['id'],x['sha256']) for x in p['datasets']['systems']]))")
    outputs = [subprocess.check_output([sys.executable, "-c", script, str(Path(module.__file__)), str(build)],
                                      env=dict(os.environ, PYTHONHASHSEED=seed), text=True)
               for seed in ["1", "314159"]]
    assert outputs[0] == outputs[1]


@pytest.fixture(scope="module")
def selected_outputs():
    """Read the hash-bound public datasets from the bundled saved scenario."""
    specification = importlib.util.spec_from_file_location("public_builder", Path(__file__).with_name("build_public.py"))
    builder = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(builder)
    snapshot, files = builder.bundled_inputs()
    datasets = {row["id"]: json.loads(files["data/" + Path(row["url"]).name]) for row in snapshot["datasets"]["systems"]}
    return snapshot, datasets


def test_bundled_outputs_retain_saved_stocks_ids_and_times(selected_outputs):
    snapshot, datasets = selected_outputs
    assert snapshot["snapshot"] == "f75347b772fd"
    assert set(datasets) == set(module.SYSTEMS)
    biomass = next(row for row in datasets["land"]["series"] if row["entity_id"] == "north_meadow" and row["variable_id"] == "biomass")
    assert len(biomass["times"]) == 721
    assert biomass["times"][0] == 0 and biomass["times"][-1] == 7200
    assert biomass["values"][0] == 0.8200804107973139
    assert biomass["values"][-1] == 0.8205792118245919
    crowns = datasets["canopy"]["entities"]
    assert len(crowns) == 34303
    assert crowns[0]["id"] == "census_lidar_0017_0000"
    assert crowns[-1]["id"] == "census_lidar_1736_2559"
    assert crowns[0]["values"]["height"] == 6.227
    assert all(row["support"]["time_kind"] == "static" for row in datasets["canopy"]["grids"])
    residual_canopy = next(row for row in datasets["canopy"]["grids"] if row["id"] == "canopy_coverage")
    assert residual_canopy["label"] == "Canopy outside crown cores"
    assert "not total canopy cover" in residual_canopy["description"]
    assert datasets["thermal"]["series"] == []
    oxygen = next(row for row in datasets["aquatic"]["variables"] if row["id"] == "oxygen")
    assert oxygen["support"]["time_kind"] == "static"
    assert oxygen["integration_step_s"] == 60
    first_actor = next(row for row in datasets["wildlife"]["entities"] if row["kind"] == "display representative")
    assert first_actor["metadata"]["position_basis"].startswith("Authored route start")


def test_bundled_exports_are_bounded_sanitized_and_hash_bound(selected_outputs):
    snapshot, datasets = selected_outputs
    rebuilt = {"snapshot": snapshot["snapshot"]}
    files = module.attach_system_datasets(rebuilt, datasets)
    assert len(files) == 7
    assert rebuilt["datasets"]["systems"] == snapshot["datasets"]["systems"]
    for payload in files.values():
        assert len(payload) < 24 * 1024 * 1024
        lowered = payload.decode().lower()
        assert all(token not in lowered for token in ["fixes-", "/users/", ".py\"", "execution_evidence", "code_rev"])
        dataset = json.loads(payload)
        assert all(len(row["sha256"]) == 64 for row in dataset["sources"])
        assert all(row["support"]["uncertainty"] == "unknown" for group in ["variables", "grids", "series", "profiles"] for row in dataset[group])
