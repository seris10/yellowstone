"""Public export selection for code and required project assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from yellowstone_python.common.io import write_json_atomic

PUBLIC_ROOTS = {"yellowstone_python", "yellowstone_midway", "yellowstone_atmosphere", "hydrology", "research"}
PRIVATE_PARTS = {".git", ".godot", ".venv", ".pytest_cache", "__pycache__", ".opencode",
                 "derived", "archive", "backups", "figs", "work", "outputs", "receipts",
                 "build", "dist", ".mypy_cache", ".ruff_cache", ".hypothesis", "worker_briefs", "research_notes"}
DOCUMENT_SUFFIXES = {".md", ".rst", ".txt", ".cff", ".ipynb", ".pdf", ".docx", ".pptx", ".xlsx"}
# Original third-party source documents retain their format specification and attribution.
PUBLIC_SOURCE_DOCUMENTS = {"yellowstone_midway/references/bsc5_ReadMe.txt"}
PUBLIC_ROOT_DOCUMENTS = {"LICENSE", "README.md", ".name-exceptions"}
EXCLUDED_NAMES = {"HANDOFF_TRACKER.json", ".DS_Store"}
# Raw point clouds, bake inputs, scene backups, and the oversize authored scene stay local.
EXCLUDED_SUFFIXES = {".laz", ".las", ".pyc", ".tmp", ".bak", ".pre-density-bake", ".pre-flora-bake"}
EXCLUDED_PATHS = {"yellowstone_midway/scenes/authored_world.tscn"}
BAKE_INPUT_PARTS = ("yellowstone_midway", "assets", "imported")


def public_path(relative: Path) -> bool:
    """Select distributable code and assets while excluding prose and local state."""
    if relative.as_posix() in PUBLIC_ROOT_DOCUMENTS:
        return True
    if not relative.parts or relative.parts[0] not in PUBLIC_ROOTS:
        return False
    if any(part in PRIVATE_PARTS or part.endswith(".egg-info") for part in relative.parts):
        return False
    if relative.name.startswith(".env"):
        return False
    if relative.name in EXCLUDED_NAMES or relative.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if relative.as_posix() in EXCLUDED_PATHS:
        return False
    if relative.parts[:3] == BAKE_INPUT_PARTS and "sources" in relative.parts[3:]:
        return False
    if relative.name.upper().split(".")[0] in {"LICENSE", "NOTICE", "COPYING", "COPYRIGHT"}:
        return True
    if relative.as_posix() in PUBLIC_SOURCE_DOCUMENTS:
        return True
    if relative.suffix.lower() in DOCUMENT_SUFFIXES:
        return relative.name == "requirements.txt"
    if relative.name.endswith(".receipt.json"):
        return False
    return True


def export_public(source: Path, destination: Path) -> dict:
    """Copy the public file selection into a fresh directory and record its hashes."""
    source, destination = source.resolve(), destination.resolve()
    if destination == source or destination.is_relative_to(source):
        raise ValueError("export destination must be outside the source repository")
    if destination.exists():
        raise FileExistsError(f"export destination exists: {destination}")
    selected = []
    for path in source.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(source)
        if public_path(relative):
            selected.append((path, relative))
    if not selected:
        raise ValueError("source has no distributable files")
    destination.mkdir(parents=True)
    hashes = {}
    for path, relative in sorted(selected):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        hashes[relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = {"schema": "yellowstone.public_export.v1", "files": hashes,
                "excluded_document_types": sorted(DOCUMENT_SUFFIXES),
                "status": "local_export_requires_owner_review"}
    write_json_atomic(destination / "public-export.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    """Write a local public export to the specified fresh directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = export_public(args.source, args.out)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"files": len(manifest["files"]), "out": str(args.out)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
