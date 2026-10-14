# fixes-46: one set of validation helpers, I/O helpers and site constants

Scope: helper functions and constants that are redefined across `yellowstone_python/` and `tools/`, with different signatures and behavior. Code quality for a public repository: a reader who opens three modules should not find three versions of the same check. Audit 2026-10-13 at the request of KJR.
Method: `rg` over `yellowstone_python/` and `tools/` (gitignored paths excluded, which only removes caches and build outputs), each hit opened to compare signature and behavior.

## Items

### 1. Twenty-seven finite-number checks with three argument orders
`_finite` is defined in 24 modules and `finite` (public) in `replay/river_transport.py:43`, `_finite_number` in `build.py:70`, plus a nested `_positive_finite` inside `aquatic_foodweb.run_foodweb` (`aquatic_foodweb.py:617-623`). Signatures disagree:
- `(value, name, minimum=None)`: `periphyton.py:53`, `river_shading.py:53`, `time_utils.py:14`, `replay/hydraulics.py:50`, `river_oxygen.py:89`, `groundwater_provider.py:13`, `overland_provider.py:22` (this one also rejects `bool`), `replay/river_transport.py:43`.
- `(name, value)`, rejecting `bool`: `overland_flow.py:40`, `review_proposals.py:20`, `hydrology_provider.py:32`, `ground_heat.py:58`, `outflow_thermal.py:66`, `microclimate.py:51`, `mat_validation.py:40`, `evapotranspiration.py:37`, `steam_microclimate.py:75`, `hydro_thermal.py:13`, `outflow_foodweb.py:153`, `microbial_mats.py:129`, `replay/obs_frame.py:19`, `insects_birds.py:205`.
- `(value, name)`, accepting `bool`: `replay/calibrate.py:23`, `replay/plume2d.py:33`, `tools/calibrate_river_transport.py:119`.
`common/validate.py:10` already has `assert_finite(name, value)`, and `common/units.py:61-72` has `require_positive` and `require_fraction`. Related copies: `_nonnegative` (7 modules), `_positive` (6), `_positive_int` (3), `_unit_interval` (1), `build.py:83-115` (`_nonnegative_number`, `_positive_finite`, `_nonnegative_finite`).
### Fix
One module `yellowstone_python/common/checks.py`:
`finite(name, value, *, minimum=None, maximum=None) -> float`, `positive(name, value) -> float`, `nonnegative(name, value) -> float`, `fraction(name, value) -> float`, `positive_int(name, value) -> int`. Name first (the majority order and the existing `assert_finite`); `bool` rejected everywhere; error type `ValueError` with the message form `"{name} must be ..."`. Replace each local definition and its call sites module by module, swapping argument order where the local helper took value first. `common/validate.assert_finite` and `common/units.require_*` become imports of the new functions. Behavior change to record: `replay/calibrate.py`, `replay/plume2d.py` and `tools/calibrate_river_transport.py` start rejecting `True` and `False` as numbers.
### Test
`tests/test_checks.py` covers NaN, infinities, `bool`, strings, bounds. After the change, `rg -n '^\s*def _?(finite|positive|nonnegative|unit_interval|positive_int|positive_finite|finite_number)\b' yellowstone_python tools` returns only `common/checks.py`. The full suite passes.
### Cost
Medium (about 30 files, mechanical, argument-order care).

### 2. Seven file hashers and four JSON loaders
SHA-256 of a file: `common/provenance.py:45 sha256_file`, `analysis_store.py:51`, `llm_backend.py:96`, `census_validate.py:20`, `publish.py:69`, `replay/river_world.py:217 sha256`, `tools/build_store.py:16`, `tools/derive_outflow_network.py:30`. JSON loaders: `llm_backend.py:55`, `exporters/godot_sidecars.py:76`, `tools/run_mat_model.py:88`, `tools/assemble_firehole_obs.py:30`. Atomic JSON writes: `build.py:2401 _atomic_json_write`, `exporters/godot_sidecars.py:97 _write_json` (not atomic), `tools/calibrate_river_transport.py:896`, and an inline `.tmp`-then-`replace` block in 28 files.
### Fix
`common/io.py` with `sha256_file(path)` (moved from `provenance.py`, which re-imports it), `load_json(path, *, label=None, expect=dict)` raising one error type with the path in the message, and `write_json_atomic(path, obj, *, indent=1)` (temp file in the same directory, `allow_nan=False`, `os.replace`, temp removed on failure). Route the 28 inline blocks and the three named writers through it. `godot_sidecars._write_json` becomes atomic as a result, which matters because Godot polls some of those files by mtime (fixes-44 item 1).
### Test
`write_json_atomic` leaves the old file intact when serialization raises (NaN input); `rg -n 'hashlib.sha256\(' yellowstone_python tools` lists only `common/io.py` and code hashing non-file data.
### Cost
Medium.

### 3. Two site coordinates under the same constant name
`SITE_LATITUDE_DEG = 44.459333` in `llm_backend.py:26` and `exporters/godot_sidecars.py:24` (with longitude -110.822272, described as the "Firehole site centroid"), and the same value as a default in `microclimate.py:43`, `:391`, `:412`. `SITE_LATITUDE_DEG = 44.525` in `river_shading.py:45` and `tools/run_mat_model.py:83`, and `OUTFLOW_SITE_LAT_DEG = 44.525` in `build.py:40`. The two latitudes are about 7 km apart; 44.525 matches Midway Geyser Basin, 44.459 lies near the Upper Geyser Basin. Solar geometry for the river and the mats uses one point, the weather snapshot and met fetch use the other, and nothing says which point each represents.
### Fix
Derive the site point from the world georeference in `common/coords.py` (E0, N0 in EPSG:32612) and publish it as `SITE_LAT_DEG`, `SITE_LON_DEG` with a comment naming it the Midway world center. If the met grid point is deliberately elsewhere (an Open-Meteo grid cell), name it `MET_GRID_LAT_DEG` and `MET_GRID_LON_DEG` in `tools/fetch_met_forcing.py` and record it in the met bundle. Every other module imports one of the two. `SITE_ELEVATION_M` (`atmospheric_constants.py:6`) moves into the same constants home (fixes-47 item 5).
### Test
A test converts (E0, N0) to latitude and longitude with pyproj and asserts the published constants match to 1e-5 degrees; `rg -n '44\.(459|525)' yellowstone_python tools --glob '*.py'` returns only the constants module and tests.
### Cost
Cheap.

### 4. Gauge identifiers repeated as string literals
`"06036805"` and `"06036905"` appear in more than 20 package and tool files (`fish.py`, `coupling.py`, `claims.py`, `param_registry.py`, `replay/calibrate.py`, `replay/hydraulics.py`, `replay/obs_model.py`, `tools/calibrate_river_transport.py` six times, and others). A typo in one place silently selects no data.
### Fix
Constants `UPSTREAM_GAUGE = "06036805"` and `DOWNSTREAM_GAUGE = "06036905"` with their station names in `replay/obs_model.py` (which already holds station metadata), imported everywhere else.
### Test
`rg -c '"06036805"|"06036905"' yellowstone_python tools --glob '*.py'` counts only the constants module and test fixtures.
### Cost
Cheap.

### 5. Duplicated forcing-grid construction
`tools/calibrate_river_transport.py:568-604 _forcing_arrays` says it mirrors `replay/calibrate.py:394-443 _fit_forcing_arrays`, but builds its grid inline while the package version uses `replay/fit_grid.build_fit_grid`. The two can produce different grid origins for the same bundle.
### Fix
Delete the tool's copy and call `replay.calibrate._fit_forcing_arrays` (renamed public `fit_forcing_arrays`).
### Test
Stage D results are unchanged on the frozen bundle (bitwise frames).
### Cost
Cheap.

### 6. Duplicated weather snapshot logic
`llm_backend.py:427-506` and `exporters/godot_sidecars.py:485-622` each build a weather snapshot with the same defaults, the same Stull (2011) wet-bulb expression (`llm_backend.py:464`, `godot_sidecars.py:526`) and the same dew-point approximation. Covered as a correctness item in fixes-44 item 11; listed here so the duplication is tracked with the other helpers.
### Fix
See fixes-44 item 11.
### Cost
Cheap.

## Calibration consistency, found while reading the calibrators

### 7. A null-model name that no fit produces
`replay/calibrate.py:1303-1308` maps null names to parameter counts for AIC, including `mixing_only_c0_at_champion_laterals`, a name `reach_heat_fit` no longer emits (it emits `mixing_only_c0_refit`, `:912`).
### Fix
Remove the dead key; take each null's parameter count from the null record itself (`"k": 2` written by `reach_heat_fit`) so the two cannot disagree.
### Test
`lsfit` on the frozen bundle produces the same selection table.
### Cost
Cheap.

### 8. AIC and BIC count autocorrelated samples as independent
`lsfit` computes AIC and BIC with `n_train` equal to the number of 900 s grid points (`replay/calibrate.py:1295-1315`). The forcing is interpolated from hourly met and the residuals are serially correlated (`hydraulics.residual_diagnostics` already reports the lag-1 autocorrelation), so the effective sample size is smaller and the criteria overstate the evidence for the 3-parameter model over the nulls.
### Fix
Report AIC and BIC with an effective sample size `n_eff = n * (1 - r1) / (1 + r1)` from the train-window lag-1 autocorrelation, alongside the current values, and label which one the selection uses.
### Test
For white-noise residuals `n_eff` is close to `n`; for an AR(1) series with r1 = 0.9 it is about `n / 19`.
### Cost
Cheap.

### 9. A shortwave parameter marked identifiable from longwave data
`tools/calibrate_river_transport.py:92-96` lists `shortwave_multiplier` as identifiable when a longwave-down channel exists. A longwave measurement constrains the longwave terms; attributing the remaining radiative misfit to shortwave assumes every other term is right.
### Fix
Require a shortwave or net-radiation channel (`surface_flux.net_radiometer_w_m2`, or a measured `meteorology.shortwave_w_m2` flagged as station data rather than reanalysis) for `shortwave_multiplier`, or write down the attribution assumption in the identifiability report.
### Test
A bundle with longwave only reports `shortwave_multiplier` as not identified.
### Cost
Cheap.

## Order
Item 1 first (largest, unblocks clean diffs elsewhere), then 2, 3, 4, 5. Each item is one commit; no logic changes ride along. Items 7 to 9 are independent of the others.
