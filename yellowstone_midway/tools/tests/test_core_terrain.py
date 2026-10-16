"""Registered imagery and residual terrain-normal contract tests."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest


TOOL = Path(__file__).resolve().parents[1] / "prepare_core_terrain.py"
if not TOOL.exists():
    TOOL = Path(__file__).with_name("prepare_core_terrain.py")
SPEC = importlib.util.spec_from_file_location("prepare_core_terrain_detail", TOOL)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def grid(n=7):
    return {"x_min_m": 0.0, "z_min_m": 0.0, "x_max_m": n - 1,
            "z_max_m": n - 1, "nx": n, "nz": n, "cell_m": 1.0}


@pytest.mark.parametrize("shape", [(7, 7), (8, 6)])
@pytest.mark.parametrize("slopes", [(0, 0), (0.2, -0.3), (-1.5, 0.8)])
def test_affine_terrain_has_neutral_residual(shape, slopes):
    z, x = np.indices(shape, dtype=float)
    height = 100 + slopes[0] * x + slopes[1] * z
    result = module._bake_normal_map(height, 1)
    np.testing.assert_array_equal(result, np.broadcast_to([128, 128, 255], result.shape))


def test_residual_green_uses_south_binormal():
    z, x = np.indices((9, 9), dtype=float)
    east = module._bake_normal_map(0.08 * np.sin(x * np.pi / 2), 1)
    south = module._bake_normal_map(0.08 * np.sin(z * np.pi / 2), 1)
    assert east[4, 4, 0] < 128
    assert east[4, 4, 1] == 128
    assert south[4, 4, 1] < 128
    assert south[4, 4, 0] == 128
    assert east[..., 2].min() >= 254


def test_residual_reconstructs_tilted_surface_detail():
    z, x = np.indices((9, 9), dtype=float)
    height = 0.3 * x + 0.2 * z + 0.08 * np.sin(x * np.pi / 2)
    pixel = module._bake_normal_map(height, 1)[4, 4].astype(float) / 255 * 2 - 1
    n = np.array([-0.3, 1, -0.2])
    n /= np.linalg.norm(n)
    t = np.array([1, 0, 0]) - n * n[0]
    t /= np.linalg.norm(t)
    b = np.cross(t, n)
    reconstructed = np.column_stack([t, b, n]) @ pixel
    reconstructed /= np.linalg.norm(reconstructed)
    target = np.array([-0.38, 1, -0.2])
    target /= np.linalg.norm(target)
    np.testing.assert_allclose(reconstructed, target, atol=0.006)


@pytest.mark.parametrize("spacing", [0, -1, float("nan")])
def test_normal_rejects_invalid_spacing(spacing):
    with pytest.raises(ValueError):
        module._bake_normal_map(np.zeros((7, 7)), spacing)


def test_registered_array_preserves_world_coordinates():
    z, x = np.meshgrid(np.arange(16) + 0.5, np.arange(20) + 0.5, indexing="ij")
    values = 2 * x + 3 * z
    target = {"x_min_m": 5.25, "z_min_m": 9.25, "cell_m": 0.5, "nx": 5, "nz": 4}
    actual = module._sample_registered_array(values, [0, 0, 20, 16], target)
    tz, tx = np.meshgrid(9.25 + np.arange(4) * 0.5, 5.25 + np.arange(5) * 0.5, indexing="ij")
    np.testing.assert_allclose(actual, 2 * tx + 3 * tz, atol=1e-6)


def test_imagery_fixture_selects_offset_crop_pixel_centers(tmp_path):
    z, x = np.indices((16, 16), dtype=np.uint8)
    rgb = np.stack([x * 10, z * 10, (x + z) * 5], axis=-1)
    path = tmp_path / "photo.png"
    Image.fromarray(rgb).save(path)
    path.with_suffix(".json").write_text(json.dumps({"local_extent_xz_m": [0, 0, 16, 16]}))
    target = {"x_min_m": 5.5, "z_min_m": 9.5, "cell_m": 1.0, "nx": 3, "nz": 3}
    sampled, meta = module._resample_imagery(path, target)
    np.testing.assert_allclose(sampled, rgb[9:12, 5:8] / 255, atol=1e-7)
    assert meta["source_shape"] == [16, 16]
    assert meta["sampling"] == "bilinear_pixel_centers_to_world_grid_vertices"


def test_registered_imagery_rejects_outside_extent():
    with pytest.raises(ValueError, match="cover"):
        module._sample_registered_array(np.zeros((10, 10)), [0, 0, 5, 5], grid())


def test_relief_has_masked_physical_support():
    rgb = np.zeros((9, 9, 3), dtype=np.float32)
    rgb[2:7, 3:6] = 1
    mask = np.zeros((9, 9), dtype=np.float32)
    mask[1:8, 1:8] = 1
    relief = module._microrelief(rgb, mask)
    assert np.isfinite(relief).all()
    assert relief.min() >= 0
    assert 0 < relief.max() <= 0.080001
    assert np.count_nonzero(relief[mask == 0]) == 0


def test_border_taper_is_zero_on_edges_and_complete_after_margin():
    weight = module._border_weight(grid(33), 12)
    assert np.count_nonzero(weight[0]) == np.count_nonzero(weight[-1]) == 0
    assert weight[16, 6] == 0.5
    assert np.all(weight[12:-12, 12:-12] == 1)


def test_master_uses_rendered_triangle_diagonal(monkeypatch):
    monkeypatch.setattr(module, "MASTER_HALF_M", 0)
    monkeypatch.setattr(module, "MASTER_STEP_M", 1)
    master = np.array([[0, 8], [0, 0]], dtype=float)
    assert module._master_sample(master, 0.25, 0.25) == 2
    assert module._master_sample(master, 0.75, 0.75) == 2


def test_stitch_refresh_retains_interior_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "MASTER_HALF_M", 0)
    monkeypatch.setattr(module, "MASTER_STEP_M", 1)
    monkeypatch.setattr(module, "MASTER_SIZE", 33)
    out = tmp_path / "core"
    out.mkdir()
    height = np.full((33, 33), 30, dtype="<f4")
    height.tofile(out / "core_heightfield.f32")
    for name in ["core_microrelief.f32", "core_normal.png", "stitch.json"]:
        (out / name).write_bytes(b"preserved fixture")
    header = {"grid": grid(33), "status": "fitted_not_validated", "layers": {
        "core_heightfield_m": {"sha256": module._sha256(out / "core_heightfield.f32")},
        "core_normal": {}}}
    (out / "core_terrain.json").write_text(json.dumps(header))
    master = tmp_path / "master.f32"
    np.full((33, 33), 10, dtype="<f4").tofile(master)
    module._refresh_stitch(out, master, tmp_path / "backup")
    updated = np.fromfile(out / "core_heightfield.f32", dtype="<f4").reshape(33, 33)
    assert updated[16, 0] == 10
    assert updated[16, 6] == 20
    assert updated[16, 12] == 30
    assert updated[12:-12, 12:-12].tobytes() == height[12:-12, 12:-12].tobytes()
    meta = json.loads((out / "core_terrain.json").read_text())
    assert meta["status"] == "fitted_not_validated"
    assert meta["stitch_refresh"]["master_source"]["vertical_units"] == "local_m"
    assert meta["layers"]["core_normal"]["status"] == "requires_detail_refresh"


def test_refresh_preserves_heightfield_stitch_and_status(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ROOT", tmp_path)
    out = tmp_path / "core"
    out.mkdir()
    heights = np.full((7, 7), 42, dtype="<f4")
    heights.tofile(out / "core_heightfield.f32")
    (out / "core_microrelief.f32").write_bytes(np.zeros_like(heights).tobytes())
    Image.fromarray(np.full((7, 7, 3), 127, dtype=np.uint8)).save(out / "core_normal.png")
    (out / "stitch.json").write_text('{"authority":"retained"}\n')
    header = {"grid": grid(), "status": "fitted_not_validated",
              "scientific_acceptance": "not_yet_accepted", "layers": {
                  "core_heightfield_m": {"sha256": module._sha256(out / "core_heightfield.f32")},
                  "core_microrelief_m": {"amplitude_m": 0.08}, "core_normal": {}}}
    (out / "core_terrain.json").write_text(json.dumps(header))
    path = tmp_path / "photo.png"
    Image.fromarray(np.full((16, 16, 3), 100, dtype=np.uint8)).save(path)
    path.with_suffix(".json").write_text(json.dumps({"local_extent_xz_m": [-1, -1, 15, 15]}))
    before = {name: (out / name).read_bytes() for name in ["core_heightfield.f32", "stitch.json", "core_normal.png"]}
    backup = tmp_path / "backup"
    module._refresh_detail(out, path, {}, backup)
    after = json.loads((out / "core_terrain.json").read_text())
    assert after["status"] == header["status"]
    assert after["scientific_acceptance"] == "not_yet_accepted"
    assert after["layers"]["core_normal"]["contract"] == "tangent_residual_mesh_frame.v1"
    for name in ["core_heightfield.f32", "stitch.json"]:
        assert (out / name).read_bytes() == before[name]
    assert (backup / "core_normal.png").read_bytes() == before["core_normal.png"]
    normal = np.asarray(Image.open(out / "core_normal.png"))
    np.testing.assert_array_equal(normal, np.broadcast_to([128, 128, 255], normal.shape))


def test_real_detail_ranges_and_normal_contract():
    root = module.ROOT
    path = root / "data" / "core_terrain" / "core_terrain.json"
    if not path.exists():
        pytest.skip("local core products unavailable")
    header = json.loads(path.read_text())
    if header["layers"]["core_normal"].get("contract") != module.NORMAL_CONTRACT:
        pytest.skip("residual detail refresh has not run")
    core = path.parent
    relief = np.fromfile(core / "core_microrelief.f32", dtype="<f4")
    normal = np.asarray(Image.open(core / "core_normal.png"))
    assert np.isfinite(relief).all()
    assert relief.min() >= 0 and relief.max() <= 0.080001
    assert normal.shape == (601, 601, 3)
    assert normal[..., 2].min() >= 128
    assert normal[..., 0].min() < 128 < normal[..., 0].max()
    assert normal[..., 1].min() < 128 < normal[..., 1].max()
    for name, file in [("core_normal", "core_normal.png"), ("core_microrelief_m", "core_microrelief.f32")]:
        assert header["layers"][name]["sha256"] == module._sha256(core / file)
