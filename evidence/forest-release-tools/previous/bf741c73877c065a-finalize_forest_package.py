"""Authenticate the prepared forest and spring release archive."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "yellowstone_python"))
from tools.run_evidence import evidence_status, source_hashes
from yellowstone_python.common.provenance import sha256_json
from forest_runtime_scope import audit_scope, excluded_observation, scoped, scoped_receipt_status
package = root / "work/Yellowstone-Forest-Spring-Update"
out = Path("/Users/kreed/Documents/Codex/2026-10-14/a-claude-instance-did-work-on/outputs")
out.mkdir(parents=True, exist_ok=True)

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

tool_manifest_path = root / "evidence/forest-release-tools/manifest.json"
tool_manifest = json.loads(tool_manifest_path.read_text())
assert tool_manifest["schema"] == "yellowstone.release_tool_snapshots.v1"
for entry in tool_manifest["files"]:
    assert digest(root / entry["source_path"]) == entry["sha256"], (entry["source_path"], "Refresh release-tool snapshots after helper change")
    assert digest(root / entry["snapshot_path"]) == entry["sha256"], entry["snapshot_path"]
report = json.loads((package / "PACKAGE.json").read_text())
equivalence_path = root / "evidence/forest-runtime-equivalence.json"
equivalence = json.loads(equivalence_path.read_text())
assert equivalence["ok"] is True
current_sources = source_hashes(root)
assert scoped(current_sources) == equivalence["scoped_runtime_source_hashes"], "Runtime changed after equivalence verification"
assert sha256_json(scoped(current_sources)) == equivalence["scoped_runtime_identity"]
assert audit_scope(root)["scope_helper_sha256"] == equivalence["runtime_scope_audit"]["scope_helper_sha256"]
assert report["source_commit"] == equivalence["model_source_commit"]
assert report["release_id"] == equivalence["release_id"]
assert report["build_id"] == equivalence["build_id"]
for relative, expected in equivalence["current_input_hashes"].items():
    assert digest(root / relative) == expected, (relative, "input changed after equivalence verification")
for relative in equivalence["current_absent_input_paths"]:
    assert not (root / relative).is_file(), (relative, "input appeared after equivalence verification")
active_pointer = json.loads((root / "yellowstone_midway/data/release.json").read_text())
assert active_pointer["release_id"] == equivalence["release_id"]
assert digest(root / "yellowstone_midway" / active_pointer["manifest"]) == equivalence["release_sha256"]
subprocess.run(["git", "merge-base", "--is-ancestor", equivalence["runtime_source_commit"], "HEAD"], cwd=root, check=True)
for relative, expected in scoped(current_sources).items():
    if relative.startswith(("yellowstone_midway/scripts/", "yellowstone_midway/shaders/", "yellowstone_midway/tools/")):
        assert digest(package / relative.removeprefix("yellowstone_midway/")) == expected, relative
receipt_paths = json.loads((root / "work/forest-package-startup-receipts.json").read_text())
assert set(receipt_paths) == {"forest-package-headless", "forest-package-native"}
required_fixtures = {str((package / path).relative_to(root)) for path in
                     ("RUNTIME.json", "project.godot", "scenes/authored_world.tscn", "data/release.json")}
runtime_manifest = json.loads((package / "RUNTIME.json").read_text())
runtime_paths = {"project.godot"}
for directory in ("assets", "data", "references", "scenes", "scripts", "shaders", "tools"):
    runtime_paths.update(str(path.relative_to(package)) for path in (package / directory).rglob("*")
                         if path.is_file() and path.name != ".DS_Store" and "__pycache__" not in path.parts)
assert runtime_paths == set(runtime_manifest["artifact_hashes"]), "Runtime file set changed after startup tests"
for relative, expected in runtime_manifest["artifact_hashes"].items():
    assert digest(package / relative) == expected, relative
for name, relative in receipt_paths.items():
    receipt = json.loads((root / relative).read_text())
    assert receipt["name"] == name
    assert scoped_receipt_status(receipt, root)["status"] == "executed_passed", relative
    assert required_fixtures.issubset(receipt["fixture_hashes"]), relative
changed = []
for relative, expected in report["artifact_hashes"].items():
    current = digest(package / relative)
    if current != expected:
        assert relative.endswith(".import"), (relative, "unexpected runtime mutation")
        changed.append({"path": relative, "before": expected, "after": current})
for directory in ("docs", "evidence"):
    shutil.copytree(root / directory, package / directory, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
for path in (package / "docs").glob("*.md"):
    path.write_text(path.read_text().replace("../yellowstone_midway/docs/", ""))
shutil.copy2(root / "LICENSE", package / "APACHE_LICENSE.txt")
shutil.copy2(root / "yellowstone_python/yellowstone_python/wildlife_motion/LICENSE", package / "WILDLIFE_MOTION_LICENSE.txt")
(package / "README.md").write_text(f'''# Yellowstone forest and spring update

This portable Godot project contains one checked model generation and the baked world. Use Godot 4.5.1; the tested platform is macOS arm64 with Metal. Python is unnecessary for offline exploration.

```sh
godot --headless --editor --path . --import --quit
godot --path .
```

WASD walks, mouse looks, Esc opens starting places, H opens the river probe, and Q pauses playback. The guided river-temperature experiment is available in the portfolio scenario.

[Render measurements](docs/PERFORMANCE.md) | [Forest floor](docs/FOREST_FLOOR.md) | [Spring display](docs/spring-display.md) | [Atmospheric optics](docs/atmosphere-optics.md)

Selected numerical generation: `{report['release_id']}`. Build: `{report['build_id']}` at model source commit `{equivalence['model_source_commit']}`. Runtime source commit: `{equivalence['runtime_source_commit']}`. The numerical artifacts retain their original identity; the runtime-only revision and unchanged model inputs are recorded in evidence/forest-runtime-equivalence.json. PACKAGE.json authenticates bundled bytes and ASSET_INVENTORY.json records asset decisions.

Full source observations and original receipts are retained. Runtime verification excludes exactly the unbundled dashboard/build_data.py generator, whose independent edits and global receipt status remain recorded. Every bundled runtime file, included source and startup fixture remains hash-checked.

The source tree census is preserved; display crowns and residual-canopy supports are authored. Terrain-checked litter, vegetation and wood add ground detail. Human-made CC0 textures supply detail. Spring color is image-informed display, while scientific radiometry remains separate. Terraces alter shading without changing terrain or collision. Cloud and rainbow optics respond to weather history and illumination; clear startup has no rainbow curtain.

Scientific and ecological claims remain unaccepted. Local plant abundance, ring widths, terrace relief and rainbow occurrence frequency are authored or uncalibrated. Tree endpoint silhouettes and brightness have remaining mismatches; complementary transitions do not establish endpoint equivalence. Performance results and retained thresholds are reported in docs/PERFORMANCE.md. Native executable exports and other platforms are untested.

KJR owns the animal meshes and authorized their inclusion. See THIRD_PARTY.md, LICENSE, APACHE_LICENSE.txt and WILDLIFE_MOTION_LICENSE.txt for code and asset scopes. Source and reproduction: https://github.com/seris10/yellowstone.
''')
report["startup_evidence"] = receipt_paths
report["model_source_commit"] = equivalence["model_source_commit"]
report["runtime_source_commit"] = equivalence["runtime_source_commit"]
report["runtime_source_identity"] = equivalence["runtime_source_identity"]
report["scoped_runtime_identity"] = equivalence["scoped_runtime_identity"]
report["source_identity_scope"] = {"package_creation_full_identity": report["source_identity"],
    "equivalence_full_identity": equivalence["runtime_source_identity"],
    "finalization_full_identity": sha256_json(current_sources),
    "scoped_runtime_identity": equivalence["scoped_runtime_identity"],
    "excluded_at_equivalence": equivalence["excluded_source_observation"],
    "excluded_at_finalization": excluded_observation(root),
    "note": "Original full inventory observations include dashboard/build_data.py and remain unchanged. The exact unbundled dashboard path is excluded only from runtime comparisons. Packaged script/shader/tool bytes, every runtime file, fixtures and included sources remain authenticated."}
report["startup_scoped_status"] = {name: scoped_receipt_status(json.loads((root / relative).read_text()), root)
                                   for name, relative in receipt_paths.items()}
report["release_tool_manifest"] = {"path": "evidence/forest-release-tools/manifest.json", "sha256": digest(tool_manifest_path)}
report["runtime_model_equivalence"] = {"path": "evidence/forest-runtime-equivalence.json", "sha256": digest(equivalence_path)}
report["startup_runtime_manifest"] = {"path": "RUNTIME.json", "sha256": digest(package / "RUNTIME.json")}
report["import_sidecar_changes"] = changed
report["documentation_assembly"] = "Portable README, source evidence, model documentation and separate license scopes."
report["artifact_hashes"] = {
    str(path.relative_to(package)): digest(path)
    for path in sorted(package.rglob("*"))
    if path.is_file() and path.name != "PACKAGE.json" and ".godot" not in path.parts
       and path.name != ".DS_Store"
}
assert len(list((package / "data/releases").iterdir())) == 1
(package / "PACKAGE.json").write_text(json.dumps(report, indent=1) + "\n")
archive = out / "Yellowstone-Forest-Spring-Update.zip"
assert not archive.exists(), "Preserve any existing archive"
prefix = "Yellowstone-Forest-Spring-Update/"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zipped:
    for relative in sorted([*report["artifact_hashes"], "PACKAGE.json"]):
        zipped.write(package / relative, prefix + relative)
with zipfile.ZipFile(archive) as zipped:
    assert len(zipped.namelist()) == len(report["artifact_hashes"]) + 1
    for relative, expected in report["artifact_hashes"].items():
        with zipped.open(prefix + relative) as member:
            assert hashlib.file_digest(member, "sha256").hexdigest() == expected, relative
    assert zipped.read(prefix + "PACKAGE.json") == (package / "PACKAGE.json").read_bytes()
receipt = {
    "schema": "yellowstone.forest_archive.v1", "release_id": report["release_id"],
    "build_id": report["build_id"], "source_identity": report["source_identity"],
    "model_source_commit": report["model_source_commit"], "runtime_source_commit": report["runtime_source_commit"],
    "runtime_source_identity": report["runtime_source_identity"],
    "scoped_runtime_identity": report["scoped_runtime_identity"],
    "source_identity_scope": report["source_identity_scope"],
    "archive": archive.name, "archive_bytes": archive.stat().st_size,
    "archive_sha256": digest(archive), "package_sha256": digest(package / "PACKAGE.json"),
    "verified_file_hashes": len(report["artifact_hashes"]), "startup_evidence": report["startup_evidence"],
    "scope": "Every archived file matches the authenticated package; one selected generation; Godot 4.5.1 required."
}
(root / "evidence/forest-package.json").write_text(json.dumps(receipt, indent=2) + "\n")
(out / "Yellowstone-Forest-Spring-Receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
(out / "Yellowstone-Forest-Spring-SHA256.txt").write_text(receipt["archive_sha256"] + "  " + archive.name + "\n")
print(json.dumps(receipt, indent=2), flush=True)
