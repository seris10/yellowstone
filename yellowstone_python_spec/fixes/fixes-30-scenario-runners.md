# fixes-30: hot low-flow and tributary-refuge scenario runners
Scope:
  yellowstone_python/tools/run_hot_lowflow.py sha256:3cc0e89ae2ae
  yellowstone_python/tools/run_hot_lowflow_tributary_refuge.py sha256:4b0b8dea465f
  yellowstone_python/tools/run_hot_lowflow_with_tributaries.py sha256:00169442e056
Callers read:
  yellowstone_python/README.md (sections "Hot low-flow scenario",
    "Tributary cold-refuge pockets", "Shear-to-disturbance coupling",
    "Fischer-D replay")
  yellowstone_python/yellowstone_python/aquatic_foodweb.py
    (compare_runs, thermal_landscape, run_foodweb,
    TRIBUTARY_CANDIDATES, TRIBUTARY_FOOD_SCALE_DEFAULT,
    build_tributary_cell, append_tributary_cells)
  yellowstone_python/yellowstone_python/fish.py
    (THERMAL_SPECIES, t_refuge_c, t_uilt_c, REFUGE_WEIGHT)
  yellowstone_python/yellowstone_python/insects_birds.py
    (trout_diet_at_temp)
  derived/hot_lowflow_replay.json,
  derived/aquatic_hot_lowflow.json,
  derived/aquatic_hot_lowflow_tributary_refuge.json,
  derived/aquatic_tributary_sweep.json,
  derived/aquatic_dispersion_d85.json,
  derived/aquatic_hot_lowflow_d85.json,
  derived/aquatic_hot_lowflow_with_tributaries.json,
  derived/aquatic_intervention.json
Related docs: fixes/fixes-19-tributaries.md and ledger/fixes-19.md
  (v2 runner and fetcher; the v1 file audited here duplicates the
  same class of bugs with different fabricated values)

## Main problems

### 1. run_hot_lowflow_with_tributaries.py is an orphan runner that fabricates two tributaries not present in the baseline survey

run_hot_lowflow_with_tributaries.py:60-121 builds a "Fairy
Creek" refuge cell and :124-185 builds a "Glacier Creek" refuge
cell, with hardcoded initial_c 11.5 and 10.5, hardcoded start_s_m
3500.0 and 4000.0, hardcoded discharge, and a complete authored
hydraulics block (froude, bed_shear_pa, travel_time_s, slope).
aquatic_foodweb.py:19-74 TRIBUTARY_CANDIDATES carries the survey
result these numbers should defer to: of the four
DEFAULT_TRIBUTARIES only two mapped creek polylines touch the
replay chain, Rabbit Creek at s=1260.0 and Mallard Creek at
s=35.0, both at 11.0 C with "authored_scenario_from_DEFAULT_
TRIBUTARIES ... zero_flow_baseline_no_observation" provenance.
Fairy Creek is explicitly recorded as >1300 m off-chain in that
survey header and is not a candidate. "Glacier Creek" is not in
DEFAULT_TRIBUTARIES, is not in world.json's mapped creek list in
the survey header, and is labeled in the file as
"glacier-fed tributary" (run_hot_lowflow_with_tributaries.py:144
"depth_source": "High-elevation glacier-fed tributary (authored)")
which conflicts with the geology of the Firehole upstream of
Midway: there are no glaciers in that catchment.

The runner is not referenced from the four README sections in
scope. Its output artifact
derived/aquatic_hot_lowflow_with_tributaries.json exists but is
not cited in README. The runner is a dead parallel path to
run_hot_lowflow_tributary_refuge.py, which uses the audited
TRIBUTARY_CANDIDATES through aquatic_foodweb.append_tributary_cells.

### Fix

Delete run_hot_lowflow_with_tributaries.py and
derived/aquatic_hot_lowflow_with_tributaries.json,
derived/hot_lowflow_with_tributaries.json. The scientifically
defensible path is run_hot_lowflow_tributary_refuge.py which
sources specs from aquatic_foodweb.TRIBUTARY_CANDIDATES. If a
future author wants a solver-level tributary mixing experiment,
file it against the river_transport prescribed-source API, not a
cell-append shim, and use only candidates listed in
TRIBUTARY_CANDIDATES or added to it with the same map-measured
confluence provenance string pattern.

### Test

Add tests/test_scenario_runners.py::test_no_fabricated_tributaries
that imports every file under yellowstone_python/tools matching
run_hot_lowflow*.py and asserts that any tributary-cell dict
appended to pulse_doc["cells"] uses an id listed in
TRIBUTARY_CANDIDATES. A second case asserts the file
run_hot_lowflow_with_tributaries.py has been removed.

---

### 2. run_hot_lowflow_with_tributaries.py appends refuge cells to replay solver cells, violating coupling.pocket_holding

run_hot_lowflow_with_tributaries.py:188
`modified_doc["cells"] = pulse_doc["cells"] + [fairy_creek_cell, glacier_creek_cell]`
and :191-200 extend each frame's temperature_c array with the new
temperatures. The appended cells carry `"river_id": "river_5856_0"`
(:77) and `"river_id": "river_5872_0"` (:141), i.e. mainstem solver
ids, not `"tributary"`. coupling.py's POCKET_CONSERVATION label
exists specifically to keep prescribed holding water out of solver
cells. aquatic_foodweb.append_tributary_cells by contrast tags
each pocket `"river_id": "tributary"` and
`"conservation": POCKET_CONSERVATION` and operates on the LANDSCAPE
dict, not the replay (aquatic_foodweb.py:174-181, 217-242).

This is the identical class of bug fixes-19 item 5 raises
against run_hot_lowflow_with_tributaries_v2.py. The v1 file
audited here has it too, with the extra wrinkle that the appended
`q_in_m3_s`/`q_out_m3_s` fields do not balance
(see finding 3).

### Fix

Removed by finding 1. If any future replacement is written, do
not append to `modified_doc["cells"]`; call
`append_tributary_cells(thermal_landscape(pulse_doc), specs=...)`
and pass the result through `compare_runs(..., extra_cells=extra)`,
which is the contract-honoring path.

### Test

If a replacement runner exists, add a parametrized test
asserting every cell in `pulse_doc["cells"]` after the runner
completes has `river_id` matching the original mainstem feature
set. aquatic_foodweb.test_aquatic_foodweb.py's
TributaryTests pattern (same file, same style) is the template.

---

### 3. with_tributaries.py breaks mass conservation at the mouth cells (q_in != q_out)

run_hot_lowflow_with_tributaries.py:74-75
```
"q_in_m3_s": 1.0,  # Tributary discharge (authored)
"q_out_m3_s": 3.5,  # Adds to main flow
```
and :138-139
```
"q_in_m3_s": 1.8,
"q_out_m3_s": 4.3,
```
inject 2.5 m3/s per cell with no corresponding source accounted
anywhere in the replay solver's lateral budget. For context:
boundary_m3s is 2.5 (:35), so each refuge cell silently doubles
the mainstem discharge of the entire scenario. The thermal
solver that produced the replay never saw this water and never
heat-mixed it in; the modified document therefore carries a
discharge field that is physically impossible and uncoupled from
every downstream flow calculation.

Same class as fixes-19 item 8. In v2 the pattern was
`q_out = discharge * 2.5`; here it is hardcoded.

### Fix

Removed by finding 1. If pockets must carry flow at all, they are
holding water: use `flow_m3_s = discharge_m3s` and drop
q_in/q_out, matching
coupling.pocket_holding/conservation=non_conservative, and leave
mainstem face discharges alone.

### Test

If a replacement runner exists, assert that for every appended
pocket cell either (a) `q_in_m3_s == q_out_m3_s` to within 1e-9,
or (b) the cell carries `conservation == POCKET_CONSERVATION`
and no `q_in_m3_s`/`q_out_m3_s` fields.

---

### 4. with_tributaries.py quadruples frame temperatures and would desync landscape length

run_hot_lowflow_with_tributaries.py:191-200
```
for frame in modified_doc["frames"]:
    new_temps = []
    for _ in range(2):  # Two tributary cells
        new_temps.append(11.5)  # Fairy Creek temperature
        new_temps.append(10.5)  # Glacier Creek temperature
    frame["temperature_c"] = frame["temperature_c"] + new_temps
```
appends 4 temperatures per frame but only 2 cells are appended at
:188. aquatic_foodweb.thermal_landscape asserts
`len(temps) == len(cells)` for every frame
(aquatic_foodweb.py:111-114). Any run of this script against a
replay the length check would gate should raise ValueError, which
means either the asserts in thermal_landscape were weaker when
the live artifact
derived/aquatic_hot_lowflow_with_tributaries.json was baked, or
the script's live downstream path bypasses thermal_landscape. The
current artifact pulse `firehole_tributary_fairy_creek_001` at
s=3501.5 and temperature 11.5 (jq verified) is reachable only if
the check did not fire; this is NOT VERIFIED by rerun (brief
disallows), but the per-frame length mismatch is immediate from
reading the loop.

### Fix

Removed by finding 1. If a replacement is ever written, the loop
is `for cell in extra_cells: new_temps.append(cell["initial_c"])`.
See fixes-19 item 6 for the same pattern in v2.

### Test

Parametrized test: for every pulse_doc produced by a scenario
runner, assert every frame's `len(temperature_c) == len(cells)`.
This belongs in tests/test_scenario_runners.py and catches the
general class.

---

### 5. The refuge-flip conclusion is an artifact of the purely relative food term with no absolute starvation

aquatic_foodweb.py:339-345 computes a cell food as
`edible * scale`, then :345 `ceiling = max(foods) or 1.0` and
:356 `u = suitability(food / ceiling, ...)`. Pocket food is
scaled by `food_scale` (0.05 by default), so a pocket's food
production is 5 percent of a mainstem cell's. But the
suitability input is the daily ratio to the max, bounded in
[0, 1], not an absolute production rate. A fish that occupies a
pocket producing zero food has `food/ceiling = 0`, which is a
single term in a weighted U; the thermal and refuge terms still
score the pocket favorably, and the fish picks it.

derived/aquatic_tributary_sweep.json size_sweep_at_spec_temp at
food_scale=0.0 shows pulse_cell = `trib_rabbit_creek` at s=1260,
pulse_U = -0.076, flipped_to_tributary = true. aquatic_foodweb.py
provenance string
(aquatic_foodweb.py:453-461) states this directly:
"per-cell production normalized by the daily maximum: purely
relative ranking, absolute starvation is impossible in this
model". README section "Hot low-flow scenario" repeats:
"food is purely relative (starvation impossible, so a best cell
always exists); drift, molluscs, mortality unmodeled as before -
a real fish leaves or dies where this one holds". README section
"Tributary cold-refuge pockets" repeats:
"no size un-flip exists while the mainstem sits at 25-28 C;
thermal + refuge terms dominate. U-math, not tuning."

The limitation is admitted. The problem is that the
"yes, it flips" headline conclusion in the tributary refuge
section follows directly from the model structure: once a
pocket exists below t_refuge_c=24.0 while the mainstem exceeds
it, the thermal_performance.feeding and refuge_drive terms
guarantee the pocket wins regardless of food, cover, velocity,
or mortality. The scenario is testing whether the model is
consistent with itself, not whether a real fish would relocate.

### Fix

The code is self-consistent and labeled. The claim text needs
two concrete changes:

Change in README "Tributary cold-refuge pockets" section:
replace "Result: YES, it flips" with
"Result: the model picks a pocket in every size variant,
including the zero-food (starved) pocket; the refuge-drive and
feeding terms dominate the suitability sum once a sub-24 C cell
exists, so the flip is a structural prediction of this model's
U, not a field prediction".

Add in run_hot_lowflow_tributary_refuge.py scenario block
(:100-116) a field
`"model_scope": "selection_only_no_mortality_no_movement_cost_no_
absolute_food"` and a field
`"starvation_absent": true`.

Optional, separate fix: wire run_foodweb to accept an
`absolute_food_floor` that drives U down when the daily food
total in the picked cell is below a per-day energetic
requirement from the trout literature (e.g. Elliott 1975
maintenance ration at the picked temperature). Score this as a
diagnostic, not a validation gate.

Primary source for an absolute requirement: Elliott, J.M. 1975
"The growth rate of brown trout (Salmo trutta L.) fed on maximum
rations" J. Anim. Ecol. 44:805-821 (already cited in
fish.THERMAL_SPECIES_PROVENANCE at fish.py:30, 44).

### Test

tests/test_aquatic_foodweb.py already exercises
ShearDisturbanceTests. Add a FoodScaleStarvationTest that
runs compare_runs with a two-cell landscape (hot mainstem 27 C,
cold pocket 11 C) at food_scale=0.0, asserts the pulse selects
the cold pocket, then documents in the test docstring that
the flip is a structural property of the model and does not
imply field persistence.

---

### 6. The 26 C boundary equals brown-trout UILT exactly; the scenario puts the whole river at the upper lethal limit by construction

run_hot_lowflow.py:34
`BOUNDARY_C = 26.0  # authored scenario; below observed 29.5 C max`
and run_hot_lowflow_with_tributaries.py:36 identical.
fish.py:57 `t_uilt_c: 26.0` for brown_trout, :69 `t_uilt_c: 26.0`
for rainbow_trout.
fish.THERMAL_SPECIES_PROVENANCE at fish.py:33 cites
"NDEP BrownTTA (UILT 24.4-26.5 C, reviewed literature)" and
:46 "NDEP RainbowTTA (UILT 24.3-26.7 C)". 26.0 is at the top of
brown's measured UILT range and inside rainbow's.

The scenario is therefore not a "hot" scenario in the sense of
exceeding what the fish tolerates by a stated margin; it is a
scenario in which the inflow temperature is already at UILT and
heats downstream, so the entire replay sits above UILT. derived/
hot_lowflow_replay.json verified by jq: per-cell time-mean
temperature range 25.05 to 28.50 C, overall mean 26.60 C, 276
cells, zero cells with mean below the Kaya 24 C refuge
threshold.

The design is scientifically defensible as a bracketing case
("below the observed 29.5 C max"), but the exact equality
26.0 C boundary = 26.0 C UILT in the module is a coincidence
only if the UILT value was authored before the scenario
boundary was chosen. More defensibly, the scenario should use a
boundary strictly below UILT so the "refuge flip" question is
not pre-answered by the choice of boundary.

The "observed 29.5 C max" phrase traces to the Kaya, Kaeding,
Burkhalter 1977 Firehole temperatures (fish.py:62, 74). The
29.5 C figure itself is NOT VERIFIED here against a primary
source: no file in the audited scope quotes a page or
instrument record for it. Burkhalter 1979 (
run_hot_lowflow.py:33 provenance string
"measured_Burkhalter_1979_baseflow_2-3") is likely Burkhalter,
D.E. 1979 MSc thesis "Fishery investigations of the thermally
stressed Firehole River" (Montana State), cited in Kaya et al.
1977 and Kaeding 1976 context; this attribution is NOT VERIFIED
here.

### Fix

run_hot_lowflow.py add a second scenario constant
`BOUNDARY_C_SUB_UILT = 25.0` and a `--sub-uilt` flag that
switches to it, so the scenario has both a "boundary at UILT"
case (current) and a "boundary below UILT by 1 C" case. Record
both in the scenario block with provenance strings
"authored_at_brown_trout_UILT_26C_fish.THERMAL_SPECIES" and
"authored_1C_below_brown_trout_UILT_fish.THERMAL_SPECIES".

Add primary-source citations as fully qualified fields in the
scenario block:
```
"boundary_m3s_source": {
    "citation": "Burkhalter, D.E. 1979. Fishery investigations of the
                 thermally stressed Firehole River. MSc thesis,
                 Montana State University.",
    "value_cited_in_file": "2-3 m3/s geothermal baseflow",
    "verification": "NOT VERIFIED against primary source in this repo"
},
"observed_max_c_source": {
    "citation": "Kaya, C.M., Kaeding, L.R., Burkhalter, D.E. 1977.
                 Use of a cold-water refuge by rainbow and brown
                 trout in a geothermally heated stream.
                 Prog. Fish-Cult. 39:37-39.",
    "value_cited_in_file": "29.5 C observed maximum",
    "verification": "NOT VERIFIED against primary source in this repo"
},
"uilt_c_source": {
    "citation": "Nevada DEP, BrownTTA/RainbowTTA technical reviews
                 citing Grande & Andersen 1991 and others.",
    "value_cited_in_file": "26 C brown UILT, 26 C rainbow UILT",
    "verification": "citation chain documented in fish.py:33, 46"
}
```

The primary-source entries belong in configs/scenarios/hot_lowflow.yaml
once such a file exists; for now, in the runner's scenario block.

### Test

tests/test_scenario_runners.py::test_boundary_c_labeled_vs_uilt
asserts that run_hot_lowflow.py's scenario block carries
`boundary_c_source` with a citation field and a verification
field. A separate assertion compares the written boundary_c to
fish.THERMAL_SPECIES["brown_trout"]["t_uilt_c"] and warns via
the sidecar if the two match within 0.1 C.

---

### 7. "Chronic full-run means" documents behavior but hides spin-up contamination

run_hot_lowflow.py:11 docstring says
"Both landscapes are full-run means (chronic scenario, not a
short pulse: no window_s)."
run_hot_lowflow.py:77-78 and
run_hot_lowflow_with_tributaries.py:253 call
`compare_runs(control_doc, pulse_doc, None, ...)` with
window_s=None. aquatic_foodweb.compare_runs at
aquatic_foodweb.py:482-485 then averages every frame including
the start-of-replay transient from the solver's initial
condition. derived/hot_lowflow_replay.json n_frames = 721 at
whatever cadence the baseline writes; the first several frames
represent the ramp from `initial_c` to the quasi-steady
temperature at the hot boundary, which drags the per-cell mean
cooler than steady state.

Verified: overall frame temperature mean 26.60 C (jq, same as
the per-cell time mean, which only matches if the ramp is
negligible or if the replay is long enough that the ramp is a
small fraction). This is NOT VERIFIED to be small; the runner
does not record a settle-time check.

run_hot_lowflow_tributary_refuge.py:97, :126, :132 call
compare_runs with window_s=None too (via `run_case`), inheriting
the same issue.

### Fix

Add to run_hot_lowflow.py and
run_hot_lowflow_tributary_refuge.py a `--settle-s` flag
(default 0 for backward compatibility) that passes
`window_s=(settle_s, +inf)` into compare_runs by using the
replay's final frame time as the upper bound. Record the
settle_s in the scenario block as
`"settle_s": settle_s, "settle_provenance":
"authored_discard_leading_transient"`. Separately, in each
runner, verify convergence by comparing the first-half and
second-half time means of each cell and refusing to publish if
any cell's halves differ by more than 0.5 C; call this the
"quasi-steady check" and record its result in the scenario
block.

### Test

tests/test_scenario_runners.py::test_quasi_steady_check runs
run_hot_lowflow.py against a short illustrative replay and
asserts the scenario block has
`"quasi_steady_check": "passed"` (or an explicit
`"quasi_steady_check": "skipped"` with reason).

---

### 8. The two scenario runners duplicate boundary constants and provenance strings instead of sourcing one authority

run_hot_lowflow.py:33-34
```
BOUNDARY_M3S = 2.5  # Burkhalter 1979 geothermal baseflow 2-3 m3/s (measured)
BOUNDARY_C = 26.0  # authored scenario; below observed 29.5 C max
```
run_hot_lowflow_with_tributaries.py:35-37 duplicates these plus
`T_REFUGE_THRESHOLD_C = 24.0  # Kaya, Kaeding & Burkhalter 1977 measured threshold`.
run_hot_lowflow_tributary_refuge.py :101-104 writes the same
boundary values as a prose string inside the scenario block
"hot low-flow (2.5 m3/s, 26 C boundary) vs pinned control".

The provenance string
`"measured_Burkhalter_1979_baseflow_2-3"` appears literally in
run_hot_lowflow.py:81 and run_hot_lowflow_with_tributaries.py:258.
If Burkhalter 1979 ever needs correction (page number, revised
range, superseding reference), there is no single place to
update it; no module imports from a shared "scenario_constants"
authority. yellowstone_python/param_registry.py is the stated
authority for authored constants (AGENTS.md section 1 item 4);
nothing in the audited files imports it for this scenario.

### Fix

Add
`yellowstone_python/scenario_constants.py` with:
```
HOT_LOWFLOW_BOUNDARY_M3S = 2.5
HOT_LOWFLOW_BOUNDARY_M3S_SOURCE = {
    "citation": "Burkhalter 1979",
    "range_cited": "2-3 m3/s",
    "verification": "pending primary-source confirmation",
}
HOT_LOWFLOW_BOUNDARY_C = 26.0
HOT_LOWFLOW_BOUNDARY_C_SOURCE = {
    "citation": "authored scenario; below Kaya 1977 29.5 C max",
    "verification": "scenario-authored not measured",
}
REFUGE_THRESHOLD_C = 24.0
REFUGE_THRESHOLD_SOURCE = {
    "citation": "Kaya CM, Kaeding LR, Burkhalter DE 1977.
                 Prog. Fish-Cult. 39:37-39.",
    "value_cited": "mean > 24 C refuge threshold",
    "verification": "citation chain only; abstract verified",
}
```
Import these in run_hot_lowflow.py, run_hot_lowflow_tributary_refuge.py
and (if kept) any replacement for with_tributaries.py.

Alternative: register them in param_registry.py and read via
`param_registry.get("hot_lowflow.boundary_m3s")`. The latter
threads with claims.py claim ids.

### Test

tests/test_scenario_runners.py::test_boundary_constants_single_source
imports both runners and asserts
`run_hot_lowflow.BOUNDARY_M3S == scenario_constants.HOT_LOWFLOW_BOUNDARY_M3S`.
Add a grep gate in tools/audit_provenance.py checking that no
runner defines a module-level `BOUNDARY_` or `T_REFUGE` constant
outside scenario_constants.py.

---

### 9. The N=1 "Rabbit Creek only" variant is produced but never emitted into its own artifact file for reuse

run_hot_lowflow_tributary_refuge.py:136-138 computes
```
_, single = run_case(control_doc, pulse_doc, specs[:1], None,
                     TRIBUTARY_FOOD_SCALE_DEFAULT,
                     args.days, args.species)
```
and inlines the summary into
derived/aquatic_tributary_sweep.json under
`single_pocket_rabbit_only_at_defaults`. README section
"Tributary cold-refuge pockets" cites this run specifically:
"Rabbit-only variant flips to s=1260 (U -0.07, -1612.5 m)".
jq-verified against the artifact: pulse_cell trib_rabbit_creek,
pulse_U -0.07, refuge_shift_m -1612.5. The claim reproduces.

But the N=1 run only writes the summary row, not the full
compare_runs document (control+pulse state, emergence totals,
dipper totals). The main N=2 artifact
derived/aquatic_hot_lowflow_tributary_refuge.json is paired with
the sweep rows; the single-pocket result has no paired full
document and cannot be independently compared with
run_hot_lowflow.py's N=0 baseline except via the sweep summary.

### Fix

run_hot_lowflow_tributary_refuge.py: add a
`--out-single-pocket` argument that, when provided, writes the
single_doc from run_case (not just the row) as a sibling to
--out, with the same scenario block tagged
`"design": "landscape_level_pocket_rabbit_only_N1"`. Keep the
existing summary row in the sweep for backward compatibility.

### Test

tests/test_scenario_runners.py::test_single_pocket_full_doc_emitted
asserts that invoking the runner with --out-single-pocket
produces a file with the yellowstone.aquatic_intervention.v1
schema and that its refuge_shift_m matches the sweep's
single_pocket_rabbit_only_at_defaults.refuge_shift_m.

---

### 10. README "25.1 C" is a round-up; the actual per-cell minimum is 25.05 C and the raw frame minimum is 24.95 C, which is below Kaya 24 C only in a frame sense

README section "Hot low-flow scenario":
"in-chain water 25.1-28.5 C (mean 26.6) - NO cell below the
Kaya 24 C threshold anywhere in 276 cells".

jq against derived/hot_lowflow_replay.json verified:
- overall frame temperature pool (276 cells x 721 frames):
  min 24.95113600763278, max 28.541916385476767,
  mean 26.60300288029337
- per-cell time means (what thermal_landscape and the foodweb
  consume):
  min 25.045085981520582, max 28.49936079417287,
  mean 26.60300288029337

So "25.1" rounds up from 25.045 (rounding is upward, so the
reported value overstates the cold edge). "28.5" rounds down
from 28.542. "mean 26.6" is exact to one decimal. "276 cells"
matches n_cells. "NO cell below Kaya 24 C" is correct for
per-cell time means (min 25.05 > 24.0) but not for individual
frames (minimum frame-cell is 24.95, still above 24 but by only
0.05 C).

The 24.95 frame minimum nearly touches the Kaya mean threshold
and does cross the Kaya 25 C max threshold referenced in the
abstract (fish.py:37 "mean >24C / max >25C"). README does not
state this.

### Fix

Edit README "Hot low-flow scenario" paragraph:
```
- Result: in-chain water (per-cell time means) 25.05-28.50 C
  (overall mean 26.60), rounded in prose to 25.1-28.5 C
  (mean 26.6). No cell's time mean falls below the Kaya mean
  threshold 24 C across 276 cells; the raw frame minimum is
  24.95 C (one frame-cell within 0.05 C of the mean threshold,
  below the Kaya max threshold 25 C).
```

### Test

tests/test_scenario_runners.py::test_hot_lowflow_readme_numbers
loads derived/hot_lowflow_replay.json, recomputes the overall
mean, the per-cell time-mean min and max, and the frame-min and
frame-max, and asserts the README-prose rounding is consistent
with the values recomputed to one decimal. Fail if any digit in
the README differs from the recomputed rounding.

---

### 11. The Fischer-D claim "same qualitative outcome as D1 (+2357 m, -221, +1.85)" uses D1 numbers inside a D85 paragraph without naming the D85-vs-D85 shift

README section "Fischer-D replay":
"Intervention repeated at D85: drive fires, trout holds s=5230
@27.7 C, emergence -220, dipper +1.85 - same qualitative
outcome as D1 (+2357 m, -221, +1.85). Conclusion robust: at
2.5 m3/s + 26 C boundary the mainstem offers no sub-24 C water
at either dispersion."

jq against derived/aquatic_hot_lowflow_d85.json: control is
firehole_cell_00113 at s=2236.0532 and 17.39 C, pulse is
firehole_cell_00263 at s=5229.9 and 27.74 C, refuge_shift_m
is 2993.8, emergence_change -219.7855, dipper_intake_change
1.8488. The s=5230, 27.7 C, -220 and +1.85 reproduce. The
D85-vs-D85 refuge shift is +2993.8 m, not written in the
paragraph. The "+2357 m" cited in the parens is the D1 shift
from derived/aquatic_hot_lowflow.json (verified +2357.4). The
paragraph conflates two comparisons: (a) D85-baseline vs
D85-hot (+2993.8 m), (b) D1-baseline vs D1-hot (+2357 m).

### Fix

Edit README "Fischer-D replay" paragraph:
```
- Intervention repeated at D85 (control = D85 baseline cell_00113
  at 2236 m, 17.4 C; pulse = D85 hot cell_00263 at 5230 m,
  27.7 C): shift +2993.8 m, drive 0 to 1.0, emergence -220,
  dipper +1.85. For comparison the D1 run against the pinned D1
  baseline (cell_00145 at 2873 m, 17.4 C) shifts +2357 m with
  the same qualitative outcome. Conclusion robust: at 2.5 m3/s
  and 26 C boundary the mainstem offers no sub-24 C water at
  either dispersion.
```

### Test

tests/test_scenario_runners.py::test_fischer_d_readme_numbers
loads derived/aquatic_hot_lowflow_d85.json and
derived/aquatic_hot_lowflow.json and asserts the paragraph's
quoted numbers match each file to one decimal.

---

### 12. The "food scale default 0.05" is an authored area ratio that lacks a sensitivity-to-mainstem-cell-size check

aquatic_foodweb.py:75-80 sets
TRIBUTARY_FOOD_SCALE_DEFAULT = 0.05 with provenance
"authored_area_ratio_22m2_pocket_over_440m2_mainstem_cell". The
numerator 22 m^2 is TRIBUTARY_WIDTH_M=6.0 x authored pocket
length ~3.67 m, both authored. The denominator ~440 m^2 is one
"typical cell" (comment:76 ~20 m x 22 m). derived/
hot_lowflow_replay.json cells vary in length and width; the
"440 m^2" is representative, not the per-cell actual.

run_hot_lowflow_tributary_refuge.py:131-134 sweeps
`SIZE_SWEEP_SCALE = (0.0, 0.01, 0.05, 0.2, 1.0)` and reports
the flip holds at every value. That is good coverage of the
scaling choice. But the sensitivity never varies the pocket
WIDTH_M, DEPTH_M, VELOCITY_M_S inputs to suitability (held at
6.0, 0.5, 0.25 in aquatic_foodweb.py:81-83): those three enter
velocity and depth suitabilities in fish.suitability and are
not swept.

### Fix

Add to run_hot_lowflow_tributary_refuge.py a second sweep
VELOCITY_DEPTH_SWEEP that varies pocket velocity and depth
across the brown-trout literature ranges
(e.g. Elliott 1975 held fish at ~0.1-0.4 m/s): run the N=2 case
at (velocity, depth) in
[(0.1,0.3), (0.25,0.5), (0.5,1.0)] with everything else at
default. Emit a `velocity_depth_sweep` section in
derived/aquatic_tributary_sweep.json alongside the existing
temperature and size sweeps.

### Test

tests/test_scenario_runners.py::test_velocity_depth_sweep_emitted
asserts the sweep artifact contains the new section with three
rows, each with pulse_cell either in TRIBUTARY_CANDIDATES ids or
in the mainstem feature set.

---

### 13. run_hot_lowflow.py print-only emission of the +2 C result; no artifact file is written for the comparison claim

README section "Hot low-flow scenario":
"Compare +2 C run: +20 m shift, emergence +98, dipper +0.15,
drive silent."

jq against derived/aquatic_intervention.json: refuge_shift_m
19.9, emergence_change 98.1733, dipper_intake_change 0.1503.
These reproduce. But run_hot_lowflow.py (the runner cited by
the README section) does not write
aquatic_intervention.json. The file is produced by
yellowstone_python.aquatic_foodweb's own CLI
(aquatic_foodweb.py:530-554 `main()`), not by any
run_hot_lowflow* runner.

The README claim is reproducible against an artifact, but the
artifact's provenance chain to run_hot_lowflow.py is broken:
nothing in the runner emits it, and the audit scope "scenarios
these runners produce" does not include aquatic_intervention.json.

### Fix

Either (a) add to run_hot_lowflow.py a `--plus-c` argument
(default 0.0; when non-zero, writes an additional
aquatic_<name>_plus<c>.json via compare_runs with the +c
boundary against the same control), and change README to cite
this runner; or (b) move the +2 C sentence into a separate
README section tied explicitly to the aquatic_foodweb CLI.

### Test

tests/test_scenario_runners.py::test_plus_c_artifact_written
runs run_hot_lowflow.py with --plus-c 2.0 and asserts a file
matching the convention is produced with refuge_shift_m within
1 m of 19.9.

---

### 14. Scenario runners do not set run_mode on the modified config, so the hot-lowflow build inherits baseline.yaml's "illustrative" tag instead of "scenario"

run_hot_lowflow.py:55-60
```
cfg = load_config(Path(args.config))
hot = copy.deepcopy(cfg)
hot.setdefault("hydro", {})["boundary_m3s"] = args.boundary_m3s
hot["hydro"]["boundary_c"] = args.boundary_c
hot.setdefault("replay", {})["dispersion_m2_s"] = args.dispersion_m2_s
validate_config(hot)
```
No `hot["run_mode"] = "scenario"`. AGENTS.md section 6:
"Every config declares run_mode: illustrative (default),
scenario, hindcast, or observed_replay. forecast builds are
refused."
run_hot_lowflow_tributary_refuge.py never touches run_mode
(it only reads frozen replays).
run_hot_lowflow_with_tributaries.py :219-224 same pattern.

The hot-lowflow replay is explicitly a boundary-condition
scenario, not an illustrative baseline run. Writing it as
illustrative is misleading in the derived artifact's provenance.

### Fix

run_hot_lowflow.py: after copy.deepcopy, before validate_config,
`hot["run_mode"] = "scenario"`. Add the same for
run_hot_lowflow_with_tributaries.py replacement if any. The
tributary_refuge runner reads frozen replays and does not
rebuild, so it inherits whatever run_mode the frozen replay has
(no change needed in that runner).

Record in the scenario block
`"run_mode": "scenario"` and
`"run_mode_provenance": "forced_by_run_hot_lowflow_runner"`.

### Test

tests/test_scenario_runners.py::test_scenario_run_mode asserts
derived/<new-build>/BUILD.json carries run_mode "scenario" when
run_hot_lowflow.py produced the replay.

---

### 15. The "pulse_U U-math" sweep claims a two-sided thermal optimum that disappears above 23 C, but 23 C is already inside the Kaya refuge-drive ramp

README section "Tributary cold-refuge pockets":
"Temperature sweep (7 values @ size 0.05): flips at trib 8-23 C;
at 26 C it stays mainstem (s=5230, U -1.227) - the flip
threshold sits inside the 22-24 C refuge-drive ramp. Coldest is
not best: 8 C (U -0.22) scores worse than 14 C (U -0.02,
two-sided optimum)."

jq against derived/aquatic_tributary_sweep.json
temperature_sweep_at_default_size: rows at 8, 11, 14, 17, 20, 23
all have pulse_cell trib_mallard_creek; at 26 C pulse_cell flips
back to firehole_cell_00263. pulse_U at 8 C is -0.216, at 11 C
-0.065, at 14 C -0.015, at 17 C -0.139, at 20 C -0.514, at 23 C
-1.189, at 26 C -1.227. The 14 C minimum is the two-sided
optimum. ✓

fish.py:56-57 brown trout `t_opt_lo_c: 12.0, t_opt_hi_c: 16.0`;
14 C is inside the authored thermal optimum. ✓

refuge_drive at 23 C is 0.5 in the sweep row, confirming the
pocket itself has entered the refuge-drive ramp when the pocket
water is 23 C. That is the claim. OK.

The pulse_refuge_drive at trib temperatures 8-20 C is 0.0,
meaning the trout at the pocket is not stressed. At 23 C
pocket, drive = 0.5. The claim "the flip threshold sits inside
the 22-24 C refuge-drive ramp" is reproducible but omits that
pulse_U at 23 C (-1.189) is already essentially equal to
mainstem pulse_U at 26 C (-1.227): the pocket at 23 C is
barely preferred (delta ~0.04). A sweep step of 1 C around
23-24 C would locate the actual flip point; the current sweep
jumps 23 to 26 and reports "below 26 flips" rather than "flips
between 23 and 26".

### Fix

run_hot_lowflow_tributary_refuge.py: expand TEMP_SWEEP_C to
(8.0, 11.0, 14.0, 17.0, 20.0, 23.0, 24.0, 25.0, 26.0) to
locate the flip point to 1 C. Update the README prose to quote
the actual flip boundary (which the new sweep will produce).

Fish literature primary source for the thermal optimum anchor:
Elliott, J.M. 1975 J. Anim. Ecol. 44:805-821 for
brown trout maintenance ration. Already cited.

### Test

tests/test_scenario_runners.py::test_temp_sweep_locates_flip
asserts the sweep contains a row with
flipped_to_tributary == True adjacent to a row with
flipped_to_tributary == False, and the temperature gap between
them is at most 1.0 C.

---

### 16. Comment-style violations per AGENTS.md section 2

See the Comment-style violations table below. Enough to flag;
fix in-place when the files are edited for the other items in
this doc.

### Fix

Standard: single-line docstrings or two lines maximum; no
ALL-CAPS emphasis; no "X, not Y" contrasts; no first-person;
no "never ... instead" hypothetical-failure narratives; no
reader addressing; American spelling. The current catalog is in
yellowstone_python_spec/ai-tells/.

### Test

Add a lint pass to tests/test_ai_tells.py over
yellowstone_python/tools/run_hot_lowflow*.py (or run the
existing lint across the tools dir).

---

# Wiring and rendering

- `run_hot_lowflow.py` -> `yellowstone_python.build.run_replay_solver`
  which uses the config's `replay`/`hydro` sections. Writes
  `derived/hot_lowflow_replay.json`
  (schema not written explicitly; it is a replay doc with cells
  and frames) and `derived/aquatic_hot_lowflow.json`
  (schema `yellowstone.aquatic_intervention.v1`). Consumed by:
  - README "Hot low-flow scenario" (prose only).
  - README "Fischer-D replay" when invoked with
    `--dispersion-m2-s 84.7`; writes
    `derived/fischer_D85_replay_*`,
    `derived/hot_lowflow_D85_replay_*`,
    `derived/aquatic_hot_lowflow_D85_*`,
    `derived/aquatic_dispersion_D85_*` (filenames exist as
    `aquatic_dispersion_d85.json`, `hot_lowflow_d85_replay.json`,
    `aquatic_hot_lowflow_d85.json`; the capitalization in README
    does not match the lowercase on disk).
  - `run_hot_lowflow_tributary_refuge.py` reads
    `derived/hot_lowflow_replay.json` as `--pulse`.
- `run_hot_lowflow_tributary_refuge.py` ->
  `aquatic_foodweb.append_tributary_cells` ->
  `aquatic_foodweb.compare_runs` with `extra_cells` plumbing;
  writes `derived/aquatic_hot_lowflow_tributary_refuge.json`
  and `derived/aquatic_tributary_sweep.json`
  (schemas `yellowstone.aquatic_intervention.v1` and
  `yellowstone.aquatic_tributary_sweep.v1`). Consumed by:
  - README "Tributary cold-refuge pockets" (prose only).
- `run_hot_lowflow_with_tributaries.py` ->
  manual cell append into `pulse_doc["cells"]` ->
  `compare_runs(control_doc, pulse_doc_with_tributaries, None)`;
  writes `derived/aquatic_hot_lowflow_with_tributaries.json`
  and `derived/hot_lowflow_with_tributaries.json`. No README
  section in scope cites this runner. Not consumed by any
  caller in the tree.
- Godot renderer: the four README sections in scope describe
  Python-side numerical experiments; `publish` (`yellowstone_
  python.publish`) stages derived artifacts for the renderer
  but no shader or scene in `yellowstone_midway` is implicated
  by these runners' outputs. The hot_lowflow and tributary
  refuge artifacts live under `derived/` only; they are not
  copied to `yellowstone_midway/data/` by any audited runner.
  `derived/aquatic_hot_lowflow*.json` are summary docs, not
  spatial fields, so there is nothing for Godot to render from
  them beyond text in the HUD if the publish step chose to
  surface them (NOT VERIFIED).
- Wiring gap: `run_hot_lowflow_with_tributaries.py` is an
  orphan runner (finding 1). Its artifacts are
  on disk but unreferenced.
- Wiring gap: `run_hot_lowflow.py`'s +2 C claim in README is
  served by `derived/aquatic_intervention.json` which is
  written by `aquatic_foodweb.main` (its own CLI), not by
  any `run_hot_lowflow*` runner (finding 13).
- Wiring gap: scenario constants (boundary 2.5, 26.0, Kaya
  24.0) are duplicated across three files with no shared
  authority (finding 8).

# Comment-style violations

| file:line | text | rule |
|---|---|---|
| run_hot_lowflow.py:11 | "Both landscapes are full-run means (chronic scenario, not a short pulse: no window_s)." | "X, not Y" contrast |
| run_hot_lowflow.py:65-67 | "The raw solver status is not in the derived/ status vocabulary (tools/audit_provenance.py scans top-level bundles); preserve it aside and label the saved scenario replay as what it is." | multi-line narrative; "what it is" reader framing |
| run_hot_lowflow.py:1-18 | docstring 18 lines | docstrings 1-2 lines |
| run_hot_lowflow.py:46-48 | "Fischer median 84.7 is a sensitivity case, not calibration (rests on authored n=0.035/banks)" | "X, not Y" contrast |
| run_hot_lowflow_tributary_refuge.py:1-23 | docstring 23 lines | docstrings 1-2 lines |
| run_hot_lowflow_tributary_refuge.py:9 | "Design notes (minimal honest):" | first-person framing voice |
| run_hot_lowflow_tributary_refuge.py:10-12 | "Pockets are LANDSCAPE cells (aquatic_foodweb.append_tributary_cells), never replay cells/frames: the 1-D solver's heat/water budget closure is untouched." | ALL-CAPS LANDSCAPE; "never ...: ..." hypothetical-failure narrative |
| run_hot_lowflow_tributary_refuge.py:13 | "Inputs are the FROZEN replays" | ALL-CAPS FROZEN |
| run_hot_lowflow_tributary_refuge.py:14 | "the replay solver is not re-run because its code path is unchanged" | hypothetical-failure narrative justification |
| run_hot_lowflow_tributary_refuge.py:96 | "Main comparison at defaults (spec 11 C, area-ratio food scale)." | OK as inline but see line 123 |
| run_hot_lowflow_tributary_refuge.py:123 | "Sensitivity sweeps: temperature at fixed size, size at fixed temp." | reader-addressing style |
| run_hot_lowflow_tributary_refuge.py:135 | "N=1 variant (Rabbit Creek only) at defaults." | OK |
| run_hot_lowflow_with_tributaries.py:1-20 | docstring 20 lines; "Task 1 ... Task 2 ... Task 3" | docstrings 1-2 lines; first-person task narrative |
| run_hot_lowflow_with_tributaries.py:7 | "Discover actual values, do not invent" | "do not invent" hypothetical-failure narrative; reader addressing |
| run_hot_lowflow_with_tributaries.py:19 | "If it never flips, say so with the U-math showing why" | reader addressing; "never" hypothetical-failure |
| run_hot_lowflow_with_tributaries.py:39-44 | "Assumptions for tributary refuge cells based on typical cold-water tributaries. In Yellowstone, cold tributaries are typically: ..." | multi-line narrative; informal "typically" |
| run_hot_lowflow_with_tributaries.py:46-49 | docstring "Add N cold tributary refuge cells to the hot low-flow landscape. Returns a modified pulse_doc with tributary refuge cells appended." | 4 lines, exceeds 1-2 |
| run_hot_lowflow_with_tributaries.py:53-55 | "Define tributary refuge cells based on research observations: 1. Fairy Creek - a documented cold-water tributary in the Firehole River system. 2. Other high-elevation tributaries with cold thermal regimes" | narrative; "based on research observations" without citation |
| run_hot_lowflow_with_tributaries.py:57-59 | "Based on literature: Fairy Creek enters the Firehole River upstream of the main hot pool complex, with mean summer temperature ~8-12 C" | narrative claim without citation |
| run_hot_lowflow_with_tributaries.py:69 | "Chainage where Fairy Creek joins (UPSTREAM of original refuge)" | ALL-CAPS UPSTREAM |
| run_hot_lowflow_with_tributaries.py:133 | "Chainage where Glacier Creek joins (UPSTREAM of original refuge)" | ALL-CAPS UPSTREAM |
| run_hot_lowflow_with_tributaries.py:192-197 | "Extract temperature for the last 3 cells (our new tributaries) ... For each frame, we need to add temperatures for the new cells ... Two tributary cells ... Fairy Creek temperature ... Glacier Creek temperature" | first-person "our"; multi-line narrative; "3 cells" is wrong (2 cells) |

# Priority order

Immediate fixes (correctness and provenance):
1. Delete run_hot_lowflow_with_tributaries.py and its orphan artifacts (finding 1). cheap.
2. Fix the "25.1" rounding and silence about the 24.95 frame minimum in README (finding 10). cheap.
3. Fix the Fischer-D paragraph to name the D85 shift (+2993.8 m) and the D1 shift (+2357 m) distinctly (finding 11). cheap.
4. Set run_mode "scenario" on the hot_lowflow build (finding 14). cheap.
5. Add primary-source citation fields to the scenario block for Burkhalter 1979, Kaya 1977, and NDEP UILT (finding 6, partial). cheap.

Scientific findings (interpretation and limits):
6. Rewrite the "YES, it flips" headline to a structural statement; add starvation_absent + model_scope fields; keep the admission (finding 5). medium.
7. Add a boundary strictly below UILT variant (finding 6, remainder). medium.
8. Expand the temperature sweep to 1 C step near the flip boundary (finding 15). cheap.
9. Add a velocity/depth pocket sweep to pair with the size and temperature sweeps (finding 12). medium.
10. Add a settle_s / quasi-steady check to the chronic-mean assumption (finding 7). medium.

Architecture:
11. Factor scenario constants into scenario_constants.py or
    param_registry.py (finding 8). medium.
12. Emit a full compare_runs doc for the Rabbit-only N=1 case
    (finding 9). cheap.
13. Wire the +2 C comparison into run_hot_lowflow.py so the
    artifact lineage matches the README citation (finding 13).
    medium.
14. Comment-style sweep across the three runners (finding 16).
    cheap.

Removed outright: run_hot_lowflow_with_tributaries.py (finding 1,
with findings 2, 3, 4 as supporting evidence for the deletion).
