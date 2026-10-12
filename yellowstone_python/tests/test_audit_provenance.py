"""Tests for tools/audit_provenance.py (synthetic/offline only)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.audit_provenance import audit_dir, audit_file

TOOL_DIR = Path(__file__).resolve().parents[1]


def _write(directory: Path, name: str, doc: dict) -> Path:
    p = directory / name
    p.write_text(json.dumps(doc))
    return p


def _good(name="good.json"):
    return {"schema": "yellowstone.firehole_obs.v1",
            "status": "measured_remote_not_calibrated"}


def test_all_live_pass_except_known(tmp_path):
    # The audit vocabulary is measured against the live derived/ directory, not
    # a stale copy under tools/. Point at the real one (sibling of tests/).
    live = sorted((TOOL_DIR / "derived").glob("*.json"))
    assert live, "derived/ must exist for this test"
    for src in live:
        (tmp_path / src.name).write_text(src.read_text())
    report = audit_dir(tmp_path)
    by_file = {}
    for f in report["failures"]:
        by_file.setdefault(f["file"], []).append(f["rule"])
    assert by_file.get("sinter_grass_cull.json") == \
        ["missing-status"], by_file
    assert by_file.get("sinter_tree_cull.json") == \
        ["missing-status"], by_file
    assert "usgs_06036805.json" not in by_file
    assert "llm_snapshot.json" not in by_file
    assert "river_state.json" not in by_file, by_file


def test_unknown_status_fails(tmp_path):
    p = _write(tmp_path, "x.json", {"schema": "yellowstone.firehole_obs.v1",
                                    "status": "calibrated"})
    failures = audit_file(p)
    assert any(f["rule"] == "unknown-status" for f in failures)


def test_comma_default_flagged(tmp_path):
    p = _write(tmp_path, "x.json", {"schema": "yellowstone.firehole_obs.v1",
                                    "status": "illustrative, not calibrated"})
    assert any(f["rule"] == "unknown-status" for f in audit_file(p))


def test_incomplete_sidecar_fails(tmp_path):
    doc = _good()
    doc["contract_version"] = "0.1.0"
    p = _write(tmp_path, "x.json", doc)
    assert any(f["rule"] == "incomplete-sidecar" for f in audit_file(p))


def test_stale_pointer_fails(tmp_path):
    _write(tmp_path, "a_obs.json",
           {"schema": "yellowstone.firehole_obs.v1",
            "status": "measured_remote_not_calibrated",
            "fetched_at_utc": "2026-10-10T00:00:00+00:00"})
    _write(tmp_path, "fit.json",
           {"schema": "yellowstone.reach_heat_fit.v1",
            "status": "fitted_not_validated_single_window",
            "fetched_at_utc": "2026-10-09T00:00:00+00:00"})
    report = audit_dir(tmp_path)
    assert any(f["rule"] == "stale-bundle-pointer" and f["file"] == "fit.json"
               for f in report["failures"])


def test_strict_nested(tmp_path):
    doc = _good()
    doc["inner"] = {"status": "whatever"}
    p = _write(tmp_path, "x.json", doc)
    assert audit_file(p) == []
    assert any(f["rule"] == "unknown-nested-status"
               for f in audit_file(p, strict=True))


def test_report_atomic(tmp_path):
    import subprocess
    out = tmp_path / "report.json"
    _write(tmp_path, "x.json", _good())
    r = subprocess.run([sys.executable, str(TOOL_DIR / "tools" /
                                            "audit_provenance.py"),
                        "--dir", str(tmp_path), "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    doc = json.loads(out.read_text())
    assert doc["schema"] == "yellowstone.provenance_audit.v1"
    assert doc["passed"] is True
