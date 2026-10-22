# Park runtime membership, bounded history and the Firehole split

## Scope

Migration step 5 of `04_PARK_STREAMING_SPEC.md` section 11 (simulation
residency on Midway), the parts that precede the anticipation set: domain
add and remove at quantum boundaries, history bounded by bytes with sparse
checkpoints, and the Firehole river split into two coupled domains with a
conservative interface. The anticipation set, admission control and worker
processes stay open. Measurements 9, 10 and 12 are recorded in section 10.
The default world mode does not change and no scientific claim changes
state; the split is a transport-level domain decomposition of the existing
river solver, compared against the single-domain solver on the published
replay forcing.

## Findings and implementation

- Fixed domain membership. `ParkRuntime` fixes its domains at
  construction and advances every domain each quantum. Implementation:
  `add_domain()` and `remove_domain()` act at the current quantum
  boundary, require the domain clock to equal the runtime frontier, record
  a membership entry with the domain's stores (water, heat, solute) in a
  runtime ledger, and restart rollback history at the boundary, so no
  intervention replays across a membership change. Removal returns the
  domain's final checkpoint and stores for the hand-off.
- Unbounded checkpoint history. `ParkRuntime` stores a full checkpoint of
  every domain at every quantum. Implementation: `checkpoint_interval_s`
  sets the rollback granule (default one quantum, the previous
  behavior); frames stay per quantum; interventions and committed saves
  restore the latest checkpoint at or before their time and replay
  forward. `history_byte_cap` bounds the estimated bytes of retained
  frames and checkpoints; `compute_until()` refuses a target whose
  projected history exceeds the cap. Domains may report their own sizes
  through `history_bytes()`; otherwise a recursive size estimate applies.
- No coupled domains. Implementation: `firehole_split.py` provides
  `RiverSegmentDomain` over a contiguous cell range of the river solver
  and `RiverInterface`, a coupler the runtime applies between the
  upstream and downstream advances of each quantum. The downstream
  boundary for the quantum is the upstream outlet export of the same
  quantum, as a constant discharge and temperature that integrate to the
  exported volume and heat; the interface dispersive flux
  `G (T_up - T_down)` of the single-domain matrix moves as an explicit
  exchange on the two interface cells, evaluated at the quantum start.
  Every transfer is recorded once in a `FluxLedger` under the interface
  id; the ledger rolls back with the runtime.

## Acceptance tolerances, set before the comparison run

Split at the face between `firehole_cell_00137` and `firehole_cell_00138`
(upstream of the Excelsior inflow at cell 159), quantum 10 s, solver step
1 s, published replay forcing, two simulated hours, against the
single-domain solver with the same step and the same initial state:

1. Water: the downstream outlet export over the run equals the
   single-domain export within 1e-9 relative.
2. Interface: the ledger's upstream export and downstream boundary input
   agree within 1e-9 relative for water and heat.
3. Heat budget: summed over both domains, storage change equals the
   declared fluxes within 1e-6 of the heat throughput.
4. Temperature: every cell at every 10 s sample within 0.02 C of the
   single-domain solution; the outlet heat export over the run within
   1e-4 relative.

## Verification

- Python tests for membership, sparse checkpoints, the byte cap,
  rollback across sparse checkpoints, and the split against the
  tolerances above on a shortened window; the two-hour comparison
  recorded in the ledger.
- `pytest tests/park_runtime`; `check_comment_style.py` and the prose
  pattern checker clean on touched files.

## Sources

- `yellowstone_python/park_runtime/runtime.py`, `coupling.py`,
  `contracts.py`; `yellowstone_python/river/river_transport.py`
  (`_system`, `_advance_to`, `set_forcing`).
- `yellowstone_python_spec/04_PARK_STREAMING_SPEC.md` sections 7.1, 10
  and 11; `yellowstone_midway/docs/park_runtime/02_SIMULATION_AND_STATE.md`.
