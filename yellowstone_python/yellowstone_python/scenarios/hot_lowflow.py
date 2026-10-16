"""Hot low-flow comparisons, authored pockets, and measured tributary scenarios."""
from __future__ import annotations

import copy
import math
from pathlib import Path

from yellowstone_python.aquatic.aquatic_foodweb import TRIBUTARY_CANDIDATES, TRIBUTARY_FOOD_SCALE_DEFAULT, build_tributary_cell, compare_runs
from yellowstone_python.insects_birds import trout_diet_at_temp
from yellowstone_python.build import load_config, load_inputs, run_replay_solver, validate_config
from yellowstone_python.common.provenance import build_id as _build_id, sha256_json
from yellowstone_python.common.io import load_json, write_json_atomic as _shared_json_write
from yellowstone_python.common.checks import finite, nonnegative, positive, positive_int
from yellowstone_python.river.river_world import Channel, firehole_chain
from yellowstone_python.registry.run_mode import normalize_run_mode

HOT_LOWFLOW_BOUNDARY_M3S = 2.5
HOT_LOWFLOW_BOUNDARY_M3S_SOURCE = {
    "citation": (
        "Burkhalter, D.E. 1979. Fishery investigations of the thermally "
        "stressed Firehole River. MSc thesis, Montana State University."
    ),
    "value_cited_in_file": "2-3 m3/s geothermal baseflow",
    "verification": "citation chain only; primary source not verified in repo",
}

HOT_LOWFLOW_BOUNDARY_C = 26.0
HOT_LOWFLOW_BOUNDARY_C_SOURCE = {
    "citation": (
        "Authored scenario. Reference: Kaya, C.M., Kaeding, L.R., "
        "Burkhalter, D.E. 1977. Prog. Fish-Cult. 39:37-39 (observed max 29.5 C)."
    ),
    "value_cited_in_file": "26 C at the upstream boundary",
    "verification": "scenario-authored not measured; below 29.5 C observed max",
}

HOT_LOWFLOW_BOUNDARY_C_SUB_UILT = 25.0
HOT_LOWFLOW_BOUNDARY_C_SUB_UILT_SOURCE = {
    "citation": "Authored sub-UILT variant: 1 C below brown-trout UILT 26 C.",
    "value_cited_in_file": "25 C at the upstream boundary",
    "verification": (
        "scenario-authored for the flip test; UILT 26 C from "
        "fish.THERMAL_SPECIES brown_trout.t_uilt_c"
    ),
}

REFUGE_THRESHOLD_C = 24.0
REFUGE_THRESHOLD_SOURCE = {
    "citation": (
        "Kaya, C.M., Kaeding, L.R., Burkhalter, D.E. 1977. Prog. Fish-Cult. "
        "39:37-39."
    ),
    "value_cited_in_file": "mean > 24 C refuge threshold",
    "verification": "citation chain only; abstract verified",
}

OBSERVED_MAX_C_SOURCE = {
    "citation": (
        "Kaya, C.M., Kaeding, L.R., Burkhalter, D.E. 1977. Prog. Fish-Cult. "
        "39:37-39."
    ),
    "value_cited_in_file": "29.5 C observed maximum",
    "verification": "citation chain only; primary source not verified in repo",
}

UILT_C_SOURCE = {
    "citation": (
        "Nevada DEP, BrownTTA and RainbowTTA technical reviews citing "
        "Grande and Andersen 1991 and others."
    ),
    "value_cited_in_file": "26 C brown UILT, 26 C rainbow UILT",
    "verification": "citation chain documented in fish.py THERMAL_SPECIES_PROVENANCE",
}

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
            sums_a[i] += finite("frame temperature_c", temps[i])
    for frame in frames[half:]:
        temps = frame.get("temperature_c") or []
        for i in range(min(n_cells, len(temps))):
            sums_b[i] += finite("frame temperature_c", temps[i])
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
    if args.pulse is not None:
        document = copy.deepcopy(load_json(args.pulse))
        document["run_mode"] = "scenario"
        document.setdefault("run_provenance", {})["run_mode"] = "scenario"
        return document
    cfg = load_config(Path(args.config))
    # Resolve the source build from the control configuration.
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
    settle_s = finite("settle_s", settle_s)
    if settle_s <= 0.0:
        return None
    frames = pulse_doc.get("frames") or []
    if not frames:
        return None
    final_t = finite("final replay time", frames[-1].get("t_s", 0.0))
    return (settle_s, final_t + 1.0)


TEMP_SWEEP_C = (8.0, 11.0, 14.0, 17.0, 20.0, 23.0, 24.0, 25.0, 26.0)
SIZE_SWEEP_SCALE = (0.0, 0.01, 0.05, 0.2, 1.0)
VELOCITY_DEPTH_SWEEP = ((0.1, 0.3), (0.25, 0.5), (0.5, 1.0))
MODEL_SCOPE = "selection_only_no_mortality_no_movement_cost_no_absolute_food"

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
            cell["velocity_m_s"] = nonnegative("velocity_m_s", velocity)
            cell["tributary_provenance"]["velocity_m_s"] = cell["velocity_m_s"]
            cell["tributary_provenance"]["velocity_provenance"] = (
                "authored_velocity_depth_sweep_override"
            )
        if depth is not None:
            cell["depth_m"] = positive("depth_m", depth)
            cell["tributary_provenance"]["depth_m"] = cell["depth_m"]
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


def run_mainstem(args) -> dict:
    """Run the scenario and write its artifacts."""

    if args.sub_uilt:
        boundary_c = HOT_LOWFLOW_BOUNDARY_C_SUB_UILT
        boundary_c_source = HOT_LOWFLOW_BOUNDARY_C_SUB_UILT_SOURCE
    else:
        boundary_c = args.boundary_c
        boundary_c_source = HOT_LOWFLOW_BOUNDARY_C_SOURCE

    pulse_doc = _run_pulse(args, boundary_c, args.dispersion_m2_s)
    args.out_replay.parent.mkdir(parents=True, exist_ok=True)
    _shared_json_write(args.out_replay, pulse_doc)

    quasi_steady = _quasi_steady_check(pulse_doc)
    window = _window(args.settle_s, pulse_doc)

    control_doc = load_json(args.control)
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
    _shared_json_write(args.out, document)

    if args.plus_c and not math.isclose(args.plus_c, 0.0):
        plus_boundary = boundary_c + args.plus_c
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
        _shared_json_write(plus_path, plus_doc)

    return document

def run_pockets(args) -> dict:
    """Run the scenario and write its artifacts."""

    control_doc = load_json(args.control)
    pulse_doc = _run_pulse(args, args.boundary_c, args.dispersion_m2_s)
    if args.out_replay is not None:
        _shared_json_write(args.out_replay, pulse_doc)
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
        "run_mode": "scenario",
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
    _shared_json_write(args.out, document)

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
        _shared_json_write(args.out_single_pocket, single_doc_out)
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
        "run_mode": "scenario",
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
    _shared_json_write(args.out_sweep, sweep)

    return document
def _normalize_tributary_record(trib: dict) -> dict:
    """Lift nested analysis fields to the top-level solver keys."""
    out = dict(trib)
    analysis = trib.get("analysis") or {}
    if "temperature_c" not in out and analysis.get("mean_temperature_c") is not None:
        out["temperature_c"] = analysis["mean_temperature_c"]
    if "discharge_m3s" not in out:
        if analysis.get("mean_discharge_m3s") is not None:
            out["discharge_m3s"] = analysis["mean_discharge_m3s"]
        elif analysis.get("mean_discharge_m3_s") is not None:
            out["discharge_m3s"] = analysis["mean_discharge_m3_s"]
    if "habitat_area_m2" not in out and analysis.get("habitat_area_m2") is not None:
        out["habitat_area_m2"] = analysis["habitat_area_m2"]
    return out

def create_tributary_refuge_cells(pulse_doc: dict, world: dict,
                                  tributary_data: dict, *,
                                  n_cells: int = 2) -> dict:
    """Create tributary refuge cells from the evidence artifact into landscape_pocket_cells."""
    modified_doc = copy.deepcopy(pulse_doc)
    try:
        channel = Channel(firehole_chain(world))
    except (KeyError, ValueError, TypeError) as exc:
        channel = None

    real_candidates = [
        _normalize_tributary_record(t)
        for t in tributary_data.get("cold_refuge_candidates", []) or []
    ]
    if not real_candidates:
        real_candidates = [
            _normalize_tributary_record(t)
            for t in tributary_data.get("tributaries", []) or []
        ]

    n_cells = positive_int("n_cells", n_cells)
    if not real_candidates:
        raise ValueError("tributary data has no measured candidate records")
    tributary_cells = []
    for i, trib in enumerate(real_candidates[:n_cells]):
        confluence_s_m = finite("confluence_s_m", trib["confluence_s_m"])
        temp_c = finite("temperature_c", trib["temperature_c"])
        discharge_m3s = positive("discharge_m3s", trib["discharge_m3s"])
        area_m2 = positive("habitat_area_m2", trib["habitat_area_m2"])
        
        # Authored pocket geometry: width = sqrt(4 * habitat area).
        width_m = math.sqrt(area_m2 * 4.0)
        depth_m = area_m2 / width_m
        
        center_s_m = confluence_s_m + 1.5
        start_s_m = confluence_s_m
        end_s_m = confluence_s_m + 3.0
        
        # Resolve position from the channel topology, or mark it unmapped.
        position_xyz = None
        position_status = "chainage_only_not_world_mapped"
        if channel is not None:
            if 0.0 <= float(confluence_s_m) <= channel.length_m:
                position_xyz = channel.position_at(float(confluence_s_m))
                position_status = "channel_position_at_s_m"
            else:
                position_status = (
                    "chainage_outside_channel_length_m_"
                    f"{channel.length_m:.1f}"
                )
        tributary_cell = {
            "id": f"firehole_tributary_{i+1}",
            "length_m": 3.0,
            "width_m": max(4.0, width_m),
            "volume_m3": area_m2 * depth_m,
            "initial_c": temp_c,
            "dispersion_m2_s": 1.0,
            "exchange_w_m2_k": 12.0,
            "geometry_status": "authored_pocket_dimensions_at_measured_chainage",
            "start_s_m": start_s_m,
            "center_s_m": center_s_m,
            "end_s_m": end_s_m,
            "cross_section_m2": width_m * depth_m,
            "surface_area_m2": area_m2,
            "flow_m3_s": discharge_m3s,
            "flow_status": "prescribed_tributary_inflow",
            "representative_velocity_m_s": min(
                0.5, discharge_m3s / (width_m * depth_m)),
            "river_id": "tributary",
            "conservation": "non_conservative",
            "depth_m": depth_m,
            "depth_status": "authored_area_width_relation",
            "depth_source": "authored geometry from evidence artifact habitat area",
            "position_xyz": position_xyz,
            "position_status": position_status,
            "hydraulics": {
                "status": "not_computed",
                "warnings": [
                    "no surveyed tributary geometry or slope supplied",
                    "no hydraulic function fitted to this reach",
                ],
                "provenance": {
                    "top_width": "authored_width_from_usgs_summary_area",
                    "depth": "estimated_from_area_and_width",
                    "slope": "not_computed",
                },
            },
        }
        
        tributary_cells.append(tributary_cell)
        
    
    modified_doc["landscape_pocket_cells"] = tributary_cells
    modified_doc["landscape_pocket_status"] = (
        "evidence_backed_pockets_not_in_solver_array")
    pocket_temps = [float(c["initial_c"]) for c in tributary_cells]
    pocket_q = [float(c["flow_m3_s"]) for c in tributary_cells]
    for frame in modified_doc["frames"]:
        frame.setdefault("landscape_pocket_temperature_c", pocket_temps)
        frame.setdefault("landscape_pocket_flow_m3_s", pocket_q)


    return modified_doc


def run_measured(args) -> dict:
    """Run measured tributary pockets from a required evidence artifact."""
    path = Path(args.tributary_data)
    if not path.is_file():
        raise FileNotFoundError(f"measured tributary data missing: {path}")
    tributaries = load_json(path)
    if tributaries.get("scientific_use") == "prohibited" or "fallback" in tributaries.get("schema", ""):
        raise ValueError(f"measured tributary data required: {path}")
    pulse = _run_pulse(args, args.boundary_c, args.dispersion_m2_s)
    world = {}
    if args.config:
        cfg = load_config(Path(args.config))
        _, world, _, _ = load_inputs(cfg)
    pulse = create_tributary_refuge_cells(pulse, world, tributaries, n_cells=args.tributary_cells)
    control = load_json(args.control)
    document = compare_runs(control, pulse, _window(args.settle_s, pulse),
                            days=args.days, trout_species=args.species)
    document["scenario"] = _scenario_block(args, args.boundary_c, args.dispersion_m2_s,
        HOT_LOWFLOW_BOUNDARY_C_SOURCE, _quasi_steady_check(pulse), args.settle_s)
    document["scenario"]["tributary_data_source"] = str(path.name)
    document["scenario"]["tributary_refuge_cells"] = len(pulse["landscape_pocket_cells"])
    _shared_json_write(args.out_replay, pulse)
    _shared_json_write(args.out, document)
    return document

