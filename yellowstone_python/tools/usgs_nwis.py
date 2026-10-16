"""Command-line entry point for usgs observations."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import logging
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from yellowstone_python.observations.usgs import *

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, choices=list(SITES))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--period-days", type=int, default=30)
    parser.add_argument("--normalized-out", type=Path, default=None,
                        help="also write the normalized observation artifact")
    parser.add_argument("--skip-measurements", action="store_true",
                        help="skip the field-measurement request")
    args = parser.parse_args()
    try:
        validate_period_days(args.period_days)
    except ValueError as e:
        parser.error(str(e))
    fetch_all(args.site, args.out, args.period_days,
              include_measurements=not args.skip_measurements,
              normalized_out=args.normalized_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
