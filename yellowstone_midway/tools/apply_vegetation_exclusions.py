"""Vegetation exclusion pass for routes, decks and pools.

Filters placement records into remove[] and writes the canopy display-exclusion sidecar.
"""

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OVERRIDES_PATH = ROOT / "data/placement_overrides.json"
RECEIPT_PATH = ROOT / "tests/vegetation_exclusion_receipt.json"
CANOPY_DIR = ROOT / "data/lidar_canopy"

ROUTE_CLEARANCE_M = {"road": 1.0, "trail": 1.0}
POOL_EDGE_M = 1.0
# Deck fields: center x/z, half-width x/z, deck y (bake_world.make_overlook).
DECKS = [(-252.0, 159.0, 3.25, 2.25, 48.07),
         (-246.95, 160.05, 1.9 / 2 + 1.0, 0.95, 48.0)]
GRID_CELL_M = 8.0


def route_segments(world: dict) -> list:
    """Return route segments as (ax, az, bx, bz, corridor half width, route id)."""
    segments = []
    for route in world["routes"]:
        half_width = float(route.get("width", 2.0)) / 2 + ROUTE_CLEARANCE_M.get(route.get("kind", "trail"), 1.0)
        points = route["points"]
        for index in range(1, len(points)):
            segments.append((float(points[index - 1][0]), float(points[index - 1][2]),
                             float(points[index][0]), float(points[index][2]), half_width, route["id"]))
    return segments


def build_grid(segments: list, cell_m: float = GRID_CELL_M) -> dict:
    """Bin segment indices into a coarse lookup grid."""
    grid = {}
    for segment_index, (ax, az, bx, bz, *_rest) in enumerate(segments):
        for ix in range(int((min(ax, bx) - cell_m) // cell_m), int((max(ax, bx) + cell_m) // cell_m) + 1):
            for iz in range(int((min(az, bz) - cell_m) // cell_m), int((max(az, bz) + cell_m) // cell_m) + 1):
                grid.setdefault((ix, iz), []).append(segment_index)
    return grid


def _segment_distance(px: float, pz: float, segment: tuple) -> tuple:
    """Return the plan-view distance from a point to one segment."""
    ax, az, bx, bz, half_width, route_id = segment
    dx, dz = bx - ax, bz - az
    length2 = dx * dx + dz * dz
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / length2))
    return math.hypot(px - (ax + t * dx), pz - (az + t * dz)), half_width, route_id


def route_violation(grid: dict, segments: list, px: float, pz: float) -> str | None:
    """Return the route id when a point lies inside a corridor."""
    ix, iz = int(px // GRID_CELL_M), int(pz // GRID_CELL_M)
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            for segment_index in grid.get((ix + dx, iz + dz), []):
                distance, half_width, route_id = _segment_distance(px, pz, segments[segment_index])
                if distance < half_width:
                    return route_id
    return None


def in_deck(px: float, pz: float, decks: list = DECKS) -> str | None:
    """Return a deck label when a point lies inside a deck footprint."""
    for deck_index, (x0, z0, half_x, half_z, _y) in enumerate(decks):
        if x0 - half_x <= px <= x0 + half_x and z0 - half_z <= pz <= z0 + half_z:
            return "deck_%d" % deck_index
    return None


def in_pool(pools: list, px: float, pz: float, edge_m: float = POOL_EDGE_M) -> str | None:
    """Return the pool id when a point lies inside a pool ring."""
    for pool in pools:
        ring = [(float(point[0]), float(point[1])) for point in pool["ring"]]
        xs = [point[0] for point in ring]
        zs = [point[1] for point in ring]
        if px < min(xs) - edge_m or px > max(xs) + edge_m:
            continue
        if pz < min(zs) - edge_m or pz > max(zs) + edge_m:
            continue
        inside = False
        for index in range(len(ring)):
            x1, z1 = ring[index]
            x2, z2 = ring[(index + 1) % len(ring)]
            if (z1 > pz) != (z2 > pz) and px < x1 + (pz - z1) * (x2 - x1) / (z2 - z1):
                inside = not inside
        if inside:
            return pool["id"]
    return None


def exclusion_reason(grid: dict, segments: list, pools: list, px: float, pz: float) -> str | None:
    """Return the corridor, deck or pool reason excluding a point."""
    return route_violation(grid, segments, px, pz) or in_deck(px, pz) or in_pool(pools, px, pz)


def filter_records(records: list, overrides: dict, grid: dict, segments: list, pools: list, source: str) -> list:
    """Move violating record ids into overrides remove and return the removed record list."""
    remove = set(overrides.get("remove", []))
    removed = []
    for record in records:
        px, pz = float(record["position"][0]), float(record["position"][2])
        reason = exclusion_reason(grid, segments, pools, px, pz)
        if reason is None:
            continue
        identity = str(record.get("id", record.get("stable_id", "")))
        if identity and identity not in remove:
            remove.add(identity)
            removed.append({"id": identity, "kind": record.get("kind", ""), "source": source,
                            "position": record["position"], "reason": reason})
    overrides["remove"] = sorted(remove)
    return removed


def mask_canopy_cells(cells: np.ndarray, first_x: float, first_z: float, cell_size: float,
                      grid: dict, segments: list, pools: list) -> list:
    """Clear active cells centered inside an exclusion and return the cleared cell list."""
    cleared = []
    height, width = cells.shape
    for row, column in np.argwhere(cells > 0):
        px, pz = first_x + column * cell_size, first_z + row * cell_size
        reason = exclusion_reason(grid, segments, pools, px, pz)
        if reason is not None:
            cells[row, column] = 0
            cleared.append({"row": int(row), "column": int(column),
                            "position": [round(px, 3), round(pz, 3)], "reason": reason})
    return cleared


def reason_class(reason: str, route_ids: set) -> str:
    """Group an exclusion reason into route, deck or pool."""
    if reason.startswith("deck"):
        return "deck"
    return "route" if reason in route_ids else "pool"


def main() -> None:
    """Apply the exclusion pass and write the review receipt."""
    world = json.loads((ROOT / "data/world.json").read_text())
    placements = json.loads((ROOT / "data/placements.json").read_text())
    overrides = json.loads(OVERRIDES_PATH.read_text())
    segments = route_segments(world)
    grid = build_grid(segments)
    pools = world["pools"]

    add_before = len(overrides.get("add", []))
    remove_before = len(overrides.get("remove", []))
    removed = filter_records(overrides.get("add", []), overrides, grid, segments, pools, "placement_overrides.json")
    placements_records = sum((placements[category] for category in ["trees", "grass", "logs", "rocks"]), [])
    removed += filter_records(placements_records, overrides, grid, segments, pools, "placements.json")
    OVERRIDES_PATH.write_text(json.dumps(overrides, indent=1) + "\n")

    metadata = json.loads((CANOPY_DIR / "unresolved_render_canopy.json").read_text())
    width, height, cell_size = int(metadata["width"]), int(metadata["height"]), float(metadata["cell_size_m"])
    first_x, first_z = float(metadata["first_cell_x_m"]), float(metadata["first_cell_z_m"])
    cells = np.fromfile(CANOPY_DIR / "unresolved_cells.u8", dtype=np.uint8).reshape(height, width).copy()
    active_before = int(np.count_nonzero(cells))
    cleared = mask_canopy_cells(cells, first_x, first_z, cell_size, grid, segments, pools)
    sidecar = CANOPY_DIR / "unresolved_cells_excluded.u8"
    sidecar.write_bytes(cells.tobytes())
    sidecar_record = {
        "schema": "yellowstone.unresolved_canopy_exclusion.v1",
        "path": sidecar.name,
        "width": width,
        "height": height,
        "cell_size_m": cell_size,
        "first_cell_x_m": first_x,
        "first_cell_z_m": first_z,
        "source_mask": "unresolved_cells.u8",
        "active_cells_before": active_before,
        "active_cells_after": int(np.count_nonzero(cells)),
        "cells_cleared": len(cleared),
        "filter_class": "display_layer_exclusion",
        "scope": "Routes, deck footprints and pool rings; the scientific canopy mask stays unchanged",
        "producer": "tools/apply_vegetation_exclusions.py",
    }
    (CANOPY_DIR / "unresolved_cells_excluded.json").write_text(json.dumps(sidecar_record, indent=1) + "\n")

    route_ids = {segment[5] for segment in segments}
    removed_by_reason = {}
    removed_by_source = {}
    for record in removed:
        key = reason_class(record["reason"], route_ids)
        removed_by_reason[key] = removed_by_reason.get(key, 0) + 1
        removed_by_source[record["source"]] = removed_by_source.get(record["source"], 0) + 1
    cleared_by_reason = {}
    for cell in cleared:
        key = reason_class(cell["reason"], route_ids)
        cleared_by_reason[key] = cleared_by_reason.get(key, 0) + 1
    receipt = {
        "schema": "yellowstone.vegetation_exclusion_receipt.v1",
        "scope": "Display-layer exclusion; placements.json and the scientific canopy mask stay unchanged",
        "parameters": {
            "route_clearance_m": ROUTE_CLEARANCE_M,
            "corridor_rule": "route width / 2 + clearance",
            "decks": DECKS,
            "pool_edge_m": POOL_EDGE_M,
        },
        "placements": {
            "add_records": add_before,
            "remove_before": remove_before,
            "remove_after": len(overrides["remove"]),
            "records_removed": len(removed),
            "removed_by_reason": removed_by_reason,
            "removed_by_source": removed_by_source,
            "removed_records": removed,
        },
        "canopy": {
            "active_cells_before": active_before,
            "active_cells_after": int(np.count_nonzero(cells)),
            "cells_cleared": len(cleared),
            "cleared_by_reason": cleared_by_reason,
            "cleared_cells": cleared,
            "sidecar": "data/lidar_canopy/unresolved_cells_excluded.u8",
        },
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=1) + "\n")
    print("exclusion: %d placement records moved to remove[] (total %d)" % (len(removed), len(overrides["remove"])))
    print("exclusion: cleared %d canopy cells -> %s" % (len(cleared), sidecar.name))
    print("exclusion: receipt -> %s" % RECEIPT_PATH.relative_to(ROOT))


if __name__ == "__main__":
    main()
