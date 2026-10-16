"""Command-line interface for figures."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Sequence
from yellowstone_python.river.figures import *
from yellowstone_python.river.figures import _resolve_status_note, _validate_slice, _pyplot, _save, _check_sizes

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obs", type=Path, required=True)
    parser.add_argument("--uq", type=Path, required=True)
    parser.add_argument("--lsfit", type=Path, required=True)
    parser.add_argument("--fit", type=Path, required=True,
                        help="reach_heat_fit artifact (carries the grids)")
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--intervention", type=Path, required=True,
                        help="aquatic_intervention artifact (refuge marker)")
    parser.add_argument("--out-dir", type=Path, default=Path("figs"))
    args = parser.parse_args()
    try:
        bundle = json.loads(args.obs.read_text(encoding="utf-8"))
        uq_doc = json.loads(args.uq.read_text(encoding="utf-8"))
        lsfit_doc = json.loads(args.lsfit.read_text(encoding="utf-8"))
        fit_doc = json.loads(args.fit.read_text(encoding="utf-8"))
        replay = json.loads(args.replay.read_text(encoding="utf-8"))
        intervention = json.loads(args.intervention.read_text(
            encoding="utf-8"))
        from yellowstone_python.aquatic.aquatic_foodweb import thermal_landscape
        landscape = thermal_landscape(replay)
        control = intervention["control"]
        for path in build_all(bundle, uq_doc, lsfit_doc, fit_doc,
                              landscape, control["s_m"],
                              control["cell_id"], args.out_dir):
            print(f"Wrote {path} ({path.stat().st_size} bytes)")
    except (ValueError, KeyError, IndexError, TypeError,
            ArithmeticError, OSError) as error:
        parser.exit(2, f"figures failed: {error.__class__.__name__}: "
                       f"{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
