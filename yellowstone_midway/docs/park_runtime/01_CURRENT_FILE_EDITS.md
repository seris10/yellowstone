# 01. Specific edits to the current Yellowstone files

Baseline: `c2b4c7923a6eeed61e2feca3946555826849ec67`. Paths below are repository-relative.
Use symbol anchors, not blind line-number replacements. This document is an ordered
implementation worklist for an agent with the actual checkout. New scripts are in
`overlay/`; the edits below are deliberately not applied to the repository by this
package. Some are substantial integrations, not one-line substitutions.

## A. Project settings and boot: opt-in before replacement

### A1. `yellowstone_midway/project.godot`

Inside the existing `[yellowstone]` section add:

```ini
park_streaming/enabled=false
park_streaming/catalog="res://data/park/catalog.json"
park_streaming/max_inflight=2
park_streaming/resident_limit_mib=128.0
park_streaming/commit_budget_ms=1.5
park_streaming/live_url="http://127.0.0.1:8766"
```

Leave the Mobile renderer, physics gravity, input mappings and current main scene
unchanged for the first integration. Do not attempt to prove a streaming improvement
by simultaneously reducing resolution, removing foliage or changing the shadow
preset. Those are separate controlled experiments.

The supplied `scenes/park_streaming_demo.tscn` can be opened explicitly without
editing `run/main_scene`. Its source data is synthetic and its material diagnostic.
Add `*.f32,*.json` to the non-resource export include filter when creating an export
preset: these inputs are read with FileAccess, not imported Godot Resources.

### A2. `yellowstone_midway/scripts/world.gd`

Add these preloads and fields next to the current preloads/state:

```gdscript
const ParkFrame = preload("res://scripts/park_runtime/world_frame.gd")
const ParkTerrain = preload("res://scripts/park_runtime/terrain_streamer.gd")
const ParkClient = preload("res://scripts/park_runtime/park_client.gd")
var park_frame = ParkFrame.new()
var park_terrain: Node3D
var park_client: Node
var park_enabled: bool = false
```

**Extract, do not delete, the legacy loader.** In `_ready()`, move the contiguous
`ResourceLoader.exists("res://scenes/authored_world.tscn")` branch into
`_load_legacy_authored_world() -> bool`. This includes the `AuthoredVegetation`
validation, `CanopySurface.refresh_geometry`, handcrafted/botanical loads and
foliage collection. Preserve its exact legacy behavior when the flag is false.

**Reorder the common boot safely.** The streamed branch needs a camera before
request planning, unlike the current full-world loader. Its order must be:

1. Validate/activate the source release and load small world metadata.
2. Create the environment and the single simulation adapter, initially clock-held.
3. Create the walker disabled; read its selected anchor as absolute site coordinates.
4. Create `ParkTerrain`, configure it against the immutable tile catalog and the
   walker's camera, and bind the movement guard described in A3.
5. Prepare the destination's terrain, collision and feature layers; then release
   the walker and present the scene. Do not spawn against a guessed height.
6. Start common atmosphere/audio/UI services. Subscribe them to accepted snapshots.

Configure the supplied streamer with actual property names:

```gdscript
park_terrain = ParkTerrain.new()
park_terrain.name = "ParkTerrain"
add_child(park_terrain)
park_terrain.max_inflight = int(ProjectSettings.get_setting("yellowstone/park_streaming/max_inflight", 2))
park_terrain.resident_limit_mib = float(ProjectSettings.get_setting("yellowstone/park_streaming/resident_limit_mib", 128.0))
park_terrain.commit_budget_ms = float(ProjectSettings.get_setting("yellowstone/park_streaming/commit_budget_ms", 1.5))
var catalog: String = str(ProjectSettings.get_setting("yellowstone/park_streaming/catalog", ""))
var ok: bool = park_terrain.configure(catalog, park_frame, player.camera, shared_terrain_material)
# shared_terrain_material must be built from the ported real material system, not
# the diagnostic material. Keep the walker disabled until preparation succeeds.
```

`shared_terrain_material` is a required integration product from section C, not a
symbol that already exists in `world.gd`. Do not paste this snippet without building
and testing that material. Source catalog parsing is a boot operation; tile reads
and mesh construction are asynchronous afterwards.

In a world-root `_physics_process`, before the walker moves, call
`park_frame.maybe_rebase(player)` and update `park_terrain.velocity = player.velocity`.
Register the walker with `park_frame.register_root(player)` exactly once. **Do not
register the streamer itself**: it rebuilds tile/body local positions from absolute
descriptors on the rebase signal. Register either a feature root or its children,
never both. Review processing priorities so rebasing precedes all movement queries.

**Remove these operations only from the streamed branch:** full authored-world load;
whole-canopy geometry refresh; full-scene material scans; `TreeSubmission.configure`;
`build_core_terrain()`'s full core build/cut pass; bulk `make_wildlife()`; whole-census
loads merely to populate hidden UI. Retain all of them in legacy mode until their
streamed counterparts pass parity tests. There must never be two overlapping copies
of the same terrain/collision in streamed mode.

Update these existing methods rather than leaving accidental legacy calls:

| Symbol | Specific streamed-mode change |
|---|---|
| `collect_foliage_materials` | Apply only to newly attached bounded layer batches. Register/unregister shared material identities; no traversal of the entire world on every chunk arrival. |
| `collect_terrain_materials` | Register the shared terrain material(s) when created, not by scanning nodes. |
| `build_core_terrain` | Legacy-only full-scene method. Streamed core composition and water cutting use section B. |
| `make_wildlife` | Replace bulk roster instantiation with visible/local actor subscriptions, preserving Python state and IDs. |
| `_process` | Read physical time from accepted service snapshots. Do not both advance `ecosystem` and adopt a second client time. UI refresh can remain throttled. |
| `_sync_atmosphere_clock` | Use the one adapter's accepted physical time, pause/hold flag and epoch. Camera movement is never an input to this clock. |
| `setup_python_runtime` | Select either the legacy client or ParkClient. Do not bind both to the same model controls. |
| `_python_frames` / `_python_control` | Translate to the revisioned packet/command schema; wait for command completion, not merely HTTP 202. |
| `_reload_generation` / `_published_changed` | Source revision change creates a new streaming generation. Cancel jobs, retain an old valid cover until replacement is ready, then swap. Do not mix terrain from two dataset revisions. |
| `go_to_anchor` | Convert anchor to absolute site coordinates; request destination; wait for collision/features; commit teleport; update absolute spawn. No naked relocation. |
| `refresh_env_caches` | Maintain resident-layer registries by attach/detach signals. Do not equate "no currently visible nodes" with "no simulated rivers". |
| `update_notes`, `map_view`, probe calls | Convert local camera/player coordinates to absolute site coordinates before scientific queries. |

Do not create an empty node named `AuthoredMidway` just to satisfy legacy lookups or
tests. Parameterize feature access and write streamed-mode assertions instead.

### A3. `yellowstone_midway/scripts/player.gd`

The current `_physics_process` resets outside `abs(position.x/z)>2038`. Keep that
only for legacy mode. Streamed mode checks dataset coverage and collision readiness,
not the original Midway square. Keep gravity, capsule, input mappings, step assist
and movement behavior otherwise unchanged.

Add an optional `stream_provider: Node`, a `coordinate_frame: RefCounted`, and
absolute spawn scalars. Immediately before the normal `move_and_slide()` call,
check the complete capsule footprint and predicted segment:

```gdscript
if stream_provider != null:
    var next_position: Vector3 = global_position + velocity * delta
    if not stream_provider.can_enter(next_position, 0.5):
        velocity = Vector3.ZERO
        return  # Hold safely; input/camera/rendering still run.
```

The supplied guard checks a footprint at the destination. For brisk/flight modes
or large physics deltas, subdivide the **swept segment** at no more than half a leaf
width; otherwise a fast move could jump over an unprepared gap. Add a bounded
maximum step/delta policy instead of an unbounded collision loop.

A missing streamed height is `NAN`, not zero. Maintain an on-screen loading/coverage
reason while movement is held. Fly mode may move without walking collision only
when explicitly selected; returning to walking requires prepared collision first.

`place_at()` must accept/convert absolute anchor coordinates in streamed mode and
recompute its local spawn on rebase. The old cached `spawn: Vector3` is not an
absolute position. Update `_try_step_up` exclusions/query coordinates only as needed;
its raycasts remain in current local physics space.

## B. Terrain, source authority, routes and water

### B1. `scripts/height_field.gd` and `scripts/rendered_ground.gd`

Retain the legacy fixed-raster implementation for legacy validation. Add a separate
provider parameter/constructor path for streamed mode. The sampled coordinate API
must say explicitly whether it accepts absolute site coordinates or local render
coordinates; the scientific-facing form should accept double scalar `x_m,z_m`.

Separate `sample_authoritative_height(x,z)` from `sample_resident_visual_height(x,z)`.
A distant low-LOD mesh is not the authoritative DEM. Walker contact can use
`ParkTerrain.height_at` only when its leaf collision is ready. Distant environmental
models query their own source fields in Python and must not depend on whether a
Godot collision tile is resident.

Preserve the current b-c triangle interpolation convention. Test against actual
Godot HeightMapShape3D raycasts on both halves of a cell in the chosen physics backend.
Do not change terrain interpolation to bilinear merely because it looks smoother.

### B2. `scripts/core_terrain.gd` / `scripts/water_polygon_cut.gd`

The current `build`, `_build_mesh_tile`, `_build_collision_tile`, `cut_master_tiles`,
`_prepare_render_cut` and `cut_open_water` operate on one full core scene. They are
not called from streamed startup.

Port the source composition into a tile-window provider with explicit inputs:
master heightfield, core heightfield, core microrelief, core/stitch metadata and
source masks. Preserve the 1 m core authority and its 2 m visual decimation choices
until an intentional replacement passes the existing contact/cut tests. The supplied
`terrain_pack.py` packs one already composed raster resolution; it does **not** compose
this core for you. Running it on `terrain.f32` alone proves infrastructure, not parity.

Required implementation steps:

1. Extract metadata validation and height-window sampling from `_load_metadata` and
   `_load_heights` into pure data functions. No Node or ArrayMesh creation in workers.
2. Build source tiles for the core and master with a non-overlapping ownership map.
   Use a common fine lattice or an explicit composite provider. Never append an
   overlapping core root to the supplied catalog: `build_pack` deliberately rejects
   overlapping root coverage.
3. Refactor water polygon subtraction to accept raw arrays plus only intersecting
   local pool/river polygons. Keep its robust polygon/orientation tolerances. Index
   polygons by tile with a border halo. Run array operations in the preparation job;
   create the final ArrayMesh only during the commit phase.
4. Preserve separate terrain, shoreline and water surfaces. Skirts must not appear
   across an intentional open-water cut. They belong on inter-tile outer edges only.
5. Prepare collision from the same accepted source geometry. Do not use visual skirts
   or a temporary coarse parent as the finest collision authority.
6. Commit terrain, required shoreline pieces and physical supports as one dependency
   group before enabling walking there.

Do not put the whole current core cutter in `_commit_ready`: that merely relocates
its stall onto a new function name. Profile the size of each worker input and each
main-thread resource creation.

### B3. `tools/bake_world.gd`

Keep `bake()` and `bake_vegetation_only()` as legacy/reference tools, clearly labeled.
Do not expand `authored_world.tscn` to encompass the park. The new path prepares
source packs and shared asset libraries, then constructs bounded geometry at runtime.

Extract reusable **data** authoring from `make_routes`, `make_water`, vegetation
placement/override resolution and collision descriptors. Preserve source identities,
protected input hashes, road/water widths and georeferenced points. Route chunks
need overlap/continuity metadata so a boardwalk does not end at a tile edge. The
runtime requires those feature pages before opening a walkable destination. The
source elevation compiler is already provided; the feature-page compiler and
layer-specific runtime adapters are explicit migration work, not claimed complete.

## C. Materials and atmosphere: preserve geography during rebasing

### C1. `scripts/terrain_materials.gd`, `shaders/ground_surface.gdshaderinc`,
`shaders/terrain.gdshader`, `shaders/thermal_apron.gdshader`

Replace hardcoded `(p.xz + vec2(2048.0))/4096.0` and fixed core extents with
layer-relative origins/extents supplied by the current source page. Each texture
layer needs a coverage rectangle, units, source hash, no-data policy and LOD.

For each layer, upload its **origin relative to the current render origin**, then
compute `(local_world_xz - layer_origin_render_xz)/layer_extent_m`. Do not add full
UTM values inside a float32 shader. For repeating fine textures, calculate the
absolute-origin phase modulo their repeat period on the CPU; update that phase only
on rebase or source changes. Otherwise a rebase makes bark, ripples or ground detail
slide across the world.

Keep macro geographic appearance available at coarse LOD. Add a separately compiled
far material without the current complete near-field texture stack. Switch by
projected error/distance only after screenshots show acceptable continuity. Keep
pigment, snow and water physics separate from visual blending. `mat_surface.gd`'s
republish blend applies to changed field textures, not all terrain geometry.

The streamer's `material` argument is one shared material in the fixture. Real
texture pages need a bounded material/texture cache keyed by dataset revision,
layer page and quality. Do not create one duplicate material per tree or frame.
Texture uploads need their own small commit queue; the current terrain job produces
no textures and does not pretend to manage their GPU memory.

### C2. `scripts/yellowstone_atmosphere.gd` and canonical counterpart

The repository contains a matching `yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd`.
Determine the canonical copy, edit it, and synchronize the packaged counterpart.
Run the repository's canonical-copy test; do not allow the two files to drift.

In `set_simulation_timestamp`, `_update_atmosphere`, `_update_rainbow`, and cloud offset
handling, use the common provider's epoch/time. Derive cloud phase from absolute
coordinates and physical time or a persistent advected field, not how long this
particular renderer node has existed. Never initialize an independent weather RNG
for each render chunk.

Audit `_create_cloud_shell` and `_update_atmosphere`: the current cloud-base branch
can attach base altitude to `player_position.y`. For fixed weather, provide an
absolute cloud-base elevation and convert it to local vertical coordinates. If only
AGL is known, use the forcing provider's declared reference ground elevation, not the
walker's instantaneous y. The precipitation emitter may follow the player visually;
the precipitation **field supplied to physics** must not.

Cache shader parameter support once per shader/material registration instead of
repeated `_shader_has_parameter` enumeration. Separate slow solar/weather updates
from frame-rate visual animation. Origin shifts must update cloud/rainbow origins
and reset/reposition world-space particles deliberately. Star-cache refresh remains
time-based, not chunk-load-based. Do not change weather equations as part of this port.

## D. Vegetation and wildlife layers

### D1. `scripts/lodgepole_library.gd`

Reuse archetypes, dimension contracts, variation keys, shared meshes, cutout mip
coverage and impostor texture arrays. Load each shared asset once. No rehashing or
reinstantiation of the entire asset library for each tile. Keep metadata/hash checks
at source activation and asset-cache population. Shared assets must not be mutated
concurrently by geometry workers.

### D2. `scripts/canopy_surface.gd`

Replace the full-grid `build`/`_build_clusters` entry path with a bounded tile-window
adapter. Read only intersecting source cells plus support/mask halo. Retain source
2 m canopy measurements as data, not mandatory one-display-instance-per-cell density.

Near demand can assemble selected measured/authored crown detail; medium demand
uses aggregated patch geometry; far demand retains coarse canopy coverage/silhouette.
A visual aggregation must preserve gaps and coverage within tested error, without
claiming its display supports are measured stems. Use `VegetationBatch.create` for
shared regional meshes and precomputed transform buffers. The helper is provided;
the project-specific canopy aggregation and texture-page generation must be written
and compared against the existing source/mask tests.

Do not call `refresh_geometry` for a whole loaded park or generate all three detailed
instance representations up front. Geometry revision belongs in each tile/cache key.

### D3. `scripts/forest_floor.gd` / `forest_floor_geometry.gd`

Index `forest_floor.json` into source-record pages in the input compiler. Preserve
IDs, guild, source class and contact information. Generate only required display
geometry and use the existing shared geometry library. Remove full-file loading from
runtime scene startup. Litter/understory get small visual budgets; scientifically
meaningful ground cover remains in the model whether rendered or not.

### D4. `scripts/tree_submission.gd`

Do not configure this global per-instance repacking controller for the new streamed
vegetation path. Leave it intact for legacy comparisons. Tile/representation selection
is upstream; regional immutable buffers are committed in bulk. A local micro-batch
compaction experiment can be added only with measured CPU/GPU benefit and a fixed
per-frame update quota. Do not retain two independent systems fighting over the same
MultiMesh's visibility/buffer.

### D5. `scripts/wildlife_actor.gd` / `wildlife_motion_controller.gd`

Split authoritative identity/state from a disposable visual actor. In `_ready`,
instantiate a model only when a subscribed entity enters the render/interaction
region. In `_process`, animate from timestamped state; do not update authoritative
feeding/grazing merely because the visual actor is processing. In `_exit_tree`,
release visuals/subscriptions, not the persistent Python animal or accumulated stores.

Audit `_world_position`, `_route`, `_last_sim_time`, `_mammal_elapsed`, `position_at_s`
and ground/water queries for absolute/local coordinate confusion. Store canonical
coordinates in the provider; convert only at the presentation boundary. A tracked
animal that reappears keeps the same ID, phenotype parameters, route/state and RNG
counter. Untracked decorative encounters must be explicitly classified as such.

Keep the motion controller's phase/speed semantics separate from scientific time
acceleration. Do not execute thousands of visual animation updates to "catch up"
a hidden animal. Reconstruct its visual phase at the accepted timestamp.

## E. Existing Python engine and Godot simulation adapters

### E1. `yellowstone_python/yellowstone_python/service/live/engine.py`

The provided `LegacyLiveDomain` wraps inspected existing methods, including private
checkpoint methods. Construct the native engine with `start_worker=False`. Do not
also call `engine.start()`. Use `ParkRuntime` with **the native frame interval**, not
its 1-second fixture default:

```python
engine = LiveEngine.from_build(build_path, start_worker=False)
domain = LegacyLiveDomain(engine, "midway.firehole")
world = ParkRuntime(
    [domain],
    quantum_s=engine.frame_interval_s,
    history_s=2 * engine.horizon_s,
    epoch_unix=engine.epoch_origin,
    max_frames=256,
)
service = RuntimeService(world, horizon_s=engine.horizon_s)
```

Verify the actual `from_build` keyword surface before use; its implementation accepts
kwargs in the inspected baseline. A local interface change must be adapted, not guessed.

Required native edits, in order:

1. Introduce public, tested `snapshot_at_frontier`, `checkpoint_state` and
   `restore_state` wrappers. Then switch `legacy_adapter.py` from private methods to
   those wrappers. Keep native solver equations and timestep policy unchanged.
2. Serialize mutable arrays and typed solver state explicitly. The current native
   checkpoint contains scientific objects, so the bridge intentionally refuses
   StateStore persistence. Do not remove that refusal until the serializer covers
   river state, solutes, ecological stores, weather/forcing revision, calibration,
   interventions, integration-segment history, tracked RNG state and model versions.
3. Make all immutable geometry/source catalogs shared and versioned, not deep-copied
   into every regional checkpoint. Bound native frame/checkpoint history separately
   from analysis exports.
4. Replace `_weather(t_s)`'s implicit one-site assumptions with a provider that accepts
   domain/site metadata. Keep one UTC epoch; regional forcing must be spatially
   consistent. The included ForcingTimeline handles time sampling/integrals, not a
   weather forecast or full spatial atmospheric model.
5. Retain `_control` rollback/invalidation behavior but expose the outer session and
   revision as the authority. The old client must not write the same engine clock.
6. For actual cross-region PDE coupling, integrate section 02's interface ledger at
   the solver step, not after independently completing a minute in each region.

Before durable native saves or park-wide use, run a same-input native-vs-adapter test:
same initial state, native sample interval, forcing schedule, intervention time and
solver tolerances. Compare every advertised scientific field and budget. The bridge
has not been executed against the full repository's dependency environment here.

### E2. `service/server.py`, `scripts/live_python_client.gd`, `scripts/ecosystem.gd`,
`scripts/python_river_replay.gd`, `scripts/simulation_panel.gd`

Keep the old loopback service at 8765 for regression/reference mode. The new service
is at 8766 and is opt-in. It returns a bracketing pair instead of the whole future
history. No HTTP handler invokes a solver. POST commands return 202 plus a command
ID; poll `/api/park/commands/{id}` before declaring an intervention applied.

Map the native UI controls to `ParkClient.queue_command`; include `session_id`,
`revision`, `event_id`, `domain_id`, `at_s` and `changes` for interventions. Clock
commands carry `paused` and/or `time_scale`. Display rejection/hold reasons visibly.
The minimal supplied client emits `command_queued`; completion polling/UI feedback
is an explicit integration task, not an implemented success notification.

In streamed live mode, disable autonomous `ecosystem._process` stepping. Preserve
`apply_python_frame` as a compatibility projection only while consumers are migrated.
Do not recursively deep-copy all nested frame dictionaries each render frame. Wire
declared hot fields through `field_codec.py` / `field_buffer.gd`; IDs, enums, budget
ledgers, provenance and discrete events are not interpolated. The binary codec is
implemented but its HTTP route is not installed by the reference service.

Keep `python_river_replay.gd` for offline replay/analysis. It must not silently take
over as a different physical history after a live connection failure. Hold the last
accepted time, show connection status, and resume only with a compatible session or
an explicit user-selected scenario switch.

### E3. `river/river_world.py` and `land/overland_flow.py`

`firehole_chain` explicitly rejects branching. Do not "support the park" by deleting
that check. Add a graph adapter with confluence/fork conservation tests and retain the
existing single-chain solver as a tested subdomain. `reference_network.py` demonstrates
accounting only; it is not the replacement transport model.

Remove `GRID=1025`, `STEP=4`, `HALF=2048` assumptions from the new overland provider
interface, not by scattering new constants. Accept a source window, spacing, extent,
explicit open/connected boundaries, initial state and forcing interval. Preserve
Green-Ampt/ET/flow timestep and budget checks. Two adjacent windows need shared flux
ownership or halo exchange with synchronization. A closed edge at a render tile
boundary is a scientific bug.

## F. Finish by migrating tests, not by weakening them

Keep all existing `tools/validate_*` scripts runnable in legacy mode. Add streamed
variants for collision, core cuts, shoreline contact, canopy masks, tree identity,
material geography, release activation and weather continuity. Change obsolete node
paths deliberately; never interpret "node absent" as "test skipped successfully".

Promote streamed mode only after the checklist in `03_ACCEPTANCE.md` has actual
reports from the user's Godot/hardware configuration and the existing Python model
environment. Until then, the new scene is an experimental path alongside the intact
legacy project.
