# Yellowstone · Midway: development specification and future directions

Research and implementation date: 7 October 2026 UTC. Geographic reference epoch: the documented source layers, especially USDA NAIP imagery acquired **19 July 2022**. This is a landscape development project, not a current visitor map or a scientific prediction product.

## 1. The intended experience

Begin on the Grand Prismatic overlook. The spring should occupy the correct portion of the view, with the Firehole corridor behind it, a low forested ridge enclosing the scene and recognizable mineral drainage patterns around the water. Walk down the actual trail alignment, continue to the boardwalk or the road, and encounter changes in sound, vegetation and wildlife appropriate to the habitat. The environment has physical scale and coherent spatial relationships. There are no quests, scores, survival meters or progression requirements.

The first domain is a **4,096 m square** around 44.525° N, 110.837° W. Its area is approximately 16.78 km². It contains the Midway thermal group, a real Grand Loop Road section, the Fairy Falls/overlook approach, the Firehole River, other mapped waterways and waterbodies, and surrounding terrain. The named thermal core receives the most deliberate attention. Other included terrain supplies context and space for subsequent hand work; its inclusion does not mean every square metre has received a finished environment-art pass.

A smaller finished place is a better expansion unit than a compressed park. Retain these distances when adding Yellowstone's other regions. NPS describes the overlook approach as approximately 0.6 mile one way with 105 ft of climb; those measurements are a reference check on trail scale, not permission to replace its geometry with a straight line. [G1]

### Completion vocabulary

| Label | Meaning in this project |
|---|---|
| Source-derived geometry | Positions obtained from the supplied USGS/NPS geographic data, with source accuracy preserved in documentation |
| Authored adaptation | An explicit design decision, such as a bridge deck height, road width, small channel width or underwater floor |
| Fixed placement draft | A saved initial arrangement proposed offline from the reference cover; it is editable, has stable identifiers and is never resampled during play |
| Original visual stand-in | Code-authored development geometry that demonstrates placement/behavior and needs a specialist art replacement |
| Illustrative simulation | A computationally coherent model with chosen coefficients; it is not a calibrated reproduction of present Yellowstone conditions |
| Future direction | A specification or prompt whose implementation is not silently counted as complete |

Use these labels in future milestone reviews. A convincing screenshot alone does not establish geographic, biological or numerical accuracy.

## 2. What is implemented

The runnable project includes native Godot scenes, a first-person character, the fixed terrain and landscape, surface materials, imported creator-made grasses, reduced versions of a creator-made pine, ambient Yellowstone recordings, visual steam, a shared environmental model and sparse animated wildlife stand-ins. Starting-place buttons make it practical to review distant portions without requiring a long walk on every test. They do not modify map distances.

The code compiles geographic data offline. Launching the game loads saved assets. It does not create a seed, invent hills or trails, scatter trees around the player, regenerate shorelines, or alter the landscape as a consequence of simulation. Surface ripples, moving foliage and ecological state are time-dependent, as they should be. Static geometry and ecological state are separate authorities.

The texture strategy uses geographic macrocolor to preserve large mineral aprons, forest openings and ground patterns, then adds creator-made repeatable ground detail at physical texture scales. This produces a useful recognizable base while preserving the opportunity to paint or replace the photographic layer. It also has a known limitation: a nadir aerial contains existing tree crowns, shadows and directional lighting. Close-range ground should eventually be reconstructed under the tree meshes rather than retaining those photographic signals.

The separate botanical scene adds thirty original willow, sedge and lupine genus/guild clumps at fixed saved transforms. These demonstrate distinct plant forms and habitat eligibility; they are not botanical specimen scans or observations of those exact individuals.

Read the supplied `VALIDATION.md` for the checks actually completed. Read the asset manifest for what was actually bundled. The species catalogue is a research and implementation catalogue, not a count of finished animal and plant models in the scene.

## 3. Geographic authority and scale

### Coordinates

The coordinate reference system is **WGS84 / UTM zone 12N, EPSG:32612**. The local origin is:

- Easting: `512952.5950985841 m`
- Northing: `4930199.044097667 m`
- Vertical offset: `2200.0 m`, with the DEM elevations treated as NAVD88

For projected east/north/elevation values:

```text
x = easting − 512952.5950985841
y = elevation_NAVD88 − 2200.0
z = 4930199.044097667 − northing
```

The mapping is intentionally east/up/south. North on the in-game map is negative z. Do not silently exchange ellipsoidal GPS height and orthometric DEM elevation. Do not assign raw UTM coordinates to a float32 Godot transform. Store geographic coordinates and tile indices in data, then convert to nearby local positions. Godot's documentation explains why precision declines far from the origin and why a centered, limited domain can use ordinary float32 transforms. [T1]

### Terrain

The source raster is retained unmodified. The playable raster has 1,025 samples on each axis at 4 m spacing, so the distance between its outer sample centers is exactly 4,096 m. The geospatial acquisition uses pixel edges extended by half a sample so the exported pixel centers land on that grid. The renderer uses 256 tiles, each covering 256 m with 65 × 65 vertices. Adjacent tiles read the same outer sample row/column. Normals use derivatives of the full source grid, not derivatives of a separately cropped tile.

Underwater cuts, road grading and small channel work are separate authored adaptations written into the playable raster. The adaptation compiler does not mutate the original DEM. Underwater floors are not a bathymetric survey. A terrain heightfield can only describe one height at a horizontal point; detailed crater walls, overhangs, bridge cavities and undercut banks require additional meshes. Godot documents these heightfield restrictions and recommends high precision height data rather than 8-bit imported height images. [T2]

The current vertex spacing does not resolve every ditch, plank, pool rim or small stream bank. A 4 m mesh must not be promoted to a claimed 4 m source accuracy. For the thermal core, the next close-range terrain pass should use the finer underlying elevation source and explicit rim meshes, while maintaining the shared 4 m outer boundary. The geographic research document records the source resolution evidence and limitations.

### Roads, trails and bridges

The supplied NPS linework determines the alignment. Road width, thickness, crossfall, drainage and bridge engineering remain explicit authored parameters. A broad asphalt road and a narrow boardwalk require different materials, collision construction and verge treatments. Do not turn every GIS line into a road. The Fountain Freight alignment overlaps the Fairy Falls approach in the source data and must not become duplicate stacked pavement.

The initial build unifies shared endpoints and ramps nearby elevations to them. This removes vertical steps caused by independently sampled segments. A larger system should replace endpoint-only logic with an explicit transport graph: every junction has an identifier, a shared vertical datum, a structure type and an ordered set of connected edges. Bridges must span a carved channel without raising terrain into a dam. Walking verification should include both banks and both ends of each deck, not simply a screenshot from the middle.

## 4. Ecology should follow the place

The thermal core is not a display case for every Yellowstone organism. Its visual diversity comes partly from the sharp transition between biologically rich hot-spring margins and ordinary terrestrial/riparian habitats. Microbial communities, cool wet ground, forest openings, dead wood, standing conifers and a flowing river require different eligibility rules.

The ecology research supplies 56 species, guild or association entries with evidence classes. Some are documented for the local corridor; some are known park-wide and remain candidates pending a local survey. Some are appropriate only for geographic extensions. Preserve that distinction. A generic imported pine is not evidence that the exact species has been represented botanically. A generic grass tuft is a useful visual asset, not a specimen identification.

### Microbial mats and thermal water

Grand Prismatic's deep hot center and colored edge should not be modeled as a single shallow painted pond. NPS describes Grand Prismatic as about 200–330 ft across and more than 121 ft deep; Excelsior is a large crater with substantial continuing discharge to the Firehole. [G2] Retain the mapped water outline, then author the crater, shallow shelves, wetted rim and drainage apron as separate features. The current ordinary terrain cut only supplies a visual floor.

The apparent color depends on temperature, water depth, substrate and biological pigments; season and lighting also matter. A single universal equation mapping temperature to rainbow hue is not a sufficient ecological model. Likewise, the photosynthetic upper temperature limit applies to the particular microbial/process context described by the scientific source, not to all life. Preserve the more careful treatment and citations in `ecology-research.md`.

USGS thermal-area maps distinguish hydrothermal ground and altered substrate from ordinary vegetation cover. Those polygons should become a first-class eligibility layer in a future art pass. Sparse surviving, stressed or dead vegetation at a thermal boundary can be meaningful; a forest scatter crossing every bright patch is a masking failure. [G3]

### Fish, birds and grazers

The Firehole's fish history differs from that of Yellowstone Lake. Use the locally appropriate introduced-trout context in the catalogue. Temperature can affect activity, refuge selection and visibility; a simple suitability index should never be presented as a mortality prediction. Ordinary fish do not inhabit the hot centers of Grand Prismatic or Excelsior.

Dippers, geese and river-edge insects provide small-scale observation opportunities without requiring a large staged herd in every view. Sparse bison or elk belong on ordinary suitable ground, with species identity and local occurrence handled carefully. Habitat polygons should prevent an animal route from crossing hot pools, cliffs, buildings or deep water merely because a straight line is shorter.

Do not install a universal `wolves → fewer elk → more willow` slider. Yellowstone contains interacting herbivores, hydrology, soils, climate, beavers, predation and different vegetation histories. The research guide includes evidence and caveats for richer models. Maintain multiple hypotheses where the evidence does not support a single causal chain.

## 5. Numerical models and their boundaries

### A fixed world can use mathematical authoring aids

Mathematics is useful for checking and proposing arrangements without making the shipped world procedural. A habitat-aware point process can propose a planting pass. The accepted output must then become stable, reviewable scene data. That is how the initial vegetation layer is stored here: explicit records with identifiers, transforms and variation keys.

For a future proposal tool, define a suitability field rather than one uniform density:

\[
\lambda_s(p)=\lambda_{s,0}\,M_{habitat}(p)\,f_s(soil, moisture, slope, aspect, canopy, disturbance)\,M_{exclusion}(p).
\]

The function and coefficients are artist/science inputs, not inferred truth. A minimum separation or pair-correlation target can avoid identical spacing. Seed-tree clusters, recruitment patches, fire history and mortality gaps can produce several local patterns. Do not use a single Poisson-disc radius for every plant category. The resulting proposals require visual and habitat review and can be modified by hand. Runtime receives the approved coordinates, never the probability field.

### Heat and flow

The river model uses a small fixed set of reaches. A useful finite-volume heat formulation is:

\[
\frac{d(V_i T_i)}{dt}=\sum_j Q_{ji}T_j+Q_{hot,i}T_{hot,i}-Q_{out,i}T_i
+\frac{V_i(T_{air}-T_i)}{\tau_i}.
\]

Here volume is in m³, discharge in m³/s, temperature in °C, and time in seconds. Density and heat capacity cancel in the simplified constant-property mixing equation. They must return if the model compares actual heat power, evaporation, variable density or phase change. The atmospheric term above is a relaxation approximation; it is not a full radiation/convection/evaporation calculation.

For a constant-volume reach, require `Qout = sum(Qin) + Qhot`. A simple mixing check is `Tmixed = (Q1*T1 + Q2*T2)/(Q1+Q2)`. Report both boundary fluxes and state changes. A shader moving a normal map is an optical effect, not a mass-transport solver.

The NPS descriptive discharge of more than 4,000 US gallons per minute at Excelsior converts to a lower reference near 0.252 m³/s. The project uses a stated scenario value around that reference; it is not a live measurement. [G2] Do not label simulated river temperatures with the precision of a field instrument. Use stability limits or substeps if the volume/time-step relation changes. If a future real dataset is added, store observation date, location, unit, uncertainty, instrument context and calibration method separately from model parameters.

### Vegetation and insects

Slow patch-level biomass can use bounded logistic growth with moisture/light modifiers and explicit grazing removal:

\[
\frac{dB}{dt}=r f_{light} f_{water} B(1-B/K)-G.
\]

This is a computational scaffold. It does not identify species composition, forage quality, seasonal phenology or carrying capacity by itself. Biomass units must remain explicit. If values are normalized indices, label them as such instead of claiming kilograms.

Insect activity can depend on temperature, wind, moisture, flowering stage and time of day. A bird's foraging behavior can then query that activity, rather than every animal following a timer unrelated to its environment. Do not expect a realistic annual plant change to be obvious in ten minutes of walking. Show short-time behavior at ordinary speed and reserve ecological time-lapse for an explicitly labeled review mode.

### Shared environmental signals

Use one authority for wind direction and time. Foliage bend, steam drift, insect exposure and audio gain can consult it. Avoid separate sine waves that imply a different prevailing wind for each subsystem. Visual gust detail may be layered over the common low-frequency wind. Distinguish the rendering clock from physical transport time and seasonal ecological time.

## 6. Rendering and asset strategy

### Finish the near view first

The priority observation ranges are 0–5 m, 5–50 m, 50–250 m and the landscape beyond. Each needs a different technique. At shoe height, bark scans and coarse aerial imagery cannot replace actual twigs, pebbles, roots, soil breakup and contact shadows. At the overlook, the spring silhouette, rim drainage, forest edge and haze matter more than individual needles.

Pine geometry is derived from a verified human-authored Poly Haven asset. The source is too dense for direct forest instancing, so the project includes reduced forms with the creator's bark and foliage imagery. Source-derived cards retain useful silhouette and color while limiting geometry. The manifest records the derivative and creator attribution. These assets are generic visual pines; selecting and tuning a proper lodgepole set remains a necessary botanical art task. Poly Haven licenses its actual assets CC0; its website renders and other page content have different terms. [A1]

The grass set contains individual tufts, not a runtime patch-scattering dependency. Imported foliage uses alpha-cutout material with a real alpha channel. Do not rely on a JPEG alone to carry transparency. Inspect cards from front, side, back, low angle and distance; bad borders often hide in a single frontal screenshot.

### Manage distances by space

Godot MultiMeshes draw their instances together; individual instances are not culled independently. Split vegetation into spatial groups and apply coherent detail levels. [T3] Do not solve performance by turning off arbitrary plants inside a protected viewpoint composition. Account for GPU cost, draw calls, alpha overdraw, shadows and CPU traversal, not only polygon counts. Godot's visibility ranges can replace near geometry with coarser representations, but transitions and bounding boxes must be tested. [T4]

The present Compatibility rendering baseline prioritizes broad desktop execution. A Forward+ quality profile can add local volumetric fog, SSAO/SSIL, better reflections and more extensive atmospheric work. Those are renderer-specific features and must be evaluated on target hardware. Increasing every setting is not an environment-art pass. Add optional features in budgeted groups and keep a consistent fallback.

### Audio should belong somewhere

The included NPS recordings were made in Yellowstone, with exact recording location retained. A recording from Geyser Hill is not relabeled as a microphone at Midway. Use it as an explicitly adapted sound source until a more precise location recording is selected. The NPS sound library states that its available recordings are public domain and requests appropriate National Park Service credit. [A2]

A future audio pass should author source positions, near/far attenuation, wind-exposed clearings, forest shelter, river-bank occlusion and distinct animal sources. It should also inspect each loop seam and avoid excessive simultaneous species calls. A sound recorded during a spring chorus should not play continuously in a late-summer afternoon merely because the file is available.

## 7. A practical order for further work

### Milestone A: one finished walking route

Finish the overlook-to-basin experience before extending the boundary. Inspect the trail from standing eye height, every 20–30 m and at every bend. Correct river banks and bridge transitions, then refine the overlook deck, boardwalk details, pool rims, mineral microrelief, close vegetation and ground contacts. Remove aerial canopy/shadow artifacts beneath new trees. Replace development fauna in this route with verified suitable models and minimal but convincing animation.

Acceptance: no open seam or forced jump along the intended walking path; no floating plant, root or log; no road embedded in the channel; no billboard silhouette failure at a planned viewpoint; no ordinary wildlife in the hot center; no claims of survey accuracy beyond the sources. Save before/after eye-height captures and a list of deliberate deviations from reference.

### Milestone B: connected local water and habitats

Upgrade river banks with cross-sections, continuous water surfaces and visible shallow substrates. Author wetland margins and off-channel habitat only where the sources support them. Extend the current six serial thermal reaches into spatial mixing fields and verified habitat/refuge queries. Refine the existing dipper, insect and grazer observations with reviewed assets and richer behavior. Verify every actor remains in valid habitat while crossing a tile boundary.

Acceptance: matching boundary fluxes, no temperature impulses caused by streaming, no upstream-flowing visible water, stable states after a long pause, and predictable restoration after an actor or tile reload.

### Milestone C: seasonal and disturbance versions

Create alternate authored summer, autumn and winter appearance layers with the same geographic topology. Add snow depth in metres with aspect, canopy, wind and thermal-ground influence; prevent thermal zones from acquiring a uniform white blanket. Store stand age and disturbance history as explicit patch data. A season switch should alter surfaces and phenology without moving the road or changing the measured distance to a viewpoint.

Acceptance: season-specific assets are explained by habitat and time, not randomly chosen; source dates are visible in provenance; material transitions remain coherent across tiles; no scientific forecast is implied by illustrative snow or biomass coefficients.

### Milestone D: continuous geographic extension

Add adjacent UTM-aligned tiles. Each tile has a unique key, source epoch, border sample contract and route/water graph ports. Retain boundary nodes even when their neighboring tile is unloaded. The present square does not need world-origin rebasing; an extensive park network eventually does. Implement origin shifts as a tested coordinate transform for physics, camera, particles, trails, audio and shaders, with high precision geographic positions kept outside float32 vectors.

Acceptance: crossing the old boundary preserves distance, heading, elevation and simulation state. Water passing across a tile edge remains one flow. Revisited tiles reproduce the same authored scenery and remembered ecology.

## 8. Geographic extensions without compressing the park

| Extension | Why it adds something distinct | Required new work |
|---|---|---|
| Fairy Falls and adjacent country | A coherent continuation of an existing mapped trail | Extend the crop to the actual falls; detailed fall/stream geometry, wet cliff habitat and a waterfall sound field |
| Lower Geyser Basin / Fountain area | Additional hydrothermal and meadow settings along the real road network | New thermal-area map, correctly classified feature types, mud/sinter material distinction and species eligibility |
| Upper Geyser Basin | Dense geyser, hot-spring and visitor-path relationships | Time-dependent geyser plumbing model with a clear observational basis, boardwalk network, authored structures and distinct eruption assets |
| Firehole Canyon / Madison | More confined river scenery and a natural downstream continuation | Canyon meshes, banks, whitewater classification, shadows and stream junctions |
| Hayden Valley | Larger grasslands and Yellowstone River habitat | A separate genuine location, river wetlands, grazer movements and soil/vegetation differences |
| Lamar Valley | Northern-range grassland, riparian and wildlife observation contexts | Actual connecting distances or an explicit region-selection loading screen; richer herbivore/predator habitat models |
| Canyon / Lower Falls | Erosion, canyon walls and a very different visual scale | Full cliff meshes, waterfall spray, long-range lighting, paths and viewpoints measured from source data |
| Yellowstone Lake / West Thumb | Large-water optics and lake/thermal adjacency | Bathymetry where licensed, shoreline waves, lake ecology and correct native/non-native fish context |
| Mammoth terraces | A chemically and visually different thermal landscape | A travertine/calcite deposition model, terrace geometry and correct limestone-derived mineral system |

Mammoth cannot be implemented by whitening the Grand Prismatic shader. NPS distinguishes calcium-carbonate travertine terraces from the siliceous deposits associated with other hydrothermal features. [G4] Likewise, NPS links different Yellowstone vegetation patterns to geology and soils; Hayden or Lamar should not inherit Midway's forest eligibility mask. [G5]

These are proposed extensions. Their names do not mean they are all already present in the 4.096 km crop. For discontinuous development, a transparent region-selection screen is preferable to moving far-apart places closer together.

## 9. Ready-to-use implementation prompts

Each prompt assumes the implementer receives this entire project, preserves its existing files, and checks the source/asset manifests first.

### Prompt 1: finish Grand Prismatic at walking distance

> Extend this exact Godot project. Preserve the EPSG:32612 origin, one-metre units, source DEM and existing route alignments. Finish the Grand Prismatic/Excelsior walking core. Replace the crude underwater terrain adaptation with authored pool-shell and rim meshes, preserving mapped water outlines and explicit connections to the outflow channels. Use the retained NAIP reference and verified NPS/USGS photographs to sculpt drainage fingers, wet sinter, crust fragments and small terrain transitions. Do not alter pool size for composition. Remove aerial tree/shadow imprints only where a hand-art ground reconstruction replaces them. Keep human-authored assets and exact licenses. Deliver updated scenes, a visual deviation ledger, before/after standing-height screenshots and collision verification along the complete boardwalk approach.

### Prompt 2: convert the planting draft into authored ecology

> Use `data/placements.json` as the existing drafting layer; do not regenerate it or invent a new seed. Work through visible stands around the overlook route. Assign each stand a justified vegetation type, disturbance history and density pattern using `species_catalogue.json` evidence classes. Replace the generic pine with a verified, suitable lodgepole visual or explicitly mark the chosen visual's limits. Edit stable transform records and `handcrafted_details.tscn`. Add shrubs, grasses, flowers, recruitment, snags and down wood where habitats support them. Preserve thermal and water exclusions. Deliver a reviewed area polygon, an ID-level change list and screenshots at 2 m, 20 m and 200 m viewing ranges.

### Prompt 3: implement physically coherent river reaches

> Preserve the fixed mapped Firehole centerline and confluences. Replace the uniform-width adaptation with authored cross-sections, bank meshes and per-reach depth/velocity fields. Keep surface elevation continuous and downstream-monotone. Upgrade the reduced heat model using explicit units, boundary inflows, thermal sources and atmospheric heat exchange. Save every calibration observation with date and uncertainty. Include conservation tests for volume and heat, stable stepping under low/high flow, and a visualized thermal mixing plume. Do not infer that a fixed discharge number is a contemporary measurement. Extend the existing temperature-based fish activity query with hydraulic conditions and independently verified refuge habitat.

### Prompt 4: improve wildlife without adding game progression

> Replace the existing wildlife stand-ins with individually verified free-to-personal-use human-authored models. Keep catalogued presence/evidence classes and actual metre dimensions. Add short behavior sets such as graze, move, rest, look, forage, perch and take-off. Use habitat-constrained navigation and suitable ground/water queries; no bird or grazer may follow a path through a hot pool. Connect insect activity, temperature and vegetation state to behavior where justified. Use sparse authored actor records and persistent IDs. Avoid population claims, constant predator spectacle and sound loops that imply an unrealistically dense assemblage. Deliver model/license files, behavior traces, placement constraints and observation clips.

### Prompt 5: an optional naturalist notebook

> Add optional player observation to the existing first-person explorer. A binocular/camera view may record an observation with location, simulation time and the system's actual confidence. Separate a visible organism category from an exact species identification when the model or evidence does not support it. Use progressive disclosure for scientific notes and retain source links. The player should be able to explore without opening the notebook. Do not add experience points, collection pressure, mandatory checklists or rewards for approaching wildlife. Store notes locally with a versioned schema and include keyboard, controller and large-text support.

### Prompt 6: non-destructive ecological experiments

> Add a clearly labeled study mode, separate from the ordinary walk. Let the player compare scenarios for air temperature, shade, upstream discharge or thermal source strength. Present units, initial conditions, time scale and uncertainty. The same parameter authority must drive water, steam, insects and fish responses. Keep geography fixed. Provide reset and side-by-side replay. Never present the illustrative model as a forecast of Yellowstone or a visitor safety instrument. Include counterexamples showing why a single variable does not determine a whole habitat.

### Prompt 7: weather, snow and seasons

> Add physically coherent seasonal appearance without relocating authored objects. Implement a weather-state authority with units and explicit time scales. Accumulate/melt snow using an energy or stated degree-day approximation, modify it with canopy/aspect/wind and thermal eligibility, and connect soil moisture to vegetation/insect state. Use artist-authored seasonal plant forms. Ground wetness, precipitation audio, steam visibility and cloud lighting must share this authority. Record which parameters are derived from Yellowstone observations and which are illustrative. Verify continuity across tiles and after save/reload.

### Prompt 8: extend to Fairy Falls

> Extend the existing square along the true Fairy Falls route, keeping every established coordinate and distance. Retrieve compatible DEM, orthophoto, stream and trail data with provenance. Add the falls at their measured location, a proper cliff mesh, wetted rock, stream junction and spray/audio region. Keep the original terrain edge samples unchanged; document any vertical-datum reconciliation. Author the joining corridor in `handcrafted_details.tscn` or new persistent detail scenes. Deliver a border continuity report and an uninterrupted first-person route review from the original overlook branch to the falls.

### Prompt 9: whole-park tile architecture

> Generalize the current local world into a versioned tile catalogue while preserving this scene as the first authored region. Separate geographic coordinates, runtime-relative coordinates and simulation IDs. Implement asynchronous loading, physics-safe handoffs, far terrain, asset residency budgets and persistent ecology. Replace the current central trunk-collision subset with nearby collision streaming from the same fixed transforms, and add reviewed rock/log collision so the visual and physical worlds agree outside the initial walking region. Use shared transport/water graph ports and border samples. Add origin rebasing only after a precision test demonstrates the need. Verify camera, physics, particles, foliage wind, positional audio and map markers across repeated boundary/origin crossings. Do not compress connecting roads.

### Prompt 10: measured rendering optimization

> Profile the exact project on a specified desktop GPU and CPU. Record frame-time percentiles, resolution, renderer, draw calls, triangles, alpha overdraw, memory and shader compilation stutters at the four starting places and during a continuous walk. Optimize spatial bins and LODs while preserving the landscape composition and habitat constraints. Produce Compatibility and Forward+ profiles with explicit differences. Replace broad safety margins with measured budgets. Do not report an assumed 60 fps; attach captured benchmark evidence and list the hardware.

### Prompt 11: add gentle physical interactions

> Add only interactions that support observing this landscape: camera placement, optional binoculars, sitting at an authored viewpoint and inspecting a sourced interpretive panel. Choose explicit, accessible inputs and allow the user to dismiss every overlay. Keep physical interactions separate from species/thermal simulation. Do not implement unrestricted collection, vegetation damage, feeding, chasing or invented ranger tasks as default behavior. Preserve free exploration, all geographic distances and the ability to load the original no-interaction scene.

### Prompt 12: model a distinct thermal basin

> Build the next Yellowstone basin as its own georeferenced authored region. Research its actual fluid chemistry, feature types, substrate, drainage, trail layout and local biological evidence. Select suitable mineral and water representations from that research rather than copying Grand Prismatic's color/rim model. For Mammoth, use the limestone/calcium-carbonate/travertine context and terrace geometry; for a geyser basin, treat constricted plumbing and eruption behavior as distinct from an open hot spring. Keep hypotheses, calibrated observations and illustrative controls separate. Deliver source data, model equations, stable scene IDs, assets/licenses and a first-person visual review.

## 10. The durable project contract

Preserve source provenance, exact scale and stable scene identifiers. Never overwrite hand-authored details during an automatic bake. Make every newly introduced species carry evidence and habitat eligibility. Keep a shared environmental state. State when an asset is an approximation. Separate plans from implemented behavior and implemented behavior from measured scientific reality.

The next useful milestone is a fully reviewed, detailed walk through the existing basin, with improved near-ground art and convincing animal models. After that, adjacent geographic tiles can expand a foundation whose scale, joins, assets and behavior are already understood.

## Sources used in this specification

### Geography and ecology

- **G1** — NPS, [Grand Prismatic Overlook Trail](https://www.nps.gov/thingstodo/yell-trail-grand-prismatic-overlook.htm). Route length/climb and location context.
- **G2** — NPS, [Midway Geyser Basin Trailhead](https://www.nps.gov/places/000/midway-geyser-basin-trailhead.htm) and [Excelsior Geyser Crater](https://www.nps.gov/places/000/excelsior-geyser-crater.htm). Thermal dimensions and descriptive discharge.
- **G3** — USGS, [Map of Yellowstone's Thermal Areas, updated 2023-12-31](https://www.usgs.gov/data/map-yellowstones-thermal-areas-updated-2023-12-31). Thermal-area definitions and dataset scope.
- **G4** — NPS, [Hydrothermal Features](https://www.nps.gov/yell/learn/nature/hydrothermal-features.htm). Feature types and mineral-system distinctions.
- **G5** — NPS, [Influence of Geology](https://www.nps.gov/yell/learn/nature/ecosystemgeology.htm). Geological basis of contrasting vegetation patterns.
- Complete geographic source URLs, imagery license, acquisition times and transformation details: `geography-research.md` and `references/` metadata.
- Detailed species evidence, scientific papers, interaction models and uncertainties: `ecology-research.md` and `data/species_catalogue.json`.

### Engine and assets

- **T1** — Godot, [Large world coordinates](https://docs.godotengine.org/en/4.5/tutorials/physics/large_world_coordinates.html).
- **T2** — Godot, [HeightMapShape3D](https://docs.godotengine.org/en/4.5/classes/class_heightmapshape3d.html).
- **T3** — Godot, [Optimization using MultiMeshes](https://docs.godotengine.org/en/4.5/tutorials/performance/using_multimesh.html).
- **T4** — Godot, [Visibility ranges](https://docs.godotengine.org/en/4.5/tutorials/3d/visibility_ranges.html).
- **T5** — Godot, [Using CharacterBody2D/3D](https://docs.godotengine.org/en/4.5/tutorials/physics/using_character_body_2d.html), [Spatial shaders](https://docs.godotengine.org/en/4.5/tutorials/shaders/shader_reference/spatial_shader.html), and [Environment](https://docs.godotengine.org/en/4.5/classes/class_environment.html).
- **A1** — Poly Haven, [Asset license](https://polyhaven.com/license), [Pine Tree 01](https://polyhaven.com/a/pine_tree_01), [Grass Medium 01](https://polyhaven.com/a/grass_medium_01), [Forest Ground 04](https://polyhaven.com/a/forest_ground_04), [Pine Bark](https://polyhaven.com/a/pine_bark), [Rock Boulder Dry](https://polyhaven.com/a/rock_boulder_dry).
- **A2** — NPS, [Yellowstone Sound Library](https://www.nps.gov/yell/learn/photosmultimedia/soundlibrary.htm).

Sources accessed during the implementation on 7 October 2026 UTC. URLs and factual references are supplied for further review; they do not imply endorsement of this project.
