## Audit summary

These files are generally better structured than the previous set, especially around provenance and atomic output in `snow_energy.py`. The most important issues are:

1. **`publish.py` does not fully roll back newly created files.**
2. **`publish.py` can publish successfully but fail while writing the receipt.**
3. **`review_proposals.py` does not actually re-check water exclusion, despite claiming it does.**
4. **Proposal validation accepts non-finite coordinates or calculated values.**
5. **Accepted flora is not checked against existing override placements or prior proposal batches.**
6. **`snow_energy.py` has an incorrect polar-day insolation branch.**
7. **Several validation metrics are calculated over the full period rather than the holdout period.**
8. **`run_mode.py` needs stricter input/type and replay-forcing validation.**

---

# `publish.py`

## Critical: rollback leaves newly created files behind

The publish loop backs up only targets that already exist:

```python
if target.exists():
    ...
    backed_up.append(rel)
```

If copying a later file fails, files created earlier in the transaction are not in `backed_up`, so they remain after rollback.

Example:

1. `data/ecosystem.json` does not exist.
2. It is copied successfully.
3. A later copy fails.
4. Rollback has nothing to remove for `ecosystem.json`.

That violates the transactional behavior described in the module docstring.

### Fix

Track created targets separately:

```python
backed_up = []
created = []

for rel, src in staged.items():
    target = dst / rel
    if target.exists():
        backup_target(target, backup_root / rel)
        backed_up.append(rel)

for rel, src in staged.items():
    target = dst / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)

    if rel not in backed_up:
        created.append(rel)

    if _sha(target) != _sha(src):
        raise IOError(f"hash mismatch after copy: {rel}")
```

Rollback:

```python
for rel in created:
    target = dst / rel
    if target.exists():
        target.unlink()

for rel in backed_up:
    shutil.copy2(backup_root / rel, dst / rel)
```

Also remove empty directories created during the failed transaction if needed.

---

## Critical: receipt writing is outside the transaction

The files are copied and then the receipt is written:

```python
(dst / f".publish-{bid}.receipt.json").write_text(...)
```

If that write fails due to permissions, disk space, or interruption, the command raises an exception after the build is already published. It also does not return the documented failure code.

### Fix

Treat the receipt as part of the transaction or explicitly separate “publish succeeded, receipt failed.”

At minimum:

```python
try:
    receipt_path.write_text(...)
except Exception as err:
    print(f"FAILED writing receipt: {err}")
    # Either roll back all published files,
    # or write a recovery warning and return a distinct status.
    return 5
```

Prefer writing the receipt to a temporary file and atomically replacing it:

```python
tmp = receipt_path.with_name(receipt_path.name + ".tmp")
tmp.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
tmp.replace(receipt_path)
```

---

## Backup directory is created before the protected transaction

```python
backup_root.mkdir(parents=True, exist_ok=True)
try:
    ...
```

If this directory creation succeeds but copying fails, the backup directory remains. That may be acceptable, but the behavior should be intentional and recorded.

Also, if `backup_root` already exists due to timestamp collision, `exist_ok=True` can mix old and new backup files.

### Fix

Use a collision-resistant suffix or fail if the directory exists:

```python
backup_root.mkdir(parents=True, exist_ok=False)
```

The timestamp currently has one-second resolution. Two publishes of the same build within one second can collide.

---

## Existing target type changes are not handled explicitly

These cases can produce partial failure:

- target is a directory but source is a file;
- target is a symlink;
- target is a file but source is a directory;
- backup destination already contains an unexpected type.

Use explicit checks before starting:

```python
if target.exists() and target.is_dir():
    raise ValueError(f"target is a directory, expected file: {target}")
```

For symlinks, decide whether to reject them or replace the link itself rather than following it.

---

## No manifest or source hash is recorded in the receipt

The code verifies hashes immediately after copying, but the receipt only contains paths:

```python
"files": sorted(staged)
```

It cannot later prove exactly which artifact bytes were published.

### Improvement

Record source and destination hashes:

```python
"files": {
    rel: {
        "source_sha256": _sha(src),
        "target_sha256": _sha(dst / rel),
        "size": (dst / rel).stat().st_size,
    }
    for rel, src in staged.items()
}
```

This is especially useful if artifacts can be modified after publication.

---

## Input validation is too optimistic

These can raise raw exceptions:

```python
checks = json.loads((b / "CHECKS.json").read_text())
build_doc = json.loads((b / "BUILD.json").read_text())
```

Potential failures include:

- missing files,
- invalid JSON,
- missing `"passed"`,
- missing `"build_id"`,
- non-boolean `"passed"`.

A release command should provide a controlled refusal rather than a traceback.

### Fix

Wrap artifact loading and validate the schema:

```python
try:
    checks = json.loads(...)
    build_doc = json.loads(...)
except (OSError, json.JSONDecodeError) as exc:
    print(f"refusing: invalid build metadata: {exc}")
    return 3

if not isinstance(checks.get("passed"), bool):
    print("refusing: CHECKS.json passed must be boolean")
    return 3
```

---

# `review_proposals.py`

## Critical: water exclusion is not actually re-verified

The module says:

```text
thermal/water exclusion re-verified with polygon math
```

But the implementation only calls:

```python
if any(in_apron(x, z, s) for s in shells):
```

There is no `in_water()` check.

If `in_apron()` does not include the full water polygon, placements can be accepted in water while the ledger claims the water gate passed.

### Fix

Import and apply both checks:

```python
from .pool_crust import in_apron, in_water
```

```python
if any(
    in_apron(x, z, s) or in_water(x, z, s)
    for s in shells
):
    reject("thermal/water exclusion")
    continue
```

If the intended rule is that apron excludes water by definition, make that explicit in the function contract and test it.

---

## Critical: non-finite proposal values can bypass checks

These are accepted without validation:

```python
x, z = float(rec["x"]), float(rec["z"])
```

For example, `NaN` can cause comparisons to evaluate false:

```python
if sl > g["slope_max_deg"]:
```

A NaN slope will not be greater than the maximum and may pass through. The same applies to suitability and moisture.

### Fix

Add finite checks for every numeric input and derived value:

```python
def finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value
```

Use:

```python
x = finite(rec["x"], "x")
z = finite(rec["z"], "z")
sl = finite(slope(x, z), "slope")
mo = finite(moisture_fn(x, z), "moisture")
suit = finite(
    guild_suitability(guild, rec.get("habitat", "forest_edge"),
                      sl, mo, canopy),
    "suitability",
)
```

For an automated review gate, rejecting the individual record may be preferable to aborting the whole batch.

---

## Unknown guilds produce a raw `KeyError`

```python
g = GUILDS[guild]
```

A malformed proposal causes the entire review to stop.

### Fix

```python
if guild not in GUILDS:
    reject(f"unknown guild {guild!r}")
    continue
```

Likewise validate required fields before accessing them:

```python
required = ("stable_id", "guild", "x", "z")
missing = [k for k in required if k not in rec]
```

---

## Pairwise spacing ignores existing override records

The function checks:

```python
if any(... for kx, kz in kept):
```

This catches spacing among proposals accepted in the current call, but not:

- existing `placement_overrides.json` records,
- proposals previously applied,
- generated candidates from another flora pass.

The main function only loads trees:

```python
trees = [(t["position"][0], t["position"][2]) for t in place["trees"]]
```

It does not load existing override additions.

### Fix

Load all existing override positions and include them in spatial checks. Ideally distinguish plant types and use their guild-specific spacing rules.

Also, if existing trees are checked only against `min_existing_m`, the guild's actual minimum spacing should be applied where appropriate.

---

## Cross-guild separation is ambiguous

Accepted candidates are stored as:

```python
kept.append((x, z))
```

Then the current candidate is compared against every prior candidate using the current candidate's guild spacing:

```python
g["min_sep_m"]
```

This is asymmetric. If grass requires 0.5 m and pine requires 4 m:

- pine after grass uses 4 m;
- grass after pine uses 0.5 m.

### Better design

Store guild with each accepted candidate:

```python
kept.append((x, z, guild))
```

Then apply a symmetric rule:

```python
required = max(
    g["min_sep_m"],
    GUILDS[other_guild]["min_sep_m"],
)
```

Or define an explicit pairwise separation matrix.

---

## Duplicate `stable_id` values are not rejected

Duplicate IDs in one proposal file can result in:

- duplicate ledger rows,
- multiple accepted records,
- confusing application behavior.

### Fix

Validate uniqueness before review:

```python
ids = [r.get("stable_id") for r in proposals]
duplicates = {sid for sid in ids if ids.count(sid) > 1}
if duplicates:
    raise ValueError(f"duplicate proposal IDs: {sorted(duplicates)}")
```

Use `Counter` for efficiency.

---

## `to_override_record()` silently defaults unknown guilds to pine

```python
kind = KIND_BY_GUILD.get(rec.get("guild", ""), "pine")
```

This is unsafe. A typo in a guild name becomes a pine placement.

### Fix

Fail closed:

```python
try:
    kind = KIND_BY_GUILD[rec["guild"]]
except KeyError as exc:
    raise ValueError(f"unknown guild: {rec.get('guild')!r}") from exc
```

Also validate:

- `yaw` is finite;
- `scale` is finite and positive;
- `variation_key` is integer-like;
- x/y/z are finite.

---

## Applying overrides is not atomic

```python
ov_path.write_text(json.dumps(ov, indent=1))
```

An interrupted write can corrupt the overrides file.

### Fix

```python
tmp = ov_path.with_name(ov_path.name + ".tmp")
tmp.write_text(json.dumps(ov, indent=1) + "\n", encoding="utf-8")
tmp.replace(ov_path)
```

A lock is also advisable if generation commands may run concurrently.

---

## Inconsistent ecosystem source file

`gen_flora.py` used:

```python
ecosystem.json.pre-python
```

This file uses:

```python
ecosystem.json
```

That can make review use different patches from proposal generation. The acceptance result may therefore differ from the proposal's original environment.

### Recommendation

Record the input artifact or use one canonical source. At minimum, add provenance:

```python
"ecosystem_source": str(ecosystem_path),
"ecosystem_sha256": ...
```

---

# `run_mode.py`

## `normalize_run_mode()` does not validate type

This works for normal strings, but values such as lists or dictionaries produce confusing errors. An unhashable value is not a problem here because tuple membership uses equality, but the error message should be clearer.

### Fix

```python
if not isinstance(mode, str):
    raise TypeError("run_mode must be a string or None")
```

Consider normalizing whitespace and case only if that is desired:

```python
mode = mode.strip()
```

---

## Replay forcing is overly broad

```python
if "replay" in cfg:
    for q in (...):
        if q not in out:
            out.append(q)
```

Any presence of a `"replay"` key means both discharge and upstream temperature are considered prescribed, even if the replay contains only one of them.

This can incorrectly suppress validation claims.

### Fix

Inspect replay contents:

```python
replay = cfg.get("replay")
if isinstance(replay, dict):
    if "discharge" in replay:
        out.append(PRESCRIBED_DISCHARGE)
    if "upstream_temperature" in replay:
        out.append(PRESCRIBED_UPSTREAM_TEMPERATURE)
```

If replay is a path or opaque object, require explicit metadata rather than inferring both quantities.

---

## `claim_allowed()` accepts an unvalidated `prescribed` argument

```python
return quantity not in set(prescribed)
```

Potential issues:

- `prescribed=None` raises;
- a string becomes a set of characters;
- non-string quantities are silently accepted.

### Fix

Normalize both arguments:

```python
def normalize_quantities(values) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, str):
        values = [values]
    result = set(values)
    if not result <= {
        PRESCRIBED_DISCHARGE,
        PRESCRIBED_UPSTREAM_TEMPERATURE,
    }:
        raise ValueError(...)
    return result
```

Use this in both `claim_allowed()` and `check_split()`.

---

## `check_split()` checks only set overlap, not semantic validity

This is fine for the current two quantities, but it will silently accept misspelled quantities:

```python
check_split(["dischage"], ["discharge"])
```

Add allowed-quantity validation.

---

# `snow_energy.py`

## Critical: polar-day TOA insolation is incorrect

In `clear_sky_toa_w_m2()`:

```python
if cos_h <= -1.0:
    return SOLAR_W_M2 * (1.0 + 0.033
                         * math.cos(2 * math.pi * day_of_year / 365.0))
```

This returns extraterrestrial normal irradiance, not daily-mean horizontal insolation. It omits the latitude/declination geometry.

The general daily-mean expression should be used with:

```python
h0 = math.pi
```

for polar day.

### Fix

```python
ecc = 1.0 + 0.033 * math.cos(
    2 * math.pi * (day_of_year - 3) / 365.0
)

if cos_h <= -1.0:
    h0 = math.pi
elif cos_h >= 1.0:
    return 0.0
else:
    h0 = math.acos(cos_h)

return (
    SOLAR_W_M2 * ecc / math.pi
    * (
        h0 * math.sin(lat) * math.sin(dec)
        + math.cos(lat) * math.cos(dec) * math.sin(h0)
    )
)
```

The exact day-angle convention should be documented and tested.

---

## The turbulent term uses absolute Celsius temperature

```python
net = sw + C0_W_M2 + c_t * air_c
```

A turbulent energy term normally depends on a temperature difference or a calibrated anomaly, not directly on Celsius relative to zero. Since `c_t` is fitted, this may work empirically, but it makes the parameter dependent on the chosen temperature scale and confounds it with `C0`.

### Better formulation

Use a reference temperature:

```python
T_REF_C = 0.0
net = sw + C0_W_M2 + c_t * (air_c - T_REF_C)
```

Or use a physically motivated surface-air temperature difference. At minimum, record the reference in provenance.

---

## `c_t` is allowed to be exactly zero but is not constrained by physical validation

```python
CT_GRID = [0.0, 2.0, ..., 30.0]
```

Zero may be useful as a boundary, but there is no post-fit check for parameters at the edge of the grid. A best value at `0` or `30` indicates the grid may be too narrow or the model is poorly identified.

### Add diagnostics

```python
at_boundary = s in {s_grid[0], s_grid[-1]} or c in {ct_grid[0], ct_grid[-1]}
```

Record:

```python
"parameter_at_grid_boundary": at_boundary
```

Also report the number of tied or near-tied solutions.

---

## Train and holdout index validation is missing

These lines can fail:

```python
persist = [obs_swe[train_idx[-1]]] * len(hold_idx)
```

Potential problems:

- no training dates;
- no holdout dates;
- split date outside the data range;
- dates unsorted or duplicated.

### Fix

After splitting:

```python
if not train_idx:
    raise ValueError(f"{triplet}: empty training window")
if not hold_idx:
    raise ValueError(f"{triplet}: empty holdout window")
```

Also validate:

```python
if len(set(dates)) != len(dates):
    raise ValueError(f"{triplet}: duplicate dates")
```

---

## Several metrics are calculated over the full period instead of holdout

In `validate_site_eb()`:

```python
"peak_timing_error_days": peak_timing_error_days(
    dates, swe, obs_swe),
```

and:

```python
depth_mm = [s * 3.0 for s in swe]
depth = score_paired_series(depth_mm, obs_depth_mm)
```

These include the training period. As a result, the artifact may appear stronger than its true out-of-sample performance.

### Fix

Calculate holdout metrics explicitly:

```python
hold_dates = [dates[i] for i in hold_idx]
hold_swe = [swe[i] for i in hold_idx]
hold_obs = [obs_swe[i] for i in hold_idx]

peak_timing = peak_timing_error_days(
    hold_dates, hold_swe, hold_obs
)
```

Likewise, calculate holdout snow-depth error and optionally report full-period metrics separately.

---

## “Snow depth” conversion is undocumented and potentially misleading

```python
depth_mm = [s * 3.0 for s in swe]
```

This assumes a fixed SWE-to-depth ratio. The code compares it to measured `SNWD`, but the factor is neither named nor given provenance.

### Fix

Name and document it:

```python
SNOW_DENSITY_RATIO = 1 / 3.0  # SWE / snow depth
```

Then:

```python
depth_mm = [s / SNOW_DENSITY_RATIO for s in swe]
```

Better still, make the conversion a parameter and record it:

```python
"snow_depth_conversion": {
    "swe_to_depth_factor": 3.0,
    "provenance": "authored_constant"
}
```

---

## `_fill_temps()` can produce misleading imputation

Missing values are forward-filled:

```python
out.append(out[-1])
```

This is reasonable for short gaps, but it is not symmetric with the air-temperature preparation logic unless `prepare_forcing()` uses the same policy. A missing TMAX/TMIN at the beginning immediately fails, while a missing value at the end is carried forward.

This should be documented in the artifact and tested against the shared forcing rules.

---

## Date parsing and day-of-year handling should be centralized

```python
y, m, d = (int(x) for x in iso.split("-"))
```

This accepts some malformed forms and duplicates date parsing behavior. Use `datetime.date.fromisoformat()`:

```python
return datetime.date.fromisoformat(iso).timetuple().tm_yday
```

---

## Frozen parameter validation needs finite/type checks

```python
s, c = params["s_rad"], params["c_turb_w_m2_k"]
if s not in S_GRID:
```

A boolean can become `1.0` through `float(True)`, and NaN gives confusing behavior. Validate explicitly:

```python
if isinstance(s, bool) or not math.isfinite(s):
    raise ValueError(...)
```

Also normalize the values before grid comparison if JSON artifacts may contain numeric formatting differences.

---

## Fixed-parameter evaluation still refits the degree-day comparator

In `evaluate_fixed_params()`, the energy model is correctly frozen, but the degree-day comparator is refitted on the new window:

```python
dd_k, dd_w, dd_train = fit_snow_params(... train_idx)
```

That is acceptable if the degree-day model is explicitly a re-fit baseline. It is not a fully frozen model comparison.

### Recommendation

Make the distinction visible in the output:

```python
"degree_day_comparator": {
    "parameter_policy": "refit_on_evaluation_train_window"
}
```

Or provide a frozen degree-day baseline for a strictly apples-to-apples comparison.

---

# Recommended priority order

1. Fix `publish.py` rollback for newly created files.
2. Make receipt creation atomic and transaction-aware.
3. Add actual `in_water()` validation in `review_proposals.py`.
4. Reject non-finite proposal and derived values.
5. Load existing override placements into spacing checks.
6. Fix polar-day insolation.
7. Validate non-empty train/holdout partitions.
8. Restrict reporting metrics to holdout data.
9. Remove unsafe default-to-pine behavior.
10. Make replay forcing quantity-specific and validate run-mode inputs.