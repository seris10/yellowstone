# Park streaming vegetation build cost

## Scope

Main-thread vegetation construction in the opt-in park streaming runtime,
left open by `fixes-64`: the first pager build loaded every shared
vegetation asset inside one frame, and each later build computed instance
transforms, canopy skin arrays and cluster buffers on the main thread. The
default world mode does not change; the promotion gate in
`docs/park_runtime/03_ACCEPTANCE.md` stays closed. No scientific claim
changes state, and the streamed batches stay byte-identical to the
`fixes-64` output.

## Findings and implementation

- Cold shared-asset load inside the first tile build. The first
  `vegetation_pager.gd` build loaded the lodgepole metadata, every
  archetype's LOD scenes, architecture variants and impostor texture
  arrays, the grass, rock and log meshes, the forest-floor assets and the
  canopy display source. A headless probe attributes 18.5 s of cold time
  to `CanopySurface.window_source()` (source verification plus 5 m display
  smoothing over the 640 x 640 grid) and about 6 s to the tree assets,
  of which 3.6 s is impostor cutout reads. Implementation: the pager
  prepares shared assets during the streamed boot hold. Worker tasks read
  and smooth the canopy source (`CanopySurface.prepare_window_data()`) and
  read verified cutout mip chains one archetype at a time
  (`Lodgepole.read_cutout_image()`); the main thread installs one asset
  group per frame (tree form, ground cover, canopy textures and cluster
  meshes, bole support profiles). Tile builds wait for preparation, and
  `world.gd` releases the boot hold only when collision is ready and
  preparation has settled. A failed preparation reports an explicit error
  and releases the hold without vegetation.
- Canopy preparation loops. `read_source()` and `_prepare_surface()` read
  dictionary entries inside per-cell loops and recomputed the smoothing
  distance with `pow()` per neighbor. Implementation: typed local arrays
  and a precomputed kernel built with the same expression. Output arrays
  are bit-identical (SHA-256 of corner heights, normals, cover, cell and
  mask data unchanged).
- Per-tile canopy cluster scan. `_build_clusters()` iterated the full
  409,600-cell grid for every tile and filtered by window. Implementation:
  the scan iterates the window rows and columns only, in the same order.
- Main-thread instance math. Tree batches computed `local_transform`,
  `display_dimensions` and two SHA-256 identity keys per record per batch
  on the main thread; canopy skin arrays, cluster buffers and forest-floor
  transforms were also main-thread work. Implementation: each committed
  leaf tile runs a worker plan job (`PlanJob` in `vegetation_pager.gd`)
  that produces instance buffers, bounds, collider parameters and skin
  arrays from plain data: `TileVegetation.plan_tile()` against batch
  descriptors registered during preparation, `CanopySurface.plan_window()`
  with bole profiles cached by `canopy_support.gd`, and
  `ForestFloor.plan_window()` with mesh bounds cached at asset creation.
  The main thread creates the MultiMesh, mesh, node and collider objects
  (`install_tile`, `install_window`), at most one tile per frame, in
  commit order. Retired tiles discard their pending plans. The worker
  reads the terrain worker's prefetched records; the terrain job itself is
  unchanged, so terrain and collision readiness do not wait on vegetation.
- Bake-path canopy clusters. The `fixes-63` shared-mesh change to
  `_build_clusters()` broke out of the LOD mesh loop after the first mesh
  when no shared meshes were passed, so the offline bake path raised an
  out-of-bounds index after one cluster node. Implementation: the guard
  tests the shared-mesh argument.
- Forest-floor snag materials. Floor snags duplicate the shared snag
  meshes; the baked scene keeps their source `StandardMaterial3D`.
  Preparation builds the floor assets before the tree-form binding, so the
  streamed floor matches the baked scene independent of tile order.

## Verification

- Byte identity of streamed batches: a per-tile fingerprint (node names,
  positions, LOD ranges, shadow mode, metadata, MultiMesh buffers and
  bounds, surface material classes, skin arrays, collider shapes) over 60
  resident leaf tiles at three stops matches the `fixes-64` code on all 60.
- Byte identity of the bake path: `CanopySurface.build()` and
  `ForestFloor.build()` fingerprints match the branch code with only the
  cluster guard fix applied.
- Gates: `stream_midway_check.gd`, `ground_rebase_check.gd`,
  `run_tests.gd`, `field_codec_check.gd`, legacy and streamed smoke (the
  streamed smoke asserts vegetation preparation settled without error and
  at least one built tile), `validate_canopy_surface.gd`,
  `validate_canopy_attachments.gd`, `validate_multimesh.gd`,
  `pytest tests/park_runtime`, `check_comment_style.py` and the prose
  pattern checker on touched files.
- Timings are headless dummy-renderer timings from the stream check.
  Visible-renderer frame times remain the performance protocol's
  measurement.

## Sources

- `yellowstone_midway/scripts/park_runtime/vegetation_pager.gd`,
  `tile_vegetation.gd`, `tile_visual.gd`; `scripts/canopy_surface.gd`,
  `canopy_support.gd`, `forest_floor.gd`, `lodgepole_library.gd`,
  `world.gd`; `tests/park_runtime/stream_midway_check.gd`.
- `fixes/ledger/fixes-64.md` (vegetation paging row).
- `yellowstone_midway/scenes/authored_world.tscn` (baked floor snag
  materials, 918 canopy cluster nodes).
