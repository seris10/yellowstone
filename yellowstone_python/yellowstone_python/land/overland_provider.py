"""Synthetic-catchment runoff mapped to a discharge series.
Rational method Q = C * i(t) * A with an optional linear-reservoir lag."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite, positive as _positive, positive_int as _positive_int

import hashlib
import json
import math
import numbers

MODEL_VERSION = "yellowstone_python-0.1.0"
METHOD_AREA = "area_runoff_coefficient"
METHOD_LANDLAB = "landlab_flow_accumulator_runoff_coefficient"
SCHEMA = "yellowstone.runoff_series.v1"
# Authored symmetric relative band (no validated coverage claim).
COVERAGE = 0.90
STATUS_OK = "synthetic_catchment_predicted_not_validated"

_RUNOFF_TEMPERATURE_RANGE_C = (-40.0, 60.0)
_BOUNDARY_ROLES = ("upstream_inflow", "lateral_source")








def route_linear_reservoir(runoff_m3_s, dt_s, tau_s,
                           initial_storage_m3=0.0):
    """Route runoff through one linear reservoir; mass is conserved.
Release fraction per step is 1 - exp(-dt/tau); returns outflow m3/s per step."""
    dt = _positive("dt_s", dt_s)
    tau = _positive("tau_s", tau_s)
    storage = _finite("initial_storage_m3", initial_storage_m3, minimum=0.0)
    release_fraction = -math.expm1(-dt / tau)
    output = []
    for inflow in runoff_m3_s:
        inflow = _finite("runoff flow", inflow, minimum=0.0)
        storage += inflow * dt
        released = storage * release_fraction
        storage -= released
        output.append(released / dt)
    return output, storage


def _temperature_series(value, n):
    if value is None:
        return None
    low, high = _RUNOFF_TEMPERATURE_RANGE_C
    if isinstance(value, (list, tuple)):
        values = [_finite("runoff_temperature_c", v) for v in value]
        if len(values) != n:
            raise ValueError(
                "runoff_temperature_c must be a scalar or match the "
                "precipitation length")
    else:
        values = [_finite("runoff_temperature_c", value)] * n
    if any(not low <= v <= high for v in values):
        raise ValueError(
            f"runoff_temperature_c must be in [{low}, {high}] C")
    return values


def synthetic_elevation(nrows=8, ncols=8, dx_m=30.0, slope=0.02):
    """Tilted-plane elevations for an authored catchment."""
    import numpy as np
    rows = _positive_int("nrows", nrows)
    cols = _positive_int("ncols", ncols)
    if rows < 3 or cols < 3:
        raise ValueError("nrows and ncols must be >= 3")
    dx = _positive("dx_m", dx_m)
    fall = _finite("slope", slope, minimum=0.0) * dx
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
    routing_tau_s=None,
    runoff_temperature_c=None,
    boundary_role="upstream_inflow",
):
    """Runoff-coefficient discharge with an authored symmetric band."""
    area = _finite("area_m2", area_m2, minimum=0.0)
    coeff = _finite("runoff_coefficient", runoff_coefficient, minimum=0.0)
    if not 0.0 <= coeff <= 1.0:
        raise ValueError("runoff_coefficient must be in [0, 1]")
    spread = _finite("spread_frac", spread_frac, minimum=0.0)
    if not 0.0 <= spread < 1.0:
        raise ValueError("spread_frac must be in [0, 1)")
    step = _positive("dt_s", dt_s)
    t0 = _finite("t0_epoch_s", t0_epoch_s, minimum=0.0)
    if boundary_role not in _BOUNDARY_ROLES:
        raise ValueError(
            f"boundary_role must be one of {_BOUNDARY_ROLES}")
    if isinstance(precip_mm_h, (str, bytes)):
        raise ValueError("precip_mm_h must be a sequence of numbers")
    try:
        raw_rates = list(precip_mm_h)
    except TypeError as exc:
        raise ValueError("precip_mm_h must be a sequence of numbers") from exc
    rates = [_finite("precip_mm_h", p, minimum=0.0) for p in raw_rates]
    if not rates:
        raise ValueError("precip_mm_h must be nonempty")
    tau = None if routing_tau_s is None else _positive("routing_tau_s", routing_tau_s)
    temperature = _temperature_series(runoff_temperature_c, len(rates))

    direct = [coeff * (p / 1000.0 / 3600.0) * area for p in rates]
    if tau is None:
        flows = direct
        storage_remaining = 0.0
    else:
        flows, storage_m3 = route_linear_reservoir(direct, step, tau)
        storage_remaining = storage_m3

    forcing = {
        "method": method,
        "area_m2": area,
        "runoff_coefficient": coeff,
        "precip_mm_h": rates,
        "dt_s": step,
        "t0_epoch_s": t0,
        "spread_frac": spread,
    }
    # Optional inputs enter the hash only when used, keeping the default-call hash stable.
    if tau is not None:
        forcing["routing_tau_s"] = tau
    if temperature is not None:
        forcing["runoff_temperature_c"] = temperature
    if boundary_role != "upstream_inflow":
        forcing["boundary_role"] = boundary_role
    digest = hashlib.sha256(
        json.dumps(forcing, sort_keys=True).encode("utf-8")
    ).hexdigest()

    lo = [q * (1.0 - spread) for q in flows]
    hi = [q * (1.0 + spread) for q in flows]
    uncertainty = {
        "type": "authored_symmetric_relative_band",
        "fraction": spread,
        "coverage_claim": None,
    }
    routing = {
        "mode": "none" if tau is None else "linear_reservoir",
        "tau_s": tau,
        "tau_status": None if tau is None else "authored_not_calibrated",
        "storage_remaining_m3": storage_remaining,
    }
    temperature_status = (
        "not_provided_not_usable_for_heat_transport" if temperature is None
        else "authored_scenario_value")
    return {
        "schema": SCHEMA,
        "t0_epoch_s": t0,
        "dt_s": step,
        "discharge_m3_s": flows,
        "discharge_lo_m3_s": lo,
        "discharge_hi_m3_s": hi,
        "coverage": COVERAGE,
        "uncertainty": uncertainty,
        "routing": routing,
        "runoff_coefficient_mode": "constant_authored",
        "temperature_c": temperature,
        "temperature_status": temperature_status,
        "boundary_role": boundary_role,
        "runoff_series": {
            "times_s": [t0 + i * step for i in range(len(flows))],
            "values": list(flows),
            "dt_s": step,
        },
        "method": method,
        "status": STATUS_OK,
        "model_version": MODEL_VERSION,
        "forcing_hash": digest,
    }


def predict_discharge_landlab(
    elevation,
    dx_m,
    precip_mm_h,
    *,
    outlet_row=None,
    outlet_col=None,
    **kwargs,
):
    """Landlab-routed drainage area feeding the discharge interface."""
    try:
        from landlab import RasterModelGrid
        from landlab.components import FlowAccumulator
    except ImportError as exc:
        raise RuntimeError("landlab not available") from exc
    import numpy as np
    if "area_m2" in kwargs:
        raise ValueError("area_m2 is derived from the routed drainage area")
    field = np.asarray(elevation, dtype=float)
    if field.ndim != 2 or field.shape[0] < 3 or field.shape[1] < 3:
        raise ValueError("elevation must be a 2-D grid at least 3 by 3")
    if not np.all(np.isfinite(field)):
        raise ValueError("elevation must be finite")
    dx = _positive("dx_m", dx_m)
    rows, cols = field.shape

    if outlet_row is None or outlet_col is None:
        raise ValueError("explicit outlet_row and outlet_col are required")
    for name, value in (("outlet_row", outlet_row),
                        ("outlet_col", outlet_col)):
        if (isinstance(value, bool)
                or not isinstance(value, numbers.Integral)):
            raise ValueError(f"{name} must be an integer")
    outlet_row = int(outlet_row)
    outlet_col = int(outlet_col)
    if not (0 <= outlet_row < rows and 0 <= outlet_col < cols):
        raise ValueError("outlet is outside elevation grid")

    grid = RasterModelGrid(field.shape, dx)
    grid.add_field("topographic__elevation", field.ravel(), at="node")
    grid.set_closed_boundaries_at_grid_edges(True, True, True, True)
    outlet = outlet_row * cols + outlet_col
    on_boundary = (
        outlet_row in (0, rows - 1) or outlet_col in (0, cols - 1))
    grid.status_at_node[outlet] = grid.BC_NODE_IS_FIXED_VALUE
    FlowAccumulator(grid).run_one_step()
    area = float(grid.at_node["drainage_area"][outlet])

    warnings = []
    if area <= dx * dx:
        warnings.append(
            "outlet drains no upstream cells; check outlet placement "
            "against the topography")
    if not on_boundary:
        warnings.append("outlet is an interior node (interior sink)")

    kwargs.setdefault("method", METHOD_LANDLAB)
    result = predict_discharge(precip_mm_h, area_m2=area, **kwargs)
    result.update({
        "outlet_index": outlet,
        "outlet_row": outlet_row,
        "outlet_col": outlet_col,
        "drainage_area_m2": area,
        "boundary_condition": ("fixed_value_boundary_node" if on_boundary
                               else "fixed_value_interior_node"),
        "warnings": warnings,
    })
    return result


def series_spec(result):
    """Series-spec view of a discharge result for solver forcing.
times_s: interval-start offsets; values: mean discharge over each interval (piecewise-constant)."""
    values = list(result["discharge_m3_s"])
    if not values:
        raise ValueError("result discharge_m3_s must be nonempty")
    dt = _positive("result dt_s", result["dt_s"])
    times = [i * dt for i in range(len(values))]
    return {"times_s": times, "values": values}


def boundary_schedule(result, *, river_t0_epoch_s=None):
    """Series schedule aligned to a river solver's internal t=0.
Rebases epoch interval starts to seconds-since-river-t0; omit the offset to start at zero."""
    values = list(result["discharge_m3_s"])
    if not values:
        raise ValueError("result discharge_m3_s must be nonempty")
    dt = _positive("result dt_s", result["dt_s"])
    t0 = _finite("result t0_epoch_s", result["t0_epoch_s"])
    if river_t0_epoch_s is None:
        reference = t0
    else:
        reference = _finite("river_t0_epoch_s", river_t0_epoch_s)
    if t0 < reference - 1e-9:
        raise ValueError(
            "provider interval starts before river_t0_epoch_s")
    base = t0 - reference
    times = [base + i * dt for i in range(len(values))]
    if times[0] > 1e-9:
        times = [0.0, *times]
        values = [values[0], *values]
    else:
        times[0] = 0.0
    return {"times_s": times, "values": values}
