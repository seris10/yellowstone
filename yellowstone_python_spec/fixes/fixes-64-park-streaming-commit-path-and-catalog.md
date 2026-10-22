# Park streaming commit path, catalog default and empty tile surfaces

## Scope

Defects in the opt-in park streaming runtime found while reviewing the
`fixes-63` result. The default world mode does not change; the promotion
gate in `docs/park_runtime/03_ACCEPTANCE.md` stays closed. No scientific
claim changes state.

## Findings and implementation

- Vegetation page reads on the main thread. `terrain_streamer.gd`
  `_commit_ready()` emits `tile_committed` inside the commit loop, and
  `vegetation_pager.gd` `_on_tile_committed()` runs synchronously on that
  signal: `FeatureSource.collect()` reads, hashes and parses every
  vegetation and forest-floor page meeting the tile and its halo
  (`feature_source.gd:56-60`), then builds the tile MultiMesh batches,
  the canopy window and the forest floor. The commit budget is tested
  only before each tile, so this work is unbounded inside one commit.
  The architecture contract assigns page reads to workers
  (`00_ARCHITECTURE_CONTRACT.md`, demand, preparation and commit). The
  `fixes-63` ledger attributes the 643 ms travel maximum to
  non-preemptible tile installs; the vegetation work runs inside the same
  measured interval. Implementation: the terrain worker job collects the
  vegetation and forest-floor records for leaf tiles and returns them
  with the tile data; the pager queues committed leaf tiles and builds at
  most one tile per frame from the prefetched records, outside the
  streamer commit loop; retirement drops queued tiles. The pager reports
  its queue length and its slowest build.
- Terrain-only default catalog. `project.godot` sets
  `park_streaming/catalog` to `res://data/park/catalog.json`, the
  master-only pack without the 1 m core or a feature index, and
  `world.gd` `_boot_streamed_world()` uses the same fallback. Enabling
  streaming alone boots terrain without pools, rivers, routes or
  vegetation; `vegetation_pager.gd:30-32` accepts a catalog without a
  feature index and pages nothing. The benchmarks edited the setting to
  `data/park_composed` and reverted it. Implementation: the setting and
  the fallback name `res://data/park_composed/catalog.json`; the main
  scene refuses a streaming catalog without a feature index with an
  explicit error. The standalone demo scene keeps accepting terrain-only
  catalogs.
- Invalid surfaces for water-covered tiles. Three core leaf tiles lie
  wholly inside thermal pools (`core:0:12:15` and `core:0:13:15` in
  `pool_1034_0`, `core:0:16:11` in `pool_1030_0`). The pool cut removes
  every triangle and every perimeter skirt edge lies over water, so
  `terrain_job.gd` returns 1089 vertices with an empty index array and
  `tile_visual.gd:15` `add_surface_from_arrays` fails with
  `Invalid array format for surface`. The tile still counts as committed
  and the failure counter stays at 0. Implementation: the job returns no
  terrain arrays for a fully cut tile and labels it water-covered; the
  tile installs without a terrain surface while keeping its heights,
  water surfaces and collision; a surface build that fails for any other
  tile is a commit failure recorded in the streamer failure map, with the
  parent tile left in place.

## Verification

- `stream_midway_check.gd`: zero failures; vegetation audit counts
  unchanged (per-tile records, canopy cells, floor records, 158,499-cell
  receipt) after waiting for the pager queue to drain; the run log
  carries no `Invalid array format for surface` error; the three
  water-covered tiles commit without a terrain surface.
- `ground_rebase_check.gd`, `run_tests.gd`, `field_codec_check.gd`
  stay at zero failures; `pytest tests/park_runtime` stays green.
- Streamer reports the slowest commit and the pager its slowest build in
  a headless stream run before and after the change, recorded as
  headless dummy-renderer timings. Visible-renderer frame times remain
  the performance protocol's measurement.
- Legacy boot with streaming off is unchanged.
- `check_comment_style.py` and the prose pattern checker clean on touched
  files.

## Sources

- `yellowstone_midway/scripts/park_runtime/terrain_streamer.gd`,
  `terrain_job.gd`, `tile_visual.gd`, `vegetation_pager.gd`,
  `feature_source.gd`; `scripts/world.gd`; `project.godot`.
- `fixes/ledger/fixes-63.md` (performance protocol row).
- `yellowstone_midway/docs/park_runtime/00_ARCHITECTURE_CONTRACT.md`.
