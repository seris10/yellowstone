"""Pool outlines traced from airborne lidar and aerial imagery.

Traces the water outline from the 3DEP return void and cross-checks it against a NAIP water mask."""
from __future__ import annotations

import hashlib
import io
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

from yellowstone_python.common.coords import E0, N0

EPT_BASE = "https://usgs-lidar-public.s3.amazonaws.com/WY_YellowstoneNP_3_2020/"
NAIP_EXPORT = ("https://imagery.nationalmap.gov/arcgis/rest/services/"
               "USGSNAIPPlus/ImageServer/exportImage")
SURFACE_CLASSES = (2, 20)
CLASS_WATER = 9
CELL_M = 0.5
NAIP_PIXEL_M = 0.3
SHIFT_SEARCH_M = 6.0
SHIFT_STEP_M = 0.3
LIDAR_SIMPLIFY_M = 0.5
MIN_SIMPLIFY_M = 0.15
MIN_AGREEMENT_IOU = 0.8
Z_RANGE_M = (2100.0, 2400.0)


def _http_get(url: str, attempts: int = 5, timeout_s: float = 90.0) -> bytes:
    """Return the response body, retrying transient network errors."""
    last = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=timeout_s) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
            time.sleep(2.0 * (attempt + 1))
    raise OSError(f"transfer failed after {attempts} attempts: {url}: {last}")


def _cached_get(url: str, path: Path) -> bytes:
    """Return a cached body, downloading it first when the file is absent."""
    if path.is_file():
        return path.read_bytes()
    body = _http_get(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_bytes(body)
    temporary.replace(path)
    return body


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def local_bounds_to_utm(bounds_local: tuple[float, float, float, float]):
    """Convert (x0, z0, x1, z1) local meters to (east0, north0, east1, north1)."""
    x0, z0, x1, z1 = bounds_local
    return (E0 + x0, N0 - z1, E0 + x1, N0 - z0)


def _node_box(cube, depth: int, ix: int, iy: int, iz: int):
    n = 2 ** depth
    sx, sy, sz = ((cube[3] - cube[0]) / n, (cube[4] - cube[1]) / n,
                  (cube[5] - cube[2]) / n)
    return (cube[0] + ix * sx, cube[1] + iy * sy, cube[2] + iz * sz,
            cube[0] + (ix + 1) * sx, cube[1] + (iy + 1) * sy,
            cube[2] + (iz + 1) * sz)


def fetch_lidar_points(bounds_local, cache: Path, z_range=Z_RANGE_M):
    """Return lidar points in a local window and a receipt of the nodes read."""
    # Source is the USGS Entwine copy of block 3 of WY_YellowstoneNP_2020_D20, stored in web mercator.
    import laspy
    from pyproj import Transformer
    cache = Path(cache)
    ept_bytes = _cached_get(EPT_BASE + "ept.json", cache / "ept.json")
    ept = json.loads(ept_bytes)
    if ept["srs"]["horizontal"] != "3857" or ept["dataType"] != "laszip":
        raise ValueError("unexpected EPT coordinate system or data type")
    cube = ept["bounds"]
    e0, n0, e1, n1 = local_bounds_to_utm(bounds_local)
    forward = Transformer.from_crs(32612, 3857, always_xy=True)
    inverse = Transformer.from_crs(3857, 32612, always_xy=True)
    corners = [forward.transform(e, n) for e in (e0, e1) for n in (n0, n1)]
    box = (min(c[0] for c in corners) - 5.0, min(c[1] for c in corners) - 5.0,
           max(c[0] for c in corners) + 5.0, max(c[1] for c in corners) + 5.0)

    def touches(key: str) -> bool:
        d, ix, iy, iz = (int(v) for v in key.split("-"))
        b = _node_box(cube, d, ix, iy, iz)
        return (b[0] < box[2] and b[3] > box[0] and b[1] < box[3]
                and b[4] > box[1] and b[2] < z_range[1] and b[5] > z_range[0])

    nodes: dict[str, int] = {}
    pages = ["0-0-0-0"]
    page_receipts = []
    while pages:
        key = pages.pop()
        body = _cached_get(EPT_BASE + f"ept-hierarchy/{key}.json",
                           cache / "ept-hierarchy" / f"{key}.json")
        page_receipts.append({"page": key, "sha256": _sha256(body)})
        for node, count in json.loads(body).items():
            if not touches(node):
                continue
            if count == -1:
                pages.append(node)
            elif count > 0:
                nodes[node] = count
    columns: dict[str, list] = {name: [] for name in (
        "x", "z", "elevation", "classification", "return_number", "number_of_returns")}
    node_receipts = []
    for key in sorted(nodes):
        body = _cached_get(EPT_BASE + f"ept-data/{key}.laz",
                           cache / "ept-data" / f"{key}.laz")
        node_receipts.append({"node": key, "points": nodes[key],
                              "bytes": len(body), "sha256": _sha256(body)})
        las = laspy.read(io.BytesIO(body))
        east, north = inverse.transform(np.asarray(las.x), np.asarray(las.y))
        x, z = east - E0, N0 - north
        keep = ((x >= bounds_local[0]) & (x <= bounds_local[2])
                & (z >= bounds_local[1]) & (z <= bounds_local[3]))
        columns["x"].append(x[keep])
        columns["z"].append(z[keep])
        columns["elevation"].append(np.asarray(las.z)[keep])
        columns["classification"].append(np.asarray(las.classification)[keep])
        columns["return_number"].append(np.asarray(las.return_number)[keep])
        columns["number_of_returns"].append(np.asarray(las.number_of_returns)[keep])
    points = {k: (np.concatenate(v) if v else np.empty(0)) for k, v in columns.items()}
    receipt = {"endpoint": EPT_BASE, "ept_sha256": _sha256(ept_bytes),
               "ept_srs": "EPSG:3857", "project": "WY_YellowstoneNP_2020_D20",
               "block": "WY_YellowstoneNP_3_2020", "quality_level": "QL1",
               "acquisition_window": ["2020-09-29", "2020-10-09"],
               "window_local_m": list(bounds_local), "hierarchy_pages": page_receipts,
               "nodes": node_receipts, "point_count": int(points["x"].size)}
    return points, receipt


def fetch_naip(bounds_local, cache: Path, name: str):
    """Return a (rows, cols, 4) uint8 RGB+NIR crop and its receipt."""
    from PIL import Image
    e0, n0, e1, n1 = local_bounds_to_utm(bounds_local)
    cols = int(round((e1 - e0) / NAIP_PIXEL_M))
    rows = int(round((n1 - n0) / NAIP_PIXEL_M))
    query = urllib.parse.urlencode({
        "bbox": f"{e0},{n0},{e1},{n1}", "bboxSR": 32612, "imageSR": 32612,
        "size": f"{cols},{rows}", "format": "tiff", "f": "image",
        "bandIds": "0,1,2,3", "interpolation": "RSP_BilinearInterpolation"})
    url = f"{NAIP_EXPORT}?{query}"
    path = Path(cache) / "naip" / f"{name}.tif"
    body = _cached_get(url, path)
    array = np.asarray(Image.open(io.BytesIO(body)))
    if array.shape != (rows, cols, 4):
        raise ValueError(f"unexpected imagery shape {array.shape} for {name}")
    receipt = {"service": NAIP_EXPORT, "request_url": url, "bytes": len(body),
               "sha256": _sha256(body), "bounds_utm_m": [e0, n0, e1, n1],
               "pixel_m": NAIP_PIXEL_M, "bands": ["red", "green", "blue", "nir"]}
    return array, receipt


def _grid_edges(bounds_local, cell: float):
    x0, z0, x1, z1 = bounds_local
    nx, nz = int(math.ceil((x1 - x0) / cell)), int(math.ceil((z1 - z0) / cell))
    return nx, nz


def lidar_void_mask(points, bounds_local, cell: float = CELL_M):
    """Return a boolean grid, true where no ground return exists, plus the grid origin."""
    from scipy import ndimage
    nx, nz = _grid_edges(bounds_local, cell)
    x0, z0 = bounds_local[0], bounds_local[1]
    surface = np.isin(points["classification"], SURFACE_CLASSES)
    ix = np.floor((points["x"][surface] - x0) / cell).astype(int)
    iz = np.floor((points["z"][surface] - z0) / cell).astype(int)
    ok = (ix >= 0) & (ix < nx) & (iz >= 0) & (iz < nz)
    land = np.zeros((nz, nx), dtype=bool)
    land[iz[ok], ix[ok]] = True
    land = ndimage.binary_closing(land, structure=np.ones((3, 3)), iterations=1)
    return ~land, (x0, z0)


def _largest_containing(mask, seed_rc):
    """Return the connected true region containing the seed, or the nearest one."""
    from scipy import ndimage
    labels, count = ndimage.label(mask)
    if count == 0:
        raise ValueError("mask holds no region")
    label = labels[seed_rc]
    if label == 0:
        _, indices = ndimage.distance_transform_edt(labels == 0, return_indices=True)
        label = labels[indices[0][seed_rc], indices[1][seed_rc]]
    return labels == label


def mask_to_ring(mask, origin, cell: float, simplify_m: float = 0.25):
    """Trace the sub-cell outline of a boolean grid and return a shapely polygon in local meters."""
    from contourpy import contour_generator
    from scipy import ndimage
    from shapely.geometry import Polygon
    padded = np.pad(mask.astype(float), 2)
    field = ndimage.gaussian_filter(padded, sigma=1.0)
    nz, nx = field.shape
    xs = (np.arange(nx) - 2 + 0.5) * cell + origin[0]
    zs = (np.arange(nz) - 2 + 0.5) * cell + origin[1]
    lines = contour_generator(xs, zs, field).lines(0.5)
    best = None
    for line in lines:
        if len(line) < 4 or not np.allclose(line[0], line[-1]):
            continue
        poly = Polygon(line)
        if poly.is_valid and poly.area > 0 and (best is None or poly.area > best.area):
            best = poly
    if best is None:
        raise ValueError("no closed contour found")
    return best.simplify(simplify_m, preserve_topology=True)


def trace_lidar_outline(points, bounds_local, seed_xz, cell: float = CELL_M):
    """Return the lidar void polygon containing the seed point."""
    void, origin = lidar_void_mask(points, bounds_local, cell)
    seed = (int((seed_xz[1] - origin[1]) // cell), int((seed_xz[0] - origin[0]) // cell))
    region = _largest_containing(void, seed)
    from scipy import ndimage
    region = ndimage.binary_fill_holes(region)
    edge_touch = region[0].any() or region[-1].any() or region[:, 0].any() or region[:, -1].any()
    if edge_touch:
        raise ValueError("void region reaches the window edge; widen the window")
    traced = mask_to_ring(region, origin, cell, simplify_m=0.0)
    tolerance = min(LIDAR_SIMPLIFY_M, max(MIN_SIMPLIFY_M, 0.03 * math.sqrt(traced.area)))
    return (traced.simplify(tolerance, preserve_topology=True),
            {"void_cells": int(region.sum()), "cell_m": cell, "simplify_m": round(tolerance, 3)})


def ndwi(array):
    """Return (green - nir) / (green + nir) per pixel."""
    green = array[..., 1].astype(float)
    nir = array[..., 3].astype(float)
    return (green - nir) / np.maximum(green + nir, 1.0)


def otsu_threshold(values, bins: int = 256) -> float:
    """Return the Otsu threshold of a one-dimensional sample over its own range."""
    counts, edges = np.histogram(values, bins=bins, range=(float(values.min()), float(values.max())))
    centers = (edges[:-1] + edges[1:]) / 2.0
    weight = np.cumsum(counts)
    total = weight[-1]
    mean = np.cumsum(counts * centers)
    between = (mean[-1] * weight - mean * total) ** 2 / np.maximum(weight * (total - weight), 1)
    return float(centers[int(np.argmax(between))])


def naip_polygon(array, bounds_local, seed_xz):
    """Trace the imagery water polygon containing the seed point, in local meters."""
    # Water is the normalized green and near-infrared difference above the Otsu threshold of the window.
    from scipy import ndimage
    index = ndwi(array)
    threshold = otsu_threshold(index.ravel())
    mask = ndimage.binary_opening(index > threshold, structure=np.ones((3, 3)))
    rows, cols = mask.shape
    x0, z0, x1, z1 = bounds_local
    seed = (int((seed_xz[1] - z0) / (z1 - z0) * rows), int((seed_xz[0] - x0) / (x1 - x0) * cols))
    region = ndimage.binary_fill_holes(_largest_containing(mask, seed))
    return (mask_to_ring(region, (x0, z0), NAIP_PIXEL_M, simplify_m=0.3),
            {"ndwi_threshold": round(threshold, 3), "water_pixels": int(region.sum())})


def ring_difference(a, b):
    """Return intersection over union and boundary distances between two polygons in meters."""
    inter = a.intersection(b).area
    union = a.union(b).area
    ab = [a.exterior.interpolate(t, normalized=True).distance(b.exterior)
          for t in np.linspace(0, 1, 400, endpoint=False)]
    ba = [b.exterior.interpolate(t, normalized=True).distance(a.exterior)
          for t in np.linspace(0, 1, 400, endpoint=False)]
    both = np.asarray(ab + ba)
    return {"iou": round(inter / union, 4) if union > 0 else 0.0,
            "mean_boundary_distance_m": round(float(both.mean()), 3),
            "p95_boundary_distance_m": round(float(np.percentile(both, 95)), 3),
            "hausdorff_m": round(float(both.max()), 3)}


def best_shift(reference, candidate, search_m: float = SHIFT_SEARCH_M, step_m: float = SHIFT_STEP_M):
    """Return the (dx, dz) translation of the candidate that maximizes overlap with the reference."""
    from shapely import affinity
    best = (0.0, 0.0, -1.0)
    steps = np.arange(-search_m, search_m + 1e-9, step_m)
    for dx in steps:
        for dz in steps:
            moved = affinity.translate(candidate, dx, dz)
            union = reference.union(moved).area
            score = reference.intersection(moved).area / union if union else 0.0
            if score > best[2]:
                best = (float(dx), float(dz), float(score))
    return {"dx_m": round(best[0], 2), "dz_m": round(best[1], 2), "iou": round(best[2], 4)}


def ring_points(poly, decimals: int = 3):
    """Return the exterior vertices without the repeated closing vertex, as [x, z] pairs."""
    coords = list(poly.exterior.coords)[:-1]
    return [[round(float(x), decimals), round(float(z), decimals)] for x, z in coords]


def lidar_context(points, poly):
    """Return class counts inside the polygon and the shore elevation just outside it."""
    import shapely
    inside = shapely.contains_xy(poly, points["x"], points["z"])
    band = shapely.contains_xy(poly.buffer(2.0), points["x"], points["z"]) & ~inside
    area = poly.area
    classes, counts = np.unique(points["classification"][inside], return_counts=True)
    shore = band & np.isin(points["classification"], SURFACE_CLASSES)
    surface = points["elevation"][shore]
    stats = {"returns_per_m2_inside": round(float(inside.sum() / area), 3),
             "returns_per_m2_shore_band": round(float(band.sum() / max(poly.buffer(2.0).area - area, 1e-9)), 3),
             "classes_inside": {str(int(c)): int(n) for c, n in zip(classes, counts)}}
    if surface.size:
        stats["shore_elevation_navd88_m"] = {
            "median": round(float(np.median(surface)), 3),
            "p05": round(float(np.percentile(surface, 5)), 3),
            "p95": round(float(np.percentile(surface, 95)), 3),
            "count": int(surface.size)}
    return stats


def trace_pool(name: str, source_id: int, prior_ring, center_xz, cache: Path, margin_m: float = 45.0):
    """Return the traced record for one pool: lidar outline, imagery cross-check, and prior comparison."""
    from shapely.geometry import Polygon
    prior = Polygon(prior_ring)
    x0, z0, x1, z1 = prior.bounds
    bounds = (math.floor(x0 - margin_m), math.floor(z0 - margin_m),
              math.ceil(x1 + margin_m), math.ceil(z1 + margin_m))
    points, lidar_receipt = fetch_lidar_points(bounds, cache)
    lidar_poly, void_info = trace_lidar_outline(points, bounds, tuple(center_xz))
    naip, naip_receipt = fetch_naip(bounds, cache, f"pool_{source_id}")
    imagery_poly, imagery_info = naip_polygon(naip, bounds, tuple(center_xz))
    qa = {"lidar_vs_prior_polygon": ring_difference(lidar_poly, prior),
          "lidar_vs_imagery": ring_difference(lidar_poly, imagery_poly),
          "imagery_vs_prior_polygon": ring_difference(imagery_poly, prior),
          "imagery_shift_to_lidar": best_shift(lidar_poly, imagery_poly),
          "imagery": imagery_info,
          "imagery_area_m2": round(imagery_poly.area, 1),
          "prior_area_m2": round(prior.area, 1),
          "lidar_context": lidar_context(points, lidar_poly), **void_info}
    shift = qa["imagery_shift_to_lidar"]
    at_edge = max(abs(shift["dx_m"]), abs(shift["dz_m"])) >= SHIFT_SEARCH_M - 1e-6
    adopted = shift["iou"] >= MIN_AGREEMENT_IOU and not at_edge
    reason = (f"registered imagery overlap {shift['iou']} meets {MIN_AGREEMENT_IOU}" if adopted else
              "imagery cross-check below threshold or shift at search limit; "
              "steam or wet surfaces make the return void unreliable")
    return {"source_id": int(source_id), "name": name,
            "adopted": bool(adopted), "adoption_reason": reason,
            "outline_basis": "lidar_return_void",
            "ring": ring_points(lidar_poly),
            "area_m2": round(lidar_poly.area, 1),
            "perimeter_m": round(lidar_poly.length, 2),
            "centroid_xz": [round(c, 3) for c in lidar_poly.centroid.coords[0]],
            "window_local_m": list(bounds), "qa": qa,
            "lidar_receipt": lidar_receipt, "imagery_receipt": naip_receipt}, {
        "lidar": lidar_poly, "imagery": imagery_poly, "prior": prior,
        "points": points, "naip": naip, "bounds": bounds}
