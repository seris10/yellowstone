"""Shared helpers for observation fetchers."""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from yellowstone_python.common.io import write_json_atomic

HASH_FIELDS = ("artifact_sha256", "artifact_sha256_scope")


def parse_utc_timestamp(value: Any) -> float:
    """Parse an ISO-8601 timestamp with timezone to UTC epoch seconds."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a nonempty string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp must include a timezone: {value!r}")
    return parsed.astimezone(timezone.utc).timestamp()


def now_utc_iso() -> str:
    return (datetime.now(timezone.utc).isoformat()
            .replace("+00:00", "Z"))


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def canonical_json_hash(document: dict) -> str:
    """Hex sha256 over canonical JSON of ``document`` excluding hash fields."""
    payload = {k: v for k, v in document.items() if k not in HASH_FIELDS}
    return hashlib.sha256(
        canonical_json(payload).encode("utf-8")).hexdigest()


def atomic_write_json(path: Path, document: dict, *,
                      embed_hash: bool = True) -> str:
    """Write ``document`` atomically. When ``embed_hash``, add a content hash."""
    path = Path(path)
    if embed_hash:
        digest = canonical_json_hash(document)
        payload = {k: v for k, v in document.items() if k not in HASH_FIELDS}
        out = {**payload, "artifact_sha256": digest,
               "artifact_sha256_scope": "canonical_json_without_hash_fields"}
    else:
        digest = ""
        out = dict(document)
    write_json_atomic(path, out)
    return digest


def validate_time_value_pairs(pairs: Iterable[Any],
                              *, name: str = "series") -> list[list[float]]:
    """Return a strictly increasing list of ``[epoch, value]`` float pairs; raises on malformed input."""
    cleaned: list[list[float]] = []
    seen_t: float | None = None
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(f"{name}: pair must have two elements")
        epoch, value = pair
        try:
            t = float(epoch)
            v = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name}: non-numeric pair {pair!r}") from exc
        if not (math.isfinite(t) and math.isfinite(v)):
            continue
        if seen_t is not None and t <= seen_t:
            continue
        cleaned.append([t, v])
        seen_t = t
    return cleaned


def quality_summary(pairs: list[list[float]],
                    requested_window_s: float | None = None) -> dict:
    """Count, start/end, nominal interval, max gap, coverage fraction."""
    result: dict[str, Any] = {
        "n": len(pairs),
        "start_epoch_unix": pairs[0][0] if pairs else None,
        "end_epoch_unix": pairs[-1][0] if pairs else None,
        "nominal_interval_s": None,
        "max_gap_s": None,
        "coverage_fraction": None,
    }
    if len(pairs) < 2:
        return result
    times = [p[0] for p in pairs]
    intervals = [b - a for a, b in zip(times, times[1:])]
    nominal = sorted(intervals)[len(intervals) // 2]
    result["nominal_interval_s"] = nominal
    result["max_gap_s"] = max(intervals)
    if requested_window_s and requested_window_s > 0 and nominal > 0:
        covered = sum(i for i in intervals if i <= 2.0 * nominal) + nominal
        result["coverage_fraction"] = min(1.0, covered / requested_window_s)
    return result


def verify_artifact_hash(document: dict) -> bool:
    return document.get("artifact_sha256") == canonical_json_hash(document)


def source_path(path: str | Path) -> str:
    """Return a source path relative to the Python project root."""
    root = Path(__file__).resolve().parents[2]
    return os.path.relpath(Path(path).resolve(), root)
