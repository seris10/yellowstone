## Audit summary

The highest-risk issues are:

1. **`hydro_thermal.step_heat()` loses most of its budget ledger when substepping.**
2. **`hydro_thermal.steady_state()` does not match the sequential transport model unless every reach has a valid `upstream_id`.**
3. **`grazers.plan_path()` uses an incorrectly scaled A* heuristic and fails to validate the actual start/goal segments.**
4. **`gen_trail_mask.py` promises an import note but never creates one, and can fail if the output directory does not exist.**
5. Several functions lack validation for empty inputs, invalid dimensions, zero volumes, negative flows, and malformed geometry.

---

# `gen_trail_mask.py`

### Issues

### 1. Output directory may not exist

```python
out = WORLD / "assets" / "textures" / "trail_mask.png"
mask.save(out)
```

This fails if `assets/textures` has not already been created.

### Fix

```python
out.parent.mkdir(parents=True, exist_ok=True)
mask.save(out)
```

---

### 2. The documented `.import` note is never written

The module says:

```text
Output: yellowstone_midway/assets/textures/trail_mask.png (+ .import note)
```

but only writes the PNG. Either create the import file or remove it from the documentation.

For Godot 4, consider generating the corresponding `.import` metadata only if the project convention requires checked-in import files. Otherwise, Godot generally generates it automatically.

---

### 3. Pixel scale is slightly inconsistent

```python
return ((x + HALF) / (2 * HALF) * (SIZE - 1),
        (z + HALF) / (2 * HALF) * (SIZE - 1))
```

With `SIZE=2048` and a 4096 m extent, this gives approximately `2.001 m/px`, not exactly `2 m/px`.

This may be acceptable, but the comment should say “approximately 2 m/px,” or the extent and mapping should be defined using a clear pixel-center convention.

---

### 4. Trail width semantics should be explicit

```python
wpx = max(1.5, float(r["width"]) / 2.0)
```

This assumes `r["width"]` is the full trail width and that `ImageDraw.line(width=...)` should receive the radius in pixels. However, Pillow’s line width is the full rendered width, not a radius. If `width` is meters, the conversion should be approximately:

```python
wpx = max(1, round(float(r["width"]) / 2.0))
```

because the raster is 2 m/px.

The current code also forces a minimum 2-pixel core:

```python
max(1.5, ...)
round(1.5) == 2
```

That means even a very narrow trail gets a 4 m-wide core. Make this intentional or document it.

---

### 5. Invalid or degenerate routes are not handled

Potential failures include:

- Missing `"points"`
- Fewer than two points
- Missing or nonnumeric `"width"`
- Empty point lists
- NaN/infinite coordinates

Suggested validation:

```python
points = r.get("points", [])
if len(points) < 2:
    continue

try:
    width_m = float(r["width"])
except (KeyError, TypeError, ValueError) as exc:
    raise ValueError(f"Invalid trail width for {r.get('id')!r}") from exc
```

---

### 6. Coordinate bounds are silently clipped

Pillow clips lines outside the image. That can hide bad world data. Consider either:

- rejecting out-of-bounds points, or
- explicitly logging/clamping them.

---

### 7. `Image.composite()` behavior should be documented

```python
mask = Image.composite(core, soft, core)
```

This produces:

- solid core where `core` is nonzero,
- blurred shoulder elsewhere.

That is probably intended, but it does not produce a smooth transition at the edge of the core because the core remains hard 255. A more controllable method is to combine the core and shoulder with `ImageChops.lighter()` or pixel-wise maximum:

```python
from PIL import ImageChops

soft = core.filter(ImageFilter.GaussianBlur(2.5)).point(
    lambda v: int(v * 0.55)
)
mask = ImageChops.lighter(core, soft)
```

This makes the intended “core plus shoulder” behavior explicit.

---

# `geochemistry.py`

### Issues

### 1. Substrate naming is inconsistent

`SYSTEMS` uses:

```python
"siliceous_sinter"
```

but `check_midway_shells()` requires:

```python
"siliceous_sinter_illustrative"
```

This may be intentional, but it creates a fragile hidden contract. A normal shell using `"siliceous_sinter"` will fail validation.

Prefer a canonical value:

```python
MIDWAY_SUBSTRATE = "siliceous_sinter"
```

Then validate against that constant.

If `"siliceous_sinter_illustrative"` is required by the asset schema, define it explicitly and explain why it differs from the system ID.

---

### 2. Input validation is brittle

This can raise `KeyError`:

```python
if s["id"] in MIDWAY_POOLS
```

Use defensive access and validate the input shape:

```python
shell_id = s.get("id")
if shell_id in MIDWAY_POOLS and s.get("substrate") != MIDWAY_SUBSTRATE:
    ...
```

---

### 3. Palette restrictions are incomplete

`forbid_whitening()` only blocks exact palette names:

```python
palette in SYSTEMS["travertine"]["palette"]
```

It does not prevent a caller from using a new travertine-like palette name. If the intent is to enforce mineral systems, accept a system ID rather than a free-form palette string:

```python
def validate_palette(shell_id: str, system_id: str) -> None:
    ...
```

Then verify that the palette belongs to the selected system.

---

### 4. Mutable global structures are returned directly

```python
return {"systems": SYSTEMS, ...}
```

A caller can mutate the module’s global configuration through the return value. Use `copy.deepcopy(SYSTEMS)` or immutable structures.

```python
import copy

return {
    "systems": copy.deepcopy(SYSTEMS),
    ...
}
```

---

### 5. `system_for_feature()` assumes feature names are globally unique

Currently, a feature can only map to one system. That is fine for the current data, but the function should detect duplicate feature assignments during module validation rather than relying on dictionary iteration order.

---

# `grazers.py`

## Critical: `plan_path()` has endpoint-segment bugs

The function checks only:

```python
if blocked(*start):
...
if blocked(*goal):
...
```

But the A* search begins at the **cell center** for `sk`, not at the actual `start`, and ends at the cell center for `gk`, not at the actual `goal`.

At the end:

```python
path[-1] = start
```

This changes the first/last path segment without calling `step_clear()` on it. Therefore, the returned route can cross blocked terrain even when every A* cell-to-cell segment was clear.

### Fix

Validate the start-to-first-cell and last-cell-to-goal segments, or use the actual endpoints as graph nodes.

At minimum:

```python
if sk == gk:
    if step_clear(start, goal):
        return [start, goal]
    raise ValueError("plan_path: start and goal share a blocked cell path")

first = pt(sk)
last = pt(gk)

if not step_clear(start, first):
    raise ValueError("plan_path: start cannot connect to start cell")

if not step_clear(last, goal):
    raise ValueError("plan_path: goal cannot connect to goal cell")
```

The more robust design is to add explicit start and goal nodes to the graph.

---

## Critical: A* heuristic is in the wrong units

Current code:

```python
step = cell_m * (1.4142 if dx and dz else 1.0)
...
h = math.hypot(nx - goal[0], nz - goal[1])
```

`nc` is measured in meters, but `nx` and `nz` are grid indices while `goal` is in world coordinates. The heuristic mixes grid coordinates and world coordinates, making it inconsistent and potentially strongly overestimating.

Use the world position of the current node:

```python
h = math.hypot(nx - goal[0], nz - goal[1])
```

only if `nx` and `nz` are world coordinates. In the current code they are grid keys. Correct version:

```python
world_nxt = pt(nxt)
h = math.hypot(world_nxt[0] - goal[0],
              world_nxt[1] - goal[1])
```

Also use the same exact diagonal cost:

```python
step = math.hypot(dx * cell_m, dz * cell_m)
```

---

## Critical: Start and goal may be outside the search bounds

There is no check that `start` and `goal` lie within `bounds`. Their keys can be outside the valid grid, and the search may fail confusingly.

Add:

```python
for name, xz in (("start", start), ("goal", goal)):
    if not (x0 <= xz[0] <= x1 and z0 <= xz[1] <= z1):
        raise ValueError(f"plan_path: {name} {xz} outside bounds")
```

---

## Critical: Same-cell start and goal returns the wrong path

If `sk == gk`, this code:

```python
path, cur = [goal], gk
...
path[-1] = start
```

returns `[start]`, omitting the goal.

Return `[start, goal]` after validating the direct segment.

---

### Other `plan_path()` improvements

- Validate `cell_m > 0` and `segment_m > 0`.
- Validate finite coordinates.
- Consider using a stale-entry check when popping from the heap:

```python
priority, cur = heapq.heappop(open_h)
if priority > cost[cur] + heuristic(cur):
    continue
```

- Cache `blocked()` results, especially when it is expensive.
- Use a priority tuple with a tie-breaker for deterministic paths.

---

### `segment_samples()` needs validation

```python
def segment_samples(a, b, every_m=2.0):
```

will divide by zero if `every_m <= 0`.

Add:

```python
if every_m <= 0 or not math.isfinite(every_m):
    raise ValueError("every_m must be finite and > 0")
```

---

### `check_routes()` needs malformed-route handling

Potential failures:

```python
pts = [(float(x), float(z)) for x, z in rec["path_xz"]]
```

This can raise on missing, malformed, or 3D points. Decide whether invalid routes should raise or produce an audit failure.

Also, `route_length([])` returns zero, so an empty route currently passes.

---

### `render_tracks()` can crash on partially empty paths

If at least one actor has valid points but another actor has no points, this fails:

```python
pts[0]
```

Filter actors before drawing:

```python
actors = [
    r for r in wildlife
    if r.get("kind") in ("bison", "elk")
    and len(r.get("path_xz", [])) >= 2
]
```

Also create the parent output directory before saving.

---

### Biological model clarity

`update_grazers()` applies the same `HYPOTHESES` list to every actor, including hypotheses marked `not_modeled`. This is useful provenance, but the field name could be clearer:

```python
"model_context": {
    "implemented": ["forage_quality"],
    "not_modeled": ["predation_risk"],
    "partial": ["hydrology"],
}
```

That avoids implying that all listed hypotheses drive the behavior.

---

# `hydro_thermal.py`

## Critical: `step_heat()` overwrites the ledger during substeps

Inside the loop:

```python
ledger = {
    ...
}
```

When `dt` exceeds the stable timestep, earlier substeps are discarded. Consequently, `run_simulation()` accumulates only the final substep’s:

- boundary input,
- lateral input,
- outlet export,
- atmosphere exchange,
- storage values.

The final `closure_residual` can therefore be incorrect even if the numerical update itself is correct.

### Fix

Accumulate ledger quantities across all substeps:

```python
ledger = {
    "units": "m3 * degC (constant rho*cp omitted)",
    "before": initial_storage,
    "after": None,
    "boundary_input": 0.0,
    "lateral_input": 0.0,
    "outlet_export": 0.0,
    "atmosphere_exchange": 0.0,
    "residual": 0.0,
    "dt_seconds": 0.0,
}
```

Then add each substep’s values rather than replacing the dictionary.

The outlet export must also be accumulated using each substep’s old outlet temperature.

---

## Critical: `steady_state()` does not match `step_heat()`

`step_heat()` uses the previous list element:

```python
up_c = float(boundary_c) if i == 0 else old[i - 1]
```

But `steady_state()` uses:

```python
up = float(boundary_c) if not r.get("upstream_id") else temps[r["upstream_id"]]
```

If `upstream_id` is absent, every reach uses the boundary temperature rather than the preceding reach’s temperature. That is inconsistent with the simulation.

For a serial chain, use:

```python
up = float(boundary_c) if i == 0 else temps[state[i - 1]["id"]]
```

If arbitrary topology is intended, then both `derive_flows()` and `step_heat()` need to use the same explicit graph topology. At present, the two models are different.

---

## Critical: empty reaches cause an index error

This line fails for an empty input:

```python
exit_heat = float(state[-1]["flow_m3s"]) * old[-1]
```

Either reject empty reaches:

```python
if not reaches:
    raise ValueError("at least one reach is required")
```

or define empty-system behavior.

---

### Input validation is insufficient

These functions should reject invalid values:

- `boundary_m3s <= 0`
- negative lateral flow
- zero or negative `volume_m3`
- nonpositive `cooling_seconds`
- nonfinite temperatures
- negative `dt`

`run_simulation()` validates boundary flow and time, but `step_heat()` and `stable_dt()` can be called directly with invalid values.

Add shared validation rather than duplicating checks.

---

### `stable_dt()` should validate volume

Current code:

```python
rate = float(r["flow_m3s"]) / float(r["volume_m3"])
```

A zero volume raises `ZeroDivisionError`; a negative volume produces a nonsensical timestep.

```python
volume = float(r["volume_m3"])
if not math.isfinite(volume) or volume <= 0:
    raise ValueError(f"invalid volume for reach {r.get('id')!r}")
```

---

### `step_heat()` has dead state

```python
last_dt = min(dt, stable_dt(state))
...
last_dt = h
```

`last_dt` is never used. Remove it.

---

### `mixing_check()` accepts physically invalid individual flows

This condition:

```python
if q1 + q2 <= 0:
```

allows `q1=-10`, `q2=20`. Reject negative flows explicitly:

```python
if q1 < 0 or q2 < 0:
    raise ValueError("mixing flows must be nonnegative")
if q1 + q2 <= 0:
    raise ValueError("total flow must be > 0")
```

---

### `steady_profile()` needs parameter validation

It can divide by zero here:

```python
... / (RHO_CP * q_m3s)
```

Validate:

```python
if q_m3s <= 0:
    raise ValueError("q_m3s must be > 0")
if he_w_m2k < 0 or width_m < 0:
    raise ValueError("heat-transfer coefficient and width must be >= 0")
```

Also clarify whether `x_m` must be nonnegative and whether it must be sorted.

---

### `render_plume_png()` can divide by zero

```python
(vmax - vmin)
```

must be nonzero. Also validate that:

```python
len(field) == nx * nz
```

and that `nx` and `nz` are positive integers.

---

### `plume_field()` should validate dimensions and parameters

Negative or zero `nx`, `nz`, `extent_m`, or `sigma_m` should fail early with a clear error rather than relying on `solve_steady()`.

---

## Recommended tests

### `gen_trail_mask.py`

- Creates missing output directories.
- Empty route list.
- One-point route.
- Narrow trail width.
- Out-of-bounds coordinates.
- Correct output mode, size, and nonzero pixel count.
- Expected shoulder intensity around a core pixel.

### `geochemistry.py`

- Every known feature maps to the intended system.
- Unknown features raise `SubstrateError`.
- Midway shells accept the canonical siliceous substrate.
- Travertine palettes are rejected for every Midway pool.
- `rules_doc()` cannot mutate global `SYSTEMS`.

### `grazers.py`

- `segment_samples()` rejects zero spacing.
- Routes crossing an apron between waypoints are rejected.
- Start and goal segments in `plan_path()` cannot cross blocked terrain.
- Start and goal outside bounds fail clearly.
- Same-cell start/goal returns both endpoints.
- A* returns the shortest path on a simple obstacle grid.
- Empty actor paths do not crash rendering.

### `hydro_thermal.py`

- `steady_state()` matches a long simulation for a serial chain.
- `step_heat()` ledger remains correct when substepping occurs.
- Closure residual is near zero.
- Empty reaches fail clearly.
- Zero-volume reaches fail clearly.
- Negative flows fail clearly.
- `render_plume_png()` rejects invalid field dimensions and equal color bounds.

## Priority order

1. Fix `step_heat()` ledger accumulation.
2. Fix `steady_state()` upstream behavior.
3. Fix A* endpoint validation and heuristic units.
4. Add shared input validation.
5. Fix output directory/import-note behavior.
6. Add regression tests for conservation, routing, and raster output.