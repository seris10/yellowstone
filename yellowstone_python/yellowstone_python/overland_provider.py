"""Synthetic-catchment runoff mapped to an upstream discharge series."""
from __future__ import annotations

import hashlib
import json
import math

MODEL_VERSION = "yellowstone_python-0.1.0"
METHOD_AREA = "area_runoff_coefficient"
METHOD_LANDLAB = "landlab_flow_accumulator_runoff_coefficient"
COVERAGE = 0.90
STATUS_OK = "synthetic_catchment_predicted_not_validated"


def _finite(value, name, minimum=None):
    """Checked float conversion for provider inputs."""
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def synthetic_elevation(nrows=8, ncols=8, dx_m=30.0, slope=0.02):
    """Tilted-plane elevations for an authored catchment."""
    import numpy as np
    rows = int(nrows)
    cols = int(ncols)
    dx = _finite(dx_m, "dx_m", 0.0)
    if rows < 3 or cols < 3:
        raise ValueError("catchment grid must be at least 3 by 3")
    fall = _finite(slope, "slope", 0.0) * dx
    base = 2400.0
    plane = base - np.add.outer(
        np.arange(rows, dtype=float) * fall,
        np.arange(cols, dtype=float) * fall,
    )
    return plane


def predict_discharge(
    precip_mm_h,
    *,
    area_m2,
    runoff_coefficient=0.4,
    dt_s=3600.0,
    t0_epoch_s=0.0,
    spread_frac=0.3,
    method=METHOD_AREA,
):
    """Runoff-coefficient discharge with 90 percent bounds."""
    area = _finite(area_m2, "area_m2", 0.0)
    coeff = _finite(runoff_coefficient, "runoff_coefficient", 0.0)
    if not 0.0 <= coeff <= 1.0:
        raise ValueError("runoff_coefficient must be in [0, 1]")
    spread = _finite(spread_frac, "spread_frac", 0.0)
    if not 0.0 <= spread < 1.0:
        raise ValueError("spread_frac must be in [0, 1)")
    step = _finite(dt_s, "dt_s", 0.0)
    t0 = _finite(t0_epoch_s, "t0_epoch_s", 0.0)
    rates = [_finite(p, "precip_mm_h", 0.0) for p in precip_mm_h]
    if not rates:
        raise ValueError("precip_mm_h must be nonempty")
    flows = [coeff * (p / 1000.0 / 3600.0) * area for p in rates]
    forcing = {
        "method": method,
        "area_m2": area,
        "runoff_coefficient": coeff,
        "precip_mm_h": rates,
        "dt_s": step,
        "t0_epoch_s": t0,
        "spread_frac": spread,
    }
    digest = hashlib.sha256(
        json.dumps(forcing, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "t0_epoch_s": t0,
        "dt_s": step,
        "discharge_m3_s": flows,
        "discharge_lo_m3_s": [q * (1.0 - spread) for q in flows],
        "discharge_hi_m3_s": [q * (1.0 + spread) for q in flows],
        "coverage": COVERAGE,
        "method": method,
        "status": STATUS_OK,
        "model_version": MODEL_VERSION,
        "forcing_hash": digest,
    }


def predict_discharge_landlab(
    elevation,
    dx_m,
    precip_mm_h,
    **kwargs,
):
    """Landlab-routed drainage area wired into the discharge interface."""
    try:
        from landlab import RasterModelGrid
        from landlab.components import FlowAccumulator
    except ImportError as exc:
        raise RuntimeError("landlab not available") from exc
    import numpy as np
    field = np.asarray(elevation, dtype=float)
    if field.ndim != 2 or field.shape[0] < 3 or field.shape[1] < 3:
        raise ValueError("elevation must be a 2-D grid at least 3 by 3")
    dx = _finite(dx_m, "dx_m", 0.0)
    grid = RasterModelGrid(field.shape, dx)
    grid.add_field("topographic__elevation", field.ravel(), at="node")
    grid.set_closed_boundaries_at_grid_edges(True, True, True, True)
    outlet = int(np.argmin(field))
    grid.status_at_node[outlet] = grid.BC_NODE_IS_FIXED_VALUE
    FlowAccumulator(grid).run_one_step()
    area = float(grid.at_node["drainage_area"][outlet])
    kwargs.setdefault("method", METHOD_LANDLAB)
    return predict_discharge(precip_mm_h, area_m2=area, **kwargs)


def series_spec(result):
    """Series-spec view of a discharge result for solver forcing."""
    times = [i * result["dt_s"] for i in range(len(result["discharge_m3_s"]))]
    return {"times_s": times, "values": list(result["discharge_m3_s"])}
