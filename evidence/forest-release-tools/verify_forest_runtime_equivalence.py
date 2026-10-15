"""Bind a runtime-only revision to unchanged checked model artifacts."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "yellowstone_python"))
from tools.run_evidence import source_hashes
from yellowstone_python.common.provenance import sha256_json
from yellowstone_python.publish import verify_build, verify_release
from forest_runtime_scope import EXCLUDED_SOURCE, audit_scope, excluded_observation, scoped


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def committed_bytes(commit, relative):
    return git("show", commit + ":" + relative)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-commit", default="18f456de029bb528f23bd38a9f90125bcbb48bea")
    parser.add_argument("--model-build", default="f75347b772fd")
    parser.add_argument("--source-receipt", default="evidence/receipts/16eb3eff5d0fe0b02f1b51c67b73e6db8ba75a3fdd52d856f61f440ce25621b3.json")
    parser.add_argument("--allow-path", action="append", default=[])
    parser.add_argument("--out", default="evidence/forest-runtime-equivalence.json")
    args = parser.parse_args()
    baseline = json.loads((ROOT / args.source_receipt).read_text())
    assert baseline["status"] == "executed_passed"
    assert baseline["source_commit"] == args.base_commit
    assert digest(ROOT / baseline["output"]) == baseline["output_sha256"]
    before = baseline["source_hashes"]
    current = source_hashes(ROOT)
    scope_audit = audit_scope(ROOT)
    before_scoped, current_scoped = scoped(before), scoped(current)
    allowed = set(args.allow_path)
    permitted_roots = ("yellowstone_midway/scripts/", "yellowstone_midway/shaders/",
                       "yellowstone_midway/tools/", "yellowstone_python/tests/")
    assert all(path.startswith(permitted_roots) for path in allowed), allowed
    changed = sorted(path for path in before_scoped.keys() | current_scoped.keys() if before_scoped.get(path) != current_scoped.get(path))
    assert set(changed) <= allowed, {"unapproved_source_changes": sorted(set(changed) - allowed)}
    assert all(path in current for path in changed), "Maintained sources cannot disappear"
    runtime_commit = git("rev-parse", "HEAD").decode().strip()
    tracked = set(git("ls-files", "-z").decode().split("\0"))
    assert set(current_scoped) <= tracked, {"uncommitted_sources": sorted(set(current_scoped) - tracked)}
    dirty = git("diff", "--name-only", "HEAD", "--", *current_scoped).decode().splitlines()
    assert not dirty, {"source_changes_not_committed": dirty}
    changes = []
    for relative in changed:
        if relative in before:
            assert hashlib.sha256(committed_bytes(args.base_commit, relative)).hexdigest() == before[relative]
        changes.append({"path": relative, "before_sha256": before.get(relative),
                        "after_sha256": current[relative],
                        "scope": "explicitly reviewed display/runtime or test change"})
    numerical = {p: h for p, h in before.items() if p.startswith((
        "yellowstone_python/yellowstone_python/", "yellowstone_python/tools/",
        "yellowstone_python/configs/")) or p in (
        "yellowstone_python/requirements-reference.lock", "yellowstone_python/pyproject.toml")}
    assert all(current.get(p) == h for p, h in numerical.items())
    assert not any(p not in before for p in current if p.startswith((
        "yellowstone_python/yellowstone_python/", "yellowstone_python/tools/", "yellowstone_python/configs/")))
    build = ROOT / "yellowstone_python/derived" / args.model_build
    manifest, checks = verify_build(build)
    assert manifest["code_commit"] == args.base_commit
    deps = manifest["deps"]
    inputs = {}
    input_hashes = {}
    absent_inputs = []
    for name in ("world.json", "placements.json", "species_catalogue.json", "terrain.f32"):
        path = ROOT / "yellowstone_midway/data" / name
        assert digest(path) == deps[name], name
        inputs[name] = {"sha256": deps[name], "unchanged": True}
        input_hashes[str(path.relative_to(ROOT))] = deps[name]
    ecosystem = Path(deps["ecosystem_path"])
    assert digest(ecosystem) == deps["ecosystem.json"]
    inputs["ecosystem.json"] = {"sha256": deps["ecosystem.json"], "unchanged": True}
    input_hashes[str(ecosystem.relative_to(ROOT))] = deps["ecosystem.json"]
    display_differences = []
    for name, entry in deps.get("external_inputs", {}).items():
        if entry.get("path") is None:
            inputs[name] = {"exists": entry["exists"], "sha256": entry.get("sha256"), "unchanged": True}
            continue
        path = Path(entry["path"])
        actual = digest(path) if path.is_file() else None
        if actual is not None:
            input_hashes[str(path.relative_to(ROOT))] = actual
        else:
            absent_inputs.append(str(path.relative_to(ROOT)))
        if path.is_file() == entry["exists"] and actual == entry.get("sha256"):
            inputs[name] = {"exists": entry["exists"], "sha256": actual, "unchanged": True}
            continue
        assert name == "asset_manifest", {"changed_model_or_display_input": name}
        relative = "yellowstone_midway/data/asset_manifest.json"
        original = committed_bytes(args.base_commit, relative)
        assert hashlib.sha256(original).hexdigest() == entry["sha256"]
        previous = json.loads(original)
        updated = json.loads(path.read_text())
        records = [item for item in updated["assets"] if item.get("asset_id") == "terrain_color_filter_manifest"]
        if not records:
            records = [item for item in updated["assets"] if item.get("id") == "terrain_color_filter_manifest"]
        assert len(records) == 1
        record = records[0]
        assert record["status"] == "authored"
        record["status"] = "deterministic_display_filter"
        assert updated == previous, "Asset metadata correction exceeds the reviewed status field"
        assert path.read_bytes() == committed_bytes(runtime_commit, relative), "Commit asset metadata before packaging"
        display_differences.append({"input": name, "path": relative, "before_sha256": entry["sha256"],
            "after_sha256": actual, "change": "terrain_color_filter_manifest.status: deterministic_display_filter -> authored",
            "effect": "release license classification only; input asset bytes unchanged"})
    world = ROOT / "yellowstone_midway"
    pointer = json.loads((world / "data/release.json").read_text())
    release_file = world / pointer["manifest"]
    assert digest(release_file) == pointer["sha256"]
    release = json.loads(release_file.read_text())
    verify_release(release_file.parent, release)
    assert release["build_id"] == args.model_build
    assert release["source_commit"] == args.base_commit
    assert release["release_id"] == pointer["release_id"]
    proof = {"schema": "yellowstone.runtime_model_equivalence.v1", "ok": True,
        "model_source_commit": args.base_commit, "runtime_source_commit": runtime_commit,
        "runtime_source_identity": sha256_json(current), "runtime_source_hashes": current,
        "scoped_runtime_identity": sha256_json(current_scoped), "scoped_runtime_source_hashes": current_scoped,
        "runtime_scope_audit": scope_audit,
        "excluded_source_observation": excluded_observation(ROOT, before.get(EXCLUDED_SOURCE)),
        "runtime_source_changes": changes, "approved_source_paths": sorted(allowed),
        "numerical_source_files_unchanged": len(numerical), "unchanged_input_records": inputs,
        "current_input_hashes": input_hashes,
        "current_absent_input_paths": absent_inputs,
        "display_input_differences": display_differences,
        "build_id": args.model_build, "build_sha256": digest(build / "BUILD.json"),
        "checks_sha256": digest(build / "CHECKS.json"), "checked_artifact_count": len(manifest["output_artifact_hashes"]),
        "release_id": release["release_id"], "release_sha256": digest(release_file),
        "baseline_test_receipt": {"path": args.source_receipt, "sha256": digest(ROOT / args.source_receipt)},
        "scope": "The existing numerical outputs retain their original build/source identity. Python model/tool/config bytes and physical/scenario inputs match that execution. Explicit display-source and license-metadata changes receive separate runtime tests. This is no new numerical build or field validation."}
    output = ROOT / args.out
    output.write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps({k: proof[k] for k in ("ok", "model_source_commit", "runtime_source_commit", "runtime_source_identity", "scoped_runtime_identity", "numerical_source_files_unchanged", "checked_artifact_count", "build_id", "release_id")}, indent=2))


if __name__ == "__main__":
    main()
