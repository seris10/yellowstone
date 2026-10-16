"""Observed canopy area beyond conservative crown render footprints."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from yellowstone_python.common.checks import finite, positive
from yellowstone_python.common.coords import H0
from yellowstone_python.common.io import sha256_file, write_json_atomic


def crown_circle_mask(trees, shape, extent, spacing):
    """Rasterize the union of detected core-circle footprints at source pixel centers."""
    spacing = positive("spacing", spacing)
    if len(extent) != 4:
        raise ValueError("canopy extent requires four finite coordinates")
    left, top, right, bottom = [finite("canopy_extent", value) for value in extent]
    if right <= left or bottom <= top:
        raise ValueError("canopy extent must have positive area")
    mask = np.zeros(shape, dtype=bool)
    for tree in trees:
        radius = positive("crown_radius_m", tree["crown_r_m"])
        x, z = finite("tree_x", tree["x"]), finite("tree_z", tree["z"])
        x0 = max(0, math.floor((x - radius - left) / spacing))
        x1 = min(shape[1], math.ceil((x + radius - left) / spacing))
        z0 = max(0, math.floor((z - radius - top) / spacing))
        z1 = min(shape[0], math.ceil((z + radius - top) / spacing))
        if x1 <= x0 or z1 <= z0:
            continue
        xs = left + (np.arange(x0, x1) + .5) * spacing
        zs = top + (np.arange(z0, z1) + .5) * spacing
        mask[z0:z1, x0:x1] |= (xs[None, :] - x) ** 2 + (zs[:, None] - z) ** 2 <= radius ** 2
    return mask


def residual_canopy(canopy_height, core_mask):
    """Separate observed above-threshold surface pixels from conservative render cores."""
    heights = np.asarray(canopy_height)
    cores = np.asarray(core_mask)
    if heights.ndim != 2 or heights.dtype.kind not in "iuf" or np.isinf(heights).any():
        raise ValueError("canopy height must be a finite-or-missing numeric raster")
    if cores.shape != heights.shape or cores.dtype.kind != "b":
        raise ValueError("core footprint must be a matching boolean raster")
    valid = np.isfinite(heights)
    observed = valid & (heights >= 2)
    return observed & ~cores, observed & cores, valid


def write_residual_canopy(canopy_height, ground_elevation, trees, out_dir, *, extent,
                          source_sha256, spacing=.5, cell_size=2.0, ground_offset=H0):
    """Export exact residual masks and compact observation-bound render surfaces."""
    from PIL import Image
    spacing, cell_size = positive("spacing", spacing), positive("cell_size", cell_size)
    ground_offset = finite("ground_offset", ground_offset)
    ratio = cell_size / spacing
    if not math.isclose(ratio, round(ratio), rel_tol=0, abs_tol=1e-9):
        raise ValueError("render cell size must be an integer multiple of source spacing")
    heights, ground = np.asarray(canopy_height), np.asarray(ground_elevation)
    if ground.shape != heights.shape or ground.dtype.kind not in "iuf" or not np.isfinite(ground).all():
        raise ValueError("matched ground raster must be finite and match the canopy shape")
    cores = crown_circle_mask(trees, heights.shape, extent, spacing)
    residual, covered, valid = residual_canopy(heights, cores)
    block = round(ratio)
    if heights.shape[0] % block or heights.shape[1] % block:
        raise ValueError("render grid must partition the entire source raster")
    rows, columns = heights.shape[0] // block, heights.shape[1] // block
    def blocks(array):
        return array.reshape(rows, block, columns, block).transpose(0, 2, 1, 3)
    active = blocks(residual)
    count = active.sum(axis=(2, 3))
    support = blocks(valid).sum(axis=(2, 3)) / block ** 2
    ground_cells = blocks(ground - ground_offset)
    ground_sum = np.where(active, ground_cells, 0).sum(axis=(2, 3))
    ground_mean = np.divide(ground_sum, count, out=ground_cells.mean(axis=(2, 3)), where=count > 0)
    height_sum = np.where(active, blocks(heights), 0).sum(axis=(2, 3))
    height_mean = np.divide(height_sum, count, out=np.full((rows, columns), np.nan), where=count > 0)
    arrays = {"canopy_top_scene_y": (ground_mean + height_mean).astype("<f4"),
              "ground_scene_y": ground_mean.astype("<f4"),
              "cover_fraction": (count / block ** 2).astype("<f4"),
              "valid_fraction": support.astype("<f4"),
              "unresolved_cells": (count > 0).astype("uint8")}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for name, array in arrays.items():
        path = out / f"{name}.{'u8' if array.dtype.kind == 'u' else 'f32'}"
        temporary = path.with_suffix(path.suffix + ".writing")
        array.tofile(temporary)
        temporary.replace(path)
        artifacts[name] = {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    for name, mask in [("unresolved_render_mask", residual), ("valid_support", valid)]:
        path = out / f"{name}.png"
        Image.fromarray(mask.astype("uint8") * 255).save(path)
        artifacts[name] = {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    observed_area = float((residual | covered).sum() * spacing ** 2)
    metadata = {"schema": "yellowstone.unresolved_canopy_render.v1", "status": "derived_not_field_validated",
        "scientific_acceptance": "not_yet_accepted", "width": columns, "height": rows,
        "cell_size_m": cell_size, "source_pixel_size_m": spacing, "extent_m": list(extent),
        "highres_mask_cell_size_m": spacing,
        "first_cell_x_m": extent[0] + cell_size / 2, "first_cell_z_m": extent[1] + cell_size / 2,
        "column_step_x_m": cell_size, "row_step_z_m": cell_size,
        "array_layout": "row-major little-endian float32; uint8 active-cell mask",
        "image_layout": "row zero north; columns+x; rows+z south",
        "ground_elevation_offset_m": ground_offset, "source_sha256": source_sha256,
        "producer_sha256": sha256_file(Path(__file__)),
        "artifacts": artifacts, "quantity": "observed surface area; no tree or stem count",
        "core_exclusion": "union detected conservative core equivalent-radius circles",
        "height_aggregation": {"status": "authored", "rule": "2m cell mean measured residual surface elevation"},
        "unsupported_cells": "source NoData preserved in support mask; inactive topY is NaN",
        "observed_canopy_area_m2": observed_area,
        "core_circle_area_on_observed_pixels_m2": float(covered.sum() * spacing ** 2),
        "unresolved_canopy_area_m2": float(residual.sum() * spacing ** 2),
        "conservation_residual_m2": observed_area - float((covered.sum() + residual.sum()) * spacing ** 2),
        "total_stem_density": None}
    write_json_atomic(out / "unresolved_render_canopy.json", metadata, indent=1)
    return metadata
