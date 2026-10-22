"""Firehole walk with segment residency against the single-domain river solver."""
from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

from yellowstone_python.common.io import load_json, sha256_file, write_json_atomic
from yellowstone_python.common.provenance import default_world_root
from yellowstone_python.park_runtime.residency import ResidencyManager, evaluate_walk, run_walk
from yellowstone_python.river.river_transport import river_from_config
from yellowstone_python.service.live.engine import replay_config

FACES = [46, 92, 138, 184, 230]


def reference_temperatures(config: dict, times_s: list[float], positions_m: list[float], quantum_s: float,
                           dt_s: float) -> list[float]:
    """Return the single-domain temperature in C at each walker position and time."""
    river = river_from_config(config)
    edges = [0.0]
    for cell in river.cells:
        edges.append(edges[-1] + cell.length_m)
    frames = {round(f["t_s"], 6): f["temperature_c"]
              for f in river.run(max(times_s), dt_s=dt_s, sample_s=quantum_s)}
    values = []
    for t_s, x in zip(times_s, positions_m):
        index = min(next((i for i, e in enumerate(edges[1:]) if x < e), len(river.cells) - 1), len(river.cells) - 1)
        values.append(frames[round(t_s, 6)][index])
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--speed-mps", type=float, default=1.4)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    replay = default_world_root() / "data" / "river_replay.json"
    document = load_json(replay)
    config = replay_config(document.get("replay", document))
    started = time.perf_counter()
    manager = ResidencyManager(config, FACES, workers=args.workers, virtual_wall=True, velocity_mps=args.speed_mps)
    try:
        end_m = manager.specs[-1].end_m
        reports = run_walk(manager, 0.0, end_m, args.speed_mps)
        walk_wall_s = time.perf_counter() - started
        result = evaluate_walk(manager, reports, 0.0, args.speed_mps)
        reference = reference_temperatures(config, [r["t_s"] for r in reports], [r["position_m"] for r in reports],
                                           manager.quantum_s, manager.dt_s)
        deltas = [abs(r["walker_temperature_c"] - ref) for r, ref in zip(reports, reference)]
        report = {"schema": "yellowstone.park_firehole_walk.v1", "run_mode": "illustrative",
                  "input": {"river_replay": "data/river_replay.json", "sha256": sha256_file(replay)},
                  "settings": {"faces": FACES, "quantum_s": manager.quantum_s, "dt_s": manager.dt_s,
                               "spinup_s": manager.spinup_s, "lead_margin_s": manager.lead_margin_s,
                               "retire_after_s": manager.retire_after_s, "utilization": manager.utilization,
                               "speed_mps": args.speed_mps, "time_scale": 1.0, "workers": args.workers},
                  "segments": [{"domain_id": s.domain_id, "cells": [s.lo, s.hi], "start_m": s.start_m,
                                "end_m": s.end_m, "travel_s": s.travel_s} for s in manager.specs],
                  "acceptance": {k: v for k, v in result.items() if k not in ("arrivals", "retirements")},
                  "arrivals": result["arrivals"], "retirements": result["retirements"], "swaps": manager.swaps,
                  "diagnostic_walker_temperature": {
                      "max_abs_delta_c": max(deltas), "mean_abs_delta_c": math.fsum(deltas) / len(deltas),
                      "samples": len(deltas), "reference": "single-domain River on the same forcing and step"},
                  "capacity_cell_s_per_s": manager.capacity, "worker_rate_cell_s_per_s": manager.worker_rate,
                  "walk_wall_s": walk_wall_s, "simulated_s": reports[-1]["t_s"]}
    finally:
        manager.close()
    write_json_atomic(args.out, report)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
