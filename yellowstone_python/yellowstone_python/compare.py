"""A/B outcome comparison between two build dirs: endpoint deltas plus a compatibility report."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


SCHEMA = "yellowstone.ab_comparison.v2"


def _load(d: Path, name: str) -> Any:
    path = d / name
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ValueError(f"missing build artifact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _index_records(records: Any, label: str) -> dict[str, dict]:
    if not isinstance(records, list):
        raise ValueError(f"{label} must be a list")
    result: dict[str, dict] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"{label}[{index}] lacks a valid id")
        if record_id in result:
            raise ValueError(f"duplicate {label} id {record_id!r}")
        result[record_id] = record
    return result


def _required_metric(metrics: dict, *names: str) -> float:
    for name in names:
        if name in metrics:
            value = metrics[name]
            try:
                result = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"metric {name!r} is not numeric: {value!r}") from exc
            if not math.isfinite(result):
                raise ValueError(f"metric {name!r} is non-finite")
            return result
    raise ValueError(
        f"none of the required metric names found: {names}")


def _load_build_manifest(directory: Path) -> dict:
    path = directory / "BUILD.json"
    if not path.is_file():
        raise ValueError(f"missing BUILD.json in {directory}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid BUILD.json in {directory}: {exc}") from exc


def _compatibility_report(a_manifest: dict,
                          b_manifest: dict) -> dict[str, Any]:
    """Named differences between two build manifests that invalidate a
straight A/B comparison. Each entry is (field, A value, B value)."""
    checks: list[tuple[str, Any, Any]] = [
        ("world_id",
         a_manifest.get("world_id"),
         b_manifest.get("world_id")),
        ("contract_version",
         a_manifest.get("contract_version"),
         b_manifest.get("contract_version")),
        ("configuration_hash",
         a_manifest.get("configuration_hash"),
         b_manifest.get("configuration_hash")),
        ("code_sha256",
         a_manifest.get("code_sha256"),
         b_manifest.get("code_sha256")),
        ("input_datasets.terrain.sha256",
         a_manifest.get("input_datasets", {}).get("terrain", {}).get("sha256"),
         b_manifest.get("input_datasets", {}).get("terrain", {}).get("sha256")),
        ("grid_and_time_step.replay_dt_s",
         a_manifest.get("grid_and_time_step", {}).get("replay_dt_s"),
         b_manifest.get("grid_and_time_step", {}).get("replay_dt_s")),
        ("grid_and_time_step.replay_duration_s",
         a_manifest.get("grid_and_time_step", {}).get("replay_duration_s"),
         b_manifest.get("grid_and_time_step", {}).get("replay_duration_s")),
        ("run_mode",
         a_manifest.get("run_mode"),
         b_manifest.get("run_mode")),
    ]
    diffs: list[str] = []
    for name, va, vb in checks:
        if va != vb:
            diffs.append(f"{name} differs: {va!r} vs {vb!r}")
    return {"comparable": not diffs, "differences": diffs}


def _refuge_location(record: dict) -> tuple:
    return (record.get("reach_id"), record.get("end_point_index"),
            record.get("refuge_s_m"), record.get("start_point_index"))


def _unwrap_replay(doc: Any) -> dict | None:
    if isinstance(doc, dict):
        if "frames" in doc and "cells" in doc:
            return doc
        inner = doc.get("replay")
        if isinstance(inner, dict):
            return _unwrap_replay(inner)
    return None


def _max_surface_linearization_w(replay: dict | None) -> float | None:
    if not isinstance(replay, dict):
        return None
    budget = replay.get("final_budget")
    if not isinstance(budget, dict):
        return None
    return _finite_float_or_none(budget.get("max_surface_linearization_error_w"))


def _finite_float_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _calibration_rmse_c(build_dir: Path) -> tuple[float | None, str]:
    """Holdout rmse from the thermal calibration artifact, when present.
Returns (value, source); searches build dir then reach-claim evidence paths."""
    from yellowstone_python.registry.claims import get_claim, resolve_artifact_id
    local = build_dir / "reach_heat_fit_v300k.json"
    try:
        if local.is_file():
            doc = json.loads(local.read_text(encoding="utf-8"))
            value = _finite_float_or_none(doc.get("holdout_rmse"))
            if value is not None:
                return value, str(local)
    except (OSError, json.JSONDecodeError):
        pass
    try:
        claim = get_claim("reach_water_temperature_ice_free")
    except KeyError:
        return None, "claim_absent"
    for aid in claim.get("evidence_artifact_ids", []):
        try:
            path = resolve_artifact_id(aid)
        except (ValueError, FileNotFoundError):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        value = _finite_float_or_none(doc.get("holdout_rmse"))
        if value is not None:
            return value, str(path)
    return None, "no_holdout_rmse_in_evidence"


def _common_cell_ids(replay_a: dict, replay_b: dict) -> list[str]:
    """Cell ids present and well-formed in both replay documents."""
    a_ids: list[str] = []
    for cell in replay_a.get("cells", []):
        if isinstance(cell, dict):
            cid = cell.get("id")
            if isinstance(cid, str):
                a_ids.append(cid)
    b_ids: set[str] = set()
    for cell in replay_b.get("cells", []):
        if isinstance(cell, dict):
            cid = cell.get("id")
            if isinstance(cid, str):
                b_ids.add(cid)
    return [cid for cid in a_ids if cid in b_ids]


def _aligned_frame_times(replay_a: dict, replay_b: dict) -> list[float]:
    """Shared frame times from each replay rounded to the microsecond.
Returns the intersection of exact t_s values so both runs sample one clock."""
    def _times(doc: dict) -> list[float]:
        out: list[float] = []
        for frame in doc.get("frames", []):
            if not isinstance(frame, dict):
                continue
            t = _required_metric({"t_s": frame.get("t_s")}, "t_s") \
                if "t_s" in frame else None
            if t is None:
                continue
            out.append(round(t, 6))
        return out

    a_times = _times(replay_a)
    b_times = _times(replay_b)
    b_set = set(b_times)
    return [t for t in a_times if t in b_set]


def _temperature_series(replay: dict, cell_id: str,
                        times: list[float]) -> list[float] | None:
    """Per-cell temperature series sampled at the given frame times."""
    cells = [c.get("id") for c in replay.get("cells", [])
             if isinstance(c, dict)]
    if cell_id not in cells:
        return None
    index = cells.index(cell_id)
    series: dict[float, float] = {}
    for frame in replay.get("frames", []):
        if not isinstance(frame, dict):
            continue
        t = frame.get("t_s")
        temps = frame.get("temperature_c")
        if not isinstance(temps, list) or not isinstance(t, (int, float)):
            continue
        if index >= len(temps):
            return None
        value = temps[index]
        try:
            fv = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(fv):
            return None
        series[round(float(t), 6)] = fv
    try:
        return [series[t] for t in times]
    except KeyError:
        return None


def _trajectory_report(replay_a: dict | None, replay_b: dict | None,
                       thresholds_c: list[float]) -> dict[str, Any]:
    """Per-cell exposure and peak metrics across common cells and times."""
    if replay_a is None or replay_b is None:
        return {"status": "replay_frames_unavailable",
                "common_cells": 0,
                "common_frames": 0,
                "exposure_thresholds_c": thresholds_c}
    times = _aligned_frame_times(replay_a, replay_b)
    if len(times) < 2:
        return {"status": "no_common_frame_times",
                "common_cells": 0,
                "common_frames": len(times),
                "exposure_thresholds_c": thresholds_c}
    cells = _common_cell_ids(replay_a, replay_b)
    peak_a_c = float("-inf")
    peak_b_c = float("-inf")
    peak_a_t = None
    peak_b_t = None
    peak_a_cell = None
    peak_b_cell = None
    max_abs_delta_c = 0.0
    sum_abs_delta_c = 0.0
    sum_signed_delta_c = 0.0
    n_samples = 0
    exposure_a = {str(th): 0.0 for th in thresholds_c}
    exposure_b = {str(th): 0.0 for th in thresholds_c}
    degree_hours_a = {str(th): 0.0 for th in thresholds_c}
    degree_hours_b = {str(th): 0.0 for th in thresholds_c}
    examined_cells = 0
    for cell_id in cells:
        series_a = _temperature_series(replay_a, cell_id, times)
        series_b = _temperature_series(replay_b, cell_id, times)
        if series_a is None or series_b is None:
            continue
        examined_cells += 1
        for i, t in enumerate(times):
            if series_a[i] > peak_a_c:
                peak_a_c = series_a[i]
                peak_a_t = t
                peak_a_cell = cell_id
            if series_b[i] > peak_b_c:
                peak_b_c = series_b[i]
                peak_b_t = t
                peak_b_cell = cell_id
            delta = series_b[i] - series_a[i]
            if abs(delta) > max_abs_delta_c:
                max_abs_delta_c = abs(delta)
            sum_abs_delta_c += abs(delta)
            sum_signed_delta_c += delta
            n_samples += 1
        # Trapezoidal integration over the shared time axis.
        for i in range(1, len(times)):
            dt_h = (times[i] - times[i - 1]) / 3600.0
            if dt_h <= 0.0:
                continue
            for th in thresholds_c:
                key = str(th)
                a_lo = max(0.0, series_a[i - 1] - th)
                a_hi = max(0.0, series_a[i] - th)
                b_lo = max(0.0, series_b[i - 1] - th)
                b_hi = max(0.0, series_b[i] - th)
                exposure_a[key] += dt_h if (a_lo > 0.0 or a_hi > 0.0) else 0.0
                exposure_b[key] += dt_h if (b_lo > 0.0 or b_hi > 0.0) else 0.0
                degree_hours_a[key] += 0.5 * (a_lo + a_hi) * dt_h
                degree_hours_b[key] += 0.5 * (b_lo + b_hi) * dt_h
    if n_samples == 0:
        return {"status": "no_common_cell_series",
                "common_cells": 0,
                "common_frames": len(times),
                "exposure_thresholds_c": thresholds_c}
    return {
        "status": "ok",
        "common_cells": examined_cells,
        "common_frames": len(times),
        "exposure_thresholds_c": thresholds_c,
        "window": {"t_start_s": times[0], "t_end_s": times[-1],
                   "duration_s": times[-1] - times[0]},
        "temperature": {
            "max_abs_delta_c": round(max_abs_delta_c, 6),
            "mean_abs_delta_c": round(sum_abs_delta_c / n_samples, 6),
            "mean_signed_delta_c": round(sum_signed_delta_c / n_samples, 6),
            "peak_A": {"temperature_c": round(peak_a_c, 3),
                       "t_s": peak_a_t, "cell_id": peak_a_cell},
            "peak_B": {"temperature_c": round(peak_b_c, 3),
                       "t_s": peak_b_t, "cell_id": peak_b_cell},
        },
        "exposure_hours": {"A": {k: round(v, 4) for k, v in exposure_a.items()},
                           "B": {k: round(v, 4) for k, v in exposure_b.items()}},
        "degree_hours_above": {
            "A": {k: round(v, 4) for k, v in degree_hours_a.items()},
            "B": {k: round(v, 4) for k, v in degree_hours_b.items()},
        },
    }


def _interpretation(a_dir: Path, b_dir: Path, replay_a: dict | None,
                    replay_b: dict | None,
                    reaches: list[dict]) -> dict[str, Any]:
    """Named uncertainty, calibration and significance context."""
    rmse, rmse_source = _calibration_rmse_c(a_dir)
    rmse_b, _ = _calibration_rmse_c(b_dir)
    if rmse is None and rmse_b is not None:
        rmse, rmse_source = rmse_b, "B " + rmse_source
    lin_a = _max_surface_linearization_w(replay_a)
    lin_b = _max_surface_linearization_w(replay_b)
    lin_values = [v for v in (lin_a, lin_b) if v is not None]
    max_lin = max(lin_values) if lin_values else None
    reach_deltas_c = [abs(float(r.get("d_temp_c", 0.0))) for r in reaches]
    max_reach_delta_c = max(reach_deltas_c) if reach_deltas_c else None
    if rmse is None or max_reach_delta_c is None:
        significance = "not_assessed"
    elif max_reach_delta_c <= rmse:
        significance = "below_calibration_rmse"
    else:
        significance = "above_calibration_rmse"
    return {
        "calibration_rmse_c": rmse,
        "calibration_rmse_source": rmse_source,
        "max_surface_linearization_error_w": max_lin,
        "max_reach_delta_c": max_reach_delta_c,
        "difference_significance": significance,
        "note": ("significance compares the maximum reach delta_C against "
                 "the holdout rmse of the thermal calibration; it is a "
                 "coarse screen, not a hypothesis test"),
    }


VALID_MODES = ("endpoint", "trajectory")
DEFAULT_EXPOSURE_THRESHOLDS_C = (20.0, 24.0)


def compare_builds(a_dir: str | Path, b_dir: str | Path,
                   allow_incompatible: bool = False,
                   mode: str = "endpoint",
                   exposure_thresholds_c: list[float] | None = None,
                   ) -> dict:
    if mode not in VALID_MODES:
        raise ValueError(
            f"mode {mode!r} unknown; choose from {list(VALID_MODES)}")
    thresholds = (list(exposure_thresholds_c) if exposure_thresholds_c
                  else list(DEFAULT_EXPOSURE_THRESHOLDS_C))
    a, b = Path(a_dir), Path(b_dir)
    try:
        a_manifest = _load_build_manifest(a)
        b_manifest = _load_build_manifest(b)
        compat = _compatibility_report(a_manifest, b_manifest)
    except ValueError as exc:
        compat = {"comparable": False,
                  "differences": [f"manifest error: {exc}"]}
        a_manifest = {}
        b_manifest = {}
    if not compat["comparable"] and not allow_incompatible:
        return {
            "schema": SCHEMA,
            "A": {"name": a.name,
                  "build_id": a_manifest.get("build_id")},
            "B": {"name": b.name,
                  "build_id": b_manifest.get("build_id")},
            "compatibility": compat,
            "comparison_refused": True,
            "scope": {"comparison_type": mode,
                      "duration_metrics_included": mode == "trajectory"},
        }
    ra = _index_records(_load(a, "river_state.json"), "river_state")
    rb = _index_records(_load(b, "river_state.json"), "river_state")
    reach_common = sorted(ra.keys() & rb.keys())
    reach_only_a = sorted(ra.keys() - rb.keys())
    reach_only_b = sorted(rb.keys() - ra.keys())
    reaches = [{"id": rid,
                "d_temp_c": round(rb[rid]["temperature_c"]
                                  - ra[rid]["temperature_c"], 3),
                "d_flow_m3s": round(rb[rid]["flow_m3s"]
                                    - ra[rid]["flow_m3s"], 4)}
               for rid in reach_common]
    fa = _index_records(_load(a, "fish.json")["wildlife"], "fish.wildlife")
    fb = _index_records(_load(b, "fish.json")["wildlife"], "fish.wildlife")
    trout_common = sorted(fa.keys() & fb.keys())
    trout_only_a = sorted(fa.keys() - fb.keys())
    trout_only_b = sorted(fb.keys() - fa.keys())
    trout = []
    for tid in trout_common:
        if "hold_seconds" not in fa[tid] or "hold_seconds" not in fb[tid]:
            raise ValueError(
                f"trout {tid!r}: missing hold_seconds metric")
        trout.append({
            "id": tid,
            "reach": (fa[tid].get("reach_id"), fb[tid].get("reach_id")),
            "d_hold_s": round(fb[tid]["hold_seconds"]
                              - fa[tid]["hold_seconds"], 2),
            "selected_location_changed":
                _refuge_location(fa[tid]) != _refuge_location(fb[tid]),
        })
    ia, ib = _load(a, "insect_bird.json"), _load(b, "insect_bird.json")
    for name, record in (("A", ia), ("B", ib)):
        if "activity" not in record:
            raise ValueError(
                f"insect_bird.json {name}: missing activity metric")
    sa, sb = _load(a, "season.json"), _load(b, "season.json")
    ma = _index_records(sa["patches"], "season.patches.A")
    mb = _index_records(sb["patches"], "season.patches.B")
    patch_common = sorted(ma.keys() & mb.keys())
    patches_only_a = sorted(ma.keys() - mb.keys())
    patches_only_b = sorted(mb.keys() - ma.keys())
    snow = []
    for pid in patch_common:
        if "snow_mm" not in ma[pid] or "snow_mm" not in mb[pid]:
            raise ValueError(
                f"season.patches {pid!r}: missing snow_mm metric")
        snow.append({
            "id": pid,
            "d_snow_mm": round(mb[pid]["snow_mm"] - ma[pid]["snow_mm"], 2),
            "phenology": (ma[pid].get("phenology"), mb[pid].get("phenology")),
            "d_gdd": (round(mb[pid]["gdd"] - ma[pid]["gdd"], 3)
                      if "gdd" in ma[pid] and "gdd" in mb[pid] else None),
        })
    ca = _load(a, "CHECKS.json")["metrics"]
    cb = _load(b, "CHECKS.json")["metrics"]
    heat_a_residual = _required_metric(
        ca, "replay_heat_budget_error", "heat_relative_residual")
    heat_b_residual = _required_metric(
        cb, "replay_heat_budget_error", "heat_relative_residual")
    activity_a = _required_metric(ia, "activity")
    activity_b = _required_metric(ib, "activity")
    replay_a = None
    replay_b = None
    if mode == "trajectory":
        try:
            replay_a = _unwrap_replay(_load(a, "river_replay.json"))
        except ValueError:
            replay_a = None
        try:
            replay_b = _unwrap_replay(_load(b, "river_replay.json"))
        except ValueError:
            replay_b = None
    trajectory = (_trajectory_report(replay_a, replay_b, thresholds)
                  if mode == "trajectory" else None)
    interpretation = _interpretation(a, b, replay_a, replay_b, reaches)
    scope_note = ("endpoint comparison; trajectory mode (--mode trajectory) "
                  "reads frames for exposure-duration metrics")
    if mode == "trajectory":
        scope_note = ("trajectory comparison on common cells and frame "
                      "times; thresholds in exposure_thresholds_c")
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "A": {"name": a.name, "build_id": a_manifest.get("build_id")},
        "B": {"name": b.name, "build_id": b_manifest.get("build_id")},
        "compatibility": compat,
        "structure": {
            "common_reaches": reach_common,
            "reaches_only_A": reach_only_a,
            "reaches_only_B": reach_only_b,
            "common_trout": trout_common,
            "trout_only_A": trout_only_a,
            "trout_only_B": trout_only_b,
            "common_patches": patch_common,
            "patches_only_A": patches_only_a,
            "patches_only_B": patches_only_b,
        },
        "reach_deltas": reaches,
        "trout": trout,
        "insect": {"activity_A": activity_a,
                   "activity_B": activity_b,
                   "delta": round(activity_b - activity_a, 4)},
        "snow": snow,
        "heat_budget": {
            "A": {"residual_j": heat_a_residual},
            "B": {"residual_j": heat_b_residual},
            "delta_residual_j": round(heat_b_residual - heat_a_residual, 12),
        },
        "interpretation": interpretation,
        "scope": {
            "comparison_type": mode,
            "duration_metrics_included": mode == "trajectory",
            "exposure_thresholds_c": thresholds,
            "note": scope_note,
        },
    }
    if trajectory is not None:
        out["trajectory"] = trajectory
    return out






def main() -> int:
    """Run the command-line interface."""
    from yellowstone_python.cli.compare import main as command
    return command()


if __name__ == "__main__":
    raise SystemExit(main())
