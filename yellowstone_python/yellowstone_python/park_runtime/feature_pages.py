"""Bounded shoreline, pool-cut, route, river, vegetation and forest-floor pages keyed by square cells.

Pages carry source geometry only; meshes are built by the streaming workers."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from .contracts import finite

SCHEMA = "yellowstone.terrain_features.v1"
MAX_PAGE_BYTES = 1 << 20

# River ribbon constants from tools/bake_world.gd.
WATER_MARGIN_FRACTION = 0.23
WATER_MARGIN_MIN_M = 0.8
WATER_MARGIN_MAX_M = 5.0
WATER_END_FADE_M = 8.0
WATER_JUNCTION_TOLERANCE_M = 1.5
WATER_SMOOTH_PASSES = 4
WATER_FOLD_SAFETY = 0.85
WATER_MIN_REACH_FRACTION = 0.30
WATER_RESAMPLE_STEP_M = 2.0
EXCELSIOR_OUTFLOW_ID = "authored_excelsior_outflow_01"

# Point layers index each record into its containing cell only.
VEGETATION_CELL_M = 64.0
VEGETATION_HALO_M = 8.0
FOREST_FLOOR_CELL_M = 64.0
FOREST_FLOOR_HALO_M = 4.0
PLACEMENT_CATEGORIES = ("trees", "grass", "logs", "rocks")
VEGETATION_KINDS = ("pine", "snag", "grass", "rock", "log")
FOREST_FLOOR_SCHEMA = "yellowstone.forest_floor.v1"
FOREST_FLOOR_KINDS = ("understory_card", "snag", "log", "litter")


def _canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()


def _number(value, name):
    return finite(value, name)


def pool_features(world: dict) -> list[dict]:
    """Return the pools with ring, water level and surface shading inputs."""
    result = []
    for pool in world.get("pools", []):
        ring = [[_number(p[0], "ring x"), _number(p[1], "ring z")] for p in pool.get("ring", [])]
        if len(ring) < 3 or any(len(p) != 2 for p in pool["ring"]):
            raise ValueError(f"pool {pool.get('id')} needs a ring of at least three coordinate pairs")
        center = pool.get("center")
        if not isinstance(center, list) or len(center) < 2:
            raise ValueError(f"pool {pool.get('id')} has no water elevation")
        xs, zs = [p[0] for p in ring], [p[1] for p in ring]
        result.append({"id": str(pool["id"]), "name": str(pool.get("name", "")), "source_id": pool.get("source_id"),
                       "thermal": bool(pool.get("thermal", False)),
                       "temperature_c": _number(pool.get("temperature_c", 0.0), "pool temperature"),
                       "center_x_m": _number(center[0], "pool center x"),
                       "center_z_m": _number(center[2], "pool center z") if len(center) > 2
                           else sum(zs)/len(zs),
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
    """Return route polylines with identities, arc lengths and a source geometry hash."""
    result = []
    for route in world.get("routes", []):
        points = [[_number(v, "route coordinate") for v in p] for p in route["points"]]
        if len(points) < 2 or any(len(p) != 3 for p in points):
            raise ValueError(f"route {route.get('id')} needs at least two x,y,z points")
        arcs = [0.0]
        for k in range(1, len(points)):
            arcs.append(arcs[-1]+math.dist(points[k-1], points[k]))
        result.append({"id": str(route["id"]), "kind": str(route.get("kind", "")), "name": str(route.get("name", "")),
                       "source_id": route.get("source_id"), "surface": route.get("surface"),
                       "width_m": route.get("width"), "points": points, "arcs": arcs,
                       "bridge_spans": [list(map(int, s)) for s in route.get("bridge_spans", [])],
                       "bridge_approach_spans": [list(map(int, s)) for s in route.get("bridge_approach_spans", [])],
                       "route_sha256": hashlib.sha256(_canonical({"id": route["id"], "points": points})).hexdigest()})
    return result


def _water_margin_m(width: float) -> float:
    return min(max(width*WATER_MARGIN_FRACTION, WATER_MARGIN_MIN_M), WATER_MARGIN_MAX_M)


def snap_water_junctions(rivers: list[dict], tolerance=WATER_JUNCTION_TOLERANCE_M) -> None:
    """Snap clustered river endpoints to their shared centroid, matching bake_world.gd."""
    ends = [(ri, end) for ri in range(len(rivers)) for end in (0, len(rivers[ri]["points"])-1)]
    used = set()
    for e in ends:
        if e in used:
            continue
        group = [e]
        p = rivers[e[0]]["points"][e[1]]
        for o in ends:
            if o == e or o in used:
                continue
            q = rivers[o[0]]["points"][o[1]]
            if math.hypot(p[0]-q[0], p[2]-q[2]) <= tolerance:
                group.append(o)
        if len(group) < 2:
            continue
        centroid = [sum(rivers[g[0]]["points"][g[1]][k] for g in group)/len(group) for k in range(3)]
        for g in group:
            rivers[g[0]]["points"][g[1]] = list(centroid)
            used.add(g)


def _river_end_is_free(rivers: list[dict], self_index: int, point) -> bool:
    limit = WATER_JUNCTION_TOLERANCE_M**2
    for other_index, other in enumerate(rivers):
        if other_index == self_index:
            continue
        for q in other["points"]:
            if (q[0]-point[0])**2+(q[2]-point[2])**2 <= limit:
                return False
    return True


def _resample_polyline(points: list, step=WATER_RESAMPLE_STEP_M) -> list:
    """Uniform station spacing with a 0.25 m endpoint tolerance, matching bake_world.gd."""
    out = [points[0]]
    carry = 0.0
    for i in range(1, len(points)):
        a = list(points[i-1])
        b = points[i]
        seg = math.dist(a, b)
        if seg < 0.0001:
            continue
        while carry+seg >= step:
            t = (step-carry)/seg
            p = [a[k]+(b[k]-a[k])*t for k in range(3)]
            out.append(p)
            a = p
            seg = math.dist(a, b)
            carry = 0.0
        carry += seg
    if math.dist(out[-1], points[-1]) > 0.25:
        out.append(list(points[-1]))
    return out


def _smooth_plan_view(points: list) -> list:
    """Smooth plan-view kinks while retaining heights and endpoints, matching bake_world.gd."""
    result = [list(p) for p in points]
    for _ in range(WATER_SMOOTH_PASSES):
        source = [list(p) for p in result]
        for i in range(1, len(points)-1):
            result[i] = [(source[i-1][0]+2.0*source[i][0]+source[i+1][0])*0.25, source[i][1],
                         (source[i-1][2]+2.0*source[i][2]+source[i+1][2])*0.25]
    return result


def _river_stations(points: list, width: float, free_start: bool, free_end: bool, tint: bool) -> list:
    """Return per-station ribbon fields (arc, reaches, fade, red) for one resampled river."""
    count = len(points)
    visual_half = width*0.5+_water_margin_m(width)
    arcs = [0.0]*count
    for i in range(1, count):
        arcs[i] = arcs[i-1]+math.dist(points[i], points[i-1])
    total_arc = arcs[-1]
    raw = [0.0]*count
    for i in range(1, count-1):
        ax, az = points[i][0]-points[i-1][0], points[i][2]-points[i-1][2]
        bx, bz = points[i+1][0]-points[i][0], points[i+1][2]-points[i][2]
        mean_length = 0.5*(math.hypot(ax, az)+math.hypot(bx, bz))
        la, lb = math.hypot(ax, az), math.hypot(bx, bz)
        if mean_length > 0.0001 and la > 0.0001 and lb > 0.0001:
            cross = (ax*bz-az*bx)/(la*lb)
            raw[i] = math.asin(min(max(cross, -1.0), 1.0))/mean_length
    stations = []
    for i in range(count):
        strongest_plus = max(raw[max(0, i-3):i+4]+[0.0])
        strongest_minus = max([-v for v in raw[max(0, i-3):i+4]]+[0.0])
        reach_plus = reach_minus = visual_half
        if strongest_plus > 0.0001:
            reach_plus = min(max(min(reach_plus, WATER_FOLD_SAFETY/strongest_plus),
                                 visual_half*WATER_MIN_REACH_FRACTION), visual_half)
        if strongest_minus > 0.0001:
            reach_minus = min(max(min(reach_minus, WATER_FOLD_SAFETY/strongest_minus),
                                  visual_half*WATER_MIN_REACH_FRACTION), visual_half)
        deficit_plus = visual_half-reach_plus
        deficit_minus = visual_half-reach_minus
        if deficit_plus > 0.0:
            reach_minus += deficit_plus
        if deficit_minus > 0.0:
            reach_plus += deficit_minus
        fade = 1.0
        if free_start:
            fade = min(fade, arcs[i]/WATER_END_FADE_M)
        if free_end:
            fade = min(fade, (total_arc-arcs[i])/WATER_END_FADE_M)
        fraction = arcs[i]/max(total_arc, 0.001)
        stations.append({"p": [float(v) for v in points[i]], "arc": arcs[i],
                         "reach_p": reach_plus, "reach_m": reach_minus,
                         "fade": min(max(fade, 0.0), 1.0),
                         "red": 1.0-fraction if tint else 1.0})
    return stations


def river_features(world: dict) -> list[dict]:
    """Return resampled river ribbon stations with endpoint and junction semantics."""
    rivers = []
    for river in world.get("rivers", []):
        points = [[_number(v, "river coordinate") for v in p] for p in river.get("points", [])]
        width = float(river.get("width", 0.0))
        if len(points) < 2 or width <= 0.0:
            raise ValueError(f"river {river.get('id')} needs at least two points and a positive width")
        rivers.append({"id": str(river["id"]), "name": str(river.get("name", "")),
                       "thermal": bool(river.get("thermal", False)), "width": width,
                       "flow_mps": _number(river.get("flow_mps", 0.0), "river flow"),
                       "points": points})
    snap_water_junctions(rivers)
    result = []
    for index, river in enumerate(rivers):
        points = river["points"]
        free_start = _river_end_is_free(rivers, index, points[0])
        free_end = _river_end_is_free(rivers, index, points[-1])
        tint = river["id"] == EXCELSIOR_OUTFLOW_ID
        smoothed = _smooth_plan_view(_resample_polyline(points))
        stations = _river_stations(smoothed, river["width"], free_start, free_end, tint)
        result.append({"id": river["id"], "name": river["name"], "thermal": river["thermal"],
                       "width_m": river["width"], "flow_mps": river["flow_mps"], "tint": tint,
                       "free_start": free_start, "free_end": free_end,
                       "sample_z": float(points[len(points)//2][2]),
                       "total_arc_m": stations[-1]["arc"],
                       "visual_half_m": river["width"]*0.5+_water_margin_m(river["width"]),
                       "river_sha256": hashlib.sha256(
                           _canonical({"id": river["id"], "points": points})).hexdigest(),
                       "stations": stations})
    return result


def _position(value, name):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{name} needs a position of three coordinates")
    return [_number(v, name) for v in value]


def vegetation_features(placements_path, overrides_path) -> list[dict]:
    """Resolve placements against overrides into effective vegetation source records.

    The resolution order matches tools/bake_world.gd make_vegetation."""
    placements = json.loads(Path(placements_path).read_bytes())
    overrides = json.loads(Path(overrides_path).read_bytes())
    records = []
    for category in PLACEMENT_CATEGORIES:
        if not isinstance(placements.get(category), list):
            raise ValueError(f"placements need a {category} list")
        records.extend(placements[category])
    add = overrides.get("add", [])
    remove = overrides.get("remove", [])
    replace = overrides.get("replace", {})
    if not isinstance(add, list) or not isinstance(remove, list) or not isinstance(replace, dict):
        raise ValueError("overrides need add and remove lists and a replace object")
    removed = {str(entry) for entry in remove}
    effective, ids = [], set()
    for record in records + add:
        if not isinstance(record, dict):
            raise ValueError("vegetation records require objects")
        identity = str(record.get("id", record.get("stable_id", "")))
        if not identity:
            raise ValueError("vegetation record requires an id")
        if identity in removed:
            continue
        resolved = replace.get(identity, record)
        resolved_id = str(resolved.get("id", resolved.get("stable_id", "")))
        if not resolved_id or resolved_id in ids:
            raise ValueError(f"vegetation record id is absent or duplicated: {resolved_id or identity}")
        if str(resolved.get("kind", "")) not in VEGETATION_KINDS:
            raise ValueError(f"vegetation record {resolved_id} has unknown kind {resolved.get('kind')}")
        _position(resolved.get("position"), f"vegetation record {resolved_id}")
        ids.add(resolved_id)
        effective.append(resolved)
    return effective


def forest_floor_features(floor_path) -> list[dict]:
    """Return authored forest-floor records with IDs, guilds and contact information."""
    parsed = json.loads(Path(floor_path).read_bytes())
    if parsed.get("schema") != FOREST_FLOOR_SCHEMA or parsed.get("status") != "authored":
        raise ValueError(f"forest floor requires authored schema {FOREST_FLOOR_SCHEMA}")
    records = parsed.get("records")
    if not isinstance(records, list):
        raise ValueError("forest floor requires records")
    ids = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("forest-floor records require objects")
        identity = str(record.get("id", ""))
        if not identity or identity in ids:
            raise ValueError(f"forest-floor record id is absent or duplicated: {identity}")
        if str(record.get("kind", "")) not in FOREST_FLOOR_KINDS:
            raise ValueError(f"forest-floor record {identity} has unknown kind {record.get('kind')}")
        _position(record.get("position"), f"forest-floor record {identity}")
        ids.add(identity)
    return records


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
                    "arcs": route["arcs"][i0:i1+1],
                    "points": points[i0:i1+1]})
    return cells


def _river_cells(rivers, grid):
    """Chunk resampled river stations by cell; adjacent chunks share the boundary station."""
    cells = {}
    for river in rivers:
        stations = river["stations"]
        hits = {}
        for k in range(len(stations)-1):
            a, b = stations[k]["p"], stations[k+1]["p"]
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
                    "id": river["id"], "kind": "river", "name": river["name"],
                    "thermal": river["thermal"], "width_m": river["width_m"],
                    "flow_mps": river["flow_mps"], "tint": river["tint"],
                    "free_start": river["free_start"], "free_end": river["free_end"],
                    "sample_z": river["sample_z"], "total_arc_m": river["total_arc_m"],
                    "visual_half_m": river["visual_half_m"],
                    "river_sha256": river["river_sha256"], "river_station_count": len(stations),
                    "first_station": i0, "last_station": i1,
                    "continues_before": i0 > 0, "continues_after": i1 < len(stations)-1,
                    "stations": stations[i0:i1+1]})
    return cells


def _point_cells(records, grid):
    """Index each record into its single containing cell; record out-of-extent records."""
    cells, outside = {}, []
    for record in records:
        position = record["position"]
        cx = int(math.floor((position[0]-grid.ox)/grid.cell))
        cz = int(math.floor((position[2]-grid.oz)/grid.cell))
        if not (0 <= cx < grid.count and 0 <= cz < grid.count):
            outside.append(str(record.get("id", record.get("stable_id", ""))))
            continue
        cells.setdefault((cx, cz), []).append(record)
    return cells, outside


def write_feature_pages(world_path: Path, features_dir: Path, *, origin_x_m=-2048., origin_z_m=-2048.,
                        extent_m=4096., cell_m=256., halo_m=16.,
                        placements_path=None, overrides_path=None, forest_floor_path=None) -> dict:
    """Write immutable cell pages and an index; return the catalog reference."""
    world_path, features_dir = Path(world_path), Path(features_dir)
    world_bytes = world_path.read_bytes()
    world = json.loads(world_bytes)
    grid = _Grid(origin_x_m, origin_z_m, extent_m, cell_m, halo_m)
    layers = {"pools": (grid, _pool_cells(pool_features(world), grid)),
              "routes": (grid, _route_cells(route_features(world), grid)),
              "rivers": (grid, _river_cells(river_features(world), grid))}
    layer_grids = {}
    out_of_extent = {}
    if (placements_path is None) != (overrides_path is None):
        raise ValueError("vegetation pages need both placements and overrides")
    if placements_path is not None:
        vegetation_grid = _Grid(origin_x_m, origin_z_m, extent_m, VEGETATION_CELL_M, VEGETATION_HALO_M)
        cells, outside = _point_cells(vegetation_features(placements_path, overrides_path), vegetation_grid)
        layers["vegetation"] = (vegetation_grid, cells)
        layer_grids["vegetation"] = {"cell_m": VEGETATION_CELL_M, "halo_m": VEGETATION_HALO_M,
                                     "cells_per_side": vegetation_grid.count}
        out_of_extent["vegetation"] = sorted(outside)
    if forest_floor_path is not None:
        floor_grid = _Grid(origin_x_m, origin_z_m, extent_m, FOREST_FLOOR_CELL_M, FOREST_FLOOR_HALO_M)
        cells, outside = _point_cells(forest_floor_features(forest_floor_path), floor_grid)
        layers["forest_floor"] = (floor_grid, cells)
        layer_grids["forest_floor"] = {"cell_m": FOREST_FLOOR_CELL_M, "halo_m": FOREST_FLOOR_HALO_M,
                                       "cells_per_side": floor_grid.count}
        out_of_extent["forest_floor"] = sorted(outside)
    index_layers = {}
    for layer, (layer_grid, cells) in layers.items():
        entries = {}
        for (cx, cz), features in sorted(cells.items()):
            raw = _canonical(_page(layer, layer_grid, cx, cz, features))
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
             "world_name": world_path.name, "layers": index_layers, "layer_grids": layer_grids,
             "out_of_extent": out_of_extent,
             "policy": "thermal pool rings subtracted from every tile that meets a padded cell; "
                       "route chunks overlap by the boundary segment and carry global point indices; "
                       "river chunks carry snapped, resampled ribbon stations and share the boundary station; "
                       "vegetation and forest-floor records live in their single containing cell"}
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


def attach_feature_pages(world_path: Path, pack_dir: Path, catalog: dict, *, origin_x_m, origin_z_m, extent_m,
                         placements_path=None, overrides_path=None, forest_floor_path=None) -> dict:
    """Write feature pages beside the pack and bind them to the catalog revision."""
    reference = write_feature_pages(world_path, Path(pack_dir)/"features", origin_x_m=origin_x_m,
                                    origin_z_m=origin_z_m, extent_m=extent_m,
                                    placements_path=placements_path, overrides_path=overrides_path,
                                    forest_floor_path=forest_floor_path)
    catalog["features"] = reference
    catalog["dataset_revision"] = ""
    catalog["dataset_revision"] = hashlib.sha256(json.dumps(catalog, sort_keys=True).encode()).hexdigest()
    (Path(pack_dir)/"catalog.json").write_text(
        json.dumps(catalog, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n")
    return catalog
