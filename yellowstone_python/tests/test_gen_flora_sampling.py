"""Flora sampling order and mineral exclusion checks."""
from __future__ import annotations

import numpy as np
import pytest

import yellowstone_python.authoring.gen_flora as gen_flora
from yellowstone_python.land.vegetation import GRID, HALF, STEP


needs_world = pytest.mark.needs_world


def test_shuffled_cells_is_seeded_permutation():
    cells = gen_flora.shuffled_cells(7, 5, 301)
    assert sorted(cells) == sorted((i, j) for j in range(5) for i in range(7))
    assert cells == gen_flora.shuffled_cells(7, 5, 301)
    assert cells != gen_flora.shuffled_cells(7, 5, 302)
    assert cells != [(i, j) for j in range(5) for i in range(7)]


def test_capped_shuffle_reaches_southern_rows():
    n = 100
    head = gen_flora.shuffled_cells(n, n, 401)[:200]
    rows = [j for _, j in head]
    assert min(rows) < n // 4 and max(rows) > 3 * n // 4


def test_is_mineral_threshold_and_off_grid():
    mask = np.zeros((GRID, GRID, 3))
    x, z = 10.0, -20.0
    mx, mz = int((x + HALF) / STEP), int((z + HALF) / STEP)
    mask[mz, mx, 0] = gen_flora.MINERAL_PINE_MAX - 0.01
    assert not gen_flora.is_mineral(mask, x, z)
    mask[mz, mx, 0] = gen_flora.MINERAL_PINE_MAX
    assert gen_flora.is_mineral(mask, x, z)
    assert gen_flora.is_mineral(mask, HALF + 50.0, 0.0)


def _check_spread_and_mineral(records, z_lo, z_hi):
    assert records, "capped run accepted no candidates"
    zs = [r["z"] for r in records]
    span = z_hi - z_lo
    assert min(zs) < z_lo + 0.3 * span
    assert max(zs) > z_hi - 0.3 * span
    mask = gen_flora._habitat_mask()
    assert not any(gen_flora.is_mineral(mask, r["x"], r["z"]) for r in records)


@needs_world
def test_forest_infill_capped_run_spans_map():
    records, _ = gen_flora.forest_infill(count=150)
    assert len(records) == 150
    _check_spread_and_mineral(records, -HALF, HALF)


@needs_world
def test_grove_planting_capped_run_spans_map():
    records, _ = gen_flora.grove_planting(count=150)
    assert len(records) == 150
    _check_spread_and_mineral(records, -HALF, HALF)


@needs_world
def test_deck_groves_capped_run_spans_ring():
    cz, r1 = 159.0, 400.0
    records, _ = gen_flora.deck_viewshed_groves(count=100)
    assert len(records) == 100
    _check_spread_and_mineral(records, cz - r1, cz + r1)


@pytest.fixture(autouse=True)
def resolved_module_paths(monkeypatch, request, resolved_paths):
    """Provide path aliases from shared fixtures and restore them after each test."""
    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, 'MIDWAY', resolved_paths['MIDWAY'], raising=False)
    if request.node.get_closest_marker("needs_world") or request.node.get_closest_marker("needs_network_inputs"):
        for relative in ('data/world.json', 'data/terrain.f32', 'data/placements.json', 'data/placement_overrides.json', 'data/ecosystem.json.pre-python', 'assets/textures/habitat_mask.png', 'references/orthophoto.jpg'):
            path = resolved_paths["MIDWAY"] / relative
            if not path.is_file():
                pytest.skip(f"required world input missing: {path}")
