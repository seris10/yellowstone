"""Firehole walk with segment residency against the single-domain river solver."""
from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

from yellowstone_python.common.io import load_json, sha256_file, write_json_atomic
from yellowstone_python.common.provenance import default_world_root
from yellowstone_python.park_runtime.residency import FIREHOLE_FACES, evaluate_walk, firehole_residency, run_walk
from yellowstone_python.river.river_transport import river_from_config


def reference_temperatures(config: dict, times_s: list[float], positions_m: list[float],
                           dt_s: float) -> list[float]:
    """Return the single-domain temperature in C at each walker position and increasing time."""
    river = river_from_config(config)
    edges = [0.0]
    for cell in river.cells:
        edges.append(edges[-1] + cell.length_m)
    values = []
    for t_s, x in zip(times_s, positions_m):
        span = t_s - river.time_s
        if span > 1e-9:
            river.run(span, dt_s=dt_s, sample_s=span)
        index = min(next((i for i, e in enumerate(edges[1:]) if x < e), len(river.cells) - 1), len(river.cells) - 1)
        values.append(river.temperature_c[index])
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--speed-mps", type=float, default=1.4)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--time-scale", type=float, default=1.0)
    parser.add_argument("--start-m", type=float, default=0.0, help="walk start chainage")
    parser.add_argument("--end-m", type=float, help="walk end chainage; the outlet when omitted")
    parser.add_argument("--no-reference", action="store_true", help="skip the single-domain diagnostic")
    args = parser.parse_args()
    replay = default_world_root() / "data" / "river_replay.json"
    document = load_json(replay)
    started = time.perf_counter()
    manager, _ = firehole_residency(document, workers=args.workers, virtual_wall=True, position_m=args.start_m,
                                    velocity_mps=args.speed_mps, time_scale=args.time_scale)
    try:
        end_m = manager.specs[-1].end_m if args.end_m is None else args.end_m
        reports = run_walk(manager, args.start_m, end_m, args.speed_mps, args.time_scale)
        walk_wall_s = time.perf_counter() - started
        result = evaluate_walk(manager, reports, args.start_m, args.speed_mps)
        diagnostic = None
        if not args.no_reference:
            reference = reference_temperatures(manager.config, [r["t_s"] for r in reports],
                                               [r["position_m"] for r in reports], manager.dt_s)
            deltas = [abs(r["walker_temperature_c"] - ref) for r, ref in zip(reports, reference)]
            diagnostic = {"max_abs_delta_c": max(deltas), "mean_abs_delta_c": math.fsum(deltas) / len(deltas),
                          "samples": len(deltas), "reference": "single-domain River on the same forcing and step"}
        replay_window = document.get("replay", document).get("simulation_time", {}).get("duration_s")
        quantum_wall_s = manager.quantum_s / result["min_effective_rate"]
        report = {"schema": "yellowstone.park_firehole_walk.v1", "run_mode": "illustrative",
                  "input": {"river_replay": "data/river_replay.json", "sha256": sha256_file(replay)},
                  "settings": {"faces": list(FIREHOLE_FACES), "quantum_s": manager.quantum_s, "dt_s": manager.dt_s,
                               "spinup_s": manager.spinup_s, "lead_margin_s": manager.lead_margin_s,
                               "retire_after_s": manager.retire_after_s, "utilization": manager.utilization,
                               "speed_mps": args.speed_mps, "time_scale": args.time_scale, "workers": args.workers,
                               "start_m": args.start_m, "end_m": end_m},
                  "forcing": {"replay_window_s": replay_window,
                              "held_after_window": replay_window is not None and reports[-1]["t_s"] > replay_window,
                              "note": "the solver holds the last forcing values after the replay window"},
                  "segments": [{"domain_id": s.domain_id, "cells": [s.lo, s.hi], "start_m": s.start_m,
                                "end_m": s.end_m, "travel_s": s.travel_s} for s in manager.specs],
                  "acceptance": {k: v for k, v in result.items() if k not in ("arrivals", "retirements")},
                  "retire_bound_s": manager.retire_after_s + quantum_wall_s,
                  "arrivals": result["arrivals"], "retirements": result["retirements"], "swaps": manager.swaps,
                  "diagnostic_walker_temperature": diagnostic,
                  "capacity_cell_s_per_s": manager.capacity, "worker_rate_cell_s_per_s": manager.worker_rate,
                  "walk_wall_s": walk_wall_s, "simulated_s": reports[-1]["t_s"]}
    finally:
        manager.close()
    write_json_atomic(args.out, report)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
