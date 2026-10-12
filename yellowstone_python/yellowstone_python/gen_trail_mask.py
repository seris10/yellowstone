"""Paint foot trails into a terrain mask instead of ribbon meshes.

Renders Native + Asphalt trail polylines (Wood boardwalks stay meshed;
roads stay meshed) into a 2048^2 world-extent mask, 2 m/px: solid core +
soft shoulder. The terrain shader blends dirt tread by this mask, so the
trail IS the ground: no float, no lip, no slab ends, no z-fighting.

Usage:
    python -m yellowstone_python.gen_trail_mask
Output: yellowstone_midway/assets/textures/trail_mask.png (+ .import note)
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .common.provenance import default_world_root

WORLD = default_world_root()
SIZE = 2048
HALF = 2048.0


def _px(x: float, z: float) -> tuple[float, float]:
    return ((x + HALF) / (2 * HALF) * (SIZE - 1),
            (z + HALF) / (2 * HALF) * (SIZE - 1))


def main() -> int:
    world = json.loads((WORLD / "data" / "world.json").read_text())
    core = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(core)
    n = 0
    for r in world["routes"]:
        if r["kind"] != "trail" or r.get("surface") == "Wood":
            continue
        pts = [_px(p[0], p[2]) for p in r["points"]]
        wpx = max(1.5, float(r["width"]) / 2.0)  # 2 m per pixel
        d.line(pts, fill=255, width=int(round(wpx)), joint="curve")
        n += 1
    # Soft shoulder: blurred copy at half strength under the solid core.
    soft = core.filter(ImageFilter.GaussianBlur(2.5)).point(
        lambda v: int(v * 0.55))
    mask = Image.composite(core, soft, core)
    out = WORLD / "assets" / "textures" / "trail_mask.png"
    mask.save(out)
    print(f"painted {n} trails -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
