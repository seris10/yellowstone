"""FiPy reference solve against analytic and hand-rolled errors."""
from __future__ import annotations

import unittest

from yellowstone_python.replay.fipy_reference import (
    HAS_FIPY,
    analytic_temperature_c,
    hand_rolled_error_c,
    run_convergence,
    solve_steady,
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


if __name__ == "__main__":
    unittest.main()
