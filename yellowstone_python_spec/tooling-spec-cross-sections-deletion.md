# Spec: tools/cross_sections.py DELETION checklist (authorization package)

Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].
NO DELETION PERFORMED — this spec is the authorization package; deletion happens in a LATER session.
Target: `tools/cross_sections.py` (175 lines) in `../../yellowstone_python/`.

## 1. Purpose + non-goals

Purpose: authorize and enumerate the deletion of dead tool `tools/cross_sections.py` (unreferenced, superseded by `tools/channel_geometry.py`). Evidence it is dead: zero code imports it; the only cross-file mention of the shared output path is `channel_geometry.py:16` docstring; live `configs/cross_sections.json` is provably `channel_geometry.py` output (status `authored_estimate_from_usgs_3dep_dem` + `depth_std` in source + 5-feature `FIREHOLE_CHAIN` scope — all absent from `cross_sections.py`'s vocabulary/scope).

Non-goals: no deletion in this session; no changes to `channel_geometry.py`, `river_world.py`, configs, or tests; no removal of `parse_cross_sections` (the CONSUMER in `river_world.py:56-96` stays — only the dead producer goes).

## 2. CLI (deletion-session commands, drafted)

```bash
# Pre-conditions (must all pass before deleting):
python3 -c "import ast,sys; sys.exit(0)"  # sanity
rg -l "cross_sections" --glob '!derived/**' --glob '!*.pyc' .   # expect list in §3 only
pytest tests/ yellowstone_python/replay/tests/ -q                # green baseline, record count
# Deletion:
trash tools/cross_sections.py            # trash, never rm (house rule)
pytest tests/ yellowstone_python/replay/tests/ -q                # still green, same count
```

## 3. Inputs / outputs with exact schemas

Non-equivalence record (transferred — the deleting session must NOT treat outputs as interchangeable):

| Aspect | `cross_sections.py` | `channel_geometry.py` |
|---|---|---|
| Transect half-width | 30.0 m (`:29`) | 35.0 m (`:52`) |
| Transect step | 1.0 m (`:30`) | 0.5 m (`:52`) |
| Bank threshold | `MIN_DEPTH_M=0.15` (`:30`) | `min_depth=0.10` (`:53`) |
| Feature loop | all `world["rivers"]` minus `authored_excelsior_outflow_01` (`:159-163`) | only 5 `FIREHOLE_CHAIN` ids (`:33,200-210`) |
| USGS branch | none | `_usgs_mean_depth` + prefer-if->0.2 m (`:159-219`) |
| Averaging | `sum/len` (`:133-135`) | `np.mean/np.std` + `depth_std` (`:143-146`) |
| Success status | `authored_estimate_from_dem_terrain` (`:139`) | `authored_estimate_from_usgs_3dep_dem` (`:150`) |
| CLI | `--world/--terrain/--out/--spacing` (`:149-152`) | `--world/--terrain/--usgs-site/--usgs-data/--out` (`:228-232`) |

Every mention to remove / update (transferred exhaustive grep, excluding `derived/*` bulk + `*.pyc`):
1. `tools/cross_sections.py` itself (the deletion).
2. `tools/channel_geometry.py:16` — mentions shared output path only; NO code change needed (it never imports the dead tool). Verify post-delete: file still standalone.
3. `configs/baseline.yaml:47` (`cross_sections_file: configs/cross_sections.json`) — NOT removed (points at the DATA file, which stays; produced by channel_geometry). Deleting session verifies the comment still reads true.
4. `yellowstone_python/build.py:116-117,194-199,210` — loads the DATA file; untouched.
5. `tests/test_build.py:75-86` — asserts the DATA file's effect; untouched.
6. `yellowstone_python/replay/river_world.py` (`parse_cross_sections`, CLI `--cross-sections`) — the consumer; untouched.
7. `yellowstone_python/replay/tests/test_river_world.py:8,136-185` — consumer tests; untouched.
8. `.pytest_cache/v/cache/nodeids:5` — cache entry; regenerates, do not hand-edit.

NOT removed: `configs/cross_sections.json` (live data, channel_geometry output), everything above except file #1.

## 4. Algorithm / rules in numbered steps (deletion session)

1. Re-verify zero references: run the §2 `rg`; the hit list must be EXACTLY §3 items 2-8 (code) + `derived/*` bulk. Any NEW hit since 2026-10-10 → STOP, re-authorize.
2. Re-verify non-equivalence note is recorded (this spec §3) in the signoff report — the deleting session must be able to answer "why not just switch back."
3. Record pytest baseline (full suite count) BEFORE deleting.
4. `trash tools/cross_sections.py` (restorable; never `rm`).
5. Re-run full suite; count must be IDENTICAL (no test imports the deleted tool — verified today: zero test hits).
6. Confirm `configs/cross_sections.json` + `channel_geometry.py` untouched (`diff` or mtime/size check).
7. Discoverability repair [AUTHORED]: `channel_geometry` has exactly 1 repo hit (its own docstring) — after deletion it is the ONLY producer of a consumed config yet nothing points to it. Add ONE pointer: a line in the repo `README.md` tooling section naming `tools/channel_geometry.py` as the producer of `configs/cross_sections.json` (single-line edit, quoted in signoff).

## 5. Provenance plan

Deletion signoff report lists: deleted file + trash location, pre/post suite counts, re-verified hit list, README pointer line. No artifact status changes (no derived data modified). This spec (authorization) is cited by path in the deletion report.

## 6. Error handling (deletion session)

| Condition | Action |
|---|---|
| New `cross_sections` reference found | STOP, do not delete, report hit |
| Suite red before deletion | STOP, fix baseline first (not this task) |
| Suite count changes after deletion | RESTORE from trash, report which test imported it |
| `channel_geometry.py` broken by deletion | Impossible by construction (no import) — if observed, restore + report |

## 7. Tests (deletion session runs, writes none new)

1. Baseline full-suite green with count recorded.
2. Post-delete full-suite green with IDENTICAL count.
3. `python3 -c "import tools"`-style smoke: N/A (tools/ is script dir, not package) — instead: `python3 tools/channel_geometry.py --help` exits 0 (survivor intact).

## 8. Acceptance criteria

- [ ] `tools/cross_sections.py` in trash, restorable; nothing else deleted/modified except the one README pointer line.
- [ ] Pre/post suite counts identical, both green.
- [ ] Signoff report contains §5 items + non-equivalence citation.
- [ ] No commit (standing rule).

## 9. Effort + dependencies

Effort: S (verification + trash + suite runs; ~30 min). Dependencies: none. Bit-for-bit regeneration claim explicitly NOT verified (no run log pins the generator invocation incl. which `--usgs-data`) — spec does not authorize claiming it.
