"""Motion input domains and serialized animation contracts."""
from __future__ import annotations

import numpy as np
import pytest

from yellowstone_python.wildlife_motion.birds import BirdEngine, paddle_cycle
from yellowstone_python.wildlife_motion.calibration import fit_periodic_track
from yellowstone_python.wildlife_motion.core import AssetError, Skeleton, two_bone_ik, unit
from yellowstone_python.wildlife_motion.gltf import accessor, export_asset, read_glb
from yellowstone_python.wildlife_motion.mammals import foot_cycle, stride_speed
from yellowstone_python.wildlife_motion.species import get_profile
from yellowstone_python.wildlife_motion.synthetic import bird_proxy
from yellowstone_python.wildlife_motion.water import WaterConfig, simulate
from yellowstone_python.wildlife_motion.asset_audit import audit_asset


@pytest.mark.parametrize("change", [{"radii_m": (1, float("nan"), 1)},
                                   {"current_m_s": (0, float("inf"), 0)}])
def test_water_vectors_require_finite_values(change):
    with pytest.raises(ValueError):
        WaterConfig(**change)


def test_short_water_trajectory_has_start_and_end():
    result = simulate(WaterConfig(foot_area_m2=0, wave_amplitude_m=0), 0.001, 1)
    assert len(result["times"]) == 2
    assert result["times"][-1] == 0.001


@pytest.mark.parametrize("change", [{"frequency_hz": float("nan")},
    {"flap_deg": float("inf")}, {"frequency_hz": 0}])
def test_bird_controls_reject_nonfinite_and_zero_frequency(change):
    _, skeleton, _, _ = bird_proxy(True)
    with pytest.raises(ValueError):
        BirdEngine(skeleton, get_profile("mallard")).parameters("Flight", change)


@pytest.mark.parametrize("function,args", [(unit, ([float("nan"), 0, 0],)),
    (two_bone_ik, ([0, 0, 0], [1, float("inf"), 0], 1, 1, [0, 0, 1])),
    (foot_cycle, (float("nan"), .7, 1, .1)),
    (stride_speed, (1, float("inf"), .7)),
    (paddle_cycle, (0, float("nan"), .7, 1, .1))])
def test_nonfinite_motion_controls_rejected(function, args):
    with pytest.raises(ValueError):
        function(*args)


def test_direction_fallback_is_normalized():
    np.testing.assert_array_equal(unit([0, 0, 0], [0, 3, 0]), [0, 1, 0])


@pytest.mark.parametrize("indices", [[2], [-1], [0, 0], []])
def test_skeleton_groups_are_valid(indices):
    with pytest.raises(ValueError):
        Skeleton(["root", "child"], [-1, 0], [[0, 0, 0], [0, 1, 0]], {"body": indices})


@pytest.mark.parametrize("offset,stride,normalized", [(-4, 12, False), (0, 13, False),
                                                     (0, 12, True)])
def test_accessor_rejects_invalid_layout(offset, stride, normalized):
    document = {"accessors": [{"bufferView": 0, "componentType": 5126,
        "type": "VEC3", "count": 1, "byteOffset": offset, "normalized": normalized}],
        "bufferViews": [{"byteLength": 12, "byteStride": stride}]}
    with pytest.raises(AssetError):
        accessor(document, bytes(12), 0)


def test_skinned_mesh_has_scene_root(tmp_path):
    asset, skeleton, joints, weights = bird_proxy(True)
    engine = BirdEngine(skeleton, get_profile("mallard"))
    path = tmp_path / "bird.glb"
    export_asset(asset, path, skeleton, joints, weights, engine.clips(["Flight"], cycles=1))
    document, _ = read_glb(path)
    mesh_node = next(i for i, n in enumerate(document["nodes"]) if "skin" in n)
    assert mesh_node in document["scenes"][0]["nodes"]
    audit = audit_asset(path, samples=3)
    assert audit["clips"][0]["surface_loop_error_asset_units"] < 1e-5


def test_periodic_fit_rejects_nonfinite_frequency():
    with pytest.raises(ValueError):
        fit_periodic_track(np.arange(20), np.arange(20), float("nan"))


def test_tangents_follow_coordinate_transform(tmp_path):
    asset, _, _, _ = bird_proxy(True)
    tangent = np.cross(asset.normals, np.array([0.0, 1.0, 0.0]))
    invalid = np.linalg.norm(tangent, axis=1) < 1e-7
    tangent[invalid] = np.cross(asset.normals[invalid], np.array([1.0, 0.0, 0.0]))
    tangent /= np.linalg.norm(tangent, axis=1, keepdims=True)
    asset.tangents = np.c_[tangent, np.ones(len(tangent))]
    matrix = np.eye(4)
    matrix[:3, :3] = np.diag([-2.0, 1.0, .5])
    transformed = asset.transformed(matrix)
    np.testing.assert_allclose(np.sum(transformed.tangents[:, :3]*transformed.normals, axis=1),
                               0, atol=1e-12)
    np.testing.assert_allclose(np.linalg.norm(transformed.tangents[:, :3], axis=1), 1, atol=1e-12)
    assert np.all(transformed.tangents[:, 3] == -1)
    path = tmp_path / "tangent.glb"
    export_asset(transformed, path)
    document, blob = read_glb(path)
    attribute = document["meshes"][0]["primitives"][0]["attributes"]["TANGENT"]
    np.testing.assert_allclose(accessor(document, blob, attribute), transformed.tangents, atol=1e-6)


def test_degenerate_uv_tangents_get_finite_orthogonal_frames():
    asset, _, _, _ = bird_proxy(True)
    asset.tangents = np.c_[np.zeros_like(asset.normals), np.ones(len(asset.normals))]
    transformed = asset.transformed(np.eye(4))
    directions = transformed.tangents[:, :3]
    assert np.isfinite(directions).all()
    np.testing.assert_allclose(np.linalg.norm(directions, axis=1), 1, atol=1e-12)
    np.testing.assert_allclose(np.sum(directions*transformed.normals, axis=1), 0, atol=1e-12)
    assert transformed.metadata["tangent_frame_repair"]["count"] == len(directions)


@pytest.mark.parametrize("index", [-1, 1])
def test_accessor_indices_are_nonnegative_and_present(index):
    with pytest.raises(AssetError):
        accessor({"accessors": []}, b"", index)


def test_pose_time_is_finite():
    _, skeleton, _, _ = bird_proxy(True)
    with pytest.raises(ValueError):
        BirdEngine(skeleton, get_profile("mallard")).pose(float("inf"), "Flight")


def test_foot_spacing_is_nonnegative():
    with pytest.raises(ValueError):
        WaterConfig(foot_separation_m=-1)


@pytest.mark.needs_world
def test_badger_preserves_supplied_pbr_channels():
    from tests.paths import MIDWAY
    from yellowstone_python.wildlife_motion.gltf import read_glb
    import json

    path = MIDWAY / "assets/imported/wildlife_motion/badger_animated.glb"
    manifest = MIDWAY / "data/wildlife_motion_assets.json"
    if not path.exists() or not manifest.exists():
        pytest.skip("wildlife motion assets are unavailable")
    document, _ = read_glb(path)
    material = document["materials"][0]
    assert "normalTexture" in material
    assert "baseColorTexture" in material["pbrMetallicRoughness"]
    assert "metallicRoughnessTexture" in material["pbrMetallicRoughness"]
    assert "TANGENT" in document["meshes"][0]["primitives"][0]["attributes"]
    record = next(a for a in json.loads(manifest.read_text())["assets"] if a["id"] == "badger")
    assert len(record["source_texture_sha256"]) == 3
    assert all(image["dimensions"] == [2048, 2048] for image in record["audit"]["images"])
    assert record["audit"]["triangles"] <= 30000


@pytest.mark.needs_world
@pytest.mark.parametrize("kind,profile,forward", [("black_bear", "black_bear", "+z"),
                                               ("canada_lynx", "canada_lynx", "-x")])
def test_supplied_mammals_retain_species_textures_and_uvs(kind, profile, forward):
    from tests.paths import MIDWAY
    import json

    root = MIDWAY / "assets/imported/wildlife_motion"
    path = root / (kind+"_animated.glb")
    manifest_path = MIDWAY / "data/wildlife_motion_assets.json"
    if not path.exists() or not manifest_path.exists():
        pytest.skip("supplied wildlife derivatives are unavailable")
    manifest = json.loads(manifest_path.read_text())
    record = next(row for row in manifest["assets"] if row["id"] == kind)
    document, blob = read_glb(path)
    source_path = root / "sources" / (kind+"_runtime_source.glb")
    if not source_path.is_file():
        pytest.skip("original reduction source is required for UV comparison: " + str(source_path))
    source, source_blob = read_glb(source_path)
    attrs = document["meshes"][0]["primitives"][0]["attributes"]
    source_attrs = source["meshes"][0]["primitives"][0]["attributes"]
    np.testing.assert_array_equal(accessor(document, blob, attrs["TEXCOORD_0"]),
                                  accessor(source, source_blob, source_attrs["TEXCOORD_0"]))
    assert "TANGENT" in attrs
    assert document["extras"]["wildlife_motion"]["rig"]["metadata"]["species"] == profile
    assert record["source_axes"] == {"forward": forward, "up": "+y"}
    assert len(record["source_texture_sha256"]) == 3
    assert record["geometry_reduction"]["runtime_triangles"] <= 30000
    assert all(image["dimensions"] == [2048, 2048] for image in record["audit"]["images"])
    assert all(clip["sampled_finite"] for clip in record["audit"]["clips"])
    mapping = manifest["wildlife_species_asset_map"][kind]
    assert mapping["path"].endswith(kind+"_animated.glb")
    assert mapping["geometry_rights"] == "owner_confirmed"
    assert mapping["geometry_owner"] == "KJR"
    assert mapping["redistribution_permission"] == "owner_authorized_project_release"
