
import pytest
import copy
import json

from yellowstone_python.river.reach_reference import (derive_flows, mixing_check,
                                              run_simulation, stable_dt,
                                              steady_state, step_heat)



def _reaches():
    return json.load(open(BASE))["river_reaches"]


def test_mixing_check():
    assert abs(mixing_check(8.0, 17.5, 0.26, 62.0) - 18.9) < 0.1


def test_conservation_and_stability():
    r = _reaches()
    s, led = run_simulation(r, 8.0, 17.5, air_c=18.0, seconds=600.0)
    assert led["heat_budget_error_j"] < 1e-6, led
    assert led["water_budget_error_m3"] < 1e-6, led


def test_low_high_flow_stable():
    r = _reaches()
    for q in (2.0, 20.0):
        rr = copy.deepcopy(r)
        s, led = run_simulation(rr, q, 17.5, air_c=18.0, seconds=120.0)
        assert led["heat_budget_error_j"] < 1e-6
        assert all(0.0 <= x["fish_activity"] <= 1.0 for x in s)


def test_excelsior_warms_mid_chain():
    r = _reaches()
    s, _ = run_simulation(r, 8.0, 17.5, air_c=18.0, seconds=600.0)
    up = next(x for x in s if x["id"] == "upstream_midway")["temperature_c"]
    mix = next(x for x in s if x["id"] == "excelsior_mixing")["temperature_c"]
    assert mix > up  # thermal lateral must warm the mixing reach


def test_steady_state_regression():
    # Long runs must land on the exact analytical fixed point T*.
    r = _reaches()
    target = steady_state(r, 8.0, 17.5, air_c=18.0)
    s, _ = run_simulation(r, 8.0, 17.5, air_c=18.0, seconds=86400.0 * 10)
    for got, want, reach in zip([x["temperature_c"] for x in s], target,
                                [x["id"] for x in s]):
        assert abs(got - want) < 0.02, (reach, got, want)


def test_timestep_convergence():
    # Halving dt must not move the 1 h answer (linear model, stable substeps).
    r = _reaches()
    a, _ = run_simulation(r, 8.0, 17.5, air_c=18.0, seconds=3600.0, dt=1.0)
    b, _ = run_simulation(r, 8.0, 17.5, air_c=18.0, seconds=3600.0, dt=0.25)
    for x, y in zip(a, b):
        assert abs(x["temperature_c"] - y["temperature_c"]) < 1e-4  # 1st-order Euler


def test_full_run_budget_closes():
    r = _reaches()
    _, led = run_simulation(r, 8.0, 17.5, air_c=18.0, seconds=3600.0)
    assert led["closure_residual"] < 1e-6
    assert led["boundary_in"] > 0 and led["lateral_in"] > 0
    assert led["steps"] == 3600


def test_zero_duration_is_defined():
    r = _reaches()
    s, led = run_simulation(r, 8.0, 17.5, air_c=18.0, seconds=0.0)
    assert led["steps"] == 0 and led["closure_residual"] == 0.0
    assert [x["temperature_c"] for x in s] == [x["temperature_c"] for x in r]


def test_invalid_inputs_rejected():
    import pytest
    r = _reaches()
    with pytest.raises(ValueError):
        run_simulation(r, 0.0, 17.5, air_c=18.0, seconds=10.0)
    with pytest.raises(ValueError):
        run_simulation(r, 8.0, 17.5, air_c=18.0, seconds=10.0, dt=0.0)

pytestmark = pytest.mark.needs_world


@pytest.fixture(autouse=True)
def resolved_module_paths(monkeypatch, request, resolved_paths):
    """Provide path aliases from shared fixtures and restore them after each test."""
    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, 'BASE', resolved_paths['ECO_LIVE'], raising=False)
