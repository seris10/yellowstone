"""M00 provenance: hashes, build ids, sidecars (SHARED_WORLD_CONTRACT §8.1)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

CONTRACT_VERSION = "0.1.0"
WORLD_ID = "yellowstone_midway"


def _sibling_world_root() -> Path:
    """yellowstone_midway checkout beside this repository, if present."""
    return Path(__file__).resolve().parents[2].parent / WORLD_ID


def default_world_root() -> Path:
    """Portable world-root default: $YELLOWSTONE_WORLD wins, else the
    sibling checkout. Callers must still verify it exists."""
    return Path(os.environ.get("YELLOWSTONE_WORLD") or _sibling_world_root())


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_id(config: dict, dep_hashes: dict) -> str:
    return hashlib.sha1(
        json.dumps({"config": config, "deps": dep_hashes},
                   sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:12]


def write_sidecar(path: str | Path, payload: dict, sources: list,
                   params: dict, code_rev: str = "yellowstone_python-0.1.0",
                   status: str = "illustrative, not calibrated") -> dict:
    """Inject contract header + provenance, write JSON, return full doc."""
    doc = {
        "contract_version": CONTRACT_VERSION,
        "world_id": WORLD_ID,
        "code_rev": code_rev,
        "status": status,
        **payload,
        "parameter_provenance": {**payload.get("parameter_provenance", {}),
                                  **params},
        "sources": sources,
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, sort_keys=True))
    return doc
