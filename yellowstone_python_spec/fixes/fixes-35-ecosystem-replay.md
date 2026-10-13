# fixes-35: ecosystem and replay
Scope: yellowstone_midway/scripts/ecosystem.gd sha256:114bc58d7a83 ; yellowstone_midway/scripts/python_river_replay.gd sha256:b98fd984882f ; yellowstone_midway/scripts/pool_overlay.gd sha256:a4a8da8c1430 ; yellowstone_midway/scripts/thermal_probe_overlay.gd sha256:94607718fd6c
Callers read: yellowstone_midway/scripts/world.gd ; yellowstone_midway/scripts/wildlife_actor.gd ; yellowstone_midway/scenes/study.tscn ; yellowstone_midway/tools/validate_ecology.gd

## Main problems

### 1. condensation_visibility mislabels pressure as mixing ratio
ecosystem.gd:267-280 computes `_saturation_vapour_pressure_kpa` (Magnus form) in kPa, then builds `ea = humidity * es_air`, `q_mix = 0.3 * es_surf + 0.7 * ea`, `t_mix = 0.3 * surface_c + 0.7 * air_c`, and returns `(q_mix - es(t_mix)) / es_surf * wind_factor`. The variable `q` is standard for specific humidity (kg/kg), but all three terms are vapor pressures in kPa. The ratio `(e_mix - e_sat(T_mix)) / e_surf` is a bounded index of mixed-parcel supersaturation, which is physically defensible, but the comment on line 272 reads "returns relative supersaturation... in [0,1]" while the division is by `es_surf` not `es(t_mix)`, which weakens the "1 at saturation" claim.
### Fix
Rename `q_mix` to `e_mix` and divide by `es(t_mix)` so the index is 0 at ambient equilibrium and 1 when the mixed-parcel vapor pressure doubles its saturation value. For scientific grounding use the Magnus coefficient set from Alduchov and Eskridge (1996), J. Appl. Meteor. 35: `6.1094 * exp(17.625 * T / (T + 243.04))` (hPa). Convert to kPa by dividing by 10 if the surrounding code expects kPa; the current implementation already uses the hPa-form coefficients but the function name claims kPa. Pick one and label it:
```gdscript
# Saturation vapor pressure, hPa (Alduchov and Eskridge 1996).
func _saturation_vapor_pressure_hpa(t_c: float) -> float:
	return 6.1094 * exp(17.625 * t_c / (t_c + 243.04))
```
### Test
`tests/test_condensation.gd`: at `surface_c = 60, air_c = 5, humidity = 0.6, wind = Vector2.ZERO` assert `condensation_visibility` increases monotonically with `humidity` on `[0, 1]` and is zero when `humidity == 0 and surface_c == air_c`.

### 2. heat budget uses t^n for outgoing flow
ecosystem.gd:154-171 captures `old = river.duplicate(true)` and computes `outgoing = r.flow_m3s * old_c`. In the explicit Euler scheme this is a forward-in-time flux using the current cell temperature. For a plug-flow cell where water leaves at the cell temperature and inflow comes from upstream, the correct outlet flux at step n is `flow * T_cell^n`, which the code does. The internal CFL check uses `rate = flow/volume + 1/cooling_seconds`, so stability holds under `h <= 0.45 / rate`. This is defensible for the illustrative run mode but is not a Godunov scheme; the comment should say so.
### Fix
Add a comment above the loop: `# Explicit Euler for a well-mixed cell, with CFL stability on the stable_dt loop.`
### Test
validate_ecology.gd:67-72 already covers the uniform-20C invariance and the batch-vs-substep equivalence. Keep as is.

### 3. day_rate advances clock_hour at 1 real second per sim second by default
ecosystem.gd:49,139. `clock_hour += h * day_rate / 3600.0` with default `day_rate = 1.0` means 1 physical second advances the clock by `1/3600` h, so one full day takes one hour of wall clock. The world.gd replay path (python_river_replay.gd:173) overrides this with `fposmod(_replay["clock_hour0"] + elapsed / 3600.0, 24.0)`, dropping `day_rate` silently. The world and the replay use different speed knobs.
### Fix
Replay should respect `day_rate` or document that it is intentionally pinned to real-time. Add to python_river_replay.gd:173:
```gdscript
clock_hour = fposmod(
	float(_replay["clock_hour0"]) + elapsed * day_rate / 3600.0, 24.0
)
```
### Test
`validate_ecology.gd`: add a case with `day_rate = 2.0` and assert `clock_hour` after `step(3600.0)` matches the base case advanced by `3600 * 2.0 / 3600.0 == 2.0` hours.

### 4. replay snapshot keeps q_in_m3s baked into memory
python_river_replay.gd:142-146 stores a per-cell `flow_m3s` from `q_out_m3_s`. The replay never re-reads this; it only interpolates temperature between frames. Reaches whose lateral sources vary over the simulated day will not update their flow in the renderer. The ecosystem fields `flow_m3s` and `velocity_mps` are therefore constants of the first frame.
### Fix
Serialize per-frame `q_cells_m3s` from the Python replay (handoff: pycl) and interpolate alongside `temperature_c` in `_apply_replay`. For now, mark the field basis: write `source_basis: "first-frame constant"` and keep it in the snapshot output of `_spatial_state`.
### Test
`python_river_replay._apply_replay`: assert the fish actor's queried `flow_m3s` matches `_spatial_state[*]["flow_m3s"]` for the exact first-frame value until the Python side ships per-frame flows.

### 5. pool_overlay class_name collides with temp_analysis/
pool_overlay.gd:1 declares `class_name MidwayPoolOverlay`. An untracked file at the project root `temp_analysis/pool_overlay.gd:1` declares the same class name. Godot refuses to register the second one and the live scene loads a stub, so `load("res://scripts/pool_overlay.gd").new()` returns a non-instantiable GDScript (world.gd:118 at headless load prints "Nonexistent function 'new' in base 'GDScript'").
### Fix
Not in cluster ownership (temp_analysis/ is outside yellowstone_midway/scripts). Handoff: owner of temp_analysis/ removes the duplicate or renames the class to `MidwayPoolOverlayScratch`. The runtime script in scripts/ is the canonical one.
### Test
After the handoff, `godot --headless --path . --quit-after 300` must not emit the "hides a global script class" parse error for pool_overlay.gd.

### 6. thermal_probe_overlay never resolves ecosystem_path
thermal_probe_overlay.gd:6,30-37 reads an `ecosystem_path: NodePath`, but world.gd:85-86 instantiates `pool_overlay` by `load().new()` and does not wire a `thermal_probe_overlay`. The study scene (`scenes/study.tscn`) must set `ecosystem_path = ^"../Ecosystem"`; outside that scene the overlay never activates.
### Fix
Document the dependency in a one-line docstring:
```gdscript
## Lives in study.tscn, requires ecosystem_path to the Ecosystem child.
```
Add a push_warning if `ecosystem_path.is_empty()` at `_ready`.
### Test
Scene-smoke on study.tscn: toggle visibility with KEY_H, confirm `_markers.size() > 0` after one process tick.

### 7. ecosystem rejects unknown patch IDs silently
ecosystem.gd:258-261 `patch()` returns a hardcoded "unavailable" dictionary when `_patch_indices` does not contain `id`. The caller (wildlife_actor._update_insects, wildlife_actor._update_ungulate via `patch()`) uses `float(habitat.get("biomass", 0.0))` so a missing habitat silently reads zero biomass. validate_ecology.gd:37 does assert the "unavailable" case but production builds can hide a typo'd `patch_id` in `data/ecosystem.json`.
### Fix
Keep the current behavior for runtime safety but push_warning once per unknown ID at first access.
### Test
Already covered by validate_ecology.gd:37.

# Wiring and rendering
- ecosystem.gd is the live ecosystem; it drives `clock_hour`, `air_c`, `wind`, and reach temperatures.
- world.gd pushes `ecosystem.wind` into foliage shaders and `ecosystem.air_c`/wind to the atmosphere controller.
- python_river_replay.gd replaces ecosystem.gd for study scenes. Its `_spatial_state[i]["temperature_c"]` is consumed by world.update_environment via `ecosystem.reach_at(z)` and by wildlife_actor._update_fish.
- pool_overlay.gd requires `data/pool_shells.json` and `assets/textures/pool_ramps/*.png`. Without them the overlay silently does nothing.
- thermal_probe_overlay.gd is only reachable from study.tscn and keyboard H.

# Comment-style violations
| file:line | text | rule |
| yellowstone_midway/scripts/ecosystem.gd:3 | `## Reduced observational model. Transport units: ... Unknown tributary flows omitted from ecosystem.json.` | passable, borderline |
| yellowstone_midway/scripts/ecosystem.gd:22 | `var transport_scale: float = 1.0 # Transport is 1:1.` | passable |
| yellowstone_midway/scripts/ecosystem.gd:260 | `# Missing habitat raises.` | contradicts code (function returns a stub, does not raise) |
| yellowstone_midway/scripts/ecosystem.gd:263 | `# Artistic condensation visibility proxy.` | passable |
| yellowstone_midway/scripts/ecosystem.gd:272 | `# Visible plume is condensed droplets. Mirrors yellowstone_python.microclimate.condensation_potential: ...` | docstring exceeds 2 lines; cross-file claim |
| yellowstone_midway/scripts/python_river_replay.gd:4-6 | `## Python owns river thermal state ... Replay interpolation is presentation, not a second solver.` | "not a second solver" is a what-it-is-not statement |
| yellowstone_midway/scripts/thermal_probe_overlay.gd:4 | `## Fixed color scale supports comparison between control and pulse runs.` | borderline |

# Priority order
1. item 1 (condensation vapor-pressure naming) - cheap
2. item 2 (plug-flow comment clarity) - cheap
3. item 3 (day_rate parity between live and replay) - cheap
4. item 4 (per-frame flow in replay) - refactor; blocks on Python producer
5. item 7 (unknown patch_id warn-once) - cheap
6. item 6 (thermal probe docstring) - cheap
7. item 5 (temp_analysis class_name) - handoff
