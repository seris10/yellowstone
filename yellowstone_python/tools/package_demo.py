"""Package one active generation with reviewed assets and the baked Godot scene."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil

from yellowstone_python.common.io import load_json, sha256_file, write_json_atomic
from yellowstone_python.common.provenance import sha256_json
from yellowstone_python.publish import FILES, DIRS, verify_release
from tools.asset_release_inventory import release_inventory
from tools.run_evidence import source_hashes


def _temporary_path(relative: Path) -> bool:
    """Identify workspace/editor detritus without excluding runtime import sidecars."""
    for name in relative.parts:
        if name in {".DS_Store", "Thumbs.db", "desktop.ini", "__pycache__", ".git", ".godot"}:
            return True
        if name.startswith("._") or name.endswith("~"):
            return True
        if Path(name).suffix.lower() in {".pyc", ".pyo", ".tmp", ".temp", ".bak", ".backup", ".old", ".orig", ".rej", ".swp", ".swo", ".package"}:
            return True
        if re.search(r"\.tscn\.pre-[a-z0-9-]+-bake$", name):
            return True
    return False


def _ignore_temporary(directory: str, names: list[str]) -> list[str]:
    """Apply the package hygiene rule when merging repository documentation."""
    return [name for name in names if _temporary_path(Path(name))]


def _bind_scene_resources(destination: Path, release: dict) -> list[dict]:
    """Bind baked scene resources to the selected immutable generation."""
    changes = []
    managed = {target for _, target, _ in FILES}
    directories = [target + "/" for _, target in DIRS]
    prefix = Path("data/releases") / release["release_id"]
    # Binary scenes ship verbatim; pool_overlay resolves managed ramps through ReleaseData.
    for scene in sorted((destination / "scenes").rglob("*.tscn")):
        before = sha256_file(scene)
        pending = scene.with_suffix(".tscn.package")
        removed, rebound = [], []
        with scene.open() as source, pending.open("w") as output:
            for line in source:
                match = re.search(r'path="res://([^"]+)"', line) if line.startswith("[ext_resource ") else None
                if match:
                    relative = match.group(1)
                    if relative in managed or any(relative.startswith(name) for name in directories):
                        artifact = release["artifacts"].get(relative, {})
                        if artifact.get("state") == "present":
                            target = str(prefix / artifact["path"])
                            line = line.replace('"res://' + relative + '"', '"res://' + target + '"')
                            line = re.sub(r' uid="[^"]+"', "", line)
                            rebound.append(relative)
                        elif 'type="Texture2D"' in line:
                            removed.append(re.search(r' id="([^"]+)"', line).group(1))
                            continue
                        else:
                            raise ValueError("baked resource unavailable: " + relative)
                    else:
                        target = relative
                    if not (destination / target).is_file():
                        raise ValueError("baked resource excluded or missing: " + target)
                for resource_id in removed:
                    line = line.replace('ExtResource("' + resource_id + '")', "null")
                output.write(line)
        pending.replace(scene)
        if rebound or removed:
            changes.append({"scene": str(scene.relative_to(destination)), "source_sha256": before,
                "packaged_sha256": sha256_file(scene), "rebound_resources": rebound,
                "disabled_optional_texture_ids": removed})
    return changes


def package_demo(world: Path, destination: Path, *, source_root: Path | None = None) -> dict:
    """Copy reviewed runtime inputs and authenticate all packaged bytes."""
    world, destination = Path(world), Path(destination)
    if destination.exists():
        raise FileExistsError("package destination already exists")
    pointer = load_json(world / "data/release.json")
    release_path = world / pointer["manifest"]
    if sha256_file(release_path) != pointer["sha256"]:
        raise ValueError("active release pointer hash differs")
    release = load_json(release_path)
    verify_release(release_path.parent, release)
    if release["verification"]["status"] != "numerical_and_contract_checks_passed":
        raise ValueError("demo packaging requires checked artifact bytes")
    if not (world / "scenes/authored_world.scn").is_file():
        raise ValueError("the offline world bake is required")
    inventory = release_inventory(world)
    excluded = {asset["path"] for asset in inventory["assets"] if asset["public_release_decision"] == "exclude"}
    managed_files = {target for _, target, _ in FILES}
    managed_dirs = [target + "/" for _, target in DIRS]
    package_paths = []
    excluded_temporary = []
    for directory in ("assets", "data", "docs", "references", "scenes", "scripts", "shaders", "tools"):
        for path in sorted((world / directory).rglob("*")):
            if not path.is_file():
                continue
            relative = str(path.relative_to(world))
            if _temporary_path(Path(relative)):
                excluded_temporary.append(relative)
                continue
            # The binary bake is the packaged scene; the text twin stays local.
            if relative == "scenes/authored_world.tscn":
                continue
            if "sources" in path.parts or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if relative.startswith("data/releases/"):
                if not path.is_relative_to(release_path.parent):
                    continue
            elif relative in managed_files or any(relative.startswith(name) for name in managed_dirs):
                continue
            if relative in excluded or path.name.startswith("_preview_"):
                continue
            package_paths.append(path)
    for filename in ("project.godot", "LICENSE", "THIRD_PARTY.md", "README.md"):
        path = world / filename
        if path.is_file():
            package_paths.append(path)
    destination.mkdir(parents=True)
    for path in package_paths:
        relative = path.relative_to(world)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    if source_root and (source_root / "docs").is_dir():
        shutil.copytree(source_root / "docs", destination / "docs", dirs_exist_ok=True, ignore=_ignore_temporary)
    readme = destination / "README.md"
    if readme.is_file():
        readme.write_text(readme.read_text().replace("(../docs/", "(docs/"))
    scene_bindings = _bind_scene_resources(destination, release)
    inventory["release_id"] = release["release_id"]
    inventory["bundled_paths"] = [asset["path"] for asset in inventory["assets"] if (destination / asset["path"]).is_file()]
    write_json_atomic(destination / "ASSET_INVENTORY.json", inventory, indent=1)
    hashes = {str(path.relative_to(destination)): sha256_file(path) for path in sorted(destination.rglob("*")) if path.is_file()}
    report = {"schema": "yellowstone.demo_package.v1", "release_id": release["release_id"],
        "build_id": release["build_id"], "model_variant_id": release["model_variant_id"],
        "scenario_id": release["scenario_id"], "source_commit": release.get("source_commit"),
        "source_identity": sha256_json(source_hashes(source_root)) if source_root else None,
        "scene_resource_bindings": scene_bindings,
        "artifact_hashes": hashes, "godot_version": "4.5.1", "startup_evidence": "unavailable_until_execution",
        "limitations": ["Illustrative ecology; model claims remain unaccepted.",
            "Godot editor runtime required; native executable export unavailable.",
            "Geometry measurements and authored modifications retain distinct provenance."],
        "code_license_scopes": inventory["code_license_scopes"],
        "excluded_asset_paths": sorted(excluded),
        "excluded_temporary_paths": sorted(excluded_temporary)}
    write_json_atomic(destination / "PACKAGE.json", report, indent=1)
    return report


def verify_package(destination: Path) -> None:
    """Reject altered or missing files from an existing demo package."""
    report = load_json(destination / "PACKAGE.json")
    for relative, expected in report["artifact_hashes"].items():
        path = destination / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError("package artifact changed: " + relative)


def main() -> int:
    """Prepare or verify a portable Godot project package."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path, default=Path(__file__).resolve().parents[2] / "yellowstone_midway")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify_package(args.out)
    else:
        report = package_demo(args.world, args.out, source_root=Path(__file__).resolve().parents[2])
        print("demo package", report["release_id"], len(report["artifact_hashes"]), "files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
