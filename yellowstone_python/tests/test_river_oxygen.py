"""Tests for the river dissolved oxygen compartment."""
from __future__ import annotations

import math

import pytest

from yellowstone_python.common.site import SITE_PRESSURE_KPA
from yellowstone_python.aquatic.river_oxygen import CHURCHILL_COEF, COVAR_DEEP_SLOW_COEF, COVAR_DEEP_SLOW_EXPONENT, COVAR_SHALLOW_DEPTH_M, OCONNOR_DOBBINS_COEF, OWENS_COEF, OxygenCell, advect_cells, churchill_per_day, describe_model, fish_suitability, insect_survival, oconnor_dobbins_per_day, owens_per_day, pressure_from_elevation_kpa, reaeration_per_day, saturation_mg_l, score_against_observations, select_reaeration_formula, step_cell


def test_pressure_matches_shared_site_constant():
    assert pressure_from_elevation_kpa(2215.0) == pytest.approx(
        SITE_PRESSURE_KPA, rel=1e-9)


def test_saturation_matches_benson_krause_1_atm_table():
    standard = 101.325
    cases = {
        0.0: 14.621,
        10.0: 11.288,
        15.0: 10.084,
        20.0: 9.092,
        25.0: 8.263,
    }
    for t_c, expected in cases.items():
        value = saturation_mg_l(t_c, standard)
        assert abs(value - expected) < 0.05, (t_c, value, expected)


def test_warmer_reach_at_equal_reaeration_holds_less_oxygen():
    rate_cold = reaeration_per_day(0.4, 1.0)
    rate_warm = reaeration_per_day(0.4, 1.0)
    assert rate_cold == rate_warm
    cold = OxygenCell(id="cold", length_m=50.0, width_m=22.0, depth_m=1.0,
                      velocity_m_s=0.4, temp_c=5.0, do_mg_l=5.0)
    warm = OxygenCell(id="warm", length_m=50.0, width_m=22.0, depth_m=1.0,
                      velocity_m_s=0.4, temp_c=25.0, do_mg_l=5.0)
    for _ in range(60):
        up_cold = saturation_mg_l(cold.temp_c)
        up_warm = saturation_mg_l(warm.temp_c)
        cold_step = step_cell(cold, up_cold, 60.0)
        warm_step = step_cell(warm, up_warm, 60.0)
        cold = OxygenCell(id=cold.id, length_m=cold.length_m,
                          width_m=cold.width_m, depth_m=cold.depth_m,
                          velocity_m_s=cold.velocity_m_s, temp_c=cold.temp_c,
                          do_mg_l=cold_step["do_mg_l"])
        warm = OxygenCell(id=warm.id, length_m=warm.length_m,
                          width_m=warm.width_m, depth_m=warm.depth_m,
                          velocity_m_s=warm.velocity_m_s, temp_c=warm.temp_c,
                          do_mg_l=warm_step["do_mg_l"])
    assert warm.do_mg_l < cold.do_mg_l
    assert saturation_mg_l(warm.temp_c) < saturation_mg_l(cold.temp_c)


def test_fish_suitability_falls_with_oxygen_at_fixed_temperature():
    high = fish_suitability(9.0)
    medium = fish_suitability(6.0)
    low = fish_suitability(4.0)
    starved = fish_suitability(2.0)
    assert high == pytest.approx(1.0)
    assert starved == pytest.approx(0.0)
    assert low < medium < high


def test_insect_survival_follows_davis_1975_thresholds():
    assert insect_survival(5.0) == pytest.approx(1.0)
    assert insect_survival(2.0) == pytest.approx(0.0)
    assert 0.0 < insect_survival(3.0) < 1.0


def test_oconnor_dobbins_coefficient_is_cited():
    assert OCONNOR_DOBBINS_COEF == pytest.approx(3.93)
    assert CHURCHILL_COEF == pytest.approx(5.026)
    assert OWENS_COEF == pytest.approx(5.32)


def _covar_curve(v_m_s: float) -> float:
    """Depth-velocity threshold from the Covar form used in QUAL2K and ICM."""
    return COVAR_DEEP_SLOW_COEF * (v_m_s ** COVAR_DEEP_SLOW_EXPONENT)


def test_covar_selects_oconnor_dobbins_above_depth_velocity_curve():
    v = 0.5
    threshold = _covar_curve(v)
    deep_above = threshold + 0.1
    assert deep_above > COVAR_SHALLOW_DEPTH_M
    picked = select_reaeration_formula(v, deep_above)
    assert picked == "oconnor_dobbins"
    assert reaeration_per_day(v, deep_above) == pytest.approx(
        oconnor_dobbins_per_day(v, deep_above))


def test_covar_selects_churchill_below_depth_velocity_curve():
    v = 1.0
    threshold = _covar_curve(v)
    deep_below = max(COVAR_SHALLOW_DEPTH_M + 0.1, threshold - 0.5)
    assert deep_below >= COVAR_SHALLOW_DEPTH_M
    assert deep_below < threshold
    picked = select_reaeration_formula(v, deep_below)
    assert picked == "churchill"
    assert reaeration_per_day(v, deep_below) == pytest.approx(
        churchill_per_day(v, deep_below))
    assert COVAR_DEEP_SLOW_COEF == pytest.approx(3.45)
    assert COVAR_DEEP_SLOW_EXPONENT == pytest.approx(2.5)


def test_covar_selects_owens_edwards_gibbs_for_shallow_reach():
    shallow = select_reaeration_formula(0.4, 0.3)
    assert shallow == "owens_edwards_gibbs"
    assert reaeration_per_day(0.4, 0.3) == pytest.approx(
        owens_per_day(0.4, 0.3))
    assert COVAR_SHALLOW_DEPTH_M == pytest.approx(0.61)
    just_shallow = select_reaeration_formula(0.1, COVAR_SHALLOW_DEPTH_M - 1e-6)
    assert just_shallow == "owens_edwards_gibbs"


def test_step_cell_raises_on_courant_above_one():
    cell = OxygenCell(id="fast", length_m=5.0, width_m=20.0, depth_m=1.0,
                      velocity_m_s=1.5, temp_c=15.0, do_mg_l=7.0)
    with pytest.raises(ValueError, match="Courant"):
        step_cell(cell, upstream_do_mg_l=9.0, dt_s=60.0)


def test_implicit_advect_stable_at_high_courant():
    cells = [
        OxygenCell(id=f"c{i}", length_m=20.0, width_m=20.0, depth_m=1.0,
                   velocity_m_s=1.5, temp_c=15.0, do_mg_l=7.0)
        for i in range(10)
    ]
    out = advect_cells(cells, upstream_do_mg_l=9.0, dt_s=600.0)
    assert out["max_advective_courant"] > 1.0
    assert all(math.isfinite(r["do_mg_l"]) for r in out["cells"])
    assert all(0.0 <= r["do_mg_l"] <= 15.0 for r in out["cells"])


def test_implicit_advect_relaxes_toward_saturation_from_deficit():
    cell = OxygenCell(id="c", length_m=50.0, width_m=20.0, depth_m=1.0,
                      velocity_m_s=0.3, temp_c=15.0, do_mg_l=4.0)
    sat = saturation_mg_l(15.0)
    out = advect_cells([cell], upstream_do_mg_l=sat, dt_s=600.0)
    assert out["cells"][0]["do_mg_l"] > 4.0
    assert out["cells"][0]["do_mg_l"] <= sat + 1e-9


def test_implicit_advect_lies_between_upstream_and_saturation():
    cell = OxygenCell(id="c", length_m=50.0, width_m=20.0, depth_m=1.0,
                      velocity_m_s=0.3, temp_c=15.0, do_mg_l=5.0)
    sat = saturation_mg_l(15.0)
    out = advect_cells([cell], upstream_do_mg_l=9.0, dt_s=600.0)
    cell_do = out["cells"][0]["do_mg_l"]
    assert min(sat, 9.0) <= cell_do <= max(sat, 9.0)


def test_describe_model_has_sources_and_thresholds():
    doc = describe_model()
    assert doc["schema"] == "yellowstone.river_oxygen.v1"
    assert "Benson" in doc["sources"]["saturation"]
    assert doc["parameters"]["salmonid_growth_min_mg_l"] == 6.5


def test_score_against_observations_computes_rmse():
    scores = score_against_observations([5.0, 7.0, 9.0], [6.0, 7.0, 10.0])
    assert math.isfinite(scores["rmse_mg_l"])
    assert scores["bias_mg_l"] == pytest.approx(-2.0 / 3.0)
    with pytest.raises(ValueError):
        score_against_observations([1.0], [1.0, 2.0])


def test_advection_pass_runs_chain():
    cells = [
        OxygenCell(id=f"c{i}", length_m=50.0, width_m=20.0, depth_m=1.0,
                   velocity_m_s=0.5, temp_c=15.0, do_mg_l=7.0)
        for i in range(5)
    ]
    result = advect_cells(cells, upstream_do_mg_l=9.0, dt_s=60.0)
    rows = result["cells"]
    assert len(rows) == 5
    assert all(math.isfinite(r["do_mg_l"]) for r in rows)
    assert result["method"].startswith("implicit_upwind")
    assert result["max_advective_courant"] <= 1.0
