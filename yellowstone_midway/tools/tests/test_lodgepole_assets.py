"""Lodgepole mesh topology and texture contracts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scipy.ndimage import map_coordinates

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
                    assert (np.linalg.norm(cards[:, 0] - cards[:, 1], axis=1) > 0.001).all()
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


def sampled_alpha(image: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Evaluate held-out UV samples through SciPy's independent bilinear sampler."""
    height, width = image.shape
    return map_coordinates(image, [uv[:, 1]*height-.5, uv[:, 0]*width-.5], order=1, mode="nearest")


def test_alpha_mip_filtered_coverage_and_color_buffers_preserve_source_cutout():
    """Check actual buffers under held-out bilinear and trilinear sampling."""
    metadata = json.loads((ASSET_ROOT / "lodgepole_metadata.json").read_text())
    assert not metadata["billboard_mips_pending"]
    assert set(metadata["cutout_mips"]) == {
        "needle_shoot.png", "needle_cluster.png", "needle_supported.png",
        *(path.name for path in ASSET_ROOT.glob("*_billboard_*.png")),
    }
    assert set(metadata["variant_billboards"]) == set(ARCHETYPES)
    assert all(len(variants) == 4 for variants in metadata["variant_billboards"].values())
    uv = np.random.default_rng(28853).random((50000, 2))
    for filename, row in metadata["cutout_mips"].items():
        data = (ASSET_ROOT / row["path"]).read_bytes()
        assert len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"]
        assert hashlib.sha256((ASSET_ROOT / filename).read_bytes()).hexdigest() == row["source_sha256"]
        assert row["filter_address_mode"] == "clamp_to_edge"
        offset, previous = 0, None
        source = np.array(Image.open(ASSET_ROOT / filename).convert("RGBA"))
        target = float((sampled_alpha(source[:, :, 3]/255, uv) >= row["cutoff"]).mean())
        assert target == pytest.approx(row["filtered_coverage_target"], abs=.01)
        for level in row["levels"]:
            width, height = level["width"], level["height"]
            assert width == max(1, row["width"] >> level["level"])
            assert height == max(1, row["height"] >> level["level"])
            assert level["offset"] == offset and level["bytes"] == width * height * 4
            rgba = np.frombuffer(data, dtype=np.uint8, count=level["bytes"], offset=offset).reshape(height, width, 4)
            if level["level"] == 0:
                np.testing.assert_array_equal(rgba, source)
            sampled = sampled_alpha(rgba[:, :, 3]/255, uv)
            coverage = float((sampled >= row["cutoff"]).mean())
            assert coverage == pytest.approx(level["bilinear_coverage"], abs=.01)
            assert rgba[:, :, 3].max() >= row["cutoff"]*255
            if width*height >= 32:
                assert abs(coverage-target) <= .025, (filename, level["level"], coverage, target)
                if previous is not None:
                    for fraction in (.25, .5, .75):
                        blended = float((previous*(1-fraction)+sampled*fraction >= row["cutoff"]).mean())
                        assert abs(blended-target) <= .025, (filename, level["level"], fraction, blended, target)
            elif width*height == 1:
                assert level["calibration_mode"] == "terminal_single_texel_conservative_visibility"
            previous = sampled
            offset += level["bytes"]
        assert offset == len(data)


def test_filtered_mip_authoring_is_deterministic_and_handles_empty_coverage(tmp_path):
    """Retain source bytes, bound filter erosion and preserve empty transparency."""
    spec = importlib.util.spec_from_file_location("lodgepole_mip_author", ASSET_ROOT.parents[2]/"tools/author_lodgepole.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path/"source.png"
    path.write_bytes((ASSET_ROOT/"needle_shoot.png").read_bytes())
    original = path.read_bytes()
    first = module.cutout_mip_chain(path)
    second = module.cutout_mip_chain(path)
    assert first == second and path.read_bytes() == original
    level = first["levels"][7]
    assert abs(level["bilinear_coverage"]-first["filtered_coverage_target"]) < .02
    assert max(abs(value-first["filtered_coverage_target"]) for value in level["trilinear_coverage_from_previous"]) < .02
    empty = tmp_path/"empty.png"
    Image.new("RGBA", (16, 32), (30, 90, 20, 0)).save(empty)
    report = module.cutout_mip_chain(empty)
    assert report["filtered_coverage_target"] == 0
    assert all(level["bilinear_coverage"] == 0 for level in report["levels"])
    color_path = tmp_path/"color.png"
    Image.fromarray(np.array([[[255, 0, 0, 255], [0, 255, 0, 255]]], dtype=np.uint8)).save(color_path)
    color_report = module.cutout_mip_chain(color_path)
    color_data = (tmp_path/color_report["path"]).read_bytes()
    np.testing.assert_allclose(list(color_data[-4:]), [187, 187, 0, 255], atol=1)
    assert color_report["color_filter_space"] == "linear_sRGB"
    with pytest.raises(ValueError, match="Alpha cutoff"):
        module.cutout_mip_chain(path, 0)


def test_twig_ring_reduction_preserves_curved_source_axes():
    """Remove redundant straight rings while retaining a genuinely bent source twig."""
    spec = importlib.util.spec_from_file_location("lodgepole_geometry_author", ASSET_ROOT.parents[2]/"tools/author_lodgepole.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    graph = module.generate_architecture(module.ARCHETYPES["sapling"], 24398)
    original = json.dumps(graph, sort_keys=True)
    surfaces, _ = module.build_tree(graph["dimensions_m"], 0, 0, architecture=graph)
    twigs = {axis["id"] for axis in graph["axes"] if axis["order"] == 2}
    assert all(tube["rings"] == 2 for tube in surfaces[1].tubes if tube["identity"] in twigs)
    assert json.dumps(graph, sort_keys=True) == original
    curved = next(axis for axis in graph["axes"] if axis["order"] == 2)
    curved["points_m"][1][0] += .07
    for shoot in graph["shoots"]:
        if shoot["parent_id"] != curved["id"]:
            continue
        index = shoot["attachment_fraction"] * 2
        lower = min(int(index), 1)
        weight = index - lower
        base = np.asarray(curved["points_m"][lower])*(1-weight) + np.asarray(curved["points_m"][lower+1])*weight
        delta = base - shoot["base_m"]
        shoot["base_m"] = base.tolist()
        shoot["tip_m"] = (np.asarray(shoot["tip_m"]) + delta).tolist()
    surfaces, _ = module.build_tree(graph["dimensions_m"], 0, 0, architecture=graph)
    tube = next(item for item in surfaces[1].tubes if item["identity"] == curved["id"])
    assert tube["rings"] == 3
