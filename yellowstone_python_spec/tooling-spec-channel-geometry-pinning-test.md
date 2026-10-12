# Spec: channel_geometry pinning test

Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].
No code written; no deletions. Target: new test file (e.g. `tests/test_channel_geometry.py`) in `/Users/kreed/Downloads/yellowstone_python/`.

## 1. Purpose + non-goals

Purpose: pin the transect math + status strings of `tools/channel_geometry.py` (grade A-: regenerates `configs/cross_sections.json` bit-for-bit claim, currently ZERO tests — verified: `rg "channel_geometry"` → 1 self-hit; only `test_build.py:75` asserts its output's downstream effect). A grade-A tool with zero unit tests regresses silently.

Non-goals: no re-deriving checked-in depths from real topography (needs the 4 MB out-of-repo file); no testing `main()` end-to-end; no USGS-preferred-path live run (all 5 committed records took the DEM branch — `dem_cross_check_depth_m` absent everywhere).

## 2. CLI (no new CLI; test invocation)

```
pytest tests/test_channel_geometry.py -q   # fast, offline, no fixtures beyond stubs
```

Test imports the tool the house way: `tools/` scripts use `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` (`channel_geometry.py:28`); the test must import WITHOUT executing `main` (guard `if __name__ == "__main__"` at `channel_geometry.py:251-252` already ensures import-safety — verify, don't assume).

## 3. Inputs / outputs with exact schemas

Functions under pin (transferred signatures/behaviors):
- `_unit_perpendicular(dx,dz)` (`:42-46`): `(-dz/len, dx/len)`, `(0,0)` if `<1e-9`.
- `_cross_section_from_dem(cx,cz,water_y,perp_x,perp_z,sample,half_width=35.0,step=0.5,min_depth=0.10)` (`:49-86`): 141 `sample` calls; bank search `depth>min_depth`; `(0,0,0)` if none (`:74-75`); trapezoid area over `d>0`; `width=right-left`, `mean=area/width`.
- `_dem_mean_depth(feature,sample,spacing_m=50.0)` (`:89-156`): `n_samples=max(3,int(total/50))`; fallback `{"depth_m":1.1,"status":"default_assumed_no_valid_transects"}` (`:137-141`); success `round(...,3)` + `status "authored_estimate_from_usgs_3dep_dem"` + `source` with `mean_area=/mean_width=/depth_std=` (`:143-155`).
- `_usgs_mean_depth(usgs_data)` (`:159-190`): `area_sqft/width_ft*0.3048`; `None` if empty (`:174-175`); skips None/0 entries (`:167`).
- Status strings pinned: `authored_estimate_from_usgs_3dep_dem` (`:150`), `usgs_field_measurement_current_meter` (`:184`), `default_assumed_no_valid_transects` (`:139`).
- Golden values (transferred, `configs/cross_sections.json:2-26`): 5 depths `0.53, 0.529, 0.512, 0.521, 0.513` + source strings (e.g. `"USGS 3DEP DEM transects every 50m over 3532m; mean_area=16.6m2 mean_width=31.2m depth_std=0.05m"`).

## 4. Algorithm / rules in numbered steps (what the TEST does)

1. Stub `sample`: flat `lambda x,z: water_y-1.0` (1 m deep everywhere) + dry `lambda x,z: water_y+5.0` + hand-made `feature={"id":..., "points":[[x,y,z],...]}` (world schema needs `id/points`, `river_world.py:460-471` shape as oracle).
2. Assert `_unit_perpendicular` basis cases incl. zero-vector.
3. Assert flat-stub cross-section: `width ≈ 2*half_width` minus edge, `mean_depth ≈ 1.0`; dry-stub → `(0,0,0)`; single-wetted-point → `(0,0,0)`.
4. Assert bank-threshold sensitivity: same stub at `min_depth=0.10` vs `0.15` differs (pins the `:53` vs cross_sections `:30` non-equivalence boundary).
5. Assert `_dem_mean_depth` flat-stub: success status string exact, `depth_m` rounded to 3 dp, `source` contains `mean_area=` + `depth_std=`; dry-stub: exact fallback dict.
6. Assert `_usgs_mean_depth`: `area 100 sqft / width 10 ft → 3.048 m`; empty → `None`.
7. Assert golden file: checked-in `configs/cross_sections.json` depths/source strings equal §3 values (regression tripwire; does NOT re-run DEM code).
8. Cost rule: no test may read the real `terrain.f32` or `world.json`. Rationale (transferred): `load_terrain` rejects any `size != 1,050,625` (`vegetation.py:141-142`); `terrain_fns` hard-wires `GRID/STEP/HALF`; the four pure functions take a plain `sample` callable so 100% of branch logic runs with zero I/O. (`analyze` itself needs full-size arrays only because it calls `terrain_fns` internally at `channel_geometry.py:199` — bypass it; optionally ONE test builds synthetic `np.zeros((1025,1025))` (~4 MB RAM, no file) to cover `analyze`'s USGS-prefer branch with stub world — [AUTHORED] allowed but not required.)

## 5. Provenance plan

Test file header comment cites this spec + `tools/channel_geometry.py` lines. Golden-value test cites `configs/cross_sections.json` by path (not copied numbers without provenance — the test reads the file). No artifact modified.

## 6. Error handling (test design)

| Case | Expected |
|---|---|
| Import executes `main` | Must not happen (guard verified); test fails loudly if stdout/argv touched on import |
| Stub grid too small passed to `terrain_fns` | Not done (bypassed by design — document why in comment) |
| Golden file legitimately regenerated | Golden test updated ONLY with the regeneration run log (which `--usgs-data`, world/terrain hashes) attached |

## 7. Tests (the spec IS the test list — names)

1. `test_unit_perpendicular_basis`
2. `test_cross_section_flat_depth`
3. `test_cross_section_dry_returns_zeros`
4. `test_bank_threshold_sensitivity_010_vs_015`
5. `test_dem_mean_depth_success_shape`
6. `test_dem_mean_depth_fallback_shape`
7. `test_usgs_mean_depth_conversion`
8. `test_usgs_mean_depth_empty_none`
9. `test_golden_cross_sections_json`
10. `test_tool_import_safe` (import has no side effects)

All synthetic/offline; runtime target <5 s total (in-process stubs; the ~15-20k-sample full run is milliseconds and NOT part of this suite).

## 8. Acceptance criteria

- [ ] 10 tests pass offline; full suite count increases by exactly 10, still green.
- [ ] Zero file I/O in tests except reading the golden JSON (assert via tmp-free run — no fixtures written).
- [ ] Bank-threshold + status-string pins fail if constants change (mutation check by inspection: change `0.10`→`0.15` locally, see test 4 fail, revert).
- [ ] USGS-preferred branch (`:215-217`, zero coverage in committed artifacts) covered at least by stub-`analyze` or documented as uncovered.

## 9. Effort + dependencies

Effort: S (~150 lines of tests; no source changes). Dependencies: none (numpy/pytest already required). Explicitly NOT required: the 4 MB real file — spec justifies why with code citations, per the brief.
