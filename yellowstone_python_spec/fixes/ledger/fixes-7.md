# fixes-7 ledger
Doc: fixes/fixes-7.md | read 2026-10-13, open rows re-verified 2026-10-13 | targets: yellowstone_python/yellowstone_python/publish.py sha256:6f9c3e7d59ae ; yellowstone_python/yellowstone_python/review_proposals.py sha256:c282effcf653 ; yellowstone_python/yellowstone_python/run_mode.py sha256:5b5b0ae38196 ; yellowstone_python/yellowstone_python/snow_energy.py sha256:9b59ec6d72dd
Summary: 29 items: 29 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| #1 | Track newly created files and delete them on rollback | implemented | publish.py:177,196-218 | `created` list tracked; rollback unlinks created and restores backed_up | cheap |
| #2 | Receipt write atomic/transaction-aware with distinct failure status | implemented | publish.py:229-238 | tmp.write_text then tmp.replace; receipt write failure returns dedicated code 5 | cheap |
| #3 | Collision-resistant backup dir (exist_ok=False or finer suffix) | implemented | publish.py:171-175 | `backup_root.mkdir(parents=True, exist_ok=False)` refuses existing dir with code 4 | cheap |
| #4 | Explicit handling of dir/symlink/type mismatch at target | implemented | publish.py:182-188 | target.is_dir() and target.is_symlink() raise IOError before copy | cheap |
| #5 | Record source+dest sha256 and sizes in receipt | implemented | publish.py:200-208,226 | file_records carries source_sha256, target_sha256, size per rel; receipt files=file_records | cheap |
| #6 | Wrap artifact loads and validate schema (passed boolean, etc.) | implemented | publish.py:76-89,102-114 | _load_json_or_refuse handles FileNotFoundError and JSONDecodeError; passed boolean and build_id string checked | cheap |
| #7 | Add in_water() check alongside in_apron() | implemented | review_proposals.py:12,99 | in_water imported from pool_crust; shells test is `in_apron(x, z, s) or in_water(x, z, s)` | cheap |
| #8 | Finite checks for every numeric input and derived value | implemented | review_proposals.py:41-42,94-95,106,114-118 | _finite applied to suitability_threshold, canopy, x, z, slope, moisture, suitability | cheap |
| #9 | Reject unknown guilds without KeyError | implemented | review_proposals.py:89-91 | `if guild not in GUILDS: reject(f"unknown guild {guild!r}")` before GUILDS[guild] | cheap |
| #10 | Load existing override records into spacing checks | implemented | review_proposals.py:59-73,200-211 | existing_overrides read from placement_overrides.json::{add} and seeded into kept with each override's guild | medium |
| #11 | Symmetric cross-guild separation using stored guild | implemented | review_proposals.py:58,126-131 | kept carries (x, z, guild); min_sep = max(g["min_sep_m"], GUILDS[kg]["min_sep_m"]) | cheap |
| #12 | Reject duplicate stable_id values before review | implemented | review_proposals.py:47-55 | `seen` set rejects duplicate proposal stable_id with ValueError | cheap |
| #13 | Fail closed on unknown guild in to_override_record | implemented | review_proposals.py:156-159 | raises ValueError when guild not in KIND_BY_GUILD; no silent "pine" default | cheap |
| #14 | Atomic write for placement_overrides.json | implemented | review_proposals.py:231-233 | tmp = ov_path.with_name(name+".tmp"); tmp.write_text(...); tmp.replace(ov_path) | cheap |
| #15 | Record ecosystem source and hash in artifact | implemented | review_proposals.py:main writes ov["ecosystem_provenance"] = {source, sha256} before replacing placement_overrides.json | ecosystem sha256 now persisted into placement_overrides.json | cheap |
| #16 | Reject non-str run_mode with TypeError | implemented | run_mode.py:21-22 | normalize_run_mode raises TypeError when mode is not str | cheap |
| #17 | Replay forcing should inspect replay contents per quantity | implemented | run_mode.py:77-83 | prescribed_quantities adds discharge/upstream_temperature only when the respective replay key is present | cheap |
| #18 | Normalize/validate `prescribed` input to claim_allowed | implemented | run_mode.py:99-105 | claim_allowed routes through _normalize_quantities(..., restrict_to_prescribed=True) | cheap |
| #19 | Validate allowed quantities in check_split | implemented | run_mode.py:108-117 | check_split rejects unknown prescribed names via _normalize_quantities(..., restrict_to_prescribed=True) | cheap |
| #20 | Polar-day TOA uses h0=pi general formula | implemented | snow_energy.py:52-73 | polar-day branch sets h0=pi then uses the general daily-mean formula; second term vanishes since sin(pi)=0 | medium |
| #21 | Reference-based turbulent term (c_t * (air_c - T_REF)) | implemented | snow_energy.py:T_REF_C,step_snow_eb | `net = sw + C0_W_M2 + c_t * (air_c - T_REF_C)` with T_REF_C=0 anchored at melting point | cheap |
| #22 | Record parameter_at_grid_boundary and tie diagnostics | implemented | snow_energy.py:fit_eb_params | returns dict with best_s_rad/best_c_turb_w_m2_k, parameter_at_grid_boundary, near_tie_count, fit_grid | cheap |
| #23 | Validate non-empty train/holdout and unique dates | implemented | snow_energy.py:_validate_unique_iso_dates | called in validate_site_eb and evaluate_fixed_params; duplicates and malformed ISO raise | cheap |
| #24 | Restrict peak-timing and depth metrics to holdout window | implemented | snow_energy.py:validate_site_eb,evaluate_fixed_params | depth and peak_timing restricted to hold_idx; `peak_timing_window`/`depth_check_window` fields set | cheap |
| #25 | Name and record snow-depth conversion factor | implemented | snow_energy.py:SWE_TO_DEPTH_RATIO | 3.0 is named with provenance; artifact carries ratio + provenance strings | cheap |
| #26 | Document/align _fill_temps policy with prepare_forcing | implemented | snow_energy.py:_fill_temps | docstring states forward-only policy matching snow_validate.prepare_forcing | cheap |
| #27 | Centralize date parsing with date.fromisoformat | implemented | snow_energy.py:day_of_year | uses `datetime.date.fromisoformat(str(iso))` | cheap |
| #28 | Finite/type checks on frozen s_rad, c_t | implemented | snow_energy.py:_finite_param,_on_grid | load_fixed_params rejects bools, non-finite, and off-grid; also rejects non-dict root and non-dict records | cheap |
| #29 | Mark degree-day comparator refit policy or freeze it | implemented | snow_energy.py:validate_site_eb,evaluate_fixed_params | `degree_day_fitted.parameter_policy: "comparator_refit_each_window"` recorded in each site | cheap |

## Cross-project issues
- The audit flags that `in_apron` with margin may structurally cover `in_water`, but review_proposals never records which; the Godot bake only consumes `data/placement_overrides.json::{add}` so if `in_water` were added the data path is unaffected.
- `review_proposals.main` reads `data/placements.json` for trees but not `data/placement_overrides.json` already-applied additions, so spacing comparisons span disjoint sets between gen passes and the Godot runtime.
- `snow_energy.evaluate_fixed_params` consumes `fit_snow_params` whose current return (dict) matches `dd_fit["best_k"]/best_wind` usage; the audit's older tuple-return example would conflict with `snow_validate.fit_snow_params` which now returns a dict.

## Scientific validity flags
- Clear-sky TOA at polar day returns extraterrestrial normal irradiance (W/m2 at TOA, not daily-mean horizontal insolation); this inflates mid-winter TOA at high latitudes and biases s_rad fits.
- `net = sw + C0 + c_t * air_c` treats a turbulent flux as a function of absolute Celsius; `c_t` conflates with `C0` through the chosen temperature scale.
- Snow-depth conversion uses an unnamed 3.0 SWE-to-depth factor and compares against measured SNWD without recording the density assumption.
- Peak-timing and depth RMSE in `validate_site_eb` are computed over the full window including training data; reported holdout performance is thus optimistic.
- `in_apron` can serve as a water test only if `apron_margin_m > 0` on every shell; absent an `in_water` call, a shell with zero apron margin leaves water pixels passable.
