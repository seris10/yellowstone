"""Public export selection and source preservation checks."""
import hashlib
import os
import shutil
import subprocess
import sys

import pytest

from tools.export_public import PUBLIC_PATTERN_LIBRARIES, PUBLIC_PROJECT_DOCUMENTS, export_public, public_path


def test_export_keeps_code_and_license_without_internal_documents(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    files = {"LICENSE": "Apache-2.0", "yellowstone_python/yellowstone_python/model.py": "x = 1\n",
             "yellowstone_midway/scripts/world.gd": "extends Node\n",
             "yellowstone_python/requirements.txt": "numpy\n",
             "yellowstone_midway/references/bsc5_ReadMe.txt": "Original catalog source terms\n",
             "yellowstone_python/internal/README.md": "Prose\n", "CITATION.cff": "metadata\n",
             "yellowstone_python/notebooks/model.ipynb": "{}",
             "yellowstone_python/derived/private.json": "{}",
             "yellowstone_python_spec/notes.md": "Private\n"}
    before = {}
    for relative, text in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        before[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    destination = tmp_path / "public"
    manifest = export_public(source, destination)
    assert set(manifest["files"]) == {"LICENSE", "yellowstone_python/yellowstone_python/model.py",
                                     "yellowstone_midway/scripts/world.gd", "yellowstone_python/requirements.txt",
                                     "yellowstone_midway/references/bsc5_ReadMe.txt"}
    assert all(hashlib.sha256((source / name).read_bytes()).hexdigest() == digest
               for name, digest in before.items())
    assert (destination / "public-export.json").is_file()


def test_export_preserves_reviewed_project_guides(tmp_path):
    source = tmp_path / "source"
    for name in PUBLIC_PROJECT_DOCUMENTS:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Technical guide\n\n" + name + "\n", encoding="utf-8")
    instructions = source / "yellowstone_python/AGENTS.md"
    instructions.write_text("# Instructions\n", encoding="utf-8")
    destination = tmp_path / "export"
    manifest = export_public(source, destination)
    assert set(manifest["files"]) == PUBLIC_PROJECT_DOCUMENTS
    assert not (destination / "yellowstone_python/AGENTS.md").exists()
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == digest
        assert (source / name).read_bytes() == (destination / name).read_bytes()


def test_export_excludes_both_authored_scene_formats(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "LICENSE").write_text("Apache-2.0")
    scene_dir = source / "yellowstone_midway/scenes"
    scene_dir.mkdir(parents=True)
    (scene_dir / "authored_world.tscn").write_text('[gd_scene format=3]\n[node name="World" type="Node3D"]\n')
    (scene_dir / "authored_world.scn").write_bytes(b"\x00\x01binary scene fixture")
    script = source / "yellowstone_midway/scripts/world.gd"
    script.parent.mkdir(parents=True)
    script.write_text("extends Node\n")
    destination = tmp_path / "public"
    manifest = export_public(source, destination)
    assert set(manifest["files"]) == {"LICENSE", "yellowstone_midway/scripts/world.gd"}
    assert not (destination / "yellowstone_midway/scenes/authored_world.tscn").exists()
    assert not (destination / "yellowstone_midway/scenes/authored_world.scn").exists()


def test_export_refuses_overwrite_and_source_descendant(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "LICENSE").write_text("license")
    with pytest.raises(ValueError, match="outside"):
        export_public(source, source / "export")
    with pytest.raises(FileExistsError):
        export_public(source, tmp_path)


def test_export_excludes_internal_and_cache_paths():
    for value in ("archive/a.py", "dashboard/index.html", "yellowstone_python/.venv/a.py",
                  "yellowstone_python/yellowstone_python/HANDOFF_TRACKER.json", "yellowstone_python/.env", "yellowstone_python/work/bench.py", "yellowstone_python/outputs/report.json", "yellowstone_midway/references/README.txt", "yellowstone_python/build/lib/model.py",
                  "yellowstone_python/dist/model.whl",
                  "yellowstone_python/data/lidar/raw/tile.laz",
                  "yellowstone_midway/assets/imported/wildlife_motion/sources/bear_source.glb",
                  "yellowstone_midway/.publish-abc123.receipt.json",
                  "yellowstone_midway/scenes/authored_world.tscn",
                  "yellowstone_midway/scenes/authored_world.scn",
                  "yellowstone_midway/scenes/authored_world.tscn.pre-density-bake",
                  "yellowstone_python/yellowstone_python/AGENTS.md"):
        assert not public_path(__import__("pathlib").Path(value))


def test_export_keeps_root_readme_and_baked_assets():
    for value in ("README.md", "yellowstone_midway/assets/imported/wildlife_motion/bear.glb",
                  "yellowstone_midway/assets/meshes/fauna/bison.glb"):
        assert public_path(__import__("pathlib").Path(value))


def test_exported_checker_loads_its_library(tmp_path, repo_root):
    source = tmp_path / "source"
    names = {"yellowstone_python/tools/check_ai_tells.py",
             "yellowstone_python/tools/check_comment_style.py"} | PUBLIC_PATTERN_LIBRARIES
    for name in names:
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root.parent / name, target)
    private = source / "yellowstone_python_spec/ai-tells/library/private.json"
    private.write_text("{}")
    destination = tmp_path / "export"
    manifest = export_public(source, destination)
    assert set(manifest["files"]) == names
    target = destination / "yellowstone_python/sample.py"
    target.write_text("# Temperature in C.\n")
    command = [sys.executable, str(destination / "yellowstone_python/tools/check_ai_tells.py"), str(target)]
    env = {key: value for key, value in os.environ.items() if key != "AI_TELLS_LIBRARY"}
    clean = subprocess.run(command, cwd=destination, env=env, capture_output=True, text=True)
    assert clean.returncode == 0, clean.stderr
    # ai-tells: ignore
    target.write_text("# We clamp the value, never silently.\n")
    bad = subprocess.run(command, cwd=destination, env=env, capture_output=True, text=True)
    assert bad.returncode == 1
    assert "house-first_person" in bad.stdout
    for name in PUBLIC_PATTERN_LIBRARIES:
        (destination / name).unlink()
    missing = subprocess.run(command, cwd=destination, env=env, capture_output=True, text=True)
    assert missing.returncode == 2
    assert "library error:" in missing.stderr
