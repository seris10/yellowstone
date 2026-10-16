from yellowstone_python.land.snow_season import date_to_season, game_clock_now, resolve_game_clock, run_season, step_snow


def test_thermal_ground_carries_flux_not_absolute_bare():
    # Heavy snow can briefly whiten an apron; the flux melt is budgeted.
    snow, melt, accum, rain, blown, thermal = step_snow(
        200.0, -5.0, 10.0, thermal_flux_mm_d=8.0)
    assert melt == 8.0 and snow == 200.0 + 10.0 - 8.0 and rain == 0.0
    assert blown == 0.0
    assert thermal == 8.0  # whole melt came from the ground flux


def test_conservation_storage():
    snow, melt, accum, rain, blown, thermal = step_snow(50.0, 5.0, 0.0)
    assert abs((50.0 + accum - melt - blown) - snow) < 1e-9
    assert melt == 15.0  # 3 mm/deg-day x 5 deg-days
    assert thermal == 0.0


def test_canopy_wind_aspect_hit_right_processes():
    base = step_snow(100.0, -2.0, 10.0)
    canopy = step_snow(100.0, -2.0, 10.0, canopy_keep=0.7)
    assert canopy[2] < base[2]  # interception reduces accumulation
    windy = step_snow(100.0, -2.0, 10.0, wind_loss=0.2)
    assert windy[4] > 0 and windy[0] < base[0]  # wind removes to runoff
    north = step_snow(100.0, 5.0, 0.0, aspect_retention=1.3)
    south = step_snow(100.0, 5.0, 0.0, aspect_retention=0.8)
    assert north[1] < south[1]  # retention slows melt


def test_rain_recharges_soil_not_snowpack():
    snow, melt, accum, rain, blown, thermal = step_snow(20.0, 8.0, 12.0)
    assert accum == 0.0 and rain == 12.0
    assert melt == 20.0 and thermal == 0.0 and blown == 0.0
    assert snow == 0.0


def test_winter_accumulates_summer_melts():
    w, _ = run_season([{"id": "m", "habitat": "dry_meadow",
                        "center_xz": [0, 0], "moisture": 0.5}],
                      days=10, air_c_by_day=[-4.0] * 10, precip_mm_d=5.0)
    assert w[0]["snow_mm"] > 0 and w[0]["phenology"] == "dormant"
    s, _ = run_season([{"id": "m", "habitat": "dry_meadow",
                       "center_xz": [0, 0], "moisture": 0.5}],
                      days=30, air_c_by_day=[12.0] * 30, precip_mm_d=0.0)
    assert s[0]["snow_mm"] == 0.0 and s[0]["phenology"] != "dormant"


def test_melt_recharges_moisture_capped():
    out, _ = run_season([{"id": "m", "habitat": "dry_meadow",
                          "center_xz": [0, 0], "moisture": 0.99,
                          "snow_mm": 100.0}],
                        days=5, air_c_by_day=[10.0] * 5, precip_mm_d=0.0)
    assert out[0]["moisture"] <= 1.0


def test_ledger_verifies_storage():
    _, led = run_season(
        [{"id": "m", "habitat": "dry_meadow", "center_xz": [0, 0],
          "moisture": 0.5},
         {"id": "f", "habitat": "forest_edge", "center_xz": [500, 500],
          "moisture": 0.4}],
        days=20, air_c_by_day=[-3.0] * 10 + [6.0] * 10, precip_mm_d=4.0,
        thermal_test=lambda x, z: False)
    assert abs(led["storage_residual_mm"]) < 0.05
    assert led["et_mm"] >= 0 and led["rain_mm"] == 80.0  # 2 patches x 10 d x 4 mm
    assert led["accum_mm"] > 0


def test_per_patch_phenology_with_stress():
    out, _ = run_season(
        [{"id": "wet", "habitat": "dry_meadow", "center_xz": [0, 0],
          "moisture": 0.8},
         {"id": "dry", "habitat": "dry_meadow", "center_xz": [500, 500],
          "moisture": 0.05}],
        days=30, air_c_by_day=[10.0] * 30, precip_mm_d=0.0,
        thermal_test=lambda x, z: False)
    stages = {p["id"]: (p["phenology"], p["pheno_stress"]) for p in out}
    assert stages["wet"][0] == "peak_green"
    assert stages["dry"][1] == "drought_delay"


def test_geometry_frozen_implied():
    out, _ = run_season([{"id": "m", "habitat": "dry_meadow",
                          "center_xz": [0, 0], "moisture": 0.5}],
                        days=3, air_c_by_day=[0.0] * 3)
    assert "routes" not in out[0] and "pools" not in out[0]


def test_date_to_season_meteorological_boundaries():
    assert date_to_season(12, 1) == "winter"
    assert date_to_season(2, 29) == "winter"
    assert date_to_season(3, 1) == "spring"
    assert date_to_season(6, 1) == "summer"
    assert date_to_season(9, 1) == "autumn"
    assert date_to_season(10, 10) == "autumn"
    for bad in ((0, 1), (13, 1), (1, 0), (1, 32)):
        try:
            date_to_season(*bad)
        except ValueError:
            continue
        raise AssertionError(f"date_to_season{bad} must refuse")


def test_game_clock_now_shape():
    import datetime
    tick = game_clock_now(
        now=datetime.datetime(2026, 10, 10, 15, 30,
                              tzinfo=datetime.timezone.utc))
    assert tick == {"as_of_local_date": "2026-10-10", "season": "autumn",
                    "clock_hour": 15.5}


def test_resolve_explicit_settings_win():
    import datetime
    now = datetime.datetime(2026, 10, 10, 15, 30,
                            tzinfo=datetime.timezone.utc)
    res = resolve_game_clock(season_cfg="winter", clock_cfg=10.0,
                             date_cfg="2026-01-15", now=now)
    assert res["season"] == "winter" and res["season_source"] == "config"
    assert res["clock_hour"] == 10.0 and res["clock_source"] == "config"
    assert res["as_of_local_date"] == "2026-01-15"
    assert res["date_source"] == "config_date"


def test_resolve_date_derives_season_clock_stays_system():
    import datetime
    now = datetime.datetime(2026, 10, 10, 15, 30,
                            tzinfo=datetime.timezone.utc)
    res = resolve_game_clock(date_cfg="2026-01-15", now=now)
    assert res["season"] == "winter" and res["season_source"] == "config_date"
    assert res["clock_hour"] == 15.5 and res["clock_source"] == "system_clock"


def test_resolve_system_defaults_and_bad_inputs():
    import datetime
    now = datetime.datetime(2026, 7, 4, 9, 0,
                            tzinfo=datetime.timezone.utc)
    res = resolve_game_clock(now=now)
    assert res["season"] == "summer" and res["season_source"] == "system_clock"
    assert res["as_of_local_date"] == "2026-07-04"
    for kwargs in ({"season_cfg": "monsoon"}, {"clock_cfg": 25.0},
                   {"date_cfg": "2026-13-01"}, {"date_cfg": "yesterday"}):
        try:
            resolve_game_clock(**kwargs)
        except ValueError:
            continue
        raise AssertionError(f"resolve_game_clock{kwargs} must refuse")


def _one_patch():
    return [{"id": "m", "habitat": "dry_meadow",
             "center_xz": [0, 0], "moisture": 0.5}]


def test_per_day_precip_series_totals_match():
    # Above-freezing air turns all precip to rain; the ledger equals the series sum for one patch.
    _, led = run_season(_one_patch(), days=5,
                        air_c_by_day=[5.0] * 5,
                        precip_mm_by_day=[0.0, 1.0, 2.0, 3.0, 4.0])
    assert led["rain_mm"] == 10.0 and led["accum_mm"] == 0.0


def test_per_day_precip_matches_scalar_when_flat():
    _, led_series = run_season(
        _one_patch(), days=6, air_c_by_day=[-2.0] * 3 + [4.0] * 3,
        precip_mm_by_day=[2.0] * 6)
    _, led_scalar = run_season(
        _one_patch(), days=6, air_c_by_day=[-2.0] * 3 + [4.0] * 3,
        precip_mm_d=2.0)
    for key in ("accum_mm", "rain_mm", "melt_mm", "et_mm", "drainage_mm",
                "runoff_mm", "final_mm", "storage_residual_mm"):
        assert led_series[key] == led_scalar[key]


def test_per_day_precip_short_series_reuses_last():
    _, led = run_season(_one_patch(), days=3,
                        air_c_by_day=[5.0] * 3,
                        precip_mm_by_day=[4.0], extend_last=True)
    assert led["rain_mm"] == 12.0  # 1 patch x 3 d x 4 mm


def test_per_day_precip_short_series_without_opt_in_rejects():
    import pytest
    with pytest.raises(ValueError):
        run_season(_one_patch(), days=3,
                   air_c_by_day=[5.0] * 3,
                   precip_mm_by_day=[4.0])


def test_empty_precip_series_falls_back_to_scalar():
    _, led = run_season(_one_patch(), days=4,
                        air_c_by_day=[5.0] * 4,
                        precip_mm_by_day=[], precip_mm_d=1.5)
    assert led["rain_mm"] == 6.0


def test_hindcast_air_hourly_averages_to_daily():
    import datetime
    base = datetime.datetime(2026, 1, 1, 0, 0, 0,
                             tzinfo=datetime.timezone.utc).timestamp()
    hourly = []
    for day in range(2):
        for h in range(24):
            air = -2.0 if day == 0 else 6.0
            hourly.append([base + (day * 24 + h) * 3600.0,
                           air, 0.5, 2.0, 100.0, 0.5])
    out, led = run_season(_one_patch(), days=2,
                          air_c_by_day=[0.0, 0.0],
                          precip_mm_d=2.0,
                          run_mode="hindcast",
                          air_hourly_c=hourly)
    assert "air_hourly_c" in led["forcing_source"]
    assert led["run_mode"] == "hindcast"
    assert led["accum_mm"] == 2.0
    assert led["rain_mm"] == 2.0


def test_illustrative_ignores_air_hourly_c():
    import datetime
    base = datetime.datetime(2026, 1, 1, 0, 0, 0,
                             tzinfo=datetime.timezone.utc).timestamp()
    hourly = [[base + h * 3600.0, 20.0, 0.5, 2.0, 100.0, 0.5]
              for h in range(24)]
    _, led = run_season(_one_patch(), days=1,
                        air_c_by_day=[-5.0],
                        precip_mm_d=4.0,
                        run_mode="illustrative",
                        air_hourly_c=hourly)
    assert led["forcing_source"] == "air_c_by_day"
    assert led["accum_mm"] == 4.0


def test_run_mode_rejects_unknown_value():
    import pytest
    with pytest.raises(ValueError):
        run_season(_one_patch(), days=1,
                   air_c_by_day=[0.0], run_mode="forecast")


def test_daily_air_c_from_hourly_grouping():
    import datetime
    from yellowstone_python.land.snow_season import daily_air_c_from_hourly
    base = datetime.datetime(2026, 6, 1, 0, 0, 0,
                             tzinfo=datetime.timezone.utc).timestamp()
    rows = []
    for h in range(48):
        air = 10.0 + (h % 24) * 0.1
        rows.append([base + h * 3600.0, air, 0.5, 2.0, 100.0, 0.5])
    daily = daily_air_c_from_hourly(rows)
    assert len(daily) == 2
    expected = sum(10.0 + h * 0.1 for h in range(24)) / 24.0
    assert abs(daily[0] - expected) < 1e-9
    assert abs(daily[1] - expected) < 1e-9
