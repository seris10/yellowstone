"""Linear-light color mipmaps for terrain display textures."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

from yellowstone_python.common.io import sha256_file, write_json_atomic
from yellowstone_python.common.provenance import default_world_root


COLOR_PATHS = (
    "assets/textures/midway_macro.jpg",
    "references/midway_orthophoto_detail.jpg",
    "assets/textures/mapped_surface_detail.png",
    "assets/textures/forrest_ground_03_diff_1k.jpg",
    "assets/textures/rocky_trail_diff_1k.jpg",
    "assets/textures/forest_ground_04_diff_1k.jpg",
    "assets/textures/rock_boulder_dry_diff_1k.jpg",
    "assets/textures/prismatic_apron_display.png",
)


def mip_chain(rgba: np.ndarray) -> tuple[bytes, list[dict]]:
    """Filter power-of-two RGBA8 colors in premultiplied linear light."""
    if rgba.dtype != np.uint8 or rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("Color mips require uint8 RGBA pixels")
    height, width = rgba.shape[:2]
    if any(size < 2 or size & (size - 1) for size in (width, height)):
        raise ValueError("Color mip dimensions require powers of two >= 2")
    values = rgba.astype(np.float32) / 255
    rgb, alpha = values[:, :, :3], values[:, :, 3:4]
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    premultiplied = linear * alpha
    blocks, levels = [], []
    offset, level = 0, 0
    while True:
        if level == 0:
            pixels = rgba
        else:
            color = np.divide(premultiplied, alpha, out=np.zeros_like(premultiplied), where=alpha > 0)
            srgb = np.where(color <= .0031308, color * 12.92,
                            1.055 * np.maximum(color, 0) ** (1 / 2.4) - .055)
            pixels = np.uint8(np.clip(np.concatenate((srgb, alpha), axis=2), 0, 1) * 255 + .5)
        block = pixels.tobytes()
        blocks.append(block)
        levels.append({"level": level, "width": width, "height": height,
                       "offset": offset, "bytes": len(block)})
        offset += len(block)
        if width == height == 1:
            break
        x_step, y_step = min(width, 2), min(height, 2)
        width, height = max(1, width // 2), max(1, height // 2)
        premultiplied = premultiplied.reshape(height, y_step, width, x_step, 3).mean(axis=(1, 3))
        alpha = alpha.reshape(height, y_step, width, x_step, 1).mean(axis=(1, 3))
        level += 1
    return b"".join(blocks), levels


def prepare(world: Path) -> dict:
    """Write hash-bound color buffers with unchanged source-resolution pixels."""
    output = world / "assets/textures/color_mips"
    output.mkdir(parents=True, exist_ok=True)
    entries = {}
    for relative in COLOR_PATHS:
        source = world / relative
        rgba = np.asarray(Image.open(source).convert("RGBA"))
        data, levels = mip_chain(rgba)
        target = output / (source.stem + ".miprgba")
        target.write_bytes(data)
        entries[relative] = {"path": target.relative_to(world).as_posix(),
            "source_sha256": sha256_file(source), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data), "width": int(rgba.shape[1]), "height": int(rgba.shape[0]),
            "levels": levels}
    report = {"schema": "yellowstone.color_mips.v1", "format": "RGBA8",
        "color_filter_space": "linear_sRGB", "alpha_filter": "premultiplied_box",
        "output_encoding": "sRGB RGB, linear alpha", "base_level": "unchanged source RGBA8",
        "evidence_class": "deterministic_display_filter", "entries": entries,
        "scope": "Color textures only; normals, ARM, masks and scientific pigment data retain their existing treatment.",
        "sources": ["https://docs.godotengine.org/en/4.5/tutorials/shaders/shader_reference/shading_language.html#using-source-color",
                    "https://www.w3.org/TR/css-color-4/#color-conversion-code",
                    "https://developer.nvidia.com/gpugems/gpugems3/part-iv-image-effects/chapter-24-importance-being-linear"]}
    write_json_atomic(output / "color_mips.json", report, indent=2)
    return report


def main() -> int:
    """Prepare the terrain color buffers."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path, default=default_world_root())
    args = parser.parse_args()
    report = prepare(args.world)
    print("COLOR_MIPS", len(report["entries"]), "textures",
          sum(entry["bytes"] for entry in report["entries"].values()), "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
