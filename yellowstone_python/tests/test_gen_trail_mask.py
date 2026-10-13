import json

import pytest

from yellowstone_python.gen_trail_mask import (MIN_TRAIL_PX, build_mask, _px)


def _world(routes):
    return {"routes": routes}


def _route(**kw):
    base = {"id": "t1", "kind": "trail", "surface": "Native", "width": 1024.0,
            "points": [[-2048.0, 0.0, 0.0], [2048.0, 0.0, 0.0]]}
    base.update(kw)
    return base


def test_main_creates_missing_output_directories(tmp_path, monkeypatch):
    from yellowstone_python import gen_trail_mask
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "world.json").write_text(
        json.dumps(_world([_route()])))
    monkeypatch.setattr(gen_trail_mask, "WORLD", tmp_path)
    assert gen_trail_mask.main() == 0
    out = tmp_path / "assets" / "textures" / "trail_mask.png"
    assert out.exists() and out.stat().st_size > 0


def test_empty_route_list_renders_a_blank_mask():
    from yellowstone_python.gen_trail_mask import build_mask
    mask = build_mask({"routes": []}, size=16)
    assert mask.size == (16, 16) and mask.mode == "L"
    assert mask.getextrema() == (0, 0)


def test_single_point_and_missing_point_routes_are_skipped():
    # A single-point route has < 2 points and is skipped by build_mask.
    from yellowstone_python.gen_trail_mask import build_mask
    mask = build_mask({"routes": [{"id": "t", "kind": "trail",
                                  "surface": "Native", "width": 4.0,
                                  "points": [[0.0, 0.0, 0.0]]}]}, size=8)
    assert mask.getextrema() == (0, 0)
    # A route missing the "points" key also skips safely.
    mask2 = build_mask({"routes": [{"id": "t", "kind": "trail",
                                   "surface": "Native", "width": 4.0}]}, size=8)
    assert mask2.getextrema() == (0, 0)


def test_wood_and_road_routes_are_skipped():
    # Wood boardwalks and roads are excluded from the mask.
    mask_wood = build_mask(_world([_route(id="w", surface="Wood")]), size=8)
    assert mask_wood.getextrema() == (0, 0)
    mask_road = build_mask(_world([_route(id="rd", kind="road")]), size=8)
    assert mask_road.getextrema() == (0, 0)


def test_narrow_trail_keeps_its_minimum_core():
    mask = build_mask(_world([_route(width=0.5)]), size=16)
    core = mask.histogram()[255]
    assert core >= MIN_TRAIL_PX


def test_mask_carries_a_hard_core_and_a_soft_shoulder():
    # Core plus shoulder visible when line does not fill the entire image.
    mask = build_mask(_world([_route(width=512.0)]), size=128)
    assert mask.mode == "L" and mask.size == (128, 128)
    hist = mask.histogram()
    assert hist[255] > 0
    assert max(v for v in hist[1:255]) > 0  # some shoulder pixels present


def test_out_of_extent_points_are_rejected():
    with pytest.raises(ValueError):
        build_mask(_world([_route(points=[[-99999.0, 0.0, 0.0],
                                          [0.0, 0.0, 0.0]])]), size=8)


def test_malformed_points_are_rejected():
    for pts in ([[0.0, 0.0]], [[0.0, 0.0], [1.0, 0.0]],
                [[0.0, 0.0, 0.0], [float("nan"), 0.0, 0.0]]):
        with pytest.raises(ValueError):
            build_mask(_world([_route(points=pts)]), size=8)


def test_invalid_width_is_rejected():
    for width in ("wide", 0.0, -1.0, float("nan")):
        with pytest.raises(ValueError):
            build_mask(_world([_route(width=width)]), size=8)
    route = _route()
    del route["width"]
    with pytest.raises(ValueError):
        build_mask(_world([route]), size=8)


def test_mask_size_must_be_positive():
    with pytest.raises(ValueError):
        build_mask(_world([]), size=0)
    with pytest.raises(ValueError):
        build_mask(_world([]), size=-1)
