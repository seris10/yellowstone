# fixes-40: microbial mat coloration and thermal-core terrain

Scope: how the colored microbial mats around Grand Prismatic Spring (and the other Midway pools) are represented in data, in the Python model, in the couplings, and in the Godot world; and how the terrain of the thermal core is represented. Audit by syn, 2026-10-13, at the request of KJR after comparing the world with aerial imagery of the spring.
Code read: `yellowstone_python/yellowstone_python/pool_crust.py` (COLOR_STOPS, make_ramp_stops, render_ramp, render_apron_mask, render_apron_tiles, OUTFLOW_CHANNELS, RECIPES); `yellowstone_midway/shaders/terrain.gdshader`; `yellowstone_midway/shaders/water.gdshader`; `yellowstone_midway/scripts/pool_overlay.gd`; `yellowstone_midway/tools/prepare_world.py` (GRID, STEP, HALF, report notes); `yellowstone_midway/tools/bake_world.gd:38-40`; `yellowstone_midway/docs/AUTHORING.md:66-68`; `yellowstone_midway/references/` provenance JSON.
Related documents: fixes-39 (rendering gaps), fixes-33 (cross-domain wiring), fixes-17 (surface flux), fixes-18 (overland), fixes-27 (groundwater).

## Sources

- Nugent, P. W., Shaw, J. A., and Vollmer, M. (2015). Colors of thermal pools at Yellowstone National Park. Applied Optics 54(4), B128. doi:10.1364/AO.54.00B128. Table 1 gives approximate temperature, observed color and community: 43 C brown, red, green (various algae, protozoa, bacteria); 57 C orange (cyanobacteria and Chromatiaceae); 70 C yellow, green or greenish-yellow (cyanobacteria and Chloroflexus); 75 C yellow (cyanobacteria); 75 C limit to photosynthesis in neutral to slightly basic pools, lower in acidic pools; 83 C pink and 85 C white (chemolithotrophic or heterotrophic bacteria and archaea). It reports Grand Prismatic Spring at about 76 m by 85 m, pH 8.3 to 8.1, temperature 63 C to 74 C, and models pool color with a 1-D radiative transfer model (water absorption and molecular scattering over depth, mat bottom reflectance, surface reflection). Shallow-water color comes mainly from the mat spectrum, deep-water color mainly from the water. It cites seasonal color fading explained by water temperature and UV-visible irradiance rather than chemistry, and notes that the temperature-color relation varies between regions and is not exact for any one pool.
- National Park Service, Grand Prismatic Spring place page: https://www.nps.gov/places/000/grand-prismatic-spring.htm (colorless and yellow thermophiles in the hottest water; orange, brown and green in cooler water).
- USGS, hyperspectral image of Grand Prismatic Spring: https://www.usgs.gov/media/images/hyperspectral-image-grand-prismatic-spring-yellowstone-wy (mat pigment variation with the thermal gradient; image record, no data table).
- Local provenance: `yellowstone_midway/references/dem_pixel_comparison.json` shows a 3DEP `locked_1m` elevation sample returned at the site (2216.95 m), so a 1 m lidar DEM is available for the thermal core; `references/midway_orthophoto_detail.json` records a NAIP export at 0.625 m pixel spacing over the 1280 m core.

## Main problems

### 1. Mat colors are a fixed radial ramp, not a function of temperature, chemistry or light
`pool_crust.py:41-48` defines six COLOR_STOPS by fraction of pool radius, labeled illustrative. `make_ramp_stops` (`:61-79`) shifts two stops by a temperature-gradient factor and darkens the center by depth, but color never depends on the water temperature at that place, on pH, or on irradiance. `shell_for_pool` records the status "colors illustrative, not bathymetry or calibrated pigment". The ramp is computed once per build.
### Fix
Add a mat community model, `yellowstone_python/yellowstone_python/microbial_mats.py`: for each cell of a thermal-core grid, community class and pigment state from local water temperature (Nugent Table 1 thresholds as a registry entry with the citation, temperatures as band edges with the uncertainty the paper states), a pH gate that lowers the photosynthesis limit for acidic water, and a chlorophyll-to-carotenoid index driven by irradiance (from `microclimate.solar_snapshot` and the weather snapshot cloud fraction) so summer mats shift toward orange and red and winter mats toward green. Mats respond over days, not minutes: integrate pigment state with a relaxation time declared as authored until a source is found. Outputs per cell: community class, chlorophyll-to-carotenoid index, an RGB reflectance class, and provenance.
### Test
Temperature sweep reproduces the Table 1 order (white or pink above 80 C, yellow near 72 C, yellow-green near 68 C, orange near 57 C, brown and green below 45 C); an acidic pH lowers the photosynthesis edge; raising irradiance raises the carotenoid index; the relaxation integrates to the steady state for constant forcing.
### Cost
Medium.

### 2. No temperature field exists across the apron or the outflow channels
Each pool has an authored `t_center_c` and `t_edge_c` (`pool_crust.py:24-39`). Nothing computes how outflow water cools as it spreads over the sinter, so a mat model has nothing to read outside the pool rim.
### Fix
Add an outflow sheet-flow energy balance: discharge from each spring split across its outflow channels (problem 3), water temperature along each channel from the surface flux terms already in `replay/surface_flux.py` (net shortwave, longwave, sensible and latent exchange with measured or authored met forcing) for a thin film of known depth and velocity, plus conduction to the sinter as an authored term. Spring discharge and channel depth are data gaps: declare them as inputs with sources or labeled authored values. Publish a per-cell `outflow_temperature_c` field with its forcing time.
### Test
Closed energy budget along a synthetic channel; cooling length scales with discharge and wind as the flux law predicts; outflow temperature at the rim equals the pool edge temperature.
### Cost
Medium to refactor (reuses surface_flux).

### 3. The outflow channels that radiate from Grand Prismatic are not modeled
`OUTFLOW_CHANNELS` (`pool_crust.py:18-20`) holds one entry, the authored Excelsior outflow. Grand Prismatic Spring has an `outflow_bearing_deg` but no channel network. `prepare_world.py` records the Excelsior outflow as "one representative authored branch, not a surveyed hydraulic reconstruction".
### Fix
Derive the outflow network from the 1 m 3DEP DEM and the 0.625 m NAIP detail export: flow routing from the spring rim across the apron (D-infinity or multiple-flow-direction so distributary fans are not forced into single lines), channel masks refined against wet-mat pixels in the imagery, and width estimates per segment. Store as a versioned `outflow_network.json` with source hashes, so problem 2 can route discharge and the renderer can draw the channels.
### Test
Every channel starts at a pool rim and drains downslope on the DEM; network area and orientation agree with the imagery mask within a stated tolerance; the build fails loudly when the DEM tile is missing rather than falling back to a radial guess.
### Cost
Medium (needs the 1 m DEM tile fetched once with provenance).

### 4. Mat coloration is not coupled to anything
No coupling in `coupling.py` or the dashboard inventories carries water temperature, pH or light to mat pigment, or mat pigment to rendering. `pools_state.json` dynamic temperatures reach the pool water shader but not the ramp.
### Fix
Add couplings: pool temperature and outflow temperature to `microbial_mats`; weather snapshot (solar, cloud, season) to the pigment index; overland runoff and snowmelt dilution to outflow temperature where they share cells; `microbial_mats` to a published `mat_pigment` field. Register each in the coupling registry with sign and units.
### Test
Coupling registry check names each exchange; a cooler pool edge in a build shifts the published band edges outward.
### Cost
Cheap once problems 1 and 2 exist.

### 5. Godot draws the mats from a 2 m photo with an artistic color boost
`terrain.gdshader` samples `macro_albedo` (`assets/textures/midway_macro.jpg`, 2048 px over 4096 m, about 2 m per pixel) and applies a "pigment" warm shift selected by color difference inside the thermal mask. `AUTHORING.md:68` states this is an artistic interpretation, not a temperature inversion. `thermal_apron.gdshader` exists and is unused. Pool interiors use the radial ramp through `pool_overlay.gd` and `water.gdshader`. Nothing changes with temperature or season.
### Fix
Publish `mat_pigment.png` (world-space, about 0.25 to 0.5 m per pixel over the thermal core, plus a JSON legend) from problem 1 and rebuild `thermal_apron.gdshader` as the mat material: albedo from the pigment field, wet film darkening and specular where outflow water runs, and the NAIP photo kept only as a validation reference. Replace the pool ramp with a temperature-and-depth ramp from the Nugent radiative transfer model (water absorption and scattering over the shell depth profile with the mat as bottom reflectance). Reload at publish and blend over seasons so changes are gradual.
### Test
Render check at the Grand Prismatic overlook and boardwalk viewpoints; the pigment field changes visibly between a summer and a winter build; with the pigment file absent the shader falls back to today's look.
### Cost
Medium.

### 6. The thermal core terrain is flat at 4 m and has no microrelief
`prepare_world.py:19` sets GRID 1025, STEP 4 m over 4096 m; its report notes "No terrain noise" and that broad channel support banks need local mesh refinement. The sinter apron, the radial channel incisions, terracettes and the raised spring rim seen in aerial imagery are below the grid resolution, so the apron reads as a flat single-color plane.
### Fix
Add a local high-resolution heightfield for the thermal core (about 600 m square around Grand Prismatic and Excelsior): 1 m 3DEP lidar as the base, channel incision and bank geometry from the problem 3 network, sinter rim and terracette microrelief as an authored, labeled layer derived from the imagery (never random noise), and a normal map baked from it. Stitch into the 4 m master grid with shared edge heights. Keep the existing master grid outside the core.
### Test
Core heights match the 1 m DEM within its stated vertical accuracy at control points; the stitch seam has no height discontinuity; walk validator passes on the boardwalk; frame time on the main scene stays within the current budget.
### Cost
Refactor (new mesh tile, bake step and validator).

### 7. No validation of mat appearance against observation
Nothing compares the rendered or modeled mat colors with imagery or measurements.
### Fix
Classify the NAIP detail export into mat color classes (blue water, yellow, orange, brown, green, white sinter) inside the thermal mask and compare with the modeled class map: confusion matrix and per-class area, reported in BUILD.json as validation, not calibration. Add the USGS hyperspectral product if a data file is obtainable, and FLIR or airborne thermal infrared of the outflow for problem 2.
### Test
Validation runs in the build and reports scores; it never feeds back into the model parameters without a declared calibration step.
### Cost
Medium.

## Order
Problem 3 (network) and problem 2 (temperature field) first, then 1 (mat model) and 4 (couplings), then 5 (rendering) and 7 (validation). Problem 6 (terrain) can run in parallel with 1 to 4 because it depends only on the DEM and the network.

## Data to obtain
- 3DEP 1 m DEM tile for the thermal core, with provenance.
- Spring discharge for Grand Prismatic Spring and channel depth or velocity samples for its outflow.
- Thermal infrared of the spring and outflow (ground FLIR or airborne), for problem 2 and validation.
- The USGS hyperspectral product behind the image record above, if a data file is published.
