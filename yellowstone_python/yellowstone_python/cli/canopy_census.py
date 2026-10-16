"""Command-line interface for canopy census."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic
import argparse
import json
import math
from pathlib import Path
import numpy as np
from yellowstone_python.common.provenance import default_world_root
from yellowstone_python.census.canopy_census import DETAIL_HALF, DETAIL_PATH, PX_M, density_stats, detect, exclude_pool_rims, load_detail, qa_census, render_overlay, to_world

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", default=DETAIL_PATH)
    ap.add_argument("--out", default="derived/census.json")
    ap.add_argument("--overlay", default=None)
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--qa", default=None,
                    help="self-check a census JSON file and exit (no imaging)")
    args = ap.parse_args()

    if args.qa is not None:
        try:
            doc = json.loads(Path(args.qa).read_text())
        except (OSError, ValueError) as exc:
            print(f"qa-unreadable: {args.qa}: {exc}")
            return 1
        failures = qa_census(doc)
        for f in failures:
            print(f"qa-rule: {f}")
        print(f"qa: {len(doc.get('trees', []))} trees, "
              f"{len(failures)} violation(s)")
        return 1 if failures else 0

    rgb = load_detail(args.detail)
    img_h, img_w = rgb.shape[:2]
    records = to_world(detect(rgb), width=img_w, height=img_h)
    records, dropped_rim = exclude_pool_rims(records)
    doc = {"schema": "yellowstone.canopy_census.v1",
           "source": {"image": args.detail, "acquired": "2022-07-19",
                      "agency": "USDA NAIP via USGS",
                      "extent_m": [-DETAIL_HALF, -DETAIL_HALF,
                                   DETAIL_HALF, DETAIL_HALF],
                      "px_m": PX_M},
           "status": "detection unreviewed; not a placement authority",
           "n": len(records),
           "dropped_rim": dropped_rim,
           "trees": records}
    if args.stats:
        doc["density"] = density_stats(records, {
            "spring_0_50m": {"circle": (-94.7, -10.6, 50.0)},
            "apron_50_100m": {"ring": (-94.7, -10.6, 50.0, 100.0)},
            "transition_100_200m": {"ring": (-94.7, -10.6, 100.0, 200.0)},
            "outwash_200_400m": {"ring": (-94.7, -10.6, 200.0, 400.0)},
            "overlook_knoll_r120": {"circle": (-252.0, 159.0, 120.0)},
            "detail_full": {"box": (-640.0, -640.0, 640.0, 640.0)},
        })
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(out, doc, indent=1)
    print(f"census: {len(records)} trees -> {out}")
    if args.overlay:
        render_overlay(rgb, [dict(r, ix=int(r["stable_id"].split("_")[1]),
                             iz=int(r["stable_id"].split("_")[2]))
                            for r in records], args.overlay)
        print(f"overlay -> {args.overlay}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
