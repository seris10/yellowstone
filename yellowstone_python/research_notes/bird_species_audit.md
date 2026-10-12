# Phase 2: Avian Diversity Audit and Documentation

## Overview
Systematic audit and documentation of all missing bird species in the Yellowstone Python simulation. Target: 100+ currently unrepresented species across all bird functional groups.

## Research Scope
This Phase 2 establishes the foundation for avian species integration by documenting:

1. Complete species taxonomy and taxonomic classification
2. Geographic distribution and Yellowstone habitat requirements
3. Species-specific ecological data: population estimates, diet composition, foraging behavior, thermal tolerances
4. Species interaction data: predator-prey relationships, competition, diet overlaps
5. Phenological patterns: breeding seasons, migration timing, nesting behavior
6. Seasonal behavioral adaptations and habitat shifts within Yellowstone's temporal ecology
7. Species-specific thermal tolerances for simulation parameters
8. Literature citations with direct URLs to primary research sources
9. Yellowstone monitoring program data where available
10. Integration recommendations for existing birds module integration

## Current Status Assessment

Based on existing traits_birds.json data, the following bird species are currently represented:
- Bald eagle (Haliaeetus leucocephalus)
- Osprey (Pandion haliaetus)
- Golden eagle (Aquila chrysaetos)
- Great gray owl (Strix nebulosa)
- Great horned owl (Bubo virginianus)
- Boreal owl (Aegolius funereus)
- Northern saw-whet owl (Aegolius acadicus)
- American kestrel (Falco sparverius)
- Peregrine falcon (Falco peregrinus)
- Sandhill crane (Antigone canadensis)
- Great blue heron (Ardea herodias)
- American white pelican (Pelecanus erythrorhynchos)
- Harlequin duck (Histrionicus histrionicus)
- Barrow's goldeneye (Bucephala islandica)
- Common merganser (Mergus merganser)
- Mallard (Anas platyrhynchos)
- Belted kingfisher (Megaceryle alcyon)
- Common nighthawk (Chordeiles minor)
- Broad-tailed hummingbird (Selasphorus platycercus)
- Calliope hummingbird (Selasphorus calliope)
- Williamson's sapsucker (Sphyrapicus thyroideus)
- Hairy woodpecker (Dryobates villosus)
- Downy woodpecker (Dryobates pubescens)
- Northern flicker (Colaptes auratus cafer)
- Pileated woodpecker (Dryocopus pileatus)
- Olive-sided flycatcher (Contopus cooperi)
- Western wood-pewee (Contopus sordidulus)
- Dusky flycatcher (Empidonax oberholseri)
- Hammond's flycatcher (Empidonax hammondii)
- Canada jay (Perisoreus canadensis)
- Steller's jay (Cyanocitta stelleri)
- Clark's nutcracker (Nucifraga columbiana)
- Mountain bluebird (Sialia currucoides)
- Townsend's solitaire (Myadestes townsendi)
- American robin (Turdus migratorius)
- Varied thrush (Ixoreus naevius)
- Hermit thrush (Catharus guttatus)
- Swainson's thrush (Catharus ustulatus)
- Yellow warbler (Setophaga petechia)
- Yellow-rumped warbler (Audubon's) (Setophaga coronata auduboni)
- MacGillivray's warbler (Geothlypis tolmiei)
- Wilson's warbler (Cardellina pusilla)
- Western tanager (Piranga ludoviciana)
- Green-tailed towhee (Pipilo chlorurus)
- Chipping sparrow (Spizella passerina)
- Song sparrow (Melospiza melodia)
- White-crowned sparrow (Zonotrichia leucophrys)
- Dark-eyed junco (Junco hyemalis)
- Red-winged blackbird (Agelaius phoeniceus)

Total currently represented: 43 species

## Target Species Categories for Phase 2

### Priority 1: Waterfowl (multiple duck, goose, teal species)
- American black duck (Melanitta nigra)
- Blue-winged teal (Spatula discors)
- Green-winged teal (Spatula cisca)
- Wood duck (Aix sponsa)
- Common goldeneye (Bucephala clangula)
- Lesser scaup (Aythya affinis)
- Greater scaup (Aythya marila)
- Ring-necked duck (Aythya collaris)
- Canvasback (Aythya valisineria)
- Redhead (Aythya americana)
- Ruddy duck (Oxyura jamaicrudis)
- Bufflehead (Bucephala albeola)

### Priority 2: Raptors (additional hawk species, eagle species)
- Cooper's hawk (Accipiter cooperii)
- Sharp-shinned hawk (Accipiter striatus)
- Red-tailed hawk (Buteo jamaicensis)
- Rough-legged hawk (Buteo lagopus)
- Ferruginous hawk (Buteo regalis)
- Northern harrier (Circus hudsonius)
- Sharp-tailed snake eagle (Circus teBay)
- American barn owl (Tyto alba)
- Short-eared owl (Asio flammeus)
- Long-eared owl (Asio otus)
- Snowy owl (Bubo scandiacus)

### Priority 3: Songbirds (additional warblers, finches, sparrows)
- Black-throated blue warbler (Setophaga caerulescens)
- Black-throated green warbler (Setophaga virens)
- Ovenbird (Seiurus aurocapilla)
- Worm-eating warbler (Helmitheros vermivorum)
- Kentucky warbler (Geothlypis formosa)
- Maryland warbler (Geothlypis polyglotta)
- Mourning warbler (Geothlypis philadelphia)
- Common yellowthroat (Geothlypis trichas)
- Yellow-breasted chat (Icteria virens)
- House finch (Haemorhous mexicanus)
- Purple finch (Haemorhous purpureus)
- Cassin's finch (Haemorhous cassinii)
- Evening grosbeak (Cymbalaria spodocephala)
- Pine grosbeak (Pinicola enucleator)
- Black-capped chickadee (Poecile atricapillus)
- Mountain chickadee (Poecile gambeli)
- Chestnut-backed chickadee (Poecile rufescens)
- Red-breasted nuthatch (Sitta canadensis)
- White-breasted nuthatch (Sitta carolinensis)

### Priority 4: Shorebirds and waterbirds
- American avocet (Recurvirostra americana)
- Black-necked grebe (Gorgany nigricollis)
- Eared grebe (Podiceps nigricollis)
- Horned grebe (Podiceps auritus)
- Red-necked grebe (Podiceps grisegena)
- Common loon (Gavia immer)
- Yellow-billed loon (Gavia adamsii)
- Surf scoter (Melanitta perspicillata)
- White-winged scoter (Melanitta fusca)
- Long-tailed duck (Clangula hyemalis)
- Bufflehead (Bucephala albeola)
- Hooded merganser (Lophodytes cucullatus)
- Common goldeneye (Bucephala clangula)

### Priority 5: Woodpeckers and related species
- Red-headed woodpecker (Melanerpes erythrocephalus)
- Red-bellied woodpecker (Melanerpes carolinus)
- Yellow-bellied woodpecker (Melanerpes flavifrons)
- Gila woodpecker (Melanerpes uropygialis)
- Acorn woodpecker (Melanerpes formicivorus)
- Gray-headed woodpecker (Picoides cryptocephalus)
- American three-toed woodpecker (Picoides dorsalis)
- Northern flicker (Colaptes auratus)

### Priority 6: Owls (additional species)
- Barred owl (Strix varia)
- Eastern screech owl (Megascops asio)
- Western screech owl (Megascops westensis)
- Great horned owl (Bubo virginianus)
- Eastern horned owl (Bubo virginianus cynomorum)
- Snowy owl (Bubo scandiacus)
- Northern pygmy owl (Glaucidium gnoma)
- Eastern pygmy owl (Glaucidium passerinum)

### Priority 7: Swifts, swallows, and flying insects
- Chimney swift (Chaetura pelagica)
- Vaux's swift (Chaetura Vauxii)
- White-throated swift (Aeronautes saxatalis)
- Northern rough-winged swallow (Stelgidopteryx serripennis)
- Bank swallow (Riparia riparia)
- Barn swallow (Hirundo rustica)
- Cliff swallow (Petrochelidon pyrrhonota)
- Purple martin (Progne subis)

### Priority 8: Seabirds (coastal Yellowstone Lake species)
- Common loon (Gavia immer)
- Yellow-billed loon (Gavia adamsii)
- White-winged scoter (Melanitta fusca)
- Surf scoter (Melanitta perspicillata)
- Long-tailed duck (Clangula hyemalis)
- Bufflehead (Bucephala albeola)
- Hooded merganser (Lophodytes cucullatus)

## Research Prompt Template

For each target species, use the following structured research approach:

### 1. Species Taxonomy and Ecological Grouping
Prompt: "Provide complete taxonomy for [Species Name] including:
- Scientific classification (Kingdom to Species)
- Subspecies and geographic variants relevant to Yellowstone
- Ecological group classification (waterfowl, raptor, songbird, etc.)
- Trophic level and functional group role
- Key morphological adaptations for Yellowstone habitat

Format as structured JSON with clear hierarchy and Yellowstone-specific notes."

### 2. Geographic Distribution and Habitat Requirements
Prompt: "Document Yellowstone-specific distribution and habitat for [Species Name]:
- Historical and current range within Yellowstone (3,472 sq mile ecosystem)
- Elevation preferences and altitudinal zonation
- Habitat types (meadows, forests, wetlands, riparian, alpine)
- Seasonal habitat shifts and migration patterns
- Thermal tolerances (temperature ranges, cold/heat tolerance limits)
- Water dependence and denning/site requirements

Include specific coordinates or management unit references where available.
Format as ecological niche parameters suitable for simulation constraints."

### 3. Species-Specific Ecological Data
Prompt: "Provide quantitative ecological data for [Species Name] for simulation use:
- Population estimates: historical, current, carrying capacity for Yellowstone
- Diet composition: primary foods, seasonal diet shifts, nutritional requirements
- Seasonal behaviors: breeding, hibernation, migration timing
- Thermal tolerances: lower/upper critical temperatures, thermoneutral zone
- Habitat preferences: structural complexity, cover requirements, territory size
- Activity patterns: diurnal/nocturnal, home range size, movement rates

Focus on parameters that can be quantified and transferred to simulation knobs.
Include uncertainty ranges where available."

### 4. Species Interaction Data
Prompt: "Document predator-prey, competition, and symbiotic relationships for [Species Name]:
- Predator relationships: natural predators, predation pressure, predator-prey dynamics
- Competition patterns: intra-specific, inter-specific competition for resources
- Disease vectors and pathogens known in Yellowstone region
- Symbiotic relationships: mutualisms, commensalisms
- Human-wildlife conflict patterns and management interventions
- Impact of wolves on other carnivores and herbivores (trophic cascades)

Include interaction strengths, seasonal variations, and Yellowstone-specific dynamics.
Focus on quantitative parameters for simulation interaction models."

### 5. Phenological Patterns and Temporal Dynamics
Prompt: "Document phenological patterns for [Species Name] in Yellowstone:
- Breeding/ reproductive timing: season, duration, environmental triggers
- Migration patterns: timing, routes, destination reasons
- Hibernation patterns: timing, duration, physiological triggers
- Seasonal behavioral shifts: activity patterns, habitat use changes
- Food caching behaviors and timing
- Annual activity budget and temporal allocation

Include specific dates or day-of-year ranges where available.
Focus on parameters that can be translated to simulation seasonal modules."

### 6. Seasonal Behavioral Adaptations and Habitat Shifts
Prompt: "Document seasonal behavioral adaptations for [Species Name]:
- Winter adaptations: insulation, metabolism, food acquisition strategies
- Summer adaptations: thermoregulation, reproductive behaviors
- Spring/Fall transition behaviors and resource use
- Denning/brochue-site selection and characteristics
- Foraging strategies by season and habitat type
- Avoidance behaviors: human proximity, predators, harsh weather

Include behavioral mechanisms and ecological rationales.
Focus on habitat shift parameters for spatial simulation components."

### 7. Species-Specific Thermal Tolerances for Simulation Parameters
Prompt: "Document thermal tolerances for [Species Name] in Yellowstone context:
- Lower critical temperature (LCT) and upper critical temperature (UCT)
- Thermoneutral zone (TNZ) boundaries
- acclimatization capacity and plasticity
- Temperature-mediated effects on reproduction and survival
- Behavioral thermoregulation strategies
- Thermal preferences for foraging and nesting sites

Focus on parameters compatible with existing insect module thermal parameters
and can be integrated into species-specific activity models."

### 8. Literature Citations with Direct URLs to Primary Research Sources
Prompt: "Provide primary research sources with direct URLs for [Species Name]:
- Peer-reviewed scientific studies specific to Yellowstone or similar ecosystems
- Government and agency reports (NPS, US Fish & Wildlife Service, etc.)
- Monitoring program data and annual reports
- Dissertation/thesis research relevant to Yellowstone
- Technical reports and agency publications

For each source, provide:
- Full citation in standardized format
- Direct URL to source
- Specific findings relevant to simulation parameters
- Data quality assessment (peer-reviewed, government data, etc.)

Format as reference list with citation tags for integration into species documentation."

### 9. Yellowstone Monitoring Program Data Where Available
Prompt: "Document Yellowstone monitoring program data for [Species Name]:
- NPS annual surveys and population counts
- Breeding bird survey (BBS) data for Yellowstone region
- Winter bird counts and roost surveys
- Nesting success rates and productivity metrics
- Radio telemetry and tracking data
- Habitat use studies and distribution maps
- Abundance trends and status assessments

Include sampling methods, time periods, and observer biases.
Focus on data sources that can be directly used in simulation validation."

### 10. Integration Recommendations for Existing Birds Module Integration
Prompt: "Recommend integration points for [Species Name] in Yellowstone Python simulation:
- Primary module placement: birds.py, mammals.py, or new module
- Parameter mapping: existing simulation knobs that correspond to species traits
- Interaction integration points: predator-prey, competition, habitat modules
- Seasonal module placement: timing and behavioral pattern integration
- Data structure recommendations: format and location for species-specific data
- Validation requirements: observable behaviors to match simulation outputs

Consider:
- Existing module architecture and data structures
- Integration with current species (e.g., dipper, raven, trout)
- Simulation temporal and spatial scales
- Parameter compatibility with existing models

Provide specific code integration guidance and potential collaboration points with other species modules.
Focus on practical implementation within current simulation constraints."

## Prioritization Framework

### High Priority (Yellowstone Monitoring Programs Established)
1. Bald eagle - keystone predator, extensive monitoring
2. Osprey - fishing specialist, camera trap data
3. Golden eagle - raptor survey data
4. Red-tailed hawk - widespread distribution data
5. Sandhill crane - migration corridor surveys
6. Great blue heron - nesting colony data
7. American white pelican - Lake Yellowstone colony monitoring
8. Common loon - breeding pair surveys
9. Bufflehead - winter roost surveys
10. Hooded merganser - dive specialist data

### Medium Priority (Good Literature Base)
1. Various duck species (blue-winged teal, wood duck, etc.)
2. Additional raptor species (Cooper's hawk, harriers)
3. Additional owl species (barred, screech)
4. Shorebird species (avocets, grebes)
5. Additional woodpecker species
6. Additional songbird species (warblers, finches)

### Lower Priority (Limited Data, Gaps Identified)
1. Seabird species (scoters, loons)
2. Swift and swallow species
3. Additional finch species
4. Additional warbler species

## Data Quality Standards

### Primary Data Sources (Highest Priority)
- Yellowstone National Park Annual Bird Surveys
- US Fish & Wildlife Service Breeding Bird Survey (BBS) data
- NPS Research publications and monitoring reports
- Peer-reviewed studies with Yellowstone focus
- Wyoming Game & Fish Department surveys

### Secondary Data Sources
- Regional avian ecology studies
- Similar high-elevation ecosystem research
- Historical museum records and specimens
- State wildlife agency breeding programs

### Data Quality Assessment Criteria
- Temporal relevance (last 10-15 years preferred)
- Geographic specificity (Yellowstone or similar high-elevation ecosystems)
- Sample size and statistical robustness
- Peer-review status and methodology quality
- Parameter relevance to simulation requirements
- Yellowstone-specific data availability

## Integration Roadmap

### Phase 2 (Current)
- Complete species taxonomy and literature review
- Document ecological requirements and habitat parameters
- Identify data gaps and reliability assessments
- Define integration points within existing birds module
- Develop research prompts for 100+ target species

### Phase 3 (Follow-up)
- Develop simulation parameter mappings
- Create data structure templates
- Establish validation frameworks
- Begin integration into birds.py module
- Implement core species modules

### Phase 4 (Implementation)
- Implement species modules with validated parameters
- Validate against existing observations
- Test integration with current ecosystem dynamics
- Refine parameters based on model performance

## Quality Assurance Standards

### Documentation Requirements
- All sources must include direct URLs
- Citation format consistency across species
- Parameter uncertainty quantification where possible
- Yellowstone-specific ecological context emphasized
- Integration feasibility assessments for each species
- Data quality ratings (high/medium/low confidence)

### Technical Standards
- Parameter units standardized (SI where applicable)
- Numerical values converted to simulation-compatible ranges
- References to specific Yellowstone studies prioritized
- Gaps clearly identified with suggested solutions
- Integration pathways clearly mapped to existing modules
- Compatibility with existing insects_birds.py functions

## Simulation Integration Requirements (add to every species profile)

Every avian species profile delivered by this audit must include the sections below. They are required for `birds.py` / `insects_birds.py` integration per `01_PYTHON_BUILD_SPEC.md` M05.

### A. Simulation Parameter Mapping
State the exact module, file, and variable structures this species feeds:
- Module: `insects_birds.py` (existing); potential `birds.py` (new).
- Data structures: `wildlife[]` (`duration`/`rate`), `patches[].insect_resource`, `traits_birds.json`, `ecosystem.json` (`weather`/`clock_hour`).
- Variable mapping: `species_id` resolves in `species_catalogue.json`; `forage_probability = g(insect_activity, patch, time_of_day)`; `insect_activity = f(Tair, wind, moisture, flowering_stage, sun/cloud, hour)`.

### B. Parameter Provenance and Status (binding per AGENTS.md)
For every numerical parameter delivered:
- Declare `run_mode`: `illustrative` (default), `scenario`, `hindcast`, or `observed_replay`. `forecast` builds are refused.
- Label `status`: `illustrative` (coefficients chosen, not calibrated) unless a locked-final evaluation window exists. Both seed claims stay `not_yet_accepted` until then.
- Provide `parameter_provenance`: source filenames, SHA references where applicable, `code_rev`, `units`, `contract_version: "0.1.0"`, `world_id: "yellowstone_midway"`.
- Unknown parameter uncertainty stays `unknown`. Do not invent distributions or ranges where data is missing.

### C. Validation Criteria (observable behaviors)
State what the simulation must visibly reproduce for this species, per M05 acceptance:
- Overcast + wind (`gust_mps` / `wind_xz_mps`) -> `insect_activity` < 0.035 -> insects `inactive`, birds `perch`.
- Sunny calm -> `hover`/`forage` behavior; `forage_probability` rises with `insect_activity`.
- Dipper stays at river-bank stones (`river_5856_0` index area); Raven `perch`/`forage`/`return` cadence follows weather state.
- Bird behavior does not drift independently of `weather` authority (`M02`).

### D. Thermal, Suitability, and Behavioral Equation Parameters
Provide quantitative parameters compatible with existing simulation functions:
- `insect_activity` model coefficients per species (if this species is prey / linked to insect guild): `Tair`, `wind`, `moisture`, `flowering_stage`, `sun/cloud`, `hour` weights.
- `forage_probability` parameters: patch preference, time-of-day factors, `insect_activity` sensitivity.
- Bird behavior durations: `perch_seconds`, `hover_seconds`, `forage_seconds`, `return_path` patterns; `walk_mps` / `flight_speed` if modeled.
- Thermal tolerance: lower/upper critical temperature (`LCT`/`UCT`), thermoneutral zone (`TNZ`), behavioral thermoregulation (shade/nest selection) compatible with `thermal_performance()` framework.
- Habitat / exclusion mapping: nest-site categories, riparian dependence (`river_id`), meadow/alpine preference, exclusion categories (`water`, `cliff`, `thermal` if applicable).
- Seasonal module (`M08`): breeding/migration `phenology_stage`, `snow_depth_m` effect on nesting/foraging, seasonal habitat shift parameters.
- If predator-prey interactions are modeled: prey list with `competition_factor` / interaction strength; predator avoidance behavior parameters.

## Deliverables

### Immediate (Phase 2 Complete)
1. Comprehensive species documentation for all target species (100+)
2. Structured research prompts completed for each species
3. Integration mapping for each species within existing birds module
4. Priority ranking and data quality assessments
5. Clear roadmap for subsequent implementation phases
6. Data gap analysis and reliability assessments

### By Project Completion
1. Fully implemented avian species modules integrated into simulation
2. Validation frameworks established for all species components
3. Complete parameter registry for avian species
4. Documentation of model improvements from avian integration
5. Ongoing monitoring and update protocols established

## Research Methodology

### Primary Research Approach
- Systematic literature review using academic databases (Web of Science, JSTOR, Google Scholar)
- Direct queries to Yellowstone National Park Monitoring and Research Program
- Review of USFWS Breeding Bird Survey protocols and data
- Analysis of regional wildlife management agency reports
- Synthesis of peer-reviewed ecological studies

### Data Integration Strategy
- Cross-reference existing traits_birds.json data
- Validate Yellowstone-specific parameters against known species ranges
- Identify complementary datasets for parameter ranges
- Establish confidence levels based on data source quality
- Create uncertainty ranges for simulation parameter sensitivity

## Quality Control Process

### Data Validation Steps
1. Source verification (peer-reviewed vs. gray literature)
2. Yellowstone relevance assessment
3. Parameter consistency checks across sources
4. Historical trend analysis where available
5. Regional applicability validation
6. Simulation compatibility assessment

### Gap Identification
1. Parameters missing entirely
2. Data quality concerns
3. Geographic coverage gaps
4. Temporal coverage issues
5. Species-specific data limitations

This Phase 2 foundation will enable subsequent phases to efficiently implement the avian species integration while maintaining scientific rigor and simulation compatibility.

---

**Next Steps:**
1. Begin systematic research using provided prompts for Priority 1 species
2. Focus on waterfowl species with established monitoring programs
3. Target species with Yellowstone-specific ecological data
4. Prioritize parameters directly compatible with existing simulation constraints
5. Maintain consistent documentation format across all species
6. Establish review process for data quality and integration recommendations
