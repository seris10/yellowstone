"""Tests for lidar and imagery pool outline tracing and the bundled pool measurement data."""
from __future__ import annotations

import json
import math

import numpy as np
import pytest
from shapely.geometry import Point, Polygon

from tests.paths import WORLD_JSON
from yellowstone_python.observations import pool_outlines as po
from yellowstone_python.registry.param_registry import PARAMS
from yellowstone_python.thermal_features import pool_crust

NAMED_POOLS = (1034, 1030, 1028, 1029)
BOILING_AT_SITE_C = 93.5


def _synthetic_points(radius=10.0, extent=40.0, density=8.0, seed=3):
    rng = np.random.default_rng(seed)
    count = int(density * (2 * extent) ** 2)
    x = rng.uniform(-extent, extent, count)
    z = rng.uniform(-extent, extent, count)
    keep = np.hypot(x, z) > radius
    return {"x": x[keep], "z": z[keep], "elevation": np.full(keep.sum(), 2200.0),
            "classification": np.full(keep.sum(), 2),
            "return_number": np.ones(keep.sum(), dtype=int),
            "number_of_returns": np.ones(keep.sum(), dtype=int)}


def test_lidar_void_trace_recovers_a_circular_pool():
    points = _synthetic_points(radius=10.0)
    bounds = (-40.0, -40.0, 40.0, 40.0)
    traced, info = po.trace_lidar_outline(points, bounds, (0.0, 0.0))
    assert traced.area == pytest.approx(math.pi * 100.0, rel=0.04)
    assert traced.centroid.distance(Point(0.0, 0.0)) < 0.3
    assert info["void_cells"] > 0


def test_lidar_trace_rejects_a_void_that_reaches_the_window_edge():
    points = _synthetic_points(radius=60.0, extent=60.0)
    with pytest.raises(ValueError, match="window edge"):
        po.trace_lidar_outline(points, (-40.0, -40.0, 40.0, 40.0), (0.0, 0.0))


def test_ring_difference_is_one_for_identical_polygons_and_less_when_shifted():
    square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    same = po.ring_difference(square, square)
    assert same["iou"] == 1.0 and same["hausdorff_m"] == 0.0
    moved = po.ring_difference(square, Polygon([(2, 0), (12, 0), (12, 10), (2, 10)]))
    assert 0.6 < moved["iou"] < 0.7
    assert moved["hausdorff_m"] == pytest.approx(2.0, abs=0.05)


def test_best_shift_recovers_a_known_translation():
    base = Polygon([(0, 0), (12, 0), (12, 8), (0, 8)])
    shifted = Polygon([(-3, -1.8), (9, -1.8), (9, 6.2), (-3, 6.2)])
    result = po.best_shift(base, shifted)
    assert (result["dx_m"], result["dz_m"]) == (pytest.approx(3.0, abs=0.31), pytest.approx(1.8, abs=0.31))
    assert result["iou"] > 0.95


def test_otsu_threshold_separates_two_modes():
    rng = np.random.default_rng(1)
    values = np.concatenate([rng.normal(0.05, 0.03, 4000), rng.normal(0.62, 0.03, 1000)])
    assert 0.05 + 3 * 0.03 < po.otsu_threshold(values) < 0.62 - 3 * 0.03


def test_imagery_polygon_follows_a_low_infrared_disk():
    size = 200
    yy, xx = np.mgrid[0:size, 0:size]
    inside = np.hypot(xx - 100, yy - 100) < 30
    image = np.zeros((size, size, 4), dtype=np.uint8)
    image[..., 1] = 190
    image[..., 3] = np.where(inside, 30, 200)
    scale = po.NAIP_PIXEL_M
    half = size * scale / 2.0
    bounds = (-half, -half, half, half)
    polygon, info = po.naip_polygon(image, bounds, (0.0, 0.0))
    assert polygon.area == pytest.approx(math.pi * (30 * scale) ** 2, rel=0.05)
    assert -0.03 < info["ndwi_threshold"] < 0.73


def test_trace_adoption_rule_constants_are_consistent():
    assert 0.5 < po.MIN_AGREEMENT_IOU <= 1.0
    assert po.MIN_SIMPLIFY_M <= po.LIDAR_SIMPLIFY_M


def _document(name):
    return json.loads((pool_crust.DATA_DIR / name).read_text(encoding="utf-8"))


def _outline_document():
    return _document("pool_outlines.json")


def test_outline_records_have_closed_valid_rings_and_receipts():
    records = {r["source_id"]: r for r in _outline_document()["pools"]}
    assert set(records) == set(NAMED_POOLS)
    for record in records.values():
        polygon = Polygon(record["ring"])
        assert polygon.is_valid and len(record["ring"]) >= 8
        assert polygon.area == pytest.approx(record["area_m2"], rel=0.005)
        assert polygon.contains(Point(record["centroid_xz"]))
        assert record["lidar_receipt"]["ept_sha256"] and record["lidar_receipt"]["nodes"]
        assert all(len(n["sha256"]) == 64 for n in record["lidar_receipt"]["nodes"])
        assert len(record["imagery_receipt"]["sha256"]) == 64
        assert record["outline_basis"] == "lidar_return_void"


def test_adoption_follows_the_registered_overlap_rule():
    for record in _outline_document()["pools"]:
        shift = record["qa"]["imagery_shift_to_lidar"]
        at_edge = max(abs(shift["dx_m"]), abs(shift["dz_m"])) >= po.SHIFT_SEARCH_M - 1e-6
        assert record["adopted"] == (shift["iou"] >= po.MIN_AGREEMENT_IOU and not at_edge)
    adopted = {r["source_id"] for r in _outline_document()["pools"] if r["adopted"]}
    assert adopted == {1034, 1028, 1029}


def test_registration_shift_is_consistent_across_adopted_pools():
    shifts = [r["qa"]["imagery_shift_to_lidar"] for r in _outline_document()["pools"] if r["adopted"]]
    assert max(s["dx_m"] for s in shifts) - min(s["dx_m"] for s in shifts) < 1.0
    assert max(s["dz_m"] for s in shifts) - min(s["dz_m"] for s in shifts) < 1.0


def test_traced_outlines_sit_near_the_mapped_polygon_for_the_large_pool():
    gp = next(r for r in _outline_document()["pools"] if r["source_id"] == 1034)
    assert gp["qa"]["lidar_vs_prior_polygon"]["iou"] > 0.85


def _temperatures():
    return _document("pool_temperatures.json")


def test_published_temperatures_are_physical_and_cited():
    for source_id, entry in _temperatures()["pools"].items():
        sample = entry["water_temperature_c"]
        if sample is None:
            continue
        assert 20.0 < sample["value"] <= BOILING_AT_SITE_C, source_id
        assert sample["source"] in _temperatures()["sources"]
        assert sample["status"] == "measured_literature"


def test_excelsior_range_contains_the_adopted_sample_and_excludes_impossible_rows():
    entry = _temperatures()["pools"]["1030"]
    values = [row["value"] for row in entry["observed_range_c"]["samples"]]
    assert entry["water_temperature_c"]["value"] in values
    assert min(values) == entry["observed_range_c"]["min"]
    assert max(values) == entry["observed_range_c"]["max"]
    assert all(row["value"] <= BOILING_AT_SITE_C for row in entry["observed_range_c"]["samples"])
    assert entry["observed_range_c"]["excluded"][0]["value"] > BOILING_AT_SITE_C


def test_turquoise_has_no_measured_temperature():
    assert _temperatures()["pools"]["1028"]["water_temperature_c"] is None
    assert pool_crust.measured_water_temperature(1028) is None


@pytest.mark.needs_world
def test_build_all_applies_measurements_and_keeps_authored_values_labeled():
    world = json.loads(WORLD_JSON.read_text())
    shells = {s["source_id"]: s for s in pool_crust.build_all(world["pools"])}
    assert shells[1030]["t_center_c"] == pytest.approx(88.7)
    assert shells[1029]["t_center_c"] == pytest.approx(55.56)
    assert shells[1034]["t_center_c"] == pytest.approx(63.3)
    assert shells[1028]["t_center_c"] == pytest.approx(63.0)
    for sid in (1030, 1029, 1034):
        assert shells[sid]["t_center_basis"] == "measured_literature"
    assert shells[1028]["t_center_basis"] == "authored"
    assert all(s["t_edge_basis"] == "authored" for s in shells.values())
    assert shells[1034]["depth_center_basis"] == "literature_lower_bound"
    assert shells[1030]["depth_center_basis"] == "authored"


@pytest.mark.needs_world
def test_build_all_uses_traced_outlines_only_where_adopted():
    world = json.loads(WORLD_JSON.read_text())
    pools = {p["source_id"]: p for p in world["pools"]}
    shells = {s["source_id"]: s for s in pool_crust.build_all(world["pools"])}
    records = {r["source_id"]: r for r in _outline_document()["pools"]}
    for sid in (1034, 1028, 1029):
        assert shells[sid]["outline_basis"] == "lidar_return_void"
        assert shells[sid]["ring"] == records[sid]["ring"]
        assert shells[sid]["mapped_area_m2"] == pytest.approx(records[sid]["area_m2"], rel=0.005)
    assert shells[1030]["outline_basis"] == "mapped_polygon"
    assert shells[1030]["ring"] == pools[1030]["ring"]
    assert "traced from lidar" in shells[1034]["status"]
    assert "measured (point sample)" in shells[1034]["status"]
    assert "authored" in shells[1028]["status"]


@pytest.mark.needs_world
def test_shell_for_pool_leaves_a_supplied_outline_and_temperature_untouched():
    world = json.loads(WORLD_JSON.read_text())
    gp = next(p for p in world["pools"] if p["source_id"] == 1034)
    shell = pool_crust.shell_for_pool(gp)
    assert shell["ring"] == gp["ring"]
    assert shell["t_center_c"] == gp["temperature_c"]
    assert shell["outline_basis"] == "mapped_polygon" and shell["t_center_basis"] == "authored"


@pytest.mark.needs_world
def test_traced_shell_keeps_the_water_inside_the_apron_and_radii_ordered():
    world = json.loads(WORLD_JSON.read_text())
    for shell in pool_crust.build_all(world["pools"]):
        assert shell["r_water_m"] < shell["r_shelf_m"] < shell["r_rim_m"] < shell["r_apron_m"]
        cx, cz = shell["center_xz"]
        if shell["outline_basis"] == "lidar_return_void":
            assert pool_crust.in_water(cx, cz, shell) and pool_crust.in_apron(cx, cz, shell)


def test_registry_declares_every_pool_quantity_with_the_right_class():
    by_id = {p["param_id"]: p for p in PARAMS}
    expected = {
        "pool.excelsior.water_temperature_c": "literature",
        "pool.opal.water_temperature_c": "literature",
        "pool.grand_prismatic.water_temperature_c": "literature",
        "pool.turquoise.water_temperature_c": "assumed",
        "pool.edge_temperature_c": "assumed",
        "pool.radial_temperature_profile": "illustrative",
        "pool.grand_prismatic.depth_center_m": "literature",
        "pool.depth_center_m": "illustrative",
        "pool.shelf_depth_m": "illustrative",
        "pool.shelf_ratio": "illustrative",
        "pool.rim_width_m": "illustrative",
        "pool.apron_width_m": "illustrative",
        "pool.outflow_bearing_deg": "illustrative",
        "pool.color_ramp_stops": "illustrative",
        "pool.outline.lidar_trace": "derived",
        "pool.outline.mapped_polygon": "literature",
    }
    for param_id, param_class in expected.items():
        assert by_id[param_id]["param_class"] == param_class, param_id
        assert by_id[param_id]["review"] == "not_yet_accepted"
    for measured in ("pool.excelsior.water_temperature_c", "pool.opal.water_temperature_c",
                     "pool.grand_prismatic.water_temperature_c"):
        assert by_id[measured]["uncertainty"] == "unknown"
