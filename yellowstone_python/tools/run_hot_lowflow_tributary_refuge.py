"""Hot low-flow with tributary cold-refuge pockets at Rabbit Creek and Mallard Creek.
Includes temperature, size, and velocity-depth sweeps around the flip thresholds."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenario_constants import (  # noqa: E402
    REFUGE_THRESHOLD_C,
    REFUGE_THRESHOLD_SOURCE,
)
from yellowstone_python.aquatic_foodweb import (  # noqa: E402
    TRIBUTARY_CANDIDATES,
    TRIBUTARY_FOOD_SCALE_DEFAULT,
    build_tributary_cell,
    compare_runs,
)
from yellowstone_python.insects_birds import trout_diet_at_temp  # noqa: E402

TEMP_SWEEP_C = (8.0, 11.0, 14.0, 17.0, 20.0, 23.0, 24.0, 25.0, 26.0)
SIZE_SWEEP_SCALE = (0.0, 0.01, 0.05, 0.2, 1.0)
# Pocket velocity (m/s) and depth (m) triples for the hydraulic sweep.
VELOCITY_DEPTH_SWEEP = ((0.1, 0.3), (0.25, 0.5), (0.5, 1.0))
MODEL_SCOPE = (
    "selection_only_no_mortality_no_movement_cost_no_absolute_food"
)


def summarize(document: dict, trib_temp_c, food_scale,
              velocity_depth=None) -> dict:
    """One sweep row: refuge outcome, diet, emergence, dipper."""
    pulse = document["pulse"]
    diet = trout_diet_at_temp(pulse["temperature_c"])
    row = {
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
    if velocity_depth is not None:
        row["pocket_velocity_m_s"] = velocity_depth[0]
        row["pocket_depth_m"] = velocity_depth[1]
    return row


def run_case(control_doc, pulse_doc, specs, trib_temp_c, food_scale,
             days, species, velocity=None, depth=None, window=None):
    """Run compare_runs for one spec set with optional velocity, depth, window."""
    extra = []
    for spec in specs:
        cell = build_tributary_cell(spec, temperature_c=trib_temp_c,
                                    food_scale=food_scale)
        if velocity is not None:
            cell["velocity_m_s"] = float(velocity)
            cell["tributary_provenance"]["velocity_m_s"] = float(velocity)
            cell["tributary_provenance"]["velocity_provenance"] = (
                "authored_velocity_depth_sweep_override"
            )
        if depth is not None:
            cell["depth_m"] = float(depth)
            cell["tributary_provenance"]["depth_m"] = float(depth)
            cell["tributary_provenance"]["depth_provenance"] = (
                "authored_velocity_depth_sweep_override"
            )
        extra.append(cell)
    document = compare_runs(control_doc, pulse_doc, window, extra_cells=extra,
                            days=days, trout_species=species)
    row_vd = None
    if velocity is not None or depth is not None:
        row_vd = (velocity, depth)
    return document, summarize(document, trib_temp_c, food_scale,
                               velocity_depth=row_vd)


def _window(settle_s: float, pulse_doc: dict):
    """Translate a settle floor into a (lo, hi) window for compare_runs."""
    if settle_s <= 0.0:
        return None
    frames = pulse_doc.get("frames") or []
    if not frames:
        return None
    final_t = float(frames[-1].get("t_s", 0.0))
    return (settle_s, final_t + 1.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path,
                        default=Path("derived/8b9199d0fb0a/river_replay.json"))
    parser.add_argument("--pulse", type=Path,
                        default=Path("derived/hot_lowflow_replay.json"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--out-sweep", type=Path, required=True)
    parser.add_argument("--out-single-pocket", type=Path, default=None,
                        help="When set, write the N=1 (Rabbit Creek only) "
                             "comparison document as a sibling.")
    parser.add_argument("--days", type=float, default=14.0)
    parser.add_argument("--species", default="brown_trout")
    parser.add_argument("--settle-s", type=float, default=0.0,
                        help="Discard pulse frames below this t_s from the "
                             "chronic-mean comparison.")
    args = parser.parse_args()

    control_doc = json.loads(args.control.read_text(encoding="utf-8"))
    pulse_doc = json.loads(args.pulse.read_text(encoding="utf-8"))
    specs = list(TRIBUTARY_CANDIDATES)
    window = _window(args.settle_s, pulse_doc)

    # Main comparison at defaults (spec 11 C, area-ratio food scale).
    document, _ = run_case(control_doc, pulse_doc, specs, None,
                           TRIBUTARY_FOOD_SCALE_DEFAULT,
                           args.days, args.species, window=window)
    document["scenario"] = {
        "baseline": "hot low-flow (2.5 m3/s, 26 C boundary) vs pinned "
                    "control (8.0 m3/s, 17.5 C), D1 dispersion",
        "baseline_provenance": "frozen_replays_control_8b9199d0fb0a_"
                               "pulse_hot_lowflow_replay",
        "study_build_id": pulse_doc.get("build_id"),
        "source_build_id": pulse_doc.get("source_build_id"),
        "study_config_sha256": pulse_doc.get("config_sha256"),
        "control_build_id": control_doc.get("build_id"),
        "run_mode": pulse_doc.get("run_mode"),
        "tributary_cells": [
            {"id": s["cell_id"], "confluence_s_m": s["confluence_s_m"],
             "temperature_c": s["temperature_c"],
             "food_scale": TRIBUTARY_FOOD_SCALE_DEFAULT,
             "confluence_provenance": s["confluence_provenance"],
             "temperature_provenance": s["temperature_provenance"]}
            for s in specs],
        "refuge_threshold_c": REFUGE_THRESHOLD_C,
        "refuge_threshold_source": REFUGE_THRESHOLD_SOURCE,
        "refuge_threshold_provenance": "measured_Kaya_Kaeding_Burkhalter_1977",
        "design": ("landscape_level_pockets_both_landscapes_solver_"
                   "untouched_off_channel_holding_water"),
        "model_scope": MODEL_SCOPE,
        "starvation_absent": True,
        "settle_s": args.settle_s,
        "settle_provenance": "authored_discard_leading_transient",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text(json.dumps(document, indent=1, allow_nan=False) + "\n",
                   encoding="utf-8")
    tmp.replace(args.out)

    # Sensitivity sweeps: temperature, size, and velocity/depth.
    temp_rows = []
    for temp in TEMP_SWEEP_C:
        _, row = run_case(control_doc, pulse_doc, specs, temp,
                          TRIBUTARY_FOOD_SCALE_DEFAULT,
                          args.days, args.species, window=window)
        temp_rows.append(row)
    size_rows = []
    for scale in SIZE_SWEEP_SCALE:
        _, row = run_case(control_doc, pulse_doc, specs, None,
                          scale, args.days, args.species, window=window)
        size_rows.append(row)
    velocity_depth_rows = []
    for velocity, depth in VELOCITY_DEPTH_SWEEP:
        _, row = run_case(control_doc, pulse_doc, specs, None,
                          TRIBUTARY_FOOD_SCALE_DEFAULT,
                          args.days, args.species,
                          velocity=velocity, depth=depth, window=window)
        velocity_depth_rows.append(row)
    # N=1 variant (Rabbit Creek only) at defaults.
    single_doc, single = run_case(control_doc, pulse_doc, specs[:1], None,
                                  TRIBUTARY_FOOD_SCALE_DEFAULT,
                                  args.days, args.species, window=window)
    if args.out_single_pocket is not None:
        single_doc_out = dict(single_doc)
        single_doc_out["scenario"] = {
            **document["scenario"],
            "design": "landscape_level_pocket_rabbit_only_N1",
            "tributary_cells": document["scenario"]["tributary_cells"][:1],
        }
        args.out_single_pocket.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out_single_pocket.with_name(
            args.out_single_pocket.name + ".tmp"
        )
        tmp.write_text(
            json.dumps(single_doc_out, indent=1, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(args.out_single_pocket)
        print(f"Wrote {args.out_single_pocket}")
    sweep = {
        "schema": "yellowstone.aquatic_tributary_sweep.v1",
        "status": "illustrative_not_calibrated",
        "days": args.days,
        "trout_species": args.species,
        "model_scope": MODEL_SCOPE,
        "starvation_absent": True,
        "settle_s": args.settle_s,
        "study_build_id": pulse_doc.get("build_id"),
        "source_build_id": pulse_doc.get("source_build_id"),
        "study_config_sha256": pulse_doc.get("config_sha256"),
        "control_build_id": control_doc.get("build_id"),
        "run_mode": pulse_doc.get("run_mode"),
        "temperature_sweep_at_default_size": temp_rows,
        "size_sweep_at_spec_temp": size_rows,
        "velocity_depth_sweep": velocity_depth_rows,
        "single_pocket_rabbit_only_at_defaults": single,
        "provenance": {
            "pockets": "TRIBUTARY_CANDIDATES_map_measured_confluences_"
                       "authored_11C_scenario_temps",
            "food_scale_default": TRIBUTARY_FOOD_SCALE_DEFAULT,
            "food_scale_meaning": "authored_area_ratio_22m2_pocket_over_"
                                  "440m2_mainstem_cell",
            "velocity_depth_source": (
                "Elliott 1975 J. Anim. Ecol. 44:805-821 brown-trout "
                "holding velocity 0.1-0.4 m/s; depths authored"
            ),
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
    print("velocity/depth sweep (v, d -> pulse cell, U):")
    for row in velocity_depth_rows:
        print(f"  v={row['pocket_velocity_m_s']} d={row['pocket_depth_m']} "
              f"-> {row['pulse_cell']} U={row['pulse_U']:>7} "
              f"flip={row['flipped_to_tributary']}")
    print(f"single pocket (rabbit only): {single['pulse_cell']} "
          f"s={single['pulse_s_m']:.0f} U={single['pulse_U']}")
    print(f"Wrote {args.out}\nWrote {args.out_sweep}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
