"""Channel cross-section profiles from USGS measurements and the 3DEP DEM."""
from __future__ import annotations

from yellowstone_python.river.obs_model import UPSTREAM_GAUGE, DOWNSTREAM_GAUGE

import argparse
import json
import math
import sys
from pathlib import Path

from yellowstone_python.common.io import write_json_atomic

import numpy as np

from yellowstone_python.land.vegetation import load_terrain, terrain_fns

# Firehole chain features (from world.json topology)
FIREHOLE_CHAIN = ["river_5856_0", "river_5872_0", "river_5913_0", "river_5933_0", "river_5998_0"]

# USGS gage sites relevant to Firehole
USGS_SITES = {
    UPSTREAM_GAUGE: {"name": "Firehole River at Old Faithful",
                 "above_midway": True,
                 "feature_id": "river_5856_0"},
    DOWNSTREAM_GAUGE: {"name": "Firehole River near West Yellowstone",
                 "above_midway": False,
                 "feature_id": "river_5998_0"},
}


def _unit_perpendicular(dx: float, dz: float) -> tuple[float, float]:
    length = math.hypot(dx, dz)
    if length < 1e-9:
        return (0.0, 0.0)
    return (-dz / length, dx / length)


def _cross_section_from_dem(
    cx: float, cz: float, water_y: float,
    perp_x: float, perp_z: float,
    sample, half_width: float = 35.0, step: float = 0.5,
    min_depth: float = 0.10,
) -> tuple[float, float, float]:
    """Walk a DEM transect; return (area_m2, width_m, mean_depth_m)."""
    n = int(half_width / step)
    points = []
    for i in range(-n, n + 1):
        offset = i * step
        x = cx + perp_x * offset
        z = cz + perp_z * offset
        ground_y = sample(x, z)
        depth = water_y - ground_y
        points.append((offset, depth))

    left_bank = None
    right_bank = None
    for offset, depth in points:
        if depth > min_depth:
            if left_bank is None:
                left_bank = offset
            right_bank = offset

    if left_bank is None or right_bank is None:
        return (0.0, 0.0, 0.0)

    area = 0.0
    wetted = [(o, d) for o, d in points if d > 0.0]
    if len(wetted) < 2:
        return (0.0, 0.0, 0.0)
    for (o1, d1), (o2, d2) in zip(wetted, wetted[1:]):
        area += 0.5 * (d1 + d2) * (o2 - o1)

    width = right_bank - left_bank
    mean_depth = area / width if width > 0 else 0.0
    return (area, width, mean_depth)


def _dem_mean_depth(
    feature: dict, sample, spacing_m: float = 50.0,
) -> dict:
    """Compute mean depth from DEM transects along a river feature."""
    pts = feature["points"]
    n = len(pts)
    total_length = sum(
        math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][2] - pts[i][2])
        for i in range(n - 1)
    )
    n_samples = max(3, int(total_length / spacing_m))

    chainages = [0.0]
    for i in range(n - 1):
        d = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][2] - pts[i][2])
        chainages.append(chainages[-1] + d)

    areas = []
    widths = []
    depths = []
    for s_target in [total_length * i / n_samples for i in range(n_samples + 1)]:
        idx = 0
        for i in range(n - 1):
            if chainages[i] <= s_target <= chainages[i + 1]:
                idx = i
                break
        else:
            idx = n - 2

        seg_len = chainages[idx + 1] - chainages[idx]
        if seg_len < 1e-9:
            continue
        t = (s_target - chainages[idx]) / seg_len
        x = pts[idx][0] + t * (pts[idx + 1][0] - pts[idx][0])
        z = pts[idx][2] + t * (pts[idx + 1][2] - pts[idx][2])
        water_y = pts[idx][1] + t * (pts[idx + 1][1] - pts[idx][1])

        dx = pts[idx + 1][0] - pts[idx][0]
        dz = pts[idx + 1][2] - pts[idx][2]
        perp_x, perp_z = _unit_perpendicular(dx, dz)

        area, width, md = _cross_section_from_dem(x, z, water_y, perp_x, perp_z, sample)
        if area > 0:
            areas.append(area)
            widths.append(width)
            depths.append(md)

    n_attempted = (n_samples + 1) if n_samples > 0 else 0
    n_valid = len(depths)
    valid_fraction = (n_valid / n_attempted) if n_attempted else 0.0
    if not depths:
        return {
            "depth_m": 1.1,
            "status": "default_assumed_no_valid_transects",
            "source": f"feature {feature['id']}: no valid DEM transects",
            "n_transects_valid": 0,
            "valid_fraction": 0.0,
        }

    mean_area = float(np.mean(areas))
    mean_width = float(np.mean(widths))
    mean_depth = float(np.mean(depths))
    std_depth = float(np.std(depths))

    return {
        "depth_m": round(mean_depth, 3),
        "status": "authored_estimate_from_usgs_3dep_dem",
        "source": (
            f"USGS 3DEP DEM transects every {spacing_m:.0f}m over "
            f"{total_length:.0f}m; mean_area={mean_area:.1f}m2 "
            f"mean_width={mean_width:.1f}m depth_std={std_depth:.2f}m"
        ),
        "n_transects_valid": n_valid,
        "n_transects_attempted": n_attempted,
        "valid_fraction": round(valid_fraction, 3),
    }


def _usgs_mean_depth(usgs_data: dict) -> dict | None:
    """Compute mean depth from USGS field measurements (area/width)."""
    measurements = usgs_data.get("measurements", [])
    depths = []
    widths = []
    areas = []
    for m in measurements:
        area = m.get("area_sqft")
        width = m.get("width_ft")
        if area is not None and width is not None and area > 0 and width > 0:
            depth_m = (area / width) * 0.3048  # ft to m
            depths.append(depth_m)
            widths.append(width * 0.3048)
            areas.append(area * 0.3048 ** 2)

    if not depths:
        return None

    mean_depth = float(np.mean(depths))
    std_depth = float(np.std(depths))
    mean_width = float(np.mean(widths))
    mean_area = float(np.mean(areas))

    return {
        "depth_m": round(mean_depth, 3),
        "status": "usgs_field_measurement_current_meter",
        "source": (
            f"USGS NWIS field measurements (n={len(depths)}); "
            f"mean_area={mean_area:.1f}m2 mean_width={mean_width:.1f}m "
            f"depth_std={std_depth:.2f}m"
        ),
    }


def analyze(
    world: dict,
    terrain: np.ndarray,
    usgs_data: dict | None = None,
    usgs_feature_id: str | None = None,
) -> dict:
    """Derive cross-section profiles for all Firehole chain features (USGS at usgs_feature_id, DEM."""
    sample, _ = terrain_fns(terrain)
    chain_features = {
        f["id"]: f for f in world["rivers"]
        if f["id"] in FIREHOLE_CHAIN
    }

    profiles: dict = {}
    for fid in FIREHOLE_CHAIN:
        feature = chain_features.get(fid)
        if feature is None:
            print(f"WARNING: {fid} not in world.json rivers")
            continue

        dem_result = _dem_mean_depth(feature, sample)
        allow_usgs = usgs_data is not None and (
            usgs_feature_id is None or usgs_feature_id == fid)
        usgs_result = (_usgs_mean_depth(usgs_data)
                       if allow_usgs and usgs_data is not None else None)

        if usgs_result and usgs_result["depth_m"] > 0.2:
            usgs_result["dem_cross_check_depth_m"] = dem_result["depth_m"]
            usgs_result["water_surface_source"] = "usgs_field_measurement"
            usgs_result["bathymetry_status"] = "measured_current_meter"
            profiles[fid] = usgs_result
        else:
            dem_result["water_surface_source"] = "world_centerline_elevation"
            dem_result["bathymetry_status"] = "dem_derived_not_measured"
            profiles[fid] = dem_result

        print(f"{fid}: depth={profiles[fid]['depth_m']:.3f}m "
              f" ({profiles[fid]['status']})")

    return profiles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--terrain", type=Path, required=True)
    parser.add_argument("--usgs-site", default=None, choices=list(USGS_SITES))
    parser.add_argument("--usgs-data", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    world = json.loads(args.world.read_text())
    terrain = load_terrain(str(args.terrain))

    usgs_data = None
    usgs_feature_id = None
    if args.usgs_data:
        usgs_data = json.loads(args.usgs_data.read_text())
        print(f"Using USGS site {args.usgs_site} field measurements")
        if args.usgs_site is not None:
            feature_id_value = USGS_SITES[args.usgs_site].get("feature_id")
            usgs_feature_id = (str(feature_id_value)
                               if feature_id_value is not None else None)
            if usgs_feature_id is not None:
                print(f"Restricting USGS override to feature {usgs_feature_id}")

    profiles = analyze(world, terrain, usgs_data,
                       usgs_feature_id=usgs_feature_id)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(args.out, profiles, indent=2)
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
