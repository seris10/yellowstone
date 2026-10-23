"""Source-bound command receipts with executed and skipped test counts."""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from yellowstone_python.common.io import sha256_file, write_json_atomic
from yellowstone_python.common.provenance import sha256_json


SOURCE_DIRECTORIES = ("yellowstone_python/yellowstone_python", "yellowstone_python/tools",
                      "yellowstone_python/tests", "yellowstone_python/configs",
                      "yellowstone_midway/scripts", "yellowstone_midway/shaders", "yellowstone_midway/tools")
SOURCE_FILES = ("yellowstone_python/requirements-reference.lock", "yellowstone_python/pyproject.toml",
                "dashboard/build_data.py", "yellowstone_midway/data/consumers.json",
                "yellowstone_midway/project.godot")
SOURCE_SUFFIXES = (".py", ".gd", ".gdshader", ".gdshaderinc", ".yaml", ".json")


SCOPES = {
    "python": {"directories": ("yellowstone_python/yellowstone_python", "yellowstone_python/tools", "yellowstone_python/tests", "yellowstone_python/configs", "yellowstone_python/examples", "hydrology"), "files": ("yellowstone_python/requirements-reference.lock", "yellowstone_python/pyproject.toml")},
    "godot": {"directories": ("yellowstone_midway/scripts", "yellowstone_midway/shaders", "yellowstone_midway/tools", "yellowstone_midway/tests"), "files": ("yellowstone_midway/data/consumers.json", "yellowstone_midway/project.godot")},
    "dashboard": {"directories": ("dashboard",), "files": ()},
}
SCOPES["combined"] = {key: tuple(value for scope in SCOPES.values() for value in scope[key]) for key in ("directories", "files")}
SCOPED_SUFFIXES = SOURCE_SUFFIXES + (".js", ".mjs", ".html", ".css", ".toml", ".lock", ".godot", ".tscn", ".csv")
EXCLUDED_PARTS = ("node_modules", "public", "__pycache__", ".git", ".venv")


def inventory_for(scope: str) -> dict:
    """Return an explicit named inventory without generated or dependency trees."""
    if scope not in SCOPES:
        raise ValueError("unknown evidence scope")
    return {**SCOPES[scope], "suffixes": SCOPED_SUFFIXES, "excluded_parts": EXCLUDED_PARTS}


def source_hashes(root: Path, inventory: dict | None = None) -> dict:
    """Hash maintained implementations, configurations and executable tests."""
    inventory = inventory or {"directories": SOURCE_DIRECTORIES, "files": SOURCE_FILES, "suffixes": SOURCE_SUFFIXES}
    hashes = {}
    for relative in inventory["directories"]:
        for path in sorted((root / relative).rglob("*")):
            if any(part in inventory.get("excluded_parts", ()) for part in path.relative_to(root).parts):
                continue
            if path.is_symlink() and inventory.get("excluded_parts"):
                raise ValueError("scoped evidence refuses source symlinks")
            if path.is_file() and path.suffix in inventory["suffixes"]:
                hashes[str(path.relative_to(root))] = sha256_file(path)
    for relative in inventory["files"]:
        path = root / relative
        if path.is_symlink() and inventory.get("excluded_parts"):
            raise ValueError("scoped evidence refuses source symlinks")
        if path.is_file():
            hashes[relative] = sha256_file(path)
    return hashes


def test_counts(path: Path) -> dict:
    """Report completed pytest cases separately from skips and failures."""
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    skipped = sum(case.find("skipped") is not None for case in cases)
    failed = sum(case.find("failure") is not None or case.find("error") is not None for case in cases)
    return {"collected_reported": len(cases), "executed": len(cases) - skipped,
            "skipped": skipped, "failed": failed,
            "skip_reasons": sorted({case.find("skipped").get("message", "") for case in cases if case.find("skipped") is not None})}


def evidence_status(receipt: dict, root: Path) -> str:
    """Resolve current execution evidence against source and fixture bytes."""
    if not receipt.get("source_hashes"):
        return "unavailable"
    if receipt.get("complete_source_inventory") and source_hashes(root, receipt.get("source_inventory")) != receipt["source_hashes"]:
        return "stale"
    artifacts = {**receipt["source_hashes"], **receipt.get("fixture_hashes", {})}
    if receipt.get("output"):
        artifacts[receipt["output"]] = receipt.get("output_sha256")
    for relative, expected in artifacts.items():
        path = root / relative
        if not path.is_file() or sha256_file(path) != expected:
            return "stale"
    return receipt.get("status", "unavailable")


def main() -> int:
    """Execute a command and persist its source-bound result and output."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--scope", choices=tuple(SCOPES), default="combined")
    parser.add_argument("--strict", action="store_true", help="return 2 when source changes during a successful command")
    parser.add_argument("--fixture", action="append", default=[])
    parser.add_argument("--junit")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required")
    root = Path(__file__).resolve().parents[2]
    inventory = inventory_for(args.scope)
    before = source_hashes(root, inventory)
    fixtures = {}
    for name in args.fixture:
        path = Path(name).resolve()
        fixtures[str(path.relative_to(root))] = sha256_file(path)
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout, end="")
    receipt = {"schema": "yellowstone.command_receipt.v2", "scope": args.scope, "strict": args.strict, "name": args.name,
               "command": command, "cwd": str(Path.cwd().relative_to(root)),
               "started_utc": start, "source_hashes": before, "complete_source_inventory": True,
               "source_inventory": inventory, "fixture_hashes": fixtures,
               "source_identity": sha256_json(before), "returncode": result.returncode,
               "status": "executed_passed" if result.returncode == 0 else "executed_failed"}
    if source_hashes(root, inventory) != before:
        receipt["status"] = "stale"
    if args.junit and Path(args.junit).is_file():
        receipt["tests"] = test_counts(Path(args.junit))
    try:
        receipt["source_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=root).strip()
    except (OSError, subprocess.CalledProcessError):
        receipt["source_commit"] = None
    identity = sha256_json(receipt)
    output = root / "evidence/receipts" / (identity + ".log")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.stdout)
    receipt["output"] = str(output.relative_to(root))
    receipt["output_sha256"] = sha256_file(output)
    write_json_atomic(output.with_suffix(".json"), receipt, indent=1)
    print("receipt:", output.with_suffix(".json").relative_to(root))
    return result.returncode or (2 if args.strict and receipt["status"] == "stale" else 0)


if __name__ == "__main__":
    sys.exit(main())
