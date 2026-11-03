# Solute transport under segment residency

## Scope

The next part of migration step 5 of `04_PARK_STREAMING_SPEC.md` section 11 after
`fixes-71`: the LiveEngine solute transport carried by the Firehole river segments in both
representations, with one conservative solute flux per interface, coarse restriction and
prolongation of solute mass, spin-up replay, interventions, and the committed save. The
default world mode does not change and no scientific claim changes state. Oxygen,
periphyton, exposure, the foodweb, insects, trout actors, the viewshed `visible` reply, the
per-tile frame filter and Godot intervention controls stay out of scope.

## Findings and implementation

- Segments carry heat only. `firehole_split.py` states "Ecology, solutes and actors stay in
  LiveEngine"; `RiverSegmentDomain` holds a `River`, `RiverInterface` records
  `Stores(water_m3, heat_j)` with `solute_kg` zero, and `ResidencyManager` builds rivers
  from the replay configuration alone. `LiveEngine` steps `SoluteTransport` on the same
  cells after each river advance (`engine.py` `_advance`), copying the river flow
  schedules into private solver attributes.
  Implementation: a segment domain optionally holds a `SoluteTransport` over its own cells.
  After each river advance it takes the river's boundary and source flow schedules through
  a public `SoluteTransport.use_flows()` and advances solutes at the solute step; a
  negative concentration raises. Heat results do not depend on the solutes.
- The solute solver has no per-cell mass forcing, no forcing API and no checkpoint.
  Interface dispersion needs a sink in the upstream end cell and a source in the
  downstream one, as `cell_heat_w` does for heat; rollback and saves need a portable state.
  Implementation: `SoluteTransport` gains `cell_mass.<solute>.<cell>` rates in
  concentration units times m3/s, entering the implicit solve and a `cell_input_mass` budget
  term; `set_forcing()` for `boundary.<solute>`, `source.<id>.<solute>` and cell mass;
  `checkpoint()` and `restore()` with a frozen `SoluteState` of plain schedules. Without
  cell mass forcing the solve and its totals are unchanged.
- The boundary chemistry rule lives inside `LiveEngine.__init__`: explicit configured
  values, then the bundled data file, then an authored zero baseline labeled
  `authored_zero_baseline_unknown_observation`. A second copy would drift.
  Implementation: `river_solute_transport()` in `solute_transport.py` returns the transport
  and the boundary provenance for a river and optional explicit boundary and source
  chemistry; `LiveEngine` calls it with its existing configuration.
- An explicitly configured boundary value keeps the data-file status: an authored chloride
  is labeled `fitted_from_upstream_gauge_sc` and an authored arsenic `unknown`. No shipped
  configuration sets solute boundaries.
  Implementation: an explicit value is labeled `authored_explicit_concentration`, as are
  explicit source chemistries.
- `test_firehole_service_saves_on_sigterm_and_resumes` fails at the baseline commit `f359ca07`
  (154 passed, 1 failed in `tests/park_runtime`). In a resumed run the banner and the resume
  line arrive together; `run_firehole` reads the banner through a buffered text pipe, which
  also takes the resume line, and `communicate()` then reads the raw descriptor, so the line
  is lost. Three 2 s resumed runs lost it once in text mode and never through an unbuffered
  binary pipe; the service resumed and saved at 10 s in every run.
  Implementation: `run_firehole` reads an unbuffered binary pipe and decodes the output.
- `RiverInterface` couples heat only.
  Implementation: with solutes on both sides, `begin()` fixes one dispersive solute rate per
  species from the quantum-start end-cell concentrations and the face conductance used for
  heat, and `transfer()` sets the downstream inlet concentration to the upstream outlet
  export mass over the exported water. Each receipt adds the advective and dispersive solute
  mass once; the face history entry gains the inlet concentrations and dispersive rates.
- The coarse tier has no solute representation.
  Implementation: coarse solutes run on the coarse river's merged cells with volume-weighted
  restriction. Prolongation scales the spin-up concentration shape inside each coarse cell
  to the coarse mass, which keeps concentrations nonnegative; a group with zero held mass
  receives the coarse concentration uniformly.
- Residency paths carry temperatures only: retirement, installation, coarse history,
  last fine states, spin-up jobs, the tier ledger, snapshots for rollback and the saved
  document.
  Implementation: each path also carries concentrations when the manager is built with
  `solutes` settings; `firehole_residency()` enables them with the data-file chemistry. The
  tier ledger closes every solute over both tiers, and each swap records its solute mass
  change. Interventions accept `solute.boundary.<solute>` on the head segment and
  `solute.source.<id>.<solute>`, refuse `solute.cell_mass.*` and boundary chemistry below
  the head, and validate against both representations. The saved schema becomes
  `yellowstone.park_residency_state.v2`, `solute_transport.py` joins the guarded model
  sources, and the identity records the solute settings and step.

## Acceptance tolerances, set before the runs

Firehole replay (276 cells, faces 46, 92, 138, 184 and 230, quantum 10 s, heat step 1 s,
solute step 10 s) or the demo river (60 cells, faces 20 and 40) with a synthetic fixture:
boundary 5 mg/L chloride, 0 ug/L arsenic and 0.05 mg/L boron, the illustrative source at
258 mg/L, 1870 ug/L and 3.01 mg/L.

1. Chain against the single domain. Over 3600 s of the Firehole replay with data-file
   chemistry, the six-segment chain matches one transport on the whole river: every cell
   within 4e-3 of the fully mixed source increment of that solute at the outlet (the bound
   of the heat split, 0.02 C on a 5 C front); outlet export mass within 1e-4 of the solute's
   boundary and lateral input over the run; at
   every face the downstream boundary input and the ledger total within 1e-9 relative of the
   upstream export plus dispersion; dispersive cell mass summing to zero within 1e-9 of
   throughput; chain mass closure within 1e-9 of throughput; temperatures identical to a
   heat-only chain; no negative concentration.
2. Restriction and prolongation. Restricted mass per coarse cell equals the fine mass within
   1e-14 relative; prolonged concentrations are nonnegative and hold each coarse cell's mass
   within 1e-14 relative; a group with zero held mass is uniform.
3. Coarse between fine neighbors. Demo river, 3600 s: each face's downstream boundary input
   equals the upstream export within 1e-12 relative per solute, chain closure within 1e-9.
4. Walk. Demo river from 0 m to the outlet at 1.4 m/s: the `fixes-69` walk checks hold, swap
   solute mass within 1e-12 relative, tier solute closure and every face within 1e-9, and no
   negative concentration at any update.
5. Spin-up. The worker replay of a segment with solutes equals the in-process replay exactly
   and the segment that ran fine in the runtime within 1e-12 relative per cell.
6. Interventions. A head boundary chloride change applied by rollback one quantum behind the
   frontier matches the same change applied at its frontier within 1e-12 relative over 60
   quanta; a source chemistry change on a coarse segment holds in the installed fine
   segment; `solute.cell_mass.*`, boundary chemistry below the head, an unknown solute, a
   negative concentration and solute names on a manager without solutes are refused with the
   state unchanged.
7. Save and load. A v2 document restores concentrations, interface solute totals, histories
   and tier terms; both managers advanced 30 quanta agree within 1e-12 relative and the
   loaded solute ledger closes within 1e-9; a v1 document and different solute settings are
   refused by name.
8. Firehole walk. With the published replay and data-file chemistry, a walk at 1.4 m/s from
   the start of `firehole.s2` to the end of `firehole.s4` installs `firehole.s3` and
   `firehole.s4` before arrival, closes heat, water and every solute within 1e-9, keeps swap
   solute mass within 1e-12, and reports nonzero arsenic in `firehole.s4`.
9. Service and LiveEngine. `--firehole` publications carry per-cell concentrations, the
   walker concentrations and the boundary provenance, and the SIGTERM save and resume test
   passes on v2; LiveEngine solute frames and saves keep their existing tests.

The outlet bound in the chain comparison uses the solute's input over the run, the scale of the
closure bound. A bound relative to the outlet export failed for arsenic in a 1800 s demo smoke
run held before the Firehole run: with a zero boundary only a numerical diffusion tail of the
source front reached the outlet, and the difference was 1.0e-2 of that tail.

## Verification

- Python tests in `tests/park_runtime/test_segment_solutes.py` and the existing residency,
  state and focus tests; the Firehole items as `needs_world` tests.
- `pytest tests/park_runtime`, full `pytest -q`, a build and `audit_provenance`;
  `check_comment_style.py` and the prose pattern checker clean on touched files.

## Sources

- `yellowstone_python/river/solute_transport.py` (`SoluteTransport`, `SOLUTE_KEYS`,
  `transport_from_mapped_replay`), `service/live/engine.py` (`__init__`, `_advance`),
  `park_runtime/firehole_split.py`, `coarse_river.py`, `residency.py`, `service.py`.
- `yellowstone_python/data/hydrothermal_solutes.json` (`firehole_upstream_boundary`,
  `excelsior`).
- `yellowstone_midway/docs/park_runtime/02_SIMULATION_AND_STATE.md` (requirements 1, 2 and
  5); `04_PARK_STREAMING_SPEC.md` section 7.1; `fixes/ledger/fixes-71.md`.
