"""Hot low-flow scenario: mapped replay + foodweb control-vs-hot comparison.

Scenario (backlog A): Burkhalter 1979 baseflow boundary ~2.5 m3/s (range
2-3, measured) with a warm 26 C boundary (authored scenario value, below
the observed 29.5 C Firehole maximum so physically admissible; labeled,
never calibrated). Low flow raises the lateral-thermal fraction, pushing
in-chain cells across the Kaya 24 C refuge-drive threshold (wired and
tested in fish.py, dormant at the 17-19 C baseline chain).

Control is the pinned baseline replay (8.0 m3/s, 17.5 C). Both landscapes
are full-run means (chronic scenario, not a short pulse: no window_s).

Usage:
    python3 tools/run_hot_lowflow.py --config configs/baseline.yaml \
        --control derived/8b9199d0fb0a/river_replay.json \
        --out-replay derived/hot_lowflow_replay.json \
        --out derived/aquatic_hot_lowflow.json
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yellowstone_python.aquatic_foodweb import compare_runs
from yellowstone_python.build import (load_config, load_inputs,
                                      run_replay_solver, validate_config)

BOUNDARY_M3S = 2.5  # Burkhalter 1979 geothermal baseflow 2-3 m3/s (measured)
BOUNDARY_C = 26.0  # authored scenario; below observed 29.5 C max


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--out-replay", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--boundary-m3s", type=float, default=BOUNDARY_M3S)
    parser.add_argument("--boundary-c", type=float, default=BOUNDARY_C)
    parser.add_argument("--dispersion-m2-s", type=float, default=1.0,
                        help="solver dispersion; Fischer median 84.7 is a "
                             "sensitivity case, not calibration (rests on "
                             "authored n=0.035/banks)")
    parser.add_argument("--dispersion-provenance", default="solver_default",
                        help="provenance label for the dispersion choice")
    parser.add_argument("--days", type=float, default=14.0)
    parser.add_argument("--species", default="brown_trout")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    hot = copy.deepcopy(cfg)
    hot.setdefault("hydro", {})["boundary_m3s"] = args.boundary_m3s
    hot["hydro"]["boundary_c"] = args.boundary_c
    hot.setdefault("replay", {})["dispersion_m2_s"] = args.dispersion_m2_s
    validate_config(hot)
    baseline, world, _, _ = load_inputs(hot)

    print(f"hot replay: Q={args.boundary_m3s} m3/s, T={args.boundary_c} C ...")
    pulse_doc = run_replay_solver(hot, baseline, world)
    # The raw solver status is not in the derived/ status vocabulary
    # (tools/audit_provenance.py scans top-level bundles); preserve it
    # aside and label the saved scenario replay as what it is.
    pulse_doc["solver_status"] = pulse_doc.get("status")
    pulse_doc["status"] = "numerical_experiment_not_field_validation"
    args.out_replay.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out_replay.with_name(args.out_replay.name + ".tmp")
    tmp.write_text(json.dumps(pulse_doc, indent=1) + "\n", encoding="utf-8")
    tmp.replace(args.out_replay)
    print(f"Wrote {args.out_replay}")

    control_doc = json.loads(args.control.read_text(encoding="utf-8"))
    document = compare_runs(control_doc, pulse_doc, None,
                            days=args.days, trout_species=args.species)
    document["scenario"] = {
        "boundary_m3s": args.boundary_m3s,
        "boundary_m3s_provenance": "measured_Burkhalter_1979_baseflow_2-3",
        "boundary_c": args.boundary_c,
        "boundary_c_provenance": ("authored_scenario_below_observed_29.5C_"
                                  "max_never_calibrated"),
        "dispersion_m2_s": args.dispersion_m2_s,
        "dispersion_provenance": args.dispersion_provenance,
        "refuge_threshold_c": 24.0,
        "refuge_threshold_provenance": "measured_Kaya_Kaeding_Burkhalter_1977",
    }
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text(json.dumps(document, indent=1, allow_nan=False) + "\n",
                   encoding="utf-8")
    tmp.replace(args.out)
    print(f"refuge shift: {document['refuge_shift_m']} m "
          f"(control s={document['control']['s_m']:.0f} m @ "
          f"{document['control']['temperature_c']} C, "
          f"refuge_drive={document['control']['refuge_drive']} -> pulse "
          f"s={document['pulse']['s_m']:.0f} m @ "
          f"{document['pulse']['temperature_c']} C, "
          f"refuge_drive={document['pulse']['refuge_drive']})")
    print(f"diet/emergence/dipper: {document['emergence_change']} / "
          f"{document['dipper_intake_change']}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
