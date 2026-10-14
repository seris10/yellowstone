# Salmon Species Research Prompts for Yellowstone Python Simulation

This document contains research prompts for salmon species targeting Yellowstone-specific data for simulation integration.

## 1. Coho Salmon (Oncorhynchus kisutch)

**Research Priority**: High (Key anadromous species with Yellowstone potential)

### Prompt 1.1: Yellowstone Lake Thermal Tolerance and Habitat Requirements
Research coho salmon thermal tolerances specifically in Yellowstone Lake ecosystem contexts. Document:
- Optimal growth temperatures observed in Yellowstone thermal regimes
- Upper thermal tolerance limits for Yellowstone survival
- Temperature-specific habitat suitability within Yellowstone Lake thermal gradient
- Yellowstone-specific thermal refugia locations and characteristics
- Integration parameters for thermal_performance() function mapping

**Required Data Sources**: USGS Pacific Southwest Research Station, Yellowstone Lake thermal monitoring data, interagency thermal ecology studies

**Primary Research Questions**:
- What are the precise thermal limits for coho salmon survival in Yellowstone Lake's temperature range (5-24°C observed)?
- How does Yellowstone Lake's summer thermocline affect coho distribution and behavior?
- What are the temperature-specific feeding rates and growth parameters for Yellowstone integration?

### Prompt 1.2: Yellowstone Anadromous Migration and Spawning Ecology
Document Yellowstone-specific migration timing and spawning requirements:
- Spawning migration timing relative to Yellowstone seasonal temperature cycles
- Yellowstone tributary spawning habitat characteristics (temperature, flow, substrate)
- Incubation temperature requirements for Yellowstone water temperatures
- Fry and juvenile habitat preferences within Yellowstone drainage system
- Yellowstone-specific survival rates through different life stages

**Required Data Sources**: Yellowstone National Park fisheries surveys, USGS Columbia River Fisheries, Wyoming Game and Fish Department salmon programs

**Integration Parameters**:
- Spawning temperature range: [specific°C range for Yellowstone]
- Migration timing: [specific Yellowstone river calendar dates]
- Fry survival rates in Yellowstone Lake/Stream segments
- Temperature-dependent development rates for Yellowstone conditions

### Prompt 1.3: Yellowstone Competition and Ecosystem Interactions
Research Yellowstone-specific interactions with existing species:
- Competitive relationships with existing trout species in Yellowstone
- Diet composition and feeding competition in Yellowstone ecosystem
- Predation pressure on coho in Yellowstone waters
- Yellowstone-specific carrying capacity considerations
- Impact of Yellowstone thermal stratification on coho survival

**Required Data Sources**: Yellowstone Lake food web studies, competitive exclusion research, predator-prey dynamics in Yellowstone ecosystem

## 2. Chinook Salmon (Oncorhynchus tshawytscha)

**Research Priority**: High (Largest anadromous species with Yellowstone significance)

### Prompt 2.1: Yellowstone Thermal Performance Parameters
Document Yellowstone-specific Chinook salmon thermal biology:
- Yellowstone Lake thermal tolerance curves (feeding, growth, survival)
- Temperature-dependent growth rates under Yellowstone summer conditions
- Yellowstone-specific upper thermal lethal temperatures
- Thermoregulation behaviors in Yellowstone Lake thermal layers
- Parameter mapping for thermal_performance() simulation integration

**Data Integration Requirements**:
- t_opt_lo_c: [0°C range for Yellowstone]
- t_opt_hi_c: [optimal range for Yellowstone]
- t_feed_zero_c: [temperature with zero feeding in Yellowstone]
- t_refuge_c: [refuge temperature for Yellowstone Chinook]
- t_uilt_c: [uninsulin-like temperature tolerance for Yellowstone]

### Prompt 2.2: Yellowstone Spawning and Nursery Habitat
Document Yellowstone-specific reproductive requirements:
- Yellowstone tributary spawning timing synchronized with thermal regime
- Substrate requirements for Chinook eggs in Yellowstone river systems
- Flow requirements for successful spawning runs in Yellowstone
- Incubation temperature relationships specific to Yellowstone water quality
- Nursery habitat preferences for fry in Yellowstone Lake

**Monitoring Data Sources**: USGS Chinook salmon monitoring programs, Yellowstone tributary habitat assessments, interagency spawning studies

## 3. Sockeye Salmon (Oncorhynchus nerka)

**Research Priority**: Medium (Lake-specific salmon with Yellowstone potential)

### Prompt 3.1: Yellowstone Lake Adaptation and Limitations
Research sockeye salmon adaptation to Yellowstone Lake conditions:
- Physiological tolerance for Yellowstone's temperature fluctuations
- Feeding ecology and growth in Yellowstone Lake environment
- Yellowstone-specific reproductive barriers or advantages
- Competition with existing Yellowstone whitefish species
- Yellowstone Lake food web integration potential

### Prompt 3.2: Yellowstone Sport Fishing and Population Data
Document Yellowstone-specific sockeye populations:
- Current sockeye abundance in Yellowstone Lake (USGS monitoring)
- Historical sockeye populations and Yellowstone restoration efforts
- Sport fishing data and angler harvest statistics in Yellowstone
- Population trends and Yellowstone-specific management actions

## 4. Pink Salmon (Oncorhynchus gorbuscha)

**Research Priority**: Low-Medium (Lesser Yellowstone significance but included for completeness)

### Prompt 4.1: Yellowstone Climate Change Vulnerability
Document Yellowstone-specific pink salmon responses:
- Thermal vulnerability in Yellowstone warming scenarios
- Competition with established Yellowstone species
- Yellowstone ecosystem disruption potential
- Yellowstone adaptive management requirements

### Prompt 4.2: Research Gap Identification
Identify data gaps for Yellowstone pink salmon integration:
- Lack of Yellowstone-specific thermal performance data
- Limited Yellowstone population monitoring
- Minimal Yellowstone sport fishing interest
- Competition concerns in Yellowstone ecosystem

## Integration Framework for All Salmon Species

### Required Simulation Parameters
Each salmon species research must deliver:

1. **THERMAL_SPECIES Dictionary Entry**:
```python
"species_name": {
    "t_opt_lo_c": [low optimal temp for Yellowstone],
    "t_opt_hi_c": [high optimal temp for Yellowstone], 
    "t_feed_zero_c": [temperature with zero feeding],
    "t_refuge_c": [refuge temperature],
    "t_uilt_c": [UILT temperature tolerance],
    "status": "yellowstone_literature_transferred",
    "sources": [ Yellowstone-specific research citations ]
}
```

2. **Competition Matrix Data**:
- Competitive hierarchy with Yellowstone trout species
- Diet overlap percentages in Yellowstone ecosystem
- Resource partitioning analysis for Yellowstone integration

3. **Population Dynamics Parameters**:
- Yellowstone carrying capacity estimates
- Growth rate curves specific to Yellowstone thermal regime
- Reproductive success rates under Yellowstone conditions

4. **Habitat Suitability Models**:
- Yellowstone Lake thermal layer preferences
- Yellowstone tributary habitat suitability indices
- Seasonal distribution patterns in Yellowstone

### Yellowstone-Specific Research Validation
All salmon research must:

1. **Cross-reference Yellowstone monitoring data** (USGS, WY G&F, NPS)
2. **Validate against Yellowstone temperature records** (5-24°C range)
3. **Consider Yellowstone ecosystem impacts** (invasive species concerns)
4. **Align with Yellowstone management objectives** (ecosystem health, biodiversity)
5. **Account for Yellowstone climate change trajectories** (warming scenarios)

### Data Quality Standards

1. **Minimum Acceptable Data**: 70% of required parameters with Yellowstone specificity
2. **High-Quality Data**: 90%+ of parameters with Yellowstone monitoring validation
3. **Priority Species**: Salmon with Yellowstone existing or potential populations
4. **Research Gap Documentation**: Clearly identify missing Yellowstone-specific data

### Integration Timeline

**Phase 1**: Complete salmon species thermal performance data collection (12 months)
**Phase 2**: Competition and ecosystem interaction studies (6-12 months)
**Phase 3**: Population dynamics modeling for Yellowstone integration (6 months)
**Phase 4**: Simulation module expansion and testing (3-6 months)

