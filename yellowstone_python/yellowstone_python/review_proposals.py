"""Machine review gate for planting proposals to placement_overrides.json.
Checks: thermal/water exclusion, slope cap, suitability floor, pairwise spacing, existing-stand proximity."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .common.provenance import default_world_root, sha256_file
from .pool_crust import build_all as build_shells
from .pool_crust import in_apron, in_water
from .vegetation import GUILDS, guild_suitability, moisture_at, terrain_fns
from .vegetation import load_terrain

PKG_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORLD = str(default_world_root())


def _finite(name: str, value) -> float:
    """Finite float or raise, so NaN cannot make a comparison always-False."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, not boolean")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number ({exc})") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def review(proposals: list, shells: list, sample, slope, trees: list,
           moisture_fn, canopy: float = 0.6,
           min_existing_m: float = 2.0,
           suitability_threshold: float = 0.12,
           existing_overrides: list | None = None,
           constraints=None) -> tuple[list, list]:
    """Run machine gates; return (accepted, ledger).
    constraints: optional object with excluded(x, z) -> bool, run after apron/water."""
    _finite("suitability_threshold", suitability_threshold)
    _finite("canopy", canopy)
    if constraints is not None and not callable(getattr(constraints,
                                                        "excluded", None)):
        raise TypeError(
            "constraints must expose an excluded(x, z) -> bool method")
    seen: set[str] = set()
    for rec in proposals:
        sid_value = rec.get("stable_id")
        if sid_value is None:
            continue
        sid_text = str(sid_value)
        if sid_text in seen:
            raise ValueError(f"duplicate proposal stable_id {sid_text!r}")
        seen.add(sid_text)
    accepted, ledger = [], []
    # kept carries (x, z, guild); pairwise separation uses the max of both guilds' min spacing.
    kept: list[tuple[float, float, str]] = []
    for override in existing_overrides or []:
        pos = override.get("position")
        if not isinstance(pos, (list, tuple)) or len(pos) < 3:
            continue
        try:
            ox = float(pos[0])
            oz = float(pos[2])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(ox) or not math.isfinite(oz):
            continue
        kind = override.get("kind")
        guild = {"pine": "lodgepole_pine",
                 "grass": "meadow_grass"}.get(kind, "lodgepole_pine")
        kept.append((ox, oz, guild))
    for rec in proposals:
        required = ("stable_id", "guild", "x", "z")
        missing = [k for k in required if k not in rec]
        if missing:
            ledger.append({"stable_id": rec.get("stable_id", "?"),
                           "decision": "reject",
                           "reason": f"missing fields {missing}"})
            continue
        sid = rec["stable_id"]
        guild = rec["guild"]

        def reject(reason, sid=sid):
            ledger.append({"stable_id": sid, "decision": "reject",
                           "reason": reason})

        if guild not in GUILDS:
            reject(f"unknown guild {guild!r}")
            continue
        g = GUILDS[guild]
        try:
            x = _finite("x", rec["x"])
            z = _finite("z", rec["z"])
        except ValueError as exc:
            reject(str(exc))
            continue
        if any(in_apron(x, z, s) or in_water(x, z, s) for s in shells):
            reject("thermal/water exclusion")
            continue
        if constraints is not None and constraints.excluded(x, z):
            reject("placement constraints exclusion")
            continue
        try:
            sl = _finite("slope", slope(x, z))
        except ValueError as exc:
            reject(str(exc))
            continue
        if sl > g["slope_max_deg"]:
            reject(f"slope {sl:.1f} deg > {g['slope_max_deg']} deg")
            continue
        try:
            mo = _finite("moisture", moisture_fn(x, z))
            suit = _finite(
                "suitability",
                guild_suitability(guild, rec.get("habitat", "forest_edge"),
                                  sl, mo, canopy))
        except ValueError as exc:
            reject(str(exc))
            continue
        if suit < suitability_threshold:
            reject(f"suitability {suit:.3f} < {suitability_threshold}")
            continue
        pairwise_reject = False
        for kx, kz, kg in kept:
            min_sep = max(g["min_sep_m"], GUILDS[kg]["min_sep_m"])
            if math.hypot(x - kx, z - kz) < min_sep:
                reject(f"separation < {min_sep} m")
                pairwise_reject = True
                break
        if pairwise_reject:
            continue
        nearest = min(
            (math.hypot(x - t[0], z - t[1]) for t in trees),
            default=float("inf"))
        if nearest < min_existing_m:
            reject(f"existing tree {nearest:.1f} m away (same spot)")
            continue
        note = "infills existing stand" if nearest < 6.0 else "new canopy gap"
        kept.append((x, z, guild))
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
    guild = rec.get("guild")
    if guild not in KIND_BY_GUILD:
        raise ValueError(f"unknown guild for override record: {guild!r}")
    kind = KIND_BY_GUILD[guild]
    yaw = _finite("yaw", rec["yaw"])
    scale = _finite("scale", rec["scale"])
    if scale <= 0:
        raise ValueError("scale must be > 0")
    try:
        variation_key = int(rec["variation_key"])
    except (TypeError, ValueError) as exc:
        raise ValueError("variation_key must be integer-like") from exc
    x = _finite("x", rec["x"])
    z = _finite("z", rec["z"])
    y_f = _finite("y", y)
    return {"id": rec["stable_id"], "kind": kind,
            "position": [x, round(y_f, 3), z],
            "yaw": yaw, "scale": scale,
            "variant": variation_key % 4,
            "review": rec.get("author_note", "")}


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
        tmp = ov_path.with_name(ov_path.name + ".tmp")
        tmp.write_text(json.dumps(ov, indent=1) + "\n", encoding="utf-8")
        tmp.replace(ov_path)
        print(f"staged {added} new records into {ov_path} "
              f"(next Godot 4.5.1 bake consumes them; installed godot "
              f"is 4.4.1, bake deferred)")
    else:
        print("dry run; pass --apply to stage into placement_overrides.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
