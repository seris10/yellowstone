"""Image-informed spring display colors and flow-oriented terrace relief."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from tools.sample_image_gradient import linear_to_srgb, srgb_to_linear
from yellowstone_python.common.io import sha256_file, write_json_atomic
from yellowstone_python.common.provenance import default_world_root


def smoothstep(low: float, high: float, value: np.ndarray) -> np.ndarray:
    """Return a bounded cubic transition."""
    phase = np.clip((value-low)/(high-low), 0, 1)
    return phase * phase * (3 - 2*phase)


def palette_profile(position: np.ndarray, controls: list) -> np.ndarray:
    """Interpolate image-sampled sRGB colors in linear light."""
    distances = np.array([row[0] for row in controls])
    if np.any(np.diff(distances) <= 0):
        raise ValueError("palette coordinates must increase strictly")
    colors = np.array([[int(row[1][i:i+2], 16)/255 for i in (1, 3, 5)] for row in controls])
    linear = srgb_to_linear(colors)
    return np.stack([np.interp(position, distances, linear[:, channel]) for channel in range(3)], axis=-1)


def shoreline_distance(x: np.ndarray, z: np.ndarray, polygon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return signed metric distance and an even-odd polygon interior mask."""
    distance2 = np.full(x.shape, np.inf)
    inside = np.zeros(x.shape, dtype=bool)
    for start, end in zip(polygon, np.roll(polygon, -1, axis=0)):
        direction = end - start
        norm = float(direction @ direction)
        if norm <= 1e-20:
            continue
        fraction = np.clip(((x-start[0])*direction[0] + (z-start[1])*direction[1])/norm, 0, 1)
        distance2 = np.minimum(distance2, (x-start[0]-fraction*direction[0])**2
                               + (z-start[1]-fraction*direction[1])**2)
        if abs(direction[1]) > 1e-12:
            crossing = ((start[1] > z) != (end[1] > z)) & (x < start[0]+(z-start[1])*direction[0]/direction[1])
            inside ^= crossing
    distance = np.sqrt(distance2)
    return np.where(inside, -distance, distance), inside


def terrace_field(x: np.ndarray, z: np.ndarray, center: list, spacing_m: float,
                  height_m: float, ridge_width_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Return bounded authored terrace height and metric derivatives."""
    if spacing_m <= 0 or height_m < 0 or ridge_width_m <= 0:
        raise ValueError("terrace dimensions must be positive")
    dx, dz = x-center[0], z-center[2]
    radius, angle = np.hypot(dx, dz), np.arctan2(dz, dx)
    flow_coordinate = radius + 1.4*np.sin(angle*7) + .8*np.sin(x/11)*np.sin(z/9)
    phase = 2*np.pi*flow_coordinate/spacing_m
    height = np.zeros_like(x)
    for harmonic in range(1, 9):
        attenuation = np.exp(-.5*(2*np.pi*harmonic*ridge_width_m/spacing_m)**2)
        height -= attenuation*np.sin(harmonic*phase)/harmonic
    height *= height_m/np.pi
    height += .012*np.sin(2*np.pi*flow_coordinate/17 + .7*np.sin(angle*13))
    spacing_z, spacing_x = abs(z[1, 0]-z[0, 0]), abs(x[0, 1]-x[0, 0])
    dz_height, dx_height = np.gradient(height, spacing_z, spacing_x)
    return height, np.stack([dx_height, dz_height], axis=-1)


def prepare(world: Path) -> dict:
    """Write display assets while preserving numerical pool and pigment artifacts."""
    config_path = world / "data/display/prismatic.json"
    config = json.loads(config_path.read_text())
    spec = json.loads((world / "data/world.json").read_text())
    pool = next(row for row in spec["pools"] if row["id"] == config["pool_id"])
    source = world / "references/midway_orthophoto_detail.jpg"
    header = json.loads((world / "references/midway_orthophoto_detail.json").read_text())
    extent = header["local_extent_xz_m"]
    photo = np.asarray(Image.open(source).convert("RGB"), float) / 255
    size_z, size_x = photo.shape[:2]
    spacing_x, spacing_z = (extent[2]-extent[0])/size_x, (extent[3]-extent[1])/size_z
    x, z = np.meshgrid(extent[0]+(np.arange(size_x)+.5)*spacing_x,
                       extent[1]+(np.arange(size_z)+.5)*spacing_z)
    distance, inside = shoreline_distance(x, z, np.asarray(pool["ring"]))
    band = palette_profile(np.maximum(distance, 0), config["apron_profile_m"])
    red, green, blue = np.moveaxis(photo, -1, 0)
    chroma = smoothstep(.035, .13, red-blue) * smoothstep(-.02, .065, red-green)
    mineral_light = smoothstep(.20, .48, (red+green+blue)/3)
    orange_support = chroma * mineral_light
    outer = smoothstep(10, 22, distance)
    orange = palette_profile(np.clip((red-green)*65, 0, 11), [[0,"#dd7947"],[4,"#f78d46"],[11,"#f18233"]])
    band = band*(1-outer[..., None]*orange_support[..., None]) + orange*outer[..., None]*orange_support[..., None]
    coverage = (1-smoothstep(65, 125, distance)) * np.maximum(1-smoothstep(10, 34, distance), orange_support*.94)
    coverage[inside] = 0
    color = np.dstack([linear_to_srgb(band), coverage])
    height, slope = terrace_field(x, z, pool["center"], config["terrace_spacing_m"],
                                  config["terrace_height_m"], config["terrace_ridge_width_m"])
    relief_mask = smoothstep(1, 8, distance)*(1-smoothstep(75, 145, distance))
    normals = -slope / np.sqrt(1+np.sum(slope*slope, axis=-1, keepdims=True))
    radial = np.stack([x-pool["center"][0], z-pool["center"][2]], axis=-1)
    radial /= np.maximum(np.linalg.norm(radial, axis=-1, keepdims=True), 1)
    edge = smoothstep(.010, .022, -np.sum(slope*radial, axis=-1))
    packed = np.dstack([normals*.5+.5, edge, relief_mask])
    directory = world / "assets/textures"
    for name, pixels in (("prismatic_apron_display.png", color), ("prismatic_terrace_detail.png", packed)):
        Image.fromarray(np.uint8(np.clip(pixels, 0, 1)*255+.5)).save(directory/name)
    ramp = palette_profile(np.linspace(0, 1, 1024), config["water_profile"])
    Image.fromarray(np.uint8(np.clip(linear_to_srgb(ramp[None]), 0, 1)*255+.5)).save(directory/"prismatic_water_display.png")
    names = ["prismatic_apron_display.png", "prismatic_terrace_detail.png", "prismatic_water_display.png"]
    report = {"schema": "yellowstone.spring_display_assets.v1", "run_mode": "illustrative",
        "value_class": "authored_image_informed_display", "uncertainty": "unknown",
        "config_sha256": sha256_file(config_path), "mapped_source_sha256": sha256_file(source),
        "world_source_sha256": sha256_file(world/"data/world.json"), "local_extent_xz_m": extent,
        "pixel_spacing_m": [spacing_x, spacing_z], "terrace_height_range_m": [float(height.min()), float(height.max())],
        "terrace_max_gradient": float(np.linalg.norm(slope, axis=-1).max()),
        "water_green_radius_fraction": [.84, .974], "water_yellow_radius_fraction": [.974, 1.0],
        "interpretation": "Authored image-informed display profiles; mapped NAIP chroma preserves runoff support. Terrace relief is procedural and unmeasured. Scientific radiative-transfer and microbial pigment outputs remain unchanged.",
        "artifacts": {name: sha256_file(directory/name) for name in names}}
    write_json_atomic(directory/"prismatic_display.json", report, indent=2)
    return report


def main() -> int:
    """Prepare the spring display assets."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path, default=default_world_root())
    args = parser.parse_args()
    print(json.dumps(prepare(args.world), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
