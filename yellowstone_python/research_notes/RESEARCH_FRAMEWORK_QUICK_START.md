# Yellowstone Python Fish Species Research - Quick Start Guide

## Overview
This guide provides a quick reference for starting the comprehensive 100+ species fish species audit for the Yellowstone Python simulation.

## Project Structure

### Core Research Categories
1. **Salmon Species** (4 species) - Key Yellowstone anadromous species
2. **Whitefish Species** (2 species) - Critical Yellowstone ecosystem components
3. **Lake Trout & Char** (2 species) - Yellowstone top predators and specialists
4. **Sculpin & Burbot** (2 species) - Yellowstone cold-water ecosystem components
5. **Minnow & Cyprinid** (2 categories) - Yellowstone forage base specialists
6. **Game Fish Species** (6 species) - Yellowstone recreational and management focus

### Data Requirements per Species
Each species research must deliver 10 key areas of Yellowstone-specific data:

**Core Simulation Parameters**:
- Thermal performance curves (t_opt_lo_c, t_opt_hi_c, t_feed_zero_c, t_refuge_c, t_uilt_c)
- Competition and interaction data
- Population dynamics parameters
- Habitat suitability indices

**Yellowstone-Specific Integration**:
- Thermal regime compatibility (5-24°C Yellowstone range)
- Seasonal behavior adaptation
- Ecosystem role validation
- Management implications assessment

## Getting Started

### Step 1: Choose Species Category
Start with **Priority Species** that have Yellowstone-specific data:

**Critical Priority (Begin First)**:
- Lake Yellowstone Whitefish (Coregonus bergi)
- Westslope Cutthroat Trout (Oncorhynchus clarki)
- Lake Trout (Salvelinus namaycush) Yellowstone
- Arctic Char (Salvelinus alpinus) Yellowstone

**High Priority**:
- Mountain Whitefish (Coregonus arcuatus)
- Various Minnow Species
- Various Cyprinid Species

### Step 2: Use Research Templates
Each category has a detailed research prompt template:

**Available Templates**:
- `SALMON_SPECIES_PROMPTS.md` - Salmon species research
- `WHITEFISH_SPECIES_PROMPTS.md` - Whitefish species research
- `LAKE_TROUT_CHAR_PROMPTS.md` - Lake trout and char research
- `SCULPIN_BURBOT_PROMPTS.md` - Sculpin and burbot research
- `MINNOW_CYPRINID_PROMPTS.md` - Minnow and cyprinid research
- `GAME_FISH_SPECIES_PROMPTS.md` - Game fish species research

### Step 3: Follow Research Format
Each template provides:

**Research Prompt Structure**:
```
SPECIES: [Species Name] ([Scientific Name])
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

... (continues through all 10 required areas)
```

### Step 4: Data Sources
Yellowstone-specific data sources include:

**Primary Research Sources**:
- USGS Northern Rockies Science Center publications
- Wyoming Game and Fish Department assessments
- Yellowstone National Park scientific monitoring reports
- Interagency cooperation agreements (EPA, USGS, USFS)

**Monitoring Programs**:
- USGS Yellowstone Lake fisheries surveys
- Wyoming Game and Fish Department whitefish assessments
- Yellowstone National Park long-term monitoring data
- Interagency Yellowstone ecosystem monitoring

### Step 5: Integration Process
After collecting research data, follow this integration sequence:

**Phase 1: Data Collection (0-6 months)**
1. Complete priority species research using templates
2. Validate Yellowstone data quality and specificity
3. Document research sources and Yellowstone monitoring programs
4. Identify and prioritize research gaps

**Phase 2: Simulation Integration (6-12 months)**
1. Expand THERMAL_SPECIES dictionary with new species
2. Enhance thermal_performance() and suitability() functions
3. Implement Yellowstone-specific competition models
4. Update population dynamics with species-specific behaviors

**Phase 3: Testing and Validation (12-18 months)**
1. Test Yellowstone simulation integration
2. Validate ecological realism of new species
3. Establish Yellowstone data quality standards
4. Create Yellowstone monitoring protocols

## Research Priority Matrix

### IMMEDIATE (Start Now)
**Lake Yellowstone Whitefish (Coregonus bergi)**
- Critical Yellowstone endemic species
- Keystone ecosystem component
- High ecological importance
- Available monitoring data

**Westslope Cutthroat Trout (Oncorhynchus clarki)**
- Critical Yellowstone native species
- Conservation priority
- Sport fishing value
- Available monitoring data

**Lake Trout (Salvelinus namaycush) Yellowstone**
- Critical Yellowstone top predator
- Ecosystem management implications
- Competition with native species
- Management program impact

### MEDIUM PRIORITY (Next 6 months)
- Mountain Whitefish (Coregonus arcuatus)
- Various Minnow Species
- Various Cyprinid Species
- Various Sculpin Species

### LOWER PRIORITY (Extended timeline)
- Various Salmon Species
- Burbot (Lota lota)
- Game Fish Species (Northern Pike, Lake Whitefish, etc.)
- Additional specialized species

## Quality Standards

### Data Completeness Requirements
- **High-Quality Research**: 90%+ of required Yellowstone-specific parameters
- **Standard Research**: 70%+ of required Yellowstone-specific parameters
- **Minimum Research**: 50%+ of core Yellowstone-specific parameters (with gap identification)

### Yellowstone Specificity Requirements
- **Yellowstone Data**: Minimum 80% of data must be Yellowstone-specific
- **Monitoring Validation**: Data must reference Yellowstone monitoring sources
- **Thermal Compatibility**: All parameters must work within Yellowstone 5-24°C range
- **Ecosystem Relevance**: All research must Yellowstone ecosystem-specific

## Quick Start Checklist

### Month 1: Foundation Setup
- [ ] Review RESEARCH_PROMPTS_GUIDE.md for complete framework
- [ ] Select priority species based on Yellowstone data availability
- [ ] Set up research coordination and data collection templates
- [ ] Establish Yellowstone data source directories

### Month 2: Priority Species Research
- [ ] Complete Lake Yellowstone Whitefish research
- [ ] Document Yellowstone population data and trends
- [ ] Validate Yellowstone thermal performance parameters
- [ ] Create Yellowstone integration specifications

### Month 3: Second Priority Species
- [ ] Complete Westslope Cutthroat Trout research
- [ ] Document Yellowstone conservation status and management
- [ ] Establish Yellowstone competition models
- [ ] Begin Yellowstone simulation integration development

### On-going: Quality Assurance
- [ ] Validate all Yellowstone data against monitoring sources
- [ ] Maintain research gap documentation
- [ ] Update Yellowstone integration specifications
- [ ] Establish Yellowstone ongoing monitoring protocols

## Resources and Tools

### Key Documents
- `RESEARCH_PROMPTS_GUIDE.md` - Complete research framework
- `FISH_SPECIES_AUDIT_SUMMARY.md` - Comprehensive audit summary
- `FISH_MODULE_EXPANSION.md` - Technical integration guide
- `SALMON_SPECIES_PROMPTS.md` - Salmon species research templates

### Research Support
- USGS Yellowstone Lake Fisheries Research
- Wyoming Game and Fish Department Yellowstone Programs
- Yellowstone National Park Scientific Monitoring
- Interagency Yellowstone Ecosystem Studies

### Technical Support
- Yellowstone Python Module Team
- Yellowstone Simulation Integration Group
- Yellowstone Ecosystem Research Center

## Next Steps

1. **Begin Priority Species Research**: Start with Lake Yellowstone Whitefish and Westslope Cutthroat Trout
2. **Establish Research Coordination**: Set up Yellowstone data collection and validation protocols
3. **Begin Integration Development**: Start expanding fish module with priority species
4. **Create Monitoring Framework**: Establish Yellowstone ongoing data collection and validation

This quick start guide provides the essential framework for beginning the comprehensive Yellowstone Python fish species audit. The structured approach ensures systematic research data collection with Yellowstone-specific focus and simulation integration capabilities.

For detailed research methodologies and technical integration specifications, refer to the comprehensive documentation files provided in this directory.

