# fixes-26: analysis store SQLite build, query, and history integrity

Scope: files audited, with sha256 first 12 from `shasum -a 256`.

- `yellowstone_python/analysis_store.py` 9381f52493a8
- `tools/build_store.py` 19f2c7e150a0
- `yellowstone_python/llm_backend.py` 394606ae552f (store sections only: imports and `Backend.store_path/query_store/density` around lines 35-37, 101-167, 494-521, 674-740)
- `tests/test_analysis_store.py` 9bec034b92a0
- `notebooks/census_explorer.ipynb` (cells reading the store)
- `derived/analysis_574c6165b5e9.sqlite` c822260fe441 (opened READ-ONLY, PRAGMA query_only=ON)
- `derived/analysis_d2a52e498b51.sqlite` 11dcba2a305f (opened READ-ONLY, PRAGMA query_only=ON)

Callers read: `tools/build_store.py` (CLI), `yellowstone_python/llm_backend.py`
(`store_path`, `query_store`, `density`, `/api/query`, `/api/density`),
`notebooks/census_explorer.ipynb` (sqlite3 direct), `tools/execute_notebook.py`
(by indirection in `test_notebook_executes_on_synthetic_store`). The build
pipeline `yellowstone_python/build.py` does NOT call the store; the store is
built after each `python3 -m yellowstone_python.build` by a separate CLI, so
nothing in the build pipeline reconciles a newer build dir against a stale
store file.

## Main problems

### 1. The failing test shows `ingest_census` cannot replace a duplicate, and the replace path is dead code

`tests/test_analysis_store.py:369-386`
(`test_duplicate_stable_id_leaves_no_stale_rtree`) feeds two rows with
`stable_id="dup"` and expects the second to replace the first (one row in
`census_trees`, one in `census_rtree`, located at the second coordinate).

`yellowstone_python/analysis_store.py:143-159`:

```python
    seen = set()
    n = 0
    for i, t in enumerate(trees):
        sid = str(t.get("stable_id", f"missing_{i}"))
        ...
        sid = str(t["stable_id"])
        if sid in seen:
            raise ValueError(f"duplicate census stable_id: {sid}")
        seen.add(sid)
```

The `seen` check raises before line 161 can run, so the `INSERT OR REPLACE`
plus R-tree-row cleanup block at lines 161-174 is unreachable. The test
exercises exactly that unreachable path. Current pytest output: 17 passed,
1 failed on this test.

Two consistent fixes exist. The test documents the intended contract
(replace, idempotent). Either reconcile the code to the test (recommended,
since replace-on-reingest is useful for incremental builds), or reconcile
the test to the code (reject duplicates loudly). Pick one; shipping both as
contradictions is the current state.

### Fix

Replace the `seen` guard with a count of occurrences, keep the
`DELETE FROM census_rtree WHERE tree_row=?` cleanup, and let
`INSERT OR REPLACE` do the row-level replacement.

```python
def ingest_census(con, doc):
    trees = doc.get("trees")
    if not isinstance(trees, list):
        raise ValueError("census doc: 'trees' must be a list")
    n = 0
    for i, t in enumerate(trees):
        for k in ("stable_id", "x", "z", "crown_r_m",
                  "confidence", "peak_exg"):
            if k not in t:
                raise ValueError(f"census tree #{i}: missing key {k!r}")
        if t["confidence"] not in CONFIDENCES:
            raise ValueError(
                f"census tree #{i}: bad confidence {t['confidence']!r}")
        sid = str(t["stable_id"])
        x = _finite_float(f"census tree #{i} x", t["x"])
        z = _finite_float(f"census tree #{i} z", t["z"])
        crown_r = _finite_float(f"census tree #{i} crown_r_m", t["crown_r_m"])
        peak_exg = _finite_float(f"census tree #{i} peak_exg", t["peak_exg"])
        old = con.execute(
            "SELECT rowid FROM census_trees WHERE stable_id=?",
            (sid,)).fetchone()
        if old is not None:
            con.execute("DELETE FROM census_rtree WHERE tree_row=?",
                        (old[0],))
        row = con.execute(
            "INSERT OR REPLACE INTO census_trees VALUES (?,?,?,?,?,?,?)",
            (sid, x, z, crown_r, t["confidence"], peak_exg,
             str(t.get("evidence_class", "")))).lastrowid
        con.execute(
            "INSERT INTO census_rtree VALUES (?,?,?,?,?)",
            (row, x, x, z, z))
        n += 1
    return n
```

Notes on correctness:

- `INSERT OR REPLACE` on a `PRIMARY KEY TEXT` conflict performs a
  DELETE+INSERT, which can assign a new integer rowid. The explicit
  `DELETE FROM census_rtree WHERE tree_row=?` on the OLD rowid runs
  before the replace. The R-tree row for the new rowid is then
  inserted. The current code's use of `INSERT OR REPLACE INTO
  census_rtree` was defensive but masked no observable bug once the
  prior DELETE is in place; prefer the plain `INSERT`.
- `ingest_replay` already clears its tables with `DELETE FROM
  replay_frames` and `DELETE FROM replay_cells` (lines 183-184).
  Mirroring that pattern inside `ingest_census` would also work, but is
  overkill when the operator wants a true merge.

### Test

`tests/test_analysis_store.py::test_duplicate_stable_id_leaves_no_stale_rtree`
is the regression test; it passes once the fix lands. Add a second test
that reingests the same tree three times with changing coordinates and
verifies `SELECT COUNT(*) FROM census_rtree`
`WHERE tree_row NOT IN (SELECT rowid FROM census_trees)` returns 0.

---

### 2. Both built stores are stale: four of six source files no longer resolve, and the newest build dir is not represented

READ-ONLY inspection of the two store files (opened with
`sqlite3.connect("file:...?mode=ro", uri=True)` and
`PRAGMA query_only=ON`):

| store | build_id | created_utc |
| --- | --- | --- |
| `derived/analysis_574c6165b5e9.sqlite` | `574c6165b5e9` | `2026-10-10T07:02:01` |
| `derived/analysis_d2a52e498b51.sqlite` | `d2a52e498b51` | `2026-10-10T07:04:22` |

Each `meta.source_shas` record names six source paths. Current state:

| recorded path | resolves today? |
| --- | --- |
| `derived/<build_id>/river_replay.json` | SAME (sha unchanged) |
| `derived/census.json` | SAME (sha unchanged) |
| `derived/firehole_obs_2026-10-09.json` | MISSING |
| `derived/snotel_obs_2026-10-10.json` | MISSING |
| `derived/reach_fit_V300000_2026-10-09.json` | MISSING |
| `derived/snow_snotel_fit_2026-10-10.json` | MISSING |

The four missing paths are date-stamped names. The current repo uses
date-free names: `derived/firehole_obs.json`, `derived/snotel_obs.json`,
`derived/reach_heat_fit_v300k.json`, `derived/snow_degree_day_fit.json`.
AGENTS.md section 3 forbids date-stamped filenames in `*.py`, `configs/`,
`tests/`, `notebooks/`, or `tools/` defaults. `tools/build_store.py`
defaults are now date-free, consistent with that rule, but the stored
`source_shas` prove the stores were built against a different filename
set. Nothing in the current tree can rebuild or re-verify them.

Separately, both stores are stale relative to the current `derived/`
tree. The newest build dir by mtime is `261e10030b24` (mtime
2026-10-12 17:22), and neither store's build_id is among the five most
recent. The newest sqlite file by mtime is
`analysis_d2a52e498b51.sqlite` (2026-10-10 23:06), which
`Backend.store_path` returns to `/api/query` and `/api/density` (see
`llm_backend.py:127-136`). `/api/build/latest`
(`llm_backend.py:503-521`) is independent of the store and selects the
newest `*/CHECKS.json`, so a client that calls both endpoints receives
a build_id of `261e10030b24` from `/api/build/latest` and store rows
tagged `d2a52e498b51` from `/api/query`. The two cannot be joined.

### Fix

The stores themselves are history and are never mutated. Fixes land in
the build and serve layers:

1. In `analysis_store.build_file`, write the resolved absolute path AND
   a path relative to the build dir, not `str(p)` which can mix cwd and
   intent:

   ```python
   shas = {
       f"derived/{build_dir.name}/river_replay.json":
           _sha256(replay_path),
       "derived/census.json": _sha256(census_path),
       # ...
   }
   ```

   Also record each source file's basename plus its sha and its size,
   so a renamed-but-identical file can still be verified:

   ```python
   {"path": "derived/firehole_obs.json",
    "basename": "firehole_obs.json",
    "sha256": "...",
    "bytes": 123456}
   ```

2. In `Backend.store_path` (`llm_backend.py:119-136`), prefer the store
   whose `meta.build_id` matches the newest `derived/*/CHECKS.json` over
   the newest `analysis_*.sqlite` by mtime. If no such match exists,
   return `None` and let `/api/query` 503, instead of silently serving
   mismatched rows:

   ```python
   def store_path(self):
       if self._store is not None:
           return self._store if self._store.exists() else None
       latest_build = self._latest_build_id()  # from CHECKS.json
       if latest_build is None:
           return None
       cand = self.derived / f"analysis_{latest_build}.sqlite"
       return cand if cand.exists() else None
   ```

3. Add `tools/audit_provenance.py --audit-stores` (or extend it) to
   enumerate every `derived/analysis_*.sqlite`, read `meta.source_shas`
   READ-ONLY, and emit `OK` / `STALE_SOURCE` / `MISSING_BUILD_DIR` /
   `UNKNOWN_PATH` per store. Both current stores would report four
   `UNKNOWN_PATH` findings and `STALE_SOURCE` for the current latest
   build dir.

### Test

- `test_store_path_prefers_build_id_match`: build two synthetic stores
  under `tmp_path` with build_ids `aaa` and `bbb`, write a
  `CHECKS.json` under `bbb/`, assert `Backend(derived=tmp_path).store_path()`
  returns the `bbb` store even when the `aaa` sqlite has a newer mtime.
- `test_store_path_returns_none_when_latest_build_has_no_store`.
- `test_audit_stores_flags_unknown_source_path`.

---

### 3. Store file was mutated after build: `analysis_d2a52e498b51.sqlite` contains six tables the schema never defines

READ-ONLY inspection of `analysis_d2a52e498b51.sqlite` lists these tables
in `sqlite_master` that `_SCHEMA` in `analysis_store.py:68-113` does not
create:

```
research_sources
simulation_modules
species_ecology
species_interactions
species_taxa
sqlite_sequence
```

Row counts for all six are 0. `species_ecology`, `species_interactions`,
and `species_taxa` match the schemas of same-named tables in the
operator-local memory store (same column names and FOREIGN KEY/CHECK
clauses when queried READ-ONLY via that store). The `sqlite_sequence`
table is created automatically by SQLite the first time an
`AUTOINCREMENT` column is defined; its presence here is diagnostic of a
`CREATE TABLE ... AUTOINCREMENT` executed against the file. The paired
store `analysis_574c6165b5e9.sqlite` has NONE of these tables.

A store "mutated after build" is a violation of the invariant at
`tools/build_store.py:3-5` ("derived artifacts are history: the default
output is a NEW file per build, never an overwrite of an existing
store") and of AGENTS.md section 4 ("stores are history: never
overwrite, never mutate"). The empty tables are not themselves harmful,
but they prove the file was opened for write at least once after
`backup()` closed.

### Fix

1. Mark the store read-only on disk at the end of `build_file` (after
   the atomic replace at `analysis_store.py:385`):

   ```python
   import os, stat
   mode = out.stat().st_mode
   out.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
   ```

   The build still writes atomically because the chmod runs on the
   final path, not the `.tmp`.

2. Change every open of a store file to use the read-only URI form
   and `PRAGMA query_only=ON`. `analysis_store._open` already does
   this (lines 456-466). `notebooks/census_explorer.ipynb` does NOT:

   ```python
   # notebooks/census_explorer.ipynb (cell 1):
   con = sqlite3.connect(str(STORE))
   ```

   Replace with:

   ```python
   con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
   con.execute("PRAGMA query_only = ON")
   ```

3. In `audit_provenance.py --audit-stores`, warn when
   `sqlite_master` contains any name not in a known allow-list:

   ```python
   KNOWN = {
       "census_trees", "census_rtree", "census_rtree_node",
       "census_rtree_parent", "census_rtree_rowid",
       "replay_cells", "replay_frames", "obs_usgs", "obs_snotel",
       "fits_reach", "fits_reach_nulls", "fits_snow", "meta",
   }
   ```

### Test

- `test_build_file_sets_readonly_bit`: after `build_file`, assert
  `not (out.stat().st_mode & stat.S_IWUSR)`.
- `test_notebook_opens_store_readonly`: parse the notebook cells,
  assert every `sqlite3.connect(` string also contains
  `"?mode=ro"` or `uri=True` with `mode=ro`.
- `test_audit_stores_flags_unknown_table`: build an in-memory store,
  `CREATE TABLE junk(x INT)`, back it up to disk, run the audit,
  assert the finding fires.

---

### 4. `ingest_firehole` silently drops any epoch that is not comparable with `set | set`, and discards duplicates at the same epoch

`analysis_store.py:221-231`:

```python
def ingest_firehole(con, doc):
    n = 0
    for site, rec in doc.get("sites", {}).items():
        series = rec.get("series", {})
        q = {e: v for e, v in series.get("discharge_m3_s", [])}
        t = {e: v for e, v in series.get("temperature_c", [])}
        for epoch in sorted(set(q) | set(t)):
            con.execute("INSERT INTO obs_usgs VALUES (?,?,?,?)",
                        (site, float(epoch), q.get(epoch), t.get(epoch)))
            n += 1
    return n
```

Problems:

- No type check on `series.get(...)`: a top-level JSON that is not a
  list of `[epoch, value]` pairs raises `TypeError` deep in the dict
  comprehension (ingest crashes rather than reporting the shape).
- A duplicate epoch inside the same series silently keeps the last
  pair encountered (dict overwrite). USGS NWIS 15-minute series
  routinely contain repeated timestamps across QC passes; losing one
  of two divergent values without a note destroys information the
  firehole-fit downstream reads.
- `float(epoch)` with no `isfinite` check lets NaN or inf through.
- `obs_usgs` has an index `(site, epoch)` but no `UNIQUE` constraint;
  the live stores already carry 1336 rows and the schema does not
  prevent an append from doubling that count on a re-ingest. The build
  path doesn't re-ingest, but `ingest_firehole` is reachable from
  `build_con` which several tests and `tools` call directly.

### Fix

```python
def ingest_firehole(con, doc):
    sites = doc.get("sites")
    if not isinstance(sites, dict):
        raise ValueError("firehole doc: 'sites' must be an object")
    n = 0
    for site, rec in sites.items():
        series = (rec or {}).get("series") or {}
        q_pairs = series.get("discharge_m3_s", []) or []
        t_pairs = series.get("temperature_c", []) or []
        if not isinstance(q_pairs, list) or not isinstance(t_pairs, list):
            raise ValueError(
                f"firehole site {site}: series must be lists")
        q = {}
        for pair in q_pairs:
            e, v = _validated_epoch_pair(f"firehole {site} q", pair)
            if e in q and q[e] != v:
                raise ValueError(
                    f"firehole {site} q: duplicate epoch {e} "
                    f"with divergent values {q[e]} vs {v}")
            q[e] = v
        # same for t
        ...
```

Add `UNIQUE(site, epoch)` to `obs_usgs` in a new schema version, OR
promote the existing index to a unique one. A migration is not needed
because stores are per-build; the next build picks up the new schema.

### Test

- `test_ingest_firehole_rejects_non_list_series`.
- `test_ingest_firehole_rejects_duplicate_epoch_with_divergent_value`.
- `test_ingest_firehole_rejects_non_finite_epoch`.

---

### 5. `ingest_replay` accepts missing or malformed `cells` and silently defaults geometry to zeros

`analysis_store.py:179-218`:

```python
    for ci, c in enumerate(cells):
        if "id" not in c:
            raise ValueError(f"replay cell #{ci}: missing 'id'")
        vel = _velocity_of(c)
        con.execute(
            "INSERT OR REPLACE INTO replay_cells VALUES (?,?,?,?,?,?,?,?,?,?)",
            (str(c["id"]), str(c.get("river_id", "?")),
             float(c.get("center_s_m",
                         (float(c.get("start_s_m", 0.0))
                          + float(c.get("end_s_m", 0.0))) / 2.0)),
             float(c.get("start_s_m", 0.0)), float(c.get("end_s_m", 0.0)),
             float(c.get("length_m", 0.0)), float(c.get("width_m", 20.0)),
             float(c.get("depth_m", 0.5)), vel,
             float(c.get("volume_m3", 0.0))))
```

A cell with just `{"id": "x"}` ingests as
`river_id="?", s_m=0.0, start_s_m=0.0, end_s_m=0.0, length_m=0.0,`
`width_m=20.0, depth_m=0.5, velocity_m_s=0.0, volume_m3=0.0`. The audit
query against the live stores confirms no rows with `volume_m3<=0`
today, but nothing in the ingest path enforces it. A column named
`volume_m3` with the value `0.0` is a lie, not a safe default.

The width/depth defaults 20.0 and 0.5 are also physical fictions that
no scientific build should produce silently. The authored defaults
match the fit notebook (`VOLUME_M3=300000`, `AREA_M2=600000`,
`depth=0.5`) which is only correct for the Firehole lumped-reach
calibration; using them as per-cell fallbacks confuses the lumped
calibration constants with per-cell geometry.

### Fix

Require the full geometry fields on every cell. Fail loudly instead of
inventing a width:

```python
REQUIRED_CELL = (
    "id", "river_id", "start_s_m", "end_s_m",
    "length_m", "width_m", "depth_m", "volume_m3",
)
for ci, c in enumerate(cells):
    for k in REQUIRED_CELL:
        if k not in c:
            raise ValueError(
                f"replay cell #{ci}: missing {k!r}")
    for k, name in (("length_m", "length"), ("width_m", "width"),
                    ("depth_m", "depth"), ("volume_m3", "volume")):
        v = _finite_float(f"cell #{ci} {name}", c[k])
        if v <= 0:
            raise ValueError(
                f"cell #{ci} {name} must be positive, got {v}")
```

Compute `center_s_m` only when it is not supplied, and verify
`start_s_m < end_s_m`. Record `representative_velocity_m_s` as a
distinct column only when the author's model stores one; the current
fallback at `_velocity_of` (`analysis_store.py:125-129`) drops the
hydraulics-vs-authored provenance.

### Test

- `test_ingest_replay_rejects_missing_geometry_field`.
- `test_ingest_replay_rejects_nonpositive_volume`.
- `test_ingest_replay_rejects_inverted_start_end`.

---

### 6. `_open` on an sqlite3.Connection mutates it: PRAGMA query_only=ON leaks past the call

`analysis_store.py:456-466`:

```python
def _open(con_or_path):
    if isinstance(con_or_path, sqlite3.Connection):
        con = con_or_path
        con.execute("PRAGMA query_only = ON")
        return con
    ...
```

When `query(...)` is called with an in-memory connection owned by a
caller, this flips `query_only` on globally for that connection and
never restores it. A later call to `ingest_*` on the same connection
would fail with "attempt to write a readonly database". The test suite
avoids this by calling `con.close()` after each `query`, but every
`A.query(con, ...)` call in `test_rtree_bbox_includes_edge_coordinates`
and `test_query_limit_offset_truncation` leaves the shared connection
in `query_only=ON`; the next ingest on that connection would fail.

### Fix

```python
def _open(con_or_path):
    if isinstance(con_or_path, sqlite3.Connection):
        return con_or_path  # trust the caller's PRAGMA state
    p = Path(con_or_path)
    if not p.exists():
        raise FileNotFoundError(f"analysis store not found: {p}")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.execute("PRAGMA query_only = ON")
    return con
```

For an owned connection, use the read-only URI alone (already enforced
by `?mode=ro`). The in-memory `create_empty` case needs no PRAGMA
because the test opens it specifically for ingestion.

### Test

`test_query_does_not_leak_query_only_pragma`: `con = A.create_empty();
A.ingest_census(con, doc); A.query(con, "census_trees");
A.ingest_census(con, doc_with_new_tree)` must succeed.

---

### 7. `query()` ORDER BY clause has an off-by-one for `fits_reach_nulls` and uses a flattened string

`analysis_store.py:608`:

```python
order_col = "stable_id" if table == "census_trees" else ("cell_id,t_s" if table == "replay_frames" else ("site,epoch" if table == "obs_usgs" else ("site,day" if table == "obs_snotel" else ("source_file" if table.startswith("fits_") else "rowid"))))
sql += f" ORDER BY {order_col} LIMIT ? OFFSET ?"
```

Two issues:

- `fits_reach_nulls` starts with `fits_` and takes the `source_file`
  branch, but has no `source_file` index or primary key: a 2-row table
  today sorts correctly, but a scale-up to thousands of nulls per fit
  would be a full-table sort on an unindexed TEXT column.
- `cell_id,t_s` and `site,epoch` are a comma-joined string spliced
  into SQL. They parse correctly today because the parser accepts
  multi-column ORDER BY written that way, but a single `order_col`
  variable makes it impossible for a reviewer to tell this is not
  SQL injection waiting to happen. The strings are internal, not
  user input, so this is a maintainability flag, not a security flag.

### Fix

Replace the chain with an explicit table:

```python
ORDER_BY = {
    "census_trees": ("stable_id",),
    "replay_cells": ("cell_id",),
    "replay_frames": ("cell_id", "t_s"),
    "obs_usgs": ("site", "epoch"),
    "obs_snotel": ("site", "day"),
    "fits_reach": ("source_file", "champion DESC"),
    "fits_reach_nulls": ("source_file", "name"),
    "fits_snow": ("source_file", "site"),
    "meta": ("rowid",),
}
order_cols = ", ".join(f'"{c}"' for c in ORDER_BY[table])
```

Add an index on `fits_reach_nulls(source_file, name)` in `_SCHEMA`
once more than a handful of nulls per fit are expected.

### Test

- `test_query_order_is_stable_across_calls`: two sequential calls to
  `query(..., "fits_reach")` return rows in the same order.
- `test_query_fits_reach_champion_first`: champion row sorts before
  non-champion rows for the same `source_file`.

---

### 8. The `evidence_class` filter is accepted on `census_trees` by schema but has no query path

`QUERY_TABLES["census_trees"]` at `analysis_store.py:399-400` includes
`evidence_class` in the output columns, and the live store carries it
(column 7). But `query()` offers no filter on it (lines 498-522 handle
only `x0/x1/z0/z1` and `confidence`). A caller cannot narrow results to
`evidence_class="synthetic"` or `evidence_class="naip_detect"` without
pulling the full table.

The schema column is used nowhere else in the codebase (ripgrep over
`evidence_class` in `yellowstone_python/` and `tools/` returns one hit:
the schema definition and the test fixtures). It is dead data today;
either expose it or stop writing it.

### Fix

Add a `evidence_class` filter in `query()`:

```python
if table == "census_trees":
    ...
    ec = filters.pop("evidence_class", None)
    if ec is not None:
        if not isinstance(ec, str) or not ec:
            raise ValueError(
                "evidence_class must be a nonempty string")
        where.append("census_trees.evidence_class = ?")
        args.append(ec)
```

Document the allowed values somewhere the ingest path can validate
against. Currently the ingest at line 172 writes `str(t.get("evidence_class", ""))`
unconditionally, so empty string is a valid value and no closed set
exists.

### Test

- `test_query_filter_evidence_class`: build a store with two trees
  (one `synthetic`, one `naip_detect`), filter on each, verify count 1.
- `test_query_filter_evidence_class_rejects_empty`.

---

### 9. `census_circle_count` and `query()` BBOX use `r.x0/r.z0` only; a tree with crown_r_m>0 is reduced to a point

`analysis_store.py:632-639`:

```python
cur = con.execute(
    "SELECT t.x, t.z FROM census_trees t JOIN census_rtree r "
    "ON r.tree_row = t.rowid "
    "WHERE r.x0 BETWEEN ? AND ? AND r.z0 BETWEEN ? AND ?",
    (x - r, x + r, z - r, z + r))
```

The R-tree row for each tree stores `(x, x, z, z)` (point, zero
extent) at insert (lines 173-174). That is a correct point-in-bbox
query, but it treats every tree as if its crown radius were 0. A tree
with `crown_r_m=2.0` whose center is 2.1 m outside the circle has a
crown overlapping the circle but is not counted. `test_rtree_bbox_includes_edge_coordinates`
proves inclusion on the point, not the crown.

For a tree density figure this does not matter at 50-400 m rings. For
a "crown canopy overlapping a 2 m radius spring apron" question it is
wrong.

### Fix

Decide once whether circle queries are "point count" or "crown
overlap", and name the function accordingly. Options:

1. Keep as point count, rename `census_circle_count` to
   `census_center_count` so the semantics are explicit in the name,
   and document in the docstring:

   ```python
   def census_center_count(con_or_path, x, z, r):
       """Count tree centers inside the circle of radius r m."""
   ```

2. Store each tree as a crown-sized bbox in the R-tree
   (`(x-c, x+c, z-c, z+c)` where `c=crown_r_m`), then filter the
   candidate set with `(hypot(px-x, pz-z) <= r + crown_r_m)` to count
   crown overlaps. This is a schema change; the stores are history,
   so this applies to new builds only.

The scientific use case (foraging habitat near a spring) matches
option 2; the plumbing use case (density per hectare) matches option
1. Both have a place in the API; one of them must stop pretending to
be the other.

### Test

- `test_circle_count_names_what_it_counts`: a tree with
  `(x=2.1, crown_r_m=2.0)` and a circle of r=1 at the origin counts 0
  under `census_center_count` and 1 under `census_crown_overlap_count`.

---

### 10. `fits_reach` loses the fit's intended fit window and null-model `k` complexity

The reach fit JSON records a fit window and a per-null-model complexity
`k` used by the AIC/BIC comparison (see
`notebooks/reach_fit.ipynb` cell `models.append({"name": ..., **aic_bic(..., n_train, k)})`,
where k is 0, 2, or 0 for the null models in that order). `ingest_reach_fit`
(`analysis_store.py:257-284`) writes none of this: it stores only the
champion plus top-9 and null rows with RMSE, biases, and `c_mult`. A
consumer of the store cannot reproduce the AIC/BIC ranking or know which
observation window the fit was over.

### Fix

Add columns to `fits_reach` and `fits_reach_nulls`:

```sql
ALTER TABLE fits_reach ADD COLUMN window_start_epoch REAL;
ALTER TABLE fits_reach ADD COLUMN window_end_epoch REAL;
ALTER TABLE fits_reach ADD COLUMN n_train INTEGER;
ALTER TABLE fits_reach ADD COLUMN n_holdout INTEGER;
ALTER TABLE fits_reach_nulls ADD COLUMN k INTEGER;
```

Populate from `doc.get("window", {})` and from the per-null `k` field,
not from a hard-coded `(0, 2, 0)`. The notebook's hard-coded zip is
fragile when the null-model list reorders.

### Test

- `test_fits_reach_records_window_bounds`.
- `test_fits_reach_nulls_records_k`.

---

### 11. `ingest_snow_fit` collapses `wind_loss` with no units, loses holdout window

`analysis_store.py:287-305`:

```python
(fit.get("k_melt_mm_per_deg_day")),
(fit.get("wind_loss_effective")),
(fit.get("train_rmse_mm")),
hold.get("rmse"), hold.get("bias"),
```

Problems:

- Column `wind_loss` is stored unitless. The source key
  `wind_loss_effective` is a dimensionless fraction in the current
  snow-fit JSON (0..1), but a reader of the store sees only
  `wind_loss REAL` and must guess.
- `train_rmse_mm` is correctly suffixed `_mm`; `holdout_rmse_mm` and
  `holdout_bias_mm` are stored under column names ending `_mm`, but
  the SOURCE `hold.get("rmse")` and `hold.get("bias")` carry no unit
  check at ingest. A snow-fit artifact that silently records holdout
  in cm or inches would store wrong units with correct-looking column
  names.
- No holdout window bounds are recorded.

### Fix

Rename the column `wind_loss` to `wind_loss_fraction`, assert
`0 <= v <= 1` at ingest, and verify the source key is
`wind_loss_effective`. Record `holdout_start_day` and `holdout_end_day`
as ISO date strings (consistent with `obs_snotel.day`).

### Test

- `test_ingest_snow_fit_rejects_wind_loss_outside_0_1`.
- `test_ingest_snow_fit_records_holdout_window`.

---

### 12. `derived/` disk usage: 502 MB, 72 build dirs account for ~420 MB, 2 stores ~43 MB

READ-ONLY `du -sh` reports:

```
502M    derived
 21M    derived/analysis_574c6165b5e9.sqlite
 22M    derived/analysis_d2a52e498b51.sqlite
420M    derived/*/ (72 build dirs, average 5.8 MB each)
```

Findings:

- 72 build dirs exist. AGENTS.md section 7 says "new artifacts land
  in `derived/<new-build-id>/`, never by editing an old build dir",
  which licenses accumulation. Nothing in the current tree deletes
  old build dirs or compresses them.
- Only two of the 72 build dirs have a matching
  `analysis_<id>.sqlite` file. The remaining 70 build dirs have no
  store, so a query against them via `/api/query` is impossible.
- `analysis_store.build_file` refuses to overwrite an existing store
  (line 346-349). That is the correct safety rail. No code produces
  the stores lazily; `tools/build_store.py` must be run manually per
  build.

This section is a reported finding, not a fix. No files are deleted.
Options a future ticket may choose from, with no action here:

- A build-time hook that runs `tools/build_store.py` after each
  successful `python3 -m yellowstone_python.build` so every build dir
  has a matching store from the start.
- A retention policy (keep the N newest build dirs, plus any build
  cited by a `claims.py` evaluation window) with an explicit opt-in
  CLI (`tools/prune_derived.py --dry-run`).
- `gzip` on `river_replay.json` inside build dirs that are older than
  the N newest; the store format itself is already compact enough that
  the sqlite files are not the pressure point.

### Fix

Add `tools/audit_provenance.py --derived-disk` to print the three
numbers above, so the operator sees pressure before it becomes a
problem. No deletion.

### Test

- `test_audit_provenance_reports_derived_disk_usage`: build a fake
  `derived/` tree with known sizes, assert the printed total.

---

### 13. `Backend.query_store` raises `FileNotFoundError` for "no store" and the handler maps it to HTTP 503; the message leaks a filesystem hint

`llm_backend.py:148-151` and `734-737`:

```python
if path is None:
    raise FileNotFoundError(
        "no derived/analysis_*.sqlite store; build one with "
        "tools/build_store.py --build derived/<id>")
...
except FileNotFoundError as exc:
    return self._send({"error": f"no store: {exc}"}, 503)
```

503 is correct for "service dependency missing". The message is
otherwise fine; the complaint is only that `FileNotFoundError` is also
raised by any legitimate missing-file inside `_load_json` deeper in the
backend, and both land in the same 503. A consumer cannot tell "no
store" from "census.json went missing mid-request".

### Fix

Define a `NoStoreError(FileNotFoundError)` subclass in
`analysis_store`:

```python
class NoStoreError(FileNotFoundError):
    """No derived/analysis_*.sqlite store exists."""
```

Raise it in `Backend.query_store` and in `_open` when
`not p.exists()`. Catch it specifically in `do_GET` and return 503;
let other `FileNotFoundError` map to 500 or a more specific 404.

### Test

- `test_query_route_503_when_no_store_but_500_when_census_missing`.

---

### 14. `query()` filter rejection does not surface the key being rejected consistently

`analysis_store.py:584-586`:

```python
if filters:
    raise ValueError(
        f"unknown filter(s) for {table}: {sorted(filters)}")
```

Good. But upstream validation inside each branch raises its own
`ValueError` with mixed phrasing: `"site must be a nonempty string"`,
`"day0 must be a nonempty string"`, `"confidence must be one of ..."`.
A CLI consumer parsing error strings has to handle three shapes.

### Fix

Centralize filter validation per filter type (string, enum, float,
date-string) in private helpers. Not a correctness fix; a maintenance
fix.

### Test

Existing `test_query_validation_rejections` covers the current
behavior. Add `test_query_rejection_messages_name_the_filter`.

---

### 15. `_velocity_of` silently maps `None` velocity to 0.0

`analysis_store.py:125-129`:

```python
def _velocity_of(cell):
    hydro = cell.get("hydraulics") or {}
    v = hydro.get("velocity_continuity_m_s",
                  cell.get("representative_velocity_m_s", 0.0))
    return float(v or 0.0)
```

`float(v or 0.0)` turns `v=None`, `v=0`, `v=0.0`, `v=False`, and
`v=""` all into `0.0`. A missing velocity is physically different from
a zero velocity. The replay cells in the current stores happen to all
have `volume_m3 > 0` and `velocity_m_s > 0`, so no live row is wrong,
but ingesting a replay doc that omits velocity today produces a cell
with `velocity_m_s=0.0` and no indication of provenance.

### Fix

```python
def _velocity_of(cell):
    hydro = cell.get("hydraulics")
    if isinstance(hydro, dict) and "velocity_continuity_m_s" in hydro:
        return _finite_float("velocity_continuity_m_s",
                             hydro["velocity_continuity_m_s"])
    if "representative_velocity_m_s" in cell:
        return _finite_float("representative_velocity_m_s",
                             cell["representative_velocity_m_s"])
    raise ValueError(f"cell {cell.get('id')!r}: no velocity field")
```

Also record which key was used in a new column `velocity_source TEXT`
(`"continuity"` or `"representative"`) so the fit downstream can
distinguish measured-equivalent from authored.

### Test

- `test_ingest_replay_rejects_cell_with_no_velocity`.
- `test_ingest_replay_records_velocity_source`.

---

# Wiring and rendering

Consumers of the store module:

- `tools/build_store.py` is the only CLI that produces store files.
  It is not invoked by `python3 -m yellowstone_python.build`; AGENTS.md
  section 4 documents it as a post-build manual step. 70 of 72 build
  dirs have no matching store today.
- `yellowstone_python/llm_backend.py:35-37` imports `RADIUS_MIN_M` and
  `RADIUS_MAX_M` from `analysis_store` as `MIN_RADIUS_M` and
  `MAX_RADIUS_M`. `test_radius_bounds_single_sourced` verifies the two
  modules agree.
- `llm_backend.Backend.store_path/query_store/density`
  (lines 119-167) select the newest sqlite by mtime and expose it to
  `/api/query` and `/api/density`.
- `notebooks/census_explorer.ipynb` opens the store directly via
  `sqlite3.connect(str(STORE))` without `?mode=ro`.
- `notebooks/reach_fit.ipynb` does NOT read the store; it reads
  `derived/firehole_obs.json` directly and the fit artifact JSON.
- Godot renders nothing from the store. The store is a Python-side
  analytics index. Godot bakes from `derived/<build-id>/` artifacts via
  `yellowstone_python.publish`.
- The failing test `test_duplicate_stable_id_leaves_no_stale_rtree`
  documents a contract the code does not satisfy (finding 1).
- `/api/build/latest` and `/api/query` can disagree on `build_id`
  because they pick the latest build dir and the latest sqlite by two
  independent orderings (finding 2).

# Comment-style violations

Rules per AGENTS.md section 2.

| file:line | text | rule |
| --- | --- | --- |
| `yellowstone_python/analysis_store.py:16` | `# Unit factors: SNOTEL stores WTEQ/PRCP/SNWD in inches, TAVG/TMAX/TMIN in degF.` | ALL-CAPS emphasis on `WTEQ/PRCP/SNWD`, `TAVG/TMAX/TMIN`. |
| `yellowstone_python/analysis_store.py:32` | `raise ValueError(f"{name} must be numeric, not boolean")` | `X, not Y` contrast. Prefer `"must be numeric; boolean rejected"` or drop. |
| `yellowstone_python/analysis_store.py:63-64` | `"...; refusing to build a store that would silently full-scan spatial queries"` | hypothetical-failure narrative (`silently`). |
| `yellowstone_python/analysis_store.py:161-162` | `# OR REPLACE frees the old rowid; its R-tree entry would otherwise survive as garbage pointing at a dead (later reusable) rowid.` | hypothetical-failure narrative (`would otherwise`); two-line inline comment. |
| `yellowstone_python/analysis_store.py:182` | `# Clear replay tables before ingestion to prevent stale frames.` | hypothetical-failure narrative (`to prevent stale`). |
| `yellowstone_python/analysis_store.py:383` | `# Atomic replace; clean up any leftover temp files on failure.` | ok lexically, but combines two statements. |
| `yellowstone_python/analysis_store.py:422` | `# Circle-radius bounds single-sourced here; llm_backend aliases these.` | temporal-contrast comment ("single-sourced here"). |
| `yellowstone_python/analysis_store.py:429` | `"must be a number, not boolean"` | `X, not Y`. |
| `yellowstone_python/analysis_store.py:441` | `"must be an integer, not boolean"` | `X, not Y`. |
| `yellowstone_python/analysis_store.py:472-478` | `"""Read-only bounded query over allow-listed tables/columns/filters.\n\n    Filters per table: ...\n    """` | docstring is 7 lines; AGENTS.md section 2 limits docstrings to one or two. |
| `tools/build_store.py:1-16` | multi-paragraph module docstring with `Derived artifacts are history: the default output is a NEW file per build, never an overwrite of an existing store.` | `never`-narrative, ALL-CAPS `NEW`, long docstring. |
| `tools/build_store.py:38-39` | `help="repeatable; empty -> fits tables empty with a meta note, never an error"` | hypothetical-failure narrative (`never an error`). |
| `yellowstone_python/llm_backend.py:35` | `# Density circles outside [MIN_RADIUS_M, MAX_RADIUS_M] are rejected. Bounds single-sourced from analysis_store.` | second sentence is a provenance-of-the-code note ("single-sourced from"), temporal-contrast style. |
| `yellowstone_python/llm_backend.py:120-124` | `"""Newest derived/analysis_*.sqlite, or None when no store exists.\n\n    Explicit constructor `store=` wins; otherwise the newest store\n    file is resolved live (stores are history: one file per build).\n    """` | docstring is 4 lines; "stores are history" is a convention restatement, not a function description. |
| `yellowstone_python/llm_backend.py:142-145` | `"""Read-only bounded query over the analysis store.\n\n    Raises FileNotFoundError (HTTP 503) when no store file exists; ValueError (HTTP 400) on any validation rejection.\n    """` | docstring is 4 lines; mixes contract and transport status. |
| `yellowstone_python/llm_backend.py:158` | `"""Circle crown count, store-backed when a store file exists. Store path and JSON path share one answer contract."""` | second sentence is a convention statement; one-sentence docstring preferred. |
| `yellowstone_python/llm_backend.py:736-737` | `# /api/query only: llm_backend still serves everything else when no store file exists.` | hypothetical-failure narrative restating normal operation. |
| `tests/test_analysis_store.py:21-22` | `# Edge coordinates deliberate: e1 sits exactly on the (0,0,10,10) bbox edges and must be INCLUDED; e2 sits just outside.` | ALL-CAPS `INCLUDED`; two-line inline comment. |
| `tests/test_analysis_store.py:321` | `# The notebook must read the store only, never the JSON interchange.` | `never` narrative. |
| `tests/test_analysis_store.py:353-354` | `# Regression: day0/day1 once passed validation but were silently discarded, returning the unfiltered table.` | temporal reference (`once`), hypothetical-failure (`silently`). |

# Operator memory drift

The operator-local memory store carries 63 `file_references` rows whose
paths contain `yellowstone`, of which 10 point under
`../../yellowstone_python/`. That directory does not
exist on disk today (confirmed by filesystem check: no entry at
`../../yellowstone_python`). The 10 broken paths are:

```
../../yellowstone_python/worker_briefs/snotel_sites_2026-10-10.md
../../yellowstone_python/derived/snotel_obs_2026-10-10.json
../../yellowstone_python/derived/snow_snotel_fit_2026-10-10.json
../../yellowstone_python/derived/reach_lsfit_V300000_2026-10-10.json
../../yellowstone_python/derived/hot_lowflow_replay_2026-10-10.json
../../yellowstone_python/derived/aquatic_hot_lowflow_2026-10-10.json
../../yellowstone_python/derived/fischer_D85_replay_2026-10-10.json
../../yellowstone_python/derived/aquatic_dispersion_D85_2026-10-10.json
../../yellowstone_python/derived/hot_lowflow_D85_replay_2026-10-10.json
../../yellowstone_python/derived/aquatic_hot_lowflow_D85_2026-10-10.json
```

Four of those basenames match the four date-stamped source paths the
built stores record in `meta.source_shas` but can no longer resolve
(`snotel_obs_2026-10-10.json` and `snow_snotel_fit_2026-10-10.json`
appear verbatim; `firehole_obs_2026-10-09.json` and
`reach_fit_V300000_2026-10-09.json` do not appear in the operator-local
memory, suggesting those were produced in a different workspace). The
simplest explanation is that an earlier sibling session built the
stores under `../../yellowstone_python/` and later
work moved to the current `!claude/roots-of-reason/.../yellowstone_python/`
tree, leaving operator-local memory pointing at the former location.
The operator-local events log corroborates this: the row at
`2026-10-10T07:17:20Z lesson` reads "concurrent session shares
yellowstone_python tree: their hot_lowflow files trip audit_provenance;
my files verified intact, no shared-file collision". That lesson predates
the move but does not record the subsequent cleanup.

Action for the operator-local memory store (outside the scope of this
project; recorded here as a finding): either re-resolve each
`../../yellowstone_python/...` row to its current
location under
`./yellowstone_python/`,
or delete the row. The project itself does not depend on these rows.

# Priority order

1. Finding 1: fix the duplicate `stable_id` dead-code / unreachable
   replace path; make the failing test pass. (cost: cheap)
2. Finding 2: match `Backend.store_path` to the newest build dir by
   `CHECKS.json`, not by sqlite mtime; add
   `audit_provenance.py --audit-stores`. (cost: medium)
3. Finding 3: chmod stores read-only at the end of `build_file`;
   switch `notebooks/census_explorer.ipynb` to the read-only URI;
   audit any store with tables outside the known allow-list. (cost:
   cheap, plus one line in the notebook)
4. Finding 6: do not flip `PRAGMA query_only=ON` on a caller-owned
   connection. (cost: cheap)
5. Finding 5: fail loudly on replay cells with missing geometry; drop
   the authored width/depth fallbacks. (cost: medium; may surface
   bad replay docs that silently ingest today)
6. Finding 15: `_velocity_of` must not conflate missing with zero;
   record provenance. (cost: cheap)
7. Finding 4: harden `ingest_firehole` and promote `obs_usgs` index
   to UNIQUE. (cost: medium)
8. Finding 10: add fit-window and `k` columns to `fits_reach` and
   `fits_reach_nulls`. (cost: medium, schema change)
9. Finding 11: unit-check `wind_loss`; record holdout window. (cost:
   cheap)
10. Finding 9: decide and name "point count" vs "crown overlap";
    change the R-tree stored bbox if option 2. (cost: medium to
    refactor)
11. Finding 8: expose or stop writing `evidence_class`. (cost: cheap)
12. Finding 7: replace the nested-conditional `order_col` string with
    an explicit mapping; add index. (cost: cheap)
13. Finding 13: define `NoStoreError`. (cost: cheap)
14. Finding 14: centralize filter-validation messages. (cost: cheap)
15. Finding 12: add `--derived-disk` reporting; no deletion. (cost:
    cheap)
16. Comment-style violations above: edit in place; AGENTS.md section 2.
    (cost: cheap)
