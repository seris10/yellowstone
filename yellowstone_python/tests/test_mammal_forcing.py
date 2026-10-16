"""Physical-time and unit conversion checks for mammal environmental drivers."""
from datetime import datetime, timezone

import pytest

from yellowstone_python.common.mammal_forcing import environmental_forcing, apply_consumption


def test_local_new_year_and_leap_year_follow_simulation_epoch():
    epoch = datetime(2024, 1, 1, 6, tzinfo=timezone.utc).timestamp()
    start = environmental_forcing([], {"air_c": -10.0}, epoch)
    middle = environmental_forcing([], {"air_c": -10.0}, epoch + 183 * 86400)
    assert start["season_phase"] == 0.0
    assert start["local_hour"] == 0.0
    assert middle["season_phase"] == 0.5
    assert middle["air_c"] == -10.0


def test_depleted_forage_and_deep_snow_reach_patch_forcing():
    patch = {"id": "forest", "habitat": "forest_edge", "biomass": 0.0,
             "capacity": 1.0, "moisture": 0.2, "snow_depth_m": 1.2,
             "soil_temperature_c": -2.0, "insect_activity": 0.0}
    result = environmental_forcing([patch], {"air_c": -20.0}, 1782064800)
    assert result["by_patch"]["forest"]["forage_fraction"] == 0.0
    assert result["by_patch"]["forest"]["snow_m"] == 1.2
    assert result["by_patch"]["forest"]["soil_temperature_c"] == -2.0
    assert "not surveyed" in result["resource_units"]
    assert "season_phase" not in patch


def test_corrupt_thermal_forcing_stops_before_model_consumption():
    with pytest.raises(ValueError, match="must be finite"):
        environmental_forcing([{"id": "edge", "soil_temperature_c": float("nan")}], {}, 1782064800)


def test_allocated_food_is_removed_once_and_budget_closes():
    patches = [{"id": "meadow", "biomass": 0.7}, {"id": "edge", "biomass": 0.2}]
    updated, ledger = apply_consumption(patches, {"meadow": 0.15, "edge": 0.1})
    assert sum(patch["biomass"] for patch in updated) == pytest.approx(0.65)
    assert ledger["consumed_biomass_index"] == 0.25
    assert ledger["residual"] == pytest.approx(0.0, abs=1e-12)
    assert patches[0]["biomass"] == 0.7


def test_excess_demand_rejects_the_whole_allocation():
    patches = [{"id": "meadow", "biomass": 0.7}, {"id": "edge", "biomass": 0.2}]
    with pytest.raises(ValueError, match="exceeds patch edge"):
        apply_consumption(patches, {"meadow": 0.1, "edge": 0.3})
    assert patches == [{"id": "meadow", "biomass": 0.7}, {"id": "edge", "biomass": 0.2}]
