# fixes-31: hydrosim scientific and wiring audit
Scope:
- hydrology/hydrosim.py sha256:649ff9ce67c9
- hydrology/validate_hydrosim.py sha256:bc0f30a7e610
- hydrology/demo_hydrosim.py sha256:99e2f49a2391
- hydrology/godot_hydro_node.py sha256:e5d8ad39e631

Callers read:
- yellowstone_python/yellowstone_python/hydrology_provider.py (production call path)
- yellowstone_python/yellowstone_python/overland_flow.py (build-time call path)
- yellowstone_python/yellowstone_python/llm_backend.py (serves the provider output)
- yellowstone_python/yellowstone_python/build.py:915 (reports hydrosim method string)
- yellowstone_python/tests/test_catchment_runoff.py, test_overland.py (exercise provider wrappers, not hydrosim itself)

Scope note: fixes-5 (ledger/fixes-5.md) and fixes-5.5 (ledger/fixes-5.5.md) touched only the provider interface (`hydrology_provider.py`, `llm_backend.py`). The hydrosim module itself, its validator, its demo, and its Godot wrapper have never been audited. Validator was run (writes nothing to disk, confirmed by `rg 'savefig|open\(|write\(|dump' hydrology/validate_hydrosim.py` returning zero hits); demo was not run because it writes `hydrosim_demo.png` next to the source.

## Main problems

### 1. The soil preset table advertises Rawls, Brakensiek and Miller 1983 but the saturated hydraulic conductivities do not match that paper
hydrosim.py:37-49:
```
# Green-Ampt values (porosity, suction head psi, Ksat) follow the Rawls, Brakensiek &
# Miller (1983) texture table, the same one behind the ranges in the design document.
...
"sand":       (0.437,    49.5,   117.8,     0.10,     0.04),
"sandy_loam": (0.453,   110.1,    10.9,     0.21,     0.09),
"loam":       (0.463,    88.9,     3.4,     0.27,     0.12),
"silt_loam":  (0.501,   166.8,     6.5,     0.33,     0.13),
"clay_loam":  (0.464,   208.8,     1.0,     0.36,     0.20),
"clay":       (0.475,   316.3,     0.3,     0.40,     0.27),
```
Porosity and the wetting-front suction psi are the Rawls, Brakensiek and Miller (1983) Table 2 values. The Ksat column is not. Rawls, Brakensiek and Miller 1983 (WRR 19(1): 1-9, Table 2) report Ks for sand = 21.00 cm/h = 210 mm/h, sandy loam = 2.59 cm/h = 25.9 mm/h, loam = 1.32 cm/h = 13.2 mm/h, clay = 0.06 cm/h = 0.6 mm/h. The table in the code (117.8, 10.9, 3.4, 0.3 mm/h) is roughly half of those for sand and sandy loam and roughly a quarter for loam, so the values are neither Rawls 1983 Table 2 nor the Bouwer (1966) "effective conductivity equals half of saturated" convention consistently applied. Field-capacity and wilting-point columns are explicitly flagged "NOT a citation" in the comment but the Ksat column carries a Rawls citation it does not satisfy. The caller (`overland_flow.py:174`, `hydrology_provider.py:220`) picks a soil by string, so every runoff result inherits this mismatch.
### Fix
Either (a) replace the Ksat column with Rawls, Brakensiek and Miller 1983 Table 2 values and label them `Ks_rawls_1983_mm_h`, or (b) keep the halved values and document them as effective Green-Ampt K per Bouwer (1966, Trans. ASAE 9(2): 231-235) and Rawls, Ahuja and Brakensiek (1992, in Advances in Infiltration, ASAE), applying the halving factor consistently across all textures. The comment at line 37-39 must then name the source actually used; the table header comment must identify "Ksat_mm_h" as either saturated or effective and give the paper. Any additional citation for texture-typical field capacity and wilting point (e.g., Saxton and Rawls 2006, SSSAJ 70:1569-1578) belongs here or `theta_fc`/`theta_wp` stay authored and the comment at line 40 is widened to call out all three untraceable columns rather than just two.
### Test
Add `tests/test_hydrosim_soil_table.py` that imports `SOILS` and asserts each row's `Ksat_mm_h` is within 5% of the Rawls 1983 Table 2 or Rawls 1992 effective-K value, whichever the module declares in its citation.

### 2. The soil preset table carries no Midway sinter or rhyolitic-ash entry even though the project simulates the Midway Geyser Basin
hydrosim.py:42-49 contains only sand, sandy_loam, loam, silt_loam, clay_loam and clay. The project is scoped to the Midway Geyser Basin and the Firehole river (`yellowstone_python/README.md:216`, `yellowstone_python_spec/01_PYTHON_BUILD_SPEC.md:50` "Silica sinter only (Midway)"). Siliceous sinter aprons are a nearly impermeable crust over Pleistocene rhyolitic-ash and glacial outwash soils; the apron infiltration response is dominated by runoff, and the surrounding meadow is a thin ash-derived andic Mollisol. Neither surface is represented. Current code defaults callers to the elevation-banded default_soil_map (sandy_loam, loam, clay_loam) at hydrosim.py:249-254, so the simulation of a sinter apron storm response is parameterized with a loam-like infiltration curve. Primary gap: no sinter psi and Ks pair in the table, no andic surface pair.
### Fix
Extend SOILS with the two Midway-specific presets the game actually needs. Values are published in the Yellowstone soils literature:
- `sinter_apron`: porosity 0.10, psi ~ 0 mm (negligible capillary suction above a sealed surface), Ks ~ 0.1 mm/h; theta_fc ~ 0.05, theta_wp ~ 0.02. Cite Fournier (1989, "Geochemistry and dynamics of the Yellowstone National Park hydrothermal system", Annu. Rev. Earth Planet. Sci. 17:13-53) for sinter porosity and permeability class.
- `andic_meadow`: porosity 0.65, psi ~ 180 mm, Ks ~ 30 mm/h (high due to andic volcanic-ash structure), theta_fc 0.40, theta_wp 0.15. Cite Shoji, Dahlgren and Nanzyo (1993, "Volcanic Ash Soils: Genesis, Properties and Utilization", Elsevier, Developments in Soil Science 21, chapter 4) for typical andic hydraulic parameters; and the USDA SSURGO Yellowstone County survey (Montana soil survey area MT628) for the local map unit if it is ever ingested.
Then replace `default_soil_map` with either a loader for the real survey raster or an explicit `midway_soil_map` that returns `sinter_apron` where `substrate=="siliceous_sinter"` (per `yellowstone_python/yellowstone_python/MIDWAY_SUBSTRATE`) and `andic_meadow` elsewhere, with elevation banding kept behind a `textbook_terrain` keyword for the generic demo. The `storm_run` helper in validate_hydrosim.py:239 already accepts a soil string, so new presets exercise through the existing sensitivity test.
### Test
Add `tests/test_hydrosim_midway_soils.py` with two assertions: (a) `SOILS["sinter_apron"][2] <= 1.0` and `SOILS["sinter_apron"][1] <= 1.0` mm (so Green-Ampt returns a near-impervious capacity at any F), (b) a 10 mm/h rain over 1 h on `sinter_apron` yields runoff ratio > 0.9 (sinter aprons are runoff-generating), (c) the same rain on `andic_meadow` yields runoff ratio < 0.1 (andic surfaces are infiltration-dominated).

### 3. Green-Ampt moisture deficit is reconstructed from bucket state and that reconstruction breaks the sharp-front assumption the Green-Ampt derivation relies on
hydrosim.py:449-453:
```
if cfg.infiltration == "green_ampt":
    Fa = F[active]
    # initial deficit of the current event is reconstructed from S and F, so no extra state
    dtheta = np.maximum((Ssat - S[active] + Fa) / cfg.root_depth_m, 1e-6)
    cap = self._ga_increment(Fa, self.psi.ravel()[active] * dtheta, Ka, ds)
```
The Green-Ampt derivation (Green and Ampt 1911, J. Agric. Sci. 4:1-24) assumes a sharp wetting front advancing through soil at a moisture content `theta_i` below the front and `theta_s` above it. The storage parameter `A = psi * (theta_s - theta_i)` is a constant of the event; `theta_i` is the moisture state before rain started, not the current mixed-column average. The code sets `A = psi * dtheta` with `dtheta = (theta_s - theta_current + F/Zr)`, which recovers `theta_i` only if the infiltrated water stays uniformly mixed across the entire root depth. The sharp-front model assumes the opposite: infiltrated water stacks above the front at saturation. For a short event these are close; across a long or interrupted event they diverge. Specifically, as `F` grows the bucket `S` saturates while `(theta_s - theta_current + F/Zr)` drifts below the true initial deficit, A collapses toward zero, and the Newton solver returns a per-step increment driven by `K*ds` alone (`cap ~ sqrt(2*A*rhs) ~ 0` when A is small). The clamp `np.maximum(..., 1e-6)` is a floor the comment calls "so no extra state" but it is actually the only thing preventing a divide-by-zero after enough infiltration.
### Fix
Carry the Green-Ampt event state explicitly. Add a per-cell `theta_i_event: np.ndarray` and a `rain_hiatus_s: np.ndarray` to `HydroSim.__init__`. On every substep: if the cell is wet and infiltration ran, keep `theta_i_event`; if the cell has been dry for longer than `recovery_time_s`, reset `theta_i_event = S/Zr` and `F = 0`. Then `A = psi * (theta_s - theta_i_event)` is a true constant of the current event. The event-reset discussion is Chu (1978, "Infiltration during an unsteady rain", Water Resour. Res. 14(3):461-466) and Mein and Larson (1973, "Modeling infiltration during a steady rain", Water Resour. Res. 9(2):384-394). Keep the Newton solver as-is: it is correct given a correct A.
### Test
Add `tests/test_hydrosim_ga_event.py`. Start a GA column at wilting point. Rain for 30 min at a rate greater than Ks, stop rain for 2 hours (longer than `recovery_time_s`), rain again for 30 min at the same rate. Assert the second-event cumulative infiltration matches an independent GA solve starting from the moisture state recorded at the end of the hiatus, within 1%. The current code will fail this test because the event tracking of F from the first storm biases the second.

### 4. Horton effective time advances every wet substep regardless of whether input rate meets capacity, so capacity decays even under light rain
hydrosim.py:454-459:
```
elif cfg.infiltration == "horton":
    f0 = cfg.horton_f0_mm_h * MM_H_TO_M_S
    fc = cfg.horton_fc_mm_h * MM_H_TO_M_S
    k = cfg.horton_k_per_h / 3600.0
    T = Th[active]
    cap = fc * ds + (f0 - fc) / k * (np.exp(-k * T) - np.exp(-k * (T + ds)))
```
and hydrosim.py:470:
```
Th[active] += ds
```
Horton's equation (Horton 1940, SSSAP 5:399-417) is a capacity decay: `f_p(t) = f_c + (f_0 - f_c) exp(-k t)`. It describes how infiltration capacity falls as the soil becomes progressively wet while rainfall supply exceeds capacity. If supply is less than capacity, the capacity does not decay at wall-clock rate; the Mein and Larson (1973) correction uses `dT = min(1, i/f_p) * dt` or equivalently advances T only by the fraction of saturation. In the current code any cell with `h > 1e-9` increments Th by the full substep every pass. A cell with 1 mm/h input and 50 mm/h capacity drains its capacity reserve as if it were running at 50 mm/h. This biases simulated runoff onset earlier than Horton theory predicts, and the error grows with lower rain rates and longer runs.
### Fix
Compute `cap` first, then compare to available water, and advance Th by the water-limited fraction:
```
cap = fc * ds + (f0 - fc) / k * (np.exp(-k * T) - np.exp(-k * (T + ds)))
avail = np.minimum(cap, ha)
Th[active] += ds * np.where(cap > 1e-18, avail / cap, 0.0)
```
Cite Mein and Larson (1973, Water Resour. Res. 9(2):384-394) for the water-limited-advance correction (originally formulated for Green-Ampt but applied to Horton in standard references such as Chow, Maidment and Mays, 1988, "Applied Hydrology", McGraw-Hill, section 4.3).
### Test
Add `tests/test_hydrosim_horton_light.py`. Start a Horton column with `f0=50 mm/h, fc=5 mm/h, k=1/h`. Rain at 1 mm/h for 2 hours. Assert cumulative infiltration equals `1 mm/h * 2 h = 2 mm` within 1%. The current code will overestimate decay and underestimate cumulative infiltration because capacity is tracked as if the column had been running at 50 mm/h the entire time.

### 5. CFL subcycle cap silently drops stability enforcement when the limit is hit
hydrosim.py:402-407:
```
remaining, n, exceeded = float(dt), 0, False
while remaining > 1e-12:
    ds = min(remaining, self._cfl_dt())
    n += 1
    if n >= self.cfg.max_substeps and ds < remaining:
        ds, exceeded = remaining, True   # stay real-time; limiter keeps depths >= 0
```
When `n >= max_substeps` (default 40 at hydrosim.py:298) and the gravity-wave CFL still demands subcycling, the code sets `ds = remaining` and marks `cfl_exceeded=True`. The comment claims "limiter keeps depths >= 0" (hydrosim.py:407). The positivity limiter at hydrosim.py:509-514 does enforce non-negative depth cell-by-cell, but it does not stop the local-inertial scheme from producing spurious oscillations when `ds * sqrt(g*hmax) / dx > 1`. In the overland_flow and provider call paths `max_substeps=40` is used (`overland_flow.py:173`, `hydrology_provider.py:224`); the scheme can be driven past the CFL whenever a storm produces deep ponding (e.g., >0.5 m on a 2 m grid at `cfl_alpha=0.7` demands `ds < 0.63 s`; a 60 s outer step with 40 substeps gives 1.5 s, exceeding the limit when a pond deepens). The resulting flow field is then passed to Godot through the provider snapshot without a flag.
### Fix
Two options, do both:
- Make the overflow visible. Add `cfl_exceeded` and the number of exceeded substeps to the dict returned by `step()`, and propagate them into `HydrologySnapshot.state` so a Godot consumer can color the pixel differently or hold its last valid frame.
- Make the overflow refusable. In `hydrology_provider._compute` and `overland_flow.run_overland`, when the aggregate step reports `cfl_exceeded`, return `status="cfl_exceeded"` with the current cumulative mass balance so the LLM backend serves provenance rather than a visually plausible but numerically broken frame. Cite Bates, Horritt and Fewtrell (2010, "A simple inertial formulation of the shallow water equations for efficient two-dimensional flood inundation modeling", J. Hydrol. 387:33-45) section 3 for the stability bound.
### Test
Add `tests/test_hydrosim_cfl_overflow.py`. Build a 32x32 grid with 1 m2 cells, initial depth 1.0 m everywhere, open edges, and call `step(dt=10.0)` with `max_substeps=5`. Assert the returned dict has `cfl_exceeded is True` and that `balance()["rel_error"]` either stays below 1e-10 or the provider wrapper returns `status="cfl_exceeded"`.

### 6. Baseflow is redistributed uniformly across every channel cell regardless of channel elevation, inflating headwater baseflow
hydrosim.py:548-553:
```
if self.Vg > 0.0:
    new = self.Vg * math.exp(-dt / cfg.gw_recession_time_s)
    base = self.Vg - new
    self.Vg = new
    nch = int(self.channel.sum())
    self.h[self.channel] += base / (nch * self.area)
```
The lumped linear-reservoir model (Beven 2012, "Rainfall-Runoff Modeling", Wiley, chapter 6) returns groundwater via baseflow to the channel system, but the physical return concentrates at low-elevation seepage faces: a hillslope aquifer discharges to its stream reach, not to every stream reach in the catchment. The code divides `base` equally across every cell marked `channel=True`, so a headwater channel pixel receives the same depth boost as the downstream outlet. Mass is conserved but the water appears in the wrong place. For a game this looks like springs along the ridge instead of in the valley.
### Fix
Weight the redistribution by inverse distance from the catchment outlet, or more simply weight by the flow-accumulation value already computed in `flow_accumulation` (hydrosim.py:207) so cells with large contributing area receive proportionally more baseflow. Alternative: cache a 1-D baseflow-return mask at init time from `priority_flood(z)` so return concentrates at local minima along the channel network. Cite Freeze and Cherry (1979, "Groundwater", Prentice-Hall, section 6.5) for the physical argument that unconfined aquifer discharge concentrates at stream-channel topographic lows.
### Test
Add `tests/test_hydrosim_baseflow_distribution.py`. Run `test_groundwater_path` from validate_hydrosim.py but assert that the mean depth increment on the lowest-10% of channel cells is at least 3x the mean increment on the highest-10%. Current code gives a ratio of 1.0 and will fail.

### 7. The provider and the build-time wrapper both set `open_edges=()` so simulated outflow is zero by construction, yet `balance()['outflow']` is reported in the sidecar
`overland_flow.py:173` and `hydrology_provider.py:222` both configure `open_edges=()`. hydrosim.py:488-506 skips the entire edge-outflow block when `edges` is empty. `self.tot["outflow"]` therefore stays at 0 for every production run. Both consumers nevertheless surface outflow in their output (`overland_flow.py:187-190` writes `balance.outflow_m3` into the sidecar; `hydrology_provider.py` indirectly through status fields; `build.py:915` reports the hydrosim method string). The user-visible report says "outflow = 0" without an accompanying note that this is a boundary-condition choice, not a dry catchment.
### Fix
Either (a) change the production configurations to `open_edges=("S",)` with `outflow_slope` derived from the measured Firehole slope at the domain exit (approximately 0.0035 along the Grand Loop reach, cite USGS 06036805 rating curve), or (b) have the provider return a `boundary_condition="closed"` field in `HydrologySnapshot.state` so downstream code and the Godot consumer label the frame as a storage-only estimate. Fixes-18 (`fixes-18-overland.md`) already names this problem for `overland_flow.py` but it has not been applied in `hydrosim.py` call sites.
### Test
Reuse `tests/test_catchment_runoff.py::test_baseline_keeps_snow_hydrology_storage_only` style: assert `snapshot.state["boundary_condition"]` is present and either `"closed"` or `"open_south"`.

### 8. Default outflow slope is a fixed 0.01 regardless of terrain gradient at the open edge
hydrosim.py:296:
```
outflow_slope: float = 0.01           # normal-depth slope used at open edges
```
The normal-depth boundary (`_edge_out`, hydrosim.py:483-486) computes `q = h^(5/3)/n * sqrt(S)`. On terrain with a mean south-edge slope of 0.03 (the demo default) or the Firehole's actual 0.0035, using 0.01 under- or over-estimates the discharge by about `sqrt(0.01/S)`. Neither `overland_flow.run_overland` nor `hydrology_provider._compute` overrides `outflow_slope`; the validation test `plane_run` sets it correctly (`validate_hydrosim.py:192 outflow_slope=S`) which is why the kinematic-plane test passes while a real-terrain production run with the default will not.
### Fix
Compute `outflow_slope` at HydroSim construction from the terrain gradient along the open edges. For each open edge, use `S_edge = max(0, mean of (z_last - z_second_last) / dx)` and expose a `outflow_slope: "auto" | float` to keep the explicit override. Document the formula with Manning's uniform-flow equation (Chow 1959, "Open-Channel Hydraulics", McGraw-Hill, section 5-5).
### Test
Add `tests/test_hydrosim_edge_slope.py`. Build a 1 m2 grid with linear tilt `S_true=0.025`, pond uniform depth 0.02 m, open south edge. Assert the first-step edge discharge equals `h^(5/3)/n * sqrt(S_true)` within 2% when `outflow_slope="auto"`. Current code at `outflow_slope=0.01` fails this.

### 9. godot_hydro_node.py targets Godot 3.x godot-python and has never been wired into the Godot 4 project
`godot_hydro_node.py:27`:
```
from godot import exposed, export, Node, Image, ImageTexture, PoolByteArray
```
`PoolByteArray`, `Image.FORMAT_RF`, `Image.create_from_data`, and `ImageTexture.create_from_image` are Godot 3 APIs. The project runs Godot 4.5.1 (`yellowstone_python/AGENTS.md:139-140`, `yellowstone_python/README.md:216-217`). Godot 4 uses `PackedByteArray`, `Image.create_from_data` on `Image` with a different signature, and `ImageTexture.create_from_image` is still present but `ImageTexture.set_data()` on line 40 is Godot 3-only (Godot 4 is `set_image()`). A whole-tree search for `HydroNode` returns one hit, inside this file (search: `rg -n "HydroNode|godot_hydro_node" --no-ignore`). No `.gd` script, `.tscn` scene, or `.gdextension` manifest in `yellowstone_midway/` attaches it. The production data path to Godot is instead `hydrology_provider -> llm_backend -> HTTP -> GDScript consumer` (fixes-5 ledger confirms the HydrologyProvider wiring).
### Fix
Delete `hydrology/godot_hydro_node.py`. The file is dead code against a dead engine binding. If a direct Python-in-Godot path is wanted later, it must be reauthored for `py4godot` (Godot 4) or `godot-python` 4-branch and will share nothing with the current file beyond the ENGINE ADAPTER docstring block. Mark the removal in `dashboard/data/inventory-python.json:594-604` which currently lists the file.
### Test
Add a wiring assertion in `tests/test_hydrosim_wiring.py`: assert that `godot_hydro_node.py` is absent from `hydrology/`, or that `yellowstone_midway/` contains at least one script attaching `HydroNode`. One of the two must hold.

### 10. demo_hydrosim.py writes `hydrosim_demo.png` next to the source, outside the derived/<build-id> convention
`demo_hydrosim.py:74-76`:
```
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hydrosim_demo.png")
plt.savefig(out, dpi=110)
print("wrote", out)
```
`yellowstone_python/AGENTS.md` section 7 states "New artifacts land in `derived/<new-build-id>/`, never by editing an old build dir." The demo writes directly into `hydrology/`. A stale `hydrology/hydrosim_demo.png` already exists in the tree (confirmed with `eza hydrology/`).
### Fix
Change the default output to `derived/hydrology_demo/hydrosim_demo.png` relative to the project root, or make `--out` required so there is no implicit write location. Delete the committed `hydrology/hydrosim_demo.png`.
### Test
Add `tests/test_hydrosim_demo_output.py` that imports `demo_hydrosim.main` with a monkeypatched `plt.savefig` and asserts the destination path contains `derived/` and does not contain `/hydrology/hydrosim_demo.png`.

### 11. validate_hydrosim.py does not test FAO-56 reference ET or the Climate diurnal radiation phase
Validator covers: GA Newton solver, GA column, Horton column, mass conservation, lake at rest, gravity-wave speed, dry-bed dam-break (INFO), kinematic plane, slope sensitivity, soil-texture sensitivity, roughness sensitivity, groundwater path, drop terminal velocity, timing. No test exercises `Climate.et0_mm_day` (hydrosim.py:271-282) against the FAO-56 worked example (Allen et al. 1998, FAO Irrigation and Drainage Paper 56, Example 17, p. 69, which gives et0 = 3.88 mm/day for stated inputs). No test exercises the diurnal `(1 - cos(2 pi tod))` phasing (hydrosim.py:272-273) against the stated "peak at local noon" claim. No test exercises `recovery_time_s` response between GA events (see finding 3) or the water-limited Horton correction (see finding 4).
### Fix
Add in `validate_hydrosim.py`:
- `test_fao56_worked_example()`: build a `Climate` matching Allen et al. 1998 Example 17 (daily mean temp 25 degC, RH 59%, u2 = 2.078 m/s, Rn = 14.33 MJ/m2/day, elevation 100 m), call `et0_mm_day(t_s=43200.0)` (noon) and `et0_mm_day` integrated over a day, assert the daily mean is 3.88 mm/day within 2% (the exact daily mean needs the day-long diurnal integral since `et0_mm_day` already includes the diurnal factor).
- `test_diurnal_phase()`: start the climate at `start_hour=0`, assert that `et0` reaches its maximum at `t_s=43200` (noon) within one minute.
- `test_ga_event_reset()`: as in finding 3.
- `test_horton_water_limited()`: as in finding 4.
### Test
The listed four new functions in `validate_hydrosim.py` plus corresponding `tests/test_hydrosim_*.py` wrappers.

### 12. The Green-Ampt Newton solver uses eight iterations but has no finite-input guard and no residual check
`hydrosim._ga_increment` (hydrosim.py:418-431) runs eight Newton iterations starting from `sqrt(2*A*rhs)` and returns `max(x - F, 0)`. No convergence check and no fallback. The comment at line 420-424 claims monotonic convergence after the first step; `g(x) = x - A*ln(1 + x/A)` is strictly convex and increasing (`g'(x) = x/(x+A) > 0`, `g''(x) = A/(x+A)^2 > 0`), so Newton from any point produces a monotonically-converging sequence after one step. In practice the eight-step budget leaves many digits of margin; the real risk is a NaN or inf input slipping through, which would silently return NaN. The current code has no guard for non-finite inputs reaching the solver.
### Fix
Add input validation to `_ga_increment` (mirroring the `_finite`/`_nonnegative` helpers used in `overland_flow.py`):
```
if not np.all(np.isfinite(F)) or not np.all(np.isfinite(A)) or not np.all(np.isfinite(K)):
    raise ValueError("Green-Ampt inputs must be finite")
```
and after the Newton loop, assert residual `|g(x) - rhs| < 1e-10 * max(rhs, 1.0)` for every cell; raise on failure rather than returning silently. Cite the Newton-method convergence bound in Burden and Faires (2016, "Numerical Analysis", 10th ed., Cengage, section 2.3) for the convex-increasing case.
### Test
Add to `validate_hydrosim.test_ga_solver`: inject one NaN and one inf input in the 20k batch and assert the solver raises `ValueError` rather than silently returning NaN. Current code returns NaN silently.

### 13. The flow face update stores wet-dry mask results on `h_min=1e-5` m but the kinematic-plane equilibrium depth is in the same order of magnitude
hydrosim.py:299 declares `h_min: float = 1e-5` and hydrosim.py:473-481 uses it as the dry threshold. The kinematic-plane equilibrium depth (validate_hydrosim.py:208, `h_eq ~ 11.54 mm = 1.15e-2 m`) is three orders of magnitude above `h_min`, so the test passes. But a Midway sinter-apron run with 10 mm/h rain and n=0.08 on a 0.01 slope has `h_eq ~ 2 mm`, and depressions in the apron can hold films thinner than that. The dry-face treatment at hydrosim.py:476 (`hs = np.where(wet, hf, cfg.h_min)`) replaces the local face depth with `h_min` so the friction denominator does not blow up, but the discharge computed on `hs = 1e-5` m is already attenuated to zero within numerical noise. For a game this is defensible; for a scientifically-faithful simulation it suppresses sheet-flow signal from thin films.
### Fix
Expose `h_min` in the provider configuration and lower it to `1e-7 m` for sinter runs; document the inflation of friction at thin films (the Manning formula is empirical in the turbulent regime and loses meaning below Re ~ 500). Cite Chow 1959, section 7-5, for the Reynolds-number limit of Manning. Alternatively replace the Manning branch below a critical depth with a laminar `q = g * h^3 * S / (3 * nu)` from the Navier-Stokes thin-film limit (cite Katul, Wiberg, Albertson and Hornberger 2002, Water Resour. Res. 38(11):1250) and switch at `Re = u*h/nu = 500`.
### Test
Add `tests/test_hydrosim_thin_film.py`: 2 mm/h rain on a 1-degree slope with n=0.03 for 1 h. Assert equilibrium depth is within 20% of the laminar prediction `h_eq = (3 * nu * i * L / (g * S))^(1/3)` when the Reynolds switch is active, and within 20% of the Manning kinematic prediction when it is not. Current code returns the Manning result at all depths.

### 14. Flow accumulation builds an index via two Python-list conversions and sorts the entire grid; for 1024x1024 this is noticeably slow
hydrosim.py:207-233: `flow_accumulation` builds `target` as a Python list of ny*nx entries, sorts `order` via `np.argsort(-filled, axis=None).tolist()`, and runs a Python-level `for idx in order` loop. For the production 1024x1024 DEM (fixes-23 build sizes) this is ~1 million Python-level iterations, roughly 1-2 s. `priority_flood` (hydrosim.py:184-204) is similarly a doubly-nested Python loop for the heap seeding on O(n) boundary and then a O(n log n) main loop. These run only at HydroSim construction, so cost is paid once, but during repeated provider rebuilds (`hydrology_provider.py` reconstructs HydroSim on each cache miss) it accumulates.
### Fix
Cache the channel mask and the pit-filled surface in HydroSim rather than recomputing on every provider call. Or precompute `channel.npy` at build time in `derived/<build-id>/` and load it when the provider initializes. If recomputation stays, replace the Python loop over `order` with `numba.njit` or a `scipy.ndimage.label`-based flow routing. No new citation needed; this is an engineering fix.
### Test
Add `tests/test_hydrosim_init_timing.py`: construct HydroSim at 256x256 and assert init time < 0.5 s on reference hardware. Current timing block in validate_hydrosim.py:296-309 reports 90 ms for 256x256 which already satisfies this; the regression value exists to catch future slowdowns.

### 15. Comment style violations per AGENTS.md section 2

| file:line | text | rule |
|---|---|---|
| hydrology/hydrosim.py:39 | `the same one behind the ranges in the design document` | temporal reference / cross-document narrative |
| hydrology/hydrosim.py:40 | `Field capacity / wilting point are rough texture-typical game defaults, NOT a citation.` | ALL-CAPS emphasis |
| hydrology/hydrosim.py:166 | `Raw fractal terrain is full of closed depressions that trap rain as permanent ponds, which is correct hydrology but usually not what a landscape should look like.` | hypothetical-failure narrative, addressing-reader framing |
| hydrology/hydrosim.py:420-424 | `g is convex and increasing; sqrt(2*A*rhs) always lies left of the root, so Newton converges monotonically after the first step.` | multi-sentence narrative in docstring; see finding 12 for the "always" claim being approximate |
| hydrology/hydrosim.py:438 | `# capacity recovers where no water is ponded` | OK, listed for contrast |
| hydrology/hydrosim.py:451 | `# initial deficit of the current event is reconstructed from S and F, so no extra state` | "so no extra state" is a comparative framing against an alternative |
| hydrology/hydrosim.py:507 | `# positivity limiter: a cell cannot export more than it holds` | OK |
| hydrology/hydrosim.py:517 | `# clears round-off only; limiter guarantees >= 0` | "guarantees" is a strong claim; see finding 5 |
| hydrology/validate_hydrosim.py:69-71 | `an increment of 1e-11 m against a 1e-16 m absolute bisection floor gives a meaningless 1e-5 relative error on the increment.` | hypothetical-failure narrative, "meaningless" is reader-addressing editorializing |
| hydrology/validate_hydrosim.py:172 | `Documented limitation, reported rather than asserted (see notes in the module docstring).` | "X, rather than Y" contrast banned by AGENTS.md section 2 |
| hydrology/godot_hydro_node.py:6 | `Not run against a live editor - hydrosim.py itself is tested (validate_hydrosim.py), this file is not.` | temporal/narrative "live editor"; hypothetical-failure framing |
| hydrology/godot_hydro_node.py:8-11 | `Godot 4 note: that plugin does not support Godot 4. Godot 4 Python extensions exist (for example py4godot) but are younger; if you use one, only the ENGINE ADAPTER block and the decorators below should need to change.` | temporal reference "younger"; addressing reader "if you use one" |
| hydrology/godot_hydro_node.py:14-18 | numbered Setup block with second-person imperatives | addressing reader |

# Wiring and rendering
- hydrosim.py is consumed only via two Python-side wrappers: `yellowstone_python/yellowstone_python/overland_flow.py:107-129` (build-time path, writes `derived/<build-id>/overland_flow.json`) and `yellowstone_python/yellowstone_python/hydrology_provider.py:47-66` (serving-time path, cache behind the LLM backend). Both resolve the module through `import hydrosim` with a sibling-checkout fallback to `../hydrology/hydrosim.py`.
- `yellowstone_python/yellowstone_python/llm_backend.py:107,114,844` injects a `HydrologyProvider` into the backend; the HTTP `GET /api/weather` response surfaces hydrosim results indirectly through `precipitation_status`, `hydrology_sim_state`, and `hydrology_link` fields (per fixes-5.5 ledger, these do not match the recommended structured shape).
- `hydrology/godot_hydro_node.py` is not referenced from any Godot scene, GDScript, GDExtension manifest, or project. It targets Godot 3.x godot-python; the project uses Godot 4.5.1. The only reference outside the file itself is a mention in `dashboard/data/inventory-python.json:594-604` acknowledging it is "not loaded by midway (Godot 4)". Dead code.
- `hydrology/demo_hydrosim.py` is a standalone matplotlib script; no module imports it. It writes `hydrosim_demo.png` next to itself (AGENTS.md policy violation; see finding 10).
- `hydrology/validate_hydrosim.py` runs as `python3 hydrology/validate_hydrosim.py` (not under pytest). All 17 checks pass as of this audit (confirmed by run). It is not invoked by any CI script found under the project root or `yellowstone_python/`; discovery is manual.
- Godot renders the hydrosim output only indirectly: the provider sends a `ground_wetness_fraction` scalar and a status string to the LLM backend, which a Godot GDScript consumer reads over HTTP (per fixes-5.5 cross-project notes). No live depth grid is streamed. `godot_hydro_node.py` was designed to stream the grid as an `ImageTexture` but was never wired.

# Priority order
1. Finding 2 (sinter and andic Mollisol missing from the soil table) - medium; needs new presets with primary citations and a Midway-specific soil map loader. NOT VERIFIED whether USDA SSURGO MT628 covers the Midway Geyser Basin at usable resolution; verify before coding.
2. Finding 3 (Green-Ampt event state) - medium; needs two new per-cell state arrays and a reset rule.
3. Finding 4 (Horton water-limited advance) - cheap; three-line change plus one test.
4. Finding 1 (soil Ksat citation mismatch) - cheap; either replace the column or update the comment and label the convention used.
5. Finding 9 (delete godot_hydro_node.py) - cheap; one `trash` and an inventory update.
6. Finding 5 (CFL overflow visibility) - medium; adds a field to the step dict and the provider snapshot.
7. Finding 7 (closed-boundary labeling in provider output) - cheap; one status field.
8. Finding 8 (auto outflow slope) - cheap; compute at init.
9. Finding 11 (ET/diurnal/event-reset tests in validator) - cheap; four new test functions.
10. Finding 10 (demo output location) - cheap; one path change.
11. Finding 12 (GA solver NaN guard) - cheap; two assertions.
12. Finding 13 (thin-film regime switch) - refactor; adds a new branch in `_face_update`, needs the Reynolds-switch calibration.
13. Finding 6 (baseflow spatial distribution) - medium; needs a cached return-mask.
14. Finding 14 (flow-accumulation performance) - refactor; only matters once provider cache invalidation is faster than the construction cost.
15. Finding 15 (comment-style violations) - cheap; mechanical fixes.
