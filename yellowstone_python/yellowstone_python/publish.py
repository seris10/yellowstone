"""M11 publish: transactional release of a validated build.

Steps: verify CHECKS passed (unless --force, recorded) → stage every
artifact into a temp dir → back up ALL overwritten targets (timestamped,
mirrored paths) → copy → hash-verify → write receipt.json. Any failure
rolls back from backups. Absent optional sidecars are explicit warnings,
never silent skips.

Usage:
    python -m yellowstone_python.publish --build derived/<id> [--to ...] [--force]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from .common.provenance import CONTRACT_VERSION, WORLD_ID, default_world_root
from .exporters.to_ecosystem import validate_for_godot

FILES = [
    ("ecosystem.godot.json", "data/ecosystem.json", True),
    # Unread artifacts are not shipped: no script, scene, shader, or tool
    # reads plume_map, apron_mask, pool_cross_section, suitability_demo,
    # refuge_map, grazer_tracks, or substrate_rules. Build sidecars keep
    # them as evidence; data/ carries only what the runtime consumes.
    ("pool_shells.json", "data/pool_shells.json", False),
    ("planting_proposal.json", "data/planting_proposal.review.json", False),
    ("snow_map.png", "assets/textures/snow_map.png", False),
    ("season.json", "data/season.json", False),
    # Replay files refresh the study-scene comparison pair when a build
    # produces them; absent files warn and keep the existing data/ copies.
    ("firehole_control.json", "data/firehole_control.json", False),
    ("firehole_pulse.json", "data/firehole_pulse.json", False),
]
DIRS = [
    ("pool_ramps", "assets/textures/pool_ramps"),
]


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True)
    ap.add_argument("--to", default=str(default_world_root()))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    b = Path(args.build)
    checks = json.loads((b / "CHECKS.json").read_text())
    if not checks["passed"] and not args.force:
        print("refusing: CHECKS failed; re-run build or pass --force")
        return 3
    build_doc = json.loads((b / "BUILD.json").read_text())
    bid = build_doc["build_id"]
    if build_doc.get("contract_version") != CONTRACT_VERSION or build_doc.get("world_id") != WORLD_ID:
        print(f"refusing: build contract {build_doc.get('contract_version')!r}/{build_doc.get('world_id')!r} != {CONTRACT_VERSION!r}/{WORLD_ID!r}")
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
    for src_name, rel, required in FILES:
        src = b / src_name
        if not src.exists():
            msg = f"absent sidecar: {src_name} (skipped, recorded)"
            if required:
                print("refusing: " + msg)
                return 3
            warnings.append(msg)
            continue
        staged[rel] = src
    for dirname, rel in DIRS:
        srcdir = b / dirname
        if not srcdir.is_dir():
            warnings.append(f"absent dir: {dirname} (skipped, recorded)")
            continue
        for png in sorted(srcdir.glob("*.png")):
            staged[f"{rel}/{png.name}"] = png

    backup_root.mkdir(parents=True, exist_ok=True)
    backed_up = []
    try:
        for rel, src in staged.items():
            target = dst / rel
            if target.exists():
                dest = backup_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, dest)
                backed_up.append(rel)
        for rel, src in staged.items():
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            if _sha(target) != _sha(src):
                raise IOError(f"hash mismatch after copy: {rel}")
    except Exception as err:
        print(f"FAILED ({err}); rolling back {len(backed_up)} files")
        for rel in backed_up:
            shutil.copy2(backup_root / rel, dst / rel)
        print("rollback complete")
        return 4

    receipt = {"build_id": bid, "utc": stamp, "forced": bool(args.force),
               "checks_passed": checks["passed"],
               "files": sorted(staged), "warnings": warnings,
               "backup": str(backup_root)}
    (dst / f".publish-{bid}.receipt.json").write_text(json.dumps(receipt, indent=2))
    print(f"published {bid} ({len(staged)} files, backup {backup_root})")
    for w in warnings:
        print("WARN:", w)
    print("NOTE: planting_proposal.review.json needs human review: merge accepted "
          "rows into placement_overrides.json::{add}; never overwrite placements.json.")
    print("In Godot 4.5.1: F5 → walk Firehole bridge; I = notes, M = map, T = +2h light.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
