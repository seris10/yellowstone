"""Pandas obs-frame alignment for the fetch-then-fit path (B1).

Replaces silent hand-rolled alignment with explicit state: every series
becomes a DatetimeIndex frame at its nominal step (resample-mean bins,
NaN where nothing was measured), gaps are listed withrun lengths,
coverage is a number, bridging is an interpolate(limit=...) whose limit
is recorded, and anything still NaN after bridging refuses loudly.
The incident behind this module: hand interpolation once bridged a
multi-day outage and the fit treated it as data (now also guarded by
check_continuity on the pairs path).

Scope: obs path only. The solver (river_transport) stays dependency
light — pandas is imported here and only here. Requires pandas, which
is NOT installed on the project interpreter (externally managed);
code importing this module raises a guided ImportError there, and its
tests skip. The pairs path in calibrate stays the default until pandas
is installed; aligned_fit_arrays must agree with it (see the parity
test) before the default flips.
"""
from __future__ import annotations

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
    """Irregular [epoch, value] pairs -> nominal-step frame.

    Values sharing a bin are averaged (resample-mean, the explicit
    cousin of resample_bin_mean); empty bins are NaN, never zero.
    """
    if step_s <= 0.0:
        raise ValueError("step_s must be positive")
    if not pairs:
        raise ValueError(f"{name}: no pairs to frame")
    frame = pd.DataFrame({"value": [float(v) for _, v in pairs]},
                         index=pd.to_datetime([t for t, _ in pairs],
                                              unit="s", utc=True))
    frame = frame.sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    # Anchor bins at the first observation, not the epoch: epoch-
    # anchored bins shift regular series by up to a step against the
    # observation times (measured failure, Oct 2026).
    return frame.resample(f"{step_s:g}s",
                          origin=frame.index[0]).mean()


def met_frame(rows: list[list[float]], step_s: float = 3600.0) -> Any:
    """Met [epoch, air, rh, wind, sw, cloud] rows -> joint frame.

    One shared index, so all five variables carry the same gap report.
    """
    if not rows:
        raise ValueError("met: no rows to frame")
    frame = pd.DataFrame(
        {"air_c": [float(r[1]) for r in rows],
         "rh": [float(r[2]) for r in rows],
         "wind_mps": [float(r[3]) for r in rows],
         "shortwave_w_m2": [float(r[4]) for r in rows],
         "cloud": [float(r[5]) for r in rows]},
        index=pd.to_datetime([r[0] for r in rows], unit="s", utc=True))
    frame = frame.sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    return frame.resample(f"{step_s:g}s",
                          origin=frame.index[0]).mean()


def gap_report(frame: Any, name: str) -> dict[str, Any]:
    """Coverage + every NaN run (start, end, length in steps)."""
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
    return {"name": name, "n_expected": total, "n_filled": filled,
            "coverage": filled / total if total else 0.0,
            "gaps": blocks,
            "worst_gap_steps": max((b["steps"] for b in blocks),
                                   default=0)}


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
    """Linearly bridge NaN runs, each direction separately up to limit.

    Standalone explicit helper. Note limit_direction="both" fills from
    each side, so interior runs up to 2x limit are fully bridged; the
    fit path (to_grid) applies its own half-limit to match the 4x rule.
    """
    return frame.interpolate(method="linear", limit=limit,
                             limit_direction="both")


def to_grid(frame: Any, grid: list[float], name: str,
            limit: int = BRIDGE_STEPS // 2) -> list[float]:
    """Frame values onto epoch grid; anything unbridgeable refuses.

    Linear interpolation between neighboring bins, each side bridged up
    to `limit` steps — interior gaps up to 2x limit (= BRIDGE_STEPS)
    fill, matching check_continuity's 4x-nominal rule; anything longer
    survives as NaN and raises, naming the first offending epoch.
    Grid endpoints must lie inside measured coverage (no silent
    endpoint clamp, unlike the pairs path).
    """
    if any(b < a for a, b in zip(grid, grid[1:])):
        raise ValueError(f"{name}: grid must be increasing")
    first, last = frame.index[0], frame.index[-1]
    stamps = pd.to_datetime(grid, unit="s", utc=True)
    if stamps[0] < first or stamps[-1] > last:
        raise ValueError(
            f"{name}: grid [{stamps[0].isoformat()}.."
            f"{stamps[-1].isoformat()}] outruns measured coverage "
            f"[{first.isoformat()}..{last.isoformat()}]")
    values = frame.reindex(frame.index.union(stamps)).interpolate(
        method="linear", limit=limit,
        limit_direction="both").reindex(stamps)
    column = values["value"] if "value" in values else values
    out = [float(v) for v in column.to_numpy()]
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
    if window_steps < 1:
        raise ValueError("window_steps must be >= 1")
    return frame.rolling(window=window_steps,
                         min_periods=min_periods).mean()


def daily_met_means(frame: Any) -> dict[str, float]:
    """Calendar-day means of each met column (forcing summary)."""
    daily = frame.resample("1D").mean(numeric_only=True)
    return {column: [float(v) for v in daily[column]]
            for column in daily.columns}


def aligned_fit_arrays(bundle: dict[str, Any],
                       dt_s: float = 900.0) -> dict[str, Any]:
    """Fit forcing arrays through frames; same shape as _fit_forcing_arrays.

    Raises on unbridgeable gaps (assert_coverable) or grid points
    outside coverage (to_grid). Returns the arrays plus a provenance
    report carrying every coverage number and the bridge limit, so the
    fit artifact can record what the alignment assumed.
    """
    from yellowstone_python.common.hydro_units import validate_usgs_bundle
    validate_usgs_bundle(bundle)
    from .calibrate import _fit_forcing_arrays  # grid convention only
    up = bundle["sites"]["06036805"]["series"]
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
    # NOTE: frames go to the grid unbridged; to_grid applies the
    # recorded limit itself, so one mechanism owns bridging.
    grid = _fit_forcing_arrays(bundle, dt_s)["grid"]

    def series_of(values: list[float]) -> Any:
        from .river_transport import Series
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
