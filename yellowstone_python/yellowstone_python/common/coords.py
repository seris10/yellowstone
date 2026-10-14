"""coords: single frame authority for Yellowstone Midway."""
from __future__ import annotations

import math

E0 = 512952.5950985841
N0 = 4930199.044097667
H0 = 2200.0
GRID = 1025
STEP = 4.0
HALF = 2048.0
CRS = "EPSG:32612"
HORIZONTAL_DATUM = "WGS 84"
VERTICAL_DATUM = "NAVD88"
GEOID_MODEL = "GEOID12B"

# Saved anchor positions in local x,z meters.
ANCHORS = {
    "grand_prismatic": (-94.707, -10.608),
    "excelsior": (15.812, -145.302),
}


def local_to_utm(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Local to UTM; horizontal WGS 84 (zone 12N), vertical NAVD88 under GEOID12B."""
    return (x + E0, N0 - z, y + H0)


def utm_to_local(e: float, n: float, h: float) -> tuple[float, float, float]:
    """(E, N, H_NAVD88) -> local (x, y, z)."""
    return (e - E0, h - H0, N0 - n)


def sample_index(x: float, z: float) -> tuple[int, int]:
    """Grid indices via floor. math.floor(-0.25) is -1; int() would give 0."""
    gx = (x + HALF) / STEP
    gz = (z + HALF) / STEP
    return (math.floor(gx), math.floor(gz))


def sample_height(h: list | tuple, x: float, z: float) -> float:
    """Bilinear sample matching height_field.gd triangle diagonal."""
    gx = min(max((x + HALF) / STEP, 0.0), float(GRID - 1))
    gz = min(max((z + HALF) / STEP, 0.0), float(GRID - 1))
    ix = min(math.floor(gx), GRID - 2)
    iz = min(math.floor(gz), GRID - 2)
    fx = gx - ix
    fz = gz - iz
    a = h[iz * GRID + ix]
    b = h[iz * GRID + ix + 1]
    c = h[(iz + 1) * GRID + ix]
    d = h[(iz + 1) * GRID + ix + 1]
    if fx + fz <= 1.0:
        return a + fx * (b - a) + fz * (c - a)
    return d + (1.0 - fx) * (c - d) + (1.0 - fz) * (b - d)
