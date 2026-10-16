"""Command-line interface for benchmarks."""
from __future__ import annotations

import argparse
from yellowstone_python.common.io import write_json_atomic
import hashlib
import json
import math
from pathlib import Path
from typing import Any
from yellowstone_python.river.river_transport import Cell, RHO_CP_J_M3_K, River, Source, Series
from yellowstone_python.river.benchmarks import *
from yellowstone_python.river.benchmarks import _max_abs_diff, _observed_rates, _danckwerts_analytic, _mms_wave_run

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = run_all_benchmarks()
        write_json_atomic(args.out, document)
    except (ValueError, ArithmeticError, OSError) as error:
        parser.exit(2, f"benchmarks failed: {error}\n")
    for result in document["results"]:
        print(f"{result['name']}: passed={result['passed']}")
    for excluded in document["not_applicable"]:
        print(f"{excluded['benchmark']}: not applicable "
              f"({excluded['reason']})")
    return 0 if document["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
