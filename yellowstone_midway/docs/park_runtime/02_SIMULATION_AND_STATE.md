# 02. Simulation, state and numerical coupling contract

## What is implemented

`ParkRuntime` owns a causal timeline. It advances registered domains to a common
completed frontier, stores independent checkpoints, supplies only a received-time
bracket, and rolls back all participating domains when one advance fails. An
intervention restores an earlier retained checkpoint, advances to its effective
time, changes forcing/state, increases causal revision and invalidates future data.
The reference service advances this kernel off the Godot process/thread. HTTP
handlers read immutable publications and enqueue commands only.

A region subscription changes which data is transferred. It does not change which
registered domains evolve. This is intentional: first establish camera-independent
truth. Adding physically different coarse/fine models is not merely a scheduler flag.

The supplied `ReservoirNetwork` is a genuine but simplified conservative branching
model for tests. It is explicitly labeled illustrative and must not replace the
project's actual river or ecological models. `LegacyLiveDomain` bridges the current
native engine in memory, but its persistent serializer is not implemented.

## Clocks and revisions

Keep these distinct:

| Name | Meaning |
|---|---|
| `dataset_revision` | Immutable source/catalog/geometry version |
| `session_id` | A running scientific history; changes on a new session/restart |
| `revision` | Causal revision after an intervention invalidates future states |
| `t_s` | Physical seconds relative to the scenario epoch |
| `epoch_unix` | UTC time origin; never a render-local clock |
| `presentation_s` | Common accepted time currently shown to the player |
| `completed_s` | Latest jointly computed state, possibly speculative future |
| `interest_sequence` | Ordering of camera/output subscriptions, not physical truth |

The renderer interpolates only inside its actual received bracket. A completed
frontier five minutes ahead does not authorize interpolation if only two seconds of
actual snapshots have been transferred. The supplied client clamps to the last
received bracket endpoint. Disconnection makes state stale, not an alternate replay.

## Global and regional forcing

Use a shared UTC epoch and a spatial forcing provider keyed by absolute coordinates,
valid times, provenance and source revision. The supplied ForcingTimeline samples
prescribed scalar fields and integrates across temporal breakpoints. Wind should be
interpolated as components, not as an angle across 359/0 degrees. Discrete rain onset
can use previous-value sampling; integrated rainfall must respect its breakpoints.

A higher-fidelity regional weather model may refine a coarse forcing field, but it
cannot restart a new weather history because a tile became visible. A camera-relative
rain emitter is a presentation device and never defines the rain volume supplied to
hydrology. Clock holds, time acceleration and region reload must not change cumulative
precipitation at a fixed physical time.

## State classes and persistence

Persistent state includes extensive water/heat/solute/snow/soil/biomass stores;
tracked individuals; spatial parameters; discrete interventions; boundary histories;
model/source versions; clocks and RNG counters. Transient state includes MeshInstance,
MultiMesh, animation players, colliders, GPU textures and cosmetic particles.

StateStore uses SQLite WAL, atomic transactions, canonical JSON, bounded compressed
payloads and SHA-256 checks. It never unpickles a save. Current saves persist the
latest completed checkpoint **at or before presentation time**, not the speculative
frontier. Restart can therefore lose at most one output quantum of presentation time;
this is explicit. Exact sub-quantum resume would store/interpolate/reintegrate a valid
checkpoint at the exact accepted time, not interpolate authoritative extensive state
without a model contract.

Events carry stable IDs. Reusing an ID with different contents fails. Session
idempotency and event history are retained in saves. Long-lived installations should
index old event identities in the database instead of retaining a growing Python
list forever; scientific history must not be discarded to fake bounded memory.

The legacy bridge blocks persistent saves because the native engine checkpoint
contains solver objects. Implement explicit native serializers or a versioned
portable checkpoint export before enabling that path. A generic `str(object)`,
`default=str`, pickle or silent omission is not acceptable.

## Numerical partitioning: one interface, one flux

For a coupled water/thermal/solute interface over `[t0,t1]`, define one signed,
time-integrated transfer:

- `water_m3 = integral Q(t) dt`
- `heat_j = integral rho * cp * Q(t) * T(t) dt`, with a declared temperature reference
- `solute_kg = integral Q(t) * C(t) dt`

The sender subtracts this exact transfer; the receiver adds it. They do not each
compute unrelated boundary values and reconcile the difference after the fact.
`FluxLedger` checks interval ordering and exactly-once receipts. It is an accounting
primitive, not a complete Riemann solver, halo exchange or coarse-fine refluxer.

At a confluence, incoming **fluxes and extensive stores** combine. Temperatures do
not combine by an unweighted arithmetic mean. For example, 1 m3 of water at 20 C
and 9 m3 at 10 C contain heat corresponding to 11 C under constant rho*cp, not 15 C.
Do not confuse a local sampling interpolation with the mass/energy update.

For coarse-to-fine reconstruction, allocate extensive stores with nonnegative
weights summing to one and reconstruct intensive fields under the solver's physical
constraints. `prolong`/`restrict` test the extensive accounting. Preserve reservoirs
whose residence times or coupled forcing matter even when no player can see them.

### Requirements before activating true adaptive scientific detail

1. Define whether coarse and fine levels represent the same physical control volume.
   The fine level must replace the covered coarse update, not double-count it.
2. Define conservative restriction/prolongation, valid positivity bounds and what
   unresolved subgrid information is irrecoverably approximated.
3. Supply boundary histories and halo widths based on physical propagation/stability,
   not camera field of view. Groundwater/implicit systems may require a global or
   iterative regional solve; they cannot be localized by a sight line.
4. Synchronize or subcycle numerical times. Fast river/overland steps and slow ecology
   output intervals are different things. Render FPS never selects a stable PDE step.
5. Accumulate and reconcile interface fluxes across level changes. Keep a budget
   ledger for refinement, coarsening, reload and rollback.
6. Compare uninterrupted fine, uninterrupted coarse and adaptive runs at the same
   forcing/physical times. Set tolerances before viewing the results. Changing the
   camera path may alter numerical approximation only within a declared accepted
   tolerance; it must not arbitrarily change the modeled outcome.

Until those requirements pass, keep authoritative coarse/legacy physics independent
of camera and use detailed visual reconstruction as a read-only presentation layer.
This is not permission to abandon adaptive simulation; it is the safe migration order.

## Cross-process transport and performance

The reference HTTP service returns a small bracketing pair and separates the model
owner from request handlers. The optional YSP1 binary codec carries float32 fields
with float64 JSON timestamps, IDs, field names and units. Values use contiguous
`[2, entity_count, field_count]` layout. There is a 64 KiB header and 16 MiB numeric
payload limit. Missing data requires an explicit validity channel, not NaN silently
converted to zero.

The supplied HTTP demo does not expose the binary route; add it when adapting the
real engine's hot fields. Keep control/provenance JSON and numeric arrays separate.
Use bounded subscriptions and preallocated interpolation buffers. Move to shared
memory or another transport only after measuring JSON/IPC as a bottleneck. Such a
change requires ownership, generation counters, readers' lifetimes and crash cleanup,
not just a new serialization library.

The Python service is a separate OS process from Godot. Its internal worker thread
provides ownership/responsiveness; it does not magically parallelize CPU-bound Python.
For multiple solver workers, prefer long-lived processes with explicitly serialized
regional state, or compiled array kernels. Do not pickle the entire world for every
job, oversubscribe Godot's workers and BLAS, or run several independent owners of the
same region. Begin with one measured native domain before parallelizing.

## Known orchestration limits

The kernel has one common output quantum. It can contain domains that internally
subcycle different processes, but it is not a distributed multirate solver scheduler.
Late interventions earlier than the latest accepted intervention are rejected rather
than silently erasing later events. Bounded history limits rollback. Long teleports
or large physical-time jumps need an explicit prepare/advance operation and progress
state; no promise of instantaneous scientific catch-up is made.

Reference for numerical AMR design, not a claim that this package implements it:
https://www.clawpack.org/amr_algorithm.html
