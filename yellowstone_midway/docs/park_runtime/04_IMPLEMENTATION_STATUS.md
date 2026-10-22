# 04. Exact implementation status

## Headless checks in this repository on Godot 4.5.1

| Check | Result |
|---|---|
| `tests/park_runtime` Python tests (`yellowstone_python/tests/park_runtime`) | 106 passed |
| `tests/park_runtime/run_tests.gd` on the synthetic fixture | 10 checks, 0 failures |
| `tests/park_runtime/stream_midway_check.gd` on `data/park_composed` (1 m core plus master, feature pages) | 3066 checks, 0 failures; leaf heights equal the river-carved legacy core inside the core footprint (Python carve matches `core_terrain.gd` `_load_heights` to 7.9e-5 m over 361201 vertices) and the master raster outside it, worst 1.4e-6 m over 1520 boundary samples and 4.5e-5 m at 11 streamed stops; removed pool area equals each thermal polygon area; bridge decks clear the terrain; 214 resident tiles, 15.6 MiB estimate |
| `tests/park_runtime/field_codec_check.gd` on the Python golden packet | 9 checks, 0 failures |
| `tests/park_runtime/client_service_check.gd` against the reference service | 11 checks, 0 failures |
| Legacy `--smoke-test` after the install | unchanged |

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

Not yet done: GPU frame traces, material paging, streamed vegetation and wildlife, the
native engine adapter run, route geometry meshes and boardwalk supports (route chunks are
delivered as data only), the opt-in switch of `project.godot` and the streaming scene to
`data/park_composed/`, legacy walking validation against the streamed terrain, and every
item under Explicit integration work remaining below.

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

## Implemented GDScript, requiring local Godot validation

`world_frame.gd`, `terrain_job.gd`, `tile_visual.gd`, `demand_planner.gd`,
`terrain_streamer.gd`, `vegetation_batch.gd`, `field_buffer.gd`, `park_client.gd`,
`runtime_monitor.gd`, `streaming_demo.gd`, and the two test/benchmark scripts are
provided as actual source. No Godot executable was available in the build sandbox.
They have not been engine-compiled, physics-tested or GPU-profiled here.

The renderer implements perspective-camera demand, movement lookahead, soft
sampled terrain occlusion, all-direction coarse cover, asynchronous mesh arrays,
parent/child coverage, separate collision creation, guarded readiness and origin
shifting. It is not an orthographic/VR/multi-camera planner, texture streamer, cloud
renderer replacement or fully proven conservative occlusion solver.

## Implemented adapter, not integration-tested against the full native environment

`legacy_adapter.py` wraps the inspected LiveEngine. It intentionally requires that
engine's own worker be disabled. In-memory checkpoint/restore is connected to native
APIs. Durable native persistence is blocked until a safe versioned serializer exists.
It uses private methods at this baseline and must be ported to public wrappers/tests
as the migration guide specifies. The original solver is not replaced by a fixture.

## Explicit integration work remaining

- Make the opt-in real world use the new streamer without loading the giant scene.
- Compose the master/core height authority; preserve pool cuts, shorelines, routes,
  boardwalks and interaction geometry in bounded feature pages/jobs.
- Page canopy, forest-floor and wildlife sources; implement the specific near/mid/far
  representations and actor state subscriptions using the new batch/transport helpers.
- Port geographic materials, texture caches, atmosphere coordinates, maps and probes.
- Adapt native controls/UI and command-completion polling. The minimal client reports
  queued commands, not final acceptance. Connect hot native fields to the binary codec.
- Add native checkpoint serialization, real domain boundary coupling, numerical
  coarse/fine reconciliation and measured regional worker parallelism where justified.
- Add budget-driven automatic quality adaptation, larger bootstrap catalog paging,
  robust fast-travel preparation and more aggressive proven occlusion only after
  correctness tests. Current terrain pressure is reported rather than silently
  violating the configured accounting budget.

These are specific tasks in `01_CURRENT_FILE_EDITS.md`, not work that has already
been completed or tested in the user's checkout. This package makes no repository
changes, no FPS promises and no claim to finish the whole park's scientific models.
