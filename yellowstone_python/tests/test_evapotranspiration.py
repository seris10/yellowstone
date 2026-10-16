"""Tests for FAO-56 Penman-Monteith reference ET and patch soil-water depletion."""
import pytest

from yellowstone_python.land.evapotranspiration import actual_et_mm_d, atmospheric_pressure_kpa, crop_coefficient_for, psychrometric_constant_kpa_c, reference_et0_mm_d, saturation_vapor_pressure_kpa, slope_svp_kpa_c, step_patches_et


def test_svp_matches_allen_table_2():
    # Allen (1998) Table 2.4: e0(20 C) = 2.339 kPa, e0(10 C) = 1.228 kPa.
    assert saturation_vapor_pressure_kpa(20.0) == pytest.approx(2.339, abs=0.01)
    assert saturation_vapor_pressure_kpa(10.0) == pytest.approx(1.228, abs=0.01)


def test_slope_svp_matches_allen_eq13():
    # Allen (1998) Eq 13 at 16.9 C: Delta = 0.122 kPa/C.
    assert slope_svp_kpa_c(16.9) == pytest.approx(0.122, abs=0.002)


def test_pressure_and_gamma_at_100m():
    # Allen (1998) FAO-56 Example 18 intermediate values at 100 m: P about 100.1 kPa, gamma about 0.0666.
    p = atmospheric_pressure_kpa(100.0)
    assert p == pytest.approx(100.1, abs=0.2)
    assert psychrometric_constant_kpa_c(p) == pytest.approx(0.0666, abs=0.002)


def test_reference_et0_fao56_example_18():
    # Allen (1998) FAO-56 Example 18 (daily ET0 at Uccle, Brussels, 6 July).
    et0 = reference_et0_mm_d(
        tmax_c=21.5, tmin_c=12.3,
        rn_mj_m2_d=13.28, g_mj_m2_d=0.14,
        u2_m_s=2.078, elevation_m=100.0,
        rh_max_pct=84.0, rh_min_pct=63.0)
    # Published Example 18 ET0 = 3.9 mm/day; the formula reproduces it to within 0.1.
    assert et0 == pytest.approx(3.9, abs=0.1)


def test_reference_et0_monotonic_in_rn_and_wind():
    base = dict(tmax_c=25.0, tmin_c=15.0, rn_mj_m2_d=12.0, g_mj_m2_d=0.0,
                u2_m_s=2.0, elevation_m=100.0, rh_mean_pct=55.0)
    base_et0 = reference_et0_mm_d(**base)
    hotter = reference_et0_mm_d(**{**base, "rn_mj_m2_d": 18.0})
    windier = reference_et0_mm_d(**{**base, "u2_m_s": 5.0})
    assert hotter > base_et0
    assert windier > base_et0


def test_crop_coefficient_lookup_known_and_unknown():
    assert crop_coefficient_for("dry_meadow") == 1.0
    assert crop_coefficient_for("sinter_dry") < 0.5
    with pytest.raises(ValueError):
        crop_coefficient_for("not_a_type")


def test_soil_water_declines_faster_under_vegetation_in_warm_weather():
    # Same ET0, same soil water, different Kc: grass meadow depletes faster than sinter.
    et0 = 6.0  # warm, dry weather
    patch_veg = {"id": "v", "habitat": "dry_meadow", "soil_mm": 80.0}
    patch_bare = {"id": "b", "habitat": "sinter_dry", "soil_mm": 80.0}
    out_v, led_v = step_patches_et([patch_veg], et0, dt_days=5.0)
    out_b, led_b = step_patches_et([patch_bare], et0, dt_days=5.0)
    assert out_v[0]["soil_mm"] < out_b[0]["soil_mm"]
    assert led_v["et_by_patch_mm"]["v"] > led_b["et_by_patch_mm"]["b"]


def test_actual_et_bounded_by_soil_water():
    # Zero soil water yields zero actual ET even at a high ET0 and Kc.
    assert actual_et_mm_d(10.0, 1.0, soil_water_fraction=0.0) == 0.0
    # Full soil water matches Kc * ET0.
    assert actual_et_mm_d(5.0, 0.8, soil_water_fraction=1.0) == pytest.approx(4.0)
