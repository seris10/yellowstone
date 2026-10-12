from yellowstone_python.microclimate import (air_temp, boiling_point_c,
                                                  condensation_potential,
                                                  dewpoint_c,
                                                  prevailing_direction,
                                                  steam_visibility, trace,
                                                  wind_series)


def test_peak_lags_solar_noon():
    assert abs(air_temp(15.0) - 22.0) < 1e-9  # Tmax near 15:00, not noon
    assert air_temp(12.0) < air_temp(15.0)
    assert abs(air_temp(0.0) - 7.0) < 1e-9
    assert abs(air_temp(12.0, 7.0, 15.0, lag_hours=0.0) - 22.0) < 1e-9


def test_trace_uses_configured_weather():
    tr = trace(seconds=10, hour0=12.0, night_air_c=-5.0, day_warming_c=6.0,
               humidity=0.9, seed=3)
    assert abs(tr[0]["air_c"] - air_temp(12.0, -5.0, 6.0)) < 1e-9
    tr2 = trace(seconds=10, hour0=12.0, night_air_c=-5.0, day_warming_c=6.0,
                humidity=0.9, seed=3)
    assert [r["wind_x"] for r in tr] == [r["wind_x"] for r in tr2]  # seeded


def test_wind_series_reverts_to_prevailing():
    import statistics
    ws = wind_series(600.0, 1.0, (1.8, 0.6), 0.45, seed=11)
    mx = statistics.mean(w[0] for w in ws)
    assert abs(mx - 1.8) < 0.15 and prevailing_direction((1.8, 0.6)) > 0


def test_condensation_physics_sane():
    assert abs(boiling_point_c() - 92.6) < 0.6  # ~2215 m site pressure
    assert abs(dewpoint_c(20.0, 1.0) - 20.0) < 0.2
    cold = condensation_potential(62.0, 2.0, 0.9)
    dry = condensation_potential(62.0, 25.0, 0.15)
    assert cold["supersaturation_kpa"] > dry["supersaturation_kpa"]
    assert cold["dewpoint_depression_c"] < dry["dewpoint_depression_c"]
