"""Simulation-time weather consistency and provenance classes."""
import pytest

from yellowstone_python.atmosphere.microclimate import air_temp, dewpoint_c, weather_snapshot
from yellowstone_python.atmosphere.time_utils import epoch_unix_for_local
from yellowstone_python.common.site import SITE_LAT_DEG, SITE_LON_DEG
from yellowstone_python.common.coords import E0, N0, CRS


def test_snapshot_uses_simulated_hour_and_magnus_dewpoint():
    epoch = epoch_unix_for_local("2026-07-15", 16.0, -6.0)
    cfg = {"night_air_c": 7.0, "day_warming_c": 15.0, "humidity": 0.45}
    snapshot = weather_snapshot(epoch, cfg)
    weather = snapshot["weather"]
    assert weather["air_temperature_c"] == pytest.approx(air_temp(16.0, 7.0, 15.0))
    assert weather["dewpoint_c"] == pytest.approx(dewpoint_c(weather["air_temperature_c"], 0.45))
    assert snapshot["simulation_time_unix"] == epoch
    assert snapshot["valid_time_unix"] == epoch
    assert snapshot["source"]["visibility_class"] == "authored"
    assert snapshot["source"]["cloud_base_class"] == "authored"


def test_world_center_coordinates_match_georeference():
    pyproj = pytest.importorskip("pyproj")
    lon, lat = pyproj.Transformer.from_crs(CRS, "EPSG:4326", always_xy=True).transform(E0, N0)
    assert SITE_LAT_DEG == pytest.approx(lat, abs=1e-5)
    assert SITE_LON_DEG == pytest.approx(lon, abs=1e-5)


def test_dry_air_has_unavailable_dewpoint():
    snapshot = weather_snapshot(0.0, {"humidity": 0.0})
    assert snapshot["weather"]["dewpoint_c"] is None
