"""Frozen river intervention and snow-phase reference experiment."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

from yellowstone_python.common.io import write_json_atomic
from yellowstone_python.common.provenance import sha256_json
from yellowstone_python.land.snow_season import run_season
from yellowstone_python.river.river_transport import river_from_config
from yellowstone_python.exporters.runtime_series import mapped_comparison
from yellowstone_python.service.live import LiveEngine




def run_reference() -> dict:
    """Evaluate one frozen intervention with matching baked and live solvers."""
    solver = {"cells": [{"id": "upstream", "length_m": 20., "width_m": 10., "volume_m3": 200.,
                           "initial_c": 15., "exchange_w_m2_k": 12.},
                          {"id": "downstream", "length_m": 20., "width_m": 10., "volume_m3": 200.,
                           "initial_c": 15., "exchange_w_m2_k": 12.}],
              "boundary_m3_s": 5., "boundary_c": {"times_s": [0., 60.], "values": [15., 25.]},
              "air_c": 8., "initialize_steady": False}
    scenario = {"epoch_unix": 1782064800., "run_mode": "scenario", "seed": 7,
                "model_variant_id": "mapped_fv_newton", "dt_s": 1., "sample_s": 10.,
                "duration_s": 180., "solver": solver}
    baked = river_from_config(solver)
    live = LiveEngine(river_from_config(solver), {"run_mode": "scenario", "live": {"dt_s": 1.}},
                      epoch_unix=scenario["epoch_unix"], frame_interval_s=10.)
    control = river_from_config({**solver, "boundary_c": 15.})
    rows = []
    for end in range(10, 181, 10):
        baked.run(10., dt_s=1., sample_s=10.)
        control.run(10., dt_s=1., sample_s=10.)
        live.compute_until(float(end))
        if max(abs(a - b) for a, b in zip(baked.temperature_c, live.river.temperature_c)) > 1e-11:
            raise ValueError("baked/live reference trajectories differ")
        rows.append({"t_s": end, "control_c": list(control.temperature_c),
                     "intervention_c": list(baked.temperature_c)})
    _, snow = run_season([{"id": "meadow", "habitat": "dry_meadow", "snow_mm": 100., "soil_mm": 12.}],
                         1, [-10.], precip_mm_d=0., wind_loss=.15, wind_mps=2.)
    if snow["runoff_mm"] != 0. or abs(snow["snow_export_mm"] - 15.) > 1e-12:
        raise ValueError("snow phase negative control failed")
    return {"schema": "yellowstone.reference_experiment.v1", "scenario": scenario,
            "scenario_id": sha256_json(scenario), "frames": rows, "snow_phase_control": snow,
            "baked_live_max_error_tolerance_c": 1e-11, "budget": baked.budget(),
            "scientific_status": "synthetic_numerical_check_not_field_validation"}


def main() -> int:
    """Write the frozen experiment and an optional temperature plot."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="work/reference-experiment.json")
    parser.add_argument("--plot")
    args = parser.parse_args()
    report = run_reference()
    write_json_atomic(args.out, report, indent=2)
    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        figure, axis = plt.subplots(figsize=(7, 3.5))
        rows = report["frames"]
        axis.plot([r["t_s"] for r in rows], [r["control_c"][1] for r in rows], label="Control: 15 C boundary")
        axis.plot([r["t_s"] for r in rows], [r["intervention_c"][1] for r in rows], label="Intervention: boundary rises to 25 C")
        axis.axvline(60., color="gray", linestyle=":", label="Input change at 60 s")
        axis.set(xlabel="Model time (s)", ylabel="Downstream temperature (C)", title="Synthetic river experiment; Newton exchange")
        axis.legend(fontsize=8)
        figure.tight_layout()
        Path(args.plot).parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.plot)
        plt.close(figure)
    print("reference scenario", report["scenario_id"], "passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
