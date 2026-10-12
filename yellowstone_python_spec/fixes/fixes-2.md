## Audit summary

The files are generally readable and have useful contract/registry intent, but several validation paths are not robust against malformed input. The most significant correctness issue is a **surface heat-flux sign contradiction between `coupling.py` and `equations.py`**. `compare.py` also reports a heat-budget error delta under the name `d_heat_throughput`, which is semantically incorrect.

---

## High-priority findings

### 1. Surface heat-flux sign convention contradicts the equation

**Files:** `coupling.py`, `equations.py`

`coupling.py` declares:

```python
"sign_convention": "positive into water",
"method": "Newton coefficient times air-minus-water temperature",
```

But `equations.py` states:

```text
Newton: Phi = h(T - Tair)
```

If positive means heat entering the water, the equation should be:

```text
Phi = h(Tair - T)
```

Otherwise a warmer atmosphere produces negative heating and a colder atmosphere produces positive heating.

### Fix

Update the equation inventory:

```python
"equations": "Newton: Phi = h(Tair - T); explicit: Phi = SW + LW + H + LE "
             "with scaled turbulent coefficients c_h, c_e",
```

Also add a regression test:

```python
def test_newton_flux_sign():
    h = 10.0
    water = 5.0
    air = 15.0
    assert h * (air - water) > 0
```

If the implementation intentionally uses `h * (T - Tair)`, then change the contract to “positive out of water.” The code, equations, and metadata must agree.

---

### 2. `compare.py` mislabels heat-budget error as heat throughput

**File:** `compare.py`

Current code:

```python
"d_heat_throughput": round(
    (cb.get("heat_budget_error", 0) - ca.get("heat_budget_error", 0)), 12),
```

This reports the change in **budget error**, not heat throughput. The field name is misleading and can lead downstream users to draw the wrong scientific conclusion.

### Fix options

If the intended metric is budget error:

```python
"d_heat_budget_error": round(
    cb.get("heat_budget_error", 0.0)
    - ca.get("heat_budget_error", 0.0),
    12,
),
```

If throughput is available, report it separately:

```python
"d_heat_throughput": round(
    cb.get("heat_throughput", 0.0)
    - ca.get("heat_throughput", 0.0),
    12,
),
"d_heat_budget_error": round(
    cb.get("heat_budget_error", 0.0)
    - ca.get("heat_budget_error", 0.0),
    12,
),
```

Avoid silently defaulting missing scientific metrics to zero. A missing metric and a true zero are different states.

---

### 3. `compare_builds()` assumes identical IDs and crashes on mismatches

**File:** `compare.py`

Examples:

```python
rb[rid]
fb[tid]
mb[pid]
```

If a build is missing an item, or contains an additional item, the function raises `KeyError`. This makes the comparison tool brittle and hides useful information about structural differences.

### Fix

Explicitly compare ID sets:

```python
def _index_records(records, *, label):
    result = {}
    for record in records:
        record_id = record.get("id")
        if not record_id:
            raise ValueError(f"{label} record has no id")
        if record_id in result:
            raise ValueError(f"duplicate {label} id: {record_id!r}")
        result[record_id] = record
    return result
```

Then report additions/removals:

```python
river_a = _index_records(_load(a, "river_state.json"), label="river")
river_b = _index_records(_load(b, "river_state.json"), label="river")

common = sorted(river_a.keys() & river_b.keys())
only_a = sorted(river_a.keys() - river_b.keys())
only_b = sorted(river_b.keys() - river_a.keys())
```

Return these explicitly:

```python
"structure": {
    "river_only_in_A": only_a,
    "river_only_in_B": only_b,
}
```

Apply the same approach to trout and landscape patches.

---

### 4. `check_coupling()` has an unreachable pocket-collision check

**File:** `coupling.py`

Current code:

```python
for cell in landscape:
    if cell.get("id") in solver_set:
        continue
    if cell.get("river_id") == "tributary":
        ...
        if cell.get("id") in solver_set:
            failures.append(...)
```

The inner collision condition can never execute because colliding IDs already hit `continue`.

### Fix

Check collisions before continuing:

```python
for cell in landscape:
    cell_id = cell.get("id")

    if cell_id in solver_set:
        if cell.get("river_id") == "tributary":
            failures.append(
                f"pocket {cell_id!r} collides with a solver cell id"
            )
        # This may be valid for ordinary mapped cells, depending on contract.
        continue

    if cell.get("river_id") == "tributary":
        n_pockets += 1
        if cell.get("conservation") != POCKET_CONSERVATION:
            failures.append(
                f"pocket {cell_id!r} lacks non-conservative label"
            )
        if "tributary_provenance" not in cell:
            failures.append(
                f"pocket {cell_id!r} lacks provenance record"
            )
    else:
        failures.append(
            f"landscape cell {cell_id!r} maps to no solver cell "
            "or declared pocket"
        )
```

---

### 5. Coupling volume check uses the wrong duration when replay time does not start at zero

**File:** `coupling.py`

Current code:

```python
duration = float(frames[-1].get("t_s", 0.0))
```

This assumes the first frame is at `t_s == 0`. If the replay begins at another time, the duration is wrong.

### Fix

```python
times = [float(frame["t_s"]) for frame in frames]
duration = times[-1] - times[0]
if duration < 0:
    failures.append("replay frame times are not ordered")
```

Also verify that frame times are finite and monotonic.

If source flow varies by frame, this check is still insufficient: volume must be integrated over the source time series rather than calculated as `flow * duration`.

---

## Medium-priority findings

### 6. Validation functions can crash instead of returning validation errors

**Files:** `coupling.py`, `equations.py`

Both contain this pattern:

```python
ids = [record["exchange_id"] for record in EXCHANGES]
```

and:

```python
names = [c["component"] for c in COMPONENTS]
```

If a record is malformed and missing the required key, validation raises `KeyError` despite being intended as a validator.

### Fix

Use `.get()` and report missing IDs:

```python
ids = []
for record in EXCHANGES:
    exchange_id = record.get("exchange_id")
    if exchange_id is not None:
        ids.append(exchange_id)

if len(ids) != len(set(ids)):
    errors.append("duplicate exchange_id in contract")
```

Likewise for `COMPONENTS`.

---

### 7. `claims.validate_claim()` lacks type and value validation

**File:** `claims.py`

The function checks field presence but not field shape. For example:

```python
"evaluation_dataset_ids": "some/path.json"
```

will be iterated character-by-character:

```python
for aid in record.get(key, []):
```

Similarly, `metrics`, `required_processes`, and `known_exclusions` can be strings, `None`, or arbitrary objects.

### Fix

Add schema validation:

```python
LIST_FIELDS = {
    "required_processes",
    "required_observations",
    "calibration_dataset_ids",
    "evaluation_dataset_ids",
    "metrics",
    "known_exclusions",
    "evidence_artifact_ids",
}

STRING_FIELDS = {
    "claim_id",
    "predicted_quantity",
    "intended_use",
    "spatial_domain",
    "temporal_domain",
    "supported_conditions",
    "model_version",
    "acceptance_criteria",
    "review_status",
}

for field in LIST_FIELDS:
    value = record.get(field)
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        errors.append(
            f"claim {record.get('claim_id', '?')}: "
            f"{field} must be a list of strings"
        )

for field in STRING_FIELDS:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(
            f"claim {record.get('claim_id', '?')}: "
            f"{field} must be a non-empty string"
        )
```

Also consider rejecting unknown fields if the registry is intended to be a strict schema.

---

### 8. Artifact path validation permits path traversal

**File:** `claims.py`

This check is insufficient:

```python
if not path or path.startswith(("-", "/", ".")) or " " in path:
```

A path such as this is accepted:

```text
derived/../outside/file.json
```

It may resolve outside the project root.

### Fix

Resolve and enforce containment:

```python
def resolve_artifact_id(artifact_id: str, root=None) -> Path:
    path, _ = split_artifact_id(artifact_id)

    if not path or "\x00" in path or " " in path:
        raise ValueError(f"malformed artifact id {artifact_id!r}")

    base = (
        Path(root).expanduser().resolve()
        if root is not None
        else Path(__file__).resolve().parents[1]
    )
    full = (base / path).resolve()

    try:
        full.relative_to(base)
    except ValueError as exc:
        raise ValueError(
            f"artifact id {artifact_id!r} escapes project root"
        ) from exc

    if not full.is_file():
        raise FileNotFoundError(
            f"registry id {artifact_id!r} resolves to missing file {full}"
        )
    return full
```

If symlinks are not allowed, additionally reject symlinked files that resolve outside the root.

---

### 9. `split_artifact_id()` uses a fragile delimiter format

**File:** `claims.py`

The format uses `:`:

```python
derived/file.json:holdout
```

This conflicts with Windows drive-letter paths and prevents colons in filenames. It is also not extensible if split names later need metadata.

Possible improvements:

- Keep the format but document that IDs are POSIX project-relative paths only.
- Use a structured representation internally.
- Or use a delimiter that cannot occur in paths, such as a separate object:

```python
{
    "path": "derived/snotel_obs.json",
    "split": "holdout",
}
```

At minimum, validate that the split is one of an allowed set rather than accepting any nonempty string.

---

### 10. `check_coupling()` does not validate record shapes before indexing

**File:** `coupling.py`

These expressions can raise exceptions:

```python
[cell["id"] for cell in rep.get("cells", [])]
[row["id"] for row in inventory.get("sources", [])]
```

A malformed replay document causes the checker itself to crash.

### Fix

Use a small helper:

```python
def _ids(records, label, failures):
    result = []
    if not isinstance(records, list):
        failures.append(f"{label} must be a list")
        return result

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            failures.append(f"{label}[{index}] must be an object")
            continue
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            failures.append(f"{label}[{index}] lacks a valid id")
            continue
        result.append(record_id)
    return result
```

Use this for cells, sources, inventory rows, and landscape records.

---

### 11. Missing or non-finite budget values can evade validation

**File:** `coupling.py`

Current code:

```python
actual = float(budget.get("lateral_input_m3", float("nan")))
if abs(actual - expected) / scale > 1e-9:
```

If `actual` is `NaN`, the comparison is false, so the check passes accidentally.

### Fix

```python
import math

raw_actual = budget.get("lateral_input_m3")
try:
    actual = float(raw_actual)
except (TypeError, ValueError):
    failures.append("lateral_input_m3 is not numeric")
else:
    if not math.isfinite(actual):
        failures.append("lateral_input_m3 is not finite")
    elif abs(actual - expected) / scale > 1e-9:
        failures.append(
            "solver lateral volume differs from recorded source flows"
        )
```

Apply the same finite-value checks to times, flows, temperatures, and other numerical inputs.

---

### 12. `check_coupling()` silently skips important checks when data is absent

Current logic:

```python
if inventory:
    ...
```

and:

```python
if budget and frames and sources:
    ...
```

An empty or missing inventory/budget can therefore avoid validation entirely.

Decide whether these are mandatory for a valid replay. If so, distinguish:

- absent: failure,
- present but empty: possibly failure,
- present and valid: inspect.

For example:

```python
if "thermal_inventory" not in rep.get("hydraulics_summary", {}):
    failures.append("missing thermal inventory")
```

---

## `equations.py` improvements

### 13. Inventory validation is too shallow

`validate_inventory()` only checks field presence and duplicate component names. It does not verify:

- non-empty strings,
- `module` paths are valid,
- equation text is present,
- component names are unique and normalized,
- declared model levels are from an allowed vocabulary.

At minimum:

```python
for field in ENTRY_FIELDS:
    value = c.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(
            f"component {c.get('component', '?')}: "
            f"{field} must be a non-empty string"
        )
```

If the inventory is intended to track implementation coverage, add a module-existence check using `importlib.util.find_spec()` or a repository-relative file check.

---

### 14. Some equation descriptions are dimensionally ambiguous

Examples:

```text
Qout = Qin + Qhot
```

`Qhot` appears to be a heat or thermal source, but `Qout` and `Qin` appear to be volumetric flow. This is dimensionally invalid unless `Qhot` is specifically a water discharge contribution.

Likewise:

```text
d(ViTi)/dt = ...
```

uses temperature rather than enthalpy while the text calls the terms “enthalpy.” A physically clearer inventory would state the heat capacity factor:

```text
d(rho cp V_i T_i)/dt = ...
```

or explicitly state that the equation is normalized by `rho cp`.

The inventory does not need to be a full mathematical specification, but the units and variable definitions should be made explicit.

---

## `compare.py` improvements

### 15. Validate build inputs before comparison

Currently `_load()` lets raw `FileNotFoundError`, `JSONDecodeError`, and malformed JSON propagate.

Improve diagnostics:

```python
def _load(d: Path, name: str):
    path = d / name
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise ValueError(f"missing build artifact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    return value
```

Also check that each top-level artifact has the expected structure before indexing.

### 16. Validate that the two builds are comparable

The output should include or verify:

- model version,
- scenario identifier,
- replay timestamp/window,
- forcing dataset IDs,
- solver configuration,
- calibration/evaluation state.

Otherwise two builds with different temporal windows may be compared as though they are a clean A/B experiment.

### 17. Avoid false “relocated” results

Current code:

```python
"relocated": fa[tid]["start_point_index"] != fb[tid]["start_point_index"]
```

This reports relocation based only on the starting index, not the final refuge or actual trajectory. If the intended result is endpoint relocation, compare the relevant final location field, such as:

```python
"relocated": (
    fa[tid].get("reach_id"),
    fa[tid].get("end_point_index"),
) != (
    fb[tid].get("reach_id"),
    fb[tid].get("end_point_index"),
)
```

If `start_point_index` is intentionally the outcome, rename the field to make that clear.

---

## Suggested test coverage

Add tests for these cases:

### `claims.py`

- Missing required field.
- Wrong type for list fields.
- Unknown review status.
- Accepted claim with no evaluation datasets.
- Duplicate claim IDs.
- Missing artifact.
- `../` path traversal.
- malformed split IDs:
  - `":holdout"`
  - `"file.json:"`
  - `"file.json:a:b"`

### `compare.py`

- Missing artifact file.
- Invalid JSON.
- Duplicate record IDs.
- Missing IDs between builds.
- Extra IDs between builds.
- Missing heat metrics.
- Nonzero build start time if replay metadata is present.

### `coupling.py`

- Duplicate solver IDs.
- Duplicate source IDs.
- Duplicate inventory IDs.
- Missing inventory.
- NaN budget values.
- Replay starting at nonzero time.
- Non-monotonic frame times.
- Pocket ID collision.
- Pocket missing provenance.
- Landscape cell with no mapping.
- Invalid surface method.
- Explicit budget without budget forcing.
- Newton method with budget forcing.

### `equations.py`

- Missing fields.
- Empty fields.
- Duplicate component names.
- Missing module file, if module verification is added.

---

## Recommended priority order

1. Fix the heat-flux sign inconsistency.
2. Correct the `d_heat_throughput` naming/semantics.
3. Fix the unreachable pocket-collision check.
4. Harden `compare_builds()` against mismatched IDs.
5. Add type/schema validation to claims and coupling documents.
6. Prevent artifact path traversal.
7. Fix replay duration calculation.
8. Add finite-number and missing-data checks.
9. Improve equation dimensional clarity.
10. Add the regression tests above.