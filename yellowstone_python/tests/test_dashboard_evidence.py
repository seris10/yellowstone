"""Dashboard command receipts and stale-source status."""
import importlib.util
import json

from yellowstone_python.common.io import sha256_file


def test_dashboard_marks_changed_source_evidence_stale(repo_root, tmp_path):
    spec = importlib.util.spec_from_file_location("dashboard_builder", repo_root.parent / "dashboard/build_data.py")
    dashboard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dashboard)
    source = tmp_path / "model.py"
    source.write_text("water = 1\n")
    receipts = tmp_path / "evidence/receipts"
    receipts.mkdir(parents=True)
    receipt = {"name": "model-tests", "status": "executed_passed",
               "source_hashes": {"model.py": sha256_file(source)},
               "tests": {"executed": 2, "skipped": 1}, "started_utc": "2026-10-14T00:00:00Z"}
    (receipts / "receipt.json").write_text(json.dumps(receipt))
    assert dashboard.collect_receipts(tmp_path)[0]["status"] == "executed_passed"
    source.write_text("water = 2\n")
    assert dashboard.collect_receipts(tmp_path)[0]["status"] == "stale"
    assert dashboard.receipt_status({}, tmp_path) == "unavailable"
