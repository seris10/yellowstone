## Audit summary

The code is generally well-structured and has good provenance/error-reporting intent, but there are several correctness issues that can produce stale data, misleading metrics, or non-reproducible results. The highest-priority fixes are:

1. **Prevent stale/duplicate replay records in `analysis_store.py`.**
2. **Fix non-divisible timestep handling in `aquatic_foodweb.py`.**
3. **Fix hard-coded/unsafe assumptions in `build.py`, especially `river_state[2]`.**
4. **Harden configuration validation against `NaN`, infinities, booleans, and disabled modules.**
5. **Make canopy coordinate conversion use the actual image dimensions.**
6. **Validate census-review inputs and tolerance values.**

---

# 1. `analysis_store.py`

## High-priority findings

### A. Replay ingestion leaves stale frames

`ingest_replay()` uses:

```python
INSERT OR REPLACE INTO replay_cells
```

but frames use:

```python
INSERT INTO replay_frames
```

If the same cell IDs are ingested more than once, old frames remain. If a replay document contains a replacement dataset, the store can contain:

- frames for cells no longer present,
- duplicate `(t_s, cell_id)` records,
- inflated query results.

The table has no uniqueness constraint to prevent this.

### Fix

Either clear both replay tables before ingestion:

```python
con.execute("DELETE FROM replay_frames")
con.execute("DELETE FROM replay_cells")
```

or add a uniqueness constraint and replace frames:

```sql
CREATE TABLE replay_frames(
  t_s REAL NOT NULL,
  cell_id TEXT NOT NULL,
  temperature_c REAL NOT NULL,
  PRIMARY KEY (t_s, cell_id)
);
```

Then:

```python
INSERT OR REPLACE INTO replay_frames VALUES (?, ?, ?)
```

Prefer a savepoint/transaction so a failed frame validation does not leave a partially ingested replay.

---

### B. Census return count can disagree with final row count

Duplicate `stable_id` values in one input document are silently replaced:

```python
INSERT OR REPLACE INTO census_trees
```

but `n` is incremented for every input record. The returned count can therefore be greater than:

```sql
SELECT COUNT(*) FROM census_trees
```

This is especially misleading in the `meta.notes` build summary.

### Fix

Reject duplicates explicitly:

```python
seen = set()

for i, t in enumerate(trees):
    sid = str(t["stable_id"])
    if sid in seen:
        raise ValueError(f"duplicate census stable_id: {sid}")
    seen.add(sid)
```

Alternatively return the final table count instead of the input count.

---

### C. Ingestion does not reject non-finite numeric values

Many values are converted with `float()` but never checked with `math.isfinite()`:

```python
x, z = float(t["x"]), float(t["z"])
```

This permits `NaN` and infinity to reach SQLite or downstream queries. SQLite adapters may turn `NaN` into `NULL`, causing confusing constraint failures or silent data corruption.

This affects:

- census coordinates and crown sizes,
- replay cells and frames,
- USGS observations,
- SNOTEL values,
- fit artifacts.

### Fix

Use a common helper:

```python
def _finite_float(name: str, value, *, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not boolean")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result
```

---

### D. Store claims to be read-only, but does not enforce read-only access

The query layer avoids accepting raw SQL, which is good, but `_open()` opens ordinary writable SQLite connections:

```python
return sqlite3.connect(str(p))
```

The returned connection is not configured with `PRAGMA query_only=ON`.

The current query implementation itself does not write, but the stated read-only contract is not enforced.

### Fix

For path-based reads:

```python
def _open(con_or_path):
    if isinstance(con_or_path, sqlite3.Connection):
        return con_or_path

    p = Path(con_or_path)
    if not p.exists():
        raise FileNotFoundError(...)

    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.execute("PRAGMA query_only = ON")
    return con
```

For caller-supplied connections, either document that the caller owns mutability or reject connections that are not query-only.

---

### E. Query results are not deterministic

Queries have no `ORDER BY`. SQLite may return rows in different orders depending on indexes, query plans, or SQLite versions.

This makes API responses and tests unstable.

### Fix

Add a deterministic order per table, for example:

```python
ORDER BY rowid
```

or explicit logical keys:

```python
ORDER BY cell_id, t_s
```

For the R-tree query, use:

```sql
ORDER BY t.stable_id
```

before `LIMIT/OFFSET`.

---

### F. SNOTEL dates are only lexically compared

`obs_snotel.day` is stored as `TEXT`, and filters compare strings. This is safe only if every date is strictly normalized to ISO `YYYY-MM-DD`.

### Fix

Validate on ingestion:

```python
datetime.date.fromisoformat(day)
```

and reject non-ISO or invalid dates.

---

### G. Atomic output handling is incomplete

`build_file()` writes to a temporary path, but:

- stale temp files are deleted without checking ownership,
- cleanup is not guaranteed if `con.backup()` or `tmp.replace()` fails,
- there is no filesystem sync before replacement,
- concurrent builders can race after the initial `out.exists()` check.

This may be acceptable for a local pipeline, but the docstring says “Atomic write.”

### Improvement

Use a unique temporary file in the destination directory and clean it in `finally`. Consider `os.replace()` and, for stronger durability, `fsync()`.

---

# 2. `aquatic_foodweb.py`

## High-priority findings

### A. Requested duration is not necessarily simulated duration

The code calculates:

```python
steps = max(1, int(round(days / dt_days)))
```

For example:

- `days=10`, `dt_days=3`
- `steps=3`
- simulated time = 9 days
- reported time = 10 days

For:

- `days=1`, `dt_days=2`
- `steps=1`
- simulated time = 2 days
- reported time = 1 day

This affects emergence, turnover, consumption, and all reported per-day metrics.

### Fix

Use partial final steps:

```python
remaining_days = float(days)
while remaining_days > 1e-12:
    step_days = min(dt_days, remaining_days)
    dt_s = step_days * 86400.0
    eat_substeps = max(1, int(math.ceil(step_days * 24.0)))
    eat_dt_h = step_days * 24.0 / eat_substeps

    # run one step using step_days and dt_s

    remaining_days -= step_days
```

Also report `steps` and `simulated_days`.

---

### B. `thermal_landscape()` lacks structural validation

This line can raise an opaque `IndexError`:

```python
frame["temperature_c"][i]
```

There is no validation that:

- every frame has `t_s`,
- every frame has a temperature list,
- temperature length equals cell count,
- temperatures are finite,
- cells have IDs,
- the selected window has valid numeric bounds.

### Fix

Validate before processing:

```python
for fi, frame in enumerate(frames):
    if "t_s" not in frame or "temperature_c" not in frame:
        raise ValueError(f"frame {fi} missing required fields")

    temps = frame["temperature_c"]
    if not isinstance(temps, list) or len(temps) != len(cells):
        raise ValueError(
            f"frame {fi}: expected {len(cells)} temperatures")

    if not all(math.isfinite(float(v)) for v in temps):
        raise ValueError(f"frame {fi}: non-finite temperature")
```

Also validate `t_min_s <= t_max_s`.

---

### C. `run_foodweb()` does not validate all model inputs

These values can be `NaN`, infinity, or invalid types:

```python
days
dt_days
cover
ne_turnover_days
```

The checks:

```python
if days <= 0 or dt_days <= 0:
```

do not reject `NaN`, because comparisons with `NaN` are false.

### Fix

Use a finite-number validator and validate `cover` explicitly:

```python
def _positive_finite(name, value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and > 0")
    return value

days = _positive_finite("days", days)
dt_days = _positive_finite("dt_days", dt_days)
ne_turnover_days = _positive_finite(
    "ne_turnover_days", ne_turnover_days)

cover = float(cover)
if not math.isfinite(cover) or not 0 <= cover <= 1:
    raise ValueError("cover must be finite and in [0, 1]")
```

---

### D. Consumption occurs only at the selected refuge cell

The model initializes prey in every cell but consumes prey only from:

```python
state[idx]
```

This may be intentional, but it should be clearly represented as a model assumption because it can create unrealistic accumulation in non-selected cells. The output says:

```text
single trout, single dipper
```

but the biological interpretation should explicitly state:

- whether prey are local and inaccessible across cells,
- whether the trout changes cells without movement cost,
- whether prey in abandoned cells continue growing indefinitely.

### Improvement

Add provenance fields such as:

```python
"foraging_scope": "selected_cell_only",
"movement_cost": "not modeled",
"unvisited_prey": "continues local dynamics"
```

---

### E. Food normalization makes absolute starvation impossible

The code intentionally does:

```python
ceiling = max(foods) or 1.0
u = suitability(food / ceiling, ...)
```

This means the food-richness term is relative to the best cell, not an absolute food availability measure. A landscape with nearly zero food can still produce a high-ranking refuge.

The limitation is documented, but this is important enough to expose in the output and perhaps provide an optional absolute-food mode.

---

### F. `compare_runs()` does not validate compatible landscapes

It assumes the control and pulse documents have equivalent cell ordering. Since `thermal_landscape()` indexes temperatures by cell position, a reordered cell list can silently compare different spatial cells.

### Fix

Check IDs and order:

```python
control_ids = [c["id"] for c in control_land]
pulse_ids = [c["id"] for c in pulse_land]

if control_ids != pulse_ids:
    raise ValueError("control and pulse landscapes have different cell ordering")
```

---

# 3. `build.py`

## High-priority findings

### A. Unsafe hard-coded `river_state[2]`

In `render_all()`:

```python
field = plume_field(
    nx=128,
    nz=128,
    hot_c=float(exc["temperature_c"]),
    river_c=float(river_state[2]["temperature_c"]),
)
```

This assumes:

- there are at least three reaches,
- index 2 is the intended river reference,
- the reach order never changes.

This can cause an `IndexError` or silently use the wrong temperature.

### Fix

Use an authored ID or a validated fallback:

```python
river_ref = next(
    (r for r in river_state if r["id"] == REACH_BRIDGE),
    river_state[-1],
)
field = plume_field(
    nx=128,
    nz=128,
    hot_c=float(exc["temperature_c"]),
    river_c=float(river_ref["temperature_c"]),
)
```

If the intended reach is not `REACH_BRIDGE`, introduce a dedicated constant such as `REACH_PLUME_REFERENCE`.

---

### B. Tributary attachment silently ignores unknown names

Both `_prepare_replay_ecosystem()` and `simulate_all()` do:

```python
t = tribs.get(n, {})
if t.get("flow_m3s", 0.0) > 0:
```

A typo in a tributary name simply results in no attachment.

This contradicts the comment:

```text
named lookups fail loudly
```

### Fix

```python
if n not in tribs:
    raise ValueError(f"unknown tributary {n!r}; have {sorted(tribs)}")
t = tribs[n]
```

Also validate that every configured attachment is a list of names.

---

### C. Configuration validation is vulnerable to `NaN` and infinity

Many checks look like:

```python
if float(value) <= 0:
```

For `NaN`, this is false, so invalid configuration passes validation.

Examples include:

- hydro boundary values,
- replay duration,
- Manning `n`,
- overland parameters,
- weather values,
- snow values.

### Fix

Introduce:

```python
def _finite(name, value):
    if isinstance(value, bool):
        raise ValueError(f"{name} must not be boolean")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result
```

Use it for every numeric configuration field.

---

### D. Disabled overland flow still requires positive parameters

When `overland.enabled` is false, validation still uses defaults:

```python
float(olfg.get("dt_s", 0.0)) <= 0
float(olfg.get("grid", 0)) <= 0
```

Therefore an omitted or minimal disabled overland configuration fails validation.

### Fix

Only validate operational parameters when enabled:

```python
olfg = cfg.get("overland", {})
if olfg.get("enabled", False):
    if float(olfg.get("dt_s", 60.0)) <= 0:
        raise ValueError(...)
    ...
```

Provide meaningful defaults such as those used by `simulate_all()`.

---

### E. Baseline data may be mutated through shallow references

This line aliases baseline patch records:

```python
patches0 = baseline["patches"]
```

If `patch_step()` or later functions mutate patch dictionaries, the supposedly frozen baseline is modified in memory. This can affect subsequent calculations or repeated calls to `simulate_all()`.

### Fix

```python
patches0 = copy.deepcopy(baseline["patches"])
```

Likewise consider defensive copies for other structures passed to functions that may mutate them.

---

### F. Foodweb settings are hard-coded

The build uses:

```python
aquatic_foodweb = run_aquatic_foodweb(
    thermal_landscape(replay_doc),
    days=14.0,
    trout_species=foodweb_species,
    cover=foodweb_cover,
)
```

There is no configuration for:

- foodweb duration,
- timestep,
- turnover,
- shear threshold,
- tributary pockets,
- food scaling.

This makes the artifact less reproducible from configuration and causes the manifest’s parameter set to omit meaningful model inputs.

### Fix

Add a `foodweb` configuration block and include it in `parameter_set`.

---

### G. Build output directories can be reused silently

`main()` does:

```python
out.mkdir(parents=True, exist_ok=True)
```

and then overwrites many files under the same build ID. This is inconsistent with `analysis_store.build_file()`, which refuses to overwrite existing derived artifacts.

### Improvement

Either:

- refuse if the build directory already contains a completed build, or
- write to a temporary build directory and atomically rename it,
- or explicitly support `--force`.

---

### H. Several output writes are not atomic

Examples:

```python
(out / "ecosystem.godot.json").write_text(...)
(out / "river_state.json").write_text(...)
(out / "weather.json").write_text(...)
```

A crash can leave a partially written artifact while `CHECKS.json` or `BUILD.json` may still exist from a prior run.

### Fix

Use a shared atomic JSON writer:

```python
def write_json_atomic(path: Path, obj) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
```

---

### I. `load_config()` does not validate YAML shape

`yaml.safe_load()` can return `None`, a list, or a scalar. Later code assumes a mapping.

### Fix

```python
cfg = yaml.safe_load(...)
if not isinstance(cfg, dict):
    raise ValueError("configuration root must be a mapping")
return cfg
```

---

# 4. `canopy_census.py`

## High-priority findings

### A. Coordinate conversion assumes a 2048×2048 image

`to_world()` uses:

```python
x = (r["ix"] + 0.5) / size * (2 * DETAIL_HALF) - DETAIL_HALF
```

with default `size=2048`, even though `load_detail()` accepts arbitrary image sizes. `render_overlay()` and validation also assume 2048.

For a resized, cropped, or differently dimensioned input image, coordinates and stable IDs become incorrect.

### Fix

Pass the actual dimensions:

```python
def to_world(records, width, height):
    ...
    x = (r["ix"] + 0.5) / width * (2 * DETAIL_HALF) - DETAIL_HALF
    z = (r["iz"] + 0.5) / height * (2 * DETAIL_HALF) - DETAIL_HALF
```

Use:

```python
h, w = rgb.shape[:2]
records = to_world(detect(rgb), width=w, height=h)
```

Better still, derive the spatial extent from image metadata rather than hard-coding `DETAIL_HALF`.

---

### B. `qa_census()` is too weak and can crash on malformed values

It does not check:

- numeric finiteness,
- nonnegative crown radius,
- coordinate bounds,
- duplicate stable IDs,
- duplicate coordinates,
- `peak_exg` range,
- `n` type,
- density area validity,
- missing `trees` list type.

For malformed input such as a string crown radius, this line can raise instead of returning a QA failure:

```python
if not (t["crown_r_m"] <= QA_CROWN_CAP_M):
```

### Fix

Make QA defensive:

```python
def finite_number(name, value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(value)
```

Validate every field and collect failures instead of throwing.

---

### C. `density_stats()` silently treats unknown zone kinds as boxes

This code:

```python
else:
    x0, z0, x1, z1 = val
```

means a typo such as `"circl"` is interpreted as a box and may produce misleading results.

### Fix

```python
elif kind == "box":
    ...
else:
    raise ValueError(f"unknown zone type: {kind}")
```

Also reject:

- zero or negative circle radius,
- `r1 <= r0`,
- zero-area boxes.

---

### D. Pool-ring exclusion only checks distance to vertices outside the polygon

For points outside a polygon, the nearest point on the boundary may be along an edge, not at a vertex. The current margin test:

```python
min((x - vx) ** 2 + (z - vz) ** 2 for vx, vz in ring)
```

can fail to exclude points close to the middle of a long edge.

### Fix

Compute point-to-segment distance for every ring edge, or use a geometry library if available.

---

### E. `load_pool_rings()` leaves file handles unmanaged

```python
world = json.load(open(world_path))
```

Use:

```python
with open(world_path, encoding="utf-8") as f:
    world = json.load(f)
```

---

### F. Detection thresholds are duplicated

`detect_v2()` repeats:

```python
sig["exg"] > 0.05
sig["light"] < 0.55
```

instead of reusing the configurable `detect()` thresholds. This means changing `detect()` defaults does not update v2 behavior.

### Fix

Centralize crown-mask construction:

```python
def crown_mask(sig, exg_min, crown_dark_max):
    return (
        (sig["exg"] > exg_min)
        & (sig["light"] < crown_dark_max)
        & (~sig["water"])
    )
```

---

# 5. `census_validate.py`

## High-priority findings

### A. Validation hard-codes image dimensions and spatial extent

Both sampling and evaluation use:

```python
640.0
1280.0
W = H = 2048
```

This duplicates assumptions from the detector and ignores the actual image size and the census document’s source metadata.

### Fix

Load image dimensions once and use the census source extent:

```python
source = census.get("source", {})
x0, z0, x1, z1 = source["extent_m"]
```

Then transform pixel/world coordinates consistently.

---

### B. Tolerances are not validated

`_hungarian()` divides by `tol`:

```python
d / tol
```

A tolerance of zero creates `NaN` or division errors. Negative tolerances are also accepted by the CLI.

### Fix

In `cmd_evaluate()`:

```python
if not args.tolerances or any(
    not math.isfinite(t) or t <= 0 for t in args.tolerances
):
    raise SystemExit("tolerances must be finite and > 0")
```

Also reject duplicate tolerances.

---

### C. Sampling arguments are not validated

These can fail obscurely:

- `--plots 0`
- `--plots` greater than population size
- `--cell-px 0`
- negative seeds are probably okay, but should be explicit.

### Fix

Validate before `rng.choice()`:

```python
if args.cell_px <= 0:
    raise SystemExit("--cell-px must be > 0")
if not 1 <= args.plots <= len(frame):
    raise SystemExit("--plots must be within the frame population")
```

---

### D. Review completion relies on mutable `reference_count`

Evaluation checks:

```python
if any(p["reference_count"] == "" for p in sample):
```

but `reference_count` is stored in `sample.json` and can become stale or be edited independently of `reference_points.json`.

A plot can be marked complete while having no reference records.

### Fix

Treat `reference_points.json` as the source of truth and verify every sampled plot has an explicit submission marker, including zero-point plots.

For example, maintain:

```json
{
  "plot_id": "P0001",
  "submitted": true,
  "points": []
}
```

rather than inferring completion from a count.

---

### E. Web annotator accepts malformed or non-finite coordinates

The POST handler directly unpacks submitted points:

```python
for i, (x, y, *rest) in enumerate(_pts, 1)
```

There is no validation that:

- the point is a list of two or three values,
- coordinates are finite,
- coordinates lie inside the crop,
- the class value is valid,
- `plot_id` belongs to the current sample.

### Fix

Validate request payloads and return HTTP 400 for malformed input. Also clamp or reject out-of-crop coordinates.

---

### F. Web crop endpoint allows path traversal

The endpoint constructs a path using a URL-provided ID:

```python
VDIR / "blind_crops" / f"{pid}.png"
```

A request containing traversal components could access unintended files.

### Fix

Only serve IDs from the frozen sample:

```python
if pid not in by_id:
    return self.send_error(404)
```

Then resolve and verify the path remains under `blind_crops`.

---

### G. The “fixed before results” tolerance claim is not enforced

The report says:

```python
"main_tolerance_basis": "... fixed before results"
```

but the CLI allows arbitrary tolerances after review.

This is a provenance issue, not just a code issue.

### Fix

Store tolerances in `sampling_plan.json` before annotation, and evaluate using those frozen values. If custom tolerances are allowed, report them as exploratory rather than as the pre-registered main tolerance.

---

### H. Freeze manifest lacks important inputs

The manifest hashes:

- census,
- detail image,
- Python code.

It does not hash:

- detector parameters,
- package versions,
- world pool geometry used by exclusion,
- validation script specifically,
- image dimensions/spatial metadata.

For reproducibility, include detector configuration and relevant data files.

---

# Suggested test additions

## `analysis_store.py`

- ingest the same replay twice and assert frame count is unchanged;
- duplicate census IDs must fail;
- `NaN` and infinity must fail;
- query results are ordered deterministically;
- path-based queries cannot modify the database.

## `aquatic_foodweb.py`

- `days=10, dt_days=3` simulates exactly 10 days;
- `days=1, dt_days=2` does not simulate two days;
- malformed frame lengths fail with `ValueError`;
- control/pulse cell order mismatch fails;
- zero/negative/NaN tolerances and inputs fail.

## `build.py`

- unknown tributary names fail;
- disabled overland flow validates successfully with no overland block;
- fewer than three reaches still renders successfully;
- repeated `simulate_all()` calls do not mutate the baseline;
- existing completed output is not silently overwritten.

## `canopy_census.py`

- non-2048 image coordinate conversion;
- malformed census QA never crashes;
- invalid density zone types fail;
- points near polygon edges are correctly excluded;
- duplicate stable IDs are rejected.

## `census_validate.py`

- sample size and cell size validation;
- zero tolerance rejection;
- malformed annotation payload rejection;
- explicit zero-tree plot submission;
- path traversal rejection;
- frozen tolerance enforcement.

---

## Recommended implementation order

1. Fix replay replacement/uniqueness and transaction boundaries.
2. Fix foodweb timestep integration.
3. Replace `river_state[2]` with an ID-based lookup.
4. Add shared finite-number validation to build and ingestion paths.
5. Fix canopy/validation coordinate transforms to use actual image metadata.
6. Harden validation annotation and completion state.
7. Add atomic output helpers and overwrite protection.
8. Add the regression tests above.