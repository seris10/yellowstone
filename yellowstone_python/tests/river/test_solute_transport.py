"""Numerical verification of the conservative solute transport engine."""
from __future__ import annotations

import math
import pytest

from yellowstone_python.river.river_transport import Cell
from yellowstone_python.river.solute_transport import BoundaryConcentrations, SOLUTE_KEYS, SoluteSource, SoluteTransport, chloride_from_specific_conductance, fit_chloride_from_conductance, load_hydrothermal_solutes, solute_habitat_multiplier, transport_summary
from yellowstone_python.river.solute_validation import GaugeRecord, observed_chloride_series, score_chloride_prediction


def _uniform_cells(n: int = 10, dispersion: float = 0.5) -> tuple[Cell, ...]:
    return tuple(
        Cell(
            id=f"c{i:02d}",
            length_m=20.0,
            width_m=4.0,
            volume_m3=20.0 * 4.0 * 1.0,
            initial_c=0.0,
            dispersion_m2_s=dispersion,
            exchange_w_m2_k=0.0,
        )
        for i in range(n)
    )


def test_solute_transport_basics_zero_sources_preserve_boundary_concentration():
    cells = _uniform_cells(8)
    transport = SoluteTransport(
        cells=cells,
        boundary_m3_s=2.0,
        boundary_concentrations=BoundaryConcentrations(
            chloride_mg_l=12.0,
            arsenic_ug_l=5.0,
            boron_mg_l=0.3,
        ),
    )
    transport.run(duration_s=6000.0, dt_s=20.0, sample_s=1000.0)
    for key, expected in (
        ("chloride_mg_l", 12.0),
        ("arsenic_ug_l", 5.0),
        ("boron_mg_l", 0.3),
    ):
        for value in transport.concentrations(key):
            assert value == pytest.approx(expected, abs=0.5 * 10 ** -(8), rel=0)


def test_solute_transport_basics_mass_balance_closes_along_reach():
    cells = _uniform_cells(6, dispersion=0.8)
    source = SoluteSource(
        id="hot_inflow",
        cell_id="c02",
        flow_m3_s=0.4,
        concentrations={
            "chloride_mg_l": 300.0,
            "arsenic_ug_l": 1800.0,
            "boron_mg_l": 4.5,
        },
    )
    transport = SoluteTransport(
        cells=cells,
        boundary_m3_s=2.0,
        boundary_concentrations=BoundaryConcentrations(
            chloride_mg_l=5.0,
            arsenic_ug_l=1.0,
            boron_mg_l=0.1,
        ),
        sources=(source,),
    )
    transport.run(duration_s=3600.0, dt_s=15.0, sample_s=600.0)
    budget = transport.mass_budget()
    for key in SOLUTE_KEYS:
        residual = budget["solutes"][key]["mass_relative_residual"]
        assert residual < 1e-10, f'solute {key} residual {residual}'
    water_residual = budget["water_relative_residual"]
    assert water_residual < 1e-12


def test_solute_transport_basics_steady_state_mass_balance_is_exact():
    cells = _uniform_cells(5, dispersion=0.5)
    source = SoluteSource(
        id="inflow",
        cell_id="c01",
        flow_m3_s=0.5,
        concentrations={
            "chloride_mg_l": 400.0,
            "arsenic_ug_l": 2000.0,
            "boron_mg_l": 5.0,
        },
    )
    transport = SoluteTransport(
        cells=cells,
        boundary_m3_s=3.0,
        boundary_concentrations=BoundaryConcentrations(
            chloride_mg_l=10.0,
            arsenic_ug_l=2.0,
            boron_mg_l=0.1,
        ),
        sources=(source,),
    )
    steady = transport.steady_concentrations()
    # At steady state the downstream outlet mass flux equals total inputs.
    q_outlet = 3.0 + 0.5
    for key, boundary_c, source_c in (
        ("chloride_mg_l", 10.0, 400.0),
        ("arsenic_ug_l", 2.0, 2000.0),
        ("boron_mg_l", 0.1, 5.0),
    ):
        input_mass_rate = 3.0 * boundary_c + 0.5 * source_c
        outlet_c = steady[key][-1]
        assert q_outlet * outlet_c == pytest.approx(input_mass_rate, abs=0.5 * 10 ** -(6), rel=0), f'steady {key} outlet flux'


def test_solute_transport_basics_step_source_travels_at_advective_velocity():
    # Pure advection: zero dispersion isolates the upwind step from mixing.
    n = 40
    cells = _uniform_cells(n, dispersion=0.0)
    area = cells[0].cross_section_m2
    q = 2.0
    boundary_chloride = {
        "times_s": [0.0, 100.0],
        "values": [0.0, 50.0],
    }
    transport = SoluteTransport(
        cells=cells,
        boundary_m3_s=q,
        boundary_concentrations=BoundaryConcentrations(
            chloride_mg_l=boundary_chloride,
            arsenic_ug_l=0.0,
            boron_mg_l=0.0,
        ),
    )
    velocity = q / area
    travel_time = cells[0].length_m / velocity
    # Advance one cell length of travel time plus 25 percent of a step for stability.
    transport.run(
        duration_s=travel_time * 10.0,
        dt_s=travel_time * 0.25,
        sample_s=travel_time,
    )
    values = transport.concentrations("chloride_mg_l")
    # Front has crossed about ten cells; cell 0 approaches the boundary value, cell -1 stays near zero.
    assert values[0] == pytest.approx(50.0, abs=0.5 * 10 ** -(0), rel=0)
    assert values[-1] == pytest.approx(0.0, abs=0.5 * 10 ** -(3), rel=0)
    # The front sits near cell index 10: first cell with value at or below half the plateau.
    front_index = next(
        i for i, v in enumerate(values) if v <= 25.0
    )
    assert front_index >= 6
    assert front_index <= 14



def test_conductance_to_chloride_fit_reproduces_published_points():
    # Synthetic paired samples constructed from a known slope and intercept.
    slope = 0.32
    intercept = -5.0
    xs = [120.0, 240.0, 380.0, 510.0, 640.0, 820.0, 950.0]
    samples = [
        {"sc_us_cm": x, "chloride_mg_l": max(0.0, slope * x + intercept)}
        for x in xs
    ]
    fit = fit_chloride_from_conductance(samples)
    assert fit['slope_mg_l_per_us_cm'] == pytest.approx(slope, abs=0.5 * 10 ** -(10), rel=0)
    assert fit['intercept_mg_l'] == pytest.approx(intercept, abs=0.5 * 10 ** -(10), rel=0)
    assert fit['r_squared'] == pytest.approx(1.0, abs=0.5 * 10 ** -(10), rel=0)
    for entry in samples:
        predicted = chloride_from_specific_conductance(
            entry["sc_us_cm"], fit["slope_mg_l_per_us_cm"],
            fit["intercept_mg_l"],
        )
        assert predicted == pytest.approx(entry['chloride_mg_l'], abs=0.5 * 10 ** -(8), rel=0)


def test_conductance_to_chloride_clamp_at_zero():
    predicted = chloride_from_specific_conductance(5.0, 0.3, -20.0)
    assert predicted == 0.0



def test_habitat_multiplier_full_suitability_below_chronic():
    multipliers = solute_habitat_multiplier(
        chloride_mg_l=20.0,
        arsenic_ug_l=10.0,
        boron_mg_l=0.3,
    )
    assert multipliers['combined'] == 1.0


def test_habitat_multiplier_zero_suitability_above_acute():
    multipliers = solute_habitat_multiplier(
        chloride_mg_l=5000.0,
        arsenic_ug_l=5000.0,
        boron_mg_l=50.0,
    )
    assert multipliers['combined'] == 0.0


def test_habitat_multiplier_ramp_is_monotonic_decreasing():
    thresholds = load_hydrothermal_solutes()[
        "aquatic_toxicity_thresholds"
    ]
    last = math.inf
    for value in (0.0, 100.0, 230.0, 500.0, 860.0, 1200.0):
        factor = solute_habitat_multiplier(
            chloride_mg_l=value,
            arsenic_ug_l=0.0,
            boron_mg_l=0.0,
            thresholds=thresholds,
        )["chloride_factor"]
        assert factor <= last
        last = factor



def test_data_file_data_file_has_required_species():
    document = load_hydrothermal_solutes()
    features = document["features"]
    for name in (
        "grand_prismatic", "excelsior", "opal_pool", "turquoise_pool",
        "firehole_upstream_boundary",
    ):
        assert name in features
        for solute in ("chloride_mg_l", "arsenic_ug_l", "boron_mg_l"):
            assert solute in features[name]
            entry = features[name][solute]
            assert 'status' in entry
            if entry["value"] is not None:
                assert entry['value'] >= 0.0
            else:
                assert entry['status'] in {'unknown', 'authored_no_verified_sample'}


def test_data_file_excelsior_values_are_measured():
    document = load_hydrothermal_solutes()
    excelsior = document["features"]["excelsior"]
    for solute in ("chloride_mg_l", "arsenic_ug_l", "boron_mg_l"):
        entry = excelsior[solute]
        assert entry['status'] == 'measured_literature'
        assert entry['value'] > 0.0
        assert 'sample_id' in entry
        assert 'sample_date' in entry
        assert 'page_or_table' in entry
        assert entry['source'] == 'ball_mccleskey_nordstrom_ofr_2010_1192'


def test_data_file_upstream_boundary_is_fitted_not_pre_thermal():
    document = load_hydrothermal_solutes()
    baseline = document["features"]["firehole_upstream_boundary"]
    assert baseline['chloride_mg_l']['status'] == 'fitted_from_upstream_gauge_sc'
    assert baseline['chloride_mg_l']['value'] > 5.0


def test_data_file_chloride_sc_relation_is_fitted():
    document = load_hydrothermal_solutes()
    relation = document["chloride_specific_conductance_relation"]
    assert relation['status'] == 'fitted_not_validated_single_window'
    assert relation['n_paired'] > 2
    assert relation['r_squared'] > 0.5



def test_solute_validation_observed_chloride_series_tracks_sc():
    records = [
        GaugeRecord(epoch_s=0.0, discharge_m3_s=5.0, sc_us_cm=200.0),
        GaugeRecord(epoch_s=600.0, discharge_m3_s=6.0, sc_us_cm=350.0),
    ]
    observed = observed_chloride_series(records, 0.3, -5.0)
    assert len(observed) == 2
    assert observed[0]['chloride_mg_l'] == pytest.approx(0.3 * 200.0 - 5.0, abs=0.5 * 10 ** -(7), rel=0)
    assert observed[1]['chloride_flux_g_s'] == pytest.approx((0.3 * 350.0 - 5.0) * 6.0, abs=0.5 * 10 ** -(7), rel=0)


def test_solute_validation_score_runs_on_synthetic_record():
    gauge = [
        {"epoch_s": 0.0, "discharge_m3_s": 5.0, "sc_us_cm": 300.0},
        {"epoch_s": 60.0, "discharge_m3_s": 5.0, "sc_us_cm": 320.0},
        {"epoch_s": 120.0, "discharge_m3_s": 5.0, "sc_us_cm": 340.0},
    ]
    slope = 0.3
    intercept = -5.0
    predictions = []
    for row in gauge:
        cl = slope * row["sc_us_cm"] + intercept
        predictions.append({
            "epoch_s": row["epoch_s"],
            "chloride_mg_l": cl,
            "chloride_flux_g_s": cl * row["discharge_m3_s"],
        })
    score = score_chloride_prediction(
        predictions, gauge,
        slope_mg_l_per_us_cm=slope,
        intercept_mg_l=intercept,
    )
    assert score['schema'] == 'yellowstone.solute_validation.v1'
    assert score['status'] == 'fitted_not_validated_single_window'
    assert score['n'] == 3
    assert abs(score['chloride_bias_mg_l']) < 1e-10
    assert score['chloride_rmse_mg_l'] < 1e-10
    assert score['chloride_flux_predicted_over_observed'] == pytest.approx(1.0, abs=0.5 * 10 ** -(10), rel=0)



def test_summary_summary_includes_mass_budget_and_cell_ids():
    cells = _uniform_cells(3)
    transport = SoluteTransport(
        cells=cells,
        boundary_m3_s=1.5,
        boundary_concentrations=BoundaryConcentrations(
            chloride_mg_l=8.0, arsenic_ug_l=2.0, boron_mg_l=0.2,
        ),
    )
    transport.run(duration_s=120.0, dt_s=10.0, sample_s=60.0)
    summary = transport_summary(transport)
    assert summary['schema'] == 'yellowstone.solute_transport.v1'
    assert summary['n_cells'] == 3
    assert summary['cell_ids'] == ['c00', 'c01', 'c02']
    assert 'mass_budget' in summary



