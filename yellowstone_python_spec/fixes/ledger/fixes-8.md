# fixes-8 ledger
Doc: fixes/fixes-8.md | read 2026-10-13 | targets: yellowstone_python/yellowstone_python/snow_season.py sha256:777ba0baeda3 ; yellowstone_python/yellowstone_python/snow_validate.py sha256:57dbcae2c847 ; yellowstone_python/yellowstone_python/study_mode.py sha256:9977c4342178 ; yellowstone_python/yellowstone_python/vegetation.py sha256:55f0be1a13f6
Summary: 49 items: 49 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts (recounted from rows 2026-10-13)

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| #1 | Report thermal melt bounded by actual delivery | implemented | snow_season.py:124-129,201,225 | `actual_thermal = min(thermal_melt, max(0, avail - min(avail, dd_melt)))` and ledger uses it | cheap |
| #2 | Reject negative/non-finite precip and related clamps | implemented | snow_season.py:step_snow | precip, snow_mm, canopy_keep (unit), aspect_retention (>0), k_melt, and thermal_flux_mm_d all validated via local `_finite_nonneg`/`_finite_unit` helpers | cheap |
| #3 | Reject empty forcing/patches/negative days in run_season | implemented | snow_season.py:166-171 | Validates `days` int>=0, `air_c_by_day` nonempty, patches nonempty | cheap |
| #4 | Replace silent last-value repeat with explicit option | implemented | snow_season.py:run_season extend_last parameter | extend_last defaults to False and raises on length mismatch; explicit opt-in retains the last-value fallback | cheap |
| #5 | Validate uniqueness/presence of patch IDs | implemented | snow_season.py:183-185 | Explicit `None` and `len(set(ids))` check | cheap |
| #6 | Separate `runoff_drain` and `subsurface_drain` labels | implemented | snow_season.py:run_season ledger | ledger carries surface_runoff_mm, subsurface_drain_mm, and wind_runoff_mm; drainage_mm and runoff_mm retained for existing consumers | medium |
| #7 | Validate soil_cap_mm > 0, field_capacity in [0,1], clamp initial moisture | implemented | snow_season.py:run_season | soil_cap_mm (finite, >0) and field_capacity (finite, [0,1]) checked; initial moisture still clamped at the patch loop | cheap |
| #8 | Keep soil unrounded internally; round only at output | implemented | snow_season.py:run_season soil_state | per-patch soil tracked unrounded in soil_state; p["soil_mm"] mirrors it at display precision | cheap |
| #9 | Use datetime validation inside date_to_season | implemented | snow_season.py:19-22 | `datetime.date(2000, int(month), int(day))` guards invalid dates | cheap |
| #10 | Treat `now is None` sentinel, not falsey | implemented | snow_season.py:43 | `local = now if now is not None else ...` | cheap |
| #11 | Validate size/center/apron and create parent dir in render_snow_map | implemented | snow_season.py:render_snow_map | size, snow_m, each shell center and apron radius validated; parent.mkdir(parents=True, exist_ok=True) | cheap |
| #12 | train_holdout_split rejects empty train or holdout | implemented | snow_validate.py:89-98 | Guards `not dates`, `idx == 0`, `idx == len(dates)` | cheap |
| #13 | Validate ISO keys, uniqueness, contiguity of site days | implemented | snow_validate.py:_validate_site_dates,validate_site | ISO parse + duplicate rejection applied at start of validate_site; contiguity gaps accepted but recorded in sorted order | cheap |
| #14 | Treat None WTEQ/SNWD as missing, not zero | implemented | snow_validate.py:270-271,179-186 | Keeps None then filters via `_scored_pairs` | cheap |
| #15 | Name and record spin-up tolerance | implemented | snow_validate.py:43,266 | `SPINUP_THRESHOLD_MM = 25.4 * 0.04` used in guard | cheap |
| #16 | Replace assert with explicit RuntimeError | implemented | snow_validate.py:122-124 | `raise RuntimeError(f"water ledger residual {residual} mm")` | cheap |
| #17 | Validate split sizes before all scoring calls | implemented | snow_validate.py:validate_site hold_keep guard | hold_keep emptiness checked before score_paired_series on both paths | cheap |
| #18 | Validate length equality and ISO dates in peak_timing | implemented | snow_validate.py:139-149 | Length check, ISO date check, missing-value refuse | cheap |
| #19 | k_melt must be exactly on fit grid, nonfinite rejected | implemented | snow_validate.py:197-206,412-417 | `_on_grid` + `_finite_param` applied to frozen params | cheap |
| #20 | load_fixed_params validates schema with useful errors | implemented | snow_validate.py:374-418 | Rejects non-dict top-level and missing per-site fields with path context | cheap |
| #21 | Derive provenance window from bundle metadata | implemented | snow_validate.py:315-317,348-350 | Format includes `bundle.get('window', 'unknown')` and split date | cheap |
| #22 | Record grid, candidate count, tie count, scored sample size | implemented | snow_validate.py:243-249 | Return dict carries `grid`, `n_candidates`, `tie_rule`, `tie_count`, `train_scored_n` | cheap |
| #23 | Report holdout_scored_n and train_scored_n after filtering | implemented | snow_validate.py:308-310 | Fields `train_scored_n` and `holdout_scored_n` in output | cheap |
| #24 | Reject NaN/Inf for every numeric slider | implemented | study_mode.py:117-118,89-91,94-99 | `math.isfinite(number)` plus daylist/list guards | cheap |
| #25 | clock_hour upper bound exclusive | implemented | study_mode.py:28,119-121 | `"exclusive"` flag honored by validator | cheap |
| #26 | Use a semantic numeric type instead of float | implemented | study_mode.py:NUMBER/INTEGER/STRING/WIND_VECTOR/ISODATE/DAYLIST/PATCH_LATERALS sentinels; _validate branches on semantic names | NUMBER rejects booleans and non-finite values; INTEGER rejects floats and booleans | cheap |
| #27 | Reject booleans in daylist and wind_xz_mps | implemented | study_mode.py:90,96 | `not isinstance(v, bool)` in daylist and 2-vector branches | cheap |
| #28 | snow.days minimum 1 (zero rejected) | implemented | study_mode.py:46 | `"snow.days": (int, 1, 365)` | cheap |
| #29 | Approve or scalarize hydro.attach/tributaries path | implemented | study_mode.py:SCHEMA holds hydro.attach and hydro.tributaries with PATCH_LATERALS type; _validate raises a managed-by-apply_preset message if used in set | preset.set entries for these paths refused with a clear message; apply_preset owns the write path | medium |
| #30 | Idempotent lateral link insertion | implemented | study_mode.py:254-256 | `if lat["id"] not in links: links.append(...)` and existing-tributary mismatch raises | cheap |
| #31 | _set_path refuses missing or non-mapping parent | implemented | study_mode.py:215-217 | Raises `ValueError` on missing node or non-dict | cheap |
| #32 | Use ALLOWED_PREFIXES in validation | implemented | study_mode.py:55-63,70-72 | `_prefix_allowed` enforces prefix list in `_validate` | cheap |
| #33 | diff_configs distinguishes missing from None via sentinel | implemented | study_mode.py:264-277 | `_MISSING = object()` with `added_in_A/B` flags | cheap |
| #34 | Validate yaml.safe_load returns mappings | implemented | study_mode.py:308-309 | `isinstance(a_raw, dict) and isinstance(b_raw, dict)` guard | cheap |
| #35 | Choose and document a stable-ID policy | implemented | vegetation.py:propose_plantings | reviewed form prop_{guild}_{seed}_{col:03d}_{row:03d} is the single canonical format; start_index retained in signature for backward compatibility but does not renumber | cheap |
| #36 | Validate radius/center/seed/threshold/moisture/canopy/count | implemented | vegetation.py:275-305 | Explicit range and finiteness checks | cheap |
| #37 | Rename parameter from `lamba0` to `lambda0` | implemented | vegetation.py:61 | `def suitability(lambda0: float = 0.9, ...)` | cheap |
| #38 | Clamp or reject nonfinite lambda0 | implemented | vegetation.py:_reject_nonfinite,suitability | `_reject_nonfinite("lambda0", lambda0)` raises on NaN/Inf before clamp; applies to m_habitat, m_exclusion, and every factor value | cheap |
| #39 | Reject invalid moisture/canopy in guild_suitability | implemented | vegetation.py:guild_suitability | moisture and canopy checked for finiteness and [0,1] range at function entry | cheap |
| #40 | Validate terrain finiteness and shape | implemented | vegetation.py:184-187,199-202 | `np.isfinite(h).all()` and shape check in load_terrain and terrain_fns | cheap |
| #41 | Document terrain boundary clamp policy | implemented | vegetation.py:191-197 | Docstring states clamp ranges for sample and slope_deg | cheap |
| #42 | Deterministic patch selection (nearest/center) | implemented | vegetation.py:224-246 | `habitat_moisture_at` picks min distance within radius | cheap |
| #43 | Single patch-selection helper used by renderer | implemented | vegetation.py:410 | `render_suitability_png` now calls `habitat_moisture_at` | cheap |
| #44 | Use math.ceil for grid rows and define placement | implemented | vegetation.py:310,313 | `per_row = max(1, math.ceil((2 * radius_m) / grid_step))` | cheap |
| #45 | Log original/effective spacing and candidate counts | implemented | vegetation.py:316-322 | Coarsened log records `original_spacing_m`, `effective_spacing_m`, `original_candidate_count` | cheap |
| #46 | Validate dt_s/biomass/capacity/rates and duplicate ids | implemented | vegetation.py:101-134 | `_finite_value`, `_nonnegative_value` and `seen_ids` cover each check | cheap |
| #47 | Detect/clarify grazer-patch assignment semantics | implemented | vegetation.py:patch_step | demand_by_patch aggregation rejects an active grazer whose patch_id is not in patches; ledger carries consumed_by_patch for a lag-1 scheduler; docstring states that several active grazers may sum into one patch | cheap |
| #48 | Validate size/bbox/canopy/guild/output dir in renderer | implemented | vegetation.py:386-417 | Guards all listed inputs and `parent.mkdir(parents=True, exist_ok=True)` | cheap |
| #49 | Lazy-import numpy or declare it as required | implemented | vegetation.py:_require_numpy | TYPE_CHECKING-only typing import at module top; load_terrain and terrain_fns call _require_numpy which raises a stated ImportError if numpy is missing | cheap |

## Cross-project issues
- `snow_season.step_snow` now returns six values including `actual_thermal`; `snow_energy.step_snow_eb` already destructures six values at line 119, so callers remain compatible.
- The split of `drain` into half-runoff and half-drain stays in `run_season`; downstream analysis (`analysis_store.replay_frames`, Godot ledger displays) reads these fields directly, so a rename would ripple through consumers.
- `vegetation.propose_plantings` still routes through `propose_plantings_reviewed` whose IDs follow `prop_{guild}_{seed}_{col:03d}_{row:03d}`; any Godot or override consumer that assumed the legacy `start_index` form never fires its renumbering branch.
- `study_mode.PRESETS["hot_surge"]` writes to `hydro.attach` and `hydro.tributaries` which `build.validate_config` consumes; adding those paths to SCHEMA would need coordination with `build.py` schema expectations.

## Scientific validity flags
- `snow_season.run_season` reports `thermal_melt_mm` only in the `thermal` branch, but `tot["melt"]` and `tot["accum"]` are summed unconditionally; the water ledger closes but the thermal-only accounting underreports non-thermal-cell melt contributions when thermal_test is None.
- Snow-depth conversion inside `snow_season.run_season` uses `float(p["snow_mm"]) / 1000.0 * 3.0` to produce `snow_depth_m`, the same unnamed 3.0 factor flagged for `snow_validate`; no density provenance recorded.
- `_phenology(moisture)` reads a rounded (4 decimals) moisture value from the same timestep; the discretization is small but introduces trajectory drift under chained short-dt simulations.
- `vegetation.suitability` clamps lambda0 instead of rejecting NaN; a NaN leaked from upstream `lambda0` cascades through `min(1, max(0, ...))` as NaN and silently zeros the output on downstream clamps.
- `vegetation.render_suitability_png` is O(size^2 * patches * shells) and uses center-nearest patch selection; large maps and overlapping patches produce visually quantized boundaries driven by patch centers, not geometry.
