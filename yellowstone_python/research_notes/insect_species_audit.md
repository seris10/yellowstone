# Phase 4: Insect Diversity Audit and Documentation

## Overview
Systematic audit and documentation of all missing insect species in the Yellowstone Python simulation. Target: 100+ currently unrepresented species beyond EPT/dipteran/aquatic_insect_guild functional groups currently implemented. This Phase 4 establishes the foundation for comprehensive insect species integration by documenting detailed ecological, phenological, and simulation-relevant parameters for Yellowstone's diverse insect communities.

## Current Status Assessment

Based on existing traits_invertebrates.json data, the following insect species are currently represented:

### Bees (Hymenoptera - Apidae)
- Bombus occidentalis (Western bumble bee)
- Bombus huntii (Hunt's bumble bee)
- Bombus centralis (Central bumble bee)
- Bombus flavifrons (Yellow-fronted bumble bee)
- Bombus mixtus (Fuzzy-horned bumble bee)
- Bombus insularis (Indiscriminate cuckoo bumble bee)

### Butterflies & Moths (Lepidoptera)
- Danaus plexippus (Monarch)
- Aglais milberti (Milbert's tortoiseshell)
- Nymphalis antiopa (Mourning cloak)
- Colias philodice (Clouded sulphur)
- Speyeria mormonia (Mormon fritillary)
- Plebejus icarioides (Boisduval's blue)
- Papilio rutulus (Western tiger swallowtail)

### Dragonflies & Damselflies (Odonata)
- Aeshna palmata (Paddle-tailed darner)
- Sympetrum internum (Cherry-faced meadowhawk)
- Enallagma spp. (Bluet damselfly guild)

### Mayflies, Stoneflies & Caddisflies (Ephemeroptera, Plecoptera, Trichoptera) - EPT Proxy
- Pteronarcys californica (California salmonfly)
- Hesperoperla pacifica (Golden stonefly)
- Drunella grandis (Green drake)
- Baetis spp. (Blue-winged olive guild)
- Hydropsyche spp. (Spotted sedge caddisfly)

### Beetles (Coleoptera)
- Cicindelidia haemorrhagica (Wetsalts tiger beetle)
- Ephydra spp. (Thermal shore fly)
- Potamopyrgus antipodarum (New Zealand mudsnail)
- Dendroctonus ponderosae (Mountain pine beetle)
- Polyphylla decemlineata (Ten-lined June beetle)
- Euphoria inda (Bumble flower beetle)
- Leptoglossus occidentalis (Western conifer seed bug)

### Ants (Formicidae)
- Formica obscuripes (Thatching ant)

### Arachnids (Arthropoda - Araneae)
- Hogna spp. (Wolf spider)

### Other Invertebrates (Miscellaneous)
- Opiliones spp. (Harvestman guild)
- Gammarus lacustris (Lacustrine scud amphipod)
- Erpobdella / Placobdella spp. (Leech guild)
- Aquarius / Gerris spp. (Water strider guild)
- Notonecta spp. (Backswimmer)
- Dytiscus spp. (Predaceous diving beetle)

### Dipterans (Already Implemented)
- Various species represented in dipteran functional group

**Total currently represented:** ~60 species

## Research Scope

This Phase 4 establishes the foundation for insect species integration by documenting:

1. Complete species taxonomy and ecological grouping within Yellowstone's freshwater/terrestrial insect communities
2. Geographic distribution and Yellowstone habitat requirements across terrestrial and aquatic ecosystems
3. Species-specific ecological data: population densities, feeding behaviors, life history patterns, temperature tolerances, breeding requirements
4. Species interaction data: food web relationships, competition patterns, predator-prey relationships, ecosystem roles
5. Phenological patterns: emergence timing, flight periods, life cycle timing in Yellowstone's thermal ecology
6. Seasonal behavioral patterns: Yellowstone seasonal ecosystem patterns, habitat shifts
7. Species-specific thermal tolerances and ecological requirements for simulation integration
8. Yellowstone-specific monitoring data from insect surveys and ecological monitoring programs
9. Literature citations with direct URLs to primary research sources, Yellowstone research studies, USDA insect surveys
10. Integration recommendations for insects_birds.py expansion

## Target Species Categories for Phase 4

### Priority 1: Aquatic Insects - Yellowstone Lake & River Species

#### Mayfly Species (400+ species in Yellowstone rivers)
- Ephemerella subvaria (Gray drake mayfly)
- Ephemerella dorsata (Pale shadow mayfly)
- Heptagenia (Heptagenia) spp. (Flat-headed mayflies)
- Leptophlebiidae spp. (Sedge flies)
- Baetidae spp. (Blue-winged olives - multiple species)
- Ephemeridae spp. (Mayflies)

#### Stonefly Species (120+ species in Yellowstone)
- Pteronarcys californica (California salmonfly)
- Helicopsyche (Spinning caddisfly)
- Rhyacophylax spp. (Swift sedges)
- Capniidae spp. (Small winter stoneflies)
- Nemouridae spp. (Pin stream stoneflies)
- Perlidae spp. (River stoneflies)

#### Caddisfly Species (300+ species in Yellowstone)
- Hydropsyche spp. (Spotted sedge)
- Phryganeidae spp. (Giant caddisflies)
- Limnephilidae spp. (Filamentous caddisflies)
- Glossosomatidae spp. (Snail-case caddisflies)
- Molannidae spp. (Spruce millers)

#### Aquatic Beetles
- Dytiscus spp. (Predaceous diving beetles)
- Gyrinus spp. (Whirligig beetles)
- Haliplidae spp. (Crawling water beetles)
- Noteridae spp. (Small water beetles)

#### Dragonfly & Damselfly Species (150+ species in Yellowstone)
- Aeshna spp. (Green darner complex)
- Anax spp. (Blue-bodied hawkers)
- Erythemis spp. (Skimmers)
- Libellula spp. (Broad-tailed dragonflies)
- Sympetrum spp. (Skimmers)
- Enallagma spp. (Bluets)
- Ischnura spp. (Darters)

### Priority 2: Terrestrial Insects - Yellowstone Terrestrial Ecosystems

#### Butterfly Species (500+ species in Yellowstone)
- Papilio machaon (Booth's swallowtail)
- Papilio polyxenes (Parsley swallowtail)
- Parnassius (Thimble) spp. (Snow butterflies)
- Lycaena (Copper) spp. (Coppers)
- EUMAEA spp. (Fritillaries)
- Polites spp. (Skippers)
- Hesperiidae spp. (Grass skippers)

#### Beetle Species (100,000+ species, Yellowstone focus)
- Carabus spp. (Ground beetles)
- Buprestidae spp. (Metallic wood-boring beetles)
- Cerambycidae spp. (Longhorn beetles)
- Curculionidae spp. (Weevils)
- Staphylinidae spp. (Rove beetles)
- Geotrupidae spp. (Earth-boring beetles)
- Scarabaeidae spp. (Scarab beetles)

#### Wasps & Ants
- Vespula spp. (Yellowjackets)
- Polistes spp. (Paper wasps)
- Dolichovespula spp. (Baldfaced hornets)
- Formica spp. (Ants - multiple species)
- Myrmica spp. (Stingless ants)

#### Specialized Species - Yellowstone Endemic Insects
- Balsam twig beetle (Natonia flavipes)
- Yellowstone cutworm moth (Protaphorura spp.)
- High-elevation specialist beetles (Carabidae)
- Thermal spring insects (Sulawesi endemic species)

#### Food Web Specialists
- Predaceous diving beetle larvae (Dytiscidae)
- Predaceous water scorpion larvae (Belostomatidae)
- Aquatic hymenopterans (Braconidae, Ichneumonidae)
- Parasitic wasps (Chalcidoidea)
- Parasitoid flies (Tachinidae, Dolichopodidae)

## Research Prompt Template

For each target species, use the following structured research approach:

### 1. Species Taxonomy and Ecological Grouping
Prompt: "Provide complete taxonomy for [Species Name] including:
- Scientific classification (Kingdom to Species)
- Subspecies and geographic variants relevant to Yellowstone
- Ecological group classification (aquatic/terrestrial, predator/prey, specialist/generalist)
- Trophic level and functional group role
- Key morphological adaptations for Yellowstone habitat

Format as structured JSON with clear hierarchy and Yellowstone-specific notes."

### 2. Geographic Distribution and Habitat Requirements
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

### 8. Yellowstone-Specific Monitoring Data
Prompt: "Document Yellowstone monitoring program data for [Species Name]:
- NPS annual insect surveys and population counts
- Statewide insect monitoring programs (Wyoming Entomology)
- Aquatic insect sampling protocols (EPIC, EPA protocols)
- Butterfly monitoring programs (MCM - Monarch Conservation Monitor)
- Beetle trap surveys and pitfall sampling data
- Thermal spring specialist surveys
- Habitat-specific sampling efforts

Include sampling methods, time periods, observer biases, and sample sizes.
Focus on data sources that can be directly used in simulation validation."

### 9. Literature Citations with Direct URLs
Prompt: "Provide primary research sources with direct URLs for [Species Name]:
- Peer-reviewed scientific studies specific to Yellowstone or similar high-elevation ecosystems
- Government and agency reports (NPS, US Fish & Wildlife Service, USDA)
- Monitoring program data and annual reports from Yellowstone
- Dissertation/thesis research relevant to Yellowstone
- Technical reports and agency publications

For each source, provide:
- Full citation in standardized format
- Direct URL to source
- Specific findings relevant to simulation parameters
- Data quality assessment (peer-reviewed, government data, etc.)

Format as reference list with citation tags for integration into species documentation."

### 10. Integration Recommendations for insects_birds.py Expansion
Prompt: "Recommend integration points for [Species Name] in Yellowstone Python simulation:
- Primary module placement: insects_birds.py, insects.py, or new module
- Parameter mapping: existing simulation knobs that correspond to species traits
- Interaction integration points: predator-prey, competition, habitat modules
- Seasonal module placement: timing and behavioral pattern integration
- Data structure recommendations: format and location for species-specific data
- Validation requirements: observable behaviors to match simulation outputs

Consider:
- Existing module architecture and data structures
- Integration with current species (dipper, raven, trout)
- Simulation temporal and spatial scales
- Parameter compatibility with existing models

Provide specific code integration guidance and potential collaboration points with other species modules.
Focus on practical implementation within current simulation constraints."

## Prioritization Framework

### High Priority (Yellowstone Monitoring Programs Established)
1. Ephemerella subvaria (Gray drake) - Indicator species, extensive sampling
2. Pteronarcys californica (California salmonfly) - Keystone predator, frequent observations
3. Aeshna spp. (Green darner) - Dragonfly surveys, widespread distribution
4. Baetidae spp. (Blue-winged olive) - Aquatic ecosystem indicator
5. Formica spp. (Thatching ant) - Soil ecosystem engineer, monitoring data available
6. Polistes spp. (Paper wasp) - Nesting observations, seasonal presence
7. Libellula spp. (Broad-tailed dragonfly) - Dragonfly surveys, common indicator
8. Colias philodice (Clouded sulphur) - Butterfly monitoring, phenology records

### Medium Priority (Good Literature Base)
1. Various Baetis species (Blue-winged olives) - Mayfly ecology studies
2. Enallagma spp. (Bluet damselflies) - Odonata research
3. Formica obscuripes (Thatching ant) - Ant ecology studies
4. Sympetrum spp. (Skimmer dragonflies) - Dragonfly behavior studies
5. Polyphylla decemlineata (Ten-lined June beetle) - Beetle ecology
6. Various carabid beetles - Ground beetle research
7. Various Parasitidae wasps - Wasp biology studies

### Lower Priority (Limited Data, Gaps Identified)
1. High-elevation specialist beetles - Limited Yellowstone data
2. Thermal spring endemic species - Rare, localized distributions
3. Specialized caddisfly species - Insufficient sampling
4. Parasitic wasp species - Limited distribution data
5. Late-season moth species - Insufficient phenology records

## Data Quality Standards

### Primary Data Sources (Highest Priority)
- Yellowstone National Park Insect Monitoring Program
- US Fish & Wildlife Service Insect Surveys
- NPS Research publications and monitoring reports
- Peer-reviewed studies with Yellowstone focus
- Wyoming Game & Fish Department entomological surveys

### Secondary Data Sources
- Regional entomological studies
- Similar high-elevation ecosystem research
- Historical museum records and specimens
- State wildlife agency monitoring programs

### Data Quality Assessment Criteria
- Temporal relevance (last 10-15 years preferred)
- Geographic specificity (Yellowstone or similar high-elevation ecosystems)
- Sample size and statistical robustness
- Peer-review status and methodology quality
- Parameter relevance to simulation requirements
- Yellowstone-specific data availability

## Integration Roadmap

### Phase 4 (Current)
- Complete species taxonomy and literature review for target 100+ species
- Document ecological requirements and habitat parameters
- Identify data gaps and reliability assessments
- Define integration points within existing insects_birds.py module
- Develop specific research prompts for each target species

### Phase 5 (Follow-up)
- Develop simulation parameter mappings for insect species
- Create data structure templates for insect species integration
- Establish validation frameworks for insect components
- Begin integration into insects_birds.py module
- Implement core insect species modules

### Phase 6 (Implementation)
- Implement species modules with validated parameters
- Validate against existing insect observations
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
- Compatibility with existing insects_birds.py functions and compartments

## Simulation Integration Requirements (add to every species profile)

Every insect species profile delivered by this audit must include the sections below. They are required for `insects_birds.py` integration per `01_PYTHON_BUILD_SPEC.md` M05.

### A. Simulation Parameter Mapping
State the exact module, file, and variable structures this species feeds:
- Module: `insects_birds.py` (existing); `insects.py` (potential new module).
- Data structures: `patches[].insect_resource`, `patches[].biomass` (if prey base), `ecosystem.json` (`weather`/`clock_hour`/`humidity`/`cloud`), `wildlife[]` (if bird interaction modeled).
- Variable mapping: `insect_activity = f(Tair, wind, moisture, flowering_stage, sun/cloud, hour)`; `dN/dt` recovery-style resource dynamics.

### B. Parameter Provenance and Status (binding per AGENTS.md)
For every numerical parameter delivered:
- Declare `run_mode`: `illustrative` (default), `scenario`, `hindcast`, or `observed_replay`. `forecast` builds are refused.
- Label `status`: `illustrative` (coefficients chosen, not calibrated) unless a locked-final evaluation window exists. Both seed claims stay `not_yet_accepted` until then.
- Provide `parameter_provenance`: source filenames, SHA references where applicable, `code_rev`, `units`, `contract_version: "0.1.0"`, `world_id: "yellowstone_midway"`.
- Unknown parameter uncertainty stays `unknown`. Do not invent distributions or ranges where data is missing.

### C. Validation Criteria (observable behaviors)
State what the simulation must visibly reproduce for this species, per M05 acceptance:
- Sunny + calm (`wind_xz_mps` low, `sun/cloud` favorable) -> `insect_activity` high -> `active` / `hover`.
- Overcast + high gust -> `insect_activity` < 0.035 -> `inactive`.
- Species-specific emergence timing (`phenology_stage`) aligns with thermal ecology (`5-24°C` range).
- Activity follows weather authority (`M02`) without per-insect phase drift.

### D. Thermal, Suitability, and Behavioral Equation Parameters
Provide quantitative parameters compatible with existing simulation functions:
- `insect_activity` function coefficients: `Tair` weight, `wind` weight, `moisture` weight, `flowering_stage` weight, `sun/cloud` weight, `hour` weight / circadian factor.
- Life-cycle / emergence: `phenology_stage` mapping (spring/summer/fall/winter); thermal trigger temperatures for emergence; flight-period duration.
- Thermal tolerance: `LCT`, `UCT`, `TNZ`; acclimatization capacity; behavior thresholds (shade, burrow, water surface).
- Feeding / resource dynamics: `dN/dt` recovery coefficient, resource base (`patch` biomass/moisture), predator-prey interaction strengths with bird species (`dipper`, `raven`, `goose`).
- Habitat / exclusion mapping: aquatic vs terrestrial, thermal spring tolerance, elevation preference; `exclusion` categories (`thermal`, `water`, `cliff`) if applicable.
- Seasonal module (`M08`): winter dormancy parameters, `snow_depth_m` survival threshold, spring emergence trigger (`soil_moisture` / temperature).

## Deliverables

### Immediate (Phase 4 Complete)
1. Comprehensive species documentation for all target species (100+)
2. Structured research prompts completed for each species
3. Integration mapping for each species within existing insects_birds.py architecture
4. Priority ranking and data quality assessments
5. Clear roadmap for subsequent implementation phases
6. Data gap analysis and reliability assessments

### By Project Completion
1. Fully implemented insect species modules integrated into simulation
2. Validation frameworks established for all insect species components
3. Complete parameter registry for insect species
4. Documentation of model improvements from insect integration
5. Ongoing monitoring and update protocols established

## Research Methodology

### Primary Research Approach
- Systematic literature review using academic databases (Web of Science, JSTOR, Google Scholar)
- Direct queries to Yellowstone National Park Monitoring and Research Program
- Review of USFWS insect monitoring protocols and data
- Analysis of regional wildlife management agency entomological reports
- Synthesis of peer-reviewed ecological studies focused on Coleoptera, Lepidoptera, Odonata, Ephemeroptera, Plecoptera, Trichoptera

### Data Integration Strategy
- Cross-reference existing traits_invertebrates.json data
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

## Next Steps

1. Begin systematic research using provided prompts for Priority 1 species
2. Focus on aquatic insects with established monitoring programs
3. Target species with Yellowstone-specific emergence timing and phenology
4. Prioritize parameters directly compatible with existing insects_birds.py functions
5. Maintain consistent documentation format across all species
6. Establish review process for data quality and integration recommendations

This Phase 4 foundation will enable subsequent phases to efficiently implement the comprehensive insect species integration while maintaining scientific rigor and simulation compatibility for Yellowstone's complex aquatic and terrestrial insect communities.
