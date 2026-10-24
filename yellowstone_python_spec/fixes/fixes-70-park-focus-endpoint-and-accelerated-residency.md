# Park focus endpoint, service residency and accelerated-time walks

## Scope

The next part of migration step 5 of `04_PARK_STREAMING_SPEC.md` section 11 after
`fixes-69`: the focus message of section 8 served by the park runtime service and
driving the Firehole segment residency, `ParkClient` sending focus and reading the
residency report, and the residency walk at accelerated time. The default world mode
does not change and no scientific claim changes state. The viewshed reply (`visible`),
the per-tile frame filter, LiveEngine ecology, solutes and actors stay out of scope.

## Findings and implementation

- Membership changes discard presentation frames. `ParkRuntime._membership_entry()`
  calls `_reset_history()`, which drops every frame. A service computes ahead of its
  presentation clock, so a tier swap at the frontier leaves the presentation time
  outside the retained frames and `packet()` raises, which pauses the service worker.
  Implementation: a membership change restarts the rollback checkpoints at the
  boundary and keeps earlier frames for presentation; `intervene()` refuses a time
  before the earliest checkpoint; `packet()` omits a region from a frame recorded
  before that region joined; `save_committed()` refuses a presentation time before
  the earliest checkpoint with an explicit error.
- No focus message. The service accepts `interest`, `clock` and `intervene` only.
  Implementation: `Focus.parse()` in `contracts.py` validates the section 8 fields
  (`sequence`, `position_m`, `velocity_mps` required; `t_s`, `view_dir`, `fov_deg`,
  `reach`, `resident`, `time_scale` optional); `POST /api/park/focus` queues it like
  the other commands; a focus older than the accepted sequence is ignored; a focus
  `time_scale` sets the requested rate under the clock command's bounds. A service
  without a residency policy rejects focus.
- No world-to-chainage mapping. Residency works on river chainage while focus carries
  local-frame meters. Implementation: `RiverChainage` in `residency.py` projects
  `x` and `z` onto the mapped centerline pieces of the published replay cells
  (`position_xyz`, `downstream_unit_xz`, `start_s_m`, `end_s_m`) and returns the
  chainage, the lateral distance and the along-channel velocity, positive downstream.
  The nearest piece decides the segment at any lateral distance; the distance is
  reported.
- The service cannot run residency. Implementation: `RuntimeService(residency=...,
  chainage=...)` applies `ResidencyManager.update()` at every worker iteration and on
  each focus, advances through `ResidencyManager.advance()` with pruning at the
  presentation time, moves the presentation clock at the lesser of the requested and
  the effective rate, and publishes a `residency` block: `focus_sequence`, `active`,
  `activating`, `retiring`, `coarse`, `reach`, `ranked`, `effective_rate`,
  `requested_rate`, `held`, `lead_wall_s`, capacity, worker rate and the walker's
  chainage, lateral distance, segment, representation and water temperature.
  Interventions are refused under residency because spin-up replays recorded interface
  history that an intervention would invalidate. `python -m
  yellowstone_python.park_runtime --firehole` serves the published replay with
  residency and writes no state file, because segment checkpoints are not persistable.
- `ParkClient` neither sends focus nor reads residency. Implementation:
  `set_focus()` takes the absolute local position as three floats, the velocity, the
  view direction and the field of view, and the client posts it once per
  `focus_interval_s` (1 s); state packets set `residency`. `world.gd` streamed mode
  passes the walker's absolute position from `park_frame.absolute_xz()` each physics
  tick.
- Accelerated time untested. `run_walk()` accepts a time scale but every recorded walk
  ran at 1x. Implementation: `tools/park_firehole_walk.py` gains `--time-scale`,
  `--start-m`, `--end-m` and `--no-reference`, records hold statistics and the forcing
  window, and `evaluate_walk()` excludes segments still in the final target set from
  the passed-segment check, because the upstream halo grows with the time scale.

## Acceptance tolerances, set before the runs

Settings as in `fixes-69` (six segments of 46 cells, quantum 10 s, fine step 1 s,
coarse cells of 23, spin-up 3600 s, lead margin 30 s, retirement hysteresis 10 s wall,
utilization 0.8), published replay forcing. The forcing covers 7200 s; the solver holds
its last values after that, so accelerated runs are runtime checks, not scenario
results.

Run A, time scale 60, walker 1.4 m/s of wall time from the upstream face to the outlet:

1. Every segment the walker enters is installed before the walker crosses its upstream
   face; zero updates with the walker on coarse state.
2. Every segment that leaves the target set returns to coarse within its hysteresis
   plus one quantum of wall time; segments behind the walker outside the final target
   set are coarse at the end.
3. Hand-off water and heat within 1e-12 relative at every swap.
4. Tier heat closure within 1e-9 of throughput; interface heat and water and total
   water within 1e-9 relative.
5. Demand inside the capacity budget at every update, or the hold reported.

Run B, time scale 3600 requested, walker 1.4 m/s from chainage 800 m to 1100 m across
the face between `firehole.s0` and `firehole.s1`: items 1, 3, 4 and 5 of run A, and at
every update where the reach cells times 3600 exceed the budget the hold is reported
with the effective rate equal to the budget over the reach cells within 1e-12
relative.

Recorded as a diagnostic without a tolerance: the walker-cell temperature against the
single-domain solver at the same times (run A).

Service and client:

6. A focus at a replay cell's `position_xyz` reports that cell's segment with lateral
   distance below 1e-6 m and chainage equal to the cell's `center_s_m` within 1e-6 m.
7. The publication after a focus carries the sent `focus_sequence`; a lower sequence
   leaves it unchanged; the walker segment is in `active` once installed.
8. The presentation clock advances at the lesser of the requested and effective rates.
9. An intervention under residency is rejected with an explicit error; the Firehole
   service stopped with SIGTERM exits 0 without a state file.
10. A membership change at the frontier keeps the bracket valid at a presentation
    time before it; an intervention before the change is refused.
11. `client_service_check.gd` with a focus position reaches a residency report that
    echoes its focus sequence with the walker segment fine.

## Verification

- Python tests for items 6 to 10 and a demo-river walk at 60x and at a held rate.
- `tools/park_firehole_walk.py` runs A and B; results recorded in the ledger.
- `client_service_check.gd` against `python -m yellowstone_python.park_runtime
  --firehole`; legacy and streamed `--smoke-test`.
- `pytest tests/park_runtime`, full `pytest -q`, a build and `audit_provenance`;
  `check_comment_style.py` and the prose pattern checker clean on touched files.

## Sources

- `yellowstone_python/park_runtime/runtime.py`, `service.py`, `contracts.py`,
  `residency.py`, `__main__.py`; `tools/park_firehole_walk.py`.
- `yellowstone_midway/scripts/park_runtime/park_client.gd`, `scripts/world.gd`,
  `tests/park_runtime/client_service_check.gd`.
- `yellowstone_python_spec/04_PARK_STREAMING_SPEC.md` sections 3, 7.1, 8 and 11;
  `fixes/ledger/fixes-69.md`.
