"""Paged elevation compiler producing source pages and a quadtree catalog.

Heights are meters above the declared vertical origin; NoData is rejected."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import os
import shutil
import tempfile
import numpy as np
from .contracts import identifier, finite
from .feature_pages import attach_feature_pages

SCHEMA = "yellowstone.terrain_tiles.v1"

def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")

def triangle_sample(grid, u, v):
    n = grid.shape[0]
    ix = np.clip(np.floor(u).astype(np.int64), 0, n-2)
    iz = np.clip(np.floor(v).astype(np.int64), 0, n-2)
    fx, fz = u-ix, v-iz
    a, b, c, d = grid[iz, ix], grid[iz, ix+1], grid[iz+1, ix], grid[iz+1, ix+1]
    return np.where(fx+fz <= 1, a+fx*(b-a)+fz*(c-a),
                    d+(1-fx)*(c-d)+(1-fz)*(b-d))

def geometric_error(source, coarse):
    """Maximum deviation at original vertices under the same b-c triangulation."""
    scale = (source.shape[0]-1)/(coarse.shape[0]-1)
    maximum = 0.
    u = np.arange(source.shape[1], dtype=np.float64)/scale
    for row in range(source.shape[0]):
        approximation = triangle_sample(coarse, u, np.full(u.shape, row/scale))
        maximum = max(maximum, float(np.max(np.abs(approximation-source[row]))))
    return maximum

def build_pack(values, output: Path, *, pack_id="midway", cell_m=4.,
               origin_x_m=-2048., origin_z_m=-2048., mesh_cells=32, root_cells=1024,
               easting_m=512952.5950985841, northing_m=4930199.044097667,
               vertical_origin_m=2200., provenance=None, append=False, exclude=()):
    identifier(pack_id)
    if any(c in pack_id for c in "/:"):
        raise ValueError("pack_id must be a simple path-safe identifier")
    for value, name in [(cell_m, "cell_m"), (origin_x_m, "origin_x_m"),
                        (origin_z_m, "origin_z_m"), (easting_m, "easting_m"),
                        (northing_m, "northing_m"), (vertical_origin_m, "vertical_origin_m")]:
        finite(value, name)
    if cell_m <= 0 or not 4 <= mesh_cells <= 128:
        raise ValueError("positive spacing and 4..128 cells per mesh required")
    if root_cells < mesh_cells or root_cells % mesh_cells:
        raise ValueError("root_cells must be a multiple of mesh_cells")
    ratio = root_cells // mesh_cells
    if ratio & (ratio - 1):
        raise ValueError("root_cells/mesh_cells must be a power of two")
    if values.ndim != 2 or (values.shape[0]-1)%root_cells or (values.shape[1]-1)%root_cells:
        raise ValueError("input cell dimensions must be whole multiples of root_cells")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    catalog_path = output/"catalog.json"
    existing = json.loads(catalog_path.read_text()) if append and catalog_path.exists() else None
    if catalog_path.exists() and not append:
        raise FileExistsError("output catalog exists; use a new directory or explicit --append")
    if (output/pack_id).exists():
        raise FileExistsError("immutable pack id already exists")
    frame = {"crs": "EPSG:32612", "easting_m": easting_m, "northing_m": northing_m,
             "vertical_origin_m": vertical_origin_m, "axis_rule": "+x east,+z south,+y up"}
    if existing and (existing["frame"] != frame or existing["schema"] != SCHEMA):
        raise ValueError("packs must share an explicit coordinate frame and schema")
    max_lod = int(math.log2(ratio))
    roots = []
    # Stage immutable pages first; publishing catalog.json is the commit point.
    staging = Path(tempfile.mkdtemp(prefix=".terrain-stage-", dir=output))
    try:
        def tile(lod, tx, tz):
            stride = 1 << lod
            count = mesh_cells * stride
            x, z = tx*count, tz*count
            source = np.asarray(values[z:z+count+1, x:x+count+1], dtype=np.float64)
            if not np.all(np.isfinite(source)):
                raise ValueError(f"NoData/nonfinite heights in root/tile {lod}/{tx}/{tz}")
            coarse = np.asarray(source[::stride, ::stride], dtype="<f4")
            prefix = f"{pack_id}/{lod}/{tx}_{tz}"
            raw = coarse.tobytes(order="C")
            path = staging/(prefix+".f32")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            descriptor = {"key": f"{pack_id}:{lod}:{tx}:{tz}", "page": prefix+".json",
                "lod": lod, "origin_x_m": origin_x_m+x*cell_m, "origin_z_m": origin_z_m+z*cell_m,
                "size_m": count*cell_m, "min_y_m": float(source.min()), "max_y_m": float(source.max()),
                "error_m": geometric_error(source, coarse.astype(np.float64)), "mesh_cells": mesh_cells}
            children = [tile(lod-1, tx*2+dx, tz*2+dz) for dz in range(2) for dx in range(2)] if lod else []
            page = {"schema": SCHEMA, "tile": descriptor, "children": children,
                    "heights": {"path": prefix+".f32", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                                "dtype": "<f4", "shape": list(coarse.shape)},
                    "quality": (provenance or {}).get("quality", "derived_source_not_field_validated")}
            _write_json(staging/(prefix+".json"), page)
            return descriptor
        root_m = root_cells*cell_m
        excluded = [tuple(float(v) for v in rect) for rect in exclude]
        for tz in range((values.shape[0]-1)//root_cells):
            for tx in range((values.shape[1]-1)//root_cells):
                x0, z0 = origin_x_m+tx*root_m, origin_z_m+tz*root_m
                if any(max(x0, e[0]) < min(x0+root_m, e[2]) and max(z0, e[1]) < min(z0+root_m, e[3])
                       for e in excluded):
                    continue
                roots.append(tile(max_lod, tx, tz))
        if not roots:
            raise ValueError("every root is excluded; nothing to pack")
        for a in roots:
            for b in (existing or {}).get("roots", []):
                if (max(a["origin_x_m"], b["origin_x_m"]) < min(a["origin_x_m"]+a["size_m"], b["origin_x_m"]+b["size_m"])
                    and max(a["origin_z_m"], b["origin_z_m"]) < min(a["origin_z_m"]+a["size_m"], b["origin_z_m"]+b["size_m"])):
                    raise ValueError("root coverage overlaps; compose core/master heights before packing")
        (staging/pack_id).rename(output/pack_id)
        catalog = {"schema": SCHEMA, "dataset_revision": "", "frame": frame,
                   "roots": (existing or {}).get("roots", [])+roots,
                   "sources": (existing or {}).get("sources", [])+[
                       {"pack_id": pack_id, "excluded_rects_m": [list(e) for e in excluded], **(provenance or {})}],
                   "edge_policy": "dyadic_shared_samples_visual_skirts_no_collision_skirts"}
        catalog["dataset_revision"] = hashlib.sha256(json.dumps(catalog,sort_keys=True).encode()).hexdigest()
        temporary = output/"catalog.pending.json"
        _write_json(temporary, catalog)
        os.replace(temporary, catalog_path)
        return catalog
    finally:
        shutil.rmtree(staging, ignore_errors=True)

CORE_SCHEMA = "yellowstone.core_terrain.v1"

def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()

def _read_layer(core_dir: Path, meta: dict, name: str, shape):
    layer = meta["layers"][name]
    path = core_dir/layer["path"]
    if _sha256_file(path) != layer["sha256"]:
        raise ValueError(f"{name} checksum differs from core_terrain.json")
    if layer["dtype"] != "<f4" or tuple(layer["shape"]) != shape:
        raise ValueError(f"{name} dtype or shape differs from the core grid")
    values = np.fromfile(path, dtype="<f4")
    if values.size != shape[0]*shape[1]:
        raise ValueError(f"{name} byte length differs from the core grid")
    values = values.reshape(shape)
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{name} contains NoData")
    return values

def load_core(core_dir) -> dict:
    """Load the 1 m core heights (heightfield plus microrelief) with checksum validation."""
    core_dir = Path(core_dir)
    meta = json.loads((core_dir/"core_terrain.json").read_text())
    if meta.get("schema") != CORE_SCHEMA:
        raise ValueError("core_terrain.json schema is not supported")
    grid = meta["grid"]
    cell, nx, nz = float(grid["cell_m"]), int(grid["nx"]), int(grid["nz"])
    x_min, z_min = float(grid["x_min_m"]), float(grid["z_min_m"])
    if (abs(x_min+(nx-1)*cell-float(grid["x_max_m"])) > 1e-9
            or abs(z_min+(nz-1)*cell-float(grid["z_max_m"])) > 1e-9):
        raise ValueError("core grid bounds disagree with nx, nz and cell_m")
    shape = (nz, nx)
    base = _read_layer(core_dir, meta, "core_heightfield_m", shape)
    micro = _read_layer(core_dir, meta, "core_microrelief_m", shape)
    # Sum both layers in float64, then store float32.
    heights = (base.astype(np.float64)+micro.astype(np.float64)).astype("<f4")
    easting, northing = meta["frame"]["origin_utm_m"]
    return {"heights": heights, "cell_m": cell, "x_min_m": x_min, "z_min_m": z_min,
            "x_max_m": x_min+(nx-1)*cell, "z_max_m": z_min+(nz-1)*cell,
            "vertical_origin_m": float(meta["vertical_origin_m"]),
            "easting_m": float(easting), "northing_m": float(northing),
            "sources": {name: _sha256_file(core_dir/name) for name in
                        ("core_terrain.json", "core_heightfield.f32", "core_microrelief.f32", "stitch.json")}}

def core_window(core: dict, *, root_m: float, origin_x_m: float, origin_z_m: float, extent_m: float):
    """Return the smallest square block of whole master roots covering the core footprint."""
    x0 = origin_x_m+math.floor((core["x_min_m"]-origin_x_m)/root_m)*root_m
    z0 = origin_z_m+math.floor((core["z_min_m"]-origin_z_m)/root_m)*root_m
    span = max(core["x_max_m"]-x0, core["z_max_m"]-z0)
    roots = 1
    while roots*root_m < span:
        roots *= 2
    size = roots*root_m
    if x0+size > origin_x_m+extent_m or z0+size > origin_z_m+extent_m:
        raise ValueError("core window leaves the master extent")
    return x0, z0, size

def _on_lattice(value: float, origin: float, step: float) -> bool:
    return abs((value-origin)/step-round((value-origin)/step)) <= 1e-9

def compose_window(master, core: dict, *, window, master_origin_x_m=-2048., master_origin_z_m=-2048.,
                   master_cell_m=4.) -> np.ndarray:
    """Return fine-lattice window heights: core inside its footprint, master b-c samples elsewhere."""
    x0, z0, size = window
    cell = core["cell_m"]
    cells = size/cell
    if cells != int(cells):
        raise ValueError("window size must be a whole number of core cells")
    cells = int(cells)
    if not (_on_lattice(core["x_min_m"], master_origin_x_m, master_cell_m)
            and _on_lattice(core["x_max_m"], master_origin_x_m, master_cell_m)
            and _on_lattice(core["z_min_m"], master_origin_z_m, master_cell_m)
            and _on_lattice(core["z_max_m"], master_origin_z_m, master_cell_m)):
        raise ValueError("core bounds must lie on the master lattice")
    if abs(master_cell_m/cell-round(master_cell_m/cell)) > 1e-9:
        raise ValueError("master spacing must be a whole multiple of the core spacing")
    i0, j0 = (core["x_min_m"]-x0)/cell, (core["z_min_m"]-z0)/cell
    rows, cols = core["heights"].shape
    if i0 != int(i0) or j0 != int(j0) or i0 < 0 or j0 < 0 or i0+cols > cells+1 or j0+rows > cells+1:
        raise ValueError("core footprint must lie on the window lattice")
    u = (x0+np.arange(cells+1)*cell-master_origin_x_m)/master_cell_m
    v = (z0+np.arange(cells+1)*cell-master_origin_z_m)/master_cell_m
    if u[0] < 0 or v[0] < 0 or u[-1] > master.shape[1]-1 or v[-1] > master.shape[0]-1:
        raise ValueError("window leaves the master raster")
    grid = np.asarray(master, dtype=np.float64)
    values = triangle_sample(grid, u[None, :], v[:, None]).astype("<f4")
    i0, j0 = int(i0), int(j0)
    values[j0:j0+rows, i0:i0+cols] = core["heights"]
    if not np.all(np.isfinite(values)):
        raise ValueError("composed window contains NoData")
    return values

def _overlap(a, b) -> bool:
    return (max(a["origin_x_m"], b["origin_x_m"]) < min(a["origin_x_m"]+a["size_m"], b["origin_x_m"]+b["size_m"])
            and max(a["origin_z_m"], b["origin_z_m"]) < min(a["origin_z_m"]+a["size_m"], b["origin_z_m"]+b["size_m"]))

def coverage_report(catalog: dict, extent) -> dict:
    """Return root area, overlapping pairs and uncovered area against an (x0, z0, x1, z1) extent."""
    roots = catalog["roots"]
    area = sum(r["size_m"]**2 for r in roots)
    overlaps = sum(_overlap(a, b) for index, a in enumerate(roots) for b in roots[index+1:])
    return {"root_area_m2": area, "overlapping_pairs": overlaps,
            "uncovered_area_m2": (extent[2]-extent[0])*(extent[3]-extent[1])-area}

def refresh_revision(catalog: dict) -> dict:
    """Recompute the dataset revision from the catalog content."""
    catalog["dataset_revision"] = ""
    catalog["dataset_revision"] = hashlib.sha256(json.dumps(catalog, sort_keys=True).encode()).hexdigest()
    return catalog

def build_composed_pack(master, core_dir, output: Path, *, world_path=None, master_name="terrain.f32",
                        master_sha256="", pack_id="midway", core_pack_id="core", mesh_cells=32,
                        master_root_cells=128, origin_x_m=-2048., origin_z_m=-2048., master_cell_m=4.) -> dict:
    """Pack the master raster and the 1 m core as one non-overlapping source catalog."""
    output = Path(output)
    if output.exists():
        raise FileExistsError("composed pack directory exists; choose a new directory")
    core = load_core(core_dir)
    extent_m = (master.shape[1]-1)*master_cell_m
    window = core_window(core, root_m=master_root_cells*master_cell_m, origin_x_m=origin_x_m,
                         origin_z_m=origin_z_m, extent_m=extent_m)
    composed = compose_window(master, core, window=window, master_origin_x_m=origin_x_m,
                              master_origin_z_m=origin_z_m, master_cell_m=master_cell_m)
    x0, z0, size = window
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".compose-stage-", dir=output.parent))
    try:
        pack = staging/"pack"
        frame = dict(easting_m=core["easting_m"], northing_m=core["northing_m"],
                     vertical_origin_m=core["vertical_origin_m"])
        quality = "derived_source_not_field_validated"
        build_pack(master, pack, pack_id=pack_id, cell_m=master_cell_m, origin_x_m=origin_x_m,
                   origin_z_m=origin_z_m, mesh_cells=mesh_cells, root_cells=master_root_cells,
                   exclude=[(x0, z0, x0+size, z0+size)], **frame,
                   provenance={"quality": quality, "source_name": master_name, "source_sha256": master_sha256,
                               "height_units": "m relative to vertical origin",
                               "owns": "master raster outside the core window"})
        catalog = build_pack(composed, pack, pack_id=core_pack_id, cell_m=core["cell_m"], origin_x_m=x0,
                             origin_z_m=z0, mesh_cells=mesh_cells, root_cells=int(size/core["cell_m"]),
                             append=True, **frame,
                             provenance={"quality": quality, "core_sources": core["sources"],
                                         "composition": "core heightfield plus microrelief inside the core footprint, "
                                                        "master b-c triangle samples elsewhere in the window",
                                         "core_footprint_m": [core["x_min_m"], core["z_min_m"],
                                                              core["x_max_m"], core["z_max_m"]],
                                         "height_units": "m relative to vertical origin",
                                         "owns": "core window"})
        report = coverage_report(catalog, (origin_x_m, origin_z_m, origin_x_m+extent_m, origin_z_m+extent_m))
        if report["overlapping_pairs"] or report["uncovered_area_m2"]:
            raise ValueError(f"composed roots must tile the extent exactly: {report}")
        if world_path is not None:
            attach_feature_pages(Path(world_path), pack, catalog, origin_x_m=origin_x_m,
                                 origin_z_m=origin_z_m, extent_m=extent_m)
        os.replace(pack, output)
        return catalog
    finally:
        shutil.rmtree(staging, ignore_errors=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, help="little-endian float32 raster; required unless --demo")
    p.add_argument("--nx", type=int, default=1025)
    p.add_argument("--nz", type=int, default=1025)
    p.add_argument("--cell", type=float, default=4.)
    p.add_argument("--origin-x", type=float, default=-2048.)
    p.add_argument("--origin-z", type=float, default=-2048.)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--pack-id", default="midway")
    p.add_argument("--mesh-cells", type=int, default=32)
    p.add_argument("--root-cells", type=int, default=1024)
    p.add_argument("--append", action="store_true")
    p.add_argument("--demo", action="store_true")
    p.add_argument("--core-dir", type=Path, help="compose the 1 m core directory with --source")
    p.add_argument("--world", type=Path, help="world.json for shoreline, pool-cut and route pages")
    args = p.parse_args()
    if args.core_dir is not None:
        if args.source is None or args.source.stat().st_size != args.nx*args.nz*4:
            p.error("--core-dir requires --source with byte length nx*nz*4")
        master = np.memmap(args.source, mode="r", dtype="<f4", shape=(args.nz, args.nx))
        catalog = build_composed_pack(master, args.core_dir, args.out, world_path=args.world,
                                      master_name=args.source.name, master_sha256=_sha256_file(args.source),
                                      pack_id=args.pack_id, mesh_cells=args.mesh_cells, origin_x_m=args.origin_x,
                                      origin_z_m=args.origin_z, master_cell_m=args.cell)
        print(json.dumps({"catalog": str(args.out/"catalog.json"), "roots": len(catalog["roots"]),
                          "dataset_revision": catalog["dataset_revision"]}))
        return
    if args.demo:
        x,z = np.meshgrid(np.linspace(-512,512,257),np.linspace(-512,512,257))
        heights = (65*np.exp(-((x-60)/75)**2)*(1-.92*np.exp(-((z+130)/65)**2))
                   +8*np.sin(x/85)*np.cos(z/160)+.012*z).astype("<f4")
        provenance = {"quality":"synthetic_fixture_not_yellowstone", "generator":"analytic_ridge_and_gap_v1"}
        kw = dict(pack_id="synthetic", origin_x_m=-512., origin_z_m=-512., root_cells=256)
    else:
        if args.source is None or args.source.stat().st_size != args.nx*args.nz*4:
            p.error("source byte length must equal nx*nz*4")
        heights = np.memmap(args.source, mode="r", dtype="<f4", shape=(args.nz,args.nx))
        hasher = hashlib.sha256()
        with args.source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024*1024),b""):
                hasher.update(block)
        provenance = {"quality":"derived_source_not_field_validated", "source_sha256":hasher.hexdigest(),
                      "source_name":args.source.name, "height_units":"m relative to vertical origin"}
        kw = dict(pack_id=args.pack_id, origin_x_m=args.origin_x, origin_z_m=args.origin_z, root_cells=args.root_cells)
    catalog = build_pack(heights,args.out,cell_m=args.cell,mesh_cells=args.mesh_cells,
                         append=args.append,provenance=provenance,**kw)
    print(json.dumps({"catalog":str(args.out/"catalog.json"),"roots":len(catalog["roots"]),
                      "dataset_revision":catalog["dataset_revision"]}))

if __name__ == "__main__":
    main()
