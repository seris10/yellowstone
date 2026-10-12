"""Build the LLM analysis store (SQLite) from one build dir + obs inputs.

Derived artifacts are history: the default output is a NEW file per build
(derived/analysis_<buildid>.sqlite), never an overwrite of an existing
store. Pass --out explicitly to choose another path.

Usage:
    python3 tools/build_store.py --build derived/574c6165b5e9
    python3 tools/build_store.py --build derived/574c6165b5e9 \
        --census derived/census.json \
        --firehole derived/firehole_obs.json \
        --snotel derived/snotel_obs.json \
        --reach-fit derived/reach_heat_fit_v300k.json \
        --snow-fit derived/snow_degree_day_fit.json \
        --out derived/analysis.sqlite
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yellowstone_python.analysis_store import build_file  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", required=True,
                    help="build dir, e.g. derived/574c6165b5e9 "
                         "(must contain river_replay.json)")
    ap.add_argument("--census", default="derived/census.json")
    ap.add_argument("--firehole", default="derived/firehole_obs.json")
    ap.add_argument("--snotel", default="derived/snotel_obs.json")
    ap.add_argument("--reach-fit", dest="reach_fits", action="append",
                    default=[], help="repeatable; empty -> fits tables "
                    "empty with a meta note, never an error")
    ap.add_argument("--snow-fit", dest="snow_fits", action="append",
                    default=[])
    ap.add_argument("--out", default=None,
                    help="default: derived/analysis_<buildid>.sqlite")
    args = ap.parse_args()

    build_dir = Path(args.build)
    if not build_dir.is_dir():
        ap.error(f"--build {build_dir} is not a directory")
    if not (build_dir / "river_replay.json").exists():
        ap.error(f"{build_dir}/river_replay.json missing")
    for label, p in (("--census", args.census),
                     ("--firehole", args.firehole),
                     ("--snotel", args.snotel),
                     *[(f"--reach-fit", f) for f in args.reach_fits],
                     *[(f"--snow-fit", f) for f in args.snow_fits]):
        if not Path(p).exists():
            ap.error(f"{label} {p} not found")
    out = Path(args.out) if args.out else \
        Path("derived") / f"analysis_{build_dir.name}.sqlite"
    try:
        summary = build_file(
            build_dir=build_dir, out=out,
            census_path=Path(args.census), firehole_path=Path(args.firehole),
            snotel_path=Path(args.snotel),
            reach_fit_paths=[Path(p) for p in args.reach_fits],
            snow_fit_paths=[Path(p) for p in args.snow_fits])
    except FileExistsError as exc:
        ap.error(str(exc))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
