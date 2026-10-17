"""Vegetation exclusion corridor, deck and pool filtering on a small fixture."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apply_vegetation_exclusions import (DECKS, build_grid, exclusion_reason, filter_records,
                                         in_deck, in_pool, mask_canopy_cells, route_segments)


def fixture_world():
    """Return one trail, one road and one square pool."""
    return {
        "routes": [
            {"id": "trail_1_0", "kind": "trail", "width": 2.0,
             "points": [[0.0, 10.0, 0.0], [40.0, 10.0, 0.0]]},
            {"id": "road_1_0", "kind": "road", "width": 7.2,
             "points": [[0.0, 12.0, 100.0], [40.0, 12.0, 100.0]]},
        ],
        "pools": [
            {"id": "pool_1", "ring": [[50.0, 50.0], [60.0, 50.0], [60.0, 60.0], [50.0, 60.0]]},
        ],
    }


def fixture_setup():
    """Return the segment grid and pools for the fixture world."""
    world = fixture_world()
    segments = route_segments(world)
    return build_grid(segments), segments, world["pools"]


def test_route_corridor_uses_half_width_plus_clearance():
    grid, segments, pools = fixture_setup()
    assert exclusion_reason(grid, segments, pools, 20.0, 1.9) == "trail_1_0"
    assert exclusion_reason(grid, segments, pools, 20.0, 2.1) is None
    assert exclusion_reason(grid, segments, pools, 20.0, 104.5) == "road_1_0"
    assert exclusion_reason(grid, segments, pools, 20.0, 104.7) is None


def test_deck_and_pool_membership():
    assert in_deck(-252.0, 159.0) == "deck_0"
    assert in_deck(-252.0, 164.0) is None
    _, _, pools = fixture_setup()
    assert in_pool(pools, 55.0, 55.0) == "pool_1"
    assert in_pool(pools, 49.0, 55.0) is None


def test_filter_records_moves_violations_into_remove():
    grid, segments, pools = fixture_setup()
    records = [
        {"id": "grass_on_trail", "kind": "grass", "position": [20.0, 10.0, 0.5]},
        {"id": "pine_on_road", "kind": "pine", "position": [10.0, 12.0, 101.0]},
        {"id": "grass_in_pool", "kind": "grass", "position": [55.0, 7.0, 55.0]},
        {"id": "pine_on_deck", "kind": "pine", "position": [-252.0, 48.0, 159.0]},
        {"id": "grass_clear", "kind": "grass", "position": [20.0, 9.0, 30.0]},
    ]
    overrides = {"add": records, "remove": ["already_gone"]}
    removed = filter_records(overrides["add"], overrides, grid, segments, pools, "placement_overrides.json")
    assert {record["id"] for record in removed} == {"grass_on_trail", "pine_on_road", "grass_in_pool", "pine_on_deck"}
    assert all(record["source"] == "placement_overrides.json" for record in removed)
    assert overrides["remove"] == sorted(["already_gone", "grass_on_trail", "pine_on_road", "grass_in_pool", "pine_on_deck"])
    assert len(overrides["add"]) == 5
    second_pass = filter_records(records, overrides, grid, segments, pools, "placements.json")
    assert second_pass == []
    assert len(overrides["remove"]) == 5


def test_mask_canopy_cells_clears_only_excluded_active_cells():
    grid, segments, pools = fixture_setup()
    cells = np.zeros((4, 4), dtype=np.uint8)
    cells[0, 0] = 1
    cells[2, 1] = 1
    cells[3, 3] = 1
    cleared = mask_canopy_cells(cells, first_x=0.0, first_z=0.0, cell_size=2.0,
                                grid=grid, segments=segments, pools=pools)
    assert [(cell["row"], cell["column"]) for cell in cleared] == [(0, 0)]
    assert cleared[0]["reason"] == "trail_1_0"
    assert cells.tolist() == [[0, 0, 0, 0], [0, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]]
