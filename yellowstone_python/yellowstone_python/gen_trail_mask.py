"""Paint foot trails into a terrain mask for the terrain shader to blend.
Native and asphalt polylines into a 2048^2 2 m/px mask; outputs trail_mask.png."""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .common.provenance import default_world_root

WORLD = default_world_root()
SIZE = 2048
HALF = 2048.0
PIXEL_M = (2.0 * HALF) / SIZE  # exactly 2 m per pixel
MIN_TRAIL_PX = 2  # 4 m core floor so narrow trails stay visible
SHOULDER_GAIN = 0.55
SHOULDER_BLUR_PX = 2.5


def _px(x: float, z: float) -> tuple[float, float]:
    """World meters to pixel centers, exactly 2 m per pixel."""
    return ((x + HALF) / PIXEL_M - 0.5,
            (z + HALF) / PIXEL_M - 0.5)


def build_mask(world: dict, size: int = SIZE) -> Image.Image:
    """Core plus blurred shoulder over the world's trail routes."""
    if int(size) <= 0:
        raise ValueError(f"mask size must be > 0, got {size}")
    core = Image.new("L", (int(size), int(size)), 0)
    d = ImageDraw.Draw(core)
    for r in world.get("routes", []):
        if r.get("kind") != "trail" or r.get("surface") == "Wood":
            continue
        pts = []
        px_m = (2.0 * HALF) / int(size)
        def px_local(x, z):
            return ((x + HALF) / px_m - 0.5,
                    (z + HALF) / px_m - 0.5)
        for p in r.get("points", []):
            if not isinstance(p, (list, tuple)) or len(p) < 3:
                raise ValueError(
                    f"trail {r.get('id')!r}: point must be [x, y, z]")
            x, z = float(p[0]), float(p[2])
            if not (math.isfinite(x) and math.isfinite(z)):
                raise ValueError(
                    f"trail {r.get('id')!r}: point must be finite")
            if abs(x) > HALF or abs(z) > HALF:
                raise ValueError(
                    f"trail {r.get('id')!r}: point ({x}, {z}) lies outside "
                    f"the baked world extent +-{HALF} m")
            pts.append(px_local(x, z))
        if len(pts) < 2:
            continue
        try:
            width_m = float(r["width"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"trail {r.get('id')!r}: invalid width") from exc
        if not math.isfinite(width_m) or width_m <= 0.0:
            raise ValueError(
                f"trail {r.get('id')!r}: width must be finite and > 0")
        px_m = (2.0 * HALF) / int(size)
        wpx = max(MIN_TRAIL_PX, int(round(width_m / px_m)))
        d.line(pts, fill=255, width=wpx, joint="curve")
    soft = core.filter(ImageFilter.GaussianBlur(SHOULDER_BLUR_PX)).point(
        lambda v: int(v * SHOULDER_GAIN))
    mask = ImageChops.lighter(core, soft)
    return mask


def main() -> int:
    world = json.loads((WORLD / "data" / "world.json").read_text())
    core = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(core)
    n = 0
    for r in world["routes"]:
        if r["kind"] != "trail" or r.get("surface") == "Wood":
            continue
        pts = []
        for p in r["points"]:
            if not isinstance(p, (list, tuple)) or len(p) < 3:
                raise ValueError(
                    f"trail {r.get('id')!r}: point must be [x, y, z]")
            x, z = float(p[0]), float(p[2])
            if not (math.isfinite(x) and math.isfinite(z)):
                raise ValueError(
                    f"trail {r.get('id')!r}: point must be finite")
            if abs(x) > HALF or abs(z) > HALF:
                raise ValueError(
                    f"trail {r.get('id')!r}: point ({x}, {z}) lies outside "
                    f"the baked world extent +-{HALF} m")
            pts.append(_px(x, z))
        if len(pts) < 2:
            continue
        try:
            width_m = float(r["width"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"trail {r.get('id')!r}: invalid width") from exc
        if not math.isfinite(width_m) or width_m <= 0.0:
            raise ValueError(
                f"trail {r.get('id')!r}: width must be finite and > 0")
        wpx = max(MIN_TRAIL_PX, int(round(width_m / PIXEL_M)))
        d.line(pts, fill=255, width=wpx, joint="curve")
        n += 1
    # Soft shoulder: blurred copy at half strength under the solid core.
    soft = core.filter(ImageFilter.GaussianBlur(SHOULDER_BLUR_PX)).point(
        lambda v: int(v * SHOULDER_GAIN))
    mask = ImageChops.lighter(core, soft)
    out = WORLD / "assets" / "textures" / "trail_mask.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    mask.save(out)
    print(f"painted {n} trails -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
