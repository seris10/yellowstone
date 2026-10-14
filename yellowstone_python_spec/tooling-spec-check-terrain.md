# Spec: tools/check_terrain.py — terrain.f32 hash/dims/range guard vs BUILD deps

Status: spec (authored 2026-10-10, pycl-2). Transferred claims cite file:line verified 2026-10-10; authored claims marked [AUTHORED].
No code written; no deletions. Target: `tools/check_terrain.py` in `../../yellowstone_python/`.

## 1. Purpose + non-goals

Purpose: guard the one input BUILD tracks only by hash. Today `build.py:155-162` records `deps["terrain.f32"] = sha256_file(...)` but NOT dims, dtype, size, or path — a truncated/corrupt `terrain.f32` with an updated hash builds silently, and a foreign grid of identical byte-size passes `load_terrain`'s only check (`h.size != GRID*GRID` → raise, `yellowstone_python/vegetation.py:141-142`). The file is NOT in the repo (verified: no `terrain.f32` under the project root) and lives only at `../../yellowstone_midway/data/terrain.f32` (4,202,500 bytes = 1025²×4, sha256 `8f5ca1bf…804b8520`, matching all 16 sampled `derived/*/BUILD.json`).

Non-goals: no re-baking terrain (game-side `yellowstone_midway/tools/prepare_world.py` owns that); no changing `load_terrain`; no asserting the vertical datum (undocumented in code — negatives to −10.89 exist unexplained).

## 2. CLI (`--help` text drafted)

```
usage: check_terrain.py [--terrain PATH] [--expect-sha256 HEX] [--out PATH]
       [--min-m F] [--max-m F]

Guard terrain.f32 against BUILD deps. Exit 0: all guards pass. Exit 1: guard
failure (report still written to --out when given). Exit 2: bad invocation.

options:
  --terrain PATH       f32 file (default: <world_root>/data/terrain.f32, with
                       world_root from configs/baseline.yaml:4 or $YELLOWSTONE_WORLD)
  --expect-sha256 HEX  required hash; defaults to BUILD-recorded hash when run
                       inside a build dir (see §4.6)
  --out PATH           write guard report JSON (atomic .tmp+replace)
  --min-m F            range floor (default: -20.0, see §4.4)
  --max-m F            range ceiling (default: 250.0, see §4.4)
```

## 3. Inputs / outputs with exact schemas

Input: `terrain.f32` — exact spec from code (`vegetation.py:23-25,138-143`): little-endian float32 (`dtype="<f4"`), `GRID=1025` → 1,050,625 elements → 4,202,500 bytes, no header, row zero north, sampling `gx=(x+HALF)/STEP` with `STEP=4.0, HALF=2048.0` (`vegetation.py:149-164`).

Measured data envelope (transferred, numpy `<f4` on the live file): min −10.889993667602539, max 238.130126953125, mean 46.139896392822266, median 22.3447265625, std 50.305206298828125, p1 −5.094217777252197, p99 221.2838897705078.

Output report schema `yellowstone.terrain_guard.v1` [AUTHORED]: `{schema, status, terrain: {path, sha256, nbytes, dims: [1025,1025], dtype: "<f4", min_m, max_m, mean_m}, expected_sha256, guards: [{name, passed, detail}]}`. Report `status`: `measured_remote_not_calibrated` is wrong (local file, not remote sensing) — use `authored_terrain_guard` [AUTHORED].

## 4. Algorithm / rules in numbered steps

1. Resolve path: `--terrain` else `$YELLOWSTONE_WORLD/data/terrain.f32` else `configs/baseline.yaml` `world_root` (`:4` = `../../yellowstone_midway`) + `/data/terrain.f32` (resolution chain mirrors `build.py:145,155-163` + `provenance.py:11-17`). Print resolved path in every verdict.
2. Size guard: `nbytes == 4202500` else fail `bad-size` (this is `load_terrain`'s own check, surfaced pre-read).
3. Dims/dtype guard: read `np.fromfile(path, dtype="<f4")`, require `size == 1050625`; reshape `(1025,1025)`. Failure → `bad-grid` with actual size.
4. Range guard: `min >= --min-m` and `max <= --max-m`. Defaults −20.0/250.0 cover the measured envelope (−10.89/238.13) with margin (−9.1/+11.9) and contain the robust p1–p99 (−5.09/221.28) [AUTHORED bounds, justified by §3 numbers; datum unknown so bounds are tripwires, not physical claims].
5. Hash guard: sha256 (streamed, cf. `provenance.py:20-25`) equals `--expect-sha256` else fail `hash-mismatch` showing both hashes.
6. BUILD cross-check [AUTHORED]: when `--terrain` is under a `derived/<bid>/` build tree, compare against that tree's `BUILD.json` `deps["terrain.f32"]` key (exact key from `build.py:155-162`); mismatch → `build-dep-mismatch`.
7. Write report atomically; exit 0 iff all guards pass.

## 5. Provenance plan

Report `status: authored_terrain_guard` (new string, defined here). The tool never modifies terrain or BUILD records; it only reads. Record the world checkout identity problem honestly: `world_root` path is recorded, and the spec notes the file is outside version control — the hash is the identity.

## 6. Error handling

| Failure mode | Exit | Message |
|---|---|---|
| Bad flags / unresolvable world_root | 2 | `parser.error` |
| File missing/unreadable | 1 | `terrain-unreadable: <resolved path>: <exc>` |
| Size/grid/range/hash mismatch | 1 | `<guard>: expected <x>, found <y>` |
| `--out` unwritable | 1 | report to stdout |

## 7. Tests (synthetic/offline only)

1. `test_good_fixture_passes` — synthetic 1025² `<f4` file in-range with matching `--expect-sha256` → exit 0. (Writes ~4 MB to tmp dir; acceptable, cleaned up.)
2. `test_truncated_fails_size` — 1000-float file → `bad-size`, exit 1.
3. `test_wrong_count_fails_grid` — 1025×1024 file (same dtype, off-by-one row) → `bad-grid`.
4. `test_out_of_range_fails` — fixture with max 999.0 → range failure naming actual max.
5. `test_hash_mismatch_names_both` — good grid, wrong expected hash → both hashes in output.
6. `test_defaults_justify_envelope` — asserts defaults (−20/250) contain the recorded live min/max (−10.89/238.13) with margin [AUTHORED regression pin].
7. `test_missing_file_exit1` — nonexistent path → `terrain-unreadable`, exit 1 (not 2).

## 8. Acceptance criteria

- [ ] Default path resolution cites `baseline.yaml:4` + `$YELLOWSTONE_WORLD` override (`build.py:528-530`).
- [ ] All guards cite `vegetation.py` lines; range defaults cite §3 measured numbers.
- [ ] No new dependency (numpy already required); suite green.

## 9. Effort + dependencies

Effort: S (~100 lines + tests). Dependencies: none new. Open question: vertical datum/units of values and the `HALF=2048.0` vs `GRID*STEP=4100 m` 4 m discrepancy — recorded as NOT verified; resolving needs the game-side bake script, out of scope.
