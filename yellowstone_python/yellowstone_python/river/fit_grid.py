"""Shared uniform-grid construction for calibration forcing."""
from __future__ import annotations
from yellowstone_python.river.obs_model import UPSTREAM_GAUGE, DOWNSTREAM_GAUGE

from typing import Any

from yellowstone_python.common.units import validate_usgs_bundle


def build_fit_grid(bundle: dict[str, Any], dt_s: float = 900.0,
                   upstream_site: str = UPSTREAM_GAUGE) -> dict[str, Any]:
    """Return {grid, t0, dt_s, forcing_window, data_window} for a bundle."""
    if not isinstance(dt_s, (int, float)) or dt_s <= 0.0:
        raise ValueError("dt_s must be a positive number")
    validate_usgs_bundle(bundle)
    up = bundle["sites"][upstream_site]["series"]
    met_rows = bundle["met"]["hourly"]
    if not up["temperature_c"] or not met_rows:
        raise ValueError("upstream temperature and met rows must be nonempty")
    t0 = max(up["temperature_c"][0][0], met_rows[0][0])
    t1 = min(up["temperature_c"][-1][0], met_rows[-1][0])
    if t1 <= t0:
        raise ValueError(
            f"empty intersection between upstream and met coverage "
            f"(t0={t0:.0f}, t1={t1:.0f})")
    n = int((t1 - t0) // dt_s)
    grid = [t0 + i * dt_s for i in range(n + 1)]
    return {
        "grid": grid,
        "t0": t0,
        "dt_s": float(dt_s),
        "forcing_window": {
            "start_epoch_unix": t0,
            "end_epoch_unix": grid[-1],
            "dt_s": float(dt_s),
        },
        "data_window": {
            "start_epoch_unix": grid[0],
            "end_epoch_unix": grid[-1],
            "n_samples": len(grid),
        },
    }
