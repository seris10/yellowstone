"""FiPy reference solve against analytic and hand-rolled errors."""
from __future__ import annotations

import unittest

from yellowstone_python.replay.fipy_reference import (
    HAS_FIPY,
    LENGTH_M,
    SYNTHETIC_DISPERSION_M2_S,
    T0_C,
    analytic_temperature_c,
    hand_rolled_error_c,
    mms_analytic_temperature_c,
    run_convergence,
    run_dispersion_convergence,
    run_mms_convergence,
    solve_mms,
    solve_steady,
    solve_steady_dispersion,
)


class AnalyticProfileTests(unittest.TestCase):
    def test_upstream_value_and_downstream_decay(self):
        self.assertAlmostEqual(analytic_temperature_c(0.0), 20.0)
        self.assertAlmostEqual(analytic_temperature_c(3000.0), 12.3256,
                               places=3)

    def test_hand_rolled_error_refines(self):
        self.assertLess(hand_rolled_error_c(30), hand_rolled_error_c(15))


@unittest.skipIf(HAS_FIPY, "fipy installed")
class MissingFipyTests(unittest.TestCase):
    def test_solve_raises_guided_error(self):
        with self.assertRaises(ImportError):
            solve_steady(15)


@unittest.skipUnless(HAS_FIPY, "fipy not installed")
class FipyReferenceTests(unittest.TestCase):
    def test_outlet_matches_analytic(self):
        result = solve_steady(30)
        self.assertLess(result["max_abs_error_c"], 0.5)
        self.assertAlmostEqual(result["outlet_c"],
                               result["analytic_outlet_c"], delta=0.05)
        self.assertIn("fipy_version", result)
        self.assertEqual(result["parameters"]["discharge_m3_s"], 2.0)

    def test_error_within_hand_rolled_error(self):
        for n in (15, 30):
            # Same upwind operator; slack covers assembly roundoff.
            self.assertLessEqual(solve_steady(n)["max_abs_error_c"],
                                 hand_rolled_error_c(n) + 1e-9)

    def test_observed_rate_is_first_order(self):
        report = run_convergence((15, 30))
        (rate,) = report["observed_rates"]
        self.assertGreaterEqual(rate, 0.7)
        self.assertLessEqual(rate, 1.3)


class ReferenceMMSTests(unittest.TestCase):
    """Method of manufactured solutions driven by cell_heat_w forcing (Roache 1998 ch. 3-4).
    The analytic profile is closed by a per-cell internal heat source; hand-rolled solver only."""

    def test_mms_boundary_matches_the_profile(self):
        self.assertAlmostEqual(
            mms_analytic_temperature_c(0.0), T0_C, places=10,
        )

    def test_mms_outflow_gradient_is_zero(self):
        # Centered finite-difference check that dT/dx(L) is numerically zero.
        epsilon = 1e-3
        slope = (
            mms_analytic_temperature_c(LENGTH_M)
            - mms_analytic_temperature_c(LENGTH_M - epsilon)
        ) / epsilon
        self.assertLess(abs(slope), 1e-2)

    def test_mms_profile_decreases_through_the_midpoint(self):
        self.assertGreater(
            mms_analytic_temperature_c(0.0),
            mms_analytic_temperature_c(LENGTH_M / 2.0),
        )

    def test_solver_recovers_mms_profile_at_moderate_resolution(self):
        result = solve_mms(120)
        self.assertLess(result["max_abs_error_c"], 2.5)
        self.assertEqual(result["n_cells"], 120)
        self.assertEqual(len(result["temperatures_c"]), 120)
        # Upstream cell center sits near x=dx/2, still close to T0.
        self.assertAlmostEqual(
            result["temperatures_c"][0],
            mms_analytic_temperature_c(result["dx_m"] / 2.0),
            delta=1.0,
        )

    def test_mms_error_refines_with_resolution(self):
        coarse = solve_mms(60)["max_abs_error_c"]
        fine = solve_mms(240)["max_abs_error_c"]
        self.assertLess(fine, coarse)

    def test_mms_convergence_observed_rate_is_positive(self):
        report = run_mms_convergence((60, 240))
        (rate,) = report["observed_rates"]
        # First-order upwind on a smooth MMS source converges; a loose positive-rate bound keeps the test robust.
        self.assertGreater(rate, 0.4)
        self.assertLessEqual(rate, 2.5)


@unittest.skipUnless(HAS_FIPY, "fipy not installed")
class ReferenceDispersionTests(unittest.TestCase):
    """FiPy run with the DiffusionTerm enabled.
    Compares FiPy against the production River at the same dispersion coefficient."""

    def test_dispersion_run_matches_hand_rolled(self):
        result = solve_steady_dispersion(60)
        self.assertEqual(result["dispersion_m2_s"],
                         SYNTHETIC_DISPERSION_M2_S)
        self.assertEqual(len(result["temperatures_c"]), 60)
        self.assertLess(result["max_abs_error_vs_hand_c"], 0.5)
        self.assertIn("fipy_version", result)

    def test_dispersion_smooths_sharp_inlet_decay(self):
        with_d = solve_steady_dispersion(60)["temperatures_c"]
        without_d = solve_steady(60)["temperatures_c"]
        # Nonzero dispersion mixes the Dirichlet inlet; the upstream cell cools faster.
        self.assertLess(with_d[0], without_d[0])

    def test_dispersion_convergence_refines(self):
        report = run_dispersion_convergence((30, 60))
        errors = report["fipy_minus_hand_errors_c"]
        self.assertLess(errors[-1], errors[0] + 1e-9)


if __name__ == "__main__":
    unittest.main()
