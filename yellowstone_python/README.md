# Yellowstone Python

Illustrative scientific modeling for the Midway Geyser Basin Godot world. Python reads frozen inputs, writes `derived/<build-id>/`, checks the outputs, and publishes runtime sidecars. Package, model, data, and calibration versions are tracked separately.

## Install and run

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-reference.lock
.venv/bin/python -m pip install -e . --no-deps --no-build-isolation
.venv/bin/python -m pytest
.venv/bin/python -m yellowstone_python.build --config configs/baseline.yaml
.venv/bin/python -m yellowstone_python.study_mode --list
.venv/bin/python -m yellowstone_python.publish --help
.venv/bin/python -m tools.hot_lowflow --help
```

The exact reference lock selects the tested numerical, geospatial and observation dependencies. FiPy, flopy, landlab and netCDF4 remain optional; skip reports identify their unavailable checks. The broader `science`, `fetch` and `dev` extras support development environments. The editable install makes package and tool imports work from outside the project. Tools run as `python -m tools.<name>`.

Open `../yellowstone_midway/project.godot` in Godot 4.5.1 to run the world. A validated build can be published with `python -m yellowstone_python.publish --build derived/<build-id> --to ../yellowstone_midway`. Source inputs and previous build directories are preserved.

The live service starts at 1x real time. Run `.venv/bin/python -m yellowstone_python.service.live --build derived/<build-id>` to serve a published build locally. The in-game speed selector supports 1x, 60x, 600x and 3600x; the service reports the effective rate when solver capacity limits acceleration.

## Time, phase and release contracts

`clock_hour` changes display lighting only. `advance_time` integrates the requested elapsed seconds. `reset` restores an identified initial state and applies a declared snow/soil spin-up once. Date controls use the reset operation. Repeating a reset target has the same result.

Wind erosion records `snow_export_mm`. `runoff_mm` contains liquid surface drainage only. The snow/soil bucket owns ET; FAO reference ET is diagnostic. Spin-up, initial biomass preparation, overland source support and the experiment each have explicit intervals in `BUILD.json`. Overland discharge ends at the source-window boundary; a longer river run cannot multiply the source volume. Baked and live land steps share the same kernel.

Published replays retain the resolved solver configuration, initial temperatures and forcing. Live resumption preserves Newton or explicit-budget exchange and the configured physical timestep. Playback speed affects delivery. A new controlled scenario receives a separate identity.

Publication authenticates `BUILD.json` hashes and the `CHECKS.json` assessment before copying. Runtime data reside in `data/releases/<release-id>/`; `data/release.json` selects one generation atomically. Godot validates its actual replay field access before activation and retains the current generation on failure. `--unverified-development` permits an explicitly labeled development generation; demo packaging refuses it.

## Frozen inputs and reference commands

The baseline declares June 21, 2026 at 22:12 UTC, wind seed 11 and authored weather. `weather.use_met_bundle: false` excludes any cached weather bundle. `configs/portfolio.yaml` adds one scheduled river-entry temperature pulse; its comparison holds all other forcing and initial cells fixed.

```sh
.venv/bin/python -m tools.reference_run --out ../work/reference-experiment.json --plot ../work/reference-experiment.png
.venv/bin/python -m tools.run_evidence --name isolated-tests --junit ../work/isolated-tests.xml -- .venv/bin/python -m pytest -m 'not needs_world' --junitxml=../work/isolated-tests.xml -q
```

Full builds use the `yellowstone_midway` sibling or `YELLOWSTONE_WORLD`. Required frozen inputs include `data/ecosystem.json`, `data/world.json`, `data/terrain.f32`, source records and canopy render artifacts. The source checkout supplies compiled world inputs; raw LiDAR tiles and observation caches require explicit acquisition with the tools below when absent. Test markers retain the distinction between isolated checks and checks requiring those inputs.

Command receipts bind execution to source and fixture hashes, report skips separately, and include output-log hashes. The dashboard labels static inventory declarations and ledger assertions separately from executed checks. Added or changed source files make old receipts stale.

## Model components

River heat transport uses a mapped finite-volume chain with advection, dispersion, lateral mixing, and surface-energy exchange. `river/river_transport.py` and `river/surface_flux.py` implement the transport and explicit flux components in `registry/equations.py`. Analytical profiles, manufactured solutions, convergence checks, and budget ledgers test the numerical behavior.

Aquatic models in `aquatic/` combine relative insect stocks, periphyton, dissolved oxygen, thermal response curves, and trout refuge selection. Their equation components describe the foodweb, oxygen, and thermal suitability assumptions. Authored off-channel pockets carry a non-conservative landscape label and stay outside transport volumes.

Land models in `land/` cover logistic vegetation growth, grazing, degree-day or energy-balance snowmelt, soil storage, and evapotranspiration. Storage and flux ledgers accompany the snow and soil-bucket equation components. Hydrology providers identify their backend and boundary assumptions.

Thermal-feature models in `thermal_features/` cover mapped outflow networks, temperature chains, solutes, microbial mats, pigment appearance, and ground heat. The equation registry records the governing approximations. Pool polygons and source imagery retain their original geometry and provenance.

Atmosphere models in `atmosphere/` produce meteorological fields and steam effects. Shared weather snapshots use the simulation epoch. Godot reads the published fields, advances the live scene, and renders player movement, wildlife, foliage, water, steam, and atmosphere.

Observation clients in `observations/` fetch and normalize USGS, Open-Meteo, and SNOTEL inputs. Bundles record timestamps, units, quality flags, and content hashes. An Open-Meteo field is model forcing; it carries its forcing class in the bundle.

`service/` exposes the analysis store and live simulation engine. `authoring/` contains placement and trail-mask tooling. Registry entries preserve the distinction between measured, literature, fitted, and authored values.

## Forest observations and placement

The USGS QL1 point-cloud workflow uses the 12 delivered tiles intersecting the 1280 m window and the matched NAVD88 DEM. Cached source bytes, LAS headers, catalog responses, coordinate operations, and checksums accompany the 0.5 m surface-height raster. NoData cells remain missing. Mapped mineral, pool-apron, and river surfaces are excluded from canopy interpretation; the raw returns remain available.

```bash
.venv/bin/python -m tools.fetch_lidar_canopy \
  --dem ../yellowstone_midway/references/dem_1m_core.tif \
  --cache data/lidar/raw --out-dir derived/lidar_canopy --workers 12
.venv/bin/python -m tools.build_lidar_forest
.venv/bin/python -m yellowstone_python.authoring.gen_flora --measured-canopy --apply
.venv/bin/python -m tools.lidar_review evaluate \
  --validation-dir derived/lidar_canopy/blind_validation \
  --out derived/lidar_canopy/blind_validation_unavailable.json
```

`build_lidar_forest` emits the dominant-crown census, 10 m coverage cells, segmentation raster, and reversible override plan. Height-dependent peak suppression uses an authored numerical window. Crown cores retain pixels where watershed and nearest-peak ownership agree; their equivalent-area radii do not establish full crown width. The measured coverage field supplies canopy fraction to the scientific pipeline independently of overlapping render crowns. Height-conditioned TreeMap donor rows supplement DBH and crown ratio with transferred, locally unvalidated values. LiDAR does not identify species or establish total or subcanopy stem counts.

Plain review crops and frozen source hashes are in `derived/lidar_canopy/blind_validation`. Evaluation requires explicit hand-label submissions, including explicit zero-crown records. Empty submissions return unavailable metrics. The 2020 point cloud and 2022 review imagery have different acquisition epochs. Raw pool and river ground controls fail the requested criterion; sparse river returns cannot establish canopy absence. The local placement layer is derived and unvalidated, and scientific acceptance remains pending.

## Tree architecture and wildlife motion

`authoring/tree_architecture.py` generates connected, seeded branch graphs and paired-needle shoot records. It preserves dimensional inputs and records the stochastic parameters. The crown-envelope option uses the regional Bechtold lodgepole equation within its DBH range; image-based fallback proportions retain unknown scale, camera pose and local error. These reconstructed envelopes remain separate from LiDAR crown cores and TreeMap donor measurements.

```bash
.venv/bin/python -m tools.tree_architecture \
  --height-m 14 --dbh-m 0.22 --crown-radius-m 2.0 \
  --crown-ratio 0.72 --identity example-pine --variants 4 \
  --out work/pine-architecture.json
.venv/bin/python -m yellowstone_python.wildlife_motion profiles
.venv/bin/python -m yellowstone_python.wildlife_motion validate \
  ../yellowstone_midway/assets/imported/wildlife_motion/bobcat_animated_2k.glb \
  --output work/bobcat-motion-validation.json
```

The imported motion library retains its MIT license. Project adapters use Apache-2.0. KJR owns all animal meshes and authorized their inclusion in the project release. Asset manifests retain rig estimates, synthetic-fixture labels and authored species shape proxies. Ownership and release permission are distinct from geometry or biological validation. Numerical skinning, contact and animation tests do not establish measured animal biomechanics.

Supplied bison, badger, bobcat, grizzly, black bear and Canada lynx models have runtime bindings. Wolf, deer and elk retain explicit shape-proxy labels. Midway encounters include habitat-qualified black bear routes; Canada lynx remains gated to suitable cold-conifer or park-reference contexts.

`land/mammals.py` couples authored guild population proxies and display encounters to current vegetation, moisture, snow, soil heat, season and daylight. Forage allocation removes normalized biomass once and records its budget; baseline grazer ownership prevents duplicate demand. Both baked trajectories and live checkpoints use the same forcing helper and physical simulation time.

The occurrence catalogue retains the primary NPSpecies rows and current NPS bat confirmations, including their conflicting counts and historical names. Unsupported local habitats and provisional taxa remain gated. Park occurrence supplies a roster; authored population equivalents and display encounter probabilities do not establish local abundance or measured sighting frequencies.

## Findings

These results describe frozen artifacts. Their recorded windows and parameter values establish the scope of each comparison.

- Snow degree-day fits use Madison Plateau and West Yellowstone observations. In the first holdout window, RMSE is 112 mm and 45 mm, compared with persistence values of 293 mm and 179 mm. Frozen parameters in a second window give 161 mm and 90 mm. Run mode: hindcast analysis. Status: `fitted_not_validated_single_window`. Artifacts: `derived/snow_degree_day_fit.json` and `derived/snow_degree_day_fit_prior_window.json`.
- Energy-balance snow fits reduce first-window RMSE to 62 mm and 14 mm. Frozen parameters give 46 mm and 55 mm in the second window. Radiation contributes at Madison Plateau; the West Yellowstone fit selects turbulent exchange alone. Run mode: hindcast analysis. Status: `fitted_not_validated_single_window`. Artifacts: `derived/snow_energy_fit.json` and `derived/snow_energy_fit_prior_window.json`.
- A hot low-flow mainstem scenario uses 2.5 m3/s and an authored 26 C upstream boundary. Mean cell temperatures span 25.05 to 28.50 C; no mean falls below the 24 C refuge threshold. Trout refuge selection moves 2357 m downstream. Run mode: `scenario`. Status: illustrative. Artifacts: `derived/hot_lowflow_replay.json` and `derived/aquatic_hot_lowflow.json`.
- Authored Rabbit Creek and Mallard Creek pockets at mapped confluences provide cold holding water. The pulse selects the Mallard pocket at 11 C and shifts 2837.5 m upstream. Temperature, size, and velocity-depth sweeps record sensitivity. Run mode: `scenario`. Status: illustrative. Artifacts: `derived/aquatic_hot_lowflow_tributary_refuge.json` and `derived/aquatic_tributary_sweep.json`.
- Shear disturbance is zero at the default authored 20 Pa threshold because mapped reach-averaged shear is 15.08 Pa. Lower thresholds suppress emergence and can change refuge selection. Status: illustrative sensitivity, with synthetic checks in `tests/aquatic/test_aquatic_foodweb.py`.
- A Fischer dispersion sensitivity of 84.7 m2/s gives the same qualitative hot-mainstem outcome: no sub-24 C mean cell temperature. Its refuge position differs from the 1 m2/s comparison. Run mode: `scenario`. Status: sensitivity analysis. Artifacts use `derived/aquatic_dispersion_D85_*` and `derived/aquatic_hot_lowflow_D85_*`.

## Validation and test requirements

Run `python -m pytest` for the single test tree. Registered markers make optional coverage visible:

| Marker | Requirement |
|---|---|
| `needs_world` | Godot world files and frozen world inputs; override their root with `YELLOWSTONE_WORLD`. |
| `needs_pvlib` | pvlib solar geometry backend. |
| `needs_fipy` | FiPy independent transport reference. |
| `needs_network_inputs` | Frozen downloaded observation, network, or imagery inputs. |
| `needs_science` | Other optional scientific dependencies such as pandas, sympy, or NetCDF. |

`pytest -m 'not needs_world'` selects checks that can run without the Godot checkout. Pytest reports skip reasons. The suite also checks the complete maintained source tree against the comment and documentation rules.

Notebook outputs are cleared in the repository. From the repository root, enable the notebook hook with:

```bash
GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0= \
  yellowstone_python/.venv/bin/python -m pre_commit install \
  --config yellowstone_python/.pre-commit-config.yaml
```

This command installs the repository hook while preserving the configured global hook path. The local global hook delegates to the repository hook. The `nbstripout` pre-commit configuration preserves this state; `python -m nbstripout --verify notebooks/*.ipynb` checks it. Generate a diagnostic figure from a frozen comparison with:

```bash
.venv/bin/python -m tools.plot_fit --artifact derived/aquatic_hot_lowflow.json \
  --out-dir work/figs --type aquatic_intervention
```

Historical figures are retained with internal working documents.

## Limits and evidence status

Boundary discharge and upstream temperature are prescribed forcing. Validation targets unprescribed outputs, and all registered scientific claims remain `not_yet_accepted`. Unknown parameter uncertainty stays `unknown`. Forecast builds require a forecast evaluation.

The models have no calibrated bathymetry, organism counts, absolute food availability, mortality, or movement cost. Mapped hydraulics depend on authored geometry and roughness. Soil moisture lacks observation validation. The shared trout and dipper foraging assumption can strand the dipper at a small pocket. These conditions bound the interpretation of the frozen results.

Measured inputs are preserved; authored profiles, positions, coefficients, and exclusion masks carry provenance. A local test pass establishes the behavior asserted by those checks. Field validation is recorded separately in claim and fit artifacts.

For the macOS reference matrix, run the core and `needs_world` scopes in separate isolated interpreter processes. A monolithic run can encounter native PROJ/SQLite child-process crashes; its failed receipt is retained. Original reduction sources in the ignored wildlife `sources/` directory are required for source-to-derivative UV comparisons. Obtain the exact owner-provided files identified by `wildlife_motion_assets.json`; absent originals produce explicit skips. See [toolchain evidence and limits](../docs/TOOLCHAIN.md).

## Implementation contracts

### Tributary identity

`observations/tributaries.py` admits `cold_refuge_candidates` only when gauge and
stream attributes match `VERIFIED_TRIBUTARY_REGISTRY`, checked against NWIS and
USGS StreamStats. The registry is empty by default; unchecked documented streams
carry `association_status = unverified` and remain outside that candidate list.
The shipped catalog's provenance warning identifies `07xxxxxx` site codes as
Lower Mississippi numbers; Yellowstone gauge prefixes are `06xxxxxx` or
`13xxxxxx`. It also flags the Arrow Creek at Tower Falls and Lamar River feeding
the Firehole associations. Promotion requires tracing both gauge and stream to
NWIS and adding the verified attributes to the registry.

### Input and fixture contracts

`observations/met.py` fixes the v1 hourly row order through `MET_COLUMNS`:
`[epoch_s_UTC, air_C, rh_0_1, wind_mps, sw_Wm2, cloud_0_1]`.
`_fit_forcing_arrays` consumes these positions; adding columns requires a v2
schema. Open-Meteo precipitation remains a separate series in mm per step.

The catchment-runoff fixture compares a 9% discharge increase, which shifts
temperature by about 0.1 C. `walk_mps` and `hold_seconds` track velocity and
activity; at least one coupled response must change. The groundwater gain
fixture uses `C = K*W*L/b = 1e-5*20*10/1 = 2e-3 m2/s` and
`q = C*(2.0-1.0) = 2e-3 m3/s`, with inflow at aquifer temperature.

### Terrain bounds

`validation/terrain.py` uses elevation tripwires of -20 to 250 m containing the
recorded raster envelope: minimum -10.89 m, maximum 238.13 m, first percentile
-5.09 m, and 99th percentile 221.28 m. The datum is undocumented; these bounds
serve as consistency checks. They do not establish an absolute elevation datum.
