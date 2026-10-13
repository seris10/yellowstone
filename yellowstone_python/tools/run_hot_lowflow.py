"""Hot low-flow scenario: mapped replay plus foodweb control-vs-hot comparison.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenario_constants import (  # noqa: E402
    HOT_LOWFLOW_BOUNDARY_C,
    HOT_LOWFLOW_BOUNDARY_C_SOURCE,
    HOT_LOWFLOW_BOUNDARY_C_SUB_UILT,
    HOT_LOWFLOW_BOUNDARY_C_SUB_UILT_SOURCE,
    HOT_LOWFLOW_BOUNDARY_M3S,
    HOT_LOWFLOW_BOUNDARY_M3S_SOURCE,
    OBSERVED_MAX_C_SOURCE,
    REFUGE_THRESHOLD_C,
    REFUGE_THRESHOLD_SOURCE,
    UILT_C_SOURCE,
)
from yellowstone_python.aquatic_foodweb import compare_runs
from yellowstone_python.build import (load_config, load_inputs,
                                      run_replay_solver, validate_config)
from yellowstone_python.common.provenance import (build_id as _build_id,
                                                  sha256_json)
from yellowstone_python.run_mode import normalize_run_mode

# Backward-compatible aliases.
BOUNDARY_M3S = HOT_LOWFLOW_BOUNDARY_M3S
BOUNDARY_C = HOT_LOWFLOW_BOUNDARY_C


def _quasi_steady_check(pulse_doc: dict) -> dict:
    """Half-split per-cell temperature means. Diagnostic for the chronic mean."""
    frames = pulse_doc.get("frames") or []
    cells = pulse_doc.get("cells") or []
    n_cells = len(cells)
    if n_cells == 0 or len(frames) < 4:
        return {"status": "skipped", "reason": "too_few_frames_or_cells"}
    half = len(frames) // 2
    sums_a = [0.0] * n_cells
    sums_b = [0.0] * n_cells
    for frame in frames[:half]:
        temps = frame.get("temperature_c") or []
        for i in range(min(n_cells, len(temps))):
            sums_a[i] += float(temps[i])
    for frame in frames[half:]:
        temps = frame.get("temperature_c") or []
        for i in range(min(n_cells, len(temps))):
            sums_b[i] += float(temps[i])
    denom_a = max(half, 1)
    denom_b = max(len(frames) - half, 1)
    max_abs = 0.0
    for i in range(n_cells):
        diff = sums_a[i] / denom_a - sums_b[i] / denom_b
        if abs(diff) > max_abs:
            max_abs = abs(diff)
    passed = max_abs <= 0.5
    return {
        "status": "passed" if passed else "failed",
        "max_abs_cell_half_diff_c": round(max_abs, 4),
        "tolerance_c": 0.5,
    }


def _run_pulse(args, boundary_c: float, dispersion: float) -> dict:
    """Build the hot scenario config, run the solver, label the replay."""
    cfg = load_config(Path(args.config))
    # The derived/ build the runner consumes comes from the unmutated config; its build id resolves to a sibling under derived/. The runner's own build id is for the mutated scenario config and matches no build directory.
    validate_config(cfg)
    _base_baseline, _base_world, source_deps, _ = load_inputs(cfg)
    source_bid = _build_id(cfg, source_deps,
                           code_rev=source_deps.get("code_rev"))
    hot = copy.deepcopy(cfg)
    hot.setdefault("hydro", {})["boundary_m3s"] = args.boundary_m3s
    hot["hydro"]["boundary_c"] = boundary_c
    hot.setdefault("replay", {})["dispersion_m2_s"] = dispersion
    hot["run_mode"] = "scenario"
    validate_config(hot)
    baseline, world, deps, _ = load_inputs(hot)
    pulse_doc = run_replay_solver(hot, baseline, world)
    pulse_doc["solver_status"] = pulse_doc.get("status")
    pulse_doc["status"] = "numerical_experiment_not_field_validation"
    bid = _build_id(hot, deps, code_rev=deps.get("code_rev"))
    config_sha = sha256_json(hot)
    mode = normalize_run_mode(hot.get("run_mode"))
    pulse_doc["build_id"] = bid
    pulse_doc["source_build_id"] = source_bid
    pulse_doc["config_sha256"] = config_sha
    pulse_doc["run_mode"] = mode
    pulse_doc["run_provenance"] = {
        "study_runner": "run_hot_lowflow",
        "build_id": bid,
        "source_build_id": source_bid,
        "config_sha256": config_sha,
        "run_mode": mode,
    }
    return pulse_doc


def _scenario_block(args, boundary_c: float, dispersion: float,
                    boundary_c_source: dict, quasi_steady: dict,
                    settle_s: float) -> dict:
    """Scenario-block provenance for the output comparison document."""
    return {
        "run_mode": "scenario",
        "run_mode_provenance": "forced_by_run_hot_lowflow_runner",
        "boundary_m3s": args.boundary_m3s,
        "boundary_m3s_source": HOT_LOWFLOW_BOUNDARY_M3S_SOURCE,
        "boundary_m3s_provenance": "measured_Burkhalter_1979_baseflow_2-3",
        "boundary_c": boundary_c,
        "boundary_c_source": boundary_c_source,
        "boundary_c_provenance": (
            "authored_scenario_below_observed_29.5C_max_never_calibrated"
        ),
        "observed_max_c_source": OBSERVED_MAX_C_SOURCE,
        "uilt_c_source": UILT_C_SOURCE,
        "dispersion_m2_s": dispersion,
        "dispersion_provenance": args.dispersion_provenance,
        "refuge_threshold_c": REFUGE_THRESHOLD_C,
        "refuge_threshold_source": REFUGE_THRESHOLD_SOURCE,
        "refuge_threshold_provenance": "measured_Kaya_Kaeding_Burkhalter_1977",
        "settle_s": settle_s,
        "settle_provenance": "authored_discard_leading_transient",
        "quasi_steady_check": quasi_steady,
    }


def _window(settle_s: float, pulse_doc: dict):
    """Translate a settle_s floor into a (lo, hi) window for compare_runs."""
    if settle_s <= 0.0:
        return None
    frames = pulse_doc.get("frames") or []
    if not frames:
        return None
    final_t = float(frames[-1].get("t_s", 0.0))
    return (settle_s, final_t + 1.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--out-replay", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--boundary-m3s", type=float,
                        default=HOT_LOWFLOW_BOUNDARY_M3S)
    parser.add_argument("--boundary-c", type=float,
                        default=HOT_LOWFLOW_BOUNDARY_C)
    parser.add_argument("--sub-uilt", action="store_true",
                        help="Switch boundary to the sub-UILT value "
                             "(1 C below brown-trout UILT 26 C).")
    parser.add_argument("--dispersion-m2-s", type=float, default=1.0,
                        help="Solver dispersion. Fischer median 84.7 is a "
                             "sensitivity case; the authored n and banks "
                             "define the model dispersion.")
    parser.add_argument("--dispersion-provenance", default="solver_default",
                        help="Provenance label for the dispersion choice.")
    parser.add_argument("--days", type=float, default=14.0)
    parser.add_argument("--species", default="brown_trout")
    parser.add_argument("--settle-s", type=float, default=0.0,
                        help="Discard replay frames with t_s below this "
                             "value from the chronic-mean comparison.")
    parser.add_argument("--plus-c", type=float, default=0.0,
                        help="When non-zero, also run a pulse with the "
                             "boundary raised by this many degrees and "
                             "write an aquatic_<out>_plus<c>.json sibling.")
    args = parser.parse_args()

    if args.sub_uilt:
        boundary_c = HOT_LOWFLOW_BOUNDARY_C_SUB_UILT
        boundary_c_source = HOT_LOWFLOW_BOUNDARY_C_SUB_UILT_SOURCE
    else:
        boundary_c = args.boundary_c
        boundary_c_source = HOT_LOWFLOW_BOUNDARY_C_SOURCE

    print(f"hot replay: Q={args.boundary_m3s} m3/s, T={boundary_c} C ...")
    pulse_doc = _run_pulse(args, boundary_c, args.dispersion_m2_s)
    args.out_replay.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out_replay.with_name(args.out_replay.name + ".tmp")
    tmp.write_text(json.dumps(pulse_doc, indent=1) + "\n", encoding="utf-8")
    tmp.replace(args.out_replay)
    print(f"Wrote {args.out_replay}")

    quasi_steady = _quasi_steady_check(pulse_doc)
    window = _window(args.settle_s, pulse_doc)

    control_doc = json.loads(args.control.read_text(encoding="utf-8"))
    document = compare_runs(control_doc, pulse_doc, window,
                            days=args.days, trout_species=args.species)
    document["scenario"] = _scenario_block(
        args, boundary_c, args.dispersion_m2_s, boundary_c_source,
        quasi_steady, args.settle_s,
    )
    document["scenario"]["study_build_id"] = pulse_doc.get("build_id")
    document["scenario"]["study_config_sha256"] = pulse_doc.get(
        "config_sha256")
    document["scenario"]["run_mode"] = pulse_doc.get("run_mode")
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
    print(f"quasi_steady_check: {quasi_steady}")
    print(f"Wrote {args.out}")

    if args.plus_c and not math.isclose(args.plus_c, 0.0):
        plus_boundary = boundary_c + args.plus_c
        print(f"plus-c pulse: T={plus_boundary} C ...")
        plus_pulse = _run_pulse(args, plus_boundary, args.dispersion_m2_s)
        plus_doc = compare_runs(control_doc, plus_pulse, window,
                                days=args.days, trout_species=args.species)
        plus_doc["scenario"] = _scenario_block(
            args, plus_boundary, args.dispersion_m2_s, {
                "citation": "Delta applied to boundary_c for sensitivity.",
                "value_cited_in_file": f"{plus_boundary} C",
                "verification": (
                    f"boundary_c + plus_c = {boundary_c} + {args.plus_c}"
                ),
            }, _quasi_steady_check(plus_pulse), args.settle_s,
        )
        plus_doc["scenario"]["plus_c_delta"] = args.plus_c
        plus_doc["scenario"]["study_build_id"] = plus_pulse.get("build_id")
        plus_doc["scenario"]["study_config_sha256"] = plus_pulse.get(
            "config_sha256")
        plus_doc["scenario"]["run_mode"] = plus_pulse.get("run_mode")
        stem = args.out.stem
        plus_tag = f"_plus{args.plus_c:g}".replace("-", "neg").replace(".", "p")
        plus_path = args.out.with_name(f"{stem}{plus_tag}{args.out.suffix}")
        tmp = plus_path.with_name(plus_path.name + ".tmp")
        tmp.write_text(
            json.dumps(plus_doc, indent=1, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(plus_path)
        print(f"plus-c refuge shift: {plus_doc['refuge_shift_m']} m "
              f"(wrote {plus_path})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
