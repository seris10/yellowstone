"""Tests for yellowstone_python.validation.contracts heat ledger and assert_finite."""
from __future__ import annotations

import decimal
import math
import warnings

import pytest

from yellowstone_python.validation.contracts import (assert_finite,
                                                check_heat_ledger)


def test_check_heat_ledger_canonical_key_passes():
    out = check_heat_ledger(
        {"heat_budget_error_j": 0.0, "water_budget_error_m3": 0.0})
    assert out == []


def test_check_heat_ledger_missing_canonical_fails():
    out = check_heat_ledger({"water_budget_error_m3": 0.0})
    assert out and "heat_budget_error_j" in out[0]


def test_check_heat_ledger_accepts_deprecated_with_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = check_heat_ledger(
            {"heat_budget_error": 0.0, "water_budget_error_m3": 0.0})
    assert out == []
    assert any(issubclass(w.category, DeprecationWarning)
               and "heat_budget_error" in str(w.message)
               for w in caught)


def test_check_heat_ledger_drift_between_keys_is_failure():
    out = check_heat_ledger(
        {"heat_budget_error_j": 0.0, "heat_budget_error": 1.0,
         "water_budget_error_m3": 0.0},
        heat_tol_j=1e-9, water_tol_m3=1e-9)
    assert any("disagree" in failure for failure in out)


def test_check_heat_ledger_separate_tolerances():
    out = check_heat_ledger(
        {"heat_budget_error_j": 1e-4, "water_budget_error_m3": 1e-8},
        heat_tol_j=1e-9, water_tol_m3=1e-7)
    assert any("heat residual" in failure for failure in out)
    assert all("water residual" not in failure for failure in out)


def test_check_heat_ledger_legacy_tol_kwarg_sets_both():
    out = check_heat_ledger(
        {"heat_budget_error_j": 0.0, "water_budget_error_m3": 0.0},
        tol=1e-12)
    assert out == []


def test_assert_finite_rejects_nonfloat_nan():
    import ctypes
    try:
        import numpy as np
    except ImportError:
        np = None
    with pytest.raises(ValueError):
        assert_finite("x", float("nan"))
    with pytest.raises(ValueError):
        assert_finite("x", float("inf"))
    with pytest.raises(ValueError):
        assert_finite("x", "nan")
    with pytest.raises(ValueError):
        assert_finite("x", decimal.Decimal("NaN"))
    with pytest.raises(ValueError):
        assert_finite("x", None)
    with pytest.raises(ValueError):
        assert_finite("x", "not-numeric")
    if np is not None:
        with pytest.raises(ValueError):
            assert_finite("x", np.float32("nan"))
    _ = ctypes


def test_assert_finite_returns_python_float():
    value = assert_finite("x", 1)
    assert isinstance(value, float)
    assert value == 1.0
    import numpy as np
    value = assert_finite("x", np.float64(2.5))
    assert isinstance(value, float)
    assert value == 2.5
    assert math.isfinite(value)


@pytest.mark.parametrize("value", ["2.5", True, False])
def test_assert_finite_rejects_strings_and_booleans(value):
    with pytest.raises(ValueError, match="must be numeric"):
        assert_finite("x", value)
