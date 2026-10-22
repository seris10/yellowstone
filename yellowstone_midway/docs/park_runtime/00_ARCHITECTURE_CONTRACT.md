# 00. Binding architecture contract

## Goal and scope

Build a park-scale, demand-streamed geographical world. The player sees a temporary
representation of persistent scientific state. Work is allocated from visibility,
projected error, terrain occlusion hints, movement prediction, collision deadlines
and scientific dependency, not only concentric radii. A small all-direction safety
region and coarse fallback remain mandatory because a camera can turn instantly.

The supplied implementation is a **migration foundation with executable components**.
It includes a paged terrain input compiler; an asynchronous GDScript terrain pipeline;
origin shifting; screen-error and predictive demand; soft topographic priority;
atomic parent/child replacement; separate collision commits; a snapshot client;
a single-owner Python timeline; persistence; forcing integration; conservative
transfer helpers; a branching reference network; an existing-live-engine adapter;
and tests. It is not a completed park-wide multiphysics solver or a drop-in visual
replacement for the current finished layers. See the exact status matrix in
`04_IMPLEMENTATION_STATUS.md`.

## Non-negotiable invariants

**One physical timeline.** One owner advances physical time. Renderer, atmosphere,
animation, HTTP client and geometry jobs cannot independently advance it. Results
carry source revision, simulation session, causal revision and valid times. These
are different identifiers and must not be conflated.

**Visibility is not existence.** Scene unload releases only transient GPU, node and
local-physics resources. Persistent water, heat, solute, snow, soil, ecological
stores, interventions and tracked identities survive. Hidden dependency regions
remain active at their appropriate scientific resolution.

**Independent partitions.** Terrain uses a quadtree; river systems use a network;
runoff uses drainage/catchment partitions; weather uses spatial fields; ecology uses
habitats and tracked populations. A square rendering tile is not a universal model
boundary. Coupled numerical regions require shared interface fluxes, not independent
calls to a generic task runner.

**Demand, preparation and commit are separate.** GDScript workers read small source
pages and build CPU arrays. Main-thread code creates meshes and commits scene nodes
in bounded batches. Physics bodies are committed during physics ticks. No scientific
solver runs inside `_process`, `_physics_process`, an HTTP handler, or a terrain job.

**No holes from partial refinement.** A render parent stays active until all four
children have complete coverage. The parent and its complete child cover switch in
one main-thread update. Skirts cover visual T-junctions; they are not physical
surfaces. Root coarse coverage is the all-direction fallback, not another full-detail
world. A failed page leaves the parent in place and surfaces an error.

**Collision has its own deadline.** Visual detail can lag. The walker cannot enter
unprepared collision coverage. Near-field collision uses leaf samples and the same
triangle diagonal as rendering. Physics activation has a one-tick readiness delay.
Teleportation is a prepare/validate/commit operation, not direct relocation into void.

**Absolute scientific coordinates are not float32 vectors.** Retain projected
coordinates as double scalars in Python and GDScript. Godot vectors contain only
near-origin offsets. Origin shifts do not alter scientific positions, wind fields,
random identities, weather phase, source masks or actor histories.

**Source preparation is allowed; exhaustive final-world baking is not required.**
Reprojection, compression, raster pyramids, bounds/error indexes, river topology,
asset LOD libraries and source provenance belong in an immutable input pipeline.
They do not precompute the complete landscape scene or its future simulation.
Terrain meshes are generated on demand. Shared static assets can be loaded rather
than regenerated when measurement shows that is cheaper.

**Do not degrade science to meet a graphics budget.** Coarsening terrain materials
or reducing decorative foliage is a presentation decision. Changing a solver grid,
timestep, boundary condition, state reconstruction or tracked population is a
scientific-model change with separate validation. Output interpolation never becomes
feedback into the authoritative solver.

## Responsibility map

| Component | Owns | Must not own |
|---|---|---|
| Input compiler | Georeferenced source windows, geometric error, content hashes | Future ecosystem state or a giant final scene |
| Demand planner | Visual error, visible/predicted demand, collision prerequisites | Whether remote physical state exists |
| Terrain jobs | Immutable tile data to CPU arrays | Scene tree, textures, numerical models |
| Streamer | Residency, resource lifecycle, commits and coarse coverage | Re-solving environmental physics |
| ParkRuntime | Causal timeline, common completed frontier, rollback | Camera-dependent model truth |
| Coupled domain | Internally coherent physics and boundary accounting | Independent adjacent flux guesses |
| StateStore | Atomic committed checkpoint and intervention identities | Pickled executable objects or speculative future saves |
| Godot client | Received timestamp bracket and presentation interpolation | Extrapolated scientific truth or a second world clock |

## Backpressure and failure policy

Use bounded queues, bounded in-flight work, bounded mesh resolution and explicit
memory accounting. A millisecond commit budget is a scheduling target, not a hard
bound on an individual non-preemptible GPU upload. Record the actual worst commits.
GPU-driver allocations and physics engine memory are not fully captured by the
streamer's byte estimate. Measure process memory and engine counters as well.

When preparation is late: retain coarse geometry; defer fine detail; guard movement
until collision is ready. When simulation is late: hold the physical clock at a
completed frontier while rendering and input remain responsive. When data is absent:
report unavailable coverage. Never substitute zero heights or reset state silently.

The supplied horizon sampler is a **soft priority heuristic**. It is not a complete
height-bound occlusion proof or GPU HZB implementation. Do not turn its sampled
"hidden" result into a hard residency deletion. A later hard-cull path needs
conservative min/max bounds, camera/height margins, previous-view retention and
ridge-gap tests.
