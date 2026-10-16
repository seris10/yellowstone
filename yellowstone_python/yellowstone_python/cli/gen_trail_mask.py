"""Trail mask command-line interface."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from yellowstone_python.authoring import gen_trail_mask as generator
from yellowstone_python.common.io import sha256_file
from yellowstone_python.common.provenance import resolve_code_rev, write_sidecar


def main(argv=None) -> int:
    """Write the metric trail mask and its provenance sidecar."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--size", type=int, default=generator.SIZE)
    parser.add_argument("--edge-softness-m", type=float, default=generator.EDGE_SOFTNESS_M)
    parser.add_argument("--supersample", type=int, default=generator.SUPERSAMPLE)
    args = parser.parse_args([] if argv is None else argv)
    world_root = (args.world or generator.WORLD).resolve()
    source = world_root / "data" / "world.json"
    world = json.loads(source.read_text())
    mask = generator.build_mask(world, size=args.size, edge_softness_m=args.edge_softness_m,
                                supersample=args.supersample)
    out = args.out or world_root / "assets" / "textures" / "trail_mask.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    mask.save(out)
    code_rev, revision_source = resolve_code_rev()
    relative = lambda path: Path(os.path.relpath(path, world_root)).as_posix()
    source_paths = [source, Path(generator.__file__), Path(__file__)]
    sources = [{"path": relative(path), "sha256": sha256_file(path)} for path in source_paths]
    trails = [r for r in world.get("routes", [])
              if r.get("kind") == "trail" and r.get("surface") != "Wood" and len(r.get("points", [])) >= 2]
    write_sidecar(out.with_suffix(".png.provenance.json"), {
        "schema": "yellowstone.trail_mask.v2", "run_mode": "illustrative",
        "code_rev_source": revision_source,
        "artifact": {"path": relative(out), "sha256": sha256_file(out)},
        "raster": {"width": args.size, "height": args.size, "pixel_m": 2.0 * generator.HALF / args.size,
                   "extent_m": [-generator.HALF, generator.HALF, -generator.HALF, generator.HALF],
                   "registration": "pixel centers; columns increase x; rows increase z"},
        "method": "subpixel mean of union coverage from metric segment distance and round caps",
        "trail_count": len(trails), "excluded_surfaces": ["Wood"],
    }, sources, {
        "route_width_m": "authored route widths retained from data/world.json; no minimum pixel width",
        "edge_softness_m": {"value": args.edge_softness_m, "value_class": "authored_illustrative",
                            "definition": "smoothstep transition centered on the route width boundary"},
        "supersample_per_axis": args.supersample,
    }, code_rev=code_rev, status="authored_illustrative")
    print(f"painted {len(trails)} trails at {2.0 * generator.HALF / args.size:g} m/pixel -> {out}")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
