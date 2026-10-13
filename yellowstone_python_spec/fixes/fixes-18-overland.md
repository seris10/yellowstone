These two files currently represent **two different hydrology models that are not wired together**:

```text
overland_flow.py
    spatial rainfall → infiltration → surface depth/runoff field

overland_provider.py
    rainfall × area × runoff coefficient → discharge time series
```

The main problem is that `overland_flow.py` explicitly reports that it produces no useful runoff, while `overland_provider.py` independently invents a discharge series from a coefficient. They should either be clearly separate scenario models or be connected through a documented catchment pipeline.

---

# 1. Current relationship

## `overland_flow.py`

This runs the spatial hydrosim model:

```python
sim = hs.HydroSim(...)
sim.step(step, rain)
```

It produces:

```text
surface-water depth field
water balance
outflow
ET
```

But it uses:

```python
open_edges=()
```

and the module documentation says:

```text
no water leaves the domain edges
```

Therefore its `outflow_m3` is intentionally zero.

## `overland_provider.py`

This does not use the hydrosim field. It calculates:

```python
flow = runoff_coefficient
       × precipitation_rate
       × catchment_area
```

Specifically:

```python
flows = [
    coeff * (p / 1000.0 / 3600.0) * area
    for p in rates
]
```

This is an instantaneous rational-method estimate. It does not include:

- infiltration;
- soil storage;
- depression storage;
- travel time;
- drainage routing;
- antecedent wetness;
- snowmelt;
- evaporation;
- flow accumulation timing.

So its `discharge_m3_s` is not the output of `overland_flow.py`.

---

# 2. Most important issue: do not call the provider “measured” or fully hydrologic

The provider status is reasonably cautious:

```python
STATUS_OK = "synthetic_catchment_predicted_not_validated"
```

Keep that discipline. The result should be described as:

```text
synthetic rainfall-runoff estimate using an assumed runoff coefficient
```

not:

```text
catchment runoff
```

unless the coefficient and catchment area have been calibrated.

The current `COVERAGE = 0.90` is also unexplained. It appears to mean a 90% interval, but the code simply sets:

```python
discharge_lo = q * (1 - spread)
discharge_hi = q * (1 + spread)
```

That is not automatically a 90% prediction interval.

Rename it or document it:

```python
INTERVAL_COVERAGE = 0.90
```

and state that the interval is an authored symmetric uncertainty band, not a statistically estimated 90% interval.

---

# 3. Bug: `_finite()` in `overland_provider.py` accepts booleans

Current code:

```python
result = float(value)
```

accepts:

```python
True  -> 1.0
False -> 0.0
```

This is inconsistent with the stronger validation in `overland_flow.py`.

Replace it with:

```python
def _finite(value, name, minimum=None):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not boolean")

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc

    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")

    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")

    return result
```

Also require a positive timestep:

```python
step = _finite(dt_s, "dt_s")
if step <= 0.0:
    raise ValueError("dt_s must be > 0")
```

Currently `dt_s=0` is accepted.

---

# 4. Bug: `series_spec()` omits the final forcing endpoint

Current code:

```python
times = [
    i * result["dt_s"]
    for i in range(len(result["discharge_m3_s"]))
]
```

For three values with `dt_s=3600`, this creates:

```text
0, 3600, 7200
```

Those are samples, not interval endpoints. If the series represents hourly rates, the final value should normally remain active through the next hour, or the API should explicitly state that values are point samples.

For a `Series` consumed by `river_transport.py`, use right-continuous interval values and include the intended end time:

```python
def series_spec(result):
    values = list(result["discharge_m3_s"])
    dt = _finite(result["dt_s"], "result dt_s")

    if dt <= 0.0:
        raise ValueError("result dt_s must be > 0")

    if len(values) == 1:
        times = [0.0]
    else:
        times = [i * dt for i in range(len(values))]

    return {
        "times_s": times,
        "values": values,
    }
```

But the more important issue is semantic: `River` currently assumes **constant discharge**, so this series cannot yet be passed to `boundary_m3_s` without extending `river_transport.py`.

---

# 5. Major wiring issue: dynamic discharge is unsupported by `River`

`overland_provider.py` produces:

```python
{
    "times_s": [...],
    "values": [...]
}
```

But `River` currently calculates face flow once in `__init__()`:

```python
q = [self.boundary_m3_s]
for lateral_q in self._lateral_q:
    q.append(q[-1] + lateral_q)
self.face_flow_m3_s = tuple(q)
```

This means a time-varying discharge series cannot affect:

- advection;
- downstream export;
- residence time;
- water balance;
- Courant number;
- thermal transport.

Do not wire the output into `boundary_m3_s` until `River` supports scheduled flow.

## Required transport change

Parse the boundary flow as a `Series`:

```python
self.boundary_m3_s = Series.parse(boundary_m3_s)
```

Then remove the fixed `self.face_flow_m3_s` calculation and add:

```python
def _face_flows_at(self, time_s: float) -> tuple[float, ...]:
    boundary_q = self.boundary_m3_s.at(time_s)

    q = [boundary_q]

    for lateral_q in self._lateral_q:
        q.append(
            finite(
                q[-1] + lateral_q,
                "derived face discharge",
                0.0,
            )
        )

    return tuple(q)
```

Use this inside `_system()` and `_advance_to()`:

```python
q = self._face_flows_at(time_s)
```

The boundary flow series must also be included in `_forcing`:

```python
forcing_series = [
    self.boundary_m3_s,
    self.boundary_c,
    self.air_c,
    self.net_heat_flux,
]
```

Water accounting then needs to integrate the actual boundary flow at each step:

```python
increments["boundary_input_m3"] = dt_s * q[0]
increments["outlet_export_m3"] = dt_s * q[-1]
```

With piecewise-constant forcing and interval splitting, this is valid.

Also change the public geometry metadata. A time-varying-flow replay should not expose only:

```python
"face_flow_m3_s": [...]
```

It should report:

```json
{
  "face_flow_semantics": "values at replay start or diagnostic only",
  "boundary_flow_forcing": {
    "times_s": [...],
    "values": [...]
  }
}
```

---

# 6. `overland_flow.py` does not currently generate a meaningful runoff signal

This is not necessarily a code bug. It is a model-result diagnosis.

The relevant configuration is:

```python
open_edges=()
```

That means no boundary outlet is available. If the purpose is to produce river inflow, configure an outlet or drainage boundary in hydrosim.

However, before doing that, define the hydrologic meaning:

```text
open_edges=()
    closed experimental surface-domain test

open outlet boundary
    catchment runoff export experiment
```

Do not simply turn on open edges and call the result calibrated runoff.

## Better API

Add an explicit outlet configuration:

```python
def run_overland(
    world_root,
    *,
    rain_mm_h=DEFAULT_RAIN_MM_H,
    soil=DEFAULT_SOIL,
    dt_s=DEFAULT_DT_S,
    sim_s=DEFAULT_SIM_S,
    grid=DEFAULT_GRID,
    cell_m=DEFAULT_CELL_M,
    open_edges=(),
):
```

Validate:

```python
VALID_EDGES = {"left", "right", "top", "bottom"}

unknown_edges = set(open_edges) - VALID_EDGES
if unknown_edges:
    raise ValueError(
        f"unknown open edges: {sorted(unknown_edges)}"
    )
```

Then:

```python
cfg = hs.HydroConfig(
    infiltration="green_ampt",
    open_edges=tuple(open_edges),
    enable_et=True,
    perc_factor=1.0,
    manning_overland=0.08,
    max_substeps=40,
)
```

Record:

```python
"configuration": {
    ...
    "open_edges": list(open_edges),
    "runoff_boundary_mode": (
        "open_edges"
        if open_edges
        else "closed_domain"
    ),
}
```

---

# 7. Spatial runoff needs an outlet mapping

Even with open edges, `overland_flow.py` returns only a grid:

```python
field
```

and aggregate balance:

```python
outflow_m3
```

It does not say:

- which cells exported water;
- which outlet corresponds to the Firehole;
- where that outflow should enter the river;
- what delay applies;
- what fraction reaches the modeled reach.

Add an outlet result if hydrosim exposes it:

```python
"outlets": [
    {
        "edge": "south",
        "flow_m3_s": ...,
        "chainage_m": ...,
        "receiving_river_id": "river_5856_0",
        "status": "authored_connection_not_measured",
    }
]
```

If hydrosim only gives total outflow, do not invent a spatial allocation. Return:

```python
"outflow_mapping_status": "not_available"
```

and keep it separate from river forcing.

---

# 8. The provider currently has no lag or storage

The provider assumes:

```python
Q_runoff(t) = C × i(t) × A
```

Real catchment discharge usually has lag and routing. A simple improvement is a linear reservoir:

\[
Q_\text{out}(t)
=
Q_\text{base}(t)
+
\frac{S(t)}{\tau}
\]

\[
\frac{dS}{dt}
=
P_\text{excess}(t) - Q_\text{out}(t)
\]

A discrete version:

```python
def route_linear_reservoir(
    runoff_m3_s: list[float],
    dt_s: float,
    tau_s: float,
    initial_storage_m3: float = 0.0,
) -> list[float]:
    dt = _finite(dt_s, "dt_s")
    tau = _finite(tau_s, "tau_s")

    if dt <= 0.0:
        raise ValueError("dt_s must be > 0")
    if tau <= 0.0:
        raise ValueError("tau_s must be > 0")

    storage = _nonnegative(
        initial_storage_m3,
        "initial_storage_m3",
    )

    output = []

    for inflow in runoff_m3_s:
        inflow = _nonnegative(inflow, "runoff flow")

        storage += inflow * dt
        outflow = storage / tau
        outflow = min(outflow, storage / dt)

        storage -= outflow * dt
        output.append(outflow)

    return output
```

Then `predict_discharge()` can optionally route the rational-method runoff:

```python
routed = route_linear_reservoir(
    direct_flows,
    step,
    routing_tau_s,
)
```

But label this as:

```text
synthetic routed runoff
```

until `tau_s` is calibrated against a gauge.

---

# 9. Add infiltration and antecedent wetness to the provider

The rational coefficient is currently a single static number:

```python
runoff_coefficient=0.4
```

That can be useful as a baseline, but it ignores:

- soil;
- initial wetness;
- storm intensity;
- snowpack;
- frozen ground;
- impervious/rocky area;
- prior precipitation.

A simple parameterization could be:

```python
effective_coeff = clamp(
    runoff_coefficient
    + wetness_sensitivity * antecedent_wetness
    + intensity_sensitivity * max(0, rain - threshold),
    0,
    1,
)
```

But this should not be added without calibration. Better is to expose it as an explicitly authored scenario:

```python
"runoff_coefficient_mode": "constant_authored"
```

For scientific use, calibrate it against observed discharge events.

---

# 10. `predict_discharge_landlab()` has questionable outlet logic

Current code:

```python
grid.set_closed_boundaries_at_grid_edges(True, True, True, True)
outlet = int(np.argmin(field))
grid.status_at_node[outlet] = grid.BC_NODE_IS_FIXED_VALUE
FlowAccumulator(grid).run_one_step()
```

Problems:

1. The lowest elevation cell is not necessarily the intended hydrologic outlet.
2. A fixed-value node is not necessarily the appropriate open-flow boundary.
3. All edges are closed before one arbitrary cell is modified.
4. The outlet may be an interior depression rather than the catchment outlet.
5. The result is a drainage area, not an actual routed discharge hydrograph.
6. A tilted plane has no explicit outlet definition.

Use an explicit outlet:

```python
def predict_discharge_landlab(
    elevation,
    dx_m,
    precip_mm_h,
    *,
    outlet_row: int | None = None,
    outlet_col: int | None = None,
    **kwargs,
):
```

Validate it:

```python
rows, cols = field.shape

if outlet_row is None or outlet_col is None:
    raise ValueError(
        "explicit outlet_row and outlet_col are required"
    )

if not (
    0 <= outlet_row < rows
    and 0 <= outlet_col < cols
):
    raise ValueError("outlet is outside elevation grid")
```

Prefer an outlet on the boundary unless the model intentionally represents an interior sink.

Also preserve:

```python
"outlet_index": outlet,
"drainage_area_m2": area,
"boundary_condition": ...,
```

in the result.

---

# 11. `synthetic_elevation()` needs stricter validation

Current code allows:

```python
slope = 0.0
```

which is valid as a flat test, but the function does not reject non-finite or extreme values. It also converts dimensions with:

```python
rows = int(nrows)
cols = int(ncols)
```

so `8.9` silently becomes `8`.

Use:

```python
def _positive_int(name, value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value
```

Then:

```python
rows = _positive_int("nrows", nrows)
cols = _positive_int("ncols", ncols)
```

Also validate that `slope` is dimensionless and nonnegative.

---

# 12. The uncertainty interval needs a better design

Current:

```python
spread_frac=0.3
```

produces:

```python
q_lo = q * 0.7
q_hi = q * 1.3
```

This is not a calibrated uncertainty interval.

Better options:

## If it is an authored scenario band

Rename:

```python
scenario_spread_fraction
```

and output:

```python
"uncertainty": {
    "type": "authored_symmetric_relative_band",
    "fraction": spread,
    "coverage_claim": None,
}
```

## If it is a calibrated interval

Estimate uncertainty from observed events and return:

```json
{
  "uncertainty": {
    "type": "empirical_prediction_interval",
    "coverage": 0.9,
    "method": "event_bootstrap",
    "n_events": 18
  }
}
```

Do not use `coverage=0.90` alone as evidence of 90% coverage.

---

# 13. Create one common runoff result schema

Both modules should emit a compatible schema.

For example:

```python
{
    "schema": "yellowstone.runoff_series.v1",
    "time": {
        "start_epoch_unix": 1784154000.0,
        "dt_s": 900.0,
        "n": 8
    },
    "forcing": {
        "precipitation_mm_h": [...],
        "soil": "sandy_loam",
        "antecedent_wetness": 0.5
    },
    "discharge": {
        "m3_s": [...],
        "source": "hydrosim|runoff_coefficient",
        "routing": "none|linear_reservoir"
    },
    "spatial": {
        "grid": 256,
        "cell_m": 8.0,
        "surface_depth_m": [...],
        "outflow_m3": 0.0
    },
    "provenance": {
        "status": "illustrative_not_calibrated",
        "model_version": "yellowstone_python-0.1.0"
    }
}
```

Then the river adapter can consume only:

```python
result["discharge"]["m3_s"]
```

and not care whether the source was hydrosim or the simpler provider.

---

# 14. Connect overland output to the provider carefully

A sensible integration path is:

```text
overland_flow.run_overland()
    ↓
surface water + total outlet flow
    ↓
convert outlet volume to discharge series
    ↓
route through lag/storage model
    ↓
river boundary/lateral forcing
```

But `run_overland()` currently runs only one constant-rain scenario and returns one aggregate balance. It cannot produce a realistic time-varying hydrograph yet.

Change the API to accept rainfall forcing:

```python
rain_mm_h: float | list[float] | dict
```

For example:

```python
rain_mm_h = {
    "times_s": [0, 900, 1800],
    "values": [0.0, 20.0, 5.0],
}
```

Then:

```python
rain_series = Series.parse(rain_mm_h)
```

and step hydrosim using:

```python
rain_now = rain_series.at(elapsed)
sim.step(step, rain_now)
```

Record output after every step:

```python
outflow_series.append({
    "t_s": elapsed,
    "outflow_m3_s": current_outflow,
})
```

This is the point where `overland_flow.py` becomes a hydrologic forcing generator rather than a single-state visual diagnostic.

---

# 15. Hydrology-to-river wiring should use lateral inflow, not necessarily upstream boundary flow

The provider docstring says:

```python
Synthetic-catchment runoff mapped to an upstream discharge series.
```

That is a strong assumption. If the catchment drains onto the modeled river reach, it may be a lateral inflow, not an upstream boundary condition.

Decide explicitly:

```text
upstream catchment:
    adds to boundary_m3_s

within-reach catchment:
    becomes a Source with cell_id and temperature

outside modeled reach:
    not included

unknown:
    do not wire automatically
```

For lateral runoff:

```python
Source(
    id="synthetic_catchment_runoff",
    cell_id="firehole_cell_00012",
    flow_m3_s=runoff_series,
    temperature_c=rain_or_soil_temperature_series,
)
```

This requires scheduled source discharge support in `River`. Until then, it should remain an external artifact rather than being silently collapsed to a mean.

---

# 16. Surface runoff temperature is missing

`overland_provider.py` produces only discharge. If runoff enters the thermal river model, it also needs temperature.

At minimum, define:

```text
runoff_temperature_c
```

Possible choices:

- rainfall temperature;
- air temperature;
- soil surface temperature;
- snowmelt temperature;
- measured tributary/runoff temperature.

Do not silently use river boundary temperature. That would remove the thermal effect of the runoff.

A normalized result should include:

```json
{
  "discharge_m3_s": [...],
  "temperature_c": [...],
  "temperature_status": "authored_rain_temperature"
}
```

or explicitly:

```json
"temperature_status": "not_provided_not_usable_for_heat_transport"
```

---

# 17. What can be calibrated

## `overland_flow.py`

Potential calibration targets:

- Green-Ampt suction/head parameters;
- hydraulic conductivity;
- initial wetness;
- Manning overland roughness;
- ET parameters;
- drainage/percolation coefficient;
- outlet boundary condition;
- soil map;
- DEM conditioning.

Observations needed:

- rain gauge;
- soil moisture;
- surface depth;
- runoff volume;
- outlet discharge;
- timing of hydrograph peaks.

## `overland_provider.py`

Potential calibration targets:

- runoff coefficient;
- routing time constant;
- baseflow;
- event-dependent coefficient;
- uncertainty interval.

Observations needed:

- rainfall event totals;
- catchment area;
- outlet discharge hydrographs;
- antecedent moisture.

## Important

Do not calibrate the runoff coefficient against river temperature alone. It is confounded with runoff temperature, river volume, lateral location, dispersion, and heat exchange.

---

# 18. Recommended implementation order

## Immediate fixes

1. Reject booleans in `overland_provider._finite()`.
2. Require `dt_s > 0`.
3. Make `series_spec()` semantics explicit.
4. Replace arbitrary Landlab outlet selection with an explicit outlet.
5. Rename the uncertainty band so it is not mistaken for a validated interval.
6. Add schema/provenance fields to both outputs.

## Integration fixes

7. Allow rainfall time series in `overland_flow.py`.
8. Record outflow at every timestep.
9. Add routing/storage.
10. Add runoff temperature.
11. Create a common runoff-series schema.
12. Add scheduled-flow support to `river_transport.py`.

## Scientific improvements

13. Open and condition the correct hydrologic outlet.
14. Calibrate soil/infiltration and routing against runoff observations.
15. Use surveyed catchment area and drainage boundaries.
16. Validate hydrograph timing and volume separately.
17. Couple only accepted/validated runoff products into river claims.

---

## Bottom line

`overland_flow.py` is currently a **spatial surface-water diagnostic** with a closed domain. `overland_provider.py` is a **simple synthetic discharge generator**. They should not currently be treated as interchangeable.

The clean architecture is:

```text
rainfall + terrain + soil
        ↓
hydrosim spatial model
        ↓
surface depth + outlet runoff series
        ↓
routing/storage
        ↓
discharge and runoff temperature series
        ↓
River scheduled lateral/boundary forcing
        ↓
thermal transport and calibration
```

Until that wiring exists, keep the provider’s discharge separate from the hydrosim field and label both as illustrative, uncalibrated products.