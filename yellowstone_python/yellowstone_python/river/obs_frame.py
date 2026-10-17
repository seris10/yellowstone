"""Pandas observation-frame alignment: resample-mean bins at nominal step with left-edge half-open."""
from __future__ import annotations
from yellowstone_python.river.obs_model import UPSTREAM_GAUGE, DOWNSTREAM_GAUGE
from yellowstone_python.common.checks import finite as _finite

from typing import Any

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError(
        "replay.obs_frame needs pandas: install it "
        "(pip install 'pandas>=2,<4') or stay on the pairs path "
        "in calibrate._fit_forcing_arrays") from exc

NOMINAL_STEP_S = {"usgs_iv": 900.0, "met": 3600.0}
BRIDGE_STEPS = 4  # same 4x-nominal rule as check_continuity





def _frame_from_pairs(pairs: list[list[float]], name: str,
                      step_s: float) -> Any:
    """Irregular [epoch, value] pairs -> nominal-step frame."""
    step_s = _finite("step_s", step_s)
    if step_s <= 0.0:
        raise ValueError("step_s must be positive")
    if not pairs:
        raise ValueError(f"{name}: no pairs to frame")
    cleaned_pairs: list[tuple[float, float]] = []
    for i, pair in enumerate(pairs):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(f"{name}: pair {i} must be [epoch, value]")
        epoch = _finite(f"{name}[{i}].epoch", pair[0])
        value = _finite(f"{name}[{i}].value", pair[1])
        cleaned_pairs.append((epoch, value))
    frame = pd.DataFrame({"value": [v for _, v in cleaned_pairs]},
                         index=pd.to_datetime([t for t, _ in cleaned_pairs],
                                              unit="s", utc=True))
    frame = frame.sort_index()
    measured_t_min = min(t for t, _ in cleaned_pairs)
    measured_t_max = max(t for t, _ in cleaned_pairs)
    # Mean duplicate timestamps; bins start at first observation and are left-labeled and left-closed.
    resampled = frame.resample(f"{step_s:g}s", origin=frame.index[0],
                               label="left", closed="left").mean()
    resampled.attrs["measured_t_min_s"] = measured_t_min
    resampled.attrs["measured_t_max_s"] = measured_t_max
    resampled.attrs["bin_label_convention"] = "left_edge_half_open"
    return resampled


def met_frame(rows: list[list[float]], step_s: float = 3600.0) -> Any:
    """Met [epoch, air, rh, wind, sw, cloud] rows -> joint frame."""
    if not rows:
        raise ValueError("met: no rows to frame")
    for i, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise ValueError(
                f"met row {i}: expected [epoch, air, rh, wind, sw, cloud]")
    epochs = [_finite(f"met row {i}.epoch", r[0])
              for i, r in enumerate(rows)]
    for i, row in enumerate(rows):
        for j, name in enumerate(
                ("air_c", "rh", "wind_mps", "shortwave_w_m2", "cloud"), 1):
            _finite(f"met row {i}.{name}", row[j])
    frame = pd.DataFrame(
        {"air_c": [float(r[1]) for r in rows],
         "rh": [float(r[2]) for r in rows],
         "wind_mps": [float(r[3]) for r in rows],
         "shortwave_w_m2": [float(r[4]) for r in rows],
         "cloud": [float(r[5]) for r in rows]},
        index=pd.to_datetime(epochs, unit="s", utc=True))
    frame = frame.sort_index()
    # Mean averages dup timestamps; label/closed left matches obs_model.interval_average.
    resampled = frame.resample(f"{step_s:g}s", origin=frame.index[0],
                               label="left", closed="left").mean()
    resampled.attrs["measured_t_min_s"] = min(epochs)
    resampled.attrs["measured_t_max_s"] = max(epochs)
    resampled.attrs["bin_label_convention"] = "left_edge_half_open"
    return resampled


def gap_report(frame: Any, name: str) -> dict[str, Any]:
    """Coverage, NaN runs, and measured-vs-bin-label extent."""
    missing = frame["value"].isna() if "value" in frame else frame.isna()
    if isinstance(missing, pd.DataFrame):
        missing = missing.any(axis=1)
    total = len(frame)
    blocks: list[dict[str, Any]] = []
    if total and bool(missing.any()):
        isles = missing.ne(missing.shift()).cumsum()
        for _, group in missing.groupby(isles):
            if bool(group.iloc[0]):
                blocks.append({
                    "start": group.index[0].isoformat(),
                    "end": group.index[-1].isoformat(),
                    "steps": int(len(group))})
    filled = int((~missing).sum()) if total else 0
    bin_min = frame.index[0].isoformat() if total else None
    bin_max = frame.index[-1].isoformat() if total else None
    attrs = getattr(frame, "attrs", {}) or {}
    return {"name": name, "n_expected": total, "n_filled": filled,
            "coverage": filled / total if total else 0.0,
            "gaps": blocks,
            "worst_gap_steps": max((b["steps"] for b in blocks),
                                   default=0),
            "bin_label_t_min": bin_min,
            "bin_label_t_max": bin_max,
            "measured_t_min_s": attrs.get("measured_t_min_s"),
            "measured_t_max_s": attrs.get("measured_t_max_s"),
            "bin_label_convention": attrs.get(
                "bin_label_convention", "left_edge_half_open")}


def assert_coverable(report: dict[str, Any],
                     max_gap_steps: int = BRIDGE_STEPS) -> None:
    """Refuse unbridgeable gaps, naming the worst one."""
    worst = report["worst_gap_steps"]
    if worst > max_gap_steps:
        gaps = "; ".join(
            f"{g['start']}..{g['end']} ({g['steps']} steps)"
            for g in report["gaps"] if g["steps"] > max_gap_steps)
        raise ValueError(
            f"{report['name']}: {worst}-step gap exceeds "
            f"{max_gap_steps} bridgeable steps; refusing to bridge: "
            f"{gaps}")


def bridge(frame: Any, limit: int = BRIDGE_STEPS) -> Any:
    """Linearly bridge NaN runs, each direction up to limit."""
    return frame.interpolate(method="linear", limit=limit,
                             limit_direction="both")


def to_grid(frame: Any, grid: list[float], name: str,
            limit: int = BRIDGE_STEPS) -> list[float]:
    """Frame values onto epoch grid by linear interpolation in time; unbridgeable gaps raise."""
    import numpy as np
    if any(b < a for a, b in zip(grid, grid[1:])):
        raise ValueError(f"{name}: grid must be increasing")
    first, last = frame.index[0], frame.index[-1]
    stamps = pd.to_datetime(grid, unit="s", utc=True)
    if stamps[0] < first or stamps[-1] > last:
        raise ValueError(
            f"{name}: grid [{stamps[0].isoformat()}.."
            f"{stamps[-1].isoformat()}] outruns measured coverage "
            f"[{first.isoformat()}..{last.isoformat()}]")
    column = frame["value"] if "value" in frame else frame.iloc[:, 0]
    index_s = np.array([ts.timestamp() for ts in frame.index])
    nominal = float(np.median(np.diff(index_s))) if len(index_s) > 1 else 0.0
    valid = column.notna().to_numpy()
    t_valid = index_s[valid]
    v_valid = column.to_numpy(dtype=float)[valid]
    if t_valid.size == 0:
        raise ValueError(f"{name}: no valid samples")
    g = np.asarray(grid, dtype=float)
    values = np.interp(g, t_valid, v_valid)
    right = np.clip(np.searchsorted(t_valid, g, side="left"), 0, t_valid.size - 1)
    left = np.clip(right - 1, 0, t_valid.size - 1)
    tol = 1e-3
    on_sample = np.abs(t_valid[right] - g) <= tol
    span = t_valid[right] - t_valid[left]
    values[(~on_sample) & (span > limit * nominal + tol)] = np.nan
    values[(g < t_valid[0] - tol) | (g > t_valid[-1] + tol)] = np.nan
    out = [float(v) for v in values]
    nans = [g for g, v in zip(grid, out) if v != v]
    if nans:
        raise ValueError(
            f"{name}: {len(nans)} grid points still NaN after "
            f"bridging (first at epoch {nans[0]:.0f}); the window "
            f"outruns measured coverage")
    return out


def rolling_mean(frame: Any, window_steps: int,
                 min_periods: int = 1) -> Any:
    """Trailing rolling mean for diagnostic smoothing (e.g. daily met)."""
    if isinstance(window_steps, bool) or not isinstance(window_steps, int):
        raise ValueError("window_steps must be an integer")
    if window_steps < 1:
        raise ValueError("window_steps must be >= 1")
    if isinstance(min_periods, bool) or not isinstance(min_periods, int):
        raise ValueError("min_periods must be an integer")
    if min_periods < 1:
        raise ValueError("min_periods must be >= 1")
    return frame.rolling(window=window_steps,
                         min_periods=min_periods).mean()


def daily_met_means(frame: Any) -> dict[str, list[float]]:
    """Calendar-day means of each met column (forcing summary)."""
    daily = frame.resample("1D").mean(numeric_only=True)
    return {column: [float(v) for v in daily[column]]
            for column in daily.columns}


def aligned_fit_arrays(bundle: dict[str, Any],
                       dt_s: float = 900.0,
                       upstream_site: str = UPSTREAM_GAUGE) -> dict[str, Any]:
    """Fit forcing arrays through frames; same shape as _fit_forcing_arrays."""
    from yellowstone_python.common.units import validate_usgs_bundle
    validate_usgs_bundle(bundle)
    from yellowstone_python.river.fit_grid import build_fit_grid
    up = bundle["sites"][upstream_site]["series"]
    met_rows = bundle["met"]["hourly"]
    up_t = _frame_from_pairs(up["temperature_c"], "upstream temperature",
                             NOMINAL_STEP_S["usgs_iv"])
    up_q = _frame_from_pairs(up["discharge_m3_s"], "upstream discharge",
                             NOMINAL_STEP_S["usgs_iv"])
    met = met_frame(met_rows, NOMINAL_STEP_S["met"])
    reports = [gap_report(up_t, "upstream temperature"),
               gap_report(up_q, "upstream discharge"),
               gap_report(met, "met")]
    for report in reports:
        assert_coverable(report)
    # Frames go to grid unbridged; to_grid applies the recorded limit.
    grid = build_fit_grid(bundle, dt_s)["grid"]

    def series_of(values: list[float]) -> Any:
        from yellowstone_python.river.river_transport import Series
        t0 = grid[0]
        rel = [g - t0 for g in grid]
        return Series(tuple([0.0] + rel[1:]), tuple(values))

    up_t_list = to_grid(up_t, grid, "upstream temperature")
    up_q_list = to_grid(up_q, grid, "upstream discharge")
    air = to_grid(met[["air_c"]].rename(
        columns={"air_c": "value"}), grid, "met air")
    rh = to_grid(met[["rh"]].rename(columns={"rh": "value"}),
                 grid, "met rh")
    wind = to_grid(met[["wind_mps"]].rename(
        columns={"wind_mps": "value"}), grid, "met wind")
    sw = to_grid(met[["shortwave_w_m2"]].rename(
        columns={"shortwave_w_m2": "value"}), grid, "met shortwave")
    cloud = to_grid(met[["cloud"]].rename(
        columns={"cloud": "value"}), grid, "met cloud")
    mean_q = float(up_q["value"].dropna().mean())
    return {"grid": grid, "t0": grid[0], "mean_q": mean_q,
            "up_t": up_t_list, "up_q": up_q_list,
            "air": air, "rh": rh, "wind": wind, "sw": sw,
            "cloud": cloud,
            "up_t_series": series_of(up_t_list),
            "met_series": {"air_c": series_of(air),
                           "rh": series_of(rh),
                           "wind_mps": series_of(wind),
                           "sw": series_of(sw),
                           "cloud": series_of(cloud)},
            "provenance": {
                "backend": "pandas_frames",
                "bridge_limit_steps": BRIDGE_STEPS,
                "coverage": {r["name"]: {"coverage": r["coverage"],
                                         "worst_gap_steps":
                                         r["worst_gap_steps"]}
                             for r in reports},
                "met_daily_means": daily_met_means(met)}}
