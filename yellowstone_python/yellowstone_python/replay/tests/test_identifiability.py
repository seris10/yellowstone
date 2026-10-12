"""Tests for hydraulic identifiability diagnostics and surface spread."""
import importlib.util
import unittest

from yellowstone_python.replay.identifiability import (
    DEPENDENCE_POLICY,
    PARAM_NAMES,
    conditioning,
    jacobian_at_truth,
    multistart_fit,
    residual_against_truth,
    run_diagnostics,
    structural_surface_spread,
)

HAS_SALIB = importlib.util.find_spec("SALib") is not None


class IdentifiabilityTests(unittest.TestCase):
    def test_residual_zero_at_truth(self):
        truth = {"manning_n": 0.035, "bank_slope_zh": 1.5,
                 "depth_m": 1.1}
        residuals = residual_against_truth(
            [truth[name] for name in PARAM_NAMES])
        self.assertEqual(len(residuals), 3)
        for value in residuals:
            self.assertAlmostEqual(value, 0.0, places=12)

    def test_jacobian_is_rank_deficient(self):
        report = conditioning(jacobian_at_truth())
        self.assertLess(report["rank"], report["n_params"])
        self.assertEqual(report["param_names"], list(PARAM_NAMES))
        self.assertEqual(len(report["null_directions"]),
                         report["n_params"] - report["rank"])

    def test_multistart_fits_spread_along_ridge(self):
        report = multistart_fit()
        self.assertLess(report["max_cost"], 1e-12)
        self.assertTrue(all(run["success"] for run in report["runs"]))
        self.assertGreater(max(report["relative_spread"].values()),
                           0.2)

    def test_structural_spread_closes_budgets(self):
        report = structural_surface_spread()
        self.assertTrue(report["budgets_ok"])
        self.assertGreater(report["max_abs_gap_c"], 0.005)
        self.assertLess(report["max_abs_gap_c"], 0.3)
        self.assertIn("not_prediction_interval", report["status"])

    def test_dependence_policy_names_gate(self):
        self.assertIn("manning_n",
                      DEPENDENCE_POLICY["varied_independently"])
        self.assertIn("salib_gate", DEPENDENCE_POLICY)

    def test_full_document(self):
        document = run_diagnostics()
        self.assertEqual(document["schema"],
                         "yellowstone.identifiability.v1")
        self.assertIn("conditioning", document)
        self.assertIn("multistart", document)
        self.assertIn("structural_surface", document)

    @unittest.skipUnless(HAS_SALIB, "SALib not installed")
    def test_sobol_screen_runs_on_ratio_residual(self):
        from yellowstone_python.replay.identifiability import sobol_screen
        report = sobol_screen(n_base=64, seed=11)
        self.assertEqual(report["param_names"], list(PARAM_NAMES))
        self.assertEqual(report["n_eval"], 64 * (2 * len(PARAM_NAMES) + 2))
        for key in ("S1", "ST", "S1_conf", "ST_conf"):
            self.assertEqual(len(report[key]), len(PARAM_NAMES))
            for value in report[key]:
                self.assertTrue(value == value)
        self.assertGreater(report["ST"][2], report["ST"][1])
        self.assertGreater(report["ST"][2], 0.3)


if __name__ == "__main__":
    unittest.main()
