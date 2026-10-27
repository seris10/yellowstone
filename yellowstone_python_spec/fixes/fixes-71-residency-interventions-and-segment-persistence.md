# Interventions under segment residency and persistable segment state

## Scope

The next part of migration step 5 of `04_PARK_STREAMING_SPEC.md` section 11 after
`fixes-70`: forcing interventions accepted while Firehole segments change between fine and
coarse representations, and a committed save and resume of the segmented river with its
residency histories. The default world mode does not change and no scientific claim
changes state. The LiveEngine ecology, solute and actor split, the viewshed `visible`
reply, the per-tile frame filter and Godot intervention controls stay out of scope.

## Findings and implementation

- Interventions are refused under residency. `RuntimeService._command()` raises
  "interventions are not supported with segment residency". `ParkRuntime.intervene()`
  restores a rollback checkpoint, and `_membership_entry()` clears those at every swap, so
  an intervention one quantum behind a frontier swap has no checkpoint. A rollback through
  the runtime alone also skips the interface and coarse histories that
  `ResidencyManager.advance()` records each quantum.
  Implementation: `ResidencyManager` records one composite snapshot per quantum boundary
  before each advance (segment checkpoints with their representation, interface ledgers,
  history marks, last fine states and open tier lifetimes), bounded by the runtime history
  window. `ResidencyManager.intervene()` restores the latest snapshot at or before the
  event, rebuilding each segment in its recorded representation, truncates the interface
  and coarse histories to it, replays through `advance()` on the quantum grid to the event
  time, applies the change, takes a new causal revision and restarts retained history and
  snapshots there. A failure reinstates the prior runtime and manager state. Spin-ups in
  flight are discarded and resubmitted by the next update.
- A swap discards intervention forcing. `_fine_domain()` and `_coarse_domain()` build a
  segment from pristine rivers, so a changed air temperature or source temperature
  disappears at the next install or retirement. Spin-up replays in workers start from the
  pristine segment as well.
  Implementation: accepted interventions are kept by segment and reapplied by forcing name
  at the build time to every rebuilt fine or coarse segment, and `replay_segment()` applies
  them at their times during a spin-up. A replay refuses an intervention time that falls
  inside a recorded interface quantum.
- Some forcing names are representation specific or owned by an interface.
  `cell_heat_w.<cell>` names a fine or coarse cell id, and an interface sets the inlet
  boundary and end-cell heat of every segment below the head each quantum.
  Implementation: under residency `cell_heat_w` changes and boundary changes below the
  head segment are refused by name; each change is validated against both pristine
  representations before any state moves, and a head-segment boundary discharge must stay
  positive so that every interface carries water.
- Segment state is not persistable. `RiverSegmentDomain.persistence_supported` is false,
  `RiverState` holds solver dataclasses, and `--firehole` writes no state file.
  Implementation: `ResidencyManager.save_committed()` writes the latest composite
  snapshot at or before the presentation time as a versioned JSON document
  (`yellowstone.park_residency_state.v1`) through `StateStore`; river states use the
  tagged encoding of `service/live/state_codec.py`, and the document carries interface,
  coarse and last-fine histories, tier lifetimes and swaps, interventions, membership and
  events. A save at a presentation time before the latest swap succeeds from the snapshot
  taken before it. `load_committed()` refuses a different replay configuration, epoch,
  segmentation, numerical policy or model source by name, then rebuilds every segment in
  its saved representation. `python -m yellowstone_python.park_runtime --firehole` loads
  and saves `--state` (default `park_firehole.sqlite3`) on Ctrl+C or SIGTERM.
- `ParkRuntime` has no public way to replace its domain set together with its timeline.
  Implementation: `reset_to()` installs restored domains, coupler states, time, revision,
  membership and events and restarts retained history; `state_token()` and `reinstate()`
  hold and return the full retained state; `prior_event()` and `record_event()` carry the
  event identity rules that `intervene()` already applies.

## Acceptance tolerances, set before the runs

Demo river (60 cells, faces 20 and 40, quantum 10 s, fine step 1 s, virtual wall) unless
stated.

1. Rollback equivalence. An air temperature change on a segment at a time one quantum
   behind the frontier, applied by rollback and replay, matches a reference manager that
   applies the same change at that time from its frontier: every cell temperature within
   1e-9 C over the next 60 quanta, equal revisions and event records, river budget terms
   within 1e-9 relative.
2. Across a swap. An intervention at a time before a frontier install is accepted, the
   segment returns to its representation at that time, and the walk continues: the
   segment installs again with swap heat and water within 1e-12 relative, tier heat
   closure within 1e-9 of throughput, water closure and every face within 1e-9 relative.
3. Spin-up through an intervention. `replay_segment` with the intervention list, from the
   published initial state and the recorded interface quanta, matches the same segment run
   fine in the runtime through the intervention within 1e-9 C.
4. Rebuilt segments keep the change. After an air temperature change on a coarse segment,
   the installed fine domain and the next retired coarse domain hold the changed value at
   the frontier exactly.
5. Refusals. `cell_heat_w` changes, boundary changes below the head segment, unknown
   names, a nonpositive head boundary discharge, empty changes, an event before the
   retained snapshots, an event earlier than the latest accepted one and a reused event
   id with different contents are refused with explicit errors that leave the state
   unchanged; a repeated id with the same contents returns the recorded result.
6. Save and load. A save at a presentation time before the latest swap succeeds at the
   snapshot time. A fresh manager loaded from it holds the same representations, exact
   cell temperatures, interface ledgers, interventions, histories and tier-ledger terms;
   both advanced 30 quanta without residency updates agree within 1e-9 C, and the loaded
   manager's tier ledger closes within 1e-9.
7. Activation after load. A walk into a coarse segment after a load activates it from the
   persisted histories and installs it before arrival; the installed segment carries an
   intervention made before the save.
8. Identity. A load into a manager with different faces, fine step or coarse grouping, or
   with a changed model source hash, is refused by name.
9. Service. Under residency an intervention with the current session and revision is
   applied and the presentation clock moves to its time; a stale revision is refused.
10. Process. `--firehole` stopped with SIGTERM exits 0, saves at a recorded physical time
    and writes the state file; a restart reports resuming at that time and saves again at
    or after it.
11. Firehole. With the published replay, a walk at 1x to the middle of `firehole.s1`, an
    air temperature change on coarse `firehole.s3`, a save at the frontier and a load into
    a fresh manager continue the walk to the end of `firehole.s3`, which is the upstream
    face of `firehole.s4`: `firehole.s2`, `firehole.s3` and `firehole.s4` install before
    arrival, installed `firehole.s3` holds the changed value, tier heat and water close
    within 1e-9.

## Verification

- Python tests for the demo-river tolerances in `tests/park_runtime/test_residency_state.py`
  and `tests/park_runtime/test_park_focus.py`, the process tolerance in
  `test_park_focus.py` and the Firehole tolerance as a `needs_world` test.
- `pytest tests/park_runtime`, full `pytest -q`, a build and `audit_provenance`;
  `check_comment_style.py` and the prose pattern checker clean on touched files.

## Sources

- `yellowstone_python/park_runtime/runtime.py`, `residency.py`, `service.py`,
  `__main__.py`; `yellowstone_python/service/live/state_codec.py`;
  `yellowstone_python/river/river_transport.py` (`RiverState`, `set_forcing`, `Series`).
- `yellowstone_midway/docs/park_runtime/02_SIMULATION_AND_STATE.md` (state classes and
  persistence) and `04_IMPLEMENTATION_STATUS.md`.
- `yellowstone_python_spec/04_PARK_STREAMING_SPEC.md` sections 7.1 and 11;
  `fixes/ledger/fixes-70.md`.
