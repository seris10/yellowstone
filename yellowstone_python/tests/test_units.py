import warnings

import pytest

from yellowstone_python.common.units import (M3S_PER_US_GPM, UnitError, c_to_k,
                                             gpm_to_m3s, label_index,
                                             m3s_to_gpm, m3s_to_us_gpm,
                                             require_fraction, us_gpm_to_m3s)


def test_excelsior_reference():
    assert abs(us_gpm_to_m3s(4000) - 0.2523608) < 1e-6
    assert abs(m3s_to_us_gpm(0.26) - 4121.3) < 1.0


def test_mismatch_raises():
    with pytest.raises(UnitError):
        us_gpm_to_m3s(-1)
    with pytest.raises(UnitError):
        require_fraction("x", 1.5)
    idx = label_index("biomass", 0.8)
    assert idx["units"] == "dimensionless_index_0_1"


def test_us_gpm_matches_nist_exact():
    assert abs(us_gpm_to_m3s(1.0) - 3.785411784e-3 / 60.0) < 1e-18
    assert M3S_PER_US_GPM == 3.785411784e-3 / 60.0


def test_c_below_absolute_zero_rejected():
    assert c_to_k(0.0) == 273.15
    with pytest.raises(UnitError):
        c_to_k(-273.16)
    with pytest.raises(UnitError):
        c_to_k(-500.0)


def test_deprecated_aliases_warn_and_match():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        v = gpm_to_m3s(1.0)
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    assert abs(v - us_gpm_to_m3s(1.0)) < 1e-18
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        v = m3s_to_gpm(1.0)
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    assert abs(v - m3s_to_us_gpm(1.0)) < 1e-12
