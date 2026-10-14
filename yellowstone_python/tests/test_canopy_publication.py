"""Canopy publication preserves the exact source surface and rejects stale bytes."""
import hashlib
import json

import pytest

from yellowstone_python.common.canopy_artifacts import CANOPY_RENDER_FILES, copy_render_canopy, copy_forest_floor


@pytest.fixture
def surface(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    artifacts = {}
    for name in CANOPY_RENDER_FILES[1:]:
        payload = name.encode("ascii")
        (source / name).write_bytes(payload)
        artifacts[name] = {"path": name, "bytes": len(payload),
                           "sha256": hashlib.sha256(payload).hexdigest()}
    metadata = {"schema": "yellowstone.unresolved_canopy_render.v1", "artifacts": artifacts}
    (source / CANOPY_RENDER_FILES[0]).write_text(json.dumps(metadata))
    return source, metadata


def test_surface_copy_is_complete_and_byte_exact(surface, tmp_path):
    source, _ = surface
    paths = copy_render_canopy(source, tmp_path / "build")
    assert {path.name for path in paths} == set(CANOPY_RENDER_FILES)
    for path in paths:
        assert path.read_bytes() == (source / path.name).read_bytes()


@pytest.mark.parametrize("failure", ["missing", "changed", "unsafe_path"])
def test_surface_rejects_incomplete_or_changed_sources(surface, tmp_path, failure):
    source, metadata = surface
    name = CANOPY_RENDER_FILES[1]
    if failure == "missing":
        (source / name).unlink()
    elif failure == "changed":
        (source / name).write_bytes(b"different")
    else:
        metadata["artifacts"][name]["path"] = "../" + name
        (source / CANOPY_RENDER_FILES[0]).write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        copy_render_canopy(source, tmp_path / "build")
    assert not (tmp_path / "build/lidar_canopy").exists()


def test_floor_copy_retains_authoring_class(tmp_path):
    source = tmp_path / "forest_floor.json"
    document = {"schema": "yellowstone.forest_floor.v1", "status": "authored",
                "scientific_acceptance": "not_yet_accepted", "quantitative_uncertainty": "unknown"}
    source.write_text(json.dumps(document))
    copied = copy_forest_floor(source, tmp_path / "build")
    assert copied.read_bytes() == source.read_bytes()
    document["status"] = "measured"
    source.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="authoring provenance"):
        copy_forest_floor(source, tmp_path / "other")
