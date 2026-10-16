"""Scheduled controls, checkpoint restoration and vector surface flux tests."""
import math

import numpy as np
import pytest

from yellowstone_python.river.river_transport import Cell, River, Series, Source
from yellowstone_python.river.surface_flux import BudgetParams, MetState, flux_array, flux_at, linearized_array, linearized
from yellowstone_python.river.calibrate import effective_sample_size


def river(**kwargs):
    return River([Cell('a', 20., 10., 200., 15.), Cell('b', 20., 10., 200., 15.)],
                 kwargs.pop('boundary_m3_s', 5.), kwargs.pop('boundary_c', 15.), **kwargs)


def test_scheduled_control_matches_constructed_schedule():
    control = river()
    control.run(20., dt_s=1., sample_s=10.)
    control.set_forcing('boundary_c', 20., 23.)
    control.run(60., dt_s=1., sample_s=10.)
    scheduled = river(boundary_c={'times_s': [0., 20.], 'values': [15., 23.]})
    scheduled.run(80., dt_s=1., sample_s=10.)
    assert control.temperature_c == scheduled.temperature_c
    assert control.budget() == scheduled.budget()
    with pytest.raises(ValueError, match='forcing change time'):
        control.set_forcing('boundary_c', 79., 25.)


def test_lateral_schedule_closes_water_budget():
    model = river(sources=[Source('spring', 'a', {'times_s': [0., 10., 20.], 'values': [0., 1., 0.]}, 60.)])
    model.run(30., dt_s=2., sample_s=10.)
    assert model.budget()['lateral_input_m3'] == 10.
    assert model.budget()['water_residual_m3'] == pytest.approx(0., abs=1e-12)
    assert model.budget()['heat_relative_residual'] < 1e-9


def test_restore_preserves_state_forcing_and_compensated_budget():
    model = river(sources=[Source('spring', 'a', .2, 60.)])
    model.run(20., dt_s=2., sample_s=10.)
    checkpoint = model.checkpoint()
    model.run(60., dt_s=2., sample_s=10.)
    final = model.checkpoint()
    model.restore(checkpoint)
    model.run(60., dt_s=2., sample_s=10.)
    assert model.checkpoint() == final
    model.restore(checkpoint)
    model.set_forcing('source.spring.flow_m3_s', 20., 0.)
    model.restore(checkpoint)
    assert model.sources[0].flow_m3_s.at(30.) == .2


@pytest.mark.parametrize('water', [[-20., 0., 10., 25., 70.], [79., 80., 85., 90.]])
@pytest.mark.parametrize('met', [MetState(7., .5, 2., 700., .1), MetState(20., .9, 0., 0., .9)])
def test_vector_flux_matches_scalar_reference(water, met):
    vector = flux_array(water, met)
    net, slope = linearized_array(water, met)
    for i, temperature in enumerate(water):
        scalar = flux_at(temperature, met)
        for key, value in scalar.items():
            assert vector[key][i] == pytest.approx(value, rel=1e-14, abs=1e-12)
        expected_net, expected_slope = linearized(temperature, met)
        assert net[i] == pytest.approx(expected_net, abs=1e-12)
        assert slope[i] == pytest.approx(expected_slope, abs=1e-12)


def test_effective_sample_size_reflects_autocorrelation():
    rng = np.random.default_rng(32)
    white = rng.normal(size=30000)
    assert effective_sample_size(white)['n_eff'] == pytest.approx(len(white), rel=.05)
    correlated = np.empty_like(white)
    correlated[0] = white[0]
    for i in range(1, len(white)):
        correlated[i] = .9 * correlated[i - 1] + white[i]
    assert effective_sample_size(correlated)['n_eff'] == pytest.approx(len(white) / 19., rel=.1)


@pytest.mark.parametrize('hot_source', [24., 85.])
def test_optimized_transport_matches_scalar_matrix_and_flux(hot_source):
    from yellowstone_python.river.river_transport import river_from_config
    config = {'cells': [{'id': f'c{i}', 'length_m': 18. + i, 'width_m': 5. + i / 10.,
        'volume_m3': (18. + i) * (5. + i / 10.) * .8, 'initial_c': 12. + i / 2.,
        'dispersion_m2_s': .4} for i in range(12)],
        'boundary_m3_s': {'times_s': [0., 36., 74.], 'values': [3., 1.8, 4.]},
        'boundary_c': {'times_s': [0., 50.], 'values': [12., 22.]}, 'air_c': 7.,
        'surface_budget': {'rh': .55, 'wind_mps': 2.4, 'shortwave_w_m2': 650., 'cloud': .2},
        'sources': [{'id': 'spring', 'cell_id': 'c4', 'flow_m3_s': .4, 'temperature_c': hot_source}],
        'hyporheic_zones': {'c7': {'storage_volume_m3': 28., 'alpha_per_s': .001}},
        'surface_relaxation': 1.}
    optimized = river_from_config(config)
    scalar = river_from_config(config)
    scalar._vector_surface = False
    optimized_frames = optimized.run(180., dt_s=2., sample_s=10.)
    scalar_frames = scalar.run(180., dt_s=2., sample_s=10.)
    assert len(optimized_frames) == len(scalar_frames)
    for actual, reference in zip(optimized_frames, scalar_frames):
        assert actual['temperature_c'] == pytest.approx(reference['temperature_c'], abs=1e-10)
    assert optimized.budget()['heat_relative_residual'] < 1e-9
    assert scalar.budget()['heat_relative_residual'] < 1e-9
    for key in ('boundary_input_j', 'lateral_input_j', 'outlet_export_j', 'surface_exchange_j'):
        assert optimized.budget()[key] == pytest.approx(scalar.budget()[key], rel=1e-12, abs=1e-5)


@pytest.mark.parametrize('n', [True, False, '100', float('nan'), float('inf'), 0, -1])
def test_information_criteria_reject_invalid_sample_count(n):
    from yellowstone_python.river.calibrate import aic_bic
    with pytest.raises(ValueError):
        aic_bic(10., n, 2)


@pytest.mark.parametrize('k', [True, False, '2', 0.0, 1.5, -1, None])
def test_information_criteria_reject_noninteger_parameter_count(k):
    from yellowstone_python.river.calibrate import aic_bic
    with pytest.raises(ValueError):
        aic_bic(10., 100., k)


def test_information_criteria_accept_fractional_effective_sample_size_and_zero_parameters():
    from yellowstone_python.river.calibrate import aic_bic
    result = aic_bic(10., 7.25, np.int64(0))
    assert result['n'] == 7.25
    assert result['k'] == 0.
    assert result['aic'] == 7.25 * math.log(10. / 7.25)
    assert result['bic'] == result['aic']
