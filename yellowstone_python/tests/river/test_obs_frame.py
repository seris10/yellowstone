"""Tests for pandas obs-frame alignment component (synthetic, offline)."""
from __future__ import annotations

import importlib.util
import math
import time
import pytest

HAS_PANDAS = importlib.util.find_spec("pandas") is not None


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_PANDAS, reason='pandas not installed')
def test_frame_frame_bins_and_coverage():
    from yellowstone_python.river.obs_frame import _frame_from_pairs, gap_report
    t0 = 1_700_000_000
    # 10 obs on a 900 s cadence with one bin skipped.
    pairs = [[float(t0 + i * 900), 10.0 + i] for i in range(5)]
    pairs += [[float(t0 + i * 900), 10.0 + i] for i in range(6, 10)]
    frame = _frame_from_pairs(pairs, "test", 900.0)
    report = gap_report(frame, "test")
    assert report['n_expected'] == 10
    assert report['n_filled'] == 9
    assert report['coverage'] == pytest.approx(0.9, abs=0.5 * 10 ** -(7), rel=0)
    assert len(report['gaps']) == 1
    assert report['gaps'][0]['steps'] == 1
    assert report['worst_gap_steps'] == 1


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_PANDAS, reason='pandas not installed')
def test_frame_frame_averages_shared_bins():
    from yellowstone_python.river.obs_frame import _frame_from_pairs
    t0 = 1_700_000_000
    pairs = [[float(t0), 10.0], [float(t0 + 100), 20.0],
             [float(t0 + 900), 30.0]]
    frame = _frame_from_pairs(pairs, "test", 900.0)
    assert frame['value'].iloc[0] == pytest.approx(15.0, abs=0.5 * 10 ** -(7), rel=0)
    assert frame['value'].iloc[1] == pytest.approx(30.0, abs=0.5 * 10 ** -(7), rel=0)


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_PANDAS, reason='pandas not installed')
def test_frame_frame_rejects_bad():
    from yellowstone_python.river.obs_frame import _frame_from_pairs
    with pytest.raises(ValueError):
        _frame_from_pairs([], "empty", 900.0)
    with pytest.raises(ValueError):
        _frame_from_pairs([[0.0, 1.0]], "x", 0.0)


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_PANDAS, reason='pandas not installed')
def test_frame_coverable_refuses_long_gap():
    from yellowstone_python.river.obs_frame import _frame_from_pairs, assert_coverable, gap_report
    t0 = 1_700_000_000
    pairs = [[float(t0), 1.0], [float(t0 + 6 * 900), 2.0]]
    report = gap_report(_frame_from_pairs(pairs, "gappy", 900.0),
                        "gappy")
    assert report['worst_gap_steps'] == 5
    with pytest.raises(ValueError) as ctx:
        assert_coverable(report)
    assert 'gappy' in str(ctx.value)
    assert_coverable(report, max_gap_steps=5)  # explicit pass


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_PANDAS, reason='pandas not installed')
def test_frame_bridge_limit_direction():
    from yellowstone_python.river.obs_frame import _frame_from_pairs, bridge
    t0 = 1_700_000_000
    pairs = [[float(t0 + i * 900), float(i)] for i in
             [0, 1, 2, 8, 9, 10]]
    frame = _frame_from_pairs(pairs, "test", 900.0)
    filled = bridge(frame, limit=2)
    # 5-step gap with per-side limit 2: filled from both ends; middle survives.
    assert int(filled['value'].isna().sum()) == 1
    filled5 = bridge(frame, limit=5)
    assert int(filled5['value'].isna().sum()) == 0


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_PANDAS, reason='pandas not installed')
def test_frame_to_grid_exact_on_knots_and_refuses_outside():
    from yellowstone_python.river.obs_frame import _frame_from_pairs, bridge, to_grid
    t0 = 1_700_000_000
    pairs = [[float(t0 + i * 900), 10.0 + i] for i in range(6)]
    frame = bridge(_frame_from_pairs(pairs, "test", 900.0))
    grid = [float(t0), float(t0 + 450), float(t0 + 5 * 900)]
    assert to_grid(frame, grid, 'test')[1] == pytest.approx(10.5, abs=0.5 * 10 ** -(7), rel=0)
    with pytest.raises(ValueError):
        to_grid(frame, [float(t0 - 3600)], "test")


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_PANDAS, reason='pandas not installed')
def test_frame_rolling_and_daily_means():
    from yellowstone_python.river.obs_frame import daily_met_means, met_frame, rolling_mean
    # Midnight-aligned start: 48 hourly rows span 2 calendar days.
    t0 = 1_700_000_000 - (1_700_000_000 % 86400)
    rows = [[float(t0 + i * 3600), 10.0, 0.5, 2.0,
             100.0, 0.2] for i in range(48)]
    frame = met_frame(rows)
    assert list(frame.columns) == ['air_c', 'rh', 'wind_mps', 'shortwave_w_m2', 'cloud']
    rolled = rolling_mean(frame[["air_c"]], 4)
    assert rolled['air_c'].iloc[3] == pytest.approx(10.0, abs=0.5 * 10 ** -(7), rel=0)
    daily = daily_met_means(frame)
    assert len(daily['air_c']) == 2
    with pytest.raises(ValueError):
        rolling_mean(frame, 0)



def _aligned_arrays_synthetic():
    # Upstream pairs at the IV step 900 s, met hourly; dense regular data where both alignment paths agree.
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


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_PANDAS, reason='pandas not installed')
def test_aligned_arrays_aligned_arrays_shape_and_provenance():
    from yellowstone_python.river.obs_frame import aligned_fit_arrays
    arrays = aligned_fit_arrays(_aligned_arrays_synthetic(), dt_s=900.0)
    for key in ("grid", "up_t", "up_q", "air", "rh", "wind", "sw",
                "cloud", "mean_q", "provenance"):
        assert key in arrays
    n = len(arrays["grid"])
    for key in ("up_t", "up_q", "air", "rh", "wind", "sw", "cloud"):
        assert len(arrays[key]) == n
    cov = arrays["provenance"]["coverage"]
    assert cov['upstream temperature']['coverage'] == pytest.approx(1.0, abs=0.5 * 10 ** -(7), rel=0)
    assert arrays['provenance']['bridge_limit_steps'] == 4
    assert 'air_c' in arrays['provenance']['met_daily_means']


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_PANDAS, reason='pandas not installed')
def test_aligned_arrays_parity_with_pairs_path():
    # Two resampling conventions over the same dense synthetic data agree closely; they differ where data is sparse.
    from yellowstone_python.river.calibrate import fit_forcing_arrays
    from yellowstone_python.river.obs_frame import aligned_fit_arrays
    bundle = _aligned_arrays_synthetic()
    hand = fit_forcing_arrays(bundle, dt_s=900.0)
    framed = aligned_fit_arrays(bundle, dt_s=900.0)
    assert framed['grid'] == hand['grid']
    worst = 0.0
    for key in ("up_t", "up_q", "air", "rh", "wind", "sw", "cloud"):
        for a, b in zip(framed[key], hand[key]):
            worst = max(worst, abs(a - b))
    assert worst < 1e-06
    assert framed['mean_q'] == pytest.approx(hand['mean_q'], abs=0.5 * 10 ** -(7), rel=0)



