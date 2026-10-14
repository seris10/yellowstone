"""Persistent foodweb stepping and movement-cost tests."""
import pytest

from yellowstone_python.aquatic.aquatic_foodweb import foodweb_state, run_foodweb, step_foodweb


def landscape():
    return [{'id': 'a', 's_m': 0., 'temperature_c': 17., 'velocity_m_s': .3, 'depth_m': 1.1},
            {'id': 'b', 's_m': 1000., 'temperature_c': 19., 'velocity_m_s': .3, 'depth_m': 1.1}]


def test_online_steps_equal_fourteen_day_run():
    cells = landscape()
    state = foodweb_state(cells)
    for _ in range(14):
        report = step_foodweb(state, cells, 1.)
    offline = run_foodweb(cells, days=14.)
    for key, value in report['trout'].items():
        assert offline['trout'][key] == value
    assert {key: round(value, 6) for key, value in state['totals'].items()} == offline['prey_totals']
    assert state['simulated_days'] == 14.
    assert state['steps'] == offline['steps']


def test_switch_gain_and_distance_cost_hold_then_move_to_cold_refuge():
    cells = landscape()
    state = foodweb_state(cells)
    settings = {'delta_u_switch': .1, 'movement_cost_per_m': .00001}
    step_foodweb(state, cells, .01, settings)
    first = state['chosen_cell_id']
    for _ in range(5):
        step_foodweb(state, cells, .01, settings)
        assert state['chosen_cell_id'] == first
    cells[0]['temperature_c'] = 28.
    cells[1]['temperature_c'] = 14.
    step_foodweb(state, cells, .01, settings)
    assert state['chosen_cell_id'] == 'b'
    step_foodweb(state, cells, .01, settings)
    assert state['chosen_cell_id'] == 'b'
