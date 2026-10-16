"""Numeric input contracts for snow, wind, and solute source adapters."""
import copy

import pytest

from yellowstone_python.atmosphere.microclimate import wind_series
from yellowstone_python.land.snow_season import date_to_season, degree_days, step_snow
from yellowstone_python.river.solute_transport import (
    SOLUTE_KEYS, load_hydrothermal_solutes, solute_habitat_multiplier,
    solute_sources_for_mapped_sources, transport_from_mapped_replay,
)


@pytest.mark.parametrize("value", [True, "6", 6.9])
@pytest.mark.parametrize("field", ["month", "day"])
def test_calendar_fields_require_integers(field, value):
    values = {"month": 6, "day": 1, field: value}
    with pytest.raises(ValueError):
        date_to_season(**values)


@pytest.mark.parametrize("field", ["air_c", "tbase"])
@pytest.mark.parametrize("value", [True, "5.0", float("nan"), float("inf")])
def test_degree_day_fields_require_finite_numbers(field, value):
    values = {"air_c": 5.0, "tbase": 0.0, field: value}
    with pytest.raises(ValueError):
        degree_days(**values)


@pytest.mark.parametrize("field", ["snow_mm", "air_c", "precip_mm_d", "k_melt", "tbase",
                                  "aspect_retention", "canopy_keep", "wind_loss", "thermal_flux_mm_d"])
@pytest.mark.parametrize("value", [True, "1.0", float("nan"), float("inf")])
def test_snow_step_rejects_coercible_and_nonfinite_fields(field, value):
    values = {"snow_mm": 10.0, "air_c": 5.0, "precip_mm_d": 1.0, field: value}
    with pytest.raises(ValueError):
        step_snow(**values)


@pytest.mark.parametrize("field", ["seconds", "dt", "max_samples"])
@pytest.mark.parametrize("value", [True, "1.0", float("nan"), float("inf")])
def test_wind_trace_rejects_coercible_and_nonfinite_time_or_capacity(field, value):
    values = {"seconds": 0.0, "dt": 1.0, "max_samples": 2, field: value}
    with pytest.raises(ValueError):
        wind_series(**values)


def test_wind_trace_capacity_requires_an_integer():
    with pytest.raises(ValueError, match="max_samples"):
        wind_series(seconds=0.0, max_samples=1.5)


@pytest.mark.parametrize("solute,field", [
    ("chloride_mg_l", "chronic_mg_l"), ("chloride_mg_l", "acute_mg_l"),
    ("arsenic_ug_l", "chronic_ug_l"), ("arsenic_ug_l", "acute_ug_l"),
    ("boron_mg_l", "no_effect_mg_l"), ("boron_mg_l", "effect_mg_l"),
])
@pytest.mark.parametrize("value", [True, "1.0", float("nan"), float("inf"), -1.0])
def test_solute_threshold_overrides_require_nonnegative_finite_numbers(solute, field, value):
    thresholds = copy.deepcopy(load_hydrothermal_solutes()["aquatic_toxicity_thresholds"])
    thresholds[solute][field] = value
    with pytest.raises(ValueError):
        solute_habitat_multiplier(0.0, 0.0, 0.0, thresholds)


def _chemistry(values):
    return {key: {"value": value} for key, value in zip(SOLUTE_KEYS, values)}


@pytest.mark.parametrize("key", SOLUTE_KEYS)
@pytest.mark.parametrize("value", [True, "1.0", float("nan"), float("inf")])
def test_mapped_source_chemistry_preserves_numeric_type_checks(key, value):
    feature = _chemistry((10.0, 2.0, 0.1))
    feature[key]["value"] = value
    data = {"mapping_notes": {"spring": {"feature_id": "chemistry"}},
            "features": {"chemistry": feature}}
    with pytest.raises(ValueError):
        solute_sources_for_mapped_sources(
            [{"id": "spring", "cell_id": "cell", "flow_m3_s": 0.1}], data)


@pytest.mark.parametrize("key", SOLUTE_KEYS)
@pytest.mark.parametrize("value", [True, "1.0", float("nan"), float("inf")])
def test_mapped_boundary_chemistry_preserves_numeric_type_checks(key, value):
    feature = _chemistry((10.0, 2.0, 0.1))
    feature[key]["value"] = value
    data = {"mapping_notes": {}, "features": {"firehole_upstream_boundary": feature}}
    replay = {"cells": [{"id": "cell", "length_m": 10.0, "width_m": 2.0, "volume_m3": 20.0}],
              "forcing": {"boundary_m3_s": 1.0, "sources": []}}
    with pytest.raises(ValueError):
        transport_from_mapped_replay(replay, data)
