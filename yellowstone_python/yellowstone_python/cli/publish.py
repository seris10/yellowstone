"""Command-line interface for publish."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic
from yellowstone_python.common.io import sha256_file as _sha
import argparse
import datetime
import hashlib
import json
import shutil
from pathlib import Path
from yellowstone_python.common.provenance import CONTRACT_VERSION, WORLD_ID, default_world_root
from yellowstone_python.common.io import load_json
from yellowstone_python.exporters.godot_sidecars import produce_all as produce_sidecars
from yellowstone_python.exporters.to_ecosystem import validate_for_godot
from yellowstone_python.publish import DIRS, FILES, STUDY_REPLAY_FILES, _load_json_or_refuse, _study_replay_build_id_ok, consumer_manifest_errors

def main() -> int:
    import logging
    logging.basicConfig(level=logging.INFO)
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

    consumer_errors = consumer_manifest_errors(dst)
    if consumer_errors:
        print("refusing: published file consumers are incomplete:")
        for error in consumer_errors:
            print("  -", error)
        return 3

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = dst / "backups" / f"pre-{bid}-{stamp}"
    staged, warnings = {}, []
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
        for jsf in sorted(srcdir.glob("*.json")):
            staged[f"{rel}/{jsf.name}"] = jsf

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
        write_json_atomic(receipt_path, receipt, indent=2)
    except OSError as err:
        # Published files are correct; receipt write failed. Distinct return code supports a receipt retry.
        print(f"FAILED writing receipt: {err}")
        return 5
    print(f"published {bid} ({len(staged)} files, backup {backup_root})")
    for w in warnings:
        print("WARN:", w)
    print('In Godot 4.5.1: F5 to walk Firehole bridge; I = notes, M = map, T = +2h simulation time.')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
