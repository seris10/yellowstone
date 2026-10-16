"""Terrain color filtering and production byte contracts."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from tools.prepare_color_mips import COLOR_PATHS, mip_chain


def test_black_white_mip_preserves_linear_energy():
    """Require the sRGB encoding of the mean linear radiance."""
    pixels = np.zeros((2, 2, 4), dtype=np.uint8)
    pixels[:, :, 3] = 255
    pixels[0, :, :3] = 255
    data, levels = mip_chain(pixels)
    assert data[:16] == pixels.tobytes()
    assert data[levels[1]["offset"]:] == bytes([188, 188, 188, 255])


def test_transparent_color_does_not_bleed_into_mips():
    """Exclude transparent blue from a red edge and filter alpha linearly."""
    pixels = np.full((2, 2, 4), [0, 0, 255, 0], dtype=np.uint8)
    pixels[0, 0] = [255, 0, 0, 255]
    data, levels = mip_chain(pixels)
    assert data[levels[1]["offset"]:] == bytes([255, 0, 0, 64])


def test_rectangular_chain_and_empty_alpha():
    """Reach one pixel with finite neutral RGB for fully transparent input."""
    pixels = np.full((2, 8, 4), [255, 128, 64, 0], dtype=np.uint8)
    data, levels = mip_chain(pixels)
    assert [(x["width"], x["height"]) for x in levels] == [(8, 2), (4, 1), (2, 1), (1, 1)]
    assert data[levels[1]["offset"]:] == bytes(len(data) - levels[1]["offset"])


@pytest.mark.parametrize("pixels", [np.zeros((3, 4, 4), dtype=np.uint8),
                                   np.zeros((4, 4, 3), dtype=np.uint8),
                                   np.zeros((4, 4, 4), dtype=float)])
def test_invalid_color_input_is_rejected(pixels):
    """Reject incompatible pixel formats and unsupported dimensions."""
    with pytest.raises(ValueError):
        mip_chain(pixels)


def test_production_buffers_match_sources_and_complete_layout():
    """Authenticate every color buffer and unchanged base level."""
    world = Path(__file__).resolve().parents[2] / "yellowstone_midway"
    report = json.loads((world / "assets/textures/color_mips/color_mips.json").read_text())
    assert set(report["entries"]) == set(COLOR_PATHS)
    for source, entry in report["entries"].items():
        source_path, target = world / source, world / entry["path"]
        assert hashlib.sha256(source_path.read_bytes()).hexdigest() == entry["source_sha256"]
        data = target.read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert len(data) == entry["bytes"] == sum(level["bytes"] for level in entry["levels"])
        image = Image.open(source_path).convert("RGBA")
        assert image.size == (entry["width"], entry["height"])
        assert data[:entry["levels"][0]["bytes"]] == image.tobytes()
        assert entry["levels"][-1]["width"] == entry["levels"][-1]["height"] == 1
