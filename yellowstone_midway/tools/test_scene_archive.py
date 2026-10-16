"""Scene archive integrity and replacement checks."""

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("unpack_scene", Path(__file__).with_name("unpack_scene.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SceneArchiveTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.scene = b'[gd_scene format=3]\n[node name="Example" type="Node3D"]\n'
        archive = gzip.compress(self.scene, mtime=0)
        (self.root / "authored_world.tscn.gz").write_bytes(archive)
        self.manifest = {
            "schema": "yellowstone.scene_archive.v1",
            "archive": {"file": "authored_world.tscn.gz", "bytes": len(archive), "sha256": hashlib.sha256(archive).hexdigest()},
            "scene": {"file": "authored_world.tscn", "bytes": len(self.scene), "sha256": hashlib.sha256(self.scene).hexdigest()},
        }
        self.write_manifest()

    def write_manifest(self):
        (self.root / "authored_world.manifest.json").write_text(json.dumps(self.manifest))

    def test_round_trip_and_idempotence(self):
        self.assertTrue(MODULE.unpack_scene(self.root))
        self.assertEqual((self.root / "authored_world.tscn").read_bytes(), self.scene)
        self.assertFalse(MODULE.unpack_scene(self.root))

    def test_modified_scene_requires_explicit_replacement(self):
        output = self.root / "authored_world.tscn"
        output.write_bytes(b"local edits")
        with self.assertRaises(FileExistsError):
            MODULE.unpack_scene(self.root)
        self.assertEqual(output.read_bytes(), b"local edits")
        self.assertTrue(MODULE.unpack_scene(self.root, force=True))

    def test_corrupt_archive_preserves_existing_scene(self):
        output = self.root / "authored_world.tscn"
        output.write_bytes(b"local edits")
        with (self.root / "authored_world.tscn.gz").open("ab") as stream:
            stream.write(b"corruption")
        with self.assertRaises(ValueError):
            MODULE.unpack_scene(self.root, force=True)
        self.assertEqual(output.read_bytes(), b"local edits")

    def test_declared_output_digest_and_size_are_enforced(self):
        for field, value in [("sha256", "0" * 64), ("bytes", 1), ("bytes", len(self.scene) + 1)]:
            with self.subTest(field=field, value=value):
                original = self.manifest["scene"][field]
                self.manifest["scene"][field] = value
                self.write_manifest()
                with self.assertRaises(ValueError):
                    MODULE.unpack_scene(self.root)
                self.assertFalse((self.root / "authored_world.tscn").exists())
                self.assertEqual(list(self.root.glob(".scene-*.tmp")), [])
                self.manifest["scene"][field] = original

    def test_manifest_cannot_redirect_output(self):
        self.manifest["scene"]["file"] = "../elsewhere.tscn"
        self.write_manifest()
        with self.assertRaises(ValueError):
            MODULE.unpack_scene(self.root)


if __name__ == "__main__":
    unittest.main()
