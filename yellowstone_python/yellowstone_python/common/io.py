"""File hashes, checked JSON reads, and atomic JSON writes."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: str | Path, *, label: str | None = None, expect: type = dict):
    """Read JSON of the expected type; raise ValueError with the source path."""
    path = Path(path)
    context = f"{label or 'JSON'} ({path})"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{context}: {exc}") from exc
    if not isinstance(value, expect):
        raise ValueError(f"{context} must contain {expect.__name__}")
    return value


def write_json_atomic(path: str | Path, obj: object, *, indent: int = 1) -> Path:
    """Replace JSON atomically; preserve the destination if serialization fails."""
    path = Path(path)
    serialized = json.dumps(obj, indent=indent, sort_keys=True, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=path.parent, delete=False,
                prefix=f".{path.name}.", suffix=".tmp") as handle:
            temporary = Path(handle.name)
            handle.write(serialized + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path
