Yes. And I think the biggest opportunity is not simply finding more scientific Python libraries. It's giving your Yellowstone simulation a proper scientific computing stack, where terrain, hydrology, hydrothermal systems, weather, ecology, and uncertainty are handled by methods designed for those disciplines rather than by a collection of plausible-looking approximations.

Your audit points toward exactly this problem. It identifies authored hydraulic parameters, uncertain temperature boundaries, simplified fish thermal-performance curves, weather scenarios, and terrain validation as potential weaknesses. These are audit findings and hypotheses, not yet independently verified defects in the full codebase.

The important distinction is that real data, scientific methods, and validated predictions are three different things. A USGS measurement can be real while the model using it is scientifically inadequate. A sophisticated solver can be mathematically correct while operating on invented geometry. You need both good observations and the right equations, with validation connecting the two.

## 1. The most relevant scientific Python ecosystem

I'd organize this into layers rather than install a giant collection of packages and hope that scientific credibility emerges from the dependency tree.

[File:Aerial image of the Midway Geyser Basin (view from the east).jpg - Wikimedia Commons](https://images.openai.com/static-rsc-4/ZWKU9h3wCKljS-OlPGg2SPQy7e4cwPFS7aCd2GQ6o4ZZB-GjW3JRc7yhfpocsWKcdzGHWATzOIaEj9gdyOqjT-vq1k6hoziJjvSgw_U4J4vkhKo9e9wti76dOewpw5ZteXsLhu-Sjv5DJDEi1pL8M8h2LyxVqTYUnO6PUkj9YBo?purpose=inline)

A. Geospatial science and terrain

Highest immediate priority

- Rasterio and rioxarray: elevation rasters, georeferencing, clipping, reprojection and raster analysis.
- GeoPandas and Shapely: river networks, drainage boundaries, roads, geothermal features and spatial relationships.
- PyProj: coordinate reference systems and accurate spatial transformations.
- WhiteboxTools: terrain derivatives, flow directions, flow accumulation and watershed delineation.
- xarray: multidimensional scientific datasets indexed by space and time.

These establish whether the simulated world actually corresponds to the geography it claims to represent. [xarray documentation](https://docs.xarray.dev/) · [WhiteboxTools](https://www.whiteboxgeo.com/)

[Base Layer Descriptions | CalTopo Training](https://images.openai.com/static-rsc-4/95x5l8WG31f0nfJBQCBdN-048O5mmnSn5a5oJ2ZAt1pjrWNLOXjYIRLoJwkSA0BQ2HInjcggmhK8qULlSRnqxY1qggZdAsjI5fzre7OvTPhG1-f1l1uuG6z97a_ePxC2i_xUyFOtpEibsQfqRh5vD9yoJQwfglZnxQ6Kydo9NGA?purpose=inline)

B. Hydrology and river hydraulics

Highest priority for the river simulation

- SciPy: numerical integration, differential equations, optimization and interpolation.

- Landlab: interconnected landscape processes, surface-water routing, erosion and hydrologic components.

- Raven with RavenPy: watershed-scale hydrologic modeling, including configurable process representations.&#x20;

  [image](https://www.google.com/s2/favicons?domain=https://ravenpy.readthedocs.io\&sz=32)

  RavenPy 0.21.0 documentation

- FloPy: Python construction, execution and analysis of MODFLOW groundwater models. Useful for subsurface flow and groundwater interactions, not as a river-flow solver by itself.&#x20;

  [image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

  GitHub

- pyHMT2D: Python-based workflows around established 2D hydraulic models such as HEC-RAS and SRH-2D.&#x20;

  [image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

  2D · GitHub



My recommendation: retain your existing custom river model initially. Compare it against an established solver on a small, well-characterized reach before considering a replacement. Two-dimensional hydraulics can be valuable for channel geometry, velocity fields and floodplain exchange, but they bring significant computational and setup costs.

[Grand Prismatic Spring - Yellowstone National Park - 688](https://images.openai.com/static-rsc-4/g-WdXnDQb40cs2r40xtnHNVsnS8K9V9wd7NzEQIKue07H_DdKIiFfACrPXgcZQyzADcSNQZmmecEPuKC26sWx4YimN4VpkRwydQmnd0SVpXCzGbJPGn0d1q337XLron94NsI2P99Nl26Fq6KvRNzQDdpW8HbYqMFjTMKwOZ0gAo?purpose=inline)

C. Hydrothermal processes and water chemistry

- PhreeqPython or a suitable PHREEQC interface: aqueous speciation, mineral equilibria and geochemical reactions.
- CoolProp: thermophysical properties of supported fluids and substances.
- SciPy: heat-transfer calculations, coupled differential equations, parameter estimation and numerical solvers.
- Numba: accelerating computationally intensive numerical loops in custom models.

These become important if the Yellowstone environment simulates more than surface appearance and water temperature. For example, geothermal inflow, mixing with cold groundwater, heat transport through sediments, and chemical changes are interacting but distinct processes.

A caveat: PHREEQC is not a general hydrothermal reservoir simulator, and CoolProp does not automatically provide a complete model of Yellowstone's mineral-rich geothermal fluids. You would still need appropriate constitutive equations, chemical databases and boundary conditions.

[Yellowstone Cutthroat Trout (Oncorhynchus clarkii bouvieri) | U.S. Fish & Wildlife Service](https://images.openai.com/static-rsc-4/2hsC156FjJlsbAufmLbPqp9034FaxDebmHYHwfQLFeA2fzC7wBHonsAK9WWpmUrxoVahm1ZFXlR5DZcwcnUJZxEAFf4Wyt5gKuzvXOkPjWJUdMNllTEFQ1MceG8ztOt3BUp1P3YfdxWGSIgvgvuqbXYQiH9pPt1zYzqvfxsj6bE?purpose=inline)

D. Thermal ecology and fish physiology

There is no single Python package that will turn an arbitrary temperature curve into a validated trout ecology model. This is an area where the scientific literature and data matter more than the name of the library.

- SciPy: fit biological response curves, solve population or bioenergetics equations and integrate exposure over time.

- lmfit: fit nonlinear response models with parameter constraints.&#x20;

  [image](https://www.google.com/s2/favicons?domain=https://lmfit.github.io\&sz=32)

  LMFIT

- emcee: sample parameter distributions using Markov chain Monte Carlo.

- ArviZ and PyMC: Bayesian inference, diagnostics and probabilistic model evaluation.

Build species-specific thermal performance from published experimental measurements, with separate representations for survival, growth, activity, reproduction and temperature-dependent habitat use where evidence supports them.

Crucially, a lethal temperature is not an optimal growth temperature. Nor does a fish's preferred temperature establish its long-term reproductive success. Those are different response variables, and combining them into one weighted score can conceal the biology you're trying to model.

[Yellowstone National Park announces 16th Biennial Scientific Conference on the Greater Yellowstone Ecosystem - Yellowstone National Park (U.S. National Park Service)](https://images.openai.com/static-rsc-4/xeXdoa2AUC1TV0pyJhV08EQSOPMD8fzj04E5l7nxMW3UBRRqOMRbzNY9rqEZ0IY9MgVK-cLppA4-Sh4TDx66hHccRHdfoigdSw1bDKeFfi_tJ-2-YHBWl7sb4Udu4abPUQ1HsipvHKwIFw-uIXS5D-77hz6NZyabMtZeCB0RQvA?purpose=inline)

E. Weather, microclimate and energy balance

- xarray and Dask: process gridded weather and climate data across time and space.

- MetPy: meteorological calculations, thermodynamic diagnostics and weather-data handling.

- wrf-python: diagnose and extract variables from Weather Research and Forecasting model output. It is not itself a weather forecast model.&#x20;

  [image](https://www.google.com/s2/favicons?domain=https://wrf-python.readthedocs.io\&sz=32)

  wrf-python 1.4.2 documentation

- pvlib: solar position and radiation-related calculations that can inform surface-energy modeling, although its primary focus is photovoltaic systems.

This layer can connect measured air temperature, humidity, wind, solar radiation, shade and snow conditions to river heat exchange. It also gives you a path toward spatially varying weather rather than applying one air-temperature value across the whole environment.

[HESS - An improved model of shade-affected stream temperature in Soil & Water Assessment Tool](https://images.openai.com/static-rsc-4/-x63fd6CSyewp_VE1AWfAHA5R5TsG-5JrXGF9GSBiFleoeNEMBmo4XLqlB3JthyZxzTYCOwDf1J8sGbAMF07FjNKH44H-Vl7bZtnB3cxpBvUrvFkpkz73Fkn8vrVnrT8LycuAU93Rq3clsBNuC39EDCx3o2VzRfFYaL_3Ag6klA?purpose=inline)

F. Calibration, uncertainty and reproducibility

- SALib: global sensitivity analysis to identify which parameters drive the results.
- Optuna: systematic optimization and calibration experiments.
- SciPy: conventional parameter estimation and numerical optimization.
- xarray: preserve coordinates, timestamps, units metadata and variable relationships.
- Pydantic: validate data contracts and configuration schemas.
- pytest: regression tests, physical invariants and verification cases.

The goal is to distinguish measurement uncertainty, parameter uncertainty, model-structure error and natural variability. They cannot all be fixed by putting a wider interval around a hardcoded number.

## 2. The libraries for obtaining actual Yellowstone observations

This is a separate layer from the simulation engines. It should retrieve and validate observations before they enter the model.

| Data source or library | Role in your project                                                                            |
| ---------------------- | ----------------------------------------------------------------------------------------------- |
| dataretrieval          | Retrieve USGS streamflow, water-quality and monitoring data where available.                    |
| Siphon                 | Access supported atmospheric and meteorological data services.                                  |
| earthaccess            | Discover and download NASA Earth science datasets.                                              |
| pystac-client          | Search STAC catalogs for satellite imagery, elevation and other geospatial assets.              |
| pandas                 | Clean, align and inspect observation tables and time series.                                    |
| xarray                 | Work with gridded observations and model outputs with explicit spatial and temporal dimensions. |

Useful starting points include the [USGS water data APIs](https://api.waterdata.usgs.gov/), [NASA Earthdata](https://www.earthdata.nasa.gov/) and [NOAA National Centers for Environmental Information](https://www.ncei.noaa.gov/).

One important detail for your project: the existence of a real monitoring station does not mean it measures the variable you need, at the location you need, or at the temporal resolution your model requires. For each measurement, record the station, parameter code, units, time interval, quality flags, observation method and source. Don't silently replace missing measurements with a convenient value.

## 3. What I'd actually implement in Yellowstone Python

I'd start with a relatively small dependency set and introduce specialized solvers only when the model needs them.

## Proposed scientific architecture

01 · Observation and terrain ingestion

USGS · NOAA · DEM/LiDAR · satellite data · field surveys

dataretrieval · pandas · Rasterio · GeoPandas · xarray

02 · Scientific data contracts

Units, coordinate systems, timestamps, provenance, uncertainty and quality flags

Pydantic · Pint · pytest

Hydrology

Flow routing, hydraulics, groundwater exchange

SciPy · Landlab · optional external solvers

Heat and chemistry

Thermal transport, geothermal inputs, mixing

SciPy · PHREEQC interface where appropriate

Atmosphere

Weather forcing, radiation, surface exchange

xarray · MetPy

Ecology

Thermal exposure, habitat suitability, bioenergetics

SciPy · lmfit · PyMC as needed

03 · Verification, calibration and uncertainty

Compare predictions with independent observations, quantify uncertainty, preserve reproducible runs

pytest · SALib · optimization and Bayesian tools

04 · Godot world export

Validated terrain, river geometry, spatial fields and ecological state

Your existing exporter and world-data contracts

I would keep the simulation's scientific state separate from its visual representation. Godot should not need to run a large numerical groundwater solver every frame. Python can generate, calibrate or simulate the scientific state at appropriate time steps, then export spatially resolved results or provide them through a separate simulation service.

## 4. The three investments with the highest initial value

1. Build a data and provenance audit first. For every numeric parameter, classify it as directly observed, derived from observations, literature-derived, calibrated, assumed, or purely illustrative. Store its units, source, applicable conditions and uncertainty. Your existing provenance infrastructure is a natural place to extend this.
2. Validate the hydrology and heat-transfer core. Start with SciPy, xarray and appropriate geospatial libraries. Compare modeled discharge, water levels and temperatures against independent observations. Bring in a specialized hydraulic or groundwater engine only where the existing equations fail to represent a necessary process.
3. Add calibration and sensitivity analysis before adding more complexity. Use SALib and a calibration workflow to determine which parameters actually influence predictions. If the model is highly sensitive to a parameter that has no defensible empirical basis, that's a concrete research priority rather than a guess about which library to install next.

I would also revise one conclusion in the supplied audit: its specific accuracy-improvement percentages, including the projected 15–40% gains and 50–70% uncertainty improvement, aren't supported by evidence presented there. They should be treated as untested hypotheses, not expected outcomes. Establishing a baseline against held-out observations is what will let you quantify genuine improvement.

My overall recommendation: build around NumPy, SciPy, xarray, Rasterio, GeoPandas, dataretrieval and a rigorous validation suite. Then add Landlab, a groundwater or hydraulic solver, and specialized geochemical or ecological tools as the actual equations and research questions demand. The most scientifically impressive model isn't the one with the most dependencies. It's the one that can explain where every important number came from, demonstrate that its equations work, and show where its predictions stop being trustworthy.

---

Yes — given the audit gaps:

- `scipy` (ODE solvers, thermal transport, parameter fits — upgrade `uncertainty.py` from numpy-only)
- `xarray` + `netCDF4` / `rioxarray` (USGS gauge assimilation, LiDAR→cross-section bathymetry, DEM-to-Manning calibration)
- `statsmodels` (calibration regression for `calibrate.py` champion-point ridge fits)
- `uncertainties` (measurement error propagation instead of authored `SCHEMA_UQ`)
- `pyWDM` / `SWMM` / `rivermapper` interfaces (real hydraulic cross-section validation, not authored `DEFAULT_BANK_SLOPE_ZH`)
- `scikit-learn` (species thermal-performance curve validation against lab data)

Current code (`replay/uncertainty`, `calibrate`, `hydraulics`) is numpy-only and explicitly avoids new dependencies. Moving to "scientific grade" means accepting these rather than authored `DEFAULT_` constants.

---

I'd consolidate the two responses into one engineering plan with a clear distinction between scientific dependencies, data provenance, model verification, and empirical validation. The main correction I'd make is that installing scientific libraries does not itself replace authored constants or make a model scientifically valid. Each dependency needs a specific job, and each model component needs tests that can demonstrate whether it performs that job correctly.

For Yellowstone Python, I'd preserve the existing architecture and add capabilities incrementally, rather than rewriting the simulation around a new stack.

## 1. Consolidated scientific stack

| Layer                           | Recommended tools                                                                    | Purpose                                                                           |
| ------------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| Numerical computing             | NumPy, SciPy                                                                         | Numerical integration, optimization, interpolation, thermal transport             |
| Spatial and terrain data        | Rasterio, GeoPandas, Shapely, PyProj, rioxarray                                      | DEM processing, coordinate transformations, terrain and river geometry            |
| Scientific time series          | pandas, xarray, netCDF4                                                              | Gauge observations, gridded weather, time alignment and scientific data formats   |
| Hydrology and hydraulics        | Existing solver, Landlab where applicable, external hydraulic models where justified | Flow routing, river hydraulics, watershed processes                               |
| Calibration and statistics      | SciPy optimization, statsmodels, optionally lmfit                                    | Parameter estimation, regression, residual analysis and confidence intervals      |
| Uncertainty and sensitivity     | uncertainties, SALib, optionally PyMC and ArviZ                                      | Error propagation, sensitivity analysis and probabilistic inference               |
| Thermal ecology                 | SciPy, published experimental datasets, optionally scikit-learn                      | Species-specific response curves, model fitting and out-of-sample evaluation      |
| Data contracts and verification | Pydantic, pytest, Hypothesis                                                         | Input validation, physical invariants, property-based tests and regression checks |

I'd treat `pyWDM`, SWMM, and `rivermapper` as candidates to investigate, not a default dependency bundle. SWMM targets stormwater and urban drainage applications, which makes it a poor default choice for a natural Yellowstone river. Similarly, a package's ability to read a cross-section or route a channel does not establish that it can validate the relevant physics.

The principle is to use established scientific software where it fits the actual process being modeled, and retain custom code where it has a defensible, testable purpose.

## 2. Make provenance enforceable, not just descriptive

Before changing solvers, I'd establish a single contract for every scientific input and derived parameter.

Every value should be classified as one of:

- Observed: directly measured by a documented instrument or survey.
- Derived: calculated from identified source observations using a documented method.
- Literature-based: taken from a cited study, with the study's conditions and applicability recorded.
- Calibrated: estimated from observations by a documented fitting procedure.
- Assumed: selected due to missing evidence, with a justification and uncertainty if defensible.
- Illustrative: chosen for visualization or experimentation, not represented as a measured real-world value.

Each record should carry units, source URL or DOI, source identifier, timestamp or applicable period, spatial reference, quality flags, transformation history, uncertainty and software version where applicable.

A few rules matter particularly:

1. An assumed value must never silently become an observed value because it was written into a JSON file.
2. A missing measurement must not silently become zero flow or a plausible temperature.
3. Derived values must retain links to their source observations and calculation method.
4. Calibration against a dataset must not be reported as independent validation against that same dataset.
5. An illustrative fallback must remain visibly illustrative throughout the export to Godot.

For example, replacing `DEFAULT_MANNING_N = 0.035` with a number estimated from a calibration run does not make that parameter directly measured. It makes it calibrated. You still need independent evidence that the calibrated model predicts the channel's behavior correctly.

## 3. Build the validation suite in six layers

The tests should answer different scientific questions. Passing a test at one layer must not be treated as proof of success at the next.

Layer 1. Data and provenance integrity

Gate 1

Test missing fields, invalid units, duplicate timestamps, impossible coordinates, stale observations, quality flags, malformed source metadata and unmarked fallback values.

Pass condition: every required input satisfies its schema and provenance policy. Missing or suspect observations are explicitly handled, not silently repaired.

Layer 2. Numerical and physical correctness

Gate 2

Test equations against analytical solutions, conservation laws, limiting cases and independently calculated reference results.

Pass condition: the numerical implementation meets predefined tolerances and obeys the relevant physical constraints.

Layer 3. Component integration

Gate 3

Test interactions between terrain, flow routing, tributary inflows, water temperature, atmospheric forcing and ecological response.

Pass condition: coupled components preserve units, spatial references, time alignment, conservation and defined interface contracts.

Layer 4. Empirical validation

Gate 4

Compare predictions with independent USGS measurements, field surveys, weather observations and relevant biological experiments.

Pass condition: performance meets preregistered, process-specific acceptance criteria on observations not used to fit the model.

Layer 5. Calibration, uncertainty and sensitivity

Quantify parameter identifiability, prediction intervals, sensitivity to assumptions, and performance across seasons and flow regimes.

Pass condition: uncertainty is reported honestly, critical parameters are identifiable where claimed, and results are not dependent on one convenient calibration case.

Layer 6. Reproducibility and regression

Run pinned environments, fixed test fixtures, deterministic benchmark scenarios where possible, and versioned reference outputs.

Pass condition: changes can be traced to code, input data, configuration or numerical settings, with scientifically meaningful regressions caught before release.

## 4. What the tests should actually do

### Hydraulics and cross-section geometry

For the existing `replay/hydraulics.py` and `replay/river_world.py` components:

- Test rectangular and trapezoidal channel geometry against hand-calculated area, wetted perimeter and hydraulic radius.
- Verify dimensional consistency in Manning's equation and the units used for discharge, slope, roughness and geometry.
- Test zero flow, shallow flow, very low slope and invalid geometry explicitly.
- Test mass conservation: upstream flow plus inflows minus outflows must equal the change in stored water, within the defined numerical tolerance.
- Compare modeled water levels and discharge against independently sourced field measurements or a verified reference solver.
- Check whether results remain stable as spatial resolution and time step are refined.

A particularly important distinction: a digital elevation model can constrain the channel's surrounding topography but generally cannot reveal submerged bathymetry at sufficient resolution by itself. A cross-section inferred from terrain data should therefore carry a different provenance classification and uncertainty from a surveyed channel bed.

### Thermal and hydrothermal modeling

For `hydro_thermal.py` and the river temperature components:

- Test heat and mass mixing against analytical energy-balance solutions.
- Verify that mixing water streams produces a physically consistent downstream temperature under the model's stated assumptions.
- Test zero tributary inflow, equal-temperature mixing and extreme but valid temperature differences.
- Check energy conservation when heat exchange, groundwater inputs or phase changes are included.
- Compare predicted temperatures against held-out observations at multiple downstream locations and times.
- Test missing data, sensor quality flags, temporal gaps and mismatched measurement intervals.

For a simple two-stream mixing calculation, absent other heat exchange and assuming equal specific heat capacity,

\\[ T\_{\mathrm{mix}} = \frac{Q_1T_1+Q_2T_2}{Q_1+Q_2} \\]

where \\(Q\\) represents volumetric flow. This provides a useful analytical test fixture. It does not validate the more complex effects of geothermal heat transfer, evaporation or changing channel geometry.

### Species thermal performance

For `fish.py`:

- Test that response curves have the expected mathematical properties and valid parameter ranges.
- Compare fitted curves against the original published experimental observations.
- Use study-level or time-blocked holdouts, rather than randomly splitting highly correlated observations into training and test sets.
- Compare against simple baselines, such as a published threshold model or a constant-mean predictor.
- Report prediction error and uncertainty separately for each supported species and endpoint.
- Keep survival, growth, activity and reproduction as separate outcomes unless evidence supports a validated joint model.

`scikit-learn` is useful for fitting and evaluating appropriate predictive models. It cannot establish that a thermal response curve is biologically correct merely because its cross-validation score is good.

### Weather, terrain and uncertainty

For weather forcing and terrain:

- Check coordinate reference systems, raster resolution, nodata handling, units, elevation ranges and spatial alignment.
- Compare weather forcing against independent station observations at the relevant elevation and time resolution.
- Test temporal interpolation and gap filling against deliberately withheld observations.
- Compare terrain-derived slopes and drainage networks against independent reference data.
- Propagate documented sensor and input uncertainty through the model, including correlated uncertainties when relevant.
- Use sensitivity analysis to identify whether outputs depend strongly on poorly supported assumptions.

The `uncertainties` package is useful for first-order propagation of many scalar uncertainties. For nonlinear coupled models, correlated parameters, non-Gaussian distributions or complex output distributions, Monte Carlo simulation or Bayesian methods may be more appropriate.

## 5. Organize the suite around scientific benchmarks

I'd make the benchmark data versioned and separate from the production model. That prevents developers from accidentally tuning the model until it passes the same cases used to judge it.

A possible repository layout:

```
tests/
  unit/
    test_hydraulic_equations.py
    test_heat_mixing.py
    test_thermal_response.py
    test_units_and_contracts.py

  properties/
    test_mass_conservation.py
    test_energy_conservation.py
    test_physical_bounds.py

  integration/
    test_tributary_coupling.py
    test_weather_forcing.py
    test_world_export.py

  data_quality/
    test_observation_provenance.py
    test_missing_data.py
    test_terrain_metadata.py

  benchmarks/
    test_analytical_channels.py
    test_thermal_reference_cases.py
    test_reference_solver.py

  validation/
    test_discharge_observations.py
    test_temperature_observations.py
    test_spatial_holdouts.py

  regression/
    test_versioned_scenarios.py

validation_data/
  manifests/
  hydraulics/
  temperature/
  weather/
  terrain/
  ecology/

reports/
  validation/
  calibration/
  uncertainty/
```

This is a proposed structure, not a claim about the directories already present in your project. It should be adapted to the actual repository after inspecting the current tests, data contracts and build process.

Use `pytest` for test execution and `Hypothesis` for generating edge cases. For each benchmark, record the source, license, units, expected result, acceptance tolerance and reason for choosing that tolerance.

### Metrics should be specific to the process

| Component                 | Useful evaluation measures                                                                      |
| ------------------------- | ----------------------------------------------------------------------------------------------- |
| Discharge and water level | Bias, MAE, RMSE, hydrograph timing and conservation residuals                                   |
| Water temperature         | Bias, MAE, RMSE, seasonal error and downstream temperature gradients                            |
| Terrain                   | Vertical error against independent control points, slope error and drainage-network agreement   |
| Ecology                   | Endpoint-specific prediction error, calibration and performance on independent studies          |
| Uncertainty               | Prediction-interval coverage, interval width, residual structure and sensitivity to assumptions |
| Numerical solver          | Analytical error, conservation error, convergence with refinement and stability                 |

No single metric should be used as a universal pass condition. For example, a high Nash–Sutcliffe efficiency can be useful for streamflow but does not establish that water temperature is correct or that the model's uncertainty estimates are calibrated.

Set tolerances from measurement accuracy, the intended scientific use and benchmark difficulty. Report failures rather than relaxing tolerances until everything turns green.

## 6. Make calibration and validation genuinely independent

This is probably the most consequential part of the plan.

A rigorous workflow separates observations into distinct roles:

1. Calibration data: observations used to estimate parameters.
2. Validation data: observations used to compare candidate models and make modeling decisions.
3. Final test data: observations reserved for an evaluation after the model and acceptance criteria are frozen.

For Yellowstone, random splitting alone can be misleading. Measurements taken minutes apart at the same station may share almost identical weather, discharge and sensor conditions. Instead, consider holding out entire time periods, monitoring stations, river reaches or flow regimes, depending on the prediction you want to support.

Where data are limited, use blocked cross-validation and explicitly disclose its limitations. Never claim geographic generalization if the model was evaluated only on neighboring measurements from the same reach.

Calibration should also investigate parameter identifiability. Manning's roughness, channel geometry and slope can sometimes compensate for each other, allowing multiple parameter combinations to fit the same hydrograph. A good fit does not prove that each fitted parameter represents reality.

For a regression-based calibration, I'd first inspect what `calibrate.py` currently does. `statsmodels` is useful for regression diagnostics and statistical inference; if the existing procedure specifically needs ridge regularization, scikit-learn's `Ridge` is a more direct candidate. Neither should be added until the fitting objective, data splitting and parameter constraints are explicit.

## 7. A practical implementation order

## 01

Establish the baseline

Inspect the actual implementations of `uncertainty.py`, `calibrate.py`, `hydraulics.py`, `river_world.py`, `fish.py` and the existing tests. Inventory dependencies, equations, input data and authored defaults. Produce a machine-readable provenance report without changing model behavior.

## 02

Add scientific invariants

Implement analytical hydraulic and thermal fixtures, unit checks, mass and energy conservation where applicable, and regression tests. These should work even before any new data sources are integrated.

## 03

Integrate observations

Add or improve data retrieval and normalization, then build provenance-aware datasets for a small, well-characterized reach. Verify actual variable availability and spatial correspondence before changing the simulation.

## 04

Calibrate and validate

Establish a baseline score, fit only defensible parameters, compare against simple alternatives and evaluate on independent observations. Add uncertainty and sensitivity analysis around the parameters that matter most.

## 05

Gate releases

Run fast unit tests on every change and the full scientific benchmark suite on relevant changes and releases. Publish a validation report with metrics, data versions, provenance coverage, known limitations and failed acceptance criteria.

## 8. What qualifies as a scientific-grade result?

I'd avoid a single overall "scientific accuracy" score. Instead, give each subsystem a transparent evidence status:

- Verified: the implementation passes mathematical, numerical and physical tests within stated tolerances.
- Empirically evaluated: predictions have been compared with independent observations, with metrics and data coverage documented.
- Calibrated: parameters have been fitted to a specified dataset and fitting procedure.
- Uncertainty characterized: relevant sources of uncertainty have been quantified, with limitations disclosed.
- Research-grade: the preceding evidence is sufficiently strong for the specific scientific claim being made.

These statuses are not interchangeable. A model can be numerically verified but empirically inaccurate. It can also fit one dataset well while failing elsewhere.

My priority would be to get the hydraulic and thermal core through analytical tests, then validate one real river reach against independent discharge and temperature observations. That gives you a defensible reference case for evaluating every subsequent improvement. Once that works, expand outward into terrain, weather, groundwater and ecological coupling.

That approach also protects the project's existing investment: you improve the scientific credibility of the simulation without throwing away its architecture or mistaking a larger dependency list for better science.

---

Yes. The draft is strong on **provenance, validation, and sensible library selection**, but it still reads more like a scientific roadmap than an implementable development specification.

The biggest missing pieces are:

1. **A clearly bounded scientific claim:** what the model predicts, where, at what resolution, and under which conditions.
2. **An observation model:** how simulated quantities become comparable to sensor measurements.
3. **Conservative coupling:** how water, energy, and constituents move between components without being lost or counted twice.
4. **Numerical verification requirements:** convergence, stability, boundary conditions, wetting/drying, and solver failure handling.
5. **Model-structure uncertainty:** uncertainty caused by missing or simplified processes—not just uncertain parameters.
6. **Scientific artifact standards:** reproducible datasets, model configurations, benchmark reports, and citable releases.
7. **A distinction between observed replay and prediction:** replaying measured discharge does not validate a discharge forecasting model.

Below are the research findings and a consolidated, more robust specification.

**Scope:** I checked primary software documentation and USGS guidance. I have not inspected your repository, verified Yellowstone monitoring coverage, or completed a species-specific biological literature review. File names in your document remain proposed inspection targets, not verified descriptions of the implementation.

---

# 1. Research findings: worthwhile additions and corrections

## Scientific tools worth adding

| Tool or standard | Specific contribution | Recommendation |
|---|---|---|
| **FiPy** | Finite-volume PDE framework with transient, diffusion, convection, and source terms. Useful for spatial heat transport and sediment–water heat exchange. | Add as an optional thermal backend or reference implementation. |
| **ANUGA** | Python-based shallow-water modeling for floods and inundation, with compiled extensions. | Evaluate for a small 2D hydraulic reference domain—not a park-wide rewrite. |
| **Clawpack / PyClaw / GeoClaw** | Conservation-law solvers, shallow-water reference problems, bathymetry-aware methods, and wet/dry capabilities in appropriate solvers. | Particularly useful for numerical benchmarks and an alternative hydraulic backend. |
| **MODFLOW 6 + FloPy** | Groundwater modeling; MODFLOW 6 also includes a **Groundwater Energy model**. | Consider for groundwater flow and heat exchange where subsurface observations justify it. |
| **SPOTPY** | Environmental-model calibration, uncertainty, sensitivity, and multi-objective optimization workflows. | A useful alternative to building a custom calibration framework around Optuna. |
| **pyEMU + PEST++** | Model-independent parameter estimation, predictive uncertainty, identifiability, and data-worth analysis. | Consider when spatial parameter fields or external simulators make calibration high-dimensional. |
| **CSDMS BMI / bmipy** | Standardized model initialization, updating, variable access, grids, units, and time metadata. | Adopt a BMI-compatible interface for scientific components. |
| **CF metadata conventions + IOOS Compliance Checker** | Standard descriptions of scientific variables, coordinates, time, and dataset metadata, with automated compliance checking. | Use for exported scientific datasets. |
| **Pint; optionally pint-xarray** | Unit-aware calculations and conversions. | Use at ingestion and component boundaries. Pin and test pint-xarray carefully; its documentation warns that it is experimental. |
| **PhreeqcRM / IPhreeqc** | Geochemical reaction calculations and coupling reactions into transport models. | More appropriate than treating a scalar PHREEQC wrapper as a complete reactive-transport engine. |

These recommendations are supported by the projects’ primary documentation: [FiPy](https://pages.nist.gov/fipy/en/stable/), [ANUGA](https://anuga.readthedocs.io/en/latest/), [Clawpack](https://www.clawpack.org/riemann/Shallow_water_Riemann_solvers.html), [MODFLOW 6](https://www.usgs.gov/software/modflow-6-usgs-modular-hydrologic-model), [SPOTPY](https://spotpy.readthedocs.io/en/latest/), [pyEMU](https://pyemu.readthedocs.io/en/develop/), [BMI](https://bmi.readthedocs.io/), and [PHREEQC](https://www.usgs.gov/software/phreeqc-version-3).

### Important qualification

These are **candidate capabilities, not a mandatory dependency bundle**. Each should enter the project only through a documented decision identifying:

- The scientific question it addresses.
- The equations and assumptions it implements.
- The observations needed to configure and evaluate it.
- Installation, licensing, and computational costs.
- A benchmark demonstrating its value over the current approach.

## Corrections to the existing proposal

### A. Groundwater heat transport deserves explicit consideration

The earlier discussion of FloPy focuses mainly on groundwater flow. MODFLOW 6’s Groundwater Energy model makes groundwater heat transport a relevant candidate.

However, **groundwater heat transport is not equivalent to a boiling, multiphase hydrothermal reservoir model**. It should not be presented as a complete Yellowstone geyser or geothermal-reservoir simulator.

### B. Scientific data need more than xarray attributes

xarray provides labeled arrays, but labels alone do not enforce correct scientific meaning.

Use a pinned, supported version of the [CF conventions](https://cfconventions.org/) for applicable scientific outputs, and run a compatible [compliance checker](https://ioos.github.io/compliance-checker/). Metadata compliance is a useful engineering gate—not evidence that the physics is correct.

### C. Sensitivity analysis needs a dependence policy

[SALib](https://salib.readthedocs.io/en/latest/) offers several sensitivity methods. Classical Sobol analysis typically assumes independent inputs.

If channel geometry, roughness, groundwater inflow, or meteorological forcing are correlated, sampling them independently can produce impossible scenarios and misleading sensitivity rankings.

The specification must require either:

- A scientifically defensible independent-input formulation; or
- A dependence-aware method with its interpretation documented.

### D. First-order uncertainty propagation is not a universal solution

`uncertainties` can handle correlated scalar quantities, but first-order propagation can still be inadequate near thresholds, wet/dry transitions, strong nonlinearities, or phase changes.

Use it for appropriate local calculations. Use joint ensembles or other suitable methods for the coupled model.

### E. Observation retrieval needs API lifecycle management

USGS now documents modernized endpoints for continuous observations, daily values, monitoring locations, time-series metadata, and field measurements.

Build ingestion against a supported `dataretrieval` interface or a versioned adapter to the [modernized USGS APIs](https://api.waterdata.usgs.gov/docs/ogcapi/migration/), rather than embedding legacy endpoint assumptions throughout the model.

### F. Snow and winter processes are a meaningful omission

For seasonal Yellowstone hydrology, explicitly address:

- Snow accumulation and melt.
- Rain/snow partitioning.
- Frozen-ground effects where relevant.
- Ice cover and its effect on river heat exchange.
- Winter boundary conditions.

[SNODAS](https://nsidc.org/data/g02158/versions/1) is a candidate snow-data product, but its outputs must be classified correctly: **a data-assimilation/model product is not a direct local measurement**.

---

# 2. Development specification

# Yellowstone Scientific Simulation — Evidence-Driven Development Spec

## 2.1 Purpose

Develop a reproducible Python scientific simulation that produces spatially and temporally resolved environmental state for a Yellowstone visualization, while supporting **explicit, independently evaluated scientific claims**.

The project shall distinguish:

- Scientific state.
- Observations.
- Parameter estimates.
- Scenario assumptions.
- Visual presentation.

**“Academic-grade” shall not be a global badge.** Evidence shall be reported for individual predictions, components, locations, and operating conditions.

### Initial scientific target

The first release should target a **small, well-characterized river reach**, selected by data availability, rather than the entire Yellowstone environment.

Initial evaluated outputs:

- Water temperature.
- Water level or depth, where suitable geometry and observations exist.
- Discharge only where the model actually predicts discharge.
- Diagnostic water and energy budgets.

Ecological outputs may initially remain literature-informed or exploratory until independently evaluated.

---

## 2.2 Operating modes

Every run shall declare its mode.

| Mode | Meaning | Permitted interpretation |
|---|---|---|
| `observed_replay` | Observed quantities prescribe some or all environmental state or forcing. | Reconstruction, visualization, and evaluation of unprescribed outputs. |
| `hindcast` | Predict historical outputs using specified forcing and frozen parameters. | Independent historical evaluation within documented coverage. |
| `scenario` | Run hypothetical boundary conditions or interventions. | Conditional results—not forecasts with demonstrated real-world accuracy. |
| `illustrative` | Use authored or synthetic conditions for demonstrations. | No empirical accuracy claim. |
| `forecast` | Predict future state using an explicitly defined forecasting workflow. | Available only after forecast-specific evaluation. |

**Required rule:** if measured discharge is prescribed, agreement with that discharge is not a discharge-validation result.

Similarly, if observed water temperature is imposed at a location, that location cannot simultaneously provide independent temperature validation.

---

## 2.3 Scientific claim registry

Each claimed capability shall have a machine-readable record containing:

```text
claim_id
predicted_quantity
intended_use
spatial_domain
temporal_domain
supported_conditions
model_version
required_processes
required_observations
calibration_dataset_ids
evaluation_dataset_ids
metrics
acceptance_criteria
known_exclusions
evidence_artifact_ids
review_status
```

Example claim:

> Predict hourly downstream water temperature for the selected reach during ice-free conditions, given upstream discharge and temperature plus meteorological forcing.

That claim does **not** automatically cover:

- Winter conditions.
- Other reaches.
- Fish population dynamics.
- Geyser eruption behavior.
- Flood forecasting.

### Acceptance criteria

Every claim shall have approved criteria **before final evaluation**.

Criteria shall identify:

- Metrics and required baselines.
- Measurement uncertainty.
- Applicable regimes.
- Minimum usable observational coverage.
- Treatment of missing observations.
- Required uncertainty diagnostics.
- Scientific reviewer approval.

A release with unresolved criteria shall report the claim as **not yet accepted**.

---

# 3. Architecture and component contracts

## 3.1 Proposed architecture

```text
External observations and literature
                ↓
Immutable raw-data snapshots
                ↓
Normalization, quality control, provenance
                ↓
Scientific datasets and parameter registry
                ↓
Initial conditions and boundary conditions
                ↓
Coupled scientific components
  ├─ Hydrology / hydraulics
  ├─ River heat transport
  ├─ Groundwater exchange
  ├─ Weather / radiation / snow
  ├─ Chemistry, where supported
  └─ Ecology, where supported
                ↓
Verification, calibration, independent evaluation
                ↓
Scientific artifacts and evidence report
                ↓
Godot export or simulation service
```

## 3.2 Component interface

Scientific components shall expose a common interface, preferably compatible with CSDMS BMI:

- Initialize from validated configuration.
- Advance to a requested model time.
- Expose state, fluxes, and diagnostic quantities.
- Declare variable units and grid locations.
- Declare time units and update semantics.
- Report solver success or failure.
- Support restart where required.
- Finalize cleanly.

BMI standardizes interfaces; **it does not guarantee conservative or stable coupling**. Those requirements must be implemented separately.

## 3.3 Coupling contract

Each exchanged quantity shall declare:

- Physical meaning.
- Units.
- Sign convention.
- Spatial support: point, cell, face, reach, or domain.
- Temporal support: instantaneous value, interval mean, or interval total.
- Whether it is state, rate, or integrated transfer.
- Source and destination components.
- Interpolation or aggregation method.
- Conservation requirements.

Examples:

- Groundwater inflow is a water transfer with associated thermal energy.
- Solar radiation is an energy flux, not a temperature adjustment.
- Rainfall is a depth rate over area, not directly a river discharge.
- Evaporation may affect both water storage and energy.

**One exchange shall have one authoritative transfer record.** Groundwater heat must not be included both as inflow energy and again as an unrelated geothermal heat source unless they represent physically distinct mechanisms.

---

# 4. Scientific data and provenance

## 4.1 Parameter registry

Every scientifically meaningful input, tunable parameter, boundary condition, and model closure shall be registered.

This requirement does not apply indiscriminately to loop indices or implementation constants.

Classification:

- `observed`
- `derived`
- `literature`
- `calibrated`
- `assumed`
- `illustrative`
- `physical_constant`

Required information:

| Category | Required information |
|---|---|
| Identity | Stable ID, meaning, quantity, units |
| Evidence | Source identifier, URL/DOI where applicable, source version |
| Applicability | Location, time period, species/life stage or environmental conditions |
| Derivation | Input IDs, transformation method, code version |
| Uncertainty | Distribution or error description, dependence group, supporting evidence |
| Missingness | Explicit missing state and reason |
| Governance | Reviewer, approval state, replacement priority |

Unknown uncertainty shall be recorded as unknown—not converted into an invented distribution or zero uncertainty.

## 4.2 Observation schema

Observations shall preserve:

- Station and sensor identifiers.
- Parameter or characteristic identifier.
- Original and normalized units.
- Observation time and interval.
- Time zone and calendar interpretation.
- Measurement depth and position when available.
- Method and quality flags.
- Provisional/approved status where supplied.
- Horizontal CRS and relevant vertical datum.
- Retrieval time and source revision information.

### Critical geospatial requirement

Water level, terrain elevation, and channel-bed elevation cannot be compared unless their vertical references are reconciled.

Gauge height is often referenced to a local gauge datum; it is not automatically an absolute elevation.

### Quality-control policy

Raw values shall remain immutable.

Processing shall produce:

- Original value.
- Quality-control flags.
- Accepted, rejected, or suspect status.
- Any replacement or imputation.
- Replacement method and uncertainty.

No unmarked “repair” of observations is permitted.

---

# 5. Required physical models

## 5.1 Hydraulics

The hydraulic component shall declare its governing model.

Possible levels:

1. Steady uniform-flow relationship.
2. Quasi-steady reach/network model.
3. Kinematic or diffusive-wave routing.
4. One-dimensional Saint-Venant model.
5. Two-dimensional shallow-water model.

The choice shall follow the prediction target.

**Manning’s equation is a resistance relationship, not a complete unsteady river model.** A model based only on uniform-flow assumptions shall not claim to resolve backwater, hydraulic jumps, floodplain dynamics, or transient momentum effects.

Required documentation:

- Cross-section representation.
- Roughness formulation.
- Bed and energy slope treatment.
- Junction rules.
- Boundary conditions.
- Storage formulation.
- Wet/dry behavior.
- Validity limits.

### Geometry requirements

- Distinguish surveyed bathymetry from inferred channel geometry.
- Preserve survey date and processing history.
- Treat DEM-derived submerged geometry as uncertain unless independently supported.
- Record hydraulic-conditioning changes to terrain separately from the original DEM.
- Do not calibrate multiple compensating geometry and roughness parameters without identifiability checks.

## 5.2 River heat transport

The component shall explicitly account for the processes required by the claim:

- Advective energy transport.
- Mixing at tributaries and junctions.
- Shortwave radiation and shading.
- Longwave exchange.
- Sensible heat exchange.
- Evaporative heat exchange.
- Groundwater thermal inputs.
- Bed conduction where relevant.
- Ice or snow interactions when winter claims are supported.

A conservative cell-level formulation is preferred:

\[
\frac{dE_i}{dt}
=
\sum_{\mathrm{in}}\dot m h
-
\sum_{\mathrm{out}}\dot m h
+
\dot E_{\mathrm{surface}}
+
\dot E_{\mathrm{bed}}
+
\dot E_{\mathrm{other}}
\]

where \(E_i\) is stored thermal energy and \(\dot m h\) represents advected enthalpy.

For a restricted single-phase, approximately constant-property model, this can be simplified using \(h \approx c_pT\), with a declared energy reference.

### Required safeguards

- Use mass-based mixing where density differences matter.
- Restrict constant-property approximations to their documented range.
- State whether cross-sectional mixing is assumed.
- Do not claim to resolve narrow thermal refuges using only reach-averaged temperatures.
- Do not enforce a universal 100°C boiling limit; phase behavior depends on pressure and composition.
- If boiling or multiphase conditions are outside scope, flag or reject those conditions rather than silently clipping temperature.

FiPy is a reasonable candidate for a spatial thermal model, but the surface-flux equations and boundary conditions still require scientific justification.

## 5.3 Groundwater and hydrothermal inputs

Initial implementation:

- Represent supported inflows as documented water and energy boundary conditions.
- Quantify uncertainty in flow, temperature, and location.
- Separate direct observations from calibrated source estimates.

Optional advanced implementation:

- MODFLOW 6 groundwater flow and energy models through a compatible FloPy workflow.
- Independently benchmark exchange terms before coupling.

Excluded unless separately developed and evaluated:

- Complete geothermal reservoir behavior.
- Multiphase eruption dynamics.
- Detailed geyser plumbing.
- Unobserved subsurface geometry presented as fact.

## 5.4 Weather, snow, and ice

Meteorological forcing shall declare whether it comes from:

- Local measurements.
- Spatially interpolated observations.
- Reanalysis or another model product.
- Forecast products.
- Synthetic scenarios.

Required handling:

- Elevation and representativeness differences.
- Radiation accumulation versus instantaneous flux.
- Precipitation interval semantics.
- Local wind and shade assumptions.
- Gap filling and its uncertainty.

If winter is outside initial scope, enforce an explicit ice-free applicability gate rather than running summer equations without warning.

## 5.5 Ecology

Ecological responses shall be endpoint-specific:

- Survival.
- Growth.
- Activity.
- Reproduction.
- Habitat use.

Required biological metadata:

- Species and population context.
- Life stage and body size where relevant.
- Exposure duration.
- Acclimation conditions.
- Experimental setting.
- Dissolved oxygen and other relevant covariates.

Temperature suitability shall not be represented as population viability unless that relationship has independent support.

Ecological limitations to investigate include:

- Dissolved oxygen.
- Flow and velocity preferences.
- Refuge connectivity.
- Food availability.
- Competition and predation.
- Recruitment and demographic effects.

Only add these processes when necessary for the intended claim and supported by evidence.

---

# 6. Observation model: the major missing layer

The project shall implement an explicit mapping from scientific state to expected observations:

\[
y = H(x,\phi) + \epsilon
\]

where:

- \(x\) is model state.
- \(H\) maps that state to the measured quantity.
- \(\phi\) includes sensor placement and sampling characteristics.
- \(\epsilon\) represents observational error.

Examples:

- Compare an interval-averaged temperature observation with an equivalent model average.
- Compare stage with the correct gauge datum.
- Account for the mismatch between a point sensor and a cross-section-averaged temperature.
- Compare satellite surface temperature with the corresponding surface quantity—not automatically with bulk river temperature.

The observation model shall document:

- Spatial mapping.
- Temporal aggregation.
- Sensor response where consequential.
- Measurement error.
- Representativeness error.

This prevents apparent model error from being confused with mismatched measurement definitions.

---

# 7. Numerical verification

## 7.1 Required benchmark families

| Benchmark | Purpose |
|---|---|
| Rectangular/trapezoidal geometry | Verify area, perimeter, hydraulic radius |
| Uniform-flow reference | Verify resistance calculation within its assumptions |
| Lake at rest over variable bed | Check well-balanced behavior where supported |
| Dam-break problem | Check transient conservation-law behavior where supported |
| Conservative tracer transport | Check advection and mixing |
| Analytical diffusion | Check thermal diffusion |
| Closed thermal system | Check energy conservation |
| Two-stream mixing | Check junction energy and mass accounting |
| Manufactured smooth solution | Check implementation and convergence of suitable PDE formulations |
| Coupled groundwater/river exchange | Check equal-and-opposite transfers |
| Restart equivalence | Check checkpoint integrity |

Benchmarks shall be applicable to the declared equations. A steady Manning model is not expected to pass an unsteady dam-break benchmark—but it must not claim that capability.

## 7.2 Convergence requirements

For applicable numerical solvers:

- Run at least three systematically refined spatial resolutions.
- Refine time steps separately to distinguish temporal and spatial errors.
- Report observed convergence rates on smooth reference cases.
- Use shock-appropriate measures for discontinuous problems.
- Record solver tolerances and stopping criteria.
- Estimate numerical error for the intended outputs.

A result shall not be accepted merely because it is stable.

### Conservation reporting

Record absolute and scaled residuals, for example:

\[
R_M = \Delta M - (M_{\mathrm{in}}-M_{\mathrm{out}}+M_{\mathrm{sources}})
\]

Scaled residuals shall use a documented reference scale with a floor to avoid misleading near-zero denominators.

### Failure handling

- Nonfinite state: fail.
- Solver nonconvergence: fail or perform a logged, approved retry.
- Negative depth: handle through a documented numerical method, not silent arbitrary correction.
- Numerical clipping: report its magnitude and budget impact.
- Unsupported physical conditions: flag or terminate.

Tolerance changes require review; they shall not be loosened simply to make tests pass.

---

# 8. Calibration, sensitivity, and uncertainty

## 8.1 Calibration contract

Each calibration experiment shall record:

- Parameters and bounds.
- Transformations and priors where used.
- Observation groups.
- Objective or likelihood.
- Treatment of correlated errors.
- Dataset roles.
- Initializations and seeds.
- Stopping criteria.
- Failed-run handling.
- Identifiability diagnostics.

Use SciPy initially. Adopt SPOTPY or pyEMU/PEST++ when their workflows address a demonstrated need.

## 8.2 Identifiability

Required diagnostics shall include appropriate combinations of:

- Parameter correlation.
- Profile likelihood.
- Jacobian or sensitivity conditioning.
- Posterior dependence.
- Multiple-start consistency.
- Synthetic parameter-recovery experiments.

A parameter fitted to data remains **calibrated**, not directly observed.

## 8.3 Uncertainty categories

Report separately where feasible:

1. Measurement uncertainty.
2. Forcing uncertainty.
3. Parameter uncertainty.
4. Initial and boundary-condition uncertainty.
5. Numerical uncertainty.
6. Model-structure uncertainty.

Do not assume these contributions are independent or simply add their variances without justification.

## 8.4 Structural alternatives

Evaluate at least one scientifically meaningful alternative for each high-impact, weakly supported assumption.

Examples:

- Constant versus spatially varying roughness.
- Different groundwater-source formulations.
- Alternative shading descriptions.
- Alternative thermal-response curves.
- Different hydraulic simplifications.

These alternatives are scenario or model-form comparisons unless defensible probabilities have been assigned. Their spread is not automatically a calibrated prediction interval.

## 8.5 Probabilistic diagnostics

Where Bayesian inference is used, require:

- Prior predictive checks.
- Posterior predictive checks.
- Multiple chains where applicable.
- Convergence and effective-sample-size diagnostics.
- Sampler-specific failure diagnostics.
- Sensitivity to consequential prior choices.

[ArviZ](https://python.arviz.org/en/stable/) provides relevant diagnostics and visualizations. A completed sampling run is not evidence that inference succeeded.

---

# 9. Independent empirical evaluation

## 9.1 Dataset separation

Maintain distinct roles:

- Calibration.
- Development/model selection.
- Locked final evaluation.

For temporal and spatially correlated data, use blocked or grouped splits suited to the claim.

The final evaluation dataset shall not influence parameter fitting, model selection, or acceptance thresholds.

If it is used to guide subsequent development, its role must be changed and a new independent evaluation established.

## 9.2 Baselines

Candidate models shall be compared with meaningful simple baselines:

- Persistence.
- Seasonal climatology.
- Simplified heat balance.
- Published biological threshold model.
- Existing custom implementation.

Complexity is justified by improved predictive usefulness, necessary process representation, or both—not by package sophistication.

## 9.3 Required report

Report:

- Bias, MAE, and RMSE where appropriate.
- Flow timing and volume errors where relevant.
- Thermal maxima, minima, and exposure-duration errors.
- Performance by season, station, reach, and flow regime.
- Residual autocorrelation.
- Sample counts and missingness.
- Prediction-interval coverage and width.
- Uncertainty in evaluation metrics, using a method appropriate to dependent data.
- Baseline comparisons.
- Extrapolation warnings.

**A good aggregate score shall not hide failure in an important operating regime.**

---

# 10. Reproducibility and scientific outputs

## 10.1 Run manifest

Every scientific run shall produce:

```text
run_id
run_mode
code_commit
environment_lock_hash
external_solver_versions
input_dataset_ids_and_hashes
configuration_hash
parameter_set_id
random_stream_configuration
grid_and_time_step_configuration
solver_tolerances
restart_information
hardware_and_parallel_settings
claim_ids
warnings_and_failures
output_artifact_hashes
```

Seeds alone do not guarantee bitwise reproducibility across hardware, compilers, or parallel execution. The project shall distinguish:

- Bitwise reproducibility where supported.
- Numerical reproducibility within approved tolerances.
- Scientific reproducibility of conclusions.

## 10.2 Scientific artifacts

Each evaluated release shall include:

- Scientific output dataset, preferably CF-compatible NetCDF where applicable.
- Parameter and provenance registry.
- Benchmark results.
- Calibration diagnostics.
- Independent evaluation results.
- Water and energy budgets.
- Machine-readable gate report.
- Human-readable evidence report.
- Methods, limitations, and bibliography.
- Software and data citation information.

Choose a CF version supported by the validation tooling, rather than blindly declaring the newest version.

## 10.3 Dependency policy

Use separate optional dependency groups:

```text
core
geospatial
observations
thermal
hydraulics_2d
groundwater
calibration
bayesian
chemistry
validation
```

External executables, chemical databases, and geospatial native libraries shall be versioned in addition to Python packages.

---

# 11. Godot export requirements

Godot shall consume scientific results without becoming their undocumented source.

Every exported scientific field shall retain:

- Quantity and units.
- Model time.
- Spatial support and resolution.
- Missing-data mask.
- Evidence status.
- Run and dataset IDs.
- Applicability limits.
- Uncertainty information where available.

Required safeguards:

- Visual smoothing shall not overwrite scientific arrays.
- Artificial river widening or depth exaggeration shall remain presentation-only.
- Interpolation shall be documented.
- Export round trips shall meet approved precision tolerances.
- Scientific resolution shall not be implied by a finer rendering mesh.
- Out-of-domain and illustrative states shall remain identifiable.

If gameplay modifies environmental state, distinguish a prescribed intervention from a validated predictive response to that intervention.

---

# 12. Delivery plan and release gates

| Work package | Deliverables | Exit condition |
|---|---|---|
| **WP1 — Repository and claim audit** | Equation inventory, dependency inventory, parameter audit, claim registry | Existing behavior and unsupported claims documented |
| **WP2 — Contracts and provenance** | Schemas, unit validation, observation adapters, raw snapshots | No unmarked missingness, assumptions, or provenance loss |
| **WP3 — Numerical verification** | Analytical fixtures, convergence studies, budget diagnostics | Applicable implementation tests pass approved criteria |
| **WP4 — Reference reach** | Geometry, forcing, observation model, dataset split | Independent evaluation is feasible for a bounded claim |
| **WP5 — Calibration and uncertainty** | Calibration experiments, identifiability report, joint ensembles | Parameters and intervals are defensible within stated limits |
| **WP6 — Independent evaluation** | Baseline comparisons, regime-specific metrics, final report | Claim-specific acceptance criteria met or failure disclosed |
| **WP7 — Scientific export and release** | Godot contract, reproducible artifacts, methods documentation | Export preserves scientific meaning and release is reproducible |

### Continuous integration

**Every relevant change**

- Unit and schema tests.
- Physical invariants.
- Small frozen numerical fixtures.
- Export compatibility.

**Scheduled or scientific-core changes**

- Convergence tests.
- Reference-solver comparisons.
- Sensitivity smoke tests.
- Restart tests.

**Release**

- Full applicable benchmark suite.
- Reproducible evaluation against frozen datasets.
- Provenance and metadata checks.
- Scientific review of the intended claims.

Live downloads shall not be required for ordinary regression tests. Test API integrations separately from the immutable scientific fixtures.

---

# 13. Definition of done

A subsystem is ready for a scientific claim only when:

- Its equations, assumptions, and limits are documented.
- Its inputs and parameters have enforceable provenance.
- Its implementation passes applicable numerical verification.
- Its component exchanges satisfy approved conservation checks.
- Its predictions have been independently evaluated for the stated domain.
- Important uncertainty and identifiability limitations are disclosed.
- Its results and evaluation can be reproduced.
- Its visualization does not misrepresent resolution or evidence.
- The claim and acceptance decision have been reviewed.

Calibration is not mandatory for every valid model, and passing these gates does not establish universal accuracy. Acceptance remains **claim-specific**.

---

## Recommended first implementation

I would make the first milestone:

> **A reproducible, conservatively coupled river-temperature hindcast for one data-supported reach, with documented geometry, explicit observation mapping, analytical heat tests, independent temperature evaluation, and an evidence-preserving Godot export.**

Start with NumPy, SciPy, pandas, xarray, Pint, Pydantic, pytest, Hypothesis, and the geospatial/observation tools actually needed. Then:

1. Trial **FiPy** if spatial thermal transport warrants a PDE backend.
2. Benchmark hydraulics against **one** suitable established solver.
3. Introduce **SALib** and a joint uncertainty workflow.
4. Evaluate **SPOTPY** or **pyEMU/PEST++** if calibration complexity warrants them.
5. Add groundwater energy or chemistry only after identifying observations and claims that require them.

**Remaining research:** repository inspection, reference-reach selection, actual station/variable coverage, bathymetric evidence, and species-specific experimental literature. The four-search allowance for this reply was exhausted; those targeted investigations remain unfinished. Further research can continue with an increased search allowance.

The strongest improvement is not another library. It is making every important prediction traceable to **equations, observations, numerical evidence, and a precisely bounded claim**.