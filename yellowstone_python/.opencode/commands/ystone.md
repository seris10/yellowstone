---
description: Orient to the Yellowstone Python project with universal rules, repo map, and roadmap to task-specific docs plus comprehensive species completeness audit tools
---

# Yellowstone orientation

You are orienting to the Yellowstone Python project (working directory).
This brief is universal: it holds regardless of task focus. Do not add
focus-specific detail beyond pointing at the roadmap below.

Focus, if given: $ARGUMENTS (may be empty; the brief stays universal
either way — use a focus only to emphasize which roadmap entries matter).

## Universal rules (apply to every task)

1. Read `AGENTS.md` in the working directory first. It carries the binding
   init rules: comment style, no-dating policy, store usage, pycl memory
   protocol, run modes, and verification commands.
2. Comment style: terse factual comments. No em dashes, no first person,
   no addressing the reader, no `X, not Y` contrasts, no
   hypothetical-failure narratives (`never silently`, `instead of
   guessing`), no temporal references (`legacy`, `audit fix`, `now`),
   American spelling. Examples are in `AGENTS.md` section 2.
3. No date-stamped filenames in code, configs, tests, notebooks, or tool
   defaults. Role words (`prior_window`) or in-file metadata instead.
4. Every config declares `run_mode`. Prescribed forcing is never reported
   as validation. Both seed claims are `not_yet_accepted`; keep them so
   until a locked-final window is evaluated. Unknown uncertainty stays
   `unknown`.
5. Verify with `pytest`, a full `build`, and `audit_provenance` before
   reporting done. New modules ship with tests.

## Orient now

Read `README.md`, then the newest `derived/<build-id>/BUILD.json`
(`run_mode`, `prescribed_quantities`, `claim_ids`). Reply with a short
orientation: what the project simulates, current build state, and which
roadmap entries the focus (if any) points at. Then ask what to do.

## Deep Research Prompt Suite - Species Completeness Audit

This section contains comprehensive deep research prompts to audit the project's simulations for species completeness across all kingdoms. The prompts will return:

1. **Comprehensive coverage** of all species currently missing from simulations
2. **Required data** on individual species including taxonomy, ecology, population dynamics
3. **Species interactions** including predator-prey relationships, competition patterns, symbiotic relationships
4. **Complete list** of research URLs and citations for verification

### Phase 1: Mammalian Species Audit

**File:** `research_notes/mammalian_species_audit.md`

**Research Focus:** Target 50+ currently unrepresented mammal species including:
- Large ungulates (elk, moose, deer - multiple subspecies)
- Carnivores (gray wolf, coyote, bears, pumas, lynx, wolverine, badgers)
- Medium-sized furbearers (beaver, otter, fisher, marten, bobcat)
- Small mammals and rodents (various species)

**Required Data for Each Species:**
1. Complete taxonomy and ecological grouping
2. Geographic distribution and Yellowstone habitat requirements
3. Population estimates, diet composition, seasonal behaviors, thermal tolerances
4. Population dynamics and carrying capacity data
5. Species interaction data (predator-prey, competition, disease vectors)
6. Phenological patterns and temporal dynamics
7. Seasonal behavioral adaptations and habitat shifts
8. Literature citations with direct URLs to primary research sources
9. Data gaps identified and reliability assessments
10. Integration recommendations for simulation module placement

### Phase 2: Avian Species Audit

**File:** `research_notes/bird_species_audit.md`

**Research Focus:** Target 100+ currently unrepresented bird species across all functional groups including:
- Waterfowl (multiple duck, goose, teal species)
- Raptors (bald eagle, peregrine falcon, hawk species)
- Songbirds (warbler species, finches, sparrows, thrushes)
- Shorebirds and waterbirds
- Woodpeckers and related species
- Owls
- Swifts, swallows, and flying insects

**Required Data for Each Species:**
1. Complete taxonomy and classification
2. Geographic distribution and Yellowstone habitat requirements
3. Species-specific ecological data (population estimates, diet composition, thermal tolerances)
4. Species interaction data (predator-prey relationships, competition, diet overlaps)
5. Phenological patterns (breeding seasons, migration timing, nesting behavior)
6. Seasonal behavioral patterns and habitat shifts
7. Species-specific thermal tolerances for simulation integration
8. Literature citations with direct URLs to primary research sources
9. Yellowstone monitoring program data where available
10. Integration recommendations for birds module integration

### Phase 3: Fish Species Audit

**File:** `research_notes/fish_species_audit.md`

**Research Focus:** Target 100+ currently unrepresented fish species beyond the two trout species currently implemented:
- Salmon species (coho, chinook, sockeye, pink)
- Whitefish species (Lake Yellowstone whitefish, mountain whitefish)
- Lake trout and Arctic char species
- Sculpin and burbot species
- Minnow and cyprinid species
- Game fish species

**Required Data for Each Species:**
1. Complete taxonomy and Yellowstone Lake ecosystem placement
2. Geographic distribution and Yellowstone habitat requirements
3. Population estimates, growth rates, temperature tolerances, spawning requirements
4. Species interaction data (predator-prey relationships, competition patterns, diet composition)
5. Life history traits (spawning timing, behavior, temperature requirements, habitat preferences)
6. Species-specific thermal tolerances for simulation integration
7. Yellowstone-specific population data from monitoring programs
8. Literature citations with direct URLs to primary research sources, USGS data, Yellowstone reports
9. Integration recommendations for fish module expansion

### Phase 4: Insect Species Audit

**File:** `research_notes/insect_species_audit.md`

**Research Focus:** Target 100+ currently unrepresented insect species beyond the three groups (EPT/dipteran/aquatic_insect_guild) currently implemented:
- Mayfly species (400+ species in Yellowstone)
- Stonefly species (120+ species in Yellowstone)
- Caddisfly species (300+ species in Yellowstone)
- Butterfly and moth species (500+ species in Yellowstone)
- Beetle species (1,000+ species in Yellowstone)
- Dragonfly and damselfly species (150+ species in Yellowstone)

**Required Data for Each Species:**
1. Complete taxonomy and Yellowstone freshwater/terrestrial insect community classification
2. Geographic distribution and Yellowstone habitat requirements across terrestrial and aquatic ecosystems
3. Species-specific ecological data (population densities, feeding behaviors, life history patterns, thermal tolerances)
4. Species interaction data (food web relationships, competition patterns, predator-prey relationships, ecosystem roles)
5. Phenological patterns (emergence timing, flight periods, life cycle timing in Yellowstone's thermal ecology)
6. Seasonal behavioral patterns (Yellowstone seasonal ecosystem patterns, habitat shifts)
7. Species-specific thermal tolerances and ecological requirements for simulation integration
8. Yellowstone-specific monitoring data from insect surveys and ecological monitoring programs
9. Literature citations with direct URLs to primary research sources, Yellowstone research studies, USDA insect surveys
10. Integration recommendations for insects_birds.py expansion

### Phase 5: Invertebrate Species Audit

**File:** `research_notes/invertebrate_species_audit.md`

**Research Focus:** Target 200+ currently unrepresented invertebrate species beyond the pool_crust module currently implemented:
- Freshwater Mollusks (mussels, snails, clams)
- Aquatic Arachnids (water mites, aquatic spiders, water scorpions)
- Onychophorans (terrestrial velvet worms)
- Tardigrades (Yellowstone extremophile species)
- Crustaceans (amphipods, isopods, copepods, decapods)
- Terrestrial Mollusks (land snails, slugs)
- Myriapods (centipedes, millipedes)
- Arachnids (spiders, scorpions)
- Zooplankton and microscopic invertebrates

**Required Data for Each Species:**
1. Complete taxonomy and Yellowstone aquatic/terrestrial invertebrate community classification
2. Geographic distribution and Yellowstone habitat requirements across Yellowstone Lake and river ecosystems
3. Species-specific ecological data (population densities, feeding behaviors, life history patterns, thermal tolerances, metabolic rates)
4. Species interaction data (food web relationships, competition patterns, predator-prey relationships, ecosystem engineering roles)
5. Phenological patterns (emergence timing, reproductive cycles)
6. Yellowstone-specific ecological roles (nutrient cycling, ecosystem engineering)
7. Yellowstone-specific monitoring data from invertebrate surveys and aquatic ecosystem monitoring programs
8. Literature citations with direct URLs to primary research sources, Yellowstone aquatic studies, EPA invertebrate surveys
9. Integration recommendations for pool_crust.py expansion

### Phase 6: Plant Species Audit

**File:** `research_notes/plant_species_audit.md`

**Research Focus:** Target 500+ currently unrepresented plant species beyond the vegetation.py module currently implemented:
- Terrestrial Plants (Conifers, Deciduous Trees, Shrubs, Herbaceous Plants, Cacti/Succulents, Ferns/Fern Allies)
- Alpine Plants (High elevation specialists, tundra plants, rock plants, snow adaptation specialists)
- Wetland Plants (Emergent, submerged, floating, reed species communities)
- Riparian Plants (Riverbank, floodplain, wet meadow, inundated species)

**Required Data for Each Species:**
1. Complete taxonomy and Yellowstone terrestrial plant community classification
2. Geographic distribution and Yellowstone habitat requirements across all ecosystems (lake, river, forest, alpine, wetland)
3. Species-specific ecological data (growth rates, canopy coverage, phenology, photosynthetic efficiency, seasonal patterns)
4. Species interaction data (competition patterns, succession, grazing relationships, Yellowstone specific plant community dynamics)
5. Phenological patterns (Yellowstone spring/summer/fall/winter flowering and fruiting patterns)
6. Seasonal behavioral patterns (Yellowstone light/temperature regime adaptation)
7. Species-specific ecological roles (Yellowstone ecosystem engineers, Yellowstone habitat modifiers)
8. Yellowstone-specific monitoring data from plant surveys and vegetation monitoring programs
9. Literature citations with direct URLs to primary research sources, Yellowstone NPS plant surveys, USDA plant distribution databases
10. Integration recommendations for vegetation.py expansion

### Phase 7: Fungi and Microbial Species Audit

**File:** `research_notes/fungi_microbial_species_audit.md`

**Research Focus:** Target 300+ currently unrepresented fungi and microbial species:
- Mycorrhizal Species (Yellowstone forest fungi relationships)
- Saprotrophic Species (Yellowstone decomposition specialists)
- Pathogenic Species (Yellowstone plant disease agents)
- Insect Pathogenic Species (Yellowstone entomopathogenic fungi)
- Endolithic Species (Yellowstone rock-inhabiting fungi)
- Lichenized Species (Yellowstone lichen communities)
- Myxomyceta (Yellowstone slime molds)
- Basidiomycota and Ascomycota species
- Bacteria, Archaea, Protozoa, Algae, and other microbial life

**Required Data for Each Species:**
1. Complete taxonomy and Yellowstone fungi and microbial community classification
2. Geographic distribution and Yellowstone habitat requirements across all Yellowstone ecosystems
3. Species-specific ecological data (metabolic rates, decomposition rates, symbiotic relationships, Yellowstone ecosystem functions)
4. Species interaction data (Yellowstone mycorrhizal networks, Yellowstone microbial food webs, Yellowstone symbiotic relationships)
5. Yellowstone-specific ecological roles (Yellowstone nutrient cycling, Yellowstone soil formation, Yellowstone ecosystem engineering)
6. Yellowstone-specific ecological significance (Yellowstone keystone species, Yellowstone ecosystem engineers, Yellowstone nutrient cyclers)
7. Yellowstone-specific ecological services (Yellowstone decomposition, Yellowstone nitrogen fixation, Yellowstone phosphorus cycling)
8. Yellowstone-specific monitoring data from fungal surveys and microbial ecology programs
9. Literature citations with direct URLs to primary research sources, Yellowstone mycological surveys, Yellowstone microbial ecology studies
10. Integration recommendations for ecosystem modules (fungi.py, microbial.py, ecosystem_support.py)

## Research Methodology

Each deep research prompt follows a structured approach:

1. **Comprehensive Literature Review**: Systematic review of primary research sources, Yellowstone monitoring programs, and ecological databases
2. **Data Quality Assessment**: Reliability and relevance evaluation of collected data
3. **Yellowstone-Specific Integration**: Focus on Yellowstone ecosystem requirements and thermal ecology (5-24°C range)
4. **Citation Management**: Direct URLs to primary sources, DOI numbers, and data quality assessments
5. **Simulation Compatibility**: Parameter mapping to existing Yellowstone Python simulation architecture

## Research Output Format

Each research phase produces comprehensive documentation with:
- **Species Profiles**: Complete taxonomic and ecological information
- **Simulation Parameters**: Integration-ready data structures for Yellowstone Python modules
- **Research Citations**: Verifiable source documentation with URLs
- **Data Quality Reports**: Reliability assessments and identified gaps
- **Implementation Roadmaps**: Technical integration specifications for simulation modules

## Next Steps

After orientation, use these research prompts to systematically audit species completeness:

1. **Begin with Priority Species**: Start with high-priority species with established Yellowstone monitoring
2. **Data Integration**: Map collected parameters to existing simulation modules
3. **Validation**: Verify data quality and Yellowstone ecosystem relevance
4. **Implementation**: Expand simulation capacity with missing species
5. **Documentation**: Maintain comprehensive research records for future reference

The deep research prompt suite provides a comprehensive foundation for transforming the Yellowstone Python simulation from a limited-species model into a comprehensive Yellowstone ecosystem simulation representing the full biological diversity of Yellowstone National Park.
