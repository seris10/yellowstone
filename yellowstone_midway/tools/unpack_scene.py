"""Restore the baked Godot scene from its lossless archive."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unpack_scene(scene_dir, force=False):
    """Verify and atomically restore the archived scene."""
    scene_dir = Path(scene_dir)
    manifest = json.loads((scene_dir / "authored_world.manifest.json").read_text())
    if manifest.get("schema") != "yellowstone.scene_archive.v1":
        raise ValueError("Unsupported scene archive schema")
    for key, filename in [("archive", "authored_world.tscn.gz"), ("scene", "authored_world.tscn")]:
        record = manifest[key]
        if record.get("file") != filename:
            raise ValueError("Unexpected archive member name")
        if type(record.get("bytes")) is not int or record["bytes"] <= 0:
            raise ValueError("Invalid archive member size")
        digest = record.get("sha256", "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid archive member digest")
    archive = scene_dir / manifest["archive"]["file"]
    destination = scene_dir / manifest["scene"]["file"]
    if archive.stat().st_size != manifest["archive"]["bytes"] or sha256(archive) != manifest["archive"]["sha256"]:
        raise ValueError("Compressed scene checksum mismatch")
    if destination.exists():
        if destination.stat().st_size == manifest["scene"]["bytes"] and sha256(destination) == manifest["scene"]["sha256"]:
            return False
        if not force:
            raise FileExistsError("The scene contains other changes; preserve them before using --force")
    temporary = None
    try:
        digest = hashlib.sha256()
        count = 0
        with tempfile.NamedTemporaryFile(dir=scene_dir, prefix=".scene-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            with gzip.open(archive, "rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    count += len(chunk)
                    if count > manifest["scene"]["bytes"]:
                        raise ValueError("Decompressed scene exceeds its declared size")
                    digest.update(chunk)
                    output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if count != manifest["scene"]["bytes"] or digest.hexdigest() != manifest["scene"]["sha256"]:
            raise ValueError("Decompressed scene checksum mismatch")
        os.replace(temporary, destination)
        return True
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Replace a modified baked scene")
    args = parser.parse_args()
    restored = unpack_scene(Path(__file__).resolve().parents[1] / "scenes", force=args.force)
    print("Baked scene restored and verified." if restored else "Baked scene already matches the archive.")


if __name__ == "__main__":
    main()
