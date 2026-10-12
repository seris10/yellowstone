# Whitefish Species Research Prompts for Yellowstone Python Simulation

This document contains comprehensive research prompts for whitefish species critical to Yellowstone Lake ecosystem integration.

## 1. Lake Yellowstone Whitefish (Coregonus bergi)

**Research Priority**: Critical (Endemic species, keystone Yellowstone ecosystem component)

### Prompt 1.1: Yellowstone Lake Thermal Ecology and Distribution
Document Yellowstone Lake-specific thermal requirements:
- Vertical distribution patterns within Yellowstone Lake thermocline structure
- Temperature-specific habitat zones in Yellowstone Lake (epilimnion, metalimnion, hypolimnion)
- Yellowstone-specific thermal tolerances across seasonal temperature variations
- Thermal refugia utilization during Yellowstone summer stratification
- Parameter mapping for Yellowstone Lake thermal layers in simulation

**Yellowstone Lake Thermal Data Required**:
- Summer epilimnion temperatures: [typical Yellowstone range]
- Winter hypolimnion temperatures: [typical Yellowstone range] 
- Metalimnion temperature gradient rates: [Yellowstone-specific]
- Thermal overturning timing: [Yellowstone seasonal patterns]

### Prompt 1.2: Yellowstone Population Dynamics and Monitoring
Research Yellowstone population status and trends:
- Current Yellowstone Lake whitefish abundance (USGS/GWY monitoring data)
- Historical population trends in Yellowstone Lake ecosystem
- Age structure and growth patterns specific to Yellowstone conditions
- Reproductive success rates under Yellowstone thermal regime
- Yellowstone carrying capacity estimates for whitefish populations

**Monitoring Programs**:
- USGS Yellowstone Lake fisheries surveys
- Wyoming Game and Fish Department whitefish assessments
- Yellowstone National Park long-term monitoring data
- Interagency whitefish population modeling efforts

### Prompt 1.3: Yellowstone Food Web Integration
Document Yellowstone ecosystem interactions:
- Diet composition and feeding ecology in Yellowstone Lake context
- Predation pressure from Yellowstone introduced species
- Competition with Yellowstone trout species for resources
- Yellowstone-specific trophic relationships and energy flow
- Seasonal diet shifts in Yellowstone seasonal thermal regime

### Prompt 1.4: Yellowstone Reproduction and Life History
Document Yellowstone-specific reproductive biology:
- Spawning timing relative to Yellowstone spring temperature patterns
- Yellowstone tributary spawning habitat requirements (if applicable)
- Egg and fry survival under Yellowstone thermal conditions
- Yellowstone-specific age at maturity and growth rates
- Reproductive investment strategies in Yellowstone environment

## 2. Mountain Whitefish (Coregonus arcuatus)

**Research Priority**: High (Important Yellowstone tributary species)

### Prompt 2.1: Yellowstone River Habitat Requirements
Document Yellowstone river system adaptations:
- Yellowstone stream temperature preferences across river systems
- Substrate requirements for Yellowstone river whitefish spawning
- Yellowstone river flow regime tolerances (seasonal variations)
- Yellowstone river thermal refugia characteristics
- Yellowstone river ecosystem integration patterns

### Prompt 2.2: Yellowstone Competition with Trout Species
Research Yellowstone competitive interactions:
- Competitive relationships with Yellowstone brown trout and rainbow trout
- Resource partitioning in Yellowstone river habitats
- Yellowstons-specific competitive hierarchies
- Impact of Yellowstone trout populations on whitefish distribution
- Yellowstone ecosystem management implications

## 3. Other Coregonid Species

**Research Priority**: Medium (Include other whitefish variants)

### Prompt 3.1: Various Coregonid Species Analysis
For each additional Coregonid species in Yellowstone:
- Species identification and Yellowstone distribution
- Yellowstone-specific ecological requirements
- Competition dynamics with established Yellowstone species
- Yellowstone population status and trends
- Yellowstone integration potential and management considerations

## Whitefish Thermal Performance Integration Framework

### THERMAL_SPECIES Dictionary Requirements
For each whitefish species, research must deliver:

```python
"species_name": {
    "t_opt_lo_c": [0°C range for Yellowstone],
    "t_opt_hi_c": [optimal range for Yellowstone],
    "t_feed_zero_c": [temperature with zero feeding in Yellowstone],
    "t_refuge_c": [refuge temperature for Yellowstone conditions],
    "t_uilt_c": [UILT tolerance for Yellowstone ecosystem],
    "status": "yellowstone_endemic_transferred",
    "sources": [Yellowstone Lake/wh fisheries research citations]
}
```

### Yellowstone-Specific Parameter Requirements

1. **Lake Whitefish (Coregonus bergi)**:
   - Optimize for Yellowstone Lake's seasonal thermal stratification
   - Consider Yellowstone summer metalimnion feeding constraints
   - Account for Yellowstone winter hypolimnion survival adaptations
   - Integrate Yellowstone spring turnover dynamics

2. **Mountain Whitefish (Coregonus arcuatus)**:
   - Focus on Yellowstone river thermal variability
   - Consider Yellowstone seasonal flow temperature relationships
   - Account for Yellowstone tributary habitat characteristics
   - Integrate Yellowstone river ecosystem interactions

### Yellowstone Monitoring Integration Requirements

1. **USGS Yellowstone Lake Surveys**:
   - Annual abundance estimates for whitefish populations
   - Age structure and growth rate data
   - Reproductive success measurements
   - Environmental correlation studies

2. **Wyoming Game and Fish Department**:
   - Whitefish population assessments
   - Harvest and angler survey data (where applicable)
   - Habitat quality indices
   - Population trend analyses

3. **Yellowstone National Park**:
   - Long-term ecological research (LTER) data integration
   - Habitat monitoring programs
   - Species interaction studies
   - Climate change impact assessments

### Data Quality Standards for Whitefish Research

1. **Endemic Species Priority**: Lake Yellowstone whitefish requires highest quality data
2. **Ecological Significance**: Species importance to Yellowstone ecosystem health
3. **Simulation Compatibility**: Parameters must integrate with existing Yellowstone trout thermal models
4. **Cross-Validation**: Multiple monitoring sources for Yellowstone population data
5. **Seasonal Coverage**: Data must cover Yellowstone's full seasonal temperature range

### Whitefish Integration Timeline

**Phase 1**: Lake Yellowstone whitefish thermal performance data collection (6-8 months)
**Phase 2**: Mountain whitefish river habitat studies (4-6 months)
**Phase 3**: Competition and food web integration (3-4 months)
**Phase 4**: Simulation testing with existing trout species (2-3 months)

### Research Gap Identification

Whitefish research must identify:
1. **Missing Yellowstone monitoring data** for population trends
2. **Unknown thermal tolerance limits** for Yellowstone conditions
3. **Unquantified competition** with established Yellowstone trout
4. **Limited Yellowstone-specific behavioral studies**
5. **Data gaps in Yellowstone reproductive biology**

### Management Implications for Yellowstone

Whitefish integration requires consideration of:
1. **Invasive species concerns** (relative to existing trout)
2. **Ecosystem balance** in Yellowstone Lake/wh waters
3. **Recreational fishery value** in Yellowstone
4. **Scientific research value** for Yellowstone ecosystem studies
5. **Climate change resilience** of Yellowstone whitefish populations

