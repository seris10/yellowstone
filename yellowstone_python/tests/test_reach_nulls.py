"""Fit nulls, regime scores, and mode claim on a synthetic bundle."""
import math
import time

from yellowstone_python.river.calibrate import reach_heat_fit, regime_scores_by_flow


def _bundle(n_days=4, step=1800.0, q_ramp=None):
    t0 = time.time()
    n = int(n_days * 86400 // step)
    grid = [t0 + i * step for i in range(n + 1)]
    up_t = [[g, 10.0 + 2.0 * math.sin((g - t0) / 86400.0 * 2 * math.pi)]
            for g in grid]
    if q_ramp is None:
        up_q = [[g, 1.0] for g in grid]
    else:
        up_q = [[g, 1.0 + 4.0 * i / n] for i, g in enumerate(grid)]
    met = [[g, 8.0 + 5.0 * math.sin((g - t0) / 86400.0 * 2 * math.pi),
            0.5, 2.0, max(0.0, 500.0 * math.sin(
                (g - t0) / 86400.0 * 2 * math.pi)), 0.2] for g in grid]
    down_t = [[g, v + 1.0] for g, v in
              zip(grid, [r[1] for r in up_t])]
    return {"schema": "yellowstone.firehole_obs.v1",
            "sites": {
                "06036805": {"series": {"temperature_c": up_t,
                                        "discharge_m3_s": up_q}},
                "06036905": {"series": {"temperature_c": down_t,
                                        "discharge_m3_s": up_q}}},
            "met": {"hourly": met}}


def test_fit_reports_three_nulls():
    doc = reach_heat_fit(_bundle(), 300000.0, 600000.0,
                         [3.5], [30.0], [1.0],
                         spinup_s=86400.0, dt_s=1800.0)
    names = [m["name"] for m in doc["null_models"]]
    assert names == ["upstream_persistence", "mixing_only_c0_refit",
                     "downstream_climatology"]
    for m in doc["null_models"]:
        assert math.isfinite(m["train_rmse"])
        assert math.isfinite(m["holdout_rmse"])


def test_fit_regime_scores_constant_flow():
    doc = reach_heat_fit(_bundle(), 300000.0, 600000.0,
                         [3.5], [30.0], [1.0],
                         spinup_s=86400.0, dt_s=1800.0)
    regimes = doc["regime_scores"]
    assert regimes["all"]["n"] > 0
    assert "bounds_m3_s" not in regimes


def test_fit_regime_scores_ramped_flow():
    doc = reach_heat_fit(_bundle(q_ramp=True), 300000.0, 600000.0,
                         [3.5], [30.0], [1.0],
                         spinup_s=86400.0, dt_s=1800.0)
    regimes = doc["regime_scores"]
    assert set(regimes) >= {"all", "low", "mid", "high", "bounds_m3_s"}
    lo, hi = regimes["bounds_m3_s"]
    assert lo < hi
    for name in ("low", "mid", "high"):
        assert regimes[name]["n"] > 0


def test_regime_scores_always_emit_groups():
    out = regime_scores_by_flow([1.0, 1.0, 100.0], [1.1, 0.9, 99.0],
                                [5.0, 5.0, 5.0001])
    for name in ("low", "mid", "high"):
        assert name in out, name


def test_fit_mode_claim_no_overlap():
    doc = reach_heat_fit(_bundle(), 300000.0, 600000.0,
                         [3.5], [30.0], [1.0],
                         spinup_s=86400.0, dt_s=1800.0)
    claim = doc["mode_claim"]
    assert claim["validated"] == ["downstream_temperature"]
    assert not (set(claim["prescribed"]) & set(claim["validated"]))


def test_regime_scores_rejects_bad_input():
    import pytest
    with pytest.raises(ValueError):
        regime_scores_by_flow([], [], [])
    with pytest.raises(ValueError):
        regime_scores_by_flow([1.0], [1.0, 2.0], [1.0, 2.0])
