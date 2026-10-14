"""Lodgepole mesh topology and texture contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ASSET_ROOT = Path(__file__).resolve().parents[2] / "assets/imported/lodgepole"
ARCHETYPES = ("dense", "edge", "open", "sapling", "snag")


def read_primitive(path: Path, document: dict, primitive: dict, attribute: str) -> np.ndarray:
    """Read one contiguous glTF primitive array."""
    reference = primitive["indices"] if attribute == "indices" else primitive["attributes"][attribute]
    accessor = document["accessors"][reference]
    view = document["bufferViews"][accessor["bufferView"]]
    components = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}[accessor["type"]]
    dtype = {5126: "<f4", 5125: "<u4", 5123: "<u2"}[accessor["componentType"]]
    data = (path.parent / document["buffers"][view["buffer"]]["uri"]).read_bytes()
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return np.frombuffer(data, dtype=dtype, count=accessor["count"] * components, offset=offset).reshape(-1, components)


@pytest.mark.parametrize("name", ARCHETYPES)
def test_split_mesh_topology_and_lods(name: str) -> None:
    """Check real tubes, alpha cards, finite arrays and reduced LOD topology."""
    metadata = json.loads((ASSET_ROOT / "lodgepole_metadata.json").read_text())
    counts = []
    for level in range(3):
        path = ASSET_ROOT / f"{name}_lod{level}.gltf"
        document = json.loads(path.read_text())
        expected = {"Bole", "Branches"} if name == "snag" else {"Bole", "Branches", "NeedleCards"}
        assert {mesh["name"] for mesh in document["meshes"]} == expected
        parts = []
        triangles = 0
        for mesh in document["meshes"]:
            for primitive in mesh["primitives"]:
                points = read_primitive(path, document, primitive, "POSITION")
                normals = read_primitive(path, document, primitive, "NORMAL")
                uv = read_primitive(path, document, primitive, "TEXCOORD_0")
                indices = read_primitive(path, document, primitive, "indices").reshape(-1, 3)
                assert np.isfinite(points).all() and np.isfinite(normals).all() and np.isfinite(uv).all()
                assert len(points) == len(normals) == len(uv)
                np.testing.assert_allclose(np.linalg.norm(normals, axis=1), 1.0, atol=0.002)
                assert indices.max() < len(points)
                faces = points[indices]
                areas = np.linalg.norm(np.cross(faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0]), axis=1)
                assert (areas > 1e-10).all()
                if mesh["name"] == "Branches":
                    assert len(indices) >= 72
                    assert np.ptp(points[:, 0]) > 0.5 and np.ptp(points[:, 2]) > 0.5
                    assert np.ptp(normals[:, 1]) > 0.8
                if mesh["name"] == "NeedleCards":
                    assert len(points) % 4 == 0 and len(indices) == len(points) // 2
                    cards = points.reshape(-1, 4, 3)
                    assert (np.linalg.norm(cards[:, 0] - cards[:, 1], axis=1) > 0.02).all()
                    material = document["materials"][primitive["material"]]
                    assert material["alphaMode"] == "MASK" and material["doubleSided"]
                parts.append(points)
                triangles += len(indices)
        points = np.concatenate(parts)
        assert points[:, 1].min() == pytest.approx(0.0, abs=1e-6)
        assert points[:, 1].max() == pytest.approx(metadata["archetypes"][name]["height_m"], abs=1e-5)
        report = next(item for item in metadata["lods"] if item["archetype"] == name and item["lod"] == level)
        np.testing.assert_allclose([points.min(axis=0), points.max(axis=0)], report["bounds_m"], atol=1e-5)
        assert triangles == report["triangles"]
        counts.append(triangles)
    assert counts[0] > counts[1] > counts[2] > 100


def test_authored_dimension_and_needle_provenance() -> None:
    """Check authored dimensions and a transparent paired-needle texture."""
    metadata = json.loads((ASSET_ROOT / "lodgepole_metadata.json").read_text())
    assert metadata["scientific_name"] == "Pinus contorta var. latifolia"
    assert metadata["dimension_provenance"] == "authored" and metadata["uncertainty"] == "unknown"
    assert metadata["lod_ranges_m"] == [[0, 18], [18, 65], [65, 180], [180, 3000]]
    assert set(metadata["archetypes"]) == set(ARCHETYPES)
    assert all(item["needle_fascicle_count"] == 2 for item in metadata["lods"])
    image = np.array(Image.open(ASSET_ROOT / "needle_shoot.png").convert("RGBA"))
    opaque = image[:, :, 3] >= 82
    assert 0.01 < opaque.mean() < 0.6
    mid = image.shape[1] // 2
    assert opaque[:, :mid].sum() > 5000 and opaque[:, mid:].sum() > 5000


@pytest.mark.parametrize("name", ARCHETYPES)
def test_four_billboard_views(name: str) -> None:
    """Check distinct transparent views and positive physical plane dimensions."""
    metadata = json.loads((ASSET_ROOT / "lodgepole_metadata.json").read_text())
    entry = metadata["billboards"][name]
    assert entry["azimuth_degrees"] == [0, 90, 180, 270] and len(entry["views"]) == 4
    assert np.isfinite([entry["width_m"], entry["height_m"], entry["center_y_m"]]).all()
    assert entry["width_m"] > 0 and entry["height_m"] > 0
    hashes = set()
    for basename in entry["views"]:
        assert Path(basename).name == basename
        path = ASSET_ROOT / basename
        hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
        image = np.array(Image.open(path).convert("RGBA"))
        opaque = image[:, :, 3] >= 82
        assert 0.005 < opaque.mean() < 0.85
    assert len(hashes) == 4


@pytest.mark.parametrize("name", ARCHETYPES)
def test_near_architecture_variants_and_exported_graph_hash(name):
    """Require four distinct branch meshes bound to the exported seeded graph library."""
    metadata = json.loads((ASSET_ROOT / "lodgepole_metadata.json").read_text())
    graph_path = ASSET_ROOT / "architecture_library.json"
    assert hashlib.sha256(graph_path.read_bytes()).hexdigest() == metadata["architecture_library_sha256"]
    assert metadata["near_architecture_variants"] == 4
    paths = metadata["near_variant_files"][name]
    hashes = set()
    for filename in paths:
        assert Path(filename).name == filename
        path = ASSET_ROOT / filename
        document = json.loads(path.read_text())
        primitive = next(mesh for mesh in document["meshes"] if mesh["name"] == "Branches")["primitives"][0]
        points = read_primitive(path, document, primitive, "POSITION")
        assert np.isfinite(points).all()
        hashes.add(hashlib.sha256(points.tobytes()).hexdigest())
    assert len(paths) == len(hashes) == 4


def test_alpha_mip_occupancy_and_color_buffers_preserve_source_cutout():
    """Require complete mip chains with bounded alpha-occupancy quantization error."""
    metadata = json.loads((ASSET_ROOT / "lodgepole_metadata.json").read_text())
    assert not metadata["billboard_mips_pending"]
    assert len(metadata["cutout_mips"]) == 22
    for filename, row in metadata["cutout_mips"].items():
        data = (ASSET_ROOT / row["path"]).read_bytes()
        assert len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"]
        assert hashlib.sha256((ASSET_ROOT / filename).read_bytes()).hexdigest() == row["source_sha256"]
        offset = 0
        for level in row["levels"]:
            width, height = level["width"], level["height"]
            assert width == max(1,row["width"] >> level["level"])
            assert height == max(1,row["height"] >> level["level"])
            assert level["offset"] == offset and level["bytes"] == width * height * 4
            rgba = np.frombuffer(data,dtype=np.uint8,count=level["bytes"],offset=offset).reshape(height,width,4)
            coverage = float((rgba[:,:,3] >= row["cutoff"]*255).mean())
            assert coverage == pytest.approx(level["alpha_test_coverage"])
            assert abs(coverage-row["base_coverage"]) <= 1/(width*height)
            offset += level["bytes"]
        assert offset == len(data)
