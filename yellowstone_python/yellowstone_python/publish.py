"""M11 publish: transactional release of a validated build.
Verifies CHECKS, backs up targets, copies, hash-verifies, writes a receipt."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
from pathlib import Path

from .common.provenance import CONTRACT_VERSION, WORLD_ID, default_world_root
from .exporters.godot_sidecars import produce_all as produce_sidecars
from .exporters.to_ecosystem import validate_for_godot

FILES = [
    ("ecosystem.godot.json", "data/ecosystem.json", True),
    # Unread artifacts stay in build sidecars; data/ carries runtime files.
    ("pool_shells.json", "data/pool_shells.json", False),
    ("planting_proposal.json", "data/planting_proposal.review.json", False),
    ("snow_map.png", "assets/textures/snow_map.png", False),
    ("season.json", "data/season.json", False),
    # Godot sidecars produced on publish; a missing source records a gap and skips the file.
    ("plume_field.json", "data/plume_field.json", False),
    ("geochemistry.json", "data/geochemistry.json", False),
    ("calibration_summary.json", "data/calibration_summary.json", False),
    ("pools_state.json", "data/pools_state.json", False),
    ("snow_cover.json", "data/snow_cover.json", False),
    ("overland_field.json", "data/overland_field.json", False),
    ("groundwater_field.json", "data/groundwater_field.json", False),
    ("census.json", "data/census.json", False),
    # Weather snapshot (schema v2) consumed by yellowstone_midway/scripts/weather_snapshot_reader.gd.
    ("weather_snapshot.json", "data/weather_snapshot.json", False),
    # Replay files refresh the study-scene comparison pair when a build produces them.
    ("firehole_control.json", "data/firehole_control.json", False),
    ("firehole_pulse.json", "data/firehole_pulse.json", False),
]
# Study replays carry a build_id that must resolve to a build dir under derived/.
STUDY_REPLAY_FILES = ("firehole_control.json", "firehole_pulse.json")
DIRS = [
    ("pool_ramps", "assets/textures/pool_ramps"),
]


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def _study_replay_build_id_ok(path: Path,
                              derived_root: Path) -> tuple[str, str]:
    """Verdict for a study-replay file: (status, detail).
    'ok' when source_build_id names a sibling build dir; 'refused' otherwise."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return "refused", f"could not read {path.name}: {exc}"
    if not isinstance(doc, dict):
        return "refused", f"{path.name} is not a JSON object"
    source_bid = doc.get("source_build_id")
    if not isinstance(source_bid, str) or not source_bid.strip():
        return "refused", (
            f"{path.name} lacks source_build_id; the study runner must "
            f"carry forward the build_id of the derived/ build it "
            f"consumed (fixes-33 item 15 runner side)")
    target = derived_root / source_bid
    if not target.is_dir():
        return "refused", (
            f"study replay source_build_id {source_bid!r} has no "
            f"matching build dir at {target}")
    return "ok", (f"{path.name} source_build_id {source_bid!r} "
                  f"resolves to {target}")


def _load_json_or_refuse(path: Path, label: str) -> tuple[dict | None, int]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        print(f"refusing: missing {label} at {path}")
        return None, 3
    except json.JSONDecodeError as exc:
        print(f"refusing: invalid JSON in {label} ({path}): {exc}")
        return None, 3
    if not isinstance(value, dict):
        print(f"refusing: {label} is not a JSON object")
        return None, 3
    return value, 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True)
    ap.add_argument("--to", default=str(default_world_root()))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    b = Path(args.build)
    checks, rc = _load_json_or_refuse(b / "CHECKS.json", "CHECKS.json")
    if checks is None:
        return rc
    if not isinstance(checks.get("passed"), bool):
        print("refusing: CHECKS.json passed must be boolean")
        return 3
    if not checks["passed"] and not args.force:
        print("refusing: CHECKS failed; re-run build or pass --force")
        return 3
    build_doc, rc = _load_json_or_refuse(b / "BUILD.json", "BUILD.json")
    if build_doc is None:
        return rc
    bid = build_doc.get("build_id")
    if not isinstance(bid, str) or not bid:
        print("refusing: BUILD.json lacks a string build_id")
        return 3
    if (build_doc.get("contract_version") != CONTRACT_VERSION
            or build_doc.get("world_id") != WORLD_ID):
        print(f"refusing: build contract "
              f"{build_doc.get('contract_version')!r}/"
              f"{build_doc.get('world_id')!r} != "
              f"{CONTRACT_VERSION!r}/{WORLD_ID!r}")
        return 3
    eco_candidate = b / "ecosystem.godot.json"
    if eco_candidate.exists():
        eco_errors = validate_for_godot(json.loads(eco_candidate.read_text()))
        if eco_errors:
            print("refusing: ecosystem.godot.json fails Godot contract:")
            for err in eco_errors:
                print("  -", err)
            return 3
    if b.name != bid:
        print(f"refusing: dir {b.name} != build {bid}")
        return 3
    dst = Path(args.to)
    if not (dst / "project.godot").exists():
        print(f"refusing: {dst} is not a Godot project root")
        return 3

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = dst / "backups" / f"pre-{bid}-{stamp}"
    staged, warnings = {}, []
    produced, gaps = produce_sidecars(b)
    for name in sorted(produced):
        warnings.append(f"produced sidecar: {name}")
    for gap in gaps:
        warnings.append(f"sidecar gap: {gap}")
    derived_root = b.parent
    for src_name, rel, required in FILES:
        src = b / src_name
        if not src.exists():
            msg = f"absent sidecar: {src_name} (skipped, recorded)"
            if required:
                print("refusing: " + msg)
                return 3
            warnings.append(msg)
            continue
        if src_name in STUDY_REPLAY_FILES:
            status, detail = _study_replay_build_id_ok(src, derived_root)
            if status == "refused":
                print(f"refusing: {src_name}: {detail}")
                return 3
            warnings.append(f"{src_name}: {detail}")
        staged[rel] = src
    for dirname, rel in DIRS:
        srcdir = b / dirname
        if not srcdir.is_dir():
            warnings.append(f"absent dir: {dirname} (skipped, recorded)")
            continue
        for png in sorted(srcdir.glob("*.png")):
            staged[f"{rel}/{png.name}"] = png

    try:
        backup_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(f"refusing: backup dir already exists at {backup_root}")
        return 4
    backed_up: list[str] = []
    created: list[str] = []
    file_records: dict[str, dict] = {}
    try:
        for rel, src in staged.items():
            target = dst / rel
            if target.exists():
                if target.is_dir():
                    raise IOError(
                        f"target is a directory, expected file: {target}")
                if target.is_symlink():
                    raise IOError(
                        f"target is a symlink, refusing to follow: {target}")
                dest = backup_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, dest)
                backed_up.append(rel)
        for rel, src in staged.items():
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            was_present = rel in backed_up
            shutil.copy2(src, target)
            if not was_present:
                created.append(rel)
            src_sha = _sha(src)
            tgt_sha = _sha(target)
            if tgt_sha != src_sha:
                raise IOError(f"hash mismatch after copy: {rel}")
            file_records[rel] = {
                "source_sha256": src_sha,
                "target_sha256": tgt_sha,
                "size": target.stat().st_size,
            }
    except (OSError, IOError) as err:
        print(f"FAILED ({err}); rolling back {len(created)} created and "
              f"{len(backed_up)} restored files")
        for rel in created:
            target = dst / rel
            if target.exists():
                try:
                    target.unlink()
                except OSError:
                    pass
        for rel in backed_up:
            shutil.copy2(backup_root / rel, dst / rel)
        print("rollback complete")
        return 4

    receipt = {"build_id": bid, "utc": stamp, "forced": bool(args.force),
               "checks_passed": checks["passed"],
               "files": file_records, "warnings": warnings,
               "backup": str(backup_root)}
    receipt_path = dst / f".publish-{bid}.receipt.json"
    try:
        tmp = receipt_path.with_name(receipt_path.name + ".tmp")
        tmp.write_text(
            json.dumps(receipt, indent=2, allow_nan=False) + "\n",
            encoding="utf-8")
        tmp.replace(receipt_path)
    except OSError as err:
        # Published files are correct; receipt write failed. Distinct return code supports a receipt retry.
        print(f"FAILED writing receipt: {err}")
        return 5
    print(f"published {bid} ({len(staged)} files, backup {backup_root})")
    for w in warnings:
        print("WARN:", w)
    print("NOTE: planting_proposal.review.json needs human review: merge accepted "
          "rows into placement_overrides.json::{add}; never overwrite placements.json.")
    print("In Godot 4.5.1: F5 → walk Firehole bridge; I = notes, M = map, T = +2h light.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
