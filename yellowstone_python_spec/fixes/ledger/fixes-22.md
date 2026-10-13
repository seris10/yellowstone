# fixes-22 ledger
Doc: fixes/fixes-22-check-terrain.md | read 2026-10-12, open rows re-verified 2026-10-13 | targets: tools/check_terrain.py sha256:2558e6720a6d ; yellowstone_python/build.py sha256:65d9b0265537
Summary: 14 items: 14 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | Reject NaN or non-finite terrain before range guard | implemented | tools/check_terrain.py:150 `finite_mask = np.isfinite(grid)` guard returns before range | counts non-finite cells and fails | cheap |
| 2 | Validate `--min-m` and `--max-m` as finite with min < max | implemented | tools/check_terrain.py:92 `_validate_range_args` enforces finite and min<max | guard raises ValueError, main parser.error | cheap |
| 3 | Implement p1/p99 percentile report or drop the claim | implemented | tools/check_terrain.py:160 `np.percentile(grid, [1.0, 99.0])` emitted in info and in guard entry | report carries p1_m / p99_m | cheap |
| 4 | Spatial plausibility: slope, flats, jumps | implemented | tools/check_terrain.py:117 `_spatial_report` computes finite-difference slope, jump, flats; guard enforces MAX_SLOPE_RATIO, MAX_JUMP_M, MAX_FLAT_CELL_FRACTION | fixture updated to a tilted grid | medium |
| 5 | Centralize cell size (`STEP = 4.0`) across modules | implemented | tools/check_terrain.py:32 `CELL_M = 4.0` exposed; report info carries it | overland_flow.STEP migration left as handoff for cluster D | cheap |
| 6 | Record and validate axis order / origin / orientation | implemented | tools/check_terrain.py:33-39 AXIS_ORDER, ROW_DIRECTION, COL_DIRECTION, ORIGIN; recorded in info and axis guard | fields emitted in every report | medium |
| 7 | Surface vertical-datum status as a visible guard | implemented | tools/check_terrain.py:88 vertical-datum guard entry carries `status: undocumented` | guard surfaced in output | cheap |
| 8 | Distinguish vertex grid vs cell grid semantics | implemented | tools/check_terrain.py:32 `GRID_SEMANTICS = "vertex_grid"` in info | consumer can key on grid_semantics | cheap |
| 9 | Compute hash on every readable path | implemented | tools/check_terrain.py:134 `info["sha256"] = _file_sha256(path)` called before size/grid returns | hash reaches report even when size fails | cheap |
| 10 | Normalize expected hash and reject bad hex | implemented | tools/check_terrain.py:98 `_normalize_expected_hash` strips, lowercases and matches _HEX64 | bad hex raises ValueError, main parser.error | cheap |
| 11 | Match BUILD.json dep by path, not nearest ancestor | implemented | tools/check_terrain.py:238 dep accepted when `path` field matches resolved terrain path; bare-string deps still work | path mismatch now skipped | cheap |
| 12 | Declare NumPy dependency with clean error | implemented | tools/check_terrain.py:22 `import numpy as np` at module top with ImportError wrapped as SystemExit | mid-function import removed | cheap |
| 13 | Write report JSON with `allow_nan=False` | implemented | tools/check_terrain.py:267,270 both `json.dumps(report, indent=2, allow_nan=False)` | NaN would raise instead of being silently emitted | cheap |
| 14 | Make `build.py` invoke `guard_terrain()` as a gate | implemented | yellowstone_python/build.py:350-384 | build.py imports guard_terrain, invokes it on terrain.f32, and raises ValueError on any critical failure (size, grid, finite, range, hash, terrain-readable, import) | medium |

## Cross-project issues
- The guard sits in `tools/` while `build.py` imports from `.`-prefixed package modules; moving the guard into the package would unblock integration without a `tools` import.
- Terrain cell-size semantics are duplicated between `tools/check_terrain.py` (nothing) and `overland_flow.py` (`STEP = 4.0`); a shared metadata module would be needed.
- `BUILD.json` currently records `deps["terrain.f32"]` as a bare sha256 string, not a path+hash object; the fix's path-match proposal requires a schema change in `build.py:180-185`.

## Scientific validity flags
- Terrain datum is undocumented in both the file (`vertical datum unknown`) and `BUILD.json`, yet downstream slope, cross-section depth, and plume elevation computations treat the field as a true DEM.
- `check_terrain.py` reports only min/max/mean so a transposed, flipped, or shuffled grid of the same bytes passes every guard.
- The 1025x1025 array is consumed as both vertices (DEM) and cells (hydrology) elsewhere; the guard asserts neither convention, so a one-row shift between consumers can go undetected.
