"""Command-line interface for river transport."""
from __future__ import annotations

import argparse
from yellowstone_python.common.io import write_json_atomic
import copy
import numpy as np
from bisect import bisect_right
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any
from yellowstone_python.river.surface_flux import BUDGET_PARAM_KEYS, BudgetParams, MetState, describe_surface_model, flux_at, linearized, flux_array, linearized_array
from yellowstone_python.common.checks import finite, positive
from yellowstone_python.atmosphere.time_utils import UTC, timestamp_metadata
from yellowstone_python.river.river_transport import *
from yellowstone_python.river.river_transport import _Sum, _parse_hyporheic_zones

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true")
    mode.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        config = (
            demo_config()
            if args.demo
            else json.loads(args.config.read_text(encoding="utf-8"))
        )
        if not isinstance(config, dict):
            raise ValueError("configuration must be a JSON object")

        document = make_replay(config)
        write_json_atomic(args.out, document, indent=2)

    except (
        ValueError, TypeError, KeyError, ArithmeticError, OSError
    ) as error:
        parser.exit(2, f"river transport failed: {error}\n")

    budget = document["final_budget"]
    passed = document["numerical_checks"]["passed"]

    print(f"Replay: {args.out}")
    print(
        f"Cells: {len(document['cells'])}; "
        f"frames: {len(document['frames'])}; "
        f"steps: {budget['steps']}"
    )
    print(
        f"Heat residual: {budget['heat_residual_j']:.6g} J; "
        f"relative: {budget['heat_relative_residual']:.3g}"
    )
    print(
        f"Water residual: {budget['water_residual_m3']:.6g} m3"
    )
    print(
        f"Maximum advective Courant number: "
        f"{budget['max_advective_courant']:.3g}"
    )
    print(f"Numerical budget checks passed: {passed}")
    print("Synthetic/illustrative model; not a Yellowstone forecast.")

    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
