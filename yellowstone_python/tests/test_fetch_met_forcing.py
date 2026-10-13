"""Tests for tools/fetch_met_forcing.py + firehole wrapper (offline only)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.fetch_met_forcing import SCHEMA_MET, build_met_rows, fetch_met


def _met_json():
    return {"elevation": 2240.0,
            "hourly": {"time": ["2026-10-09T00:00", "2026-10-09T01:00"],
                       "temperature_2m": [16.8, 15.0],
                       "relative_humidity_2m": [31.0, 40.0],
                       "wind_speed_10m": [16.5, 10.0],
                       "shortwave_radiation": [203.0, 100.0],
                       "cloud_cover": [0.0, 50.0]}}


def test_row_builder_conversions():
    out = build_met_rows(_met_json())
    assert out["elevation_m"] == 2240.0
    r0 = out["hourly"][0]
    assert r0[1] == 16.8
    assert r0[2] == pytest.approx(0.31)
    assert r0[3] == pytest.approx(16.5 / 3.6)
    assert r0[4] == 203.0
    assert r0[5] == pytest.approx(0.0)
    assert all(len(r) == 6 for r in out["hourly"])


def test_incomplete_table_raises():
    bad = _met_json()
    bad["hourly"]["cloud_cover"] = [0.0]
    with pytest.raises(RuntimeError, match="incomplete hourly table"):
        build_met_rows(bad)


def test_days_range_rejected():
    import subprocess
    r = subprocess.run([sys.executable, str(Path(__file__).resolve(
        ).parents[1] / "tools" / "fetch_met_forcing.py"),
        "--lat", "44.4", "--lon", "-110.8", "--days", "17",
        "--out", "/tmp/x.json"], capture_output=True, text=True)
    assert r.returncode == 2


def test_wrapper_backcompat(monkeypatch):
    import tools.fetch_firehole_obs as f
    import tools.fetch_met_forcing as mf
    monkeypatch.setattr(mf, "_get_json", lambda url: _met_json())
    out = f.fetch_met(44.459333, -110.822272, 7)
    assert {"url", "elevation_m", "hourly"}.issubset(set(out))
    assert out["hourly"][0][1] == 16.8
    assert "past_days=7" in out["url"]


def test_consumer_indices_unchanged(monkeypatch):
    import datetime
    import tools.fetch_met_forcing as mf
    from yellowstone_python.replay.calibrate import _fit_forcing_arrays
    t0 = 1790990100.0
    stamps = [(datetime.datetime.fromtimestamp(t0 + i * 3600.0,
                                               datetime.timezone.utc)
               .strftime("%Y-%m-%dT%H:%M")) for i in range(6)]

    def fake(url):
        doc = _met_json()
        n = len(stamps)
        doc["hourly"] = {"time": stamps,
                         "temperature_2m": [10.0] * n,
                         "relative_humidity_2m": [40.0] * n,
                         "wind_speed_10m": [10.0] * n,
                         "shortwave_radiation": [200.0] * n,
                         "cloud_cover": [10.0] * n}
        return doc

    monkeypatch.setattr(mf, "_get_json", fake)
    met = mf.fetch_met(44.459333, -110.822272, 7)
    bundle = {"met": {"hourly": met["hourly"]},
              "sites": {"06036805": {"series": {
                  "temperature_c": [[t0 + i * 900.0, 10.0]
                                    for i in range(20)],
                  "discharge_m3_s": [[t0 + i * 900.0, 1.07]
                                     for i in range(20)]}}}}
    got = _fit_forcing_arrays(bundle)
    assert "met_series" in got


def test_full_url_recorded():
    assert SCHEMA_MET == "yellowstone.met_forcing.v1"
    import inspect
    import tools.fetch_met_forcing as mf
    src = inspect.getsource(mf.main)
    assert "request" in src and '"url": result["url"]' in src


def test_vars_wrong_width_rejected():
    import subprocess
    r = subprocess.run([sys.executable, str(Path(__file__).resolve(
        ).parents[1] / "tools" / "fetch_met_forcing.py"),
        "--lat", "44.4", "--lon", "-110.8", "--days", "7",
        "--vars", "temperature_2m,cloud_cover",
        "--out", "/tmp/x.json"], capture_output=True, text=True)
    assert r.returncode == 2


def _met_json_with_precip():
    doc = _met_json()
    doc["hourly"]["precipitation"] = [0.0, 1.25]
    return doc


def test_build_met_rows_emits_hourly_origin_and_precipitation():
    """fixes-33 item 7: hourly origin plus a precipitation sidecar series."""
    out = build_met_rows(_met_json_with_precip())
    assert out["hourly"][0][0] == out["hourly_origin_epoch_s"]
    assert out["precipitation_mm"] == [0.0, 1.25]
    assert all(len(r) == 6 for r in out["hourly"])


def test_build_met_rows_absent_precip_is_none():
    """No precipitation column -> precipitation_mm is None, origin set."""
    out = build_met_rows(_met_json())
    assert out["precipitation_mm"] is None
    assert out["hourly_origin_epoch_s"] == out["hourly"][0][0]


def test_build_met_rows_precip_length_mismatch_raises():
    bad = _met_json_with_precip()
    bad["hourly"]["precipitation"] = [0.0]
    with pytest.raises(RuntimeError, match="precipitation column length"):
        build_met_rows(bad)


def test_fetch_met_forcing_adds_precipitation_to_query(monkeypatch):
    """The outgoing URL must include the precipitation variable."""
    import tools.fetch_met_forcing as mf

    captured_url = {}

    def fake(url):
        captured_url["url"] = url
        return _met_json_with_precip()

    monkeypatch.setattr(mf, "_get_json", fake)
    out = mf.fetch_met_forcing(44.459333, -110.822272, 7)
    assert "precipitation" in captured_url["url"]
    assert out["precipitation_mm"] == [0.0, 1.25]
    assert out["hourly_origin_epoch_s"] == out["hourly"][0][0]
