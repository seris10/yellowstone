Fixes applied: fixes-6.md COMPLETE (microclimate.py was already done; this session finished overland_flow.py, param_registry.py, pool_crust.py). fixes-8.md COMPLETE for the modules in scope (snow_season.py, snow_validate.py, study_mode.py, vegetation.py).

A concurrent session also edited this workspace (commit 2022995 "Yellowstone Python scientific stack: verified replay solver, calibration, coupling, providers") and added overland_provider.py, groundwater_provider.py, hydrology_provider.py plus their tests. Those provider modules are outside this handoff's scope; they pass.

Regression fixes required before any new work (all found by running the suite, not the spec):
- vegetation.py:242 infinite loop: the coarsening while-loop never recomputed per_row, so any proposal over the grid budget hung the process and froze the whole test run. per_row is now recomputed inside the loop.
- build.py:264 and llm_backend.py:197 still imported load_real_weather after microclimate.py was renamed; every build and the /api/weather endpoint died with ImportError. Now load_weather_bundle.
- llm_backend.weather(): round(float(None)) crashed when the bundle carried no precipitation; missing stays None.
- snow_season.step_snow returns a 6-tuple (thermal attribution added earlier); the annotation, snow_energy.py:119, and three tests still unpacked 5.
- analysis_store.ingest_census raised on duplicate stable_id, defeating the upsert that test_duplicate_stable_id_leaves_no_stale_rtree asserts.
- analysis_store.ingest_replay ran DELETE FROM replay_cells/replay_frames AFTER inserting cells, leaving replay_cells empty in every store.
- snow_validate.validate_site referenced an out-of-scope name `bundle` in its provenance string: every fit run raised NameError. bundle is now a parameter, passed by run_validation.

Files edited with absolute paths:
yellowstone/yellowstone_python/yellowstone_python/vegetation.py
yellowstone/yellowstone_python/yellowstone_python/overland_flow.py
yellowstone/yellowstone_python/yellowstone_python/param_registry.py
yellowstone/yellowstone_python/yellowstone_python/pool_crust.py
yellowstone/yellowstone_python/yellowstone_python/snow_validate.py
yellowstone/yellowstone_python/yellowstone_python/snow_energy.py
yellowstone/yellowstone_python/yellowstone_python/study_mode.py
yellowstone/yellowstone_python/yellowstone_python/build.py
yellowstone/yellowstone_python/yellowstone_python/llm_backend.py
yellowstone/yellowstone_python/yellowstone_python/analysis_store.py
yellowstone/yellowstone_python/tests/test_overland.py (new)
yellowstone/yellowstone_python/tests/test_param_registry.py
yellowstone/yellowstone_python/tests/test_pools.py
yellowstone/yellowstone_python/tests/test_snow.py
yellowstone/yellowstone_python/tests/test_snow_validate.py
yellowstone/yellowstone_python/tests/test_study.py
yellowstone/yellowstone_python/tests/test_vegetation.py

What landed for fixes-6:
- overland_flow: the soil argument now drives a uniform soil map (names=[soil]) and raises on an unknown texture; _downsample is a validated block-mean that covers the whole source extent (1025 to 256 keeps the trailing row/column); rain/dt/sim/grid/cell/soil validated finite and in range; a trailing partial step absorbs a non-divisible sim_s and the result reports the seconds actually simulated; hydrosim import records which implementation was loaded and no longer grows sys.path; numpy is a declared dependency imported at module top; unused terrain_fns call removed; a configuration block records effective settings (infiltration, manning, ET, perc_factor, init_wetness, max_substeps, source DEM dims, downsampling, soil); a non-finite balance returns status balance_invalid.
- param_registry: validate_entry requires nonempty strings for every field, checks param_id segments, checks review against claims.REVIEW_STATUSES, rejects comma-joined units; registry_errors reads ids with .get so a malformed entry cannot raise KeyError; optional source_refs {path,key,expected} with source_ref_errors(configs) cross-checks claims against configs/baseline.yaml; hydro.excelsior_outflow split into discharge and temperature records and fish.THERMAL_SPECIES.anchors renamed with units C.
- pool_crust: buffering uses shapely when present and otherwise reports radial_expansion_from_centroid_approximation_not_guaranteed (the previous label and its conservatism claim are gone); render_apron_tiles fills the apron (255) under the mapped water (200); _validate_ring and depth_at/radial_temp validation refuse short, non-finite, duplicate, zero-radius and shelf_mult<=1 inputs; make_ramp_stops is pure and returns stops plus ramp_params with fractions clamped to [0,1.3] and validate_ramp_stops; shell records mapped_area_m2 and area_disagreement_pct from a shoelace area; outflow_channel comes from OUTFLOW_CHANNELS keyed by pool source_id; render_ramp refuses w<2 and creates its parent directory; render_cross_section writes a <path>.meta.json stating the plate is radial on circular-equivalent radii.

What landed for fixes-8:
- snow_validate: fit_snow_params returns a dict with grid, candidate count, tie rule, tie count and scored sample count (first-wins on ties is now recorded, not hidden); peak_timing_error_days validates ISO dates, equal lengths and missing values; peak_timing_on_observed excludes missing observation days and reports rows used; train/holdout scored counts and missing_obs_n reported next to index counts; load_fixed_params refuses non-mapping documents, missing keys, non-finite values and k values off the fit grid; evaluate_fixed_params keeps missing observations missing, reports holdout_scored_n, missing_obs_n and unused_fixed_triplets; SPINUP_THRESHOLD_MM is a module constant.
- study_mode: ALLOWED_PREFIXES now enforces what may change (every SCHEMA key and every preset key is checked); preset_errors() validates all presets including lateral records; _validate_lateral refuses missing ids, non-numeric or negative flow, non-finite temperature; apply_preset refuses to overwrite a tributary defined with different values and inserts links idempotently; the exclusive-bound handling is one branch.
- vegetation: load_terrain and terrain_fns refuse wrong shape and NaN/inf, and the clamped edge behavior of sample/slope_deg is documented; habitat_moisture_at gives one nearest-patch selection shared by moisture_at and render_suitability_png; render_suitability_png validates guild, size, bbox ordering and canopy and creates its output directory; patch_step validates dt_s, biomass, capacity, growth rate, grazer rate and duplicate patch ids, and its docstring states the demand unit.

Verification:
PYTHONPATH=yellowstone/yellowstone_python python3 -m pytest tests/ -q   -> 403 passed, 2 skipped (flopy, landlab absent)
PYTHONPATH=yellowstone/yellowstone_python python3 -m yellowstone_python.build --config configs/baseline.yaml -> passed=True
PYTHONPATH=yellowstone/yellowstone_python python3 tools/audit_provenance.py --dir derived -> 2 pre-existing failures, sinter_grass_cull.json and sinter_tree_cull.json carry no status; both are dated Oct 9 artifacts and derived/ is history, so they were left alone.

Known open items:
- start_index in propose_plantings is still legacy-only: reviewed IDs are cell-derived (prop_guild_seed_col_row), so the renumbering branch rarely triggers. The audit allows documenting this or removing the parameter.
- The audit gap above, plus the racy test_compare_quantiques_ab that picked the newest derived/ directory even when a build was still writing into it (now selects the newest complete build).
- A concurrent session is active in this workspace; check git status and the file mtimes before editing shared modules.

Decisions made: missing observations stay None and are excluded from scoring with explicit counts; peak timing over days with observations; k_melt first-wins ties recorded in the artifact rather than hidden; the buffer fallback is labeled an approximation rather than called conservative; ramp stops are clamped and returned without mutating the shell; outflow links are keyed by pool source_id; compound units are split into separate parameter records; review vocabulary is imported from claims.py; structural validators reject booleans for numeric fields; nearest-patch selection is shared between proposals and rendering; numeric literals stay in SI.