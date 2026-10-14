"""Tests for the river periphyton compartment."""
from __future__ import annotations

import math

import pytest

from yellowstone_python.aquatic.periphyton import O2_PER_C_MASS, PHOTOSYNTHETIC_QUOTIENT, PeriphytonParams, describe_model, gpp_mg_c_m2_s, light_factor, net_o2_production_mg_o2_m2_s, respiration_mg_c_m2_s, step_biomass, temperature_factor


def test_light_factor_monotonic_and_saturates():
    params = PeriphytonParams()
    values = [light_factor(sw, params)
              for sw in (0.0, 50.0, 200.0, 800.0, 2000.0)]
    assert values == sorted(values)
    assert values[0] == 0.0
    assert values[-1] < 1.0
    assert values[-1] > 0.9


def test_biomass_rises_with_light_then_saturates():
    params = PeriphytonParams(min_biomass_mg_c_m2=1.0,
                              grazing_rate_per_day=0.0,
                              respiration_rate_per_day=0.0,
                              biomass_saturation_mg_c_m2=1e9)
    starting = 100.0
    after_dark = step_biomass(starting, 0.0, 20.0, 0.0, 300.0, params)
    after_dim = step_biomass(starting, 100.0, 20.0, 0.0, 300.0, params)
    after_bright = step_biomass(starting, 1500.0, 20.0, 0.0, 300.0, params)
    assert after_dark["biomass_mg_c_m2"] == pytest.approx(starting)
    assert (after_dark["biomass_mg_c_m2"]
            < after_dim["biomass_mg_c_m2"]
            < after_bright["biomass_mg_c_m2"])
    very_bright = step_biomass(
        starting, 5000.0, 20.0, 0.0, 300.0, params)
    assert very_bright["biomass_mg_c_m2"] / after_bright["biomass_mg_c_m2"] < 1.1


def test_zero_producers_starves_grazer_over_declared_time_scale():
    params = PeriphytonParams(grazing_rate_per_day=1.0,
                              respiration_rate_per_day=0.0,
                              min_biomass_mg_c_m2=0.0)
    biomass = 100.0
    grazer_intake = 0.0
    dt_s = 86400.0 / 48.0
    for _ in range(48):
        row = step_biomass(biomass, 0.0, 20.0, 1.0, dt_s, params)
        grazer_intake += row["grazing_mg_c_m2_s"] * dt_s
        biomass = row["biomass_mg_c_m2"]
    assert biomass < 50.0
    biomass_bright = 100.0
    grazer_intake_bright = 0.0
    for _ in range(48):
        row = step_biomass(biomass_bright, 1500.0, 20.0, 1.0, dt_s, params)
        grazer_intake_bright += row["grazing_mg_c_m2_s"] * dt_s
        biomass_bright = row["biomass_mg_c_m2"]
    assert grazer_intake_bright > grazer_intake


def test_temperature_factor_at_reference_is_one():
    params = PeriphytonParams(reference_temp_c=20.0)
    assert temperature_factor(20.0, params) == pytest.approx(1.0)
    assert temperature_factor(10.0, params) < 1.0
    assert temperature_factor(30.0, params) > 1.0


def test_o2_production_matches_carbon_times_stoichiometry():
    params = PeriphytonParams()
    gpp_c = gpp_mg_c_m2_s(500.0, 400.0, 15.0, params)
    r_c = respiration_mg_c_m2_s(500.0, 15.0, params)
    out = net_o2_production_mg_o2_m2_s(500.0, 400.0, 15.0, params)
    assert out["gpp_mg_o2_m2_s"] == pytest.approx(gpp_c * O2_PER_C_MASS)
    assert out["respiration_mg_o2_m2_s"] == pytest.approx(r_c * O2_PER_C_MASS)
    assert out["net_mg_o2_m2_s"] == pytest.approx(
        (gpp_c - r_c) * O2_PER_C_MASS)
    assert PHOTOSYNTHETIC_QUOTIENT == pytest.approx(1.2)


def test_describe_model_carries_sources():
    doc = describe_model()
    assert doc["schema"] == "yellowstone.periphyton.v1"
    assert "Eppley" in doc["sources"]["temperature"]
    assert math.isfinite(doc["parameters"]["p_max_specific_per_day"])
