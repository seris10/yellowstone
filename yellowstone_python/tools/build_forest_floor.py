"""Independent authored forest-floor display layer."""
from __future__ import annotations

import argparse
from pathlib import Path

from yellowstone_python.authoring.forest_floor import build_forest_floor
from yellowstone_python.common.provenance import default_world_root


def main(argv=None):
    """Write bounded floor records without modifying existing tree placements."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--world", type=Path, default=default_world_root())
    parser.add_argument("--out", type=Path)
    parser.add_argument("--seed", type=int, default=54107)
    args = parser.parse_args(argv)
    doc = build_forest_floor(args.project, args.world, settings={"seed": args.seed}, output=args.out)
    print(f"forest floor: {doc['diagnostics']['counts']}; authored, acceptance pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
