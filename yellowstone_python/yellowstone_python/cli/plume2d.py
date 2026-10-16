"""Command-line interface for plume2d."""
from __future__ import annotations

import argparse
from yellowstone_python.common.io import write_json_atomic
from yellowstone_python.common.checks import finite as _finite
import math
import numpy as np
from yellowstone_python.river.plume2d import *
from yellowstone_python.river.plume2d import _require_sparse, _discrete_residual

def main() -> int:
    import json
    from pathlib import Path
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--hot-c", type=float, default=19.1)
    ap.add_argument("--river-c", type=float, default=17.8)
    ap.add_argument("--grid", type=int, default=128)
    args = ap.parse_args()
    artifact = run_experiment(nx=args.grid, nz=args.grid,
                              ambient_c=args.river_c,
                              source_c=args.hot_c)
    write_json_atomic(args.out, artifact)
    print(f"peak={artifact['metrics']['peak_anomaly_c']}C "
          f"footprint={artifact['metrics']['footprint_length_m']}m "
          f"exchange={artifact['metrics']['exchange_length_u_over_k_m']}m "
          f"mixing={artifact['anchors']['mixing_verdict']} "
          f"closure={artifact['closure']['verdict']}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
