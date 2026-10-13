"""M00 provenance: hashes, build ids, sidecars (SHARED_WORLD_CONTRACT 8.1)."""
from __future__ import annotations

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


def build_id(config: dict, dep_hashes: dict, code_rev: str | None = None) -> str:
    """Short build id over config, dep hashes, and an optional code revision."""
    payload: dict = {"config": config, "deps": dep_hashes}
    if code_rev is not None:
        payload["code_rev"] = code_rev
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:12]


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
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=2, sort_keys=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
                "w", delete=False, dir=p.parent,
                prefix=p.name + ".", suffix=".tmp", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_name = handle.name
        os.replace(tmp_name, p)
        tmp_name = None
    finally:
        if tmp_name is not None and os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return doc
