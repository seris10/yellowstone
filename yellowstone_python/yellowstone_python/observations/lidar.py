"""USGS point-cloud acquisition and canopy-height rasters."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import urllib.request
import urllib.parse

import numpy as np

from yellowstone_python.common.checks import positive, positive_int
from yellowstone_python.common.io import load_json, sha256_file, write_json_atomic

logger = logging.getLogger(__name__)
PROJECT = "WY_YellowstoneNP_2020_D20"
BLOCK = "WY_YellowstoneNP_3_2020"
TILE_BASE_URL = ("https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/"
                 f"LPC/Projects/{PROJECT}/{BLOCK}/LAZ/")
ACQUISITION = ["2020-09-29", "2020-10-09"]
REPORT_URL = ("https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/"
              f"{PROJECT}/{BLOCK}/reports/USGS_{BLOCK}_FINAL_LPC_Report.txt")
PROJECT_REPORT_URL = ("https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/"
                      f"{PROJECT}/USGS_{PROJECT}_Project_Report.pdf")
TILE_NAME = re.compile(r"USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ(\d{3})(\d{3})\.laz")


def tile_bounds(name: str) -> tuple[float, float, float, float]:
    """Return the 500 m tile footprint in its delivered UTM coordinates."""
    match = TILE_NAME.fullmatch(name)
    if not match:
        raise ValueError(f"unknown Midway point-cloud tile name: {name}")
    east = 500000 + int(match.group(1)) * 100
    north = 4900000 + int(match.group(2)) * 100
    return east, north, east + 500, north + 500


def intersecting_tiles(names, bounds) -> list[str]:
    """Select tiles with positive-area overlap with the requested bounding box."""
    x0, y0, x1, y1 = bounds
    if not all(math.isfinite(v) for v in bounds) or x1 <= x0 or y1 <= y0:
        raise ValueError("point-cloud bounds must have finite positive area")
    selected = []
    for name in names:
        a, b, c, d = tile_bounds(name)
        if a < x1 and c > x0 and b < y1 and d > y0:
            selected.append(name)
    return sorted(selected)


def catalog_tiles(bounds, cache: Path, *, refresh=False, timeout_s=30.0):
    """Cache the primary TNM catalog response and verify it before resuming acquisition."""
    from pyproj import Transformer
    timeout_s = positive("timeout_s", timeout_s)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    body_path = cache / "lpc_catalog_response.json"
    receipt_path = cache / "lpc_catalog.provenance.json"
    if not refresh and body_path.is_file() and receipt_path.is_file():
        receipt = load_json(receipt_path)
        if receipt["response_sha256"] != sha256_file(body_path):
            raise ValueError("cached USGS catalog checksum does not match its provenance")
        if list(bounds) != receipt["bounds_utm_m"]:
            raise ValueError("cached USGS catalog covers a different requested window")
        products = json.loads(body_path.read_bytes())
    else:
        converter = Transformer.from_crs(32612, 4326, always_xy=True)
        west, south = converter.transform(bounds[0], bounds[1])
        east, north = converter.transform(bounds[2], bounds[3])
        query = urllib.parse.urlencode({"datasets": "Lidar Point Cloud (LPC)",
            "bbox": f"{west},{south},{east},{north}", "max": 100, "outputFormat": "JSON"})
        url = "https://tnmaccess.nationalmap.gov/api/v1/products?" + query
        with urllib.request.urlopen(url, timeout=timeout_s) as response:
            body = response.read()
        products = json.loads(body)
        receipt = {"schema": "yellowstone.lidar_catalog.v1", "status": "measured",
            "query_url": url, "bounds_utm_m": list(bounds), "response_bytes": len(body),
            "response_sha256": hashlib.sha256(body).hexdigest(),
            "retrieved_utc": datetime.now(timezone.utc).isoformat()}
        temporary = body_path.with_suffix(".writing.json")
        temporary.write_bytes(body)
        os.replace(temporary, body_path)
        write_json_atomic(receipt_path, receipt)
    sizes = {}
    for item in products.get("items", []):
        url = item.get("downloadURL", "")
        name = url.rsplit("/", 1)[-1]
        if TILE_NAME.fullmatch(name):
            if url != TILE_BASE_URL + name:
                raise ValueError(f"catalog tile points to a different project or block: {name}")
            sizes[name] = positive_int("catalog_tile_bytes", item["sizeInBytes"])
    names = intersecting_tiles(sizes, bounds)
    expected = {f"USGS_LPC_WY_YellowstoneNP_2020_D20_12TWQ{(e - 500000) // 100:03d}{(n - 4900000) // 100:03d}.laz"
                for e in range(math.floor(bounds[0] / 500) * 500, math.ceil(bounds[2] / 500) * 500, 500)
                for n in range(math.floor(bounds[1] / 500) * 500, math.ceil(bounds[3] / 500) * 500, 500)}
    missing = expected - set(names)
    if missing:
        raise ValueError(f"USGS catalog is missing required overlapping tiles: {sorted(missing)}")
    return names, {name: sizes[name] for name in names}, receipt


def las_header(data: bytes) -> dict:
    """Read the point count and bounds from a LAS 1.4 public header."""
    if len(data) < 375 or data[:4] != b"LASF" or tuple(data[24:26]) != (1, 4):
        raise ValueError("point cloud must have a complete LAS 1.4 public header")
    xmax, xmin, ymax, ymin, zmax, zmin = struct.unpack_from("<6d", data, 179)
    count = struct.unpack_from("<Q", data, 247)[0]
    if count <= 0:
        raise ValueError("point cloud has no points")
    return {"las_version": "1.4", "point_format": data[104] & 63,
            "point_count": count, "bounds_utm_m": [xmin, ymin, xmax, ymax],
            "elevation_range_m": [zmin, zmax]}


def fetch_tile(name: str, cache: Path, *, timeout_s=300.0, expected_bytes=None) -> dict:
    """Download one tile with a resumable partial file and an immutable source receipt."""
    tile_bounds(name)
    timeout_s = positive("timeout_s", timeout_s)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / name
    receipt_path = cache / f"{name}.provenance.json"
    if target.exists():
        if not receipt_path.is_file():
            raise ValueError(f"existing point cloud has no source receipt: {target}")
        receipt = load_json(receipt_path)
        if receipt["sha256"] != sha256_file(target) or receipt["bytes"] != target.stat().st_size:
            raise ValueError(f"point-cloud checksum does not match its source receipt: {target}")
        if expected_bytes is not None and receipt["bytes"] != positive_int("catalog_tile_bytes", expected_bytes):
            raise ValueError(f"cached point-cloud byte count does not match the source catalog: {name}")
        return receipt
    partial = cache / f"{name}.part"
    url = TILE_BASE_URL + name
    headers_path = cache / f"{name}.http-headers.txt"
    result = subprocess.run(["curl", "-4", "--fail", "--show-error", "--silent", "--location",
        "--proto", "=https", "--proto-redir", "=https", "--continue-at", "-", "--retry", "3",
        "--connect-timeout", "8", "--max-time", str(timeout_s), "--dump-header", str(headers_path),
        "--output", str(partial), url], capture_output=True, text=True)
    if result.returncode:
        raise OSError(f"point-cloud transfer failed for {name}: {result.stderr.strip()}")
    response_headers = {}
    for line in headers_path.read_text().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            response_headers[key.lower()] = value.strip()
    total = expected_bytes
    if total is None and "content-range" in response_headers:
        total = int(response_headers["content-range"].rsplit("/", 1)[1])
    elif total is None and "content-length" in response_headers:
        total = int(response_headers["content-length"])
    if total is None or partial.stat().st_size != total:
        raise ValueError(f"downloaded byte count does not match the catalog or response: {name}")
    with partial.open("rb") as stream:
        header = las_header(stream.read(375))
    receipt = {"schema": "yellowstone.lidar_tile.v1", "status": "measured",
               "path": name, "url": url, "project": PROJECT, "block": BLOCK,
               "quality_level": "QL1", "acquisition_window": ACQUISITION,
               "project_report_url": PROJECT_REPORT_URL, "pointcloud_qc_report_url": REPORT_URL,
               "bytes": partial.stat().st_size,
               "sha256": sha256_file(partial), "last_modified": response_headers.get("last-modified"),
               "etag": response_headers.get("etag"), "transfer_client": "curl IPv4; TLS verified",
               "content_type": response_headers.get("content-type"),
               "retrieved_utc": datetime.now(timezone.utc).isoformat(), **header}
    os.replace(partial, target)
    write_json_atomic(receipt_path, receipt)
    logger.info("downloaded %s: %s bytes", name, receipt["bytes"])
    return receipt


def fetch_tiles(names, cache: Path, *, workers=4, timeout_s=300.0, expected_sizes=None) -> list[dict]:
    """Download the selected primary tiles and verify any existing cache entries."""
    workers = positive_int("workers", workers)
    if len(set(names)) != len(names):
        raise ValueError("point-cloud tile names must be unique")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda name: fetch_tile(name, cache, timeout_s=timeout_s,
            expected_bytes=(expected_sizes or {}).get(name)), names))


def rasterize_highest_first(surface, support, x, y, z, classification,
                            return_number, withheld, transform) -> dict:
    """Accumulate highest class 1/2 first returns without filling unsupported cells."""
    valid = ((return_number == 1) & np.isin(classification, [1, 2]) & ~withheld
             & np.isfinite(x) & np.isfinite(y) & np.isfinite(z))
    x, y, z = x[valid], y[valid], z[valid]
    columns = np.floor((x - transform.c) / transform.a).astype(np.int64)
    rows = np.floor((transform.f - y) / -transform.e).astype(np.int64)
    inside = ((rows >= 0) & (rows < surface.shape[0])
              & (columns >= 0) & (columns < surface.shape[1]))
    indexes = rows[inside] * surface.shape[1] + columns[inside]
    np.maximum.at(surface.ravel(), indexes, z[inside])
    np.add.at(support.ravel(), indexes, 1)
    return {"eligible_first_returns": int(valid.sum()),
            "first_returns_inside": int(inside.sum())}


def pit_fill(surface: np.ndarray, *, footprint=3) -> np.ndarray:
    """Close small canopy-surface pits while preserving every unsupported cell."""
    from scipy.ndimage import grey_closing
    footprint = positive_int("footprint", footprint)
    valid = np.isfinite(surface)
    work = np.where(valid, surface, -np.inf)
    closed = grey_closing(work, size=(footprint, footprint))
    return np.where(valid, np.maximum(work, closed), np.nan).astype(np.float32)


def build_canopy_height(tiles, cache: Path, dem_path: Path, out_dir: Path,
                        *, resolution_m=0.5, chunk_points=1000000) -> dict:
    """Subtract the matched NAVD88 DEM from georeferenced highest first-return elevations."""
    import laspy
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from pyproj import CRS, Transformer

    resolution_m = positive("resolution_m", resolution_m)
    chunk_points = positive_int("chunk_points", chunk_points)
    cache, dem_path, out_dir = Path(cache), Path(dem_path), Path(out_dir)
    dem_receipt = load_json(Path(f"{dem_path}.provenance.json"))
    if dem_receipt.get("vertical_datum") != "NAVD88" or PROJECT not in dem_receipt.get("dataset", ""):
        raise ValueError("canopy subtraction requires the matched project NAVD88 bare-earth DEM")
    if sha256_file(dem_path) != dem_receipt["sha256"]:
        raise ValueError("bare-earth DEM checksum does not match its provenance")
    with rasterio.open(dem_path) as source:
        width = round((source.bounds.right - source.bounds.left) / resolution_m)
        height = round((source.bounds.top - source.bounds.bottom) / resolution_m)
        transform = from_bounds(*source.bounds, width, height)
        ground = source.read(1, out_shape=(height, width), resampling=Resampling.bilinear,
                             masked=True).filled(np.nan).astype(np.float32)
        raster_crs = source.crs
        bounds = tuple(source.bounds)
    surface = np.full(ground.shape, -np.inf, dtype=np.float32)
    support = np.zeros(ground.shape, dtype=np.uint32)
    stats, source_receipts = [], []
    for name in tiles:
        path = cache / name
        receipt = load_json(cache / f"{name}.provenance.json")
        if sha256_file(path) != receipt["sha256"]:
            raise ValueError(f"point-cloud checksum mismatch: {name}")
        with laspy.open(path) as reader:
            delivered = reader.header.parse_crs()
            if delivered is None or not delivered.is_compound:
                raise ValueError(f"point-cloud vertical CRS is missing: {name}")
            vertical = delivered.sub_crs_list[1]
            if "NAVD88" not in vertical.name or any(a.unit_conversion_factor != 1 for a in vertical.axis_info):
                raise ValueError(f"point cloud requires NAVD88 elevations in meters: {name}")
            horizontal = delivered.to_2d()
            transformer = Transformer.from_crs(horizontal, CRS.from_user_input(raster_crs),
                                               always_xy=True, allow_ballpark=False)
            counts = {"all_returns": 0, "all_first_returns": 0,
                      "eligible_first_returns": 0, "first_returns_inside": 0}
            for points in reader.chunk_iterator(chunk_points):
                px, py = transformer.transform(np.asarray(points.x), np.asarray(points.y))
                counts["all_returns"] += len(points)
                counts["all_first_returns"] += int(np.sum(points.return_number == 1))
                added = rasterize_highest_first(surface, support, px, py, np.asarray(points.z),
                    np.asarray(points.classification), np.asarray(points.return_number),
                    np.asarray(points.withheld, dtype=bool), transform)
                for key, value in added.items():
                    counts[key] += value
            stats.append({"tile": name, **counts, "source_crs_wkt": delivered.to_wkt(),
                          "horizontal_operation": transformer.description,
                          "horizontal_accuracy_m": transformer.accuracy,
                          "ballpark_allowed": False, "vertical_shift_m": 0.0})
            logger.info("rasterized %s: %s eligible detail-window first returns", name,
                        counts["first_returns_inside"])
        source_receipts.append(receipt)
    surface[~np.isfinite(surface)] = np.nan
    canopy = pit_fill((surface - ground).astype(np.float32))
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {"canopy_height": "canopy_height.tif", "first_return_support": "first_return_support.tif"}
    for key, array in [("canopy_height", canopy), ("first_return_support", support)]:
        path = out_dir / paths[key]
        temporary = path.with_suffix(".writing.tif")
        with rasterio.open(temporary, "w", driver="GTiff", height=height, width=width,
                           count=1, dtype=array.dtype, crs=raster_crs, transform=transform,
                           nodata=np.nan if array.dtype.kind == "f" else 0,
                           compress="deflate", tiled=True) as raster:
            raster.write(array, 1)
        os.replace(temporary, path)
    finite = np.isfinite(canopy)
    acquisition_area = len(tiles) * 500.0 ** 2
    provenance = {"schema": "yellowstone.canopy_height.v1", "status": "measured",
                  "project": PROJECT, "block": BLOCK, "quality_level": "QL1",
                  "acquisition_window": ACQUISITION, "tile_count": len(tiles),
                  "tiles": source_receipts, "tile_point_statistics": stats,
                  "point_density_all_returns_per_m2": sum(s["all_returns"] for s in stats) / acquisition_area,
                  "point_density_first_returns_per_m2": sum(s["all_first_returns"] for s in stats) / acquisition_area,
                  "dem_sha256": dem_receipt["sha256"], "dem_source": dem_receipt,
                  "accuracy_scope": "project-level tested accuracy; site-specific canopy error unknown",
                  "value_class": "first-return surface height above matched ground; vegetation unclassified",
                  "producer_sha256": sha256_file(Path(__file__)),
                  "software_versions": {"laspy": laspy.__version__, "rasterio": rasterio.__version__,
                                         "numpy": np.__version__},
                  "resolution_m": resolution_m, "crs": str(raster_crs),
                  "bounds_utm_m": list(bounds), "extent_m": dem_receipt["local_extent_xz_m"],
                  "shape": [height, width], "valid_fraction": float(finite.mean()),
                  "missing_fraction": float((~finite).mean()), "height_units": "m",
                  "height_range_m": [float(canopy[finite].min()), float(canopy[finite].max())] if finite.any() else None,
                  "method": "highest class1/2 first return minus bilinear matched DEM; 3x3 canopy pit closing",
                  "unsupported_cells": "NoData preserved; no zero fill or extrapolation",
                  "artifacts": {key: {"path": value, "sha256": sha256_file(out_dir / value)}
                                for key, value in paths.items()}}
    write_json_atomic(out_dir / "canopy_height.provenance.json", provenance)
    return provenance
