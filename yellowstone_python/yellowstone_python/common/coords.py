"""M00 coords: single EPSG:32612 frame authority for Yellowstone Midway.

Matches:
- tools/prepare_world.py constants (E0, N0, H0, GRID=1025, STEP=4, HALF=2048)
- scripts/height_field.gd::sample diagonal (10-01): fx+fz<=1 branch.
- GEOSPATIAL_CONTRACT numerics: floor indexing, no epsilon, GDAL centre note.

Local mapping (project contract):
    x = E - E0
    y = H - H0        (H is NAVD88 orthometric, not ellipsoidal GPS height)
    z = N0 - N        (positive z is south; north is -z)
"""
from __future__ import annotations

import math

E0 = 512952.5950985841
N0 = 4930199.044097667
H0 = 2200.0
GRID = 1025
STEP = 4.0
HALF = 2048.0
CRS = "EPSG:32612"
VERTICAL_DATUM = "NAVD88"

# Saved anchors (references/geoanchors.json; local x,z metres)
ANCHORS = {
    "grand_prismatic": (-94.707, -10.608),
    "excelsior": (15.812, -145.302),
}


def local_to_utm(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Local (x=east, y=up-from-2200, z=south) -> (E, N, H_NAVD88)."""
    return (x + E0, N0 - z, y + H0)


def utm_to_local(e: float, n: float, h: float) -> tuple[float, float, float]:
    """(E, N, H_NAVD88) -> local (x, y, z)."""
    return (e - E0, h - H0, N0 - n)


def sample_index(x: float, z: float) -> tuple[int, int]:
    """Grid indices via floor (never truncation, never epsilon nudge)."""
    gx = (x + HALF) / STEP
    gz = (z + HALF) / STEP
    return (math.floor(gx), math.floor(gz))


def sample_height(h: list | tuple, x: float, z: float) -> float:
    """Bilinear sample matching height_field.gd diagonal.

    h: flat row-major GRID*GRID array, row zero is north (iz=0 -> z=-HALF).
    Clamps to valid range like GDScript clampf.
    """
    gx = min(max((x + HALF) / STEP, 0.0), float(GRID - 1) - 1e-5)
    gz = min(max((z + HALF) / STEP, 0.0), float(GRID - 1) - 1e-5)
    ix = math.floor(gx)
    iz = math.floor(gz)
    fx = gx - ix
    fz = gz - iz
    a = h[iz * GRID + ix]
    b = h[iz * GRID + ix + 1]
    c = h[(iz + 1) * GRID + ix]
    d = h[(iz + 1) * GRID + ix + 1]
    if fx + fz <= 1.0:
        return a + fx * (b - a) + fz * (c - a)
    return d + (1.0 - fx) * (c - d) + (1.0 - fz) * (b - d)
