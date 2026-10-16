"""Tests for tools/audit_provenance.py (synthetic/offline only)."""

import json

import pytest
import sys
from pathlib import Path

from tools.audit_provenance import audit_dir, audit_file

TOOL_DIR = Path(__file__).resolve().parents[1]


def _write(directory: Path, name: str, doc: dict) -> Path:
    p = directory / name
    p.write_text(json.dumps(doc))
    return p


def _good(name="good.json"):
    return {"schema": "yellowstone.firehole_obs.v1",
            "status": "measured_remote_not_calibrated"}


@pytest.mark.needs_network_inputs
def test_all_live_pass(tmp_path):
    # The audit vocabulary is measured against the live derived/ directory.
    live = sorted((TOOL_DIR / "derived").glob("*.json"))
    if not live:
        pytest.skip(f"frozen derived artifacts missing: {TOOL_DIR / 'derived'}")
    for src in live:
        (tmp_path / src.name).write_text(src.read_text())
    report = audit_dir(tmp_path)
    by_file = {}
    for f in report["failures"]:
        by_file.setdefault(f["file"], []).append(f["rule"])
    assert by_file == {}, by_file
    assert report["passed"] is True


@pytest.mark.needs_network_inputs
def test_sinter_cull_has_status():
    """Each sinter cull artifact carries a status in STATUS_VOCABULARY."""
    from tools.audit_provenance import STATUS_VOCABULARY
    for name in ("sinter_grass_cull.json", "sinter_tree_cull.json"):
        path = TOOL_DIR / "derived" / name
        if not path.is_file():
            pytest.skip(f"frozen artifact missing: {path}")
        doc = json.loads(path.read_text())
        assert doc.get("status") in STATUS_VOCABULARY, name


def test_unknown_status_fails(tmp_path):
    p = _write(tmp_path, "x.json", {"schema": "yellowstone.firehole_obs.v1",
                                    "status": "calibrated"})
    failures = audit_file(p)
    assert any(f["rule"] == "unknown-status" for f in failures)


def test_comma_default_flagged(tmp_path):
    p = _write(tmp_path, "x.json", {"schema": "yellowstone.firehole_obs.v1",
                                    "status": 'illustrative. calibrated'})
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


def test_sidecar_rule_matches_check_provenance(tmp_path):
    """Pin the sidecar keys against the shared validation contract."""
    from tools.audit_provenance import SIDECAR_KEYS
    from yellowstone_python.validation.contracts import check_provenance

    doc = {"schema": "yellowstone.firehole_obs.v1",
           "status": "measured_remote_not_calibrated",
           "world_id": "yellowstone_midway", "code_rev": "abc",
           "parameter_provenance": {}, "sources": {},
           "contract_version": "0.1.0"}
    assert check_provenance(doc) == []
    assert audit_file(_write(tmp_path, "x.json", doc)) == []
    for key in SIDECAR_KEYS:
        if key == "contract_version":
            continue
        bad = dict(doc)
        bad.pop(key)
        p = _write(tmp_path, f"missing_{key}.json", bad)
        failures = audit_file(p)
        assert any(f["rule"] == "incomplete-sidecar" and key in f["found"]
                   for f in failures), failures


def test_derived_disk_flag(tmp_path):
    _write(tmp_path, "x.json", _good())
    report = __import__("tools.audit_provenance",
                        fromlist=["audit_dir"]).audit_dir(tmp_path)
    assert "disk" not in report
    import subprocess
    out = tmp_path / "report.json"
    r = subprocess.run([sys.executable, str(TOOL_DIR / "tools" /
                                            "audit_provenance.py"),
                        "--dir", str(tmp_path), "--out", str(out),
                        "--derived-disk"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    doc = json.loads(out.read_text())
    assert "disk" in doc and doc["disk"]["bytes"] > 0


def test_audit_stores_flag(tmp_path):
    import sqlite3
    _write(tmp_path, "x.json", _good())
    store = tmp_path / "analysis_abcd1234.sqlite"
    con = sqlite3.connect(store)
    con.execute("CREATE TABLE meta (key TEXT, value TEXT)")
    con.execute("INSERT INTO meta VALUES (?, ?)", ("build_id", "test"))
    con.commit()
    con.close()
    import subprocess
    out = tmp_path / "report.json"
    r = subprocess.run([sys.executable, str(TOOL_DIR / "tools" /
                                            "audit_provenance.py"),
                        "--dir", str(tmp_path), "--out", str(out),
                        "--audit-stores"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    doc = json.loads(out.read_text())
    assert "stores" in doc and len(doc["stores"]) == 1
    assert doc["stores"][0]["meta"]["build_id"] == "test"


def test_audit_stores_source_classifications(tmp_path):
    """source_shas records emit OK / STALE_SOURCE / MISSING_BUILD_DIR."""
    import hashlib
    import sqlite3
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    good = sources_dir / "good.bin"
    good.write_bytes(b'{"a": 1}')
    good_sha = hashlib.sha256(good.read_bytes()).hexdigest()
    stale = sources_dir / "stale.bin"
    stale.write_bytes(b'{"a": 2}')
    stale_sha = "f" * 64
    missing_dir = tmp_path / "no_build_dir" / "missing.bin"
    source_records = [
        {"path": str(good), "basename": "good.bin", "sha256": good_sha,
         "bytes": good.stat().st_size},
        {"path": str(stale), "basename": "stale.bin", "sha256": stale_sha,
         "bytes": stale.stat().st_size},
        {"path": str(missing_dir), "basename": "missing.bin",
         "sha256": good_sha, "bytes": 0},
    ]
    store = tmp_path / "analysis_src1.sqlite"
    con = sqlite3.connect(store)
    con.execute("CREATE TABLE meta (key TEXT, value TEXT)")
    con.execute("INSERT INTO meta VALUES (?, ?)",
                ("source_shas", json.dumps(source_records)))
    con.commit()
    con.close()
    from tools.audit_provenance import _audit_store
    audit = _audit_store(store)
    statuses = [row["status"] for row in audit["source_audit"]]
    assert statuses.count("OK") == 1
    assert statuses.count("STALE_SOURCE") == 1
    assert statuses.count("MISSING_BUILD_DIR") == 1


def test_audit_stores_rejects_unknown_tables(tmp_path):
    import sqlite3
    store = tmp_path / "analysis_badtbl.sqlite"
    con = sqlite3.connect(store)
    con.execute("CREATE TABLE meta (key TEXT, value TEXT)")
    con.execute("CREATE TABLE pirates (name TEXT)")
    con.commit()
    con.close()
    from tools.audit_provenance import _audit_store
    audit = _audit_store(store)
    assert "pirates" in audit.get("unknown_tables", [])


@pytest.mark.parametrize("status", [
    "authored_estimate_from_usgs_3dep_dem",
    "illustrative_river_entry_forcing_not_measured",
])
def test_strict_accepts_explicit_nested_geometry_and_forcing_classes(tmp_path, status):
    doc = _good()
    doc["parameter_provenance"] = {"source": {"status": status}}
    p = _write(tmp_path, "replay.json", doc)
    assert audit_file(p, strict=True) == []
    doc["status"] = status
    p = _write(tmp_path, "top.json", doc)
    assert any(f["rule"] == "unknown-status" for f in audit_file(p, strict=True))


@pytest.mark.parametrize("status", [
    "measured_estimate_from_usgs_3dep_dem",
    "calibrated_river_entry_forcing",
    "illustrative_river_entry_forcing",
])
def test_strict_rejects_unregistered_nested_source_claims(tmp_path, status):
    doc = _good()
    doc["parameter_provenance"] = {"source": {"status": status}}
    p = _write(tmp_path, "replay.json", doc)
    assert any(f["rule"] == "unknown-nested-status" for f in audit_file(p, strict=True))
