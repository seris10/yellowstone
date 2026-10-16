"""Tests for ground_heat: flux field, soil temperature, snow melt and tree gate."""
import math

import pytest

from yellowstone_python.thermal_features.ground_heat import BOILING_T_REFERENCE_SITE_M, GHF_APRON_W_M2, GHF_BACKGROUND_W_M2, LODGEPOLE_SOIL_DIEOFF_C, boiling_point_c, heat_flux_at, heat_flux_mask_field, soil_temperature_by_patch, soil_temperature_c, thermal_flux_mm_d_by_patch, thermal_melt_mm_d_from_ghf, tree_thermal_suitability
from yellowstone_python.land.snow_season import run_season


def _ring(cx, cz, r, n=16):
    out = []
    for k in range(n):
        a = 2 * math.pi * k / n
        out.append([cx + r * math.cos(a), cz + r * math.sin(a)])
    return out


def _shell(sid, cx, cz, r_water, r_apron):
    return {"id": sid, "name": sid, "center_xz": [cx, cz],
            "ring": _ring(cx, cz, r_water),
            "r_water_m": r_water, "r_apron_m": r_apron,
            "apron_margin_m": r_apron - r_water}


def test_point_flux_hot_vs_background():
    shells = [_shell("pool1", 0.0, 0.0, 10.0, 40.0)]
    # Pool interior reads the pool flux (hottest).
    assert heat_flux_at(0.0, 0.0, shells) > GHF_APRON_W_M2
    # Buffered apron reads the apron flux.
    assert heat_flux_at(20.0, 0.0, shells) == pytest.approx(GHF_APRON_W_M2)
    # Far from any pool reads the basin background.
    assert heat_flux_at(500.0, 500.0, shells) == pytest.approx(GHF_BACKGROUND_W_M2)


def test_soil_temperature_scales_with_flux():
    hot = soil_temperature_c(0.0, 200.0, depth_m=0.1)
    cold = soil_temperature_c(0.0, 10.0, depth_m=0.1)
    assert hot > cold


def test_soil_temperature_bounded_by_local_boiling_point():
    # At the Yellowstone site elevation, water boils below 100 C.
    tb = boiling_point_c(BOILING_T_REFERENCE_SITE_M)
    assert 90.0 < tb < 95.0
    saturated = soil_temperature_c(0.0, 1.0e5, depth_m=0.1,
                                   site_elevation_m=BOILING_T_REFERENCE_SITE_M)
    assert saturated == pytest.approx(tb, abs=1e-6)


def test_snow_free_duration_rises_with_ground_heat_flux():
    # Two patches, same climate, different per-patch thermal fluxes.
    patches = [
        {"id": "cold", "habitat": "dry_meadow", "center_xz": [0, 0],
         "moisture": 0.4, "snow_mm": 50.0},
        {"id": "hot", "habitat": "dry_meadow", "center_xz": [10, 0],
         "moisture": 0.4, "snow_mm": 50.0},
    ]
    # Air just below freezing: degree-day melt is zero, so differences come from thermal flux alone.
    air_c_by_day = [-2.0] * 20
    thermal_cold = thermal_melt_mm_d_from_ghf(1.0)   # near-zero, basin background
    thermal_hot = thermal_melt_mm_d_from_ghf(100.0)  # thermal apron
    out, led = run_season(
        patches, days=20, air_c_by_day=air_c_by_day, precip_mm_d=0.0,
        thermal_flux_mm_d_by_patch={"cold": thermal_cold, "hot": thermal_hot})
    by_id = {p["id"]: p for p in out}
    assert by_id["hot"]["snow_mm"] < by_id["cold"]["snow_mm"]
    # Water ledger must still close.
    assert abs(led["storage_residual_mm"]) < 0.05


def test_tree_suitability_zero_above_dieoff_threshold():
    assert tree_thermal_suitability(LODGEPOLE_SOIL_DIEOFF_C + 1.0) == 0.0
    assert tree_thermal_suitability(LODGEPOLE_SOIL_DIEOFF_C) == 0.0
    assert tree_thermal_suitability(LODGEPOLE_SOIL_DIEOFF_C - 10.0) == 1.0
    # Linear band of 5 C below threshold.
    mid = tree_thermal_suitability(LODGEPOLE_SOIL_DIEOFF_C - 2.5)
    assert 0.4 <= mid <= 0.6


def test_heat_flux_mask_field_shape_and_values():
    shells = [_shell("p", 0.0, 0.0, 10.0, 40.0)]
    field = heat_flux_mask_field(shells, size=8)
    assert field["grid"]["nx"] == 8
    assert field["grid"]["nz"] == 8
    assert len(field["values_w_m2"]) == 8
    assert all(len(r) == 8 for r in field["values_w_m2"])
    # At least some cell is at the background value (world is big relative to the pool).
    all_values = [v for row in field["values_w_m2"] for v in row]
    assert min(all_values) == pytest.approx(GHF_BACKGROUND_W_M2)


def test_patch_flux_and_soil_t_dict_keyed_by_id():
    shells = [_shell("p", 0.0, 0.0, 10.0, 40.0)]
    patches = [
        {"id": "A", "center_xz": [0, 0]},
        {"id": "B", "center_xz": [500, 500]},
    ]
    flux = thermal_flux_mm_d_by_patch(patches, shells)
    assert flux["A"] > flux["B"]
    soil = soil_temperature_by_patch(patches, shells, air_c=0.0, depth_m=0.1)
    assert soil["A"] > soil["B"]
