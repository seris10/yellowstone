"""TreeMap imputed species and tree-size distributions."""
from __future__ import annotations

import csv
from functools import lru_cache
import hashlib
import io
import math
import os
from pathlib import Path
import tempfile
import urllib.request
import zipfile

from yellowstone_python.common.io import sha256_file
from yellowstone_python.observations.bundles import atomic_write_json, now_utc_iso

RASTER_URL = ("https://data.fs.usda.gov/geodata/rastergateway/treemap/2020/"
              "TreeMap2020_CONUS_TM_ID.zip")
PUBLICATION_URL = ("https://usfs-public.box.com/shared/static/"
                   "o117n4eh5swc7vpq9wg83eeqnh2xuula.zip")
DATASET_DOI = "https://doi.org/10.2737/RDS-2025-0031"
RASTER_MEMBER = "TreeMap2020_CONUS_TM_ID.tif"
TREE_MEMBER = "Data/TreeMap2020_CONUS_Tree_Table.csv"


class _RemoteArchive(io.RawIOBase):
    def __init__(self, url, timeout_s):
        self.url = url
        self.timeout_s = timeout_s
        self.position = 0
        response, data = self._range(0, 0)
        self.size = int(response.headers["Content-Range"].rsplit("/", 1)[1])
        if len(data) != 1:
            raise ValueError("archive range response has an invalid byte count")

    def _range(self, start, end):
        request = urllib.request.Request(
            self.url, headers={"Range": f"bytes={start}-{end}"})
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            if response.status != 206:
                raise ValueError("archive server must support byte ranges")
            expected = f"bytes {start}-{end}/"
            if not response.headers.get("Content-Range", "").startswith(expected):
                raise ValueError("archive server returned a different byte range")
            self.url = response.url
            data = response.read()
            return response, data

    def seekable(self):
        return True

    def seek(self, offset, whence=0):
        if whence not in (0, 1, 2):
            raise ValueError("unknown seek origin")
        position = (offset if whence == 0 else self.position + offset
                    if whence == 1 else self.size + offset)
        if position < 0:
            raise ValueError("archive seek precedes its first byte")
        self.position = position
        return position

    def tell(self):
        return self.position

    def read(self, size=-1):
        end = self.size - 1 if size < 0 else min(self.size - 1, self.position + size - 1)
        if end < self.position:
            return b""
        _, data = self._range(self.position, end)
        if len(data) != end - self.position + 1:
            raise ValueError("archive range response is incomplete")
        self.position = end + 1
        return data


def _number(row, name):
    value = row[name].strip()
    if value in ("", "NA"):
        return None
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"TreeMap {name} must be finite")
    return value


def read_tree_profiles(table_path, tm_ids):
    """Read joint imputed donor records and normalize their sample expansion weights."""
    wanted = {int(value) for value in tm_ids}
    profiles = {}
    with Path(table_path).open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            tm_id = int(row["TM_ID"])
            if tm_id not in wanted:
                continue
            plot_cn = row["PLT_CN"].strip()
            if not plot_cn or not plot_cn.isdigit():
                raise ValueError("TreeMap plot CN must be an exact digit string")
            profile = profiles.setdefault(str(tm_id), {"tm_id": tm_id,
                "plot_cn": plot_cn, "source_class": "imputed", "trees": []})
            if profile["plot_cn"] != plot_cn:
                raise ValueError("TreeMap ID maps to multiple plot CN values")
            status_code = int(row["STATUSCD"])
            if status_code not in (1, 2):
                raise ValueError("TreeMap tree status must be live or dead")
            diameter = _number(row, "DIA")
            height = _number(row, "HT")
            actual_height = _number(row, "ACTUALHT")
            crown_ratio = _number(row, "CR")
            weight = _number(row, "TPA_UNADJ")
            if weight is None or weight <= 0:
                raise ValueError("TreeMap sample expansion weight must be positive")
            if any(v is not None and v <= 0 for v in (diameter, height, actual_height)):
                raise ValueError("TreeMap tree dimensions must be positive")
            if crown_ratio is not None and not 0 <= crown_ratio <= 100:
                raise ValueError("TreeMap crown ratio must be within 0 to 100 percent")
            scientific_name = row["SCIENTIFIC_NAME"].strip()
            diameter_cm = diameter * 2.54 if diameter is not None else None
            dbh_species = scientific_name.split()[0] in {
                "Pinus", "Pseudotsuga", "Abies", "Picea", "Populus"}
            profile["trees"].append({
                "species_code": int(row["SPCD"]),
                "species_symbol": row["SPECIES_SYMBOL"].strip(),
                "scientific_name": scientific_name,
                "common_name": row["COMMON_NAME"].strip(),
                "diameter_cm": diameter_cm,
                "dbh_cm": diameter_cm if dbh_species else None,
                "diameter_reference": "dbh" if dbh_species else "fia_dbh_or_root_crown",
                "fia_reference_height_m": height * 0.3048 if height is not None else None,
                "fia_actual_height_m": actual_height * 0.3048
                    if actual_height is not None else None,
                "crown_ratio": crown_ratio / 100 if crown_ratio is not None else None,
                "tree_status": "live" if status_code == 1 else "dead",
                "sampling_weight": weight,
                "fia_subplot": int(row["SUBP"]),
                "fia_tree_record": int(row["TREE"]),
            })
    missing = wanted - {int(key) for key in profiles}
    if missing:
        raise ValueError(f"TreeMap donor profiles are missing for IDs: {sorted(missing)}")
    for profile in profiles.values():
        totals = {status: sum(t["sampling_weight"] for t in profile["trees"]
                             if t["tree_status"] == status) for status in ("live", "dead")}
        for tree in profile["trees"]:
            tree["sampling_weight"] /= totals[tree["tree_status"]]
    return profiles


def crop_tm_ids(bounds_utm, out_path):
    """Crop the public 30 m plot-ID raster through HTTP byte ranges."""
    import numpy as np
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import Window, from_bounds

    x0, y0, x1, y1 = map(float, bounds_utm)
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)) or x1 <= x0 or y1 <= y0:
        raise ValueError("TreeMap bounds must have finite positive area")
    remote = f"/vsizip//vsicurl/{RASTER_URL}/{RASTER_MEMBER}"
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".zip", GDAL_HTTP_TIMEOUT="120"):
        with rasterio.open(remote) as source:
            bounds = transform_bounds("EPSG:32612", source.crs, x0, y0, x1, y1,
                                      densify_pts=21)
            window = from_bounds(*bounds, source.transform)
            left, top = math.floor(window.col_off), math.floor(window.row_off)
            right = math.ceil(window.col_off + window.width)
            bottom = math.ceil(window.row_off + window.height)
            window = Window(left, top, right - left, bottom - top)
            values = source.read(1, window=window)
            if values.shape != (bottom - top, right - left):
                raise ValueError("TreeMap raster does not cover the requested bounds")
            transform = source.window_transform(window)
            profile = source.profile.copy()
            profile.update(width=values.shape[1], height=values.shape[0],
                           transform=transform, tiled=False, compress="deflate")
            profile.pop("blockxsize", None)
            profile.pop("blockysize", None)
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(out_path, "w", **profile) as target:
                target.write(values, 1)
            ids = set(np.unique(values).tolist()) - {source.nodata}
            return {"crs": str(source.crs), "transform": list(transform)[:6],
                    "nodata": source.nodata, "tm_ids": values.tolist(),
                    "valid_pixel_count": int(np.count_nonzero(values != source.nodata)),
                    "nodata_pixel_count": int(np.count_nonzero(values == source.nodata))}, ids


def fetch_tree_table(path, *, timeout_s=120.0):
    """Extract the official tree table and verify its archive CRC."""
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("TreeMap timeout must be positive")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(_RemoteArchive(PUBLICATION_URL, timeout_s)) as archive:
        info = archive.getinfo(TREE_MEMBER)
        content = archive.read(info)
        digest = hashlib.sha256(content).hexdigest()
        if path.exists() and sha256_file(path) != digest:
            raise ValueError("TreeMap cache differs from the official archive member")
        if not path.exists():
            temporary = None
            try:
                with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False,
                        prefix=f".{path.name}.", suffix=".tmp") as stream:
                    temporary = Path(stream.name)
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
                temporary = None
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return {"url": PUBLICATION_URL, "member": TREE_MEMBER,
                "sha256": digest, "bytes": info.file_size,
                "archive_crc32": f"{info.CRC:08x}"}


def fetch_treemap(bounds_utm, out_path, *, cache):
    """Write a site bundle of imputed tree-size and species references."""
    cache = Path(cache)
    raster_path = cache / "midway_tm_ids.tif"
    table_path = cache / "TreeMap2020_CONUS_Tree_Table.csv"
    grid, ids = crop_tm_ids(bounds_utm, raster_path)
    table_receipt = fetch_tree_table(table_path)
    profiles = read_tree_profiles(table_path, ids)
    x0, y0, x1, y1 = map(float, bounds_utm)
    transformer = _transformer("EPSG:32612", grid["crs"])
    transformer.transform((x0 + x1) / 2, (y0 + y1) / 2)
    operation = transformer.get_last_used_operation()
    payload = {
        "schema": "yellowstone.treemap_site.v1", "schema_version": 1,
        "status": "transferred", "product": "TreeMap2020_CONUS",
        "source_class": "imputed", "evidence_class": "transferred",
        "run_mode": "illustrative", "claim_status": "not_yet_accepted",
        "uncertainty": "unknown", "retrieved_utc": now_utc_iso(),
        "citation": "Zimmer et al. (2025), doi:10.2737/RDS-2025-0031",
        "use_constraints": "USDA permits use without additional permissions or fees; cite source",
        "requested_bounds_utm_m": [x0, y0, x1, y1],
        "world_center_utm_m": [(x0 + x1) / 2, (y0 + y1) / 2],
        "world_crs": "EPSG:32612", "pixel_size_m": 30,
        "world_to_grid_transform": {
            "description": operation.description, "pipeline": operation.definition,
            "stated_accuracy_m": operation.accuracy if operation.accuracy >= 0 else "unknown",
            "ballpark": any(op.has_ballpark_transformation for op in operation.operations),
        },
        "local_axes": {"x": "east", "z": "south"},
        "sampling_weight_definition": "TPA_UNADJ normalized within donor live/dead pool",
        "permitted_use": ["species_composition", "joint_tree_size_distribution"],
        "excluded_use": ["local_stem_count", "local_stem_density", "tree_position"],
        "nodata_interpretation": "No imputed donor assignment; local forest abundance unknown",
        "grid": grid, "profiles": profiles,
        "sources": [{"doi": DATASET_DOI, "url": RASTER_URL,
                     "member": RASTER_MEMBER, "subset_sha256": sha256_file(raster_path),
                     "subset_bytes": raster_path.stat().st_size}, table_receipt],
    }
    atomic_write_json(Path(out_path), payload)
    return payload


@lru_cache(maxsize=8)
def _transformer(source_crs, target_crs):
    from pyproj import Transformer
    return Transformer.from_crs(source_crs, target_crs, always_xy=True)


def profile_at_local(bundle, x_m, z_m):
    """Return the imputed donor profile at a local east/south world coordinate."""
    if not all(math.isfinite(v) for v in (x_m, z_m)):
        raise ValueError("TreeMap local coordinates must be finite")
    center_e, center_n = bundle["world_center_utm_m"]
    east, north = center_e + x_m, center_n - z_m
    x0, y0, x1, y1 = bundle["requested_bounds_utm_m"]
    if not (x0 <= east < x1 and y0 < north <= y1):
        return None
    grid = bundle["grid"]
    east, north = _transformer(bundle["world_crs"], grid["crs"]).transform(east, north)
    a, b, c, d, e, f = grid["transform"]
    determinant = a * e - b * d
    if determinant == 0:
        raise ValueError("TreeMap grid transform is singular")
    col = math.floor((e * (east - c) - b * (north - f)) / determinant)
    row = math.floor((-d * (east - c) + a * (north - f)) / determinant)
    values = grid["tm_ids"]
    if not 0 <= row < len(values) or not 0 <= col < len(values[row]):
        raise ValueError("TreeMap crop does not cover a requested coordinate")
    tm_id = values[row][col]
    if tm_id == grid["nodata"]:
        return None
    return bundle["profiles"][str(tm_id)]


def sample_tree_reference(profile, rng, *, status="live", species_symbol=None,
                          measured_height_m=None):
    """Sample one joint donor record from the requested species and live/dead pool."""
    if status not in ("live", "dead"):
        raise ValueError("TreeMap sampling status must be live or dead")
    if measured_height_m is not None and (
            not math.isfinite(measured_height_m) or measured_height_m <= 0):
        raise ValueError("TreeMap measured canopy height must be finite and positive")
    if profile is None:
        return None
    candidates = [t for t in profile["trees"] if t["tree_status"] == status
                  and (species_symbol is None or t["species_symbol"] == species_symbol)]
    height_mismatch = None
    if measured_height_m is not None:
        candidates = [t for t in candidates
                      if t.get("fia_reference_height_m") is not None
                      and math.isfinite(t["fia_reference_height_m"])
                      and t["fia_reference_height_m"] > 0]
        if candidates:
            height_mismatch = min(abs(t["fia_reference_height_m"] - measured_height_m)
                                  for t in candidates)
            candidates = [t for t in candidates
                          if abs(t["fia_reference_height_m"] - measured_height_m)
                          == height_mismatch]
    if not candidates:
        return None
    weights = [t["sampling_weight"] for t in candidates]
    if any(not math.isfinite(w) or w <= 0 for w in weights):
        raise ValueError("TreeMap sampling weights must be finite and positive")
    uniform = rng.random()
    if not math.isfinite(uniform) or not 0 <= uniform < 1:
        raise ValueError("TreeMap random generator must return a value in [0, 1)")
    target = uniform * sum(weights)
    cumulative = 0.0
    for tree, weight in zip(candidates, weights):
        cumulative += weight
        if target < cumulative:
            return {**tree, "tm_id": profile["tm_id"], "plot_cn": profile["plot_cn"],
                    "source_class": "imputed", "evidence_class": "transferred",
                    "measured_height_m": measured_height_m,
                    "height_mismatch_m": height_mismatch,
                    "matching_method": "nearest_fia_reference_height_cohort"
                        if measured_height_m is not None else "unconditioned_donor_pool",
                    "matching_rule_evidence_class": "authored",
                    "local_transfer_error": "unknown"}
    raise ValueError("TreeMap random generator must return a value in [0, 1)")
