# Firehole simulation residency with a coarse tier, anticipation, admission and worker spin-up

## Scope

The remainder of migration step 5 of `04_PARK_STREAMING_SPEC.md` section 11 after
`fixes-67`: the anticipation set and admission control of section 7.1, a coarse
representation for river segments outside the fine set, activation and retirement with a
conservative hand-off, and spin-up in worker processes, accepted by a walk along the
Firehole. The default world mode does not change and no scientific claim changes state.
The coarse representation and the residency policy are illustrative runtime machinery
over the existing river heat solver; ecology, solutes and actors stay in LiveEngine.

## Findings and implementation

- No coarse tier for a river segment. A segment outside the fine set has no
  representation, so `fixes-67` retirement leaves the downstream boundary holding the
  last transfer. Implementation: `coarse_river.py` builds a coarse segment by merging
  consecutive fine cells into control volumes (lengths, volumes and surface areas
  summed, temperature volume-weighted), keeping the lateral sources, boundary and
  surface energy budget, and runs the same `River` solver at a step of one runtime
  quantum. A coarse cell starts at each lateral inflow cell, so an inflow mixes only
  into the water downstream of it. Restriction from fine to coarse conserves water and heat exactly;
  prolongation shifts a fine profile per coarse cell so each coarse cell's heat is
  matched exactly. Prescribed cell heat, shortwave multipliers and hyporheic zones are
  refused for coarse restriction.
- No anticipation set. Implementation: `residency.anticipation()` ranks segments by
  the reach set (the segment holding the walker position `p` and the one holding
  `q = p + v * 20 s`), then the stretch along the river ahead of the walker out to the
  distance covered in the activation lead time `L`, then the propagation halo: each
  upstream segment whose inlet-to-tile water travel time is shorter than `L` in
  simulated seconds. `L` in wall seconds is the spin-up cost in cell-simulated-seconds
  (the largest segment times the replay interval) divided by the measured worker rate,
  plus an authored margin; spin-up runs in worker processes, so the fine island's own
  capacity does not carry it.
- No admission control. Implementation: `residency.admit()` admits segments in
  priority order while the fine cells times the requested time scale stay inside the
  measured capacity times a utilization factor; the rest stay coarse. When the reach
  set itself cannot be admitted, the effective rate is the capacity share the reach
  cells allow and the hold is reported.
- No worker processes. Implementation: activation spin-up runs in long-lived worker
  processes (`concurrent.futures.ProcessPoolExecutor`, spawn context). A job rebuilds
  the fine segment, starts from the segment's last fine checkpoint when it is less
  than one simulated day old, otherwise from the coarse state one spin-up interval
  before the frontier, prolonged to the fine cells, and replays the recorded interface
  history (inlet discharge, inlet temperature and face dispersion power per quantum).
  A result older than the frontier starts a catch-up job from its state. Installation
  reconciles the fine profile to the coarse heat at the frontier and records the
  reconciliation energy per coarse cell. Resident segments advance in the runtime
  process because adjacent segments exchange within each quantum.
- `RiverInterface` computes the face dispersion from the adjacent end cells when no
  conductance is given, so fine and coarse neighbors share one coupler.

## Acceptance tolerances, set before the walk run

Firehole published replay forcing, six segments of 46 cells, quantum 10 s, fine step
1 s, coarse cells of 23 fine cells at a 10 s step, time scale 1, spin-up interval
3600 s, lead margin 30 s, retirement hysteresis 10 s wall, a walker starting at the
upstream face and moving downstream at 1.4 m/s along the chainage to the outlet:

1. Activation before arrival: every segment the walker enters is fine and installed at
   the first quantum boundary at or after the walker crosses its upstream face; zero
   arrivals on coarse state.
2. Retirement: every segment the walker has left and that is outside the anticipation
   set returns to coarse within its hysteresis plus one quantum; at most three
   segments are fine at any quantum.
3. Hand-off ledger: at every membership swap the water of the removed and added
   segment agree within 1e-12 relative and the heat within 1e-12 of the segment heat.
4. Tier conservation over the walk: the change of total heat over all segments equals
   the external fluxes (prescribed inlet, lateral sources, surface exchange, outlet)
   within 1e-9 of the heat throughput; internal interface exports equal the downstream
   boundary inputs within 1e-9 relative; total water closes within 1e-9 relative.
5. Admission: at every update the fine cells times the time scale stay inside the
   capacity estimate times the utilization factor, or the hold is reported.

Recorded as a diagnostic without a tolerance: the temperature difference at the
walker's cell against the single-domain solver at the same times.

## Verification

- Python tests: coarse restriction and prolongation conservation, a coarse segment
  coupled to fine neighbors with a closed budget, anticipation and admission on
  synthetic inputs, spin-up in a worker process equal to the same replay in process,
  and a shortened Firehole walk against items 1 to 5.
- `tools/park_firehole_walk.py` runs the full walk and the single-domain reference and
  writes the report; the result is recorded in the ledger.
- `pytest tests/park_runtime`; `check_comment_style.py` and the prose pattern checker
  clean on touched files.

## Sources

- `yellowstone_python/park_runtime/runtime.py`, `firehole_split.py`;
  `yellowstone_python/river/river_transport.py` (`checkpoint`, `restore`,
  `set_forcing`, `budget`).
- `yellowstone_python_spec/04_PARK_STREAMING_SPEC.md` sections 7, 7.1, 10 and 11;
  `yellowstone_midway/docs/park_runtime/02_SIMULATION_AND_STATE.md`.
