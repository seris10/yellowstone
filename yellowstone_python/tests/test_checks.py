"""Numeric input rejection and inclusive bounds."""
import pytest

from yellowstone_python.common.checks import finite, fraction, nonnegative, positive, positive_int


@pytest.mark.parametrize("value", [True, False, None, "2", "", float("nan"), float("inf"), -float("inf")])
def test_finite_rejects_non_numeric_and_nonfinite(value):
    with pytest.raises(ValueError, match="sample must be"):
        finite("sample", value)


def test_inclusive_bounds():
    assert finite("sample", 2, minimum=2, maximum=2) == 2.0
    with pytest.raises(ValueError):
        finite("sample", 3, maximum=2)
    with pytest.raises(ValueError):
        finite("sample", 1, minimum=2)
    assert fraction("share", 0) == 0
    assert nonnegative("amount", 0) == 0
    assert positive("amount", 1) == 1
    for validator in (positive, positive_int):
        with pytest.raises(ValueError):
            validator("amount", 0)
    with pytest.raises(ValueError):
        positive_int("count", 1.0)

