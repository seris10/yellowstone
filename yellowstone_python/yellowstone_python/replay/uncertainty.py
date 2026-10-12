"""Uncertainty quantification for the lumped reach fit and authored-knob sensitivity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from . import calibrate
from .hydraulics import cell_hydraulics, score_paired_series

SCHEMA_UQ = "yellowstone.reach_uq.v1"
ENSEMBLE_SEED = 20261010

# All parameters AUTHORED (not derived from measurement error): ENSEMBLE_SEED, tol_frac, min_members, n_bootstrap, spinup_s, train_frac, band_level. Module reports fit ambiguity, not predictive calibration.
UQ_PROVENANCE = {
    "status": "authored_knob_sensitivity_fitted_not_validated_single_window",
    "real_data_gap": ("No instrument measurement errors, replicate study results, "
                      "or calibrated model posteriors available. All ranges (tol_frac, "
                      "min_members, n_bootstrap, spinup/train split) are authored choices. "
                      "Integration point: external calibrated model outputs or instrument specs."),
    "parameters": {
        "ENSEMBLE_SEED": {"value": ENSEMBLE_SEED, "type": "authored_seed"},
        "tol_frac": {"value": 0.10, "type": "authored_ensemble_threshold"},
        "min_members": {"value": 5, "type": "authored_ensemble_size"},
        "n_bootstrap": {"value": 1000, "type": "authored_mc_count"},
        "spinup_s": {"value": 86400.0, "type": "authored_fit_split"},
        "train_frac": {"value": 0.7, "type": "authored_fit_split"},
    },
}


# ---------------------------------------------------------------------------
# 1. Ridge ensemble
# ---------------------------------------------------------------------------

def ridge_members(results: list[dict[str, Any]], champion_train_rmse: float,
                  tol_frac: float = 0.10,
                  min_members: int = 5) -> list[dict[str, Any]]:
    """Grid points within tol_frac of the champion train RMSE.

    Falls back to the top-min_members by train RMSE when the ridge rule
    admits fewer (a tight optimum is still an ensemble of one plus its
    nearest neighbors, and the fallback is recorded by the caller).
    """
    if champion_train_rmse < 0.0:
        raise ValueError("champion_train_rmse must be >= 0")
    if not 0.0 <= tol_frac:
        raise ValueError("tol_frac must be >= 0")
    cutoff = champion_train_rmse * (1.0 + tol_frac)
    members = [r for r in results if r["train_rmse"] <= cutoff]
    fallback = False
    if len(members) < min_members:
        members = sorted(results,
                         key=lambda r: r["train_rmse"])[:min_members]
        fallback = True
    return [{"q_lat": m["q_lat"], "t_lat": m["t_lat"],
             "c_mult": m["c_mult"], "train_rmse": m["train_rmse"],
             "fallback_member": fallback} for m in members]


def fit_masks(grid: list[float], spinup_s: float,
              train_frac: float) -> tuple[slice, slice]:
    """Train/holdout slices matching reach_heat_fit's convention."""
    if not 0.0 < train_frac < 1.0:
        raise ValueError("train_frac must be in (0, 1)")
    start = next(i for i, g in enumerate(grid) if g - grid[0] >= spinup_s)
    split = start + int((len(grid) - start) * train_frac)
    if split >= len(grid):
        raise ValueError("spinup/train leaves no holdout")
    return slice(start, split), slice(split, len(grid))


def member_trajectories(bundle: dict[str, Any], volume_m3: float,
                        area_m2: float, members: Sequence[dict[str, Any]],
                        dt_s: float = 900.0) -> dict[str, Any]:
    """Forward run per ensemble member; returns shared grid + trajectories."""
    if not members:
        raise ValueError("members must be nonempty")
    runs = [calibrate.run_fit_forward(bundle, volume_m3, area_m2,
                                      m["q_lat"], m["t_lat"], m["c_mult"],
                                      dt_s)
            for m in members]
    grids = [r["grid"] for r in runs]
    if any(g != grids[0] for g in grids[1:]):
        raise ValueError("member grids disagree; same bundle/dt required")
    return {"grid": grids[0],
            "trajectories": [r["modeled_c"] for r in runs]}


def ensemble_bands(trajectories: Sequence[Sequence[float]],
                   quantiles: tuple[float, float, float] = (0.05, 0.5, 0.95),
                   seed: int = ENSEMBLE_SEED,
                   n_bootstrap: int = 1000) -> dict[str, Any]:
    """Percentile bands + seeded-bootstrap standard error of the edges. Bands are cross-member percentiles at each timestep. Bootstrap resamples members with replacement."""
    lo_q, mid_q, hi_q = quantiles
    if not 0.0 < lo_q < mid_q < hi_q < 1.0:
        raise ValueError("quantiles must satisfy 0 < lo < mid < hi < 1")
    if n_bootstrap < 100:
        raise ValueError("n_bootstrap must be >= 100 for stable SEs")
    arr = np.asarray(trajectories, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2:
        raise ValueError("need >= 2 member trajectories of equal length")
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
    inside = sum(1 for l, h, t in zip(lo, hi, target) if l <= t <= h)
    width = sum(h - l for h, l in zip(hi, lo)) / len(lo)
    return {"n": len(target), "n_inside": inside,
            "coverage": inside / len(target), "mean_width_c": width}


# ---------------------------------------------------------------------------
# 2. One-at-a-time sensitivity
# ---------------------------------------------------------------------------

_FIT_KNOBS = ("q_lat", "t_lat", "c_mult", "volume_m3", "area_m2")


def oat_fit(bundle: dict[str, Any], volume_m3: float, area_m2: float,
            champion: dict[str, float],
            perturbations: dict[str, list[float]],
            spinup_s: float = 86400.0, train_frac: float = 0.7,
            dt_s: float = 900.0) -> dict[str, Any]:
    """Holdout-RMSE response to single-knob moves off the champion.

    Each row reruns the forward model with exactly one knob changed;
    the baseline row reruns the champion itself (a rerun, not the
    recorded number, so deltas are self-consistent).
    """
    for knob in perturbations:
        if knob not in _FIT_KNOBS:
            raise ValueError(f"unknown fit knob {knob!r}")
    base = {"q_lat": champion["q_lat"], "t_lat": champion["t_lat"],
            "c_mult": champion["c_mult"], "volume_m3": volume_m3,
            "area_m2": area_m2}
    down = bundle["sites"]["06036905"]["series"]

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


def refuge_weight_oat(landscape: list[dict[str, Any]], species: str,
                      weights: Sequence[float] = (0.3, 0.6, 0.9),
                      food: float = 0.7,
                      cover: float = 0.6) -> list[dict[str, Any]]:
    """Refuge-cell response to REFUGE_WEIGHT at fixed food/cover.

    Food is held uniform (food/ceiling = 1 everywhere) to isolate the
    refuge-drive term: this measures the weight's leverage on selection,
    not a foraging outcome. Response is the argmax-U cell chainage.
    """
    from ..fish import suitability
    if len(weights) < 2:
        raise ValueError("need >= 2 weights to rank")
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
    base_s = next(r["refuge_s_m"] for r in rows if r["value"] == 0.6)
    for r in rows:
        r["shift_vs_default_m"] = round(r["refuge_s_m"] - base_s, 1)
    return rows


def turnover_oat(landscape: list[dict[str, Any]],
                 values: Sequence[float] = (1.0, 2.0, 4.0),
                 **foodweb_kwargs: Any) -> list[dict[str, Any]]:
    """run_foodweb reruns over ne_turnover_days on a recorded landscape."""
    from ..aquatic_foodweb import run_foodweb
    if len(values) < 2:
        raise ValueError("need >= 2 values to rank")
    rows = []
    for v in values:
        out = run_foodweb(landscape, ne_turnover_days=v, **foodweb_kwargs)
        rows.append({"knob": "ne_turnover_days", "value": v,
                     "emergence": out["prey_totals"]["emergence"],
                     "trout_s_m": out["trout"]["s_m"],
                     "dipper_intake": out["dipper"]["intake_total"]})
    return rows


def manning_oat(cells: list[dict[str, Any]],
                z_values: Sequence[float] = (1.0, 1.5, 2.0),
                n_values: Sequence[float] = (0.025, 0.035, 0.045)
                ) -> list[dict[str, Any]]:
    """Median Manning-consistency-ratio response to z and n. Recomputes cell_hydraulics per recorded cell with one authored knob varied; cells where Manning is undefined stay excluded."""
    if len(z_values) < 2 or len(n_values) < 2:
        raise ValueError("need >= 2 values per knob to rank")
    inputs = []
    for cell in cells:
        hydro = cell.get("hydraulics") or {}
        slope = hydro.get("slope")
        q_in = cell.get("q_in_m3_s")
        q_out = cell.get("q_out_m3_s")
        if slope is None or q_in is None or q_out is None:
            continue
        inputs.append({"length_m": cell["length_m"],
                       "top_width_m": cell["width_m"],
                       "depth_m": cell["depth_m"],
                       "discharge_m3_s": (q_in + q_out) / 2.0,
                       "slope": slope})
    if not inputs:
        raise ValueError("no cells carry discharge+slope for recompute")

    def median_ratio(z: float, n: float) -> tuple[float, int]:
        ratios = []
        for kw in inputs:
            rec = cell_hydraulics(bank_slope_zh=z, manning_n=n, **kw)
            if rec["manning_consistency_ratio"] is not None:
                ratios.append(rec["manning_consistency_ratio"])
        return (float(np.median(ratios)), len(ratios))

    rows = []
    base_ratio, base_n = median_ratio(1.5, 0.035)
    for z in z_values:
        ratio, count = median_ratio(z, 0.035)
        rows.append({"knob": "bank_slope_zh", "value": z,
                     "median_consistency_ratio": round(ratio, 3),
                     "n_defined": count,
                     "delta_vs_default": round(ratio - base_ratio, 3)})
    for n in n_values:
        ratio, count = median_ratio(1.5, n)
        rows.append({"knob": "manning_n", "value": n,
                     "median_consistency_ratio": round(ratio, 3),
                     "n_defined": count,
                     "delta_vs_default": round(ratio - base_ratio, 3)})
    _ = base_n
    return rows


# ---------------------------------------------------------------------------
# Document assembly + CLI
# ---------------------------------------------------------------------------

def build_uq_document(bundle: dict[str, Any], volume_m3: float,
                      area_m2: float, fit_results: list[dict[str, Any]],
                      champion: dict[str, Any],
                      perturbations: dict[str, list[float]],
                      spinup_s: float = 86400.0, train_frac: float = 0.7,
                      dt_s: float = 900.0,
                      band_level: float = 0.90,
                      seed: int = ENSEMBLE_SEED) -> dict[str, Any]:
    """Full pass: ensemble bands + coverage + fit OAT ranking."""
    members = ridge_members(fit_results, champion["train_rmse"])
    trajs = member_trajectories(bundle, volume_m3, area_m2, members, dt_s)
    tail = (1.0 - band_level) / 2.0
    bands = ensemble_bands(trajs["trajectories"],
                           quantiles=(tail, 0.5, 1.0 - tail), seed=seed)
    _, holdout = fit_masks(trajs["grid"], spinup_s, train_frac)
    target = calibrate.interp_series(
        bundle["sites"]["06036905"]["series"]["temperature_c"],
        trajs["grid"])
    holdout_target = target[holdout]
    coverage = band_coverage(
        bands["lo"][holdout], bands["hi"][holdout], holdout_target)
    oat = oat_fit(bundle, volume_m3, area_m2, champion, perturbations,
                  spinup_s, train_frac, dt_s)
    return {
        "schema": SCHEMA_UQ,
        "status": "fitted_not_validated_single_window",
        "fetched_at_utc": bundle.get("fetched_at_utc"),
        "effective_geometry": {"volume_m3": volume_m3, "area_m2": area_m2,
                               "status": ("authored_illustrative_effective_"
                                          "mixing_volume")},
        "ridge_rule": {"tol_frac": 0.10, "min_members": 5,
                       "n_members": len(members),
                       "fallback_to_top5": any(
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
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obs", type=Path, required=True)
    parser.add_argument("--fit", type=Path, required=True,
                        help="reach_heat_fit artifact (grids + champion)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--volume-m3", type=float, required=True)
    parser.add_argument("--area-m2", type=float, required=True)
    args = parser.parse_args()
    try:
        bundle = json.loads(args.obs.read_text(encoding="utf-8"))
        if bundle.get("schema") != "yellowstone.firehole_obs.v1":
            raise ValueError("obs bundle has wrong schema")
        fit_doc = json.loads(args.fit.read_text(encoding="utf-8"))
        if fit_doc.get("schema") != calibrate.SCHEMA_FIT:
            raise ValueError("fit artifact has wrong schema")
        grids = fit_doc["grids"]
        champ = fit_doc["champion"]
        # Full-grid scores come from a fresh fit (also a reproducibility
        # check against the recorded champion); the artifact keeps
        # top10 only.
        full = calibrate.reach_heat_fit(
            bundle, args.volume_m3, args.area_m2,
            grids["q_lat"], grids["t_lat"], grids["c_mult"],
            return_all=True)
        recorded = (champ["q_lat"], champ["t_lat"], champ["c_mult"])
        fresh_champ = full["champion"]
        reproduces = (fresh_champ["q_lat"], fresh_champ["t_lat"],
                      fresh_champ["c_mult"]) == recorded
        q_grid, t_grid = grids["q_lat"], grids["t_lat"]
        qi = q_grid.index(champ["q_lat"])
        ti = t_grid.index(champ["t_lat"])
        perturbations = {
            "q_lat": [q_grid[max(0, qi - 1)], q_grid[
                min(len(q_grid) - 1, qi + 1)]],
            "t_lat": [t_grid[max(0, ti - 1)], t_grid[
                min(len(t_grid) - 1, ti + 1)]],
            "c_mult": sorted({c for c in (champ["c_mult"] / 2.0,
                                          champ["c_mult"] * 2.0)
                              if c > 0}),
            "volume_m3": [args.volume_m3 / 2.0, args.volume_m3 * 2.0],
            "area_m2": [args.area_m2 / 2.0, args.area_m2 * 2.0],
        }
        document = build_uq_document(
            bundle, args.volume_m3, args.area_m2, full["all_results"],
            champ, perturbations)
        document["uncertainty_provenance"] = UQ_PROVENANCE
        document["reproducibility"] = {
            "fresh_champion_matches_recorded": reproduces,
            "fresh_champion": {k: fresh_champ[k] for k in
                               ("q_lat", "t_lat", "c_mult", "train_rmse",
                                "holdout_rmse")},
            "recorded_champion": {k: champ[k] for k in
                                  ("q_lat", "t_lat", "c_mult",
                                   "train_rmse", "holdout_rmse")},
        }
        text = json.dumps(document, indent=1, allow_nan=False) + "\n"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_name(args.out.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(args.out)
    except (ValueError, KeyError, ArithmeticError, OSError) as error:
        parser.exit(2, f"uncertainty failed: {error}\n")
    cov = document["holdout_coverage"]
    print(f"members: {document['ridge_rule']['n_members']} "
          f"(fallback={document['ridge_rule']['fallback_to_top5']})")
    print(f"reproduces recorded champion: "
          f"{document['reproducibility']['fresh_champion_matches_recorded']}")
    print(f"holdout coverage: {cov['coverage']:.2f} "
          f"(nominal {cov['nominal']:.2f}, n={cov['n']}, "
          f"width {cov['mean_width_c']:.2f} C)")
    print("OAT ranking (|Δholdout RMSE|):")
    for row in document["fit_oat"]["ranking"]:
        print(f"  {row['knob']}={row['value']}: "
              f"{row['holdout_rmse']:.3f} (Δ {row['delta_rmse']:+.3f})")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
