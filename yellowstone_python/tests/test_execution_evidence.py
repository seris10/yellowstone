"""Portable content identity and source-bound command evidence."""
import copy

from yellowstone_python.common.io import sha256_file
from yellowstone_python.common.provenance import build_id
from tools.run_evidence import evidence_status, source_hashes, test_counts as read_test_counts


def test_content_identity_survives_relocation_and_discovery_method(tmp_path):
    first = {"world_root": str(tmp_path / "first"), "run_mode": "scenario",
             "replay": {"cross_sections_file": str(tmp_path / "first/sections.json"), "dt_s": 1.}}
    second = copy.deepcopy(first)
    second["world_root"] = str(tmp_path / "second")
    second["replay"]["cross_sections_file"] = str(tmp_path / "second/sections.json")
    a = {"code": "same_source", "config": "path_specific_hash", "code_hash_source": "fd",
         "external_inputs": {"cross_sections": {"path": str(tmp_path / "first/sections.json"),
             "exists": True, "sha256": "same_input"}}}
    b = copy.deepcopy(a)
    b["code_hash_source"] = "rglob"
    b["config"] = "different_path_specific_hash"
    b["external_inputs"]["cross_sections"]["path"] = str(tmp_path / "second/sections.json")
    assert build_id(first, a) == build_id(second, b)
    b["external_inputs"]["cross_sections"]["sha256"] = "changed_input"
    assert build_id(first, a) != build_id(second, b)


def test_source_or_fixture_change_makes_execution_evidence_stale(tmp_path):
    source = tmp_path / "model.py"
    fixture = tmp_path / "forcing.json"
    source.write_text("water = 1\n")
    fixture.write_text("{}")
    receipt = {"status": "executed_passed", "source_hashes": {"model.py": sha256_file(source)},
               "fixture_hashes": {"forcing.json": sha256_file(fixture)}}
    assert evidence_status(receipt, tmp_path) == "executed_passed"
    source.write_text("water = 2\n")
    assert evidence_status(receipt, tmp_path) == "stale"
    assert evidence_status({}, tmp_path) == "unavailable"


def test_skipped_cases_are_reported_separately_from_executed_cases(tmp_path):
    report = tmp_path / "tests.xml"
    report.write_text('<testsuites><testsuite><testcase/><testcase><skipped message="missing observation"/></testcase></testsuite></testsuites>')
    assert read_test_counts(report) == {"collected_reported": 2, "executed": 1, "skipped": 1,
                                    "failed": 0, "skip_reasons": ["missing observation"]}


def test_new_source_file_and_changed_log_invalidate_receipts(tmp_path):
    folder = tmp_path / "yellowstone_python/yellowstone_python"
    folder.mkdir(parents=True)
    (folder / "model.py").write_text("water = 1\n")
    log = tmp_path / "command.log"
    log.write_text("passed\n")
    receipt = {"status": "executed_passed", "source_hashes": source_hashes(tmp_path),
               "complete_source_inventory": True, "output": "command.log", "output_sha256": sha256_file(log)}
    assert evidence_status(receipt, tmp_path) == "executed_passed"
    log.write_text("altered\n")
    assert evidence_status(receipt, tmp_path) == "stale"
    log.write_text("passed\n")
    (folder / "additional_model.py").write_text("soil = 2\n")
    assert evidence_status(receipt, tmp_path) == "stale"
