"""Isolate the existing human-made CC0 pine shoot without synthesizing new imagery."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt, label

ROOT = Path(__file__).resolve().parents[1]


def bough_from_shoot(image):
    """Assemble five metrically unchanged photos on a connected authored support."""
    canvas = Image.new("RGBA", (384, 512))
    draw = ImageDraw.Draw(canvas)
    draw.line([(192, 511), (192, 490), (194, 445), (196, 400), (198, 355), (200, 310)], fill=(92, 83, 60, 255), width=4)
    placements = [(192, 490, 35), (194, 445, -38), (196, 400, 22), (198, 355, -28), (200, 310, 4)]
    scale = .5625
    for x, y, angle in placements:
        radians = np.deg2rad(angle)
        a, b = np.cos(radians) / scale, np.sin(radians) / scale
        matrix = [a, b, 128 - a * x - b * y, -b, a, 511 + b * x - a * y]
        layer = image.transform(canvas.size, Image.Transform.AFFINE, matrix, Image.Resampling.BICUBIC)
        canvas = Image.alpha_composite(canvas, layer)
    pixels = np.array(canvas)
    nearest = distance_transform_edt(pixels[:, :, 3] == 0, return_distances=False, return_indices=True)
    pixels[:, :, :3] = pixels[nearest[0], nearest[1], :3]
    return Image.fromarray(pixels), placements


def prepare():
    """Write a root-centered natural shoot and independently hashed filtering provenance."""
    source = ROOT / "assets/imported/pine_tree_01/textures"
    diffuse = source / "pine_tree_01_twig_diff_1k.jpg"
    alpha = source / "pine_tree_01_alpha_1k.png"
    rgb = np.asarray(Image.open(diffuse).convert("RGB"))
    opacity = np.asarray(Image.open(alpha).convert("L"))
    components, _ = label(opacity[:460, :256] >= 82)
    selected = components == components[430, 140]
    if components[430, 140] == 0 or int(selected.sum()) != 22215:
        raise ValueError("CC0 shoot component differs from the reviewed source atlas")
    crop = [12, 35, 268, 547]
    isolated = np.zeros(opacity.shape, dtype=np.uint8)
    isolated[:460, :256] = np.where(selected, opacity[:460, :256], 0)
    rgba = np.dstack((rgb[crop[1]:crop[3], crop[0]:crop[2]], isolated[crop[1]:crop[3], crop[0]:crop[2]]))
    rgba = rgba[:418]
    rgba = np.pad(rgba, ((94, 0), (0, 0), (0, 0)))
    nearest = distance_transform_edt(rgba[:, :, 3] == 0, return_distances=False, return_indices=True)
    rgba[:, :, :3] = rgba[nearest[0], nearest[1], :3]
    output = ROOT / "assets/imported/canopy_shoot"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "pine_shoot.png"
    shoot = Image.fromarray(rgba)
    shoot.save(path)
    bough, placements = bough_from_shoot(shoot)
    bough_path = output / "pine_bough.png"
    bough.save(bough_path)
    spec = importlib.util.spec_from_file_location("lodgepole_authoring", ROOT / "tools/author_lodgepole.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = {"schema": "yellowstone.canopy_shoot.v1", "source_class": "human_made_cc0",
                "source_url": "https://polyhaven.com/a/pine_tree_01", "license": "CC0-1.0",
                "license_url": "https://polyhaven.com/license", "species_identity": "representative_pine_not_local_species_verification",
                "sources": [{"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in [diffuse, alpha]],
                "selection": {"alpha_threshold_u8": 82, "connected_component_seed_xy": [140, 430], "atlas_region_xywh": [0, 0, 256, 460],
                              "crop_xywh": [12, 35, 256, 418], "top_padding_px": 94, "root_uv": [0.5, 1.0]},
                "color_processing": "original shoot sRGB; bicubic rotated composition and nearest valid RGB dilation; no saturation or hue alteration",
                "display_dimensions_m": [.48, .64], "component_dimensions_m": [.18, .36],
                "dimension_class": "authored_unknown_uncertainty",
                "assembly": {"class": "authored_connected_bough", "photos": 5, "root_xy_and_rotation_deg": placements,
                             "component_pixel_scale": .5625, "support_width_m": .005, "field_branch_claim": "none"},
                "component_mips": module.cutout_mip_chain(path), "mips": module.cutout_mip_chain(bough_path)}
    (output / "pine_shoot.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
