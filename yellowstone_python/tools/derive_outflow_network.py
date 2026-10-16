#!/usr/bin/env python3
"""Midway outflow network derivation and raster export."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from yellowstone_python.common.io import write_json_atomic

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
import yellowstone_python.thermal_features.outflow_network as onet  # noqa: E402


# Named Midway thermal pools with surface outflow across the apron.
DEFAULT_SPRING_NAMES = (
    "Grand Prismatic Spring",
    "Excelsior Geyser Crater",
    "Opal Pool",
    "Turquoise Pool",
)


from yellowstone_python.common.io import sha256_file as _sha256


def _load_dem(dem_path: Path) -> tuple[np.ndarray, str]:
    """Return the DEM as a numpy array of shape (CORE_SIZE, CORE_SIZE)."""
    if not dem_path.exists():
        raise FileNotFoundError(
            f"DEM tile not found at {dem_path}. "
            "Fetch the 1 m 3DEP tile first (see dem_1m_core.tif.provenance.json)."
        )
    sha = _sha256(dem_path)
    Image.MAX_IMAGE_PIXELS = None
    img = Image.open(dem_path)
    if img.size != (onet.CORE_SIZE, onet.CORE_SIZE):
        raise ValueError(
            f"DEM size {img.size} does not match core grid "
            f"({onet.CORE_SIZE}, {onet.CORE_SIZE})"
        )
    if img.mode != "F":
        img = img.convert("F")
    arr = np.asarray(img, dtype=np.float32)
    if not np.all(np.isfinite(arr)):
        raise ValueError("DEM contains non-finite values; cannot route")
    return arr, sha


def _load_naip(naip_path: Path, grid: onet.Grid) -> tuple[np.ndarray, str]:
    """Resample NAIP RGB JPEG to the core 1 m grid as float32 in [0, 1]."""
    sha = _sha256(naip_path)
    Image.MAX_IMAGE_PIXELS = None
    img = Image.open(naip_path).convert("RGB")
    img = img.resize((grid.size, grid.size), Image.Resampling.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return arr, sha


def _world_pools(world_path: Path, names: tuple[str, ...]) -> list[dict]:
    """Return the matching pool entries from world.json preserving list order."""
    data = json.loads(world_path.read_text())
    pools = data.get("pools", [])
    chosen = [p for p in pools if p.get("name") in names]
    if not chosen:
        raise ValueError(
            f"no pools in {world_path} matched the requested names {names}")
    return chosen


def _verify_frame(midway_root: Path) -> dict:
    """Confirm that the DEM frame matches the orthophoto and master grid."""
    ortho = json.loads((midway_root / "references" /
                        "midway_orthophoto_detail.json").read_text())
    terrain = json.loads((midway_root / "references" /
                          "terrain_source.json").read_text())
    world = json.loads((midway_root / "data" / "world.json").read_text())
    ortho_origin = tuple(ortho["origin_utm_m"])
    terrain_origin = tuple(terrain["origin_utm_m"])
    world_origin = tuple(world["georeference"]["origin"][:2])
    if not (math.isclose(ortho_origin[0], terrain_origin[0], abs_tol=1e-3)
            and math.isclose(ortho_origin[1], terrain_origin[1], abs_tol=1e-3)):
        raise ValueError(
            "orthophoto and master terrain origins disagree; frames differ")
    if not (math.isclose(ortho_origin[0], world_origin[0], abs_tol=1e-3)
            and math.isclose(ortho_origin[1], world_origin[1], abs_tol=1e-3)):
        raise ValueError(
            "orthophoto and world.json origins disagree; frames differ")
    return {
        "ortho_origin_utm_m": list(ortho_origin),
        "terrain_origin_utm_m": list(terrain_origin),
        "world_origin_utm_m": list(world_origin),
        "local_extent_xz_m": ortho["local_extent_xz_m"],
    }


def _write_raster(path: Path, array: np.ndarray, dtype: str) -> dict:
    """Write a little-endian row-major raster and return a header snippet."""
    arr = np.ascontiguousarray(array, dtype=dtype)
    arr.astype(dtype).tofile(path)
    sha = _sha256(path)
    return {"path": path.name, "dtype": dtype, "sha256": sha,
            "shape": list(array.shape)}


def _grid_header(grid: onet.Grid) -> dict:
    return {
        "origin_xz_m": [-grid.half_m, -grid.half_m],
        "cell_m": grid.cell_m,
        "size": grid.size,
        "row_order": "north_to_south",
        "coordinate_frame": "local xz meters, x east, z south, "
                            "aligned with references/midway_orthophoto_detail.json",
    }


def _assemble_spring_entry(pool: dict, grid: onet.Grid,
                           dem: np.ndarray) -> dict:
    """Compute the rim cells, elevations and bearings for one pool."""
    ring = pool.get("ring", [])
    if len(ring) < 3:
        raise ValueError(f"pool {pool.get('id')} ring has fewer than 3 points")
    center = pool.get("center", [0, 0, 0])
    cx = float(center[0])
    cz = float(center[2])
    pool_mask = onet.polygon_mask([(float(p[0]), float(p[1])) for p in ring], grid)
    rim = onet.rim_mask(pool_mask)
    rim_idx = np.argwhere(rim)
    if rim_idx.size == 0:
        raise ValueError(
            f"pool {pool.get('id')} produced no rim cells on the core grid; the ring likely falls outside the core extent"
        )
    rim_cells: list[tuple[int, int, float]] = []
    rim_coords: list[list[float]] = []
    rim_elev: list[float] = []
    for j, i in rim_idx:
        rim_cells.append((int(j), int(i), 0.0))
        x, z = grid.cell_center_xz(int(j), int(i))
        rim_coords.append([round(x, 3), round(z, 3)])
        rim_elev.append(float(dem[int(j), int(i)]))
    return {
        "pool_id": pool.get("id"),
        "name": pool.get("name"),
        "source_id": pool.get("source_id"),
        "center_xz": (cx, cz),
        "pool_mask": pool_mask,
        "rim_mask": rim,
        "rim_cells": rim_cells,
        "rim_cell_elevations_m": rim_elev,
        "rim_xz": rim_coords,
        "rim_elevation_m": float(np.mean(rim_elev)),
    }


def _near_rim_overlap(spring_entries: list[dict], weir_disc: np.ndarray,
                      uniform_disc: np.ndarray, imagery_wet: np.ndarray,
                      grid: onet.Grid, wet_threshold: float,
                      radius_m: float) -> list[dict]:
    """Compute near-rim channel-vs-imagery overlap for weir and uniform runs."""
    xs = -grid.half_m + 0.5 * grid.cell_m + np.arange(grid.size) * grid.cell_m
    zs = -grid.half_m + 0.5 * grid.cell_m + np.arange(grid.size) * grid.cell_m
    xx, zz = np.meshgrid(xs, zs)
    reports = []
    for s_idx, spring in enumerate(spring_entries):
        rim_xz = np.asarray(spring["rim_xz"], dtype=np.float64)
        if rim_xz.size == 0:
            continue
        rim_x = rim_xz[:, 0]
        rim_z = rim_xz[:, 1]
        near = np.zeros((grid.size, grid.size), dtype=bool)
        r2 = radius_m ** 2
        for rx, rz in zip(rim_x, rim_z):
            near |= (xx - rx) ** 2 + (zz - rz) ** 2 <= r2
        near &= ~spring["pool_mask"]
        weir_wet = (weir_disc[s_idx] > wet_threshold) & near
        uni_wet = (uniform_disc[s_idx] > wet_threshold) & near
        img_wet = imagery_wet & near

        def _metrics(mask_channel, mask_imagery):
            inter = int(np.count_nonzero(mask_channel & mask_imagery))
            union = int(np.count_nonzero(mask_channel | mask_imagery))
            c = int(np.count_nonzero(mask_channel))
            i_cells = int(np.count_nonzero(mask_imagery))
            return {
                "iou": round(inter / union, 4) if union > 0 else 0.0,
                "channel_wet_cells": c,
                "channel_hits_imagery": inter,
                "fraction_of_imagery_captured": (round(inter / i_cells, 4)
                                                 if i_cells > 0 else 0.0),
                "fraction_of_channel_in_imagery": (round(inter / c, 4)
                                                   if c > 0 else 0.0),
            }
        weir_metrics = _metrics(weir_wet, img_wet)
        uniform_metrics = _metrics(uni_wet, img_wet)
        reports.append({
            "spring_index": s_idx,
            "pool_id": spring["pool_id"],
            "radius_m": radius_m,
            "near_rim_cells": int(np.count_nonzero(near)),
            "imagery_wet_cells": int(np.count_nonzero(img_wet)),
            "weir": weir_metrics,
            "uniform": uniform_metrics,
            "weir_minus_uniform_fraction_of_imagery_captured": round(
                weir_metrics["fraction_of_imagery_captured"]
                - uniform_metrics["fraction_of_imagery_captured"], 4),
        })
    return reports


def _apply_weir_injection(spring_entries: list[dict],
                          discharges: dict,
                          convention: str) -> list[dict]:
    """Set rim-cell weights per spring under the chosen convention."""
    reports = []
    for spring in spring_entries:
        pool_id = spring.get("pool_id")
        entry = discharges.get(pool_id)
        if entry is None:
            raise ValueError(
                f"pool {pool_id} is missing from the spring discharges input")
        q = float(entry["discharge_m3_s"])
        z_rim = spring["rim_cell_elevations_m"]
        if convention == "weir":
            res = onet.weir_rim_injection(z_rim, q)
            weights = res["weights"]
            sensitivity = onet.rim_injection_sensitivity(z_rim, q)
            pool_stage = res["pool_stage_above_lowest_rim_m"]
            n_active = res["n_active_rim"]
        else:
            weights = [1.0 / len(z_rim)] * len(z_rim)
            sensitivity = None
            pool_stage = None
            n_active = len(z_rim)
        updated_cells: list[tuple[int, int, float]] = []
        for (j, i, _old), w_new in zip(spring["rim_cells"], weights):
            updated_cells.append((int(j), int(i), float(w_new)))
        spring["rim_cells"] = updated_cells
        spring_discharge_entry = {
            "pool_id": pool_id,
            "discharge_m3_s": q,
            "discharge_status": entry.get("status", "unknown"),
            "pool_stage_above_lowest_rim_m": (round(pool_stage, 4)
                                              if pool_stage is not None else None),
            "n_active_rim_cells": n_active,
            "weir_sensitivity_rmse_z_m": (sensitivity["rmse_z_m"]
                                          if sensitivity else None),
            "weir_sensitivity_nominal": (sensitivity["nominal"]
                                         if sensitivity else None),
            "weir_sensitivity_monte_carlo": (sensitivity["monte_carlo"]
                                             if sensitivity else None),
            "weir_sensitivity_noise_samples": (sensitivity["noise_samples"]
                                               if sensitivity else None),
            "citation": entry.get("citation"),
            "note": entry.get("note"),
        }
        reports.append(spring_discharge_entry)
    return reports


def _collect_in_pool(spring_entries: list[dict], grid: onet.Grid) -> np.ndarray:
    acc = np.zeros((grid.size, grid.size), dtype=bool)
    for s in spring_entries:
        acc |= s["pool_mask"]
    return acc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem", type=Path,
                        default=ROOT.parent / "yellowstone_midway" /
                        "references" / "dem_1m_core.tif",
                        help="Path to the 1 m DEM GeoTIFF over the core extent.")
    parser.add_argument("--pools", type=Path,
                        default=ROOT.parent / "yellowstone_midway" /
                        "data" / "world.json",
                        help="Path to world.json containing pool polygons.")
    parser.add_argument("--imagery", type=Path,
                        default=ROOT.parent / "yellowstone_midway" /
                        "references" / "midway_orthophoto_detail.jpg",
                        help="Path to the NAIP detail JPEG for the core extent.")
    parser.add_argument("--midway-root", type=Path,
                        default=ROOT.parent / "yellowstone_midway",
                        help="Root of the yellowstone_midway tree for frame checks.")
    parser.add_argument("--out-dir", type=Path,
                        default=ROOT.parent / "yellowstone_midway" / "data" /
                        "outflow_network",
                        help="Directory to receive outflow_network.json and rasters.")
    parser.add_argument("--spring-names", nargs="+",
                        default=list(DEFAULT_SPRING_NAMES),
                        help="Names of pools to treat as spring sources.")
    parser.add_argument("--flow-threshold", type=float, default=0.05,
                        help="Minimum spring fraction kept in the segment list.")
    parser.add_argument("--spring-discharges", type=Path,
                        default=ROOT.parent / "yellowstone_midway" / "data" /
                        "outflow_network" / "spring_discharges.json",
                        help="JSON file with per-pool discharges for the weir rim injection.")
    parser.add_argument("--injection-convention", choices=["weir", "uniform"],
                        default="weir",
                        help="Rim injection convention. Weir is the default.")
    args = parser.parse_args(argv)
    try:
        frame = _verify_frame(args.midway_root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"frame verification failed: {exc}", file=sys.stderr)
        return 2
    try:
        dem, dem_sha = _load_dem(args.dem)
    except (FileNotFoundError, ValueError) as exc:
        print(f"DEM load failed: {exc}", file=sys.stderr)
        return 2
    grid = onet.Grid()
    pools = _world_pools(args.pools, tuple(args.spring_names))
    pool_sha = _sha256(args.pools)
    spring_entries = [_assemble_spring_entry(p, grid, dem) for p in pools]
    discharge_doc = json.loads(args.spring_discharges.read_text())
    discharge_doc_sha = _sha256(args.spring_discharges)
    discharge_reports = _apply_weir_injection(
        spring_entries, discharge_doc["springs"],
        convention=args.injection_convention)
    centers = [s["center_xz"] for s in spring_entries]
    thermal = onet.thermal_proximity_mask(grid, centers, radius_m=220.0)
    rgb, naip_sha = _load_naip(args.imagery, grid)
    wet, wet_params = onet.classify_wet_mask(rgb, thermal)
    in_pool = _collect_in_pool(spring_entries, grid)
    wet = wet & ~in_pool
    # Pool interior raised to a plateau forces rim routing outward.
    interior_dem = dem.copy()
    for spring in spring_entries:
        interior_only = spring["pool_mask"] & ~spring["rim_mask"]
        interior_dem[interior_only] = float(dem.max()) + 1000.0
    filled = onet.fill_depressions(interior_dem)
    weights = onet.mfd_weights(filled, cell_m=grid.cell_m,
                               exponent=onet.MFD_EXPONENT)
    injections: list[tuple[int, int, int, float]] = []
    for s_idx, spring in enumerate(spring_entries):
        for j, i, w in spring["rim_cells"]:
            injections.append((s_idx, j, i, w))
    discharge, dominant, exported = onet.propagate_discharge(
        weights, filled, injections)
    # Baseline uniform injection for the convention comparison.
    uniform_injections: list[tuple[int, int, int, float]] = []
    for s_idx, spring in enumerate(spring_entries):
        n = len(spring["rim_cells"])
        if n == 0:
            continue
        for j, i, _w in spring["rim_cells"]:
            uniform_injections.append((s_idx, int(j), int(i), 1.0 / n))
    uniform_discharge, _udom, _uexp = onet.propagate_discharge(
        weights, filled, uniform_injections)
    # Slope on the unmodified fill keeps the raised plateau out of the raster.
    slope_dem = onet.fill_depressions(dem)
    slope = onet.slope_magnitude(slope_dem, cell_m=grid.cell_m)
    rim_sources = [(j, i) for s in spring_entries for j, i, _ in s["rim_cells"]]
    flow_len = onet.flow_length_raster(weights, filled, rim_sources,
                                       cell_m=grid.cell_m)
    spring_index = onet.spring_index_raster(dominant, in_pool, discharge,
                                            threshold=1e-5)
    flow_frac = onet.flow_fraction_raster(discharge)
    world_data = json.loads(args.pools.read_text())
    rivers = world_data.get("rivers", [])
    river_mask = onet.rasterize_rivers_mask(rivers, grid)
    raw_segments = onet.extract_channels(spring_entries, weights, discharge, slope,
                                         wet, grid, river_mask,
                                         flow_threshold=args.flow_threshold)
    segments, cleanup_report = onet.cleanup_segments(raw_segments, slope, grid)
    length_histogram = onet.segment_length_histogram(segments)
    conservation = onet.junction_conservation(segments, grid)
    agreement = onet.orientation_agreement(segments, wet, grid)
    exit_fractions = onet.river_and_grid_fractions(
        weights, filled, injections, river_mask)
    near_rim_overlap = _near_rim_overlap(
        spring_entries, discharge, uniform_discharge, wet, grid,
        wet_threshold=args.flow_threshold, radius_m=30.0)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    raster_headers = {
        "spring_index": _write_raster(args.out_dir / "spring_index.i16",
                                      spring_index, "<i2"),
        "flow_fraction": _write_raster(args.out_dir / "flow_fraction.f32",
                                       flow_frac, "<f4"),
        "flow_length_m": _write_raster(args.out_dir / "flow_length_m.f32",
                                       flow_len, "<f4"),
        "slope": _write_raster(args.out_dir / "slope.f32",
                               slope, "<f4"),
        "wet_mask": _write_raster(args.out_dir / "wet_mask.i16",
                                  wet.astype(np.int16), "<i2"),
        "in_pool": _write_raster(args.out_dir / "in_pool.i16",
                                 in_pool.astype(np.int16), "<i2"),
    }
    springs_out = []
    for s_idx, spring in enumerate(spring_entries):
        reach_segs = [seg for seg in segments
                      if seg["spring_index"] == s_idx and seg.get("reaches_river")]
        fractions = next((f for f in exit_fractions
                          if f["spring_index"] == s_idx),
                         {"river_inflow_fraction": 0.0,
                          "grid_exit_fraction": 0.0,
                          "river_plus_grid": 0.0,
                          "injected_fraction": 0.0})
        rim_report = next((r for r in discharge_reports
                           if r["pool_id"] == spring["pool_id"]), {})
        overlap = next((n for n in near_rim_overlap
                        if n["spring_index"] == s_idx), {})
        springs_out.append({
            "pool_id": spring["pool_id"],
            "name": spring["name"],
            "source_id": spring["source_id"],
            "index": s_idx,
            "rim_xz": spring["rim_xz"],
            "rim_elevation_m": round(spring["rim_elevation_m"], 3),
            "rim_cell_count": len(spring["rim_cells"]),
            "exported_fraction": round(float(exported[s_idx]), 6),
            "river_inflow_fraction": fractions["river_inflow_fraction"],
            "grid_exit_fraction": fractions["grid_exit_fraction"],
            "river_plus_grid_fraction": fractions["river_plus_grid"],
            "injected_fraction_conservation_note": (
                "river_inflow_fraction and grid_exit_fraction are computed "
                "from the conservative absorbing-boundary MFD propagation "
                "(river cells are sinks). Their sum equals the injected "
                "fraction within the stated tolerance."),
            "river_terminal_segment_ids": [seg["id"] for seg in reach_segs],
            "river_terminal_points": [
                {"xz": seg["downstream_endpoint_xz"],
                 "flow_fraction_at_terminal": seg["flow_fraction"],
                 "segment_id": seg["id"]} for seg in reach_segs],
            "river_terminal_points_note": (
                "flow_fraction_at_terminal is the per-cell MFD accumulation "
                "at the segment downstream endpoint, so these values are "
                "not additive across segments that share upstream flow. "
                "Use river_inflow_fraction for the fraction of this spring "
                "that enters the Firehole channel."),
            "rim_overflow": rim_report,
            "near_rim_imagery_overlap": overlap,
        })
    network = {
        "schema": onet.SCHEMA,
        "status": "fitted_not_validated",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "grid": _grid_header(grid),
        "frame": frame,
        "sources": [
            {"path": str(args.dem.resolve().relative_to(ROOT.parent)),
             "sha256": dem_sha,
             "role": "elevation_1m_dem"},
            {"path": str(args.pools.resolve().relative_to(ROOT.parent)),
             "sha256": pool_sha,
             "role": "pool_polygons"},
            {"path": str(args.imagery.resolve().relative_to(ROOT.parent)),
             "sha256": naip_sha,
             "role": "naip_imagery"},
            {"path": str(args.spring_discharges.resolve().relative_to(ROOT.parent)),
             "sha256": discharge_doc_sha,
             "role": "spring_discharges"},
        ],
        "method": {
            "routing": onet.METHOD_SOURCES["routing"],
            "depression_fill": onet.METHOD_SOURCES["depression_fill"],
            "rim_injection": {
                **onet.METHOD_SOURCES["rim_injection"],
                "convention": args.injection_convention,
            },
            "imagery_classifier": {
                "name": "luminance_saturation_threshold",
                "thresholds": wet_params,
                "status": wet_params.get("status", "authored"),
            },
            "thermal_mask_radius_m": 220.0,
            "thermal_mask_status": "authored",
            "flow_fraction_threshold": args.flow_threshold,
        },
        "springs": springs_out,
        "segments": segments,
        "rasters": raster_headers,
        "validation": {
            "orientation_agreement": agreement,
            "exported_fraction_sum": round(float(exported.sum()), 6),
            "injected_fraction_sum": round(sum(a for _, _, _, a in injections), 6),
            "segment_cleanup": cleanup_report,
            "segment_length_histogram_m": length_histogram,
            "junction_conservation": conservation,
            "river_vs_grid_fractions": exit_fractions,
            "river_vs_grid_tolerance": 1e-3,
            "river_vs_grid_tolerance_status": "authored",
            "near_rim_imagery_overlap_30m": near_rim_overlap,
            "rim_injection_convention": args.injection_convention,
            "rim_injection_discharges": discharge_reports,
            "per_segment_flow_note": (
                "segments[*].flow_fraction and springs[*].river_terminal_points"
                "[*].flow_fraction_at_terminal are per-cell MFD accumulations. "
                "They are not additive across overlapping D8 paths. For the "
                "fraction of each spring that enters the Firehole, read "
                "springs[*].river_inflow_fraction, computed conservatively "
                "with river cells as absorbing sinks."),
        },
    }
    out_json = args.out_dir / "outflow_network.json"
    write_json_atomic(out_json, network, indent=2)
    print(f"wrote {out_json} and {len(raster_headers)} rasters")
    print(f"segments: {len(segments)}; "
          f"orientation agreement {agreement['fraction_on_wet_pixels']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
