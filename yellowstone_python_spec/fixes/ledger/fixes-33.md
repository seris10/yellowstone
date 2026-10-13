# fixes-33 ledger (E2-a scope: items 3, 4, 11)
Doc: fixes/fixes-33-cross-domain-wiring.md | read 2026-10-12, open rows re-verified 2026-10-13 | targets: yellowstone_python/yellowstone_python/insects_birds.py sha256:1bbdfec2a0b2 ; yellowstone_python/yellowstone_python/aquatic_foodweb.py sha256:bf41259c35e6 ; yellowstone_python/yellowstone_python/fish.py sha256:06d673a3382d

Summary: 17 items: 13 implemented, 0 shortcut, 1 partial, 1 missing, 2 superseded, 0 conflicts (recounted from rows 2026-10-13)

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 3 | insect compartments share shear-based disturbance with foodweb | implemented | build.py bridge cell shear via shear_to_disturbance(foodweb_shear_disturb_pa) | prey_ledger carries forcing_disturbance, forcing_shear_pa, forcing_shear_disturb_pa, forcing_source | medium |
| 4 | insect forcing cell id and temperature recorded on compartment output | implemented | build.py prey_ledger forcing_cell_id, forcing_water_c; benthic_grid.json carries per-cell nb/emergence/disturbance_loss | bridge cell chosen as last Firehole landscape cell for the compartments path; C shipped `develop_benthic_grid` and A wires it from the replay thermal landscape in build.py and persists `benthic_grid.json` next to aquatic_foodweb.json | medium |
| 11 | trout position single authority (foodweb refuge cell) | implemented | build.py place_trout_at_chainage unconditional; trout_position_authority recorded in res and BUILD.json provenance; update_trout now takes cell_velocity_mps and cell_depth_m from the replay thermal landscape via `_per_point_hydraulics_from_cells` | update_trout retained to populate start/end point indices and now scores suitability on per-cell velocity and depth; equations.py entry is an E1-3 handoff | medium |

## Cross-project issues
- All three items need build.py (E1) to call existing E2-a code differently. E2-a code side is already compatible: shear_to_disturbance is a public function; insects_birds.step_compartments already accepts disturbance via forcing; place_trout_at_chainage already consumes the foodweb refuge selection.
- Item 11: equations.py (E1) must record which function is the single trout position authority.

## Scientific validity flags
- Item 3: two insect models in one build see different disturbance for the same river (foodweb maps bed_shear_pa through shear_to_disturbance; compartments see 0.0). Ecological inconsistency.
- Item 4: compartment output does not name which cell forces it; readers cannot trace a thermal response to a cell id.
- Item 11: trout position inconsistency between fish.update_trout (reach-level) and aquatic_foodweb (per-cell refuge) means published trout coordinates can disagree with the refuge rationale.

## Handoffs (E1)
- Compute per-step `disturbance = shear_to_disturbance(bridge.bed_shear_pa, SHEAR_DISTURB_PA)` in build.py; pass as `forcing["disturbance"]` to step_compartments. Record the shared SHEAR_DISTURB_PA source.
- Pass bridge cell id into step_compartments forcing or augment its ledger output to include `cell_id` and `water_c` provenance.
- Switch build.py to call `place_trout_at_chainage(wildlife, reaches, river_points, foodweb_selection)` instead of `update_trout` after the foodweb runs. Record the choice in equations.py.

# E2-b scope: items 9, 10, 13
Targets: yellowstone_python/yellowstone_python/vegetation.py ; snow_season.py ; hydrology_provider.py ; llm_backend.py (census read).

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 9 | grazing feedback into patch_step with stated lag | implemented | build.py:simulate_all `_grazers_input_from_consumed(prev_consumed_by_patch, sim_s)` fed into patch_step; veg_ledger records grazing_feedback_source=`grazer_module_previous_step_consumed_by_patch`, lag=1, prev_consumed_by_patch, config_grazers_ignored | the config vcfg.grazers no longer drives patch_step; a lag-1 driver reads `cfg.vegetation.prev_consumed_by_patch` (empty for single-step), so single-step builds run with zero demand; test_grazers_input_from_consumed_wiring covers the conversion | medium |
| 10 | vegetation suitability reads per-patch canopy from census | implemented | build.py _canopy_from_census reads derived/census.json; proposal canopy threaded through propose_plantings_reviewed | 0.6 kept only as labeled illustrative_fallback_* when census.json missing/empty; canopy_source recorded in BUILD.json provenance | medium |
| 13 | document two soil-water models and their domains | implemented | snow_season.py:run_season docstring, hydrology_provider.py:HydrologyProvider docstring | Decision: snow-season bucket is the authority for patch phenology; hydrosim ground_wetness is the authority for overland generation. The two represent different depths and must not be compared without a documented cross-grid mapping. Downstream consumers read at most one per patch | cheap |

## E2-b cross-project issues
- Item 9's upstream in build.py cannot be edited by E2-b; vegetation.patch_step now returns `consumed_by_patch` keyed by patch id so a lag-1 scheduler in build.py can carry it forward.
- Item 10 depends on build.py reading `census.json` (now exposed through llm_backend.Backend.census and census_points) and computing crown-area-in-patch over patch-area for each patch; vegetation side is already ready to accept a per-patch canopy value.

## E2-b handoffs (E1)
- build.py: on each patch_step call, pass `grazers={grazer_id: {patch_id, active, rate_per_second}}` built from the grazer module's output of the previous step. The patch_step ledger returns `consumed_by_patch` so the lag-1 scheduler reads from step n-1.
- build.py: before calling `vegetation.suitability`, compute per-patch canopy fraction from `derived/census.json` crown positions (circle-sum intersected with each patch polygon over patch area) and pass the per-patch value; keep the 0.6 scalar only as an explicit illustrative fallback.

# E1-5 scope: items 5 and 6 (publish side)
Targets: yellowstone_python/yellowstone_python/publish.py ; yellowstone_python/yellowstone_python/exporters/to_ecosystem.py ; yellowstone_python/yellowstone_python/exporters/godot_sidecars.py (new).

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 5 | geochemistry.json shipped to Godot as per-cell silica saturation diagnostic | implemented (publish side) | exporters/godot_sidecars.py:131-189; publish.py FILES entry and produce_sidecars call | writes per-cell quartz-equilibrium SI (Fournier 1977 no-steam-loss) from the last replay frame; silica_saturation_index=null + flag=no_observation when SiO2 observations are absent (current build case). The ecological coupling (silica -> aquatic habitat) stays proposed per the fixes doc; this publish only reaches Godot. The build-side call to diagnose_replay_frame (fixes-33 item 5 build.py scope) stays an E1-2 handoff; the sidecar is produced in-place during publish instead. | medium |
| 6 | plume_field.json shipped to Godot in place of plume_map.png | implemented (publish side) | exporters/godot_sidecars.py:66-128; publish.py FILES entry and produce_sidecars call | 128x128 steady plume via replay.plume2d.solve_steady with the build's Excelsior and Firehole bridge temperatures; sidecar carries axes_x_m, axes_z_m, origin_xz, hot_source_c, river_c, temperature_grid_c, discrete_residual_c_s, status=illustrative. plume_map.png stays as evidence; neither is overlaid on the foodweb (overlay stays proposed). | medium |

## E1-5 cross-project issues
- Items 5 and 6 are landed on the publish side (the sidecars reach yellowstone_midway/data/) but their build-side computation (per fixes-33 "E1" scope in the doc) stays an E1-2 handoff; publish-time computation is a reasonable interim path since the sources (river_state.json, river_replay.json) are already in the build dir.
- Fixes-28 item 4 depends on build.py (E1-2) calling merge_fragments with the effective boundary_m3s and boundary_c; the exporter now accepts them, but until build.py passes them the ecosystem.godot.json still carries the baseline boundary (equal to the illustrative 8.0 m3/s for standard runs). Record this when any downstream code reports a boundary mismatch.

## E1-5 handoffs (E1-2 build.py)
- build.py:788-800: update `merge_fragments(baseline, river_state, weather_frag_filtered, clock_hour=hour0)` to also pass `boundary_m3s=boundary_m3s` and `boundary_c=hcfg.get("boundary_c", baseline["boundary_c"])` so the exported ecosystem.godot.json carries the effective (baseflow+runoff) boundary. The exporter now accepts these kwargs with defaults that preserve current behavior.
- Optional: pre-produce the Godot sidecars inside build.py by calling `yellowstone_python.exporters.godot_sidecars.produce_all(out)` after the rest of the build runs, so BUILD.json records the sidecars and their shas. The current publish-time production is the fallback path.

# E1-2 build.py scope: items 5, 6 (build side), 7, 8, 12, 14, 15

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 5 (build) | call diagnose_replay_frame and write geochemistry.json | superseded | build.py:1491-1494 produce_all writes geochemistry.json through exporters/godot_sidecars.write_geochemistry_json | coordinator 2026-10-12: the build-side block was removed; it read thermal_landscape before the function imported it (UnboundLocalError that its except clause did not catch) and its output was overwritten by the exporter at the end of the same build. One writer per file. | cheap |
| 6 (build) | publish 2-D plume field as data | superseded | build.py:1491-1494 produce_all writes plume_field.json through exporters/godot_sidecars.write_plume_field_json; render_all keeps plume_map.png | coordinator 2026-10-12: the build-side block was removed; it treated the flat nx*nz field as rows (TypeError, every build crashed in render_all) and duplicated the exporter's file. Build 839a78f1c159 passes with the exporter as the single writer. | cheap |
| 7 | measured precipitation drives overland flow in hindcast/observed_replay | implemented | build.py:869-908 reads met_bundle.precipitation_mm in hindcast/observed_replay, averages finite non-negative samples into rain_mm_h, records rain_source; raises when neither explicit nor bundle precipitation is available in non-illustrative modes | tools/fetch_met_forcing.py side was already closed; build.py side now consumes it | medium |
| 8 | run_season uses measured bundle in hindcast/observed_replay | implemented (snow_season side) | snow_season.py:185-280 ; snow_season.py:21-45 daily_air_c_from_hourly | run_season accepts run_mode and air_hourly_c (met_forcing.v1 rows [epoch, air_c, ...]); hindcast/observed_replay with air_hourly_c derives the daily series from a per-UTC-day mean and overrides the passed air_c_by_day; illustrative keeps air_c_by_day verbatim; forcing_source and run_mode land in the ledger. S1 2026-10-12: build.py handoff (E1-2) to pass run_mode=run_mode_norm and air_hourly_c=met_bundle["hourly"] into run_season | medium |
| 12 | explicit energy budget default by run_mode and bundle fullness | implemented | build.py run_replay_solver call sets energy_budget via run_mode + full_bundle; replay_doc.provenance.energy_budget_source and BUILD.json provenance.energy_budget_source | hindcast/observed_replay with full bundle default to True; illustrative keeps config default | cheap |
| 14 | orphan modules labeled or wired | missing | module docstrings not updated here | handed off to the module owners; AGENTS.md section 7 update is E1-4 scope | medium |
| 1 | overland runoff reaches the river boundary | implemented | build.py:simulate_all `_compute_overland_field` + `_overland_runoff_to_boundary`; boundary_m3s = baseflow + snow_runoff + overland_runoff; BUILD.json records hydrology_components and overland_field.boundary_contribution | step R (scheduled boundary) was already in River; A now converts overland outlet volume to a mean rate (outflow_m3 / sim_s) and adds it to the scalar boundary; coupling tagged partial (contributing area not delineated from terrain); baseline overland disabled keeps baseline unchanged; test_overland_runoff_divides_outflow_by_window and test_overland_runoff_zero_when_disabled cover both paths | medium |
| 2 | groundwater exchange wired only once physical | partial | build.py:_write_variant_and_gate calls `head_gradient_exchange` when `hydro.groundwater.cells` is configured; checks.metrics.groundwater_exchange carries status/totals or the partial reason | B shipped head_gradient_exchange (q = C (h_aq - h_r), C = K W L / b, gaining = Source, losing = sidecar); A wires it conditionally and records the "no cells configured" reason in BUILD.json otherwise; coupling stays partial because baseline has no authored cells | refactor |
| 15 | study replays record build_id and run_mode | implemented | tools/run_hot_lowflow.py:77-114 (source_build_id stamped from the unmutated config); tools/run_hot_lowflow_with_tributaries_v2.py:285-324; yellowstone_python/publish.py:63-91,153-160 | runner stamps source_build_id = build_id of the unmutated config; publish refuses firehole_control.json / firehole_pulse.json whose source_build_id is absent or does not resolve to a sibling under derived/. Rule: the study runner's own build_id is for the mutated scenario config and does not match a derived/ dir, so the gate keys on source_build_id | medium |

## E1-2 cross-project
- Item 7: full wiring needs an Open-Meteo precipitation field (not in the current bundle schema), handed off to D cluster.
- Item 8: wiring the met bundle hourly temperatures into run_season's daily air_c_by_day requires choosing an aggregation window; handed off to E2-b (snow_season.py).
- Item 15: study runners live in tools/ (D cluster) and publish.py (E1-5); build.py cannot enforce the record from here.

## Coordinator finding (2026-10-12, after the fixes-14 item 3 solar block landed)
- Weather solar block versus Godot validators: llm_backend's weather response carries microclimate.solar_snapshot, whose solar_elevation_deg is the true elevation (below -18 degrees at night). weather_snapshot_reader.gd rejected the whole snapshot when elevation fell below -18 (the controller then kept stale weather all night) and weather_http_consumer.gd dropped the pair. Both validators now accept the physical range [-90, 90]; yellowstone_atmosphere.gd still clamps to [-18, 90] for lighting. Evidence: yellowstone_midway/scripts/weather_snapshot_reader.gd:370, weather_http_consumer.gd:514, mirrored in yellowstone_atmosphere/scripts; validate_atmosphere_canonical.gd OK (4 pairs); headless main scene zero SCRIPT ERROR. Verdict: implemented.
