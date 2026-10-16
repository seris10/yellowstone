"""Command-line interface for aquatic foodweb."""
from __future__ import annotations

import argparse
from yellowstone_python.common.io import write_json_atomic
import json
import math
from pathlib import Path
from typing import Any
from yellowstone_python.common.checks import finite, positive, fraction, nonnegative
from yellowstone_python.registry.coupling import POCKET_CONSERVATION
from yellowstone_python.aquatic.fish import REFUGE_WEIGHT, predation_survival_factor, suitability_with_stressors, thermal_performance
from yellowstone_python.insects_birds import DEFAULT_DIETS, INSECT_GROUPS, develop_benthic, emergence_total_from_taxa, holling_type_ii, trout_diet_at_temp
from yellowstone_python.aquatic.aquatic_foodweb import *
from yellowstone_python.aquatic.aquatic_foodweb import _taxon_do_survival, _per_cell_stressor_factors

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--pulse", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--days", type=float, default=14.0)
    parser.add_argument("--species", default="brown_trout")
    parser.add_argument("--window", type=float, nargs=2, default=None,
                        metavar=("T_MIN_S", "T_MAX_S"),
                        help="isolate the intervention clock interval in "
                             "both runs (required for short pulses)")
    args = parser.parse_args()
    try:
        control_doc = json.loads(args.control.read_text(encoding="utf-8"))
        kwargs: dict[str, Any] = {"days": args.days,
                                  "trout_species": args.species}
        if args.pulse:
            pulse_doc = json.loads(args.pulse.read_text(encoding="utf-8"))
            window = tuple(args.window) if args.window else None
            document = compare_runs(control_doc, pulse_doc, window,
                                    **kwargs)
        else:
            landscape = thermal_landscape(control_doc)
            document = run_foodweb(landscape, **kwargs)
        write_json_atomic(args.out, document)

    except (ValueError, KeyError, ArithmeticError, OSError) as error:
        parser.exit(2, f"aquatic foodweb failed: {error}\n")
    if "refuge_shift_m" in document:
        print(f"refuge shift: {document['refuge_shift_m']} m "
              f"(control s={document['control']['s_m']:.0f} m @ "
              f"{document['control']['temperature_c']} C -> pulse "
              f"s={document['pulse']['s_m']:.0f} m @ "
              f"{document['pulse']['temperature_c']} C)")
    else:
        print(f"refuge: {document['trout']['cell_id']} "
              f"s={document['trout']['s_m']:.0f} m @ "
              f"{document['trout']['temperature_c']} C")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
