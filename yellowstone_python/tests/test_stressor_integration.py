"""Integration tests for and wiring."""
from __future__ import annotations

import math

from yellowstone_python.aquatic.aquatic_foodweb import run_foodweb, thermal_landscape
from yellowstone_python.registry.coupling import EXCHANGES, validate_contract
from yellowstone_python.registry.equations import COMPONENTS, validate_inventory
from yellowstone_python.registry.param_registry import PARAMS, registry_errors
from yellowstone_python.aquatic.piscivores import refuge_predation_risk
from yellowstone_python.river.river_transport import make_replay


REQUIRED_EXCHANGES = (
    "solute_habitat_multiplier",
    "chloride_flux_validation",
    "oxygen_do_fish_multiplier",
    "oxygen_do_insect_multiplier",
    "periphyton_oxygen_metabolism",
    "shortwave_shading_multiplier",
    "hyporheic_exchange",
    "piscivore_predation",
    "aerial_insectivore_consumption",
    "ground_heat_snow_melt",
    "ground_heat_tree_suitability",
    "snow_depth_grazer_cost",
    "warm_ground_grazer_refuge",
    "grazer_nutrient_return",
    "grazer_trampling_crust",
    "reference_et_soil_water",
    "steam_plume_microclimate",
    "outflow_foodweb_mat",
)


REQUIRED_PARAMS = (
    "solute_transport.excelsior_chloride_mg_l",
    "solute_transport.firehole_upstream_chloride_mg_l",
    "fish.solute_toxicity.chloride_chronic_mg_l",
    "fish.solute_toxicity.boron_no_effect_mg_l",
    "river_oxygen.covar_shallow_depth_m",
    "river_oxygen.salmonid_growth_min_mg_l",
    "periphyton.photosynthetic_quotient",
    "river_shading.canopy_transmissivity",
    "hyporheic.alpha_per_s",
    "ground_heat.background_w_m2",
    "ground_heat.lodgepole_soil_dieoff_c",
    "grazers.bison_crater_depth_m",
    "vegetation.nitrogen_decay_tau_s",
    "vegetation.sinter_deposition_mm_per_s",
    "evapotranspiration.method",
    "piscivore_density.osprey_per_km2",
    "steam_microclimate.ibl_coefficient_a",
    "invert_taxa.nz_mudsnail_competition_weight",
    "outflow_foodweb.mite_baseline_parasitism",
)


REQUIRED_COMPONENTS = (
    "replay solute transport",
    "river dissolved oxygen",
    "periphyton biomass",
    "river shading",
    "ground heat flux and soil temperature",
    "reference evapotranspiration",
    "piscivore predation",
    "aerial insectivores",
    "outflow food web",
    "steam microclimate plume",
    "invertebrate taxa foodweb",
)


def test_coupling_registry_names_each_new_exchange():
    assert validate_contract() == []
    ids = {record["exchange_id"] for record in EXCHANGES}
    missing = [exchange for exchange in REQUIRED_EXCHANGES if exchange not in ids]
    assert not missing, f"missing exchanges in coupling registry: {missing}"


def test_param_registry_names_each_new_param():
    assert registry_errors() == []
    ids = {record["param_id"] for record in PARAMS}
    missing = [param for param in REQUIRED_PARAMS if param not in ids]
    assert not missing, f"missing params in registry: {missing}"


def test_equations_registry_names_each_new_component():
    assert validate_inventory() == []
    names = {record["component"] for record in COMPONENTS}
    missing = [component for component in REQUIRED_COMPONENTS
               if component not in names]
    assert not missing, f"missing equations components: {missing}"


def _landscape():
    config = {
        "boundary_m3_s": 2.0,
        "boundary_c": 15.0,
        "air_c": 9.0,
        "duration_s": 600.0,
        "dt_s": 10.0,
        "sample_s": 60.0,
        "cells": [
            {"id": f"c{i}", "length_m": 50.0, "width_m": 10.0,
             "volume_m3": 550.0, "initial_c": 15.0,
             "exchange_w_m2_k": 12.0}
            for i in range(4)
        ],
        "sources": [
            {"id": "creek", "cell_id": "c1", "flow_m3_s": 0.2,
             "temperature_c": 11.0,
             "status": "illustrative_not_calibrated"},
        ],
    }
    doc = make_replay(config)
    return thermal_landscape(doc)


def test_disabling_a_stressor_restores_the_previous_fish_outputs():
    landscape = _landscape()
    baseline = run_foodweb(landscape, days=3.0, dt_days=1.0,
                           trout_species="brown_trout")
    stressed = run_foodweb(landscape, days=3.0, dt_days=1.0,
                           trout_species="brown_trout",
                           predation_rate_by_cell={cell["id"]: 0.3
                                                   for cell in landscape},
                           predation_window_days=1.0)
    neutral = run_foodweb(landscape, days=3.0, dt_days=1.0,
                          trout_species="brown_trout",
                          predation_rate_by_cell=None,
                          do_mg_l_by_cell=None,
                          solute_concentrations=None)
    # Neutral kwargs match the no-kwargs baseline exactly.
    assert neutral["trout"]["U"] == baseline["trout"]["U"]
    assert neutral["trout"]["s_m"] == baseline["trout"]["s_m"]
    # A positive predation rate reduces trout habitat suitability.
    assert stressed["trout"]["U"] <= baseline["trout"]["U"]


def test_piscivore_refuge_risk_decreases_with_depth():
    shallow = refuge_predation_risk(cell_depth_m=0.2, size_class="adult")
    deep = refuge_predation_risk(cell_depth_m=2.0, size_class="adult")
    assert math.isfinite(shallow)
    assert math.isfinite(deep)
    assert deep < shallow
