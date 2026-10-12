"""Reference dataset roles for the temperature claim.

Calibration fits parameters. Development selects models. Locked-final
evaluates once, after the model and acceptance criteria freeze. A
locked-final entry used for further development changes role, and a
new independent evaluation is then required.
"""
from __future__ import annotations

from ..claims import get_claim, resolve_artifact_id, split_artifact_id

CLAIM_ID = "reach_water_temperature_ice_free"

ROLES = {
    "calibration": ["derived/firehole_obs.json:train"],
    "development": ["derived/firehole_obs.json:holdout",
                    "derived/usgs_06036805.json"],
    "locked_final": ["derived/firehole_obs_locked_final.json"],
}


def _bundle_range(path) -> tuple | None:
    """(min epoch, max epoch) over series and met rows, None when dateless."""
    import json
    bundle = json.loads(path.read_text(encoding="utf-8"))
    epochs = [p[0] for rec in bundle.get("sites", {}).values()
              for series in rec.get("series", {}).values() for p in series]
    epochs += [row[0] for row in bundle.get("met", {}).get("hourly", [])]
    if not epochs:
        return None
    return min(epochs), max(epochs)


def window_errors() -> list:
    """Locked-final window disjoint from fitted and selected windows."""
    errors = []
    try:
        locked = _bundle_range(resolve_artifact_id(
            ROLES["locked_final"][0]))
    except (ValueError, FileNotFoundError, IndexError) as exc:
        return [f"locked_final: {exc}"]
    if locked is None:
        return ["locked_final bundle carries no dated observations"]
    for role in ("calibration", "development"):
        for aid in ROLES[role]:
            path, _ = split_artifact_id(aid)
            try:
                window = _bundle_range(resolve_artifact_id(aid))
            except (ValueError, FileNotFoundError) as exc:
                errors.append(f"role {role}: {exc}")
                continue
            if window is None:
                continue
            if not (locked[1] < window[0] or locked[0] > window[1]):
                errors.append(f"locked_final overlaps {role} {aid!r}")
    return errors


def role_errors() -> list:
    errors = []
    for role, ids in ROLES.items():
        for aid in ids:
            try:
                resolve_artifact_id(aid)
            except (ValueError, FileNotFoundError) as exc:
                errors.append(f"role {role}: {exc}")
    claim = get_claim(CLAIM_ID)
    for aid in ROLES["calibration"]:
        if aid not in claim["calibration_dataset_ids"]:
            errors.append(f"role calibration id {aid!r} outside claim record")
    for aid in ROLES["development"]:
        if aid not in claim["evaluation_dataset_ids"]:
            errors.append(f"role development id {aid!r} outside claim record")
    for aid in ROLES["locked_final"]:
        if aid not in claim["evaluation_dataset_ids"]:
            errors.append(f"role locked_final id {aid!r} outside claim record")
    errors += window_errors()
    return errors
