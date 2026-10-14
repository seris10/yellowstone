# Yellowstone Python - agent init rules

Read this file at session start, before touching code. Run `/ystone` for a
spoken orientation plus the roadmap to task-specific docs.

## 1. First reads (in order)

1. `README.md` - what Python simulates vs Godot, measured/authored split.
2. `../yellowstone_python_spec/00_OVERVIEW_AND_VERDICT.md`
   - why this world, fast-path strategy.
3. Latest `derived/<build-id>/BUILD.json` - current `run_mode`,
   `prescribed_quantities`, `claim_ids`, `checks_passed`.
4. The registries before changing any knob:
   `yellowstone_python/registry/claims.py`, `registry/param_registry.py`, `registry/equations.py`.

## 2. Comment and documentation style

Module docstrings use a noun phrase naming the module, with one optional scope line. Function and class docstrings use one imperative line under 100 characters, with one optional contract or unit line. Equations and extended sources live in the component registry.

Comments use one present-tense line describing the code. Banners use `# --- Label ---`. Text uses ASCII and American spelling. Citations use `Author (YYYY)` or `First et al. (YYYY), doi:10.xxxx/...`. Unit strings use `m3/s`, `m2`, `W/m2`, `W/m2/K`, `mg/L`, and `C`. Provenance identifies the source and value class: measured, literature, fitted, or authored within a cited range.

Internal process labels, session narration, history narration, reader address, first person, emphasis, and hypothetical failure stories are excluded. Markdown prose and notebook markdown follow the ASCII, dash, vocabulary, process-label, and operational-date rules. Code examples illustrate the rules:

```python
# Bad module: "M01 hydro chain."
# Good module: "River heat transport and mixing."
# Bad function: "Temperature estimate; first clause; second clause; third clause."
# Good function: "Return the river temperature in C."
# Bad comment: "Kept for parity; never silently lose physical time."
# Good comment: "Retain elapsed-time debt after a slow frame."
# Bad banner: "# ---- River ----"
# Good banner: "# --- River ---"
# Bad citation: "Davis 1975, DOI:10.example/source."
# Good citation: "Davis (1975), doi:10.example/source."
# Bad units: "m^3 s^-1"
# Good units: "m3/s"
# Bad text: "Temperature delta: Unicode arrow."
# Good text: "Temperature delta in C."
# Bad source: "Existence verified via WebSearch."
# Good source: "Davis (1975); authored_within_cited_range."
```

## 3. No dating in code paths

No date-stamped filenames in `*.py`, `configs/`, `tests/`, `notebooks/`,
or `tools/` defaults. Window identity uses role words
(`prior_window`, `second_window`) or metadata inside the file.
Timestamps as data values and prose dates in docs are allowed.

Check before committing work:

```bash
rg '_2026-10|_2026_10|WY2025_2026' yellowstone_python tools tests \
  configs notebooks --glob '*.py' --glob '*.yaml' --glob '*.ipynb'
```

That query must return zero filename hits.

## 4. Analysis store (SQLite)

One store file per build. Stores are history: never overwrite, never mutate.

Build (after `python3 -m yellowstone_python.build --config ...`):

```bash
python3 -m tools.build_store --build derived/<build-id> \
  --firehole derived/firehole_obs.json \
  --snotel derived/snotel_obs.json \
  --reach-fit derived/reach_heat_fit_v300k.json \
  --snow-fit derived/snow_degree_day_fit.json
```

`--out` defaults to `derived/analysis_<buildid>.sqlite`. Missing inputs
raise errors; repeat `--reach-fit` / `--snow-fit` for multiple artifacts.

Query (read-only, allow-listed tables and columns, no raw SQL):

```python
from yellowstone_python.service.analysis_store import query
query("derived/analysis_<buildid>.sqlite", "meta")
query("derived/analysis_<buildid>.sqlite", "replay_frames",
      columns=["t_s", "cell_id", "temperature_c"],
      cell_id="cell_00145", limit=50)
```

Tables: `census_trees`, `replay_cells`, `replay_frames`, `obs_usgs`,
`obs_snotel`, `fits_reach`, `fits_reach_nulls`, `fits_snow`, `meta`.
Filters per table are listed in `query()`; unknown tables, columns, or
filters raise. Spatial and circle queries go through the same module
(`circle_stats`); the HTTP equivalent is
`python3 -m yellowstone_python.service.llm_backend --serve --port 8765`
(`GET /api/snapshot`, `/api/density`, `/api/compare`, ...).

Rebuild the store when: a new build dir exists, an obs bundle changed
(new fetch), or a fit artifact changed. Record `source_shas` from the
build output; the store carries them in `meta`.

## 5. Python memory store (operator-local)

Session memory lives outside this repository. The operator provides the
handbook path at session start; follow it for event logging, file
registration, and stable facts. Nothing in this section is required to
build, test, or publish the project.

## 6. Run modes and claims

- Every config declares `run_mode`: `illustrative` (default), `scenario`,
  `hindcast`, or `observed_replay`. `forecast` builds are refused.
- Boundary discharge and upstream temperature are prescribed forcing;
  validation covers unprescribed outputs (`run_mode.check_split`
  enforces this; `validation/checks.py` gates it).
- Both seed claims are `not_yet_accepted`. Never mark a claim accepted
  without evaluation datasets listed and a locked-final window evaluated.
- Unknown parameter uncertainty stays `unknown`. Do not invent
  distributions.

## 7. Verify before reporting done

The project interpreter is `.venv/bin/python` (created with
`python3 -m venv --system-site-packages .venv` and
`.venv/bin/python -m pip install -r requirements.txt`). It adds pandas,
pvlib and metpy on top of the Homebrew Python, which refuses package
installs.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m yellowstone_python.build --config configs/baseline.yaml
.venv/bin/python -m tools.audit_provenance --dir derived
.venv/bin/python -m pytest tests/test_repository_style.py -q
```

Suite covers the single `tests/` tree.
World and numerical reference tests can take several minutes. New modules ship with tests.
The test suite runs the style gate across the maintained source tree and fails
on hard-rule findings.
New artifacts land in `derived/<new-build-id>/`, never by editing an
old build dir. Godot publish is transactional via
`python3 -m yellowstone_python.publish --build derived/<id> --to
../yellowstone_midway` (bake needs Godot 4.5.1;
installed 4.4.1 is check-only).
