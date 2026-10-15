"""Command-line interface for compare."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic

import argparse
import json
import math
from pathlib import Path
from typing import Any
from yellowstone_python.compare import DEFAULT_EXPOSURE_THRESHOLDS_C, VALID_MODES, compare_builds

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("A")
    ap.add_argument("B")
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--allow-incompatible", action="store_true",
                    help=("run the comparison even when build manifests "
                          "differ on load-bearing fields"))
    ap.add_argument("--mode", default="endpoint", choices=list(VALID_MODES),
                    help=("endpoint reads scalar outputs; trajectory reads "
                          "river_replay.json frames and reports exposure, "
                          "degree-hours above thresholds, peaks and signed "
                          "mean delta on common cells"))
    ap.add_argument("--exposure-thresholds-c", default=None,
                    help=("comma-separated temperatures C for trajectory "
                          "exposure and degree-hours (default "
                          f"{','.join(str(t) for t in DEFAULT_EXPOSURE_THRESHOLDS_C)})"))
    args = ap.parse_args()
    thresholds: list[float] | None = None
    if args.exposure_thresholds_c:
        thresholds = []
        for token in args.exposure_thresholds_c.split(","):
            text = token.strip()
            if not text:
                continue
            thresholds.append(float(text))
    out = compare_builds(args.A, args.B,
                         allow_incompatible=args.allow_incompatible,
                         mode=args.mode,
                         exposure_thresholds_c=thresholds)
    text = json.dumps(out, indent=2, allow_nan=False)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(output, out, indent=2)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
