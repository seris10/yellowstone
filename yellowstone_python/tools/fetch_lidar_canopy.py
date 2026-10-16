"""USGS point-cloud canopy workflow."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from yellowstone_python.observations.lidar import build_canopy_height, catalog_tiles, fetch_tiles
from yellowstone_python.common.io import write_json_atomic


def main(argv=None) -> int:
    """Fetch intersecting primary tiles and produce a georeferenced canopy-height model."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--fetch-only", action="store_true")
    parser.add_argument("--refresh-catalog", action="store_true")
    args = parser.parse_args(argv)
    import rasterio
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with rasterio.open(args.dem) as raster:
        names, sizes, catalog = catalog_tiles(tuple(raster.bounds), args.cache,
                                               refresh=args.refresh_catalog)
    receipts = fetch_tiles(names, args.cache, workers=args.workers, expected_sizes=sizes)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(args.out_dir / "lidar_sources.json", {
        "schema": "yellowstone.lidar_sources.v1", "status": "measured", "tiles": receipts,
        "source_catalog": catalog})
    if not args.fetch_only:
        build_canopy_height(names, args.cache, args.dem, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
