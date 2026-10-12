## Audit summary

The main risks are:

1. **`figures.py` has a definite plotting bug: the train shading spans zero width.**
2. **`figures.py` crashes when residual diagnostics return an empty Q-Q result, such as a perfect fit.**
3. **`hydraulics.py` claims Fischer dispersion requires positive velocity but permits zero velocity.**
4. **`hydraulics.residual_diagnostics()` divides by zero for constant nonzero residuals.**
5. **`datasets.py` validates temporal overlap only through aggregate min/max ranges, which can produce false overlap results for discontinuous datasets.**
6. **`identifiability.py` lacks validation and has compatibility problems in the SALib path.**

---

# `datasets.py`

## 1. Aggregate min/max windows can report false overlap

```python
return min(epochs), max(epochs)
```

This treats all observations between the first and last timestamp as occupied. For a dataset with two separated observation periods, a locked-final window located in the gap is incorrectly reported as overlapping.

If dataset windows are expected to be continuous, validate continuity and document that assumption. Otherwise return intervals:

```python
[(min_epoch, max_epoch), ...]
```

or derive explicit metadata from the bundle.

---

## 2. Epoch types are not validated

```python
epochs = [p[0] ...]
```

If one source stores timestamps as strings and another as numeric epochs, `min()` or comparisons may fail or behave inconsistently.

Validate that all timestamps are:

- numeric seconds, or
- normalized datetime values.

Also reject malformed series points rather than allowing `IndexError`.

---

## 3. `_bundle_range()` does not validate point structure

These expressions assume every row is a nonempty sequence:

```python
p[0]
row[0]
```

Malformed or null observations can crash the audit with an unrelated exception.

Add a helper:

```python
def _epoch(row, context):
    if not isinstance(row, (list, tuple)) or not row:
        raise ValueError(f"{context}: malformed observation row")
    value = float(row[0])
    if not math.isfinite(value):
        raise ValueError(f"{context}: nonfinite timestamp")
    return value
```

---

## 4. Role membership validation is exact-string dependent

```python
if aid not in claim["calibration_dataset_ids"]:
```

This requires the claim record to use exactly the same artifact IDs, including selectors such as `:train`. That is probably intended, but the error should distinguish:

- artifact exists but selector differs,
- artifact is absent from the claim,
- claim field is malformed.

---

## 5. `get_claim()` errors are not handled

`role_errors()` calls:

```python
claim = get_claim(CLAIM_ID)
```

outside the guarded section. A missing or malformed claim can raise instead of returning an audit error list.

Wrap claim lookup:

```python
try:
    claim = get_claim(CLAIM_ID)
except (KeyError, ValueError, FileNotFoundError) as exc:
    errors.append(f"claim {CLAIM_ID!r}: {exc}")
    return errors
```

---

## 6. `window_errors()` resolves the locked artifact repeatedly

`role_errors()` first resolves all role artifacts, then `window_errors()` resolves them again. This is minor, but a shared resolution/cache would:

- reduce filesystem work,
- avoid inconsistent results if artifacts change during the audit,
- make diagnostics easier to test.

---

## 7. Role exclusivity is not checked

The module checks locked-final overlap with calibration and development, but does not check:

- calibration versus development overlap,
- duplicate artifact IDs within a role,
- the same artifact appearing in multiple roles.

If the policy requires role separation, validate all pairwise role overlaps and membership conflicts.

---

# `figures.py`

## Critical: train shading is incorrect

```python
ax.axvspan(hours[0], hours[train.start], ...)
```

For the usual `train = slice(0, split)`, this shades from `hours[0]` to `hours[0]`, producing no visible train region.

The holdout should be shaded:

```python
holdout_start = train.stop
holdout_end = len(hours) - 1

ax.axvspan(hours[holdout_start], hours[holdout_end],
           color="gray", alpha=0.15)
```

Or, if the train region is intended:

```python
ax.axvspan(hours[train.start or 0], hours[train.stop - 1],
           color="gray", alpha=0.15)
```

The label currently says `"holdout"`, so shading the holdout is probably the intended behavior.

---

## Critical: perfect-fit residuals can crash figure generation

`residual_diagnostics()` returns:

```python
{"perfect_fit": True, "qq": {}}
```

Then `build_all()` does:

```python
qq_levels = sorted(resid["qq"])
...
residual_figure(...)
```

and `residual_figure()` calls:

```python
min(qq_normal)
min(qq_empirical)
```

which fails on empty lists.

Handle perfect fits explicitly:

```python
if resid.get("perfect_fit"):
    qq_empirical = [0.0]
    qq_normal = [0.0]
```

Better: make `residual_figure()` accept empty Q-Q data and display “Q-Q unavailable: perfect fit.”

---

## Figure functions lack length and slice validation

Examples:

```python
ax.plot(hours, target)
ax.plot(hours, modeled)
```

If one series has a different length, Matplotlib raises a low-level error. Validate all lengths at the function boundary.

For `fit_holdout_figure()`:

```python
n = len(grid)
for name, series in (...):
    if len(series) != n:
        raise ValueError(...)
if train.start not in (None, 0) or train.stop is None:
    ...
```

Likewise validate `holdout.start`, `holdout.stop`, and nonempty slices in `bands_figure()`.

---

## Generic `Sequence` slicing is not guaranteed to return the expected plotting type

This is usually fine for lists and tuples:

```python
h_hold = hours[holdout]
```

but arbitrary `Sequence` implementations may not support slice semantics as expected. Convert once:

```python
hours = list(...)
lo = list(lo)
mid = list(mid)
hi = list(hi)
target_holdout = list(target_holdout)
```

This also makes length checks straightforward.

---

## `bands_figure()` can misalign the target series

The function receives:

```python
target_holdout
```

but then uses:

```python
ax.plot(h_hold, target_holdout)
```

The caller passes:

```python
target[holdout]
```

so the contract is “already sliced.” That should be explicit in the parameter name/docstring, or pass the full target series and slice internally to prevent accidental double/missing slicing.

---

## `ridge_figure()` assumes exact float equality

```python
pts = [r for r in rows if r["c_mult"] == best_c]
```

If values came through JSON or floating-point calculations, exact equality can fail. Use a tolerance or select the nearest grid value:

```python
pts = [
    r for r in rows
    if math.isclose(r["c_mult"], best_c, rel_tol=0, abs_tol=1e-12)
]
```

If no points are found, raise a clear error instead of producing an empty plot.

---

## `ridge_figure()` can fail on empty rows

These expressions fail if `pts` is empty:

```python
ax.scatter(...)
```

or produce an uninformative empty figure. Validate:

```python
if not pts:
    raise ValueError(f"no ridge rows found for c_mult={best_c}")
```

Also validate required keys in `champion`, `polished`, and each row.

---

## Status text is hard-coded

```python
STATUS_NOTE = "fitted_not_validated_single_window"
```

Every figure will carry that label even when artifacts are:

- locked-final,
- independently validated,
- synthetic,
- exploratory.

Read status from the artifact documents and either reject inconsistent statuses or display the actual status.

---

## `_save()` should use the figure’s own canvas lifecycle

```python
import matplotlib.pyplot as plt
plt.close(figure)
```

This is generally okay, but it imports pyplot again and relies on the global pyplot state. Prefer:

```python
figure.savefig(...)
figure.clf()
```

or close through the figure manager if needed. Also consider specifying `bbox_inches="tight"` consistently.

---

## CLI error handling is incomplete

`build_all()` can raise:

- `IndexError`
- `TypeError`
- `AttributeError`
- `ImportError`
- SciPy/Matplotlib errors

but the CLI catches only:

```python
(ValueError, KeyError, ArithmeticError, OSError)
```

Catch expected artifact/schema errors explicitly, but avoid hiding programming errors. At minimum, validate inputs before calling the plotting pipeline.

---

# `hydraulics.py`

## Critical: Fischer dispersion accepts zero velocity

The docstring says:

> needs positive velocity, depth, and shear velocity

but the implementation uses:

```python
velocity = _finite(velocity_m_s, "velocity_m_s", 0.0)
```

That allows `velocity_m_s == 0`, returning zero dispersion.

Fix:

```python
velocity = _positive(velocity_m_s, "velocity_m_s")
```

This is especially important because `cell_hydraulics()` only calls Fischer with Manning velocity when slope is positive, so the direct public helper should enforce the same contract.

---

## Critical: residual diagnostics divide by zero for constant nonzero residuals

The function only handles all-zero residuals:

```python
if float(np.sum(resid ** 2)) == 0.0:
    return ...
```

For a constant residual such as `[1, 1, 1]`:

```python
dev = resid - mean
denom = sum(dev ** 2)  # 0
```

Then autocorrelations become `0 / 0`, and:

```python
std = np.std(resid)  # 0
```

standardized residuals become NaN.

Handle all constant residuals:

```python
if float(np.std(resid)) == 0.0:
    return {
        "n": int(mod.size),
        "perfect_fit": bool(np.all(resid == 0)),
        "constant_residual": True,
        "autocorr": {},
        "qq": {},
        "max_qq_gap": None,
    }
```

---

## Manning slope threshold is inconsistently defined

The module says:

```python
MIN_SLOPE_FOR_MANNING = 1e-4
```

and `cell_hydraulics()` treats:

```python
slope <= MIN_SLOPE_FOR_MANNING
```

as undefined.

But the lower-level functions `manning_velocity_m_s()`, `bed_shear_pa()`, and `shear_velocity_m_s()` accept any positive slope, including `1e-12`.

Either:

- keep low-level functions mathematically general and document that the threshold is only a cell-level policy, or
- centralize the threshold policy in a shared validator.

---

## `cell_hydraulics()` does not validate slope before storing it

```python
"slope": slope
```

A string or invalid object is stored, then later may cause a `TypeError` in:

```python
math.isfinite(slope)
```

Normalize once:

```python
grade = None if slope is None else _finite(slope, "slope")
```

Store `grade`.

---

## `froude_number()` permits zero velocity by design, but this should be explicit

A zero-discharge Froude number of `0.0` is reasonable. However, the lower-level helper should state that zero velocity is allowed, unlike Fischer dispersion. The current validation style makes the distinction easy to miss.

---

## `load_usgs_cross_section()` mutates global provenance

```python
CROSS_SECTION_PROVENANCE["last_integration_attempt"] = ...
```

This creates:

- hidden global state,
- test-order dependence,
- possible race conditions,
- a provenance dictionary that is no longer a static description.

Return an attempt record instead, or store it in a caller-owned audit object.

---

## The provenance says “current” facts with a future-dated hard-coded claim

```python
"Oct 2026"
```

This is brittle and potentially incorrect depending on the actual execution date. Treat availability as external metadata, not a hard-coded historical assertion, and record the source/version/date used to establish it.

---

## `thermal_inventory()` silently treats malformed scheduled temperatures as valid

Any dictionary is interpreted as a scheduled source:

```python
if isinstance(raw_temp, dict):
```

There is no validation that it contains a usable schedule, times, or values. A typo such as `{"temprature": ...}` silently contributes flow but no heat.

Validate scheduled source schema or raise a clear error.

---

## `thermal_inventory()` includes scheduled flow in total flow but excludes it from heat

This is documented, but the result can be misleading:

```python
"total_thermal_flow_m3_s": total_q
"total_heat_m3_c_per_s": total_qt
```

A caller might assume the latter corresponds to all thermal flow. Add:

```python
"constant_temperature_flow_m3_s": const_q
"scheduled_flow_m3_s": total_q - const_q
```

and make the basis prominent.

---

## Optional dependency handling is inconsistent

- `skill_scores()` imports NumPy unconditionally.
- `residual_diagnostics()` imports NumPy and SciPy unconditionally.
- `identifiability.py` imports NumPy at module import time.

If diagnostics are optional, move these imports inside functions and produce actionable dependency errors.

---

# `identifiability.py`

## Critical: `conditioning()` lacks shape and empty-matrix validation

```python
jac = np.asarray(jacobian, dtype=float)
_, singular, vt = np.linalg.svd(jac)
```

Problems:

- empty Jacobian,
- one-dimensional input,
- NaN/inf values,
- zero-column matrix.

Also:

```python
cutoff = max(singular) * rank_tol
```

fails if there are no singular values.

Validate:

```python
if jac.ndim != 2 or jac.shape[0] == 0 or jac.shape[1] == 0:
    raise ValueError("jacobian must be a nonempty 2-D matrix")
if not np.isfinite(jac).all():
    raise ValueError("jacobian contains nonfinite values")
```

---

## `jacobian_at_truth()` does not validate the finite-difference step

A zero, negative, NaN, or very large step can produce invalid diagnostics.

```python
if not math.isfinite(step) or step <= 0:
    raise ValueError("step must be finite and positive")
```

Also consider scaling the step per parameter more explicitly and recording the actual perturbation used.

---

## `multistart_fit()` does not validate starts

A start outside the bounds produces a SciPy error. Malformed starts can also have the wrong dimension.

Validate every start:

```python
if len(start) != len(PARAM_NAMES):
    raise ValueError(...)
for value, name in zip(start, PARAM_NAMES):
    if not math.isfinite(float(value)):
        raise ValueError(...)
```

Either reject out-of-bound starts or clip them explicitly and record that clipping occurred.

---

## Relative spread calculation can divide by zero in future configurations

```python
... / truth[i]
```

Current truth values are nonzero, but this is fragile. Use an absolute spread when the truth is zero.

---

## `structural_surface_spread()` lacks argument validation

Negative or zero values for:

```python
duration_s
dt_s
```

can produce empty frames or invalid solver behavior. Add checks and handle `duration_s == 0` explicitly before:

```python
max(gaps)
```

which currently fails if no frames are produced.

---

## `sobol_screen()` has SALib API compatibility risks

The code handles sampler differences but not analyzer differences:

```python
indices = sobol.analyze(..., seed=seed)
```

Older SALib versions may not accept `seed`. Add a fallback as done for sampling.

Also, the fallback:

```python
np.random.seed(seed)
```

mutates global NumPy RNG state. Prefer a local generator where supported, and restore state if compatibility requires global seeding.

---

## `sobol_screen()` needs parameter validation

Reject:

- `n_base <= 0`
- noninteger `n_base`
- boolean `n_base`
- invalid `seed`
- nonboolean `calc_second_order`

Some Sobol samplers require particular sample sizes or produce warnings for unsuitable values. Record the actual evaluation count and sampler method.

---

## Sobol objective interpretation needs stronger documentation

```python
values = np.array([
    math.fsum(v * v for v in residual_against_truth(p))
    for p in sample
])
```

This is a scalar sum-of-squared error over synthetic scenarios. It is not sensitivity of each scenario’s output individually. That is valid, but the artifact should state:

- objective definition,
- scenario weights,
- whether residuals are normalized,
- whether parameters are sampled independently.

Otherwise the indices can be misread as sensitivities of the physical variables themselves.

---

## Identifiability diagnostics do not record numerical settings

The output should record:

- finite-difference step,
- rank tolerance,
- parameter bounds,
- truth values,
- scenario definitions,
- solver tolerances,
- SciPy/SALib versions if reproducibility matters.

Without these, rerunning the diagnostic may produce a different interpretation while appearing to use the same schema.

---

## Unused imports and dependencies

`identifiability.py` imports:

```python
import math
from typing import Any, Sequence
import numpy as np
```

all are used, but the module imports NumPy eagerly. Move it inside the functions if this diagnostic is optional.

---

# Recommended tests

## Dataset roles

- Malformed observation rows.
- Mixed timestamp types.
- Discontinuous observation windows.
- Locked-final gap between two calibration intervals.
- Missing claim record.
- Duplicate artifact across roles.
- Calibration/development overlap.

## Figures

- `train=slice(0, split)` visibly shades the intended region.
- Perfect residuals produce a valid figure instead of crashing.
- Constant nonzero residuals produce a diagnostic figure.
- Empty ridge subset raises a clear error.
- Mismatched series lengths fail before Matplotlib.
- Artifact status is reflected in titles.

## Hydraulics

- `fischer_dispersion_m2_s(0, ...)` raises.
- Constant residuals do not produce NaN autocorrelations.
- Invalid slope types fail with `ValueError`.
- Scheduled thermal sources are schema-validated.
- `thermal_inventory()` reports constant and scheduled flow separately.

## Identifiability

- Empty/1-D/NaN Jacobians fail clearly.
- Invalid finite-difference steps fail.
- Out-of-bounds starts fail clearly.
- Zero-duration structural comparison returns a defined result.
- Older SALib versions work through the compatibility fallback.
- Sobol output records the scalar objective and scenario weights.

## Priority order

1. Fix `residual_diagnostics()` constant-residual division by zero.
2. Fix the incorrect train/holdout figure shading.
3. Handle perfect-fit Q-Q plots.
4. Require positive velocity in Fischer dispersion.
5. Add artifact and series validation in `figures.py` and `datasets.py`.
6. Add numerical/API validation to `identifiability.py`.