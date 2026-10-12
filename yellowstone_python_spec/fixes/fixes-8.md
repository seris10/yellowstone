## Audit summary

The most important fixes are:

1. **`snow_validate.py` can crash on valid-looking data when the split date is absent or produces an empty train/holdout set.**
2. **`snow_season.py` misattributes thermal melt and lacks validation for several physically invalid inputs.**
3. **`study_mode.py` allows nonfinite numeric values and has a mismatch between `clock_hour` schema validation and runtime validation.**
4. **`vegetation.py` has weak parameter validation, questionable stable-ID behavior, and several edge cases in terrain/grid generation.**

---

# `snow_season.py`

## Critical: thermal melt attribution is incorrect

`step_snow()` combines degree-day melt and thermal melt:

```python
melt = min(avail, degree_day_melt + float(thermal_flux_mm_d))
```

Later, `run_season()` records:

```python
tot["thermal_melt"] += min(melt, thermal_flux_mm_d)
```

This can overstate thermal melt. For example:

- degree-day melt: 10 mm
- thermal flux: 8 mm
- available snow: 12 mm
- actual melt: 12 mm
- reported thermal melt: 8 mm

The thermal contribution could only be 2 mm after the degree-day component consumes the available snow.

Return the components separately:

```python
dd_melt = float(k_melt) * degree_days(air_c, tbase) / retention
thermal_melt = max(0.0, float(thermal_flux_mm_d))
melt = min(avail, dd_melt + thermal_melt)

actual_thermal = min(
    thermal_melt,
    max(0.0, avail - min(avail, dd_melt)),
)
```

Better still, change `step_snow()` to return both requested and actual melt components.

---

## Critical: negative precipitation is accepted

Current code allows:

```python
precip_mm_d = -50
```

which can produce negative accumulation or rain and corrupt the water balance.

Validate:

```python
if not math.isfinite(float(precip_mm_d)) or precip_mm_d < 0:
    raise ValueError("precip_mm_d must be finite and >= 0")
```

Apply similar checks to:

- `snow_mm`
- `k_melt`
- `thermal_flux_mm_d`
- `canopy_keep`
- `aspect_retention`
- `wind_loss`

`wind_loss` is clamped, but `canopy_keep` and `thermal_flux_mm_d` are not.

---

## `run_season()` can fail unexpectedly for empty inputs

This line fails if `air_c_by_day=[]`:

```python
else air_c_by_day[-1]
```

Also, `days` may be negative, and an empty patch list silently produces an apparently valid zero ledger.

Add:

```python
if isinstance(days, bool) or not isinstance(days, int) or days < 0:
    raise ValueError("days must be a nonnegative integer")

if days > 0 and not air_c_by_day:
    raise ValueError("air_c_by_day must not be empty when days > 0")

if not patches:
    raise ValueError("at least one patch is required")
```

---

## Input series lengths are ambiguous

The code silently repeats the last forcing value:

```python
air_c_by_day[d] if d < len(air_c_by_day) else air_c_by_day[-1]
```

and does the same for precipitation.

That may be intentional, but it can hide truncated datasets. Prefer an explicit option:

```python
repeat_last_forcing: bool = False
```

or require sufficient input length for validation runs.

For SNOTEL validation, silently extending a series is especially risky because it changes the experiment.

---

## Duplicate patch IDs silently overwrite state

These dictionaries assume IDs are unique:

```python
gdd = {p["id"]: 0.0 for p in out}
mods = {p["id"]: patch_modifiers(p) for p in out}
```

Duplicate IDs cause one patch’s state to overwrite another’s. Validate IDs before simulation:

```python
ids = [p.get("id") for p in out]
if any(i is None for i in ids) or len(ids) != len(set(ids)):
    raise ValueError("patch IDs must be present and unique")
```

---

## Water ledger is correct only under a non-obvious runoff convention

The code computes:

```python
tot["runoff"] += blown + drain * 0.5
tot["drain"] += drain * 0.5
```

and the soil balance subtracts:

```python
2.0 * tot["drain"]
```

This means `drain` is not total drainage; it is half of the post-cap excess, while the other half is classified as runoff. The naming is confusing.

Use separate quantities:

```python
drain_total = max(0.0, soil - cap)
runoff_drain = drain_total * 0.5
subsurface_drain = drain_total - runoff_drain
```

Then report those explicitly.

---

## Soil storage can exceed the configured capacity in some cases

Initial soil is derived from:

```python
float(p.get("moisture", 0.5)) * soil_cap_mm
```

but moisture is not clamped. A patch with `moisture=2.0` starts above capacity and only gets reduced after inflow.

Validate or clamp initial moisture:

```python
initial_moisture = min(1.0, max(0.0, float(...)))
```

Also validate `soil_cap_mm > 0` and `field_capacity` in `[0, 1]`.

---

## Phenology moisture uses rounded storage

The code rounds before calculating moisture:

```python
p["soil_mm"] = round(soil, 3)
p["moisture"] = round(min(1.0, soil / soil_cap_mm), 4)
```

This is generally harmless, but it introduces avoidable numerical drift in chained simulations. Keep internal values unrounded and round only in the final output.

---

## `date_to_season()` does not actually validate calendar dates

It accepts:

```python
date_to_season(2, 31)
```

because it only checks day `1..31`.

Use `datetime.date` validation if the function claims to validate dates:

```python
import datetime

try:
    datetime.date(2000, int(month), int(day))
except ValueError as exc:
    raise ValueError("invalid calendar date") from exc
```

---

## `game_clock_now()` mishandles falsey `now`

```python
local = now or datetime.datetime.now().astimezone()
```

A falsey datetime-like object would be ignored. Use:

```python
local = now if now is not None else datetime.datetime.now().astimezone()
```

Also, naive datetimes should either be rejected or explicitly interpreted in a documented timezone.

---

## `render_snow_map()` needs validation and directory creation

Potential issues:

- `size <= 0`
- missing `center_xz`
- missing or negative `r_apron_m`
- output parent directory absent
- coordinates outside the world silently clipped

Add validation and:

```python
Path(path).parent.mkdir(parents=True, exist_ok=True)
```

---

# `snow_validate.py`

## Critical: split handling can crash

```python
idx = next(i for i, d in enumerate(dates) if d >= split)
```

This raises `StopIteration` if all dates precede the split. It also allows an empty training set if the first date is already on or after the split.

Use explicit checks:

```python
def train_holdout_split(dates, split):
    if not dates:
        raise ValueError("no dates supplied")

    idx = next((i for i, d in enumerate(dates) if d >= split), len(dates))

    if idx == 0:
        raise ValueError("split produces an empty training set")
    if idx == len(dates):
        raise ValueError("split produces an empty holdout set")

    return list(range(idx)), list(range(idx, len(dates)))
```

---

## Critical: dates are sorted without sorting associated records safely

```python
dates = sorted(site["days"])
get = lambda code: [site["days"][d][code] for d in dates]
```

This is correct only if `site["days"]` is a dictionary keyed by ISO dates. Validate that:

- keys are valid ISO dates,
- dates are unique,
- dates are contiguous or gaps are explicitly allowed,
- each day contains all required fields.

---

## Missing observations are silently converted to zero

```python
obs_swe = [in_to_mm(v or 0.0) for v in get("WTEQ")]
obs_depth_mm = [in_to_mm(v or 0.0) for v in get("SNWD")]
```

A missing WTEQ value and a measured zero are scientifically different. Treat missing observed values as missing, then exclude those pairs from scoring or fail the validation.

At minimum, distinguish:

```python
None  # missing
0.0   # measured zero
```

The same applies to `SNWD`.

---

## The model uses fixed zero initial snow regardless of observed day 0

```python
state["snow_mm"] = 0.0
```

The code checks that day-0 observed SWE is near zero, which is reasonable for spin-up, but the threshold is only:

```python
0.04 inches ≈ 1.016 mm
```

That tolerance should be named and recorded in the output. Also validate that the first forcing date is the intended start date.

---

## `assert` is being used for scientific validation

```python
assert abs(led["storage_residual_mm"]) < 0.01, led
```

Assertions are disabled under Python optimization (`python -O`). This should be an explicit exception:

```python
residual = abs(led["storage_residual_mm"])
if residual >= 0.01:
    raise RuntimeError(f"water ledger residual {residual} mm")
```

---

## Empty train/holdout lists can break scoring

These calls assume both lists contain values:

```python
score_paired_series(...)
```

This affects:

- train scoring
- holdout scoring
- persistence null
- peak timing

Validate split sizes before all calculations.

---

## `peak_timing_error_days()` is not robust across year boundaries

```python
return ord_day(m_peak) - ord_day(o_peak)
```

This is correct for valid ISO dates because ordinals are absolute, but the function does not validate that dates are ISO dates or that modeled and observed lengths match.

Add:

```python
if len(dates) != len(modeled) or len(dates) != len(observed):
    raise ValueError("dates and series must have equal lengths")
```

If observed values can be missing, peak timing needs an explicit missing-data policy.

---

## Fixed-parameter validation is too permissive for `k_melt`

The docstring says parameters are validated against the fit grid, but the code only checks range:

```python
if not (min(K_GRID) <= k <= max(K_GRID)):
```

It accepts `0.51`, even though the fit grid uses increments of `0.25`.

If exact grid membership is required:

```python
if k not in K_GRID:
    raise ValueError(...)
```

Also reject NaN and infinity explicitly. Comparisons with NaN currently bypass the range check:

```python
math.isfinite(k)
```

---

## `load_fixed_params()` can fail unclearly on malformed JSON structures

This branch:

```python
else:
    out = {t: ... for t, v in doc.items()}
```

assumes `doc` is a mapping. A list or malformed artifact produces an unrelated exception. Validate the schema and provide a useful error.

Also reject unknown triplets in a fixed artifact if the artifact contains sites not present in the evaluation bundle, or report them explicitly.

---

## Fitted parameters are site-specific but the provenance is hard-coded

```python
"provenance": "fitted_single_window_WY2026_joint_grid"
```

This remains `"WY2026"` even when:

- the input window is different,
- the user changes the split date,
- the script is run on a prior or synthetic window.

Derive provenance from bundle metadata or record the actual fit window and split date.

---

## `fit_snow_params()` has tie behavior but does not record it

The first parameter combination wins on equal RMSE. This is deterministic, but the output should record:

- grid definition,
- number of candidates,
- tie-breaking rule,
- training sample count.

---

## Holdout evaluation should report sample counts after missing-data filtering

The output currently reports:

```python
"holdout_n": len(hold_idx)
```

but if missing observations are later excluded, this will not represent the actual scoring count. Report both index count and scored count.

---

# `study_mode.py`

## Critical: nonfinite numeric values are accepted

The numeric validator checks:

```python
if not (lo <= float(value) <= hi):
```

For `NaN`, both comparisons are false, so the condition does not behave as intended. Infinity may also produce confusing validation behavior.

Add:

```python
import math

number = float(value)
if not math.isfinite(number):
    raise ValueError(f"{dotted!r} must be finite")
if lo is not None and number < lo or hi is not None and number > hi:
    raise ValueError(...)
```

Apply this to:

- scalar floats
- `wind_xz_mps`
- `daylist`
- all preset values

---

## `clock_hour` allows 24.0 during schema validation

Schema:

```python
"clock_hour": (float, 0.0, 24.0)
```

But runtime clock semantics are `[0, 24)`:

```python
if not (0.0 <= clock_hour < 24.0):
```

Set the schema upper bound to `24.0` with exclusive handling, or special-case it clearly. As written, `_validate("clock_hour", 24.0)` succeeds while the resulting config may later be rejected.

---

## `clock_hour` accepts integers but the schema declares float

This may be intentional because numeric values accept both `int` and `float`, but the schema representation is misleading. Use a semantic type such as `"number"` rather than Python `float`.

---

## `daylist` accepts booleans

Because `bool` is a subclass of `int`:

```python
isinstance(True, (int, float))
```

is true.

Reject explicitly:

```python
and not isinstance(v, bool)
```

Do the same for `wind_xz_mps`.

---

## `snow.days` accepts zero but the preset model may not

Schema allows:

```python
"snow.days": (int, 0, 365)
```

If zero-day snow experiments are valid, fine. Otherwise use a minimum of 1. Also reject booleans for integer fields; the generic numeric check does so, but only because it explicitly checks `isinstance(value, bool)`.

---

## `patch_laterals` bypasses the approved schema

The comments say only approved slider keys may change, but `hot_surge` modifies:

```python
hydro.attach
hydro.tributaries
```

without validating those paths or values. This is a controlled preset, but it contradicts the stated schema guarantee.

Either:

1. add these paths to an approved preset-only schema, or
2. represent the surge as an approved scalar such as `hydro.source_strength`.

At minimum validate flow and temperature.

---

## Repeated lateral IDs can accumulate

```python
attach.setdefault(rid, []).append(lat["id"])
```

If the baseline already contains the same attachment, applying the preset produces duplicates. This may double-count the tributary.

Use idempotent insertion:

```python
links = attach.setdefault(rid, [])
if lat["id"] not in links:
    links.append(lat["id"])
```

Also detect an existing tributary with the same ID but different values.

---

## `_set_path()` can create unexpected configuration structure

```python
node = node.setdefault(p, {})
```

If `cfg` contains a scalar where a dictionary is expected, it raises an obscure error. If the path is misspelled, it silently creates a new subtree.

Since paths are controlled, validate the existing structure:

```python
if p not in node or not isinstance(node[p], dict):
    raise ValueError(f"config path {dotted!r} is missing or not a mapping")
```

---

## `ALLOWED_PREFIXES` is unused

This creates a false sense of enforcement. Remove it or use it to validate preset keys, including the special lateral mechanism.

---

## `diff_configs()` does not distinguish missing keys from explicit `None`

```python
va, vb = a.get(k), b.get(k)
```

A missing key and a present key with `None` both appear as `None`. Use a sentinel:

```python
_MISSING = object()
va = a.get(k, _MISSING)
vb = b.get(k, _MISSING)
```

Then report additions/removals accurately.

---

## YAML loading needs type validation

`yaml.safe_load()` may return `None`, a list, or another scalar. Validate that baseline and diff inputs are mappings before passing them to config functions.

---

# `vegetation.py`

## Critical: `propose_plantings()` stable-ID behavior is broken or misleading

It calls the reviewed generator, which creates IDs like:

```python
prop_{guild}_{seed}_{col}_{row}
```

Then it checks:

```python
legacy_prefix = f"prop_{guild}_{start_index:05d}"
collisions = any(r["stable_id"].startswith(legacy_prefix) for r in accepted)
```

Those prefixes do not match the generated ID format in normal use, so the renumbering almost never occurs. `start_index` therefore has no meaningful effect.

Choose one stable-ID policy:

- remove `start_index`, or
- generate IDs using `start_index`, or
- explicitly document that reviewed IDs are cell-derived and `start_index` is legacy-only.

For stable reproducibility, cell-based IDs are preferable:

```python
prop_{guild}_{seed}_{col:04d}_{row:04d}
```

---

## Critical: proposal geometry lacks validation

These values are not adequately checked:

```python
radius_m
center_xz
seed
suitability_threshold
moisture
canopy
```

Problems include:

- negative radius
- NaN radius
- infinite center coordinates
- nonnumeric center tuple
- suitability threshold outside `[0, 1]`
- moisture and canopy outside expected ranges
- extremely large radius causing excessive work

Add explicit validation before calculating the grid.

---

## `suitability()` has a typo in its public parameter

```python
def suitability(lamba0: float, ...)
```

This should be `lambda0`. The typo becomes part of the callable API and encourages keyword-call failures:

```python
suitability(lambda0=...)
```

Rename it, or support the old name temporarily with a compatibility wrapper.

---

## `suitability()` does not validate `lambda0`

The function claims to return a value in `[0, 1]`, but a caller can pass:

```python
lamba0 = 5.0
```

and get values above 1 before downstream clamping.

Clamp or validate:

```python
lambda0 = min(1.0, max(0.0, float(lambda0)))
```

Also reject nonfinite values.

---

## `guild_suitability()` allows invalid moisture/canopy values

The downstream factors are eventually clamped, so bad inputs do not fail loudly. For a review tool, silent clamping can conceal data errors.

Validate:

```python
if not 0.0 <= moisture <= 1.0:
    raise ValueError(...)
if not 0.0 <= canopy <= 1.0:
    raise ValueError(...)
```

Likewise, reject nonfinite or negative slope unless negative slope has a deliberate meaning.

---

## Terrain sampling assumes valid shape and finite values

`terrain_fns()` assumes:

- `h.shape == (GRID, GRID)`
- all values are finite
- `h` is numeric

`load_terrain()` checks size but not finiteness. Add:

```python
if not np.isfinite(h).all():
    raise ValueError("terrain contains NaN or infinite values")
```

and validate the array shape in `terrain_fns()`.

---

## Terrain boundary handling is implicit and asymmetric

`sample()` clamps to nearly `GRID - 1`, while `slope_deg()` clamps to `[1, GRID - 3]`. This avoids indexing errors but creates edge behavior that is not obvious.

Document that edge samples use clamped coordinates, or reject proposals outside the DEM’s valid interior.

---

## `moisture_at()` returns the first matching patch, not the nearest or best patch

```python
for p in patches:
    ...
    if distance <= radius:
        return ...
```

Overlapping patches therefore depend on input order. That makes suitability sensitive to asset ordering.

Choose a deterministic policy:

- nearest patch,
- highest moisture,
- highest priority,
- explicit patch priority field.

Nearest patch is usually the least surprising:

```python
matches = [...]
return min(matches, key=lambda item: item[0])[1]
```

The renderer has the same first-match behavior, so both functions should share one patch-selection helper.

---

## `render_suitability_png()` duplicates patch-selection logic

The proposal system uses `moisture_at()`, while rendering uses an independent loop. These can disagree for overlapping patches or malformed patch data.

Extract:

```python
def habitat_moisture_at(x, z, patches) -> tuple[str, float]:
    ...
```

and use it in both places.

---

## Candidate grid can under-sample the requested area

The grid is built with:

```python
per_row = max(1, int((2 * radius_m) / grid_step))
```

This does not guarantee the final row/column reaches the intended radius. It also means a small radius still creates a 2×2 grid, with jitter possibly placing all candidates outside the circle.

Use an explicit `ceil` and define cell-center placement:

```python
per_row = max(1, math.ceil(2 * radius_m / grid_step))
```

Then document whether the grid includes boundaries or cell centers.

---

## Coarsening can violate the claimed separation relationship

The code coarsens `grid_step` but enforces separation using the original guild spacing:

```python
if math.hypot(x - kx, z - kz) < step:
```

That is safe but can reject many candidates. More importantly, the log says the grid is coarsened but does not record the original candidate count or effective coverage.

Add:

```python
{
    "original_spacing_m": step,
    "effective_spacing_m": grid_step,
    "original_candidate_count": ...,
    "candidate_count": ...,
}
```

---

## `patch_step()` accepts invalid simulation parameters

Potential problems:

```python
hours = dt_s / 3600.0
```

Negative `dt_s` produces negative growth and can increase/decrease biomass incorrectly.

Also:

- negative biomass is accepted,
- negative capacity is clamped only internally,
- negative growth rates become zero through `max`,
- negative grazer rates reduce demand,
- duplicate patch IDs are not detected.

Validate `dt_s >= 0`, biomass/capacity nonnegative, and grazer rates nonnegative.

---

## `patch_step()` may apply a grazer’s full demand to multiple patches

The loop sums all grazers into the matching patch, which is correct if every grazer has exactly one patch. But malformed data with duplicate or ambiguous patch assignments is not detected.

Also clarify whether consumption is a rate in biomass units or a dimensionless fraction. The current code says dimensionless index, but no unit conversion or per-area interpretation exists.

---

## `render_suitability_png()` needs output and image validation

Add checks for:

- `size > 0`
- valid `bbox`
- `x1 > x0`, `z1 > z0`
- output directory creation
- known guild
- valid `canopy`

---

## Dependency and performance concerns

`numpy` is imported at module load time even though only terrain-loading functions require it. If this module is used in lightweight tooling, the import becomes a hard dependency.

Consider lazy importing NumPy inside `load_terrain()` or clearly declare it as a required dependency.

`render_suitability_png()` is `O(size² × patches × shells)`. For large maps, spatial indexing or pre-rasterized masks would materially improve runtime.

---

# Recommended test cases

## Snow

- Negative precipitation rejected.
- Empty forcing with `days > 0` rejected.
- Split date before all dates and after all dates rejected clearly.
- Missing WTEQ is not treated as measured zero.
- Thermal melt attribution never exceeds actual melt.
- Duplicate patch IDs rejected.
- Invalid calendar date rejected.

## Study mode

- NaN and infinity rejected for every numeric slider.
- `clock_hour=24` rejected consistently.
- Boolean day-list values rejected.
- Applying `hot_surge` twice does not duplicate tributary links.
- Diff distinguishes missing keys from explicit `None`.
- Malformed YAML produces a useful error.

## Vegetation

- Negative/NaN radius rejected.
- Invalid guild rejected in render functions as well as proposal functions.
- Overlapping patch behavior is deterministic.
- Stable IDs remain unchanged when unrelated candidate cells are rejected.
- `start_index` either works or is removed.
- Terrain NaN and wrong shape rejected.
- Negative timestep and grazer rates rejected.
- Output directories are created before PNG writes.

## Priority order

1. Fix snow validation split/empty-series failures.
2. Correct thermal melt component accounting.
3. Stop treating missing observations as zero.
4. Add finite/range validation in `study_mode`.
5. Resolve vegetation stable-ID semantics.
6. Unify patch selection and validate terrain/proposal inputs.