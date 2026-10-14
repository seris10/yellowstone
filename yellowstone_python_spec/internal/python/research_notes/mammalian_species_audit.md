# Phase 1: Mammalian Diversity Audit and Documentation

## Overview
Systematic audit and documentation of all missing mammal species in the Yellowstone Python simulation. Target: 50+ currently unrepresented species including elk, wolf, bear, deer, moose, beaver, otter, puma, lynx, wolverine, badgers, weasels, rodents, and other small mammals.

## Research Scope
This Phase 1 establishes the foundation for mammalian species integration by documenting:
1. Complete species taxonomy and ecological grouping
2. Geographic distribution and Yellowstone habitat requirements
3. Species-specific ecological data for simulation parameters
4. Population dynamics and carrying capacity data
5. Species interaction data
6. Phenological patterns and temporal dynamics
7. Seasonal behavioral adaptations and habitat shifts
8. Literature citations with direct URLs to primary research sources
9. Data gaps identified and reliability assessments
10. Integration recommendations for simulation module placement

## Target Species Categories

### Large Ungulates
- Elk (Cervus canadensis) - multiple subspecies (e.g., Roosevelt elk, Rocky Mountain elk)
- Moose (Alces alces)
- Deer (Odocoileus spp.) - mule deer (O. hemionus), white-tailed deer (O. virginianus)

### Carnivores
- Gray wolf (Canis lupus)
- Coyote (Canis latrans)
- Grizzly bear (Ursus arctos horribilis)
- Black bear (Ursus americanus)
- Puma / cougar / mountain lion (Puma concolor)
- Lynx (Lynx canadensis)
- Wolverine (Gulo gulo)
- Badgers (Taxidea taxus)
- Weasels (Mustelidae family)

### Medium-sized Furbearers
- Beaver (Castor canadensis)
- Otter (Lontra canadensis)
- Fisher (Pekania pennanti)
- Marten (Martes americana)
- Bobcat (Lynx rufus)

### Small Mammals and Rodents
- Various rodent species (Squirrel family, mouse family, etc.)
- Shrews (Soricidae family)
- Pikas (Ochotona princeps)
- Ground squirrels

## Research Prompt Template

For each target species, use the following structured research approach:

### 1. Species Taxonomy and Ecological Grouping
Prompt: "Provide complete taxonomy for [Species Name] including:
- Scientific classification (Kingdom to Species)
- Subspecies and geographic variants relevant to Yellowstone
- Ecological group classification (ungulate, carnivore, rodent, etc.)
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

### 4. Population Dynamics and Carrying Capacity
Prompt: "Document population parameters for [Species Name] in Yellowstone context:
- Historical population trends and monitoring data
- Current population estimates with confidence intervals
- Carrying capacity calculations for Yellowstone ecosystem
- Reproductive rates: litter size, breeding frequency, age-specific fertility
- Survival rates: juvenile, adult, senescence mortality
- Density-dependent regulation mechanisms
- Impact of predators, disease, environmental factors on population dynamics

Include data sources, time periods, and reliability assessments.
Focus on parameters compatible with existing simulation population models."

### 5. Species Interaction Data
Prompt: "Document predator-prey, competition, and symbiotic relationships for [Species Name]:
- Predator relationships: natural predators, predation pressure, predator-prey dynamics
- Competition patterns: intra-specific, inter-specific competition for resources
- Disease vectors and pathogens known in Yellowstone region
- Symbiotic relationships: mutualisms, commensalisms
- Human-wildlife conflict patterns and management interventions
- Impact of wolves on other carnivores and herbivores (trophic cascades)

Include interaction strengths, seasonal variations, and Yellowstone-specific dynamics.
Focus on quantitative parameters for simulation interaction models."

### 6. Phenological Patterns and Temporal Dynamics
Prompt: "Document phenological patterns for [Species Name] in Yellowstone:
- Breeding/ reproductive timing: season, duration, environmental triggers
- Migration patterns: timing, routes, destination reasons
- Hibernation patterns: timing, duration, physiological triggers
- Seasonal behavioral shifts: activity patterns, habitat use changes
- Food caching behaviors and timing
- Annual activity budget and temporal allocation

Include specific dates or day-of-year ranges where available.
Focus on parameters that can be translated to simulation seasonal modules."

### 7. Seasonal Behavioral Adaptations and Habitat Shifts
Prompt: "Document seasonal behavioral adaptations for [Species Name]:
- Winter adaptations: insulation, metabolism, food acquisition strategies
- Summer adaptations: thermoregulation, reproductive behaviors
- Spring/Fall transition behaviors and resource use
- Denning/brochue-site selection and characteristics
- Foraging strategies by season and habitat type
- Avoidance behaviors: human proximity, predators, harsh weather

Include behavioral mechanisms and ecological rationales.
Focus on habitat shift parameters for spatial simulation components."

### 8. Literature Citations and Research Sources
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

### 9. Data Gaps and Reliability Assessments
Prompt: "Identify data gaps and assess reliability for key parameters of [Species Name]:
- Missing parameters: critical for simulation that lack quantitative data
- Data quality: peer-reviewed vs observational, temporal coverage issues
- Geographic gaps: regions with sparse data vs well-studied areas
- Temporal gaps: seasonal coverage, trend data availability
- Uncertainty ranges: confidence levels for existing parameters
- Priority recommendations: which gaps most impact simulation accuracy

For each gap, provide:
- Parameter name and why it's needed
- Current uncertainty level
- Suggested data collection methods
- Impact assessment on simulation reliability

Focus on gaps that would improve simulation predictive capability."

### 10. Integration Recommendations for Simulation Module Placement
Prompt: "Recommend integration points for [Species Name] in Yellowstone Python simulation:
- Primary module placement: grazers.py, mammals.py, or new module
- Parameter mapping: existing simulation knobs that correspond to species traits
- Interaction integration points: predator-prey, competition, habitat modules
- Seasonal module placement: timing and behavioral pattern integration
- Data structure recommendations: format and location for species-specific data
- Validation requirements: observable behaviors to match simulation outputs

Consider:
- Existing module architecture and data structures
- Integration with current species (elk, trout, insects)
- Simulation temporal and spatial scales
- Parameter compatibility with existing models

Provide specific code integration guidance and potential collaboration points with other species modules.
Focus on practical implementation within current simulation constraints."

## Prioritization Framework

### High Priority (Yellowstone Monitoring Programs Established)
1. Elk (multiple subspecies) - primary grazer, extensive monitoring
2. Gray wolf - keystone predator, intensive research program
3. Moose - foundation species, population trends tracked
4. Grizzly bear - flagship species, radio telemetry data
5. Coyote - widespread, population estimates available

### Medium Priority (Good Literature Base)
1. Mule deer and white-tailed deer - hunting and population data
2. Black bear - management programs and observations
3. Puma - camera traps and radio telemetry
4. Beaver - ecosystem engineer, trapping data
5. Otter - distribution surveys
6. Lynx - snow shoe hare cycle research

### Lower Priority (Limited Data, Gaps Identified)
1. Wolverine - rare, limited monitoring
2. Fisher and marten - furbearer data available
3. Bobcat - regional surveys
4. Small mammals - snapshot studies
5. Weasels - limited distribution data

## Data Quality Standards

### Primary Data Sources (Highest Priority)
- Yellowstone National Park Monitoring and Research Program data
- Peer-reviewed scientific journals with Yellowstone focus
- US Fish & Wildlife Service surveys and reports
- NPS research publications and technical reports

### Secondary Data Sources
- Regional wildlife studies
- Similar ecosystem research
- Historical records and museum data
- State wildlife agency reports

### Data Quality Assessment Criteria
- Temporal relevance (last 10-15 years preferred)
- Geographic specificity (Yellowstone or similar high-elevation ecosystems)
- Sample size and statistical robustness
- Peer-review status and methodology quality
- Parameter relevance to simulation requirements

## Integration Roadmap

### Phase 1 (Current)
- Complete species taxonomy and literature review
- Document ecological requirements and habitat parameters
- Identify data gaps and reliability assessments
- Define integration points within existing modules

### Phase 2 (Follow-up)
- Develop simulation parameter mappings
- Create data structure templates
- Establish validation frameworks
- Begin integration into grazers.py and potential mammals.py module

### Phase 3 (Implementation)
- Implement core species modules
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

### Technical Standards
- Parameter units standardized (SI where applicable)
- Numerical values converted to simulation-compatible ranges
- References to specific Yellowstone studies prioritized
- Gaps clearly identified with suggested solutions
- Integration pathways clearly mapped to existing modules

## Simulation Integration Requirements (add to every species profile)

Every mammalian species profile delivered by this audit must include the sections below. They are required for `grazers.py` / potential `mammals.py` integration per `01_PYTHON_BUILD_SPEC.md` M07.

### A. Simulation Parameter Mapping
State the exact module, file, and variable structures this species feeds:
- Module: `grazers.py` (existing); potential `mammals.py` (new).
- Data structures: `wildlife[]` (`path_xz`, `graze/rest_seconds`, `grazing_index_per_second`), `patch_state.json` (`patches[].biomass`), exclusion mask (`thermal/water/cliff/building`), `ecosystem.json`.
- Variable mapping: `species_id` matches `species_catalogue.json`; `habitat_mask.png` eligibility grid; biomass dynamics `dB/dt = r·flight·fwater·B(1-B/K) - G`.

### B. Parameter Provenance and Status (binding per AGENTS.md)
For every numerical parameter delivered:
- Declare `run_mode`: `illustrative` (default), `scenario`, `hindcast`, or `observed_replay`. `forecast` builds are refused.
- Label `status`: `illustrative` (coefficients chosen, not calibrated) unless a locked-final evaluation window exists. Both seed claims stay `not_yet_accepted` until then.
- Provide `parameter_provenance`: source filenames, SHA references where applicable, `code_rev`, `units`, `contract_version: "0.1.0"`, `world_id: "yellowstone_midway"`.
- Unknown parameter uncertainty stays `unknown`. Do not invent distributions or ranges where data is missing.

### C. Validation Criteria (observable behaviors)
State what the simulation must visibly reproduce for this species, per M07 acceptance:
- A* path never enters exclusion (`thermal`/`water`/`cliff`/`building`).
- Biomass declines with grazing (`G`) then recovers (`dB/dt` ledger positive over season).
- 10-min walk trace stays inside valid habitat tiles; tile-boundary crossings are logged.
- Sparse counts stay sparse (no universal `wolves→elk→willow` slider invented without evidence).

### D. Thermal, Suitability, and Behavioral Equation Parameters
Provide quantitative parameters compatible with existing simulation functions:
- Exclusion mask categories applicable to this species (`thermal`, `water`, `cliff`, `building`).
- Habitat suitability field parameters: `λs,0`, `Mhabitat(p)`, `fs(...)` factors (soil, moisture, slope, aspect, canopy, disturbance), `Mexclusion(p)`.
- Movement/path planning: `walk_mps`, `path_xz` format, A* eligibility grid constraints, home-range / territory size.
- Grazing dynamics: `graze/rest_seconds`, `grazing_index_per_second`, biomass debit `G`, carrying capacity `K`, growth rate `r`.
- Seasonal module (`M08`): `snow_depth_m` response, `phenology_stage`, thermal exclusion behavior in winter.
- If interaction with predators (`wolf`, `coyote`, etc.) is modeled: `competition_factor`, interaction strength, seasonal variation.

## Deliverables

### Immediate (Phase 1 Complete)
1. Comprehensive species documentation for all target species
2. Structured research prompts completed for each species
3. Integration mapping for each species within existing simulation architecture
4. Priority ranking and data quality assessments
5. Clear roadmap for subsequent implementation phases

### By Project Completion
1. Fully implemented mammalian species modules integrated into simulation
2. Validation frameworks established for all species components
3. Complete parameter registry for mammalian species
4. Documentation of model improvements from mammalian integration
5. Ongoing monitoring and update protocols established

## Next Steps

1. Begin systematic research using provided prompts
2. Prioritize species with established Yellowstone monitoring programs
3. Focus on parameters directly compatible with existing simulation constraints
4. Maintain consistent documentation format across all species
5. Establish review process for data quality and integration recommendations

This Phase 1 foundation will enable subsequent phases to efficiently implement the mammalian species integration while maintaining scientific rigor and simulation compatibility.
