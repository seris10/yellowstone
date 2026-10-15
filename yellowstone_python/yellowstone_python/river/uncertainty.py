"""Uncertainty quantification for the lumped reach fit and authored-knob sensitivity."""
from __future__ import annotations
from yellowstone_python.river.obs_model import UPSTREAM_GAUGE, DOWNSTREAM_GAUGE

import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from yellowstone_python.river import calibrate
from yellowstone_python.river.hydraulics import cell_hydraulics, score_paired_series

SCHEMA_UQ = "yellowstone.reach_uq.v1"
ENSEMBLE_SEED = 20261010

DEFAULT_TOL_FRAC = 0.10
DEFAULT_MIN_MEMBERS = 5
DEFAULT_N_BOOTSTRAP = 1000
DEFAULT_SPINUP_S = 86400.0
DEFAULT_TRAIN_FRAC = 0.7
DEFAULT_BAND_LEVEL = 0.90


def uq_provenance(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build UQ_PROVENANCE from actual runtime values when supplied."""
    actual = {
        "ENSEMBLE_SEED": ENSEMBLE_SEED,
        "tol_frac": DEFAULT_TOL_FRAC,
        "min_members": DEFAULT_MIN_MEMBERS,
        "n_bootstrap": DEFAULT_N_BOOTSTRAP,
        "spinup_s": DEFAULT_SPINUP_S,
        "train_frac": DEFAULT_TRAIN_FRAC,
        "band_level": DEFAULT_BAND_LEVEL,
    }
    if settings:
        for key, value in settings.items():
            actual[key] = value
    types = {
        "ENSEMBLE_SEED": "authored_seed",
        "tol_frac": "authored_ensemble_threshold",
        "min_members": "authored_ensemble_size",
        "n_bootstrap": "authored_mc_count",
        "spinup_s": "authored_fit_split",
        "train_frac": "authored_fit_split",
        "band_level": "authored_quantile_level",
    }
    return {
        "status": "authored_knob_sensitivity_fitted_not_validated_single_window",
        "real_data_gap": (
            "No instrument measurement errors, replicate study results, "
            "or calibrated model posteriors available. Reported knob ranges "
            "are authored choices."),
        "parameters": {k: {"value": v, "type": types.get(k, "authored")}
                       for k, v in actual.items()},
    }


UQ_PROVENANCE = uq_provenance()


# Ridge ensemble.

def ridge_members(results: list[dict[str, Any]], champion_train_rmse: float,
                  tol_frac: float = DEFAULT_TOL_FRAC,
                  min_members: int = DEFAULT_MIN_MEMBERS
                  ) -> list[dict[str, Any]]:
    """Grid points within tol_frac of the champion train RMSE."""
    champion_train_rmse = float(champion_train_rmse)
    if not math.isfinite(champion_train_rmse) or champion_train_rmse < 0.0:
        raise ValueError("champion_train_rmse must be finite and >= 0")
    if not math.isfinite(float(tol_frac)) or tol_frac < 0.0:
        raise ValueError("tol_frac must be finite and >= 0")
    if isinstance(min_members, bool) or not isinstance(min_members, int):
        raise ValueError("min_members must be an integer")
    if min_members < 1:
        raise ValueError("min_members must be >= 1")
    if not results:
        raise ValueError("results must be nonempty")
    required_keys = ("q_lat", "t_lat", "c_mult", "train_rmse")
    clean: list[dict[str, Any]] = []
    for row in results:
        missing = [k for k in required_keys if k not in row]
        if missing:
            raise ValueError(f"result row missing keys: {missing}")
        try:
            rmse = float(row["train_rmse"])
        except (TypeError, ValueError) as exc:
            raise ValueError("train_rmse must be numeric") from exc
        if not math.isfinite(rmse):
            continue
        for key in ("q_lat", "t_lat", "c_mult"):
            if not math.isfinite(float(row[key])):
                raise ValueError(f"{key} must be finite")
        if calibrate.candidate_numerically_valid(row):
            clean.append(row)
    cutoff = champion_train_rmse * (1.0 + tol_frac)
    members = [r for r in clean if float(r["train_rmse"]) <= cutoff]
    fallback = False
    if len(members) < min_members:
        members = sorted(clean,
                         key=lambda r: float(r["train_rmse"]))[:min_members]
        fallback = True
    return [{"q_lat": m["q_lat"], "t_lat": m["t_lat"],
             "c_mult": m["c_mult"], "train_rmse": m["train_rmse"],
             "budget_ok": True,
             "inclusion_reason": "valid_within_tolerance" if float(m["train_rmse"]) <= cutoff else "valid_topn_outside_tolerance",
             "membership_rule": "numerical_validity_then_training_rmse",
             "fallback_member": fallback,
             "requested_min_members": min_members,
             "actual_members": len(members),
             "minimum_unavailable": len(clean) < min_members}
            for m in members]


def fit_masks(grid: list[float], spinup_s: float,
              train_frac: float) -> tuple[slice, slice]:
    """Train/holdout slices matching reach_heat_fit's convention."""
    if not 0.0 < train_frac < 1.0:
        raise ValueError("train_frac must be in (0, 1)")
    if not grid:
        raise ValueError("grid must be nonempty")
    if not math.isfinite(float(spinup_s)) or spinup_s < 0.0:
        raise ValueError("spinup_s must be finite and >= 0")
    for a, b in zip(grid, grid[1:]):
        if b <= a:
            raise ValueError("grid must be strictly increasing")
    start_candidates = [i for i, g in enumerate(grid)
                        if g - grid[0] >= spinup_s]
    if not start_candidates:
        raise ValueError("spinup_s leaves no usable data")
    start = start_candidates[0]
    split = start + int((len(grid) - start) * train_frac)
    if split >= len(grid):
        raise ValueError("spinup/train leaves no holdout")
    if split <= start:
        raise ValueError("spinup/train leaves no training data")
    return slice(start, split), slice(split, len(grid))


def member_trajectories(bundle: dict[str, Any], volume_m3: float,
                        area_m2: float, members: Sequence[dict[str, Any]],
                        dt_s: float = 900.0) -> dict[str, Any]:
    """Forward run per ensemble member; returns shared grid + trajectories."""
    if not members:
        raise ValueError("members must be nonempty")
    runs, accepted, rejected = [], [], []
    for member in members:
        if member.get("budget_ok") is False:
            rejected.append({"member": dict(member), "reason": "previously_rejected_numerical_candidate"})
            continue
        forward = calibrate.run_fit_forward(bundle, volume_m3, area_m2,
            member["q_lat"], member["t_lat"], member["c_mult"], dt_s)
        if not calibrate.candidate_numerically_valid(forward):
            rejected.append({"member": dict(member), "reason": "forward_numerical_checks_failed"})
            continue
        runs.append(forward)
        accepted.append(dict(member))
    grids = [r["grid"] for r in runs]
    if any(g != grids[0] for g in grids[1:]):
        raise ValueError("member grids disagree; same bundle/dt required")
    return {"grid": grids[0] if grids else [],
            "trajectories": [r["modeled_c"] for r in runs],
            "members": accepted, "rejected_members": rejected,
            "numerical_validity": "passed" if runs else "unavailable"}


def ensemble_bands(trajectories: Sequence[Sequence[float]],
                   quantiles: tuple[float, float, float] = (0.05, 0.5, 0.95),
                   seed: int = ENSEMBLE_SEED,
                   n_bootstrap: int = 1000) -> dict[str, Any]:
    """Percentile bands + seeded-bootstrap standard error of the edges."""
    lo_q, mid_q, hi_q = quantiles
    for name, value in (("lo", lo_q), ("mid", mid_q), ("hi", hi_q)):
        if not math.isfinite(float(value)):
            raise ValueError(f"quantile {name} must be finite")
    if not 0.0 < lo_q < mid_q < hi_q < 1.0:
        raise ValueError("quantiles must satisfy 0 < lo < mid < hi < 1")
    if isinstance(n_bootstrap, bool) or not isinstance(n_bootstrap, int):
        raise ValueError("n_bootstrap must be an integer")
    if n_bootstrap < 100:
        raise ValueError("n_bootstrap must be >= 100 for stable SEs")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    rows = list(trajectories)
    if len(rows) < 2:
        raise ValueError("need >= 2 member trajectories of equal length")
    first_len = len(rows[0])
    if first_len == 0:
        raise ValueError("trajectories must have at least one timestep")
    for i, row in enumerate(rows[1:], start=1):
        if len(row) != first_len:
            raise ValueError(
                f"trajectory {i} length {len(row)} differs from "
                f"trajectory 0 length {first_len}")
    arr = np.asarray(rows, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2:
        raise ValueError("need >= 2 member trajectories of equal length")
    if arr.shape[1] == 0:
        raise ValueError("trajectories must have at least one timestep")
    if not np.all(np.isfinite(arr)):
        raise ValueError("trajectories must be finite")
    lo = np.quantile(arr, lo_q, axis=0)
    mid = np.quantile(arr, mid_q, axis=0)
    hi = np.quantile(arr, hi_q, axis=0)
    rng = np.random.default_rng(seed)
    n_members = arr.shape[0]
    lo_boot = np.empty((n_bootstrap, arr.shape[1]))
    hi_boot = np.empty((n_bootstrap, arr.shape[1]))
    for b in range(n_bootstrap):
        sample = arr[rng.integers(0, n_members, n_members)]
        lo_boot[b] = np.quantile(sample, lo_q, axis=0)
        hi_boot[b] = np.quantile(sample, hi_q, axis=0)
    return {"quantiles": list(quantiles), "seed": seed,
            "n_bootstrap": n_bootstrap, "n_members": n_members,
            "lo": lo.tolist(), "mid": mid.tolist(), "hi": hi.tolist(),
            "lo_se_mean": float(np.mean(np.std(lo_boot, axis=0))),
            "hi_se_mean": float(np.mean(np.std(hi_boot, axis=0))),
            "band_width_mean": float(np.mean(hi - lo))}


def band_coverage(lo: Sequence[float], hi: Sequence[float],
                  target: Sequence[float]) -> dict[str, float]:
    """Fraction of target points inside [lo, hi]; mean width for context."""
    if not (len(lo) == len(hi) == len(target)) or not target:
        raise ValueError("lo/hi/target must be nonempty and equal length")
    for low, high, tgt in zip(lo, hi, target):
        if not all(math.isfinite(float(v)) for v in (low, high, tgt)):
            raise ValueError("band and target values must be finite")
        if low > high:
            raise ValueError("lower band exceeds upper band")
    inside = sum(1 for low, high, tgt in zip(lo, hi, target)
                 if low <= tgt <= high)
    width = sum(high - low for high, low in zip(hi, lo)) / len(lo)
    return {"n": len(target), "n_inside": inside,
            "coverage": inside / len(target), "mean_width_c": width,
            "interpretation": (
                "fraction of holdout observations inside the "
                "model-ensemble band; not a calibrated predictive "
                "interval")}


# One-at-a-time sensitivity.

_FIT_KNOBS = ("q_lat", "t_lat", "c_mult", "volume_m3", "area_m2")

_FIT_KNOB_BOUNDS = {
    "q_lat": (0.0, math.inf),
    "t_lat": (-100.0, 100.0),
    "c_mult": (0.0, math.inf),
    "volume_m3": (0.0, math.inf),
    "area_m2": (0.0, math.inf),
}


def _validate_knob_value(knob: str, value: float) -> float:
    """Reject non-finite or out-of-range OAT perturbation values."""
    fval = float(value)
    if not math.isfinite(fval):
        raise ValueError(f"{knob} value {value!r} must be finite")
    lo, hi = _FIT_KNOB_BOUNDS[knob]
    if not lo <= fval <= hi:
        raise ValueError(
            f"{knob} value {value!r} outside bounds [{lo}, {hi}]")
    if knob in ("volume_m3", "area_m2") and fval == 0.0:
        raise ValueError(f"{knob} must be positive")
    return fval


def oat_fit(bundle: dict[str, Any], volume_m3: float, area_m2: float,
            champion: dict[str, float],
            perturbations: dict[str, list[float]],
            spinup_s: float = 86400.0, train_frac: float = 0.7,
            dt_s: float = 900.0) -> dict[str, Any]:
    """Holdout-RMSE response to single-knob moves off the champion."""
    for knob in perturbations:
        if knob not in _FIT_KNOBS:
            raise ValueError(f"unknown fit knob {knob!r}")
    for knob, values in perturbations.items():
        for value in values:
            _validate_knob_value(knob, value)
    base = {"q_lat": champion["q_lat"], "t_lat": champion["t_lat"],
            "c_mult": champion["c_mult"], "volume_m3": volume_m3,
            "area_m2": area_m2}
    down = bundle["sites"][DOWNSTREAM_GAUGE]["series"]

    def holdout_rmse(knobs: dict[str, float]) -> float:
        fwd = calibrate.run_fit_forward(
            bundle, knobs["volume_m3"], knobs["area_m2"],
            knobs["q_lat"], knobs["t_lat"], knobs["c_mult"], dt_s)
        _, holdout = fit_masks(fwd["grid"], spinup_s, train_frac)
        target = calibrate.interp_series(
            down["temperature_c"], fwd["grid"])
        return score_paired_series(
            fwd["modeled_c"][holdout], target[holdout])["rmse"]

    baseline = holdout_rmse(base)
    rows = []
    for knob, values in perturbations.items():
        for value in values:
            moved = dict(base)
            moved[knob] = value
            rmse = holdout_rmse(moved)
            rows.append({"knob": knob, "value": value,
                         "holdout_rmse": rmse,
                         "delta_rmse": rmse - baseline})
    rows.sort(key=lambda r: abs(r["delta_rmse"]), reverse=True)
    return {"baseline_holdout_rmse": baseline, "ranking": rows}


DEFAULT_REFUGE_WEIGHT = 0.6


def refuge_weight_oat(landscape: list[dict[str, Any]], species: str,
                      weights: Sequence[float] = (0.3, 0.6, 0.9),
                      food: float = 0.7,
                      cover: float = 0.6) -> list[dict[str, Any]]:
    """Refuge-cell response to REFUGE_WEIGHT at fixed food/cover."""
    from yellowstone_python.aquatic.fish import suitability
    if len(weights) < 2:
        raise ValueError("need >= 2 weights to rank")
    for w in weights:
        if not math.isfinite(float(w)) or not 0.0 <= float(w) <= 1.0:
            raise ValueError("weights must be finite values in [0, 1]")
    if DEFAULT_REFUGE_WEIGHT not in weights:
        raise ValueError(
            f"weights must include the default {DEFAULT_REFUGE_WEIGHT}")
    if not landscape:
        raise ValueError("landscape must be nonempty")
    required = ("id", "s_m", "temperature_c", "velocity_m_s", "depth_m")
    for i, cell in enumerate(landscape):
        for key in required:
            if key not in cell:
                raise ValueError(
                    f"landscape cell {i} missing {key!r}")
        for key in ("s_m", "temperature_c", "velocity_m_s", "depth_m"):
            if not math.isfinite(float(cell[key])):
                raise ValueError(
                    f"landscape cell {i} {key!r} must be finite")
    _ = food
    rows = []
    for w in weights:
        scored = [(suitability(1.0, cover, cell["temperature_c"],
                               cell["velocity_m_s"], cell["depth_m"],
                               species=species, refuge_weight=w),
                   cell["s_m"], cell["id"])
                  for cell in landscape]
        best_u, best_s, best_id = max(scored, key=lambda r: r[0])
        rows.append({"knob": "refuge_weight", "value": w,
                     "refuge_s_m": best_s, "refuge_cell": best_id,
                     "refuge_u": round(best_u, 3)})
    base_s = next(r["refuge_s_m"] for r in rows
                  if math.isclose(float(r["value"]),
                                  DEFAULT_REFUGE_WEIGHT,
                                  rel_tol=0.0, abs_tol=1e-12))
    for r in rows:
        r["shift_vs_default_m"] = round(r["refuge_s_m"] - base_s, 1)
    return rows


_TURNOVER_OUTPUT_KEYS = ("prey_totals", "trout", "dipper")


def turnover_oat(landscape: list[dict[str, Any]],
                 values: Sequence[float] = (1.0, 2.0, 4.0),
                 **foodweb_kwargs: Any) -> list[dict[str, Any]]:
    """run_foodweb reruns over ne_turnover_days on a recorded landscape."""
    from yellowstone_python.aquatic.aquatic_foodweb import run_foodweb
    if len(values) < 2:
        raise ValueError("need >= 2 values to rank")
    for v in values:
        fv = float(v)
        if not math.isfinite(fv) or fv <= 0.0:
            raise ValueError("ne_turnover_days must be finite and > 0")
    rows = []
    for v in values:
        out = run_foodweb(landscape, ne_turnover_days=v, **foodweb_kwargs)
        for key in _TURNOVER_OUTPUT_KEYS:
            if key not in out:
                raise KeyError(
                    f"run_foodweb output missing required key {key!r}")
        if "emergence" not in out["prey_totals"]:
            raise KeyError("run_foodweb prey_totals missing 'emergence'")
        if "s_m" not in out["trout"]:
            raise KeyError("run_foodweb trout missing 's_m'")
        if "intake_total" not in out["dipper"]:
            raise KeyError("run_foodweb dipper missing 'intake_total'")
        rows.append({"knob": "ne_turnover_days", "value": v,
                     "emergence": out["prey_totals"]["emergence"],
                     "trout_s_m": out["trout"]["s_m"],
                     "dipper_intake": out["dipper"]["intake_total"]})
    return rows


def manning_oat(cells: list[dict[str, Any]],
                z_values: Sequence[float] = (1.0, 1.5, 2.0),
                n_values: Sequence[float] = (0.025, 0.035, 0.045)
                ) -> list[dict[str, Any]]:
    """Median Manning-consistency-ratio response to z and n."""
    if len(z_values) < 2 or len(n_values) < 2:
        raise ValueError("need >= 2 values per knob to rank")
    for z in z_values:
        if not math.isfinite(float(z)) or float(z) <= 0.0:
            raise ValueError("bank_slope_zh values must be finite and > 0")
    for n in n_values:
        if not math.isfinite(float(n)) or float(n) <= 0.0:
            raise ValueError("manning_n values must be finite and > 0")
    inputs = []
    for cell in cells:
        hydro = cell.get("hydraulics") or {}
        slope = hydro.get("slope")
        q_in = cell.get("q_in_m3_s")
        q_out = cell.get("q_out_m3_s")
        if slope is None or q_in is None or q_out is None:
            continue
        for key in ("length_m", "width_m", "depth_m"):
            if key not in cell:
                raise KeyError(f"cell missing {key!r}")
        if not math.isfinite(float(slope)) or float(slope) <= 0.0:
            raise ValueError("cell slope must be finite and > 0")
        for key in ("length_m", "width_m", "depth_m"):
            value = float(cell[key])
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"cell {key!r} must be finite and > 0")
        if not math.isfinite(float(q_in)) or not math.isfinite(float(q_out)):
            raise ValueError("cell discharge must be finite")
        inputs.append({"length_m": cell["length_m"],
                       "top_width_m": cell["width_m"],
                       "depth_m": cell["depth_m"],
                       "discharge_m3_s": (q_in + q_out) / 2.0,
                       "slope": slope})
    if not inputs:
        raise ValueError("no cells carry discharge+slope for recompute")

    def median_ratio(z: float, n: float) -> tuple[float | None, int]:
        ratios = []
        for kw in inputs:
            rec = cell_hydraulics(bank_slope_zh=z, manning_n=n, **kw)
            if rec["manning_consistency_ratio"] is not None:
                ratios.append(rec["manning_consistency_ratio"])
        if not ratios:
            return (None, 0)
        return (float(np.median(ratios)), len(ratios))

    def _round(value: float | None) -> float | None:
        return None if value is None else round(value, 3)

    def _delta(value: float | None, base: float | None) -> float | None:
        if value is None or base is None:
            return None
        return round(value - base, 3)

    rows = []
    base_ratio, _base_n = median_ratio(1.5, 0.035)
    for z in z_values:
        ratio, count = median_ratio(z, 0.035)
        rows.append({"knob": "bank_slope_zh", "value": z,
                     "median_consistency_ratio": _round(ratio),
                     "n_defined": count,
                     "delta_vs_default": _delta(ratio, base_ratio)})
    for n in n_values:
        ratio, count = median_ratio(1.5, n)
        rows.append({"knob": "manning_n", "value": n,
                     "median_consistency_ratio": _round(ratio),
                     "n_defined": count,
                     "delta_vs_default": _delta(ratio, base_ratio)})
    return rows


# Document assembly + CLI.

def build_uq_document(bundle: dict[str, Any], volume_m3: float,
                      area_m2: float, fit_results: list[dict[str, Any]],
                      champion: dict[str, Any],
                      perturbations: dict[str, list[float]],
                      spinup_s: float = DEFAULT_SPINUP_S,
                      train_frac: float = DEFAULT_TRAIN_FRAC,
                      dt_s: float = 900.0,
                      band_level: float = DEFAULT_BAND_LEVEL,
                      tol_frac: float = DEFAULT_TOL_FRAC,
                      min_members: int = DEFAULT_MIN_MEMBERS,
                      n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
                      seed: int = ENSEMBLE_SEED) -> dict[str, Any]:
    """Full pass: ensemble bands + coverage + fit OAT ranking."""
    if not math.isfinite(float(band_level)) or not 0.0 < band_level < 1.0:
        raise ValueError("band_level must be in (0, 1)")
    champ_key = (champion["q_lat"], champion["t_lat"], champion["c_mult"])
    if not any(math.isclose(float(r["q_lat"]), champ_key[0],
                            rel_tol=0.0, abs_tol=1e-12)
               and math.isclose(float(r["t_lat"]), champ_key[1],
                                rel_tol=0.0, abs_tol=1e-12)
               and math.isclose(float(r["c_mult"]), champ_key[2],
                                rel_tol=0.0, abs_tol=1e-12)
               for r in fit_results):
        raise ValueError("recorded champion is absent from fit results")
    members = ridge_members(fit_results, champion["train_rmse"],
                            tol_frac=tol_frac, min_members=min_members)
    trajs = member_trajectories(bundle, volume_m3, area_m2, members, dt_s)
    tail = (1.0 - band_level) / 2.0
    bands = ensemble_bands(trajs["trajectories"],
                           quantiles=(tail, 0.5, 1.0 - tail),
                           seed=seed, n_bootstrap=n_bootstrap)
    _, holdout = fit_masks(trajs["grid"], spinup_s, train_frac)
    target = calibrate.interp_series(
        bundle["sites"][DOWNSTREAM_GAUGE]["series"]["temperature_c"],
        trajs["grid"])
    holdout_target = target[holdout]
    coverage = band_coverage(
        bands["lo"][holdout], bands["hi"][holdout], holdout_target)
    oat = oat_fit(bundle, volume_m3, area_m2, champion, perturbations,
                  spinup_s, train_frac, dt_s)
    provenance = uq_provenance({"tol_frac": tol_frac,
                                "min_members": min_members,
                                "n_bootstrap": n_bootstrap,
                                "spinup_s": spinup_s,
                                "train_frac": train_frac,
                                "band_level": band_level,
                                "ENSEMBLE_SEED": seed})
    return {
        "schema": SCHEMA_UQ,
        "status": "fitted_not_validated_single_window",
        "fetched_at_utc": bundle.get("fetched_at_utc"),
        "effective_geometry": {"volume_m3": volume_m3, "area_m2": area_m2,
                               "status": ("authored_illustrative_effective_"
                                          "mixing_volume")},
        "ridge_rule": {"tol_frac": tol_frac, "min_members": min_members,
                       "n_members": len(members),
                       "fallback_to_topn": any(
                           m["fallback_member"] for m in members)},
        "members": [{k: m[k] for k in ("q_lat", "t_lat", "c_mult",
                                       "train_rmse")} for m in members],
        "bands": {**{k: v for k, v in bands.items()
                     if k in ("quantiles", "seed", "n_bootstrap",
                              "n_members", "lo_se_mean", "hi_se_mean",
                              "band_width_mean")},
                  "level": band_level},
        "holdout_coverage": {**coverage, "nominal": band_level},
        "fit_oat": oat,
        "uncertainty_provenance": provenance,
    }


def _dedup_perturbation(values: Sequence[float],
                        baseline: float) -> list[float]:
    """Drop champion-equal values; preserve input order after dedup."""
    seen: list[float] = []
    for v in values:
        fv = float(v)
        if math.isclose(fv, float(baseline), rel_tol=0.0, abs_tol=1e-12):
            continue
        if any(math.isclose(fv, u, rel_tol=0.0, abs_tol=1e-12)
               for u in seen):
            continue
        seen.append(fv)
    return seen
