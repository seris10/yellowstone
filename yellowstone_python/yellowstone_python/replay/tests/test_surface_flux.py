"""Tests for the explicit surface energy budget.

Physics sign conventions and solver integration only — coefficients are
illustrative, not fitted, and no test asserts a Yellowstone temperature.
"""
from __future__ import annotations

import importlib.util
import math
import unittest

from yellowstone_python.replay.river_transport import (
    Cell,
    River,
    river_from_config,
)
from yellowstone_python.replay.surface_flux import (
    BudgetParams,
    MetState,
    flux_at,
    linearized,
)

HAS_SYMPY = importlib.util.find_spec("sympy") is not None


def met(**kw):
    base = {"air_c": 10.0, "rh": 0.5, "wind_mps": 2.0,
            "shortwave_w_m2": 0.0, "cloud": 0.0}
    base.update(kw)
    return MetState(**base)


class FluxComponentTests(unittest.TestCase):
    def test_hot_water_loses_heat_all_terms(self):
        parts = flux_at(40.0, met())
        self.assertLess(parts["longwave"], 0.0)
        self.assertLess(parts["sensible"], 0.0)
        self.assertLess(parts["latent"], 0.0)
        self.assertEqual(parts["shortwave"], 0.0)
        self.assertLess(parts["net"], 0.0)

    def test_shortwave_scales_with_albedo(self):
        day = met(shortwave_w_m2=500.0)
        self.assertAlmostEqual(flux_at(10.0, day)["shortwave"], 460.0)
        dark = BudgetParams(albedo=0.5)
        self.assertAlmostEqual(
            flux_at(10.0, day, dark)["shortwave"], 250.0)

    def test_saturated_isothermal_air_kills_turbulent_terms(self):
        parts = flux_at(15.0, met(air_c=15.0, rh=1.0))
        self.assertAlmostEqual(parts["sensible"], 0.0, places=9)
        self.assertAlmostEqual(parts["latent"], 0.0, places=9)

    def test_cold_dry_windy_evaporates_more(self):
        calm = flux_at(20.0, met(air_c=10.0, rh=0.8, wind_mps=0.1))
        windy = flux_at(20.0, met(air_c=10.0, rh=0.2, wind_mps=8.0))
        self.assertLess(windy["latent"], calm["latent"])

    def test_bad_inputs_rejected(self):
        with self.assertRaises(ValueError):
            MetState(air_c=10.0, rh=1.5, wind_mps=1.0,
                     shortwave_w_m2=0.0, cloud=0.0)
        with self.assertRaises(ValueError):
            MetState(air_c=10.0, rh=0.5, wind_mps=-1.0,
                     shortwave_w_m2=0.0, cloud=0.0)
        with self.assertRaises(ValueError):
            BudgetParams(albedo=1.5)
        with self.assertRaises(ValueError):
            flux_at(float("nan"), met())

    def test_linearization_matches_finite_difference(self):
        for water in (-2.0, 10.0, 40.0, 70.0):
            state = met(air_c=12.0, rh=0.7, wind_mps=3.0,
                        shortwave_w_m2=300.0, cloud=0.4)
            _, slope = linearized(water, state)
            h = 1e-4
            numeric = (flux_at(water + h, state)["net"]
                       - flux_at(water - h, state)["net"]) / (2.0 * h)
            self.assertAlmostEqual(slope, numeric, places=4)
            self.assertLess(slope, 0.0)  # stabilizing feedback


@unittest.skipUnless(HAS_SYMPY, "sympy not installed")
class SymbolicJacobianTests(unittest.TestCase):
    """The hand-derived dF/dT vs symbolic differentiation.

    flux_at is re-expressed from the module's documented equations and
    differentiated by SymPy — the independence is in the differentiation,
    not the transcription (the flux VALUE is asserted equal too, so a
    transcription slip fails loudly instead of cancelling). Requires
    sympy, which is test-only: the test skips where sympy is absent.
    """

    @staticmethod
    def _lambdified():
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

    def test_symbolic_derivative_matches_hand_code(self):
        f_sym, d_sym = self._lambdified()
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
                                    self.assertAlmostEqual(
                                        f0, expect_f,
                                        delta=1e-6 * abs(expect_f) + 1e-9)
                                    denom = abs(expect_d) or 1.0
                                    rel = abs(slope - expect_d) / denom
                                    worst = max(worst, rel)
                                    count += 1
        self.assertLess(worst, 1e-6)
        self.assertGreater(count, 500)


def budget_river(**kw):
    cells = [Cell(f"c{i}", 10.0, 5.0, 50.0, 10.0,
                  dispersion_m2_s=0.5, exchange_w_m2_k=12.0)
             for i in range(3)]
    spec = {"rh": 0.5, "wind_mps": 2.0, "shortwave_w_m2": 0.0,
            "cloud": 0.0}
    spec.update(kw.pop("budget", {}))
    return River(cells, boundary_m3_s=2.0, boundary_c=10.0, air_c=10.0,
                 surface_budget=spec, **kw)


class BudgetSolverTests(unittest.TestCase):
    def test_budget_closes_and_components_sum(self):
        river = budget_river()
        river.run(3600.0, dt_s=30.0, sample_s=3600.0)
        totals = river.budget()
        self.assertLess(totals["heat_relative_residual"], 1e-9)
        self.assertAlmostEqual(
            totals["surface_exchange_j"],
            totals["surface_shortwave_j"] + totals["surface_longwave_j"]
            + totals["surface_sensible_j"] + totals["surface_latent_j"],
            places=3)

    def test_sunlit_water_runs_hotter_than_newton(self):
        sunny = budget_river(budget={"shortwave_w_m2": 800.0})
        sunny.run(86400.0, dt_s=120.0, sample_s=21600.0)
        newton = River(
            [Cell(f"c{i}", 10.0, 5.0, 50.0, 10.0, dispersion_m2_s=0.5,
                  exchange_w_m2_k=12.0) for i in range(3)],
            boundary_m3_s=2.0, boundary_c=10.0, air_c=10.0)
        newton.run(86400.0, dt_s=120.0, sample_s=21600.0)
        self.assertTrue(
            all(s > n for s, n in zip(sunny.temperature_c, newton.temperature_c))
        )
        self.assertTrue(all(t > 10.0 for t in sunny.temperature_c))
        self.assertTrue(all(abs(t - 10.0) < 1e-6
                            for t in newton.temperature_c))
        self.assertLess(sunny.budget()["heat_relative_residual"], 1e-9)

    def test_config_round_trip_and_rejections(self):
        river = river_from_config({
            "boundary_m3_s": 2.0, "boundary_c": 10.0,
            "cells": [{"id": "c", "length_m": 10.0, "width_m": 5.0,
                       "volume_m3": 50.0, "initial_c": 10.0}],
            "surface_budget": {"rh": 0.5, "wind_mps": 2.0,
                               "shortwave_w_m2": 100.0, "cloud": 0.2,
                               "params": {"albedo": 0.1}},
        })
        self.assertIsNotNone(river.surface_budget)
        self.assertAlmostEqual(river.surface_budget.params.albedo, 0.1)
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
            with self.assertRaises(ValueError, msg=str(bad_budget)):
                river_from_config({
                    "boundary_m3_s": 2.0, "boundary_c": 10.0,
                    "cells": [{"id": "c", "length_m": 10.0, "width_m": 5.0,
                               "volume_m3": 50.0, "initial_c": 10.0}],
                    "surface_budget": bad_budget,
                })

    def test_legacy_path_has_zero_components(self):
        river = River([Cell("c", 10.0, 5.0, 50.0, 10.0,
                            exchange_w_m2_k=12.0)],
                      boundary_m3_s=2.0, boundary_c=10.0, air_c=10.0)
        river.run(600.0, dt_s=30.0, sample_s=600.0)
        totals = river.budget()
        for name in ("surface_shortwave_j", "surface_longwave_j",
                     "surface_sensible_j", "surface_latent_j"):
            self.assertEqual(totals[name], 0.0)


class MappedBudgetTests(unittest.TestCase):
    def test_mapped_energy_path_runs_and_labels(self):
        from yellowstone_python.replay.river_world import (
            build_mapped_replay,
        )
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
        doc = build_mapped_replay(world, ecosystem, duration_s=600.0,
                                  maximum_cell_m=25.0, energy_budget=True)
        self.assertTrue(doc["numerical_checks"]["passed"])
        self.assertEqual(doc["model"]["surface_flux"], "explicit_budget")
        self.assertIn("Explicit", doc["parameter_notes"]["exchange_status"])
        self.assertIsNotNone(doc["forcing"]["surface_budget"])
        # Same geometry as the lumped path: budget changes heat, not volume.
        plain = build_mapped_replay(world, ecosystem, duration_s=60.0,
                                    maximum_cell_m=25.0)
        self.assertEqual(
            [c["volume_m3"] for c in doc["cells"]][:5],
            [c["volume_m3"] for c in plain["cells"]][:5])


if __name__ == "__main__":
    unittest.main()
