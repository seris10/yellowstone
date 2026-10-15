"""Bind post-import runtime bytes for reproducible package startup checks."""
from pathlib import Path
import hashlib
import json
import sys

package = Path(sys.argv[1]).resolve()
report = json.loads((package / "PACKAGE.json").read_text())
paths = [package / "project.godot"]
for directory in ("assets", "data", "references", "scenes", "scripts", "shaders", "tools"):
    paths.extend(path for path in (package / directory).rglob("*")
                 if path.is_file() and path.name != ".DS_Store" and "__pycache__" not in path.parts)
inventory = {}
for path in sorted(paths):
    with path.open("rb") as stream:
        inventory[str(path.relative_to(package))] = hashlib.file_digest(stream, "sha256").hexdigest()
value = {"schema": "yellowstone.runtime_inventory.v1", "release_id": report["release_id"],
         "build_id": report["build_id"], "artifact_hashes": inventory,
         "scope": "Post-import runtime files; documentation and verification metadata are excluded."}
(package / "RUNTIME.json").write_text(json.dumps(value, indent=1) + "\n")
print("Runtime inventory:", len(inventory), "files", report["release_id"])
