"""Trace thermal pool outlines from airborne lidar and aerial imagery."""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from yellowstone_python.common.io import write_json_atomic
from yellowstone_python.common.provenance import default_world_root
from yellowstone_python.observations import pool_outlines as po

POOL_SOURCE_IDS = (1034, 1030, 1028, 1029)
SCHEMA = "yellowstone.pool_outlines.v1"


def _write_figure(path: Path, record: dict, geometry: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x0, z0, x1, z1 = geometry["bounds"]
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    for axis in axes:
        axis.set_aspect("equal")
        axis.set_xlim(x0, x1)
        axis.set_ylim(z1, z0)
    axes[0].imshow(geometry["naip"][..., :3], extent=(x0, x1, z1, z0))
    points = geometry["points"]
    for code, color in ((2, "gray"), (1, "green"), (20, "cyan"), (9, "red"), (7, "orange"), (18, "magenta")):
        keep = points["classification"] == code
        axes[1].scatter(points["x"][keep], points["z"][keep], s=0.6, c=color)
    for axis in axes:
        for key, color in (("lidar", "black"), ("imagery", "blue"), ("prior", "red")):
            xs, zs = geometry[key].exterior.xy
            axis.plot(xs, zs, color=color, lw=1.2, label=key)
    axes[0].legend()
    axes[0].set_title(f"{record['name']}: imagery")
    axes[1].set_title("lidar returns by class")
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)


def main(argv=None) -> int:
    """Trace the named thermal pools and write the outline record."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, default=None,
                        help="midway world root holding data/world.json")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--qa-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root = args.world or default_world_root()
    world = json.loads((Path(root) / "data" / "world.json").read_text())
    pools = {p["source_id"]: p for p in world["pools"]}
    records = []
    for source_id in POOL_SOURCE_IDS:
        pool = pools[source_id]
        cx, _, cz = pool["center"]
        record, geometry = po.trace_pool(pool["name"], source_id, pool["ring"], (cx, cz), args.cache)
        records.append(record)
        logging.info("%s: adopted=%s area=%s m2 (prior %s m2)", record["name"], record["adopted"],
                     record["area_m2"], record["qa"]["prior_area_m2"])
        if args.qa_dir:
            args.qa_dir.mkdir(parents=True, exist_ok=True)
            _write_figure(args.qa_dir / f"pool_{source_id}.png", record, geometry)
    shifts = [r["qa"]["imagery_shift_to_lidar"] for r in records if r["adopted"]]
    registration: dict = {"adopted_pool_ids": [r["source_id"] for r in records if r["adopted"]]}
    if shifts:
        registration["imagery_shift_to_lidar_m"] = {
            "median_dx": round(float(np.median([s["dx_m"] for s in shifts])), 2),
            "median_dz": round(float(np.median([s["dz_m"] for s in shifts])), 2)}
    document = {
        "schema": SCHEMA, "status": "derived",
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "frame": {"crs": "EPSG:32612", "local_axes": "x east, z south",
                  "origin_utm_m": [po.E0, po.N0]},
        "method": {
            "outline": "boundary of the airborne lidar return void (no class 2 or class 20 return in "
                       f"{po.CELL_M} m cells) containing the pool center, smoothed and simplified with a "
                       f"tolerance of {po.MIN_SIMPLIFY_M} to {po.LIDAR_SIMPLIFY_M} m scaled to pool area",
            "cross_check": "NAIP NDWI (green and near infrared) water polygon above the Otsu threshold of the "
                           "window, translated to the lidar frame by the best-overlap shift",
            "adoption_rule": f"registered overlap of at least {po.MIN_AGREEMENT_IOU} and a shift inside the "
                             f"{po.SHIFT_SEARCH_M} m search window; otherwise the prior polygon is kept",
            "lidar_surface_classes": list(po.SURFACE_CLASSES)},
        "registration": registration,
        "pools": records}
    write_json_atomic(args.out, document, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
