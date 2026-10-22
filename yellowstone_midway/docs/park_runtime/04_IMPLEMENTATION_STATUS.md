# 04. Exact implementation status

## Headless checks in this repository on Godot 4.5.1

| Check | Result |
|---|---|
| `tests/park_runtime` Python tests (`yellowstone_python/tests/park_runtime`) | 115 passed |
| `tests/park_runtime/run_tests.gd` on the synthetic fixture | 10 checks, 0 failures |
| `tests/park_runtime/stream_midway_check.gd` on `data/park_composed` (1 m core plus master, feature pages) | 0 failures (3439 to 3580 checks; the count varies with residency timing); leaf heights equal the river-carved legacy core inside the core footprint (Python carve matches `core_terrain.gd` `_load_heights` to 7.9e-5 m over 361201 vertices) and the master raster outside it, worst 1.4e-6 m over 1520 boundary samples and 4.5e-5 m at 11 streamed stops; removed pool area equals each thermal polygon area; bridge decks clear the terrain; three water-covered leaf tiles carry no terrain surface; route meshes, pool and river surfaces, vegetation, canopy, forest floor and wildlife revisit audited per tile; 121 resident tiles, 10.4 MiB estimate |
| `tests/park_runtime/ground_rebase_check.gd` | 272 checks, 0 failures |
| `tests/park_runtime/field_codec_check.gd` on the Python golden packet | 9 checks, 0 failures |
| `tests/park_runtime/client_service_check.gd` against the reference service | 11 checks, 0 failures (not rerun since the package install) |
| `--smoke-test` with streaming off and on (`data/park_composed`) | `SMOKE ok=true` in both; a catalog without a feature index exits 1 |

Two defects in the supplied GDScript were found by running it and are fixed here:
the planner returned an untyped array where `Array[String]` is declared, and the field
decoder rejected every valid packet because Godot parses JSON integers as floats.

Terrain composition: `terrain_pack --core-dir data/core_terrain --world data/world.json`
packs the master raster outside a 1024 m window and the 1 m core inside it as 61 roots with no
overlap and no gap, plus shoreline, pool-cut and route pages under `features/`. With `--world`
the core block also receives the authored river bed carve from the world.json rivers, matching
the legacy `_load_heights` semantics; the carve keeps the stitched outermost vertex ring fixed
to the master surface, and the carve report rides in the core source provenance. The
pack is `data/park_composed/`; `data/park/` stays the master-only baseline.

Done since the package install (`fixes-62` to `fixes-64` ledgers): the streamed boot
branch behind `park_streaming/enabled` (default off) reading `data/park_composed`, the
shared ground material, pool, river and route geometry with collision, vegetation and
wildlife paging, and the performance protocol runs (`evidence/park-streaming-benchmark-*`).
Not yet done: GPU-millisecond attribution, the 18-case regression matrix of
`03_ACCEPTANCE.md`, main-thread vegetation build cost, steam for streamed thermal pools,
the service wiring that feeds native engine state to `ParkClient`, and the items under
Explicit integration work remaining below.

## Implemented source, exercised by Python tests

| Component | Scope |
|---|---|
| `contracts.py` | Coordinate conversion, validated interest messages, dependency closure |
| `terrain_pack.py` | Out-of-core-capable source input, paged dyadic hierarchy, triangulated error, shared samples, immutable hashes, non-overlap checks |
| `forcing.py` | Shared prescribed timeline, exact interval integration for supported interpolation modes |
| `reference_network.py` | Illustrative conservative branching reservoirs, confluences, water/heat/solute ledgers |
| `coupling.py` | Conservative extensive-state split/merge and exactly-once interface accounting |
| `runtime.py` | Common frontier, atomic domain advance, retained history, intervention rollback, filtered bracket, committed saves |
| `state_store.py` | Atomic SQLite checkpoints/events, integrity checks and model-version guards |
| `service.py` | Loopback worker-owned service, bounded commands/publications and independent rendering |
| `field_codec.py` | Bounded binary numeric field-pair codec |

The test report records **34 passed** at the final package validation. See the
final report for any subsequent additions/reruns. Scientific tests apply to the
reference numerical fixture and orchestration contracts, not new park predictions.

## Implemented GDScript, compiled and run on Godot 4.5.1

`world_frame.gd`, `terrain_job.gd`, `tile_visual.gd`, `demand_planner.gd`,
`terrain_streamer.gd`, `vegetation_batch.gd`, `field_buffer.gd`, `park_client.gd`,
`runtime_monitor.gd`, `streaming_demo.gd`, the pagers and the tile builders compile and
run in the headless checks above and in the visible-renderer benchmarks. GPU time is not
attributed.

The renderer implements perspective-camera demand, movement lookahead, soft
sampled terrain occlusion, all-direction coarse cover, asynchronous mesh arrays,
parent/child coverage, separate collision creation, guarded readiness and origin
shifting. It is not an orthographic/VR/multi-camera planner, texture streamer, cloud
renderer replacement or fully proven conservative occlusion solver.

## Native engine adapter

`legacy_adapter.py` wraps LiveEngine through its public checkpoint, restore, export and
import methods and requires that engine's own worker be disabled. Durable persistence
uses `LiveEngine.export_state`/`import_state`; `test_live_state_persistence.py` covers a
bit-identical resume on a fresh engine, refusal of other builds and source drift, and
native against adapter parity. The original solver is not replaced by a fixture. The
game does not yet run the adapter: `ParkClient` connects without consuming snapshots.
Simulation residency at park scale is specified in
`yellowstone_python_spec/04_PARK_STREAMING_SPEC.md` section 7.1.

## Explicit integration work remaining

- Far representations for non-resident vegetation, the far-LOD material variant and a
  per-page texture cache; maps and probes in streamed mode.
- Adapt native controls/UI and command-completion polling. The minimal client reports
  queued commands, not final acceptance. Connect hot native fields to the binary codec.
- Add real domain boundary coupling, runtime domain add and remove, numerical
  coarse/fine reconciliation and measured regional worker parallelism
  (`04_PARK_STREAMING_SPEC.md` section 7.1).
- Add budget-driven automatic quality adaptation, larger bootstrap catalog paging,
  robust fast-travel preparation and more aggressive proven occlusion only after
  correctness tests. The streamer reports terrain budget pressure in its
  stats.

These are specific tasks in `01_CURRENT_FILE_EDITS.md` and the park streaming
specification. Nothing here promises a frame rate or finishes the whole park's
scientific models.
