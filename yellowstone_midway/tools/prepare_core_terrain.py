#!/usr/bin/env python3
"""Author the thermal-core 1 m heightfield, normal map and stitch tables."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PYROOT = ROOT.parent / "yellowstone_python"


VERTICAL_ORIGIN_M = 2200.0

CORE_X_MIN = -340.0
CORE_X_MAX = 260.0
CORE_Z_MIN = -380.0
CORE_Z_MAX = 220.0

MASTER_HALF_M = 2048.0
MASTER_STEP_M = 4.0
MASTER_SIZE = 1025

MICRORELIEF_AMPLITUDE_M = 0.08
MICRORELIEF_LENGTH_SCALE_M = 3.0
MICRORELIEF_SMOOTH_SIGMA_PX = 1.2
NORMAL_MESH_DECIMATION = 2
NORMAL_CONTRACT = "tangent_residual_mesh_frame.v1"

CHANNEL_WIDTH_TO_DEPTH = 20.0
CHANNEL_BANK_BLEND_M = 1.5

STITCH_BLEND_MARGIN_M = 12.0


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_path(path: Path) -> str:
    """Record project-relative source paths where available."""
    resolved = path.resolve()
    return str(resolved.relative_to(ROOT.parent)) if resolved.is_relative_to(ROOT.parent) else str(resolved)


def _core_grid() -> dict:
    cell_m = 1.0
    nx = int(round((CORE_X_MAX - CORE_X_MIN) / cell_m)) + 1
    nz = int(round((CORE_Z_MAX - CORE_Z_MIN) / cell_m)) + 1
    return {"cell_m": cell_m,
            "x_min_m": CORE_X_MIN, "x_max_m": CORE_X_MAX,
            "z_min_m": CORE_Z_MIN, "z_max_m": CORE_Z_MAX,
            "nx": nx, "nz": nz}


def _load_core_dem(dem_path: Path, grid: dict) -> np.ndarray:
    Image.MAX_IMAGE_PIXELS = None
    img = Image.open(dem_path)
    if img.mode != "F":
        img = img.convert("F")
    full = np.asarray(img, dtype=np.float32)
    if full.shape != (1280, 1280):
        raise ValueError(
            f"expected 1 m DEM of shape (1280, 1280), got {full.shape}")
    j0 = int(round(grid["z_min_m"] + 640))
    j1 = j0 + grid["nz"]
    i0 = int(round(grid["x_min_m"] + 640))
    i1 = i0 + grid["nx"]
    core = full[j0:j1, i0:i1].astype(np.float32) - np.float32(VERTICAL_ORIGIN_M)
    if core.shape != (grid["nz"], grid["nx"]):
        raise ValueError(
            f"core slice shape {core.shape} does not match grid "
            f"({grid['nz']}, {grid['nx']})")
    return core


def _master_grid_elevation(terrain_source_path: Path,
                           absolute_elevations: bool = False) -> np.ndarray:
    """Load the master grid with explicit local or absolute vertical units."""
    arr = np.fromfile(terrain_source_path, dtype="<f4")
    if arr.size != MASTER_SIZE * MASTER_SIZE:
        raise ValueError(
            f"terrain_source.f32 size mismatch: got {arr.size}, "
            f"expected {MASTER_SIZE * MASTER_SIZE}")
    height = arr.reshape(MASTER_SIZE, MASTER_SIZE)
    return height - np.float32(VERTICAL_ORIGIN_M) if absolute_elevations else height


def _master_sample(master: np.ndarray, x: float, z: float) -> float:
    """Sample the master's rendered b-c triangle diagonal at local xz."""
    gx = (x + MASTER_HALF_M) / MASTER_STEP_M
    gz = (z + MASTER_HALF_M) / MASTER_STEP_M
    i0 = max(0, min(int(math.floor(gx)), master.shape[1] - 2))
    j0 = max(0, min(int(math.floor(gz)), master.shape[0] - 2))
    i1 = i0 + 1
    j1 = j0 + 1
    fx = gx - i0
    fz = gz - j0
    a, b = master[j0, i0], master[j0, i1]
    c, d = master[j1, i0], master[j1, i1]
    v = (a + fx * (b - a) + fz * (c - a) if fx + fz <= 1
         else d + (1 - fx) * (c - d) + (1 - fz) * (b - d))
    return float(v)


def _apply_channel_incision(height: np.ndarray, grid: dict,
                            network: dict) -> tuple[np.ndarray, dict]:
    """Lower cells inside each channel by width-to-depth ratio with bank blend."""
    original = height.copy()
    out = height.copy()
    recorded = []
    for seg in network.get("segments", []):
        width_m = max(0.5, float(seg["width_m"]))
        depth_m = width_m / CHANNEL_WIDTH_TO_DEPTH
        half_m = width_m * 0.5
        blend = CHANNEL_BANK_BLEND_M
        for a, b in zip(seg["points_xz"], seg["points_xz"][1:]):
            _carve_segment(out, original, grid, a, b, half_m, blend, depth_m)
        recorded.append({"id": seg["id"], "depth_m": round(depth_m, 3),
                         "width_m": round(width_m, 3),
                         "spring_index": seg["spring_index"]})
    return out, {"width_to_depth_ratio": CHANNEL_WIDTH_TO_DEPTH,
                 "bank_blend_m": CHANNEL_BANK_BLEND_M,
                 "ratio_status": "authored",
                 "segments": recorded}


def _carve_segment(h: np.ndarray, original: np.ndarray, grid: dict,
                   a: list, b: list,
                   half_m: float, blend_m: float, depth_m: float) -> None:
    """Shallow U carve along one line segment, referenced to the pre-carve height."""
    nz = grid["nz"]
    nx = grid["nx"]
    x0, z0 = float(a[0]), float(a[1])
    x1, z1 = float(b[0]), float(b[1])
    length = math.hypot(x1 - x0, z1 - z0)
    if length == 0:
        return
    radius = half_m + blend_m
    steps = max(2, int(math.ceil(length)))
    for s in range(steps + 1):
        t = s / steps
        xs = x0 + t * (x1 - x0)
        zs = z0 + t * (z1 - z0)
        i_min = max(0, int(math.floor(xs - radius - grid["x_min_m"])))
        i_max = min(nx - 1, int(math.ceil(xs + radius - grid["x_min_m"])))
        j_min = max(0, int(math.floor(zs - radius - grid["z_min_m"])))
        j_max = min(nz - 1, int(math.ceil(zs + radius - grid["z_min_m"])))
        for j in range(j_min, j_max + 1):
            z_cell = grid["z_min_m"] + j
            dz = z_cell - zs
            for i in range(i_min, i_max + 1):
                x_cell = grid["x_min_m"] + i
                dx = x_cell - xs
                dist = math.hypot(dx, dz)
                if dist >= radius:
                    continue
                if dist <= half_m:
                    cut = depth_m
                else:
                    f = (radius - dist) / blend_m
                    cut = depth_m * max(0.0, min(1.0, f))
                target = float(original[j, i]) - cut
                if target < h[j, i]:
                    h[j, i] = target


def _sinter_mask_from_network(network: dict, grid: dict) -> np.ndarray:
    """Boolean mask inside the thermal apron: within 90 m of any spring."""
    mask = np.zeros((grid["nz"], grid["nx"]), dtype=bool)
    xs = grid["x_min_m"] + np.arange(grid["nx"])
    zs = grid["z_min_m"] + np.arange(grid["nz"])
    xx, zz = np.meshgrid(xs, zs)
    for spring in network.get("springs", []):
        rim = spring.get("rim_xz", [])
        if not rim:
            continue
        rim_arr = np.asarray(rim, dtype=np.float32)
        cx = float(rim_arr[:, 0].mean())
        cz = float(rim_arr[:, 1].mean())
        mask |= (xx - cx) ** 2 + (zz - cz) ** 2 <= 90.0 ** 2
    return mask


def _microrelief(naip_rgb: np.ndarray, sinter_mask: np.ndarray) -> np.ndarray:
    """Imagery-derived microrelief amplitude in meters."""
    r = naip_rgb[..., 0].astype(np.float32)
    g = naip_rgb[..., 1].astype(np.float32)
    b = naip_rgb[..., 2].astype(np.float32)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    gy = _sobel_axis(lum, axis=0)
    gx = _sobel_axis(lum, axis=1)
    edge = np.hypot(gx, gy)
    radius = max(1, int(MICRORELIEF_LENGTH_SCALE_M / 2))
    smooth = _boxcar(edge, radius)
    detrended = edge - smooth
    detrended -= detrended.min()
    scaled = detrended * sinter_mask.astype(np.float32)
    if scaled.max() > 0:
        scaled /= scaled.max()
    return (scaled * MICRORELIEF_AMPLITUDE_M).astype(np.float32)


def _sample_registered_array(array: np.ndarray, extent: list,
                             grid: dict) -> np.ndarray:
    """Sample a world-registered raster at the grid's vertex coordinates."""
    x0, z0, x1, z1 = map(float, extent)
    if not np.isfinite(extent).all() or x1 <= x0 or z1 <= z0:
        raise ValueError("invalid imagery extent")
    xs = grid["x_min_m"] + np.arange(grid["nx"]) * grid["cell_m"]
    zs = grid["z_min_m"] + np.arange(grid["nz"]) * grid["cell_m"]
    if xs.min() < x0 or xs.max() > x1 or zs.min() < z0 or zs.max() > z1:
        raise ValueError("imagery does not cover the core grid")
    rows, cols = array.shape[:2]
    gx = np.clip((xs - x0) * cols / (x1 - x0) - 0.5, 0, cols - 1)
    gz = np.clip((zs - z0) * rows / (z1 - z0) - 0.5, 0, rows - 1)
    ii, jj = np.floor(gx).astype(int), np.floor(gz).astype(int)
    i1, j1 = np.minimum(ii + 1, cols - 1), np.minimum(jj + 1, rows - 1)
    fx, fz = np.meshgrid(gx - ii, gz - jj)
    if array.ndim == 3:
        fx, fz = fx[..., None], fz[..., None]
    return ((1 - fz) * ((1 - fx) * array[jj[:, None], ii]
                        + fx * array[jj[:, None], i1])
            + fz * ((1 - fx) * array[j1[:, None], ii]
                    + fx * array[j1[:, None], i1])).astype(np.float32)


def _resample_imagery(path: Path, grid: dict) -> tuple[np.ndarray, dict]:
    """Load imagery through its local extent and pixel-center registration."""
    sidecar = path.with_suffix(".json")
    header = json.loads(sidecar.read_text())
    extent = header["local_extent_xz_m"]
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    sampled = _sample_registered_array(rgb, extent, grid)
    return sampled, {"path": _source_path(path), "sha256": _sha256(path),
                     "sidecar": _source_path(sidecar), "sidecar_sha256": _sha256(sidecar),
                     "source_extent_xz_m": extent,
                     "source_shape": list(rgb.shape[:2]),
                     "sampling": "bilinear_pixel_centers_to_world_grid_vertices"}


def _detail_products(height: np.ndarray, grid: dict, imagery: Path,
                     network: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    """Create registered authored relief and residual surface normals."""
    rgb, registration = _resample_imagery(imagery, grid)
    mask = _sinter_mask_from_network(network, grid).astype(np.float32)
    habitat_path = ROOT / "assets" / "textures" / "habitat_mask.png"
    mask_source = {"spring_radius_m": 90.0}
    if habitat_path.exists():
        with Image.open(habitat_path) as image:
            mineral = np.asarray(image.convert("RGB"), dtype=np.float32)[..., 0] / 255
        mask *= _sample_registered_array(mineral, [-2048, -2048, 2048, 2048], grid)
        mask_source.update({"mineral_mask": _source_path(habitat_path),
                            "sha256": _sha256(habitat_path)})
    mask *= _border_weight(grid, STITCH_BLEND_MARGIN_M)
    mask_source["border_taper_m"] = STITCH_BLEND_MARGIN_M
    micro = _microrelief(rgb, mask)
    normal = _bake_normal_map(height + micro, grid["cell_m"])
    return micro, normal, {"imagery_registration": registration,
                           "relief_support": mask_source,
                           "relief_status": "authored_from_imagery"}


def _sobel_axis(arr: np.ndarray, axis: int) -> np.ndarray:
    kernel = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
    if axis == 0:
        kernel = kernel.T
    return _convolve2d(arr, kernel)


def _convolve2d(arr: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Reflect-pad 2D convolution for small kernels."""
    kh, kw = kernel.shape
    pad_h = kh // 2
    pad_w = kw // 2
    padded = np.pad(arr, ((pad_h, pad_h), (pad_w, pad_w)), mode="edge")
    out = np.zeros_like(arr, dtype=np.float32)
    for jj in range(kh):
        for ii in range(kw):
            out += kernel[jj, ii] * padded[jj:jj + arr.shape[0], ii:ii + arr.shape[1]]
    return out


def _boxcar(arr: np.ndarray, radius: int) -> np.ndarray:
    """Simple boxcar blur with reflect padding."""
    r = max(1, int(radius))
    size = 2 * r + 1
    kernel = np.ones((size, size), dtype=np.float32) / (size * size)
    return _convolve2d(arr, kernel)


def _pin_edges_to_master(core_h: np.ndarray, grid: dict,
                         master: np.ndarray, margin_m: float
                         ) -> tuple[np.ndarray, dict]:
    """Pin core heightfield edges to the master grid with a linear inward blend."""
    nz = grid["nz"]
    nx = grid["nx"]
    cell_m = grid["cell_m"]
    out = core_h.copy()
    master_sample = np.zeros_like(core_h, dtype=np.float32)
    xs = grid["x_min_m"] + np.arange(nx) * cell_m
    zs = grid["z_min_m"] + np.arange(nz) * cell_m
    for j in range(nz):
        for i in range(nx):
            master_sample[j, i] = _master_sample(master, float(xs[i]), float(zs[j]))
    j_grid, i_grid = np.meshgrid(np.arange(nz), np.arange(nx), indexing="ij")
    d_j = np.minimum(j_grid, nz - 1 - j_grid)
    d_i = np.minimum(i_grid, nx - 1 - i_grid)
    distance_m = np.minimum(d_j, d_i) * cell_m
    blend = np.clip(distance_m / margin_m, 0.0, 1.0).astype(np.float32)
    out = (1.0 - blend) * master_sample + blend * core_h
    return out.astype(np.float32), {
        "margin_m": margin_m,
        "status": "authored",
        "master_sampling": "rendered_triangle_diagonal_b_c",
    }


def _border_weight(grid: dict, margin_m: float) -> np.ndarray:
    """Blend from zero at the perimeter to one beyond the border margin."""
    jj, ii = np.indices((grid["nz"], grid["nx"]))
    distance = np.minimum(np.minimum(jj, grid["nz"] - 1 - jj),
                          np.minimum(ii, grid["nx"] - 1 - ii)) * grid["cell_m"]
    return np.clip(distance / margin_m, 0, 1).astype(np.float32)


def _bake_normal_map(height: np.ndarray, cell_m: float) -> np.ndarray:
    """Encode fine surface normals relative to the interpolated mesh TBN frame."""
    height = np.asarray(height, dtype=np.float64)
    if height.ndim != 2 or min(height.shape) < 3 or not np.isfinite(height).all():
        raise ValueError("normal heightfield requires a finite 2D grid")
    if not math.isfinite(cell_m) or cell_m <= 0:
        raise ValueError("normal cell spacing must be positive")
    gz, gx = np.gradient(height, cell_m)
    target = np.stack([-gx, np.ones_like(gx), -gz], axis=-1)
    target /= np.linalg.norm(target, axis=-1, keepdims=True)
    nz, nx = height.shape
    ci = np.unique(np.r_[np.arange(0, nx, NORMAL_MESH_DECIMATION), nx - 1])
    cj = np.unique(np.r_[np.arange(0, nz, NORMAL_MESH_DECIMATION), nz - 1])
    mesh_height = height[np.ix_(cj, ci)]
    ip = np.minimum(np.arange(len(ci)) + 1, len(ci) - 1)
    ine = np.maximum(np.arange(len(ci)) - 1, 0)
    jp = np.minimum(np.arange(len(cj)) + 1, len(cj) - 1)
    jne = np.maximum(np.arange(len(cj)) - 1, 0)
    dx = (mesh_height[:, ip] - mesh_height[:, ine]) / ((ci[ip] - ci[ine]) * cell_m)
    dz = (mesh_height[jp] - mesh_height[jne]) / ((cj[jp] - cj[jne]) * cell_m)[:, None]
    normal = np.stack([-dx, np.ones_like(dx), -dz], axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    tangent = np.zeros_like(normal)
    tangent[..., 0] = 1
    tangent -= normal * normal[..., :1]
    tangent /= np.linalg.norm(tangent, axis=-1, keepdims=True)
    binormal = np.cross(tangent, normal)
    coarse_frame = np.stack([tangent, binormal, normal], axis=-1)
    ii = np.clip(np.searchsorted(ci, np.arange(nx), side="right") - 1, 0, len(ci) - 2)
    jj = np.clip(np.searchsorted(cj, np.arange(nz), side="right") - 1, 0, len(cj) - 2)
    fx, fz = np.meshgrid((np.arange(nx) - ci[ii]) / (ci[ii + 1] - ci[ii]),
                         (np.arange(nz) - cj[jj]) / (cj[jj + 1] - cj[jj]))
    a = coarse_frame[jj[:, None], ii]
    b = coarse_frame[jj[:, None], ii + 1]
    c = coarse_frame[jj[:, None] + 1, ii]
    d = coarse_frame[jj[:, None] + 1, ii + 1]
    fx, fz = fx[..., None, None], fz[..., None, None]
    frame = np.where(fx + fz <= 1, a + fx * (b - a) + fz * (c - a),
                     d + (1 - fx) * (c - d) + (1 - fz) * (b - d))
    residual = np.linalg.solve(frame, target[..., None])[..., 0]
    residual /= np.linalg.norm(residual, axis=-1, keepdims=True)
    residual[np.abs(residual) < 1e-12] = 0
    return np.rint(np.clip(residual * 0.5 + 0.5, 0, 1) * 255).astype(np.uint8)


def _refresh_detail(out_dir: Path, imagery: Path, network: dict,
                    backup_dir: Path) -> None:
    """Refresh detail products while preserving terrain heights and stitch data."""
    header_path = out_dir / "core_terrain.json"
    header = json.loads(header_path.read_text())
    grid = header["grid"]
    height_path = out_dir / "core_heightfield.f32"
    height_sha = _sha256(height_path)
    height = np.fromfile(height_path, dtype="<f4").reshape(grid["nz"], grid["nx"])
    if height_sha != header["layers"]["core_heightfield_m"]["sha256"]:
        raise ValueError("core heightfield does not match its recorded hash")
    micro, normal, detail_meta = _detail_products(height, grid, imagery, network)
    backup_dir.mkdir(parents=True, exist_ok=True)
    names = ["core_terrain.json", "core_heightfield.f32", "core_microrelief.f32",
             "core_normal.png", "stitch.json"]
    for name in names:
        source = out_dir / name
        destination = backup_dir / name
        if destination.exists():
            raise ValueError(f"backup already exists: {destination}")
        if source.exists():
            shutil.copy2(source, destination)
    micro_path, normal_path = out_dir / "core_microrelief.f32", out_dir / "core_normal.png"
    micro_sha = _write_f32(micro_path, micro)
    Image.fromarray(normal).save(normal_path)
    header["layers"]["core_microrelief_m"].update({
        "sha256": micro_sha, "status": "authored_from_imagery",
        "range_m": [float(micro.min()), float(micro.max())]})
    header["layers"]["core_normal"].update({
        "sha256": _sha256(normal_path), "contents": "fine_surface_relative_to_rendered_mesh_frame",
        "contract": NORMAL_CONTRACT, "flat_rgb": [128, 128, 255],
        "mesh_decimation": NORMAL_MESH_DECIMATION,
        "target_spacing_m": grid["cell_m"],
        "channels": ["east_projected_tangent", "south_binormal_cross_tangent_normal", "surface_normal"],
        "frame_sampling": "mesh_vertex_tbn_barycentric_diagonal_b_c",
        "channel_ranges": [[int(normal[..., k].min()), int(normal[..., k].max())] for k in range(3)],
        "status": "authored_residual_detail"})
    header["detail_refresh"] = detail_meta
    header["detail_refresh"]["generated_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header_path.write_text(json.dumps(header, indent=2) + "\n")
    if _sha256(height_path) != height_sha:
        raise RuntimeError("core heightfield changed during detail refresh")


def _refresh_stitch(out_dir: Path, master_path: Path, backup_dir: Path,
                    absolute_elevations: bool = False) -> None:
    """Correct the existing authored border against the rendered master terrain."""
    header_path = out_dir / "core_terrain.json"
    header = json.loads(header_path.read_text())
    grid = header["grid"]
    height_path = out_dir / "core_heightfield.f32"
    before_sha = _sha256(height_path)
    if before_sha != header["layers"]["core_heightfield_m"]["sha256"]:
        raise ValueError("core heightfield does not match its recorded hash")
    original = np.fromfile(height_path, dtype="<f4").reshape(grid["nz"], grid["nx"])
    master = _master_grid_elevation(master_path, absolute_elevations)
    updated, blend = _pin_edges_to_master(original, grid, master, STITCH_BLEND_MARGIN_M)
    interior = _border_weight(grid, STITCH_BLEND_MARGIN_M) == 1
    if not np.array_equal(updated[interior], original[interior]):
        raise RuntimeError("stitch correction changed interior heights")
    backup_dir.mkdir(parents=True, exist_ok=True)
    for name in ["core_terrain.json", "core_heightfield.f32", "core_microrelief.f32",
                 "core_normal.png", "stitch.json"]:
        destination = backup_dir / name
        if destination.exists():
            raise ValueError(f"backup already exists: {destination}")
        shutil.copy2(out_dir / name, destination)
    delta = updated - original
    header["layers"]["core_heightfield_m"].update({
        "sha256": _write_f32(height_path, updated),
        "contents": "existing_core_heightfield_plus_authored_master_stitch_correction"})
    source = {"path": _source_path(master_path), "sha256": _sha256(master_path),
              "role": "rendered_master_terrain_4m",
              "vertical_units": "absolute_m" if absolute_elevations else "local_m"}
    header["stitch_refresh"] = {
        "status": "authored_border_correction", "input_core_sha256": before_sha,
        "master_source": source, "blend": blend,
        "delta_range_m": [float(delta.min()), float(delta.max())],
        "changed_cells": int(np.count_nonzero(delta)),
        "interior_unchanged": True,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    stitch = _stitch_table(updated, grid, master)
    stitch["sources"] = [source]
    stitch["blend_margin"] = blend
    stitch["refresh_provenance"] = header["stitch_refresh"]
    (out_dir / "stitch.json").write_text(json.dumps(stitch, indent=2) + "\n")
    header["layers"]["core_normal"].update({"contract": "", "status": "requires_detail_refresh"})
    header_path.write_text(json.dumps(header, indent=2) + "\n")


def _stitch_table(core_height: np.ndarray, grid: dict,
                  master: np.ndarray) -> dict:
    """Shared edge heights between the core border and the master grid."""
    out: dict = {"grid_step_m": MASTER_STEP_M,
                 "vertical_origin_m": VERTICAL_ORIGIN_M,
                 "edges": {}, "cells_covered": []}
    for side, iterate in (("north", _edge_north), ("south", _edge_south),
                          ("east", _edge_east), ("west", _edge_west)):
        vertices = []
        for xv, zv in iterate(grid, step_m=MASTER_STEP_M):
            core_val = _bilinear_core(core_height, grid, xv, zv)
            master_val = _master_sample(master, xv, zv)
            vertices.append({"x": round(xv, 3), "z": round(zv, 3),
                             "core_m": round(core_val, 4),
                             "master_m": round(master_val, 4)})
        out["edges"][side] = vertices
    i0 = int(math.ceil((grid["x_min_m"] + MASTER_HALF_M) / MASTER_STEP_M))
    i1 = int(math.floor((grid["x_max_m"] + MASTER_HALF_M) / MASTER_STEP_M))
    j0 = int(math.ceil((grid["z_min_m"] + MASTER_HALF_M) / MASTER_STEP_M))
    j1 = int(math.floor((grid["z_max_m"] + MASTER_HALF_M) / MASTER_STEP_M))
    out["cells_covered"] = {"i_range": [i0, i1], "j_range": [j0, j1],
                            "count": max(0, (i1 - i0)) * max(0, (j1 - j0))}
    return out


def _edge_north(grid: dict, step_m: float):
    z = grid["z_min_m"]
    for i in range(int(round((grid["x_max_m"] - grid["x_min_m"]) / step_m)) + 1):
        yield grid["x_min_m"] + i * step_m, z


def _edge_south(grid: dict, step_m: float):
    z = grid["z_max_m"]
    for i in range(int(round((grid["x_max_m"] - grid["x_min_m"]) / step_m)) + 1):
        yield grid["x_min_m"] + i * step_m, z


def _edge_east(grid: dict, step_m: float):
    x = grid["x_max_m"]
    for j in range(int(round((grid["z_max_m"] - grid["z_min_m"]) / step_m)) + 1):
        yield x, grid["z_min_m"] + j * step_m


def _edge_west(grid: dict, step_m: float):
    x = grid["x_min_m"]
    for j in range(int(round((grid["z_max_m"] - grid["z_min_m"]) / step_m)) + 1):
        yield x, grid["z_min_m"] + j * step_m


def _bilinear_core(height: np.ndarray, grid: dict, x: float, z: float) -> float:
    gx = (x - grid["x_min_m"]) / grid["cell_m"]
    gz = (z - grid["z_min_m"]) / grid["cell_m"]
    i0 = max(0, min(height.shape[1] - 2, int(math.floor(gx))))
    j0 = max(0, min(height.shape[0] - 2, int(math.floor(gz))))
    fx = max(0.0, min(1.0, gx - i0))
    fz = max(0.0, min(1.0, gz - j0))
    v = (height[j0, i0] * (1 - fx) * (1 - fz)
         + height[j0, i0 + 1] * fx * (1 - fz)
         + height[j0 + 1, i0] * (1 - fx) * fz
         + height[j0 + 1, i0 + 1] * fx * fz)
    return float(v)


def _write_f32(path: Path, arr: np.ndarray) -> str:
    arr.astype("<f4").tofile(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem", type=Path,
                        default=ROOT / "references" / "dem_1m_core.tif")
    parser.add_argument("--outflow",
                        type=Path,
                        default=ROOT / "data" / "outflow_network" /
                        "outflow_network.json")
    parser.add_argument("--imagery", type=Path,
                        default=ROOT / "references" /
                        "midway_orthophoto_detail.jpg")
    parser.add_argument("--master-terrain", type=Path,
                        default=ROOT / "data" / "terrain.f32")
    parser.add_argument("--master-absolute", action="store_true")
    parser.add_argument("--out-dir", type=Path,
                        default=ROOT / "data" / "core_terrain")
    parser.add_argument("--refresh-detail", action="store_true")
    parser.add_argument("--refresh-stitch", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args(argv)
    if args.refresh_detail and args.refresh_stitch:
        parser.error("choose one refresh operation")
    if args.refresh_stitch:
        if args.backup_dir is None:
            parser.error("--refresh-stitch requires --backup-dir")
        _refresh_stitch(args.out_dir, args.master_terrain, args.backup_dir, args.master_absolute)
        print(f"refreshed authored border in {args.out_dir}; run --refresh-detail")
        return 0
    if args.refresh_detail:
        if args.backup_dir is None:
            parser.error("--refresh-detail requires --backup-dir")
        network = json.loads(args.outflow.read_text()) if args.outflow.exists() else {}
        _refresh_detail(args.out_dir, args.imagery, network, args.backup_dir)
        print(f"refreshed registered detail in {args.out_dir}; preserved heightfield and stitch")
        return 0
    if not args.dem.exists():
        print(f"missing DEM {args.dem}", file=sys.stderr)
        return 2
    grid = _core_grid()
    core_dem = _load_core_dem(args.dem, grid)
    base_sha = _sha256(args.dem)
    network = {}
    outflow_status = "absent"
    channel_meta = {"width_to_depth_ratio": CHANNEL_WIDTH_TO_DEPTH,
                    "bank_blend_m": CHANNEL_BANK_BLEND_M,
                    "ratio_status": "authored",
                    "segments": []}
    if args.outflow.exists():
        network = json.loads(args.outflow.read_text())
        outflow_status = "linked"
        core_incised, channel_meta = _apply_channel_incision(
            core_dem.copy(), grid, network)
    else:
        core_incised = core_dem.copy()
    naip_sha = _sha256(args.imagery) if args.imagery.exists() else ""
    master = _master_grid_elevation(args.master_terrain, args.master_absolute)
    core_height, blend_info = _pin_edges_to_master(
        core_incised.astype(np.float32), grid, master,
        margin_m=STITCH_BLEND_MARGIN_M)
    detail_meta = {}
    if args.imagery.exists():
        microrelief, normals, detail_meta = _detail_products(
            core_height, grid, args.imagery, network)
    else:
        microrelief = np.zeros_like(core_height, dtype=np.float32)
        normals = _bake_normal_map(core_height, grid["cell_m"])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    height_path = args.out_dir / "core_heightfield.f32"
    height_sha = _write_f32(height_path, core_height)
    microrelief_path = args.out_dir / "core_microrelief.f32"
    micro_sha = _write_f32(microrelief_path, microrelief)
    normal_path = args.out_dir / "core_normal.png"
    Image.fromarray(normals, mode="RGB").save(normal_path)
    normal_sha = hashlib.sha256(normal_path.read_bytes()).hexdigest()
    stitch = _stitch_table(core_height, grid, master)
    stitch_path = args.out_dir / "stitch.json"
    stitch["sources"] = [
        {"path": str(args.master_terrain.resolve().relative_to(ROOT.parent)),
         "sha256": _sha256(args.master_terrain), "role": "rendered_master_terrain_4m",
         "vertical_units": "absolute_m" if args.master_absolute else "local_m"},
        {"path": str(args.dem.resolve().relative_to(ROOT.parent)),
         "sha256": base_sha, "role": "lidar_1m_dem"},
    ]
    stitch["blend_margin"] = blend_info
    stitch_path.write_text(json.dumps(stitch, indent=2) + "\n")
    header = {
        "schema": "yellowstone.core_terrain.v1",
        "status": "fitted_not_validated",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "grid": grid,
        "vertical_origin_m": VERTICAL_ORIGIN_M,
        "vertical_datum": "NAVD88",
        "frame": {
            "crs": "EPSG:32612",
            "origin_utm_m": [512952.5950985841, 4930199.044097667],
        },
        "layers": {
            "core_heightfield_m": {
                "path": height_path.name,
                "sha256": height_sha,
                "dtype": "<f4",
                "shape": [core_height.shape[0], core_height.shape[1]],
                "contents": "lidar_base_minus_vertical_origin_plus_channel_incision",
            },
            "core_microrelief_m": {
                "path": microrelief_path.name,
                "sha256": micro_sha,
                "dtype": "<f4",
                "shape": [microrelief.shape[0], microrelief.shape[1]],
                "contents": "authored_from_imagery",
                "amplitude_m": MICRORELIEF_AMPLITUDE_M,
                "length_scale_m": MICRORELIEF_LENGTH_SCALE_M,
                "status": "authored_from_imagery",
            },
            "core_normal": {
                "path": normal_path.name,
                "sha256": normal_sha,
                "contents": "fine_surface_relative_to_rendered_mesh_frame",
                "contract": NORMAL_CONTRACT,
                "flat_rgb": [128, 128, 255],
                "mesh_decimation": NORMAL_MESH_DECIMATION,
                "target_spacing_m": grid["cell_m"],
                "channels": ["east_projected_tangent", "south_binormal_cross_tangent_normal", "surface_normal"],
                "frame_sampling": "mesh_vertex_tbn_barycentric_diagonal_b_c",
            },
        },
        "detail_refresh": detail_meta,
        "channel_incision": channel_meta,
        "outflow_network_status": outflow_status,
        "sources": [
            {"path": str(args.dem.resolve().relative_to(ROOT.parent)),
             "sha256": base_sha, "role": "lidar_1m_dem"},
            {"path": str(args.imagery.resolve().relative_to(ROOT.parent)),
             "sha256": naip_sha, "role": "naip_imagery"} if naip_sha else {},
            {"path": str(args.outflow.resolve().relative_to(ROOT.parent))
             if args.outflow.exists() else str(args.outflow),
             "sha256": _sha256(args.outflow) if args.outflow.exists() else "",
             "role": "outflow_network"},
        ],
    }
    (args.out_dir / "core_terrain.json").write_text(
        json.dumps(header, indent=2) + "\n")
    print(f"core heightfield shape {core_height.shape} range "
          f"[{float(core_height.min()):.2f}, {float(core_height.max()):.2f}] m")
    print(f"wrote {args.out_dir}/core_terrain.json plus layers and stitch.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
