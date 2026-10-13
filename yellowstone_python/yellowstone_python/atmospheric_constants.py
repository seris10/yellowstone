"""Shared site atmospheric constants.
Single source for site elevation and the barometric pressure derived from it.
"""
from __future__ import annotations

SITE_ELEVATION_M = 2215.0

# Standard-atmosphere barometric formula (pressure in kPa, elevation in m).
SITE_PRESSURE_KPA = (
    101.325 * (1.0 - 2.25577e-5 * SITE_ELEVATION_M) ** 5.25588
)
