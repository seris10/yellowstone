"""Geometry permission remains separate from motion software licensing."""
from yellowstone_python.common.io import sha256_file, write_json_atomic
from tools.asset_release_inventory import release_inventory


def test_motion_software_license_does_not_clear_unknown_geometry(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "assets").mkdir()
    geometry = tmp_path / "assets/model.glb"
    geometry.write_bytes(b"fixture")
    write_json_atomic(tmp_path / "data/asset_manifest.json", {"assets": []})
    write_json_atomic(tmp_path / "data/wildlife_motion_assets.json", {
        "software_license": "MIT", "assets": [{"id": "animal", "path": "assets/model.glb",
            "geometry_rights": "unknown", "sha256": sha256_file(geometry)}]})
    report = release_inventory(tmp_path)
    assert report["assets"][0]["present"]
    assert report["assets"][0]["public_release_decision"] == "exclude"
    assert not report["assets"][0]["redistribution_status_established"]


def test_owner_confirmed_geometry_is_included_without_changing_scientific_status(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "assets").mkdir()
    geometry = tmp_path / "assets/model.glb"
    geometry.write_bytes(b"fixture")
    write_json_atomic(tmp_path / "data/asset_manifest.json", {"assets": []})
    write_json_atomic(tmp_path / "data/wildlife_motion_assets.json", {"assets": [{
        "id": "animal", "path": "assets/model.glb", "sha256": sha256_file(geometry),
        "geometry_rights": "owner_confirmed", "geometry_owner": "KJR",
        "redistribution_permission": "owner_authorized_project_release", "scientific_acceptance": "not_yet_accepted"}]})
    report = release_inventory(tmp_path)
    assert report["assets"][0]["public_release_decision"] == "include"
    assert report["assets"][0]["scientific_status"] == "not_yet_accepted"
