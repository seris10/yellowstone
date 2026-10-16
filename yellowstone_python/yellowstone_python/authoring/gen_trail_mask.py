"""Metric trail coverage masks."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from yellowstone_python.common.provenance import default_world_root

WORLD = default_world_root()
SIZE = 4096
HALF = 2048.0
PIXEL_M = 2.0 * HALF / SIZE
EDGE_SOFTNESS_M = 0.6
SUPERSAMPLE = 4


def _px(x: float, z: float) -> tuple[float, float]:
    """Map world coordinates to pixel-center indices."""
    return ((x + HALF) / PIXEL_M - 0.5, (z + HALF) / PIXEL_M - 0.5)


def _segments(world: dict, half: float, softness: float) -> list:
    """Validate trail routes and return metric segment bounds."""
    if not isinstance(world, dict) or not isinstance(world.get("routes", []), list):
        raise ValueError("world routes must be a list")
    segments = []
    for route in world.get("routes", []):
        if not isinstance(route, dict):
            raise ValueError("route must be an object")
        if route.get("kind") != "trail" or route.get("surface") == "Wood":
            continue
        points = []
        raw_points = route.get("points", [])
        if not isinstance(raw_points, (list, tuple)):
            raise ValueError(f"trail {route.get('id')!r}: points must be a list")
        for point in raw_points:
            if not isinstance(point, (list, tuple)) or len(point) < 3:
                raise ValueError(f"trail {route.get('id')!r}: point must be [x, y, z]")
            try:
                x, z = float(point[0]), float(point[2])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"trail {route.get('id')!r}: point must be numeric") from exc
            if not (math.isfinite(x) and math.isfinite(z)):
                raise ValueError(f"trail {route.get('id')!r}: point must be finite")
            if abs(x) > half or abs(z) > half:
                raise ValueError(f"trail {route.get('id')!r}: point outside world extent")
            points.append((x, z))
        if len(points) < 2:
            continue
        try:
            width = float(route["width"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"trail {route.get('id')!r}: invalid width") from exc
        if not math.isfinite(width) or width <= 0.0 or isinstance(route["width"], bool):
            raise ValueError(f"trail {route.get('id')!r}: width must be finite and > 0")
        radius = width * 0.5
        for a, b in zip(points[:-1], points[1:]):
            segments.append((a, b, radius, radius + softness * 0.5))
    return segments


def build_mask(world: dict, size: int = SIZE, *, half_extent_m: float = HALF,
               edge_softness_m: float = EDGE_SOFTNESS_M,
               supersample: int = SUPERSAMPLE) -> Image.Image:
    """Rasterize round-capped trails at their physical widths and pixel centers."""
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 8192:
        raise ValueError("mask size must be an integer in [1, 8192]")
    if not math.isfinite(half_extent_m) or half_extent_m <= 0.0:
        raise ValueError("half extent must be finite and > 0")
    if not math.isfinite(edge_softness_m) or edge_softness_m < 0.0:
        raise ValueError("edge softness must be finite and >= 0")
    if isinstance(supersample, bool) or not isinstance(supersample, int) or not 1 <= supersample <= 8:
        raise ValueError("supersample must be an integer in [1, 8]")
    pixel_m = 2.0 * half_extent_m / size
    prepared = []
    for a, b, radius, support in _segments(world, half_extent_m, edge_softness_m):
        c0 = max(0, math.floor((min(a[0], b[0]) - support + half_extent_m) / pixel_m))
        c1 = min(size, math.ceil((max(a[0], b[0]) + support + half_extent_m) / pixel_m))
        r0 = max(0, math.floor((min(a[1], b[1]) - support + half_extent_m) / pixel_m))
        r1 = min(size, math.ceil((max(a[1], b[1]) + support + half_extent_m) / pixel_m))
        if c0 < c1 and r0 < r1:
            prepared.append((a, b, radius, r0, r1, c0, c1))
    total = np.zeros((size, size), dtype=np.float32)
    if not prepared:
        return Image.fromarray(total.astype(np.uint8))
    field = np.zeros_like(total)
    for sy in range(supersample):
        for sx in range(supersample):
            field.fill(0.0)
            for a, b, radius, r0, r1, c0, c1 in prepared:
                x = -half_extent_m + (np.arange(c0, c1) + (sx + 0.5) / supersample) * pixel_m
                z = -half_extent_m + (np.arange(r0, r1)[:, None] + (sy + 0.5) / supersample) * pixel_m
                dx, dz = b[0] - a[0], b[1] - a[1]
                length2 = dx * dx + dz * dz
                t = np.clip(((x - a[0]) * dx + (z - a[1]) * dz) / length2, 0.0, 1.0) if length2 else 0.0
                distance = np.hypot(x - a[0] - t * dx, z - a[1] - t * dz)
                if edge_softness_m:
                    edge = np.clip((distance - radius + edge_softness_m * 0.5) / edge_softness_m, 0.0, 1.0)
                    coverage = 1.0 - edge * edge * (3.0 - 2.0 * edge)
                else:
                    coverage = distance <= radius
                window = field[r0:r1, c0:c1]
                np.maximum(window, coverage, out=window)
            total += field
    return Image.fromarray(np.rint(total * (255.0 / supersample ** 2)).astype(np.uint8))


def main(argv=None) -> int:
    """Run the command-line interface."""
    from yellowstone_python.cli.gen_trail_mask import main as command
    return command(argv)


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
