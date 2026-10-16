"""Command-line entry point for assembly observation data."""
from __future__ import annotations
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from yellowstone_python.observations.assembly import *

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usgs-normalized", type=Path, action="append",
                        default=[],
                        help="normalized usgs_nwis artifact "
                             "(repeat for multiple sites)")
    parser.add_argument("--met", type=Path, required=True,
                        help="fetch_met_forcing bundle to attach")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--exclude-quality", action="append", default=None,
                        help="per-row quality_status label to drop; "
                             "defaults to estimated and flagged_conditions")
    args = parser.parse_args()
    if not args.usgs_normalized:
        parser.error("at least one --usgs-normalized is required")

    exclude = (frozenset(args.exclude_quality)
               if args.exclude_quality is not None else EXCLUDE_QUALITY)
    bundle = assemble(args.usgs_normalized, args.met, exclude=exclude)
    atomic_write_json(args.out, bundle)
    print(f"Wrote {args.out}")
    for site_id, record in bundle["sites"].items():
        kept_t = record["quality_filtering"]["temperature_c"]["retained"]
        kept_q = record["quality_filtering"]["discharge_m3_s"]["retained"]
        print(f"  {site_id}: temperature n={kept_t}, discharge n={kept_q}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
