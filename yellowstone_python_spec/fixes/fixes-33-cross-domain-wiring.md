# fixes-33: cross-domain wiring

Scope: couplings between modules and domains, as traced in `dashboard/data/inventory-python.json` and `dashboard/data/inventory-godot.json` (key file hashes recorded in each file's `generated_from`; build.py sha256 65d9b0265537 at trace time). Line numbers are as of that trace and may move while other fixes land; re-locate by the quoted call before editing.
Callers read: `yellowstone_python/yellowstone_python/build.py`, `coupling.py`, `vegetation.py`, `insects_birds.py`, `fish.py`, `geochemistry.py`, `overland_flow.py`, `groundwater_provider.py`, `snow_season.py`, `canopy_census.py`, `replay/hydraulics.py`, `replay/plume2d.py`, `hydro_thermal.py`, `publish.py`.
Related documents: fixes-18 (overland), fixes-23 (build), fixes-24 (coupling contract), fixes-26 (analysis store), fixes-27 (groundwater, thermal curves, orphans), fixes-28 (exporters, reference solution), fixes-14 series (Godot atmosphere), fixes-39 (rendering gaps, Godot side).

The coupling contract (`coupling.py` EXCHANGES and `coupling.json`) lists what the build claims to exchange. Of 48 traced couplings, 31 are wired, 9 partial, 3 missing, 5 proposed. This document covers the 17 that are not wired, plus modules whose outputs reach no consumer. Each item names the code area that owns the fix: R (river and atmosphere physics), D (data ingestion), E1 (pipeline and registries), E2 (ecology, snow, census, backend), G (Godot).

## Main problems

### 1. Overland runoff never reaches the river

`build.py:581` stores the `run_overland` result only in `overland_field`; `build.py:912` writes it to `overland_flow.json`; nothing in the build reads `overland_field` surface runoff. The river boundary discharge is fixed at initialization (`river_transport.py:410-467`, see the fixes-15, 15.2 and 18 ledgers), so even a correct runoff series has no place to enter.
### Fix
Two steps, in order. R: let `River` accept a scheduled boundary discharge (a `Series` of m3/s with breakpoints), with face flows recomputed per step and the water budget closing on the scheduled inflow. E1 with D: convert overland outlet runoff to discharge only for the area that drains to the upstream boundary (runoff depth rate in m/s times contributing area in m2), add it to the prescribed baseflow, and record both components separately in `BUILD.json` with `run_mode` rules intact (prescribed forcing is not validation). If the contributing area cannot be delineated from the terrain, leave the coupling `partial` and say why in the coupling contract.
### Test
`test_overland_runoff_enters_boundary`: a synthetic storm on a closed synthetic catchment raises the boundary discharge by exactly the integrated outlet volume; the river water budget closes to round-off.

### 2. Groundwater exchange is not wired, and should not be until it is physical

`groundwater_provider.py:47` (`riv_reaches_to_sources`) is called only from `replay/tests/test_river_world.py:204`; there is no build import. fixes-27 found the provider computes no Darcy flux and never runs MF6.
### Fix
Do not wire the current provider. E2 or R first implements fixes-27's groundwater items (head-gradient exchange q = C (h_aquifer - h_river) with conductance C from bed conductivity, thickness, width and length, sign positive into the river). Then wire it as lateral sources per cell with source temperature from the aquifer (authored, labeled). Until then the coupling contract lists it as `proposed`, not `missing`.
### Test
`test_groundwater_exchange_sign_and_budget`: a gaining reach adds water and heat at the aquifer temperature; a losing reach removes water at river temperature; totals match the conductance law.

### 3. Insect compartments ignore bed shear

`build.py:508` passes `'disturbance': 0.0` to `step_compartments`, while `aquatic_foodweb` already maps `bed_shear_pa` to disturbance through `shear_to_disturbance`. The two insect models disagree about the same river.
### Fix
E2: compute disturbance for the insect compartments with the same `shear_to_disturbance` function and threshold used by the foodweb, from the bridge cell's shear (the cell the compartments already use for temperature). One function, one threshold, one source.
### Test
`test_insect_disturbance_matches_foodweb`: for the same shear the two paths return the same disturbance fraction; zero shear gives zero disturbance.

### 4. Insect development uses one cell's temperature

`build.py:507` passes `water_c = bridge.temperature_c` to `step_compartments`; the per-cell landscape reaches only `aquatic_foodweb`.
### Fix
E2: keep the single-cell forcing (the compartments model one patch) but state it in the compartments' provenance and in `equations.py`, and add the cell id to the output. If the compartments are meant to represent the reach, force them with the length-weighted mean over the reach's cells instead. Choose one and record it.
### Test
`test_insect_forcing_cell_recorded`: the output names the forcing cell id and its temperature.

### 5. Silica saturation is defined but never computed

`geochemistry.py:200` (`silica_saturation_index`) and `geochemistry.py:211` (`diagnose_replay_frame`) have no build caller.
### Fix
E1: call `diagnose_replay_frame` on the replay frames in the build and write `geochemistry.json` (silica SI per cell, with the solubility relation and its source). No biological gate on it (the geochemistry to aquatic habitat coupling stays `proposed`) until the hydrothermal science supports one.
### Test
`test_build_writes_geochemistry_diagnostics`: the sidecar exists, every cell has a finite SI, and SI decreases where the replay temperature rises (amorphous silica solubility increases with temperature).

### 6. The 2-D plume is drawn to a PNG and goes nowhere

`build.py:674` calls `plume_field(...)`; `publish.py:28` does not ship `plume_map.png`; the foodweb's thermal landscape uses only 1-D replay cells (`aquatic_foodweb.py:102`).
### Fix
E1: publish the plume field as data (a small grid JSON with axes, units, the hot and river temperatures used, and status illustrative) so Godot can draw it (fixes-39). Do not overlay it on the foodweb: the 2-D steady plume and the 1-D transient cells are different models of the same water, and merging them needs a defined mapping and a mixing check first. Record the overlay as `proposed`.
### Test
`test_publish_includes_plume_field`: the published file exists and round-trips with axes and units.

### 7. Measured precipitation does not drive overland flow

`build.py:583` uses `olfg.rain_mm_h or scfg.precip_mm_d`; fixes-23 found the fallback treats a daily depth as an hourly rate (about 24 times too much rain).
### Fix
E1 with D: in `hindcast` and `observed_replay` modes, drive overland flow from the met bundle's hourly precipitation series; in `illustrative` mode require an explicit `rain_mm_h`. Remove the daily fallback; if a daily total is the only input, convert with a stated storm duration and label it authored.
### Test
`test_overland_rain_units`: a 24 mm daily total with no duration raises a configuration error; with a stated 6 h duration it yields 4 mm/h.

### 8. The build's snow season ignores the measured forcing the validator uses

`build.py:401` uses `scfg.air_c_by_day or [air0] * snow_days`; the SNOTEL bundle reaches `run_season` only through `snow_validate.py:525`.
### Fix
E1 with E2: in `hindcast` and `observed_replay`, force `run_season` with the same daily series and fitted parameters the validator froze; in `illustrative`, keep the config list and say so in `season.json`.
### Test
`test_build_snow_uses_bundle_in_hindcast`: a hindcast build reproduces the validator's frozen-parameter SWE series for the same window.

### 9. Grazing pressure on vegetation comes from config, not from the grazers

`build.py:382` passes `grazers=vcfg.grazers` to `patch_step`; the grazer module's routes and grazing timing never feed back into patch biomass.
### Fix
E2: compute grazing offtake per patch from the grazer module's output (head count, intake rate per head, time on patch) and pass it to `patch_step` with a one-step lag (vegetation at step n uses grazing from step n-1), documenting the lag. If intake rates lack a source, mark the coupling `partial` with the reason.
### Test
`test_grazing_feedback_reduces_biomass`: doubling grazer time on a patch reduces that patch's biomass relative to control by the intake integral.

### 10. Vegetation suitability uses a hard-coded canopy

`build.py:392` passes a scalar canopy of 0.6 to suitability; `canopy_census.py` writes per-crown data that only the analysis store reads.
### Fix
E2: compute canopy fraction per patch from `census.json` (crown area within the patch polygon over patch area) and pass it to `suitability`; record the census build and method. Keep 0.6 only as an explicit illustrative fallback when no census exists, labeled authored.
### Test
`test_canopy_from_census`: a synthetic census with known crown areas yields the exact canopy fraction per patch.

### 11. Two trout models use different hydraulics

`fish.py` `update_trout` uses reach-level flows; `aquatic_foodweb` uses per-cell velocity cost to choose the refuge cell that also places the rendered trout.
### Fix
E2: make the foodweb's refuge selection the single authority for trout position and pass its cell hydraulics to `update_trout`, or retire `update_trout`'s placement logic. Record which in `equations.py`.
### Test
`test_trout_position_single_authority`: the published trout position equals the foodweb's refuge cell for both control and pulse runs.

### 12. The explicit surface energy budget is off by default even when measured forcing exists

`build.py:293` passes `energy_budget`, default Newton (lumped); the measured shortwave in the bundle is not forced into every build.
### Fix
E1 with R: when the met bundle carries shortwave, humidity, wind and cloud, and `run_mode` is `hindcast` or `observed_replay`, default to the explicit budget; keep Newton for `illustrative` and say so in `BUILD.json`. The parameter registry records which law ran.
### Test
`test_budget_mode_follows_run_mode`: hindcast with a full bundle runs the explicit budget; illustrative runs Newton; both are recorded.

### 13. Two soil-water models run side by side

`hydrology/hydrosim.py` (through `overland_flow`) and `snow_season.py:132` both keep soil water; neither reads the other. `hydrology_provider.py:131` exposes soil wetness only to the HTTP backend.
### Fix
E2 with R: choose one soil-water authority per build (recommend the snow-season bucket for patch phenology, hydrosim for overland generation) and pass soil state one way with a stated mapping between grids, or document that they represent different depths and must not be compared. Until then the couplings stay `proposed`.
### Test
`test_single_soil_state_per_patch`: the patch moisture published to Godot traces to one model, named in the patch provenance.

### 14. Modules with no consumer

No production caller: `weather_ingest/` (docstring only), `exporters/to_map.py` (stub), `thermal_curves.py` (fish uses `THERMAL_SPECIES`; fixes-27), `common/units.py` (tests only), `replay/nc_export.py` (own test only), `replay/fipy_reference.py` (not in `validation/checks.py`; fixes-28), `tools/build_store.py` (not run by the build; fixes-26).
### Fix
E1 and E2, per module: wire it where the science calls for it (`thermal_curves` as the single thermal authority for fish, after fixes-27's curve-shape fix; `build_store` as an optional build step per fixes-26), or mark it `not implemented` in its docstring and the coupling contract so the dashboard and claims stop counting it. Deleting files is the owner's call; do not delete.
### Test
`test_no_orphan_modules`: every module under `yellowstone_python/yellowstone_python/` is either imported by the build path, a tool listed in `README.md`, or listed as not implemented.

### 15. Study replays are produced outside the build

`firehole_control.json` and `firehole_pulse.json` (read by `python_river_replay.gd`) come from `study_mode` and the hot low-flow runners, not from `build.py`, so `BUILD.json` cannot vouch for what the study scene shows.
### Fix
E1: have the study and runner outputs record the build id, config hash and `run_mode` they were produced from, and have `publish.py` refuse to ship a replay whose recorded build id is absent from `derived/`.
### Test
`test_publish_rejects_orphan_replay`: a replay without a matching build id is refused.

# Wiring and rendering

Godot draws 24 of 30 systems (inventory-godot). The Python side reaches Godot through `ecosystem.json`, `world.json`, `placements.json`, `season.json`, the replay JSONs and the pool ramp PNGs. Python outputs that reach no Godot reader: `species_catalogue.json`, `substrate_rules.json`, `grazer.json`, `fish.json`, `insect_bird.json`, `planting_proposal.review.json`, `bake_report.json`, the plume field, geochemistry beyond the ramp id, and the weather snapshot (the atmosphere controller and readers are not instantiated in `world.gd`; fixes-14 ledger). Godot-side plans for each are in fixes-39.

# Comment-style violations

None recorded here; fixes-32 covers comment style across the tree.

# Priority order

1. Item 1 (scheduled boundary discharge, then overland routing): refactor. Unblocks fixes-15, 15.2 and 18.
2. Item 7 (rain units): cheap. Item 12 (budget mode by run mode): cheap.
3. Items 3, 4, 10, 11: medium. Close the biggest ecological inconsistencies.
4. Items 5, 6, 15: medium. Make hydrothermal outputs and study replays traceable and drawable.
5. Items 8, 9, 13: medium to refactor.
6. Item 2: after fixes-27. Item 14: cheap per module once each decision is recorded.
