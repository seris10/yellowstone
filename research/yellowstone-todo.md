# Scientific Rainfall and Hydrology Simulation: Implementation Task List

## 1. Establish the Runtime and Scientific Architecture

- [ ] Verify Python-binding compatibility with the target Godot version.
- [ ] Compare embedded Python, an external Python simulation process, native extensions, and GDScript for scientific computation.
- [ ] Select the supported integration strategy for the chosen Godot release.
- [ ] Isolate Godot-specific APIs behind a thin simulation integration wrapper.
- [ ] Separate the hydrological solver from rendering, user input, and scene management.
- [ ] Define module boundaries for rainfall, infiltration, soil moisture, groundwater, overland flow, terrain, ecology interfaces, and diagnostics.
- [ ] Define a versioned configuration schema for physical parameters and numerical settings.
- [ ] Define a versioned simulation-state schema for exchanging data between Python and Godot.
- [ ] Establish a single authoritative simulation clock independent of rendered frame rate.
- [ ] Separate physical simulation time, accelerated world time, and wall-clock execution time.
- [ ] Define the relationship between Godot world coordinates and physical distances in metres.
- [ ] Standardize internal units for length, time, area, volume, velocity, discharge, and water flux.
- [ ] Use SI units internally and implement explicit conversions for millimetres per hour, metres per second, and display units.
- [ ] Define a reproducible configuration format for soil, terrain, precipitation, and numerical solver parameters.
- [ ] Record the provenance, reference source, calibration status, and uncertainty of every scientifically meaningful parameter.
- [ ] Define a stable interface for receiving external precipitation fields from the future cloud system.
- [ ] Define a stable interface for sending surface-water inflow, groundwater discharge, and precipitation inputs to the future pool and river models.

## 2. Design the Water and Soil Simulation Data Model

- [ ] Define per-cell terrain elevation, cell dimensions, and surface area.
- [ ] Define per-cell surface-water depth and calculate its corresponding water volume.
- [ ] Define per-cell soil-water content, saturation, porosity, and available storage.
- [ ] Define cumulative infiltration and the state variables required by the selected infiltration model.
- [ ] Define root-zone water storage separately from deeper soil and groundwater storage.
- [ ] Define soil hydraulic properties, including saturated hydraulic conductivity and capillary suction.
- [ ] Define field capacity, permanent wilting point, and saturation water content for each soil preset.
- [ ] Define soil-layer thicknesses and the physical depth represented by each storage variable.
- [ ] Define per-face water discharge, flow direction, and friction parameters for overland flow.
- [ ] Define incoming and outgoing water fluxes for every modeled storage compartment.
- [ ] Define canopy water storage if vegetation interception is enabled.
- [ ] Define cumulative precipitation, infiltration, evapotranspiration, drainage, runoff, recharge, and boundary losses.
- [ ] Define diagnostic fields for soil saturation, infiltration capacity, runoff generation, and root-zone water availability.
- [ ] Define explicit boundary-condition metadata for every domain edge.
- [ ] Define ecological output variables that can update continuously without waiting for rainfall-category transitions.

## 3. Implement Continuous Rainfall Generation

- [ ] Define precipitation intensity as a continuous physical flux, expressed internally in metres per second.
- [ ] Convert precipitation intensity to equivalent millimetres per hour for configuration, diagnostics, and user-facing controls.
- [ ] Map the rainfall slider to a continuous intensity function with a clearly defined minimum and maximum.
- [ ] Select and document a linear, nonlinear, or piecewise-smooth slider mapping appropriate to the intended rainfall range.
- [ ] Guarantee that a zero rainfall setting produces zero precipitation flux.
- [ ] Separate the instantaneous rainfall control from the temporal profile of a storm.
- [ ] Integrate rainfall depth over each simulation substep rather than adding a fixed quantity per frame.
- [ ] Convert rainfall depth into water volume using each cell's physical surface area.
- [ ] Implement uniform rainfall as a baseline forcing model.
- [ ] Implement spatially varying precipitation intensity fields.
- [ ] Implement smooth storm-intensity envelopes that support gradual onset, intensification, weakening, and cessation.
- [ ] Compare continuous storm profiles with stochastic rainfall generators based on documented temporal point-process models.
- [ ] Generate spatial rain cells with configurable size, intensity, lifetime, and overlap.
- [ ] Normalize generated rain-cell fields so their intended domain-average rainfall intensity is preserved.
- [ ] Introduce controlled spatial and temporal correlation rather than relying on independent random values in adjacent cells.
- [ ] Advect rain-cell fields using a defined movement vector without coupling them to cloud rendering.
- [ ] Apply smooth spatial falloff functions to rain cells and verify their resulting intensity distributions.
- [ ] Seed the random-number generator and support reproducible rainfall sequences.
- [ ] Define reproducible rainfall presets for constant rain, short intense storms, prolonged light rain, intermittent rainfall, and dry intervals.
- [ ] Preserve integrated precipitation volume when changing simulation timestep, rendering frame rate, or numerical substep count.
- [ ] Define a precipitation-field interface that allows a future cloud model to supply intensity and spatial distribution without changing the hydrological solver.
- [ ] Separate rainfall-field generation from the conversion of rainfall intensity into visible raindrops.
- [ ] Compare raindrop terminal-velocity estimates with published relationships for representative drop diameters.
- [ ] Implement a documented raindrop-size distribution only where drop impacts, splash behavior, or erosion calculations require it.
- [ ] Calibrate visible raindrop density against precipitation intensity without using particle counts as the authoritative water-volume calculation.
- [ ] Quantify the assumptions involved in representing atmospheric precipitation without resolving cloud microphysics.

## 4. Model Rainfall Interception and Surface Input

- [ ] Define whether vegetation canopy interception is included in the initial model.
- [ ] Implement canopy interception storage and throughfall if vegetation-specific rainfall partitioning is required.
- [ ] Limit intercepted precipitation by available canopy storage.
- [ ] Calculate canopy drainage and drip as continuous water fluxes.
- [ ] Track intercepted water separately from ground-level precipitation.
- [ ] Define canopy evaporation as a separate flux rather than silently discarding intercepted water.
- [ ] Partition precipitation among canopy interception, ground throughfall, and precipitation landing directly on open-water surfaces.
- [ ] Preserve water balance when precipitation enters different surface types.
- [ ] Expose ground-level throughfall as the rainfall input to infiltration and surface-water calculations.

## 5. Implement Green-Ampt Infiltration

- [ ] Implement the Green-Ampt wetting-front infiltration-capacity equation.
- [ ] Define the effective wetting-front suction and initial moisture deficit for each soil cell.
- [ ] Calculate moisture deficit from the selected soil-moisture state and appropriate saturation content.
- [ ] Maintain cumulative infiltration and the associated wetting-front state explicitly.
- [ ] Distinguish infiltration capacity from actual infiltration.
- [ ] Limit actual infiltration by the water available at the soil surface.
- [ ] Limit infiltration by the remaining soil storage when the selected formulation assumes finite available storage.
- [ ] Detect the transition between rainfall-limited infiltration and ponding-limited infiltration.
- [ ] Implement the appropriate Green-Ampt cumulative-infiltration equation for the ponded regime.
- [ ] Handle the unponded regime without creating water or permitting infiltration beyond supplied rainfall.
- [ ] Solve the implicit Green-Ampt cumulative-infiltration equation with a safeguarded Newton iteration.
- [ ] Derive a valid upper bound for the Newton iteration from the governing equation and current state.
- [ ] Choose an efficient initial Newton estimate that remains inside the valid solution interval.
- [ ] Verify monotonicity and derivative behavior over the permitted solution interval.
- [ ] Bracket the root before iteration and preserve the bracket after each update.
- [ ] Fall back to bisection or another bounded method when Newton's method leaves the valid interval or fails its convergence test.
- [ ] Define absolute and relative convergence tolerances in physical and numerical terms.
- [ ] Test convergence near zero cumulative infiltration and across very small moisture deficits.
- [ ] Avoid evaluating expressions with zero denominators during dry-start and near-saturated conditions.
- [ ] Implement continuous infiltration updates when rainfall intensity changes during a storm.
- [ ] Define how dry intervals alter wetting-front state and initial moisture deficit.
- [ ] Avoid resetting cumulative infiltration merely because the rainfall rate reaches zero.
- [ ] Reconstruct initial soil deficit consistently from measured or prescribed moisture, cumulative infiltration, and the chosen soil formulation.
- [ ] Compare the Green-Ampt implementation against its analytical cumulative-infiltration relationship.
- [ ] Compare Green-Ampt behavior with the empirical Horton model to quantify the trade-off between physical interpretability and computational cost.
- [ ] Keep any Horton implementation explicitly labeled as an empirical alternative rather than presenting it as equivalent to Green-Ampt.
- [ ] Define the conditions under which a more detailed Richards-equation solver would be scientifically justified.

## 6. Implement Soil Moisture Storage, Drainage, and Groundwater

- [ ] Compile soil presets with documented values for porosity, hydraulic conductivity, capillary suction, field capacity, and wilting point.
- [ ] Match parameter presets to named soil textures and document the source of each value.
- [ ] Distinguish illustrative presets from site-calibrated soil parameters.
- [ ] Update soil-water storage by integrating infiltration and other incoming fluxes.
- [ ] Limit soil-water content to physically permitted storage bounds.
- [ ] Implement drainage from saturated soil and percolation below the root zone.
- [ ] Define drainage behavior between saturation, field capacity, and the lower moisture limit.
- [ ] Make drainage dependent on soil hydraulic properties rather than a frame-dependent constant.
- [ ] Transfer percolated water into a deeper soil or groundwater store instead of deleting it.
- [ ] Implement groundwater storage with an explicit water balance.
- [ ] Define a groundwater recharge interface for soil drainage.
- [ ] Implement optional groundwater baseflow using a documented discharge relationship.
- [ ] Limit baseflow by the groundwater water actually available during the substep.
- [ ] Expose groundwater discharge as an inflow interface for the future river model.
- [ ] Handle dry periods without negative soil moisture or negative groundwater storage.
- [ ] Define a soil-moisture recovery strategy that remains consistent with the selected infiltration model.
- [ ] Test soil storage against controlled infiltration and drainage scenarios.

## 7. Implement Evaporation, Transpiration, and Ecological Interfaces

- [ ] Identify the meteorological inputs required by the selected evapotranspiration formulation.
- [ ] Implement FAO-56 Penman-Monteith reference evapotranspiration when sufficient climate inputs are available.
- [ ] Define the units and sampling interval of radiation, temperature, humidity, and wind inputs.
- [ ] Implement a clearly documented fallback evapotranspiration model for simulations without complete meteorological forcing.
- [ ] Separate reference evapotranspiration from vegetation-specific actual evapotranspiration.
- [ ] Define vegetation or crop coefficients only where the corresponding vegetation representation justifies their use.
- [ ] Calculate soil-moisture stress using a documented continuous stress function.
- [ ] Reduce transpiration as root-zone water availability declines.
- [ ] Limit evaporation and transpiration by the water available in the relevant storage compartment.
- [ ] Separate canopy evaporation, bare-soil evaporation, and plant transpiration.
- [ ] Update soil moisture continuously in response to infiltration, drainage, evaporation, and root-water uptake.
- [ ] Expose volumetric soil-water content and normalized moisture availability to ecological models.
- [ ] Expose root-zone water storage, saturation, and water-stress indicators at the hydrological simulation timestep.
- [ ] Provide continuous moisture signals to plant-growth and vegetation-stress models.
- [ ] Preserve the timing and duration of wet and dry conditions for later ecological response calculations.
- [ ] Expose continuous surface wetness and infiltration-rate signals for soil, vegetation, and habitat models.
- [ ] Prevent ecological outputs from depending solely on discrete labels such as dry, wet, or saturated.
- [ ] Document ecological variables as model inputs or outputs without assuming that one generic water-stress equation applies to every species.

## 8. Implement Terrain, Overland Flow, and Runoff Generation

- [ ] Define a terrain grid with consistent elevations, horizontal spacing, and cell areas.
- [ ] Implement reproducible terrain elevation generation using spectral noise synthesis where procedural terrain is required.
- [ ] Separate aesthetic terrain noise from any elevation data used as a scientifically meaningful land-surface model.
- [ ] Derive cell slopes and face-centered elevation gradients from the terrain grid.
- [ ] Compute flow directions and accumulation using a documented priority-flood depression-handling algorithm.
- [ ] Distinguish terrain preprocessing from dynamic water-flow calculations.
- [ ] Accumulate effective rainfall and infiltration excess into the surface-water storage.
- [ ] Implement face-based discharge updates for surface-water transport.
- [ ] Select and document the intended overland-flow formulation, such as inertial shallow-water, diffusive-wave, or kinematic-wave routing.
- [ ] Derive the chosen governing equations and their assumptions before implementing the numerical fluxes.
- [ ] Implement an inertial friction formulation consistent with the selected shallow-water approximation.
- [ ] Define Manning roughness or equivalent friction parameters with consistent units.
- [ ] Apply friction weighting in the appropriate momentum or discharge update rather than as an arbitrary visual slowdown.
- [ ] Implement wetting and drying limits that prevent unstable flow through effectively dry cells.
- [ ] Define a minimum numerical depth for stable dry-state handling without creating physical water.
- [ ] Prevent water depth from becoming negative during flux updates.
- [ ] Cap each cell's total outgoing water volume by its available surface storage.
- [ ] Scale competing face discharges together when their combined outflow exceeds the cell's available water.
- [ ] Compute candidate face fluxes before committing cell storage updates.
- [ ] Apply internal face transfers conservatively so one cell's outflow equals its neighbor's inflow.
- [ ] Account explicitly for incoming and outgoing boundary fluxes.
- [ ] Configure closed, open, and prescribed-flux boundary conditions.
- [ ] Configure open-boundary outflow using a documented boundary formulation.
- [ ] Route boundary losses through adjusted edge elevations only when the selected boundary geometry requires it.
- [ ] Expose runoff generation and outgoing discharge as interfaces for the future river and pool simulation.
- [ ] Avoid implementing full channel stage or pool-level dynamics in this phase.
- [ ] Distinguish physical surface-water depth from any artistic water-surface offset used in rendering.

## 9. Stabilize Time Integration and Numerical Solvers

- [ ] Establish fixed hydrological simulation timesteps independently of display refresh.
- [ ] Add substep scheduling when the requested simulation interval exceeds the permitted numerical timestep.
- [ ] Derive the relevant Courant-Friedrichs-Lewy (CFL) constraint for the chosen overland-flow equations.
- [ ] Include local water depth, flow velocity, gravitational wave speed, and grid spacing in the applicable stability calculation.
- [ ] Compute a permitted timestep for every substep or spatial region as required by the solver.
- [ ] Limit substeps by both numerical stability and the available execution budget.
- [ ] Preserve integrated rainfall volume when subdividing a simulation interval.
- [ ] Update fluxes in a consistent order so rainfall, infiltration, drainage, and runoff cannot independently spend the same water volume.
- [ ] Define whether the implementation uses operator splitting, a coupled update, or another documented integration scheme.
- [ ] Evaluate the numerical error introduced by the selected process-update ordering.
- [ ] Prevent timestep changes from changing cumulative rainfall or other integrated water inputs.
- [ ] Implement positivity-preserving updates for water depth and soil storage.
- [ ] Define convergence criteria for nonlinear infiltration and any implicit flow calculations.
- [ ] Report solver failures rather than silently accepting unconverged states.
- [ ] Monitor maximum velocity, water depth, Courant number, and minimum cell storage.
- [ ] Compare simulation outputs under successive timestep halvings.
- [ ] Test highly conductive soil, steep terrain, intense rainfall, nearly dry cells, and near-saturated soil.
- [ ] Establish deterministic ordering for face-flux updates and seeded stochastic rainfall.
- [ ] Track numerical residuals separately from physical boundary losses.

## 10. Integrate Python and Godot

- [ ] Implement a Python-facing simulation API that accepts configuration, precipitation fields, and elapsed simulation time.
- [ ] Implement an engine-facing wrapper that passes physical inputs into the solver and returns updated state snapshots.
- [ ] Keep scene-tree operations and rendering updates on the appropriate Godot thread.
- [ ] Evaluate threaded simulation stepping without allowing concurrent writes to shared simulation arrays.
- [ ] Use immutable snapshots, double buffers, or another explicit ownership strategy for solver and renderer data.
- [ ] Define worker-thread failure handling and simulation shutdown behavior.
- [ ] Select contiguous numeric arrays or another suitable storage layout for the hydrological grid.
- [ ] Benchmark numerical kernels before committing to NumPy, native extensions, GPU compute, or other acceleration strategies.
- [ ] Measure data-transfer and synchronization overhead between Python and Godot.
- [ ] Avoid copying full simulation grids between processes or threads when only a smaller set of outputs is required.
- [ ] Expose per-cell water depth, soil moisture, rainfall intensity, and diagnostic fields to rendering systems.
- [ ] Keep the simulation runnable in headless mode for reproducible numerical testing.
- [ ] Test the integration wrapper independently of the scene and visual effects.
- [ ] Profile representative grid sizes and substep counts under realistic storm conditions.
- [ ] Record simulation-step duration, rendering duration, communication overhead, and missed execution budgets separately.

## 11. Render Rain and Water Without Compromising the Physics

- [ ] Treat the hydrological state as the authoritative source of precipitation and surface-water quantities.
- [ ] Render raindrop particles from the physical precipitation intensity field.
- [ ] Derive particle spawn rates from precipitation intensity and an explicitly chosen visual scaling factor.
- [ ] Separate particle count, particle size, and particle velocity from physical rainfall-volume accounting.
- [ ] Map simulated rainfall intensity to continuous changes in visible rain density and streak characteristics.
- [ ] Interpolate visual state between simulation updates without modifying the underlying conserved water state.
- [ ] Visualize water depth using a documented mapping from physical depth to mesh displacement or shader output.
- [ ] Distinguish numerical water depth from visual water-surface smoothing.
- [ ] Expose surface wetness and soil moisture to terrain and vegetation materials.
- [ ] Render splashes, surface disturbances, and wetting effects as consequences of rainfall intensity.
- [ ] Keep artistic ripple animation separate from the water transport solver.
- [ ] Prevent particle pooling or dropped visual particles from affecting simulated precipitation totals.
- [ ] Benchmark particle rendering and water visualization independently of hydrological computation.

## 12. Implement Water-Balance Accounting and Diagnostics

- [ ] Track precipitation volume entering each surface compartment.
- [ ] Track canopy interception, throughfall, and canopy evaporation when interception is enabled.
- [ ] Track infiltration transfers from surface storage into soil storage.
- [ ] Track surface-water transfer between neighboring cells.
- [ ] Track soil percolation and groundwater recharge.
- [ ] Track evapotranspiration losses from the modeled water system.
- [ ] Track groundwater baseflow and other transfers to downstream interfaces.
- [ ] Track boundary outflow and any other explicit losses from the modeled domain.
- [ ] Calculate total water storage across surface, soil, canopy, and groundwater compartments.
- [ ] Verify that internal transfers cancel when calculating the total system water balance.
- [ ] Calculate a water-balance residual at every validation interval.
- [ ] Define absolute and relative water-balance tolerances based on numerical precision and scale.
- [ ] Flag unexplained water creation or loss rather than masking it with corrective visual adjustments.
- [ ] Expose water-balance residuals, cumulative fluxes, and storage diagnostics to test reports.
- [ ] Check that conservation errors remain bounded under changing rainfall intensity and adaptive substepping.

## 13. Validate the Science and the Implementation

- [ ] Verify all physical equations against primary literature, established hydrology references, or recognized technical documentation.
- [ ] Separate physically derived governing equations from empirical parameterizations and artistic controls.
- [ ] Validate soil parameter presets against published datasets or site-specific measurements.
- [ ] Test unit conversions using known rainfall intensities and accumulated depths.
- [ ] Verify that constant rainfall integrates to the expected water depth and volume.
- [ ] Verify that zero rainfall produces no new precipitation volume.
- [ ] Test rainfall accumulation across different frame rates and substep counts.
- [ ] Test spatially uniform rain fields for consistent rainfall delivery across the domain.
- [ ] Test stochastic rain generation for its intended intensity distribution and spatial-temporal statistics.
- [ ] Validate Green-Ampt infiltration against analytical cumulative-infiltration solutions.
- [ ] Test Newton convergence across the full supported soil-parameter range.
- [ ] Test the safeguarded solver near zero infiltration, ponding onset, and near-saturated conditions.
- [ ] Test soil-water storage with controlled infiltration, drainage, and evapotranspiration.
- [ ] Verify that soil moisture never exceeds its physical storage limits.
- [ ] Verify that groundwater storage never becomes negative.
- [ ] Test overland-flow transport on a simple planar slope.
- [ ] Test stationary-water stability where the selected flow formulation is expected to preserve it.
- [ ] Test dam-break front propagation against an appropriate analytical or published numerical benchmark.
- [ ] Test open-boundary discharge and closed-boundary conservation independently.
- [ ] Verify that flow-face updates preserve positivity and respect available cell volumes.
- [ ] Compare solutions at progressively finer spatial and temporal resolutions.
- [ ] Run sensitivity tests for saturated hydraulic conductivity, capillary suction, soil moisture deficit, surface roughness, and terrain slope.
- [ ] Verify that increasing infiltration capacity reduces infiltration-excess runoff under otherwise equivalent conditions.
- [ ] Verify that increasing rainfall intensity produces continuous changes in water inputs and resulting fluxes.
- [ ] Compare simulated precipitation against appropriate rain-gauge or gridded precipitation observations where realistic forcing data are available.
- [ ] Compare simulated soil moisture against observations or documented soil-water benchmarks where available.
- [ ] Record every validation test, expected result, observed result, numerical tolerance, and relevant configuration.
- [ ] Create regression tests that run automatically whenever the numerical solver or configuration schema changes.

## 14. Optimize Performance Without Sacrificing Validity

- [ ] Benchmark rainfall generation, Green-Ampt infiltration, soil storage, and overland flow as separate numerical kernels.
- [ ] Measure execution cost as a function of grid resolution, active rain cells, and required substeps.
- [ ] Identify the operations that dominate runtime before introducing parallelization.
- [ ] Precompute terrain-derived quantities that do not change during simulation.
- [ ] Cache static soil and hydraulic parameters in an efficient array layout.
- [ ] Reuse temporary buffers to reduce per-step allocations.
- [ ] Evaluate vectorized numerical operations before adding more complex execution infrastructure.
- [ ] Evaluate parallel computation or GPU acceleration for operations that can be safely performed independently.
- [ ] Preserve deterministic validation paths when adding optimized execution paths.
- [ ] Compare optimized outputs against the reference solver within defined numerical tolerances.
- [ ] Define a minimum supported resolution and a documented performance target.
- [ ] Reduce visual particle workload independently from physical precipitation intensity when performance requires it.
- [ ] Avoid reducing water storage, rainfall volume, or ecological update frequency without documenting the resulting approximation.

## 15. Prepare the Interfaces for Later Simulation Sessions

- [ ] Publish continuous precipitation fluxes to the future cloud-to-rain interface.
- [ ] Publish ground-level precipitation and interception losses to the land-surface model.
- [ ] Publish infiltration, surface-water depth, soil moisture, and drainage to ecological and geological models.
- [ ] Publish spatially distributed runoff discharge to the future channel and pool models.
- [ ] Publish groundwater recharge and baseflow to the future river model.
- [ ] Define downstream interfaces in terms of physical fluxes, volumes, storage, and elevation rather than rendering-only values.
- [ ] Preserve substep-resolved flux information where downstream models require finer temporal resolution.
- [ ] Ensure that later river and pool models can return water-stage or boundary-condition information without rewriting the rainfall generator.
- [ ] Keep cloud motion, cloud formation, condensation, and cloud rendering outside the rainfall solver's initial implementation.
- [ ] Keep detailed pool-level, river-stage, backwater, and channel-routing dynamics outside this phase while preserving the required interfaces.
- [ ] Document the assumptions, limitations, dependencies, and validation status of the complete rainfall and land-water model.