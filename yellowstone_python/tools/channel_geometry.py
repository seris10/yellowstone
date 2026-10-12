"""Derive channel cross-section profiles from USGS field measurements + USGS 3DEP DEM.

Data sources:
  - USGS NWIS field measurements (current-meter surveys with width, area, velocity)
  - USGS 3DEP 1/3 arc-second DEM (~10 m resolution) for bank elevations
  - Project terrain.f32 (4 m resolution, derived from 3DEP) for fine-scale transects

Output: cross-section profiles per river feature for the 1-D advection-dispersion solver.

Usage:
    python tools/channel_geometry.py \
        --world ../yellowstone_midway/data/world.json \
        --terrain ../yellowstone_midway/data/terrain.f32 \
        --usgs-site 06036805 \
        --usgs-data derived/usgs_06036805.json \
        --out configs/cross_sections.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yellowstone_python.vegetation import load_terrain, terrain_fns

# Firehole chain features (from world.json topology)
FIREHOLE_CHAIN = ["river_5856_0", "river_5872_0", "river_5913_0", "river_5933_0", "river_5998_0"]

# USGS gage sites relevant to Firehole
USGS_SITES = {
    "06036805": {"name": "Firehole River at Old Faithful", "above_midway": True},
    "06036905": {"name": "Firehole River near West Yellowstone", "above_midway": False},
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

    if not depths:
        return {
            "depth_m": 1.1,
            "status": "default_assumed_no_valid_transects",
            "source": f"feature {feature['id']}: no valid DEM transects",
        }

    mean_area = float(np.mean(areas))
    mean_width = float(np.mean(widths))
    mean_depth = float(np.mean(depths))
    std_depth = float(np.std(depths))

    return {
        "depth_m": round(mean_depth, 3),
        "status": "authored_estimate_from_usgs_3dep_dem",
        "source": (
            f"USGS 3DEP DEM transects every {spacing_m:.0f}m over {total_length:.0f}m; "
            f"mean_area={mean_area:.1f}m2 mean_width={mean_width:.1f}m "
            f"depth_std={std_depth:.2f}m"
        ),
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
) -> dict:
    """Derive cross-section profiles for all Firehole chain features."""
    sample, _ = terrain_fns(terrain)
    chain_features = {
        f["id"]: f for f in world["rivers"]
        if f["id"] in FIREHOLE_CHAIN
    }

    profiles = {}
    for fid in FIREHOLE_CHAIN:
        feature = chain_features.get(fid)
        if feature is None:
            print(f"WARNING: {fid} not in world.json rivers")
            continue

        dem_result = _dem_mean_depth(feature, sample)
        usgs_result = _usgs_mean_depth(usgs_data) if usgs_data else None

        if usgs_result and usgs_result["depth_m"] > 0.2:
            usgs_result["dem_cross_check_depth_m"] = dem_result["depth_m"]
            profiles[fid] = usgs_result
        else:
            profiles[fid] = dem_result

        print(f"{fid}: depth={profiles[fid]['depth_m']:.3f}m  ({profiles[fid]['status']})")

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
    if args.usgs_data:
        usgs_data = json.loads(args.usgs_data.read_text())
        print(f"Using USGS site {args.usgs_site} field measurements")

    profiles = analyze(world, terrain, usgs_data)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(profiles, indent=2) + "\n")
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
