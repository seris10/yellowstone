"""Tests for the cross-family temperature gate and its forcing inputs."""
import json

import pytest

from yellowstone_python.build import _prepare_replay_ecosystem
from yellowstone_python.registry.coupling import check_cross_family
from yellowstone_python.atmosphere.microclimate import air_temp
from yellowstone_python.river.river_world import physical_weather

BASELINE = {
    "clock_hour": 16.2,
    "weather": {"night_air_c": 7.0, "day_warming_c": 15.0,
                "wind_xz_mps": [1.8, 0.6], "gust_mps": 0.45,
                "humidity": 0.45, "cloud": 0.16},
    "boundary_m3s": 8.0,
    "boundary_c": 17.5,
    "river_reaches": [{"id": "upstream_midway", "temperature_c": 17.5}],
    "schema_version": 1,
}


def _landscape(temps, step=100.0):
    return [{"id": f"cell_{i:03d}", "s_m": i * step, "temperature_c": t}
            for i, t in enumerate(temps)]


def test_weather_fragment_reaches_the_solver():
    weather = {"night_air_c": 11.5, "day_warming_c": 9.0,
               "wind_xz_mps": [3.0, 1.0], "gust_mps": 0.8,
               "humidity": 0.6, "cloud": 0.4, "lag_hours": 2.0,
               "weather_provenance": "measured_remote_not_calibrated"}
    eco = _prepare_replay_ecosystem(BASELINE, {}, hour0=3.5, weather=weather)
    assert eco["clock_hour"] == 3.5
    assert eco["weather"]["night_air_c"] == 11.5
    assert eco["weather"]["lag_hours"] == 2.0
    assert "weather_provenance" not in eco["weather"]
    assert BASELINE["clock_hour"] == 16.2
    assert BASELINE["weather"]["night_air_c"] == 7.0


def test_boundary_overrides_still_apply_alongside_weather():
    cfg = {"hydro": {"boundary_m3s": 2.5, "boundary_c": 26.0}}
    eco = _prepare_replay_ecosystem(BASELINE, cfg, hour0=16.2,
                                    weather={"night_air_c": 8.5})
    assert eco["boundary_m3s"] == 2.5
    assert eco["boundary_c"] == 26.0
    assert eco["weather"]["night_air_c"] == 8.5
    assert eco["weather"]["day_warming_c"] == 15.0


def test_solver_and_chain_share_one_air_curve():
    weather = {"night_air_c": 8.5, "day_warming_c": 15.0, "lag_hours": 3.0}
    eco = _prepare_replay_ecosystem(BASELINE, {}, hour0=16.2, weather=weather)
    series, records = physical_weather(eco, 3600.0, interval_s=600.0)
    for value, record in zip(series.values, records):
        assert value == pytest.approx(
            air_temp(record["hour"], 8.5, 15.0, lag_hours=3.0))
        assert value == pytest.approx(record["air_c"])


def test_absent_weather_keeps_the_baseline_curve():
    series, _ = physical_weather(BASELINE, 600.0, interval_s=600.0)
    assert series.values[0] == pytest.approx(
        air_temp(16.2, 7.0, 15.0, lag_hours=3.0))


def test_cross_family_passes_inside_tolerance():
    result = check_cross_family(_landscape([17.0, 17.5, 18.0, 18.5]),
                                [{"id": "r1", "temperature_c": 17.2}],
                                ["r1", "r1", "r1", "r1"],
                                [0.0, 100.0, 200.0, 300.0])
    assert result["passed"], result["failures"]
    assert result["metrics"]["cross_family_compared"] == 1
    assert result["metrics"]["cross_family_max_delta_c"] < 2.0


def test_cross_family_fails_outside_tolerance():
    result = check_cross_family(_landscape([17.0, 17.5, 18.0, 18.5]),
                                [{"id": "r1", "temperature_c": 24.0}],
                                ["r1", "r1", "r1", "r1"],
                                [0.0, 100.0, 200.0, 300.0],
                                tolerance_c=2.0)
    assert not result["passed"]
    assert any("r1" in f for f in result["failures"])


def test_cross_family_applies_the_chainage_offset():
    field = _landscape([10.0, 11.0, 12.0, 13.0])
    result = check_cross_family(field, [{"id": "r1", "temperature_c": 11.0}],
                                ["r1"] * 4, [0.0, 100.0, 200.0, 300.0],
                                chainage_offset_m=100.0)
    assert result["passed"], result["failures"]


def test_cross_family_reports_reaches_without_points():
    result = check_cross_family(_landscape([17.0, 17.5, 18.0]),
                                [{"id": "ghost", "temperature_c": 17.0}],
                                ["r1", "r1", "r1"], [0.0, 100.0, 200.0])
    assert not result["passed"]
    assert any("ghost" in s
               for s in result["metrics"]["cross_family_skipped"])


def test_cross_family_requires_usable_inputs():
    result = check_cross_family([], [{"id": "r1", "temperature_c": 17.0}],
                                ["r1"], [0.0])
    assert not result["passed"]
    assert result["metrics"]["cross_family_compared"] == 0
