"""Tests for the prepare_core_terrain tool."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
MIDWAY_ROOT = ROOT.parent / "yellowstone_midway"
TOOL = MIDWAY_ROOT / "tools" / "prepare_core_terrain.py"
DEM = MIDWAY_ROOT / "references" / "dem_1m_core.tif"


def _require_output():
    data_dir = MIDWAY_ROOT / "data" / "core_terrain"
    header_path = data_dir / "core_terrain.json"
    stitch_path = data_dir / "stitch.json"
    height_path = data_dir / "core_heightfield.f32"
    micro_path = data_dir / "core_microrelief.f32"
    if not (DEM.exists() and header_path.exists() and stitch_path.exists()
            and height_path.exists() and micro_path.exists()):
        pytest.skip("core terrain outputs are not present")
    return header_path, stitch_path, height_path, micro_path


def test_tool_fails_without_dem(tmp_path):
    out_dir = tmp_path / "out"
    cmd = [sys.executable, str(TOOL),
           "--dem", str(tmp_path / "missing.tif"),
           "--out-dir", str(out_dir)]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert completed.returncode != 0
    assert "missing" in completed.stderr.lower() or \
           "missing" in completed.stdout.lower() or \
           "dem" in completed.stderr.lower()


def test_core_heightfield_shape_and_offset():
    header_path, _, height_path, _ = _require_output()
    header = json.loads(header_path.read_text())
    grid = header["grid"]
    arr = np.fromfile(height_path, dtype="<f4").reshape(grid["nz"], grid["nx"])
    assert arr.shape == (601, 601)
    assert header["vertical_origin_m"] == 2200.0
    assert float(arr.min()) > -200.0
    assert float(arr.max()) < 300.0


def test_microrelief_is_bounded_and_zero_outside_sinter():
    header_path, _, _, micro_path = _require_output()
    header = json.loads(header_path.read_text())
    micro = np.fromfile(micro_path, dtype="<f4")
    assert float(np.nanmax(micro)) <= float(
        header["layers"]["core_microrelief_m"]["amplitude_m"]) + 1e-6
    assert float(np.nanmin(micro)) >= 0.0
    nonzero = int((micro != 0).sum())
    assert nonzero > 0


def test_stitch_edges_match_master_grid_within_tolerance():
    _, stitch_path, _, _ = _require_output()
    stitch = json.loads(stitch_path.read_text())
    for side_name, verts in stitch["edges"].items():
        assert verts, f"side {side_name} should have vertices"
        for v in verts:
            delta = abs(float(v["core_m"]) - float(v["master_m"]))
            # After edge pinning the seam matches master within float32 noise.
            assert delta < 1e-4, (
                f"stitch {side_name} vertex at ({v['x']}, {v['z']}) "
                f"delta {delta:.6f} m exceeds pin tolerance")


def _tool_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("prepare_core_terrain_contract", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("slopes", [(0.0, 0.0), (0.2, -0.1)])
def test_stitch_blend_weight_is_monotone_across_margin(slopes):
    module = _tool_module()
    zz, xx = np.meshgrid(np.arange(1025) * 4 - 2048,
                         np.arange(1025) * 4 - 2048, indexing="ij")
    master = (40 + slopes[0] * xx + slopes[1] * zz).astype(np.float32)
    grid = {"x_min_m": 0.0, "z_min_m": 0.0, "cell_m": 1.0, "nx": 33, "nz": 33}
    z, x = np.indices((33, 33))
    base = (40 + slopes[0] * x + slopes[1] * z).astype(np.float32)
    initial = base + 20
    result, _ = module._pin_edges_to_master(initial, grid, master, margin_m=12)
    weight = (result[16, :17] - base[16, :17]) / 20
    expected = np.minimum(np.arange(17) / 12, 1)
    np.testing.assert_allclose(weight, expected, atol=1e-6)
    assert np.all(np.diff(weight) >= 0)
    assert result[12:-12, 12:-12].tobytes() == initial[12:-12, 12:-12].tobytes()


def _rendered_triangle_sample(height, x, z, x0, z0, step):
    gx, gz = (x - x0) / step, (z - z0) / step
    i = max(0, min(int(np.floor(gx)), height.shape[1] - 2))
    j = max(0, min(int(np.floor(gz)), height.shape[0] - 2))
    fx, fz = gx - i, gz - j
    a, b, c, d = height[j, i], height[j, i + 1], height[j + 1, i], height[j + 1, i + 1]
    return float(a + fx * (b - a) + fz * (c - a) if fx + fz <= 1
                 else d + (1 - fx) * (c - d) + (1 - fz) * (b - d))


@pytest.mark.needs_world
def test_stitch_boundary_matches_rendered_master_authority():
    header_path, stitch_path, height_path, micro_path = _require_output()
    header = json.loads(header_path.read_text())
    stitch = json.loads(stitch_path.read_text())
    source = stitch["sources"][0]
    path = Path(source["path"])
    if not path.is_absolute():
        path = ROOT.parent / path
    master = np.fromfile(path, dtype="<f4").reshape(1025, 1025)
    if source["vertical_units"] == "absolute_m":
        master -= np.float32(2200)
    else:
        assert source["vertical_units"] == "local_m"
    grid = header["grid"]
    height = np.fromfile(height_path, dtype="<f4").reshape(grid["nz"], grid["nx"])
    micro = np.fromfile(micro_path, dtype="<f4").reshape(height.shape)
    assert np.count_nonzero(micro[0]) == np.count_nonzero(micro[-1]) == 0
    assert np.count_nonzero(micro[:, 0]) == np.count_nonzero(micro[:, -1]) == 0
    rendered = (height + micro)[::2, ::2]
    perimeter = [(x, z) for x in np.arange(grid["x_min_m"], grid["x_max_m"] + 1)
                 for z in [grid["z_min_m"], grid["z_max_m"]]]
    perimeter += [(x, z) for z in np.arange(grid["z_min_m"], grid["z_max_m"] + 1)
                  for x in [grid["x_min_m"], grid["x_max_m"]]]
    errors = [abs(_rendered_triangle_sample(rendered, x, z, grid["x_min_m"], grid["z_min_m"], 2)
                  - _rendered_triangle_sample(master, x, z, -2048, -2048, 4)) for x, z in perimeter]
    assert max(errors) < 1e-4


def test_microrelief_is_deterministic():
    _, _, height_path, micro_path = _require_output()
    data = micro_path.read_bytes()
    data2 = micro_path.read_bytes()
    assert data == data2
    heights = height_path.read_bytes()
    heights2 = height_path.read_bytes()
    assert heights == heights2


@pytest.mark.needs_world
def test_core_heights_match_dem_control_points():
    header_path, _, height_path, _ = _require_output()
    if not DEM.exists():
        pytest.skip("real 1 m DEM tile is not present")
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    header = json.loads(header_path.read_text())
    grid = header["grid"]
    core = np.fromfile(height_path, dtype="<f4").reshape(grid["nz"], grid["nx"])
    full = np.asarray(Image.open(DEM), dtype=np.float32)
    j0 = int(round(grid["z_min_m"] + 640))
    i0 = int(round(grid["x_min_m"] + 640))
    # Points chosen well inside the stitch blend margin.
    for (jj, ii) in [(100, 100), (300, 300), (450, 150), (200, 400)]:
        core_val = float(core[jj, ii]) + float(header["vertical_origin_m"])
        dem_val = float(full[j0 + jj, i0 + ii])
        assert abs(core_val - dem_val) < 1.0, (
            f"core vs DEM mismatch at ({jj}, {ii}): {core_val} vs {dem_val}")
