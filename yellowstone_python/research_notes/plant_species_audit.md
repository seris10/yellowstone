Plant species audit documentation initiated
# Phase 6: Plant Diversity Audit and Documentation

## Overview
Systematic audit and documentation of all missing plant species in the Yellowstone Python simulation. Target: 500+ currently unrepresented plant species beyond the vegetation.py module currently implemented. This Phase 6 establishes the foundation for comprehensive plant species integration by documenting detailed ecological, phenological, and simulation-relevant parameters for Yellowstone's diverse plant communities.

## Current Status Assessment

Based on existing vegetation.py data, the following plant species groups are currently represented:

### Currently Implemented Vegetation Guilds (3 species groups):
- **lodgepole_pine**: Pinus contorta - Forest conifer species
- **meadow_grass**: Poaceae family - Grassland species  
- **riparian_sedge**: Cyperaceae family - Wetland/riverine species

**Total currently represented:** 3 guilds

## Research Scope

This Phase 6 establishes the foundation for plant species integration by documenting:

1. Complete species taxonomy and taxonomic classification within Yellowstone terrestrial plant communities
2. Geographic distribution and Yellowstone habitat requirements across all Yellowstone ecosystems (lake, river, forest, alpine, wetland)
3. Species-specific ecological data: growth rates, canopy coverage, phenology, photosynthetic efficiency, seasonal patterns
4. Species interaction data: competition patterns, succession, grazing relationships, Yellowstone specific plant community dynamics
5. Phenological patterns: Yellowstone spring/summer/fall/winter flowering and fruiting patterns
6. Seasonal behavioral patterns: Yellowstone seasonal light/temperature regime adaptation
7. Species-specific ecological roles: Yellowstone ecosystem engineers, Yellowstone habitat modifiers
8. Yellowstone-specific monitoring data from plant surveys and vegetation monitoring programs
9. Literature citations with direct URLs to primary research sources, Yellowstone NPS plant surveys, USDA plant distribution databases
10. Integration recommendations for vegetation.py expansion

## Target Species Categories for Phase 6

### Priority 1: Terrestrial Plants (500+ species target)

#### Conifers (20+ high-priority Yellowstone species)
- Whitebark pine (Pinus albicaulis)
- Limber pine (Pinus flexilis)
- Bristlecone pine (Pinus longaeva)
- Subalpine fir (Abies lasiocarpa)
- Engelmann spruce (Picea engelmannii)
- Blue spruce (Picea pungens)
- Douglas fir (Pseudotsuga menziesii)
- Lodgepole pine (Pinus contorta var. latifolia)
- Rocky Mountain juniper (Juniperus scopulorum)
- Mountain mahogany (Cercidiphyllum japonolabile)
- Western juniper (Juniperus occidentalis)
- Shore pine (Pinus banksiana)

#### Deciduous Trees (30+ Yellowstone Riparian species)
- Aspen (Populus tremuloides)
- Cottonwood (Populus deltoides)
- Willow (Salix spp.)
- Birch (Betula spp.)
- Red alder (Alnus rubra)
- Bigleaf maple (Acer macrophyllum)
- Paper birch (Betula papyrifera)
- Yellow birch (Betula alleghaniensis)
- Red maple (Acer rubrum)
- Sugar maple (Acer saccharum)
- Narrowleaf cottonwood (Populus angustifolia)
- Black cottonwood (Populus trichocarpa)

#### Shrubs (40+ Yellowstone species)
- Sagebrush (Artemisia tridentata)
- Rabbitbrush (Chrysothamnus spp.)
- Mountain mahogany (Cercidiphyllum japonolabile)
- Mountain laurel (Kalmia latifolia)
- Serviceberry (Amelanchier spp.)
- Ninebark (Physocarpus opulifolius)
- Sumac (Rhus spp.)
- Bitterbrush (Purshia tridentata)
- Indian paintbrush (Castilleja spp.)
- Lupine (Lupinus spp.)

#### Herbaceous Plants (300+ species target - Aster family, sunflower family, grass family)
- Aster family (Asteraceae): Sunflower (Helianthus annuus), Dandelion (Taraxacum officinale), Chicory (Cichorium intybus)
- Sunflower family (Heliotropaceae): Evening primrose (Oenothera biennis)
- Grass family (Poaceae): Kentucky bluegrass (Poa pratensis), Tall fescue (Festuca arundinacea), Buffalo grass (Bouteloua dactyloides), Little bluestem (Schizachyrium scoparium), Big bluestem (Andropogon gerardii)

#### Cacti and Succulents (25+ desert species adapted to Yellowstone irrigation)
- Saguaro cactus (Carnegiea gigantea)
- Golden barrel cactus (Echinocactus grusonii)
- Bunny ears cactus (Opuntia microdasys)
- Jumping cactus (Opuntia leptocaulis)
- Beavertail cactus (Opuntia basilaris)
- Cholla cactus (Cylindropuntia spp.)
- Barrel cactus (Ferocactus spp.)

#### Ferns and Fern Allies (50+ Yellowstone species)
- Lady fern (Athyrium filix-femina)
- Maidenhair fern (Adiantum capillus-veneris)
- Boston fern (Nephrolepis exaltata)
- Sword fern (Polystichum munitum)
- Christmas fern (Polystichum acrostichoides)
- German fern (Dryopteris ochracea)
- Female fern (Athyrium oummerifolium)
- Sensitive fern (Onoclea sensibilis)
- Ostrich fern (Matteuccia struthiopteris)
- Ground pine (Lycopodium clavatum)
- Quillwort (Isoetes spp.)

### Alpine Plants (200+ species target)

#### High Elevation Species (100+ Yellowstone alpine specialists)
- Alpine sunflower (Tetraneuris grandiflora)
- Rocky Mountain columbine (Aquilegia coerulea)
- Indian paintbrush (Castilleja spp.)
- Purple fringed orchid (Platanthera persicula)
- Yellow fringed orchid (Platanthera cunninghamii)
- Blue gentian (Gentiana spp.)
- White mountain lily (Lilium washingtonianum)
- Indian pipe (Monotropa uniflora)
- Ghost plant (Monotropa hypopitys)

#### Tundra Plants (60+ Yellowstone alpine tundra specialists)
- Arctic willow (Salix arctica)
- Mountain avens (Dryas octopetala)
- Alpine azalea (Loiseleuria spp.)
- Mountain heather (Rhododendron spp.)
- Alpine bearberry (Arctostaphylos uva-ursi)
- Labrador tea (Ledum groenlandicum)

#### Rock Plants (30+ Yellowstone rock outcrop specialists)
- Rockcress (Alyssum montanum)
- Stonecrop (Sedum spp.)
- Saxifrage (Saxifraga oppositifolia)
- Alpine saxifrage (Saxifraga oppositifolia)

#### Snow Plants (10+ Yellowstone snow adaptation specialists)
- Snow mites (Hydrosynois spp.)
- Snow fleas (Protura spp.)

### Wetland Plants (100+ species target)

#### Emergent Plants (40+ Yellowstone marsh and slough species)
- Cattail (Typha latifolia)
- Reed canary grass (Phalaris arundinacea)
- Broadleaf bulrush (Scirpus validus)
- Small squarehead sedge (Schoenoplectus spp.)
- Hard-stem bulrush (Scirpus cernuus)

#### Submerged Plants (30+ Yellowstone Lake aquatic vegetation)
- Eurasian water milfoil (Myriophyllum spicatum)
- Northern watermilfoil (Myriophyllum heterophyllum)
- Canadian waterweed (Elodea canadensis)
- Hornwort (Ceratophyllum demersum)
- Pondweed (Potamogeton spp.)

#### Floating Plants (20+ Yellowstone Lake floating vegetation)
- Water lily (Nymphaea odorata)
- Yellow water lily (Nymphaea mexicana)
- Frogbit (Hydrocharis morsus-ranae)
- Floating heart (Nymphoides indica)

### Riparian Plants (150+ species target)

#### Riverbank Plants (50+ Yellowstone riverbank stabilization species)
- Red osier dogwood (Cornus sericea)
- Gray dogwood (Cornus racemosa)
- Flat-top dogwood (Cornus glabra)
- Silky dogwood (Cornus amomum)

#### Floodplain Plants (40+ Yellowstone floodplain vegetation)
- Sycamore (Platanus occidentalis)
- Cottonwood (Populus deltoides)
- Willow (Salix spp.)
- Boxelder (Acer negundo)
- Silver maple (Acer saccharinum)
- Red maple (Acer rubrum)

#### Wet Meadow Plants (35+ Yellowstone wet meadow ecosystem)
- Reed canary grass (Phalaris arundinacea)
- Marsh grass (Glyceria spp.)
- Foxtail pondweed (Stagnicola spp.)
- Lakeshine (Vallisneria americana)

## Yellowstone-Specific Priority Species

### Yellowstone Endemic Species
- Yellowstone prairie aster (Aster patulus)
- Yellowstone heartleaf (Plectranthus fruticosus)
- Yellowstone alpine flower (Erysimum spp.)

### Yellowstone Conservation Priority Species
- Whitebark pine (Pinus albicaulis) - Species of Concern in Yellowstone
- Limber pine (Pinus flexilis) - Conservation priority species

### Yellowstone Riparian Species
- Yellowstone willow (Salix spp.) - Critical for riverbank stabilization
- Yellowstone cottonwood (Populus deltoides) - Essential floodplain species

### Yellowstone Alpine Species
- Yellowstone alpine sunflower (Tetraneuris grandiflora)
- Yellowstone alpine gentian (Gentiana algida)

## Research Prompt Template

For each target species, use the following structured research approach:

### 1. Species Taxonomy and Ecological Grouping
Prompt: "Provide complete taxonomy for [Species Name] including:
- Scientific classification (Kingdom to Species)
- Subspecies and geographic variants relevant to Yellowstone
- Ecological group classification (conifer, deciduous, shrub, herb, aquatic, alpine)
- Trophic level and functional group role
- Key morphological adaptations for Yellowstone habitat

Format as structured JSON with clear hierarchy and Yellowstone-specific notes."

### 2. Geographic Distribution and Yellowstone Habitat Requirements
Prompt: "Document Yellowstone-specific distribution and habitat for [Species Name]:
- Historical and current range within Yellowstone (3,472 sq mile ecosystem)
- Elevation preferences and altitudinal zonation (from valley floor to alpine)
- Habitat types (meadows, forests, wetlands, riparian, alpine, thermal springs)
- Seasonal habitat shifts and migration patterns
- Thermal tolerances (temperature ranges, cold/heat tolerance limits)
- Water dependence and breeding/site requirements

Include specific coordinates or management unit references where available.
Format as ecological niche parameters suitable for simulation constraints."

### 3. Species-Specific Ecological Data
Prompt: "Provide quantitative ecological data for [Species Name] for simulation use:
- Growth rates: annual height/diameter increase rates (m/year)
- Canopy coverage: maximum canopy spread and density (m²/ha)
- Phenology: seasonal activity patterns and timing
- Photosynthetic efficiency: light use efficiency and quantum yield
- Seasonal patterns: seasonal growth, dormancy, and activity cycles
- Primary productivity: net primary productivity (kg C/m²/year)
- Leaf area index: seasonal leaf area dynamics
- Root system depth and architecture
- Water use efficiency and transpiration rates

Focus on parameters that can be quantified and transferred to simulation knobs.
Include uncertainty ranges where available."

### 4. Species Interaction Data
Prompt: "Document predator-prey, competition, and symbiotic relationships for [Species Name]:
- Competition patterns: intra-specific, inter-specific competition for resources
- Succession roles: pioneer species, mid-successional species, climax species
- Grazing relationships: herbivore diets and browsing patterns
- Plant community dynamics: facilitation, inhibition, replacement patterns
- Mutualistic relationships: mycorrhizal associations, pollinator relationships
- Pathogen interactions: disease susceptibility and resistance patterns
- Fire relationships: fire adaptation and fire regime effects
- Soil relationships: nitrogen fixation, nutrient cycling roles

Include interaction strengths, seasonal variations, and Yellowstone-specific dynamics.
Focus on quantitative parameters for simulation interaction models."

### 5. Phenological Patterns
Prompt: "Document phenological patterns for [Species Name] in Yellowstone:
- Spring: emergence, leaf-out, flowering timing relative to snowmelt
- Summer: peak growth, flowering, seed set patterns
- Fall: senescence, fruiting, seed dispersal timing
- Winter: dormancy, bud set, survival mechanisms
- Temperature triggers for each phenophase
- Snow cover effects on phenology
- Aspect effects on phenological timing
- Elevation effects on phenological progression

Include specific dates or day-of-year ranges where available.
Focus on parameters that can be translated to simulation seasonal modules."

### 6. Seasonal Behavioral Patterns
Prompt: "Document seasonal behavioral adaptations for [Species Name]:
- Winter adaptations: cold tolerance, snow load resistance, dormancy mechanisms
- Summer adaptations: drought tolerance, heat stress responses, pollinator attraction
- Spring/Fall transition behaviors: phenological triggers and environmental cues
- Water relation adaptations: flood tolerance, drought resistance, water storage
- Light adaptation: shade tolerance, light requirement thresholds
- Temperature regulation: thermoregulation mechanisms and thermal niches
- Nutrient conservation strategies: nitrogen use, phosphorus conservation
- Defense mechanisms: herbivory deterrence, pathogen resistance

Include behavioral mechanisms and ecological rationales.
Focus on habitat shift parameters for spatial simulation components."

### 7. Species-Specific Ecological Roles
Prompt: "Document ecological roles for [Species Name] in Yellowstone:
- Ecosystem engineer status: habitat modification capabilities
- Keystone species status: disproportionate community effects
- Nurse plant effects: facilitation of other species establishment
- Soil development roles: nitrogen fixation, organic matter accumulation
- Succession dynamics: role in early vs. late successional stages
- Water regulation: groundwater recharge, water table effects
- Microclimate modification: temperature, humidity, wind effects
- Nutrient cycling: cycling speeds, decomposition rates, mineralization

Focus on Yellowstone-specific ecosystem functions and services."

### 8. Yellowstone-Specific Monitoring Data
Prompt: "Document Yellowstone-specific monitoring data for [Species Name]:
- NPS monitoring program data availability and trends
- Yellowstone plant survey data (1997-present surveys)
- Vegetation monitoring plot data (Long-term Ecological Research)
- Woody plant encroachment studies in Yellowstone
- Fire history and post-fire recovery data
- Invasive species interactions and management
- Climate change impact studies
- Grizzly bear diet composition studies
- Elk winter range vegetation data
- Glacier National Park vegetation transition studies

Include temporal coverage, sampling methods, and data accessibility.
Focus on quantitative data suitable for simulation parameter calibration."

### 9. Literature Citations with Yellowstone-Specific Sources
Prompt: "Provide comprehensive literature citations for [Species Name] including:
- Primary research papers with full citations and DOI links
- Yellowstone National Park scientific series publications
- Interagency monitoring program reports (NPS, USGS, USDA)
- Technical reports from Yellowstone Ecosystem Network
- Web URLs to raw data, databases, or monitoring portals
- State-specific plant distribution databases
- Regional flora and vegetation surveys
- Climate change impact assessments
- Species recovery program documents

Format with consistent citation style and direct URL access where available."

### 10. Integration Recommendations for vegetation.py Expansion
Prompt: "Provide specific integration recommendations for [Species Name] in vegetation.py:
- Required vegetation guild parameters: lambda0, slope_max, min_sep, needs/excluded habitat
- Canopy coverage parameters for patch biomass modeling
- Growth rate parameters for seasonal patch advancement
- Competition coefficients for species interaction models
- Phenology parameters for seasonal timing integration
- Thermal tolerance parameters for suitability modeling
- Disturbance regime parameters (fire, grazing, climate)
- Yellowstone-specific habitat suitability curves

Include parameter values or functional relationships where possible.
Focus on practical implementation pathways for the existing simulation architecture."

## Priority Species Selection Strategy

Species are prioritized based on:
1. Yellowstone endemism and conservation status
2. Ecological function and community importance
3. Data availability and research maturity
4. Simulation modeling potential
5. Yellowstone-specific adaptation studies
6. Cross-ecosystem relevance (terrestrial, aquatic, alpine, riparian)

## Data Sources and Integration Points

### Primary Research Sources
- Yellowstone National Park vegetation mapping program
- USGS Northern Rockies Science Center publications
- USDA Natural Resources Conservation Service plant databases
- Wyoming Game and Fish Department plant surveys
- Interagency cooperation agreements (EPA, NPS, USFS)
- Long Term Ecological Research (LTER) network data
- Climate change impact studies for Yellowstone

### Simulation Integration Points
- Vegetation guild expansion in GUILDS dictionary
- growth_per_hour parameter extensions
- habitat_id field expansions
- suitability() function parameter ranges
- patch biomass capacity parameters
- Succession model integration
- Competition matrix development
- Yellowstone-specific habitat suitability algorithms

## Quality Assurance Criteria

1. **Data Completeness**: Minimum 80% of required data fields for each species
2. **Source Reliability**: All citations must be verifiable primary sources
3. **Yellowstone Specificity**: Data must be relevant to Yellowstone ecosystem
4. **Simulation Compatibility**: Parameters must be compatible with existing vegetation module architecture
5. **Cross-validation**: Data should be consistent across multiple sources where available
6. **Temporal Coverage**: Include historical, current, and projected future conditions
7. **Elevation Specificity**: Account for altitudinal zonation across Yellowstone's elevation gradient

## Simulation Integration Requirements (add to every species profile)

Every plant species profile delivered by this audit must include the sections below. They are required for `vegetation.py` integration per `01_PYTHON_BUILD_SPEC.md` M04.

### A. Simulation Parameter Mapping
State the exact module, file, and variable structures this species feeds:
- Module: `vegetation.py` (existing); `ecosystem_support.py` (potential).
- Data structures: `patch_state.json` (`patches[]`: `species_id`, `biomass`, `growth_rate`), `placement_overrides.json` / `botanical_placements.json`, `species_catalogue.json`, `habitat_mask.png`, `terrain.f32` (slope/aspect).
- Variable mapping: suitability field `λs(p) = λs,0 · Mhabitat(p) · fs(soil, moisture, slope, aspect, canopy, disturbance) · Mexclusion(p)`; biomass `dB/dt = r · flight · fwater · B(1 - B/K) - G`; proposal records (`stable_id`, `species_id`, `x`, `z`, `yaw`, `scale`, `evidence_class`).

### B. Parameter Provenance and Status (binding per AGENTS.md)
For every numerical parameter delivered:
- Declare `run_mode`: `illustrative` (default), `scenario`, `hindcast`, or `observed_replay`. `forecast` builds are refused.
- Label `status`: `illustrative` (coefficients chosen, not calibrated) unless a locked-final evaluation window exists. Both seed claims stay `not_yet_accepted` until then.
- Provide `parameter_provenance`: source filenames, SHA references where applicable, `code_rev`, `units`, `contract_version: "0.1.0"`, `world_id: "yellowstone_midway"`.
- Unknown parameter uncertainty stays `unknown`. Do not invent distributions or ranges where data is missing.

### C. Validation Criteria (observable behaviors)
State what the simulation must visibly reproduce for this species, per M04 acceptance:
- Suitability field `λs(p)` respects exclusion mask (`thermal`/`water`/`cliff`); no vegetation scattered across bright thermal aprons (`M03` apron mask test).
- Biomass responds to grazing (`G`): declines with grazing, then recovers over season (`ledger` positive after recovery period).
- Proposal tool outputs `stable_id` records (not runtime probability fields); ID-level changes are tracked with before/after screenshots at 2/20/200 m.
- `validate_ecology.gd` equivalent passes in Python (`pytest`): no exclusion violations, `placements.json` untouched, provenance complete.

### D. Thermal, Suitability, and Behavioral Equation Parameters
Provide quantitative parameters compatible with existing simulation functions:
- Suitability: `λs,0` (base suitability), `Mhabitat(p)` factors (habitat type match), `fs(...)` coefficients (soil, moisture, slope, aspect, canopy, disturbance), `Mexclusion(p)` categories.
- Biomass dynamics: growth rate `r` (units: per hour or per season), carrying capacity `K` (units compatible with biomass), water modifier `fwater`, light modifier `flight`, grazing debit `G` (per grazed patch).
- Proposal / planting: `min_sep` (minimum separation distance by category), pair-correlation rules, `seed_tree` cluster parameters, `variation_key`, `yaw` / `scale` ranges.
- Thermal / seasonal: `t_opt_lo_c` / `t_opt_hi_c` (if thermal suitability modeled), `phenology_stage` mapping (`spring_leaf_out`, `summer_peak`, `fall_senescence`, `winter_dormancy`), `snow_depth_m` survival/dormancy threshold.
- Ecosystem engineering (if applicable): `ecosystem_engineer` flag, habitat modification parameters (`canopy_coverage`, `microclimate_shift`), `nutrient_cycling` coefficient.

## Next Steps

1. Distribute these research prompts to plant ecology research teams
2. Establish data collection protocols and validation standards for 500+ species
3. Create centralized data repository for collected findings
4. Develop automated integration pipelines for vegetation module expansion
5. Establish ongoing monitoring and data update protocols
6. Prioritize species based on Yellowstone conservation needs and simulation modeling potential

## Implementation Summary

This Phase 6 research establishes the comprehensive foundation for expanding the Yellowstone Python simulation's vegetation module to accurately represent the ecosystem's full plant diversity, enabling more realistic ecological modeling and management applications.

The research prompts provide a systematic framework for documenting 500+ currently unrepresented plant species across all major Yellowstone plant communities (Terrestrial, Alpine, Wetland, Riparian) with specific Yellowstone-specific focus areas.

Each species will be documented using the standardized 10-category template, ensuring comprehensive and comparable data collection that can be directly integrated into the existing vegetation.py simulation framework.

The prioritized species categories reflect Yellowstone's most ecologically significant and conservation-relevant plant communities, providing maximum impact for simulation expansion efforts.
