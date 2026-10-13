import math
import unittest

from yellowstone_python.replay.hydraulics import (
    TrapezoidGeometry,
    bed_shear_pa,
    cell_hydraulics,
    fischer_dispersion_m2_s,
    froude_number,
    manning_velocity_m_s,
    rectangular_area_m2,
    residual_diagnostics,
    score_paired_series,
    shear_velocity_m_s,
    skill_scores,
    slope_from_drop,
    thermal_inventory,
    travel_time_s,
)
from yellowstone_python.replay.river_world import build_mapped_replay

# Fixed replay epoch so the clock is deterministic across runs.
REPLAY_START = {"simulation_start_epoch_unix": 1784000000.0}


class TrapezoidTests(unittest.TestCase):
    def test_rectangular_limit(self):
        g = TrapezoidGeometry(10.0, 2.0, 0.0)
        self.assertAlmostEqual(g.area_m2, 20.0)
        self.assertAlmostEqual(g.wetted_perimeter_m, 14.0)
        self.assertAlmostEqual(g.bottom_width_m, 10.0)

    def test_trapezoid_handcalc(self):
        # W=10, d=2, z=1: b=6, A=(10-2)*2=16, P=6+4*sqrt2
        g = TrapezoidGeometry(10.0, 2.0, 1.0)
        self.assertAlmostEqual(g.bottom_width_m, 6.0)
        self.assertAlmostEqual(g.area_m2, 16.0)
        self.assertAlmostEqual(g.wetted_perimeter_m, 6.0 + 4.0 * math.sqrt(2.0))
        self.assertAlmostEqual(g.hydraulic_depth_m, 1.6)

    def test_banks_meeting_rejected(self):
        with self.assertRaises(ValueError):
            TrapezoidGeometry(3.0, 2.0, 1.0)  # b = 3-4 < 0
        with self.assertRaises(ValueError):
            TrapezoidGeometry(10.0, -1.0, 1.0)

    def test_rectangular_area_legacy(self):
        self.assertAlmostEqual(rectangular_area_m2(22.0, 1.1), 24.2)


class ManningTests(unittest.TestCase):
    def test_manning_handcalc(self):
        v = manning_velocity_m_s(1.0, 0.01, 0.05)
        self.assertAlmostEqual(v, (1.0 / 0.05) * 1.0 * math.sqrt(0.01))

    def test_manning_rejects_flat_grade(self):
        with self.assertRaises(ValueError):
            manning_velocity_m_s(1.0, 0.0)
        with self.assertRaises(ValueError):
            manning_velocity_m_s(1.0, -0.001)

    def test_froude_critical(self):
        h = 1.0
        v_crit = math.sqrt(9.81 * h)
        self.assertAlmostEqual(froude_number(v_crit, h), 1.0, places=9)

    def test_shear_and_ustar_consistent(self):
        tau = bed_shear_pa(1.0, 0.01)
        self.assertAlmostEqual(tau, 1000.0 * 9.81 * 1.0 * 0.01)
        self.assertAlmostEqual(shear_velocity_m_s(1.0, 0.01),
                               math.sqrt(9.81 * 1.0 * 0.01))

    def test_fischer_positive_and_guarded(self):
        d = fischer_dispersion_m2_s(1.0, 20.0, 0.5, 0.1)
        self.assertAlmostEqual(d, 0.011 * 1.0 * 400.0 / (0.5 * 0.1))
        with self.assertRaises(ValueError):
            fischer_dispersion_m2_s(1.0, 20.0, 0.5, 0.0)

    def test_travel_time(self):
        self.assertAlmostEqual(travel_time_s(100.0, 2.0), 50.0)
        with self.assertRaises(ValueError):
            travel_time_s(100.0, 0.0)

    def test_slope_from_drop(self):
        self.assertAlmostEqual(slope_from_drop(2.0, 1000.0), 0.002)


class CellHydraulicsTests(unittest.TestCase):
    def test_positive_grade_full_diagnostics(self):
        h = cell_hydraulics(20.0, 10.0, 1.0, 5.0, 0.002)
        self.assertGreater(h["area_rect_m2"], h["area_trap_m2"])
        self.assertGreater(h["rectangular_bias_pct"], 0.0)
        self.assertAlmostEqual(h["velocity_continuity_m_s"],
                               5.0 / h["area_trap_m2"])
        self.assertIsNotNone(h["velocity_manning_m_s"])
        self.assertIsNotNone(h["fischer_dispersion_m2_s"])
        self.assertIsNotNone(h["travel_time_s"])
        self.assertIn("bank_slope_zh", h["provenance"])
        self.assertEqual(h["provenance"]["manning_n"],
                         "authored_illustrative_not_calibrated")

    def test_flat_grade_leaves_manning_undefined(self):
        for slope in (None, 0.0, -0.001):
            h = cell_hydraulics(20.0, 10.0, 1.0, 5.0, slope)
            self.assertIsNone(h["velocity_manning_m_s"])
            self.assertIsNone(h["fischer_dispersion_m2_s"])
            self.assertIsNone(h["manning_consistency_ratio"])
            self.assertIn("flat_or_adverse_grade_manning_undefined",
                          h["warnings"])
            # Continuity diagnostics still defined.
            self.assertGreater(h["velocity_continuity_m_s"], 0.0)
            self.assertIsNotNone(h["travel_time_s"])


class ScoringTests(unittest.TestCase):
    def test_rmse_bias_handcalc(self):
        s = score_paired_series([1.0, 2.0, 3.0], [1.0, 2.0, 4.0])
        self.assertAlmostEqual(s["bias"], -1.0 / 3.0)
        self.assertAlmostEqual(s["rmse"], math.sqrt(1.0 / 3.0))
        self.assertAlmostEqual(s["mae"], 1.0 / 3.0)
        self.assertAlmostEqual(s["max_abs"], 1.0)
        self.assertEqual(s["n"], 3.0)

    def test_rejections(self):
        with self.assertRaises(ValueError):
            score_paired_series([], [])
        with self.assertRaises(ValueError):
            score_paired_series([1.0], [1.0, 2.0])
        with self.assertRaises(ValueError):
            score_paired_series([float("nan")], [1.0])

    def test_thermal_inventory(self):
        inv = thermal_inventory([
            {"id": "a", "flow_m3_s": 1.0, "temperature_c": 60.0,
             "status": "measured"},
            {"id": "b", "flow_m3_s": 3.0, "temperature_c": 20.0,
             "status": "authored"},
        ])
        self.assertAlmostEqual(inv["total_thermal_flow_m3_s"], 4.0)
        self.assertAlmostEqual(inv["flow_weighted_entry_c"], 30.0)
        self.assertEqual(inv["n_sources"], 2)

    def test_thermal_inventory_excludes_scheduled_temps(self):
        # Regression: pulse sources carry Series dicts; scheduled interventions are listed and excluded from the single-value mean.
        inv = thermal_inventory([
            {"id": "a", "flow_m3_s": 1.0, "temperature_c": 60.0,
             "status": "measured"},
            {"id": "pulse", "flow_m3_s": 0.5,
             "temperature_c": {"times_s": [0.0, 1.0], "values": [60.0, 80.0]},
             "status": "synthetic_intervention"},
        ])
        self.assertEqual(inv["n_scheduled_sources"], 1)
        self.assertAlmostEqual(inv["total_thermal_flow_m3_s"], 1.5)
        self.assertAlmostEqual(inv["flow_weighted_entry_c"], 60.0)
        self.assertTrue(inv["sources"][1]["scheduled"])
        self.assertIsNone(inv["sources"][1]["temperature_c"])


def _sloped_world():
    # Steady 2 m drop over 100 m: slope 0.02 everywhere.
    return {
        "georeference": {"note": "test"},
        "rivers": [{
            "id": "seg_a",
            "name": "FIREHOLE RIVER",
            "width": 10.0,
            "endpoint_node_ids": ["n0", "n1"],
            "points": [[0, 2, 100], [0, 0, 0]],
        }],
    }, {
        "boundary_m3s": 5.0,
        "boundary_c": 15.0,
        "clock_hour": 12.0,
        "weather": {},
        "river_reaches": [],
    }


class MappedHydraulicsTests(unittest.TestCase):
    def test_diagnostics_present_volumes_unchanged(self):
        world, ecosystem = _sloped_world()
        doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=120.0,
                                  maximum_cell_m=25.0)
        self.assertIn("hydraulics_summary", doc)
        self.assertIn("thermal_inventory",
                      doc["hydraulics_summary"])
        for record in doc["cells"]:
            hydro = record["hydraulics"]
            # Solver volume still rectangular.
            self.assertAlmostEqual(
                record["volume_m3"],
                record["length_m"] * record["width_m"] * record["depth_m"])
            self.assertGreater(hydro["rectangular_bias_pct"], 0.0)
            self.assertAlmostEqual(hydro["slope"], 0.02, places=9)
            self.assertIsNotNone(hydro["velocity_manning_m_s"])
            self.assertIsNotNone(hydro["travel_time_s"])
        total = doc["hydraulics_summary"]["total_travel_time_s"]
        parts = sum(r["hydraulics"]["travel_time_s"] for r in doc["cells"])
        self.assertAlmostEqual(total, parts)
        self.assertTrue(doc["numerical_checks"]["passed"])

    def test_flat_world_warns_without_failing(self):
        world = {
            "georeference": {"note": "test"},
            "rivers": [{
                "id": "seg_a",
                "name": "FIREHOLE RIVER",
                "width": 10.0,
                "endpoint_node_ids": ["n0", "n1"],
                "points": [[0, 0, 100], [0, 0, 0]],
            }],
        }
        _, ecosystem = _sloped_world()
        doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                                  maximum_cell_m=200.0)
        for record in doc["cells"]:
            self.assertIn("flat_or_adverse_grade_manning_undefined",
                          record["hydraulics"]["warnings"])
            self.assertIsNone(
                record["hydraulics"]["velocity_manning_m_s"])
        self.assertTrue(doc["numerical_checks"]["passed"])


class SkillTests(unittest.TestCase):
    def test_perfect_scores(self):
        series = [10.0 + 0.5 * i for i in range(20)]
        skill = skill_scores(series, series)
        self.assertAlmostEqual(skill["nse"], 1.0)
        self.assertAlmostEqual(skill["kge"], 1.0)
        self.assertAlmostEqual(skill["correlation"], 1.0)

    def test_mean_model_scores_zero_nse(self):
        observed = [10.0 + 0.5 * i for i in range(20)]
        mean = sum(observed) / len(observed)
        skill = skill_scores([mean] * 20, observed)
        self.assertAlmostEqual(skill["nse"], 0.0)
        self.assertIsNone(skill["kge"])
        self.assertTrue(skill["constant_modeled"])

    def test_kge_degrades_with_bias(self):
        observed = [10.0 + 0.5 * i for i in range(20)]
        biased = [v + 2.0 for v in observed]
        self.assertLess(skill_scores(biased, observed)["kge"],
                        skill_scores(observed, observed)["kge"])

    def test_skill_rejects_degenerate(self):
        with self.assertRaises(ValueError):
            skill_scores([1.0] * 10, [1.0] * 10)
        with self.assertRaises(ValueError):
            skill_scores([1.0, 2.0], [1.0])
        with self.assertRaises(ValueError):
            skill_scores([], [])


class ResidualTests(unittest.TestCase):
    def test_perfect_fit_flag(self):
        series = [10.0 + 0.1 * i for i in range(15)]
        diag = residual_diagnostics(series, series)
        self.assertTrue(diag["perfect_fit"])
        self.assertEqual(diag["max_qq_gap"], 0.0)

    def test_autocorr_recovers_ar1(self):
        import random
        rng = random.Random(20261010)
        resid = [0.0]
        for _ in range(400):
            resid.append(0.7 * resid[-1] + rng.gauss(0.0, 1.0))
        observed = [10.0] * 401
        modeled = [o + r for o, r in zip(observed, resid)]
        diag = residual_diagnostics(modeled, observed)
        self.assertAlmostEqual(diag["autocorr"][1], 0.7, delta=0.1)
        self.assertGreater(diag["autocorr"][1], diag["autocorr"][5])

    def test_qq_small_gap_on_gaussian(self):
        import random
        rng = random.Random(7)
        noise = [rng.gauss(0.0, 2.0) for _ in range(500)]
        observed = [15.0] * 500
        modeled = [o + e for o, e in zip(observed, noise)]
        diag = residual_diagnostics(modeled, observed)
        self.assertLess(diag["max_qq_gap"], 0.3)

    def test_residuals_reject_bad(self):
        with self.assertRaises(ValueError):
            residual_diagnostics([1.0], [1.0])
        with self.assertRaises(ValueError):
            residual_diagnostics([1.0, 2.0], [1.0])
        with self.assertRaises(ValueError):
            residual_diagnostics([1.0, 2.0, 3.0], [1.0, 2.0, 3.0],
                                 max_lag=3)


if __name__ == "__main__":
    unittest.main()
