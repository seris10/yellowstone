"""Tests for tools/compare_bundles.py (synthetic/offline only)."""

import json
import sys
from pathlib import Path

from tools.compare_bundles import compare_bundles

LIVE = Path(__file__).resolve().parents[1] / "derived" / \
    "firehole_obs.json"


def _bundle(q_shift=0.0, t_shift=0.0):
    t0 = 1790990100.0
    series = {"discharge_m3_s": [[t0 + i * 900.0, 1.07 + q_shift]
                                 for i in range(5)],
              "temperature_c": [[t0 + i * 900.0, 10.0 + t_shift]
                                for i in range(5)]}
    return {"schema": "yellowstone.firehole_obs.v1",
            "status": "measured_remote_not_calibrated",
            "fetched_at_utc": "2026-10-10T00:00:00+00:00",
            "sites": {"06036805": {"series": dict(series)},
                      "06036905": {"series": dict(series)}},
            "met": {"hourly": [[t0 + i * 3600.0, 10.0, 0.4, 3.0, 200.0, 0.1]
                               for i in range(3)]}}


def test_identical_passes():
    r = compare_bundles(_bundle(), _bundle(), 0.05, 0.5)
    assert r["passed"] is True
    assert r["verdict"] == "identical"


def test_small_revision_passes():
    r = compare_bundles(_bundle(), _bundle(q_shift=0.02, t_shift=0.2),
                        0.05, 0.5)
    assert r["passed"] is True
    assert r["verdict"] == "within-tolerance-revision"


def test_q_drift_fails():
    r = compare_bundles(_bundle(), _bundle(q_shift=0.15), 0.05, 0.5)
    assert r["passed"] is False
    assert any("discharge" in m["element"] and not m["passed"]
               for m in r["metrics"])


def test_schema_mismatch_fails():
    new = _bundle()
    new["schema"] = "yellowstone.snotel_obs.v1"
    r = compare_bundles(_bundle(), new, 0.05, 0.5)
    assert r["passed"] is False
    assert r["error"].startswith("schema-mismatch")


def test_empty_is_noninformative():
    old, new = _bundle(), _bundle()
    old["sites"]["06036805"]["series"]["discharge_m3_s"] = []
    r = compare_bundles(old, new, 0.05, 0.5)
    assert "06036805/discharge_m3_s" in r["non_informative"]
    assert r["passed"] is True


def test_no_overlap_fails_informatively():
    old, new = _bundle(), _bundle()
    new["sites"]["06036805"]["series"]["temperature_c"] = [
        [1890990100.0 + i * 900.0, 10.0] for i in range(5)]
    new["sites"]["06036905"]["series"]["temperature_c"] = [
        [1890990100.0 + i * 900.0, 10.0] for i in range(5)]
    new["met"]["hourly"] = []
    r = compare_bundles(old, new, 0.05, 0.5)
    assert r["passed"] is False
    assert any(m.get("detail") == "no-overlap" for m in r["metrics"])


def test_live_self_comparison():
    live = json.loads(LIVE.read_text())
    r = compare_bundles(live, live, 0.05, 0.5)
    assert r["passed"] is True
    assert r["verdict"] == "identical"


def test_cli_schema_mismatch_clean_exit(tmp_path):
    import subprocess
    old, new = tmp_path / "o.json", tmp_path / "n.json"
    old.write_text(json.dumps(_bundle()))
    bad = _bundle()
    bad["schema"] = "yellowstone.snotel_obs.v1"
    new.write_text(json.dumps(bad))
    tool = Path(__file__).resolve().parents[1] / "tools" / "compare_bundles.py"
    r = subprocess.run([sys.executable, str(tool), "--old", str(old),
                        "--new", str(new)], capture_output=True, text=True)
    assert r.returncode == 1
    assert "schema-mismatch" in r.stdout
    assert "Traceback" not in r.stdout and "Traceback" not in r.stderr


def test_both_empty_no_informative():
    old, new = _bundle(), _bundle()
    for site in ("06036805", "06036905"):
        old["sites"][site]["series"] = {"discharge_m3_s": [],
                                        "temperature_c": []}
        new["sites"][site]["series"] = {"discharge_m3_s": [],
                                        "temperature_c": []}
    old["met"]["hourly"] = []
    new["met"]["hourly"] = []
    r = compare_bundles(old, new, 0.05, 0.5)
    assert r["passed"] is False
    assert r["verdict"] == "no-informative-data"


def test_report_carries_provenance_note():
    r = compare_bundles(_bundle(), _bundle(), 0.05, 0.5)
    assert "provenance_note" in r
    assert "fetched_at_utc" in r["provenance_note"]


def test_window_shift_reported():
    old = _bundle()
    new = _bundle()
    t0 = old["sites"]["06036805"]["series"]["temperature_c"][0][0]
    new["sites"]["06036805"]["series"]["temperature_c"] = [
        [t0 + 7200.0 + i * 900.0, 10.0] for i in range(5)]
    r = compare_bundles(old, new, 0.05, 0.5)
    for m in r["metrics"]:
        if m["element"] == "06036805/temperature_c":
            assert m.get("window_shift_s") == 7200.0
            return
    raise AssertionError("06036805/temperature_c metric missing")


def test_snotel_cli_tolerances_override(tmp_path):
    """CLI flags thread SNOTEL per-code tolerances through compare_bundles."""
    import subprocess
    old = {"schema": "yellowstone.snotel_obs.v1",
           "status": "measured_remote_not_calibrated",
           "fetched_at_utc": "2026-10-10T00:00:00+00:00",
           "sites": {"609:MT:SNTL": {"days": {
               "2026-01-01": {"WTEQ": 10.0, "SNWD": 25.0, "PRCP": 1.0,
                              "TAVG": 30.0, "TMAX": 40.0, "TMIN": 20.0},
               "2026-01-02": {"WTEQ": 10.5, "SNWD": 25.0, "PRCP": 1.0,
                              "TAVG": 30.0, "TMAX": 40.0, "TMIN": 20.0}}}}}
    new = json.loads(json.dumps(old))
    new["sites"]["609:MT:SNTL"]["days"]["2026-01-01"]["WTEQ"] = 11.0
    new["sites"]["609:MT:SNTL"]["days"]["2026-01-02"]["WTEQ"] = 11.5
    op = tmp_path / "o.json"
    np_ = tmp_path / "n.json"
    op.write_text(json.dumps(old))
    np_.write_text(json.dumps(new))
    tool = Path(__file__).resolve().parents[1] / "tools" / "compare_bundles.py"
    # Default tolerance 2.0 inches: a 1-inch WTEQ step passes.
    r = subprocess.run([sys.executable, str(tool), "--old", str(op),
                        "--new", str(np_)], capture_output=True, text=True,
                       check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    # At tolerance 0.5 inch the WTEQ step fails.
    r = subprocess.run([sys.executable, str(tool), "--old", str(op),
                        "--new", str(np_), "--wteq-abs-tol-in", "0.5"],
                       capture_output=True, text=True, check=False)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "WTEQ" in r.stdout
