# fixes-1 ledger
Doc: fixes/fixes-1.md | read 2026-10-12, open rows re-verified 2026-10-13 | targets: yellowstone_python/yellowstone_python/analysis_store.py sha256:9381f52493a8 ; yellowstone_python/yellowstone_python/aquatic_foodweb.py sha256:ed265ea3ec2e ; yellowstone_python/yellowstone_python/build.py sha256:65d9b0265537 ; yellowstone_python/yellowstone_python/canopy_census.py sha256:9e98b6dd17a7 ; yellowstone_python/yellowstone_python/census_validate.py sha256:6188e19ec58e
Summary: 36 items: 35 implemented, 0 shortcut, 0 partial, 0 missing, 1 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1.A | clear replay tables (or PK) before ingestion to prevent stale frames | implemented | analysis_store.py:81-83,183-184 | `DELETE FROM replay_frames/cells` plus `PRIMARY KEY (t_s, cell_id)`; savepoint/transaction extra not added | cheap |
| 1.B | reject duplicate stable_id in census ingest | superseded | analysis_store.py:139-170 | duplicate stable_id now uses last-write-wins REPLACE semantics with paired R-tree row deletion; see test_duplicate_stable_id_leaves_no_stale_rtree | cheap |
| 1.C | finite-number validation across all numeric ingestion paths | implemented | analysis_store.py:ingest_firehole,ingest_snotel,ingest_census,ingest_replay | `_finite_float` now applied to usgs epoch/discharge/temperature (allow_none) and snotel WTEQ/PRCP/SNWD/TAVG/TMAX/TMIN; census and replay paths already validated | medium |
| 1.D | enforce read-only connections (query_only + file:...?mode=ro) | implemented | analysis_store.py:456-466 | path reads use `mode=ro` plus `PRAGMA query_only=ON`; caller-supplied conn also forced query_only | cheap |
| 1.E | deterministic ORDER BY in every query path | implemented | analysis_store.py:600,608 | spatial path orders by stable_id; non-spatial path has per-table order_col default rowid | cheap |
| 1.F | validate SNOTEL ISO date on ingestion | implemented | analysis_store.py:240-242 | `datetime.date.fromisoformat(day)` raises `ValueError` on malformed dates | cheap |
| 1.G | atomic build_file write with cleanup and durability | implemented | analysis_store.py:build_file | tmp sqlite -> fsync(tmp) -> re-check `out.exists()` to defend against racers -> `tmp.replace(out)` -> fsync parent directory; stale tmp cleared before writing | medium |
| 2.A | partial final step so simulated duration matches requested days | implemented | aquatic_foodweb.py:run_foodweb output | returned document now includes `simulated_days` (float) and `steps` (int) alongside `days` so consumers see actual integrated duration | cheap |
| 2.B | validate frame shape and finite temperatures in thermal_landscape | implemented | aquatic_foodweb.py:110-125 | validates `t_s`, `temperature_c` list length, finiteness, and `t_min_s<=t_max_s` | cheap |
| 2.C | reject NaN/infinite inputs to run_foodweb and bound `cover` | implemented | aquatic_foodweb.py:277-290 | `_positive_finite` for days/dt_days/ne_turnover_days plus explicit `cover` finite+[0,1] check | cheap |
| 2.D | document single-cell foraging scope and movement assumptions | implemented | aquatic_foodweb.py:462-464 | provenance block adds `foraging_scope`, `movement_cost`, `unvisited_prey` | cheap |
| 2.E | expose relative-food limitation (optional absolute mode) | implemented | aquatic_foodweb.py:267-293,340-347 | run_foodweb now accepts food_mode ("relative" default, "absolute") plus food_absolute_scale; absolute path divides production by scale and clamps to [0,1]; provenance records chosen mode | medium |
| 2.F | validate compatible cell ordering between control and pulse | implemented | aquatic_foodweb.py:500-503 | compares `control_ids`/`pulse_ids` and raises on mismatch | cheap |
| 3.A | replace river_state[2] with ID-based lookup | implemented | build.py:669-675 | `river_ref = next((r for r in river_state if r["id"] == REACH_BRIDGE), river_state[-1])` plus empty guard | cheap |
| 3.B | fail loudly on unknown tributary names (not just reach IDs) | implemented | build.py:416-429,673-687 | `if n not in tribs: raise ValueError(f"unknown tributary {n!r}; have {sorted(tribs)}")` guards both tributary-apply paths | cheap |
| 3.C | finite-number validation across every numeric config field | implemented | build.py:validate_config | `_finite_number`/`_fraction`/`_positive_finite`/`_nonnegative_finite`/`_nonnegative_int` now cover clock_hour, hydro.boundary_m3s/boundary_c/simulate_seconds, weather.humidity/cloud/gust_mps/lag_hours/night_air_c/day_warming_c/wind_xz_mps, insects.flowering_stage, fish.food/cover, snow.days/precip_mm_d, replay.duration_s/max_cell_m/depth_m/dispersion_m2_s/exchange_w_m2_k/dt_s/sample_s/hydraulics.*, overland.*, hydro.catchment.area_m2, simulation.start_epoch_unix/utc_offset_hours, wind_seed; test_validate_config_rejects_nan_and_inf_numerics covers NaN/inf/bool | medium |
| 3.D | skip overland validation when disabled | implemented | build.py:149-160 | validation gated by `if olfg.get("enabled", False)` | cheap |
| 3.E | deep-copy baseline collections to prevent aliased mutation | implemented | build.py:381,428 | `patches0 = copy.deepcopy(baseline.get("patches", []))` and `copy.deepcopy(baseline["river_reaches"])` | cheap |
| 3.F | foodweb configuration surfaced in cfg + manifest | implemented | build.py:461-474,772-782 | `foodweb` block consumed by `run_aquatic_foodweb` and included in `parameter_set` | cheap |
| 3.G | refuse to silently reuse completed build output directories | implemented | build.py main() checks CHECKS.json before mkdir; --force overrides | default behavior unchanged for a fresh output dir; a completed one raises FileExistsError | cheap |
| 3.H | atomic JSON writes for all build artifacts | implemented | build.py:1259-1261,1277-1316,1446,1495-1497 | `_atomic_json_write` writes tmp then rename for ecosystem, river_state, weather, met, CHECKS, and BUILD.json | cheap |
| 3.I | load_config rejects non-mapping YAML roots | implemented | build.py:46-48 | `if cfg is None or not isinstance(cfg, dict): raise ValueError` | cheap |
| 4.A | coordinate conversion uses actual image dimensions | implemented | canopy_census.py:314-316 | main() reads rgb.shape and calls to_world(..., width=img_w, height=img_h); downstream census.source.extent_m is already the spatial truth | cheap |
| 4.B | qa_census is defensive and catches all malformed values | implemented | canopy_census.py:260-324 | trees list type, n int-type, duplicate stable_ids, duplicate coords, extent-based coord bounds, peak_exg finite+range added alongside crown_r_m check | medium |
| 4.C | density_stats raises on unknown zone kinds and invalid dims | implemented | canopy_census.py:221-242 | circle radius > 0, ring r1>r0, zero-area box, else-raise on unknown kind | cheap |
| 4.D | pool-ring exclusion uses point-to-segment distance | implemented | canopy_census.py:_point_to_segment_distance_sq,exclude_pool_rims | margin test now scans each ring segment with point-to-segment squared distance; vertex-only test replaced | medium |
| 4.E | file handles for pool rings use context manager | implemented | canopy_census.py:102-105 | `with open(world_path, encoding="utf-8") as f: world = json.load(f)` | cheap |
| 4.F | detection thresholds centralized in crown_mask | implemented | canopy_census.py:24-29,50,355 | crown_mask shared helper now used by detect, calibrate_lone_trees, detect_v2 | cheap |
| 5.A | load image dims once and use census source extent | implemented | census_validate.py:70-104,297-326 | sample and evaluate paths read extent_m from census.source and use frozen image_dims_px from sampling_plan.json; no 640/1280/2048 constants left in the conversion math | medium |
| 5.B | validate tolerances (finite, > 0, no duplicates) | implemented | census_validate.py:273-278 | finite+positive plus duplicate-rejection check | cheap |
| 5.C | validate `--plots` and `--cell-px` sampling arguments | implemented | census_validate.py:71-82 | `>0` guards present plus `--plots <= len(frame)` guard against col*row population | cheap |
| 5.D | reference_points as source of truth, explicit submission marker | implemented | census_validate.py:290-315,330-339 | web annotator writes reference_submissions.json submission markers (zero-point plots included); evaluate warns on unresolved plots | medium |
| 5.E | validate web annotator payloads (finite coords, bounds, class, plot id) | implemented | census_validate.py:313-346 | isinstance, len>=2, numeric coords, finite check, in-crop bounds against the plot's crop width/height, robust int(class) coercion with range check | cheap |
| 5.F | reject crop path traversal | implemented | census_validate.py:259-269 | pid existence plus `resolve().relative_to(blind_dir)` guard | cheap |
| 5.G | enforce frozen main tolerance (freeze before results) | implemented | census_validate.py:113-125,279-293,431-443 | sampling_plan.json records tolerances_frozen_px + main_tolerance_px; evaluate tags any CLI tolerance outside that set as exploratory in the report | medium |
| 5.H | freeze manifest hashes detector params, package versions, pool/dim metadata | implemented | census_validate.py:48-96 | manifest adds detector_params, package_versions (numpy/scipy/PIL), world_pools_sha256, source_metadata | medium |

## Cross-project issues
- Fix 3.C spans many modules (hydro, replay, weather, snow); applying it as written requires touching callers that pass bool/NaN via YAML, not just build.py.
- Fix 4.A requires detail-image metadata to propagate; downstream validation (census_validate.py 5.A) hard-codes the same 2048/640 constants and must change together.
- Fix 2.A reporting change would alter the `aquatic_foodweb.json` schema consumed by Godot and the build manifest (`days` key currently stable).
- Fix 5.G frozen-tolerance change requires altering `sampling_plan.json` schema plus evaluate CLI contract.

## Scientific validity flags
- `aquatic_foodweb.run_foodweb` normalizes food by the daily maximum (aquatic_foodweb.py:338), so absolute starvation is unrepresentable even after fix 2.C.
- Trout refuge, Holling intake, and prey turnover all occur only at the best-ranked cell (aquatic_foodweb.py:361-385) with no movement cost or dispersal, inflating selected-cell throughput regardless of fix 2.D documentation.
- `check_trout_clear_of_pools` samples the centerline plus one signed lateral offset only (fish.py context), so corridor-width lateral risks are undercounted independent of fixes-1 scope.
- `obs_snotel` dates are stored as TEXT with lexical comparison (analysis_store.py:91,580-583); even with ISO validation, timezone/DST-adjacent lookups remain string-sorted.
