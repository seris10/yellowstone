Yes—this is useful as a **file-integrity tripwire**, but it is weak as a terrain-quality guard. It verifies “this file has the expected size, approximate value range, and optionally expected hash,” not that the terrain is spatially or scientifically valid.

## Main problems

### 1. NaN terrain can pass the range guard

This is the most important correctness bug.

```python
if info["min_m"] < min_m or info["max_m"] > max_m:
```

If the terrain contains NaNs, `grid.min()` and `grid.max()` may be `nan`. Both comparisons return `False`, so the range guard can pass.

### Fix

```python
finite_mask = np.isfinite(raw)

if not finite_mask.all():
    bad_count = int((~finite_mask).sum())
    guards.append({
        "name": "finite",
        "passed": False,
        "detail": f"{bad_count} non-finite float32 values",
    })
else:
    guards.append({
        "name": "finite",
        "passed": True,
        "detail": "all terrain values are finite",
    })
```

Do this before calculating min/max.

---

### 2. It does not validate the requested bounds

The CLI accepts:

```bash
--min-m 250 --max-m -20
```

and then reports failure for every valid terrain, but the input itself is invalid.

Add:

```python
min_m = float(args.min_m)
max_m = float(args.max_m)

if not math.isfinite(min_m) or not math.isfinite(max_m):
    parser.error("--min-m and --max-m must be finite")

if min_m >= max_m:
    parser.error("--min-m must be less than --max-m")
```

Also validate `expect_sha256` as a 64-character hexadecimal digest.

---

### 3. The comments claim percentile checks that are not implemented

The comment says:

```text
Tripwires containing the measured envelope
(min -10.89, max 238.13, p1 -5.09, p99 221.28)
```

but the script only checks:

```python
min_m
max_m
```

It never calculates `p1` or `p99`.

Either remove the percentile claim or implement it:

```python
p1, p99 = np.percentile(raw, [1.0, 99.0])

info.update({
    "p01_m": float(p1),
    "p99_m": float(p99),
})
```

Percentiles are useful for detecting corrupt strips or isolated spikes that do not exceed the absolute range.

---

### 4. The terrain is not checked for spatial plausibility

A file can have:

- the correct size;
- the correct hash if the expected hash was updated;
- plausible minimum and maximum values;

yet still be spatially corrupted, transposed, flipped, shifted, or replaced with random smooth-looking values.

The guard should calculate at least:

- adjacent-cell slope statistics;
- maximum local slope;
- fraction of extreme slopes;
- number of flat cells;
- connected NaN/invalid regions;
- edge/interior statistics;
- optional known control-point elevations.

Example:

```python
dx_m = 4.0

dz_dx = np.diff(grid, axis=1) / dx_m
dz_dz = np.diff(grid, axis=0) / dx_m

slope = np.hypot(
    dz_dx[:-1, :],
    dz_dz[:, :-1],
)

info["slope"] = {
    "max_m_per_m": float(np.max(slope)),
    "p99_m_per_m": float(np.percentile(slope, 99)),
    "mean_m_per_m": float(np.mean(slope)),
}
```

Then guard against obvious corruption:

```python
if info["slope"]["p99_m_per_m"] > 5.0:
    guards.append({
        "name": "slope-plausibility",
        "passed": False,
        "detail": "unusually large local slopes",
    })
```

The threshold must be project-specific and should be labeled as a tripwire, not a physical truth.

---

### 5. `STEP = 4.0` is duplicated elsewhere but not used here

`overland_flow.py` has:

```python
STEP = 4.0
```

`check_terrain.py` does not define the source cell size at all. If slope checks are added, a hardcoded spacing must be centralized.

Create shared terrain metadata:

```python
TERRAIN_GRID = 1025
TERRAIN_CELL_M = 4.0
TERRAIN_DTYPE = "<f4"
```

or load it from a manifest:

```json
{
  "path": "data/terrain.f32",
  "shape": [1025, 1025],
  "dtype": "<f4",
  "cell_size_m": 4.0,
  "axis_order": ["z", "x"],
  "vertical_datum": "unknown"
}
```

---

### 6. It does not check the terrain’s coordinate orientation

The guard verifies array dimensions but not whether:

- rows correspond to north/south or z;
- columns correspond to east/west or x;
- the origin is correct;
- the array is vertically flipped;
- the terrain agrees with the world coordinate convention.

This matters because `vegetation.load_terrain()`, `terrain_fns()`, overland flow, masks, and rendered world coordinates all consume the same terrain.

Add a terrain manifest with:

```json
{
  "axis_order": "row=z, col=x",
  "row_direction": "increasing_south",
  "column_direction": "increasing_east",
  "origin_x_m": -2048.0,
  "origin_z_m": -2048.0,
  "cell_size_m": 4.0
}
```

Then validate the binary terrain against that manifest.

---

### 7. It does not validate the vertical datum

The comment explicitly says:

```text
Datum undocumented
```

That is a serious limitation for:

- cross-section depths;
- hydrology;
- slope;
- cloud/terrain elevation relationships;
- world placement.

The script should not pretend that a plausible elevation range means the terrain is correctly georeferenced.

Add metadata:

```python
info["vertical_datum"] = "unknown"
```

and make this a visible warning:

```python
guards.append({
    "name": "vertical-datum",
    "passed": False,
    "detail": "vertical datum is undocumented",
})
```

Whether that should fail the build depends on the build mode:

```text
strict scientific mode: fail
visual mode: warning
```

---

### 8. The fixed-size requirement is too rigid for a reusable guard

Current constants:

```python
GRID = 1025
N_ELEMS = GRID * GRID
```

This is acceptable for this one asset, but it makes the guard less reusable and hides the fact that `1025` may be a **vertex grid**, while hydrology may treat it as cells.

That distinction matters:

- a 1025×1025 vertex DEM represents 1024×1024 cells;
- `overland_flow.py` currently downsamples the full 1025×1025 array;
- the meaning of `cell_m=4.0` may therefore be ambiguous.

The guard should identify this explicitly:

```python
"grid_semantics": "vertices",
"cell_count": [1024, 1024],
"vertex_count": [1025, 1025],
```

If hydrosim expects cell-centered elevations, either:

- trim the final row/column intentionally;
- resample to cell centers;
- or document the hydrosim convention.

This is more important than the current byte-size check.

---

### 9. The hash is checked too late and only in some paths

For a wrong-size file, the function returns before calculating the hash. That is not necessarily incorrect, but it means the report does not identify the actual file digest.

A stronger report should always calculate the hash if the file can be read:

```python
sha256 = hash_file(path)
```

Then independently report:

```text
size passed/failed
grid passed/failed
finite passed/failed
range passed/failed
hash passed/failed
```

This helps diagnose “wrong file” versus “corrupt file.”

---

### 10. Hash comparison is not normalized or validated

Current code compares directly:

```python
info["sha256"] != expect_sha256
```

A digest supplied in uppercase will fail even though it is equivalent.

Use:

```python
expected = expect_sha256.strip().lower()
actual = info["sha256"].lower()
```

Validate:

```python
if not re.fullmatch(r"[0-9a-f]{64}", expected):
    raise ValueError("expected SHA-256 must be 64 hexadecimal characters")
```

---

### 11. `BUILD.json` lookup may trust the wrong build

The script searches ancestors:

```python
for parent in [here, *here.parents]:
```

and takes the first `BUILD.json` containing:

```python
deps["terrain.f32"]
```

That can accidentally use a parent build’s hash for a different terrain file.

At minimum, confirm that the dependency path corresponds to the resolved terrain path:

```python
terrain_path = path.resolve()
dep_path = Path(dep_entry.get("path", "")).resolve()

if dep_path == terrain_path:
    expect = dep_entry["sha256"]
```

A dependency entry should be structured:

```json
"terrain.f32": {
  "path": ".../terrain.f32",
  "sha256": "...",
  "size": 4202500
}
```

not only:

```json
"terrain.f32": "hash"
```

---

### 12. `guard_terrain()` has an undeclared hard dependency on NumPy

The script imports NumPy only after the size check:

```python
import numpy as np
```

If NumPy is unavailable, the guard crashes without a useful report.

Options:

- declare NumPy as a required tool dependency;
- catch the import error and return a failed guard;
- implement a lightweight `struct`/`array` fallback.

For a scientific terrain guard, requiring NumPy is reasonable:

```python
try:
    import numpy as np
except ImportError as exc:
    raise RuntimeError(
        "check_terrain requires numpy"
    ) from exc
```

---

### 13. The output JSON may contain non-finite values

The report writes:

```python
json.dumps(report, indent=2)
```

without:

```python
allow_nan=False
```

If the terrain contains NaNs and NumPy produces `nan`, Python’s JSON encoder can emit non-standard JSON:

```json
NaN
```

Use:

```python
json.dumps(
    report,
    indent=2,
    allow_nan=False,
)
```

This should be combined with an explicit finite guard.

---

### 14. The guard is not actually integrated with the build

The documentation says:

```text
Guard terrain.f32 ... before a build trusts the file.
```

But this script does not appear to be called by `build.py`. It only independently reports status.

If the build can proceed without invoking it, it is advisory, not a guard.

Add one of:

```python
build.py → guard_terrain(...)
```

or a required pre-build command:

```bash
python tools/check_terrain.py
python -m yellowstone_python.build ...
```

Better:

```python
terrain_report = guard_terrain(...)
if not terrain_report["passed"]:
    raise BuildError("terrain guard failed")
```

Store the report in `BUILD.json`:

```json
{
  "guards": {
    "terrain": {
      "schema": "yellowstone.terrain_guard.v1",
      "passed": true,
      "sha256": "..."
    }
  }
}
```

---

# Recommended stronger design

Split the checks into categories.

## Integrity checks

These should normally fail:

```text
file exists
file readable
expected byte size
expected dtype
expected hash
```

## Numerical validity checks

These should normally fail:

```text
all finite
minimum/maximum range
optional percentile range
```

## Spatial plausibility checks

These may be warnings or failures depending on mode:

```text
local slope distribution
adjacent jump distribution
flat-region fraction
edge discontinuities
```

## Scientific metadata checks

These should be explicit:

```text
grid semantics
cell size
axis order
world extent
vertical datum
source DEM
processing version
```

---

# Example stronger report

```json
{
  "schema": "yellowstone.terrain_guard.v2",
  "status": "terrain_integrity_and_plausibility_guard",
  "passed": true,
  "terrain": {
    "path": "data/terrain.f32",
    "sha256": "...",
    "nbytes": 4202500,
    "dtype": "<f4",
    "vertex_dims": [1025, 1025],
    "cell_dims": [1024, 1024],
    "cell_size_m": 4.0,
    "vertical_datum": "unknown",
    "min_m": -10.89,
    "max_m": 238.13,
    "p01_m": -5.09,
    "p99_m": 221.28,
    "mean_m": 94.2,
    "finite_fraction": 1.0
  },
  "guards": [
    {
      "name": "size",
      "passed": true
    },
    {
      "name": "dtype",
      "passed": true
    },
    {
      "name": "finite",
      "passed": true
    },
    {
      "name": "range",
      "passed": true
    },
    {
      "name": "percentiles",
      "passed": true
    },
    {
      "name": "hash",
      "passed": true
    },
    {
      "name": "spatial-jumps",
      "passed": true,
      "detail": "p99 adjacent elevation jump = 1.8 m"
    },
    {
      "name": "vertical-datum",
      "passed": false,
      "severity": "warning",
      "detail": "vertical datum undocumented"
    }
  ]
}
```

Notice that scientific metadata can be incomplete without pretending the raw bytes are invalid.

---

# Minimal patch for the most urgent issues

Add imports:

```python
import math
import re
```

Add:

```python
def _validate_sha256(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip().lower()

    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError(
            "expected SHA-256 must be 64 hexadecimal characters"
        )

    return normalized
```

Before range checks:

```python
if not np.isfinite(raw).all():
    bad = int((~np.isfinite(raw)).sum())
    guards.append({
        "name": "finite",
        "passed": False,
        "detail": f"{bad} non-finite values",
    })
else:
    guards.append({
        "name": "finite",
        "passed": True,
        "detail": "all values finite",
    })
```

Add percentiles:

```python
if np.isfinite(raw).all():
    p01, p99 = np.percentile(raw, [1.0, 99.0])
    info["p01_m"] = float(p01)
    info["p99_m"] = float(p99)
```

Validate bounds:

```python
if not math.isfinite(min_m) or not math.isfinite(max_m):
    raise ValueError("terrain bounds must be finite")

if min_m >= max_m:
    raise ValueError("min_m must be less than max_m")
```

Write strict JSON:

```python
tmp.write_text(
    json.dumps(report, indent=2, allow_nan=False) + "\n",
    encoding="utf-8",
)
```

---

## Bottom line

Your instinct is right: `check_terrain.py` is currently a **basic checksum-and-envelope check**, not a robust terrain validation system.

It should be improved primarily by:

1. rejecting NaNs and infinities;
2. implementing the documented percentile checks;
3. validating spatial gradients and jumps;
4. recording vertex-versus-cell semantics;
5. documenting datum and coordinate orientation;
6. ensuring the build actually invokes it;
7. making the `BUILD.json` hash association path-specific;
8. separating file integrity from scientific terrain validity.

The current script is still worth keeping, but it should be described as:

```text
terrain binary integrity tripwire
```

until those stronger checks and build integration are added.