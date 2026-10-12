"""Tests for tools/compare_bundles.py (synthetic/offline only)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
