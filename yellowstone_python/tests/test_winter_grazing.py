"""Tests for grazers winter behavior: snow-depth cost and warm-ground refuge."""
import math

import pytest

from yellowstone_python.land.grazers import SPECIES_PARAMS, route_cost, snow_movement_cost, update_grazers


def test_movement_cost_rises_with_snow_depth():
    assert snow_movement_cost("bison", 0.0) == pytest.approx(1.0)
    light = snow_movement_cost("bison", 0.1)
    deep = snow_movement_cost("bison", 0.5)
    assert light > 1.0
    assert deep > light
    # Beyond the cratering depth movement cost is infinite.
    assert math.isinf(snow_movement_cost("bison",
                                         SPECIES_PARAMS["bison"]["crater_depth_m"]))


def test_route_cost_rises_with_snow_depth():
    path = [[0, 0], [100, 0]]
    assert route_cost(path, 0.0, "bison") == pytest.approx(100.0)
    assert route_cost(path, 0.3, "bison") > 100.0
    # Elk reach their cratering limit at a lower depth than bison.
    assert math.isinf(route_cost(path, 0.6, "elk"))
    assert route_cost(path, 0.6, "bison") < math.inf


def test_grazing_shifts_to_warm_patch_in_deep_snow():
    patches = [
        {"id": "meadow", "biomass": 0.6, "capacity": 1.0, "center_xz": [0, 0]},
        {"id": "warm_apron", "biomass": 0.3, "capacity": 1.0,
         "center_xz": [100, 0]},
    ]
    wl = [{"id": "bison_demo", "kind": "bison", "patch_id": "meadow",
           "graze_seconds": 30, "rest_seconds": 20}]
    # Deep snow on meadow, warm ground available at warm_apron.
    out = update_grazers(wl, patches,
                         snow_depth_by_patch={"meadow": 1.2, "warm_apron": 0.0},
                         warm_ground_by_patch={"meadow": False,
                                                "warm_apron": True})
    assert out[0]["patch_id"] == "warm_apron"
    assert out[0]["patch_shift_reason"] == "warm_ground_refuge_under_deep_snow"


def test_grazing_stays_without_deep_snow():
    patches = [
        {"id": "meadow", "biomass": 0.6, "capacity": 1.0, "center_xz": [0, 0]},
        {"id": "warm_apron", "biomass": 0.3, "capacity": 1.0,
         "center_xz": [100, 0]},
    ]
    wl = [{"id": "bison_demo", "kind": "bison", "patch_id": "meadow",
           "graze_seconds": 30, "rest_seconds": 20}]
    out = update_grazers(wl, patches,
                         snow_depth_by_patch={"meadow": 0.1,
                                               "warm_apron": 0.0},
                         warm_ground_by_patch={"meadow": False,
                                                "warm_apron": True})
    assert out[0]["patch_id"] == "meadow"
    # Light snow still raises the movement cost so the recorded factor is > 1.
    assert float(out[0]["movement_cost_factor"]) > 1.0


def test_elk_uses_elk_crater_depth():
    patches = [{"id": "m", "biomass": 0.6, "capacity": 1.0,
                "center_xz": [0, 0]}]
    wl = [{"id": "elk_demo", "kind": "elk", "patch_id": "m",
           "graze_seconds": 30, "rest_seconds": 20}]
    out = update_grazers(
        wl, patches,
        snow_depth_by_patch={"m": SPECIES_PARAMS["elk"]["crater_depth_m"]},
        warm_ground_by_patch=None)
    assert out[0]["movement_cost_factor"] == "inf"


def test_consumed_by_patch_from_grazers_is_available():
    from yellowstone_python.land.grazers import consumed_by_patch_from_grazers
    patches = [{"id": "m", "biomass": 0.9, "capacity": 1.0,
                "center_xz": [0, 0]}]
    wl = [{"id": "bison_1", "kind": "bison", "patch_id": "m",
           "graze_seconds": 30, "rest_seconds": 20}]
    out = update_grazers(wl, patches)
    consumed = consumed_by_patch_from_grazers(out, dt_s=3600.0)
    assert "m" in consumed and consumed["m"] > 0.0
