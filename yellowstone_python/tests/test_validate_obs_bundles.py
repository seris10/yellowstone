"""Tests for tools/validate_obs_bundles.py (synthetic/offline only)."""

import json
import subprocess
import sys
from pathlib import Path

from tools.validate_obs_bundles import gate_bundle

TOOL = Path(__file__).resolve().parents[1] / "tools" / "validate_obs_bundles.py"
LIVE_FIREHOLE = Path(__file__).resolve().parents[1] / "derived" / \
    "firehole_obs.json"
LIVE_SNOTEL = Path(__file__).resolve().parents[1] / "derived" / \
    "snotel_obs.json"


def _firehole(n_per=3, step=900.0, gap_at=None):
    t0 = 1790990100.0
    series = {}
    for key, base in (("temperature_c", 10.0), ("discharge_m3_s", 1.07)):
        pts = [[t0 + i * step, base] for i in range(n_per)]
        if gap_at is not None and key == "temperature_c":
            pts[gap_at][0] += 7200.0
        series[key] = pts
    sites = {s: {"series": dict(series)} for s in ("06036805", "06036905")}
    met = {"hourly": [[t0 + i * 3600.0, 10.0, 0.4, 3.0, 200.0, 0.1]
                      for i in range(3)]}
    return {"schema": "yellowstone.firehole_obs.v1",
            "status": "measured_remote_not_calibrated",
            "sites": sites, "met": met}


def _snow(day0_wteq=0.0, tavg_nulls=(), end="2026-07-31"):
    days = {}
    d = "2025-10-01"
    vals = {"PRCP": 0.0, "SNWD": 0.0, "TAVG": 30.0, "TMAX": 40.0,
            "TMIN": 25.0, "WTEQ": 0.0}
    cur = [2025, 10, 1]
    out = {}
    import datetime as dt
    start = dt.date(2025, 10, 1)
    stop = dt.date(*map(int, end.split("-")))
    day = start
    first = True
    while day <= stop:
        row = dict(vals)
        if first:
            row["WTEQ"] = day0_wteq
            first = False
        if day.isoformat() in tavg_nulls:
            row["TAVG"] = None
        out[day.isoformat()] = row
        day += dt.timedelta(days=1)
    return {"schema": "yellowstone.snotel_obs.v1",
            "status": "measured_remote_not_calibrated",
            "sites": {"609:MT:SNTL": {"days": out}}}


def test_firehole_known_good_passes():
    v = gate_bundle(_firehole(), "firehole")
    assert v["passed"] is True
    assert v["schema"] == "yellowstone.obs_bundle_verdict.v1"


def test_firehole_gap_fails():
    v = gate_bundle(_firehole(gap_at=1), "firehole")
    assert v["passed"] is False
    assert any(not c["passed"] and "gap" in c["detail"].lower()
               for c in v["checks"])


def test_firehole_wrong_schema_fails():
    b = _firehole()
    b["schema"] = "yellowstone.snotel_obs.v1"
    v = gate_bundle(b, "firehole")
    assert v["passed"] is False
    assert any(c["name"] == "schema" and not c["passed"] for c in v["checks"])


def test_snow_spinup_refusal():
    v = gate_bundle(_snow(day0_wteq=5.0), "snow")
    assert v["passed"] is False
    assert any("spinup" in c["name"] and not c["passed"] for c in v["checks"])


def test_snow_tavg_long_gap_fails():
    nulls = tuple(f"2026-01-0{d}" for d in range(1, 6))
    v = gate_bundle(_snow(tavg_nulls=nulls), "snow")
    assert v["passed"] is False
    assert any("tavg-fill" in c["name"] and not c["passed"] for c in v["checks"])


def test_snow_no_holdout_span_fails():
    v = gate_bundle(_snow(end="2026-02-01"), "snow")
    assert v["passed"] is False
    assert any("holdout-span" in c["name"] and not c["passed"]
               for c in v["checks"])


def test_verdict_atomic_write(tmp_path):
    out = tmp_path / "verdict.json"
    b = tmp_path / "bundle.json"
    b.write_text(json.dumps(_firehole()))
    r = subprocess.run([sys.executable, str(TOOL), "--bundle", str(b),
                        "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0
    doc = json.loads(out.read_text())
    assert doc["schema"] == "yellowstone.obs_bundle_verdict.v1"
    assert doc["passed"] is True


def test_live_bundles_pass():
    fire = json.loads(LIVE_FIREHOLE.read_text())
    snow = json.loads(LIVE_SNOTEL.read_text())
    assert gate_bundle(fire, "firehole")["passed"] is True
    assert gate_bundle(snow, "snow")["passed"] is True


def test_verdict_records_bundle_fetched_at_utc():
    bundle = _firehole()
    bundle["fetched_at_utc"] = "2026-10-10T00:00:00+00:00"
    v = gate_bundle(bundle, "firehole")
    assert v["bundle_fetched_at_utc"] == "2026-10-10T00:00:00+00:00"
    bundle = _firehole(gap_at=1)
    bundle["fetched_at_utc"] = "2026-10-10T00:00:00+00:00"
    v = gate_bundle(bundle, "firehole")
    assert v["passed"] is False
    assert v["bundle_fetched_at_utc"] == "2026-10-10T00:00:00+00:00"


def test_unknown_schema_label():
    bundle = _firehole()
    bundle["schema"] = "yellowstone.something.v1"
    v = gate_bundle(bundle, "auto")
    assert v["passed"] is False
    assert any(c["name"] == "unknown-schema" for c in v["checks"])


def test_all_consumer_propagates_bundle_fetched_at_utc(tmp_path):
    bundle = _firehole()
    bundle["fetched_at_utc"] = "2026-10-10T00:00:00+00:00"
    b = tmp_path / "bundle.json"
    b.write_text(json.dumps(bundle))
    out = tmp_path / "verdict.json"
    r = subprocess.run([sys.executable, str(TOOL), "--bundle", str(b),
                        "--out", str(out), "--consumer", "all"],
                       capture_output=True, text=True, check=False)
    doc = json.loads(out.read_text())
    assert doc["bundle_fetched_at_utc"] == "2026-10-10T00:00:00+00:00"
    assert all(v.get("bundle_fetched_at_utc") ==
               "2026-10-10T00:00:00+00:00"
               for v in doc["verdicts"].values())
    assert r.returncode in (0, 1)
