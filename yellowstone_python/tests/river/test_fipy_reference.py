"""FiPy reference solve against analytic and hand-rolled errors."""
from __future__ import annotations

import pytest

from yellowstone_python.river.fipy_reference import HAS_FIPY, LENGTH_M, SYNTHETIC_DISPERSION_M2_S, T0_C, analytic_temperature_c, hand_rolled_error_c, mms_analytic_temperature_c, run_convergence, run_dispersion_convergence, run_mms_convergence, solve_mms, solve_steady, solve_steady_dispersion


def test_analytic_profile_upstream_value_and_downstream_decay():
    assert analytic_temperature_c(0.0) == pytest.approx(20.0, abs=0.5 * 10 ** -(7), rel=0)
    assert analytic_temperature_c(3000.0) == pytest.approx(12.3256, abs=0.5 * 10 ** -(3), rel=0)


def test_analytic_profile_hand_rolled_error_refines():
    assert hand_rolled_error_c(30) < hand_rolled_error_c(15)



@pytest.mark.needs_fipy
@pytest.mark.skipif(HAS_FIPY, reason='fipy installed')
def test_missing_fipy_solve_raises_guided_error():
    with pytest.raises(ImportError):
        solve_steady(15)



@pytest.mark.needs_fipy
@pytest.mark.skipif(not HAS_FIPY, reason='fipy not installed')
def test_fipy_reference_outlet_matches_analytic():
    result = solve_steady(30)
    assert result['max_abs_error_c'] < 0.5
    assert result['outlet_c'] == pytest.approx(result['analytic_outlet_c'], abs=0.05, rel=0)
    assert 'fipy_version' in result
    assert result['parameters']['discharge_m3_s'] == 2.0


@pytest.mark.needs_fipy
@pytest.mark.skipif(not HAS_FIPY, reason='fipy not installed')
def test_fipy_reference_error_within_hand_rolled_error():
    for n in (15, 30):
        # Same upwind operator; slack covers assembly roundoff.
        assert solve_steady(n)['max_abs_error_c'] <= hand_rolled_error_c(n) + 1e-09


@pytest.mark.needs_fipy
@pytest.mark.skipif(not HAS_FIPY, reason='fipy not installed')
def test_fipy_reference_observed_rate_is_first_order():
    report = run_convergence((15, 30))
    (rate,) = report["observed_rates"]
    assert rate >= 0.7
    assert rate <= 1.3



def test_reference_m_m_s_mms_boundary_matches_the_profile():
    assert mms_analytic_temperature_c(0.0) == pytest.approx(T0_C, abs=0.5 * 10 ** -(10), rel=0)


def test_reference_m_m_s_mms_outflow_gradient_is_zero():
    # Centered finite-difference check that dT/dx(L) is numerically zero.
    epsilon = 1e-3
    slope = (
        mms_analytic_temperature_c(LENGTH_M)
        - mms_analytic_temperature_c(LENGTH_M - epsilon)
    ) / epsilon
    assert abs(slope) < 0.01


def test_reference_m_m_s_mms_profile_decreases_through_the_midpoint():
    assert mms_analytic_temperature_c(0.0) > mms_analytic_temperature_c(LENGTH_M / 2.0)


def test_reference_m_m_s_solver_recovers_mms_profile_at_moderate_resolution():
    result = solve_mms(120)
    assert result['max_abs_error_c'] < 2.5
    assert result['n_cells'] == 120
    assert len(result['temperatures_c']) == 120
    # Upstream cell center sits near x=dx/2, still close to T0.
    assert result['temperatures_c'][0] == pytest.approx(mms_analytic_temperature_c(result['dx_m'] / 2.0), abs=1.0, rel=0)


def test_reference_m_m_s_mms_error_refines_with_resolution():
    coarse = solve_mms(60)["max_abs_error_c"]
    fine = solve_mms(240)["max_abs_error_c"]
    assert fine < coarse


def test_reference_m_m_s_mms_convergence_observed_rate_is_positive():
    report = run_mms_convergence((60, 240))
    (rate,) = report["observed_rates"]
    # First-order upwind converges on a smooth MMS source; the rate bound requires positive convergence.
    assert rate > 0.4
    assert rate <= 2.5



@pytest.mark.needs_fipy
@pytest.mark.skipif(not HAS_FIPY, reason='fipy not installed')
def test_reference_dispersion_dispersion_run_matches_hand_rolled():
    result = solve_steady_dispersion(60)
    assert result['dispersion_m2_s'] == SYNTHETIC_DISPERSION_M2_S
    assert len(result['temperatures_c']) == 60
    assert result['max_abs_error_vs_hand_c'] < 0.5
    assert 'fipy_version' in result


@pytest.mark.needs_fipy
@pytest.mark.skipif(not HAS_FIPY, reason='fipy not installed')
def test_reference_dispersion_dispersion_smooths_sharp_inlet_decay():
    with_d = solve_steady_dispersion(60)["temperatures_c"]
    without_d = solve_steady(60)["temperatures_c"]
    # Nonzero dispersion mixes the Dirichlet inlet; the upstream cell cools faster.
    assert with_d[0] < without_d[0]


@pytest.mark.needs_fipy
@pytest.mark.skipif(not HAS_FIPY, reason='fipy not installed')
def test_reference_dispersion_dispersion_convergence_refines():
    report = run_dispersion_convergence((30, 60))
    errors = report["fipy_minus_hand_errors_c"]
    assert errors[-1] < errors[0] + 1e-09



