"""Authenticate runtime evidence while identifying one unbundled dashboard input."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "yellowstone_python"))
from tools.run_evidence import evidence_status, source_hashes
from yellowstone_python.common.provenance import sha256_json

EXCLUDED_SOURCE = "dashboard/build_data.py"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def scoped(hashes):
    return {path: value for path, value in hashes.items() if path != EXCLUDED_SOURCE}


def excluded_observation(root, recorded=None):
    path = root / EXCLUDED_SOURCE
    current = digest(path) if path.is_file() else None
    result = subprocess.run(["git", "show", "HEAD:" + EXCLUDED_SOURCE], cwd=root,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    committed = hashlib.sha256(result.stdout).hexdigest() if result.returncode == 0 else None
    return {"path": EXCLUDED_SOURCE, "recorded_sha256": recorded, "observed_sha256": current,
            "head_sha256": committed, "uncommitted_outside_runtime": current != committed,
            "reason": "Dashboard inventory generator; absent from the numerical source-hash roots, production dependencies and portable Godot runtime."}


def audit_scope(root):
    roots = ["yellowstone_python/yellowstone_python", "yellowstone_python/tools",
             "yellowstone_midway/scripts", "yellowstone_midway/shaders", "yellowstone_midway/tools"]
    assert not any((root / EXCLUDED_SOURCE).is_relative_to(root / entry) for entry in roots)
    references = []
    needles = ("dashboard/build_data.py", "dashboard.build_data", "from dashboard", "import dashboard")
    for directory in roots:
        for path in (root / directory).rglob("*"):
            if not path.is_file() or path.suffix not in (".py", ".gd", ".gdshader", ".gdshaderinc"):
                continue
            for line_number, line in enumerate(path.read_text().splitlines(), 1):
                if any(needle in line for needle in needles):
                    relative = str(path.relative_to(root))
                    assert relative == "yellowstone_python/tools/run_evidence.py", (relative, line_number)
                    assert '"dashboard/build_data.py"' in line
                    references.append({"path": relative, "line": line_number, "role": "full-source receipt inventory only"})
    package_roots = ("assets", "data", "docs", "references", "scenes", "scripts", "shaders", "tools")
    assert EXCLUDED_SOURCE.split("/")[0] not in package_roots
    package = root / "work/Yellowstone-Forest-Spring-Update/PACKAGE.json"
    package_check = None
    if package.is_file():
        value = json.loads(package.read_text())
        assert not any(path == EXCLUDED_SOURCE or path.startswith("dashboard/") for path in value["artifact_hashes"])
        package_check = {"sha256": digest(package), "dashboard_files_bundled": 0}
    return {"excluded_paths": [EXCLUDED_SOURCE], "production_source_roots": roots,
            "direct_reference_scan": references, "package_runtime_roots": package_roots,
            "observed_package_check": package_check,
            "audited_source_hashes": {path: digest(root / path) for path in (
                "yellowstone_python/yellowstone_python/pipeline/inputs.py",
                "yellowstone_python/tools/package_demo.py", "yellowstone_python/tools/run_evidence.py")},
            "scope_helper_sha256": digest(Path(__file__)),
            "scope": "Exact-path runtime scope only. Global receipts remain unchanged. A dashboard exclusion cannot excuse a changed fixture, output, included source, recorded failure or recorded stale execution."}


def scoped_receipt_status(receipt, root):
    full = source_hashes(root)
    expected = receipt.get("source_hashes", {})
    status = "unavailable"
    if expected and receipt.get("status") == "executed_passed" and receipt.get("returncode") == 0:
        status = "executed_passed" if scoped(expected) == scoped(full) else "stale"
        artifacts = dict(receipt.get("fixture_hashes", {}))
        if receipt.get("output"):
            artifacts[receipt["output"]] = receipt.get("output_sha256")
        for relative, wanted in artifacts.items():
            path = root / relative
            if not path.is_file() or digest(path) != wanted:
                status = "stale"
    return {"status": status, "original_recorded_status": receipt.get("status", "unavailable"),
            "global_status": evidence_status(receipt, root),
            "recorded_full_source_identity": receipt.get("source_identity"),
            "scoped_runtime_identity": sha256_json(scoped(expected)) if expected else None,
            "current_full_source_identity": sha256_json(full),
            "excluded_source": excluded_observation(root, expected.get(EXCLUDED_SOURCE))}
