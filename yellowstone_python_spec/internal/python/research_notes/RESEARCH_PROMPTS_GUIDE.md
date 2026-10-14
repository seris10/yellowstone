# Yellowstone Python Fish Species Research Prompts Guide

## Overview
This document provides comprehensive research prompts for systematically auditing and documenting 100+ currently unrepresented fish species in the Yellowstone Python simulation.

## Current Status
The Yellowstone Python simulation currently implements:
- **Species**: brown_trout, rainbow_trout
- **Thermal performance data**: Yes (Literature-based with anchors and authored interpolation)
- **Simulation integration**: Complete with habitat suitability, thermal performance, and refuge selection

## Research Prompt Structure

Each research prompt follows this format:

### SPECIES: [Species Name] ([Scientific Name])
**Research Priority**: [High/Medium/Low]
**Focus Area**: [Ecosystem Role/Habitat/Population/etc.]

**1. Complete species taxonomy and taxonomic classification within Yellowstone Lake ecosystem**
- Primary common and scientific names
- Phylogenetic classification within Yellowstone Lake ecosystem
- Taxonomic relationships to existing species (trout, salmon, whitefish)
- Endemic vs. introduced status in Yellowstone

**2. Geographic distribution and Yellowstone Lake/Stream habitat requirements**
- Natural range and Yellowstone-specific distribution
- Habitat requirements in Yellowstone Lake vs. streams
- Temperature preferences for Yellowstone thermal ecology
- Substrate and flow requirements within Yellowstone context
- Seasonal distribution patterns in Yellowstone

**3. Species-specific ecological data: population estimates, growth rates, temperature tolerances, spawning requirements**
- Current Yellowstone population estimates (USGS/GWY monitoring)
- Maximum/minimum sustainable population levels for Yellowstone
- Growth rates specific to Yellowstone thermal regime
- Temperature tolerance ranges for Yellowstone integration
- Spawning requirements (water temperature, flow, substrate)
- Age at maturity in Yellowstone conditions

**4. Species interaction data: predator-prey relationships, competition patterns, diet composition**
- Primary predators in Yellowstone ecosystem
- Prey species and dietary composition
- Competition relationships with existing trout species (brown_trout, rainbow_trout)
- Competitive hierarchies within Yellowstone Lake
- Seasonal diet shifts in Yellowstone ecology

**5. Life history traits: spawning timing, behavior, temperature requirements, habitat preferences**
- Spawning timing relative to Yellowstone seasonal cycles
- Behavioral characteristics specific to Yellowstone thermal ecology
- Temperature requirements for critical life stages in Yellowstone
- Habitat preferences for spawning, nursery, and adult habitats
- Migration patterns within Yellowstone system

**6. Seasonal behavioral patterns and migration timing within Yellowstone's thermal ecology**
- Seasonal distribution patterns in Yellowstone Lake
- Spawning migrations in Yellowstone tributaries
- Feeding behavior shifts across Yellowstone thermal gradients
- Winter behavioral adaptations in Yellowstone cold-water ecology
- Summer thermal refuge seeking behavior

**7. Species-specific thermal tolerances for simulation integration**
- Preferred temperature range in Yellowstone context
- Thermal tolerance limits for Yellowstone survival
- Optimal growth temperature for Yellowstone conditions
- Upper thermal tolerance (lethal thresholds) for Yellowstone
- Lower thermal tolerance (cold tolerance) for Yellowstone

**8. Yellowstone-specific population data from monitoring programs**
- USGS Yellowstone monitoring program data availability
- Wyoming Game and Fish Department data
- Yellowstone National Park monitoring data
- Trend analysis for Yellowstone populations
- Density estimates specific to Yellowstone Lake/Stream segments

**9. Literature citations with direct URLs to primary research sources, USGS data, Yellowstone monitoring reports**
- Primary research papers with full citations and DOI links
- USGS scientific reports specific to Yellowstone
- Yellowstone National Park scientific series publications
- Technical reports from interagency monitoring programs
- Web URLs to raw data, databases, or monitoring portals

**10. Integration recommendations for fish module expansion**
- Required thermal performance curve parameters for simulation
- Behavioral traits to model in Yellowstone context
- Population dynamics parameters for Yellowstone
- Interaction complexity recommendations for Yellowstone ecosystem
- Data gaps and research priorities for Yellowstone integration

## Priority Species Categories

### Salmon Species (Key Anadromous Species)
- Coho salmon (Oncorhynchus kisutch)
- Chinook salmon (Oncorhynchus tshawytscha)
- Sockeye salmon (Oncorhynchus nerka)
- Pink salmon (Oncorhynchus gorbuscha)

### Whitefish Species
- Lake Yellowstone whitefish (Coregonus bergi)
- Mountain whitefish (Coregonus arcuatus)
- Various Coregonid species

### Lake Trout
- Lake trout (Salvelinus namaycush) Yellowstone-specific populations
- Arctic char (Salvelinus alpinus) Yellowstone Lake populations

### Coldwater Minors
- Sculpin species (various)
- Burbot (Lota lota)
- Various minnows and cyprinids

### Game Fish Species
- Various sport fish species with Yellowstone monitoring

## Data Sources and Integration Points

### Primary Research Sources
- USGS Northern Rockies Science Center publications
- Wyoming Game and Fish Department assessments
- Yellowstone National Park scientific monitoring reports
- Interagency cooperation agreements (EPA, USGS, USFS)

### Simulation Integration Points
- THERMAL_SPECIES dictionary expansion
- thermal_performance() function extension
- suitability() function integration
- population modeling parameters
- Species interaction matrices

## Quality Assurance Criteria

1. **Data Completeness**: Minimum 80% of required data fields for each species
2. **Source Reliability**: All citations must be verifiable primary sources
3. ** Yellowstone Specificity**: Data must be relevant to Yellowstone Lake/Stream ecosystem
4. **Simulation Compatibility**: Parameters must be compatible with existing fish module architecture
5. **Cross-validation**: Data should be consistent across multiple sources where available

## Simulation Integration Requirements (binding for all fish research)

Every fish species profile delivered through this guide must include:

### A. Simulation Parameter Mapping
- `THERMAL_SPECIES` entry format (`t_opt_lo_c`, `t_opt_hi_c`, `t_feed_zero_c`, `t_refuge_c`, `t_uilt_c`, `status`, `sources`, `yellowstone_specific`).
- `thermal_performance()` and `suitability()` parameter mapping (`wf`, `wc`, `wt`, `wv`, `wd`, `VELOCITY_OPT_MPS`, `VELOCITY_TOL_MPS`, `DEPTH_REF_M`).
- `update_trout()` / enhanced `update_species()` output fields (`start_point_index`, `end_point_index`, `reach_id`, `reach_temp_c`, `hold_seconds`, `walk_mps`, `lateral_offset_m`, `suitability_U`, `refuge_reason`).

### B. Parameter Provenance and Status (AGENTS.md binding)
- `run_mode`: `illustrative` / `scenario` / `hindcast` / `observed_replay`. `forecast` refused.
- `status`: `illustrative` unless locked-final evaluation window exists. Both seed claims `not_yet_accepted` until then.
- Unknown parameter uncertainty stays `unknown`. No invented distributions or ranges.
- `parameter_provenance`: `contract_version: "0.1.0"`, `world_id: "yellowstone_midway"`, source URLs / DOIs, `code_rev`, `units`.

### C. Validation Criteria
- `pytest` green; `audit_provenance` passes.
- Volume/heat conservation (`1e-9` / `1e-10` ledger format).
- Downstream temperature monotone; substep stability `dt_sub ≤ 0.45/rate`.
- `check_trout_clear_of_pools()` passes; no wildlife through `pool_1034_0` / `pool_1030_0` exclusions.
- Before/after captures; 10-min replay stable.

### D. Equation Structure References
- `FISH_MODULE_EXPANSION.md` sections 1-9 define the exact function signatures, dictionary formats, validation functions (`validate_yearly_fish_data`), and output file structures (`derived/<build-id>/river_state.json`, `plume_map.png`, `refuge_map.png`).
- `01_PYTHON_BUILD_SPEC.md` M01 (hydro_thermal), M06 (fish), M09 (geochemistry guardrail), M11 (publish/validation) define module-level acceptance criteria.

## Next Steps

1. Distribute these research prompts to ichthyology research teams
2. Establish data collection protocols and validation standards
3. Create centralized data repository for collected findings
4. Develop automated integration pipelines for simulation module expansion
5. Establish ongoing monitoring and data update protocols

