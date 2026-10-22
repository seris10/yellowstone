"""Impostor sprite luminance guard against dark or washed-out billboard bakes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from normalize_lodgepole_impostors import ASSETS, linear_to_srgb, opaque_mean_luminance

import numpy as np
from PIL import Image


def test_billboard_sprites_hold_display_luminance_range():
    sprites = sorted(ASSETS.glob("*_billboard_*.png"))
    assert len(sprites) == 80
    for path in sprites:
        pixels = np.asarray(Image.open(path).convert("RGBA"), dtype=np.float64) / 255
        luminance = float(linear_to_srgb(np.array(opaque_mean_luminance(pixels))))
        assert 0.25 <= luminance <= 0.45, "%s luminance %.3f" % (path.name, luminance)
