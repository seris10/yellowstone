"""Command-line interface for review proposals."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic
from yellowstone_python.common.checks import (finite as _finite)
import argparse
import json
import math
from pathlib import Path
from yellowstone_python.common.provenance import default_world_root, sha256_file
from yellowstone_python.thermal_features.pool_crust import build_all as build_shells
from yellowstone_python.thermal_features.pool_crust import in_apron, in_water
from yellowstone_python.land.vegetation import GUILDS, guild_suitability, moisture_at, terrain_fns
from yellowstone_python.land.vegetation import load_terrain
from yellowstone_python.authoring.review_proposals import DEFAULT_WORLD, review, to_override_record

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proposal", required=True)
    ap.add_argument("--world", default=DEFAULT_WORLD)
    ap.add_argument("--apply", action="store_true",
                    help="write placement_overrides.json (default: dry run)")
    args = ap.parse_args()
    world = Path(args.world)
    prop = json.loads(Path(args.proposal).read_text(encoding="utf-8"))
    proposals = prop["proposals"]
    world_json = world / "data" / "world.json"
    terrain_path = world / "data" / "terrain.f32"
    placements_path = world / "data" / "placements.json"
    ecosystem_path = world / "data" / "ecosystem.json"
    overrides_path = world / "data" / "placement_overrides.json"
    w = json.loads(world_json.read_text(encoding="utf-8"))
    shells = build_shells(w["pools"])
    sample, slope = terrain_fns(load_terrain(str(terrain_path)))
    place = json.loads(placements_path.read_text(encoding="utf-8"))
    trees = [(t["position"][0], t["position"][2]) for t in place["trees"]]
    patches = json.loads(
        ecosystem_path.read_text(encoding="utf-8"))["patches"]
    existing_overrides: list = []
    if overrides_path.is_file():
        try:
            ov_doc = json.loads(overrides_path.read_text(encoding="utf-8"))
            if isinstance(ov_doc, dict):
                existing_overrides = list(ov_doc.get("add", []))
        except json.JSONDecodeError:
            existing_overrides = []
    accepted, ledger = review(
        proposals, shells, sample, slope, trees,
        lambda x, z: moisture_at(x, z, patches),
        existing_overrides=existing_overrides)
    print(f"accepted {len(accepted)}/{len(proposals)}")
    ecosystem_sha256 = sha256_file(ecosystem_path)
    print(f"ecosystem_source: {ecosystem_path} sha256={ecosystem_sha256}")
    for row in ledger:
        if row["decision"] == "reject":
            print("  REJECT", row["stable_id"], "-", row["reason"])
    if args.apply:
        ov_path = overrides_path
        ov = (json.loads(ov_path.read_text(encoding="utf-8"))
              if ov_path.is_file() else {})
        have = {r["id"] for r in ov.get("add", [])}
        added = 0
        for rec in accepted:
            if rec["stable_id"] in have:
                continue
            ov.setdefault("add", []).append(
                to_override_record(
                    rec, sample(float(rec["x"]), float(rec["z"]))))
            added += 1
        # Record the ecosystem.json sha256 the review was run against.
        ov["ecosystem_provenance"] = {
            "source": "data/ecosystem.json",
            "sha256": ecosystem_sha256,
        }
        write_json_atomic(ov_path, ov, indent=1)
        print(f"staged {added} new records into {ov_path} "
              f"(next Godot 4.5.1 bake consumes them; installed godot "
              f"is 4.4.1, bake deferred)")
    else:
        print("dry run; pass --apply to stage into placement_overrides.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
