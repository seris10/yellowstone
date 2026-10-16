"""Command-line interface for gen flora."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic
import argparse
import json
import math
import random
from yellowstone_python.common.provenance import default_world_root
from yellowstone_python.thermal_features.pool_crust import build_all as build_shells
from yellowstone_python.thermal_features.pool_crust import in_apron as _in_apron
from yellowstone_python.authoring.review_proposals import review, to_override_record
from yellowstone_python.land.vegetation import HALF, load_terrain, moisture_at, terrain_fns
from yellowstone_python.land.vegetation import propose_plantings_reviewed
from yellowstone_python.authoring.gen_flora import PlacementConstraints, REGIONS, WORLD, canopy_driven_forest, corridor_flora, deck_viewshed_groves, forest_infill, grove_planting, override_id

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--regions", action="store_true")
    ap.add_argument("--forest-infill", action="store_true")
    ap.add_argument("--corridor-flora", action="store_true")
    ap.add_argument("--grove", action="store_true")
    ap.add_argument("--deck-groves", action="store_true")
    ap.add_argument("--measured-canopy", action="store_true",
                    help="derive dominant-tree placements from the verified LiDAR coverage")
    args = ap.parse_args()
    from pathlib import Path
    measured = Path(__file__).resolve().parents[2] / "derived/lidar_canopy/canopy_height.provenance.json"
    explicit = any([args.regions, args.forest_infill, args.corridor_flora, args.grove, args.deck_groves])
    if args.measured_canopy or (measured.is_file() and not explicit):
        result = canopy_driven_forest(apply=args.apply)
        print(f"observed dominant crowns: {result['n_dominant']}; applied={result['applied']}")
        return 0

    world = json.loads((WORLD / "data" / "world.json").read_text())
    shells = build_shells(world["pools"])
    sample, slope = terrain_fns(load_terrain(str(WORLD / "data" / "terrain.f32")))
    place = json.loads((WORLD / "data" / "placements.json").read_text())
    trees = [(t["position"][0], t["position"][2]) for t in place["trees"]]
    ov0 = json.loads((WORLD / "data" / "placement_overrides.json").read_text())
    trees += [(r["position"][0], r["position"][2]) for r in ov0.get("add", [])
              if r.get("kind") == "pine"]
    patches = json.loads((WORLD / "data" / "ecosystem.json.pre-python").read_text())["patches"]
    # River and route point sets for the shared constraints gate.
    river_pts: list[tuple[float, float]] = []
    river_hw: list[float] = []
    for riv in world.get("rivers", []):
        hw = float(riv.get("width", 22.0)) / 2.0 + 4.0
        for pt in riv.get("points", []):
            river_pts.append((float(pt[0]), float(pt[2])))
            river_hw.append(hw)
    route_pts: list[tuple[float, float, float]] = []
    for rt in world.get("routes", []):
        rw = 8.0 if rt.get("kind") == "road" else 5.0
        for pt in rt.get("points", [])[::4]:
            route_pts.append((float(pt[0]), float(pt[2]), rw))
    pc = PlacementConstraints(shells=shells, patches=patches, trees=trees,
                              river_pts=river_pts, river_hw=river_hw,
                              route_pts=route_pts, ortho_data=None)
    excluded = pc.excluded

    staged, total_log = [], []
    run_all = not any([args.regions, args.forest_infill, args.corridor_flora,
                       args.grove, args.deck_groves])
    if run_all or args.regions:
        for reg in REGIONS:
            accepted, _rlog = propose_plantings_reviewed(
                reg["guild"], tuple(reg["center"]), reg["radius"], reg["count"],
                reg["seed"], habitat_id=reg["habitat"], exclusion_test=excluded,
                terrain_fn=(sample, slope), patches=patches,
                canopy=reg["canopy"], suitability_threshold=reg["threshold"],
                constraints=pc)
            ok, ledger = review(accepted, shells, sample, slope, trees,
                                lambda x, z: moisture_at(x, z, patches),
                                canopy=reg["canopy"],
                                min_existing_m=reg["min_existing_m"],
                                suitability_threshold=reg["threshold"],
                                constraints=pc)
            rej = sum(1 for r in ledger if r["decision"] == "reject")
            print(f"{reg['guild']} @ {reg['center']}: {len(ok)}/{len(accepted)} "
                  f"staged ({rej} machine-rejected)")
            staged.extend(ok)
            total_log.extend(ledger)
    if args.forest_infill:
        extra, _ = forest_infill()
        print(f"forest_infill: {len(extra)} candidates")
        staged.extend(extra)
    if args.corridor_flora:
        extra, _ = corridor_flora()
        print(f"corridor_flora: {len(extra)} candidates")
        staged.extend(extra)
    if args.grove:
        extra, _ = grove_planting()
        print(f"grove_planting: {len(extra)} candidates")
        staged.extend(extra)
    if args.deck_groves:
        extra, _ = deck_viewshed_groves()
        print(f"deck_viewshed_groves: {len(extra)} candidates")
        staged.extend(extra)

    print(f"TOTAL staged: {len(staged)}")
    if args.apply:
        ov_path = WORLD / "data" / "placement_overrides.json"
        ov = json.loads(ov_path.read_text())
        have = {override_id(r) for r in ov.get("add", []) if override_id(r) is not None}
        added = 0
        for rec in staged:
            sid = override_id(rec)
            if sid in have:
                continue
            ov.setdefault("add", []).append(to_override_record(rec, rec["y"]))
            added += 1
        write_json_atomic(ov_path, ov, indent=1)
        print(f"staged {added} new records into {ov_path}")
    else:
        print("dry run; pass --apply to stage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
