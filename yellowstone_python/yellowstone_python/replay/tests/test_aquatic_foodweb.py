"""Tests for the aquatic vertical slice (all synthetic, offline).

Literature-anchor tests pin transferred values; mechanism tests prove
the coupling direction (heat -> prey -> refuge); ledger tests prove
accounting. No network, no midway data files.
"""
from __future__ import annotations

import unittest

from yellowstone_python.aquatic_foodweb import (
    TRIBUTARY_CANDIDATES,
    TRIBUTARY_FOOD_SCALE_DEFAULT,
    append_tributary_cells,
    build_tributary_cell,
    compare_runs,
    run_foodweb,
    shear_to_disturbance,
    thermal_landscape,
    unwrap_replay,
)
from yellowstone_python.fish import THERMAL_SPECIES, thermal_performance
from yellowstone_python.insects_birds import (
    INSECT_GROUPS,
    develop_benthic,
    trout_diet_at_temp,
)


def fake_replay(temps_by_frame, n_cells=5):
    cells = [{
        "id": f"cell_{i:03d}", "river_id": "test_river",
        "center_s_m": i * 100.0, "start_s_m": i * 100.0,
        "end_s_m": (i + 1) * 100.0,
        "width_m": 20.0, "depth_m": 0.5,
        "representative_velocity_m_s": 0.5,
        "volume_m3": 100.0 * 20.0 * 0.5,
    } for i in range(n_cells)]
    frames = [{"t_s": k * 60.0, "temperature_c": list(temps)}
              for k, temps in enumerate(temps_by_frame)]
    return {"cells": cells, "frames": frames}


class PerformanceAnchorTests(unittest.TestCase):
    def test_brown_anchors(self):
        self.assertEqual(
            thermal_performance(14.0, "brown_trout")["feeding"], 1.0)
        self.assertEqual(
            thermal_performance(20.5, "brown_trout")["feeding"], 0.0)
        self.assertEqual(
            thermal_performance(21.0, "brown_trout")["refuge_drive"], 0.0)
        self.assertEqual(
            thermal_performance(24.5, "brown_trout")["refuge_drive"], 1.0)
        self.assertEqual(
            thermal_performance(27.0, "brown_trout")["lethal_flag"], 1)
        self.assertEqual(
            thermal_performance(20.0, "brown_trout")["lethal_flag"], 0)

    def test_rainbow_more_tolerant_than_brown(self):
        brown = thermal_performance(20.0, "brown_trout")["feeding"]
        rainbow = thermal_performance(20.0, "rainbow_trout")["feeding"]
        self.assertEqual(brown, 0.0)
        self.assertGreater(rainbow, 0.0)
        self.assertEqual(
            thermal_performance(16.0, "rainbow_trout")["feeding"], 1.0)

    def test_species_table_carries_provenance(self):
        for species, spec in THERMAL_SPECIES.items():
            self.assertTrue(spec["sources"])
            self.assertIn("transferred", spec["status"])

    def test_unknown_species_rejected(self):
        with self.assertRaises(ValueError):
            thermal_performance(15.0, "cutthroat_trout")

    def test_hot_water_never_ties_at_zero_weight(self):
        # Regression (review F1): above feed_zero, feeding saturates at 0,
        # so without the stress gradient every hot cell tied and ties
        # broke toward the hottest water. Coolest must win at any weight.
        from yellowstone_python.fish import suitability
        for weight in (0.0, 0.6, 2.0):
            scored = sorted((
                suitability(0.5, 0.6, t, 0.5, 0.5, species="brown_trout",
                            refuge_weight=weight), t)
                for t in (23.0, 24.5, 26.0))
            self.assertEqual(scored[-1][1], 23.0)


class InsectGroupTests(unittest.TestCase):
    def test_groups_carry_provenance(self):
        for group, params in INSECT_GROUPS.items():
            self.assertTrue(params["sources"])
            self.assertIn("transferred", params["status"])

    def test_group_table_ordering(self):
        # Table-level claim: dipterans start later, develop faster, and
        # tolerate more heat than EPT fauna.
        ept, dipt = INSECT_GROUPS["ept"], INSECT_GROUPS["dipteran"]
        self.assertGreater(dipt["tbase_c"], ept["tbase_c"])
        self.assertGreater(dipt["rate_per_dd"], ept["rate_per_dd"])
        self.assertGreater(dipt["t_cutoff_c"], ept["t_cutoff_c"])

    def test_group_ordering_and_cutoff(self):
        e = INSECT_GROUPS["ept"]
        d = INSECT_GROUPS["dipteran"]
        _, warm_ept = develop_benthic(0.5, 18.0, 86400.0, tbase=e["tbase_c"],
                                      rate=e["rate_per_dd"],
                                      t_cutoff=e["t_cutoff_c"])
        _, warm_dipt = develop_benthic(0.5, 18.0, 86400.0, tbase=d["tbase_c"],
                                       rate=d["rate_per_dd"],
                                       t_cutoff=d["t_cutoff_c"])
        self.assertGreater(warm_dipt, warm_ept)
        _, cold_ept = develop_benthic(0.5, 6.0, 86400.0, tbase=e["tbase_c"],
                                      rate=e["rate_per_dd"],
                                      t_cutoff=e["t_cutoff_c"])
        _, cold_dipt = develop_benthic(0.5, 6.0, 86400.0, tbase=d["tbase_c"],
                                       rate=d["rate_per_dd"],
                                       t_cutoff=d["t_cutoff_c"])
        self.assertGreater(cold_ept, cold_dipt)
        _, stupor = develop_benthic(0.5, 24.0, 86400.0, tbase=e["tbase_c"],
                                    rate=e["rate_per_dd"],
                                    t_cutoff=e["t_cutoff_c"])
        self.assertEqual(stupor, 0.0)
        # Legacy path (no cutoff) still emerges at 24 C.
        _, legacy = develop_benthic(0.5, 24.0, 86400.0)
        self.assertGreater(legacy, 0.0)

    def test_diet_shifts_to_emergers_when_warm(self):
        cold = trout_diet_at_temp(10.0)
        warm = trout_diet_at_temp(25.0)
        self.assertGreater(cold["benthic"], cold["emergent"])
        self.assertGreater(warm["emergent"], warm["benthic"])
        self.assertAlmostEqual(cold["benthic"] + cold["emergent"], 1.0)
        self.assertAlmostEqual(warm["benthic"] + warm["emergent"], 1.0)


class FoodwebMechanismTests(unittest.TestCase):
    def test_refuge_seeks_cool_water(self):
        doc = fake_replay([[14.0, 16.0, 18.0, 22.0, 26.0]] * 3)
        out = run_foodweb(thermal_landscape(doc), days=4.0)
        self.assertLessEqual(out["trout"]["temperature_c"], 18.0)
        self.assertEqual(out["trout"]["refuge_drive"], 0.0)
        self.assertEqual(out["status"], "illustrative_not_calibrated")

    def test_hot_landscape_drives_refuge_and_flags(self):
        doc = fake_replay([[25.5, 26.0, 26.5, 27.5, 28.0]] * 3)
        out = run_foodweb(thermal_landscape(doc), days=2.0)
        self.assertEqual(out["trout"]["refuge_drive"], 1.0)
        self.assertIn("lethal", str(out["trout"]["thermal_performance"]))

    def test_ledger_and_stocks_sane(self):
        doc = fake_replay([[16.0] * 5] * 3)
        out = run_foodweb(thermal_landscape(doc), days=7.0)
        totals = out["prey_totals"]
        self.assertGreater(totals["emergence"], 0.0)
        self.assertGreaterEqual(totals["regrowth"], 0.0)
        self.assertGreaterEqual(totals["trout_eaten"], 0.0)
        self.assertGreaterEqual(totals["dipper_eaten"], 0.0)
        for row in out["per_cell"]:
            self.assertGreaterEqual(row["ept"], 0.0)
            self.assertGreaterEqual(row["dipt"], 0.0)
            self.assertGreaterEqual(row["ne"], 0.0)

    def test_warming_moves_refuge_upstream(self):
        # Control refuge sits mid-reach; a downstream heat plume makes the
        # tail uninhabitable and the refuge jumps upstream of it.
        control = fake_replay(
            [[16.0, 15.0, 14.0, 15.0, 16.0]] * 3)
        warm = fake_replay(
            [[16.0, 15.0, 16.0, 24.0, 27.0]] * 3)
        cmp = compare_runs(control, warm, days=4.0)
        self.assertLess(cmp["refuge_shift_m"], 0.0)
        self.assertLessEqual(cmp["pulse"]["temperature_c"], 16.0)
        self.assertEqual(cmp["pulse"]["refuge_drive"], 0.0)

    def test_window_and_wrapper_handling(self):
        doc = fake_replay([[15.0] * 5] * 5)
        full = thermal_landscape(doc)
        part = thermal_landscape(doc, t_min_s=60.0, t_max_s=120.0)
        self.assertEqual(len(full), len(part))
        wrapped = thermal_landscape({"replay": doc})
        self.assertEqual(len(wrapped), 5)
        with self.assertRaises(ValueError):
            thermal_landscape(doc, t_min_s=99999.0)
        with self.assertRaises(ValueError):
            unwrap_replay({"nope": True})
        with self.assertRaises(ValueError):
            run_foodweb([])


class ShearDisturbanceTests(unittest.TestCase):
    def test_ramp_shape_and_nulls(self):
        self.assertEqual(shear_to_disturbance(None, 20.0), 0.0)
        self.assertEqual(shear_to_disturbance(15.0, None), 0.0)
        self.assertEqual(shear_to_disturbance(15.0, 20.0), 0.0)
        self.assertEqual(shear_to_disturbance(20.0, 20.0), 0.0)
        self.assertAlmostEqual(shear_to_disturbance(30.0, 20.0), 0.5)
        self.assertEqual(shear_to_disturbance(40.0, 20.0), 1.0)
        self.assertEqual(shear_to_disturbance(400.0, 20.0), 1.0)
        for bad in ((-1.0, 20.0), (15.0, 0.0), (15.0, -5.0),
                    (float("nan"), 20.0), (15.0, float("inf"))):
            with self.assertRaises(ValueError):
                shear_to_disturbance(*bad)

    def test_default_threshold_leaves_disturbance_free_behavior(self):
        doc = fake_replay([[15.0] * 5] * 8)
        land = thermal_landscape(doc)
        for cell in land:
            cell["shear_pa"] = 15.08  # mapped reach-uniform value
        default = run_foodweb(land)
        off = run_foodweb(land, shear_disturb_pa=None)
        legacy = run_foodweb(
            [{k: v for k, v in cell.items() if k != "shear_pa"}
             for cell in land])
        self.assertEqual(default["prey_totals"], off["prey_totals"])
        self.assertEqual(default["prey_totals"], legacy["prey_totals"])
        self.assertEqual(default["trout"]["cell_id"],
                         legacy["trout"]["cell_id"])

    def test_lower_threshold_suppresses_emergence(self):
        doc = fake_replay([[15.0] * 5] * 8)
        land = thermal_landscape(doc)
        for cell in land:
            cell["shear_pa"] = 15.08
        calm = run_foodweb(land, shear_disturb_pa=20.0)
        rough = run_foodweb(land, shear_disturb_pa=10.0)
        self.assertLess(rough["prey_totals"]["emergence"],
                        calm["prey_totals"]["emergence"])
        self.assertIn("shear_coupling", rough["provenance"])

    def test_shear_null_cells_run_clean(self):
        doc = fake_replay([[15.0] * 5] * 8)
        land = thermal_landscape(doc)
        for cell in land:
            cell["shear_pa"] = None  # Manning-undefined cells
        result = run_foodweb(land, shear_disturb_pa=10.0)
        self.assertGreater(result["prey_totals"]["emergence"], 0.0)


class TributaryRefugeTests(unittest.TestCase):
    def test_candidates_below_refuge_threshold_with_provenance(self):
        self.assertEqual(len(TRIBUTARY_CANDIDATES), 2)
        seen = set()
        for spec in TRIBUTARY_CANDIDATES:
            self.assertLess(spec["temperature_c"], 24.0)
            self.assertGreaterEqual(spec["confluence_s_m"], 0.0)
            self.assertIn("authored", spec["temperature_provenance"])
            self.assertIn("map_measured", spec["confluence_provenance"])
            self.assertNotIn(spec["cell_id"], seen)
            seen.add(spec["cell_id"])

    def test_append_returns_new_list_with_provenance(self):
        doc = fake_replay([[16.0] * 5] * 3)
        land = thermal_landscape(doc)
        out = append_tributary_cells(land)
        self.assertEqual(len(out), len(land) + 2)
        self.assertEqual(len(land), 5)  # input not mutated
        for cell in out[-2:]:
            self.assertEqual(cell["river_id"], "tributary")
            self.assertIsNone(cell["shear_pa"])
            self.assertEqual(cell["food_scale"],
                             TRIBUTARY_FOOD_SCALE_DEFAULT)
            self.assertIn("tributary_provenance", cell)

    def test_builder_rejects_bad_scales_and_temps(self):
        spec = TRIBUTARY_CANDIDATES[0]
        for bad in (-0.1, float("nan"), float("inf"), None):
            with self.assertRaises(ValueError):
                build_tributary_cell(spec, food_scale=bad)
        with self.assertRaises(ValueError):
            build_tributary_cell(spec, temperature_c=float("nan"))
        # food_scale 0 is allowed (starvation-pocket edge case).
        zero = build_tributary_cell(spec, food_scale=0.0)
        self.assertEqual(zero["food_scale"], 0.0)

    def test_food_scale_default_reproduces_unscaled_behavior(self):
        doc = fake_replay([[15.0] * 5] * 8)
        land = thermal_landscape(doc)
        plain = run_foodweb(land)
        scaled = run_foodweb(
            [{**cell, "food_scale": 1.0} for cell in land])
        self.assertEqual(scaled["prey_totals"], plain["prey_totals"])
        self.assertEqual(scaled["trout"]["cell_id"],
                         plain["trout"]["cell_id"])

    def test_food_scale_downranks_but_cold_still_wins_when_hot(self):
        # Hot mainstem (all > 24 C, drive firing) plus one cold pocket
        # at 1/20th food: the pocket must win on thermal + refuge terms.
        doc = fake_replay([[26.0, 26.5, 27.0, 27.5, 28.0]] * 3)
        land = thermal_landscape(doc)
        pocket = build_tributary_cell(
            {**TRIBUTARY_CANDIDATES[0], "temperature_c": 11.0},
            food_scale=TRIBUTARY_FOOD_SCALE_DEFAULT)
        out = run_foodweb(land + [pocket], days=4.0)
        self.assertEqual(out["trout"]["cell_id"], pocket["id"])
        self.assertEqual(out["trout"]["refuge_drive"], 0.0)

    def test_starved_pocket_loses_to_cool_mainstem(self):
        # food_scale 0 pocket vs comfortable 16 C mainstem: the model
        # must prefer real food — food still matters, cold is not a
        # free win.
        doc = fake_replay([[16.0] * 5] * 3)
        land = thermal_landscape(doc)
        pocket = build_tributary_cell(
            {**TRIBUTARY_CANDIDATES[0], "temperature_c": 11.0},
            food_scale=0.0)
        out = run_foodweb(land + [pocket], days=4.0)
        self.assertFalse(out["trout"]["cell_id"].startswith("trib_"))

    def test_compare_runs_appends_extra_cells_to_both(self):
        control = fake_replay([[16.0] * 5] * 3)
        hot = fake_replay([[27.0] * 5] * 3)
        extra = [build_tributary_cell(TRIBUTARY_CANDIDATES[0])]
        cmp = compare_runs(control, hot, extra_cells=extra, days=4.0)
        self.assertEqual(cmp["pulse"]["cell_id"], extra[0]["id"])
        self.assertIn("trib_", cmp["landscape_window"])
        # Without the pocket the hot run holds mainstem water.
        cmp0 = compare_runs(control, hot, days=4.0)
        self.assertFalse(cmp0["pulse"]["cell_id"].startswith("trib_"))


if __name__ == "__main__":
    unittest.main()
