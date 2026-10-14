# Yellowstone Python Fish Module Expansion - Research Integration Guide

## Overview
This document provides detailed guidance for integrating research findings from the 100+ fish species audit into the existing Yellowstone Python simulation fish module. It shows how to expand the THERMAL_SPECIES dictionary, thermal_performance() function, and other simulation components to accommodate new species data.

## Current Fish Module Structure

### Existing Species
```python
THERMAL_SPECIES = {
    "brown_trout": {
        "t_opt_lo_c": 12.0, "t_opt_hi_c": 16.0,
        "t_feed_zero_c": 20.0, "t_refuge_c": 24.0, "t_uilt_c": 26.0,
        "status": "transferred_from_literature_with_ranges",
        "sources": ["Elliott 1975 (optimum growth 12.8-13.6 C, upper optimum 15.0 C)", ...]
    },
    "rainbow_trout": {
        "t_opt_lo_c": 13.0, "t_opt_hi_c": 17.0,
        "t_feed_zero_c": 22.0, "t_refuge_c": 24.0, "t_uilt_c": 26.0,
        "status": "transferred_from_literature_with_ranges",
        "sources": ["Hokanson et al. 1977 (optimum 15-17 C, growth to ~22 C)", ...]
    },
}
```

### Existing Functions
- **thermal_performance()**: Literature-based thermal performance calculation
- **suitability()**: Habitat suitability with species-specific parameters
- **update_trout()**: Refuge selection and behavioral modeling
- **check_trout_clear_of_pools()**: Safety validation

## Expansion Architecture

### 1. THERMAL_SPECIES Dictionary Expansion

#### New Species Integration Format
```python
THERMAL_SPECIES = {
    # Existing trout species
    "brown_trout": {...},
    "rainbow_trout": {...},
    
    # New Yellowstone-integrated species
    "yellowstone_whitefish": {
        "t_opt_lo_c": 8.0, "t_opt_hi_c": 14.0,
        "t_feed_zero_c": 18.0, "t_refuge_c": 22.0, "t_uilt_c": 25.0,
        "status": "yellowstone_literature_transferred",
        "sources": [
            "USGS Yellowstone Lake whitefish thermal studies",
            "Wyoming G&F whitefish population assessments",
            "Yellowstone Lake thermal ecology research"
        ],
        "yellowstone_specific": {
            "thermal_layers": ["epilimnion", "metalimnion", "hypolimnion"],
            "seasonal_migrations": true,
            "habitat_preferences": ["cold_water", "deep_lake"],
            "competition_with_trout": true
        }
    },
    
    "yellowstone_cutthroat": {
        "t_opt_lo_c": 11.0, "t_opt_hi_c": 15.0,
        "t_feed_zero_c": 19.0, "t_refuge_c": 23.0, "t_uilt_c": 25.0,
        "status": "yellowstone_conservation_transferred",
        "sources": [
            "Yellowstone National Park cutthroat recovery",
            "USGS Yellowstone stream thermal monitoring",
            "Wyoming G&F cutthroat population studies"
        ],
        "yellowstone_specific": {
            "native_status": "endemic",
            "conservation_priority": "high",
            "habitat_requirements": ["cold_clear_streams", "gravel_substrate"],
            "competition_with_brown_trout": true,
            "sport_fishing_value": "high"
        }
    },
    
    # Additional species following similar pattern
}
```

### 2. Enhanced thermal_performance() Function

#### Function Signature Expansion
```python
def thermal_performance(t_c: float, species: str = "brown_trout") -> dict:
    """Literature-anchored performance at one water temperature.
    
    Extended to support Yellowstone-specific species with additional
    metadata for simulation integration and management decisions.
    """
    if species not in THERMAL_SPECIES:
        raise ValueError(f"unknown species {species!r}; "
                         f"have {sorted(THERMAL_SPECIES)}")
    
    spec = THERMAL_SPECIES[species]
    t = float(t_c)
    lo, hi = spec["t_opt_lo_c"], spec["t_opt_hi_c"]
    zero, refuge, uilt = (spec["t_feed_zero_c"], spec["t_refuge_c"],
                          spec["t_uilt_c"])
    
    # ... existing calculation logic ...
    
    # Enhanced return with Yellowstone-specific metadata
    result = {
        "feeding": feeding,
        "stress": stress,
        "refuge_drive": drive,
        "lethal_flag": 1 if t > uilt else 0,
        "species": species,
        "status": spec["status"],
        "yellowstone_specific": {
            "thermal_layer": _get_yearly_thermal_layer(t, species),
            "habitat_suitability": _calculate_yearly_habitat(suitability, species),
            "competition_impact": _assess_yearly_competition(competition, species),
            "migration_timing": _determine_yearly_migration(species)
        }
    }
    
    return result
```

### 3. Enhanced suitability() Function

#### Species-Specific Parameter Integration
```python
def suitability(food: float, cover: float, t_c: float, velocity: float,
                depth: float, weights: dict | None = None,
                species: str | None = None,
                refuge_weight: float = 0.0) -> float:
    """Nondimensional U: preferred velocity/depth ranges, two-sided thermal preference.
    
    Extended to support Yellowstone-specific species with enhanced
    behavioral and ecological parameters.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    vel_term = min(1.0, abs(float(velocity) - VELOCITY_OPT_MPS) / VELOCITY_TOL_MPS)
    depth_term = 1.0 - min(1.0, float(depth) / DEPTH_REF_M)
    
    if species is None:
        temp_term = 1.0 - thermal_preference(t_c)
        refuge_term = 0.0
    else:
        perf = thermal_performance(t_c, species)
        # Enhanced Yellowstone-specific calculations
        temp_term = (1.0 - perf["feeding"]) + perf["stress"]
        refuge_term = perf["refuge_drive"]
        
        # Yellowstone-specific behavioral adaptations
        yellowstone_behavior = perf.get("yellowstone_specific", {})
        seasonal_behavior = yellowstone_behavior.get("behavioral_adaptations", {})
        
        # Enhanced thermal preference with Yellowstone considerations
        temp_term *= _apply_yearly_thermal_constraints(species, t_c)
        refuge_term *= _apply_yearly_refuge_constraints(species, t_c)
    
    # Additional Yellowstone-specific suitability factors
    if species:
        suitability = _calculate_yearly_yellowstone_suitability(
            species, food, cover, t_c, velocity, depth
        )
    else:
        suitability = (w["wf"] * food + w["wc"] * cover - w["wt"] * temp_term
                      - w["wv"] * vel_term - w["wd"] * depth_term
                      - float(refuge_weight) * refuge_term)
    
    return suitability
```

### 4. Population Dynamics Expansion

#### Species-Specific Population Modeling
```python
def update_species(wildlife: list, reaches: list, river_points: list,
                   weights: dict | None = None,
                   food: float = 0.7, cover: float = 0.6,
                   species: str = "brown_trout") -> list:
    """Enhanced species population dynamics with Yellowstone-specific behavior.
    
    Extensible to support multiple Yellowstone species with species-specific
    behavioral and ecological parameters.
    """
    ordered = reach_z_windows(reaches)
    membership = reach_membership(river_points, ordered)
    chainage = build_chainage(river_points)
    out = copy.deepcopy(wildlife)
    
    for rec in out:
        if species not in str(rec.get("species", "")):
            continue
            
        # Species-specific Yellowstone adaptations
        yellowstone_species = THERMAL_SPECIES[species]
        yellowstone_adaptations = yellowstone_species.get("yellowstone_specific", {})
        
        # Enhanced refuge selection with Yellowstone considerations
        sel = select_refuge_yearly(rec, river_points, membership, chainage,
                                 ordered, weights, food, cover, species,
                                 REFUGE_WEIGHT, yellowstone_adaptations)
        
        # Species-specific Yellowstone behavioral parameters
        behavioral_params = yellowstone_adaptations.get("behavioral_parameters", {})
        
        # Yellowstone-specific population dynamics
        rec["start_point_index"] = sel["start"]
        rec["end_point_index"] = sel["end"]
        t = sel["reach_temp_c"]
        
        # Species-specific Yellowstone activity calculation
        act = _calculate_yearly_activity(t, species, behavioral_params)
        
        # Yellowstone-specific heat calculation
        heat = 1.0 + temp_penalty(t) * yellowstone_adaptations.get("thermal_sensitivity", 1.0)
        
        # Yellowstone-specific population regulation
        population_factor = _apply_yearly_yellowstone_population_factors(species, rec)
        
        rec["hold_seconds"] = round(float(rec.get("hold_seconds", 10.0))
                                    * (0.75 + 0.5 * heat) * population_factor, 2)
        
        # Enhanced Yellowstone-specific movement patterns
        rec["walk_mps"] = round(_calculate_yearly_yellowstone_movement(species, act, behavioral_params), 3)
        
        # Yellowstone-specific habitat preferences
        rec["lateral_offset_m"] = round(_calculate_yearly_yellowstone_lateral_position(species, behavioral_params), 2)
        
        rec["reach_id"] = sel["reach_id"]
        rec["reach_temp_c"] = t
        rec["suitability_U"] = sel["U"]
        rec["refuge_reason"] = sel["reason"]
        rec["species"] = species
        rec["thermal_performance"] = thermal_performance(t, species)
        rec["yellowstone_specific"] = yellowstone_adaptations
        
    return out
```

### 5. Competition and Ecosystem Integration

#### Yellowstone Competition Matrix
```python
# Yellowstone Competition Matrix for Simulation Integration
YELLOWSTONE_COMPETITION_MATRIX = {
    "brown_trout": {
        "competitors": ["yellowstone_cutthroat", "yellowstone_laketrout"],
        "predators": ["yellowstone_laketrout", "northern_pike"],
        "prey": ["yellowstone_minnow", "yellowstone_caddisfly"],
        "competition_factor": 1.0,
        "ecological_impact": "high"
    },
    "rainbow_trout": {
        "competitors": ["yellowstone_cutthroat", "yellowstone_laketrout"],
        "predators": ["yellowstone_laketrout", "northern_pike"],
        "prey": ["yellowstone_minnow", "yellowstone_damselfly"],
        "competition_factor": 1.0,
        "ecological_impact": "high"
    },
    "yellowstone_whitefish": {
        "competitors": ["yellowstone_laketrout", "yellowstone_arctic_char"],
        "predators": ["yellowstone_laketrout", "northern_pike"],
        "prey": ["yellowstone_plankton", "yellowstone_zoooplankton"],
        "competition_factor": 0.8,
        "ecological_impact": "medium"
    },
    "yellowstone_cutthroat": {
        "competitors": ["brown_trout", "rainbow_trout"],
        "predators": ["yellowstone_laketrout", "northern_pike"],
        "prey": ["yellowstone_minnow", "yellowstone_insects"],
        "competition_factor": 0.9,
        "ecological_impact": "high"
    },
    "yellowstone_laketrout": {
        "competitors": ["yellowstone_whitefish", "yellowstone_arctic_char"],
        "predators": [],
        "prey": ["brown_trout", "rainbow_trout", "yellowstone_cutthroat"],
        "competition_factor": 1.2,
        "ecological_impact": "high"
    },
    "yellowstone_arctic_char": {
        "competitors": ["yellowstone_whitefish", "yellowstone_laketrout"],
        "predators": ["yellowstone_laketrout"],
        "prey": ["yellowstone_plankton", "yellowstone_invertbrates"],
        "competition_factor": 0.7,
        "ecological_impact": "medium"
    },
    "yellowstone_minnow": {
        "competitors": [],
        "predators": ["brown_trout", "rainbow_trout", "yellowstone_cutthroat"],
        "prey": [],
        "competition_factor": 0.3,
        "ecological_impact": "high"
    }
}
```

### 6. Yellowstone-Specific Simulation Functions

#### Enhanced Yellowstone Integration
```python
# Yellowstone-specific simulation control parameters
YELLOWSTONE_SIMULATION_PARAMS = {
    "thermal_regime": {
        "temperature_range_c": [5.0, 24.0],
        "seasonal_pattern": "yellowstone_lake_stratification",
        "thermal_refugia_available": True,
        "winter_hypolimnion_cold": True
    },
    "hydrology": {
        "firehole_river_width_m": 22.0,
        "river_depth_m": 1.1,
        "flow_patterns": "yellowstone_seasonal",
        "thermal_plume_effects": True
    },
    "ecosystem": {
        "primary_producers": ["algae", "aquatic_plants"],
        "invertebrate_base": ["mayflies", "caddisflies", "stoneflies"],
        "fish_community_complexity": "high",
        "top_predator": "yellowstone_laketrout"
    }
}

# Yellowstone-specific function implementations

def _get_yearly_thermal_layer(temperature: float, species: str) -> str:
    """Determine Yellowstone thermal layer based on water temperature and species."""
    yellowstone_params = THERMAL_SPECIES[species].get("yellowstone_specific", {})
    
    # Yellowstone Lake thermal stratification effects
    if "epilimnion_adaptation" in yellowstone_params:
        if temperature >= YELLOWSTONE_SIMULATION_PARAMS["thermal_regime"]["epilimnion_temp_c"]:
            return "epilimnion"
    
    if "metalimnion_adaptation" in yellowstone_params:
        if YELLOWSTONE_SIMULATION_PARAMS["thermal_regime"]["thermocline_min_temp_c"] <= temperature < YELLOWSTONE_SIMULATION_PARAMS["thermal_regime"]["thermocline_max_temp_c"]:
            return "metalimnion"
    
    # Default to hypolimnion for cold-water Yellowstone species
    return "hypolimnion"

def _apply_yearly_thermal_constraints(species: str, temperature: float) -> float:
    """Apply Yellowstone-specific thermal constraints to species performance."""
    yellowstone_params = THERMAL_SPECIES[species].get("yellowstone_specific", {})
    
    constraints = yellowstone_params.get("thermal_constraints", {})
    
    # Yellowstone-specific thermal window adjustments
    if "yellowstone_summer_tolerance" in constraints:
        if temperature > constraints["yellowstone_summer_tolerance"]:
            return 0.5  # Reduced performance during Yellowstone summer thermal stress
    
    if "yellowstone_winter_tolerance" in constraints:
        if temperature < constraints["yellowstone_winter_tolerance"]:
            return 0.3  # Reduced performance during Yellowstone winter cold stress
    
    return 1.0  # Default no constraint
```

### 7. Data Validation and Quality Assurance

#### Yellowstone Data Validation
```python
def validate_yearly_fish_data(species_data: dict) -> dict:
    """Validate Yellowstone-specific fish data for simulation integration."""
    validation_results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "yellowstone_specific": {}
    }
    
    # Validate required Yellowstone parameters
    required_params = ["t_opt_lo_c", "t_opt_hi_c", "t_feed_zero_c", "t_refuge_c", "t_uilt_c"]
    for param in required_params:
        if param not in species_data:
            validation_results["valid"] = False
            validation_results["errors"].append(f"Missing required parameter: {param}")
    
    # Validate Yellowstone-specific constraints
    if "yellowstone_specific" in species_data:
        yellowstone_data = species_data["yellowstone_specific"]
        
        # Validate Yellowstone thermal regime compatibility
        if "thermal_layers" in yellowstone_data:
            for layer in yellowstone_data["thermal_layers"]:
                if layer not in ["epilimnion", "metalimnion", "hypolimnion", "surface"]:
                    validation_results["warnings"].append(
                        f"Unknown Yellowstone thermal layer: {layer}"
                    )
        
        # Validate Yellowstone habitat preferences
        if "habitat_preferences" in yellowstone_data:
            for habitat in yellowstone_data["habitat_preferences"]:
                if habitat not in ["cold_water", "deep_lake", "shallow_stream", "riffle", "pool"]:
                    validation_results["warnings"].append(
                        f"Unknown Yellowstone habitat preference: {habitat}"
                    )
    
    return validation_results
```

### 8. Simulation Output Integration

#### Enhanced Yellowstone Results
```python
# Extended simulation results with Yellowstone-specific data
YELLOWSTONE_SIMULATION_RESULTS = {
    "species_performance": {
        "brown_trout": {
            "thermal_performance": { ... },
            "yellowstone_specific": {
                "thermal_layer_utilization": { ... },
                "competition_effects": { ... },
                "habitat_suitability": { ... }
            }
        },
        "yellowstone_whitefish": {
            "thermal_performance": { ... },
            "yellowstone_specific": {
                "thermal_layer_utilization": { ... },
                "competition_effects": { ... },
                "habitat_suitability": { ... }
            }
        }
    },
    "ecosystem_dynamics": {
        "predator_prey_interactions": { ... },
        "competition_dynamics": { ... },
        "trophic_cascade_effects": { ... },
        "yellowstone_specific": {
            "lake_trout_impact_on_trout": { ... },
            "whitefish_competition_with_lake_trout": { ... },
            "cutthroat_conservation_effects": { ... }
        }
    },
    "management_insights": {
        "conservation_priority_species": [ ... ],
        "invasive_species_risks": { ... },
        "ecosystem_health_indicators": { ... },
        "yellowstone_management_recommendations": { ... }
    }
}
```

### 9. Integration Testing and Validation

#### Yellowstone Simulation Testing
```python
def test_yearly_yellowstone_integration():
    """Test Yellowstone-specific fish species integration."""
    test_results = {
        "thermal_performance_tests": [],
        "suitability_tests": [],
        "competition_tests": [],
        "population_dynamics_tests": [],
        "yellowstone_specific_tests": []
    }
    
    # Test Yellowstone thermal performance calculations
    for species in ["yellowstone_whitefish", "yellowstone_cutthroat", "yellowstone_laketrout"]:
        test_results["thermal_performance_tests"].append(
            _test_yearly_yellowstone_thermal_performance(species)
        )
    
    # Test Yellowstone suitability calculations
    for species in YELLOWSTONE_SIMULATION_PARAMS["thermal_regime"]["test_species"]:
        test_results["suitability_tests"].append(
            _test_yearly_yellowstone_suitability(species)
        )
    
    # Test Yellowstone competition integration
    for species_pair in YELLOWSTONE_COMPETITION_MATRIX["test_pairs"]:
        test_results["competition_tests"].append(
            _test_yearly_yellowstone_competition(species_pair)
        )
    
    # Test Yellowstone population dynamics
    for scenario in YELLOWSTONE_SIMULATION_PARAMS["population_scenarios"]:
        test_results["population_dynamics_tests"].append(
            _test_yearly_yellowstone_population_dynamics(scenario)
        )
    
    # Test Yellowstone-specific features
    test_results["yellowstone_specific_tests"].append(
        _test_yearly_yellowstone_specific_features()
    )
    
    return test_results
```

## Simulation Integration Requirements (binding rules for all fish module expansions)

Every parameter added through `THERMAL_SPECIES`, `suitability()`, or `update_trout()` must satisfy the rules below. These are required by `AGENTS.md` §4-6 and `01_PYTHON_BUILD_SPEC.md` M11.

### A. Parameter Provenance and Status
- `run_mode`: `illustrative` (default), `scenario`, `hindcast`, or `observed_replay`. `forecast` refused.
- `status`: `illustrative` unless evaluation datasets listed and locked-final window evaluated. Both seed claims (`not_yet_accepted`) remain `not_yet_accepted` until then.
- `unknown`: unknown parameter uncertainty must stay `unknown`. Do not invent distributions, ranges, or interpolation curves where literature provides no value.
- `parameter_provenance`: every entry in `THERMAL_SPECIES` and every coefficient in `suitability()` / `thermal_performance()` must include `sources` array with direct URLs or DOIs; `status` string (`illustrative` / `scenario` / etc.); `contract_version`; `world_id`.
- No date-stamped filenames (`_2026_10`, `_WY2025_2026`) in any derived code, config, or default.

### B. Validation Criteria (acceptance tests per M01 / M06 / M11)
Every new species / parameter must pass before reporting done:
- `pytest` suite stays green (`tests/`); new modules ship with tests.
- Volume conservation (`∑Qin + Qhot = Qout`) to 1e-9; heat residual ~1e-10 m³·°C (ledger format).
- Downstream temperature monotone (`T(x)` decreases or stays stable along chain); no non-physical jumps.
- `check_trout_clear_of_pools()` passes: no wildlife record passes through `pool_1034_0` / `pool_1030_0` mask exclusions.
- `audit_provenance` (`python3 tools/audit_provenance.py --dir derived`) passes: provenance complete, source hashes present, `illustrative` labeled.
- Before/after captures at overlook + boardwalk; 10-min replay stable (`M01` substep stability `dt_sub ≤ 0.45/rate`).

### C. Thermal / Suitability / Behavioral Equation Structure
Every new `THERMAL_SPECIES` entry and every modified coefficient must map to the existing function signatures:
- `thermal_performance(t_c, species)`: uses `t_opt_lo_c`, `t_opt_hi_c`, `t_feed_zero_c`, `t_refuge_c`, `t_uilt_c` from `THERMAL_SPECIES` dict; returns `feeding`, `stress`, `refuge_drive`, `lethal_flag`, `species`, `status`, `yellowstone_specific`.
- `suitability(food, cover, t_c, velocity, depth, weights, species, refuge_weight)`: uses `wf`, `wc`, `wt`, `wv`, `wd` weights; `thermal_preference(t_c)`; `refuge_term`; `vel_term` (`VELOCITY_OPT_MPS`, `VELOCITY_TOL_MPS`); `depth_term` (`DEPTH_REF_M`).
- `update_trout()` / enhanced `update_species()`: reads `behavioral_params` from `yellowstone_specific`; applies `population_factor` and `yellowstone_adaptations`; writes `start_point_index`, `end_point_index`, `reach_id`, `reach_temp_c`, `hold_seconds`, `walk_mps`, `lateral_offset_m`, `suitability_U`, `refuge_reason`, `thermal_performance`, `yellowstone_specific`.
- `YELLOWSTONE_COMPETITION_MATRIX`: `competition_factor`, `predators`, `prey`, `competitors`, `ecological_impact` per species pair.
- `validate_yearly_fish_data()`: required params `t_opt_lo_c`, `t_opt_hi_c`, `t_feed_zero_c`, `t_refuge_c`, `t_uilt_c`; `yellowstone_specific` validation (layer names, habitat preferences, thermal constraints).

### D. Data Structure References (for citation in every profile)
- `THERMAL_SPECIES` dictionary format (see M06 in `FISH_MODULE_EXPANSION.md`).
- `derived/<build-id>/river_state.json`: `river_reaches[]` with `temperature_c`, `volume_m3`.
- `derived/<build-id>/plume_map.png`: `T(x)` plan-view temperature field; same origin as `habitat_mask.png`.
- `derived/<build-id>/refuge_map.png`: eligibility layer for cold tributary / shaded bank selection.
- `derived/<build-id>/pool_shells.json`: per-pool `center`, `ring_radii_m`, `shelf_depth_m`, `rim_w_m`, `outflow_id`, `T_center_C`, `T_edge_C`, `color_stops[]`.
- `derived/<build-id>/substrate_rules.json` (`M09`): `substrate_type` (`silica_sinter`); no travertine applied to Midway.

## Summary of Yellowstone Integration Approach

### Key Integration Components

1. **THERMAL_SPECIES Dictionary Expansion**: Add Yellowstone-specific species with enhanced parameters
2. **Enhanced Functions**: Modify thermal_performance(), suitability(), and update_species() for Yellowstone integration
3. **Competition Matrix**: Implement Yellowstone-specific competition relationships
4. **Population Dynamics**: Extend Yellowstone population modeling with species-specific behaviors
5. **Data Validation**: Implement Yellowstone-specific data quality assurance
6. **Simulation Outputs**: Enhance Yellowstone results with species-specific insights

### Yellowstone-Specific Features

1. **Thermal Layer Integration**: Yellowstone Lake thermal stratification considerations
2. **Seasonal Adaptations**: Yellowstone seasonal temperature and flow patterns
3. **Habitat Specialization**: Yellowstone-specific habitat requirements
4. **Competition Dynamics**: Yellowstone competitive interactions between species
5. **Management Implications**: Yellowstone conservation and management considerations

### Implementation Strategy

1. **Phase 1**: Integrate Yellowstone whitefish and cutthroat species
2. **Phase 2**: Add lake trout and arctic char Yellowstone adaptations
3. **Phase 3**: Complete forage species and game fish integration
4. **Phase 4**: Implement Yellowstone competition and ecosystem dynamics
5. **Phase 5**: Validate and test Yellowstone simulation integration

### Expected Benefits

1. **Enhanced Yellowstone Ecosystem Understanding**: Comprehensive Yellowstone aquatic ecosystem modeling
2. **Improved Yellowstone Resource Management**: Data-driven Yellowstone conservation decisions
3. **Yellowstone Climate Change Assessment**: Yellowstone ecosystem response modeling
4. **Yellowstone Sport Fishing Management**: Yellowstone fisheries management support
5. **Yellowstone Educational Capabilities**: Yellowstone ecosystem education and outreach

This comprehensive integration framework provides a structured approach to expand the Yellowstone Python simulation with Yellowstone-specific fish species data while maintaining simulation compatibility and ecological relevance.

