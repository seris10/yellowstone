import pytest

from yellowstone_python.common.units import (UnitError, gpm_to_m3s, label_index,
                                             m3s_to_gpm, require_fraction)


def test_excelsior_reference():
    # NPS >4000 gpm ≈ 0.252 m3/s order-of-magnitude; code uses 0.26 illustrative.
    assert abs(gpm_to_m3s(4000) - 0.2523608) < 1e-6
    assert abs(m3s_to_gpm(0.26) - 4121.3) < 1.0


def test_mismatch_raises():
    with pytest.raises(UnitError):
        gpm_to_m3s(-1)
    with pytest.raises(UnitError):
        require_fraction("x", 1.5)
    idx = label_index("biomass", 0.8)
    assert idx["units"] == "dimensionless_index_0_1"
