"""CLI for terrain hash, dimensions, range, and axis checks."""
import argparse
import json
from pathlib import Path

from yellowstone_python.common.io import write_json_atomic as _shared_json_write
from yellowstone_python.validation.terrain import (
    DEFAULT_MAX_M, DEFAULT_MIN_M, _resolve_terrain, guard_terrain,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terrain", default=None)
    parser.add_argument("--expect-sha256", default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--min-m", type=float, default=DEFAULT_MIN_M)
    parser.add_argument("--max-m", type=float, default=DEFAULT_MAX_M)
    parser.add_argument("--require-datum", action="store_true",
                        help="fail when vertical datum is not documented")
    parser.add_argument("--datum-status", default=None,
                        help="override vertical datum status")
    args = parser.parse_args()
    path = _resolve_terrain(args.terrain)
    expect = args.expect_sha256
    if expect is None:
        resolved = path.resolve()
        here = resolved if resolved.is_dir() else resolved.parent
        for parent in [here, *here.parents]:
            build_json = parent / "BUILD.json"
            if not build_json.exists():
                continue
            try:
                deps = json.loads(build_json.read_text()).get("deps", {})
            except (OSError, ValueError):
                continue
            match = deps.get("terrain.f32")
            if isinstance(match, dict):
                dep_path = match.get("path")
                if dep_path and str(resolved) != str(
                        (parent / dep_path).resolve()):
                    continue
                expect = match.get("sha256")
            elif isinstance(match, str):
                expect = match
            if expect is not None:
                break
    try:
        report = guard_terrain(path, expect, args.min_m, args.max_m,
                               require_datum=args.require_datum,
                               datum_status=args.datum_status)
    except ValueError as exc:
        parser.error(str(exc))
    if args.out is not None:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            _shared_json_write(args.out, report)
        except OSError as exc:
            print(json.dumps(report, indent=2, allow_nan=False))
            print(f"report-unwritable: {args.out}: {exc}")
            return 1
    for g in report["guards"]:
        print(("PASS" if g["passed"] else "FAIL") + f" {g['name']}: "
              f"{g['detail']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
