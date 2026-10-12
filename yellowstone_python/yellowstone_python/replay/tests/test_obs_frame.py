"""Tests for pandas obs-frame alignment (B1).

All synthetic and offline. Requires pandas, which is NOT installed on
the project interpreter: the whole module skips there and runs where
pandas exists (validated in a contained venv). The skip is the honest
state, not a hole — the pairs path stays the default until pandas is
installed (see obs_frame module docstring).
"""
from __future__ import annotations

import importlib.util
import math
import time
import unittest

HAS_PANDAS = importlib.util.find_spec("pandas") is not None


@unittest.skipUnless(HAS_PANDAS, "pandas not installed")
class FrameTests(unittest.TestCase):
    def test_frame_bins_and_coverage(self):
        from yellowstone_python.replay.obs_frame import (
            _frame_from_pairs,
            gap_report,
        )
        t0 = 1_700_000_000
        # 10 obs on a 900 s cadence with one bin skipped.
        pairs = [[float(t0 + i * 900), 10.0 + i] for i in range(5)]
        pairs += [[float(t0 + i * 900), 10.0 + i] for i in range(6, 10)]
        frame = _frame_from_pairs(pairs, "test", 900.0)
        report = gap_report(frame, "test")
        self.assertEqual(report["n_expected"], 10)
        self.assertEqual(report["n_filled"], 9)
        self.assertAlmostEqual(report["coverage"], 0.9)
        self.assertEqual(len(report["gaps"]), 1)
        self.assertEqual(report["gaps"][0]["steps"], 1)
        self.assertEqual(report["worst_gap_steps"], 1)

    def test_frame_averages_shared_bins(self):
        from yellowstone_python.replay.obs_frame import _frame_from_pairs
        t0 = 1_700_000_000
        pairs = [[float(t0), 10.0], [float(t0 + 100), 20.0],
                 [float(t0 + 900), 30.0]]
        frame = _frame_from_pairs(pairs, "test", 900.0)
        self.assertAlmostEqual(frame["value"].iloc[0], 15.0)
        self.assertAlmostEqual(frame["value"].iloc[1], 30.0)

    def test_frame_rejects_bad(self):
        from yellowstone_python.replay.obs_frame import _frame_from_pairs
        with self.assertRaises(ValueError):
            _frame_from_pairs([], "empty", 900.0)
        with self.assertRaises(ValueError):
            _frame_from_pairs([[0.0, 1.0]], "x", 0.0)

    def test_coverable_refuses_long_gap(self):
        from yellowstone_python.replay.obs_frame import (
            _frame_from_pairs,
            assert_coverable,
            gap_report,
        )
        t0 = 1_700_000_000
        pairs = [[float(t0), 1.0], [float(t0 + 6 * 900), 2.0]]
        report = gap_report(_frame_from_pairs(pairs, "gappy", 900.0),
                            "gappy")
        self.assertEqual(report["worst_gap_steps"], 5)
        with self.assertRaises(ValueError) as ctx:
            assert_coverable(report)
        self.assertIn("gappy", str(ctx.exception))
        assert_coverable(report, max_gap_steps=5)  # explicit pass

    def test_bridge_limit_direction(self):
        from yellowstone_python.replay.obs_frame import (
            _frame_from_pairs,
            bridge,
        )
        t0 = 1_700_000_000
        pairs = [[float(t0 + i * 900), float(i)] for i in
                 [0, 1, 2, 8, 9, 10]]
        frame = _frame_from_pairs(pairs, "test", 900.0)
        filled = bridge(frame, limit=2)
        # 5-step gap with per-side limit 2: filled from both ends,
        # middle survives.
        self.assertEqual(int(filled["value"].isna().sum()), 1)
        filled5 = bridge(frame, limit=5)
        self.assertEqual(int(filled5["value"].isna().sum()), 0)

    def test_to_grid_exact_on_knots_and_refuses_outside(self):
        from yellowstone_python.replay.obs_frame import (
            _frame_from_pairs,
            bridge,
            to_grid,
        )
        t0 = 1_700_000_000
        pairs = [[float(t0 + i * 900), 10.0 + i] for i in range(6)]
        frame = bridge(_frame_from_pairs(pairs, "test", 900.0))
        grid = [float(t0), float(t0 + 450), float(t0 + 5 * 900)]
        self.assertAlmostEqual(to_grid(frame, grid, "test")[1], 10.5)
        with self.assertRaises(ValueError):
            to_grid(frame, [float(t0 - 3600)], "test")

    def test_rolling_and_daily_means(self):
        from yellowstone_python.replay.obs_frame import (
            daily_met_means,
            met_frame,
            rolling_mean,
        )
        # Midnight-aligned start: 48 hourly rows span 2 calendar days.
        t0 = 1_700_000_000 - (1_700_000_000 % 86400)
        rows = [[float(t0 + i * 3600), 10.0, 0.5, 2.0,
                 100.0, 0.2] for i in range(48)]
        frame = met_frame(rows)
        self.assertEqual(list(frame.columns),
                         ["air_c", "rh", "wind_mps", "shortwave_w_m2",
                          "cloud"])
        rolled = rolling_mean(frame[["air_c"]], 4)
        self.assertAlmostEqual(rolled["air_c"].iloc[3], 10.0)
        daily = daily_met_means(frame)
        self.assertEqual(len(daily["air_c"]), 2)
        with self.assertRaises(ValueError):
            rolling_mean(frame, 0)


@unittest.skipUnless(HAS_PANDAS, "pandas not installed")
class AlignedArraysTests(unittest.TestCase):
    @staticmethod
    def _synthetic():
        # Upstream pairs at the nominal IV step (900 s), met hourly:
        # dense regular data where both alignment paths must agree.
        t0 = time.time()
        n = int(2 * 86400 // 900)
        grid = [t0 + i * 900 for i in range(n + 1)]
        up_t = [[g, 10.0 + 2.0 * math.sin((g - t0) / 86400.0 * 2 * math.pi)]
                for g in grid]
        up_q = [[g, 1.0] for g in grid]
        mgrid = [t0 + i * 3600
                 for i in range(int(2 * 86400 // 3600) + 1)]
        met = [[g, 8.0 + 5.0 * math.sin((g - t0) / 86400.0 * 2 * math.pi),
                0.5, 2.0, max(0.0, 500.0 * math.sin(
                    (g - t0) / 86400.0 * 2 * math.pi)), 0.2]
               for g in mgrid]
        return {"schema": "yellowstone.firehole_obs.v1",
                "sites": {
                    "06036805": {"series": {"temperature_c": up_t,
                                            "discharge_m3_s": up_q}},
                    "06036905": {"series": {"temperature_c": up_t,
                                            "discharge_m3_s": up_q}}},
                "met": {"hourly": met}}

    def test_aligned_arrays_shape_and_provenance(self):
        from yellowstone_python.replay.obs_frame import aligned_fit_arrays
        arrays = aligned_fit_arrays(self._synthetic(), dt_s=900.0)
        for key in ("grid", "up_t", "up_q", "air", "rh", "wind", "sw",
                    "cloud", "mean_q", "provenance"):
            self.assertIn(key, arrays)
        n = len(arrays["grid"])
        for key in ("up_t", "up_q", "air", "rh", "wind", "sw", "cloud"):
            self.assertEqual(len(arrays[key]), n)
        cov = arrays["provenance"]["coverage"]
        self.assertAlmostEqual(
            cov["upstream temperature"]["coverage"], 1.0)
        self.assertEqual(arrays["provenance"]["bridge_limit_steps"], 4)
        self.assertIn("air_c", arrays["provenance"]["met_daily_means"])

    def test_parity_with_pairs_path(self):
        # Two resampling conventions over the same dense synthetic
        # data must agree closely; they differ exactly where data is
        # sparse, which is the explicit part (gap reports above).
        from yellowstone_python.replay.calibrate import (
            _fit_forcing_arrays,
        )
        from yellowstone_python.replay.obs_frame import aligned_fit_arrays
        bundle = self._synthetic()
        hand = _fit_forcing_arrays(bundle, dt_s=900.0)
        framed = aligned_fit_arrays(bundle, dt_s=900.0)
        self.assertEqual(framed["grid"], hand["grid"])
        worst = 0.0
        for key in ("up_t", "up_q", "air", "rh", "wind", "sw", "cloud"):
            for a, b in zip(framed[key], hand[key]):
                worst = max(worst, abs(a - b))
        self.assertLess(worst, 1e-6)
        self.assertAlmostEqual(framed["mean_q"], hand["mean_q"])


if __name__ == "__main__":
    unittest.main()
