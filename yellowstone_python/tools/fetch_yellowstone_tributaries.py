"""Command-line entry point for tributaries observation data."""
from __future__ import annotations
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from yellowstone_python.observations.tributaries import *

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True,
                        help="Output JSON file for tributary_evidence.v1 artifact")
    parser.add_argument("--days", type=int, default=7,
                        help="Number of days of data to fetch (1-16)")
    parser.add_argument("--cells", type=int, default=2,
                        help="Downstream consumer hint; recorded in output only (1-5)")
    parser.add_argument(
        "--world", type=Path, default=None,
        help=(
            "Path to world.json. When supplied, confluence chainage is "
            "validated against Channel.length_m from replay/river_world.py."
        ),
    )

    args = parser.parse_args()

    if args.days < 1 or args.days > 16:
        parser.error("--days must be in [1, 16]")

    if args.cells < 1 or args.cells > 5:
        parser.error("--cells must be in [1, 5]")

    print("Yellowstone tributary evidence builder")
    print("=" * 70)
    print(f"Parameters: days={args.days}, world={args.world}")
    print()

    tributary_data = generate_tributary_data(
        args.days, world_path=args.world
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    _shared_json_write(args.out, tributary_data)

    print(f"Wrote {args.out}")
    summary = tributary_data["summary"]
    print("")
    print("=" * 70)
    print("TRIBUTARY EVIDENCE SUMMARY")
    print("=" * 70)
    print(f"Schema: {tributary_data['schema']}")
    print(f"Status: {tributary_data['status']}")
    print(f"Records queried: {summary['total_tributaries_queried']}")
    print(f"Verified: {summary['verified']}")
    print(f"Unverified: {summary['unverified']}")
    print(f"Solver sources: {summary['solver_sources']}")
    print(f"Landscape pockets: {summary['landscape_pockets']}")
    print(f"Cold-refuge candidates: {summary['cold_refuge_candidates']}")
    print(f"Channel length (world): {tributary_data['channel_length_m']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
