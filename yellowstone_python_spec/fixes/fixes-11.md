## Audit summary

The strongest issue is in `benchmarks.py`: **the restart-equivalence benchmark is invalid because all `River` instances share the same mutable `Cell` objects**. That can make the benchmark appear to pass or fail for the wrong reason.

Other important issues:

- Several numerical helpers silently accept malformed or mismatched arrays.
- Calibration uses a mean discharge rather than the measured time-varying discharge.
- Train/holdout configuration is insufficiently validated.
- Time-series ordering and duplicate timestamps are not safely handled.
- The IVP cross-check has a questionable pre-grid hold behavior and fragile floating-point divisibility checks.
- Parameter and geometry constraints are mostly unchecked.

---

# `benchmarks.py`

## Critical: restart benchmark shares mutable cells

Current code:

```python
cells = [
    Cell(...)
    for i in range(5)
]

def make() -> River:
    return River(
        cells,
        ...
    )
```

Every call to `make()` reuses the same `Cell` instances.

Therefore:

```python
whole = make()
whole.run(...)

split = make()
```

does not create a fresh split run. `split` starts with cells already modified by `whole`.

Likewise:

```python
mid = make()
mid.run(...)
```

also starts from the shared, already-mutated cells.

### Fix

Construct the cells inside `make()`:

```python
def make() -> River:
    cells = [
        Cell(
            f"c{i}",
            50.0,
            22.0,
            50.0 * 22.0 * 1.1,
            15.0,
            dispersion_m2_s=1.0,
            exchange_w_m2_k=12.0,
        )
        for i in range(5)
    ]
    return River(
        cells,
        boundary_m3_s=8.0,
        boundary_c=17.5,
        air_c=9.0,
        sources=[Source("lat", "c2", 0.25, 60.0)],
    )
```

This should be fixed before trusting any benchmark result.

---

## `_max_abs_diff()` fails unclearly on empty inputs

```python
return max(abs(x - y) for x, y in zip(a, b))
```

Problems:

- unequal lengths are silently truncated;
- empty lists raise `ValueError: max() arg is an empty sequence`.

### Fix

```python
def _max_abs_diff(a, b) -> float:
    if len(a) != len(b):
        raise ValueError("sequences must have equal length")
    if not a:
        raise ValueError("sequences must be nonempty")
    return max(abs(x - y) for x, y in zip(a, b))
```

---

## `_observed_rates()` is fragile around zero errors

```python
return [math.log2(a / b) for a, b in zip(errors, errors[1:])]
```

This fails or produces misleading values when:

- `a == 0`,
- `b == 0`,
- either error is negative,
- values are NaN or infinity.

A manufactured or exactly solvable case can legitimately produce a zero error.

### Fix

```python
def _observed_rates(errors: list[float]) -> list[float]:
    if len(errors) < 2:
        raise ValueError("at least two errors are required")
    for e in errors:
        if not math.isfinite(e) or e < 0:
            raise ValueError("errors must be finite and nonnegative")

    rates = []
    for coarse, fine in zip(errors, errors[1:]):
        if fine == 0.0:
            rates.append(math.inf if coarse > 0.0 else 0.0)
        elif coarse == 0.0:
            rates.append(-math.inf)
        else:
            rates.append(math.log2(coarse / fine))
    return rates
```

The benchmark should then decide how infinite rates are handled.

---

## Benchmark pass criteria are hard-coded around expected rates

Examples:

```python
passed = all(0.7 <= r <= 1.3 for r in rates)
```

and:

```python
passed = all(1.5 <= r <= 2.5 for r in spatial_rates)
```

This is reasonable for a smoke test, but the result does not record:

- the tolerance policy,
- the expected order,
- whether the rate was degraded by boundary effects,
- whether a parameter was outside the asymptotic regime.

Add explicit fields:

```python
"rate_tolerance": [0.7, 1.3],
"expected_order": 1.0,
```

---

## Conservative tracer benchmark may be boundary-contaminated

The initial pulse is centered in the domain, but the expected displacement is:

```python
expected = discharge / (width_m * depth_m) * duration_s
```

At 8 m³/s and 22 × 1.1 m, the velocity is approximately 0.331 m/s, so over 600 seconds the pulse moves approximately 199 m. That is probably safe in this case, but the benchmark should explicitly verify that the pulse remains sufficiently far from the outlet.

Otherwise, advective loss through the outlet shifts the centroid and makes the solver look inaccurate.

Add a domain-retention check based on the pulse support or anomaly mass.

---

## Diffusive decay initial condition is not exactly compatible with discrete boundary treatment

The analytic solution uses:

```python
math.cos(wave * x)
```

with a Neumann boundary condition. The cell-center initial condition is appropriate for a finite-volume approximation, but the boundary closure and cell-centered discrete Laplacian may not correspond exactly to the continuous cosine solution.

This is acceptable as a convergence test, but the docstring should say it is a **cell-center comparison to the continuous solution**, not an exact discrete eigenmode test.

For a sharper benchmark, use a discrete eigenmode matching the actual boundary stencil.

---

## MMS benchmark needs a stronger boundary statement

The manufactured wave is:

```python
exact(x, t) = air + amp * sin(wave * (x - vel * t))
```

The boundary is prescribed at `x=0`, while the outlet is governed by the solver's boundary closure. The interior norm excludes the first and last cells:

```python
if 0 < i < n - 1
```

That is sensible, but the benchmark should report:

- which cells were excluded;
- whether the source is applied at all cells;
- whether the boundary errors are separately recorded.

Otherwise it is easy to overstate full-domain convergence.

---

## `benchmark_closed_thermal()` does not explicitly test source-free isolation

```python
river = River(cells, 0.0, 0.0)
```

This assumes the `River` implementation treats zero discharge and zero boundary temperature as a closed system. If the solver still applies a boundary exchange or outlet operation at Q=0, the test may not represent a true closed system.

Make the intent explicit in the solver API if possible, or test the budget components directly:

```python
assert budget["boundary_input_j"] == 0
assert budget["outlet_export_j"] == 0
```

---

# `calibrate.py`

## Critical: calibration replaces time-varying discharge with its mean

In `_fit_forcing_arrays()`:

```python
mean_q = math.fsum(up_q) / len(up_q)
```

Then:

```python
river = build_fit_river(
    ...,
    arrays["mean_q"],
    ...
)
```

The upstream discharge series is read and interpolated, but only its mean is used in the model.

This means the calibration does not actually use measured discharge dynamics. It fits a constant-discharge model while the output claims upstream gauge discharge supplies the boundary forcing.

### Options

#### Option A: explicitly declare mean discharge

Rename the field and provenance:

```python
"boundary_q_policy": "mean_upstream_discharge"
```

#### Option B: support time-varying discharge

Pass a `Series` into `River` if supported:

```python
boundary_m3_s=arrays["up_q_series"]
```

and include it in `_fit_forcing_arrays()`:

```python
"up_q_series": to_series(up_q)
```

This is the more physically faithful fix.

---

## `_fit_forcing_arrays()` assumes raw series are chronologically ordered

```python
t0 = max(up["temperature_c"][0][0], met_rows[0][0])
t1 = min(up["temperature_c"][-1][0], met_rows[-1][0])
```

But `check_continuity()` sorts timestamps internally. If the input records are unordered, the continuity check may pass while `t0` and `t1` are wrong.

### Fix

Normalize every input series once:

```python
def _sorted_pairs(pairs, label):
    clean = sorted(
        (_finite(t, f"{label} time"), _finite(v, f"{label} value"))
        for t, v in pairs
    )
    if any(t1 <= t0 for (t0, _), (t1, _) in zip(clean, clean[1:])):
        raise ValueError(f"{label}: timestamps must be strictly increasing")
    return clean
```

Then use the normalized values everywhere.

---

## Duplicate timestamps are not rejected

`interp_series()` sorts duplicate times and uses:

```python
frac = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
```

This silently accepts duplicate records and arbitrarily favors one value.

For gauge and meteorological data, duplicate timestamps should either be:

- aggregated explicitly,
- deduplicated with a documented rule,
- rejected.

Rejecting is safest for calibration.

---

## `check_continuity()` does not validate `max_gap_s`

```python
if worst > max_gap_s:
```

A negative or NaN threshold produces invalid behavior.

Also, intervals are derived after sorting, so duplicated timestamps result in zero-length intervals rather than an error.

### Fix

```python
max_gap_s = _finite(max_gap_s, "max_gap_s")
if max_gap_s <= 0:
    raise ValueError("max_gap_s must be positive")
```

Reject nonpositive intervals after sorting.

---

## `resample_bin_mean()` does not implement its documented bin boundaries exactly

The docstring says bin `i` covers:

```text
[origin + (i - 0.5) * dt, origin + (i + 0.5) * dt)
```

But the implementation uses:

```python
index = int(round((epoch - origin) / dt_s))
```

This creates tie and boundary behavior that depends on Python's banker rounding. For example, a point exactly halfway between bins may be assigned unexpectedly.

### Fix

Use an explicit floor-based index:

```python
index = math.floor((epoch - origin + 0.5 * dt_s) / dt_s)
```

Then define the right-edge convention clearly.

Also, duplicate observations in one bin are averaged, which is fine, but the output should record counts if coverage quality matters.

---

## `resample_bin_mean()` does not validate sorted grid spacing

It assumes:

- `grid` is sorted;
- spacing equals `dt_s`;
- grid values are finite.

Add:

```python
grid = [_finite(v, "grid time") for v in grid]
if any(b <= a for a, b in zip(grid, grid[1:])):
    raise ValueError("grid must be strictly increasing")
```

Optionally verify uniform spacing.

---

## `pulse_moments()` silently truncates mismatched arrays

```python
zip(volume_m3, anomalies, centers_m)
```

If lengths differ, the extra values are ignored.

It also does not validate volumes or positions. Negative volume values can produce invalid mass or variance.

### Fix

```python
if not (
    len(centers_m)
    == len(volume_m3)
    == len(temperatures_c)
):
    raise ValueError("centers, volumes, and temperatures must have equal length")

volumes = [_finite(v, "volume") for v in volume_m3]
if any(v <= 0 for v in volumes):
    raise ValueError("volumes must be positive")
```

---

## `uniform_pulse_run()` lacks parameter validation

These can produce divisions by zero or nonsensical experiments:

```python
dx = length_m / n_cells
...
d_eff = (...) / (2.0 * duration_s)
...
expected = discharge_m3_s / (width_m * depth_m) * duration_s
```

Validate:

- `length_m > 0`;
- `n_cells >= 8`;
- width/depth/discharge nonnegative or positive as appropriate;
- `pulse_sigma_m > 0`;
- `duration_s > 0`;
- `dt_s > 0`;
- `duration_s / dt_s` is compatible with `River.run`;
- dispersion `>= 0`.

The current code only validates `n_cells`.

---

## Cold-pulse semantics are confusing

The docstring says:

```text
A cold pulse needs the sign flipped by the caller, explicitly.
```

But the default setup is:

```python
background_c=15.0
pulse_c=5.0
initial_c=background_c + pulse_c * exp(...)
```

That is a warm pulse of +5 °C, not a cold pulse. The variable name `pulse_c` is ambiguous.

### Improve

Use:

```python
pulse_amplitude_c: float = 5.0
```

and document positive/negative amplitude. Or make the default explicitly warm.

---

## `reach_heat_fit()` needs stronger grid and split validation

This line assumes all parameter grids are nonempty:

```python
probe = forward(lateral_q_grid[0], lateral_t_grid[0], c_mult_grid[0])
```

Also, these cases are not rejected:

- `train_frac <= 0` or `>= 1`;
- negative `spinup_s`;
- spinup that leaves fewer than two training samples;
- empty holdout;
- negative lateral discharge;
- invalid or empty parameter grids;
- NaN or infinity in grid values.

Add a shared validation helper:

```python
def validate_fit_config(
    volume_m3,
    area_m2,
    q_grid,
    t_grid,
    c_grid,
    spinup_s,
    train_frac,
    dt_s,
):
    if volume_m3 <= 0 or area_m2 <= 0:
        raise ValueError("volume and area must be positive")
    if not q_grid or not t_grid or not c_grid:
        raise ValueError("parameter grids must be nonempty")
    if not 0.0 < train_frac < 1.0:
        raise ValueError("train_frac must lie strictly between 0 and 1")
    if spinup_s < 0 or dt_s <= 0:
        raise ValueError("invalid spinup or timestep")
```

---

## The calibration output does not report whether the champion is on a grid boundary

A fitted result at:

- minimum/maximum lateral flow;
- minimum/maximum lateral temperature;
- minimum/maximum exchange multiplier;

is a warning that the optimum may lie outside the searched domain.

Record:

```python
"at_parameter_boundary": {
    "q_lat": ...,
    "t_lat": ...,
    "c_mult": ...,
}
```

Do this for both the grid champion and least-squares solution.

---

## Null model B can be mislabeled

If `c_mult_grid` does not contain zero:

```python
zero = forward(champion["q_lat"], champion["t_lat"], 0.0)
```

The lateral parameters are not refit for the no-exchange model. The output calls the fallback:

```python
"mixing_only_c0_at_champion_laterals"
```

That name is accurate, but the module-level documentation says:

```text
Null B ... Q_lat/T_lat refit on train.
```

That statement is false in the fallback path.

### Fix

Either:

1. require `0.0 in c_mult_grid`, or
2. separately optimize/refit `q_lat` and `t_lat` with `c_mult=0`.

The second option is preferable.

---

## Null-model parameter counts in AIC/BIC should be explicit

In the CLI:

```python
for null, k in zip(fit_doc["null_models"], (0, 2, 1)):
```

This relies on the fixed ordering:

```python
[null_a, null_b, null_c]
```

That is fragile. Use names:

```python
parameter_counts = {
    "upstream_persistence": 0,
    "mixing_only_c0_refit": 2,
    "mixing_only_c0_at_champion_laterals": 0,
    "downstream_climatology": 1,
}
```

Also ensure the AIC/BIC parameter count matches the actual fit performed.

---

## AIC/BIC calculation is undefined for perfect fits

```python
base = n * math.log(rss / n)
```

If `rss == 0`, this raises a math-domain error. Exact zero is unlikely with observations but should be handled:

```python
if rss == 0.0:
    return {
        "aic": -math.inf,
        "bic": -math.inf,
        "n": float(n),
        "k": float(k),
    }
```

Or reject it explicitly with a clearer explanation.

---

## `least_squares_fit()` can start outside its bounds

The grid search permits values outside:

```python
LS_BOUNDS = {
    "q_lat": (0.5, 8.0),
    "t_lat": (-10.0, 60.0),
    "c_mult": (0.0, 8.0),
}
```

For example, a user can provide a grid champion with `q_lat=0.0`, then SciPy may reject the initial point.

### Fix

Validate or clip `x0`:

```python
for value, lo, hi in zip(x0, lower, upper):
    if not lo <= value <= hi:
        raise ValueError("x0 must lie within least-squares bounds")
```

Also make sure the grid search bounds and LS bounds are deliberately aligned.

---

## `max_nfev` is not validated

```python
least_squares(..., max_nfev=max_nfev)
```

A zero or negative value will fail downstream. Validate it before invoking SciPy.

---

## `ivp_crosscheck()` has fragile timestep divisibility

```python
if step <= 0 or dt_s % step != 0:
```

Floating-point modulo is unreliable. For example, `900.0 % 0.1` may not be exactly zero.

### Fix

```python
ratio = dt_s / step
if step <= 0 or not math.isclose(ratio, round(ratio), rel_tol=0, abs_tol=1e-9):
    raise ValueError("euler_dt_s must divide dt_s")
```

---

## `ivp_crosscheck()` has questionable pre-grid behavior

```python
if index < 0:
    index = len(values) - 1
```

If the solver evaluates before the first forcing time, this uses the final forcing value. That is almost certainly wrong. It should use the first value:

```python
if index < 0:
    index = 0
```

The current integration begins at zero, so this may not be triggered in normal operation, but it is unsafe.

---

## `ivp_crosscheck()` does not compare budget closure for the RK45 trajectory

It reports:

```python
"budget_ok": river.budget()["heat_relative_residual"] <= 1e-5
```

That only checks the backward-Euler `River` run. The RK45 trajectory is independently integrated but has no corresponding energy-budget residual.

Either rename the field:

```python
"euler_budget_ok"
```

or calculate an RK45 budget independently.

---

## `run_fit_forward()` has an undocumented sample alignment assumption

```python
frames = river.run(n * dt_s, dt_s=dt_s, sample_s=dt_s)
modeled = [f["temperature_c"][0] for f in frames]
```

The rest of the code assumes `modeled` has exactly `len(grid)` samples, including the initial state. That contract should be asserted:

```python
if len(modeled) != len(grid):
    raise ValueError(
        f"River returned {len(modeled)} frames for {len(grid)} grid times"
    )
```

Do the same in the IVP comparison.

---

## `build_fit_river()` does not validate geometry or fitted parameters

Invalid inputs can reach the solver:

```python
width_m=area_m2 / 1000.0
```

Potential failures include:

- zero or negative volume;
- zero or negative area;
- negative lateral flow;
- negative exchange multiplier;
- non-finite lateral temperature.

Validate before constructing the `River`.

---

# Recommended priority order

1. **Fix shared mutable cells in `benchmark_restart_equivalence()`.**
2. **Decide whether calibration supports time-varying discharge; currently it does not despite loading the series.**
3. Normalize and validate all timestamped series before continuity checks and interpolation.
4. Add strict parameter, geometry, grid, and train/holdout validation.
5. Fix the IVP pre-grid hold behavior and floating-point timestep divisibility.
6. Make Null B genuinely refit lateral parameters with `c_mult=0`.
7. Add boundary-of-grid diagnostics for fitted parameters.
8. Add length, finiteness, and positivity checks to moment calculations.
9. Assert model-frame/grid alignment.
10. Make benchmark edge cases—zero errors, empty series, boundary contamination—explicit rather than allowing raw numerical exceptions.