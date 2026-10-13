"""Tests for the applicable numerics benchmarks (synthetic, offline).
Verify mathematical behavior at the declared equation level."""
from __future__ import annotations

import unittest

from yellowstone_python.replay.benchmarks import (
    NOT_APPLICABLE,
    benchmark_closed_thermal,
    benchmark_conservative_tracer,
    benchmark_diffusive_decay,
    benchmark_mms_traveling_wave,
    benchmark_restart_equivalence,
    benchmark_spatial_convergence,
    benchmark_spatial_convergence_dispersive,
    benchmark_temporal_convergence,
    benchmark_two_stream_mixing,
    run_all_benchmarks,
)


class BenchmarkTests(unittest.TestCase):
    def test_restart_equivalence(self):
        result = benchmark_restart_equivalence()
        self.assertTrue(result["passed"])
        self.assertLessEqual(result["split_run_gap_c"], 1e-9)
        self.assertLessEqual(result["fresh_object_gap_c"], 1e-9)

    def test_closed_thermal(self):
        result = benchmark_closed_thermal()
        self.assertTrue(result["passed"])
        self.assertLessEqual(result["drift_c"], 1e-9)

    def test_two_stream_mixing(self):
        result = benchmark_two_stream_mixing()
        self.assertTrue(result["passed"])
        self.assertAlmostEqual(result["steady_c"], result["expected_c"],
                               places=9)

    def test_conservative_tracer(self):
        result = benchmark_conservative_tracer()
        self.assertTrue(result["passed"])
        self.assertLess(abs(result["advection_error_pct"]), 5.0)
        self.assertLessEqual(result["heat_relative_residual"], 1e-9)

    def test_momentum_benchmarks_recorded_not_run(self):
        names = [e["benchmark"] for e in NOT_APPLICABLE]
        self.assertIn("lake_at_rest_over_variable_bed", names)
        self.assertIn("dam_break_transient", names)
        for entry in NOT_APPLICABLE:
            self.assertIn("momentum", entry["reason"])

    def test_suite_passes(self):
        document = run_all_benchmarks()
        self.assertEqual(document["schema"],
                         "yellowstone.numerics_benchmarks.v1")
        self.assertTrue(document["passed"])
        self.assertEqual(len(document["results"]), 9)

    def test_convergence_rates_are_first_order(self):
        for fn in (benchmark_temporal_convergence,
                   benchmark_spatial_convergence):
            result = fn()
            self.assertTrue(result["passed"])
            self.assertEqual(len(result["errors_c"]), 3)
            for rate in result["observed_rates"]:
                self.assertGreaterEqual(rate, 0.7)
                self.assertLessEqual(rate, 1.3)

    def test_dispersive_steady_rates_are_first_order(self):
        result = benchmark_spatial_convergence_dispersive()
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["cases"]), 2)
        for case in result["cases"]:
            self.assertEqual(len(case["errors_c"]), 3)
            for rate in case["observed_rates"]:
                self.assertGreaterEqual(rate, 0.7)
                self.assertLessEqual(rate, 1.3)

    def test_diffusive_decay_orders(self):
        result = benchmark_diffusive_decay()
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["spatial_errors_c"]), 3)
        for rate in result["spatial_rates"]:
            self.assertGreaterEqual(rate, 1.5)
            self.assertLessEqual(rate, 2.5)
        self.assertEqual(len(result["temporal_errors_c"]), 3)
        for rate in result["temporal_rates"]:
            self.assertGreaterEqual(rate, 0.7)
            self.assertLessEqual(rate, 1.3)

    def test_mms_wave_rates_are_first_order(self):
        result = benchmark_mms_traveling_wave()
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["spatial_errors_c"]), 3)
        for rate in result["spatial_rates"]:
            self.assertGreaterEqual(rate, 0.7)
            self.assertLessEqual(rate, 1.3)
        self.assertEqual(len(result["temporal_errors_c"]), 3)
        for rate in result["temporal_rates"]:
            self.assertGreaterEqual(rate, 0.7)
            self.assertLessEqual(rate, 1.3)
        self.assertLessEqual(result["heat_relative_residual"], 1e-9)


if __name__ == "__main__":
    unittest.main()
