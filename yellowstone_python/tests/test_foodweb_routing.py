"""Tests for routing the replay food web refuge into the rendered trout."""
import json
from pathlib import Path

import pytest

from yellowstone_python.aquatic.fish import build_chainage, chainage_to_index, place_trout_at_chainage, update_trout
from yellowstone_python.insects_birds import update_wildlife_from_intake



def _data():
    world = json.load(open(WORLD))
    eco = json.load(open(ECO))
    river = next(r for r in world["rivers"] if r["id"] == "river_5856_0")
    return (river["points"], eco["river_reaches"],
            [w for w in eco["wildlife"] if "trout" in w["id"]],
            eco["wildlife"])


def _selection(s_m, temp=17.3, cell_id="firehole_cell_00146"):
    return {"s_m": s_m, "temperature_c": temp, "U": -0.071,
            "cell_id": cell_id, "refuge_reason": f"cell {cell_id} selected"}


def test_chainage_to_index_snaps_to_the_nearest_point():
    chainage = [0.0, 10.0, 20.0, 30.0]
    assert chainage_to_index(chainage, 10.0) == 1
    assert chainage_to_index(chainage, 14.0) == 1
    assert chainage_to_index(chainage, 16.0) == 2
    assert chainage_to_index(chainage, -50.0) == 0
    assert chainage_to_index(chainage, 999.0) == 3


def test_placement_moves_the_window_and_preserves_its_width():
    points, reaches, trout, _ = _data()
    placed = update_trout(trout, reaches, points)
    width = (placed[0]["end_point_index"] - placed[0]["start_point_index"])
    chainage = build_chainage(points)
    target = chainage[len(chainage) // 2]
    moved = place_trout_at_chainage(placed, reaches, points,
                                    _selection(target))
    assert (moved[0]["end_point_index"]
            - moved[0]["start_point_index"]) == width
    mid = build_chainage(points)[
        (moved[0]["start_point_index"] + moved[0]["end_point_index"]) // 2]
    assert mid == pytest.approx(target, abs=5.0)


def test_placement_carries_the_food_web_selection():
    points, reaches, trout, _ = _data()
    chainage = build_chainage(points)
    moved = place_trout_at_chainage(trout, reaches, points,
                                    _selection(chainage[400]))
    rec = moved[0]
    assert rec["refuge_cell_id"] == "firehole_cell_00146"
    assert rec["refuge_basis"] == "replay_foodweb"
    assert rec["reach_temp_c"] == 17.3
    assert rec["suitability_U"] == -0.071
    assert rec["thermal_performance"]
    assert rec["refuge_reason"] == "cell firehole_cell_00146 selected"


def test_placement_applies_the_replay_chainage_offset():
    points, reaches, trout, _ = _data()
    chainage = build_chainage(points)
    local = chainage[600]
    moved = place_trout_at_chainage(trout, reaches, points,
                                    _selection(local + 1947.66),
                                    chainage_offset_m=1947.66)
    assert moved[0]["refuge_off_polyline_m"] == pytest.approx(0.0, abs=5.0)
    unshifted = place_trout_at_chainage(trout, reaches, points,
                                        _selection(local))
    assert moved[0]["start_point_index"] == unshifted[0]["start_point_index"]


def test_selection_upstream_of_the_polyline_clamps_and_records_the_gap():
    points, reaches, trout, _ = _data()
    moved = place_trout_at_chainage(trout, reaches, points,
                                    _selection(35.0, temp=11.0,
                                               cell_id="trib_mallard_creek"),
                                    chainage_offset_m=1947.66)
    rec = moved[0]
    assert rec["start_point_index"] == 0
    assert rec["refuge_off_polyline_m"] < -1900.0
    assert rec["refuge_chainage_m"] == 35.0
    assert rec["refuge_cell_id"] == "trib_mallard_creek"
    assert rec["reach_temp_c"] == 11.0


def test_selection_downstream_of_the_polyline_clamps_to_the_last_point():
    points, reaches, trout, _ = _data()
    total = build_chainage(points)[-1]
    placed = update_trout(trout, reaches, points)
    width = placed[0]["end_point_index"] - placed[0]["start_point_index"]
    moved = place_trout_at_chainage(trout, reaches, points,
                                    _selection(total + 250.0))
    assert (moved[0]["end_point_index"]
            - moved[0]["start_point_index"]) == width
    assert moved[0]["end_point_index"] == len(points) - 1
    assert moved[0]["refuge_off_polyline_m"] == pytest.approx(250.0, abs=5.0)


def test_placement_requires_a_finite_chainage():
    points, reaches, trout, _ = _data()
    with pytest.raises(ValueError):
        place_trout_at_chainage(trout, reaches, points, {"cell_id": "x"})
    with pytest.raises(ValueError):
        place_trout_at_chainage(trout, reaches, points,
                                {"s_m": float("nan")})


def test_non_trout_records_are_untouched():
    points, reaches, trout, wildlife = _data()
    others = [w for w in wildlife if "trout" not in w["id"]]
    mixed = place_trout_at_chainage(others + trout, reaches, points,
                                    _selection(500.0))
    kept = [w for w in mixed if "trout" not in w["id"]]
    assert kept == others


def test_intake_basis_is_recorded_per_consumer():
    wildlife = [{"id": "dipper_01", "perch_seconds": 12.0,
                 "forage_seconds": 18.0},
                {"id": "raven_01", "perch_seconds": 12.0,
                 "forage_seconds": 18.0}]
    out = update_wildlife_from_intake(
        wildlife, {"dipper": 0.04, "raven": 0.01},
        {"dipper": "replay_foodweb", "raven": "insect_compartments"})
    basis = {w["id"]: w["intake_basis"] for w in out}
    assert basis == {"dipper_01": "replay_foodweb",
                     "raven_01": "insect_compartments"}


def test_intake_basis_is_absent_when_not_supplied():
    wildlife = [{"id": "dipper_01", "perch_seconds": 12.0,
                 "forage_seconds": 18.0}]
    out = update_wildlife_from_intake(wildlife, {"dipper": 0.04})
    assert "intake_basis" not in out[0]

pytestmark = pytest.mark.needs_world


@pytest.fixture(autouse=True)
def resolved_module_paths(monkeypatch, request, resolved_paths):
    """Provide path aliases from shared fixtures and restore them after each test."""
    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, 'ECO', resolved_paths['ECO_FROZEN'], raising=False)
    monkeypatch.setattr(module, 'WORLD', resolved_paths['WORLD_JSON'], raising=False)
