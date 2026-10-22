===
# Park streaming commit path, catalog default and empty tile surfaces ledger

Specification: `fixes/fixes-64-park-streaming-commit-path-and-catalog.md`.

Baseline ledger written at document creation with every row `missing`;
rows updated with the implementation and its evidence.

| Item | Verdict | Implementation and evidence |
|---|---|---|
| Vegetation page reads on the main thread | implemented; build cost remains | Baseline: `vegetation_pager.gd:41-80` read pages and built batches inside the `tile_committed` signal emitted at `terrain_streamer.gd:206`. `terrain_job.gd` now collects vegetation and forest-floor records for leaf tiles in the worker and returns them as `vegetation_records`; `tile_visual.gd` keeps them on the tile; `vegetation_pager.gd` queues committed leaf tiles, builds `max_builds_per_frame` (1) per frame in `_process` from the prefetched records, drops queued tiles on retirement, and reports `pending_count()`, `build_ms_max` and `build_ms_total`. `stream_midway_check.gd` waits for the queue to drain before the vegetation audit. Headless dummy-renderer timings, same check: streamer `commit_ms_max` 8321.9 ms before, 97.8 ms and 51.6 ms after (two runs). The work moved out of the commit loop without disappearing: the first pager build takes 7361-9706 ms (cold shared-asset load) and the remaining 73 builds average about 63 ms (`build_ms_total` 14313.7 ms over 74 tiles). Both stay far above the 1.5 ms provisional commit target; visible-renderer frame times are not measured here. |
| Terrain-only default catalog | implemented | Baseline: `project.godot:270` and `world.gd:303` named `res://data/park/catalog.json`. Both now name `res://data/park_composed/catalog.json`; `_boot_streamed_world()` refuses a catalog without a feature index with an explicit error. A boot refusal under `--smoke-test` prints `SMOKE ok=false boot=refused` and exits 1; before, the process never quit. Verified with a temporary `override.cfg`: terrain-only catalog exits 1 with the error; composed-catalog streamed smoke `SMOKE ok=true`; legacy smoke `SMOKE ok=true`. |
| Invalid surfaces for water-covered tiles | implemented | Baseline: `terrain_job.gd` returned 1089 vertices with an empty index array for `core:0:12:15`, `core:0:13:15` (`pool_1034_0`) and `core:0:16:11` (`pool_1030_0`); `tile_visual.gd:15` logged `Invalid array format for surface` with the failure counter at 0. The job now returns no terrain arrays and `water_covered=true` for a fully cut tile; `install()` skips the terrain surface for it and returns false when any other surface fails; `terrain_streamer.gd` records that failure in `_failures`, emits `stream_error` and leaves the parent resident. `audit_skirts` asserts no terrain arrays and a fully omitted skirt for the three tiles. Run logs carry no `Invalid array format for surface`. |

Gates after implementation (Godot 4.5.1 headless): `stream_midway_check.gd`
0 failures (3562 and 3439 checks over two runs; the count varies with
residency timing), `ground_rebase_check.gd` 272/0, `run_tests.gd` 10/0,
`field_codec_check.gd` 9/0; `pytest tests/park_runtime` 115 passed;
`check_comment_style.py` and the prose pattern checker clean on touched
files. The streamed smoke ran before the final `world.gd` refusal-exit
edit, which touches only the refusal path.
