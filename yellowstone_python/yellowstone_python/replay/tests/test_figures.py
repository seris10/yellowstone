"""Tests for publication diagnostic figures (headless Agg).

All synthetic and offline. Each test renders to tmp_path — the repo
never collects test figures.
"""
from __future__ import annotations

import math
import time
import unittest
from pathlib import Path

from yellowstone_python.replay import figures
from yellowstone_python.replay.calibrate import (
    interp_series,
    run_fit_forward,
)
from yellowstone_python.replay.hydraulics import residual_diagnostics
from yellowstone_python.replay.uncertainty import (
    ensemble_bands,
    fit_masks,
    member_trajectories,
)


def synthetic_setup():
    t0 = time.time()
    n = int(2 * 86400 // 1800)
    grid = [t0 + i * 1800 for i in range(n + 1)]
    up_t = [[g, 10.0 + 2.0 * math.sin((g - t0) / 86400.0 * 2 * math.pi)]
            for g in grid]
    up_q = [[g, 1.0] for g in grid]
    met = [[g, 8.0 + 5.0 * math.sin((g - t0) / 86400.0 * 2 * math.pi),
            0.5, 2.0, max(0.0, 500.0 * math.sin(
                (g - t0) / 86400.0 * 2 * math.pi)), 0.2] for g in grid]
    bundle = {"sites": {
        "06036805": {"series": {"temperature_c": up_t,
                                "discharge_m3_s": up_q}},
        "06036905": {"series": {"temperature_c": [], "discharge_m3_s": []}}},
        "met": {"hourly": met}}
    fwd = run_fit_forward(bundle, 20000.0, 40000.0, 2.0, 25.0, 1.0,
                          dt_s=1800.0)
    bundle["sites"]["06036905"]["series"] = {
        "temperature_c": [[g, v] for g, v in zip(fwd["grid"],
                                                 fwd["modeled_c"])],
        "discharge_m3_s": [[g, 3.0] for g in fwd["grid"]]}
    return bundle


def assert_png(test: unittest.TestCase, path: Path) -> None:
    test.assertTrue(path.exists())
    test.assertGreater(path.stat().st_size, 1000)
    with open(path, "rb") as handle:
        test.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n")


class FigureTests(unittest.TestCase):
    def test_fit_holdout(self):
        bundle = synthetic_setup()
        fwd = run_fit_forward(bundle, 20000.0, 40000.0, 2.0, 25.0, 1.0,
                              dt_s=1800.0)
        grid = fwd["grid"]
        target = interp_series(
            bundle["sites"]["06036905"]["series"]["temperature_c"],
            grid)
        upstream = interp_series(
            bundle["sites"]["06036805"]["series"]["temperature_c"],
            grid)
        train, holdout = fit_masks(grid, 3600.0, 0.6)
        out = Path(self._tmp("fig")) / "fit.png"
        figures.fit_holdout_figure(grid, fwd["modeled_c"], target,
                                   upstream, train, holdout, "test",
                                   out)
        assert_png(self, out)

    def test_bands(self):
        bundle = synthetic_setup()
        members = [{"q_lat": 1.0, "t_lat": 15.0, "c_mult": 0.5,
                    "train_rmse": 0.4},
                   {"q_lat": 2.0, "t_lat": 25.0, "c_mult": 1.0,
                    "train_rmse": 0.0},
                   {"q_lat": 3.0, "t_lat": 35.0, "c_mult": 2.0,
                    "train_rmse": 0.5}]
        trajs = member_trajectories(bundle, 20000.0, 40000.0, members,
                                    dt_s=1800.0)
        bands = ensemble_bands(trajs["trajectories"], n_bootstrap=100)
        grid = trajs["grid"]
        _, holdout = fit_masks(grid, 3600.0, 0.6)
        target = interp_series(
            bundle["sites"]["06036905"]["series"]["temperature_c"],
            grid)
        out = Path(self._tmp("fig")) / "bands.png"
        figures.bands_figure(grid, bands["lo"], bands["mid"],
                             bands["hi"], target[holdout], holdout,
                             0.90, 1.0, "test", out)
        assert_png(self, out)

    def test_residuals_and_ridge(self):
        resid = [0.1 * math.sin(i * 0.5) for i in range(60)]
        qq_e = sorted(resid)
        qq_n = sorted(resid)
        out = Path(self._tmp("fig")) / "resid.png"
        figures.residual_figure(resid, resid[:20], qq_e, qq_n, "test",
                                out)
        assert_png(self, out)
        rows = [{"q_lat": q, "t_lat": t, "c_mult": 1.0,
                 "train_rmse": abs(q - 2.0) + abs(t - 25.0) / 10.0}
                for q in (1.0, 2.0, 3.0) for t in (15.0, 25.0, 35.0)]
        champ = {"q_lat": 2.0, "t_lat": 25.0, "c_mult": 1.0}
        out2 = Path(self._tmp("fig")) / "ridge.png"
        figures.ridge_figure(rows, champ, None, out2)
        assert_png(self, out2)

    def test_refuge_profile(self):
        chainage = [float(i * 20) for i in range(30)]
        temps = [16.0 + 0.1 * i for i in range(30)]
        out = Path(self._tmp("fig")) / "refuge.png"
        figures.refuge_profile_figure(chainage, temps, 200.0,
                                      "cell_00010", out)
        assert_png(self, out)

    def _tmp(self, name: str) -> str:
        import tempfile
        path = tempfile.mkdtemp(prefix=f"uqq_{name}_")
        self.addCleanup(__import__("shutil").rmtree, path,
                        ignore_errors=True)
        return path


if __name__ == "__main__":
    unittest.main()
