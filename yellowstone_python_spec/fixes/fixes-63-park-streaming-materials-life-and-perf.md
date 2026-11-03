# Park streaming materials, life layers and performance evidence

## Scope

Promotion-track work for the opt-in park streaming runtime.
`fixes-62` landed the streamed boot branch behind
`park_streaming/enabled` (default off) with both gates green. Streamed
mode still renders the fallback terrain material, carries no feature
layers (pools, shorelines, routes), and pages no vegetation or wildlife.
This document covers the edit-map sections B, C and D
(`docs/park_runtime/01_CURRENT_FILE_EDITS.md`) and the performance
protocol evidence (`docs/park_runtime/03_ACCEPTANCE.md`). The default
world mode does not change; the promotion gate stays closed under this
document. No scientific claim changes state.

## Findings and implementation

- Shared geographic terrain material (section C). Streamed tiles render
  the streamer's fallback `StandardMaterial3D`; the real ground
  compositor (`shaders/ground_surface.gdshaderinc` bound through
  `scripts/terrain_materials.gd`) runs only on the legacy baked tiles.
  Port the material system per C1: one shared ground material whose
  repeat phases follow the `WorldFrame` origin (the phase contract and
  `DETAIL_PHASES` write path from `fixes-62` gate 2 are the mechanism),
  passed to the streamer as `shared_terrain_material` at the
  `_boot_streamed_world()` call site (`world.gd`), replacing the
  documented `null` fallback. Atmosphere coordinates follow C2:
  `yellowstone_atmosphere.gd` and its canonical counterpart must read
  site-absolute positions so fog, sun and weather stay fixed across
  rebases. Origin-zero output stays bit-identical to the legacy material.
- Terrain feature authority (section B). Streamed mode renders terrain
  only: pool cuts, shorelines, routes and boardwalk geometry are absent,
  and the composed pack's feature pages
  (`data/park_composed/features/`) have no consumer. Implement the
  section B items: height authority composition so the
  streamed core matches the carved core terrain, feature-page jobs that
  produce route and water geometry within the commit budget, and the
  `bake_world.gd` split that emits per-tile feature pages alongside the
  single world mesh used by the legacy bake. `core_terrain.gd` and `water_polygon_cut.gd` keep their legacy
  semantics; `validate_core_cut.gd` and `stream_midway_check.gd` define
  parity.
- Vegetation paging (sections D1-D4). Page the lodgepole batches,
  canopy surface, forest floor and tree submission per tile:
  `lodgepole_library.gd` impostor batches become tile-scoped MultiMesh
  sources, `canopy_surface.gd` publishes per-tile cell subsets,
  `forest_floor.gd` and `forest_floor_geometry.gd` stream their authored
  beds and logs by tile, and `tree_submission.gd` compaction operates on
  resident tiles. The batch-3 display exclusions and the
  `fixes-57` LOD/dither budgets hold per tile; `validate_multimesh.gd`
  and the canopy validators stay green against the legacy scene.
- Wildlife paging (section D5). Actors subscribe to tile residency:
  spawn on admission, suspend on eviction, and reconstruct visual phase
  from persistent stores on revisit, per the regression matrix row
  (revisit hidden wildlife keeps persistent IDs; no duplicate animals,
  no reset consumption). `wildlife_actor.gd` and
  `wildlife_motion_controller.gd` keep their motion models.
- Performance protocol evidence. Run `tests/park_runtime/benchmark_route.gd`
  in a visible renderer on legacy and streamed scenes with the protocol's
  recorded conditions (hardware, OS, engine, renderer, viewport, AA,
  shadows, revision, scenario, route, seed, warmup): boot, warm steady
  views, continuous travel, teleport recovery as separate workloads;
  p50/p95/p99 and maximum frame times; CPU script and GPU time separate;
  resource creation and retirement spikes; resident memory across
  repeated routes. Add a walker-driven route for collision deadlines and
  predictive loading, and a georeferenced route JSON for the integrated
  scene per the protocol. Targets are provisional engineering targets
  (16.67 ms frames at 60 Hz, 1.5 ms main-thread commit budget, no steady
  resident growth), recorded as measured results with their conditions.
- Regression matrix execution. Run the 19-case matrix from
  `03_ACCEPTANCE.md` against the integrated scene: 180-degree turn,
  ridge gap, crest arrival, parent-to-children cover, corrupt child page,
  revisit residency plateau, origin shift during jobs, collision delay,
  tile seam raycast, teleport, hidden upstream region, hidden wildlife
  revisit, intervention during lookahead, worker failure, service
  restart, accelerated time, native adapter parity, and core/water
  parity. Each case records its required observation; failures block the
  promotion gate by name.

## Verification

- `stream_midway_check.gd` 3066/0 and `ground_rebase_check.gd` 235/0
  stay green after every layer lands.
- Material port: rebase render check with the shared material on a
  visible renderer; legacy smoke test values unchanged.
- Feature parity: `validate_core_cut.gd`, `validate_river_surface.gd`,
  `validate_river_junctions.gd` against the composed pack; streamed-mode
  captures at the bridge and pools compared with legacy captures.
- Vegetation/wildlife: `validate_multimesh.gd`, canopy validators,
  revisit test showing persistent wildlife IDs.
- Benchmark JSON artifacts recorded under `evidence/` with the full
  condition list; memory plateau demonstrated over repeated routes.
- The 19-case matrix produces a recorded pass/fail table; any failure
  is named in the ledger.
- `python3 -m pytest -q` green; `check_comment_style.py` and
  the prose pattern checker clean on touched files.

## Sources

- Edit map: `yellowstone_midway/docs/park_runtime/01_CURRENT_FILE_EDITS.md`
  sections B, C, D.
- Acceptance and measurement:
  `yellowstone_midway/docs/park_runtime/03_ACCEPTANCE.md` (regression
  matrix, performance protocol, promotion gate).
- Remaining-work inventory:
  `yellowstone_midway/docs/park_runtime/04_IMPLEMENTATION_STATUS.md`.
- Gate baselines: `fixes/ledger/fixes-62.md`.

Benchmark numbers are measured artifacts with recorded conditions, and
targets stay provisional until measured. The promotion gate
(`03_ACCEPTANCE.md`) governs any later default-mode change; this
document does not open it.
