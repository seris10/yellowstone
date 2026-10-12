## Audit summary

The main issues are:

1. **`surface_flux.py` can enter invalid Magnus/humidity domains at extreme temperatures or pressures.**
2. **`linearized()` is mathematically consistent for the current formulas, but its validity range is not checked.**
3. **`uncertainty.py` has a real reporting bug: `band_level`, `seed`, and related settings are not consistently passed through.**
4. **Several uncertainty helpers can silently produce invalid or misleading results from empty, mismatched, or non-finite inputs.**
5. **The uncertainty bands measure ensemble/model-selection spread, not calibrated predictive uncertainty.**

---

# `surface_flux.py`

## 1. Magnus formula needs domain protection

```python
def es_kpa(t_c: float) -> float:
    return 0.61094 * math.exp(17.625 * t_c / (t_c + 243.04))
```

At `t_c == -243.04`, this divides by zero. Near that temperature, the result can overflow or become physically meaningless.

The same issue propagates into:

```python
_des_dt()
_specific_humidity()
_dq_de()
```

### Fix

Validate the temperature range:

```python
MAGNUS_MIN_C = -80.0
MAGNUS_MAX_C = 60.0

def es_kpa(t_c: float) -> float:
    t_c = float(t_c)
    if not math.isfinite(t_c):
        raise ValueError("temperature must be finite")
    if not MAGNUS_MIN_C <= t_c <= MAGNUS_MAX_C:
        raise ValueError(
            f"temperature {t_c}°C outside Magnus validity range"
        )
    return 0.61094 * math.exp(17.625 * t_c / (t_c + 243.04))
```

The exact range should match the chosen Magnus formulation's documented validity range.

---

## 2. Humidity calculations need pressure-domain validation

```python
def _specific_humidity(es, pressure_kpa):
    return 0.622 * es / (pressure_kpa - 0.378 * es)
```

This requires:

```text
pressure_kpa - 0.378 * es > 0
```

Otherwise humidity can become negative, infinite, or nonsensical. `BudgetParams` only checks that pressure is positive.

### Fix

```python
def _specific_humidity(es: float, pressure_kpa: float) -> float:
    denominator = pressure_kpa - 0.378 * es
    if denominator <= 0.0:
        raise ValueError("vapor pressure is incompatible with air pressure")
    return 0.622 * es / denominator
```

Also reject vapor pressure greater than total pressure:

```python
if es >= pressure_kpa:
    raise ValueError("saturation vapor pressure must be below air pressure")
```

This matters especially if users provide low pressure or very warm water temperatures.

---

## 3. `BudgetParams` allows physically questionable coefficients

These checks are syntactically valid:

```python
if not math.isfinite(value) or value < 0.0:
```

But allowing:

```python
c_h = 0.0
c_e = 0.0
```

may be intentional, while allowing arbitrarily large values can make the model numerically stiff and cause the linearized solution to behave poorly.

Consider range validation or at least diagnostic warnings for extreme values.

Also, albedo and emissivity values of exactly `1.0` or `0.0` are mathematically allowed but potentially suspicious for this application.

---

## 4. Incoming longwave uses unbounded air temperature

```python
t_k = air_c + 273.15
```

`MetState` only checks that `air_c` is finite. A value below `-273.15` produces a nonphysical or negative absolute temperature and potentially a negative longwave result.

### Fix

Validate absolute temperature:

```python
if air_c <= -273.15:
    raise ValueError("air temperature must exceed absolute zero")
```

Apply the same guard to `t_water_c`.

---

## 5. `_lw_in_w_m2()` should validate its inputs independently

Although normal callers use `MetState`, `_lw_in_w_m2()` is a private helper that can be called directly:

```python
def _lw_in_w_m2(air_c, rh, cloud):
```

It currently permits:

- negative RH;
- cloud outside `[0, 1]`;
- non-finite values;
- invalid temperature.

Either rely strictly on `MetState` and document that contract, or validate at the helper boundary.

---

## 6. Longwave cloud correction should be documented more precisely

```python
eps_clear * (1.0 + 0.22 * cloud ** 2)
```

This can produce an effective emissivity above one. For `cloud=1`, the multiplier is `1.22`. The resulting incoming longwave may still be physically reasonable as an empirical cloud correction, but the code should state that this is a radiative correction rather than literal emissivity.

If the intent is an emissivity, cap it:

```python
eps = min(1.0, eps_clear * (1.0 + 0.22 * cloud ** 2))
```

Do not cap it automatically without deciding which interpretation is intended.

---

## 7. `linearized()` should verify the derivative numerically in tests

The derivative is currently:

```python
slope = (
    -4.0 * ...
    - rho * CP_AIR_J_KG_K * ...
    - rho * L_VAPOR_J_KG * ... * dq_sat
)
```

For the current equations this is broadly correct because air density and air humidity are held fixed with respect to water temperature.

Add a finite-difference regression test:

```python
f0, derivative = linearized(t, met, params)
eps = 1e-4
numeric = (
    flux_at(t + eps, met, params)["net"]
    - flux_at(t - eps, met, params)["net"]
) / (2 * eps)
assert math.isclose(derivative, numeric, rel_tol=1e-6)
```

This will catch future changes to `flux_at()` that are not reflected in `linearized()`.

---

## 8. Linearization quality should be exposed

The docstring says the solver uses:

```text
F(T_new) ~= F0 + dF/dT * (T_new - T_old)
```

But no error estimate is returned. For large timesteps or large temperature jumps, the linearized flux may be a poor approximation even though the scheme remains stable.

Consider returning or logging:

- old temperature;
- predicted new temperature;
- linearized flux;
- actual flux;
- linearization residual.

This is particularly important for latent heat, because saturation vapor pressure is nonlinear.

---

## 9. `spec_from_series()` parses every input twice

For example:

```python
"rh": {"times_s": list(Series.parse(rh).times_s),
       "values": list(Series.parse(rh).values)}
```

This is inefficient and can be subtly inconsistent if `Series.parse()` performs validation or normalization.

### Fix

```python
def as_mapping(value):
    series = Series.parse(value)
    return {
        "times_s": list(series.times_s),
        "values": list(series.values),
    }

rh_s = as_mapping(rh)
wind_s = as_mapping(wind_mps)
...
```

Also verify all series share the same time grid if the River configuration requires aligned forcing.

---

## 10. `spec_from_series()` accepts arbitrary parameter keys

```python
"params": dict(params or {})
```

Typos are silently passed downstream:

```python
{"emissivty": 0.9}
```

Use an allowlist or validate through `BudgetParams`:

```python
allowed = {"albedo", "emissivity", "c_h", "c_e", "pressure_kpa"}
unknown = set(params or {}) - allowed
if unknown:
    raise ValueError(f"unknown surface-budget parameters: {sorted(unknown)}")
```

---

# `uncertainty.py`

## Critical: requested band level is ignored

`build_uq_document()` accepts:

```python
band_level: float = 0.90,
seed: int = ENSEMBLE_SEED
```

but then calls:

```python
members = ridge_members(fit_results, champion["train_rmse"])
```

and:

```python
bands = ensemble_bands(
    trajs["trajectories"],
    quantiles=(tail, 0.5, 1.0 - tail),
    seed=seed,
)
```

The default ridge settings and `n_bootstrap` are used, which is partly intentional, but the CLI never exposes `band_level`, and the document claims:

```python
"level": band_level
```

If a caller passes `band_level=0.80`, that is correctly used for quantiles. However, `UQ_PROVENANCE` still hardcodes 0.10 and 5, and the output does not record all actual settings consistently.

### Fix

Pass all settings explicitly:

```python
def build_uq_document(...,
                      band_level=0.90,
                      tol_frac=0.10,
                      min_members=5,
                      n_bootstrap=1000,
                      seed=ENSEMBLE_SEED):
    members = ridge_members(
        fit_results,
        champion["train_rmSE"],
        tol_frac=tol_frac,
        min_members=min_members,
    )
    bands = ensemble_bands(
        trajs["trajectories"],
        quantiles=(tail, 0.5, 1.0 - tail),
        seed=seed,
        n_bootstrap=n_bootstrap,
    )
```

Then record the actual values rather than the module defaults.

---

## 1. `ridge_members()` does not validate inputs sufficiently

```python
if champion_train_rmse < 0.0:
```

This does not reject NaN or infinity.

Also:

```python
if len(members) < min_members:
    members = sorted(results, ...)[:min_members]
```

If there are fewer than `min_members` results, the function returns fewer members than requested without indicating that the minimum was impossible.

### Fix

```python
if not math.isfinite(champion_train_rmse) or champion_train_rmse < 0:
    raise ValueError(...)
if not isinstance(min_members, int) or min_members < 1:
    raise ValueError(...)
if not results:
    raise ValueError("results must be nonempty")
```

Record:

```python
"requested_min_members": min_members,
"actual_members": len(members),
"minimum_unavailable": len(results) < min_members,
```

---

## 2. Ridge membership may include malformed result rows

```python
members = [r for r in results if r["train_rmse"] <= cutoff]
```

A NaN `train_rmse` is silently excluded; a missing key crashes. Validate all candidate rows before selection.

Also validate that `q_lat`, `t_lat`, and `c_mult` are finite.

---

## 3. `fit_masks()` can raise raw `StopIteration`

```python
start = next(i for i, g in enumerate(grid)
             if g - grid[0] >= spinup_s)
```

If spinup exceeds the grid duration, this raises an unhelpful exception.

### Fix

```python
if not grid:
    raise ValueError("grid must be nonempty")
if any(b <= a for a, b in zip(grid, grid[1:])):
    raise ValueError("grid must be strictly increasing")
if spinup_s < 0:
    raise ValueError("spinup_s must be >= 0")

start_candidates = [
    i for i, g in enumerate(grid)
    if g - grid[0] >= spinup_s
]
if not start_candidates:
    raise ValueError("spinup_s leaves no usable data")
```

Also verify that training and holdout each contain enough samples.

---

## 4. `ensemble_bands()` needs stronger validation

It validates array dimensionality, but not:

- `n_bootstrap` being an integer;
- seed being valid;
- quantile values being finite;
- trajectory length being nonzero;
- `band_width` being nonnegative.

Add:

```python
if not isinstance(n_bootstrap, int) or n_bootstrap < 100:
    raise ValueError(...)
if arr.shape[1] == 0:
    raise ValueError("trajectories must have at least one timestep")
```

`np.asarray()` may also raise a less clear error for ragged trajectories. Validate lengths before constructing the array.

---

## 5. `band_coverage()` does not validate interval ordering or finiteness

```python
inside = sum(1 for l, h, t in zip(lo, hi, target)
             if l <= t <= h)
```

It accepts:

- `lo > hi`;
- NaN;
- infinite values.

A malformed interval can silently produce an apparently valid coverage score.

### Fix

```python
for l, h, t in zip(lo, hi, target):
    if not all(math.isfinite(float(v)) for v in (l, h, t)):
        raise ValueError("band and target values must be finite")
    if l > h:
        raise ValueError("lower band exceeds upper band")
```

---

## 6. Reported coverage is not predictive calibration

The code reports:

```python
"holdout_coverage": ...
```

This is useful, but the bands are generated from a ridge of models selected using the training data. They are not calibrated probabilistic prediction intervals.

The current provenance correctly says this is authored knob sensitivity, but the output field name may be read too strongly.

### Recommendation

Rename or qualify it:

```python
"holdout_ensemble_coverage"
```

and include:

```python
"interpretation": (
    "fraction of holdout observations inside model-ensemble band; "
    "not a calibrated predictive interval"
)
```

---

## 7. `oat_fit()` lacks validation for perturbation values

The function validates knob names but not values:

```python
moved[knob] = value
```

Invalid values can reach the solver:

- negative volume;
- zero area;
- negative exchange multiplier;
- non-finite lateral temperature;
- negative lateral flow.

Validate by knob:

```python
BOUNDS = {
    "q_lat": (0.0, math.inf),
    "t_lat": (-100.0, 100.0),
    "c_mult": (0.0, math.inf),
    "volume_m3": (0.0, math.inf),
    "area_m2": (0.0, math.inf),
}
```

Also reject NaN and infinity.

---

## 8. OAT perturbations can duplicate the baseline

At grid boundaries:

```python
[q_grid[max(0, qi - 1)], q_grid[min(...)]]
```

If the champion is at the first or last grid point, one perturbation may equal the champion. The output then contains a row with zero movement but is presented as a sensitivity test.

### Fix

Deduplicate and annotate:

```python
values = sorted({
    q_grid[max(0, qi - 1)],
    q_grid[min(len(q_grid) - 1, qi + 1)],
} - {champion["q_lat"]})
```

If no values remain, record that the champion is at a singleton grid boundary.

---

## 9. `refuge_weight_oat()` assumes weight `0.6` exists

```python
base_s = next(r["refuge_s_m"] for r in rows if r["value"] == 0.6)
```

If the caller supplies:

```python
weights=(0.2, 0.4, 0.8)
```

the function raises `StopIteration`.

### Fix

Use the nearest default weight or require it explicitly:

```python
DEFAULT_REFUGE_WEIGHT = 0.6
if DEFAULT_REFUGE_WEIGHT not in weights:
    raise ValueError("weights must include the default 0.6")
```

Also validate nonempty landscapes and finite cell fields.

---

## 10. `refuge_weight_oat()` can fail on an empty landscape

```python
best_u, best_s, best_id = max(scored, ...)
```

Add:

```python
if not landscape:
    raise ValueError("landscape must be nonempty")
```

Validate `temperature_c`, velocity, depth, chainage, and IDs before scoring.

---

## 11. `turnover_oat()` should validate values and output schema

It accepts arbitrary values, including zero or negative turnover times:

```python
run_foodweb(..., ne_turnover_days=v)
```

Validate `v > 0`, and check that the expected output keys exist before constructing rows.

---

## 12. `manning_oat()` can produce NaN from an empty ratio set

```python
return (float(np.median(ratios)), len(ratios))
```

If every cell has undefined Manning consistency, NumPy returns a warning and NaN. Later JSON serialization may fail because `allow_nan=False`.

### Fix

```python
if not ratios:
    return math.nan, 0
```

Then either reject the entire sensitivity run or record null:

```python
if not ratios:
    return None, 0
```

The result should not silently contain NaN.

Also validate:

- `z > 0`;
- `n > 0`;
- finite slopes;
- positive dimensions;
- finite discharge.

---

## 13. `build_uq_document()` does not verify the champion belongs to the result set

It uses:

```python
members = ridge_members(fit_results, champion["train_rmse"])
```

but does not verify that the recorded champion parameters are present in `fit_results`.

This can create an ensemble that does not include the stated champion, especially if the fit artifact and freshly recomputed results differ.

### Fix

Compare parameter tuples and fail or record a mismatch:

```python
champ_key = (
    champion["q_lat"],
    champion["t_lat"],
    champion["c_mult"],
)
if not any(
    (r["q_lat"], r["t_lat"], r["c_mult"]) == champ_key
    for r in fit_results
):
    raise ValueError("recorded champion is absent from fit results")
```

---

## 14. Reproducibility comparison uses exact floating-point tuple equality

```python
reproduces = (...) == recorded
```

Exact equality is acceptable if values come directly from JSON grid values, but it is brittle if values are normalized or recalculated.

Use a semantic comparison:

```python
reproduces = all(
    math.isclose(a, b, rel_tol=0.0, abs_tol=1e-12)
    for a, b in zip(fresh, recorded)
)
```

Also compare the train RMSE and holdout RMSE, not just parameter identity.

---

## 15. Fresh fit uses defaults that may differ from the recorded fit

The UQ CLI calls:

```python
full = calibrate.reach_heat_fit(...)
```

without passing the original:

- `spinup_s`;
- `train_frac`;
- `dt_s`.

It therefore assumes the fit artifact used the same defaults. That is not verified.

### Fix

Record these values in the fit artifact and reuse them:

```python
fit_cfg = fit_doc["fit_config"]
full = calibrate.reach_heat_fit(
    ...,
    spinup_s=fit_cfg["spinup_s"],
    train_frac=fit_cfg["train_frac"],
    dt_s=fit_cfg["dt_s"],
    return_all=True,
)
```

Without this, “fresh champion reproduces recorded champion” is not a complete reproducibility check.

---

## 16. `UQ_PROVENANCE` is static and can become inaccurate

```python
UQ_PROVENANCE = {
    ...
    "tol_frac": {"value": 0.10, ...},
    ...
}
```

But the functions accept configurable values, and the document accepts `seed` and `band_level`.

The provenance should be generated from actual runtime values, not copied from module constants.

---

# Recommended priority order

1. Fix `build_uq_document()` so actual band/ridge/bootstrap settings are passed and recorded.
2. Add fit configuration to the calibration artifact and reuse it during UQ recomputation.
3. Validate `surface_flux` temperature, vapor-pressure, and pressure domains.
4. Reject malformed, empty, non-finite, and mismatched uncertainty inputs.
5. Fix `refuge_weight_oat()` default-weight assumptions.
6. Handle empty Manning ratio sets without emitting NaN.
7. Add parameter-bound and duplicate-perturbation diagnostics.
8. Rename or qualify coverage as model-ensemble coverage, not calibrated predictive coverage.
9. Add derivative finite-difference tests for `surface_flux.linearized()`.
10. Validate all generated JSON values before writing with `allow_nan=False`.