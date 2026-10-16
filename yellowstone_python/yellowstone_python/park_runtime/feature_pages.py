"""Bounded shoreline, pool-cut and route feature pages keyed by square cells.

Pages carry source geometry only; meshes are built by the streaming workers."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from .contracts import finite

SCHEMA = "yellowstone.terrain_features.v1"
MAX_PAGE_BYTES = 1 << 20


def _canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()


def _number(value, name):
    return finite(value, name)


def pool_features(world: dict) -> list[dict]:
    """Return the thermal pools that the open-water cut subtracts, with ring and water level."""
    result = []
    for pool in world.get("pools", []):
        if not pool.get("thermal"):
            continue
        ring = [[_number(p[0], "ring x"), _number(p[1], "ring z")] for p in pool.get("ring", [])]
        if len(ring) < 3 or any(len(p) != 2 for p in pool["ring"]):
            raise ValueError(f"pool {pool.get('id')} needs a ring of at least three coordinate pairs")
        center = pool.get("center")
        if not isinstance(center, list) or len(center) < 2:
            raise ValueError(f"pool {pool.get('id')} has no water elevation")
        xs, zs = [p[0] for p in ring], [p[1] for p in ring]
        result.append({"id": str(pool["id"]), "name": str(pool.get("name", "")), "source_id": pool.get("source_id"),
                       "water_y_m": _number(center[1], "water elevation"), "ring": ring,
                       "bounds_m": [min(xs), min(zs), max(xs), max(zs)]})
    return result


def _segment_hits(ax, az, bx, bz, rect) -> bool:
    low, high = 0.0, 1.0
    for origin, delta, lo, hi in ((ax, bx-ax, rect[0], rect[2]), (az, bz-az, rect[1], rect[3])):
        if abs(delta) < 1e-12:
            if origin < lo or origin > hi:
                return False
            continue
        t0, t1 = (lo-origin)/delta, (hi-origin)/delta
        if t0 > t1:
            t0, t1 = t1, t0
        low, high = max(low, t0), min(high, t1)
        if low > high:
            return False
    return True


def route_features(world: dict) -> list[dict]:
    """Return route polylines with identities and a hash of the full source geometry."""
    result = []
    for route in world.get("routes", []):
        points = [[_number(v, "route coordinate") for v in p] for p in route["points"]]
        if len(points) < 2 or any(len(p) != 3 for p in points):
            raise ValueError(f"route {route.get('id')} needs at least two x,y,z points")
        result.append({"id": str(route["id"]), "kind": str(route.get("kind", "")), "name": str(route.get("name", "")),
                       "source_id": route.get("source_id"), "surface": route.get("surface"),
                       "width_m": route.get("width"), "points": points,
                       "bridge_spans": [list(map(int, s)) for s in route.get("bridge_spans", [])],
                       "bridge_approach_spans": [list(map(int, s)) for s in route.get("bridge_approach_spans", [])],
                       "route_sha256": hashlib.sha256(_canonical({"id": route["id"], "points": points})).hexdigest()})
    return result


def _clip_spans(spans, low, high):
    return [[max(a, low), min(b, high)] for a, b in spans if b >= low and a <= high]


def _runs(indices):
    runs, start, previous = [], None, None
    for index in indices:
        if start is None:
            start = previous = index
        elif index == previous+1:
            previous = index
        else:
            runs.append((start, previous))
            start = previous = index
    if start is not None:
        runs.append((start, previous))
    return runs


class _Grid:
    def __init__(self, origin_x_m, origin_z_m, extent_m, cell_m, halo_m):
        self.ox, self.oz, self.cell, self.halo = origin_x_m, origin_z_m, cell_m, halo_m
        self.count = int(math.ceil(extent_m/cell_m))

    def rect(self, cx, cz):
        return (self.ox+cx*self.cell, self.oz+cz*self.cell, self.ox+(cx+1)*self.cell, self.oz+(cz+1)*self.cell)

    def padded(self, cx, cz):
        r = self.rect(cx, cz)
        return (r[0]-self.halo, r[1]-self.halo, r[2]+self.halo, r[3]+self.halo)

    def span(self, low, high, origin):
        a = int(math.floor((low-self.halo-origin)/self.cell))
        b = int(math.floor((high+self.halo-origin)/self.cell))
        return max(a, 0), min(b, self.count-1)


def _page(layer, grid, cx, cz, features):
    x0, z0, x1, _ = grid.rect(cx, cz)
    return {"schema": SCHEMA, "layer": layer, "halo_m": grid.halo,
            "cell": {"cx": cx, "cz": cz, "origin_x_m": x0, "origin_z_m": z0, "size_m": x1-x0},
            "features": features}


def _pool_cells(pools, grid):
    cells = {}
    for pool in pools:
        b = pool["bounds_m"]
        c0, c1 = grid.span(b[0], b[2], grid.ox)
        r0, r1 = grid.span(b[1], b[3], grid.oz)
        for cz in range(r0, r1+1):
            for cx in range(c0, c1+1):
                cells.setdefault((cx, cz), []).append(pool)
    return cells


def _route_cells(routes, grid):
    cells = {}
    for route in routes:
        points = route["points"]
        hits = {}
        for k in range(len(points)-1):
            a, b = points[k], points[k+1]
            c0, c1 = grid.span(min(a[0], b[0]), max(a[0], b[0]), grid.ox)
            r0, r1 = grid.span(min(a[2], b[2]), max(a[2], b[2]), grid.oz)
            for cz in range(r0, r1+1):
                for cx in range(c0, c1+1):
                    if _segment_hits(a[0], a[2], b[0], b[2], grid.padded(cx, cz)):
                        hits.setdefault((cx, cz), []).append(k)
        for cell, segments in hits.items():
            for first, last in _runs(segments):
                i0, i1 = first, last+1
                cells.setdefault(cell, []).append({
                    "id": route["id"], "kind": route["kind"], "name": route["name"],
                    "source_id": route["source_id"], "surface": route["surface"], "width_m": route["width_m"],
                    "route_sha256": route["route_sha256"], "route_point_count": len(points),
                    "first_point": i0, "last_point": i1,
                    "continues_before": i0 > 0, "continues_after": i1 < len(points)-1,
                    "bridge_spans": _clip_spans(route["bridge_spans"], i0, i1),
                    "bridge_approach_spans": _clip_spans(route["bridge_approach_spans"], i0, i1),
                    "points": points[i0:i1+1]})
    return cells


def write_feature_pages(world_path: Path, features_dir: Path, *, origin_x_m=-2048., origin_z_m=-2048.,
                        extent_m=4096., cell_m=256., halo_m=16.) -> dict:
    """Write immutable cell pages and an index; return the catalog reference."""
    world_path, features_dir = Path(world_path), Path(features_dir)
    world_bytes = world_path.read_bytes()
    world = json.loads(world_bytes)
    grid = _Grid(origin_x_m, origin_z_m, extent_m, cell_m, halo_m)
    layers = {"pools": _pool_cells(pool_features(world), grid), "routes": _route_cells(route_features(world), grid)}
    index_layers = {}
    for layer, cells in layers.items():
        entries = {}
        for (cx, cz), features in sorted(cells.items()):
            raw = _canonical(_page(layer, grid, cx, cz, features))
            if len(raw) > MAX_PAGE_BYTES:
                raise ValueError(f"{layer} page {cx}_{cz} exceeds {MAX_PAGE_BYTES} bytes")
            relative = f"{layer}/{cx}_{cz}.json"
            target = features_dir/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            entries[f"{cx}_{cz}"] = {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(),
                                     "bytes": len(raw), "count": len(features)}
        index_layers[layer] = entries
    index = {"schema": SCHEMA, "origin_x_m": origin_x_m, "origin_z_m": origin_z_m, "cell_m": cell_m,
             "halo_m": halo_m, "cells_per_side": grid.count, "world_sha256": hashlib.sha256(world_bytes).hexdigest(),
             "world_name": world_path.name, "layers": index_layers,
             "policy": "thermal pool rings subtracted from every tile that meets a padded cell; "
                       "route chunks overlap by the boundary segment and carry global point indices"}
    raw = _canonical(index)
    (features_dir/"index.json").write_bytes(raw)
    return {"schema": SCHEMA, "index": "features/index.json", "sha256": hashlib.sha256(raw).hexdigest(),
            "cell_m": cell_m, "halo_m": halo_m}


def verify_feature_pages(pack_dir: Path, catalog: dict) -> dict:
    """Check the catalog-to-index-to-page hash chain and return page counts per layer."""
    pack_dir = Path(pack_dir)
    reference = catalog["features"]
    raw = (pack_dir/reference["index"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError("feature index checksum differs from the catalog")
    index = json.loads(raw)
    counts = {}
    for layer, entries in index["layers"].items():
        for name, entry in entries.items():
            page = (pack_dir/"features"/entry["path"]).read_bytes()
            if hashlib.sha256(page).hexdigest() != entry["sha256"] or len(page) != entry["bytes"]:
                raise ValueError(f"{layer} page {name} differs from the index")
        counts[layer] = len(entries)
    return counts


def attach_feature_pages(world_path: Path, pack_dir: Path, catalog: dict, *, origin_x_m, origin_z_m, extent_m) -> dict:
    """Write feature pages beside the pack and bind them to the catalog revision."""
    reference = write_feature_pages(world_path, Path(pack_dir)/"features", origin_x_m=origin_x_m,
                                    origin_z_m=origin_z_m, extent_m=extent_m)
    catalog["features"] = reference
    catalog["dataset_revision"] = ""
    catalog["dataset_revision"] = hashlib.sha256(json.dumps(catalog, sort_keys=True).encode()).hexdigest()
    (Path(pack_dir)/"catalog.json").write_text(
        json.dumps(catalog, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n")
    return catalog
