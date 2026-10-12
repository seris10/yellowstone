## Audit summary

The main issues are:

- `obs_frame.py` can silently fill leading/trailing gaps using nearest-value propagation.
- Its resampling labels may introduce a time shift and synthetic endpoint coverage.
- `obs_model.py` needs stronger validation and clearer handling of missing bins/errors.
- `plume2d.py` has a likely reversed north/south boundary implementation.
- `plume2d.py` lacks validation for several finite, positive, and physically meaningful parameters.
- The plume metrics can divide by zero or produce misleading results for cold/negative anomalies.

---

# 1. `obs_frame.py`

## Critical: boundary gaps can be silently extrapolated

`to_grid()` uses:

```python
.interpolate(
    method="linear",
    limit=limit,
    limit_direction="both"
)
```

With `limit_direction="both"`, leading and trailing missing values may be filled from the nearest measured value. That is not interpolation between observations; it is endpoint extrapolation/constant propagation.

The docstring says:

> Grid endpoints must lie inside measured coverage

but the implementation only checks against the frame index:

```python
first, last = frame.index[0], frame.index[-1]
```

It does not check that the actual first and last values are non-NaN.

### Recommended fix

Reject leading/trailing gaps before interpolation:

```python
def _assert_no_edge_gaps(frame: Any, name: str) -> None:
    values = frame["value"] if "value" in frame else frame

    if values.iloc[0].isna() if hasattr(values.iloc[0], "isna") else False:
        raise ValueError(f"{name}: leading gap cannot be bridged")

    if values.iloc[-1].isna() if hasattr(values.iloc[-1], "isna") else False:
        raise ValueError(f"{name}: trailing gap cannot be bridged")
```

For a one-column frame:

```python
def assert_no_edge_gaps(frame: Any, name: str) -> None:
    values = frame["value"] if "value" in frame else frame.squeeze()

    if pd.isna(values.iloc[0]) or pd.isna(values.iloc[-1]):
        raise ValueError(
            f"{name}: leading/trailing missing values cannot be bridged"
        )
```

Then use:

```python
values = (
    frame.reindex(frame.index.union(stamps))
    .interpolate(
        method="linear",
        limit=limit,
        limit_direction="forward",
        limit_area="inside",
    )
    .reindex(stamps)
)
```

`limit_area="inside"` is especially important because it prevents filling outside the observed range.

---

## Critical: resampling may shift observations

`_frame_from_pairs()` says it creates nominal-step bins, but:

```python
frame.resample(f"{step_s:g}s", origin=frame.index[0]).mean()
```

uses left-labeled bins by default. If the first observation is at `t0`, the first bin represents approximately:

```text
[t0, t0 + step)
```

but is labeled `t0`, not the bin center. The output is therefore not actually “interval centers from the first time.”

`interval_average()` in `obs_model.py` labels bins at:

```python
t0 + (k + 0.5) * interval_s
```

so the two paths use different time conventions.

### Fix one convention and use it everywhere

For left-edge labels:

```python
return frame.resample(
    f"{step_s:g}s",
    origin=frame.index[0],
    label="left",
    closed="left",
).mean()
```

For center labels:

```python
return (
    frame.resample(
        f"{step_s:g}s",
        origin=frame.index[0],
        label="left",
        closed="left",
    )
    .mean()
    .set_axis(
        frame.resample(
            f"{step_s:g}s",
            origin=frame.index[0],
            label="left",
            closed="left",
        ).mean().index
        + pd.to_timedelta(step_s / 2.0, unit="s")
    )
)
```

The simpler solution is to define one shared binning helper and use it in both modules.

---

## Critical: frame index does not necessarily represent measured coverage

A resampled frame can contain a final bin whose timestamp is later than the last actual observation. This makes this check potentially too permissive:

```python
if stamps[-1] > last:
    raise ValueError(...)
```

`last` may be the end label of a partially populated bin rather than the timestamp of a measurement.

### Improvement

Track actual coverage separately:

```python
observed_first = frame.index[frame.notna().any(axis=1)][0]
observed_last = frame.index[frame.notna().any(axis=1)][-1]
```

Use those timestamps for endpoint validation, and separately record the resampling-bin extent.

---

## Numeric validation is incomplete

These expressions can accept `NaN` and infinity:

```python
float(v)
pd.to_datetime(...)
```

Affected inputs include:

- observation times,
- observation values,
- `step_s`,
- grid values,
- `limit`,
- `window_steps`,
- `dt_s`.

### Add helpers

```python
def _finite(name: str, value) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    return out
```

Then validate:

```python
step_s = _finite("step_s", step_s)
if step_s <= 0:
    raise ValueError("step_s must be positive")
```

Also validate all pair rows before constructing the DataFrame:

```python
clean = []
for i, pair in enumerate(pairs):
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        raise ValueError(f"{name}: pair {i} must be [epoch, value]")
    clean.append((_finite(f"{name}[{i}].epoch", pair[0]),
                  _finite(f"{name}[{i}].value", pair[1])))
```

---

## Duplicate timestamp policy is inconsistent with the docstring

The comment says:

> Values sharing a bin are averaged

but exact duplicate timestamps are handled first with:

```python
frame = frame[~frame.index.duplicated(keep="last")]
```

So exact duplicates are not averaged; the last value wins.

### Fix

Remove the deduplication and let resampling average duplicates:

```python
frame = frame.sort_index()
return frame.resample(...).mean()
```

If duplicates should be rejected instead:

```python
if frame.index.has_duplicates:
    raise ValueError(f"{name}: duplicate timestamps are not allowed")
```

Pick one policy and record it in provenance.

---

## `met_frame()` needs row-shape validation

This currently assumes every row has at least six fields:

```python
[r[1] for r in rows]
```

A malformed row causes an opaque `IndexError`.

### Fix

```python
for i, row in enumerate(rows):
    if not isinstance(row, (list, tuple)) or len(row) != 6:
        raise ValueError(
            f"met row {i}: expected [epoch, air, rh, wind, sw, cloud]"
        )
```

Also validate each numeric field as finite.

---

## `daily_met_means()` annotation is incorrect

It declares:

```python
def daily_met_means(frame: Any) -> dict[str, float]:
```

but returns lists:

```python
return {column: [float(v) for v in daily[column]] ...}
```

Correct it to:

```python
def daily_met_means(frame: Any) -> dict[str, list[float]]:
```

---

## `aligned_fit_arrays()` hard-codes one site

```python
up = bundle["sites"]["06036805"]["series"]
```

This makes the function unusable for another upstream station and can silently conflict with station metadata.

### Improvement

Accept a station parameter:

```python
def aligned_fit_arrays(
    bundle: dict[str, Any],
    dt_s: float = 900.0,
    upstream_site: str = "06036805",
) -> dict[str, Any]:
```

Then validate that the station exists and that its nominal interval agrees with the configured frame step.

---

## `aligned_fit_arrays()` has a dependency cycle smell

It imports:

```python
from .calibrate import _fit_forcing_arrays
```

only to obtain the grid convention. If `calibrate` later imports `obs_frame`, this can become a circular import.

### Improvement

Extract grid construction into a dependency-light helper:

```python
from .fit_grid import build_fit_grid
```

Both `calibrate` and `obs_frame` should use that public helper.

---

# 2. `obs_model.py`

## `interval_average()` validates too late

This occurs before numeric conversion:

```python
t0 = min(times)
```

If values are strings, mixed types, or contain invalid data, `min()` can produce incorrect behavior or an opaque exception.

### Fix

Normalize first:

```python
clean_times = []
clean_values = []

for i, (t, v) in enumerate(zip(times, values)):
    t = _finite(f"times[{i}]", t)
    v = _finite(f"values[{i}]", v)
    clean_times.append(t)
    clean_values.append(v)

t0 = min(clean_times)
```

Also validate `interval_s` as finite before comparing it to zero.

---

## `interval_average()` omits empty bins

It returns only bins containing observations:

```python
centers = [ ... for k in sorted(bins)]
```

For time series alignment, this may be dangerous because an absent bin is different from a missing observation. The caller cannot distinguish:

- a regularly spaced series;
- a series with missing intervals.

### Improvement

Return every bin from first to last, with `NaN` for empty bins:

```python
first_bin = 0
last_bin = max(bins)

centers = [
    t0 + (k + 0.5) * interval_s
    for k in range(first_bin, last_bin + 1)
]

means = [
    math.fsum(bins[k]) / len(bins[k]) if k in bins else math.nan
    for k in range(first_bin, last_bin + 1)
]
```

This would make `interval_average()` consistent with the explicit gap behavior in `obs_frame.py`.

---

## `compare()` does not validate errors

The function accepts:

```python
measurement_error: Any = 0.2
representativeness: Any = 0.6
```

and returns them unchanged. It should reject invalid uncertainty values:

```python
def _uncertainty(name: str, value) -> float:
    value = _finite(name, value)
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value
```

Then:

```python
measurement_error = _uncertainty(
    "measurement_error", measurement_error
)
representativeness = _uncertainty(
    "representativeness", representativeness
)
```

If these values are intended for a combined uncertainty calculation, expose that explicitly:

```python
combined_error = math.hypot(
    measurement_error,
    representativeness,
)
```

Currently the function reports the components but does not use them in scoring.

---

## `compare()` should validate paired lengths

This depends on `score_paired_series()` to do so:

```python
scores = score_paired_series(modeled, observed)
```

Validate locally or document the contract:

```python
if len(modeled) != len(observed):
    raise ValueError("modeled and observed must have equal length")
if not modeled:
    raise ValueError("modeled and observed must be nonempty")
```

Also reject non-finite paired values unless the scoring function explicitly supports missing values.

---

## Stage validation could be stronger

`stage_to_elevation_ft_navd88()` checks finiteness but accepts negative stage values. Whether this is valid depends on the gauge datum and domain.

At minimum, make it explicit:

```python
if stage < 0:
    raise ValueError("stage_ft must be >= 0")
```

If negative gauge stages are physically possible, retain the current behavior but document that only finiteness is enforced.

---

## Station metadata should be immutable

`STATIONS` is a mutable global dictionary. Code elsewhere can modify uncertainty or datum values at runtime.

Use immutable structures, such as frozen dataclasses:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Station:
    name: str
    datum_ft_navd88: float
    interval_s: float
    ...
```

This is not urgent, but it protects provenance-critical metadata.

---

# 3. `plume2d.py`

## Critical: north/south boundary conditions appear reversed

The module docstring says:

> the north edge is fixed at ambient_c; south edge is zero-gradient

But the implementation does:

```python
for i in range(nx):
    if idx(i, 0) not in fixed:
        fixed[idx(i, 0)] = float(ambient_c)
```

This fixes `j == 0` to ambient. Later:

```python
if j == nz - 1:
    mat[row, row] = 1.0
    mat[row, idx(i, j - 1)] = -1.0
```

This applies zero-gradient at `j == nz - 1`.

Given:

```python
zs = [(j / (nz - 1) - 0.5) * extent_m for j in range(nz)]
```

`j == 0` is south and `j == nz - 1` is north.

### Fix

If the docstring is correct, reverse the conditions:

```python
# South edge: zero-gradient is handled by the equation at j == 0.
# North edge: fixed ambient.
for i in range(nx):
    if idx(i, nz - 1) not in fixed:
        fixed[idx(i, nz - 1)] = float(ambient_c)
```

Then implement the south Neumann condition:

```python
if j == 0:
    mat[row, row] = 1.0
    mat[row, idx(i, j + 1)] = -1.0
    rhs[row] = 0.0
    continue
```

However, be careful with advection. For positive `u`, `j == 0` is the upstream boundary, so a zero-gradient upstream condition may be physically different from a downstream outflow condition. The boundary design should be explicitly reviewed against the coordinate convention.

Add a test that asserts the boundary values:

```python
sol = solve_steady(...)
field = np.asarray(sol["field"]).reshape(sol["nz"], sol["nx"])

assert np.allclose(field[-1, :], ambient_c)
assert np.allclose(field[0, 1:-1], field[1, 1:-1])
```

---

## Source cells can override boundary conditions

Source cells are assigned first:

```python
fixed[idx(i, j)] = float(source_c)
```

Then boundaries are assigned only when the cell is not already fixed:

```python
if idx(i, 0) not in fixed:
    fixed[idx(i, 0)] = float(ambient_c)
```

If `source_xz/source_r_m` reaches a boundary, the source temperature wins over the stated boundary temperature.

That may be intended, but it should be validated or explicitly documented.

### Options

Reject source regions touching fixed boundaries:

```python
if any(
    math.isclose(abs(x), extent_m / 2.0) or
    math.isclose(abs(z), extent_m / 2.0)
    for x, z in source_boundary_intersections
):
    raise ValueError("source region overlaps a fixed boundary")
```

Or define precedence explicitly in the output:

```python
"boundary_precedence": "source_cells_override_boundary"
```

---

## Numeric validation is incomplete

These checks allow `NaN` to pass:

```python
if extent_m <= 0 or d_long_m2_s <= 0 ...
if k_per_s < 0 ...
if u_m_s < 0 ...
```

For `NaN`, all comparisons are false.

Validate every parameter:

```python
def _finite(name: str, value) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value
```

Then:

```python
extent_m = _finite("extent_m", extent_m)
u_m_s = _finite("u_m_s", u_m_s)
d_long_m2_s = _finite("d_long_m2_s", d_long_m2_s)
d_trans_m2_s = _finite("d_trans_m2_s", d_trans_m2_s)
k_per_s = _finite("k_per_s", k_per_s)
source_r_m = _finite("source_r_m", source_r_m)
```

Validate:

```python
if extent_m <= 0:
    raise ValueError("extent_m must be > 0")
if d_long_m2_s <= 0 or d_trans_m2_s <= 0:
    raise ValueError("diffusivities must be > 0")
if u_m_s < 0:
    raise ValueError("u_m_s must be >= 0")
if k_per_s < 0:
    raise ValueError("k_per_s must be >= 0")
if source_r_m < 0:
    raise ValueError("source_r_m must be >= 0")
```

Also validate `source_xz` has exactly two finite values.

---

## `plume_metrics()` divides by zero when `k_per_s == 0`

```python
"exchange_length_u_over_k_m": round(u_m_s / k_per_s, 1)
```

`solve_steady()` explicitly permits:

```python
k_per_s == 0
```

### Fix

```python
exchange_length = (
    math.inf if k_per_s == 0 and u_m_s > 0
    else 0.0 if k_per_s == 0
    else u_m_s / k_per_s
)
```

JSON output cannot serialize infinity with strict JSON settings, so use `None`:

```python
exchange_length = None if k_per_s == 0 else u_m_s / k_per_s
```

and report:

```python
"exchange_length_u_over_k_m": (
    round(exchange_length, 1)
    if exchange_length is not None
    else None
),
"exchange_length_status": (
    "undefined_when_k_zero" if exchange_length is None else "defined"
),
```

---

## Solver output should be checked for finiteness

After:

```python
t = np.asarray(spsolve(...))
```

check:

```python
if not np.all(np.isfinite(t)):
    raise ValueError("plume solve returned non-finite temperatures")
```

Also check the sparse solve result for warnings or singularity. A singular or poorly conditioned matrix may otherwise produce invalid fields.

---

## `centerline()` needs dimension validation

It assumes:

```python
len(field) == nx * nz
```

Add:

```python
if len(field) != nx * nz:
    raise ValueError(
        f"field length {len(field)} != nx*nz={nx*nz}"
    )
if nx < 1 or nz < 1:
    raise ValueError("nx and nz must be positive")
```

---

## `plume_metrics()` can report misleading footprint lengths

This code:

```python
above = [j for j, v in enumerate(anom) if v >= thresh_c]
foot_len = zs[above[-1]] - zs[above[0]]
```

assumes the threshold region is contiguous. If there are multiple disjoint regions, it reports the span from the first to last region, including gaps.

### Improvement

Find contiguous threshold segments and report either:

- the longest connected segment;
- total threshold length;
- first downstream crossing;
- all segments.

For example:

```python
segments = []
start = None

for j, value in enumerate(anom):
    if value >= thresh_c and start is None:
        start = j
    elif value < thresh_c and start is not None:
        segments.append((start, j - 1))
        start = None

if start is not None:
    segments.append((start, len(anom) - 1))

longest = max(
    (zs[b] - zs[a] for a, b in segments),
    default=0.0,
)
```

---

## Negative plume anomalies are not handled clearly

If `source_c < ambient_c`, then:

```python
peak = max(anom)
```

may be negative or close to zero. The half-width calculation then uses:

```python
v >= 0.5 * peak
```

which can classify much of the field as “above half peak” in a nonsensical way.

### Fix

Require a warm plume:

```python
if source_c <= ambient_c:
    raise ValueError(
        "source_c must exceed ambient_c for warm-plume metrics"
    )
```

Or support both warm and cold plumes by using the maximum absolute anomaly and carrying a sign.

---

## `mixing_rise_c()` needs physical validation

Currently:

```python
return (...) / (q + river_m3s) - river_c
```

Potential problems:

- negative river flow;
- zero total flow;
- non-finite inputs;
- negative temperatures are probably valid, so only flow needs strict bounds.

### Fix

```python
def mixing_rise_c(river_m3s: float, river_c: float) -> float:
    river_m3s = _finite("river_m3s", river_m3s)
    river_c = _finite("river_c", river_c)

    if river_m3s < 0:
        raise ValueError("river_m3s must be >= 0")

    total_q = EXCELSIOR_M3S + river_m3s
    if total_q <= 0:
        raise ValueError("total discharge must be > 0")

    return (
        EXCELSIOR_M3S * EXCELSIOR_C + river_m3s * river_c
    ) / total_q - river_c
```

---

## The fully mixed bound check needs a clearer physical interpretation

This check:

```python
0.0 < peak <= rise + 1e-9
```

is only meaningful if:

- the source concentration/temperature is hotter than river water;
- the plume model’s source area and discharge are consistent with the mixing calculation;
- `rise` corresponds to the same thermal source and flow geometry.

At present, the 2-D source cells are fixed at `source_c`, while the fully mixed anchor uses:

```python
EXCELSIOR_C = 93.0
EXCELSIOR_M3S = 0.255
```

That is a useful conservative bound, but it should be labeled as a comparison anchor rather than a strict conservation test.

Suggested wording:

```python
"fully_mixed_bound_interpretation":
    "diagnostic upper-bound comparison; not a coupled heat-budget closure"
```

---

# Recommended implementation order

1. **Fix the plume north/south boundary-condition reversal.**
2. Add plume finite/bounds validation and `k_per_s == 0` handling.
3. Add plume field-finiteness and dimension checks.
4. Prevent `obs_frame.to_grid()` from filling edge gaps.
5. Standardize timestamp/bin labeling between `obs_frame.py` and `obs_model.py`.
6. Validate and preserve missing bins in `interval_average()`.
7. Add uncertainty and paired-series validation to `obs_model.compare()`.
8. Remove the hard-coded station ID from `aligned_fit_arrays()`.
9. Add regression tests for:
   - boundary conditions,
   - edge-gap rejection,
   - duplicate observations,
   - missing interval preservation,
   - zero exchange,
   - cold-plume behavior,
   - non-finite parameter rejection.