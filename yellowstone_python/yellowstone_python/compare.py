"""A/B outcome comparison: quantify scenario response, not just config diff.

Reads two derived/ build dirs and reports endpoint outcome deltas:
reach temperatures/flows, trout holds/reaches, insect activity, snow
storage, phenology, heat-budget totals. Labeled as endpoint comparison of
final states — exposure-duration metrics need timestamped replays (Phase 3).

Usage:
    python -m yellowstone_python.compare derived/<A> derived/<B> [-o outcomes.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(d: Path, name: str):
    return json.loads((d / name).read_text())


def compare_builds(a_dir: str | Path, b_dir: str | Path) -> dict:
    a, b = Path(a_dir), Path(b_dir)
    ra = {r["id"]: r for r in _load(a, "river_state.json")}
    rb = {r["id"]: r for r in _load(b, "river_state.json")}
    reaches = []
    for rid in ra:
        reaches.append({"id": rid,
                        "d_temp_c": round(rb[rid]["temperature_c"] - ra[rid]["temperature_c"], 3),
                        "d_flow_m3s": round(rb[rid]["flow_m3s"] - ra[rid]["flow_m3s"], 4)})
    fa = {t["id"]: t for t in _load(a, "fish.json")["wildlife"]}
    fb = {t["id"]: t for t in _load(b, "fish.json")["wildlife"]}
    trout = [{"id": tid,
              "reach": (fa[tid].get("reach_id"), fb[tid].get("reach_id")),
              "d_hold_s": round(fb[tid]["hold_seconds"] - fa[tid]["hold_seconds"], 2),
              "relocated": fa[tid]["start_point_index"] != fb[tid]["start_point_index"]}
             for tid in fa]
    ia, ib = _load(a, "insect_bird.json"), _load(b, "insect_bird.json")
    sa, sb = _load(a, "season.json"), _load(b, "season.json")
    ma = {p["id"]: p for p in sa["patches"]}
    mb = {p["id"]: p for p in sb["patches"]}
    snow = [{"id": pid,
             "d_snow_mm": round(mb[pid]["snow_mm"] - ma[pid]["snow_mm"], 2),
             "phenology": (ma[pid]["phenology"], mb[pid]["phenology"])}
            for pid in ma]
    ca, cb = _load(a, "CHECKS.json")["metrics"], _load(b, "CHECKS.json")["metrics"]
    return {"A": a.name, "B": b.name,
            "reach_deltas": reaches, "trout": trout,
            "d_insect_activity": round(ib["activity"] - ia["activity"], 4),
            "snow": snow,
            "d_heat_budget_error": round(
                cb.get("heat_budget_error", 0.0)
                - ca.get("heat_budget_error", 0.0), 12),
            "scope": "endpoint comparison of final states; durations need replays"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("A")
    ap.add_argument("B")
    ap.add_argument("-o", "--output", default=None)
    args = ap.parse_args()
    out = compare_builds(args.A, args.B)
    text = json.dumps(out, indent=2)
    if args.output:
        Path(args.output).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
