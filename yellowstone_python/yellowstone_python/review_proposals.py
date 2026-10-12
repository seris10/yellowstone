"""Machine review gate for planting proposals → placement_overrides.json.

Automated checks (ledger records every decision):
  1. thermal/water exclusion re-verified with polygon math (belt and braces)
  2. slope ≤ guild maximum from the real DEM
  3. suitability ≥ threshold (recomputed, not trusted from proposal)
  4. pairwise separation ≥ guild minimum (recomputed)
  5. existing-stand proximity: <2 m reject (same spot), 2–6 m accept as infill

Still required by a human: NAIP eyeball check of each accepted transform
(see ledger). Never touches placements.json or the baked scene; the next
Godot 4.5.1 bake consumes placement_overrides.json::{add}.

Usage:
    python -m yellowstone_python.review_proposals --proposal derived/<id>/planting_proposal.json --apply
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .common.provenance import default_world_root
from .pool_crust import build_all as build_shells
from .pool_crust import in_apron
from .vegetation import GUILDS, guild_suitability, moisture_at, terrain_fns
from .vegetation import load_terrain

PKG_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORLD = str(default_world_root())


def review(proposals: list, shells: list, sample, slope, trees: list,
           moisture_fn, canopy: float = 0.6,
           min_existing_m: float = 2.0,
           suitability_threshold: float = 0.12) -> tuple[list, list]:
    for _name, _val in (("suitability_threshold", suitability_threshold),
                        ("canopy", canopy)):
        if isinstance(_val, bool):
            raise ValueError(f"{_name} must be a number, not boolean")
        try:
            _f = float(_val)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{_name} must be a number ({exc})") from exc
        if not math.isfinite(_f):
            # NaN would make every `suit < threshold` comparison False and
            # silently accept everything below; fail closed instead.
            raise ValueError(f"{_name} must be finite")
    accepted, ledger = [], []
    kept = []
    for rec in proposals:
        sid = rec["stable_id"]
        guild = rec["guild"]
        g = GUILDS[guild]
        x, z = float(rec["x"]), float(rec["z"])

        def reject(reason):
            ledger.append({"stable_id": sid, "decision": "reject",
                           "reason": reason})

        if any(in_apron(x, z, s) for s in shells):
            reject("thermal/water exclusion"); continue
        sl = slope(x, z)
        if sl > g["slope_max_deg"]:
            reject(f"slope {sl:.1f}° > {g['slope_max_deg']}°"); continue
        suit = guild_suitability(guild, rec.get("habitat", "forest_edge"),
                                 sl, moisture_fn(x, z), canopy)
        if suit < suitability_threshold:
            reject(f"suitability {suit:.3f} < {suitability_threshold}"); continue
        if any(math.hypot(x - kx, z - kz) < g["min_sep_m"] for kx, kz in kept):
            reject(f"separation < {g['min_sep_m']} m"); continue
        nearest = min(([math.hypot(x - t[0], z - t[1]) for t in trees]),
                      default=float("inf"))
        if nearest < min_existing_m:
            reject(f"existing tree {nearest:.1f} m away (same spot)"); continue
        note = "infills existing stand" if nearest < 6.0 else "new canopy gap"
        kept.append((x, z))
        accepted.append(rec)
        ledger.append({"stable_id": sid, "decision": "accept",
                       "suitability": round(suit, 3),
                       "slope_deg": round(sl, 1),
                       "nearest_existing_m": round(nearest, 1), "note": note})
    return accepted, ledger


KIND_BY_GUILD = {"lodgepole_pine": "pine", "meadow_grass": "grass",
                   "riparian_sedge": "grass"}


def to_override_record(rec: dict, y: float) -> dict:
    """Bake-consumed schema: {id, kind, position, yaw, scale, variant}."""
    kind = KIND_BY_GUILD.get(rec.get("guild", ""), "pine")
    return {"id": rec["stable_id"], "kind": kind,
            "position": [rec["x"], round(y, 3), rec["z"]],
            "yaw": rec["yaw"], "scale": rec["scale"],
            "variant": int(rec["variation_key"]) % 4,
            "review": rec.get("author_note", "")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proposal", required=True)
    ap.add_argument("--world", default=DEFAULT_WORLD)
    ap.add_argument("--apply", action="store_true",
                    help="write placement_overrides.json (default: dry run)")
    args = ap.parse_args()
    world = Path(args.world)
    prop = json.loads(Path(args.proposal).read_text())
    proposals = prop["proposals"]
    w = json.loads((world / "data" / "world.json").read_text())
    shells = build_shells(w["pools"])
    sample, slope = terrain_fns(load_terrain(str(world / "data" / "terrain.f32")))
    place = json.loads((world / "data" / "placements.json").read_text())
    trees = [(t["position"][0], t["position"][2]) for t in place["trees"]]
    patches = json.loads((world / "data" / "ecosystem.json").read_text())["patches"]
    accepted, ledger = review(proposals, shells, sample, slope, trees,
                              lambda x, z: moisture_at(x, z, patches))
    print(f"accepted {len(accepted)}/{len(proposals)}")
    for row in ledger:
        if row["decision"] == "reject":
            print("  REJECT", row["stable_id"], "-", row["reason"])
    if args.apply:
        ov_path = world / "data" / "placement_overrides.json"
        ov = json.loads(ov_path.read_text())
        have = {r["id"] for r in ov.get("add", [])}
        added = 0
        for rec in accepted:
            if rec["stable_id"] in have:
                continue
            ov.setdefault("add", []).append(
                to_override_record(rec, sample(float(rec["x"]), float(rec["z"]))))
            added += 1
        ov_path.write_text(json.dumps(ov, indent=1))
        print(f"staged {added} new records into {ov_path} "
              f"(next Godot 4.5.1 bake consumes them; installed godot is 4.4.1, bake deferred)")
    else:
        print("dry run; pass --apply to stage into placement_overrides.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
