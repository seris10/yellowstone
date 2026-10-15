"""Tests for the explicit surface energy budget."""
from __future__ import annotations

import importlib.util
import math
import pytest

from yellowstone_python.river.river_transport import Cell, River, river_from_config
from yellowstone_python.river.surface_flux import BudgetParams, MetState, flux_at, linearized

# Fixed replay epoch so the clock is deterministic across runs.
REPLAY_START = {"simulation_start_epoch_unix": 1784000000.0}

HAS_SYMPY = importlib.util.find_spec("sympy") is not None


def met(**kw):
    base = {"air_c": 10.0, "rh": 0.5, "wind_mps": 2.0,
            "shortwave_w_m2": 0.0, "cloud": 0.0}
    base.update(kw)
    return MetState(**base)


def test_flux_component_hot_water_loses_heat_all_terms():
    parts = flux_at(40.0, met())
    assert parts['longwave'] < 0.0
    assert parts['sensible'] < 0.0
    assert parts['latent'] < 0.0
    assert parts['shortwave'] == 0.0
    assert parts['net'] < 0.0


def test_flux_component_shortwave_scales_with_albedo():
    day = met(shortwave_w_m2=500.0)
    assert flux_at(10.0, day)['shortwave'] == pytest.approx(460.0, abs=0.5 * 10 ** -(7), rel=0)
    dark = BudgetParams(albedo=0.5)
    assert flux_at(10.0, day, dark)['shortwave'] == pytest.approx(250.0, abs=0.5 * 10 ** -(7), rel=0)


def test_flux_component_saturated_isothermal_air_kills_turbulent_terms():
    parts = flux_at(15.0, met(air_c=15.0, rh=1.0))
    assert parts['sensible'] == pytest.approx(0.0, abs=0.5 * 10 ** -(9), rel=0)
    assert parts['latent'] == pytest.approx(0.0, abs=0.5 * 10 ** -(9), rel=0)


def test_flux_component_cold_dry_windy_evaporates_more():
    calm = flux_at(20.0, met(air_c=10.0, rh=0.8, wind_mps=0.1))
    windy = flux_at(20.0, met(air_c=10.0, rh=0.2, wind_mps=8.0))
    assert windy['latent'] < calm['latent']


def test_flux_component_bad_inputs_rejected():
    with pytest.raises(ValueError):
        MetState(air_c=10.0, rh=1.5, wind_mps=1.0,
                 shortwave_w_m2=0.0, cloud=0.0)
    with pytest.raises(ValueError):
        MetState(air_c=10.0, rh=0.5, wind_mps=-1.0,
                 shortwave_w_m2=0.0, cloud=0.0)
    with pytest.raises(ValueError):
        BudgetParams(albedo=1.5)
    with pytest.raises(ValueError):
        flux_at(float("nan"), met())


def test_flux_component_linearization_matches_finite_difference():
    for water in (-2.0, 10.0, 40.0, 70.0):
        state = met(air_c=12.0, rh=0.7, wind_mps=3.0,
                    shortwave_w_m2=300.0, cloud=0.4)
        _, slope = linearized(water, state)
        h = 1e-4
        numeric = (flux_at(water + h, state)["net"]
                   - flux_at(water - h, state)["net"]) / (2.0 * h)
        assert slope == pytest.approx(numeric, abs=0.5 * 10 ** -(4), rel=0)
        assert slope < 0.0  # stabilizing feedback



def _symbolic_jacobian_lambdified():
    import sympy as sp
    (T, Ta, rh, U, SW, cl, alb, emi, ch, ce, P) = sp.symbols(
        "T Ta rh U SW cl alb emi ch ce P")
    SIG, R, CP, LV = (5.670374419e-8, 287.058, 1005.0, 2.45e6)
    es_air = 0.61094 * sp.exp(17.625 * Ta / (Ta + 243.04))
    ea = rh * es_air
    t_kair = Ta + 273.15
    rho = P * 1000.0 / (R * t_kair) * (1.0 - 0.378 * ea / P)
    q_air = 0.622 * ea / (P - 0.378 * ea)
    es_w = 0.61094 * sp.exp(17.625 * T / (T + 243.04))
    q_sat = 0.622 * es_w / (P - 0.378 * es_w)
    lw_in = (0.642 * (ea * 10.0 / t_kair) ** 0.142
             * (1.0 + 0.22 * cl ** 2) * SIG * t_kair ** 4)
    flux = ((1.0 - alb) * SW
            + lw_in - emi * SIG * (T + 273.15) ** 4
            + rho * CP * ch * U * (Ta - T)
            + rho * LV * ce * U * (q_air - q_sat))
    return (sp.lambdify((T, Ta, rh, U, SW, cl, alb, emi, ch, ce, P),
                        flux, "math"),
            sp.lambdify((T, Ta, rh, U, SW, cl, alb, emi, ch, ce, P),
                        sp.diff(flux, T), "math"))


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_SYMPY, reason='sympy not installed')
def test_symbolic_jacobian_symbolic_derivative_matches_hand_code():
    f_sym, d_sym = _symbolic_jacobian_lambdified()
    param_sets = [BudgetParams(),
                  BudgetParams(albedo=0.2, emissivity=0.9,
                               c_h=2.5e-3, c_e=1.0e-3,
                               pressure_kpa=85.0)]
    worst = 0.0
    count = 0
    for params in param_sets:
        for water in (-5.0, 0.0, 10.0, 20.0, 30.0, 45.0):
            for air in (-5.0, 12.0, 28.0):
                for rh in (0.05, 0.5, 0.95):
                    for wind in (0.5, 9.0):
                        for sw in (0.0, 900.0):
                            for cloud in (0.0, 1.0):
                                state = met(
                                    air_c=air, rh=rh,
                                    wind_mps=wind,
                                    shortwave_w_m2=sw,
                                    cloud=cloud)
                                args = (
                                    water, air, rh, wind, sw,
                                    cloud, params.albedo,
                                    params.emissivity, params.c_h,
                                    params.c_e,
                                    params.pressure_kpa)
                                f0, slope = linearized(
                                    water, state, params)
                                expect_f = f_sym(*args)
                                expect_d = d_sym(*args)
                                assert f0 == pytest.approx(expect_f, abs=1e-06 * abs(expect_f) + 1e-09, rel=0)
                                denom = abs(expect_d) or 1.0
                                rel = abs(slope - expect_d) / denom
                                worst = max(worst, rel)
                                count += 1
    assert worst < 1e-06
    assert count > 500



def budget_river(**kw):
    cells = [Cell(f"c{i}", 10.0, 5.0, 50.0, 10.0,
                  dispersion_m2_s=0.5, exchange_w_m2_k=12.0)
             for i in range(3)]
    spec = {"rh": 0.5, "wind_mps": 2.0, "shortwave_w_m2": 0.0,
            "cloud": 0.0}
    spec.update(kw.pop("budget", {}))
    return River(cells, boundary_m3_s=2.0, boundary_c=10.0, air_c=10.0,
                 surface_budget=spec, **kw)


def test_budget_solver_budget_closes_and_components_track_the_total():
    river = budget_river()
    river.run(3600.0, dt_s=30.0, sample_s=3600.0)
    totals = river.budget()
    assert totals['heat_relative_residual'] < 1e-09
    # surface_exchange_j is the linearized total integrated by the solver; component totals are nonlinear.
    components = math.fsum(
        totals[name]
        for name in ("surface_shortwave_j", "surface_longwave_j",
                     "surface_sensible_j", "surface_latent_j")
    )
    assert totals['surface_exchange_j'] == pytest.approx(components, abs=abs(components) * 1e-06, rel=0)
    assert totals['max_surface_linearization_error_w'] < abs(components) * 1e-06
    assert totals['additional_heat_flux_j'] == pytest.approx(0.0, abs=0.5 * 10 ** -(6), rel=0)


def test_budget_solver_sunlit_water_runs_hotter_than_newton():
    sunny = budget_river(budget={"shortwave_w_m2": 800.0})
    sunny.run(86400.0, dt_s=120.0, sample_s=21600.0)
    newton = River(
        [Cell(f"c{i}", 10.0, 5.0, 50.0, 10.0, dispersion_m2_s=0.5,
              exchange_w_m2_k=12.0) for i in range(3)],
        boundary_m3_s=2.0, boundary_c=10.0, air_c=10.0)
    newton.run(86400.0, dt_s=120.0, sample_s=21600.0)
    assert (all((s > n for s, n in zip(sunny.temperature_c, newton.temperature_c))))
    assert (all((t > 10.0 for t in sunny.temperature_c)))
    assert (all((abs(t - 10.0) < 1e-06 for t in newton.temperature_c)))
    assert sunny.budget()['heat_relative_residual'] < 1e-09


def test_budget_solver_config_round_trip_and_rejections():
    river = river_from_config({
        "boundary_m3_s": 2.0, "boundary_c": 10.0,
        "cells": [{"id": "c", "length_m": 10.0, "width_m": 5.0,
                   "volume_m3": 50.0, "initial_c": 10.0}],
        "surface_budget": {"rh": 0.5, "wind_mps": 2.0,
                           "shortwave_w_m2": 100.0, "cloud": 0.2,
                           "params": {"albedo": 0.1}},
    })
    assert river.surface_budget is not None
    assert river.surface_budget.params.albedo == pytest.approx(0.1, abs=0.5 * 10 ** -(7), rel=0)
    for bad_budget in ({"wind_mps": 1.0, "shortwave_w_m2": 0.0,
                        "cloud": 0.0},
                       {"rh": 2.0, "wind_mps": 1.0,
                        "shortwave_w_m2": 0.0, "cloud": 0.0},
                       {"rh": 0.5, "wind_mps": 1.0,
                        "shortwave_w_m2": 0.0, "cloud": 0.0,
                        "params": {"albedo": 9.0}},
                       {"rh": 0.5, "wind_mps": 1.0,
                        "shortwave_w_m2": 0.0, "cloud": 0.0,
                        "mystery": 1.0}):
        with pytest.raises(ValueError):
            river_from_config({
                "boundary_m3_s": 2.0, "boundary_c": 10.0,
                "cells": [{"id": "c", "length_m": 10.0, "width_m": 5.0,
                           "volume_m3": 50.0, "initial_c": 10.0}],
                "surface_budget": bad_budget,
            })


def test_budget_solver_legacy_path_has_zero_components():
    river = River([Cell("c", 10.0, 5.0, 50.0, 10.0,
                        exchange_w_m2_k=12.0)],
                  boundary_m3_s=2.0, boundary_c=10.0, air_c=10.0)
    river.run(600.0, dt_s=30.0, sample_s=600.0)
    totals = river.budget()
    for name in ("surface_shortwave_j", "surface_longwave_j",
                 "surface_sensible_j", "surface_latent_j"):
        assert totals[name] == 0.0



def test_mapped_budget_mapped_energy_path_runs_and_labels():
    from yellowstone_python.river.river_world import build_mapped_replay
    world = {
        "georeference": {"note": "test"},
        "rivers": [{
            "id": "seg", "name": "FIREHOLE RIVER", "width": 10.0,
            "endpoint_node_ids": ["n0", "n1"],
            "points": [[0, 0, 100], [0, 0, 0]],
        }],
    }
    ecosystem = {
        "boundary_m3s": 5.0, "boundary_c": 15.0, "clock_hour": 12.0,
        "weather": {"humidity": 0.5, "cloud": 0.1},
        "river_reaches": [],
    }
    doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=600.0,
                              maximum_cell_m=25.0, energy_budget=True)
    assert (doc['numerical_checks']['passed'])
    assert doc['model']['surface_flux'] == 'explicit_budget'
    assert 'Explicit' in doc['parameter_notes']['exchange_status']
    assert doc['forcing']['surface_budget'] is not None
    # Same geometry as the lumped path; budget changes heat only.
    plain = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                                maximum_cell_m=25.0)
    assert [c['volume_m3'] for c in doc['cells']][:5] == [c['volume_m3'] for c in plain['cells']][:5]



def test_sensible_latent_comparator_absent_observations_report_no_observation():
    from yellowstone_python.river.surface_flux import compare_sensible_latent
    state = met(air_c=10.0, rh=0.5, wind_mps=2.0)
    report = compare_sensible_latent(20.0, state)
    rows = {row["channel"]: row for row in report["rows"]}
    for name in ("sensible", "latent"):
        assert rows[name]['status'] == 'no_observation'
        assert rows[name]['observed_w_m2'] is None
        assert rows[name]['residual_w_m2'] is None
        assert (math.isfinite(rows[name]['modeled_w_m2']))


def test_sensible_latent_comparator_observations_produce_signed_residuals():
    from yellowstone_python.river.surface_flux import compare_sensible_latent
    state = met(air_c=10.0, rh=0.5, wind_mps=2.0)
    baseline = flux_at(20.0, state)
    report = compare_sensible_latent(
        20.0, state,
        observed_sensible_w_m2=baseline["sensible"] - 5.0,
        observed_latent_w_m2=baseline["latent"] + 7.0,
    )
    rows = {row["channel"]: row for row in report["rows"]}
    assert rows['sensible']['residual_w_m2'] == pytest.approx(5.0, abs=0.5 * 10 ** -(6), rel=0)
    assert rows['latent']['residual_w_m2'] == pytest.approx(-7.0, abs=0.5 * 10 ** -(6), rel=0)


def test_sensible_latent_comparator_nonfinite_observation_is_refused():
    from yellowstone_python.river.surface_flux import compare_sensible_latent
    state = met()
    with pytest.raises(ValueError):
        compare_sensible_latent(
            20.0, state, observed_sensible_w_m2=float("nan"))



