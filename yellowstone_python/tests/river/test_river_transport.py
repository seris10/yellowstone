"""Numerical verification of the river-temperature engine."""
from __future__ import annotations

import math
import pytest

from yellowstone_python.river.river_transport import make_replay
from yellowstone_python.river.river_transport import Cell, River, RHO_CP_J_M3_K, Series, Source, SurfaceBudget, make_replay, river_from_config
from yellowstone_python.river.surface_flux import BudgetParams

def test_river_transport_uniform_temperature_is_preserved():
    cells = [
        Cell(
            id=f"c{i}",
            length_m=20.0 + i,
            width_m=3.0,
            volume_m3=40.0 + 10.0 * i,
            initial_c=20.0,
            dispersion_m2_s=0.8,
            exchange_w_m2_k=15.0,
        )
        for i in range(5)
    ]
    river = River(
        cells,
        boundary_m3_s=2.0,
        boundary_c=20.0,
        air_c=20.0,
        sources=[
            Source("lateral", "c2", 0.3, 20.0),
        ],
    )
    river.run(1000.0, dt_s=13.0, sample_s=1000.0)

    for temperature in river.temperature_c:
        assert temperature == pytest.approx(20.0, abs=0.5 * 10 ** -(10), rel=0)

    assert river.budget()['heat_relative_residual'] < 1e-10


def test_river_transport_one_cell_steady_solution_matches_formula():
    cell = Cell(
        "c", 100.0, 10.0, 100.0, 12.0,
        exchange_w_m2_k=20.0,
    )
    river = River(
        [cell],
        boundary_m3_s=2.0,
        boundary_c=10.0,
        air_c=5.0,
        net_heat_flux_w_m2=100.0,
        sources=[Source("hot", "c", 1.0, 60.0)],
    )

    exchange = (
        cell.exchange_w_m2_k
        * cell.surface_area_m2
        / RHO_CP_J_M3_K
    )
    extra = (
        cell.surface_area_m2 * 100.0 / RHO_CP_J_M3_K
    )
    expected = (
        2.0 * 10.0 + 1.0 * 60.0 + exchange * 5.0 + extra
    ) / (3.0 + exchange)

    assert river.steady_temperatures()[0] == pytest.approx(expected, abs=0.5 * 10 ** -(12), rel=0)


def test_river_transport_cell_heat_closes_budget():
    cells = [
        Cell(f"c{i}", 50.0, 20.0, 50.0 * 20.0 * 1.1, 10.0,
             dispersion_m2_s=1.0, exchange_w_m2_k=12.0)
        for i in range(5)
    ]
    river = River(
        cells,
        boundary_m3_s=2.0,
        boundary_c=15.0,
        air_c=5.0,
        cell_heat_w={"c2": 1000.0},
    )
    river.run(600.0, dt_s=10.0, sample_s=600.0)
    budget = river.budget()
    assert budget['cell_heat_j'] == pytest.approx(600000.0, abs=0.5 * 10 ** -(7), rel=0)
    assert budget['heat_relative_residual'] < 1e-09
    with pytest.raises(ValueError):
        River(
            cells,
            boundary_m3_s=2.0,
            boundary_c=15.0,
            cell_heat_w={"missing": 1.0},
        )


def test_river_transport_time_refinement_improves_one_cell_solution():
    def calculate(dt_s):
        river = River(
            [Cell("c", 10.0, 1.0, 10.0, 10.0)],
            boundary_m3_s=1.0,
            boundary_c=20.0,
        )
        river.run(10.0, dt_s=dt_s, sample_s=10.0)
        return river.temperature_c[0]

    exact = 20.0 - 10.0 * math.exp(-1.0)
    coarse_error = abs(calculate(1.0) - exact)
    fine_error = abs(calculate(0.5) - exact)

    assert fine_error < 0.6 * coarse_error


def test_river_transport_advection_grid_refinement_reduces_front_error():
    def calculate_error(n):
        dx = 1.0 / n
        river = River(
            [
                Cell(f"c{i}", dx, 1.0, dx, 0.0)
                for i in range(n)
            ],
            boundary_m3_s=1.0,
            boundary_c=1.0,
        )
        river.run(
            0.5, dt_s=0.2 * dx, sample_s=0.5
        )

        # Exact plug-flow: a unit front at 1 m/s is at s=0.5 m after 0.5 s.
        return math.fsum(
            dx * abs(
                temperature
                - (1.0 if (i + 0.5) * dx < 0.5 else 0.0)
            )
            for i, temperature in enumerate(river.temperature_c)
        )

    assert calculate_error(80) < calculate_error(40)


def test_river_transport_large_step_does_not_create_temperature_overshoot():
    river = River(
        [
            Cell(
                f"c{i}", 10.0, 2.0, 20.0,
                5.0 if i % 2 == 0 else 30.0,
                dispersion_m2_s=2.0,
                exchange_w_m2_k=10.0,
            )
            for i in range(4)
        ],
        boundary_m3_s=1.0,
        boundary_c=12.0,
        air_c=8.0,
        sources=[Source("hot", "c1", 0.2, 40.0)],
    )
    river.step(100000.0)

    for temperature in river.temperature_c:
        assert temperature >= 5.0 - 1e-10
        assert temperature <= 40.0 + 1e-10


def test_river_transport_closed_dispersion_conserves_energy():
    cells = [
        Cell(
            "a", 10.0, 1.0, 10.0, 10.0,
            dispersion_m2_s=2.0,
        ),
        Cell(
            "b", 30.0, 1.0, 30.0, 30.0,
            dispersion_m2_s=2.0,
        ),
    ]
    river = River(cells, 0.0, 0.0)

    initial = math.fsum(
        cell.volume_m3 * temperature
        for cell, temperature in zip(
            cells, river.temperature_c
        )
    )
    river.step(1000000.0)
    final = math.fsum(
        cell.volume_m3 * temperature
        for cell, temperature in zip(
            cells, river.temperature_c
        )
    )

    assert (math.isclose(initial, final, rel_tol=1e-10))
    assert river.temperature_c[0] > 10.0
    assert river.temperature_c[1] < 30.0


def test_river_transport_prescribed_surface_power_changes_storage():
    cell = Cell("c", 100.0, 2.0, 100.0, 5.0)
    river = River(
        [cell],
        boundary_m3_s=0.0,
        boundary_c=5.0,
        net_heat_flux_w_m2=50.0,
    )
    river.step(10.0)

    expected_j = 50.0 * cell.surface_area_m2 * 10.0
    budget = river.budget()

    # Prescribed heat flux is accounted apart from the surface term.
    assert budget['additional_heat_flux_j'] == pytest.approx(expected_j, abs=0.5 * 10 ** -(6), rel=0)
    assert budget['surface_exchange_j'] == pytest.approx(0.0, abs=0.5 * 10 ** -(6), rel=0)
    assert budget['storage_change_j'] == pytest.approx(expected_j, abs=0.001, rel=0)


def test_river_transport_forcing_changes_are_not_integrated_early():
    river = River(
        [Cell("c", 10.0, 1.0, 10.0, 0.0)],
        boundary_m3_s=1.0,
        boundary_c=Series(
            (0.0, 2.0), (0.0, 10.0)
        ),
    )

    # A direct step cannot straddle the t=2 forcing change.
    with pytest.raises(ValueError):
        river.step(3.0)
    assert river.time_s == 0.0

    river.run(3.0, dt_s=5.0, sample_s=3.0)

    # [0,2] stays at 0 C; [2,3] applies inflow: 10*T_new = 10*0 + 1*(10 - T_new).
    assert river.temperature_c[0] == pytest.approx(10.0 / 11.0, abs=0.5 * 10 ** -(12), rel=0)
    assert river.steps == 2
    assert river.time_s == 3.0


def test_river_transport_run_records_exact_final_time():
    river = River(
        [Cell("c", 10.0, 1.0, 10.0, 10.0)],
        1.0, 10.0,
    )
    frames = river.run(
        25.0, dt_s=7.0, sample_s=10.0
    )
    assert [frame['t_s'] for frame in frames] == [0.0, 10.0, 20.0, 25.0]


def test_river_transport_zero_duration_returns_starting_state():
    river = River(
        [Cell("c", 10.0, 1.0, 10.0, 10.0)],
        1.0, 10.0,
    )
    frames = river.run(0.0)
    assert len(frames) == 1
    assert river.steps == 0


def test_river_transport_repeat_runs_are_deterministic():
    config = {
        "cells": [
            {
                "id": "c",
                "length_m": 10.0,
                "width_m": 2.0,
                "volume_m3": 20.0,
                "initial_c": 12.0,
            }
        ],
        "boundary_m3_s": 1.0,
        "boundary_c": 17.0,
    }
    a = river_from_config(config)
    b = river_from_config(config)

    assert a.run(30.0, 2.0, 10.0) == b.run(30.0, 2.0, 10.0)


def test_river_transport_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        Cell("c", 0.0, 1.0, 10.0, 10.0)

    with pytest.raises(ValueError):
        Series((0.0, 0.0), (10.0, 20.0))

    with pytest.raises(ValueError):
        Source("s", "c", -1.0, 20.0)

    cell = Cell("c", 10.0, 1.0, 10.0, 10.0)

    with pytest.raises(ValueError):
        River([cell, cell], 1.0, 10.0)

    with pytest.raises(ValueError):
        River(
            [cell], 1.0, 10.0,
            sources=[Source("s", "missing", 1.0, 20.0)],
        )

    river = River([cell], 1.0, 10.0)
    with pytest.raises(ValueError):
        river.run(10.0, dt_s=0.0)


def test_river_transport_series_is_right_continuous_at_change_times():
    series = Series((0.0, 10.0, 20.0), (1.0, 2.0, 3.0))
    assert series.at(0.0) == 1.0
    assert series.at(9.999) == 1.0
    # Right-continuous: value at the change time belongs to the new segment.
    assert series.at(10.0) == 2.0
    assert series.at(10.001) == 2.0
    assert series.at(20.0) == 3.0
    # Final value persists past the last change time.
    assert series.at(10000.0) == 3.0


def test_river_transport_closed_unforced_steady_problem_is_not_unique():
    river = River(
        [Cell("c", 10.0, 1.0, 10.0, 10.0)],
        0.0, 10.0,
    )
    with pytest.raises(ArithmeticError):
        river.steady_temperatures()


def _surface_budget_forcing_river( budget):
    return River(
        cells=(Cell(id="c0", length_m=10.0, width_m=2.0,
                    volume_m3=20.0, initial_c=10.0),),
        boundary_m3_s=1.0,
        boundary_c=10.0,
        surface_budget=budget,
    )


def test_surface_budget_forcing_meteorological_change_splits_integration():
    river = _surface_budget_forcing_river({
        "rh": {"times_s": [0.0, 5.0], "values": [0.5, 0.8]},
        "wind_mps": 2.0,
        "shortwave_w_m2": 0.0,
        "cloud": 0.5,
    })
    river.run(duration_s=10.0, dt_s=10.0, sample_s=10.0)
    assert river.time_s == pytest.approx(10.0, abs=0.5 * 10 ** -(7), rel=0)
    assert river.steps == 2


def test_surface_budget_forcing_step_refuses_to_cross_a_meteorological_change():
    river = _surface_budget_forcing_river({
        "rh": 0.5,
        "wind_mps": {"times_s": [0.0, 4.0], "values": [2.0, 6.0]},
        "shortwave_w_m2": 0.0,
        "cloud": 0.5,
    })
    with pytest.raises(ValueError):
        river.step(10.0)
    river.step(4.0)
    assert river.time_s == pytest.approx(4.0, abs=0.5 * 10 ** -(7), rel=0)


def test_surface_budget_forcing_explicit_budget_closes_against_nonlinear_accounting():
    """Accounting uses flux_at(T_converged)."""
    river = _surface_budget_forcing_river({
        "rh": 0.5,
        "wind_mps": 2.0,
        "shortwave_w_m2": 100.0,
        "cloud": 0.2,
    })
    river.run(duration_s=60.0, dt_s=1.0, sample_s=60.0)
    budget = river.budget()
    assert budget['heat_relative_residual'] < river.surface_tolerance_c


def test_surface_budget_forcing_linearization_diagnostic_is_reported():
    river = _surface_budget_forcing_river({
        "rh": 0.5,
        "wind_mps": 2.0,
        "shortwave_w_m2": 900.0,
        "cloud": 0.1,
    })
    river.run(duration_s=600.0, dt_s=120.0, sample_s=600.0)
    budget = river.budget()
    assert budget['max_surface_linearization_error_w'] > 0.0
    assert budget['heat_relative_residual'] < river.surface_tolerance_c


def test_surface_budget_forcing_damped_newton_converges_without_failures():
    river = _surface_budget_forcing_river({
        "rh": 0.5,
        "wind_mps": 2.0,
        "shortwave_w_m2": 300.0,
        "cloud": 0.3,
    })
    river.run(duration_s=120.0, dt_s=60.0, sample_s=120.0)
    budget = river.budget()
    assert budget['max_surface_iterations_used'] >= 1
    assert budget['surface_iteration_failures'] == 0


def test_surface_budget_forcing_newton_failure_counter_fires_when_max_iterations_too_small():
    river = River(
        cells=(Cell(id="c0", length_m=10.0, width_m=2.0,
                    volume_m3=20.0, initial_c=10.0),),
        boundary_m3_s=1.0,
        boundary_c=10.0,
        surface_budget={
            "rh": 0.5, "wind_mps": 2.0,
            "shortwave_w_m2": 900.0, "cloud": 0.1,
        },
        max_surface_iterations=1,
        surface_relaxation=0.1,
    )
    with pytest.raises(ArithmeticError):
        river.run(duration_s=600.0, dt_s=600.0, sample_s=600.0)
    assert river.surface_iteration_failures >= 1



def _replay_metadata_config( surface_budget):
    return {
        "cells": [{
            "id": "c0",
            "length_m": 10.0,
            "width_m": 2.0,
            "volume_m3": 20.0,
            "initial_c": 10.0,
        }],
        "boundary_m3_s": 1.0,
        "boundary_c": 10.0,
        "surface_budget": surface_budget,
    }


def test_replay_metadata_null_surface_budget_is_newton():
    document = make_replay(_replay_metadata_config(None))
    assert document['model']['surface_flux'] == 'newton_lumped'
    assert document['model']['surface_accounting']['method'] == 'newton_lumped'


def test_replay_metadata_present_surface_budget_is_explicit():
    document = make_replay(_replay_metadata_config({
        "rh": 0.5, "wind_mps": 2.0,
        "shortwave_w_m2": 0.0, "cloud": 0.2,
    }))
    assert document['model']['surface_flux'] == 'explicit_budget'
    assert document['model']['surface_accounting']['method'] == 'linearized_implicit_budget'


def test_replay_metadata_simulation_time_is_stamped_when_supplied():
    config = _replay_metadata_config(None)
    config["simulation_start_epoch_unix"] = 1784000000.0
    config["duration_s"] = 30.0
    document = make_replay(config)
    assert document['simulation_time']['timezone'] == 'UTC'
    assert document['simulation_time']['end_epoch_unix'] - document['simulation_time']['start_epoch_unix'] == pytest.approx(30.0, abs=0.5 * 10 ** -(7), rel=0)


def test_replay_metadata_simulation_time_is_absent_without_a_start():
    document = make_replay(_replay_metadata_config(None))
    assert document['simulation_time'] == {}


def test_replay_metadata_cell_heat_w_round_trips_through_river_from_config():
    config = _replay_metadata_config(None)
    config["cell_heat_w"] = {"c0": 1000.0}
    config["duration_s"] = 600.0
    document = make_replay(config)
    assert document['final_budget']['cell_heat_j'] == pytest.approx(600000.0, abs=0.5 * 10 ** -(6), rel=0)
    assert (document['numerical_checks']['passed'])


def test_scheduled_boundary_discharge_scalar_and_constant_series_match():
    def run(bq):
        river = River(
            [Cell(f"c{i}", 50.0, 20.0, 50.0 * 20.0 * 1.1, 10.0,
                  dispersion_m2_s=1.0, exchange_w_m2_k=12.0)
             for i in range(4)],
            boundary_m3_s=bq, boundary_c=15.0, air_c=5.0,
        )
        river.run(600.0, dt_s=10.0, sample_s=600.0)
        return river.temperature_c, river.budget()

    scalar_t, scalar_b = run(2.0)
    series_t, series_b = run({"times_s": [0.0], "values": [2.0]})
    for a, b in zip(scalar_t, series_t):
        assert a == pytest.approx(b, abs=0.5 * 10 ** -(12), rel=0)
    assert scalar_b['boundary_input_m3'] == pytest.approx(series_b['boundary_input_m3'], abs=0.5 * 10 ** -(9), rel=0)


def test_scheduled_boundary_discharge_scheduled_discharge_closes_water_budget():
    # With no laterals, integrated inflow matches the step-schedule area across the t=400 s breakpoint.
    schedule = {"times_s": [0.0, 400.0], "values": [1.0, 3.0]}
    river = River(
        [Cell(f"c{i}", 50.0, 20.0, 50.0 * 20.0 * 1.1, 10.0,
              dispersion_m2_s=1.0, exchange_w_m2_k=12.0)
         for i in range(4)],
        boundary_m3_s=schedule, boundary_c=15.0, air_c=5.0,
    )
    river.run(1000.0, dt_s=10.0, sample_s=1000.0)
    budget = river.budget()
    expected_in = 1.0 * 400.0 + 3.0 * 600.0
    assert budget['boundary_input_m3'] == pytest.approx(expected_in, abs=0.5 * 10 ** -(9), rel=0)
    # No laterals: inflow equals outflow.
    assert budget['boundary_input_m3'] == pytest.approx(budget['outlet_export_m3'], abs=0.5 * 10 ** -(9), rel=0)
    assert budget['heat_relative_residual'] < 1e-09


def test_scheduled_boundary_discharge_step_refuses_to_cross_a_discharge_change():
    river = River(
        [Cell("c", 10.0, 1.0, 10.0, 0.0)],
        boundary_m3_s={"times_s": [0.0, 2.0], "values": [1.0, 5.0]},
        boundary_c=20.0,
    )
    with pytest.raises(ValueError):
        river.step(3.0)
    river.step(2.0)
    assert river.time_s == pytest.approx(2.0, abs=0.5 * 10 ** -(7), rel=0)


def test_scheduled_boundary_discharge_schedule_round_trips_in_replay():
    config = {
        "cells": [{
            "id": "c0", "length_m": 10.0, "width_m": 2.0,
            "volume_m3": 20.0, "initial_c": 10.0,
        }],
        "boundary_m3_s": {"times_s": [0.0, 5.0], "values": [1.0, 2.0]},
        "boundary_c": 10.0,
        "duration_s": 10.0,
        "dt_s": 1.0,
        "sample_s": 10.0,
    }
    document = make_replay(config)
    assert list(document['forcing']['boundary_m3_s']['times_s']) == [0.0, 5.0]
    assert list(document['forcing']['boundary_m3_s']['values']) == [1.0, 2.0]



def test_surface_budget_serialization_to_dict_round_trips_every_budget_param_field():
    # Non-identity values on every BudgetParams field verify to_dict preserves calibrator-set values.
    params = BudgetParams(
        albedo=0.12,
        emissivity=0.95,
        c_h=1.75e-3,
        c_e=1.80e-3,
        pressure_kpa=82.0,
        shortwave_multiplier=0.9,
        longwave_multiplier=1.05,
        longwave_bias_w_m2=-3.0,
        cloud_longwave_factor=0.18,
        a_RH=1.1,
        b_RH=-0.05,
    )
    budget = SurfaceBudget(
        Series.parse(0.5), Series.parse(2.0),
        Series.parse(100.0), Series.parse(0.3),
        params,
    )
    payload = budget.to_dict()
    reparsed = SurfaceBudget.parse(payload)
    for field in (
        "albedo", "emissivity", "c_h", "c_e", "pressure_kpa",
        "shortwave_multiplier", "longwave_multiplier",
        "longwave_bias_w_m2", "cloud_longwave_factor", "a_RH", "b_RH",
    ):
        assert getattr(reparsed.params, field) == getattr(params, field), f'field {field} did not round-trip'


def test_surface_budget_serialization_parse_rejects_unknown_budget_param_keys():
    with pytest.raises(ValueError):
        SurfaceBudget.parse({
            "rh": 0.5, "wind_mps": 2.0,
            "shortwave_w_m2": 0.0, "cloud": 0.1,
            "params": {"not_a_knob": 1.0},
        })


def test_surface_budget_serialization_replay_round_trip_preserves_non_default_params():
    config = {
        "cells": [{
            "id": "c0", "length_m": 10.0, "width_m": 2.0,
            "volume_m3": 20.0, "initial_c": 10.0,
        }],
        "boundary_m3_s": 1.0,
        "boundary_c": 10.0,
        "surface_budget": {
            "rh": 0.5, "wind_mps": 2.0,
            "shortwave_w_m2": 100.0, "cloud": 0.2,
            "params": {
                "shortwave_multiplier": 0.85,
                "longwave_bias_w_m2": -5.0,
                "a_RH": 1.2,
                "b_RH": -0.1,
                "cloud_longwave_factor": 0.19,
            },
        },
    }
    document = make_replay(config)
    serialized = document["forcing"]["surface_budget"]
    assert serialized['params']['shortwave_multiplier'] == pytest.approx(0.85, abs=0.5 * 10 ** -(7), rel=0)
    assert serialized['params']['longwave_bias_w_m2'] == pytest.approx(-5.0, abs=0.5 * 10 ** -(7), rel=0)
    assert serialized['params']['a_RH'] == pytest.approx(1.2, abs=0.5 * 10 ** -(7), rel=0)
    assert serialized['params']['b_RH'] == pytest.approx(-0.1, abs=0.5 * 10 ** -(7), rel=0)
    assert serialized['params']['cloud_longwave_factor'] == pytest.approx(0.19, abs=0.5 * 10 ** -(7), rel=0)



def test_surface_model_metadata_explicit_budget_replay_carries_describe_surface_model():
    document = make_replay({
        "cells": [{
            "id": "c0", "length_m": 10.0, "width_m": 2.0,
            "volume_m3": 20.0, "initial_c": 10.0,
        }],
        "boundary_m3_s": 1.0,
        "boundary_c": 10.0,
        "surface_budget": {
            "rh": 0.5, "wind_mps": 2.0,
            "shortwave_w_m2": 100.0, "cloud": 0.2,
        },
    })
    surface_model = document["model"]["surface_model"]
    assert surface_model['method'] == 'explicit_budget'
    assert surface_model['sign_convention'] == 'positive_into_water'
    assert surface_model['not_identified_independently'] == ['c_h', 'c_e']
    assert 'parameters' in surface_model
    assert 'parameter_status' in surface_model
    for key in ("a_RH", "b_RH", "shortwave_multiplier",
                "longwave_bias_w_m2", "cloud_longwave_factor"):
        assert key in surface_model['parameters']
        assert key in surface_model['parameter_status']
    assert 'surface_flux_sign' not in document['model']


def test_surface_model_metadata_newton_lumped_replay_carries_bare_surface_model():
    document = make_replay({
        "cells": [{
            "id": "c0", "length_m": 10.0, "width_m": 2.0,
            "volume_m3": 20.0, "initial_c": 10.0,
        }],
        "boundary_m3_s": 1.0,
        "boundary_c": 10.0,
    })
    assert document['model']['surface_model'] == {'method': 'newton_lumped', 'sign_convention': 'positive_into_water'}
    assert 'surface_flux_sign' not in document['model']



def test_step_diagnostics_step_reports_old_new_temperature_summary():
    river = River(
        [Cell(f"c{i}", 10.0, 1.0, 10.0, 20.0 - i)
         for i in range(3)],
        boundary_m3_s=1.0, boundary_c=5.0,
    )
    info = river.step(5.0)
    assert info['temperature_old_min_c'] == 18.0
    assert info['temperature_old_max_c'] == 20.0
    assert info['temperature_new_min_c'] < info['temperature_old_min_c'] + 1e-12
    assert info['max_cell_temperature_change_c'] >= 0.0
    # Newton-lumped: no inner iteration, residual is zero.
    assert info['surface_newton_residual_c'] == 0.0


def test_step_diagnostics_explicit_budget_step_reports_newton_residual():
    river = River(
        cells=(Cell(id="c0", length_m=10.0, width_m=2.0,
                    volume_m3=20.0, initial_c=10.0),),
        boundary_m3_s=1.0,
        boundary_c=10.0,
        surface_budget={
            "rh": 0.5, "wind_mps": 2.0,
            "shortwave_w_m2": 500.0, "cloud": 0.3,
        },
    )
    info = river.step(60.0)
    assert info['surface_iterations'] >= 1
    assert info['surface_newton_residual_c'] <= river.surface_tolerance_c
    budget = river.budget()
    assert 'max_surface_newton_residual_c' in budget
    assert budget['max_surface_newton_residual_c'] <= river.surface_tolerance_c



def test_numerical_warning_courant_warning_fires_above_one():
    # One cell, high boundary flow and small volume force Courant > 1.
    river = River(
        [Cell("c", 10.0, 1.0, 1.0, 10.0)],
        boundary_m3_s=5.0, boundary_c=10.0,
    )
    river.run(10.0, dt_s=1.0, sample_s=10.0)
    budget = river.budget()
    assert budget['max_advective_courant'] > 1.0
    assert (any(('Courant' in message for message in budget['numerical_warnings']))), budget['numerical_warnings']


def test_numerical_warning_make_replay_exposes_numerical_warnings():
    document = make_replay({
        "cells": [{
            "id": "c0", "length_m": 10.0, "width_m": 1.0,
            "volume_m3": 1.0, "initial_c": 10.0,
        }],
        "boundary_m3_s": 5.0,
        "boundary_c": 10.0,
        "duration_s": 10.0,
        "dt_s": 1.0,
        "sample_s": 10.0,
    })
    assert 'numerical_warnings' in document['numerical_checks']
    assert (document['numerical_checks']['numerical_warnings'])


def test_numerical_warning_calm_run_has_no_numerical_warnings():
    river = River(
        [Cell("c", 100.0, 10.0, 1000.0, 10.0)],
        boundary_m3_s=0.1, boundary_c=10.0,
    )
    river.run(10.0, dt_s=1.0, sample_s=10.0)
    budget = river.budget()
    assert budget['numerical_warnings'] == []



def test_solve_tridiagonal_diagnostics_singular_pivot_names_cell_and_inputs():
    from yellowstone_python.river.river_transport import solve_tridiagonal
    with pytest.raises(ArithmeticError, match='cell firehole_cell_00001.*inputs'):
        solve_tridiagonal(
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 0.0],
            [1.0, 1.0],
            cell_ids=["firehole_cell_00000", "firehole_cell_00001"],
        )



def test_series_serialization_make_replay_source_temperature_is_a_series_dict():
    document = make_replay({
        "cells": [{
            "id": "c0", "length_m": 10.0, "width_m": 2.0,
            "volume_m3": 20.0, "initial_c": 10.0,
        }],
        "boundary_m3_s": 1.0,
        "boundary_c": 10.0,
        "sources": [{
            "id": "s", "cell_id": "c0",
            "flow_m3_s": 0.1, "temperature_c": 15.0,
        }],
    })
    serialized = document["forcing"]["sources"][0]["temperature_c"]
    assert isinstance(serialized, dict)
    assert isinstance(serialized['times_s'], list)
    assert isinstance(serialized['values'], list)
    assert serialized['times_s'] == [0.0]
    assert serialized['values'] == [15.0]



