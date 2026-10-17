"""Linear-light luminance rebalance for baked lodgepole impostor sprites.

Sprites need author_lodgepole.py --mipmaps-only afterwards to refresh mip buffers and hashes.
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets/imported/lodgepole"
# sRGB-space opaque-mean luminance target; near-tree sunlit renders near 0.41 and shaded near 0.10.
TARGET_LUM = 0.30
ALPHA_CUTOFF = 0.32


def srgb_to_linear(channel: np.ndarray) -> np.ndarray:
    """Decode sRGB channel values into linear light."""
    return np.where(channel <= 0.04045, channel / 12.92, ((channel + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(channel: np.ndarray) -> np.ndarray:
    """Encode linear-light channel values into sRGB."""
    return np.where(channel <= 0.0031308, channel * 12.92, 1.055 * np.clip(channel, 0, None) ** (1 / 2.4) - 0.055)


def opaque_mean_luminance(pixels: np.ndarray) -> float:
    """Return the linear-light mean luminance of opaque texels."""
    mask = pixels[:, :, 3] >= ALPHA_CUTOFF
    linear = srgb_to_linear(pixels[:, :, :3][mask])
    return float((linear * [0.2126, 0.7152, 0.0722]).sum(axis=1).mean())


def normalize_sprite(path: Path) -> dict:
    """Scale one sprite in linear light to the luminance target."""
    image = Image.open(path).convert("RGBA")
    pixels = np.asarray(image, dtype=np.float64) / 255
    luminance = opaque_mean_luminance(pixels)
    current = float(linear_to_srgb(np.array(luminance)))
    scale = TARGET_LUM / current
    pixels[:, :, :3] = np.clip(pixels[:, :, :3] * scale, 0, 1)
    Image.fromarray((pixels * 255).astype(np.uint8)).save(path)
    after = opaque_mean_luminance(np.asarray(Image.open(path), dtype=np.float64) / 255)
    return {"sprite": path.name, "luminance_before": round(float(linear_to_srgb(np.array(luminance))), 4),
            "luminance_after": round(float(linear_to_srgb(np.array(after))), 4), "scale": round(scale, 4)}


def main() -> None:
    """Rebalance every archetype billboard sprite and report per-sprite scales."""
    sprites = sorted(ASSETS.glob("*_billboard_*.png"))
    if not sprites:
        raise SystemExit("No impostor sprites found in %s" % ASSETS)
    report = [normalize_sprite(path) for path in sprites]
    print(json.dumps({"target_luminance": TARGET_LUM, "sprites": len(report), "records": report}, indent=1))


if __name__ == "__main__":
    main()
