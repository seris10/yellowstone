"""Command-line entry point for hot low-flow scenario comparisons."""
from __future__ import annotations

import argparse
from pathlib import Path

from yellowstone_python.scenarios import hot_lowflow as scenarios


def main(argv: list[str] | None = None) -> int:
    """Run a mainstem or tributary scenario subcommand."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("mainstem", "tributary-pockets", "measured-tributaries"):
        sub = subcommands.add_parser(name)
        sub.add_argument("--config", type=Path)
        sub.add_argument("--control", type=Path, required=True)
        sub.add_argument("--pulse", type=Path)
        sub.add_argument("--out", type=Path, required=True)
        sub.add_argument("--out-replay", type=Path)
        sub.add_argument("--boundary-m3s", type=float, default=scenarios.HOT_LOWFLOW_BOUNDARY_M3S)
        sub.add_argument("--boundary-c", type=float, default=scenarios.HOT_LOWFLOW_BOUNDARY_C)
        sub.add_argument("--dispersion-m2-s", type=float, default=1.0)
        sub.add_argument("--dispersion-provenance", default="solver_default")
        sub.add_argument("--days", type=float, default=14.0)
        sub.add_argument("--species", default="brown_trout")
        sub.add_argument("--settle-s", type=float, default=0.0)
        sub.add_argument("--sub-uilt", action="store_true")
        sub.add_argument("--plus-c", type=float, default=0.0)
        if name == "tributary-pockets":
            sub.add_argument("--out-sweep", type=Path, required=True)
            sub.add_argument("--out-single-pocket", type=Path)
        elif name == "measured-tributaries":
            sub.add_argument("--tributary-data", type=Path, required=True)
            sub.add_argument("--tributary-cells", type=int, default=2)
    args = parser.parse_args(argv)
    if args.pulse is None and args.config is None:
        parser.error("provide --config to build a pulse or --pulse to use a frozen replay")
    if args.command in ("mainstem", "measured-tributaries") and args.out_replay is None:
        parser.error("--out-replay is required for this subcommand")
    if args.pulse is not None and args.plus_c:
        parser.error("--plus-c requires a config-based solver run")
    runner = {"mainstem": scenarios.run_mainstem, "tributary-pockets": scenarios.run_pockets,
              "measured-tributaries": scenarios.run_measured}[args.command]
    try:
        result = runner(args)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(f"refuge shift: {result['refuge_shift_m']} m")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
