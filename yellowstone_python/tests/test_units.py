import pytest

from yellowstone_python.common.units import (M3S_PER_US_GPM, UnitError, c_to_k,
                                             k_to_c, label_index,
                                             m3s_to_us_gpm,
                                             require_fraction, us_gpm_to_m3s)


def test_excelsior_reference():
    assert abs(us_gpm_to_m3s(4000) - 0.2523608) < 1e-6
    assert abs(m3s_to_us_gpm(0.26) - 4121.3) < 1.0


def test_mismatch_raises():
    with pytest.raises(UnitError):
        us_gpm_to_m3s(-1)
    with pytest.raises(ValueError):
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


def test_flow_converters_round_trip():
    assert m3s_to_us_gpm(us_gpm_to_m3s(1.0)) == pytest.approx(1.0)


@pytest.mark.parametrize("converter", [c_to_k, k_to_c, us_gpm_to_m3s, m3s_to_us_gpm])
@pytest.mark.parametrize("value", [True, False, "1.0", float("nan"), float("inf"), None])
def test_converters_reject_coercible_and_nonfinite_inputs(converter, value):
    with pytest.raises(UnitError):
        converter(value)


@pytest.mark.parametrize("converter", [c_to_k, k_to_c, us_gpm_to_m3s, m3s_to_us_gpm])
def test_converters_accept_numpy_real_scalars(converter):
    import numpy as np
    assert converter(np.float64(1.0)) == pytest.approx(converter(1.0))
