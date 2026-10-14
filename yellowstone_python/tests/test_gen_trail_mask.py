import json

import numpy as np
import pytest

from yellowstone_python.authoring.gen_trail_mask import _px, build_mask


def _world(routes):
    return {"routes": routes}


def _route(**kw):
    base = {"id": "t1", "kind": "trail", "surface": "Native", "width": 1024.0,
            "points": [[-2048.0, 0.0, 0.0], [2048.0, 0.0, 0.0]]}
    base.update(kw)
    return base


def test_main_creates_missing_output_directories(tmp_path, monkeypatch):
    import yellowstone_python.authoring.gen_trail_mask as generator
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "world.json").write_text(json.dumps(_world([_route()])))
    monkeypatch.setattr(generator, "WORLD", tmp_path)
    called = []
    original = generator.build_mask

    def recording_build(world, **kwargs):
        called.append(kwargs)
        return original(world, **kwargs)

    monkeypatch.setattr(generator, "build_mask", recording_build)
    assert generator.main(["--size", "32"]) == 0
    out = tmp_path / "assets" / "textures" / "trail_mask.png"
    assert out.exists() and out.stat().st_size > 0
    assert len(called) == 1 and called[0]["size"] == 32
    meta = json.loads(out.with_suffix(".png.provenance.json").read_text())
    assert meta["run_mode"] == "illustrative"
    assert meta["artifact"]["path"] == "assets/textures/trail_mask.png"
    assert all(not row["path"].startswith("/") for row in meta["sources"])
    assert meta["parameter_provenance"]["edge_softness_m"]["value"] == 0.6


def test_empty_route_list_renders_a_blank_mask():
    mask = build_mask(_world([]), size=16)
    assert mask.size == (16, 16) and mask.mode == "L"
    assert mask.getextrema() == (0, 0)


def test_single_point_and_missing_point_routes_are_skipped():
    for points in ([[0.0, 0.0, 0.0]], []):
        mask = build_mask(_world([_route(points=points)]), size=8)
        assert mask.getextrema() == (0, 0)
    route = _route()
    del route["points"]
    assert build_mask(_world([route]), size=8).getextrema() == (0, 0)


def test_wood_and_road_routes_are_skipped():
    for kwargs in ({"surface": "Wood"}, {"kind": "road"}):
        assert build_mask(_world([_route(**kwargs)]), size=8).getextrema() == (0, 0)


def test_narrow_trail_preserves_width_without_pixel_floor():
    route = _route(width=0.5, points=[[-12, 0, 0.5], [12, 0, 0.5]])
    mask = np.asarray(build_mask(_world([route]), size=32, half_extent_m=16,
                                 edge_softness_m=0), float) / 255
    assert mask[:, 16].sum() == pytest.approx(0.5, abs=0.01)
    assert mask[:, 16].max() < 1.0


def test_physical_2_3_m_cross_section_with_soft_shoulder():
    route = _route(width=2.3, points=[[-12, 0, 0.3], [12, 0, 0.3]])
    mask = np.asarray(build_mask(_world([route]), size=320, half_extent_m=16), float)
    assert mask[:, 160].sum() / 255 * 0.1 == pytest.approx(2.3, abs=0.01)
    assert mask.max() == 255 and np.any((mask > 0) & (mask < 255))


def test_pixel_center_registration():
    rows = []
    for z in (0.5, 1.5):
        route = _route(width=0.5, points=[[-12, 0, z], [12, 0, z]])
        mask = np.asarray(build_mask(_world([route]), size=32, half_extent_m=16,
                                     edge_softness_m=0))
        rows.append(int(np.argmax(mask[:, 16])))
    assert rows == [16, 17]
    assert _px(-2047.5, -2047.5) == (0.0, 0.0)
    assert _px(2047.5, 2047.5) == (4095.0, 4095.0)


def test_round_caps_match_capsule_area():
    route = _route(width=2.0, points=[[0, 0, 0], [4, 0, 0]])
    mask = np.asarray(build_mask(_world([route]), size=128, half_extent_m=8,
                                 edge_softness_m=0), float) / 255
    assert mask.sum() * 0.125 ** 2 == pytest.approx(8 + np.pi, abs=0.04)


def test_overlap_union_is_order_independent_and_idempotent():
    a = _route(width=2.3, points=[[-12, 0, 0.3], [12, 0, 0.3]])
    b = _route(width=2.3, points=[[0.3, 0, -12], [0.3, 0, 12]])
    kwargs = {"size": 64, "half_extent_m": 16}
    forward = np.asarray(build_mask(_world([a, b]), **kwargs))
    reverse = np.asarray(build_mask(_world([b, a, a]), **kwargs))
    assert np.array_equal(forward, reverse)


def test_out_of_extent_points_are_rejected():
    with pytest.raises(ValueError):
        build_mask(_world([_route(points=[[-99999, 0, 0], [0, 0, 0]])]), size=8)


def test_malformed_points_are_rejected():
    for points in ([[0, 0]], [[0, 0], [1, 0]], [[0, 0, 0], [float("nan"), 0, 0]],
                   [[None, 0, 0], [1, 0, 0]]):
        with pytest.raises(ValueError):
            build_mask(_world([_route(points=points)]), size=8)


def test_invalid_width_is_rejected():
    for width in ("wide", 0, -1, float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            build_mask(_world([_route(width=width)]), size=8)
    route = _route()
    del route["width"]
    with pytest.raises(ValueError):
        build_mask(_world([route]), size=8)


@pytest.mark.parametrize("kwargs", [{"size": 0}, {"size": -1}, {"size": 2.5},
                                    {"size": True}, {"size": 8193},
                                    {"half_extent_m": 0}, {"half_extent_m": float("nan")},
                                    {"edge_softness_m": -1}, {"supersample": 0},
                                    {"supersample": 9}, {"supersample": 1.5}])
def test_invalid_raster_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        build_mask(_world([]), **kwargs)


def test_programmatic_main_ignores_host_arguments(tmp_path, monkeypatch):
    import sys
    import yellowstone_python.authoring.gen_trail_mask as generator
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "world.json").write_text(json.dumps(_world([])))
    monkeypatch.setattr(generator, "WORLD", tmp_path)
    monkeypatch.setattr(generator, "SIZE", 16)
    monkeypatch.setattr(sys, "argv", ["host-app", "--unrelated-option"])
    assert generator.main() == 0
