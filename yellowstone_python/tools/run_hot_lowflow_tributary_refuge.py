"""Hot low-flow with tributary cold-refuge pockets (landscape-level).

Re-runs the hot-vs-control foodweb comparison at D1 with two cold
tributary mouth-pocket cells (Rabbit Creek s~=1260 m, Mallard Creek
s~=35 m, map-measured confluences; authored 11 C scenario temperatures)
appended to BOTH landscapes, plus temperature and habitat-area
sensitivity sweeps to find the flip thresholds.

Design notes (minimal honest):
  - Pockets are LANDSCAPE cells (aquatic_foodweb.append_tributary_cells),
    never replay cells/frames: the 1-D solver's heat/water budget
    closure is untouched. Control and pulse rank the same choice set.
  - Inputs are the FROZEN replays (pinned baseline control + hot pulse);
    the replay solver is not re-run because its code path is unchanged.
  - Every pocket assumption carries authored provenance on the cell.

Usage:
    python3 tools/run_hot_lowflow_tributary_refuge.py \
        --control derived/8b9199d0fb0a/river_replay.json \
        --pulse derived/hot_lowflow_replay.json \
        --out derived/aquatic_hot_lowflow_tributary_refuge.json \
        --out-sweep derived/aquatic_tributary_sweep.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yellowstone_python.aquatic_foodweb import (
    TRIBUTARY_CANDIDATES,
    TRIBUTARY_FOOD_SCALE_DEFAULT,
    build_tributary_cell,
    compare_runs,
)
from yellowstone_python.insects_birds import trout_diet_at_temp

TEMP_SWEEP_C = (8.0, 11.0, 14.0, 17.0, 20.0, 23.0, 26.0)
SIZE_SWEEP_SCALE = (0.0, 0.01, 0.05, 0.2, 1.0)


def summarize(document: dict, trib_temp_c, food_scale) -> dict:
    """One sweep row: refuge outcome + diet + emergence + dipper."""
    pulse = document["pulse"]
    diet = trout_diet_at_temp(pulse["temperature_c"])
    return {
        "trib_temp_c": trib_temp_c,
        "food_scale": food_scale,
        "control_cell": document["control"]["cell_id"],
        "control_s_m": round(document["control"]["s_m"], 1),
        "control_temp_c": document["control"]["temperature_c"],
        "control_U": document["control"]["U"],
        "pulse_cell": pulse["cell_id"],
        "pulse_s_m": round(pulse["s_m"], 1),
        "pulse_temp_c": pulse["temperature_c"],
        "pulse_U": pulse["U"],
        "pulse_feeding": pulse["feeding"],
        "pulse_refuge_drive": pulse["refuge_drive"],
        "flipped_to_tributary": pulse["cell_id"].startswith("trib_"),
        "refuge_shift_m": document["refuge_shift_m"],
        "diet_benthic_share": round(diet["benthic"], 3),
        "diet_emergent_share": round(diet["emergent"], 3),
        "emergence_change": document["emergence_change"],
        "dipper_intake_change": document["dipper_intake_change"],
    }


def run_case(control_doc, pulse_doc, specs, trib_temp_c, food_scale,
             days, species) -> dict:
    extra = [build_tributary_cell(s, temperature_c=trib_temp_c,
                                  food_scale=food_scale) for s in specs]
    document = compare_runs(control_doc, pulse_doc, extra_cells=extra,
                            days=days, trout_species=species)
    return document, summarize(document, trib_temp_c, food_scale)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path,
                        default=Path("derived/8b9199d0fb0a/river_replay.json"))
    parser.add_argument("--pulse", type=Path,
                        default=Path("derived/hot_lowflow_replay.json"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--out-sweep", type=Path, required=True)
    parser.add_argument("--days", type=float, default=14.0)
    parser.add_argument("--species", default="brown_trout")
    args = parser.parse_args()

    control_doc = json.loads(args.control.read_text(encoding="utf-8"))
    pulse_doc = json.loads(args.pulse.read_text(encoding="utf-8"))
    specs = list(TRIBUTARY_CANDIDATES)

    # Main comparison at defaults (spec 11 C, area-ratio food scale).
    document, _ = run_case(control_doc, pulse_doc, specs, None,
                           TRIBUTARY_FOOD_SCALE_DEFAULT,
                           args.days, args.species)
    document["scenario"] = {
        "baseline": "hot low-flow (2.5 m3/s, 26 C boundary) vs pinned "
                    "control (8.0 m3/s, 17.5 C), D1 dispersion",
        "baseline_provenance": "frozen_replays_control_8b9199d0fb0a_"
                               "pulse_hot_lowflow_replay",
        "tributary_cells": [
            {"id": s["cell_id"], "confluence_s_m": s["confluence_s_m"],
             "temperature_c": s["temperature_c"],
             "food_scale": TRIBUTARY_FOOD_SCALE_DEFAULT,
             "confluence_provenance": s["confluence_provenance"],
             "temperature_provenance": s["temperature_provenance"]}
            for s in specs],
        "refuge_threshold_c": 24.0,
        "refuge_threshold_provenance": "measured_Kaya_Kaeding_Burkhalter_1977",
        "design": ("landscape_level_pockets_both_landscapes_solver_"
                   "untouched_off_channel_holding_water"),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text(json.dumps(document, indent=1, allow_nan=False) + "\n",
                   encoding="utf-8")
    tmp.replace(args.out)

    # Sensitivity sweeps: temperature at fixed size, size at fixed temp.
    temp_rows = []
    for temp in TEMP_SWEEP_C:
        _, row = run_case(control_doc, pulse_doc, specs, temp,
                          TRIBUTARY_FOOD_SCALE_DEFAULT,
                          args.days, args.species)
        temp_rows.append(row)
    size_rows = []
    for scale in SIZE_SWEEP_SCALE:
        _, row = run_case(control_doc, pulse_doc, specs, None,
                          scale, args.days, args.species)
        size_rows.append(row)
    # N=1 variant (Rabbit Creek only) at defaults.
    _, single = run_case(control_doc, pulse_doc, specs[:1], None,
                         TRIBUTARY_FOOD_SCALE_DEFAULT,
                         args.days, args.species)
    sweep = {
        "schema": "yellowstone.aquatic_tributary_sweep.v1",
        "status": "illustrative_not_calibrated",
        "days": args.days,
        "trout_species": args.species,
        "temperature_sweep_at_default_size": temp_rows,
        "size_sweep_at_spec_temp": size_rows,
        "single_pocket_rabbit_only_at_defaults": single,
        "provenance": {
            "pockets": "TRIBUTARY_CANDIDATES_map_measured_confluences_"
                       "authored_11C_scenario_temps",
            "food_scale_default": TRIBUTARY_FOOD_SCALE_DEFAULT,
            "food_scale_meaning": "authored_area_ratio_22m2_pocket_over_"
                                  "440m2_mainstem_cell",
        },
    }
    tmp = args.out_sweep.with_name(args.out_sweep.name + ".tmp")
    tmp.write_text(json.dumps(sweep, indent=1, allow_nan=False) + "\n",
                   encoding="utf-8")
    tmp.replace(args.out_sweep)

    print(f"main: control {document['control']['cell_id']} "
          f"s={document['control']['s_m']:.0f} U={document['control']['U']} "
          f"-> pulse {document['pulse']['cell_id']} "
          f"s={document['pulse']['s_m']:.0f} @ "
          f"{document['pulse']['temperature_c']} C "
          f"U={document['pulse']['U']} "
          f"(shift {document['refuge_shift_m']:.1f} m)")
    print("temp sweep (T -> pulse cell, U, drive):")
    for row in temp_rows:
        print(f"  trib {row['trib_temp_c']:>4}C -> {row['pulse_cell']} "
              f"U={row['pulse_U']:>7} drive={row['pulse_refuge_drive']} "
              f"flip={row['flipped_to_tributary']}")
    print("size sweep (scale -> pulse cell, U):")
    for row in size_rows:
        print(f"  scale {row['food_scale']:>4} -> {row['pulse_cell']} "
              f"U={row['pulse_U']:>7} "
              f"flip={row['flipped_to_tributary']}")
    print(f"single pocket (rabbit only): {single['pulse_cell']} "
          f"s={single['pulse_s_m']:.0f} U={single['pulse_U']}")
    print(f"Wrote {args.out}\nWrote {args.out_sweep}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
