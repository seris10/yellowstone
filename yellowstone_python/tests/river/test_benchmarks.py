"""Tests for the applicable numerics benchmarks (synthetic, offline)."""
from __future__ import annotations

import pytest

from yellowstone_python.river.benchmarks import NOT_APPLICABLE, benchmark_closed_thermal, benchmark_conservative_tracer, benchmark_diffusive_decay, benchmark_mms_traveling_wave, benchmark_restart_equivalence, benchmark_spatial_convergence, benchmark_spatial_convergence_dispersive, benchmark_temporal_convergence, benchmark_two_stream_mixing, run_all_benchmarks


def test_benchmark_restart_equivalence():
    result = benchmark_restart_equivalence()
    assert (result['passed'])
    assert result['split_run_gap_c'] <= 1e-09
    assert result['fresh_object_gap_c'] <= 1e-09


def test_benchmark_closed_thermal():
    result = benchmark_closed_thermal()
    assert (result['passed'])
    assert result['drift_c'] <= 1e-09


def test_benchmark_two_stream_mixing():
    result = benchmark_two_stream_mixing()
    assert (result['passed'])
    assert result['steady_c'] == pytest.approx(result['expected_c'], abs=0.5 * 10 ** -(9), rel=0)


def test_benchmark_conservative_tracer():
    result = benchmark_conservative_tracer()
    assert (result['passed'])
    assert abs(result['advection_error_pct']) < 5.0
    assert result['heat_relative_residual'] <= 1e-09


def test_benchmark_momentum_benchmarks_recorded_not_run():
    names = [e["benchmark"] for e in NOT_APPLICABLE]
    assert 'lake_at_rest_over_variable_bed' in names
    assert 'dam_break_transient' in names
    for entry in NOT_APPLICABLE:
        assert 'momentum' in entry['reason']


def test_benchmark_suite_passes():
    document = run_all_benchmarks()
    assert document['schema'] == 'yellowstone.numerics_benchmarks.v1'
    assert (document['passed'])
    assert len(document['results']) == 9


def test_benchmark_convergence_rates_are_first_order():
    for fn in (benchmark_temporal_convergence,
               benchmark_spatial_convergence):
        result = fn()
        assert (result['passed'])
        assert len(result['errors_c']) == 3
        for rate in result["observed_rates"]:
            assert rate >= 0.7
            assert rate <= 1.3


def test_benchmark_dispersive_steady_rates_are_first_order():
    result = benchmark_spatial_convergence_dispersive()
    assert (result['passed'])
    assert len(result['cases']) == 2
    for case in result["cases"]:
        assert len(case['errors_c']) == 3
        for rate in case["observed_rates"]:
            assert rate >= 0.7
            assert rate <= 1.3


def test_benchmark_diffusive_decay_orders():
    result = benchmark_diffusive_decay()
    assert (result['passed'])
    assert len(result['spatial_errors_c']) == 3
    for rate in result["spatial_rates"]:
        assert rate >= 1.5
        assert rate <= 2.5
    assert len(result['temporal_errors_c']) == 3
    for rate in result["temporal_rates"]:
        assert rate >= 0.7
        assert rate <= 1.3


def test_benchmark_mms_wave_rates_are_first_order():
    result = benchmark_mms_traveling_wave()
    assert (result['passed'])
    assert len(result['spatial_errors_c']) == 3
    for rate in result["spatial_rates"]:
        assert rate >= 0.7
        assert rate <= 1.3
    assert len(result['temporal_errors_c']) == 3
    for rate in result["temporal_rates"]:
        assert rate >= 0.7
        assert rate <= 1.3
    assert result['heat_relative_residual'] <= 1e-09



