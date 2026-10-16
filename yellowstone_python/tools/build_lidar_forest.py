"""Generate measured dominant-crown coverage and reviewed placements."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from yellowstone_python.census.lidar_workflow import build_forest_products
from yellowstone_python.common.provenance import default_world_root


def main(argv=None):
    """Run the forest producer without changing Godot scenes or manifests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--world", type=Path, default=default_world_root())
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    build_forest_products(args.project, args.world, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
