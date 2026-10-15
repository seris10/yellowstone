"""provenance: hashes, build ids, sidecars (provenance contract)."""
from __future__ import annotations

from yellowstone_python.common.io import sha256_file, write_json_atomic

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

CONTRACT_VERSION = "0.1.0"
WORLD_ID = "yellowstone_midway"
FALLBACK_CODE_REV = "yellowstone_python-0.1.0"


def _sibling_world_root() -> Path:
    """yellowstone_midway checkout beside this repository, if present."""
    return Path(__file__).resolve().parents[2].parent / WORLD_ID


def default_world_root() -> Path:
    """Return $YELLOWSTONE_WORLD when set, otherwise the sibling checkout path."""
    return Path(os.environ.get("YELLOWSTONE_WORLD") or _sibling_world_root())


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_code_rev(repo_root: str | Path | None = None) -> tuple[str, str]:
    """Return (code_rev, source) where source is 'git' or 'fallback'."""
    root = Path(repo_root) if repo_root is not None else _repo_root()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return (FALLBACK_CODE_REV, "fallback")
    rev = proc.stdout.strip()
    if proc.returncode == 0 and rev:
        return (rev, "git")
    return (FALLBACK_CODE_REV, "fallback")




def sha256_json(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def portable_identity_payload(config: dict, deps: dict) -> dict:
    """Separate logical content from machine paths and discovery receipts."""
    def effective(value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == "world_root":
                    continue
                if key in ("met_bundle", "cross_sections_file") and isinstance(item, str):
                    result[key] = "input:" + key
                elif isinstance(item, str) and Path(item).is_absolute():
                    result[key] = "input:" + key
                else:
                    result[key] = effective(item)
            return result
        if isinstance(value, (list, tuple)):
            return [effective(item) for item in value]
        return value
    ignored = {"ecosystem_path", "code_hash_source", "code_rev_source", "config",
               "external_inputs_sha256", "terrain_guard", "terrain_guard_advisories",
               "execution_receipt"}
    logical = {}
    for key, value in deps.items():
        if key in ignored:
            continue
        if key == "external_inputs":
            logical[key] = {name: {field: entry.get(field) for field in ("exists", "sha256")}
                            for name, entry in value.items()}
        elif isinstance(value, dict) and "path" in value:
            logical[key] = {field: value.get(field) for field in ("exists", "sha256") if field in value}
        else:
            logical[key] = effective(value)
    return {"config": effective(config), "logical_inputs": logical}


def build_id(config: dict, dep_hashes: dict, code_rev: str | None = None) -> str:
    """Return a portable content identity for configuration and input bytes."""
    payload = portable_identity_payload(config, dep_hashes)
    if code_rev is not None:
        payload["code_rev"] = code_rev
    return sha256_json(payload)[:12]


def write_sidecar(path: str | Path, payload: dict, sources: list,
                  params: dict, code_rev: str = FALLBACK_CODE_REV,
                  status: str = "illustrative, not calibrated") -> dict:
    """Inject contract header and provenance; write JSON through tempfile + os.replace."""
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
    write_json_atomic(path, doc, indent=2)
    return doc
