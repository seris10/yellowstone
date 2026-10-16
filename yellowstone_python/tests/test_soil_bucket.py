"""Soil water storage, evapotranspiration, and split drainage balances."""
import pytest

from yellowstone_python.land.snow_season import step_soil_bucket


def test_overflow_drains_above_field_capacity_and_preserves_water():
    result = step_soil_bucket(100.0, 20.0, 20.0, 3.0)
    assert result["soil_mm"] == pytest.approx(84.0)
    assert result["et_mm"] == pytest.approx(0.96)
    assert result["drain_mm"] == pytest.approx(35.04)
    assert result["surface_drain_mm"] == pytest.approx(17.52)
    assert result["subsurface_drain_mm"] == pytest.approx(17.52)
    assert sum(result[key] for key in ("soil_mm", "et_mm", "drain_mm")) == pytest.approx(120.0)
    assert result["water_residual_mm"] == pytest.approx(0.0, abs=1e-12)


def test_dry_bucket_cannot_supply_evapotranspiration():
    result = step_soil_bucket(0.0, 0.0, 40.0, 30.0, elapsed_days=2.0)
    assert all(value == 0.0 for value in result.values())


def test_evapotranspiration_stops_at_available_water():
    result = step_soil_bucket(0.2, 0.1, 20.0, 0.0)
    assert result["et_mm"] == pytest.approx(0.3)
    assert result["soil_mm"] == 0.0
    assert result["drain_mm"] == 0.0
    assert result["water_residual_mm"] == pytest.approx(0.0, abs=1e-12)


def test_subzero_air_preserves_liquid_storage_without_evapotranspiration():
    result = step_soil_bucket(20.0, 10.0, -5.0, 0.0)
    assert result["soil_mm"] == 30.0
    assert result["et_mm"] == result["drain_mm"] == 0.0
    assert result["water_residual_mm"] == 0.0


def test_elapsed_days_scales_et_within_available_storage():
    full = step_soil_bucket(40.0, 0.0, 20.0, 0.0)
    quarter = step_soil_bucket(40.0, 0.0, 20.0, 0.0, elapsed_days=0.25)
    assert full["et_mm"] == pytest.approx(4.0 * quarter["et_mm"])
    assert full["water_residual_mm"] == quarter["water_residual_mm"] == 0.0


@pytest.mark.parametrize("key,value", [
    ("soil_mm", -1.0), ("soil_mm", True), ("inflow_mm", -1.0),
    ("air_c", float("nan")), ("air_c", "20.0"),
    ("wind_mps", -0.1), ("wind_mps", float("inf")),
    ("elapsed_days", 0.0), ("elapsed_days", -1.0), ("elapsed_days", False),
    ("soil_cap_mm", 0.0), ("soil_cap_mm", float("inf")),
    ("field_capacity", -0.1), ("field_capacity", 1.1), ("field_capacity", True),
    ("k_et", -0.1), ("k_et", "0.8"),
])
def test_invalid_soil_inputs_are_rejected(key, value):
    values = {"soil_mm": 40.0, "inflow_mm": 10.0, "air_c": 15.0, "wind_mps": 2.0}
    values[key] = value
    with pytest.raises(ValueError):
        step_soil_bucket(**values)
