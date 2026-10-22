"""Vegetation and forest-floor feature page checks."""
import json
import math
from pathlib import Path

import pytest

from yellowstone_python.park_runtime.feature_pages import (
    FOREST_FLOOR_CELL_M, VEGETATION_CELL_M, forest_floor_features, vegetation_features,
    verify_feature_pages, write_feature_pages)

DATA = Path(__file__).resolve().parents[3]/"yellowstone_midway"/"data"
needs_data = pytest.mark.skipif(not (DATA/"placements.json").exists(),
                                reason="real Midway source data is absent")


def write_placements(tmp_path, trees, adds=None, removes=None, replaces=None):
    placements = {"schema": 1, "trees": trees, "grass": [], "logs": [], "rocks": []}
    overrides = {"schema": 1, "add": adds or [], "remove": removes or [], "replace": replaces or {}}
    placements_path = tmp_path/"placements.json"
    overrides_path = tmp_path/"overrides.json"
    placements_path.write_text(json.dumps(placements))
    overrides_path.write_text(json.dumps(overrides))
    return placements_path, overrides_path


def tree(record_id, x=10.0, z=20.0, kind="pine"):
    return {"id": record_id, "kind": kind, "position": [x, 5.0, z], "yaw": 1.0, "scale": 1.0, "variant": 0}


def floor_record(record_id, x=10.0, z=20.0, kind="litter"):
    return {"id": record_id, "kind": kind, "position": [x, 5.0, z], "size": [1.0, 1.0, 1.0],
            "yaw": 0.0, "ground_normal": [0.0, 1.0, 0.0]}


def write_floor(tmp_path, records):
    floor_path = tmp_path/"forest_floor.json"
    floor_path.write_text(json.dumps({"schema": "yellowstone.forest_floor.v1", "status": "authored",
                                      "scientific_acceptance": "not_yet_accepted", "records": records}))
    return floor_path


def small_world(tmp_path):
    world_path = tmp_path/"world.json"
    world_path.write_text(json.dumps({"pools": [], "routes": [], "rivers": []}))
    return world_path


def test_vegetation_resolution_applies_add_remove_replace(tmp_path):
    placements_path, overrides_path = write_placements(
        tmp_path, [tree("a"), tree("b"), tree("c")],
        adds=[tree("d", 30.0)], removes=["b", "d"], replaces={"c": tree("c", 11.0, 21.0)})
    records = vegetation_features(placements_path, overrides_path)
    assert [r["id"] for r in records] == ["a", "c"]
    assert records[1]["position"] == [11.0, 5.0, 21.0]


def test_vegetation_resolution_rejects_duplicate_and_unknown_ids(tmp_path):
    placements_path, overrides_path = write_placements(tmp_path, [tree("a"), tree("a", 30.0)])
    with pytest.raises(ValueError, match="duplicated"):
        vegetation_features(placements_path, overrides_path)
    placements_path, overrides_path = write_placements(tmp_path, [tree("a", kind="fern")])
    with pytest.raises(ValueError, match="unknown kind"):
        vegetation_features(placements_path, overrides_path)


def test_forest_floor_features_validate_schema_and_records(tmp_path):
    with pytest.raises(ValueError, match="authored schema"):
        forest_floor_features(write_placements(tmp_path, [tree("a")])[0])
    floor_path = write_floor(tmp_path, [floor_record("a"), floor_record("a", 30.0)])
    with pytest.raises(ValueError, match="duplicated"):
        forest_floor_features(floor_path)
    floor_path = write_floor(tmp_path, [floor_record("a", kind="shrub")])
    with pytest.raises(ValueError, match="unknown kind"):
        forest_floor_features(floor_path)
    floor_path = write_floor(tmp_path, [floor_record("a"), floor_record("b", 30.0, kind="log")])
    assert [r["id"] for r in forest_floor_features(floor_path)] == ["a", "b"]


def test_point_layers_index_each_record_exactly_once(tmp_path):
    placements_path, overrides_path = write_placements(
        tmp_path, [tree("a", -2040.0, -2040.0), tree("b", -2030.0, -2040.0), tree("c", 100.0, 100.0)],
        adds=[tree("edge", -3000.0, 0.0)])
    floor_path = write_floor(tmp_path, [floor_record("f1", -2040.0, -2040.0), floor_record("f2", 100.0, 100.0)])
    catalog = write_feature_pages(small_world(tmp_path), tmp_path/"features",
                                  placements_path=placements_path, overrides_path=overrides_path,
                                  forest_floor_path=floor_path)
    index = json.loads((tmp_path/"features"/"index.json").read_text())
    assert index["layer_grids"]["vegetation"]["cell_m"] == VEGETATION_CELL_M
    assert index["layer_grids"]["vegetation"]["cells_per_side"] == 64
    assert index["layer_grids"]["forest_floor"]["cell_m"] == FOREST_FLOOR_CELL_M
    assert index["out_of_extent"]["vegetation"] == ["edge"]
    assert index["out_of_extent"]["forest_floor"] == []
    seen = []
    for layer in ("vegetation", "forest_floor"):
        for entry in index["layers"][layer].values():
            page = json.loads((tmp_path/"features"/entry["path"]).read_text())
            assert page["layer"] == layer
            assert page["cell"]["size_m"] == 64.0
            seen.extend(str(f.get("id")) for f in page["features"])
    assert sorted(seen) == ["a", "b", "c", "f1", "f2"]
    counts = verify_feature_pages(tmp_path, {"features": catalog})
    assert counts["vegetation"] == 2 and counts["forest_floor"] == 2


def test_vegetation_pages_need_placements_and_overrides_together(tmp_path):
    placements_path, _ = write_placements(tmp_path, [tree("a")])
    with pytest.raises(ValueError, match="both"):
        write_feature_pages(small_world(tmp_path), tmp_path/"features", placements_path=placements_path)


@needs_data
def test_real_vegetation_and_floor_records_match_the_bake_receipts(tmp_path):
    records = vegetation_features(DATA/"placements.json", DATA/"placement_overrides.json")
    pines = [r for r in records if r["kind"] == "pine"]
    assert len(pines) == 63554
    assert len(records) == 76809
    floor = forest_floor_features(DATA/"forest_floor.json")
    assert len(floor) == 43624
    catalog = write_feature_pages(DATA/"world.json", tmp_path/"features",
                                  placements_path=DATA/"placements.json",
                                  overrides_path=DATA/"placement_overrides.json",
                                  forest_floor_path=DATA/"forest_floor.json")
    index = json.loads((tmp_path/"features"/"index.json").read_text())
    assert len(index["out_of_extent"]["vegetation"]) == 5
    paged = sum(entry["count"] for entry in index["layers"]["vegetation"].values())
    assert paged == len(records)-5
    paged_floor = sum(entry["count"] for entry in index["layers"]["forest_floor"].values())
    assert paged_floor == len(floor)
    assert all(entry["bytes"] <= 1 << 20
               for layer in ("vegetation", "forest_floor") for entry in index["layers"][layer].values())
    counts = verify_feature_pages(tmp_path, {"features": catalog})
    assert counts["vegetation"] > 1000 and counts["forest_floor"] > 100
