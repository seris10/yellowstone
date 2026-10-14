window.YS_DASHBOARD = {
 "generated_utc": "2026-10-14 01:37 UTC",
 "sources": {
  "inventory_python": "Current referenced-source sha256-12: hydrology/demo_hydrosim.py=daa91c657881; hydrology/hydrosim.py=2fe6f6074e3d; hydrology/validate_hydrosim.py=354ef65c2ee0; yellowstone_midway/scripts/ecosystem.gd=add6a99dfec5; yellowstone_midway/scripts/pool_overlay.gd=0636371d9b83; yellowstone_midway/scripts/python_river_replay.gd=bda1dced97bf; yellowstone_midway/scripts/thermal_probe_overlay.gd=4dcee11c7769; yellowstone_midway/scripts/wildlife_actor.gd=8d1f69d370d0; yellowstone_midway/scripts/world.gd=286bf8522556; yellowstone_python/tools/audit_provenance.py=42f5ec7bfb46; yellowstone_python/tools/build_store.py=8a1333b6f2b9; yellowstone_python/tools/calibrate_river_transport.py=201c4b51512f; yellowstone_python/tools/channel_geometry.py=3521dfdcd77e; yellowstone_python/tools/check_terrain.py=eae68353c9ad; yellowstone_python/tools/compare_bundles.py=736c435a1bde; yellowstone_python/tools/execute_notebook.py=59bd2fe83bc4; yellowstone_python/tools/fetch_firehole_obs.py=fb5dcc296425; yellowstone_python/tools/fetch_met_forcing.py=decc67866af2; yellowstone_python/tools/fetch_snotel_obs.py=b1e48768531e; yellowstone_python/tools/fetch_yellowstone_tributaries.py=c3e9eeac6845; yellowstone_python/tools/plot_fit.py=04f6f8a02448; yellowstone_python/tools/usgs_nwis.py=637fc5fb2f16; yellowstone_python/tools/validate_obs_bundles.py=a0c682a9eca3; yellowstone_python/yellowstone_python/aquatic/aquatic_foodweb.py=406e2cfe6094; yellowstone_python/yellowstone_python/aquatic/fish.py=94aa2107d78b; yellowstone_python/yellowstone_python/aquatic/thermal_curves.py=022e33e3a68f; yellowstone_python/yellowstone_python/atmosphere/microclimate.py=7d72a9ace691; yellowstone_python/yellowstone_python/atmosphere/time_utils.py=fc1bc89c0034; yellowstone_python/yellowstone_python/authoring/gen_flora.py=2ac3a3fcb200; yellowstone_python/yellowstone_python/authoring/gen_trail_mask.py=f3d7303a4564; yellowstone_python/yellowstone_python/authoring/review_proposals.py=e6ea09c3b2b1; yellowstone_python/yellowstone_python/census/canopy_census.py=e5d5c9358e64; yellowstone_python/yellowstone_python/census/census_validate.py=f4ce39e091b9; yellowstone_python/yellowstone_python/cli/publish.py=93353164579a; yellowstone_python/yellowstone_python/common/coords.py=f8aea03661d6; yellowstone_python/yellowstone_python/common/provenance.py=bbbe3b133f2b; yellowstone_python/yellowstone_python/common/units.py=1a2b66a7805c; yellowstone_python/yellowstone_python/compare.py=3a4f539f95eb; yellowstone_python/yellowstone_python/exporters/godot_sidecars.py=172d66696a74; yellowstone_python/yellowstone_python/exporters/to_ecosystem.py=fdf9f0f7fd96; yellowstone_python/yellowstone_python/exporters/to_map.py=0647193734f2; yellowstone_python/yellowstone_python/insects_birds.py=9907ffee428f; yellowstone_python/yellowstone_python/land/grazers.py=9edef5b1a822; yellowstone_python/yellowstone_python/land/groundwater_provider.py=db4f1db489ef; yellowstone_python/yellowstone_python/land/hydrology_provider.py=2c9944ba1bc6; yellowstone_python/yellowstone_python/land/overland_flow.py=8e8dff278ee4; yellowstone_python/yellowstone_python/land/overland_provider.py=b924da64a1ee; yellowstone_python/yellowstone_python/land/snow_energy.py=21e9735190eb; yellowstone_python/yellowstone_python/land/snow_season.py=8530e64c6ab1; yellowstone_python/yellowstone_python/land/snow_validate.py=aeca5e5a5d84; yellowstone_python/yellowstone_python/land/vegetation.py=838ee01986f7; yellowstone_python/yellowstone_python/pipeline/config.py=81715bacaaf9; yellowstone_python/yellowstone_python/pipeline/inputs.py=6f039a591d76; yellowstone_python/yellowstone_python/pipeline/pipeline.py=5c24b07108d4; yellowstone_python/yellowstone_python/pipeline/render.py=184395bc6222; yellowstone_python/yellowstone_python/pipeline/sidecars.py=a3ee5a6bc71e; yellowstone_python/yellowstone_python/publish.py=20709897b639; yellowstone_python/yellowstone_python/registry/claims.py=57faf990357e; yellowstone_python/yellowstone_python/registry/coupling.py=a1867aaa9475; yellowstone_python/yellowstone_python/registry/equations.py=8d48ef6d07b0; yellowstone_python/yellowstone_python/registry/param_registry.py=e7d41edab545; yellowstone_python/yellowstone_python/registry/run_mode.py=6d1f496511d0; yellowstone_python/yellowstone_python/river/benchmarks.py=ce3f7acce30a; yellowstone_python/yellowstone_python/river/calibrate.py=67ae4ca11d77; yellowstone_python/yellowstone_python/river/datasets.py=72c44a7406fb; yellowstone_python/yellowstone_python/river/figures.py=58bedd341501; yellowstone_python/yellowstone_python/river/fipy_reference.py=ee14c79ed594; yellowstone_python/yellowstone_python/river/hydraulics.py=3f8a52180fcc; yellowstone_python/yellowstone_python/river/identifiability.py=6965d5bbdb3a; yellowstone_python/yellowstone_python/river/nc_export.py=e1a5c0aaf8e7; yellowstone_python/yellowstone_python/river/obs_frame.py=c406e7ae68d5; yellowstone_python/yellowstone_python/river/obs_model.py=8c457f30adab; yellowstone_python/yellowstone_python/river/plume2d.py=0942686fb0de; yellowstone_python/yellowstone_python/river/reach_reference.py=0ce0da88cc21; yellowstone_python/yellowstone_python/river/river_transport.py=360fe7e6cbdd; yellowstone_python/yellowstone_python/river/river_world.py=008ced9a47d1; yellowstone_python/yellowstone_python/river/surface_flux.py=dfe568aa14d8; yellowstone_python/yellowstone_python/river/uncertainty.py=f3a9ea13784a; yellowstone_python/yellowstone_python/scenarios/hot_lowflow.py=d033250ac7ba; yellowstone_python/yellowstone_python/service/analysis_store.py=be6948e9fd8d; yellowstone_python/yellowstone_python/service/llm_backend.py=c56b1a993bde; yellowstone_python/yellowstone_python/study_mode.py=51d920aa12ce; yellowstone_python/yellowstone_python/thermal_features/geochemistry.py=56ea01159b86; yellowstone_python/yellowstone_python/thermal_features/pool_crust.py=dc3314e9be3b; yellowstone_python/yellowstone_python/validation/checks.py=9a5c93a27f4c; yellowstone_python/yellowstone_python/validation/claims.py=f0ff294f154e; yellowstone_python/yellowstone_python/validation/contracts.py=b7a5d84d7f12",
  "inventory_godot": "Current source/data SHA-256 inventory: yellowstone_midway/data/asset_manifest.json@d82a74822797, yellowstone_midway/data/consumers.json@5650d9348369, yellowstone_midway/data/terrain.f32@8f5ca1bf65eb, yellowstone_midway/project.godot@cc54a9b3ba3f, yellowstone_midway/scenes/authored_world.tscn@0d1e6476f0dd, yellowstone_midway/scenes/botanical_details.tscn@70a06586f6ce, yellowstone_midway/scenes/handcrafted_details.tscn@d85430e528aa, yellowstone_midway/scenes/study.tscn@5e3b7ba3ee84, yellowstone_midway/scripts/authored_placement.gd@5103c95d73de, yellowstone_midway/scripts/calibration_panel.gd@ad0c32cb1a20, yellowstone_midway/scripts/data_watcher.gd@6018ea44be50, yellowstone_midway/scripts/ecosystem.gd@add6a99dfec5, yellowstone_midway/scripts/height_field.gd@222fe409957b, yellowstone_midway/scripts/input_help.gd@0dd8beb94a63, yellowstone_midway/scripts/live_python_client.gd@9f22c6fb682a, yellowstone_midway/scripts/map_view.gd@6fa399091680, yellowstone_midway/scripts/mat_surface.gd@f1462054281a, yellowstone_midway/scripts/player.gd@98ceea1b96f7, yellowstone_midway/scripts/pool_overlay.gd@0636371d9b83, yellowstone_midway/scripts/python_river_replay.gd@bda1dced97bf, yellowstone_midway/scripts/scientific_overlays.gd@7d8e2bc77eaa, yellowstone_midway/scripts/simulation_panel.gd@a2fe8d35f9c0, yellowstone_midway/scripts/thermal_probe_overlay.gd@4dcee11c7769, yellowstone_midway/scripts/weather_snapshot_reader.gd@2054cd25daa5, yellowstone_midway/scripts/wildlife_actor.gd@8d1f69d370d0, yellowstone_midway/scripts/world.gd@286bf8522556, yellowstone_midway/scripts/yellowstone_atmosphere.gd@466a8710e66c, yellowstone_midway/shaders/boardwalk.gdshader@a6a6028ffbf9, yellowstone_midway/shaders/foliage.gdshader@9c2b6fbc19a0, yellowstone_midway/shaders/steam.gdshader@c604fadf723c, yellowstone_midway/shaders/terrain.gdshader@5da142ac6140, yellowstone_midway/shaders/trail.gdshader@388494c2d20f, yellowstone_midway/shaders/water.gdshader@c6d1bb9b94b0, yellowstone_midway/shaders/yellowstone_cloud_shell.gdshader@7f5acf01294f, yellowstone_midway/tools/bake_botany.gd@6c795f473668, yellowstone_midway/tools/bake_world.gd@64d3c52c7ee5, yellowstone_midway/tools/prepare_swimming_trout.py@d99eaf0d1f9a, yellowstone_midway/tools/tests/test_fish_swim.py@0e2ebedc9f41, yellowstone_midway/tools/validate_consumers.gd@443254002aa5, yellowstone_midway/tools/validate_data_watcher.gd@04b9bb6719f6, yellowstone_midway/tools/validate_ecology.gd@3d3e2083fd76, yellowstone_midway/tools/validate_interface.gd@0ea8dfd39c20, yellowstone_midway/tools/validate_live_client.gd@ac3355d60a37, yellowstone_midway/tools/validate_live_service.gd@bfd815a56f36, yellowstone_midway/tools/validate_projection.gd@656b7ece9d99, yellowstone_python/yellowstone_python/aquatic/aquatic_foodweb.py@406e2cfe6094, yellowstone_python/yellowstone_python/aquatic/fish.py@94aa2107d78b, yellowstone_python/yellowstone_python/atmosphere/microclimate.py@7d72a9ace691, yellowstone_python/yellowstone_python/exporters/godot_sidecars.py@172d66696a74, yellowstone_python/yellowstone_python/exporters/runtime_series.py@50866c7394a1, yellowstone_python/yellowstone_python/insects_birds.py@9907ffee428f, yellowstone_python/yellowstone_python/land/snow_season.py@8530e64c6ab1, yellowstone_python/yellowstone_python/land/vegetation.py@838ee01986f7, yellowstone_python/yellowstone_python/registry/equations.py@8d48ef6d07b0, yellowstone_python/yellowstone_python/registry/param_registry.py@e7d41edab545, yellowstone_python/yellowstone_python/river/calibrate.py@67ae4ca11d77, yellowstone_python/yellowstone_python/river/river_transport.py@360fe7e6cbdd, yellowstone_python/yellowstone_python/service/live/engine.py@bcf14fe1218b, yellowstone_python/yellowstone_python/service/server.py@646818416bd8, yellowstone_python/yellowstone_python/study_mode.py@51d920aa12ce, yellowstone_python/yellowstone_python/thermal_features/mat_appearance.py@af21e0dbfa49, yellowstone_midway/data/river_replay.json@fa51a017de6e, yellowstone_midway/data/ecosystem.json@f71f2ad7b056, yellowstone_midway/data/world.json@ee15ef84b106",
  "inventory_plans": "Current referenced-source sha256-12: yellowstone_atmosphere/scripts/weather_http_consumer.gd=181a1f27512c; yellowstone_atmosphere/scripts/weather_snapshot_reader.gd=2054cd25daa5; yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd=466a8710e66c; yellowstone_midway/scripts/data_watcher.gd=6018ea44be50; yellowstone_midway/scripts/live_python_client.gd=9f22c6fb682a; yellowstone_midway/scripts/simulation_panel.gd=a2fe8d35f9c0; yellowstone_midway/scripts/weather_http_consumer.gd=181a1f27512c; yellowstone_midway/scripts/weather_snapshot_reader.gd=2054cd25daa5; yellowstone_midway/scripts/world.gd=286bf8522556; yellowstone_midway/scripts/yellowstone_atmosphere.gd=466a8710e66c; yellowstone_midway/shaders/terrain.gdshader=5da142ac6140; yellowstone_midway/shaders/thermal_apron.gdshader=34c3f60b866d; yellowstone_midway/shaders/yellowstone_cloud_shell.gdshader=7f5acf01294f; yellowstone_midway/tools/prepare_world.py=bf1f7b278080; yellowstone_python/tests/river/test_identifiability.py=73016137e19b; yellowstone_python/tools/calibrate_river_transport.py=201c4b51512f; yellowstone_python/yellowstone_python/aquatic/fish.py=94aa2107d78b; yellowstone_python/yellowstone_python/atmosphere/microclimate.py=7d72a9ace691; yellowstone_python/yellowstone_python/build.py=794a32c0c86e; yellowstone_python/yellowstone_python/exporters/godot_sidecars.py=172d66696a74; yellowstone_python/yellowstone_python/land/groundwater_provider.py=db4f1db489ef; yellowstone_python/yellowstone_python/pipeline/sidecars.py=a3ee5a6bc71e; yellowstone_python/yellowstone_python/registry/claims.py=57faf990357e; yellowstone_python/yellowstone_python/river/identifiability.py=6965d5bbdb3a; yellowstone_python/yellowstone_python/river/nc_export.py=e1a5c0aaf8e7; yellowstone_python/yellowstone_python/service/live/engine.py=bcf14fe1218b; yellowstone_python/yellowstone_python/service/llm_backend.py=c56b1a993bde; yellowstone_python/yellowstone_python/service/server.py=646818416bd8; yellowstone_python/yellowstone_python/study_mode.py=51d920aa12ce; yellowstone_python/yellowstone_python/thermal_features/geochemistry.py=56ea01159b86; yellowstone_python/yellowstone_python/thermal_features/pool_crust.py=dc3314e9be3b; yellowstone_python/yellowstone_python/validation/claims.py=f0ff294f154e"
 },
 "verified": {
  "python": "2026-10-13T08:06Z",
  "godot": "2026-10-14T01:36:34+00:00",
  "plans": "2026-10-13T10:05Z"
 },
 "component_statuses": [
  "rendered",
  "python_only",
  "partial_unwired",
  "not_started",
  "next_phase"
 ],
 "coupling_statuses": [
  "wired",
  "partial",
  "missing",
  "proposed"
 ],
 "verdicts": [
  "implemented",
  "shortcut",
  "partial",
  "missing",
  "superseded",
  "conflicts"
 ],
 "area_labels": {
  "D": "Data ingestion",
  "R": "River and atmosphere physics",
  "E1": "Pipeline and registries",
  "E2": "Ecology, snow, census, backend",
  "G": "Godot world and atmosphere",
  "N": "Additional specifications"
 },
 "components": [
  {
   "id": "build_orchestrator",
   "label": "Build pipeline (simulate_all + render_all + gate)",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/pipeline/pipeline.py",
    "yellowstone_python/yellowstone_python/pipeline/config.py",
    "yellowstone_python/yellowstone_python/pipeline/inputs.py",
    "yellowstone_python/yellowstone_python/pipeline/render.py",
    "yellowstone_python/yellowstone_python/pipeline/sidecars.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/pipeline/pipeline.py:8 stage_contracts",
    "yellowstone_python/yellowstone_python/pipeline/pipeline.py:14 validate_stage_dependencies",
    "yellowstone_python/yellowstone_python/pipeline/pipeline.py:24 simulate_all",
    "yellowstone_python/yellowstone_python/pipeline/config.py:6 load_config",
    "yellowstone_python/yellowstone_python/pipeline/config.py:24 normalized_config",
    "yellowstone_python/yellowstone_python/pipeline/config.py:32 validate_config",
    "yellowstone_python/yellowstone_python/pipeline/inputs.py:59 load_inputs",
    "yellowstone_python/yellowstone_python/pipeline/render.py:6 render_all",
    "yellowstone_python/yellowstone_python/pipeline/sidecars.py:461 mat_imagery_pigment_ref"
   ],
   "method": "ordered declared stages: weather, thermal features, vegetation, land, river, foodweb, insects, fish, grazers, finalize; mapped finite-volume river cells provide the runtime temperature and discharge",
   "validation": "none",
   "notes": "fresh build directories contain model outputs, conservation checks, dependency hashes, registries, and runtime sidecars",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "publish_transaction",
   "label": "Transactional publish to Godot world",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/publish.py",
    "yellowstone_python/yellowstone_python/cli/publish.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/publish.py:80 consumer_manifest_errors",
    "yellowstone_python/yellowstone_python/publish.py:147 main",
    "yellowstone_python/yellowstone_python/cli/publish.py:18 main"
   ],
   "method": "check completed build and consumer manifest; back up targets, copy completed artifacts, verify hashes, and write receipt; roll back copied targets on failure",
   "validation": "none",
   "notes": "publishes river_replay.json, runtime world epoch, ecosystem, weather, declared sidecars and textures; leaves completed build artifacts unchanged",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "run_mode",
   "label": "Run mode declaration and prescribed/predicted split",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/registry/run_mode.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/registry/run_mode.py:17 normalize_run_mode",
    "yellowstone_python/yellowstone_python/registry/run_mode.py:60 prescribed_quantities",
    "yellowstone_python/yellowstone_python/registry/run_mode.py:79 predicted_quantities"
   ],
   "method": "enum validation of run_mode plus list of prescribed/predicted quantities",
   "validation": "none",
   "notes": "feeds BUILD.json manifest and validation checks",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "claims_registry",
   "label": "Scientific claim registry",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/registry/claims.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/registry/claims.py:224 split_artifact_id",
    "yellowstone_python/yellowstone_python/registry/claims.py:238 resolve_artifact_id",
    "yellowstone_python/yellowstone_python/registry/claims.py:266 get_claim"
   ],
   "method": "static list of five claims each with required processes, calibration/evaluation dataset IDs, acceptance criteria; all review_status=not_yet_accepted",
   "validation": "none",
   "notes": "two seed claims (reach temperature, snow SWE) have evidence artifacts; the three provider claims (discharge, groundwater, 2-D channel) have empty datasets",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "coupling_registry",
   "label": "Component exchange contract",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/registry/coupling.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/registry/coupling.py:410 validate_contract",
    "yellowstone_python/yellowstone_python/registry/coupling.py:482 check_coupling",
    "yellowstone_python/yellowstone_python/registry/coupling.py:728 check_cross_family"
   ],
   "method": "declared exchanges, conservation and physical-support checks; runtime reach summaries use the mapped river cells",
   "validation": "none",
   "notes": "named exchanges: boundary_water, boundary_heat, lateral_water, lateral_heat, outlet_export, surface_newton, surface_budget, landscape_temperature, pocket_holding, snow_runoff_discharge, shear_disturbance; coupling_check.json records the verifier verdict per build",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "equations_registry",
   "label": "Governing equations inventory",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/registry/equations.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/registry/equations.py:356 validate_inventory"
   ],
   "method": "static declaration of model level, equations, assumptions, limits per component",
   "validation": "none",
   "notes": "governing equations, assumptions, units and evidence status for each declared component",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "param_registry",
   "label": "Parameter class and evidence registry",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/registry/param_registry.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/registry/param_registry.py:1112 validate_entry",
    "yellowstone_python/yellowstone_python/registry/param_registry.py:1172 source_ref_errors",
    "yellowstone_python/yellowstone_python/registry/param_registry.py:1196 registry_errors"
   ],
   "method": "per-knob record of param_class (observed, derived, literature, calibrated, assumed, illustrative, physical_constant), source references, applicability, uncertainty, missingness, review",
   "validation": "none",
   "notes": "unknown uncertainty allowed; registry_errors cross-checks source references against config files",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "provenance",
   "label": "Hashes, build IDs, sidecars",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/common/provenance.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/common/provenance.py:23 default_world_root",
    "yellowstone_python/yellowstone_python/common/provenance.py:32 resolve_code_rev",
    "yellowstone_python/yellowstone_python/common/provenance.py:49 sha256_json"
   ],
   "method": "SHA-256 hashing of inputs/code/config; build_id = short digest; write_sidecar adds parameter_provenance block",
   "validation": "none",
   "notes": "every build artifact carries sources and params provenance block",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "validation_checks",
   "label": "Build gate (checks)",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/validation/checks.py",
    "yellowstone_python/yellowstone_python/validation/claims.py",
    "yellowstone_python/yellowstone_python/validation/contracts.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/validation/checks.py:18 check_uq_document",
    "yellowstone_python/yellowstone_python/validation/checks.py:53 run_all",
    "yellowstone_python/yellowstone_python/validation/claims.py:53 check_reach_rmse",
    "yellowstone_python/yellowstone_python/validation/claims.py:110 check_snotel_rmse",
    "yellowstone_python/yellowstone_python/validation/claims.py:146 run_claim_gates",
    "yellowstone_python/yellowstone_python/validation/contracts.py:12 check_reach_chain",
    "yellowstone_python/yellowstone_python/validation/contracts.py:33 check_heat_ledger",
    "yellowstone_python/yellowstone_python/validation/contracts.py:67 check_provenance"
   ],
   "method": "conservation (heat ledger), topology, provenance, determinism, run-mode split; folds coupling, cross-family and FiPy convergence checks; validation/claims.py gates reach and SNOTEL holdout rmse against null models; aggregates godot/apron/refuge/substrate/snow/grazer/replay-budget failures",
   "validation": "none",
   "notes": "exit code 2 when any gate fails",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "hydro_units",
   "label": "Hydrology unit validation",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/common/units.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/common/units.py:10 UnitError",
    "yellowstone_python/yellowstone_python/common/units.py:21 c_to_k",
    "yellowstone_python/yellowstone_python/common/units.py:28 k_to_c"
   ],
   "method": "optional pint registry; refuses bare or mixed-unit hydro fields",
   "validation": "none",
   "notes": "",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "coords_frame",
   "label": "Single EPSG:32612 coordinate frame",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/common/coords.py",
    "yellowstone_python/yellowstone_python/common/units.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/common/coords.py:24 local_to_utm",
    "yellowstone_python/yellowstone_python/common/coords.py:29 utm_to_local",
    "yellowstone_python/yellowstone_python/common/coords.py:34 sample_index",
    "yellowstone_python/yellowstone_python/common/units.py:10 UnitError",
    "yellowstone_python/yellowstone_python/common/units.py:21 c_to_k",
    "yellowstone_python/yellowstone_python/common/units.py:28 k_to_c"
   ],
   "method": "central constants matched against prepare_world.py; unit converters fail on bare or mixed units",
   "validation": "none",
   "notes": "",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "exporter_to_ecosystem",
   "label": "Merge Python fragments into schema-v1 ecosystem.json",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/exporters/to_ecosystem.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/ecosystem.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/exporters/to_ecosystem.py:15 merge_fragments",
    "yellowstone_python/yellowstone_python/exporters/to_ecosystem.py:46 validate_for_godot"
   ],
   "method": "copy baseline, overwrite river_reaches, inject weather keys, set clock_hour, attach patches2 and wildlife3; validate_for_godot gates schema",
   "validation": "illustrative",
   "notes": "sole published surface for river/weather/patches/wildlife; ecosystem.gd advances insect_activity, biomass, moisture off these records",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "exporter_to_map",
   "label": "Reproject PNG fields into midway_macro frame",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/exporters/to_map.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/exporters/to_map.py:5 reproject_to_macro"
   ],
   "method": "stub placeholder, 9 lines",
   "validation": "none",
   "notes": "declared responsibility; no implementation and not called by build",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "analysis_store",
   "label": "SQLite analysis store (per-build)",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/service/analysis_store.py",
    "yellowstone_python/tools/build_store.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/service/analysis_store.py:22 NoStoreError",
    "yellowstone_python/yellowstone_python/service/analysis_store.py:26 f_to_c",
    "yellowstone_python/yellowstone_python/service/analysis_store.py:30 in_to_mm",
    "yellowstone_python/tools/build_store.py:59 main"
   ],
   "method": "read-only queries over allow-listed tables and columns (census_trees, replay_cells, replay_frames, obs_usgs, obs_snotel, fits_reach, fits_snow, meta)",
   "validation": "none",
   "notes": "operator runs tools/build_store.py after a build; neither build.py nor publish.py call it",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "llm_backend",
   "label": "HTTP backend for census analysis and proposal review",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/service/llm_backend.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/service/llm_backend.py:58 DataError",
    "yellowstone_python/yellowstone_python/service/llm_backend.py:162 Backend",
    "yellowstone_python/yellowstone_python/service/llm_backend.py:803 serve"
   ],
   "method": "stdlib HTTP server exposing /api/snapshot, /api/density, /api/compare, /api/propose over analysis_store and provider stacks",
   "validation": "none",
   "notes": "runs on demand (python3 -m yellowstone_python.llm_backend --serve); not touched by build/publish",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "study_mode",
   "label": "study_mode A/B presets",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/study_mode.py"
   ],
   "godot": [
    "yellowstone_midway/scenes/study.tscn"
   ],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/study_mode.py:89 control_schema",
    "yellowstone_python/yellowstone_python/study_mode.py:229 preset_errors",
    "yellowstone_python/yellowstone_python/study_mode.py:314 apply_preset"
   ],
   "method": "allow-listed config overrides (air temperature, discharge, shade/cloud, thermal source); writes two ecosystem.json variants",
   "validation": "none",
   "notes": "firehole_control.json / firehole_pulse.json are produced via study_mode runs or hot_lowflow tools and consumed by python_river_replay.gd; build.py does not call study_mode",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "study_mode_toggle",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "time_utils",
   "label": "Game-clock epoch parsing",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/atmosphere/time_utils.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/atmosphere/time_utils.py:18 parse_simulation_start",
    "yellowstone_python/yellowstone_python/atmosphere/time_utils.py:73 timestamp_metadata",
    "yellowstone_python/yellowstone_python/atmosphere/time_utils.py:93 epoch_unix_for_local"
   ],
   "method": "ISO date to local-offset epoch converter",
   "validation": "none",
   "notes": "",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "microclimate",
   "label": "microclimate (air, wind, humidity, condensation)",
   "domain": "atmosphere",
   "python": [
    "yellowstone_python/yellowstone_python/atmosphere/microclimate.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/ecosystem.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/atmosphere/microclimate.py:34 wet_bulb_c",
    "yellowstone_python/yellowstone_python/atmosphere/microclimate.py:55 weather_snapshot",
    "yellowstone_python/yellowstone_python/atmosphere/microclimate.py:139 fetch_real_weather"
   ],
   "method": "sinusoidal diurnal air curve lagging 15:00; mean + stochastic wind trace with seed; Magnus-Tetens dewpoint; measured Open-Meteo bundle (if present) overrides authored defaults",
   "validation": "fitted_not_validated",
   "notes": "Python curve lags noon by 3 h; Godot ecosystem.gd uses noon-peaking curve, residual documented at build.py:359",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "steam_plumes",
     "status": "rendered"
    },
    {
     "id": "sky_sun_time",
     "status": "rendered"
    },
    {
     "id": "clouds_precipitation",
     "status": "rendered"
    },
    {
     "id": "wind",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "met_forcing_fetcher",
   "label": "Open-Meteo met forcing fetcher",
   "domain": "atmosphere",
   "python": [
    "yellowstone_python/tools/fetch_met_forcing.py",
    "yellowstone_python/tools/fetch_firehole_obs.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/tools/fetch_met_forcing.py:10 main",
    "yellowstone_python/tools/fetch_firehole_obs.py:14 main"
   ],
   "method": "stdlib urllib Open-Meteo hourly bundle (shortwave, air, humidity, wind) frozen to derived/met.json",
   "validation": "none",
   "notes": "operator runs these fetchers; build.py loads whatever met.json exists",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "fetchers_calibration",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "surface_flux",
   "label": "Explicit surface energy budget",
   "domain": "atmosphere",
   "python": [
    "yellowstone_python/yellowstone_python/river/surface_flux.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/surface_flux.py:58 finite_flux",
    "yellowstone_python/yellowstone_python/river/surface_flux.py:95 es_kpa_wagner_pruss",
    "yellowstone_python/yellowstone_python/river/surface_flux.py:141 es_kpa"
   ],
   "method": "shortwave, longwave, sensible, latent (W/m2) with scaled turbulent coefficients, linearized implicitly",
   "validation": "illustrative",
   "notes": "selected when replay.energy_budget flag or explicit meteorology bundle; otherwise Newton lumped exchange is used",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "hydro_thermal_mixing",
   "label": "Analytical six-reach reference",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/river/reach_reference.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/reach_reference.py:50 derive_flows",
    "yellowstone_python/yellowstone_python/river/reach_reference.py:72 stable_dt",
    "yellowstone_python/yellowstone_python/river/reach_reference.py:82 mixing_check"
   ],
   "method": "fully mixed reach equations for independent analytical comparison",
   "validation": "illustrative",
   "notes": "benchmark reference; runtime reaches are flow-weighted summaries of finite-volume replay cells",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "river_heat",
     "status": "rendered"
    },
    {
     "id": "river_flow",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "replay_river_world",
   "label": "Mapped Firehole chain for the replay solver",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/river/river_world.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/python_river_replay.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/river_world.py:45 validate_duration_and_step",
    "yellowstone_python/yellowstone_python/river/river_world.py:65 validate_source_record",
    "yellowstone_python/yellowstone_python/river/river_world.py:84 validate_mapped_inputs"
   ],
   "method": "map saved Midway Firehole to cells with chainage and cross-sections; feed river_transport solver",
   "validation": "illustrative",
   "notes": "maps replay cells to the saved world geometry; publishes river_replay.json to the world and preserves the study control/pulse pair",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "river_heat",
     "status": "rendered"
    },
    {
     "id": "thermal_probe_overlay",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "replay_river_transport",
   "label": "Conservative finite-volume river transport",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/river/river_transport.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/python_river_replay.gd",
    "yellowstone_midway/scripts/thermal_probe_overlay.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/river_transport.py:38 series_dict",
    "yellowstone_python/yellowstone_python/river/river_transport.py:46 Series",
    "yellowstone_python/yellowstone_python/river/river_transport.py:101 Cell"
   ],
   "method": "finite-volume d(V T)/dt = Q(T_{i-1}-T_i) + D A (T_{i+1}-2T_i+T_{i-1})/dx + Phi_i with per-cell sources and Newton or explicit budget surface flux",
   "validation": "illustrative",
   "notes": "relative heat residual limit 1e-9 and relative water residual limit 1e-12; runtime and live river authority",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "river_heat",
     "status": "rendered"
    },
    {
     "id": "river_flow",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "replay_hydraulics",
   "label": "Trapezoidal channel hydraulics diagnostics",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/river/hydraulics.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/hydraulics.py:37 load_usgs_cross_section",
    "yellowstone_python/yellowstone_python/river/hydraulics.py:57 TrapezoidGeometry",
    "yellowstone_python/yellowstone_python/river/hydraulics.py:100 rectangular_area_m2"
   ],
   "method": "V = Q/A on trapezoidal cross-section, Manning consistency ratio, Froude, Fischer longitudinal dispersion, bed shear",
   "validation": "fitted_not_validated",
   "notes": "diagnostic only; river_transport solver remains rectangular. bed_shear_pa feeds foodweb shear_disturbance",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "replay_identifiability",
   "label": "Hydraulic identifiability diagnostics",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/river/identifiability.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/identifiability.py:53 residual_against_truth",
    "yellowstone_python/yellowstone_python/river/identifiability.py:59 jacobian_at_truth",
    "yellowstone_python/yellowstone_python/river/identifiability.py:76 conditioning"
   ],
   "method": "roughness, bank-slope, depth multi-start Manning-ratio cost; rank+max-cost reported",
   "validation": "fitted_not_validated",
   "notes": "records rank and surface-flux structural gap in CHECKS metrics",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "replay_benchmarks",
   "label": "Numerical benchmarks for the replay solver",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/river/benchmarks.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/benchmarks.py:42 benchmark_restart_equivalence",
    "yellowstone_python/yellowstone_python/river/benchmarks.py:87 benchmark_closed_thermal",
    "yellowstone_python/yellowstone_python/river/benchmarks.py:125 benchmark_two_stream_mixing"
   ],
   "method": "advection and dispersion benchmarks for the declared equation level (no momentum)",
   "validation": "illustrative",
   "notes": "",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "replay_calibrate",
   "label": "Reach-scale calibration and dispersion experiments",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/river/calibrate.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/calibrate.py:24 resample_bin_mean",
    "yellowstone_python/yellowstone_python/river/calibrate.py:65 interp_series",
    "yellowstone_python/yellowstone_python/river/calibrate.py:89 check_continuity"
   ],
   "method": "fit Newton h, dispersion, surface budget params against Firehole obs bundle",
   "validation": "fitted_not_validated",
   "notes": "operator-run (reach_heat_fit_v300k.json evidence artifact); not part of build",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "replay_uncertainty",
   "label": "Reach fit uncertainty quantification",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/river/uncertainty.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/uncertainty.py:26 uq_provenance",
    "yellowstone_python/yellowstone_python/river/uncertainty.py:65 ridge_members",
    "yellowstone_python/yellowstone_python/river/uncertainty.py:113 fit_masks"
   ],
   "method": "lumped-fit UQ + authored-knob sensitivity",
   "validation": "fitted_not_validated",
   "notes": "standalone CLI; evidence artifact reach_ensemble_uq_v300k.json",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "replay_fipy_reference",
   "label": "FiPy steady 1-D advection + Newton reference",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/river/fipy_reference.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/fipy_reference.py:52 decay_per_m",
    "yellowstone_python/yellowstone_python/river/fipy_reference.py:57 loss_per_s",
    "yellowstone_python/yellowstone_python/river/fipy_reference.py:62 analytic_temperature_c"
   ],
   "method": "FiPy reference compared against analytic profile",
   "validation": "illustrative",
   "notes": "optional dependency gated by importlib.util",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "replay_figures",
   "label": "Diagnostic replay figures",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/river/figures.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/figures.py:63 fit_holdout_figure",
    "yellowstone_python/yellowstone_python/river/figures.py:102 bands_figure",
    "yellowstone_python/yellowstone_python/river/figures.py:128 residual_figure"
   ],
   "method": "matplotlib Agg figures from frozen artifacts",
   "validation": "none",
   "notes": "",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "replay_obs_frame",
   "label": "Pandas obs-frame alignment for fits",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/river/obs_frame.py",
    "yellowstone_python/yellowstone_python/river/obs_model.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/obs_frame.py:53 met_frame",
    "yellowstone_python/yellowstone_python/river/obs_frame.py:84 gap_report",
    "yellowstone_python/yellowstone_python/river/obs_frame.py:116 assert_coverable",
    "yellowstone_python/yellowstone_python/river/obs_model.py:58 stage_to_elevation_ft_navd88",
    "yellowstone_python/yellowstone_python/river/obs_model.py:71 interval_average",
    "yellowstone_python/yellowstone_python/river/obs_model.py:107 compare"
   ],
   "method": "DatetimeIndex resample-mean alignment; H(x) measurement operator over station chainage",
   "validation": "none",
   "notes": "used by calibrate/uncertainty",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "replay_datasets",
   "label": "Reference dataset split roles",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/river/datasets.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/datasets.py:71 window_errors",
    "yellowstone_python/yellowstone_python/river/datasets.py:119 role_errors"
   ],
   "method": "calibration/development/locked-final split assignment",
   "validation": "none",
   "notes": "declarative metadata",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "replay_nc_export",
   "label": "CF-style NetCDF export",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/river/nc_export.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/nc_export.py:27 write_replay_netcdf",
    "yellowstone_python/yellowstone_python/river/nc_export.py:82 read_replay_netcdf"
   ],
   "method": "CF export of temperature frames",
   "validation": "none",
   "notes": "standalone utility",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "replay_plume2d",
   "label": "Steady 2-D thermal plume (Excelsior mixing zone)",
   "domain": "hydrothermal",
   "python": [
    "yellowstone_python/yellowstone_python/river/plume2d.py",
    "yellowstone_python/yellowstone_python/river/reach_reference.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/world.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/plume2d.py:36 solve_steady",
    "yellowstone_python/yellowstone_python/river/plume2d.py:168 centerline",
    "yellowstone_python/yellowstone_python/river/plume2d.py:179 plume_metrics",
    "yellowstone_python/yellowstone_python/river/reach_reference.py:50 derive_flows",
    "yellowstone_python/yellowstone_python/river/reach_reference.py:72 stable_dt",
    "yellowstone_python/yellowstone_python/river/reach_reference.py:82 mixing_check"
   ],
   "method": "u dT/dz = Dx d2T/dx2 + Dz d2T/dz2 - k(T-ambient) on 128x128 implicit upwind/centered grid",
   "validation": "illustrative",
   "notes": "plume_field.json drawn as a world-space temperature quad with legend",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "plume_field_summary",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "overland_flow",
   "label": "overland flow (rainfall/infiltration/runoff)",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/land/overland_flow.py",
    "hydrology/hydrosim.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/world.gd"
   ],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/land/overland_flow.py:155 run_overland",
    "hydrology/hydrosim.py:30 marshall_palmer",
    "hydrology/hydrosim.py:36 sample_drop_diameters",
    "hydrology/hydrosim.py:48 terminal_velocity"
   ],
   "method": "wraps hydrology/hydrosim.py local-inertial shallow-water solver (Bates et al. 2010) with Green-Ampt infiltration on block-mean terrain.f32; rain source is overland.rain_mm_h, then met_bundle precipitation_mm, then snow.precip_mm_d",
   "validation": "illustrative",
   "notes": "outlet runoff now reaches the river boundary; Godot shows a scene-wide tint from a scalar only, no per-cell field yet",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "groundwater_overland",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "hydrosim_prototype",
   "label": "Standalone shallow-water + soil model",
   "domain": "hydrology",
   "python": [
    "hydrology/hydrosim.py",
    "hydrology/demo_hydrosim.py",
    "hydrology/validate_hydrosim.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "hydrology/hydrosim.py:30 marshall_palmer",
    "hydrology/hydrosim.py:36 sample_drop_diameters",
    "hydrology/hydrosim.py:48 terminal_velocity",
    "hydrology/demo_hydrosim.py:18 slider",
    "hydrology/demo_hydrosim.py:28 main",
    "hydrology/validate_hydrosim.py:14 check",
    "hydrology/validate_hydrosim.py:19 ga_reference",
    "hydrology/validate_hydrosim.py:31 column"
   ],
   "method": "Green-Ampt / Horton infiltration, local-inertial Bates shallow-water, Brooks-Corey drainage, FAO-56 ET, linear-reservoir groundwater",
   "validation": "validated",
   "notes": "self-validated against analytic + Newton bisection in validate_hydrosim.py; integrated into build only through overland_flow.run_overland; the Godot 3 plugin wrapper godot_hydro_node.py was removed (fixes-31 F9)",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "hydrology_provider",
   "label": "Cached hydrology service wrapper around hydrosim",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/land/hydrology_provider.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/land/hydrology_provider.py:18 HydrologySnapshot",
    "yellowstone_python/yellowstone_python/land/hydrology_provider.py:35 HydrologyProvider"
   ],
   "method": "snapshot(weather, hour) wrapper over hydrosim; returns ground_wetness_fraction and a status string; refuse_on_cfl_overflow=True yields status=refused_cfl_exceeded when hydrosim exceeds its CFL",
   "validation": "none",
   "notes": "surfaced only through llm_backend HTTP server; the overland-runoff authority remains overland_flow in the build",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "overland_provider",
   "label": "Synthetic-catchment runoff discharge series",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/land/overland_provider.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/land/overland_provider.py:30 route_linear_reservoir",
    "yellowstone_python/yellowstone_python/land/overland_provider.py:66 synthetic_elevation",
    "yellowstone_python/yellowstone_python/land/overland_provider.py:83 predict_discharge"
   ],
   "method": "synthetic elevation + Green-Ampt predicts discharge series; optional landlab path",
   "validation": "illustrative",
   "notes": "claim upstream_discharge_predicted (not_yet_accepted); not called by build/publish",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "groundwater_provider",
   "label": "Synthetic MODFLOW RIV laterals",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/land/groundwater_provider.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/land/groundwater_provider.py:33 authored_reaches_to_sources",
    "yellowstone_python/yellowstone_python/land/groundwater_provider.py:84 with_chainage",
    "yellowstone_python/yellowstone_python/land/groundwater_provider.py:145 head_gradient_exchange"
   ],
   "method": "flopy-driven synthetic MF6 model; maps RIV package to replay Source dicts with lateral discharge + temperature",
   "validation": "illustrative",
   "notes": "claim groundwater_lateral_heat (not_yet_accepted); not called by build/publish",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "groundwater_overland",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "pool_crust",
   "label": "hydrothermal pool shells, rims, aprons",
   "domain": "hydrothermal",
   "python": [
    "yellowstone_python/yellowstone_python/thermal_features/pool_crust.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/pool_overlay.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/thermal_features/pool_crust.py:61 make_ramp_stops",
    "yellowstone_python/yellowstone_python/thermal_features/pool_crust.py:82 validate_ramp_stops",
    "yellowstone_python/yellowstone_python/thermal_features/pool_crust.py:94 render_ramp"
   ],
   "method": "radial T(r)=T_edge+(T_c-T_edge)(1-(r/rw)^2); color ramp per RECIPE; apron buffered ring; exclusion test used by vegetation and grazer planners",
   "validation": "illustrative",
   "notes": "pool_shells.json and pool_ramps/*.png are shipped by publish.py",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "pools_surface",
     "status": "rendered"
    },
    {
     "id": "pool_aprons_pigment",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "geochemistry",
   "label": "geochemistry / substrate rules / silica",
   "domain": "hydrothermal",
   "python": [
    "yellowstone_python/yellowstone_python/thermal_features/geochemistry.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/world.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/thermal_features/geochemistry.py:46 SubstrateError",
    "yellowstone_python/yellowstone_python/thermal_features/geochemistry.py:61 system_for_feature",
    "yellowstone_python/yellowstone_python/thermal_features/geochemistry.py:69 check_midway_shells"
   ],
   "method": "siliceous Midway vs travertine Mammoth palette gate; silica solubility T-polynomials (quartz, chalcedony, amorphous) and saturation index per cell from the last replay frame",
   "validation": "literature",
   "notes": "silica saturation markers along the Firehole; geochemistry.json now carries chainage_m, x_m, z_m, overlay still spaces markers along the mainline",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "pool_aprons_pigment",
     "status": "rendered"
    },
    {
     "id": "geochemistry_bands",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "snow_season",
   "label": "snowpack, soil water, phenology",
   "domain": "cryosphere",
   "python": [
    "yellowstone_python/yellowstone_python/land/snow_season.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/world.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/land/snow_season.py:15 degree_days",
    "yellowstone_python/yellowstone_python/land/snow_season.py:19 date_to_season",
    "yellowstone_python/yellowstone_python/land/snow_season.py:39 game_clock_now"
   ],
   "method": "degree-day melt = k_melt max(0, T-tbase) + thermal ground flux; soil bucket with ET and drainage; phenology stage from GDD and moisture",
   "validation": "fitted_not_validated",
   "notes": "produces snow_runoff_m3_s as a discharge increment added to boundary_m3s; geometry frozen so renderer applies snow via shader mask",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "snow_cover",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "snow_energy",
   "label": "Energy-balance snowmelt vs SNOTEL",
   "domain": "cryosphere",
   "python": [
    "yellowstone_python/yellowstone_python/land/snow_energy.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/land/snow_energy.py:40 clear_sky_toa_w_m2",
    "yellowstone_python/yellowstone_python/land/snow_energy.py:60 cloud_factor",
    "yellowstone_python/yellowstone_python/land/snow_energy.py:66 day_of_year"
   ],
   "method": "SW_down = S_RAD * TOA(doi,lat) * cloud(dtr); melt = (1-albedo)*SW + C0 + C_T*TAVG",
   "validation": "fitted_not_validated",
   "notes": "replaces degree-day with energy budget; standalone validator against SNOTEL",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "snow_validate",
   "label": "SNOTEL validation of snow and soil water model",
   "domain": "cryosphere",
   "python": [
    "yellowstone_python/yellowstone_python/land/snow_validate.py",
    "yellowstone_python/tools/fetch_snotel_obs.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/land/snow_validate.py:46 f_to_c",
    "yellowstone_python/yellowstone_python/land/snow_validate.py:50 in_to_mm",
    "yellowstone_python/yellowstone_python/land/snow_validate.py:54 prepare_forcing",
    "yellowstone_python/tools/fetch_snotel_obs.py:12 main"
   ],
   "method": "train/holdout split on SNOTEL WTEQ/PRCP/TAVG; k_melt grid fit; RMSE/bias/peak-timing against persistence and no-melt nulls",
   "validation": "validated",
   "notes": "claim snow_swe_clearings evidence; standalone operator CLI",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "vegetation",
   "label": "patch biomass, suitability, plantings",
   "domain": "terrestrial_ecology",
   "python": [
    "yellowstone_python/yellowstone_python/land/vegetation.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/ecosystem.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/land/vegetation.py:76 suitability",
    "yellowstone_python/yellowstone_python/land/vegetation.py:90 guild_suitability",
    "yellowstone_python/yellowstone_python/land/vegetation.py:111 sunlight"
   ],
   "method": "logistic biomass with light/water factors and grazing loss; proposals pass thermal exclusion, slope, suitability, pair-separation gates",
   "validation": "illustrative",
   "notes": "patch_state.json sidecar is diagnostic; the live patches reach Godot via ecosystem.variant.patches",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "canopy_census",
   "label": "Canopy census tree detector",
   "domain": "terrestrial_ecology",
   "python": [
    "yellowstone_python/yellowstone_python/census/canopy_census.py",
    "yellowstone_python/yellowstone_python/census/census_validate.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/world.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/census/canopy_census.py:20 load_detail",
    "yellowstone_python/yellowstone_python/census/canopy_census.py:26 crown_mask",
    "yellowstone_python/yellowstone_python/census/canopy_census.py:34 vegetation_signals",
    "yellowstone_python/yellowstone_python/census/census_validate.py:35 cmd_freeze",
    "yellowstone_python/yellowstone_python/census/census_validate.py:81 cmd_sample",
    "yellowstone_python/yellowstone_python/census/census_validate.py:253 cmd_annotate_web"
   ],
   "method": "NAIP tree detection with QA self-check; blind SRS plot validation with Hungarian matching; crown-area canopy fraction fed to the planting-proposal reviewer",
   "validation": "validated",
   "notes": "census crowns drawn on the map view; canopy also drives vegetation suitability",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "trees_pine",
     "status": "rendered"
    },
    {
     "id": "census_overlay",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "gen_flora",
   "label": "Flora density generator and machine-review",
   "domain": "terrestrial_ecology",
   "python": [
    "yellowstone_python/yellowstone_python/authoring/gen_flora.py",
    "yellowstone_python/yellowstone_python/authoring/review_proposals.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/authoring/gen_flora.py:50 green_light_at",
    "yellowstone_python/yellowstone_python/authoring/gen_flora.py:69 PlacementConstraints",
    "yellowstone_python/yellowstone_python/authoring/gen_flora.py:117 shuffled_cells",
    "yellowstone_python/yellowstone_python/authoring/review_proposals.py:24 review",
    "yellowstone_python/yellowstone_python/authoring/review_proposals.py:145 to_override_record",
    "yellowstone_python/yellowstone_python/authoring/review_proposals.py:173 main"
   ],
   "method": "regional seeded point sets passed through review (slope, thermal exclusion, suitability, pairwise separation)",
   "validation": "illustrative",
   "notes": "writes placement_overrides.json manually; not called by build",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "trees_pine",
     "status": "rendered"
    },
    {
     "id": "grass_logs_rocks",
     "status": "rendered"
    },
    {
     "id": "botanical_details",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "gen_trail_mask",
   "label": "Foot trail mask bake",
   "domain": "terrestrial_ecology",
   "python": [
    "yellowstone_python/yellowstone_python/authoring/gen_trail_mask.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/authoring/gen_trail_mask.py:64 build_mask",
    "yellowstone_python/yellowstone_python/authoring/gen_trail_mask.py:110 main"
   ],
   "method": "paint trail polylines into a 2048x2048 world-extent mask with core + soft shoulder for the terrain shader",
   "validation": "none",
   "notes": "operator bake, consumed by Godot terrain shader; not called by build.py",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "insects_birds",
   "label": "insect activity, compartments, bird intake",
   "domain": "aquatic_ecology",
   "python": [
    "yellowstone_python/yellowstone_python/insects_birds.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/ecosystem.gd",
    "yellowstone_midway/scripts/wildlife_actor.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/insects_birds.py:21 sunlight",
    "yellowstone_python/yellowstone_python/insects_birds.py:30 wind_factor",
    "yellowstone_python/yellowstone_python/insects_birds.py:36 flowering_factor"
   ],
   "method": "activity = sun*wind*cloud*moisture*flowering gates; Holling type II prey intake; compartments Nt (terrestrial), Nb (benthic), Ne (emergent) with degree-day emergence",
   "validation": "illustrative",
   "notes": "activity is published via ecosystem.variant.patches[].insect_activity and wildlife durations",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "birds_goose_dipper_raven",
     "status": "rendered"
    },
    {
     "id": "insects",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "fish",
   "label": "trout suitability, refuge, chainage placement",
   "domain": "aquatic_ecology",
   "python": [
    "yellowstone_python/yellowstone_python/aquatic/fish.py",
    "yellowstone_python/yellowstone_python/aquatic/thermal_curves.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/wildlife_actor.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/aquatic/fish.py:151 species_is_default_on",
    "yellowstone_python/yellowstone_python/aquatic/fish.py:165 load_lab_thermal",
    "yellowstone_python/yellowstone_python/aquatic/fish.py:177 thermal_data_status",
    "yellowstone_python/yellowstone_python/aquatic/thermal_curves.py:278 growth",
    "yellowstone_python/yellowstone_python/aquatic/thermal_curves.py:283 feeding",
    "yellowstone_python/yellowstone_python/aquatic/thermal_curves.py:288 survival"
   ],
   "method": "suitability-weighted score Ui = wf Fi + wc Ci - wt phi(Ti) - wv Vi - wd Di; refuge chosen as argmax within swim range; chainage-window hold placement",
   "validation": "illustrative",
   "notes": "trout wildlife records merged into ecosystem.variant; fish.json sidecar + refuge_map.png are diagnostic (not published)",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "fish",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "thermal_curves",
   "label": "Trout thermal response fits",
   "domain": "aquatic_ecology",
   "python": [
    "yellowstone_python/yellowstone_python/aquatic/thermal_curves.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/aquatic/thermal_curves.py:278 growth",
    "yellowstone_python/yellowstone_python/aquatic/thermal_curves.py:283 feeding",
    "yellowstone_python/yellowstone_python/aquatic/thermal_curves.py:288 survival"
   ],
   "method": "species-specific split-Gaussian / logistic curves fitted via scipy least_squares to literature anchors",
   "validation": "literature",
   "notes": "aquatic/fish.py uses THERMAL_SPECIES lookup; thermal_curves fits are standalone",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "aquatic_foodweb",
   "label": "14-day insect/trout/dipper food web on replay thermal landscape",
   "domain": "aquatic_ecology",
   "python": [
    "yellowstone_python/yellowstone_python/aquatic/aquatic_foodweb.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/wildlife_actor.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/aquatic/aquatic_foodweb.py:136 taxon_step",
    "yellowstone_python/yellowstone_python/aquatic/aquatic_foodweb.py:218 run_taxon_foodweb",
    "yellowstone_python/yellowstone_python/aquatic/aquatic_foodweb.py:354 unwrap_replay"
   ],
   "method": "time-mean thermal landscape -> per-cell suitability + Holling II prey splits among trout and dipper, with benthic degree-day emergence; bed-shear ramp disturbs benthic stock",
   "validation": "illustrative",
   "notes": "aquatic_foodweb.json sidecar not read by Godot; refuge chainage and dipper intake flow into wildlife records in ecosystem.variant",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "fish",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "grazers",
   "label": "grazer plan-paths and route validation",
   "domain": "terrestrial_ecology",
   "python": [
    "yellowstone_python/yellowstone_python/land/grazers.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/wildlife_actor.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/land/grazers.py:26 model_context",
    "yellowstone_python/yellowstone_python/land/grazers.py:61 route_length",
    "yellowstone_python/yellowstone_python/land/grazers.py:66 segment_samples"
   ],
   "method": "Euclidean-heuristic shortest path with per-cell block tests; grazing timings from biomass vs capacity",
   "validation": "illustrative",
   "notes": "grazer.json sidecar not read by Godot; wildlife path_xz travels through ecosystem.variant",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "ungulates_bison_elk",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "compare",
   "label": "A/B scenario endpoint comparison",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/compare.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/compare.py:371 compare_builds",
    "yellowstone_python/yellowstone_python/compare.py:526 main"
   ],
   "method": "reads two derived/<build-id> dirs and reports deltas (temperatures, flows, trout holds, insect activity, snow, phenology, heat budget)",
   "validation": "none",
   "notes": "endpoint deltas only; exposure-duration metrics flagged for later phase",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "study_mode_toggle",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "runner_hot_lowflow",
   "label": "Hot low-flow scenarios",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/scenarios/hot_lowflow.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/python_river_replay.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/scenarios/hot_lowflow.py:189 summarize",
    "yellowstone_python/yellowstone_python/scenarios/hot_lowflow.py:219 run_case",
    "yellowstone_python/yellowstone_python/scenarios/hot_lowflow.py:248 run_mainstem"
   ],
   "method": "mainstem, authored tributary pockets, or measured tributaries using a shared replay setup; measured inputs are required for the measured subcommand",
   "validation": "illustrative",
   "notes": "preserves solver cell ids; scenario outputs declare forcing and evidence classes",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "runner_fetch_firehole",
   "label": "Firehole obs bundle fetcher",
   "domain": "observation",
   "python": [
    "yellowstone_python/tools/fetch_firehole_obs.py",
    "yellowstone_python/tools/usgs_nwis.py",
    "yellowstone_python/tools/fetch_yellowstone_tributaries.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/tools/fetch_firehole_obs.py:14 main",
    "yellowstone_python/tools/usgs_nwis.py:18 main",
    "yellowstone_python/tools/fetch_yellowstone_tributaries.py:12 main"
   ],
   "method": "stdlib urllib fetch of USGS Water Services + Open-Meteo for Firehole gauges and tributary candidates; writes frozen bundles for the calibrate/validate paths",
   "validation": "none",
   "notes": "evidence for claim reach_water_temperature_ice_free",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "runner_fetch_snotel",
   "label": "SNOTEL obs bundle fetcher",
   "domain": "observation",
   "python": [
    "yellowstone_python/tools/fetch_snotel_obs.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/tools/fetch_snotel_obs.py:12 main"
   ],
   "method": "fetch daily WTEQ, PRCP, SNWD, TAVG/TMAX/TMIN for configured SNOTEL sites",
   "validation": "none",
   "notes": "feeds land/snow_validate.py",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "runner_validate_obs",
   "label": "Observation bundle gate",
   "domain": "observation",
   "python": [
    "yellowstone_python/tools/validate_obs_bundles.py",
    "yellowstone_python/tools/compare_bundles.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/tools/validate_obs_bundles.py:191 gate_bundle",
    "yellowstone_python/tools/validate_obs_bundles.py:225 main",
    "yellowstone_python/tools/compare_bundles.py:70 compare_bundles",
    "yellowstone_python/tools/compare_bundles.py:186 main"
   ],
   "method": "schema/continuity/coverage checks and old-vs-refetch drift detection",
   "validation": "none",
   "notes": "",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "runner_channel_geometry",
   "label": "Channel cross-section geometry derivation",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/tools/channel_geometry.py",
    "yellowstone_python/tools/check_terrain.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/tools/channel_geometry.py:189 analyze",
    "yellowstone_python/tools/channel_geometry.py:231 main",
    "yellowstone_python/tools/check_terrain.py:12 main"
   ],
   "method": "USGS NWIS field measurements + 3DEP DEM used to build trapezoidal cross-section profiles consumed by replay.hydraulics",
   "validation": "none",
   "notes": "",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "runner_audit_provenance",
   "label": "Provenance audit over derived/",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/tools/audit_provenance.py",
    "yellowstone_python/tools/plot_fit.py",
    "yellowstone_python/tools/execute_notebook.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/tools/audit_provenance.py:56 audit_file",
    "yellowstone_python/tools/audit_provenance.py:212 audit_dir",
    "yellowstone_python/tools/audit_provenance.py:243 main",
    "yellowstone_python/tools/plot_fit.py:19 new_canvas",
    "yellowstone_python/tools/plot_fit.py:31 bar_groups",
    "yellowstone_python/tools/plot_fit.py:73 fig_reach_heat",
    "yellowstone_python/tools/execute_notebook.py:9 execute",
    "yellowstone_python/tools/execute_notebook.py:37 main"
   ],
   "method": "mechanical check of status strings against measured vocabulary; Pillow-only diagnostic PNGs; stdlib notebook smoke executor",
   "validation": "none",
   "notes": "",
   "source_inventory": "python",
   "kind": "component"
  },
  {
   "id": "calibration_summary",
   "label": "Calibration summary sidecar for Godot",
   "domain": "observation",
   "python": [
    "yellowstone_python/yellowstone_python/exporters/godot_sidecars.py",
    "yellowstone_python/tools/calibrate_river_transport.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/world.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/exporters/godot_sidecars.py:72 MissingSourceError",
    "yellowstone_python/yellowstone_python/exporters/godot_sidecars.py:94 write_plume_field_json",
    "yellowstone_python/yellowstone_python/exporters/godot_sidecars.py:153 write_geochemistry_json",
    "yellowstone_python/tools/calibrate_river_transport.py:154 observation_hierarchy_report",
    "yellowstone_python/tools/calibrate_river_transport.py:184 StageAResult",
    "yellowstone_python/tools/calibrate_river_transport.py:197 stage_a_hydraulics"
   ],
   "method": "pack the champion reach-heat fit scalars (q_lat, t_lat, c_mult, train/holdout rmse and bias, budget_ok) with the first gauge site's discharge-temperature trace",
   "validation": "fitted_not_validated",
   "notes": "reach fit and gauge trace drawn in the calibration panel",
   "source_inventory": "python",
   "kind": "component",
   "rendered_by": [
    {
     "id": "fetchers_calibration",
     "status": "rendered"
    }
   ]
  },
  {
   "id": "star_catalog_vendor",
   "label": "Vendored star catalog (RA, Dec, mag, B-V)",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "rendered",
   "evidence": [
    "yellowstone_midway/references/bsc5_catalog.gz.provenance.json (syn 2026-10-13 after fixes pass 2: published build 71c8f00455af, main and study scenes 0 script errors; visual acceptance NOT TESTED)",
    "yellowstone_python_spec/fixes/fixes-14.md:188-203 (Star data vendor + convert to res://data/stars.bin)",
    "rg star_catalog|starcatalog|stars.bin|catalog.json over repo returns no code hits outside fixes-14.md"
   ],
   "method": "Vendor Long-Night-style catalog once; convert to compact project asset.",
   "validation": "none",
   "notes": "BSC5 (CDS V/50) vendored with provenance; tools/convert_star_catalog.py writes data/stars.json, 9096 stars",
   "source": "yellowstone_python_spec/fixes/fixes-14.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "sidereal_star_renderer",
   "label": "Local sidereal-time star positioning + MultiMesh renderer",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "rendered",
   "evidence": [
    "yellowstone_atmosphere.gd _load_star_catalog (syn 2026-10-13 after fixes pass 2: published build 71c8f00455af, main and study scenes 0 script errors; visual acceptance NOT TESTED)",
    "yellowstone_python_spec/fixes/fixes-14.md:205-269 (RA/Dec->alt/az transform, Compatibility MultiMesh + magnitude/B-V)",
    "rg sidereal|hour.angle|horizontal_to_world over repo returns no code hits"
   ],
   "method": "H=LST-RA; sin(alt)=sin(dec)sin(lat)+cos(dec)cos(lat)cos(H); world dir on +X east/+Y up/+Z south.",
   "validation": "none",
   "notes": "RA/Dec through local sidereal time, magnitude flux and B-V color from data/stars.json",
   "source": "yellowstone_python_spec/fixes/fixes-14.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "milky_way_flux_layer",
   "label": "Milky Way unresolved-flux background",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "fixes-14 ledger item 6 (syn 2026-10-13 after fixes pass 2: published build 71c8f00455af, main and study scenes 0 script errors; visual acceptance NOT TESTED)",
    "yellowstone_python_spec/fixes/fixes-14.md:347-361 (galactic-coord population aggregated to equirectangular grid)",
    "rg milky.?way over repo returns only fixes-14.md and improvements.md"
   ],
   "method": "Offline galactic-coord sampling + aggregate unresolved flux into 512x256 equirectangular or 6-face cubemap.",
   "validation": "none",
   "notes": "unresolved-flux grid wired; awaits visual verification with the catalog",
   "source": "yellowstone_python_spec/fixes/fixes-14.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "moffat_point_spread",
   "label": "Moffat star PSF + bright-star diffraction spikes",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "fixes-14 ledger item 5 (syn 2026-10-13 after fixes pass 2: published build 71c8f00455af, main and study scenes 0 script errors; visual acceptance NOT TESTED)",
    "yellowstone_python_spec/fixes/fixes-14.md:333-341 (Moffat profile glsl snippet)"
   ],
   "method": "pow(1+r^2/a^2,-b) PSF; magnitude-gated diffraction spikes.",
   "validation": "none",
   "notes": "reduced to a 4-neighbor wing; full Moffat kernel pending",
   "source": "yellowstone_python_spec/fixes/fixes-14.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "dust_extinction_reddening",
   "label": "Galactic-plane dust extinction and reddening",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/fixes/fixes-14.md:359-360 (dust extinction near galactic plane in longitude bands)",
    "yellowstone_python_spec/fixes/fixes-14.md:1064 (Phase 3 item: Add dust extinction and reddening)"
   ],
   "method": "Reduce flux near galactic plane in selected longitude bands.",
   "validation": "none",
   "notes": "Phase 3.",
   "source": "yellowstone_python_spec/fixes/fixes-14.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "horizon_occlusion",
   "label": "Terrain/horizon occlusion for celestial objects",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/fixes/fixes-14.md:8 (terrain occludes objects below the horizon)",
    "yellowstone_python_spec/fixes/fixes-14.md:1066 (Phase 3: Add terrain/horizon occlusion)"
   ],
   "method": "Depth or ray-against-heightfield test for stars/planets/Moon.",
   "validation": "none",
   "source": "yellowstone_python_spec/fixes/fixes-14.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "moon_ephemeris",
   "label": "Moon position via skyfield/astropy ephemerides",
   "domain": "atmosphere",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/fixes/fixes-14.md:150-157 (skyfield/astropy for Moon and planets)",
    "yellowstone_python_spec/fixes/fixes-14.md:1061 (Phase 2 item: Add Moon and planet positions with skyfield or astropy)"
   ],
   "method": "Compute RA/Dec from ephemeris; convert to alt/az at simulation UTC+site.",
   "validation": "none",
   "source": "yellowstone_python_spec/fixes/fixes-14.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "planet_ephemeris",
   "label": "Planet positions via skyfield/astropy",
   "domain": "atmosphere",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/fixes/fixes-14.md:6 (planets and the Moon computed separately)",
    "yellowstone_python_spec/fixes/fixes-14.md:1061"
   ],
   "method": "Shared ephemeris pipeline with Moon; separate rendering treatment.",
   "validation": "none",
   "source": "yellowstone_python_spec/fixes/fixes-14.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "pvlib_authoritative_solar",
   "label": "pvlib authoritative solar geometry in Python snapshot",
   "domain": "atmosphere",
   "python": [
    "yellowstone_python/yellowstone_python/atmosphere/microclimate.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/weather_snapshot_reader.gd",
    "yellowstone_midway/scripts/yellowstone_atmosphere.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/atmosphere/microclimate.py:55 weather_snapshot",
    "yellowstone_python/yellowstone_python/atmosphere/microclimate.py:500 solar_snapshot"
   ],
   "method": "Shared Python weather snapshot uses the simulation epoch, common Midway site and pvlib solar geometry; Godot consumes the model snapshot.",
   "validation": "weather_snapshot_tests",
   "notes": "The current project environment includes pvlib. Unavailable solar is still labeled if that dependency is absent.",
   "source": "yellowstone_python_spec/fixes/fixes-14.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "weather_snapshot_schema_v2",
   "label": "Unified schema_version 2 weather snapshot",
   "domain": "atmosphere",
   "python": [
    "yellowstone_python/yellowstone_python/service/llm_backend.py"
   ],
   "godot": [
    "yellowstone_atmosphere/scripts/weather_snapshot_reader.gd",
    "yellowstone_atmosphere/scripts/weather_http_consumer.gd",
    "yellowstone_midway/scripts/weather_http_consumer.gd"
   ],
   "status": "rendered",
   "evidence": [
    "godot_sidecars.write_weather_snapshot_json; weather_snapshot_reader.gd (syn 2026-10-13 after fixes pass 2: published build 71c8f00455af, main and study scenes 0 script errors; visual acceptance NOT TESTED)",
    "yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:10 (const SUPPORTED_SCHEMA_VERSION: int = 1)",
    "yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:230 (if int(schema_value) != SUPPORTED_SCHEMA_VERSION fails)",
    "yellowstone_midway/scripts/weather_http_consumer.gd:9 (const SCHEMA_VERSION: int = 1)",
    "yellowstone_python/yellowstone_python/service/llm_backend.py:279 (Return a schema_version 1 nested weather snapshot for the Godot HTTP consumer)",
    "yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:179-192 (solar nested block now accepted alongside weather) and reader-consumer parity on nested shape"
   ],
   "method": "Normalize provider adapters to {schema_version:2, generated_at_unix, valid_time_unix, simulation_time_unix, source, weather, solar, terrain}.",
   "validation": "none",
   "notes": "schema 2 produced by godot_sidecars and accepted by the reader and HTTP consumer",
   "source": "yellowstone_python_spec/fixes/fixes-14.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "weather_http_consumer",
   "label": "HTTP weather consumer with anti-overlap + endpoint provenance",
   "domain": "atmosphere",
   "python": [],
   "godot": [
    "yellowstone_midway/scripts/weather_http_consumer.gd",
    "yellowstone_atmosphere/scripts/weather_http_consumer.gd"
   ],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_midway/scripts/weather_http_consumer.gd:1-2 (class_name YellowstoneWeatherHttpConsumer extends Node)",
    "yellowstone_midway/scripts/weather_http_consumer.gd:9 (const SCHEMA_VERSION: int = 1)",
    "yellowstone_midway/scripts/weather_http_consumer.gd:232-238 (generated_at_unix provenance from server; generated_at_unix recorded on normalized snapshot)",
    "yellowstone_midway/scripts/weather_http_consumer.gd:413-417 (flat endpoint solar fields nested into solar block)",
    "yellowstone_atmosphere/scripts/weather_http_consumer.gd:1-2 (same class in the add-on directory)",
    "yellowstone_midway/scripts/weather_snapshot_reader.gd:47 (snapshot_path = \"user://weather/latest.json\"); rg --no-ignore for latest.json/weather_http_consumer over yellowstone_python and yellowstone_midway scenes finds no writer and no instantiation (syn spot-check 2026-10-13)"
   ],
   "method": "Request-in-flight guard, provider-reported generated_at_unix, nested schema parity with file reader.",
   "validation": "none",
   "notes": "Script is installed in yellowstone_midway/scripts but nothing instantiates it; world.gd uses the file reader instead.",
   "source": "yellowstone_python_spec/fixes/fixes-14.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "replay_live_bridge",
   "label": "Python live HTTP service and published-data watcher",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/service/live/engine.py",
    "yellowstone_python/yellowstone_python/service/server.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/live_python_client.gd",
    "yellowstone_midway/scripts/data_watcher.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_midway/scripts/world.gd:224 setup_python_runtime",
    "yellowstone_midway/scripts/world.gd:257 _published_changed"
   ],
   "method": "HTTP schema, control and buffered model frames; content-signature watcher reloads local published files.",
   "validation": "local_runtime_tests",
   "notes": "Actual Python service, unavailable-service baked mode, and sub-second watcher reload verified. Human visual acceptance remains pending.",
   "source": "yellowstone_python_spec/01_PYTHON_BUILD_SPEC.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "species_gen_package",
   "label": "yellowstone_species_gen Python package (registry, distributions, growth, color, pattern, individual, generate, validate)",
   "domain": "terrestrial_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_species_gen/00_RESEARCH_SPEC.md:163-181 (full generator program design)",
    "yellowstone_species_gen/ directory contains only 00_RESEARCH_SPEC.md and data/*.json; no ysg/ package directory"
   ],
   "method": "Sample order sex->age->growth(size)->proportions->morph loci->condition axes->pattern->seasonal overlay->jitter; truncnorm/lognormal/beta/dirichlet; von Bertalanffy and Gompertz growth.",
   "validation": "none",
   "notes": "Trait-library data (8 kingdom JSONs) exists but no sampler/CLI.",
   "source": "yellowstone_species_gen/00_RESEARCH_SPEC.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "species_gen_cli",
   "label": "ysg generate --species X --n N --day D --seed S CLI",
   "domain": "terrestrial_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_species_gen/00_RESEARCH_SPEC.md:174-181 (CLI contract and per-individual record output)",
    "rg 'yellowstone_species_gen|ysg\\.|from ysg' yellowstone_python/ returns no hits"
   ],
   "method": "Deterministic-per-seed individual records consumable by wildlife_actor-style builders or glTF morph-target applier.",
   "validation": "none",
   "source": "yellowstone_species_gen/00_RESEARCH_SPEC.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "species_gen_distribution_validator",
   "label": "Distribution test harness (moments, KS, Dirichlet freq chi^2)",
   "domain": "terrestrial_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_species_gen/00_RESEARCH_SPEC.md:177-178 (validate.py: N=10k samples/species, moments vs source ranges, KS, morph freq chi^2)"
   ],
   "method": "Monte Carlo check of sampled individuals vs documented ranges and morph frequencies.",
   "validation": "none",
   "source": "yellowstone_species_gen/00_RESEARCH_SPEC.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "yellowstone_cutthroat_profile",
   "label": "Yellowstone cutthroat trout thermal + growth profile",
   "domain": "aquatic_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/fish-spec.md:12 (native species, no THERMAL_SPECIES entry)",
    "yellowstone_python_spec/fish-spec.md:36 (priority missing; literature anchors Rogers 2022 16.5-16.9 C; Heinle 2025)"
   ],
   "method": "Literature-transferred THERMAL_SPECIES anchors; curve shape authored between points.",
   "validation": "none",
   "notes": "Core to native-species claim.",
   "source": "yellowstone_python_spec/fish-spec.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "arctic_grayling_profile",
   "label": "Arctic grayling thermal profile",
   "domain": "aquatic_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/fish-spec.md:13 (native; below Firehole Falls)",
    "yellowstone_python_spec/fish-spec.md:37 (species to add)"
   ],
   "method": "Cold-water specialist; narrower thermal window than trout.",
   "validation": "none",
   "source": "yellowstone_python_spec/fish-spec.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "mountain_whitefish_profile",
   "label": "Mountain whitefish thermal profile",
   "domain": "aquatic_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/fish-spec.md:14 (native Madison/Firehole)",
    "yellowstone_python_spec/fish-spec.md:38"
   ],
   "method": "Thermal preference + growth limits (cold-water).",
   "validation": "none",
   "source": "yellowstone_python_spec/fish-spec.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "brook_trout_profile",
   "label": "Brook trout THERMAL_SPECIES profile",
   "domain": "aquatic_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/fish-spec.md:15 (papers already present; no profile configured)",
    "yellowstone_python_spec/fish-spec.md:39 (Chadwick 2017 growth >16 C decreases; Jonsson 2023 UILT ~25.3 C)"
   ],
   "method": "THERMAL_SPECIES entry from Chadwick 2017 + Jonsson 2023 anchors.",
   "validation": "none",
   "source": "yellowstone_python_spec/fish-spec.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "nonsalmonid_native_fish",
   "label": "Mottled sculpin / longnose dace / longnose sucker / redside shiner / Utah chub",
   "domain": "aquatic_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_species_gen/00_RESEARCH_SPEC.md:53 (Fish list for species_gen includes mottled sculpin, longnose dace, longnose sucker, redside shiner, Utah chub)"
   ],
   "method": "parametric_mesh / deform_base per species per 00_RESEARCH_SPEC.md gen modes.",
   "validation": "none",
   "source": "yellowstone_species_gen/00_RESEARCH_SPEC.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "river_cross_section_survey",
   "label": "Surveyed Firehole + Excelsior cross-section geometry",
   "domain": "hydrology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:32 (P0 asset 4: Firehole 3 + Excelsior outflow 1 bank mesh + per-reach depth/velocity)",
    "yellowstone_python_spec/03_AUDIT_RESPONSE.md:66-69 (1-D advection-dispersion river + energy budget deferred: needs cross-section survey data)",
    "yellowstone_python/yellowstone_python/river/README.md (cross-sections optional; depth defaults to 1.1 m authored assumed)"
   ],
   "method": "Hand transects or bathymetric survey replacing uniform 1.1 m authored depth.",
   "validation": "none",
   "notes": "P0 asset gap; blocks honest 1-D advection-dispersion claim.",
   "source": "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "dynamic_hydraulic_routing",
   "label": "1-D Saint-Venant or diffusive-wave dynamic hydraulic routing",
   "domain": "hydrology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/improvements.md:862-884 (hydraulic levels 1-5; Manning is a resistance relationship not a complete unsteady model)",
    "research/yellowstone-todo.md:163-170 (select and document shallow-water / diffusive-wave / kinematic-wave formulation)"
   ],
   "method": "Choose level 4 (1-D Saint-Venant) or 3 (kinematic/diffusive wave); replace quasi-steady Manning chain.",
   "validation": "none",
   "source": "yellowstone_python_spec/improvements.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "two_d_shallow_water_backend",
   "label": "Optional ANUGA/Clawpack 2-D shallow-water backend",
   "domain": "hydrology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/improvements.md:541-542 (ANUGA, Clawpack/PyClaw/GeoClaw candidates)",
    "yellowstone_python_spec/improvements.md:869-870 (Two-dimensional shallow-water model level)"
   ],
   "method": "Benchmark 2-D hydraulics on small reference domain; not a park-wide rewrite.",
   "validation": "none",
   "source": "yellowstone_python_spec/improvements.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "bmi_component_interface",
   "label": "CSDMS BMI/bmipy component interface",
   "domain": "infrastructure",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/improvements.md:546 (CSDMS BMI / bmipy tool-table entry)",
    "yellowstone_python_spec/improvements.md:748-761 (component interface shall expose BMI-compatible init/update/state/grid/time/finalize)"
   ],
   "method": "Add bmipy.Bmi-compatible wrappers for hydro_thermal, overland_flow, snow_season, microclimate, surface_flux.",
   "validation": "none",
   "source": "yellowstone_python_spec/improvements.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "cf_netcdf_scientific_outputs",
   "label": "CF-compatible NetCDF scientific-release outputs + IOOS compliance",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/river/nc_export.py",
    "yellowstone_python/yellowstone_python/build.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/nc_export.py:1 (CF-conformant NetCDF export of replay temperature frames (CF-1.11, Standard Name Table v83))",
    "yellowstone_python/yellowstone_python/river/nc_export.py:10-11 (SCHEMA = 'yellowstone.replay_netcdf.v1'; CF_CONVENTIONS = 'CF-1.11')",
    "yellowstone_python/yellowstone_python/pipeline/sidecars.py:68 write_replay_netcdf"
   ],
   "method": "xarray/netCDF4 export of replay cell_temperature_c with CF-1.11 conventions; opt-in via cfg.replay.netcdf.",
   "validation": "none",
   "notes": "Replay NetCDF only (not park-wide scientific release) and IOOS Compliance Checker is not yet wired into CI.",
   "source": "yellowstone_python_spec/improvements.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "spotpy_calibration",
   "label": "SPOTPY (or pyEMU/PEST++) calibration workflow",
   "domain": "infrastructure",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/improvements.md:544-545 (SPOTPY, pyEMU/PEST++ candidates)",
    "yellowstone_python_spec/improvements.md:1119 (adopt SPOTPY or pyEMU/PEST++ when workflow addresses demonstrated need)"
   ],
   "method": "Replace or supplement scipy.least_squares with SPOTPY DREAM/SCE-UA sampling + identifiability diagnostics.",
   "validation": "none",
   "source": "yellowstone_python_spec/improvements.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "modflow6_groundwater_energy",
   "label": "MODFLOW 6 Groundwater Energy backend via FloPy",
   "domain": "hydrology",
   "python": [
    "yellowstone_python/yellowstone_python/land/groundwater_provider.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/land/groundwater_provider.py:6 (STATUS = 'authored_lateral_not_modeled')",
    "yellowstone_python/yellowstone_python/land/groundwater_provider.py:118-139 (def synthetic_mf6_simulation builds a one-layer flopy.mf6.MFSimulation with GwfDis/Npf/Ic/Riv)",
    "yellowstone_python/yellowstone_python/exporters/godot_sidecars.py:378 (groundwater_provider.STATUS is authored_lateral_not_modeled)",
    "yellowstone_python/yellowstone_python/HANDOFF_TRACKER.json (tests_result: 403 passed, 2 skipped (flopy and landlab absent))"
   ],
   "method": "FloPy-based synthetic MF6 simulation + authored lateral inflows mapped to river Source dicts; benchmark path exists but build path uses authored lateral only.",
   "validation": "none",
   "notes": "Thermal exchange with the river heat budget is still authored lateral, not an MF6 Groundwater Energy run.",
   "source": "yellowstone_python_spec/improvements.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "snodas_snow_assimilation",
   "label": "SNODAS snow data assimilation",
   "domain": "cryosphere",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/improvements.md:610 (SNODAS candidate; data-assimilation product classification)"
   ],
   "method": "Fetch SNODAS daily SWE/depth; adapt to overland/snow_season grid; carry assimilation-product provenance.",
   "validation": "none",
   "source": "yellowstone_python_spec/improvements.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "phreeqc_reactive_transport",
   "label": "PhreeqcRM reactive-transport chemistry (silica, As, B)",
   "domain": "hydrothermal",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/improvements.md:549 (PhreeqcRM / IPhreeqc)",
    "yellowstone_python_spec/03_AUDIT_RESPONSE.md:70 (PHREEQC silica chemistry explicitly research-gated)"
   ],
   "method": "Couple geochemistry.py substrate rules to a reactive-transport reaction module for silica/As/B pathways.",
   "validation": "none",
   "source": "yellowstone_python_spec/improvements.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "ice_cover_winter_heat",
   "label": "Ice/snow interaction with river heat exchange + winter claim gate",
   "domain": "hydrology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/improvements.md:906 (ice or snow interactions when winter claims are supported)",
    "yellowstone_python_spec/improvements.md:977 (explicit ice-free applicability gate rather than running summer equations)"
   ],
   "method": "Add ice-cover energy term + applicability gate reporting ice-cover state.",
   "validation": "none",
   "source": "yellowstone_python_spec/improvements.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "model_structure_uncertainty",
   "label": "Model-structure uncertainty ensemble (alternative formulations)",
   "domain": "observation",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/improvements.md:1143 (Model-structure uncertainty category)",
    "yellowstone_python_spec/improvements.md:1149-1159 (evaluate >=1 scientifically meaningful alternative per high-impact weakly supported assumption)"
   ],
   "method": "Run ensembles of alternative roughness/shading/thermal-curve/hydraulic simplifications; report spread as scenario, not calibrated prediction interval.",
   "validation": "none",
   "source": "yellowstone_python_spec/improvements.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "scientific_claim_registry",
   "label": "Machine-readable scientific claim registry",
   "domain": "infrastructure",
   "python": [
    "yellowstone_python/yellowstone_python/registry/claims.py",
    "yellowstone_python/yellowstone_python/validation/claims.py",
    "yellowstone_python/yellowstone_python/build.py"
   ],
   "godot": [],
   "status": "python_only",
   "evidence": [
    "yellowstone_python/yellowstone_python/registry/claims.py:7-24 (REQUIRED_CLAIM_FIELDS = ('claim_id','predicted_quantity','intended_use','spatial_domain','temporal_domain','supported_conditions','model_version','implementation_status','evidence_status','required_processes','required_observations','calibration_dataset_ids','evaluation_dataset_ids','metrics','acceptance_criteria','known_exclusions','evidence_artifact_ids','review_status'))",
    "yellowstone_python/yellowstone_python/registry/claims.py:52-55 (REVIEW_STATUSES, IMPLEMENTATION_STATUSES, EVIDENCE_STATUSES enum tuples)",
    "yellowstone_python/yellowstone_python/validation/claims.py (per-claim gate: check_reach_rmse against recorded nulls; evidence_artifact resolution)",
    "yellowstone_python/yellowstone_python/pipeline/sidecars.py:99 registry_errors",
    "yellowstone_python/yellowstone_python/pipeline/sidecars.py:302 claims sidecar"
   ],
   "method": "In-code CLAIMS registry with required/optional fields + per-claim gate checks against recorded nulls; sidecar JSON emitted on every build.",
   "validation": "none",
   "notes": "No Godot overlay yet consumes the sidecar's evidence_status/review_status.",
   "source": "yellowstone_python_spec/improvements.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "salib_dependence_aware",
   "label": "SALib dependence-aware sensitivity (correlated inputs)",
   "domain": "observation",
   "python": [
    "yellowstone_python/yellowstone_python/river/identifiability.py"
   ],
   "godot": [],
   "status": "partial_unwired",
   "evidence": [
    "yellowstone_python/yellowstone_python/river/identifiability.py:25-35 (DEPENDENCE_POLICY = {'varied_independently': {...}, 'held_fixed': (...), 'salib_gate': 'independent-input formulation above, or a dependence-aware method with documented interpretation'})",
    "yellowstone_python/yellowstone_python/river/identifiability.py:217-233 (SALib.analyze.sobol + sampler with saltelli/sobol fallbacks; records salib_version)",
    "yellowstone_python/tests/river/test_identifiability.py:53 (self.assertIn('salib_gate', DEPENDENCE_POLICY))"
   ],
   "method": "Documented independence policy via DEPENDENCE_POLICY plus a Sobol screen implementation; no Shapley effects or copula-based variant.",
   "validation": "none",
   "notes": "Dependence policy is declared and gated; Shapley/copula-based alternative for correlated inputs is still absent.",
   "source": "yellowstone_python_spec/improvements.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "canopy_interception",
   "label": "Canopy interception storage + throughfall partitioning",
   "domain": "hydrology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "research/yellowstone-todo.md:71-80 (canopy interception, throughfall, canopy evap as separate flux)",
    "rg canopy_intercept|throughfall yellowstone_python/ returns no module"
   ],
   "method": "Capacity-limited canopy bucket; drip + canopy evap as separate fluxes.",
   "validation": "none",
   "source": "research/yellowstone-todo.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "storm_intensity_profile",
   "label": "Smooth storm-intensity envelope (gradual onset/intensification/cessation)",
   "domain": "atmosphere",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "research/yellowstone-todo.md:52-55 (continuous storm envelopes; stochastic point-process comparison)"
   ],
   "method": "Smooth temporal envelope separate from slider instant intensity; preserve integrated volume.",
   "validation": "none",
   "source": "research/yellowstone-todo.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "spatial_rain_cells",
   "label": "Spatial rain cells with configurable size/intensity/lifetime + advection",
   "domain": "atmosphere",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "research/yellowstone-todo.md:55-58 (spatial rain cells with configurable size/intensity/lifetime/overlap; normalized to intended domain-average; advect by movement vector)"
   ],
   "method": "Lagrangian rain-cell generator with smooth spatial falloff; preserve intensity distribution and integrated volume.",
   "validation": "none",
   "source": "research/yellowstone-todo.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "raindrop_size_distribution",
   "label": "Documented raindrop-size distribution for splash/erosion",
   "domain": "atmosphere",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "research/yellowstone-todo.md:66-67 (raindrop terminal velocity vs published; Marshall-Palmer or similar DSD)"
   ],
   "method": "Marshall-Palmer DSD only where drop impacts/splash/erosion require it.",
   "validation": "none",
   "source": "research/yellowstone-todo.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "snow_fraction_from_wetbulb",
   "label": "Rain/snow partitioning via wet-bulb temperature",
   "domain": "atmosphere",
   "python": [
    "yellowstone_python/yellowstone_python/atmosphere/microclimate.py",
    "yellowstone_python/yellowstone_python/service/llm_backend.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/weather_http_consumer.gd",
    "yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd"
   ],
   "status": "rendered",
   "evidence": [
    "weather_snapshot.json weather.snow_fraction (syn 2026-10-13 after fixes pass 2: published build 71c8f00455af, main and study scenes 0 script errors; visual acceptance NOT TESTED)",
    "yellowstone_python/yellowstone_python/atmosphere/microclimate.py:430-449 (def metpy_wet_bulb_temperature uses mpcalc.wet_bulb_temperature with site pressure)",
    "yellowstone_python/yellowstone_python/service/llm_backend.py:449-479 (t_w from metpy_wet_bulb_temperature with Stull 2011 fallback; partition ramp 100 percent snow at T_w <= -1 C, 0 at T_w >= 3 C, linear between)",
    "yellowstone_python/yellowstone_python/service/llm_backend.py:486 (snow_fraction and snow_partition_source written to the weather extra block)",
    "yellowstone_midway/scripts/weather_http_consumer.gd:10-19 (snow_fraction listed in REQUIRED_WEATHER_FIELDS)",
    "yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd (controller scales GPU snow emitter by snow_fraction)",
    "yellowstone_midway/scripts/weather_snapshot_reader.gd:47 (snapshot_path = \"user://weather/latest.json\"); rg --no-ignore for latest.json/weather_http_consumer over yellowstone_python and yellowstone_midway scenes finds no writer and no instantiation (syn spot-check 2026-10-13)"
   ],
   "method": "metpy_wet_bulb_temperature with Stull 2011 fallback; linear ramp 100 percent snow at T_w <= -1 C, 0 at T_w >= 3 C.",
   "validation": "none",
   "notes": "snow fraction (Stull 2011 wet bulb) published in the snapshot and consumed by the precipitation particles",
   "source": "yellowstone_atmosphere/README.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "scientific_tree_inventory_validation",
   "label": "Blind-annotation + difference-estimator tree inventory validation",
   "domain": "terrestrial_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/addons.md:36-55 (install + scientific_addons.py design)",
    "yellowstone_python_spec/addons.md:179-258 (archive_run, frozen pre-review inventory, state_sha256, boundary_quality, scale_sensitivity)",
    "yellowstone_python_spec/addons.md:336-412 (create_sample SRS WOR)",
    "yellowstone_python_spec/addons.md:430-520 (annotate_sample blind GUI)",
    "yellowstone_python_spec/addons.md:522-684 (match_points one-to-one; pooled_metrics; plot_bootstrap; difference_estimate)",
    "rg scientific_addons|difference_estimator yellowstone_python/ returns no hits (archive/scientific_addons.py is historical, not integrated)"
   ],
   "method": "Hungarian one-to-one matching per tolerance; SRS-WOR corrected total with t-interval; plot-level bootstrap for exploratory metric bands.",
   "validation": "none",
   "notes": "canopy_census + census_validate exist but do not implement this methodology.",
   "source": "yellowstone_python_spec/addons.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "tree_inventory_boundary_quality",
   "label": "Boundary-quality flagging + scale sensitivity",
   "domain": "terrestrial_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python_spec/addons.md:261-316 (boundary_quality distance_transform_edt; scale_sensitivity area/density range)"
   ],
   "method": "distance_transform_edt against mask + explicit scale-range sensitivity (not a confidence interval).",
   "validation": "none",
   "source": "yellowstone_python_spec/addons.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "weather_live_bridge_timestamp_coupling",
   "label": "Simulation-timestamp freshness mode for weather snapshot reader",
   "domain": "atmosphere",
   "python": [],
   "godot": [
    "yellowstone_atmosphere/scripts/weather_snapshot_reader.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_midway/scripts/weather_snapshot_reader.gd:96 set_simulation_epoch_unix",
    "yellowstone_midway/scripts/world.gd:224 setup_python_runtime"
   ],
   "method": "freshness_mode export; sim epoch written into reader when a simulation epoch is active.",
   "validation": "none",
   "notes": "Published baked snapshots and live frames use the same simulation epoch. Snapshot freshness is compared with simulation time.",
   "source": "yellowstone_python_spec/fixes/fixes-14.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "weather_content_signature_detection",
   "label": "Content-hash file-change detection for snapshot reader",
   "domain": "atmosphere",
   "python": [],
   "godot": [
    "yellowstone_atmosphere/scripts/weather_snapshot_reader.gd"
   ],
   "status": "rendered",
   "evidence": [
    "weather_snapshot_reader.gd (syn 2026-10-13 after fixes pass 2: published build 71c8f00455af, main and study scenes 0 script errors; visual acceptance NOT TESTED)",
    "yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:77-78 (Content signature catches rapid atomic replacements on filesystems with coarse timestamp resolution; var _last_signature: int = -1)",
    "yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:141-142 (var signature := hash(bytes); if signature == _last_signature)",
    "yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:196 (_last_signature = signature)",
    "yellowstone_midway/scripts/weather_snapshot_reader.gd:47 (snapshot_path = \"user://weather/latest.json\"); rg --no-ignore for latest.json/weather_http_consumer over yellowstone_python and yellowstone_midway scenes finds no writer and no instantiation (syn spot-check 2026-10-13)"
   ],
   "method": "Hash file bytes with Godot's hash(); compare against last-seen signature; skip reload if unchanged.",
   "validation": "none",
   "notes": "content signature active on the published snapshot",
   "source": "yellowstone_python_spec/fixes/fixes-14.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "pool_shell_rim_meshes",
   "label": "Hand-sculpted pool-shell and rim meshes for Grand Prismatic + Excelsior",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:29 (P0 asset 1)",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:211 (Prompt 1: replace crude underwater terrain cut with authored pool-shell/rim meshes)"
   ],
   "method": "Low-poly shells preserving mapped water outline; separate crater wall, shelf, wetted rim, outflow lip.",
   "validation": "none",
   "notes": "Pool-overlay shim is rendered; underlying geometry still terrain cut.",
   "source": "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "thermal_apron_texture",
   "label": "Thermal-apron eligibility texture at ~1 m",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:30 (P0 asset 2)"
   ],
   "method": "USGS thermal polygons + NAIP detail -> apron_mask.png at ~1 m.",
   "validation": "none",
   "source": "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "species_correct_wildlife_rigs",
   "label": "Species-correct wildlife rigs (bison, Canada goose, dipper, raven, trout)",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:31 (P0 asset 3)",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:221-223 (Prompt 4: replace stand-ins with verified rigged models)"
   ],
   "method": "Keep path_xz / river_id indices / lateral_offset_m interface.",
   "validation": "none",
   "source": "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "lodgepole_pine_set",
   "label": "Lodgepole-tuned pine set replacing generic Poly Haven pine",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:35 (P1 asset 5)",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:144-145 (pine geometry is reduced Poly Haven; lodgepole set remains botanical art task)"
   ],
   "method": "Lodgepole silhouette/color/thin-bark; 3 LODs + billboard in existing MultiMesh slots.",
   "validation": "none",
   "source": "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "shrub_forb_grass_upgrades",
   "label": "Sedge/willow/lupine variants + snag/down-wood",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:36 (P1 asset 6)"
   ],
   "method": "2-3 variants per guild + snag/down-wood for recruitment/mortality storytelling.",
   "validation": "none",
   "source": "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "insect_swarm_gpu_particles",
   "label": "GPU insect swarm + dipper perch stones",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:37 (P1 asset 7)"
   ],
   "method": "GPU point/quad swarm driven by insect_activity + 2-3 perch stones.",
   "validation": "none",
   "source": "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "steam_volumetric_lite",
   "label": "Steam upgrade from quads to soft volumetric-lite",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:38 (P1 asset 8)"
   ],
   "method": "Height-faded, wind-advected shader reading shared wind vector.",
   "validation": "none",
   "source": "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "boardwalk_microdetail",
   "label": "Boardwalk/overlook microdetail (planks, rails, deck edge, drainage fingers)",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:39 (P1 asset 9)"
   ],
   "method": "Sculpted from midway_orthophoto_detail.jpg.",
   "validation": "none",
   "source": "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "snow_phenology_overlays",
   "label": "Seasonal ground-detail textures + bare-branch/needle tint variants",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:42 (P2 asset 10)",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:233-235 (Prompt 7: physically coherent seasonal appearance)"
   ],
   "method": "Season-specific textures + phenology tint variants; keyed to GDD.",
   "validation": "none",
   "notes": "snow_map shader uniform exists; alternate texture layers not authored.",
   "source": "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "positional_audio_set",
   "label": "Positional audio (Firehole whitewater, boardwalk footsteps, wind shelter vs clearing, waterfall)",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:43 (P2 asset 11)",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:155-159 (audio pass items)"
   ],
   "method": "Author source positions, near/far attenuation, bank/forest occlusion.",
   "validation": "none",
   "source": "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "field_notes_overlay_art",
   "label": "Field-notes / binocular overlay art (pool_cross_section, plume_map, refuge_map, suitability notebook plates)",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:44 (P2 asset 12)",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:225-227 (Prompt 5: optional naturalist notebook)"
   ],
   "method": "Framed notebook plates triggered by I/M keys; progressive disclosure of scientific notes.",
   "validation": "none",
   "notes": "The PNGs are produced by Python M11; Godot does not consume them.",
   "source": "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "naturalist_observation_mode",
   "label": "Optional naturalist notebook / binocular observation mode",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:225-227 (Prompt 5 full text)",
    "no gd script named notebook/binocular/observation under yellowstone_midway/scripts/"
   ],
   "method": "Binocular/camera view records observation (location, sim time, confidence); separate visible-category from exact ID when evidence insufficient; large-text + controller + keyboard support.",
   "validation": "none",
   "notes": "No XP, no mandatory checklists; local versioned schema.",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "study_mode_in_engine_ab_ui",
   "label": "In-engine study-mode A/B slider UI with reset + side-by-side replay",
   "domain": "rendering",
   "python": [
    "yellowstone_python/yellowstone_python/service/live/engine.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/simulation_panel.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_midway/scripts/world.gd:408 apply_comparison",
    "yellowstone_midway/scripts/simulation_panel.gd:125 _build_schema"
   ],
   "method": "Mark A clones the Python model checkpoint; B controls recompute causal model frames; ghost actors and temperature ribbons show equal-time A/B output.",
   "validation": "identical_branches_equal",
   "notes": "Non-grid Mark A, physical-origin capture and zero identical-branch metrics verified against the actual service.",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "counterexample_presets",
   "label": "Counterexample study presets (single variable != whole habitat)",
   "domain": "rendering",
   "python": [
    "yellowstone_python/yellowstone_python/study_mode.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/simulation_panel.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/study_mode.py:245 PRESETS",
    "yellowstone_midway/scripts/simulation_panel.gd:125 _build_schema"
   ],
   "method": "Python scenario records define parameter changes, descriptions and expected responses; Godot reads the service schema.",
   "validation": "preset_control_tests",
   "source": "yellowstone_python_spec/01_PYTHON_BUILD_SPEC.md",
   "notes": "Presets preserve separate river and atmospheric forcing; expected responses remain model claims.",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "guided_scenario_inquiry_prompts",
   "label": "Guided scenario inquiry prompts + annotation overlays",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:44 (notebook plates: Prompt 5 without progression/XP)",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:227 (progressive disclosure of scientific notes; separate visible category from exact ID)"
   ],
   "method": "Scripted narrator prompts tied to overlook/boardwalk/bridge/meadow waypoints; links back to notebook plates and study_mode variants.",
   "validation": "none",
   "notes": "Educational-interactivity hook over existing study_mode + compare + control-pulse toggle.",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "experiment_controls_in_scene",
   "label": "In-scene experiment control toggles for air T, shade/cloud, upstream Q, Excelsior strength",
   "domain": "rendering",
   "python": [
    "yellowstone_python/yellowstone_python/study_mode.py",
    "yellowstone_python/yellowstone_python/service/live/engine.py"
   ],
   "godot": [
    "yellowstone_midway/scripts/simulation_panel.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_python/yellowstone_python/study_mode.py:20 SCHEMA",
    "yellowstone_midway/scripts/simulation_panel.gd:125 _build_schema"
   ],
   "method": "Schema-driven controls send bounded values to Python; stage dependencies and provenance are displayed from the response.",
   "validation": "actual_service_causal_boundary_test",
   "source": "yellowstone_python_spec/01_PYTHON_BUILD_SPEC.md",
   "notes": "Live-only controls are disabled until the service schema is available.",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "gentle_physical_interactions",
   "label": "Viewpoint sit, interpretive panels, binoculars, inspection",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:249-251 (Prompt 11)"
   ],
   "method": "Authored viewpoints + sourced interpretive panels; accessible dismissible overlays; no collection/damage/feeding.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "fairy_falls_extension",
   "label": "Fairy Falls extension (DEM, orthophoto, cliff, wetted rock, spray + audio)",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:45 (P2 asset 13 deferred until Milestone A passes)",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:191 (extension row: Fairy Falls)",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:237-239 (Prompt 8 full text)"
   ],
   "method": "Extend domain along true Fairy Falls route; cliff + stream junction with Firehole chain.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "lower_geyser_basin_tile",
   "label": "Lower Geyser Basin / Fountain extension tile",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:192"
   ],
   "method": "New thermal-area map, mud/sinter material distinction, species eligibility.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "upper_geyser_basin_tile",
   "label": "Upper Geyser Basin extension with time-dependent geyser plumbing",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:193"
   ],
   "method": "Time-dependent geyser plumbing + eruption-asset model with observational basis.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "firehole_canyon_madison_tile",
   "label": "Firehole Canyon / Madison extension",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:194"
   ],
   "method": "Canyon meshes, banks, whitewater classification, stream junctions.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "hayden_valley_tile",
   "label": "Hayden Valley extension",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:195",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:201 (Hayden/Lamar should not inherit Midway's forest eligibility mask)"
   ],
   "method": "Separate grassland + river wetlands + grazer habitat; distinct eligibility mask.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "lamar_valley_tile",
   "label": "Lamar Valley extension",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:196"
   ],
   "method": "Northern-range grassland + riparian; connecting distances or explicit region-selection loading screen.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "canyon_lower_falls_tile",
   "label": "Canyon / Lower Falls extension",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:197"
   ],
   "method": "Full cliff meshes, waterfall spray, long-range lighting, paths from source data.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "yellowstone_lake_tile",
   "label": "Yellowstone Lake / West Thumb extension",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:198"
   ],
   "method": "Bathymetry where licensed; shoreline waves; native/non-native fish context.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "mammoth_travertine_basin",
   "label": "Mammoth travertine basin (chemically distinct thermal landscape)",
   "domain": "hydrothermal",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:199-201 (Mammoth cannot be implemented by whitening Grand Prismatic)",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:253-255 (Prompt 12 full text)",
    "yellowstone_python/yellowstone_python/thermal_features/geochemistry.py (sinter vs travertine guardrail only; no Mammoth model)"
   ],
   "method": "Travertine/calcite deposition model + terrace geometry + limestone-derived mineral system.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "whole_park_tile_architecture",
   "label": "Versioned tile catalog + async loading + physics-safe handoffs + origin rebase",
   "domain": "infrastructure",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:241-243 (Prompt 9 full text)"
   ],
   "method": "Separate geographic coordinates / runtime-relative coordinates / simulation IDs; shared transport+water graph ports; origin rebasing after precision test demonstrates need.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "measured_rendering_optimization",
   "label": "Measured rendering optimization (frame-time percentiles, draw calls, LOD budgets)",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:245-247 (Prompt 10 full text)"
   ],
   "method": "Record percentiles, draw calls, triangles, alpha overdraw, memory, shader stutters at the four starting places + continuous walk; produce Compatibility + Forward+ profiles.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "milestone_a_walking_route",
   "label": "Milestone A: one finished walking route (overlook-to-basin)",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:163-168 (acceptance: no open seam, no floating plant, no road in channel, no billboard failure, no ordinary wildlife in hot center)"
   ],
   "method": "Eye-height captures every 20-30 m; replace development fauna in this route; before/after ledger.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "milestone_c_seasonal_layers",
   "label": "Milestone C: authored summer/autumn/winter appearance layers",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:175-179 (Milestone C acceptance)"
   ],
   "method": "Same geographic topology across seasons; snow depth in m with aspect/canopy/wind/thermal eligibility; alternate authored plant forms per season.",
   "validation": "none",
   "notes": "snow_season.py writes season.json; apply_season reads it; alternate seasonal visual asset layers not authored.",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "forward_plus_quality_tier",
   "label": "Forward+ renderer quality tier (volumetric fog, SSAO/SSIL, volumetric clouds)",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_atmosphere/README.md:27 (Compatibility renderer; volumetric fog Forward+-only; true ray-marched volumetric cloud should be a separate Forward+ quality tier)",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:152-153 (Forward+ quality profile can add local volumetric fog, SSAO/SSIL, better reflections)"
   ],
   "method": "Separate quality profile with ray-marched volumetric clouds, local volumetric fog, SSAO/SSIL.",
   "validation": "none",
   "source": "yellowstone_atmosphere/README.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "audio_full_pass",
   "label": "Full positional audio pass (source positions, occlusion, loop-seam audit)",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:155-159 (Audio should belong somewhere; source positions, near/far attenuation, bank occlusion, chorus-time labeling)"
   ],
   "method": "Author source positions + near/far attenuation + wind clearings vs forest shelter vs river-bank occlusion; inspect each loop seam.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "atmosphere_controller_install",
   "label": "Install yellowstone_atmosphere/ controller into yellowstone_midway scripts + apply integration patch",
   "domain": "atmosphere",
   "python": [],
   "godot": [
    "yellowstone_midway/scripts/yellowstone_atmosphere.gd",
    "yellowstone_midway/scripts/weather_snapshot_reader.gd",
    "yellowstone_midway/scripts/weather_http_consumer.gd",
    "yellowstone_midway/shaders/yellowstone_cloud_shell.gdshader",
    "yellowstone_midway/scripts/world.gd"
   ],
   "status": "rendered",
   "evidence": [
    "yellowstone_midway/scripts/yellowstone_atmosphere.gd (class_name YellowstoneAtmosphereController extends Node3D; Preetham physical sky with sun animated from a simulation timestamp)",
    "yellowstone_midway/shaders/yellowstone_cloud_shell.gdshader:1 (shader_type spatial; Camera-following cloud-layer shell)",
    "yellowstone_midway/scripts/world.gd:6-7 (const AtmosphereController = preload('res://scripts/yellowstone_atmosphere.gd'); const WeatherSnapshotReader = preload('res://scripts/weather_snapshot_reader.gd'))",
    "yellowstone_midway/scripts/world.gd (atmosphere_controller = AtmosphereController.new(); atmosphere_controller.configure(sun, environment, player); weather_snapshot_reader.bind(atmosphere_controller))",
    "yellowstone_midway/scripts/world.gd:132-138 (reader instantiated, bound, flipped to simulation_clock)"
   ],
   "method": "res://scripts/yellowstone_atmosphere.gd, weather_snapshot_reader.gd, weather_http_consumer.gd and the cloud shell shader present in the midway project; world.gd preloads, instantiates and configures the controller against sun/environment/player.",
   "validation": "none",
   "notes": "Package is installed and wired; sky material swap to PhysicalSkyMaterial not independently reverified here.",
   "source": "yellowstone_atmosphere/README.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "educational_annotation_overlays",
   "label": "Educational annotation overlays tied to pool shells, plumes, fish refuges",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "next_phase",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:227 (progressive disclosure of scientific notes; retain source links)",
    "yellowstone_python_spec/01_PYTHON_BUILD_SPEC.md:107-108 (Prompt 6 companion: units + uncertainty shown)"
   ],
   "method": "Trigger notebook plates / HUD annotations by proximity to features; show units, uncertainty, source link.",
   "validation": "none",
   "source": "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "outflow_network_gps",
   "label": "Grand Prismatic outflow channel network",
   "domain": "hydrothermal",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_python/yellowstone_python/thermal_features/pool_crust.py:18-20 (OUTFLOW_CHANNELS holds only the authored Excelsior outflow)",
    "yellowstone_python_spec/fixes/fixes-40-microbial-mats-and-thermal-core-terrain.md problem 3"
   ],
   "method": "Flow routing from the spring rim over the 1 m 3DEP DEM, refined against 0.625 m NAIP wet-mat pixels",
   "validation": "none",
   "notes": "Radial distributary channels seen in aerial imagery are absent from data and world.",
   "source": "yellowstone_python_spec/fixes/fixes-40-microbial-mats-and-thermal-core-terrain.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "outflow_temperature_field",
   "label": "Outflow sheet-flow temperature field",
   "domain": "hydrothermal",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "pool_crust.py:24-39 (authored t_center_c and t_edge_c only)",
    "fixes-40 problem 2"
   ],
   "method": "Thin-film energy balance along each channel using replay/surface_flux terms",
   "validation": "none",
   "notes": "Needs spring discharge and channel depth data.",
   "source": "yellowstone_python_spec/fixes/fixes-40-microbial-mats-and-thermal-core-terrain.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "microbial_mat_model",
   "label": "Microbial mat community and pigment model",
   "domain": "hydrothermal",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "pool_crust.py:41-48 (COLOR_STOPS fixed by radius fraction, labeled illustrative)",
    "fixes-40 problem 1"
   ],
   "method": "Community class from local water temperature (Nugent et al. 2015 Table 1), pH gate, irradiance-driven chlorophyll to carotenoid index with a relaxation time",
   "validation": "none",
   "notes": "Mat colors today are a static radial ramp computed once per build.",
   "source": "yellowstone_python_spec/fixes/fixes-40-microbial-mats-and-thermal-core-terrain.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "mat_pigment_render",
   "label": "Mat pigment material on the apron and outflows",
   "domain": "rendering",
   "python": [],
   "godot": [
    "yellowstone_midway/shaders/thermal_apron.gdshader"
   ],
   "status": "not_started",
   "evidence": [
    "yellowstone_midway/shaders/terrain.gdshader (photo-based pigment boost from a 2 m macro orthophoto)",
    "yellowstone_midway/docs/AUTHORING.md:68",
    "fixes-40 problem 5"
   ],
   "method": "World-space pigment field from the mat model drives albedo and wet-film shading; NAIP kept as validation reference",
   "validation": "none",
   "notes": "thermal_apron.gdshader exists and is unused.",
   "source": "yellowstone_python_spec/fixes/fixes-40-microbial-mats-and-thermal-core-terrain.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "thermal_core_microrelief",
   "label": "Thermal core high-resolution terrain",
   "domain": "rendering",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "yellowstone_midway/tools/prepare_world.py:19 (GRID 1025, STEP 4 m)",
    "yellowstone_midway/references/dem_pixel_comparison.json (3DEP locked_1m sample available)",
    "fixes-40 problem 6"
   ],
   "method": "Local 1 m lidar tile plus channel incision and authored sinter rim microrelief, stitched into the 4 m master grid",
   "validation": "none",
   "notes": "Apron reads as a flat single-color plane at 4 m.",
   "source": "yellowstone_python_spec/fixes/fixes-40-microbial-mats-and-thermal-core-terrain.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "mat_validation_imagery",
   "label": "Mat color validation against imagery",
   "domain": "observation",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "fixes-40 problem 7"
   ],
   "method": "NAIP detail classification into mat color classes; confusion matrix against modeled classes",
   "validation": "none",
   "notes": "Validation only; no feedback into parameters without a declared calibration step.",
   "source": "yellowstone_python_spec/fixes/fixes-40-microbial-mats-and-thermal-core-terrain.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "geothermal_solute_transport",
   "label": "Geothermal solutes in the river (chloride, arsenic, boron)",
   "domain": "hydrology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "sweep: one descriptive hit in geochemistry.py",
    "fixes-41 item 1"
   ],
   "method": "Conservative advection on replay cells; chloride flux checked against gauge specific conductance",
   "validation": "none",
   "notes": "Chloride is an independent check on geothermal heat inputs (McCleskey et al. 2012); arsenic and boron are a separate trout stressor (Nimick et al. 1998; Goldstein 2001).",
   "source": "yellowstone_python_spec/fixes/fixes-41-missing-couplings-and-species.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "dissolved_oxygen",
   "label": "Dissolved oxygen",
   "domain": "hydrology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "sweep: no oxygen model",
    "fixes-41 item 2"
   ],
   "method": "Temperature and pressure dependent saturation, reaeration from hydraulics, metabolism from periphyton",
   "validation": "none",
   "notes": "",
   "source": "yellowstone_python_spec/fixes/fixes-41-missing-couplings-and-species.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "river_periphyton",
   "label": "River primary producers (periphyton, aquatic plants)",
   "domain": "aquatic_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "sweep: zero hits for periphyton, algae, primary production, nutrient",
    "fixes-41 item 3"
   ],
   "method": "Light and temperature limited growth per cell, nutrient limitation authored",
   "validation": "none",
   "notes": "Food base for grazing invertebrates.",
   "source": "yellowstone_python_spec/fixes/fixes-41-missing-couplings-and-species.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "hot_spring_flies",
   "label": "Hot-spring outflow food web (ephydrid flies, mites, predators)",
   "domain": "hydrothermal",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "sweep: zero hits for ephydrid or brine fly",
    "fixes-41 item 4"
   ],
   "method": "Fly occupancy on mats by temperature window, mite parasitism, predation by beetles and shorebirds",
   "validation": "none",
   "notes": "Brock, Wiegert and Brock 1969; Kuenzel and Wiegert 1973. Needs fixes-40 mat model.",
   "source": "yellowstone_python_spec/fixes/fixes-41-missing-couplings-and-species.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "ground_heat_flux_field",
   "label": "Geothermal ground heat flux and soil temperature",
   "domain": "hydrothermal",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "sweep: zero hits for ground heat flux or soil temperature",
    "fixes-41 item 6"
   ],
   "method": "Basin field authored from apron mask and thermal imagery until measured",
   "validation": "none",
   "notes": "Drives snow-free refuges, thermal-soil plants and tree die-off.",
   "source": "yellowstone_python_spec/fixes/fixes-41-missing-couplings-and-species.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "river_shading",
   "label": "Terrain and riparian shading of river shortwave",
   "domain": "atmosphere",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "study_mode.py:2 (shade is a study slider only)",
    "fixes-41 item 7"
   ],
   "method": "Sky view and direct-beam shading from DEM and canopy census",
   "validation": "none",
   "notes": "",
   "source": "yellowstone_python_spec/fixes/fixes-41-missing-couplings-and-species.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "plume_microclimate_feedback",
   "label": "Steam plume effect on local air, fog and rime",
   "domain": "atmosphere",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "build.py:828-844 (condensation index is one-way)",
    "fixes-41 item 8"
   ],
   "method": "Pool and outflow heat and vapor flux into downwind humidity and temperature",
   "validation": "none",
   "notes": "",
   "source": "yellowstone_python_spec/fixes/fixes-41-missing-couplings-and-species.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "aerial_insectivores",
   "label": "Aerial insectivores and riparian spiders (swallows, bats)",
   "domain": "terrestrial_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "fixes-41 item 9"
   ],
   "method": "Consumers of the emergent insect compartment",
   "validation": "none",
   "notes": "",
   "source": "yellowstone_python_spec/fixes/fixes-41-missing-couplings-and-species.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "fish_piscivores",
   "label": "Trout predators (osprey, eagle, merganser, kingfisher, otter)",
   "domain": "aquatic_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "grazers.py:15-18 (predation listed as unknown only)",
    "fixes-41 item 10"
   ],
   "method": "Size-class predation mortality from authored piscivore densities",
   "validation": "none",
   "notes": "",
   "source": "yellowstone_python_spec/fixes/fixes-41-missing-couplings-and-species.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "grazer_nutrient_trampling",
   "label": "Grazer nutrient return and trampling",
   "domain": "terrestrial_ecology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "sweep: zero hits for dung, nutrient, trampling, wallow",
    "fixes-41 item 11"
   ],
   "method": "Nitrogen return and disturbance per patch",
   "validation": "none",
   "notes": "",
   "source": "yellowstone_python_spec/fixes/fixes-41-missing-couplings-and-species.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "evapotranspiration",
   "label": "Plant water uptake (evapotranspiration)",
   "domain": "cryosphere",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "sweep: zero hits for evapotranspiration",
    "fixes-41 item 12"
   ],
   "method": "Reference ET from met forcing with a coefficient per patch type",
   "validation": "none",
   "notes": "",
   "source": "yellowstone_python_spec/fixes/fixes-41-missing-couplings-and-species.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "hyporheic_exchange",
   "label": "Hyporheic exchange",
   "domain": "hydrology",
   "python": [],
   "godot": [],
   "status": "not_started",
   "evidence": [
    "sweep: zero hits for hyporheic",
    "fixes-41 item 12"
   ],
   "method": "Bed exchange term on replay cells, authored rates until measured",
   "validation": "none",
   "notes": "",
   "source": "yellowstone_python_spec/fixes/fixes-41-missing-couplings-and-species.md",
   "source_inventory": "plans",
   "kind": "component"
  },
  {
   "id": "air_temperature",
   "label": "air temperature",
   "domain": "atmosphere",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "weather_bundle",
   "label": "weather bundle",
   "domain": "atmosphere",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "shortwave_radiation",
   "label": "shortwave radiation",
   "domain": "atmosphere",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "boundary_discharge",
   "label": "boundary discharge",
   "domain": "hydrology",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "boundary_temperature",
   "label": "boundary temperature",
   "domain": "hydrology",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "tributary_sources",
   "label": "tributary sources",
   "domain": "hydrology",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "ecosystem_variant",
   "label": "ecosystem variant",
   "domain": "rendering",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "plume_field",
   "label": "plume field",
   "domain": "hydrothermal",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "patches",
   "label": "patches",
   "domain": "terrestrial_ecology",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "world_shader",
   "label": "world shader",
   "domain": "rendering",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "wildlife_variant",
   "label": "wildlife variant",
   "domain": "rendering",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "aquatic_ecology",
   "label": "aquatic ecology",
   "domain": "aquatic_ecology",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "world_display",
   "label": "world display",
   "domain": "rendering",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "wildlife_actors",
   "label": "wildlife actors",
   "domain": "infrastructure",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "river_heat_budget",
   "label": "river heat budget",
   "domain": "infrastructure",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "geochemistry_substrate_rules",
   "label": "geochemistry substrate rules",
   "domain": "infrastructure",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "rendering",
   "label": "rendering",
   "domain": "infrastructure",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  },
  {
   "id": "fish_suitability",
   "label": "fish suitability",
   "domain": "infrastructure",
   "status": "interface",
   "kind": "interface",
   "evidence": [],
   "notes": "Quantity or artifact named by a coupling; not a module."
  }
 ],
 "couplings": [
  {
   "from": "air_temperature",
   "to": "hydro_thermal_mixing",
   "quantity": "surface Newton air forcing (C)",
   "status": "wired",
   "evidence": [
    "build.py:340 air0 = air_temp(hour0, ...)",
    "build.py:443 run_simulation(... air0, sim_s)"
   ],
   "notes": "microclimate.air_temp feeds the chain surface Newton term",
   "cross_domain": true
  },
  {
   "from": "air_temperature",
   "to": "replay_river_transport",
   "quantity": "surface Newton or budget air forcing",
   "status": "wired",
   "evidence": [
    "build.py:453 run_replay_solver(cfg, baseline, world, hour0, weather_frag, boundary_m3s)",
    "build.py:214 injected weather keys include lag_hours/night_air_c/day_warming_c"
   ],
   "notes": "weather_frag carries authored or measured air curve into the replay solver",
   "cross_domain": true
  },
  {
   "from": "weather_bundle",
   "to": "microclimate",
   "quantity": "measured hourly air, humidity, wind, cloud, shortwave",
   "status": "wired",
   "evidence": [
    "build.py:333 load_weather_bundle(met_path)",
    "build.py:335 bundle_weather(met_bundle, hour=hour0)"
   ],
   "notes": "frozen Open-Meteo bundle overrides authored defaults",
   "cross_domain": false
  },
  {
   "from": "shortwave_radiation",
   "to": "surface_flux",
   "quantity": "net SW into water (W/m2)",
   "status": "wired",
   "evidence": [
    "build.py energy_budget_choice (syn 2026-10-13 after fixes pass 2: build 71c8f00455af passed, 950 tests pass, main and study scenes 0 script errors)",
    "river/surface_flux.py:1 docstring (SW/LW/sensible/latent)",
    "registry/coupling.py EXCHANGES surface_budget",
    "build.py:293 energy_budget flag passed through"
   ],
   "notes": "explicit surface budget forced by the measured bundle in hindcast and observed_replay; Newton exchange stays the declared illustrative default",
   "cross_domain": false
  },
  {
   "from": "boundary_discharge",
   "to": "hydro_thermal_mixing",
   "quantity": "upstream water inflow (m3/s)",
   "status": "wired",
   "evidence": [
    "build.py:439 baseflow_m3s = hcfg.boundary_m3s",
    "build.py:442 run_simulation(reaches_in, boundary_m3s, ...)",
    "registry/coupling.py EXCHANGES boundary_water"
   ],
   "notes": "prescribed forcing",
   "cross_domain": false
  },
  {
   "from": "boundary_discharge",
   "to": "replay_river_transport",
   "quantity": "upstream water inflow (m3/s)",
   "status": "wired",
   "evidence": [
    "build.py:453 run_replay_solver(..., boundary_m3s=boundary_m3s)"
   ],
   "notes": "same effective boundary as the mixing chain",
   "cross_domain": false
  },
  {
   "from": "boundary_temperature",
   "to": "hydro_thermal_mixing",
   "quantity": "upstream water temperature (C)",
   "status": "wired",
   "evidence": [
    "build.py:443 run_simulation(... hcfg.boundary_c ... air0, sim_s)"
   ],
   "notes": "prescribed forcing",
   "cross_domain": false
  },
  {
   "from": "boundary_temperature",
   "to": "replay_river_transport",
   "quantity": "upstream water temperature (C)",
   "status": "wired",
   "evidence": [
    "build.py:210 eco.boundary_c for replay"
   ],
   "notes": "shared with chain via _prepare_replay_ecosystem",
   "cross_domain": false
  },
  {
   "from": "snow_season",
   "to": "replay_river_transport",
   "quantity": "snowmelt runoff added to boundary discharge (m3/s)",
   "status": "wired",
   "evidence": [
    "build.py:416 catchment_runoff_m3_s(patches1, snow_ledger, ...)",
    "build.py:440 boundary_m3s = baseflow_m3s + runoff_m3_s",
    "registry/coupling.py EXCHANGES snow_runoff_discharge"
   ],
   "notes": "only when hydro.catchment.area_m2 configured; otherwise storage-only",
   "cross_domain": true
  },
  {
   "from": "snow_season",
   "to": "hydro_thermal_mixing",
   "quantity": "snowmelt runoff increment on prescribed baseflow (m3/s)",
   "status": "wired",
   "evidence": [
    "build.py:440 shared boundary_m3s",
    "build.py:442 passed to run_simulation"
   ],
   "notes": "same increment reaches both hydrology models",
   "cross_domain": true
  },
  {
   "from": "tributary_sources",
   "to": "replay_river_transport",
   "quantity": "lateral water + heat per authored source",
   "status": "wired",
   "evidence": [
    "build.py:218 tribs = DEFAULT_TRIBUTARIES merged with hcfg.tributaries",
    "build.py:220 hcfg.attach places lateral_sources on reaches",
    "registry/coupling.py EXCHANGES lateral_water, lateral_heat"
   ],
   "notes": "authored illustrative tributaries; status marked illustrative on each entry",
   "cross_domain": false
  },
  {
   "from": "tributary_sources",
   "to": "hydro_thermal_mixing",
   "quantity": "lateral water + heat per authored source",
   "status": "wired",
   "evidence": [
    "build.py:430 hcfg.attach applied to reaches_in"
   ],
   "notes": "same lateral_sources structure as the replay path",
   "cross_domain": false
  },
  {
   "from": "overland_flow",
   "to": "replay_river_transport",
   "quantity": "surface runoff -> upstream discharge increment (m3/s)",
   "status": "partial",
   "evidence": [
    "build.py _overland_runoff_to_boundary; river/river_world.py boundary Series (syn 2026-10-13 after fixes pass 2: build 71c8f00455af passed, 950 tests pass, main and study scenes 0 script errors)",
    "build.py:581 run_overland result stored only in overland_field",
    "build.py:912 overland_flow.json sidecar",
    "no reads of overland_field.surface_runoff anywhere in build.py"
   ],
   "notes": "overland outlet runoff added to the scheduled river boundary and recorded separately in BUILD.json; contributing area not delineated from terrain",
   "cross_domain": false
  },
  {
   "from": "groundwater_provider",
   "to": "replay_river_transport",
   "quantity": "lateral groundwater inflow + temperature per cell",
   "status": "partial",
   "evidence": [
    "land/groundwater_provider.py head_gradient_exchange; build.py groundwater_exchange (syn 2026-10-13 after fixes pass 2: build 71c8f00455af passed, 950 tests pass, main and study scenes 0 script errors)",
    "land/groundwater_provider.py:47 riv_reaches_to_sources",
    "river/tests/test_river_world.py:204 only call site",
    "no build.py import"
   ],
   "notes": "head-gradient exchange implemented with sign and budget test; build calls it only when hydro.groundwater.cells is configured (baseline has none)",
   "cross_domain": false
  },
  {
   "from": "replay_river_transport",
   "to": "aquatic_foodweb",
   "quantity": "thermal landscape (cell time-mean temperature + hydraulics)",
   "status": "wired",
   "evidence": [
    "aquatic/aquatic_foodweb.py:102 thermal_landscape",
    "build.py:468 thermal_landscape(replay_doc)",
    "registry/coupling.py EXCHANGES landscape_temperature"
   ],
   "notes": "landscape also fed to validation.checks and figures",
   "cross_domain": true
  },
  {
   "from": "replay_hydraulics",
   "to": "aquatic_foodweb",
   "quantity": "bed shear (Pa) -> benthic disturbance fraction",
   "status": "wired",
   "evidence": [
    "aquatic/aquatic_foodweb.py:148 shear_pa = hydro.bed_shear_pa",
    "aquatic/aquatic_foodweb.py:245 shear_to_disturbance",
    "registry/coupling.py EXCHANGES shear_disturbance",
    "build.py:465 shear_disturb_pa default 20 Pa"
   ],
   "notes": "None shear maps to 0 so coupling degrades silently where Manning is undefined",
   "cross_domain": true
  },
  {
   "from": "replay_hydraulics",
   "to": "insects_birds",
   "quantity": "bed shear disturbance for insect compartments",
   "status": "wired",
   "evidence": [
    "build.py:780 bridge_cell_shear_pa = bridge_cell.get('shear_pa')",
    "build.py:781 bridge_disturbance = shear_to_disturbance(bridge_cell_shear_pa, foodweb_shear_disturb_pa)",
    "build.py:795 'disturbance': bridge_disturbance passed to step_compartments",
    "insects_birds.py:144 disturbance is a step input"
   ],
   "notes": "the per-minute insect compartments now take disturbance from the bridge-cell shear through the shared shear_to_disturbance ramp",
   "cross_domain": true
  },
  {
   "from": "aquatic_foodweb",
   "to": "fish",
   "quantity": "refuge cell (chainage, temperature, suitability) for the rendered trout",
   "status": "wired",
   "evidence": [
    "build.py:547 place_trout_at_chainage(wildlife2, river_state, firehole_points, aquatic_foodweb['trout'], chainage_offset_m=fh_offset)",
    "aquatic/fish.py build_chainage / place_trout_at_chainage"
   ],
   "notes": "landscape foodweb picks the refuge; aquatic/fish.py places the rendered trout actor there",
   "cross_domain": false
  },
  {
   "from": "aquatic_foodweb",
   "to": "insects_birds",
   "quantity": "dipper intake per day",
   "status": "wired",
   "evidence": [
    "build.py:521 fw_dipper = aquatic_foodweb['dipper']",
    "build.py:523 rates['dipper'] = intake_per_day/24.0",
    "build.py:526 update_wildlife_from_intake"
   ],
   "notes": "dipper rate comes from the replay landscape; raven stays on the legacy insect-compartment ledger",
   "cross_domain": false
  },
  {
   "from": "replay_river_transport",
   "to": "fish",
   "quantity": "reach-cell temperature and flow for trout suitability",
   "status": "wired",
   "evidence": [
    "build.py:531 update_trout(... river_state ...)",
    "registry/equations.py:68 trout U = wf F + wc C - wt phi(T) - wv V - wd D"
   ],
   "notes": "update_trout uses mixing-chain reach_state (not replay cells); replay landscape informs refuge argmax",
   "cross_domain": true
  },
  {
   "from": "replay_river_transport",
   "to": "ecosystem_variant",
   "quantity": "river_reaches temperature + flow for Godot",
   "status": "wired",
   "evidence": [
    "build.py:602 merge_fragments(baseline, river_state, ...)",
    "exporters/to_ecosystem.py merges reach fields",
    "ecosystem.gd:46 reads river_reaches"
   ],
   "notes": "mixing-chain state is what reaches Godot; python_river_replay.gd handles the separate study-scene A/B pair",
   "cross_domain": true
  },
  {
   "from": "pool_crust",
   "to": "vegetation",
   "quantity": "apron exclusion test (hydrothermal keep-out)",
   "status": "wired",
   "evidence": [
    "build.py:376 _excluded = any(_in_apron(x,z,s) for s in shells)",
    "build.py:391 propose_plantings_reviewed(exclusion_test=_excluded)",
    "thermal_features/pool_crust.py:357 in_apron"
   ],
   "notes": "proposed plantings refused inside the buffered apron rings",
   "cross_domain": true
  },
  {
   "from": "pool_crust",
   "to": "grazers",
   "quantity": "apron exclusion test for route planner",
   "status": "wired",
   "evidence": [
    "build.py:552 update_grazers(wildlife2, patches1)",
    "build.py:565 plan_path(_a, _b, _excluded, cell_m=4.0, bounds=_bounds)",
    "land/grazers.py:102 check_routes against shells"
   ],
   "notes": "A*-style planner rejects segments crossing apron",
   "cross_domain": true
  },
  {
   "from": "pool_crust",
   "to": "snow_season",
   "quantity": "thermal exclusion for snow accumulation (bare apron)",
   "status": "wired",
   "evidence": [
    "build.py:405 run_season(... thermal_test=_excluded)",
    "land/snow_season.py:157 run_season uses thermal_test"
   ],
   "notes": "snow kept off thermally active apron tiles",
   "cross_domain": true
  },
  {
   "from": "pool_crust",
   "to": "fish",
   "quantity": "exclusion check for trout route (clear of pools)",
   "status": "wired",
   "evidence": [
    "build.py:548 check_trout_clear_of_pools(wildlife2, firehole_points, shells)"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "geochemistry",
   "to": "pool_crust",
   "quantity": "siliceous substrate palette gate (Midway vs Mammoth)",
   "status": "wired",
   "evidence": [
    "thermal_features/geochemistry.py:67 check_midway_shells",
    "thermal_features/geochemistry.py:81 validate_palette",
    "build.py:374 check_midway_shells(shells)"
   ],
   "notes": "whitening palettes refused on silica systems",
   "cross_domain": false
  },
  {
   "from": "replay_river_transport",
   "to": "geochemistry",
   "quantity": "cell temperature -> silica saturation index",
   "status": "wired",
   "evidence": [
    "exporters/godot_sidecars.py:143 _load_json(build_dir / 'river_replay.json')",
    "exporters/godot_sidecars.py:157 diagnose_replay_frame call with last-frame temperatures",
    "build.py:1491 produce_all runs the geochemistry producer against the build"
   ],
   "notes": "the godot_sidecars producer feeds the last replay frame through diagnose_replay_frame and writes geochemistry.json per build",
   "cross_domain": true
  },
  {
   "from": "pool_crust",
   "to": "plume_field",
   "quantity": "hot source temperature for 2-D plume (Excelsior reach T)",
   "status": "partial",
   "evidence": [
    "build.py:674 plume_field(nx=128, nz=128, hot_c=float(exc.temperature_c), river_c=float(river_ref.temperature_c))",
    "publish.py:28 plume_map.png not shipped"
   ],
   "notes": "rendered to PNG in derived/ only",
   "cross_domain": false
  },
  {
   "from": "weather_bundle",
   "to": "overland_flow",
   "quantity": "rainfall rate (mm/h)",
   "status": "wired",
   "evidence": [
    "build.py:873 bundle_precip = met_bundle.get('precipitation_mm')",
    "build.py:884 window-mean mm/h computed from the bundle",
    "build.py:909 run_overland(..., rain_mm_h=rain_mm_h)"
   ],
   "notes": "overland.rain_mm_h wins; otherwise in run_mode hindcast or observed_replay the met_bundle precipitation_mm mean drives the forcing; snow.precip_mm_d is only the illustrative fallback",
   "cross_domain": true
  },
  {
   "from": "weather_bundle",
   "to": "snow_season",
   "quantity": "hourly air temperature from the met bundle plus authored daily air",
   "status": "wired",
   "evidence": [
    "build.py:645 air_hourly_c=(met_bundle.get('hourly') if met_bundle else None) passed to run_season",
    "land/snow_season.py run_season consumes air_hourly_c",
    "land/snow_validate.py drives run_season from the SNOTEL bundle for the standalone validator"
   ],
   "notes": "the build now hands met_bundle hourly air to run_season alongside the authored daily series; SNOTEL still reaches snow_season only through snow_validate for the holdout gate",
   "cross_domain": true
  },
  {
   "from": "patches",
   "to": "insects_birds",
   "quantity": "patch moisture + insect_resource -> activity + resource decay",
   "status": "wired",
   "evidence": [
    "build.py:481 riparian = _find(patches1, 'id', PATCH_RIPARIAN, 'patch')",
    "build.py:486 insect_activity(..., moisture=riparian['moisture'], resource=riparian['insect_resource'], ...)"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "patches",
   "to": "grazers",
   "quantity": "patch biomass + capacity -> grazing cadence",
   "status": "wired",
   "evidence": [
    "land/grazers.py:57 graze_timing(biomass, capacity, ...)",
    "build.py:552 update_grazers(wildlife2, patches1)"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "grazers",
   "to": "patches",
   "quantity": "grazing pressure on patch biomass",
   "status": "wired",
   "evidence": [
    "build.py _grazers_input_from_consumed (syn 2026-10-13 after fixes pass 2: build 71c8f00455af passed, 950 tests pass, main and study scenes 0 script errors)",
    "land/vegetation.py:92 patch_step grazers argument",
    "build.py:382 patch_step(patches0, hour0, sim_s, grazers=vcfg.grazers)"
   ],
   "notes": "previous step consumed_by_patch feeds vegetation patch_step (lag 1)",
   "cross_domain": false
  },
  {
   "from": "snow_season",
   "to": "patches",
   "quantity": "snow depth / soil moisture / phenology updates on patches",
   "status": "wired",
   "evidence": [
    "build.py:402 patches2, snow_ledger = run_season(patches1, ...)"
   ],
   "notes": "patches2 goes into ecosystem.variant",
   "cross_domain": true
  },
  {
   "from": "snow_season",
   "to": "world_shader",
   "quantity": "snow mask + snow_depth summary for terrain shader",
   "status": "wired",
   "evidence": [
    "land/snow_season.py:297 render_snow_map",
    "build.py:665 render_snow_map",
    "world.gd:122 reads season.json",
    "world.gd:135 loads snow_map.png"
   ],
   "notes": "Godot terrain shader blends snow by this mask",
   "cross_domain": true
  },
  {
   "from": "insects_birds",
   "to": "wildlife_variant",
   "quantity": "dipper / raven foraging cadence from intake",
   "status": "wired",
   "evidence": [
    "build.py:526 update_wildlife_from_intake(wildlife1, rates, intake_basis)",
    "wildlife_actor.gd:443 set_insect_forager_activity"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "fish",
   "to": "wildlife_variant",
   "quantity": "trout hold location + swim parameters",
   "status": "wired",
   "evidence": [
    "build.py:545 place_trout_at_chainage returns updated wildlife2",
    "wildlife_actor.gd:98 kind dispatch for authored proxy"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "grazers",
   "to": "wildlife_variant",
   "quantity": "bison / elk route and grazing timing",
   "status": "wired",
   "evidence": [
    "build.py:552 wildlife3 = update_grazers(...)",
    "wildlife_actor.gd:237 path_xz consumer"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "vegetation",
   "to": "ecosystem_variant",
   "quantity": "patches biomass + capacity for Godot patch advance",
   "status": "wired",
   "evidence": [
    "build.py:608 variant['patches'] = patches2",
    "ecosystem.gd:196 _advance_patches reads biomass/capacity/moisture"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "microclimate",
   "to": "ecosystem_variant",
   "quantity": "weather keys (night_air_c, day_warming_c, wind_xz_mps, gust_mps, humidity, cloud)",
   "status": "wired",
   "evidence": [
    "build.py:603 filter of weather_frag into merge_fragments weather subset",
    "ecosystem.gd:433 uses wind + air_c"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "canopy_census",
   "to": "vegetation",
   "quantity": "canopy fraction over the proposal circle for suitability",
   "status": "wired",
   "evidence": [
    "build.py:199 _canopy_from_census crown-area sum",
    "build.py:621 canopy_input, canopy_source = _canopy_from_census(proposal_center, proposal_radius_m, census.json)",
    "build.py:623 propose_plantings_reviewed(..., canopy=canopy_input, ...)",
    "land/vegetation.py:61 suitability takes canopy argument"
   ],
   "notes": "fallback 0.6 remains when derived/census.json is missing, empty, or has a bad proposal radius; otherwise the crown-area sum over the proposal circle drives suitability",
   "cross_domain": false
  },
  {
   "from": "overland_flow",
   "to": "snow_season",
   "quantity": "soil moisture / infiltration feedback",
   "status": "proposed",
   "evidence": [
    "hydrology/hydrosim.py docstring soil bucket",
    "land/snow_season.py:132 patch_modifiers soil model"
   ],
   "notes": "the two water-balance models run side by side without exchanging soil state",
   "cross_domain": true
  },
  {
   "from": "overland_flow",
   "to": "vegetation",
   "quantity": "cell soil wetness influencing suitability",
   "status": "proposed",
   "evidence": [
    "land/hydrology_provider.py:131 snapshot returns soil wetness",
    "land/vegetation.py:224 habitat_moisture_at currently uses patch moisture"
   ],
   "notes": "hydrology_provider surface exposed only through llm_backend; not fed into patch moisture",
   "cross_domain": true
  },
  {
   "from": "replay_hydraulics",
   "to": "fish",
   "quantity": "cell velocity / depth for trout velocity-cost term",
   "status": "wired",
   "evidence": [
    "build.py _per_point_hydraulics_from_cells (syn 2026-10-13 after fixes pass 2: build 71c8f00455af passed, 950 tests pass, main and study scenes 0 script errors)",
    "aquatic/fish.py update_trout uses reach-level flows",
    "river/hydraulics.py provides per-cell V = Q/A diagnostics"
   ],
   "notes": "per-cell velocity and depth feed fish.update_trout",
   "cross_domain": true
  },
  {
   "from": "replay_river_transport",
   "to": "insects_birds",
   "quantity": "water temperature forcing on benthic degree-day development",
   "status": "wired",
   "evidence": [
    "build.py develop_benthic_grid wiring (syn 2026-10-13 after fixes pass 2: build 71c8f00455af passed, 950 tests pass, main and study scenes 0 script errors)",
    "build.py:507 water_c = bridge.temperature_c passed to step_compartments",
    "insects_birds.py:124 develop_benthic"
   ],
   "notes": "per-cell water temperature drives develop_benthic_grid; benthic_grid.json published",
   "cross_domain": true
  },
  {
   "from": "plume_field",
   "to": "aquatic_foodweb",
   "quantity": "2-D plume heat as a landscape temperature overlay",
   "status": "proposed",
   "evidence": [
    "river/plume2d.py 2-D steady plume",
    "aquatic/aquatic_foodweb.py:102 thermal_landscape uses only 1-D replay cells"
   ],
   "notes": "plume is rendered to PNG and never merged into the foodweb landscape",
   "cross_domain": true
  },
  {
   "from": "geochemistry",
   "to": "aquatic_ecology",
   "quantity": "silica saturation / substrate pH gate on habitat",
   "status": "proposed",
   "evidence": [
    "thermal_features/geochemistry.py:200 silica_saturation_index",
    "thermal_features/geochemistry.py:211 diagnose_replay_frame (unused)"
   ],
   "notes": "chemistry diagnostics defined but no biological consumer; absent in coupling.json EXCHANGES",
   "cross_domain": true
  },
  {
   "from": "weather_bundle",
   "to": "surface_flux",
   "quantity": "shortwave, longwave, humidity, wind for explicit budget",
   "status": "wired",
   "evidence": [
    "build.py budget_mode_source (syn 2026-10-13 after fixes pass 2: build 71c8f00455af passed, 950 tests pass, main and study scenes 0 script errors)",
    "river/surface_flux.py:1 docstring",
    "registry/coupling.py EXCHANGES surface_budget 'prescribed meteorology series'",
    "build.py:293 energy_budget flag off by default"
   ],
   "notes": "full measured bundle selects the explicit budget in measured run modes",
   "cross_domain": false
  },
  {
   "from": "replay_plume2d",
   "to": "world_display",
   "quantity": "2-D plume field summary to the Godot status HUD",
   "status": "wired",
   "evidence": [
    "exporters/godot_sidecars.py:63 write_plume_field_json",
    "publish.py:24 plume_field.json shipped",
    "yellowstone_midway/scripts/world.gd:153 load_optional_sidecar(res://data/plume_field.json)",
    "yellowstone_midway/scripts/world.gd:657 reports plume_field grid, Excelsior and bridge temperatures"
   ],
   "notes": "replaces the earlier publish.py exclusion of plume_map.png with a published plume_field.json",
   "cross_domain": true
  },
  {
   "from": "geochemistry",
   "to": "world_display",
   "quantity": "per-cell silica saturation summary to the Godot status HUD",
   "status": "wired",
   "evidence": [
    "exporters/godot_sidecars.py:139 write_geochemistry_json",
    "publish.py:25 geochemistry.json shipped",
    "yellowstone_midway/scripts/world.gd:154 load_optional_sidecar(res://data/geochemistry.json)",
    "yellowstone_midway/scripts/world.gd:658 geochemistry.cells read for HUD"
   ],
   "notes": "cells are quartz-phase saturation only; sio2_obs_mg_L stays null until an observed field is wired",
   "cross_domain": true
  },
  {
   "from": "calibration_summary",
   "to": "world_display",
   "quantity": "reach heat fit scalars + first gauge trace to the Godot status HUD",
   "status": "wired",
   "evidence": [
    "exporters/godot_sidecars.py:195 write_calibration_summary_json",
    "publish.py:26 calibration_summary.json shipped",
    "yellowstone_midway/scripts/world.gd:155 load_optional_sidecar(res://data/calibration_summary.json)",
    "yellowstone_midway/scripts/world.gd:668 reach_fit summary line"
   ],
   "notes": "source files are the latest derived/reach_heat_fit*.json and firehole_obs_locked_final.json or firehole_obs.json",
   "cross_domain": true
  },
  {
   "from": "canopy_census",
   "to": "world_display",
   "quantity": "census tree records to the Godot status HUD",
   "status": "wired",
   "evidence": [
    "exporters/godot_sidecars.py:382 write_census_sidecar",
    "publish.py:31 census.json shipped",
    "yellowstone_midway/scripts/world.gd:156 load_optional_sidecar(res://data/census.json)",
    "yellowstone_midway/scripts/world.gd:674 census summary line"
   ],
   "notes": "the Godot reader unwraps either the raw census.json or the godot_sidecars wrapper carrying it under payload",
   "cross_domain": true
  },
  {
   "from": "overland_flow",
   "to": "world_display",
   "quantity": "overland field status to the Godot status HUD",
   "status": "wired",
   "evidence": [
    "exporters/godot_sidecars.py:327 write_overland_field_json",
    "publish.py:29 overland_field.json shipped",
    "yellowstone_midway/scripts/world.gd:159 load_optional_sidecar(res://data/overland_field.json)",
    "yellowstone_midway/scripts/world.gd:685 overland field status line"
   ],
   "notes": "overland field is a diagnostic status only; it is still not routed to the river boundary",
   "cross_domain": true
  },
  {
   "from": "species_gen_package",
   "to": "wildlife_actors",
   "quantity": "per-individual trait record consumed as spawn/skin parameters",
   "status": "proposed",
   "evidence": [
    "yellowstone_species_gen/00_RESEARCH_SPEC.md:179-181 (output per individual is the exact record wildlife_actor-style builders or a glTF morph-target applier consumes)"
   ],
   "notes": "Deterministic per --seed.",
   "cross_domain": true
  },
  {
   "from": "pvlib_authoritative_solar",
   "to": "atmosphere_controller_install",
   "quantity": "solar_azimuth_deg, solar_elevation_deg (+ sunrise/sunset epochs)",
   "status": "partial",
   "evidence": [
    "yellowstone_python/yellowstone_python/service/llm_backend.py:283-285 (solar_block = solar_snapshot(now_unix, ...)) emitted in weather HTTP payload",
    "yellowstone_atmosphere/scripts/weather_snapshot_reader.gd:179-192 (reader merges nested solar block into state passed to controller)",
    "yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:94-95 (controller stores solar_azimuth_deg/solar_elevation_deg and drives sun from them)",
    "yellowstone_midway/scripts/weather_snapshot_reader.gd:47 (snapshot_path = \"user://weather/latest.json\"); rg --no-ignore for latest.json/weather_http_consumer over yellowstone_python and yellowstone_midway scenes finds no writer and no instantiation (syn spot-check 2026-10-13)"
   ],
   "notes": "Solar block reaches the HTTP backend only. No Python code writes user://weather/latest.json (the path world.gd:132-138 binds through weather_snapshot_reader.gd:47), and no scene or script instantiates weather_http_consumer.gd, so this data does not reach the Godot sky.",
   "cross_domain": false
  },
  {
   "from": "moon_ephemeris",
   "to": "atmosphere_controller_install",
   "quantity": "lunar RA/Dec + altitude/azimuth; moon-phase illumination fraction",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/fixes/fixes-14.md:150-157 (skyfield/astropy for Moon/planets separate from stars)",
    "yellowstone_python_spec/fixes/fixes-14.md:1061"
   ],
   "cross_domain": false
  },
  {
   "from": "star_catalog_vendor",
   "to": "sidereal_star_renderer",
   "quantity": "RA, Dec, mag, B-V per star (res://data/stars.bin)",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/fixes/fixes-14.md:187-203"
   ],
   "cross_domain": false
  },
  {
   "from": "sidereal_star_renderer",
   "to": "milky_way_flux_layer",
   "quantity": "fade stars between point layer and unresolved flux layer at limiting magnitude",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/fixes/fixes-14.md:357 (fade stars between the point layer and flux layer around the limiting magnitude)"
   ],
   "cross_domain": false
  },
  {
   "from": "weather_snapshot_schema_v2",
   "to": "atmosphere_controller_install",
   "quantity": "normalized {schema_version:2, generated_at_unix, valid_time_unix, simulation_time_unix, source, weather, solar, terrain} payload",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/fixes/fixes-14.md:1012-1039"
   ],
   "cross_domain": false
  },
  {
   "from": "weather_http_consumer",
   "to": "weather_snapshot_schema_v2",
   "quantity": "nested schema parity between HTTP and file reader",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/fixes/fixes-14.md:697-736 (fix endpoint contract divergence)"
   ],
   "cross_domain": false
  },
  {
   "from": "snow_fraction_from_wetbulb",
   "to": "weather_snapshot_schema_v2",
   "quantity": "snow_fraction (0..1) field in weather block",
   "status": "proposed",
   "evidence": [
    "yellowstone_atmosphere/README.md:25 (feed snow_fraction from meteorological pipeline, ideally wet-bulb)",
    "yellowstone_python_spec/fixes/fixes-14.md:1088"
   ],
   "cross_domain": false
  },
  {
   "from": "pool_shell_rim_meshes",
   "to": "thermal_apron_texture",
   "quantity": "shared water-outline polygons feeding apron eligibility mask",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:29-30 (both P0; apron eligibility layer in a future art pass)"
   ],
   "cross_domain": false
  },
  {
   "from": "river_cross_section_survey",
   "to": "dynamic_hydraulic_routing",
   "quantity": "surveyed depth(x,y) + bank mesh + per-reach velocity for Saint-Venant / diffusive-wave",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/03_AUDIT_RESPONSE.md:67-69 (1-D advection-dispersion needs cross-section survey data before equations are honest)"
   ],
   "cross_domain": false
  },
  {
   "from": "modflow6_groundwater_energy",
   "to": "river_heat_budget",
   "quantity": "groundwater inflow (m3/s) with associated thermal energy",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/improvements.md:779-784 (one authoritative transfer record; groundwater inflow is water transfer with associated thermal energy)",
    "yellowstone_python_spec/improvements.md:949-950"
   ],
   "cross_domain": true
  },
  {
   "from": "snodas_snow_assimilation",
   "to": "snow_season",
   "quantity": "SWE (mm) and snow depth (m) daily assimilation to snow_season grid",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/improvements.md:610"
   ],
   "cross_domain": false
  },
  {
   "from": "phreeqc_reactive_transport",
   "to": "geochemistry_substrate_rules",
   "quantity": "reaction-coupled silica/As/B species concentrations driving substrate transition rules",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/improvements.md:549",
    "yellowstone_python_spec/03_AUDIT_RESPONSE.md:70"
   ],
   "cross_domain": true
  },
  {
   "from": "scientific_claim_registry",
   "to": "rendering",
   "quantity": "per-field evidence_status + applicability_limits consumed by Godot overlays",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/improvements.md:1298-1312 (Godot export requirements: evidence status, applicability limits, uncertainty where available)"
   ],
   "cross_domain": false
  },
  {
   "from": "cf_netcdf_scientific_outputs",
   "to": "bmi_component_interface",
   "quantity": "CF-labeled component I/O variables with grid + time metadata",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/improvements.md:546-547"
   ],
   "cross_domain": false
  },
  {
   "from": "yellowstone_cutthroat_profile",
   "to": "fish_suitability",
   "quantity": "THERMAL_SPECIES anchors (t_opt_lo/hi, t_feed_zero, t_refuge, t_uilt) + survivorship curve for native-species prediction",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/fish-spec.md:36"
   ],
   "cross_domain": true
  },
  {
   "from": "arctic_grayling_profile",
   "to": "fish_suitability",
   "quantity": "cold-water thermal window endpoints for extended Madison/confluence scope",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/fish-spec.md:37"
   ],
   "cross_domain": true
  },
  {
   "from": "mountain_whitefish_profile",
   "to": "fish_suitability",
   "quantity": "cold-water thermal preference endpoints",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/fish-spec.md:38"
   ],
   "cross_domain": true
  },
  {
   "from": "brook_trout_profile",
   "to": "fish_suitability",
   "quantity": "upper-growth-limit curve (Chadwick 2017, Jonsson 2023)",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/fish-spec.md:39"
   ],
   "cross_domain": true
  },
  {
   "from": "canopy_interception",
   "to": "overland_flow",
   "quantity": "throughfall as rainfall input to infiltration + surface storage (mm/h)",
   "status": "proposed",
   "evidence": [
    "research/yellowstone-todo.md:80 (expose ground-level throughfall as the rainfall input)"
   ],
   "cross_domain": false
  },
  {
   "from": "spatial_rain_cells",
   "to": "overland_flow",
   "quantity": "spatially distributed precipitation intensity field (m/s per cell)",
   "status": "proposed",
   "evidence": [
    "research/yellowstone-todo.md:51-63"
   ],
   "cross_domain": true
  },
  {
   "from": "study_mode_in_engine_ab_ui",
   "to": "experiment_controls_in_scene",
   "quantity": "slider state (air T, shade/cloud, upstream Q, Excelsior strength) written to ecosystem.json variant A/B",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/01_PYTHON_BUILD_SPEC.md:104-108"
   ],
   "cross_domain": false
  },
  {
   "from": "field_notes_overlay_art",
   "to": "naturalist_observation_mode",
   "quantity": "pool_cross_section/plume_map/refuge_map/suitability PNG consumed as framed plates in notebook",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:44",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:225-227"
   ],
   "cross_domain": false
  },
  {
   "from": "guided_scenario_inquiry_prompts",
   "to": "study_mode_in_engine_ab_ui",
   "quantity": "scenario preset ID + narrator prompt triggered at waypoint",
   "status": "proposed",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:225-227 (Prompt 5 progressive disclosure)",
    "yellowstone_python_spec/01_PYTHON_BUILD_SPEC.md:106 (counterexample presets)"
   ],
   "cross_domain": false
  },
  {
   "from": "fairy_falls_extension",
   "to": "whole_park_tile_architecture",
   "quantity": "first additional UTM-aligned tile exercising shared transport + water graph ports",
   "status": "proposed",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:181-186 (Milestone D acceptance: crossing boundary preserves distance, heading, elevation and simulation state)"
   ],
   "cross_domain": true
  },
  {
   "from": "mammoth_travertine_basin",
   "to": "phreeqc_reactive_transport",
   "quantity": "travertine deposition from Ca-HCO3-CO2 chemistry drives terrace growth rules",
   "status": "proposed",
   "evidence": [
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:199-201",
    "yellowstone_python/yellowstone_python/thermal_features/geochemistry.py (sinter vs travertine guardrail only)"
   ],
   "cross_domain": false
  },
  {
   "from": "ice_cover_winter_heat",
   "to": "river_heat_budget",
   "quantity": "ice-cover state gate + modified longwave/sensible/evaporative terms when ice present",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/improvements.md:906"
   ],
   "cross_domain": true
  },
  {
   "from": "model_structure_uncertainty",
   "to": "scientific_claim_registry",
   "quantity": "alternative-structure scenario spread recorded as structural uncertainty category",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/improvements.md:1143-1159"
   ],
   "cross_domain": true
  },
  {
   "from": "scientific_tree_inventory_validation",
   "to": "canopy_census",
   "quantity": "frozen pre-review automated inventory + validation_report.json corrected total",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/addons.md:179-258",
    "yellowstone_python_spec/addons.md:685-845 (evaluate_sample report + validation_report.json)"
   ],
   "cross_domain": false
  },
  {
   "from": "educational_annotation_overlays",
   "to": "field_notes_overlay_art",
   "quantity": "feature-proximity trigger id -> notebook plate asset",
   "status": "proposed",
   "evidence": [
    "yellowstone_python_spec/02_PREREQS_ASSETS_CHECKLIST.md:44",
    "yellowstone_midway/docs/DEVELOPMENT_AND_FUTURE_DIRECTIONS.md:225-227"
   ],
   "cross_domain": false
  },
  {
   "from": "outflow_network_gps",
   "to": "outflow_temperature_field",
   "quantity": "channel geometry and discharge split (m, m3/s)",
   "status": "proposed",
   "evidence": [
    "fixes-40 problems 2-3"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "surface_flux",
   "to": "outflow_temperature_field",
   "quantity": "net surface heat flux on the outflow film (W/m2)",
   "status": "proposed",
   "evidence": [
    "fixes-40 problem 2"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "outflow_temperature_field",
   "to": "microbial_mat_model",
   "quantity": "local water temperature (C)",
   "status": "proposed",
   "evidence": [
    "fixes-40 problems 1, 4"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "pool_crust",
   "to": "microbial_mat_model",
   "quantity": "pool edge temperature and pH (C, pH)",
   "status": "proposed",
   "evidence": [
    "fixes-40 problem 4"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "pvlib_authoritative_solar",
   "to": "microbial_mat_model",
   "quantity": "irradiance and season for the chlorophyll to carotenoid index (W/m2)",
   "status": "proposed",
   "evidence": [
    "fixes-40 problems 1, 4"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "microbial_mat_model",
   "to": "mat_pigment_render",
   "quantity": "per-cell community class and pigment index",
   "status": "proposed",
   "evidence": [
    "fixes-40 problem 5"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "outflow_network_gps",
   "to": "thermal_core_microrelief",
   "quantity": "channel incision geometry (m)",
   "status": "proposed",
   "evidence": [
    "fixes-40 problem 6"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "mat_validation_imagery",
   "to": "microbial_mat_model",
   "quantity": "class agreement scores (validation, not calibration)",
   "status": "proposed",
   "evidence": [
    "fixes-40 problem 7"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "tributary_sources",
   "to": "geothermal_solute_transport",
   "quantity": "hydrothermal inflow solute load (mg/s)",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 1"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "geothermal_solute_transport",
   "to": "fish",
   "quantity": "arsenic and boron concentration as a stressor (ug/L)",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 1"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "geothermal_solute_transport",
   "to": "runner_fetch_firehole",
   "quantity": "predicted chloride flux vs gauge specific conductance (validation)",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 1"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "replay_river_transport",
   "to": "dissolved_oxygen",
   "quantity": "water temperature for oxygen saturation (C)",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 2"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "replay_hydraulics",
   "to": "dissolved_oxygen",
   "quantity": "reaeration from depth and velocity",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 2"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "dissolved_oxygen",
   "to": "fish",
   "quantity": "dissolved oxygen (mg/L)",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 2"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "shortwave_radiation",
   "to": "river_periphyton",
   "quantity": "light at the bed (W/m2)",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 3"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "river_periphyton",
   "to": "aquatic_foodweb",
   "quantity": "producer biomass as food for grazing invertebrates",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 3"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "river_periphyton",
   "to": "dissolved_oxygen",
   "quantity": "photosynthesis and respiration (g O2/m2/d)",
   "status": "proposed",
   "evidence": [
    "fixes-41 items 2, 3"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "microbial_mat_model",
   "to": "hot_spring_flies",
   "quantity": "mat biomass and temperature window",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 4"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "hot_spring_flies",
   "to": "insects_birds",
   "quantity": "flies as prey for shorebirds and swallows",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 4"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "snow_season",
   "to": "grazers",
   "quantity": "snow depth and water equivalent as movement and forage cost",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 5"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "ground_heat_flux_field",
   "to": "snow_season",
   "quantity": "ground heat flux melting snow (W/m2)",
   "status": "proposed",
   "evidence": [
    "fixes-41 items 5, 6"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "ground_heat_flux_field",
   "to": "vegetation",
   "quantity": "soil temperature limit on plants and trees (C)",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 6"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "river_shading",
   "to": "surface_flux",
   "quantity": "shaded fraction of direct beam and sky view",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 7"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "canopy_census",
   "to": "river_shading",
   "quantity": "riparian canopy geometry",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 7"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "plume_microclimate_feedback",
   "to": "microclimate",
   "quantity": "downwind humidity and air temperature adjustment",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 8"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "insects_birds",
   "to": "aerial_insectivores",
   "quantity": "emergent insect prey",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 9"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "fish_piscivores",
   "to": "fish",
   "quantity": "predation mortality by size class",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 10"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "grazers",
   "to": "grazer_nutrient_trampling",
   "quantity": "grazer presence per patch",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 11"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "grazer_nutrient_trampling",
   "to": "patches",
   "quantity": "nitrogen return and disturbance",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 11"
   ],
   "notes": "",
   "cross_domain": false
  },
  {
   "from": "evapotranspiration",
   "to": "overland_flow",
   "quantity": "soil water loss to plants (mm/d)",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 12"
   ],
   "notes": "",
   "cross_domain": true
  },
  {
   "from": "hyporheic_exchange",
   "to": "replay_river_transport",
   "quantity": "bed exchange of water and heat",
   "status": "proposed",
   "evidence": [
    "fixes-41 item 12"
   ],
   "notes": "",
   "cross_domain": false
  }
 ],
 "rendering": [
  {
   "id": "river_heat",
   "label": "River heat transport (reach temperatures on river surfaces)",
   "domain": "hydrology",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/ecosystem.gd",
    "yellowstone_midway/scripts/python_river_replay.gd",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/shaders/water.gdshader"
   ],
   "evidence": [
    "yellowstone_midway/scripts/ecosystem.gd:configure/apply_python_frame",
    "yellowstone_midway/scripts/python_river_replay.gd:_apply_replay",
    "yellowstone_midway/scripts/world.gd:refresh_env_caches"
   ],
   "notes": "Frame-time temperatures and actual API probe equality pass headless checks; modeled temperatures remain unaccepted empirical predictions.",
   "sources": [
    "replay_river_transport",
    "replay_river_world",
    "hydro_thermal_mixing"
   ]
  },
  {
   "id": "river_flow",
   "label": "River flow (surface geometry and reach rate)",
   "domain": "hydrology",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/ecosystem.gd",
    "yellowstone_midway/scripts/python_river_replay.gd",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/shaders/water.gdshader",
    "yellowstone_midway/tools/bake_world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/python_river_replay.gd:_apply_replay",
    "yellowstone_midway/scripts/world.gd:cache_river_flow_defaults/refresh_env_caches"
   ],
   "notes": "Geometry and shader speed are presentation inputs; runtime reader consistency does not validate hydraulic geometry.",
   "sources": [
    "replay_river_transport",
    "hydro_thermal_mixing"
   ]
  },
  {
   "id": "pools_surface",
   "label": "Thermal and non-thermal pools (water surfaces)",
   "domain": "hydrothermal",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/pool_overlay.gd",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/shaders/water.gdshader",
    "yellowstone_midway/tools/bake_world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/world.gd:load_pool_shell_temperatures/refresh_pools_state/apply_pool_temperatures"
   ],
   "notes": "Optional published state is consumed when present.",
   "sources": [
    "pool_crust"
   ]
  },
  {
   "id": "pool_aprons_pigment",
   "label": "Pool pigment bands (microbial mat ramps)",
   "domain": "hydrothermal",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/mat_surface.gd",
    "yellowstone_midway/scripts/pool_overlay.gd",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/shaders/water.gdshader",
    "yellowstone_midway/tools/bake_world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/pool_overlay.gd:_ready",
    "yellowstone_midway/scripts/mat_surface.gd:load_pigment/start_blend",
    "yellowstone_midway/scripts/world.gd:_poll_mat_pigment_change"
   ],
   "notes": "Pigment is a visualization of the published model; no biological color validation is claimed.",
   "sources": [
    "pool_crust",
    "geochemistry"
   ]
  },
  {
   "id": "steam_plumes",
   "label": "Steam plumes above thermal pools",
   "domain": "hydrothermal",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/ecosystem.gd",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/shaders/steam.gdshader",
    "yellowstone_midway/tools/bake_world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/ecosystem.gd:condensation_visibility",
    "yellowstone_midway/scripts/world.gd:refresh_env_caches"
   ],
   "notes": "Condensation visibility and the density multiplier are presentation calculations.",
   "sources": [
    "microclimate"
   ]
  },
  {
   "id": "trees_pine",
   "label": "Pine trees (LOD MultiMesh)",
   "domain": "terrestrial_ecology",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/tools/bake_world.gd",
    "yellowstone_midway/shaders/foliage.gdshader",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/tools/bake_world.gd (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/shaders/foliage.gdshader (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/scripts/world.gd (current source/resource reference; source hash recorded below)"
   ],
   "notes": "Placements come from data/placements.json (published by Python); overrides via placement_overrides.json.",
   "sources": [
    "canopy_census",
    "gen_flora"
   ]
  },
  {
   "id": "grass_logs_rocks",
   "label": "Ground scatter: grass clumps, deadwood logs, boulders",
   "domain": "terrestrial_ecology",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/tools/bake_world.gd",
    "yellowstone_midway/shaders/foliage.gdshader"
   ],
   "evidence": [
    "yellowstone_midway/tools/bake_world.gd (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/shaders/foliage.gdshader (current source/resource reference; source hash recorded below)"
   ],
   "notes": "No dynamic growth/senescence; purely visual scatter.",
   "sources": [
    "gen_flora"
   ]
  },
  {
   "id": "botanical_details",
   "label": "Hand-placed botanical details (willow, lupine, sedge, bunchgrass)",
   "domain": "terrestrial_ecology",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/tools/bake_botany.gd",
    "yellowstone_midway/scenes/botanical_details.tscn",
    "yellowstone_midway/shaders/foliage.gdshader",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/tools/bake_botany.gd (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/scenes/botanical_details.tscn (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/shaders/foliage.gdshader (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/scripts/world.gd (current source/resource reference; source hash recorded below)"
   ],
   "notes": "Positions authored in data/botanical_placements.json.",
   "sources": [
    "gen_flora"
   ]
  },
  {
   "id": "ungulates_bison_elk",
   "label": "Bison / elk actors (grazers)",
   "domain": "terrestrial_ecology",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/ecosystem.gd",
    "yellowstone_midway/scripts/wildlife_actor.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/wildlife_actor.gd:_update_ungulate/_sync_feeding",
    "yellowstone_midway/scripts/ecosystem.gd:set_grazer_activity",
    "yellowstone_midway/scripts/world.gd:intervene"
   ],
   "notes": "Grazing interventions POST patch-specific bison count to Python. Actor routes pass headless checks.",
   "sources": [
    "grazers"
   ]
  },
  {
   "id": "birds_goose_dipper_raven",
   "label": "Birds: goose (float), dipper and raven (perch/forage)",
   "domain": "terrestrial_ecology",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/ecosystem.gd",
    "yellowstone_midway/scripts/wildlife_actor.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/wildlife_actor.gd:_update_goose/_update_bird/_sync_feeding",
    "yellowstone_midway/scripts/ecosystem.gd:set_insect_forager_activity"
   ],
   "notes": "Godot forager registration is presentation bookkeeping and does not step the foodweb.",
   "sources": [
    "insects_birds"
   ]
  },
  {
   "id": "fish",
   "label": "Fish actors (rainbow and brown trout)",
   "domain": "aquatic_ecology",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/python_river_replay.gd",
    "yellowstone_midway/scripts/wildlife_actor.gd",
    "yellowstone_midway/tools/tests/test_fish_swim.py"
   ],
   "evidence": [
    "yellowstone_midway/scripts/wildlife_actor.gd:_update_fish/_update_swim_clip",
    "yellowstone_midway/scripts/python_river_replay.gd:trout_state/position_at_s/river_state_at_position",
    "yellowstone_midway/tools/tests/test_fish_swim.py"
   ],
   "notes": "Headless refuge, feeding, clip and twelve-actor CPU checks pass. Bainbridge relation is transferred to trout; below5Hz is extrapolated. Asset source license is unspecified; GPU and visual acceptance are pending.",
   "sources": [
    "fish",
    "aquatic_foodweb"
   ]
  },
  {
   "id": "insects",
   "label": "Riverbank insect swarms",
   "domain": "aquatic_ecology",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/ecosystem.gd",
    "yellowstone_midway/scripts/wildlife_actor.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/wildlife_actor.gd:_update_insects",
    "yellowstone_midway/scripts/ecosystem.gd:apply_python_frame",
    "yellowstone_midway/scripts/world.gd:load_insect_bird_summary"
   ],
   "notes": "The reader contains no local patch growth, insect depletion or river heat integration.",
   "sources": [
    "insects_birds"
   ]
  },
  {
   "id": "terrain",
   "label": "Terrain tiles (georeferenced heightmap)",
   "domain": "hydrology",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/height_field.gd",
    "yellowstone_midway/tools/bake_world.gd",
    "yellowstone_midway/shaders/terrain.gdshader",
    "yellowstone_midway/data/terrain.f32"
   ],
   "evidence": [
    "yellowstone_midway/scripts/height_field.gd (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/tools/bake_world.gd (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/shaders/terrain.gdshader (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/data/terrain.f32 (current source/resource reference; source hash recorded below)"
   ],
   "notes": "Fixed landscape; height sampler shared by player/walker and wildlife.",
   "sources": []
  },
  {
   "id": "trails_boardwalks",
   "label": "Trails, roads, boardwalk decks",
   "domain": "infrastructure",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/tools/bake_world.gd",
    "yellowstone_midway/shaders/trail.gdshader",
    "yellowstone_midway/shaders/boardwalk.gdshader",
    "yellowstone_midway/shaders/terrain.gdshader"
   ],
   "evidence": [
    "yellowstone_midway/tools/bake_world.gd (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/shaders/trail.gdshader (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/shaders/boardwalk.gdshader (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/shaders/terrain.gdshader (current source/resource reference; source hash recorded below)"
   ],
   "notes": "Overlook deck is a separate OverlookDeck node group (scenes/authored_world.tscn:197263+).",
   "sources": []
  },
  {
   "id": "map_view",
   "label": "Field map overlay",
   "domain": "observation",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/map_view.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/map_view.gd:set_census/_draw",
    "yellowstone_midway/scripts/world.gd:_unhandled_input"
   ],
   "notes": "Map source wiring is inspected; cartographic and visual acceptance are not claimed.",
   "sources": []
  },
  {
   "id": "thermal_probe_overlay",
   "label": "Global water and ground probes with A/B ribbons",
   "domain": "observation",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scenes/study.tscn",
    "yellowstone_midway/scripts/python_river_replay.gd",
    "yellowstone_midway/scripts/simulation_panel.gd",
    "yellowstone_midway/scripts/thermal_probe_overlay.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/simulation_panel.gd:_update_probe/_ground_probe/probe_text",
    "yellowstone_midway/scripts/thermal_probe_overlay.gd:_update_ribbon",
    "yellowstone_midway/scripts/world.gd:setup_python_runtime"
   ],
   "notes": "Frame-time water probe equality and interface formatting pass; all modeled quantities retain their provenance.",
   "sources": [
    "replay_river_world"
   ]
  },
  {
   "id": "snow_cover",
   "label": "Snow cover (season overlay)",
   "domain": "cryosphere",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/scripts/yellowstone_atmosphere.gd",
    "yellowstone_midway/shaders/terrain.gdshader"
   ],
   "evidence": [
    "yellowstone_midway/scripts/world.gd:apply_season/update_environment",
    "yellowstone_midway/scripts/yellowstone_atmosphere.gd:set_weather_state"
   ],
   "notes": "Snow values are not integrated locally by the renderer.",
   "sources": [
    "snow_season"
   ]
  },
  {
   "id": "sky_sun_time",
   "label": "Sky, sun elevation, time-of-day lighting",
   "domain": "atmosphere",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/ecosystem.gd",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/scripts/yellowstone_atmosphere.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/ecosystem.gd:apply_python_frame",
    "yellowstone_midway/scripts/world.gd:adopt_python_clock/_process/_unhandled_input"
   ],
   "notes": "T sends a Python +2-hour control in live mode or seeks cached baked time. The renderer distinguishes backend hold from user pause.",
   "sources": [
    "microclimate"
   ]
  },
  {
   "id": "clouds_precipitation",
   "label": "Clouds, rain, snow particles, visibility fog, wetness",
   "domain": "atmosphere",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/weather_snapshot_reader.gd",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/scripts/yellowstone_atmosphere.gd",
    "yellowstone_midway/shaders/yellowstone_cloud_shell.gdshader"
   ],
   "evidence": [
    "yellowstone_midway/scripts/yellowstone_atmosphere.gd:_update_weather_interpolation",
    "yellowstone_midway/scripts/world.gd:update_environment"
   ],
   "notes": "The600x cloud property response passes headless checks; cloud appearance and GPU costs need visual acceptance.",
   "sources": [
    "microclimate"
   ]
  },
  {
   "id": "wind",
   "label": "Wind gusts (foliage sway, steam advection)",
   "domain": "atmosphere",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/ecosystem.gd",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/shaders/foliage.gdshader",
    "yellowstone_midway/shaders/steam.gdshader"
   ],
   "evidence": [
    "yellowstone_midway/scripts/ecosystem.gd:apply_python_frame",
    "yellowstone_midway/scripts/world.gd:update_environment/refresh_env_caches"
   ],
   "notes": "The duplicated Godot gust and daily air equations were removed.",
   "sources": [
    "microclimate"
   ]
  },
  {
   "id": "player_camera",
   "label": "Player walker and camera",
   "domain": "rendering",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/input_help.gd",
    "yellowstone_midway/scripts/player.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/player.gd:_physics_process/_unhandled_input",
    "yellowstone_midway/scripts/input_help.gd:pressed/bindings_text"
   ],
   "notes": "All project actions have keyboard and gamepad entries in the headless binding test; physical gamepad acceptance is pending.",
   "sources": []
  },
  {
   "id": "hud_notes",
   "label": "Field-notes HUD (reach T, flow, insects, snow, biological ledger, sidecars)",
   "domain": "observation",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/simulation_panel.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/world.gd:simulation_status_text/update_notes/format_sidecar_block",
    "yellowstone_midway/scripts/simulation_panel.gd:model_notes/probe_text/update_computation"
   ],
   "notes": "Live HUD/probe values match actual Python frames. Fresh published-data model-label assertion is pending final publication.",
   "sources": []
  },
  {
   "id": "audio_ambience",
   "label": "Ambient audio (wind, geyser hill water/birds, Firehole geese)",
   "domain": "rendering",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/world.gd (current source/resource reference; source hash recorded below)"
   ],
   "notes": "Godot-only presentation; files loaded conditionally.",
   "sources": []
  },
  {
   "id": "study_mode_toggle",
   "label": "Study-mode replay toggle (C switches pulse vs control)",
   "domain": "observation",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scenes/study.tscn",
    "yellowstone_midway/scripts/python_river_replay.gd",
    "yellowstone_midway/scripts/simulation_panel.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/world.gd:toggle_replay/mark_comparison/apply_comparison",
    "yellowstone_midway/scripts/simulation_panel.gd:_response"
   ],
   "notes": "Ghosts start at the marked physical position/time; non-grid identical A/B frames and metrics pass actual API checks.",
   "sources": [
    "study_mode",
    "compare"
   ]
  },
  {
   "id": "overlook_deck",
   "label": "Overlook viewing platform (handcrafted)",
   "domain": "infrastructure",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scenes/authored_world.tscn"
   ],
   "evidence": [
    "yellowstone_midway/scenes/authored_world.tscn (current source/resource reference; source hash recorded below)"
   ],
   "notes": "Baked into authored_world.tscn by tools/bake_world.gd (bake_world.gd:503 group name 'OverlookDeck').",
   "sources": []
  },
  {
   "id": "handcrafted_details_hook",
   "label": "Handcrafted details scene (authored-placement wrapper)",
   "domain": "infrastructure",
   "status": "partial_unwired",
   "godot": [
    "yellowstone_midway/scenes/handcrafted_details.tscn",
    "yellowstone_midway/scripts/authored_placement.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scenes/handcrafted_details.tscn (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/scripts/authored_placement.gd (current source/resource reference; source hash recorded below)",
    "yellowstone_midway/scripts/world.gd (current source/resource reference; source hash recorded below)"
   ],
   "notes": "Hook exists for designer-placed PackedScenes but no authored placements have been dropped in.",
   "sources": []
  },
  {
   "id": "census_overlay",
   "label": "Species / wildlife census overlay",
   "domain": "terrestrial_ecology",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/map_view.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/map_view.gd:set_census/_draw",
    "yellowstone_midway/scripts/world.gd:_published_changed/format_sidecar_block"
   ],
   "notes": "Tree ecological dynamics are not simulated by this overlay.",
   "sources": [
    "canopy_census"
   ]
  },
  {
   "id": "geochemistry_bands",
   "label": "Geochemistry / pigment-band model (beyond pool ramp texture)",
   "domain": "hydrothermal",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/pool_overlay.gd",
    "yellowstone_midway/scripts/scientific_overlays.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/pool_overlay.gd:_ready",
    "yellowstone_midway/scripts/scientific_overlays.gd:_build_geochemistry_markers/reload",
    "yellowstone_midway/scripts/world.gd:format_sidecar_block"
   ],
   "notes": "These are published model diagnostics, not validated in-game chemistry observations.",
   "sources": [
    "geochemistry"
   ]
  },
  {
   "id": "groundwater_overland",
   "label": "Groundwater / overland hydrology",
   "domain": "hydrology",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/scientific_overlays.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/scientific_overlays.gd:_build_overland_overlay/_build_groundwater_overlay/reload",
    "yellowstone_midway/scripts/world.gd:format_sidecar_block"
   ],
   "notes": "Overlay intensity uses published aggregates; per-cell flow geometry is not claimed.",
   "sources": [
    "overland_flow",
    "groundwater_provider"
   ]
  },
  {
   "id": "fetchers_calibration",
   "label": "External observations / calibration / uncertainty",
   "domain": "observation",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/calibration_panel.gd",
    "yellowstone_midway/scripts/simulation_panel.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/calibration_panel.gd:set_doc",
    "yellowstone_midway/scripts/simulation_panel.gd:update_computation/_draw_chart"
   ],
   "notes": "Observed downstream temperature and RMSE are labeled separately from prescribed upstream temperature and discharge.",
   "sources": [
    "calibration_summary",
    "met_forcing_fetcher"
   ]
  },
  {
   "id": "plume_field_summary",
   "label": "Hydrothermal plume field summary (HUD text)",
   "domain": "hydrothermal",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/scientific_overlays.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/scientific_overlays.gd:_build_plume_overlay/reload",
    "yellowstone_midway/scripts/world.gd:format_sidecar_block"
   ],
   "notes": "Python owns source/ambient temperature selection; final build data consistency remains a publication gate.",
   "sources": [
    "replay_plume2d"
   ]
  },
  {
   "id": "live_python_client",
   "label": "Live Python API and buffered playback",
   "domain": "observation",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/live_python_client.gd",
    "yellowstone_midway/scripts/python_river_replay.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/live_python_client.gd",
    "yellowstone_midway/scripts/python_river_replay.gd",
    "yellowstone_midway/scripts/world.gd"
   ],
   "notes": "Source wiring and applicable headless checks verified; no GPU, human visual or empirical acceptance claimed.",
   "sources": []
  },
  {
   "id": "simulation_controls",
   "label": "Conditions, time controls and located interventions",
   "domain": "observation",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/simulation_panel.gd",
    "yellowstone_midway/scripts/input_help.gd",
    "yellowstone_midway/project.godot",
    "yellowstone_midway/scripts/world.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/simulation_panel.gd",
    "yellowstone_midway/scripts/input_help.gd",
    "yellowstone_midway/project.godot",
    "yellowstone_midway/scripts/world.gd"
   ],
   "notes": "Source wiring and applicable headless checks verified; no GPU, human visual or empirical acceptance claimed.",
   "sources": []
  },
  {
   "id": "data_reload",
   "label": "Published data watcher and consumer manifest",
   "domain": "observation",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/data_watcher.gd",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/data/consumers.json"
   ],
   "evidence": [
    "yellowstone_midway/scripts/data_watcher.gd",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/data/consumers.json"
   ],
   "notes": "Source wiring and applicable headless checks verified; no GPU, human visual or empirical acceptance claimed.",
   "sources": []
  },
  {
   "id": "branch_compare",
   "label": "Marked A/B branches and measured display",
   "domain": "observation",
   "status": "rendered",
   "godot": [
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/scripts/simulation_panel.gd",
    "yellowstone_midway/scripts/thermal_probe_overlay.gd"
   ],
   "evidence": [
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/scripts/simulation_panel.gd",
    "yellowstone_midway/scripts/thermal_probe_overlay.gd"
   ],
   "notes": "Source wiring and applicable headless checks verified; no GPU, human visual or empirical acceptance claimed.",
   "sources": []
  }
 ],
 "docs": [
  {
   "id": "1",
   "file": "yellowstone_python_spec/fixes/fixes-1.md",
   "area": "E2",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-1.md",
   "counts": {
    "implemented": 35,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 1,
    "conflicts": 0
   },
   "items": 36,
   "targets": [
    "yellowstone_python/yellowstone_python/analysis_store.py",
    "yellowstone_python/yellowstone_python/aquatic_foodweb.py",
    "yellowstone_python/yellowstone_python/build.py",
    "yellowstone_python/yellowstone_python/canopy_census.py",
    "yellowstone_python/yellowstone_python/census_validate.py"
   ]
  },
  {
   "id": "2",
   "file": "yellowstone_python_spec/fixes/fixes-2.md",
   "area": "E1",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-2.md",
   "counts": {
    "implemented": 17,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 17,
   "targets": [
    "yellowstone_python/yellowstone_python/coupling.py",
    "yellowstone_python/yellowstone_python/equations.py",
    "yellowstone_python/yellowstone_python/compare.py",
    "yellowstone_python/yellowstone_python/claims.py"
   ]
  },
  {
   "id": "3",
   "file": "yellowstone_python_spec/fixes/fixes-3.md",
   "area": "E2",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-3.md",
   "counts": {
    "implemented": 25,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 25,
   "targets": [
    "yellowstone_python/yellowstone_python/fish.py",
    "yellowstone_python/yellowstone_python/gen_flora.py"
   ]
  },
  {
   "id": "4",
   "file": "yellowstone_python_spec/fixes/fixes-4.md",
   "area": "E2",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-4.md",
   "counts": {
    "implemented": 32,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 32,
   "targets": [
    "yellowstone_python/yellowstone_python/gen_trail_mask.py",
    "yellowstone_python/yellowstone_python/geochemistry.py",
    "yellowstone_python/yellowstone_python/grazers.py",
    "yellowstone_python/yellowstone_python/hydro_thermal.py",
    "yellowstone_python/tests/test_gen_trail_mask.py",
    "yellowstone_python/tests/test_geochemistry.py",
    "yellowstone_python/tests/test_grazers.py",
    "yellowstone_python/tests/test_hydro.py"
   ]
  },
  {
   "id": "5",
   "file": "yellowstone_python_spec/fixes/fixes-5.md",
   "area": "E2",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-5.md",
   "counts": {
    "implemented": 35,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 35,
   "targets": [
    "yellowstone_python/yellowstone_python/insects_birds.py",
    "yellowstone_python/yellowstone_python/llm_backend.py",
    "yellowstone_python/yellowstone_python/hydrology_provider.py",
    "yellowstone_python/yellowstone_python/microclimate.py",
    "yellowstone_python/tests/test_insects.py",
    "yellowstone_python/tests/test_llm_backend.py",
    "yellowstone_python/tests/test_hydrology_provider.py"
   ]
  },
  {
   "id": "5.5",
   "file": "yellowstone_python_spec/fixes/fixes-5.5.md",
   "area": "E2",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-5.5.md",
   "counts": {
    "implemented": 20,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 20,
   "targets": [
    "yellowstone_python/yellowstone_python/hydrology_provider.py",
    "yellowstone_python/yellowstone_python/llm_backend.py",
    "yellowstone_python/yellowstone_python/insects_birds.py",
    "yellowstone_python/yellowstone_python/microclimate.py"
   ]
  },
  {
   "id": "6",
   "file": "yellowstone_python_spec/fixes/fixes-6.md",
   "area": "E2",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-6.md",
   "counts": {
    "implemented": 40,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 40,
   "targets": [
    "yellowstone_python/yellowstone_python/microclimate.py",
    "yellowstone_python/yellowstone_python/overland_flow.py",
    "yellowstone_python/yellowstone_python/param_registry.py",
    "yellowstone_python/yellowstone_python/pool_crust.py",
    "yellowstone_python/tests/test_microclimate.py",
    "yellowstone_python/tests/test_param_registry.py"
   ]
  },
  {
   "id": "6.5",
   "file": "yellowstone_python_spec/fixes/fixes-6.5.md",
   "area": "E2",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-6.5.md",
   "counts": {
    "implemented": 5,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 5,
   "targets": [
    "yellowstone_python/yellowstone_python/microclimate.py",
    "yellowstone_python/yellowstone_python/overland_flow.py",
    "yellowstone_python/yellowstone_python/pool_crust.py",
    "yellowstone_python/tests/test_microclimate.py",
    "yellowstone_python/tests/test_overland.py",
    "yellowstone_python/tests/test_pools.py"
   ]
  },
  {
   "id": "7",
   "file": "yellowstone_python_spec/fixes/fixes-7.md",
   "area": "E1",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-7.md",
   "counts": {
    "implemented": 29,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 29,
   "targets": [
    "yellowstone_python/yellowstone_python/publish.py",
    "yellowstone_python/yellowstone_python/review_proposals.py",
    "yellowstone_python/yellowstone_python/run_mode.py",
    "yellowstone_python/yellowstone_python/snow_energy.py"
   ]
  },
  {
   "id": "8",
   "file": "yellowstone_python_spec/fixes/fixes-8.md",
   "area": "E2",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-8.md",
   "counts": {
    "implemented": 49,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 49,
   "targets": [
    "yellowstone_python/yellowstone_python/snow_season.py",
    "yellowstone_python/yellowstone_python/snow_validate.py",
    "yellowstone_python/yellowstone_python/study_mode.py",
    "yellowstone_python/yellowstone_python/vegetation.py"
   ]
  },
  {
   "id": "9",
   "file": "yellowstone_python_spec/fixes/fixes-9.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-9.md",
   "counts": {
    "implemented": 24,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 24,
   "targets": [
    "yellowstone_python/replay/obs_frame.py",
    "yellowstone_python/replay/obs_model.py",
    "yellowstone_python/replay/plume2d.py"
   ]
  },
  {
   "id": "10",
   "file": "yellowstone_python_spec/fixes/fixes-10.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-10.md",
   "counts": {
    "implemented": 29,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 29,
   "targets": [
    "yellowstone_python/yellowstone_python/replay/river_transport.py",
    "yellowstone_python/yellowstone_python/replay/river_world.py"
   ]
  },
  {
   "id": "11",
   "file": "yellowstone_python_spec/fixes/fixes-11.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-11.md",
   "counts": {
    "implemented": 29,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 29,
   "targets": [
    "yellowstone_python/replay/benchmarks.py",
    "yellowstone_python/replay/calibrate.py"
   ]
  },
  {
   "id": "12",
   "file": "yellowstone_python_spec/fixes/fixes-12.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-12.md",
   "counts": {
    "implemented": 36,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 1,
    "conflicts": 0
   },
   "items": 37,
   "targets": [
    "yellowstone_python/replay/datasets.py",
    "yellowstone_python/replay/figures.py",
    "yellowstone_python/replay/hydraulics.py",
    "yellowstone_python/replay/identifiability.py"
   ]
  },
  {
   "id": "13",
   "file": "yellowstone_python_spec/fixes/fixes-13.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-13.md",
   "counts": {
    "implemented": 27,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 27,
   "targets": [
    "yellowstone_python/replay/surface_flux.py",
    "yellowstone_python/replay/uncertainty.py"
   ]
  },
  {
   "id": "14",
   "file": "yellowstone_python_spec/fixes/fixes-14.md",
   "area": "G",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-14.md",
   "counts": {
    "implemented": 20,
    "shortcut": 0,
    "partial": 4,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 24,
   "targets": [
    "yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd",
    "yellowstone_atmosphere/scripts/weather_snapshot_reader.gd",
    "yellowstone_atmosphere/scripts/weather_http_consumer.gd",
    "yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader",
    "yellowstone_atmosphere/docs/integration_patch.md",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/scripts/yellowstone_atmosphere.gd",
    "yellowstone_midway/scripts/weather_snapshot_reader.gd",
    "yellowstone_midway/scripts/weather_http_consumer.gd",
    "yellowstone_midway/shaders/yellowstone_cloud_shell.gdshader",
    "yellowstone_midway/tools/test_sun_direction.gd",
    "yellowstone_midway/project.godot",
    "yellowstone_midway/scenes/main.tscn",
    "yellowstone_python/yellowstone_python/llm_backend.py",
    "yellowstone_python/yellowstone_python/replay/river_world.py",
    "yellowstone_python/yellowstone_python/microclimate.py"
   ]
  },
  {
   "id": "14.1",
   "file": "yellowstone_python_spec/fixes/fixes-14.1-weather-snapshot-reader_[implemented].md",
   "area": "G",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-14.1.md",
   "counts": {
    "implemented": 10,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 10,
   "targets": [
    "yellowstone_atmosphere/scripts/weather_snapshot_reader.gd",
    "yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/scenes/main.tscn"
   ]
  },
  {
   "id": "14.2",
   "file": "yellowstone_python_spec/fixes/fixes-14.2-weather_http_consumer.gd",
   "area": "G",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-14.2.md",
   "counts": {
    "implemented": 8,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 8,
   "targets": [
    "yellowstone_atmosphere/scripts/weather_http_consumer.gd",
    "yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_python/yellowstone_python/llm_backend.py"
   ]
  },
  {
   "id": "14.3",
   "file": "yellowstone_python_spec/fixes/fixes-14.3-yellowstone_atmosphere.md",
   "area": "G",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-14.3.md",
   "counts": {
    "implemented": 14,
    "shortcut": 0,
    "partial": 1,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 15,
   "targets": [
    "yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd",
    "yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader",
    "yellowstone_atmosphere/docs/integration_patch.md",
    "yellowstone_midway/scripts/yellowstone_atmosphere.gd",
    "yellowstone_midway/shaders/yellowstone_cloud_shell.gdshader",
    "yellowstone_midway/scripts/world.gd"
   ]
  },
  {
   "id": "14.4",
   "file": "yellowstone_python_spec/fixes/fixes-14.4-yellowstone_cloud_shell.gdshader",
   "area": "G",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-14.4.md",
   "counts": {
    "implemented": 10,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 10,
   "targets": [
    "yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader",
    "yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd",
    "yellowstone_midway/shaders/yellowstone_cloud_shell.gdshader",
    "yellowstone_midway/scripts/yellowstone_atmosphere.gd"
   ]
  },
  {
   "id": "14.5",
   "file": "yellowstone_python_spec/fixes/fixes-14.5-riverworld.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-14.5.md",
   "counts": {
    "implemented": 16,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 16,
   "targets": [
    "yellowstone_python/yellowstone_python/replay/river_world.py",
    "yellowstone_python/yellowstone_python/replay/river_transport.py",
    "yellowstone_python/yellowstone_python/time_utils.py",
    "yellowstone_python/yellowstone_python/build.py",
    "yellowstone_python/yellowstone_python/microclimate.py"
   ]
  },
  {
   "id": "14.6",
   "file": "yellowstone_python_spec/fixes/fixes-14.6-river_transport-1.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-14.6.md",
   "counts": {
    "implemented": 15,
    "shortcut": 0,
    "partial": 0,
    "missing": 1,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 16,
   "targets": [
    "yellowstone_python/yellowstone_python/replay/river_transport.py",
    "yellowstone_python/yellowstone_python/replay/surface_flux.py",
    "yellowstone_python/yellowstone_python/replay/tests/test_river_transport.py"
   ]
  },
  {
   "id": "14.6.2",
   "file": "yellowstone_python_spec/fixes/fixes-14.6.2-river_transport-2.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-14.6.2.md",
   "counts": {
    "implemented": 16,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 16,
   "targets": [
    "yellowstone_python/yellowstone_python/replay/river_transport.py",
    "yellowstone_python/yellowstone_python/replay/surface_flux.py",
    "yellowstone_python/yellowstone_python/replay/tests/test_river_transport.py (grepped)"
   ]
  },
  {
   "id": "14.6.3",
   "file": "yellowstone_python_spec/fixes/fixes-14.6.3-river_transport-3.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-14.6.3.md",
   "counts": {
    "implemented": 12,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 12,
   "targets": [
    "yellowstone_python/yellowstone_python/replay/river_transport.py",
    "yellowstone_python/yellowstone_python/replay/tests/test_river_transport.py (grepped)"
   ]
  },
  {
   "id": "14.6.4",
   "file": "yellowstone_python_spec/fixes/fixes-14.6.4-river_transport-4.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-14.6.4.md",
   "counts": {
    "implemented": 16,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 16,
   "targets": [
    "yellowstone_python/yellowstone_python/replay/river_transport.py",
    "yellowstone_python/yellowstone_python/replay/surface_flux.py",
    "yellowstone_python/yellowstone_python/replay/tests/test_river_transport.py (grepped)"
   ]
  },
  {
   "id": "15",
   "file": "yellowstone_python_spec/fixes/fixes-15-calibration-1.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-15-calibration-1.md",
   "counts": {
    "implemented": 15,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 15,
   "targets": [
    "yellowstone_python/replay/calibrate.py",
    "yellowstone_python/replay/surface_flux.py",
    "yellowstone_python/replay/river_transport.py",
    "yellowstone_python/param_registry.py (reference)",
    "yellowstone_python/claims.py (reference)"
   ]
  },
  {
   "id": "15.2",
   "file": "yellowstone_python_spec/fixes/fixes-15.2-calibration-2.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-15.2-calibration-2.md",
   "counts": {
    "implemented": 15,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 15,
   "targets": [
    "yellowstone_python/replay/calibrate.py",
    "yellowstone_python/replay/surface_flux.py",
    "yellowstone_python/replay/river_transport.py"
   ]
  },
  {
   "id": "16",
   "file": "yellowstone_python_spec/fixes/fixes-16-microclimate.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-16-microclimate.md",
   "counts": {
    "implemented": 8,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 8,
   "targets": [
    "yellowstone_python/yellowstone_python/microclimate.py",
    "yellowstone_python/tests/test_microclimate.py"
   ]
  },
  {
   "id": "17",
   "file": "yellowstone_python_spec/fixes/fixes-17-surface_flux.md",
   "area": "R",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-17-surface_flux.md",
   "counts": {
    "implemented": 16,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 16,
   "targets": [
    "yellowstone_python/replay/surface_flux.py",
    "yellowstone_python/replay/river_transport.py",
    "yellowstone_python/replay/calibrate.py",
    "yellowstone_python/microclimate.py",
    "yellowstone_python/replay/tests/test_surface_flux.py"
   ]
  },
  {
   "id": "18",
   "file": "yellowstone_python_spec/fixes/fixes-18-overland.md",
   "area": "D",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-18-overland.md",
   "counts": {
    "implemented": 15,
    "shortcut": 0,
    "partial": 1,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 16,
   "targets": [
    "yellowstone_python/overland_flow.py",
    "yellowstone_python/overland_provider.py",
    "yellowstone_python/replay/river_transport.py",
    "yellowstone_python/replay/river_world.py (parse_upstream_discharge)",
    "yellowstone_python/tests/test_overland.py",
    "yellowstone_python/tests/test_overland_provider.py",
    "yellowstone_python/tests/test_catchment_runoff.py"
   ]
  },
  {
   "id": "19",
   "file": "yellowstone_python_spec/fixes/fixes-19-tributaries.md",
   "area": "D",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-19.md",
   "counts": {
    "implemented": 19,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 19,
   "targets": [
    "yellowstone_python/tools/run_hot_lowflow_with_tributaries_v2.py",
    "yellowstone_python/tools/fetch_yellowstone_tributaries.py",
    "yellowstone_python/tools/channel_geometry.py"
   ]
  },
  {
   "id": "20",
   "file": "yellowstone_python_spec/fixes/fixes-20-usgs_nwis.md",
   "area": "D",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-20.md",
   "counts": {
    "implemented": 17,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 17,
   "targets": [
    "yellowstone_python/tools/usgs_nwis.py",
    "../../ystone-fixed-scripts/usgs_nwis.py"
   ]
  },
  {
   "id": "21",
   "file": "yellowstone_python_spec/fixes/fixes-21-fetch-scripts.md",
   "area": "D",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-21.md",
   "counts": {
    "implemented": 25,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 25,
   "targets": [
    "yellowstone_python/tools/fetch_firehole_obs.py",
    "yellowstone_python/tools/fetch_met_forcing.py",
    "yellowstone_python/tools/fetch_snotel_obs.py"
   ]
  },
  {
   "id": "22",
   "file": "yellowstone_python_spec/fixes/fixes-22-check-terrain.md",
   "area": "D",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-22.md",
   "counts": {
    "implemented": 14,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 14,
   "targets": [
    "tools/check_terrain.py",
    "yellowstone_python/build.py"
   ]
  },
  {
   "id": "23",
   "file": "yellowstone_python_spec/fixes/fixes-23-build.md",
   "area": "E1",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-23.md",
   "counts": {
    "implemented": 26,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 26,
   "targets": [
    "yellowstone_python/build.py",
    "yellowstone_python/validation/checks.py",
    "derived/261e10030b24/BUILD.json"
   ]
  },
  {
   "id": "24",
   "file": "yellowstone_python_spec/fixes/fixes-24-coupling_equations.md",
   "area": "E1",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-24.md",
   "counts": {
    "implemented": 20,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 20,
   "targets": [
    "yellowstone_python/coupling.py",
    "yellowstone_python/equations.py",
    "yellowstone_python/build.py",
    "yellowstone_python/validation/checks.py"
   ]
  },
  {
   "id": "25",
   "file": "yellowstone_python_spec/fixes/fixes-25-claims_compare.md",
   "area": "E1",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-25.md",
   "counts": {
    "implemented": 19,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 19,
   "targets": [
    "yellowstone_python/claims.py",
    "yellowstone_python/compare.py",
    "yellowstone_python/build.py",
    "derived/261e10030b24/BUILD.json"
   ]
  },
  {
   "id": "26",
   "file": "yellowstone_python_spec/fixes/fixes-26-analysis-store-sqlite.md",
   "area": "E2",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-26.md",
   "counts": {
    "implemented": 15,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 15,
   "targets": [
    "yellowstone_python/yellowstone_python/analysis_store.py",
    "tools/build_store.py",
    "yellowstone_python/yellowstone_python/llm_backend.py",
    "tests/test_analysis_store.py"
   ]
  },
  {
   "id": "27",
   "file": "yellowstone_python_spec/fixes/fixes-27-thermal-groundwater-common.md",
   "area": "E1",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-27.md",
   "counts": {
    "implemented": 15,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 15,
   "targets": [
    "yellowstone_python/yellowstone_python/thermal_curves.py"
   ]
  },
  {
   "id": "28",
   "file": "yellowstone_python_spec/fixes/fixes-28-exporters-validation-reference.md",
   "area": "E1",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-28.md",
   "counts": {
    "implemented": 7,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 7,
   "targets": [
    "yellowstone_python/exporters/to_ecosystem.py",
    "yellowstone_python/exporters/to_map.py",
    "yellowstone_python/validation/checks.py",
    "yellowstone_python/replay/fipy_reference.py",
    "yellowstone_python/replay/nc_export.py"
   ]
  },
  {
   "id": "29",
   "file": "yellowstone_python_spec/fixes/fixes-29-tooling-gates.md",
   "area": "D",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-29.md",
   "counts": {
    "implemented": 8,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 8,
   "targets": [
    "yellowstone_python/tools/audit_provenance.py",
    "yellowstone_python/tools/compare_bundles.py",
    "yellowstone_python/tools/validate_obs_bundles.py",
    "yellowstone_python/tools/plot_fit.py",
    "yellowstone_python/tools/execute_notebook.py",
    "yellowstone_python/tools/build_store.py"
   ]
  },
  {
   "id": "30",
   "file": "yellowstone_python_spec/fixes/fixes-30-scenario-runners.md",
   "area": "D",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-30.md",
   "counts": {
    "implemented": 15,
    "shortcut": 0,
    "partial": 1,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 16,
   "targets": [
    "yellowstone_python/tools/run_hot_lowflow.py",
    "yellowstone_python/tools/run_hot_lowflow_tributary_refuge.py",
    "yellowstone_python/tools/run_hot_lowflow_with_tributaries.py"
   ]
  },
  {
   "id": "31",
   "file": "yellowstone_python_spec/fixes/fixes-31-hydrosim.md",
   "area": "D",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-31.md",
   "counts": {
    "implemented": 15,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 15,
   "targets": [
    "hydrology/hydrosim.py",
    "hydrology/validate_hydrosim.py",
    "hydrology/demo_hydrosim.py",
    "hydrology/godot_hydro_node.py"
   ]
  },
  {
   "id": "32",
   "file": "yellowstone_python_spec/fixes/fixes-32-comment-style.md",
   "area": "E1",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-32.md",
   "counts": {
    "implemented": 2,
    "shortcut": 0,
    "partial": 1,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 3,
   "targets": [
    "yellowstone_python/AGENTS.md",
    "yellowstone_python/tools/check_comment_style.py"
   ]
  },
  {
   "id": "33",
   "file": "yellowstone_python_spec/fixes/fixes-33-cross-domain-wiring.md",
   "area": "E1",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-33.md",
   "counts": {
    "implemented": 13,
    "shortcut": 0,
    "partial": 1,
    "missing": 1,
    "superseded": 2,
    "conflicts": 0
   },
   "items": 17,
   "targets": [
    "yellowstone_python/yellowstone_python/insects_birds.py",
    "yellowstone_python/yellowstone_python/aquatic_foodweb.py",
    "yellowstone_python/yellowstone_python/fish.py"
   ]
  },
  {
   "id": "34",
   "file": "yellowstone_python_spec/fixes/fixes-34-world-environment.md",
   "area": "G",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-34.md",
   "counts": {
    "implemented": 6,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 6,
   "targets": [
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/scripts/height_field.gd",
    "yellowstone_midway/scripts/map_view.gd",
    "yellowstone_midway/scripts/authored_placement.gd",
    "yellowstone_midway/tools/validate_atmosphere_canonical.gd"
   ]
  },
  {
   "id": "35",
   "file": "yellowstone_python_spec/fixes/fixes-35-ecosystem-replay.md",
   "area": "G",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-35.md",
   "counts": {
    "implemented": 7,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 7,
   "targets": [
    "yellowstone_midway/scripts/ecosystem.gd",
    "yellowstone_midway/scripts/python_river_replay.gd",
    "yellowstone_midway/scripts/pool_overlay.gd",
    "yellowstone_midway/scripts/thermal_probe_overlay.gd"
   ]
  },
  {
   "id": "36",
   "file": "yellowstone_python_spec/fixes/fixes-36-wildlife-player.md",
   "area": "G",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-36.md",
   "counts": {
    "implemented": 7,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 7,
   "targets": [
    "yellowstone_midway/scripts/wildlife_actor.gd",
    "yellowstone_midway/scripts/player.gd"
   ]
  },
  {
   "id": "37",
   "file": "yellowstone_python_spec/fixes/fixes-37-shaders.md",
   "area": "G",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-37.md",
   "counts": {
    "implemented": 7,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 7,
   "targets": [
    "yellowstone_midway/shaders/boardwalk.gdshader",
    "yellowstone_midway/shaders/foliage.gdshader",
    "yellowstone_midway/shaders/steam.gdshader",
    "yellowstone_midway/shaders/terrain.gdshader",
    "yellowstone_midway/shaders/thermal_apron.gdshader",
    "yellowstone_midway/shaders/trail.gdshader",
    "yellowstone_midway/shaders/water.gdshader"
   ]
  },
  {
   "id": "38",
   "file": "yellowstone_python_spec/fixes/fixes-38-tools-validators.md",
   "area": "G",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-38.md",
   "counts": {
    "implemented": 9,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 9,
   "targets": [
    "yellowstone_midway/tools/bake_botany.gd",
    "yellowstone_midway/tools/bake_world.gd",
    "yellowstone_midway/tools/inspect_fauna_glb.gd",
    "yellowstone_midway/tools/recolor_goose_texture.gd",
    "yellowstone_midway/tools/render_fauna_preview.gd",
    "yellowstone_midway/tools/validate_baked.gd",
    "yellowstone_midway/tools/validate_ecology.gd",
    "yellowstone_midway/tools/validate_multimesh.gd",
    "yellowstone_midway/tools/validate_walk.gd",
    "yellowstone_midway/tools/prepare_world.py",
    "yellowstone_midway/tools/validate_world.py"
   ]
  },
  {
   "id": "39",
   "file": "yellowstone_python_spec/fixes/fixes-39-rendering-gaps.md",
   "area": "G",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-39.md",
   "counts": {
    "implemented": 11,
    "shortcut": 0,
    "partial": 2,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 13,
   "targets": [
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/shaders/water.gdshader",
    "yellowstone_midway/shaders/terrain.gdshader"
   ]
  },
  {
   "id": "40",
   "file": "yellowstone_python_spec/fixes/fixes-40-microbial-mats-and-thermal-core-terrain.md",
   "area": "N",
   "ledger": null,
   "counts": {
    "implemented": 0,
    "shortcut": 0,
    "partial": 0,
    "missing": 7,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 7,
   "targets": []
  },
  {
   "id": "41",
   "file": "yellowstone_python_spec/fixes/fixes-41-missing-couplings-and-species.md",
   "area": "N",
   "ledger": null,
   "counts": {
    "implemented": 0,
    "shortcut": 0,
    "partial": 0,
    "missing": 12,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 12,
   "targets": []
  },
  {
   "id": "42",
   "file": "yellowstone_python_spec/fixes/fixes-42-render-surfaces-flora-and-outflow-forcing.md",
   "area": "N",
   "ledger": null,
   "counts": {
    "implemented": 0,
    "shortcut": 0,
    "partial": 0,
    "missing": 9,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 9,
   "targets": []
  },
  {
   "id": "43",
   "file": "yellowstone_python_spec/fixes/fixes-43-live-simulation-service.md",
   "area": "N",
   "ledger": null,
   "counts": {
    "implemented": 0,
    "shortcut": 0,
    "partial": 0,
    "missing": 15,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 15,
   "targets": []
  },
  {
   "id": "44",
   "file": "yellowstone_python_spec/fixes/fixes-44-godot-live-state-and-transitions.md",
   "area": "N",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-44.md",
   "counts": {
    "implemented": 14,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 14,
   "targets": [
    "yellowstone_atmosphere/scripts/weather_http_consumer.gd",
    "yellowstone_atmosphere/scripts/weather_snapshot_reader.gd",
    "yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd",
    "yellowstone_midway/data/asset_manifest.json",
    "yellowstone_midway/data/consumers.json",
    "yellowstone_midway/project.godot",
    "yellowstone_midway/scripts/data_watcher.gd",
    "yellowstone_midway/scripts/ecosystem.gd",
    "yellowstone_midway/scripts/live_python_client.gd",
    "yellowstone_midway/scripts/python_river_replay.gd",
    "yellowstone_midway/scripts/scientific_overlays.gd",
    "yellowstone_midway/scripts/simulation_panel.gd",
    "yellowstone_midway/scripts/weather_snapshot_reader.gd",
    "yellowstone_midway/scripts/wildlife_actor.gd",
    "yellowstone_midway/scripts/world.gd",
    "yellowstone_midway/scripts/yellowstone_atmosphere.gd",
    "yellowstone_midway/tests/feeding-fixture.json",
    "yellowstone_midway/tools/fish_swim.py",
    "yellowstone_midway/tools/prepare_swimming_trout.py"
   ]
  },
  {
   "id": "45",
   "file": "yellowstone_python_spec/fixes/fixes-45-player-controls.md",
   "area": "N",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-45.md",
   "counts": {
    "implemented": 10,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 10,
   "targets": [
    "yellowstone_midway/project.godot",
    "yellowstone_midway/scripts/input_help.gd",
    "yellowstone_midway/scripts/live_python_client.gd",
    "yellowstone_midway/scripts/player.gd",
    "yellowstone_midway/scripts/python_river_replay.gd",
    "yellowstone_midway/scripts/simulation_panel.gd",
    "yellowstone_midway/scripts/thermal_probe_overlay.gd",
    "yellowstone_midway/scripts/world.gd"
   ]
  },
  {
   "id": "46",
   "file": "yellowstone_python_spec/fixes/fixes-46-shared-helpers-and-site-constants.md",
   "area": "N",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-46.md",
   "counts": {
    "implemented": 9,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 9,
   "targets": [
    "yellowstone_python/tools/calibrate_river_transport.py",
    "yellowstone_python/yellowstone_python/atmosphere/microclimate.py",
    "yellowstone_python/yellowstone_python/cli/calibrate.py",
    "yellowstone_python/yellowstone_python/common/checks.py",
    "yellowstone_python/yellowstone_python/common/coords.py",
    "yellowstone_python/yellowstone_python/common/io.py",
    "yellowstone_python/yellowstone_python/common/site.py",
    "yellowstone_python/yellowstone_python/common/units.py",
    "yellowstone_python/yellowstone_python/exporters/godot_sidecars.py",
    "yellowstone_python/yellowstone_python/river/calibrate.py",
    "yellowstone_python/yellowstone_python/river/obs_model.py",
    "yellowstone_python/yellowstone_python/service/llm_backend.py"
   ]
  },
  {
   "id": "47",
   "file": "yellowstone_python_spec/fixes/fixes-47-package-layout-and-module-consolidation.md",
   "area": "N",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-47.md",
   "counts": {
    "implemented": 8,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 8,
   "targets": [
    "dashboard/build_data.py",
    "yellowstone_python/AGENTS.md",
    "yellowstone_python/README.md",
    "yellowstone_python/data/census_validation/sampling_plan.json",
    "yellowstone_python/notebooks/reach_fit.ipynb",
    "yellowstone_python/pyproject.toml",
    "yellowstone_python/tests/river/test_river_transport.py",
    "yellowstone_python/tests/test_package_layout.py",
    "yellowstone_python/tests/test_pipeline.py",
    "yellowstone_python/tests/test_scenario_runners.py",
    "yellowstone_python/tools/hot_lowflow.py",
    "yellowstone_python/yellowstone_python/authoring/gen_flora.py",
    "yellowstone_python/yellowstone_python/cli/calibrate.py",
    "yellowstone_python/yellowstone_python/cli/gen_flora.py",
    "yellowstone_python/yellowstone_python/cli/river_transport.py",
    "yellowstone_python/yellowstone_python/common/site.py",
    "yellowstone_python/yellowstone_python/common/units.py",
    "yellowstone_python/yellowstone_python/land/hydrosim_loader.py",
    "yellowstone_python/yellowstone_python/observations/bundles.py",
    "yellowstone_python/yellowstone_python/observations/met.py",
    "yellowstone_python/yellowstone_python/observations/tributaries.py",
    "yellowstone_python/yellowstone_python/observations/usgs.py",
    "yellowstone_python/yellowstone_python/pipeline/pipeline.py",
    "yellowstone_python/yellowstone_python/river/README.md",
    "yellowstone_python/yellowstone_python/scenarios/hot_lowflow.py",
    "yellowstone_python/yellowstone_python/validation/contracts.py",
    "yellowstone_python/yellowstone_python/validation/terrain.py"
   ]
  },
  {
   "id": "48",
   "file": "yellowstone_python_spec/fixes/fixes-48-public-repository-hygiene.md",
   "area": "N",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-48.md",
   "counts": {
    "implemented": 7,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 7,
   "targets": [
    "CITATION.cff",
    "LICENSE",
    "README.md",
    "dashboard/deploy.sh",
    "yellowstone_python/.gitignore",
    "yellowstone_python/.pre-commit-config.yaml",
    "yellowstone_python/AGENTS.md",
    "yellowstone_python/LICENSE",
    "yellowstone_python/README.md",
    "yellowstone_python/pyproject.toml",
    "yellowstone_python/tests/test_fetch_yellowstone_tributaries.py",
    "yellowstone_python/tests/test_public_export.py",
    "yellowstone_python/tests/test_repository_style.py",
    "yellowstone_python/tools/export_public.py",
    "yellowstone_python/yellowstone_python/observations/bundles.py",
    "yellowstone_python/yellowstone_python/river/README.md",
    "yellowstone_python_spec/fixes/fixes-48-public-repository-hygiene.md",
    "yellowstone_python_spec/internal/python/HANDOFF.md",
    "yellowstone_python_spec/internal/python/fixtures/met_seed.json",
    "yellowstone_python_spec/internal/python/progress.md"
   ]
  },
  {
   "id": "49",
   "file": "yellowstone_python_spec/fixes/fixes-49-comment-and-docstring-house-style.md",
   "area": "N",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-49.md",
   "counts": {
    "implemented": 7,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 7,
   "targets": [
    "yellowstone_python/AGENTS.md",
    "yellowstone_python/tests/test_check_comment_style.py",
    "yellowstone_python/tests/test_equations.py",
    "yellowstone_python/tests/test_repository_style.py",
    "yellowstone_python/tests/test_stressor_integration.py",
    "yellowstone_python/tools/check_comment_style.py",
    "yellowstone_python/yellowstone_python/aquatic/aquatic_foodweb.py",
    "yellowstone_python/yellowstone_python/aquatic/fish.py"
   ]
  },
  {
   "id": "50",
   "file": "yellowstone_python_spec/fixes/fixes-50-test-suite-consistency.md",
   "area": "N",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-50.md",
   "counts": {
    "implemented": 7,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 7,
   "targets": [
    "yellowstone_python/README.md",
    "yellowstone_python/pyproject.toml",
    "yellowstone_python/tests/aquatic/test_aquatic_foodweb.py",
    "yellowstone_python/tests/aquatic/test_thermal_curves.py",
    "yellowstone_python/tests/conftest.py",
    "yellowstone_python/tests/river/test_river_transport.py",
    "yellowstone_python/tests/river/test_solute_transport.py",
    "yellowstone_python/tests/test_build.py",
    "yellowstone_python/tests/test_catchment_runoff.py",
    "yellowstone_python/tests/test_fetch_yellowstone_tributaries.py",
    "yellowstone_python/tests/test_reach_notebook.py",
    "yellowstone_python/tests/test_scenario_runners.py",
    "yellowstone_python/tests/test_stressor_integration.py"
   ]
  },
  {
   "id": "51",
   "file": "yellowstone_python_spec/fixes/fixes-51-forest-density-tree-form-and-fish-models.md",
   "area": "N",
   "ledger": null,
   "counts": {
    "implemented": 0,
    "shortcut": 0,
    "partial": 0,
    "missing": 6,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 6,
   "targets": []
  },
  {
   "id": "52",
   "file": "yellowstone_python_spec/fixes/fixes-52-terrain-materials-and-shadow-quality.md",
   "area": "N",
   "ledger": "yellowstone_python_spec/fixes/ledger/fixes-52.md",
   "counts": {
    "implemented": 8,
    "shortcut": 0,
    "partial": 0,
    "missing": 0,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 8,
   "targets": []
  },
  {
   "id": "53",
   "file": "yellowstone_python_spec/fixes/fixes-53-lidar-canopy-and-tree-count-sources.md",
   "area": "N",
   "ledger": null,
   "counts": {
    "implemented": 0,
    "shortcut": 0,
    "partial": 0,
    "missing": 6,
    "superseded": 0,
    "conflicts": 0
   },
   "items": 6,
   "targets": []
  }
 ],
 "totals": {
  "components": {
   "rendered": 28,
   "python_only": 27,
   "partial_unwired": 25,
   "not_started": 45,
   "next_phase": 30
  },
  "couplings": {
   "wired": 46,
   "partial": 4,
   "missing": 0,
   "proposed": 64
  },
  "rendering": {
   "rendered": 34,
   "python_only": 0,
   "partial_unwired": 1,
   "not_started": 0,
   "next_phase": 0
  },
  "verdicts": {
   "implemented": 985,
   "shortcut": 0,
   "partial": 11,
   "missing": 57,
   "superseded": 4,
   "conflicts": 0
  },
  "fix_items": 1057
 }
};
