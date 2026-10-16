"""Per-cell river shortwave shading: sky view and direct-beam blocking from DEM horizon and census."""
from __future__ import annotations

from yellowstone_python.common.site import SITE_LAT_DEG, SITE_LON_DEG

from yellowstone_python.common.checks import finite as _finite

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from yellowstone_python.common.site import SITE_ELEVATION_M
from yellowstone_python.common.provenance import default_world_root

SCHEMA = "yellowstone.river_shading.v1"

DEFAULT_HORIZON_AZIMUTHS = 36
DEFAULT_HORIZON_SAMPLE_M = 2.0
DEFAULT_HORIZON_MAX_M = 600.0
DEFAULT_OBSERVER_OFFSET_M = 1.0

DEFAULT_CANOPY_TRANSMISSIVITY = 0.1
CANOPY_TRANS_SOURCE = (
    "authored_representative_closed_conifer_canopy; general-literature "
    "range of 0.05 to 0.15 commonly cited for closed boreal and montane "
    "conifer stands (for example Hardy et al. 2004; specific publication "
    "details not independently verified)"
)

DEFAULT_TREE_HEIGHT_M = 15.0
TREE_HEIGHT_SOURCE = (
    "authored_default_15_m_pending_site_measurement; placeholder "
    "representative height for mature lodgepole pine stands at Midway"
)

DIRECT_BEAM_FRACTION_DEFAULT = 0.8
DIFFUSE_FRACTION_DEFAULT = 0.2
DIRECT_DIFFUSE_SOURCE = (
    "authored_representative_clear_sky_midday_split; typical of mid-"
    "latitude clear-sky conditions. The hourly diffuse fraction varies "
    "with the clearness index, altitude, air temperature and humidity "
    "(Reindl, Beckman and Duffie 1990, Solar Energy 45(1), 1-7, "
    "DOI 10.1016/0038-092X(90)90060-P)"
)

SOLAR_POSITION_SOURCE = (
    "pvlib.solarposition.get_solarposition following NREL SPA; "
    "Reda and Andreas (2004), Solar Energy 76(5), 577-589"
)




@dataclass(frozen=True)
class TerrainGrid:
    """DEM in the local world frame; j increases southward, i eastward.
heights are stored with vertical_origin_m already subtracted or zero when absolute."""

    heights_m: Any
    origin_xz_m: tuple[float, float]
    cell_size_m: float
    vertical_origin_m: float = 0.0

    def __post_init__(self) -> None:
        if self.cell_size_m <= 0.0:
            raise ValueError("cell_size_m must be positive")
        if (not isinstance(self.origin_xz_m, tuple)
                or len(self.origin_xz_m) != 2):
            raise ValueError("origin_xz_m must be a two-element tuple")
        if not hasattr(self.heights_m, "shape"):
            raise ValueError("heights_m must be a 2-D array")
        if len(self.heights_m.shape) != 2:
            raise ValueError("heights_m must have two dimensions")

    def elevation_at(self, x_m: float, z_m: float) -> float:
        """Bilinear elevation sample in local meters; raises outside the extent."""
        ix = (x_m - self.origin_xz_m[0]) / self.cell_size_m
        iz = (z_m - self.origin_xz_m[1]) / self.cell_size_m
        n_j, n_i = self.heights_m.shape
        if ix < 0.0 or ix > n_i - 1 or iz < 0.0 or iz > n_j - 1:
            raise ValueError(
                f"({x_m}, {z_m}) is outside the terrain extent")
        i0 = int(math.floor(ix))
        j0 = int(math.floor(iz))
        i1 = min(i0 + 1, n_i - 1)
        j1 = min(j0 + 1, n_j - 1)
        a = ix - i0
        b = iz - j0
        h00 = float(self.heights_m[j0, i0])
        h10 = float(self.heights_m[j0, i1])
        h01 = float(self.heights_m[j1, i0])
        h11 = float(self.heights_m[j1, i1])
        interpolated = ((1 - a) * (1 - b) * h00
                        + a * (1 - b) * h10
                        + (1 - a) * b * h01
                        + a * b * h11)
        return float(self.vertical_origin_m) + interpolated


def load_terrain_source(root: Path | None = None) -> TerrainGrid:
    """Load yellowstone_midway/references/terrain_source.f32 as a TerrainGrid.
Raw heights are stored as absolute elevations; vertical_origin_m is metadata only."""
    import numpy as np
    root = Path(root) if root is not None else default_world_root()
    header = json.loads(
        (root / "references/terrain_source.json").read_text(encoding="utf-8"))
    width = int(header["width"])
    height = int(header["height"])
    spacing = float(header["spacing_m"])
    bounds = header["sample_bounds_local_xz_m"]
    raw = np.frombuffer(
        (root / "references/terrain_source.f32").read_bytes(),
        dtype="<f4").reshape(height, width)
    return TerrainGrid(
        heights_m=raw.astype("float32"),
        origin_xz_m=(float(bounds[0]), float(bounds[1])),
        cell_size_m=spacing,
        vertical_origin_m=0.0,
    )


def horizon_angle_rad(terrain: TerrainGrid, x_m: float, z_m: float,
                      azimuth_rad: float,
                      sample_m: float = DEFAULT_HORIZON_SAMPLE_M,
                      max_m: float = DEFAULT_HORIZON_MAX_M,
                      observer_offset_m: float = DEFAULT_OBSERVER_OFFSET_M
                      ) -> float:
    """Horizon elevation angle along azimuth (clockwise from north)."""
    base = terrain.elevation_at(x_m, z_m) + _finite("observer_offset_m", observer_offset_m, minimum=0.0)
    dx = math.sin(azimuth_rad)
    dz = -math.cos(azimuth_rad)
    step = _finite("sample_m", sample_m)
    if step <= 0.0:
        raise ValueError("sample_m must be positive")
    reach = _finite("max_m", max_m)
    if reach <= 0.0:
        raise ValueError("max_m must be positive")
    max_tan = 0.0
    distance = step
    while distance <= reach:
        xp = x_m + dx * distance
        zp = z_m + dz * distance
        try:
            elev = terrain.elevation_at(xp, zp)
        except ValueError:
            break
        rise = elev - base
        if rise > 0.0:
            tan_angle = rise / distance
            if tan_angle > max_tan:
                max_tan = tan_angle
        distance += step
    return math.atan(max_tan)


def sky_view_factor(terrain: TerrainGrid, x_m: float, z_m: float,
                    azimuth_count: int = DEFAULT_HORIZON_AZIMUTHS,
                    sample_m: float = DEFAULT_HORIZON_SAMPLE_M,
                    max_m: float = DEFAULT_HORIZON_MAX_M,
                    observer_offset_m: float = DEFAULT_OBSERVER_OFFSET_M
                    ) -> float:
    """Isotropic sky view fraction, mean of cos^2(horizon) over azimuths."""
    count = int(azimuth_count)
    if count < 4:
        raise ValueError("azimuth_count must be at least 4")
    total = 0.0
    for i in range(count):
        az = 2.0 * math.pi * i / count
        theta = horizon_angle_rad(terrain, x_m, z_m, az,
                                  sample_m=sample_m, max_m=max_m,
                                  observer_offset_m=observer_offset_m)
        c = math.cos(theta)
        total += c * c
    return total / count


def canopy_direct_beam_fraction(
        trees: Sequence[dict], x_m: float, z_m: float,
        solar_azimuth_rad: float, solar_elevation_rad: float,
        tree_height_m: float = DEFAULT_TREE_HEIGHT_M,
        tau: float = DEFAULT_CANOPY_TRANSMISSIVITY
) -> float:
    """Direct-beam transmissivity through census trees along the solar bearing."""
    if solar_elevation_rad <= 0.0:
        return 0.0
    height = _finite("tree_height_m", tree_height_m, minimum=0.0)
    if height <= 0.0:
        raise ValueError("tree_height_m must be positive")
    canopy_tau = _finite("tau", tau, minimum=0.0)
    if canopy_tau > 1.0:
        raise ValueError("tau must be in [0, 1]")
    tan_elev = math.tan(solar_elevation_rad)
    if tan_elev <= 0.0:
        return 0.0
    dx = math.sin(solar_azimuth_rad)
    dz = -math.cos(solar_azimuth_rad)
    fraction = 1.0
    for tree in trees:
        tree_height = _finite("tree.height_m", tree.get("height_m", height), minimum=0.0)
        if tree_height <= 0.0:
            raise ValueError("tree.height_m must be positive")
        crown_r = _finite("tree.crown_r_m", tree.get("crown_r_m", 1.5), minimum=0.0)
        crown_ratio = None
        if tree.get("crown_ratio") is not None:
            crown_ratio = _finite("tree.crown_ratio", tree["crown_ratio"], minimum=0.0)
            if crown_ratio > 1.0:
                raise ValueError("tree.crown_ratio must be in [0, 1]")
        vx = _finite("tree.x", tree["x"]) - x_m
        vz = _finite("tree.z", tree["z"]) - z_m
        along = vx * dx + vz * dz
        if crown_r == 0.0 or along <= 0.0 or along > tree_height / tan_elev:
            continue
        if crown_ratio is not None:
            if crown_ratio == 0.0 or along * tan_elev < tree_height * (1.0 - crown_ratio):
                continue
        perp_x = vx - along * dx
        perp_z = vz - along * dz
        perp_sq = perp_x * perp_x + perp_z * perp_z
        if perp_sq > crown_r * crown_r:
            continue
        fraction *= canopy_tau
    return fraction


def solar_position(when_utc: Any,
                   latitude_deg: float = SITE_LAT_DEG,
                   longitude_deg: float = SITE_LON_DEG,
                   elevation_m: float = SITE_ELEVATION_M
                   ) -> dict[str, float]:
    """Solar elevation and azimuth in radians via pvlib SPA."""
    import pandas as pd
    from pvlib import solarposition
    times = pd.DatetimeIndex([when_utc])
    sp = solarposition.get_solarposition(times, latitude_deg, longitude_deg,
                                         altitude=elevation_m)
    return {
        "elevation_rad": math.radians(
            float(sp["apparent_elevation"].iloc[0])),
        "azimuth_rad": math.radians(float(sp["azimuth"].iloc[0])),
        "elevation_deg": float(sp["apparent_elevation"].iloc[0]),
        "azimuth_deg": float(sp["azimuth"].iloc[0]),
    }


def shortwave_multiplier(terrain: TerrainGrid, trees: Sequence[dict],
                         x_m: float, z_m: float, when_utc: Any,
                         latitude_deg: float = SITE_LAT_DEG,
                         longitude_deg: float = SITE_LON_DEG,
                         tree_height_m: float = DEFAULT_TREE_HEIGHT_M,
                         canopy_transmissivity: float =
                         DEFAULT_CANOPY_TRANSMISSIVITY,
                         svf: float | None = None,
                         direct_weight: float = DIRECT_BEAM_FRACTION_DEFAULT,
                         diffuse_weight: float = DIFFUSE_FRACTION_DEFAULT
                         ) -> dict[str, float]:
    """Combined per-cell shortwave multiplier for terrain and canopy shading."""
    _finite("direct_weight", direct_weight, minimum=0.0)
    _finite("diffuse_weight", diffuse_weight, minimum=0.0)
    if abs(direct_weight + diffuse_weight - 1.0) > 1e-9:
        raise ValueError("direct_weight + diffuse_weight must equal 1")
    sun = solar_position(when_utc, latitude_deg, longitude_deg)
    direct_fraction = 0.0
    if sun["elevation_rad"] > 0.0:
        horizon = horizon_angle_rad(terrain, x_m, z_m, sun["azimuth_rad"])
        if sun["elevation_rad"] > horizon:
            direct_fraction = canopy_direct_beam_fraction(
                trees, x_m, z_m, sun["azimuth_rad"], sun["elevation_rad"],
                tree_height_m, canopy_transmissivity)
    if svf is None:
        svf = sky_view_factor(terrain, x_m, z_m)
    svf_value = _finite("svf", svf, minimum=0.0)
    if svf_value > 1.0:
        raise ValueError("svf must lie in [0, 1]")
    multiplier = direct_weight * direct_fraction + diffuse_weight * svf_value
    return {
        "sky_view_factor": svf_value,
        "direct_fraction": direct_fraction,
        "shortwave_multiplier": multiplier,
        "solar_elevation_rad": sun["elevation_rad"],
        "solar_azimuth_rad": sun["azimuth_rad"],
    }


def describe_model() -> dict[str, Any]:
    """Model metadata and source citations suitable for a sidecar JSON."""
    return {
        "schema": SCHEMA,
        "status": "illustrative",
        "sources": {
            "canopy_transmissivity": CANOPY_TRANS_SOURCE,
            "tree_height_default": TREE_HEIGHT_SOURCE,
            "tree_height_records": "per-tree height_m takes precedence; absent heights use the authored default",
            "crown_base": "crown_ratio sets live-crown base when supplied; absent ratios use a ground-to-top column",
            "direct_diffuse_split": DIRECT_DIFFUSE_SOURCE,
            "solar_position": SOLAR_POSITION_SOURCE,
        },
        "parameters": {
            "latitude_deg": SITE_LAT_DEG,
            "longitude_deg": SITE_LON_DEG,
            "site_elevation_m": SITE_ELEVATION_M,
            "default_horizon_azimuths": DEFAULT_HORIZON_AZIMUTHS,
            "default_horizon_sample_m": DEFAULT_HORIZON_SAMPLE_M,
            "default_horizon_max_m": DEFAULT_HORIZON_MAX_M,
            "default_tree_height_m": DEFAULT_TREE_HEIGHT_M,
            "default_canopy_transmissivity": DEFAULT_CANOPY_TRANSMISSIVITY,
            "direct_weight": DIRECT_BEAM_FRACTION_DEFAULT,
            "diffuse_weight": DIFFUSE_FRACTION_DEFAULT,
        },
    }
