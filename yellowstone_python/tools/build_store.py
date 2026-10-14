"""SQLite analysis-store construction from build and observation inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from yellowstone_python.service.analysis_store import build_file  # noqa: E402


from yellowstone_python.common.io import sha256_file as _sha256


def _collect_build_shas(build_dir: Path) -> dict:
    """Return a basename to sha256 map harvested from BUILD.json entries."""
    build_json = build_dir / "BUILD.json"
    if not build_json.exists():
        return {}
    try:
        doc = json.loads(build_json.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict = {}

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str) and len(value) == 64 and \
                        all(c in "0123456789abcdef" for c in value):
                    out.setdefault(Path(key).name, value)
                else:
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    for key in ("source_shas", "deps"):
        if key in doc:
            _walk(doc[key])
    return out


def _check_against_build(label: str, path: Path,
                         known: dict, warnings: list) -> str | None:
    """Return an error message when path's sha disagrees with BUILD.json."""
    recorded = known.get(path.name)
    if recorded is None:
        warnings.append(
            f"{label} {path}: not referenced by BUILD.json")
        return None
    if _sha256(path) != recorded:
        return (f"source-sha-mismatch: {label} {path} does not match "
                f"BUILD.json sha for basename {path.name!r}")
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", required=True,
                    help="build dir, e.g. derived/574c6165b5e9 "
                         "(must contain river_replay.json)")
    ap.add_argument("--census", default="derived/census.json")
    ap.add_argument("--firehole", default="derived/firehole_obs.json")
    ap.add_argument("--snotel", default="derived/snotel_obs.json")
    ap.add_argument("--reach-fit", dest="reach_fits", action="append",
                    default=[], help="repeatable; omit to leave fits_reach "
                    "and fits_reach_nulls empty with a meta note")
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
                     *[("--reach-fit", f) for f in args.reach_fits],
                     *[("--snow-fit", f) for f in args.snow_fits]):
        if not Path(p).exists():
            ap.error(f"{label} {p} not found")
    known_shas = _collect_build_shas(build_dir)
    warnings: list[str] = []
    for p in args.reach_fits:
        err = _check_against_build("--reach-fit", Path(p),
                                   known_shas, warnings)
        if err is not None:
            print(err, file=sys.stderr)
            return 2
    for p in args.snow_fits:
        err = _check_against_build("--snow-fit", Path(p),
                                   known_shas, warnings)
        if err is not None:
            print(err, file=sys.stderr)
            return 2
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
    except (json.JSONDecodeError, OSError, RuntimeError) as exc:
        print(f"build-failed: {exc}", file=sys.stderr)
        return 1
    for line in warnings:
        print(line)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
