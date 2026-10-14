import math

import pytest

from yellowstone_python.river.obs_model import STATIONS, compare, interval_average, stage_to_elevation_ft_navd88


def test_station_table_covers_both_gauges():
    assert set(STATIONS) == {"06036805", "06036905"}
    for site, info in STATIONS.items():
        assert info["datum_ft_navd88"] > 7000, site
        assert info["interval_s"] == 900.0, site
        assert info["provisional"] is True, site
        assert info["temp_accuracy_c"] == 0.2, site
        assert info["representativeness_c"] == 0.6, site
    assert STATIONS["06036905"]["datum_superseded_ft"] == 7050.0


def test_stage_to_elevation_uses_current_datum():
    assert stage_to_elevation_ft_navd88(0.0, "06036805") == 7339.88
    assert stage_to_elevation_ft_navd88(2.5, "06036905") == \
        7056.08 + 2.5
    with pytest.raises(KeyError):
        stage_to_elevation_ft_navd88(1.0, "99999999")
    with pytest.raises(ValueError):
        stage_to_elevation_ft_navd88(math.inf, "06036805")


def test_interval_average_bins_from_first_time():
    times = [100.0, 130.0, 200.0, 260.0]
    values = [10.0, 14.0, 20.0, 22.0]
    # Bin labels are left edges of half-open intervals (same convention as obs_frame._frame_from_pairs): [100,200) averages 10.0 and 14.0; [200,300) averages 20.0 and 22.0.
    lefts, means = interval_average(times, values, 100.0)
    assert lefts == [100.0, 200.0]
    assert means == [12.0, 21.0]
    with pytest.raises(ValueError):
        interval_average([], [], 100.0)
    with pytest.raises(ValueError):
        interval_average([1.0], [1.0, 2.0], 100.0)


def test_compare_returns_scores_and_error_terms():
    out = compare([1.0, 2.0, 3.0], [1.0, 2.0, 4.0],
                  measurement_error=0.1,
                  representativeness=0.2)
    assert out["rmse"] > 0.0
    assert out["n"] == 3.0
    assert out["measurement_error"] == 0.1
    assert out["representativeness"] == 0.2


def test_compare_defaults_sourced():
    out = compare([1.0], [1.5])
    assert out["measurement_error"] == 0.2
    assert out["representativeness"] == 0.6
