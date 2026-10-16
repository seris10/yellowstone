"""Public export selection and source preservation checks."""
import hashlib
import os
import shutil
import subprocess
import sys

import pytest

from tools.export_public import export_public, public_path


def test_export_keeps_code_and_license_without_documents(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    files = {"LICENSE": "Apache-2.0", "yellowstone_python/yellowstone_python/model.py": "x = 1\n",
             "yellowstone_midway/scripts/world.gd": "extends Node\n",
             "yellowstone_python/requirements.txt": "numpy\n",
             "yellowstone_midway/references/bsc5_ReadMe.txt": "Original catalog source terms\n",
             "yellowstone_python/README.md": "Prose\n", "CITATION.cff": "metadata\n",
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
                  "yellowstone_midway/scenes/authored_world.tscn.pre-density-bake",
                  "yellowstone_python/yellowstone_python/AGENTS.md"):
        assert not public_path(__import__("pathlib").Path(value))


def test_export_keeps_root_readme_and_baked_assets():
    for value in ("README.md", "yellowstone_midway/assets/imported/wildlife_motion/bear.glb",
                  "yellowstone_midway/assets/meshes/fauna/bison.glb"):
        assert public_path(__import__("pathlib").Path(value))
