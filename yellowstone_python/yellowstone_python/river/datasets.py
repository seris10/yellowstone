"""Reference dataset roles for the temperature claim."""
from __future__ import annotations

import math

from yellowstone_python.registry.claims import get_claim, resolve_artifact_id, split_artifact_id

CLAIM_ID = "reach_water_temperature_ice_free"

ROLES = {
    "calibration": ["derived/firehole_obs.json:train"],
    "development": ["derived/firehole_obs.json:holdout",
                    "derived/usgs_06036805.json"],
    "locked_final": ["derived/firehole_obs_locked_final.json"],
}


def _epoch(row, context) -> float:
    """Validate a numeric epoch at position 0 of a row-like value."""
    if not isinstance(row, (list, tuple)) or not row:
        raise ValueError(f"{context}: malformed observation row")
    value = float(row[0])
    if not math.isfinite(value):
        raise ValueError(f"{context}: nonfinite timestamp")
    return value


def _collect_epochs(bundle, context) -> list[float]:
    """Validated numeric epochs from site series and met rows."""
    epochs: list[float] = []
    sites = bundle.get("sites", {})
    if sites and not isinstance(sites, dict):
        raise ValueError(f"{context}: sites must be a mapping")
    for site_id, record in sites.items():
        series_map = record.get("series", {}) if isinstance(record, dict) else {}
        for name, series in series_map.items():
            for i, row in enumerate(series):
                epochs.append(_epoch(row, f"{context} {site_id}/{name}[{i}]"))
    met = bundle.get("met", {})
    for i, row in enumerate(met.get("hourly", []) if isinstance(met, dict) else []):
        epochs.append(_epoch(row, f"{context} met[{i}]"))
    return epochs


def _bundle_intervals(path) -> list[tuple[float, float]]:
    """Contiguous [epoch, epoch] intervals over observed samples."""
    import json
    bundle = json.loads(path.read_text(encoding="utf-8"))
    epochs = sorted(_collect_epochs(bundle, str(path)))
    if not epochs:
        return []
    gap_s = 7.0 * 86400.0
    intervals: list[tuple[float, float]] = []
    start = prev = epochs[0]
    for value in epochs[1:]:
        if value - prev > gap_s:
            intervals.append((start, prev))
            start = value
        prev = value
    intervals.append((start, prev))
    return intervals


def _resolve_cached(aid, cache):
    """Resolve an artifact id once per helper invocation."""
    if aid not in cache:
        cache[aid] = resolve_artifact_id(aid)
    return cache[aid]


def window_errors(cache: dict | None = None) -> list:
    """Locked-final intervals disjoint from fitted and selected windows."""
    errors = []
    cache = cache if cache is not None else {}
    try:
        locked_intervals = _bundle_intervals(_resolve_cached(
            ROLES["locked_final"][0], cache))
    except (ValueError, FileNotFoundError, IndexError) as exc:
        return [f"locked_final: {exc}"]
    if not locked_intervals:
        return ["locked_final bundle carries no dated observations"]
    for role in ("calibration", "development"):
        for aid in ROLES[role]:
            try:
                window_intervals = _bundle_intervals(_resolve_cached(aid, cache))
            except (ValueError, FileNotFoundError) as exc:
                errors.append(f"role {role}: {exc}")
                continue
            if not window_intervals:
                continue
            overlapped = False
            for locked_a, locked_b in locked_intervals:
                for win_a, win_b in window_intervals:
                    if not (locked_b < win_a or locked_a > win_b):
                        overlapped = True
                        break
                if overlapped:
                    break
            if overlapped:
                errors.append(f"locked_final overlaps {role} {aid!r}")
    return errors


def _claim_membership(claim, field, aid) -> str:
    """Classify aid in claim[field]: present, absent, selector_mismatch, malformed."""
    ids = claim.get(field)
    if not isinstance(ids, list):
        return "malformed"
    if aid in ids:
        return "present"
    base = aid.split(":", 1)[0] if ":" in aid else aid
    for entry in ids:
        entry_base = entry.split(":", 1)[0] if ":" in entry else entry
        if entry_base == base:
            return "selector_mismatch"
    return "absent"


def role_errors() -> list:
    errors = []
    cache: dict = {}
    for role, ids in ROLES.items():
        for aid in ids:
            try:
                _resolve_cached(aid, cache)
            except (ValueError, FileNotFoundError) as exc:
                errors.append(f"role {role}: {exc}")
    try:
        claim = get_claim(CLAIM_ID)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        errors.append(f"claim {CLAIM_ID!r}: {exc}")
        return errors
    checks = (("calibration", "calibration_dataset_ids"),
              ("development", "evaluation_dataset_ids"),
              ("locked_final", "evaluation_dataset_ids"))
    for role, field in checks:
        for aid in ROLES[role]:
            status = _claim_membership(claim, field, aid)
            if status == "present":
                continue
            if status == "selector_mismatch":
                errors.append(
                    f"role {role} id {aid!r}: selector differs from claim record")
            elif status == "malformed":
                errors.append(
                    f"role {role}: claim field {field!r} is malformed")
            else:
                errors.append(
                    f"role {role} id {aid!r} outside claim record")
    seen: dict[str, list[str]] = {}
    for role, ids in ROLES.items():
        for aid in ids:
            seen.setdefault(aid, []).append(role)
    for aid, roles in seen.items():
        if len(roles) > 1:
            errors.append(
                f"artifact {aid!r} assigned to multiple roles: "
                f"{sorted(set(roles))}")
    for role, ids in ROLES.items():
        if len(ids) != len(set(ids)):
            errors.append(f"role {role}: duplicate artifact ids")
    _ = split_artifact_id
    errors += window_errors(cache)
    return errors
