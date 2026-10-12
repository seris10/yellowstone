## Audit summary

I found several correctness issues, a few likely runtime failures, and some model/design inconsistencies. The highest-priority fixes are:

1. **`fish.py` raises `NameError` when thermal-data helpers are called.**
2. **`fish.py` can produce suitability values outside the documented range.**
3. **Reach-chain ordering and reach windows are fragile and may assign points to the wrong reach.**
4. **`gen_flora.py` uses point-distance checks for rivers/routes instead of segment-distance checks, allowing placements through gaps.**
5. **`gen_flora.py` has order-dependent global state and several empty-array failure cases.**
6. **Flora candidates are not checked against other candidates, so generated plants can overlap or violate spacing.**

---

# `fish.py`

## High-priority issues

### 1. `REAL_LAB_DATA_PATH` is undefined

These functions fail immediately:

```python
def load_lab_thermal(...):
    if REAL_LAB_DATA_PATH is None:
```

and:

```python
def thermal_data_status():
    "real_lab_data_available": REAL_LAB_DATA_PATH is not None,
```

There is only a commented reference:

```python
# Lab thermal measurements integration point. REAL_LAB_DATA_PATH = None
```

### Fix

Define it explicitly:

```python
REAL_LAB_DATA_PATH: str | None = None
```

Preferably allow configuration through an environment variable:

```python
import os

REAL_LAB_DATA_PATH = os.getenv("REAL_LAB_DATA_PATH")
```

Also, `load_lab_thermal()` currently imports `pathlib` and `json` but never loads anything. Either implement it or make the limitation explicit:

```python
def load_lab_thermal(species: str = "brown_trout") -> dict | None:
    """Return configured laboratory data, or None when unavailable."""
    if REAL_LAB_DATA_PATH is None:
        return None

    path = Path(REAL_LAB_DATA_PATH)
    if not path.is_file():
        return None

    data = json.loads(path.read_text())
    return data.get(species)
```

---

### 2. `suitability()` is not guaranteed to be nondimensional or bounded

The docstring implies a suitability score, but the result can be:

- strongly negative,
- greater than `1`,
- greater than the nominal contribution range if inputs are unbounded.

For example:

```python
depth_term = 1.0 - min(1.0, float(depth) / DEPTH_REF_M)
```

If `depth > DEPTH_REF_M`, `depth_term` becomes negative:

```python
depth = 2.0
depth_term = 1 - 1 = 0
```

Actually values above the reference are capped at zero, so deep water receives no penalty. That may be intended, but it does not represent a preferred depth range. More importantly, negative `food` or `cover` values are accepted, and species thermal terms can exceed `1`.

This line can exceed one:

```python
temp_term = (1.0 - perf["feeding"]) + perf["stress"]
```

At high temperatures, this reaches `2.0`.

### Fix

Normalize input features and explicitly clamp the final result:

```python
def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
```

Then:

```python
food_term = _clamp01(food)
cover_term = _clamp01(cover)
```

For thermal stress, either retain a penalty score that can exceed one and document it, or cap it:

```python
temp_term = min(
    1.0,
    (1.0 - perf["feeding"]) + perf["stress"],
)
```

Finally:

```python
u = (
    w["wf"] * food_term
    + w["wc"] * cover_term
    - w["wt"] * temp_term
    - w["wv"] * vel_term
    - w["wd"] * depth_term
    - float(refuge_weight) * refuge_term
)
return max(0.0, min(1.0, u))
```

If negative values are useful for ranking, do not clamp—but change the documentation to say the score is an unbounded ranking utility.

---

### 3. Default weights sum to `1.8`

```python
DEFAULT_WEIGHTS = {
    "wf": 0.4,
    "wc": 0.3,
    "wt": 0.5,
    "wv": 0.4,
    "wd": 0.2,
}
```

The positive terms total `0.7`, while penalties total `1.1`. This may be intentional, but it makes the score difficult to interpret as a normalized suitability value.

### Recommendation

Either normalize weights:

```python
def normalize_weights(weights: dict) -> dict:
    total = sum(max(0.0, float(v)) for v in weights.values())
    if total <= 0:
        raise ValueError("at least one weight must be positive")
    return {k: max(0.0, float(v)) / total for k, v in weights.items()}
```

Or document that the weights are calibrated coefficients rather than proportions.

---

### 4. Depth suitability is one-sided, despite the documentation

Current code:

```python
depth_term = 1.0 - min(1.0, float(depth) / DEPTH_REF_M)
```

This gives:

| Depth | Penalty |
|---:|---:|
| 0 m | 1 |
| 0.5 m | 0.58 |
| 1.2 m | 0 |
| 10 m | 0 |

Deep water is treated as equally suitable as exactly `DEPTH_REF_M`.

If the intended model is a preferred depth, use a two-sided penalty:

```python
DEPTH_TOL_M = 0.8

depth_term = min(
    1.0,
    abs(float(depth) - DEPTH_REF_M) / DEPTH_TOL_M,
)
```

Or define explicit minimum and maximum preferred depths.

---

### 5. Unknown species errors occur late and can abort the entire update

`update_trout()` obtains species from the record:

```python
species = rec.get("species", "brown_trout")
```

Then `thermal_performance()` raises for unknown species. One malformed record can terminate processing for every trout.

### Fix

Validate before processing:

```python
species = rec.get("species", "brown_trout")
if species not in THERMAL_SPECIES:
    rec["refuge_reason"] = f"unknown species {species!r}; skipped"
    continue
```

Alternatively, raise a clear error before making any modifications.

---

## Reach assignment issues

### 6. `_chain_order()` may traverse the chain in the wrong direction

The function says:

```python
"""Order reaches by declared upstream_id chain (first = boundary)."""
```

But the traversal is:

```python
nxt = cur.get("upstream_id")
cur = by_id.get(nxt)
```

If `upstream_id` means “the reach immediately upstream of this reach”, then starting at a reach with no `upstream_id` and following `upstream_id` moves upstream from the boundary, which may be correct only if the first node is the downstream boundary. The naming and direction are ambiguous.

This ambiguity directly affects:

```python
reach_z_windows()
reach_membership()
```

### Recommendation

Use explicit terminology and validate the chain:

```python
def _chain_order(reaches: list[dict]) -> list[dict]:
    ...
```

Add checks for:

- missing referenced IDs,
- multiple roots,
- cycles,
- disconnected components,
- duplicate IDs.

For example:

```python
ids = [r["id"] for r in reaches]
if len(ids) != len(set(ids)):
    raise ValueError("duplicate reach IDs")

missing = {
    r["upstream_id"]
    for r in reaches
    if r.get("upstream_id") and r["upstream_id"] not in by_id
}
if missing:
    raise ValueError(f"unknown upstream reach IDs: {sorted(missing)}")
```

---

### 7. `reach_z_windows()` can create unintuitive windows

```python
lo = float(r["z"])
hi = float(ordered[i - 1]["z"]) if i > 0 else 1e9
```

This assumes the ordered list and the z-coordinate direction always agree. If the chain order is reversed or z is not monotonically ordered, the resulting bands can be incorrect.

Also, the first reach gets an effectively infinite upper bound, which may assign nearly every unmatched point to that reach.

### Better approach

Assign membership by chainage, not by z. Since the code already has river points, calculate each reach's nearest chainage or use declared point/index bounds. Z-based windows are not robust for bends, loops, or non-monotonic elevation.

At minimum, verify windows:

```python
if lo > hi:
    raise ValueError(f"invalid reach window for {r['id']}: {lo}, {hi}")
```

---

### 8. `reach_membership()` accepts a `reaches` list but relies on z-only membership

The docstring correctly notes that z-nearestness fails for looping channels, but the replacement still uses z-windows:

```python
if lo <= z <= hi:
```

This remains unreliable for:

- U-shaped channels,
- loops,
- repeated elevations,
- reaches with overlapping z ranges.

A true chainage-based membership calculation would solve the stated problem.

---

## Refuge selection issues

### 9. `select_refuge()` assumes valid indices and a valid chainage array

These can raise `IndexError` or produce incorrect results:

```python
i0, i1 = int(record["start_point_index"]), int(record["end_point_index"])
mid_s = (chainage[i0] + chainage[i1]) / 2.0
```

Add validation:

```python
if not 0 <= i0 <= i1 < len(river_points):
    raise ValueError(f"invalid trout interval: {i0}, {i1}")
if len(chainage) != len(river_points):
    raise ValueError("chainage and river_points must have equal length")
```

Also reject empty river point lists before calling `min()` or `next()`.

---

### 10. The swim-window search is more complicated than necessary

Current code:

```python
lo = next(i for i, s in enumerate(chainage) if s >= mid_s - REFUGE_WINDOW_M)
hi = next((i for i, s in enumerate(chainage) if s > mid_s + REFUGE_WINDOW_M),
          len(chainage) - 1)
```

This is O(n) and assumes monotonic chainage. Use `bisect`:

```python
from bisect import bisect_left, bisect_right

lo = max(0, bisect_left(chainage, mid_s - REFUGE_WINDOW_M))
hi = min(
    len(chainage) - 1,
    bisect_right(chainage, mid_s + REFUGE_WINDOW_M),
)
```

This also makes the boundary behavior clearer.

---

### 11. The selected `reach_id` is based on the best single index, but the holding window may span multiple reaches

That may be acceptable, but the record then represents an interval with one reach ID:

```python
"reach_id": best_r
```

Consider storing:

```python
"reach_ids": sorted(set(...))
```

or explicitly documenting that the ID identifies the best midpoint rather than the whole holding segment.

---

### 12. `check_trout_clear_of_pools()` does not validate record bounds

Malformed records can cause invalid indexing:

```python
for i in range(int(rec["start_point_index"]),
               int(rec["end_point_index"])):
```

Add the same interval validation used by `select_refuge()`.

Also, the function only tests the centerline and one offset:

```python
for off in (0.0, lateral):
```

If `lateral` is signed, this is probably correct for the actual fish path. If the intent is to validate the whole possible lateral corridor, sample both sides:

```python
offsets = {0.0, lateral, -abs(lateral), abs(lateral)}
```

---

# `gen_flora.py`

## High-priority issues

### 1. River and route exclusion checks only test vertices

Several functions do this:

```python
d2 = (river_pts[:, 0] - x) ** 2 + (river_pts[:, 1] - z) ** 2
if bool(((d2 < (river_hw + 2.0) ** 2)).any()):
    continue
```

and:

```python
if bool((((route_pts[:, 0] - x) ** 2 +
          (route_pts[:, 1] - z) ** 2) < (route_pts[:, 2]) ** 2).any()):
    continue
```

These only check distance to sampled points, not distance to the line segments connecting them. A candidate can fall between widely spaced points and be placed directly on a river or route.

### Fix

Implement point-to-segment distance:

```python
def point_segment_distance_sq(px, pz, ax, az, bx, bz):
    dx, dz = bx - ax, bz - az
    denom = dx * dx + dz * dz
    if denom == 0:
        return (px - ax) ** 2 + (pz - az) ** 2

    t = ((px - ax) * dx + (pz - az) * dz) / denom
    t = max(0.0, min(1.0, t))
    qx, qz = ax + t * dx, az + t * dz
    return (px - qx) ** 2 + (pz - qz) ** 2
```

Then use a reusable polyline exclusion function. This should also be used for pool-like or route geometry where appropriate.

---

### 2. Empty river/route arrays can cause indexing errors

For example:

```python
river_pts = _np.array(river_pts)
...
river_pts[:, 0]
```

If there are no rivers, the array has shape `(0,)`, and indexing with `[:, 0]` fails.

Likewise for `route_pts`.

### Fix

Normalize shapes:

```python
river_pts = _np.asarray(river_pts, dtype=float).reshape(-1, 2)
river_hw = _np.asarray(river_hw, dtype=float).reshape(-1)

route_pts = _np.asarray(route_pts, dtype=float).reshape(-1, 3)
```

Then skip checks when empty:

```python
if len(river_pts):
    ...
```

The same issue occurs in:

- `forest_infill()`
- `grove_planting()`
- `deck_viewshed_groves()`

---

### 3. `_BARREN` is mutable global state and makes behavior order-dependent

```python
_BARREN = (None,)
```

Several functions mutate it:

```python
global _BARREN
_BARREN = (True,) + _ortho()
```

`deck_viewshed_groves()` reads `_BARREN` but does not initialize it. Therefore:

- calling it directly uses the initial `(None,)` state;
- calling another generator first changes its behavior;
- tests can pass or fail depending on call order.

### Fix

Do not use global state. Load the orthophoto locally or pass it into helper functions:

```python
def deck_viewshed_groves(..., ortho_data=None):
    if ortho_data is None:
        ortho_data = _ortho()
```

Better:

```python
def load_barren_test():
    im, H, W = _ortho()
    return lambda x, z: is_barren(im, H, W, x, z)
```

Then each generator receives an explicit `barren_test`.

---

### 4. Hard-coded world bounds are inconsistent with imported constants

The code uses:

```python
(x + 2048) / 4096
```

and:

```python
n = int(4096 / cell)
```

while also importing:

```python
from .vegetation import GRID, HALF, STEP
```

If the world size changes, terrain and orthophoto coordinates will diverge.

### Fix

Use `HALF` consistently:

```python
world_size = 2.0 * HALF
ix = min(max(int((x + HALF) / world_size * (W - 1)), 0), W - 1)
```

For grid iteration:

```python
n = math.ceil((2.0 * HALF) / cell)
```

Also ensure the orthophoto georeferencing is centralized in one helper.

---

## Placement-quality issues

### 5. Candidate-to-candidate spacing is not enforced

Existing trees are checked:

```python
tree.query_ball_point([x, z], 4.0)
```

But newly accepted records are not inserted into the spatial index. Consequently:

- corridor grass candidates can overlap,
- corridor pines can be too close to one another,
- grove jitter can violate intended spacing,
- deck candidates can overlap across nearby cells,
- multiple generator passes can duplicate plants unless all prior overrides are loaded correctly.

### Fix

Maintain an accepted spatial index or at least a list with distance checks. For large batches, rebuild a KD-tree periodically:

```python
accepted_xy = []

def clear_of_accepted(x, z, radius):
    return all(
        (x - ax) ** 2 + (z - az) ** 2 >= radius ** 2
        for ax, az in accepted_xy
    )
```

For performance, use `cKDTree` after each batch or use a spatial hash grid.

---

### 6. Existing override records are deduplicated using `"id"`, but generated records use `"stable_id"`

This code assumes `to_override_record()` always converts the identifier:

```python
have = {r["id"] for r in ov.get("add", [])}
if rec["stable_id"] in have:
```

That may be correct, but it is an implicit contract. If any override lacks `"id"` or uses `"stable_id"`, this fails or duplicates records.

### Fix

Centralize identity extraction:

```python
def override_id(record: dict) -> str | None:
    return record.get("id") or record.get("stable_id")
```

Then:

```python
have = {
    override_id(r)
    for r in ov.get("add", [])
    if override_id(r) is not None
}
```

Also validate the result of `to_override_record()` before writing.

---

### 7. Writes are not atomic

Both staging paths directly overwrite the JSON file:

```python
ov_path.write_text(json.dumps(ov, indent=1))
```

A crash or interruption can leave `placement_overrides.json` truncated.

### Fix

Write to a temporary file and replace atomically:

```python
tmp = ov_path.with_suffix(".tmp")
tmp.write_text(json.dumps(ov, indent=1) + "\n")
tmp.replace(ov_path)
```

Use a file lock if multiple generation processes may run concurrently.

---

### 8. `main()` is invoked before the rest of the module definitions

The file contains:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

before definitions of:

- `_ortho`
- `forest_infill`
- `corridor_flora`
- `grove_planting`
- `deck_viewshed_groves`

This does not break the current CLI because `main()` only uses earlier definitions, but it is fragile and surprising. If `main()` later dispatches to one of those functions, it will fail during module execution.

### Fix

Move the `if __name__ == "__main__"` block to the end of the file.

---

## Logic and maintainability issues

### 9. The CLI does not expose most implemented generators

The module implements several generation passes, but the CLI only runs `REGIONS`:

```python
for reg in REGIONS:
    ...
```

The following functions are unreachable from the documented command:

- `forest_infill`
- `corridor_flora`
- `grove_planting`
- `deck_viewshed_groves`

Either remove them from this module or add explicit CLI options:

```text
--regions
--forest-infill
--corridor-flora
--grove
--deck-groves
```

Avoid silently maintaining dead generation paths.

---

### 10. The first pass and later passes use different exclusion policies

The main region pass uses:

```python
exclusion_test=excluded
```

where `excluded` only checks pool aprons:

```python
excluded = lambda x, z: any(_in_apron(x, z, s) for s in shells)
```

It does not visibly exclude:

- rivers,
- routes,
- existing plantings,
- other generated candidates.

The later generators use more gates. This means similar flora generation paths have inconsistent placement guarantees.

### Recommendation

Create one shared `PlacementConstraints` object or common helper:

```python
constraints = PlacementConstraints(
    shells=shells,
    river_segments=...,
    route_segments=...,
    existing_trees=...,
)
```

All generators should use the same exclusion API.

---

### 11. Pool checks perform unnecessary repeated work

For example:

```python
if any((x - cx) ** 2 + (z - cz) ** 2 < (r + 2.0) ** 2
       for cx, cz, r in circles):
    if any(_in_apron(x, z, s) for s in shells):
        continue
```

This is a useful broad phase, but it is repeated in multiple functions and does not make the broad-phase circles correspond exactly to each shell geometry. Encapsulate it:

```python
def excluded_by_shells(x, z, shells, circles):
    ...
```

A spatial index would improve performance for large candidate counts.

---

### 12. `grove_planting()` hardcodes suitability

```python
"suitability": 0.9,
```

This differs from the actual computed suitability used elsewhere. It makes generated records misleading and can break downstream review or reporting.

### Fix

Compute and store the actual value:

```python
suit = ...
...
"suitability": round(float(suit), 3),
```

If `0.9` is intentionally an evidence confidence rather than ecological suitability, use a separate field:

```python
"evidence_confidence": 0.9
```

---

### 13. `grove_planting()` does not use `canopy_light_max`

The parameter is present only in the comparison:

```python
if light[oz, ox] > canopy_light_max:
    continue
```

That is fine, but the function samples only the top-left cell:

```python
x0, z0 = ...
ox, oz = ...
```

while placements cover the entire cell. A cell can be dark at its corner and bright elsewhere, or vice versa. Sample the candidate point instead of the cell origin.

---

### 14. `deck_viewshed_groves()` imports unused functions

```python
from .pool_crust import in_apron, in_water
```

Neither is used in the function. Similarly, several imports and variables are unused across the module.

Run:

```bash
ruff check gen_flora.py fish.py
```

and remove or correct the reported items.

---

# Recommended tests

Add focused tests before changing generation behavior.

## `fish.py`

```python
def test_thermal_data_status_does_not_raise():
    status = thermal_data_status()
    assert "real_lab_data_available" in status

def test_suitability_is_finite():
    value = suitability(0.7, 0.6, 24, 0.35, 1.1,
                        species="brown_trout",
                        refuge_weight=REFUGE_WEIGHT)
    assert math.isfinite(value)

def test_invalid_trout_interval_is_rejected():
    ...
```

Test:

- temperatures below and above all anchors,
- unknown species,
- depth above reference,
- empty river point lists,
- zero-length chainage,
- non-monotonic z reaches,
- cyclic `upstream_id` data.

## `gen_flora.py`

Test:

- no rivers,
- no routes,
- no pools,
- empty existing tree list,
- orthophoto/world coordinate boundaries,
- duplicate stable IDs,
- candidate spacing,
- placement directly between two route/rivers vertices,
- repeated generator calls in different orders.

---

# Suggested implementation order

1. Define `REAL_LAB_DATA_PATH`.
2. Add validation for fish indices, species, reaches, and empty inputs.
3. Decide whether suitability is bounded or an unbounded utility; update code and docs consistently.
4. Replace z-window reach membership with chainage-based membership.
5. Centralize flora exclusion checks.
6. Replace vertex-only river/route checks with point-to-segment checks.
7. Remove `_BARREN` global state.
8. Normalize empty NumPy arrays.
9. Add candidate-to-candidate spacing.
10. Make override writes atomic and add CLI controls for the additional generators.