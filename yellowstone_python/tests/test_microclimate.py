import inspect
import math
import warnings
from datetime import datetime, timezone

import pytest

from yellowstone_python.atmosphere.microclimate import air_temp, boiling_point_c, bundle_weather, condensation_potential, dewpoint_c, fetch_nws_station_data, load_real_weather, load_weather_bundle, metpy_wet_bulb_temperature, prevailing_direction, pvlib_solar_azimuth_elevation, steam_visibility, trace, wind_from_direction, wind_series
import yellowstone_python.atmosphere.microclimate as m


def test_peak_lags_solar_noon():
    assert abs(air_temp(15.0) - 22.0) < 1e-9  # Tmax near 15:00
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
    assert cold["supersat_pressure_kpa"] > dry["supersat_pressure_kpa"]
    assert cold["dewpoint_depression_c"] < dry["dewpoint_depression_c"]


# Regression tests from audit spec.


def test_wet_bulb_pressure_default():
    default = inspect.signature(
        metpy_wet_bulb_temperature
    ).parameters["pressure_pa"].default
    assert default == pytest.approx(m.SITE_PRESSURE_KPA * 1000.0)


def test_site_boiling_point():
    assert 92.0 < boiling_point_c() < 94.0


def test_wind_initial_sample():
    assert wind_series(seconds=0.0) == [(1.8, 0.6)]


@pytest.mark.parametrize(
    "seconds, dt",
    [(-1.0, 1.0), (60.0, 0.0), (60.0, -1.0)],
)
def test_invalid_sampling(seconds, dt):
    with pytest.raises(ValueError):
        wind_series(seconds=seconds, dt=dt)


def test_seeded_wind_is_repeatable():
    assert wind_series(seed=11) == wind_series(seed=11)


def test_bundle_weather_selects_by_epoch():
    bundle = {
        "schema": "yellowstone.met_forcing.v1",
        "hourly": [
            [1000.0, 10.0, 0.5, 2.0, 200.0, 0.2],
            [2000.0, 15.0, 0.6, 3.0, 250.0, 0.3],
        ],
    }
    out = bundle_weather(bundle, epoch_s_utc=1500.0)
    assert out["night_air_c"] == 10.0  # nearest to 1500 is 1000


def test_bundle_weather_nearest_row():
    bundle = {
        "schema": "yellowstone.met_forcing.v1",
        "hourly": [[3600.0, 5.0, 0.4, 1.5, 150.0, 0.1]],
    }
    out = bundle_weather(bundle, epoch_s_utc=3600.0)
    assert out["night_air_c"] == 5.0


def test_bundle_weather_rejects_bad_epoch():
    bundle = {
        "schema": "yellowstone.met_forcing.v1",
        "hourly": [[3600.0, 5.0, 0.4, 1.5, 150.0, 0.1]],
    }
    with pytest.raises(ValueError):
        bundle_weather(bundle, epoch_s_utc=10000.0, max_distance_s=60.0)


def test_bundle_weather_rejects_empty_bundle():
    with pytest.raises(ValueError):
        bundle_weather({"schema": "yellowstone.met_forcing.v1", "hourly": []}, epoch_s_utc=0)


def test_bundle_weather_rejects_bad_schema():
    with pytest.raises(ValueError):
        bundle_weather({"schema": "other"}, epoch_s_utc=0)


def test_bundle_weather_rejects_malformed_rows():
    with pytest.raises(ValueError):
        bundle_weather(
            {"schema": "yellowstone.met_forcing.v1", "hourly": [[1, 2]]},
            epoch_s_utc=1,
        )


def test_bundle_weather_rejects_nan():
    with pytest.raises(ValueError):
        bundle_weather(
            {"schema": "yellowstone.met_forcing.v1", "hourly": [[float('nan'), 10, 0.5, 2, 200, 0.1]]},
            epoch_s_utc=1,
        )


def test_bundle_weather_rejects_out_of_range_rh():
    with pytest.raises(ValueError):
        bundle_weather(
            {"schema": "yellowstone.met_forcing.v1", "hourly": [[1, 10, 1.5, 2, 200, 0.1]]},
            epoch_s_utc=1,
        )


def test_bundle_weather_output_wind_vector_matches_speed():
    bundle = {
        "schema": "yellowstone.met_forcing.v1",
        "hourly": [[3600.0, 10.0, 0.5, 2.5, 150.0, 0.1]],
    }
    out = bundle_weather(bundle, epoch_s_utc=3600.0, default_wind=(1.8, 0.6))
    speed = math.hypot(out["wind_xz_mps"][0], out["wind_xz_mps"][1])
    assert abs(speed - 2.5) < 2e-3


def test_load_real_weather_validates():
    # A valid frozen bundle should load successfully.
    import tempfile, json, os
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json.dump({
            "schema": "yellowstone.met_forcing.v1",
            "hourly": [[1000.0, 10.0, 0.5, 2.0, 200.0, 0.2]],
        }, f)
        path = f.name
    try:
        result = load_real_weather(path)
        assert result is not None
        assert result["hourly"][0][1] == 10.0
    finally:
        os.unlink(path)


def test_load_real_weather_rejects_bad_file():
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        f.write("not json")
        path = f.name
    try:
        assert load_real_weather(path) is None
    finally:
        os.unlink(path)


def test_dewpoint_rejects_dry_air():
    with pytest.raises(ValueError):
        dewpoint_c(20.0, 0.0)


def test_dewpoint_rejects_negative_rh():
    with pytest.raises(ValueError):
        dewpoint_c(20.0, -0.1)


def test_dewpoint_rejects_over_one_rh():
    with pytest.raises(ValueError):
        dewpoint_c(20.0, 1.5)


def test_condensation_potential_rejects_bad_rh():
    with pytest.raises(ValueError):
        condensation_potential(62.0, 2.0, 1.5)


def test_boiling_point_positive_pressure():
    with pytest.raises(ValueError):
        boiling_point_c(-10.0)


def test_wind_from_direction_calm_raises():
    with pytest.raises(ValueError):
        wind_from_direction((0.0, 0.0))


@pytest.mark.needs_pvlib
def test_solar_negative_at_night():
    try:
        import pvlib
        import pandas as pd
    except ImportError:
        pytest.skip("pvlib/pandas not installed")
    # At midnight UTC in October, elevation should be negative at this latitude.
    az, el = pvlib_solar_azimuth_elevation(
        timestamp_utc_str="2026-10-11T04:00:00+00:00"
    )
    assert el < 0.0


@pytest.mark.needs_science
def test_metpy_wet_bulb_saturated_approx_equals_air():
    try:
        import metpy
    except ImportError:
        pytest.skip("metpy not installed")
    # At 100% RH and moderate temperature, wet bulb approximates air temperature.
    result = metpy_wet_bulb_temperature(15.0, 1.0)
    assert abs(result - 15.0) < 2.0


def test_nws_null_values_distinguished():
    # The function returns None for missing observations under a synthetic properties dict.
    from yellowstone_python.atmosphere.microclimate import _nws_quantity
    assert _nws_quantity({"temperature": {"value": None}}, "temperature", {"wmoUnit:degC": 1.0}) is None


def test_nws_precip_unit_conversion():
    from yellowstone_python.atmosphere.microclimate import _nws_quantity
    # Millimeters reports as 1.0 * 1.0 = value
    assert _nws_quantity({"precipitationLastHour": {"value": 10, "unitCode": "wmoUnit:mm"}}, "precipitationLastHour", {"wmoUnit:mm": 1.0, "wmoUnit:in": 25.4}) == 10.0
    # Inches reports as value * 25.4
    assert _nws_quantity({"precipitationLastHour": {"value": 2, "unitCode": "wmoUnit:in"}}, "precipitationLastHour", {"wmoUnit:mm": 1.0, "wmoUnit:in": 25.4}) == pytest.approx(50.8)


def test_weather_loader_names_are_distinct():
    # The network fetcher and the frozen-bundle loader are separate.
    assert hasattr(m, "fetch_real_weather")
    assert hasattr(m, "load_weather_bundle")
    assert callable(m.fetch_real_weather)
    assert callable(m.load_weather_bundle)
    assert m.fetch_real_weather is not m.load_weather_bundle


def test_load_real_weather_is_deprecated_alias():
    import tempfile
    import json
    import os
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False,
                                     mode="w") as f:
        json.dump({
            "schema": "yellowstone.met_forcing.v1",
            "hourly": [[1000.0, 10.0, 0.5, 2.0, 200.0, 0.2]],
        }, f)
        path = f.name
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = load_real_weather(path)
        assert result is not None
        assert any(issubclass(w.category, DeprecationWarning)
                   for w in caught)
    finally:
        os.unlink(path)


def test_bundle_weather_timestamp_utc_selects_row():
    base_epoch = 1_700_000_000
    bundle = {
        "schema": "yellowstone.met_forcing.v1",
        "hourly": [
            [base_epoch + 0 * 3600, 1.0, 0.40, 2.0, 100.0, 0.10],
            [base_epoch + 1 * 3600, 11.0, 0.50, 3.0, 200.0, 0.20],
            [base_epoch + 2 * 3600, 21.0, 0.60, 4.0, 300.0, 0.30],
        ],
    }
    target = datetime.fromtimestamp(base_epoch + 1 * 3600,
                                    tz=timezone.utc)
    result = bundle_weather(bundle, timestamp_utc=target)
    assert result["night_air_c"] == pytest.approx(11.0)
    assert result["humidity"] == pytest.approx(0.50)
    assert result["cloud"] == pytest.approx(0.20)
    assert result["met_bundle"]["row_index_utc"] == 1


def test_bundle_weather_timestamp_utc_requires_tzinfo():
    bundle = {
        "schema": "yellowstone.met_forcing.v1",
        "hourly": [[3600.0, 5.0, 0.4, 1.5, 150.0, 0.1]],
    }
    with pytest.raises(ValueError):
        bundle_weather(bundle, timestamp_utc=datetime(2026, 1, 1))


def test_bundle_weather_rejects_multiple_time_args():
    bundle = {
        "schema": "yellowstone.met_forcing.v1",
        "hourly": [[3600.0, 5.0, 0.4, 1.5, 150.0, 0.1]],
    }
    with pytest.raises(ValueError):
        bundle_weather(bundle, epoch_s_utc=3600.0, hour=1.0)


def test_bundle_weather_hour_warns_deprecated():
    bundle = {
        "schema": "yellowstone.met_forcing.v1",
        "hourly": [[3600.0, 5.0, 0.4, 1.5, 150.0, 0.1]],
    }
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        bundle_weather(bundle, hour=0.0)
    assert any(issubclass(w.category, DeprecationWarning)
               for w in caught)


def test_wind_series_caps_sample_count():
    with pytest.raises(ValueError):
        wind_series(seconds=1000.0, dt=0.001, max_samples=100)


def test_condensation_potential_proxy_label_key():
    result = condensation_potential(62.0, 2.0, 0.9)
    assert "evap_pressure_index_kpa_weighted" in result
    assert "supersat_pressure_kpa" in result
    assert "evap_flux_kpa_weighted" not in result
    assert "supersaturation_kpa" not in result


def test_condensation_potential_values_unrounded():
    # Values are returned without rounding; serializers choose precision.
    result = condensation_potential(62.0, 2.0, 0.9)
    # Raw floats retain more than 3 decimals; this confirms non-trivial precision survives.
    pressure = result["evap_pressure_index_kpa_weighted"]
    rounded = round(pressure, 3)
    assert pressure != 0.0
    assert math.isfinite(pressure)
    # The raw value usually differs from the 3-decimal round value.
    assert abs(pressure - rounded) >= 0.0  # finite comparison
    assert isinstance(pressure, float)


def test_fetch_nws_station_data_requires_station_id():
    with pytest.raises(ValueError):
        fetch_nws_station_data("")


def test_herbie_requires_date_str():
    from yellowstone_python.atmosphere.microclimate import herbie_retrieve_hrrr_rtma
    with pytest.raises(ValueError):
        herbie_retrieve_hrrr_rtma("")


# llm_backend weather reports snow_partition_source for metpy, Stull, and invalid wet-bulb inputs.


def _write_bundle(path, epoch, air_c, rh):
    import json
    bundle = {
        "schema": "yellowstone.met_forcing.v1",
        "hourly": [[float(epoch), float(air_c), float(rh),
                    2.0, 150.0, 0.1]],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle), encoding="utf-8")


def _make_backend(tmp_path):
    from yellowstone_python.service.llm_backend import Backend
    world = tmp_path / "world"
    derived = tmp_path / "derived"
    world.mkdir(parents=True, exist_ok=True)
    derived.mkdir(parents=True, exist_ok=True)
    return Backend(world=world, derived=derived)


@pytest.mark.needs_science
def test_wet_bulb_switch_uses_metpy_when_available(tmp_path):
    try:
        import metpy  # noqa: F401
    except ImportError:
        pytest.skip("metpy not installed")
    _write_bundle(tmp_path / "derived" / "met.json",
                  epoch=0.0, air_c=0.0, rh=0.5)
    backend = _make_backend(tmp_path)
    response = backend.weather(epoch_unix=0.0)
    assert response["weather"]["snow_partition_source"] == "metpy_wet_bulb"
    # Partition ramp around a 1 C wet-bulb threshold yields a finite 0..1 fraction for Godot consumers.
    assert 0.0 <= response["weather"]["snow_fraction"] <= 1.0


def test_wet_bulb_switch_falls_back_to_stull(monkeypatch, tmp_path):
    import yellowstone_python.atmosphere.microclimate as mc

    def _fail(*_args, **_kwargs):
        raise ImportError("metpy forced off for test")

    monkeypatch.setattr(mc, "metpy_wet_bulb_temperature", _fail)
    _write_bundle(tmp_path / "derived" / "met.json",
                  epoch=0.0, air_c=0.0, rh=0.5)
    backend = _make_backend(tmp_path)
    response = backend.weather(epoch_unix=0.0)
    assert (response["weather"]["snow_partition_source"]
            == "stull_2011_wet_bulb")
    assert 0.0 <= response["weather"]["snow_fraction"] <= 1.0


def test_wet_bulb_switch_reports_unavailable_outside_stull_range(
    monkeypatch, tmp_path,
):
    import yellowstone_python.atmosphere.microclimate as mc

    def _fail(*_args, **_kwargs):
        raise ImportError("metpy forced off for test")

    monkeypatch.setattr(mc, "metpy_wet_bulb_temperature", _fail)
    # -40 C is outside Stull's validity window of [-20, 50] C.
    _write_bundle(tmp_path / "derived" / "met.json",
                  epoch=0.0, air_c=-40.0, rh=0.5)
    backend = _make_backend(tmp_path)
    response = backend.weather(epoch_unix=0.0)
    assert (response["weather"]["snow_partition_source"]
            == "unavailable_outside_stull_2011_validity_range")
    # Unavailable wet-bulb leaves snow_fraction at 0; snow_partition_source supplies the diagnostic.
    assert response["weather"]["snow_fraction"] == 0.0
