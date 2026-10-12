"""Guard terrain.f32 (hash/dims/range) against BUILD deps.

BUILD records only the sha256 of terrain.f32 (build.py deps); this tool
checks size, grid, value range, and hash before a build trusts the file.
See tooling-spec-check-terrain.md.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCHEMA_GUARD = "yellowstone.terrain_guard.v1"

GRID = 1025
N_ELEMS = GRID * GRID
N_BYTES = N_ELEMS * 4
DTYPE = "<f4"

# Tripwires containing the measured envelope (min -10.89, max 238.13,
# p1 -5.09, p99 221.28). Datum undocumented: bounds are tripwires, not
# physical claims.
DEFAULT_MIN_M = -20.0
DEFAULT_MAX_M = 250.0


def _resolve_terrain(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("YELLOWSTONE_WORLD")
    if env:
        return Path(env) / "data" / "terrain.f32"
    cfg_path = Path(__file__).resolve().parents[1] / "configs" / \
        "baseline.yaml"
    try:
        import yaml
        cfg = yaml.safe_load(cfg_path.read_text())
        return Path(cfg["world_root"]) / "data" / "terrain.f32"
    except Exception:
        from yellowstone_python.common.provenance import default_world_root
        return default_world_root() / "data" / "terrain.f32"


def guard_terrain(path: Path, expect_sha256: str | None,
                  min_m: float, max_m: float) -> dict:
    """Read-only guard; returns the report dict (no I/O beyond the read)."""
    guards: list = []
    info: dict = {"path": str(path)}
    try:
        nbytes = path.stat().st_size
    except OSError as exc:
        return {"schema": SCHEMA_GUARD, "status": "authored_terrain_guard",
                "terrain": info, "expected_sha256": expect_sha256,
                "passed": False,
                "guards": [{"name": "terrain-readable", "passed": False,
                            "detail": f"terrain-unreadable: {path}: {exc}"}]}
    info["nbytes"] = nbytes
    if nbytes != N_BYTES:
        guards.append({"name": "size", "passed": False,
                       "detail": f"bad-size: expected {N_BYTES}, found "
                                 f"{nbytes}"})
        return {"schema": SCHEMA_GUARD, "status": "authored_terrain_guard",
                "terrain": info, "expected_sha256": expect_sha256,
                "passed": False, "guards": guards}
    guards.append({"name": "size", "passed": True,
                   "detail": f"{nbytes} bytes"})
    import numpy as np
    raw = np.fromfile(str(path), dtype=DTYPE)
    if raw.size != N_ELEMS:
        guards.append({"name": "grid", "passed": False,
                       "detail": f"bad-grid: expected {N_ELEMS} <f4 "
                                 f"elements, found {raw.size}"})
        return {"schema": SCHEMA_GUARD, "status": "authored_terrain_guard",
                "terrain": info, "expected_sha256": expect_sha256,
                "passed": False, "guards": guards}
    grid = raw.reshape(GRID, GRID)
    info.update({"dims": [GRID, GRID], "dtype": DTYPE,
                 "min_m": float(grid.min()), "max_m": float(grid.max()),
                 "mean_m": float(grid.mean())})
    guards.append({"name": "grid", "passed": True,
                   "detail": f"{GRID}x{GRID} {DTYPE}"})
    if info["min_m"] < min_m or info["max_m"] > max_m:
        guards.append({"name": "range", "passed": False,
                       "detail": f"range [{info['min_m']:.2f}, "
                                 f"{info['max_m']:.2f}] outside "
                                 f"[{min_m}, {max_m}]"})
    else:
        guards.append({"name": "range", "passed": True,
                       "detail": f"[{info['min_m']:.2f}, {info['max_m']:.2f}] "
                                 f"within [{min_m}, {max_m}]"})
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            sha.update(chunk)
    info["sha256"] = sha.hexdigest()
    if expect_sha256 is not None:
        if info["sha256"] != expect_sha256:
            guards.append({"name": "hash", "passed": False,
                           "detail": f"hash-mismatch: expected "
                                     f"{expect_sha256}, found "
                                     f"{info['sha256']}"})
        else:
            guards.append({"name": "hash", "passed": True,
                           "detail": info["sha256"][:12] + "..."})
    return {"schema": SCHEMA_GUARD, "status": "authored_terrain_guard",
            "terrain": info, "expected_sha256": expect_sha256,
            "passed": all(g["passed"] for g in guards), "guards": guards}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terrain", default=None)
    parser.add_argument("--expect-sha256", default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--min-m", type=float, default=DEFAULT_MIN_M)
    parser.add_argument("--max-m", type=float, default=DEFAULT_MAX_M)
    args = parser.parse_args()
    path = _resolve_terrain(args.terrain)
    expect = args.expect_sha256
    if expect is None:
        # Cross-check against the enclosing build tree when run inside one.
        here = path if path.is_dir() else path.parent
        for parent in [here, *here.parents]:
            build_json = parent / "BUILD.json"
            if not build_json.exists():
                continue
            try:
                deps = json.loads(build_json.read_text()).get("deps", {})
                if deps.get("terrain.f32"):
                    expect = deps["terrain.f32"]
                    break
            except (OSError, ValueError):
                continue
    report = guard_terrain(path, expect, args.min_m, args.max_m)
    if args.out is not None:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            tmp = args.out.with_name(args.out.name + ".tmp")
            tmp.write_text(json.dumps(report, indent=2))
            tmp.replace(args.out)
        except OSError as exc:
            print(json.dumps(report, indent=2))
            print(f"report-unwritable: {args.out}: {exc}")
            return 1
    for g in report["guards"]:
        print(("PASS" if g["passed"] else "FAIL") + f" {g['name']}: "
              f"{g['detail']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
