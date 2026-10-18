"""Interactive process datasets must preserve their checked scientific support."""

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder, domains, processes = load("build_public"), load("domain_data"), load("process_data")


@pytest.fixture(scope="module")
def selected():
    try:
        path = builder.selected_build(builder.ROOT)
    except (FileNotFoundError, ValueError):
        pytest.skip("Checked model artifacts are local; fixture validation runs in public clones")
    checked = domains.CheckedBuild(path)
    return checked, processes.export_visuals(checked)


def test_visual_identity_and_provenance_are_checked_artifacts(selected):
    checked, visuals = selected
    assert set(visuals) == {"steam", "mat", "hyporheic"}
    for identity, document in visuals.items():
        assert document["schema"] == "yellowstone.process-visual.v1"
        assert document["id"] == identity
        assert document["snapshot"] == checked.manifest["build_id"]
        assert document["sources"]
        assert all(source["sha256"] in checked.manifest["output_artifact_hashes"].values() for source in document["sources"])
        assert document["support"]["uncertainty"] == "unknown"
        public = json.dumps(document, allow_nan=False)
        assert "/Users/" not in public and "execution_evidence" not in public


def test_steam_retains_exact_report_and_source_components(selected):
    checked, visuals = selected
    native = checked.document("steam_microclimate.json")["report"]
    steam = visuals["steam"]
    assert steam["report"] == {key: native[key] for key in steam["report"]}
    for component in steam["components"]:
        for key in ["area_m2", "latent_w_m2", "sensible_w_m2"]:
            assert component[key] == native["components"][component["id"] + "_" + key]
    assert {row["id"] for row in steam["components"]} == {"pool", "outflow"}
    assert steam["support"]["time_kind"] == "static"
    assert "times" not in steam and "values" not in steam
    assert "pool plume only" not in json.dumps(steam)


def test_mat_retains_every_native_cell_and_exact_class_areas(selected):
    checked, visuals = selected
    mat = visuals["mat"]
    native = checked.document("mat_state.json")
    nodata = native["rasters"]["community"]["nodata"]
    expected = [None if value == nodata else value
                for value, in struct.iter_unpack("<h", checked.binary("mat_community.i16"))]
    assert mat["values"] == expected
    assert mat["grid"] == {"nx": native["grid"]["nx"], "nz": native["grid"]["nz"],
        "cell_m": native["grid"]["cell_size_m"], "origin_xz_m": native["grid"]["origin_xz_m"], "row_order": "z_increasing"}
    assert len(mat["values"]) == mat["grid"]["nx"] * mat["grid"]["nz"]
    counts = Counter(expected)
    for exported, original in zip(mat["legend"], native["legend"]):
        assert exported["class_id"] == original["class_id"]
        assert exported["rgb"] == original["rgb"]
        assert exported["count"] == counts[original["class_id"]]
        assert exported["area_m2"] == counts[original["class_id"]] * native["grid"]["cell_size_m"] ** 2
    assert sum(row["count"] for row in mat["legend"]) == len(expected) - counts[None]
    assert {row["sha256"] for row in mat["sources"]} == {
        checked.manifest["output_artifact_hashes"]["mat_state.json"],
        checked.manifest["output_artifact_hashes"]["mat_community.i16"]}


def test_hyporheic_retains_every_saved_time_cell_and_temperature(selected):
    checked, visuals = selected
    native = checked.document("river_replay.json")["replay"]
    data = visuals["hyporheic"]
    assert data["times"] == [frame["t_s"] for frame in native["frames"]]
    assert data["times"][-1] > 60
    assert data["cells"] == [{"id": cell["id"], "position_m": cell["center_s_m"],
        "x": cell["position_xyz"][0], "z": cell["position_xyz"][2]} for cell in native["cells"]]
    assert data["water"] == [frame["temperature_c"] for frame in native["frames"]]
    assert data["bed"] == [frame["budget"]["hyporheic"]["storage_temperature_c"] for frame in native["frames"]]
    assert data["water"][-1] != data["bed"][-1]
    assert data["support"]["interval_s"] == [data["times"][0], data["times"][-1]]
    catalog = processes.process_views(checked, {})["hyporheic"]
    assert catalog[0]["id"] == "channel_bed" and catalog[0]["kind"] == "visual"
    assert {view["id"] for view in catalog} >= {"channel_bed", "hyporheic_exchange_j", "storage_temperature"}


def fixture_build(path, documents, binaries=None):
    payloads = {name: json.dumps(value).encode() for name, value in documents.items()}
    payloads.update(binaries or {})
    payloads["CHECKS.json"] = json.dumps({"passed": True}).encode()
    hashes = {}
    for name, payload in payloads.items():
        (path / name).write_bytes(payload)
        hashes[name] = hashlib.sha256(payload).hexdigest()
    (path / "BUILD.json").write_text(json.dumps({"build_id": "fixture", "checks_passed": True, "output_artifact_hashes": hashes}))
    return domains.CheckedBuild(path)


def replay_fixture():
    return {"replay": {
        "cells": [{"id": "upstream", "center_s_m": 10, "position_xyz": [1, 2, 3]},
                  {"id": "downstream", "center_s_m": 30, "position_xyz": [4, 5, 6]}],
        "frames": [{"t_s": 0, "temperature_c": [20, None], "budget": {"hyporheic": {"storage_temperature_c": [18, 19]}}},
                   {"t_s": 10, "temperature_c": [21, 22], "budget": {}}]}}


def test_missing_bed_frame_is_explicit_and_water_missing_value_is_preserved(tmp_path):
    checked = fixture_build(tmp_path, {"river_replay.json": replay_fixture()})
    data = processes.export_visuals(checked)["hyporheic"]
    assert data["water"] == [[20, None], [21, 22]]
    assert data["bed"] == [[18, 19], [None, None]]


@pytest.mark.parametrize("problem", ["water-dimensions", "bed-dimensions", "time-order", "cell-order", "duplicate-cell", "nonfinite-temperature"])
def test_invalid_replay_cannot_publish_plausible_but_misaligned_charts(tmp_path, problem):
    document = replay_fixture()
    replay = document["replay"]
    if problem == "water-dimensions":
        replay["frames"][1]["temperature_c"] = [21]
    elif problem == "bed-dimensions":
        replay["frames"][0]["budget"]["hyporheic"]["storage_temperature_c"] = [18]
    elif problem == "time-order":
        replay["frames"][1]["t_s"] = 0
    elif problem == "cell-order":
        replay["cells"][1]["center_s_m"] = 5
    elif problem == "duplicate-cell":
        replay["cells"][1]["id"] = "upstream"
    else:
        replay["frames"][1]["temperature_c"][0] = float("inf")
    checked = fixture_build(tmp_path, {"river_replay.json": document})
    with pytest.raises(ValueError):
        processes.export_visuals(checked)


@pytest.mark.parametrize("problem", ["byte-dimensions", "metadata-hash", "unknown-class", "orientation"])
def test_invalid_mat_grid_cannot_publish_a_misleading_map(tmp_path, problem):
    payload = struct.pack("<hh", 0, -1)
    native = {"grid": {"nx": 2, "nz": 1, "cell_size_m": 1, "origin_xz_m": [0, 0], "row_order": "north_to_south"},
        "rasters": {"community": {"dtype": "int16", "nodata": -1, "sha256": hashlib.sha256(payload).hexdigest()}},
        "legend": [{"class_id": 0, "name": "sinter_dry", "rgb": [184, 168, 138]}]}
    if problem == "byte-dimensions":
        native["grid"]["nx"] = 3
    elif problem == "metadata-hash":
        native["rasters"]["community"]["sha256"] = "0" * 64
    elif problem == "unknown-class":
        native["legend"][0]["class_id"] = 1
    else:
        native["grid"]["row_order"] = "upside_down"
    checked = fixture_build(tmp_path, {"mat_state.json": native}, {"mat_community.i16": payload})
    with pytest.raises(ValueError):
        processes.export_visuals(checked)


def test_corrupt_artifact_bytes_block_visual_export(tmp_path):
    fixture_build(tmp_path, {"steam_microclimate.json": {"report": {}}})
    (tmp_path / "steam_microclimate.json").write_text('{"report":{"upwind_air_c":999}}')
    with pytest.raises(ValueError, match="Artifact hash mismatch"):
        processes.export_visuals(domains.CheckedBuild(tmp_path))
