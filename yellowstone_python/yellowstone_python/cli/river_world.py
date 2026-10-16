"""Command-line interface for river world."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any
from yellowstone_python.river.river_transport import RHO_CP_J_M3_K, Series, finite, make_replay, positive
from yellowstone_python.common.io import sha256_file, write_json_atomic
from yellowstone_python.atmosphere.time_utils import ISO_HINT, UTC, parse_simulation_start, timestamp_metadata
from yellowstone_python.atmosphere.microclimate import air_temp, wind_at
from yellowstone_python.river.hydraulics import DEFAULT_BANK_SLOPE_ZH, DEFAULT_MANNING_N, cell_hydraulics, thermal_inventory
from yellowstone_python.river.river_world import *
from yellowstone_python.river.river_world import _weather_times, _forcing_series_from_weather

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--ecosystem", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--simulation-start-utc", default=None,
        help="Replay start as a timezone-aware ISO-8601 UTC timestamp, "
             f"{ISO_HINT}",
    )
    parser.add_argument(
        "--simulation-start-epoch", type=float, default=None,
        help="Replay start as Unix seconds since 1970-01-01 UTC",
    )
    parser.add_argument("--duration", type=float, default=7200.0)
    parser.add_argument("--cell-m", type=float, default=20.0)
    parser.add_argument("--depth-m", type=float, default=1.1)
    parser.add_argument("--dispersion", type=float, default=1.0)
    parser.add_argument("--exchange", type=float, default=12.0)
    parser.add_argument("--dt", type=float, default=2.0)
    parser.add_argument("--sample", type=float, default=10.0)
    parser.add_argument("--pulse-source", default="")
    parser.add_argument("--pulse-start", type=float, default=300.0)
    parser.add_argument("--pulse-end", type=float, default=900.0)
    parser.add_argument("--pulse-delta-c", type=float, default=18.0)
    parser.add_argument(
        "--reach-anchors", type=Path,
        help="Optional JSON: reach id -> {river_id, vertex_index}",
    )
    parser.add_argument(
        "--cross-sections", type=Path,
        help="Optional JSON: river feature id -> "
             "{depth_m, status, source?} mean-depth profiles",
    )
    parser.add_argument(
        "--upstream-discharge", type=Path,
        help="Optional JSON: predicted upstream discharge series with "
             "bounds (overland_provider interface)",
    )
    parser.add_argument(
        "--extra-sources", type=Path,
        help="Optional JSON list: provider laterals as "
             "{id, s_m, flow_m3_s, temperature_c, status}",
    )
    parser.add_argument(
        "--silica-obs", type=Path,
        help="Optional JSON: river feature id -> observed dissolved "
             "SiO2 mg/L for the silica diagnostic",
    )
    parser.add_argument(
        "--landscape-pockets", type=Path,
        help="Optional JSON list of off-channel refuge pockets. Pockets "
             "ship as a landscape artifact beside the solver; the thermal "
             "solver does not integrate them.",
    )
    parser.add_argument(
        "--energy-budget", action="store_true",
        help="Use the explicit shortwave/longwave/sensible/latent "
             "surface budget instead of the lumped Newton coefficient",
    )
    parser.add_argument(
        "--bank-slope", type=float, default=DEFAULT_BANK_SLOPE_ZH,
        help="Trapezoid bank slope z (H:V) for hydraulics diagnostics; "
             "authored illustrative, not measured",
    )
    parser.add_argument(
        "--manning-n", type=float, default=DEFAULT_MANNING_N,
        help="Manning roughness for hydraulics diagnostics; "
             "authored illustrative, not calibrated",
    )
    args = parser.parse_args()

    if args.simulation_start_utc is None and args.simulation_start_epoch is None:
        parser.error(
            "one of --simulation-start-utc or --simulation-start-epoch "
            "is required; the replay clock has no calendar date without it"
        )

    # A diagnostic output path must never overwrite immutable inputs.
    inputs = [args.world, args.ecosystem]
    if args.reach_anchors:
        inputs.append(args.reach_anchors)
    if args.cross_sections:
        inputs.append(args.cross_sections)
    if args.upstream_discharge:
        inputs.append(args.upstream_discharge)
    if args.extra_sources:
        inputs.append(args.extra_sources)
    if args.silica_obs:
        inputs.append(args.silica_obs)
    if args.landscape_pockets:
        inputs.append(args.landscape_pockets)
    if args.out.resolve() in {path.resolve() for path in inputs}:
        parser.error("output must not overwrite an input")

    try:
        world = json.loads(args.world.read_text(encoding="utf-8"))
        ecosystem = json.loads(
            args.ecosystem.read_text(encoding="utf-8")
        )
        anchors = (
            json.loads(args.reach_anchors.read_text(encoding="utf-8"))
            if args.reach_anchors else None
        )
        sections = (
            json.loads(args.cross_sections.read_text(encoding="utf-8"))
            if args.cross_sections else None
        )
        discharge = (
            json.loads(args.upstream_discharge.read_text(encoding="utf-8"))
            if args.upstream_discharge else None
        )
        extra = (
            json.loads(args.extra_sources.read_text(encoding="utf-8"))
            if args.extra_sources else None
        )
        silica_file = (
            json.loads(args.silica_obs.read_text(encoding="utf-8"))
            if args.silica_obs else None
        )
        pockets_file = (
            json.loads(args.landscape_pockets.read_text(encoding="utf-8"))
            if args.landscape_pockets else None
        )

        document = build_mapped_replay(
            world, ecosystem,
            simulation_start_utc=args.simulation_start_utc,
            simulation_start_epoch_unix=args.simulation_start_epoch,
            duration_s=args.duration,
            maximum_cell_m=args.cell_m,
            depth_m=args.depth_m,
            dispersion_m2_s=args.dispersion,
            exchange_w_m2_k=args.exchange,
            dt_s=args.dt,
            sample_s=args.sample,
            pulse_source=args.pulse_source,
            pulse_start_s=args.pulse_start,
            pulse_end_s=args.pulse_end,
            pulse_delta_c=args.pulse_delta_c,
            reach_anchors=anchors,
            cross_sections=sections,
            energy_budget=args.energy_budget,
            bank_slope_zh=args.bank_slope,
            manning_n=args.manning_n,
            upstream_discharge=discharge,
            extra_sources=extra,
            silica_obs=silica_file,
            landscape_pockets=pockets_file,
        )
        document["input_files"] = {
            "world": {"path": str(args.world), "sha256": sha256(args.world)},
            "ecosystem": {
                "path": str(args.ecosystem),
                "sha256": sha256(args.ecosystem),
            },
        }
        if args.reach_anchors:
            document["input_files"]["reach_anchors"] = {
                "path": str(args.reach_anchors),
                "sha256": sha256(args.reach_anchors),
            }
        if args.cross_sections:
            document["input_files"]["cross_sections"] = {
                "path": str(args.cross_sections),
                "sha256": sha256(args.cross_sections),
            }
        if args.upstream_discharge:
            document["input_files"]["upstream_discharge"] = {
                "path": str(args.upstream_discharge),
                "sha256": sha256(args.upstream_discharge),
            }
        if args.extra_sources:
            document["input_files"]["extra_sources"] = {
                "path": str(args.extra_sources),
                "sha256": sha256(args.extra_sources),
            }
        if args.silica_obs:
            document["input_files"]["silica_obs"] = {
                "path": str(args.silica_obs),
                "sha256": sha256(args.silica_obs),
            }
        if args.landscape_pockets:
            document["input_files"]["landscape_pockets"] = {
                "path": str(args.landscape_pockets),
                "sha256": sha256(args.landscape_pockets),
            }
        document["adapter_code_sha256"] = sha256(Path(__file__))

        if not document["numerical_checks"]["passed"]:
            raise ArithmeticError("solver budget closure checks failed")

        write_json_atomic(args.out, document, indent=2)

    except (ValueError, TypeError, KeyError, ArithmeticError, OSError) as error:
        parser.exit(2, f"mapped river build failed: {error}\n")

    print(f"Wrote {args.out}")
    print("Chain:", " -> ".join(document["mapping"]["chain_order"]))
    print(f"Length: {document['mapping']['length_m']:.1f} m")
    print(f"Cells: {len(document['cells'])}")
    for connection in document["source_connections"]:
        print(
            f"Source {connection['source_id']}: "
            f"s={connection['s_m']:.1f} m, "
            f"{connection['target_river_id']} "
            f"vertex {connection['target_vertex_index']}"
        )
    print("Budget:", document["final_budget"]["heat_relative_residual"])
    print("Mapped illustrative simulation; not a Yellowstone forecast.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
