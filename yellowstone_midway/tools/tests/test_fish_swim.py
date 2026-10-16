"""Numerical rig checks and reduced-asset import contracts."""
from pathlib import Path
import importlib.util
import sys

import numpy as np
import pytest

MODULE_PATH = Path(__file__).parents[1] / "fish_swim.py"
SPEC = importlib.util.spec_from_file_location("midway_fish_swim", MODULE_PATH)
f = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = f
SPEC.loader.exec_module(f)


def mesh():
    return np.array([[.055 * np.cos(t), .11 * np.sin(t), z]
                     for z in np.linspace(-1., 1., 91)
                     for t in np.linspace(0., 2 * np.pi, 12, endpoint=False)], dtype=np.float32)


def test_skin_weights_and_rest_pose():
    points = mesh()
    rig = f.make_rig(points)
    np.testing.assert_allclose(rig.weights.sum(axis=1), 1., atol=2e-7)
    np.testing.assert_allclose(f.skin_vertices(points, rig, 0., f.PRESETS[1], amplitude_multiplier=0.), points, atol=1e-6)


def test_cycle_closure_and_head_tail_motion():
    points = mesh()
    rig = f.make_rig(points)
    for preset in f.PRESETS:
        np.testing.assert_allclose(f.local_spine_angles(0., rig, preset), f.local_spine_angles(2., rig, preset), atol=1e-12)
    a = f.skin_vertices(points, rig, 0., f.PRESETS[1])
    b = f.skin_vertices(points, rig, .125, f.PRESETS[1])
    assert np.max(np.abs(a[points[:, 2] > .81] - points[points[:, 2] > .81])) < 1e-4
    assert np.mean(np.abs(b[points[:, 2] < -.8, 0] - a[points[:, 2] < -.8, 0])) > .005


def test_invalid_rig_bounds():
    with pytest.raises(ValueError):
        f.make_rig(mesh(), num_joints=3)


@pytest.mark.parametrize("species", ["brown_trout", "rainbow_trout"])
def test_reduced_asset_skin_clips_budget(species):
    path = Path(__file__).parents[2] / "assets/imported/fauna/trout" / (species + "_swim.glb")
    doc, binary = f.read_glb(path)
    assert len(doc["skins"][0]["joints"]) == 15
    assert {a["name"] for a in doc["animations"]} == {p.name for p in f.PRESETS}
    primitive = doc["meshes"][0]["primitives"][0]
    vertices = f.accessor_array(doc, binary, primitive["attributes"]["POSITION"])
    assert len(vertices) < 8000
    weights = f.accessor_array(doc, binary, primitive["attributes"]["WEIGHTS_0"])
    np.testing.assert_allclose(weights.sum(axis=1), 1., atol=2e-6)
    assert path.stat().st_size < 4 * 1024 * 1024
