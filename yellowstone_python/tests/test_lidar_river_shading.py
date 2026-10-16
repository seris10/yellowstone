"""Canopy geometry controls direct solar blocking."""
import math

import pytest

from yellowstone_python.aquatic.river_shading import canopy_direct_beam_fraction


def beam(tree):
    return canopy_direct_beam_fraction([tree], 0.0, 0.0, math.pi / 2,
                                      math.pi / 6, tree_height_m=15.0, tau=0.1)


def test_measured_heights_control_shadow_reach():
    tree = {"x": 20.0, "z": 0.0, "crown_r_m": 2.0}
    assert beam(tree) == 0.1
    assert beam(dict(tree, height_m=5.0)) == 1.0
    assert beam(dict(tree, height_m=30.0)) == 0.1


def test_live_crown_base_leaves_clear_bole_transparent():
    tree = {"x": 20.0, "z": 0.0, "crown_r_m": 2.0, "height_m": 30.0,
            "crown_ratio": 0.2}
    assert beam(tree) == 1.0
    assert beam(dict(tree, x=50.0)) == 0.1
    assert beam(dict(tree, x=50.0, crown_ratio=0.0)) == 1.0


@pytest.mark.parametrize("field,value", [
    ("height_m", 0.0), ("height_m", float("nan")),
    ("crown_r_m", -1.0), ("x", float("inf")),
    ("crown_ratio", 1.1),
])
def test_invalid_tree_dimensions_are_rejected(field, value):
    tree = {"x": 20.0, "z": 0.0, "crown_r_m": 2.0, "height_m": 30.0}
    tree[field] = value
    with pytest.raises(ValueError):
        beam(tree)
