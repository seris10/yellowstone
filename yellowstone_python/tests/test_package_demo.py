"""Portable package preserves one generation and rejects altered bytes."""
import pytest

from tests.test_release_generations import build_fixture, project
from yellowstone_python.common.io import write_json_atomic
from yellowstone_python.publish import publish_generation
from tools.package_demo import package_demo, verify_package


def test_package_has_one_complete_release_and_excludes_unknown_assets(tmp_path, project):
    (project / "scenes").mkdir()
    (project / "scenes/authored_world.scn").write_bytes(b"\x00\x01binary scene fixture")
    (project / "scenes/authored_world.tscn").write_text('[gd_scene format=3]\n[node name="World" type="Node3D"]\n')
    (project / "assets").mkdir()
    (project / "assets/unknown.glb").write_bytes(b"unknown fixture")
    (project / "docs").mkdir()
    (project / "docs/geography.md").write_text("Frozen geographic source record.\n")
    (project / "README.md").write_text("[Geography](docs/geography.md) [Current evidence](../docs/PORTFOLIO.md)\n")
    source = tmp_path / "source"
    (source / "docs").mkdir(parents=True)
    (source / "docs/PORTFOLIO.md").write_text("Measured geography, simulated state, authored assumptions.\n")
    write_json_atomic(project / "data/asset_manifest.json", {"assets": [{
        "id": "unknown", "included": True, "files": [{"path": "assets/unknown.glb"}]}]})
    write_json_atomic(project / "data/wildlife_motion_assets.json", {"assets": []})
    first = publish_generation(build_fixture(tmp_path, "a"), project)
    second = publish_generation(build_fixture(tmp_path, "b", optional=False), project)
    destination = tmp_path / "demo"
    report = package_demo(project, destination, source_root=source)
    assert report["release_id"] == second["release_id"]
    assert not (destination / "data/releases" / first["release_id"]).exists()
    assert not (destination / "assets/unknown.glb").exists()
    assert (destination / "scenes/authored_world.scn").is_file()
    assert not (destination / "scenes/authored_world.tscn").exists()
    assert (destination / "docs/geography.md").is_file()
    assert (destination / "docs/PORTFOLIO.md").is_file()
    assert "(docs/PORTFOLIO.md)" in (destination / "README.md").read_text()
    verify_package(destination)
    (destination / "scenes/authored_world.scn").write_bytes(b"changed")
    with pytest.raises(ValueError, match="package artifact changed"):
        verify_package(destination)


def test_package_requires_the_binary_bake(tmp_path, project):
    write_json_atomic(project / "data/asset_manifest.json", {"assets": []})
    write_json_atomic(project / "data/wildlife_motion_assets.json", {"assets": []})
    (project / "scenes").mkdir()
    (project / "scenes/authored_world.tscn").write_text('[gd_scene format=3]\n[node name="World" type="Node3D"]\n')
    publish_generation(build_fixture(tmp_path), project)
    with pytest.raises(ValueError, match="the offline world bake is required"):
        package_demo(project, tmp_path / "demo")


@pytest.mark.parametrize("optional", [False, True])
def test_baked_texture_access_uses_the_generation_or_explicit_absence(tmp_path, project, optional):
    write_json_atomic(project / "data/asset_manifest.json", {"assets": []})
    write_json_atomic(project / "data/wildlife_motion_assets.json", {"assets": []})
    (project / "scenes").mkdir()
    (project / "scenes/authored_world.scn").write_bytes(b"\x00\x01binary scene fixture")
    (project / "scenes/authored_world.tscn").write_text(
        '[gd_scene format=3]\n[ext_resource type="Texture2D" path="res://assets/textures/pool_ramps/ramp.png" id="ramp"]\n'
        '[sub_resource type="StandardMaterial3D" id="material"]\nalbedo_texture = ExtResource("ramp")\n'
        '[node name="World" type="Node3D"]\n')
    (project / "scenes/handcrafted_details.tscn").write_text(
        '[gd_scene format=3]\n[ext_resource type="Texture2D" path="res://assets/textures/pool_ramps/ramp.png" id="ramp"]\n'
        '[sub_resource type="StandardMaterial3D" id="material"]\nalbedo_texture = ExtResource("ramp")\n'
        '[node name="Details" type="Node3D"]\n')
    release = publish_generation(build_fixture(tmp_path, optional=optional), project)
    destination = tmp_path / "demo"
    report = package_demo(project, destination)
    assert (destination / "scenes/authored_world.scn").read_bytes() == b"\x00\x01binary scene fixture"
    assert not (destination / "scenes/authored_world.tscn").exists()
    scene = (destination / "scenes/handcrafted_details.tscn").read_text()
    if optional:
        target = "data/releases/" + release["release_id"] + "/assets/textures/pool_ramps/ramp.png"
        assert 'path="res://' + target + '"' in scene
        assert (destination / target).is_file()
    else:
        assert "ExtResource" not in scene and "albedo_texture = null" in scene
    assert report["scene_resource_bindings"]
    verify_package(destination)


def test_package_drops_backups_and_os_files_but_retains_runtime_sidecars(tmp_path, project):
    write_json_atomic(project / "data/asset_manifest.json", {"assets": []})
    write_json_atomic(project / "data/wildlife_motion_assets.json", {"assets": []})
    (project / "scenes").mkdir()
    (project / "scenes/authored_world.scn").write_bytes(b"\x00\x01binary scene fixture")
    temporary = ["scenes/.DS_Store", "scenes/._authored_world.tscn",
                 "scenes/authored_world.tscn.pre-density-bake", "scenes/authored_world.tscn.pre-flora-bake",
                 "scenes/authored_world.tscn.bak", "scripts/world.gd~", "scripts/world.gd.swp",
                 "docs/report.md.tmp", "docs/cache/__pycache__/analysis.pyc"]
    retained = ["scripts/world.gd.uid", "assets/textures/texture.png.import", "docs/pre-bake-checklist.md"]
    for name in temporary + retained:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    source = tmp_path / "source"
    (source / "docs").mkdir(parents=True)
    (source / "docs/.DS_Store").write_text("finder metadata")
    (source / "docs/notes.md.bak").write_text("backup")
    (source / "docs/PORTFOLIO.md").write_text("release documentation")
    publish_generation(build_fixture(tmp_path), project)
    destination = tmp_path / "demo"
    report = package_demo(project, destination, source_root=source)
    assert set(report["excluded_temporary_paths"]) == set(temporary)
    assert all(not (destination / name).exists() for name in temporary)
    assert all((destination / name).is_file() for name in retained)
    assert not (destination / "docs/.DS_Store").exists()
    assert not (destination / "docs/notes.md.bak").exists()
    assert (destination / "docs/PORTFOLIO.md").is_file()
    verify_package(destination)


def test_package_rejects_a_baked_dependency_that_hygiene_would_exclude(tmp_path, project):
    write_json_atomic(project / "data/asset_manifest.json", {"assets": []})
    write_json_atomic(project / "data/wildlife_motion_assets.json", {"assets": []})
    (project / "scenes").mkdir()
    (project / "scenes/authored_world.scn").write_bytes(b"\x00\x01binary scene fixture")
    (project / "scenes/handcrafted_details.tscn").write_text(
        '[gd_scene format=3]\n[ext_resource type="PackedScene" path="res://scenes/source.tscn.bak" id="backup"]\n'
        '[node name="Details" type="Node3D"]\n')
    (project / "scenes/source.tscn.bak").write_text('[gd_scene format=3]\n')
    publish_generation(build_fixture(tmp_path), project)
    with pytest.raises(ValueError, match="baked resource excluded or missing: scenes/source.tscn.bak"):
        package_demo(project, tmp_path / "demo")
