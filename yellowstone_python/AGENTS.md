# Yellowstone Python — agent init rules

Read this file at session start, before touching code. Run `/ystone` for a
spoken orientation plus the roadmap to task-specific docs.

## 1. First reads (in order)

1. `README.md` — what Python simulates vs Godot, measured/authored split.
2. `../yellowstone_python_spec/00_OVERVIEW_AND_VERDICT.md`
   — why this world, fast-path strategy.
3. Latest `derived/<build-id>/BUILD.json` — current `run_mode`,
   `prescribed_quantities`, `claim_ids`, `checks_passed`.
4. The registries before changing any knob:
   `yellowstone_python/claims.py`, `param_registry.py`, `equations.py`.

## 2. Comment style (no AI tells)

Every new or edited comment follows these. Full catalog:
`../yellowstone_python_spec/ai-tells/`.

- No em dashes. Use periods or colons.
- No first person (`I`, `we`, `my`) and no addressing the reader (`you`, `your`).
- No `X, not Y` contrasts. State what the thing is.
- No hypothetical-failure narratives (`never silently`, `instead of
  guessing`, `rather than`, `cannot drift apart`).
- No temporal references (`legacy`, `new work`, `audit fix`, `now`,
  `used to`, date-stamped NOTEs).
- No `Every` comprehensiveness claims, no ALL-CAPS emphasis.
- Docstrings are one or two lines. Inline comments are one line.
- American spelling (`meters`, `vapor`, `color`).

Good and bad (from `ai-tells/edits-2.md`):

```python
# BAD:  # Newton exchange is an illustrative lumped heat-loss term, not full surface physics.
# GOOD: # Newton exchange is a lumped heat-loss term.

# BAD:  # Retain elapsed-time debt after a slow frame; never silently lose physical time.
# GOOD: # Retain elapsed-time debt after a slow frame.

# BAD:  # Kept for interface compatibility; transport is always 1:1.
# GOOD: # Transport is 1:1.

# BAD:  """Per-cell quasi-steady thermal + hydraulic habitat from replay frames.
#         t_min_s/t_max_s restrict to a window — REQUIRED for intervention
#         comparison, where a whole-run mean would dilute a short pulse
#         into invisibility. Window bounds are explicit so control and pulse
#         landscapes cover the same clock interval."""
# GOOD: """Per-cell quasi-steady thermal + hydraulic habitat from replay frames.
#         t_min_s/t_max_s restrict to a window for intervention comparison."""
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
python3 tools/build_store.py --build derived/<build-id> \
  --firehole derived/firehole_obs.json \
  --snotel derived/snotel_obs.json \
  --reach-fit derived/reach_heat_fit_v300k.json \
  --snow-fit derived/snow_degree_day_fit.json
```

`--out` defaults to `derived/analysis_<buildid>.sqlite`. Missing inputs
fail loudly; repeat `--reach-fit` / `--snow-fit` for multiple artifacts.

Query (read-only, allow-listed tables and columns, no raw SQL):

```python
from yellowstone_python.analysis_store import query
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
`python3 -m yellowstone_python.llm_backend --serve --port 8765`
(`GET /api/snapshot`, `/api/density`, `/api/compare`, ...).

Rebuild the store when: a new build dir exists, an obs bundle changed
(new fetch), or a fit artifact changed. Record `source_shas` from the
build output; the store carries them in `meta`.

## 5. Python memory store (operator-local)

Session memory lives outside this repository. The operator provides the
handbook path at session start; follow it for event logging, file
registration, and stable facts. Nothing in this section is required to
build, test, or publish the project.

## 6. Run modes and claims (Phase A/B state)

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

```bash
python3 -m pytest tests -q
python3 -m yellowstone_python.build --config configs/baseline.yaml
python3 tools/audit_provenance.py --dir derived
```

Suite is ~35s and must stay green. New modules ship with tests.
New artifacts land in `derived/<new-build-id>/`, never by editing an
old build dir. Godot publish is transactional via
`python3 -m yellowstone_python.publish --build derived/<id> --to
../yellowstone_midway` (bake needs Godot 4.5.1;
installed 4.4.1 is check-only).
