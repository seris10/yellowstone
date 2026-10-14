"""Tests for hydraulic identifiability diagnostics and surface spread."""
import importlib.util
import pytest

from yellowstone_python.river.identifiability import DEPENDENCE_POLICY, PARAM_NAMES, conditioning, jacobian_at_truth, multistart_fit, residual_against_truth, run_diagnostics, structural_surface_spread

HAS_SALIB = importlib.util.find_spec("SALib") is not None


def test_identifiability_residual_zero_at_truth():
    truth = {"manning_n": 0.035, "bank_slope_zh": 1.5,
             "depth_m": 1.1}
    residuals = residual_against_truth(
        [truth[name] for name in PARAM_NAMES])
    assert len(residuals) == 3
    for value in residuals:
        assert value == pytest.approx(0.0, abs=0.5 * 10 ** -(12), rel=0)


def test_identifiability_jacobian_is_rank_deficient():
    report = conditioning(jacobian_at_truth())
    assert report['rank'] < report['n_params']
    assert report['param_names'] == list(PARAM_NAMES)
    assert len(report['null_directions']) == report['n_params'] - report['rank']


def test_identifiability_multistart_fits_spread_along_ridge():
    report = multistart_fit()
    assert report['max_cost'] < 1e-12
    assert (all((run['success'] for run in report['runs'])))
    assert max(report['relative_spread'].values()) > 0.2


def test_identifiability_structural_spread_closes_budgets():
    report = structural_surface_spread()
    assert (report['budgets_ok'])
    assert report['max_abs_gap_c'] > 0.005
    assert report['max_abs_gap_c'] < 0.3
    assert 'not_prediction_interval' in report['status']


def test_identifiability_dependence_policy_names_gate():
    assert 'manning_n' in DEPENDENCE_POLICY['varied_independently']
    assert 'salib_gate' in DEPENDENCE_POLICY


def test_identifiability_full_document():
    document = run_diagnostics()
    assert document['schema'] == 'yellowstone.identifiability.v1'
    assert 'conditioning' in document
    assert 'multistart' in document
    assert 'structural_surface' in document


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_SALIB, reason="SALib not installed")
def test_identifiability_sobol_screen_runs_on_ratio_residual():
    from yellowstone_python.river.identifiability import sobol_screen
    report = sobol_screen(n_base=64, seed=11)
    assert report['param_names'] == list(PARAM_NAMES)
    assert report['n_eval'] == 64 * (2 * len(PARAM_NAMES) + 2)
    for key in ("S1", "ST", "S1_conf", "ST_conf"):
        assert len(report[key]) == len(PARAM_NAMES)
        for value in report[key]:
            assert (value == value)
    assert report['ST'][2] > report['ST'][1]
    assert report['ST'][2] > 0.3



