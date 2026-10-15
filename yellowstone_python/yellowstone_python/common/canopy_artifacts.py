"""Verified canopy surface artifacts shared by build and publication."""
from pathlib import Path
import shutil

from yellowstone_python.common.io import load_json, sha256_file


CANOPY_RENDER_FILES = (
    "unresolved_render_canopy.json", "canopy_top_scene_y.f32",
    "cover_fraction.f32", "ground_scene_y.f32", "unresolved_cells.u8",
    "unresolved_render_mask.png", "valid_fraction.f32", "valid_support.png",
)
FOREST_FLOOR_FILE = "forest_floor.json"


def copy_forest_floor(source: Path, build: Path) -> Path | None:
    """Preserve authored floor records without promoting them to observations."""
    if not source.is_file():
        return None
    document = load_json(source)
    if (document.get("schema") != "yellowstone.forest_floor.v1"
            or document.get("status") != "authored"
            or document.get("scientific_acceptance") != "not_yet_accepted"
            or document.get("quantitative_uncertainty") != "unknown"):
        raise ValueError("forest floor requires explicit unvalidated authoring provenance")
    build.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copy2(source, build / FOREST_FLOOR_FILE))


def copy_render_canopy(source: Path, build: Path) -> list[Path]:
    """Copy the complete surface after verifying every declared byte and hash."""
    metadata = source / CANOPY_RENDER_FILES[0]
    if not metadata.is_file():
        return []
    document = load_json(metadata)
    if document.get("schema") != "yellowstone.unresolved_canopy_render.v1":
        raise ValueError("unsupported canopy render schema")
    artifacts = document.get("artifacts", {})
    expected = set(CANOPY_RENDER_FILES[1:])
    paths = [entry.get("path") for entry in artifacts.values()]
    if len(paths) != len(expected) or set(paths) != expected:
        raise ValueError("canopy render artifacts do not match the declared surface contract")
    for entry in artifacts.values():
        path = source / entry["path"]
        if (not path.is_file() or path.stat().st_size != entry["bytes"]
                or sha256_file(path) != entry["sha256"]):
            raise ValueError(f"canopy render artifact checksum or size mismatch: {path.name}")
    destination = build / "lidar_canopy"
    destination.mkdir(parents=True, exist_ok=True)
    return [Path(shutil.copy2(source / name, destination / name))
            for name in CANOPY_RENDER_FILES]
