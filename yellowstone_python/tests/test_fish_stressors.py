"""Fish suitability stressor hooks: arsenic and boron, dissolved oxygen, piscivore predation."""
from __future__ import annotations

import math

import pytest

from yellowstone_python.aquatic.fish import predation_survival_factor, suitability, suitability_with_stressors, thermal_performance


_FAVOURABLE = {
    "food": 1.0,
    "cover": 1.0,
    "velocity": 0.35,
    "depth": 1.2,
    "weights": {"wf": 0.6, "wc": 0.3, "wt": 0.05, "wv": 0.025, "wd": 0.025},
    "species": "brown_trout",
    "refuge_weight": 0.0,
}


def _base_u(t_c: float) -> float:
    return suitability(t_c=t_c, **_FAVOURABLE)


def test_defaults_reproduce_existing_suitability():
    """Omitting the stressor kwargs leaves ranking unchanged."""
    for t in (10.0, 14.0, 18.0, 22.0):
        base = _base_u(t)
        with_none = suitability(t_c=t,
                                solute_multiplier=None,
                                do_multiplier=None,
                                predation_multiplier=None,
                                **_FAVOURABLE)
        assert base == pytest.approx(with_none)


def test_solute_multiplier_lowers_suitability_monotonically():
    """Shrinking the solute factor from 1.0 toward 0 decreases U at a fixed temperature."""
    t = 14.0
    base = _base_u(t)
    half = suitability(t_c=t, solute_multiplier=0.5, **_FAVOURABLE)
    zero = suitability(t_c=t, solute_multiplier=0.0, **_FAVOURABLE)
    assert zero < half < base
    assert zero == pytest.approx(0.0, abs=1e-12)


def test_do_multiplier_lowers_suitability_monotonically():
    """Shrinking the DO factor from 1.0 toward 0 decreases U at a fixed temperature."""
    t = 14.0
    base = _base_u(t)
    half = suitability(t_c=t, do_multiplier=0.5, **_FAVOURABLE)
    zero = suitability(t_c=t, do_multiplier=0.0, **_FAVOURABLE)
    assert zero < half < base


def test_predation_multiplier_lowers_suitability_monotonically():
    """Lower predation survival factor decreases U at a fixed temperature."""
    t = 14.0
    base = _base_u(t)
    half = suitability(t_c=t, predation_multiplier=0.5, **_FAVOURABLE)
    low = suitability(t_c=t, predation_multiplier=0.1, **_FAVOURABLE)
    assert low < half < base


def test_each_stressor_independent_of_temperature():
    """A fixed stressor factor acts as the same multiplier on positive thermal rankings."""
    factor = 0.4
    for t in (10.0, 14.0, 18.0):
        base = _base_u(t)
        adj = suitability(t_c=t, solute_multiplier=factor, **_FAVOURABLE)
        assert adj == pytest.approx(base * factor, rel=1e-9, abs=1e-9)


def test_combined_stressors_multiply_as_separate_factors():
    """Combined factor equals the product of per-stressor factors."""
    t = 14.0
    report = suitability_with_stressors(
        t_c=t, solute_multiplier=0.6, do_multiplier=0.5,
        predation_multiplier=0.8, **_FAVOURABLE)
    assert report["solute_factor"] == pytest.approx(0.6)
    assert report["do_factor"] == pytest.approx(0.5)
    assert report["predation_factor"] == pytest.approx(0.8)
    assert report["combined_stressor_factor"] == pytest.approx(
        0.6 * 0.5 * 0.8)
    assert report["U"] == pytest.approx(
        report["thermal_only"] * 0.6 * 0.5 * 0.8, rel=1e-9, abs=1e-9)


def test_predation_survival_factor_monotonic_in_rate():
    """exp(-rate*days) decreases in rate and in days; rate=0 or days=0 returns 1."""
    assert predation_survival_factor(0.0, days=1.0) == pytest.approx(1.0)
    assert predation_survival_factor(0.1, days=0.0) == pytest.approx(1.0)
    s0 = predation_survival_factor(0.0, days=5.0)
    s_low = predation_survival_factor(0.01, days=5.0)
    s_high = predation_survival_factor(0.3, days=5.0)
    assert s_high < s_low < s0
    assert s_high == pytest.approx(math.exp(-0.3 * 5.0))


def test_thermal_only_still_matches_old_suitability():
    """thermal_only in the stressors report equals the no-stressor suitability."""
    for t in (10.0, 14.0, 18.0):
        base = _base_u(t)
        report = suitability_with_stressors(t_c=t, **_FAVOURABLE)
        assert report["thermal_only"] == pytest.approx(base)
        assert report["U"] == pytest.approx(base)
        assert report["combined_stressor_factor"] == pytest.approx(1.0)


def test_negative_thermal_only_not_raised_by_small_multiplier():
    """A negative thermal ranking (poor habitat) must not improve when multiplied by a factor less than 1."""
    hostile = {
        "food": 0.0, "cover": 0.0,
        "velocity": 1.0, "depth": 0.1,
        "weights": {"wf": 0.1, "wc": 0.1, "wt": 0.4, "wv": 0.3, "wd": 0.1},
        "species": "brown_trout", "refuge_weight": 0.6,
    }
    # 26 C triggers the refuge drive and feed-zero to drag thermal ranking down.
    base = suitability(t_c=26.0, **hostile)
    stressed = suitability(t_c=26.0, solute_multiplier=0.1, **hostile)
    assert stressed <= base


def test_stressor_factors_clamped_to_unit_interval():
    """Factor inputs outside [0, 1] are clamped before applying."""
    t = 14.0
    base = _base_u(t)
    high = suitability(t_c=t, solute_multiplier=5.0, **_FAVOURABLE)
    low = suitability(t_c=t, solute_multiplier=-0.5, **_FAVOURABLE)
    assert high == pytest.approx(base)
    assert low == pytest.approx(0.0, abs=1e-12)


def test_thermal_performance_unchanged_by_stressor_terms():
    """The temperature path is independent of the stressor path."""
    for t in (10.0, 18.0, 24.0):
        perf = thermal_performance(t, "brown_trout")
        assert "feeding" in perf and "stress" in perf
