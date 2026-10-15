"""Midway world center and site atmospheric constants."""
from __future__ import annotations

from yellowstone_python.common.coords import CRS, E0, N0

# Midway world center in WGS 84, transformed from the world georeference.
SITE_LAT_DEG = 44.525
SITE_LON_DEG = -110.837
SITE_ELEVATION_M = 2215.0
SITE_UTC_OFFSET_HOURS = -6.0
SITE_PRESSURE_KPA = 101.325 * (1.0 - 2.25577e-5 * SITE_ELEVATION_M) ** 5.25588
