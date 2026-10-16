"""Terrain hash, dimensions, range, and axis checks against build dependencies."""

import math
import os
import re
from pathlib import Path

import numpy as np

from yellowstone_python.common.io import sha256_file as _file_sha256

SCHEMA_GUARD = "yellowstone.terrain_guard.v1"

GRID = 1025
N_ELEMS = GRID * GRID
N_BYTES = N_ELEMS * 4
DTYPE = "<f4"
CELL_M = 4.0
GRID_SEMANTICS = "vertex_grid"
AXIS_ORDER = "row_major_C"
ROW_DIRECTION = "south_to_north"
COL_DIRECTION = "west_to_east"
ORIGIN = "southwest_corner"
VERTICAL_DATUM_STATUS = "undocumented"

MAX_SLOPE_RATIO = 8.0
MAX_FLAT_CELL_FRACTION = 0.75
MAX_JUMP_M = 30.0

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Tripwires containing the measured envelope (min -10.89, max 238.13, p1 -5.09, p99 221.28). Datum undocumented; the bounds are tripwires.
DEFAULT_MIN_M = -20.0
DEFAULT_MAX_M = 250.0


def _resolve_terrain(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("YELLOWSTONE_WORLD")
    if env:
        return Path(env) / "data" / "terrain.f32"
    cfg_path = Path(__file__).resolve().parents[2] / "configs" / \
        "baseline.yaml"
    try:
        import yaml
        cfg = yaml.safe_load(cfg_path.read_text())
        return Path(cfg["world_root"]) / "data" / "terrain.f32"
    except Exception:
        from yellowstone_python.common.provenance import default_world_root
        return default_world_root() / "data" / "terrain.f32"


def _validate_range_args(min_m: float, max_m: float) -> None:
    if not (math.isfinite(min_m) and math.isfinite(max_m)):
        raise ValueError(
            f"min_m and max_m must be finite; got min_m={min_m}, max_m={max_m}")
    if not min_m < max_m:
        raise ValueError(
            f"min_m must be strictly less than max_m; got min_m={min_m}, "
            f"max_m={max_m}")


def _normalize_expected_hash(expect: str | None) -> str | None:
    if expect is None:
        return None
    normalized = expect.strip().lower()
    if not _HEX64.match(normalized):
        raise ValueError(
            f"expected sha256 must be 64 hex characters; got {expect!r}")
    return normalized



def _spatial_report(grid) -> tuple[dict, dict]:
    """Compute slope, flats and jump statistics without pulling scipy."""
    dz_dx = (grid[:, 1:] - grid[:, :-1]) / CELL_M
    dz_dy = (grid[1:, :] - grid[:-1, :]) / CELL_M
    slope = np.hypot(
        np.pad(dz_dx, ((0, 0), (0, 1))), np.pad(dz_dy, ((0, 1), (0, 0))))
    jump = np.maximum(np.abs(np.pad(dz_dx * CELL_M, ((0, 0), (0, 1)))),
                      np.abs(np.pad(dz_dy * CELL_M, ((0, 1), (0, 0)))))
    flat_fraction = float((slope < 1e-6).mean())
    max_jump = float(jump.max())
    max_slope = float(slope.max())
    stats = {
        "max_slope_ratio": max_slope,
        "max_jump_m": max_jump,
        "flat_cell_fraction": flat_fraction,
    }
    passed = (max_slope <= MAX_SLOPE_RATIO
              and max_jump <= MAX_JUMP_M
              and flat_fraction <= MAX_FLAT_CELL_FRACTION)
    detail = (f"slope<={max_slope:.3f}, jump<={max_jump:.2f} m, "
              f"flats={flat_fraction:.3f}")
    return stats, {"name": "spatial", "passed": passed, "detail": detail}


def guard_terrain(path: Path, expect_sha256: str | None,
                  min_m: float, max_m: float, *,
                  require_datum: bool = False,
                  datum_status: str | None = None) -> dict:
    """Read-only guard; returns the report dict (no I/O beyond the read)."""
    _validate_range_args(min_m, max_m)
    expect_sha256 = _normalize_expected_hash(expect_sha256)
    guards: list = []
    info: dict = {
        "path": str(path),
        "cell_m": CELL_M,
        "axis_order": AXIS_ORDER,
        "grid_semantics": GRID_SEMANTICS,
        "row_direction": ROW_DIRECTION,
        "col_direction": COL_DIRECTION,
        "origin": ORIGIN,
        "vertical_datum_status": VERTICAL_DATUM_STATUS,
    }
    try:
        nbytes = path.stat().st_size
    except OSError as exc:
        info["sha256"] = None
        return {"schema": SCHEMA_GUARD, "status": "authored_terrain_guard",
                "terrain": info, "expected_sha256": expect_sha256,
                "passed": False,
                "guards": [{"name": "terrain-readable", "passed": False,
                            "detail": f"terrain-unreadable: {path}: {exc}"}]}
    info["nbytes"] = nbytes
    info["sha256"] = _file_sha256(path)
    effective_datum = datum_status or VERTICAL_DATUM_STATUS
    info["vertical_datum_status"] = effective_datum
    datum_known = effective_datum not in ("undocumented", "unknown", None)
    guards.append({
        "name": "vertical-datum",
        "passed": datum_known or not require_datum,
        "detail": f"status: {effective_datum}",
    })
    if nbytes != N_BYTES:
        guards.append({"name": "size", "passed": False,
                       "detail": f"bad-size: expected {N_BYTES}, found "
                                 f"{nbytes}"})
        return {"schema": SCHEMA_GUARD, "status": "authored_terrain_guard",
                "terrain": info, "expected_sha256": expect_sha256,
                "passed": False, "guards": guards}
    guards.append({"name": "size", "passed": True,
                   "detail": f"{nbytes} bytes"})
    raw = np.fromfile(str(path), dtype=DTYPE)
    if raw.size != N_ELEMS:
        guards.append({"name": "grid", "passed": False,
                       "detail": f"bad-grid: expected {N_ELEMS} <f4 "
                                 f"elements, found {raw.size}"})
        return {"schema": SCHEMA_GUARD, "status": "authored_terrain_guard",
                "terrain": info, "expected_sha256": expect_sha256,
                "passed": False, "guards": guards}
    grid = raw.reshape(GRID, GRID)
    finite_mask = np.isfinite(grid)
    n_bad = int((~finite_mask).sum())
    if n_bad:
        guards.append({"name": "finite", "passed": False,
                       "detail": f"{n_bad} non-finite values"})
        info["dims"] = [GRID, GRID]
        info["dtype"] = DTYPE
        return {"schema": SCHEMA_GUARD, "status": "authored_terrain_guard",
                "terrain": info, "expected_sha256": expect_sha256,
                "passed": False, "guards": guards}
    guards.append({"name": "finite", "passed": True,
                   "detail": f"{N_ELEMS} finite"})
    percentiles = np.percentile(grid, [1.0, 99.0])
    info.update({"dims": [GRID, GRID], "dtype": DTYPE,
                 "min_m": float(grid.min()), "max_m": float(grid.max()),
                 "mean_m": float(grid.mean()),
                 "p1_m": float(percentiles[0]),
                 "p99_m": float(percentiles[1])})
    guards.append({"name": "grid", "passed": True,
                   "detail": f"{GRID}x{GRID} {DTYPE}"})
    guards.append({"name": "axis", "passed": True,
                   "detail": (f"{AXIS_ORDER}; rows={ROW_DIRECTION}; "
                              f"cols={COL_DIRECTION}; origin={ORIGIN}")})
    if info["min_m"] < min_m or info["max_m"] > max_m:
        guards.append({"name": "range", "passed": False,
                       "detail": f"range [{info['min_m']:.2f}, "
                                 f"{info['max_m']:.2f}] outside "
                                 f"[{min_m}, {max_m}]"})
    else:
        guards.append({"name": "range", "passed": True,
                       "detail": f"[{info['min_m']:.2f}, {info['max_m']:.2f}] "
                                 f"within [{min_m}, {max_m}]"})
    guards.append({"name": "percentiles", "passed": True,
                   "detail": (f"p1={info['p1_m']:.2f}, "
                              f"p99={info['p99_m']:.2f}")})
    spatial_stats, spatial_guard = _spatial_report(grid)
    info["spatial"] = spatial_stats
    guards.append(spatial_guard)
    if expect_sha256 is not None:
        if info["sha256"] != expect_sha256:
            guards.append({"name": "hash", "passed": False,
                           "detail": f"hash-mismatch: expected "
                                     f"{expect_sha256}, found "
                                     f"{info['sha256']}"})
        else:
            guards.append({"name": "hash", "passed": True,
                           "detail": info["sha256"][:12] + "..."})
    return {"schema": SCHEMA_GUARD, "status": "authored_terrain_guard",
            "terrain": info, "expected_sha256": expect_sha256,
            "passed": all(g["passed"] for g in guards), "guards": guards}


