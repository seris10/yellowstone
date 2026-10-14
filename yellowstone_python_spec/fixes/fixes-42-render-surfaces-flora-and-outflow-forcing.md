# fixes-42: render surfaces, flora overrides and outflow forcing

Scope: defects KJR reported from the running world on 2026-10-13 (missing ground at Grand Prismatic, trees on the sinter, blocky monochrome mats, flat deck and rail textures, and the outflow temperature floor), the causes found, what was changed in the session, and what remains. Audit and fixes by the session working from the Grand Prismatic Overlook screenshot, 2026-10-13.

## Sources
- Edinger, J. E., Duttweiler, D. W., and Geyer, J. C. (1968). The response of water temperatures to meteorological conditions. Water Resources Research 4(5), 1137-1143 (equilibrium temperature and the linearized exchange used by `outflow_thermal`).
- Diment, W. H., and Pratt, H. R. (1988). Thermal conductivity of some rock-forming minerals: a tabulation. USGS Open-File Report 88-690, doi:10.3133/ofr88690 (opal conductivity used by `outflow_thermal.SinterConduction`).
- Ineichen, P., and Perez, R. (2002). A new airmass independent formulation for the Linke turbidity coefficient. Solar Energy 73(3), 151-157 (pvlib `get_clearsky(model="ineichen")`).
- Kasten, F., and Czeplak, G. (1980). Solar and terrestrial radiation dependent on the amount and type of cloud. Solar Energy 24(2), 177-189.
- Nugent, P. W., Shaw, J. A., and Vollmer, M. (2015). Colors of thermal pools at Yellowstone National Park. Applied Optics 54(4), B128-B139 (class temperature centers reused by `mat_appearance.model_ramp_rgb`).
- USDA NAIP 2022-07-19 detail export, `yellowstone_midway/references/midway_orthophoto_detail.jpg` (0.6 m native).

## Item status
| Item | Status |
|---|---|
| 1 mat png nodata alpha | implemented |
| 2 core tile winding | implemented |
| 3 flora override bands and sinter ring | implemented (data and generator; generator not rerun with --apply) |
| 4 mat appearance layer | implemented (module, tests, shader, build wiring); published from build 2a8c8948128c; visual acceptance open (see Integration) |
| 5 deck and timber textures | implemented |
| 6 outflow shortwave forcing | implemented |
| 7 mat insolation date | implemented |
| 8 sinter substrate parameters | implemented (conductivity cited; thickness and substrate temperature authored, no source found) |
| 9 replay heat budget closure | implemented |

### 1. Mat pigment png marked nodata cells opaque black
`microbial_mats.write_mat_pigment_png` set alpha 0 only for dry sinter; nodata cells (community -1, 90 percent of the core grid) were written RGB 0 with alpha 255. The core tile drew black and fog lifted it to the sky color.
### Fix
Alpha 0 for sinter and nodata. Regression test `test_mat_pigment_png_nodata_and_sinter_are_transparent`.

### 2. Thermal-core tile triangles faced down
`core_terrain.gd` wound indices (a, c, b) where the master tiles in `bake_world.gd` use (a, b, c); with `cull_back` the 600 m tile was culled from above and the sky showed through.
### Fix
Index order matches the master tiles. Checked in the running scene.

### 3. Flora overrides placed 19,500 pines off observed cover
`placement_overrides.json::add` held three `gen_flora.py` passes: `prop_deck` (3,500, labeled "art-directed density enhancement (NOT observed cover)") on Grand Prismatic's sinter flats, and `prop_infill_pine` (12,000) and `prop_grove` (4,000) confined to the northern third of the map with straight southern edges. Each pass scans cells row-major and stops at its count cap, so the cap truncates the map. `is_barren` misses NAIP sinter because sinter reads slightly green in that orthophoto (green index 0.30 to 0.36 at 0.56 to 0.79 lightness).
### Fix (data, done)
Removed the three groups; the 30,856 base pines from measured cover and the reviewed corridor and M04 pines stay. Backup in `yellowstone_midway/backups/pre-tree-fix-2026-10-13/`. World rebaked.
### Fix (generator, done)
`gen_flora.forest_infill`, `grove_planting` and `deck_viewshed_groves` iterate cells through `shuffled_cells(n_i, n_j, seed)` (a seeded permutation), so a count cap samples the whole grid; stable ids stay keyed to the cell. Each pine candidate is rejected when `is_mineral` reads the habitat-mask R channel at or above `MINERAL_PINE_MAX = 0.35` (points off the mask read mineral); `is_barren` stays as a second gate. Two defects found by the new tests were fixed in passing: `forest_infill` compared `prev.get("guild")` against `GUILDS["lodgepole_pine"]["guild"]`, a missing key, so it raised KeyError on its second acceptance; `grove_planting` called `guild_suitability` without importing it. The generator was not rerun with `--apply`; `placement_overrides.json` is unchanged.
### Test
`tests/test_gen_flora_sampling.py`: the shuffle is a seeded permutation that is not row-major and reaches both ends of the grid within its first 200 cells; `is_mineral` threshold and off-grid behavior; capped runs (150 infill, 150 grove, 100 deck) on the real world reach within 30 percent of both ends of the map z range (deck: of the ring) and accept no candidate on mineral at or above 0.35.

### 4. Mats rendered as 1 m blocks in one orange
Pigment index is 1.0 on every mat cell (summer saturation) and 75 percent of mat cells sit at the 30.78 C equilibrium floor (item 6), so every cell shifted to the same carotenoid endpoint, and the png repeated each cell as a 2 by 2 block.
### Fix (done)
`yellowstone_python/mat_appearance.py`: mat geometry from NAIP warm chroma (CIELAB, above the sinter median) inside the mineral and model-mat region; color from model flow intensity, temperature and pigment departure on a palette fitted by `tools/fit_mat_palette.py` (k-means k=6) over satellite imagery of the apron; streamline averaging along the 1 m DEM downslope direction for flow-shaped streaks; open water, shadow and vegetation masked. `thermal_apron.gdshader` draws the NAIP 0.6 m detail photo under the layer and softens the 1 m wet rasters. Tests in `tests/test_mat_appearance.py`. The published `data/mat_pigment.png` was rendered by hand from the published d3e02892a81a rasters because builds fail on item 9.
### Build wiring (done)
`_run_outflow_chain` returns the 1 m DEM. `_write_integration_sidecars` calls `_write_mat_appearance`, which renders `mat_pigment.png` with `mat_appearance.write_mat_appearance_png` from the mat state, outflow temperature, `network_rasters["flow_fraction"]`, the DEM, `references/midway_orthophoto_detail.jpg` (`load_photo` at 2560 px) and the habitat-mask mineral channel (`load_mineral`, world half 2048 m, core half 640 m), and writes `mat_appearance.json` (contract header, palette, parameters, imagery and mask sha256). `pigment_ref` comes from `mat_imagery_pigment_ref()`: `steady_state_pigment_index` of the clear-sky daily mean shortwave on 2022-07-19 (382 W/m2, index 1.0). When the photo, mask, DEM or flow raster is absent the class-color writer runs as before. `mat_appearance.json` is not in `publish.FILES`; Godot reads only the png.
### Test
`tests/test_outflow_forcing.py::test_mat_appearance_wiring` (inputs, grid sizes, pigment_ref, sidecar), `::test_mat_appearance_absent_inputs_returns_none`, `::test_imagery_pigment_ref_is_clear_sky_on_acquisition_date`. A direct render from the 2026-10-13 16:12 MDT chain wrote `mat_pigment.png` and `mat_appearance.json` in 13 s; at the October pigment (0.56 against the 1.0 reference) the layer reads browner and less orange than the hand-published July-style render.

### 5. Deck and rails used pine bark as wood grain
`boardwalk.gdshader` sampled the bark texture with box-face UVs, and rails and posts used `bark_mat`.
### Fix
Procedural milled grain in `shaders/wood_grain.gdshaderinc`; world-space planks for the overlook deck; `shaders/timber.gdshader` for posts, beams and stringers with grain along each member's long axis. Logs keep bark.

### 6. Outflow equilibrium temperature is forced by a constant 1000 W/m2
`build._run_outflow_chain` sets `shortwave_w_m2 = 1000 * (1 - cloud)` for every hour and date. With the d3e weather (air 11.4 C, RH 0.34, cloud 0, wind 2.2 m/s) the equilibrium is 30.78 C, which is the floor found on 75 percent of mat cells. The floor itself is physical: thin sheet flow reaches equilibrium within millimeters to meters (cooling length rho cp q / k), so the distal sheets should sit at it.
| Forcing | Shortwave W/m2 | T_eq C |
|---|---|---|
| build constant | 1000 | 30.78 |
| 2026-10-13 16:12 MDT, pvlib Ineichen x Kasten-Czeplak | 426 | 19.37 |
| 2026-10-13 noon MDT | 666 | 24.38 |
| night | 0 | 9.62 |
| 2026-10-13 daily mean | 195 | 14.22 |
### Fix (done)
`simulate_all` resolves the epoch with `resolve_replay_start_epoch(cfg, hour0)` and passes it with its source to `_run_outflow_chain(world_root, air_c, wcfg, start_epoch_s, epoch_source)`. The MetState shortwave is `microbial_mats.instantaneous_shortwave_w_m2` at that epoch for the Grand Prismatic site (44.525 N, 110.837 W, 2240 m; `OUTFLOW_SITE_*` in `build.py`) with the configured cloud fraction. The sweep receives `forcing_epoch_utc`, and the outflow sidecar carries `shortwave_forcing` (clear-sky GHI, cloud factor, all-sky value, epoch, epoch source, site, sources). `mat_state.json` records the same `forcing_epoch_utc`.
### Verification
Direct `_run_outflow_chain` runs with the d3e weather (air 11.4 C, RH 0.34, cloud 0, wind 2.2 m/s): 2026-10-13 16:12 MDT gives 426.0 W/m2 and T_eq 19.42 C; 02:00 MDT gives 0 W/m2 and T_eq 9.64 C (table above: 19.37 and 9.62). 93 and 91 percent of wet cells sit within 0.01 C of T_eq, so the distal sheets still reach equilibrium, now at the forced value. Tests: `tests/test_outflow_forcing.py::test_outflow_shortwave_follows_simulation_epoch`, `::test_outflow_shortwave_scales_with_cloud`.

### 7. Mat insolation is computed for 2026-07-15 regardless of date
`_run_outflow_chain` passes the literal date to `daily_mean_insolation_w_m2`. Use the simulation date.
### Fix (done)
The daily mean is computed for the UTC date of the simulation epoch with the configured cloud fraction; `insolation` records `date_utc` and `date_source`. 2026-10-13 gives 195.0 W/m2 (table above: 195) and pigment 0.557. Test: `tests/test_outflow_forcing.py::test_mat_insolation_uses_simulation_date` (October below 0.7 of July; pigment equals the steady index).
### Not changed
`_run_periphyton` still forces periphyton with `1000 * (1 - cloud)` W/m2; it is outside this item.

### 8. Sinter substrate temperature, conductivity and thickness are authored
`SinterConduction` uses 20 C, 2.5 W/m/K and 0.10 m with status authored. These set part of the equilibrium. Needs a measured ground temperature under the apron (thermal infrared or probe literature) or a cited sinter conductivity; until then the status stays authored and the uncertainty stays unknown.
### Search
- Conductivity, found: Diment, W. H., and Pratt, H. R. (1988). Thermal conductivity of some rock-forming minerals: a tabulation. USGS Open-File Report 88-690, doi:10.3133/ofr88690 (Crossref checked). Table 1, read from the scanned page: opal, Virgin Valley, Nev., room dried, measured density 1.89 g/cm3, 3.3 mcal/cm/s/C at 30 C (25 and 100 bars); silica glass 3.3 (Ratcliffe 1959). 3.3 mcal/cm/s/C is 1.38 W/m/K. Siliceous sinter is opal-A, so this is the conductivity of the sinter solid. The 2.5 W/m/K default had no source; in the same table chert, jasper and novaculite run 13.0 to 17.4 mcal/cm/s/C (5.4 to 7.3 W/m/K) and flint 8.1 (3.4 W/m/K).
- Conductivity of apron sinter itself, not found: searches on siliceous sinter thermal conductivity and on near-surface rock properties in New Zealand geothermal fields returned no sinter measurement. Hurwitz and others (2012, JGR Solid Earth 117, doi:10.1029/2012JB009463) measured soil properties in acid-sulfate vapor-dominated ground, a different substrate. Porosity and water saturation of the apron sinter are unmeasured, so the bulk value is unknown.
- Thickness and substrate temperature, not found: no Grand Prismatic apron thickness, temperature profile, probe or borehole temperature under sheet flow was found. Vaughan and others (2012) give radiant surface heat flux, not a temperature at depth.
### Fix (done)
`outflow_thermal.SINTER_CONDUCTIVITY_W_M_K = 1.38` with `SINTER_CONDUCTIVITY_STATUS = "literature"` and `SINTER_CONDUCTIVITY_SOURCE`. Thickness 0.10 m and substrate 20 C stay authored as named constants (`SINTER_THICKNESS_M`, `SINTER_SUBSTRATE_T_C`). `param_registry` gains `outflow_thermal.sinter_k_w_m_k` (literature) and `outflow_thermal.sinter_thickness_m` and `outflow_thermal.sinter_substrate_t_c` (assumed), all with uncertainty unknown and review not_yet_accepted. The sidecar `sinter.status` stays authored because two of the three inputs are authored.
### Effect
The sinter coefficient k/L drops from 25 to 13.8 W/m2/K. The 20 C substrate acts as a thermostat, so daytime equilibria rise and night equilibria fall. With the d3e weather (air 11.4 C, RH 0.34, cloud 0, wind 2.2 m/s), T_eq at 2.5 and then 1.38 W/m/K: 1000 W/m2 30.84 and 33.82 C; 666 W/m2 24.43 and 25.86 C; 426 W/m2 19.41 and 19.19 C; 195 W/m2 14.24 and 11.95 C; 0 W/m2 9.63 and 5.20 C. The item 6 table was computed at 2.5 W/m/K. The real-network regression pin in `test_graph_sweep_outflow_temperature_matches_rework_7_real_run` (512 W/m2) moved from 21.173 to 21.555 C. `test_sinter_conductivity_default_is_opal_table_value` checks the unit conversion and the registry classes.
### Open
The lumped term holds a 20 C reservoir 0.10 m under perennial flow. At steady state the sinter under a perennial sheet warms toward the film and carries the geothermal flux upward, so the conductive term would be close to the apron heat flux into the water (`ground_heat.GHF_APRON_W_M2`, 120 W/m2, authored within cited ranges) at every water temperature. That boundary raises the 426 W/m2 equilibrium from 19.19 to 24.92 C. It is a model change outside this item and needs its own fixes entry.

### 9. Replay heat budget fails since the outflow override changed
Builds 1eead02b8171 and c300d2b51f5e fail `replay: budget closure checks failed`: heat relative residual 3.69e-7 against the 1e-7 tolerance after the Excelsior lateral changed from 0.26 m3/s at 62 C to 0.307 m3/s at 40.85 C (outflow chain override). Water closes; storage change is 639 MJ, so the run is not at steady state and the per-step residual (about 1,860 J) grows with the transient. `tests/test_build.py::test_replay_solver_conserves_heat_and_water` fails for the same reason. Blocks publish.
### Cause
Bookkeeping, not tolerance. `River._advance_to` applies the analytic hyporheic exchange (`_apply_hyporheic`) to the implicit-solve temperatures, then evaluated face fluxes, outlet export and surface power at the post-exchange temperatures. The solve balanced those fluxes at the pre-exchange temperatures, so each step left a residual of dt times the flux change at the outlet and surface (interior faces telescope). It scales with channel-storage disequilibrium, which the transient drives: hyporheic exchange was 0.93 J in d3e02892a81a and 11.5 GJ in 1eead02b8171. The 1e-7 tolerance is correct for a linear implicit solve with the Newton surface at 1e-7 C.
### Fix (done)
`_advance_to` keeps `transported`, the solve temperatures, and books faces and surface power on it; the exchange is booked separately as `hyporheic_exchange_j`. Physics and tolerance unchanged.
### Test
`replay/tests/test_hyporheic.py::test_transient_exchange_closes_to_roundoff` (zones on every cell, storage 8 C off the channel): relative residual 1.45e-3 before, below 1e-12 after; per-step and per-cell residuals below 0.01 J. `test_replay_solver_conserves_heat_and_water` passes at 1e-9. Build 7d39bfaa5739 passed: heat relative residual 1.26e-13, max step residual 2.5e-4 J, hyporheic exchange 16.8 GJ, combined channel plus storage residual 2.0e-13. audit_provenance 44 files, 0 failures. Not published: item 4 build wiring is open.

## Integration
Items 3, 4, 6, 7, 8 and 9 together, 2026-10-13.
- Suite `.venv/bin/python -m pytest tests yellowstone_python/replay/tests -q`: 1219 passed, 15 skipped, 0 failed (854 s).
- Build 2a8c8948128c (`configs/baseline.yaml`): passed, no failures. Replay heat relative residual 1.24e-13, max step residual 2.5e-4 J, water residual 4.5e-13 m3. Outflow forcing 426.0 W/m2 at 2026-10-13 22:12 UTC, T_eq 19.15 C (19.37 C at the old conductivity). Excelsior lateral override 0.307 m3/s at 34.82 C. `mat_appearance.json` status fitted_from_imagery, pigment_ref 1.0.
- `tools/audit_provenance.py --dir derived`: 44 files, 0 failures. Comment-style gate clean on the item 8 files.
- Published 2a8c8948128c into `yellowstone_midway` (78 files). The hand-rendered `data/mat_pigment.png` and the rest of the prior data are in `yellowstone_midway/backups/pre-2a8c8948128c-20261013T212604Z/`. `data/mat_pigment.png` matches the build png (sha256 1ee539584772078e...).
- Overlook view (Godot 4.5.1 `--capture --capture-index=0`, before and after publish, 0 script errors): ground present across the core, no pines on the sinter flats, deck and rail grain intact. The orange outflow streaks of the hand-rendered layer are gone. At the October pigment (0.557 against the 1.0 imagery reference) the Grand Prismatic rim reads yellow-olive, the outflow aprons dark olive to gray-brown, and the distal sheets close to bare sinter, so the spring loses its orange halo from the overlook. The boardwalk view shows no mat color near the walk. NOT TESTED: whether the pigment-departure mapping in `mat_appearance` matches autumn imagery of the apron; KJR visual acceptance.
