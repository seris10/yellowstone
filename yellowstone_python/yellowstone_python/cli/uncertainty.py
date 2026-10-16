"""Command-line interface for uncertainty."""
from __future__ import annotations

import argparse
from yellowstone_python.common.io import write_json_atomic
import json
import math
from pathlib import Path
from typing import Any, Sequence
import numpy as np
from yellowstone_python.cli import calibrate
from yellowstone_python.river.hydraulics import cell_hydraulics, score_paired_series
from yellowstone_python.river.uncertainty import *
from yellowstone_python.river.uncertainty import _FIT_KNOBS, _FIT_KNOB_BOUNDS, _validate_knob_value, _TURNOVER_OUTPUT_KEYS, _dedup_perturbation

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obs", type=Path, required=True)
    parser.add_argument("--fit", type=Path, required=True,
                        help="reach_heat_fit artifact (grids + champion)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--volume-m3", type=float, required=True)
    parser.add_argument("--area-m2", type=float, required=True)
    parser.add_argument("--band-level", type=float,
                        default=DEFAULT_BAND_LEVEL)
    parser.add_argument("--tol-frac", type=float,
                        default=DEFAULT_TOL_FRAC)
    parser.add_argument("--min-members", type=int,
                        default=DEFAULT_MIN_MEMBERS)
    parser.add_argument("--n-bootstrap", type=int,
                        default=DEFAULT_N_BOOTSTRAP)
    parser.add_argument("--seed", type=int, default=ENSEMBLE_SEED)
    parser.add_argument("--dt-s", type=float, default=900.0)
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
        # Reuse the fit artifact's split; dt_s defaults to the calibrate.reach_heat_fit default (900 s).
        fit_spinup = float(fit_doc.get("spinup_s", DEFAULT_SPINUP_S))
        fit_train_frac = float(
            fit_doc.get("train_frac", DEFAULT_TRAIN_FRAC))
        fit_dt = float(args.dt_s)
        # Full-grid scores from a fresh fit (reproducibility check vs recorded champion); artifact keeps top10 only.
        full = calibrate.reach_heat_fit(
            bundle, args.volume_m3, args.area_m2,
            grids["q_lat"], grids["t_lat"], grids["c_mult"],
            spinup_s=fit_spinup, train_frac=fit_train_frac,
            dt_s=fit_dt, return_all=True)
        recorded = (champ["q_lat"], champ["t_lat"], champ["c_mult"])
        fresh_champ = full["champion"]
        fresh_values = (fresh_champ["q_lat"], fresh_champ["t_lat"],
                        fresh_champ["c_mult"])
        params_close = all(
            math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-12)
            for a, b in zip(fresh_values, recorded))
        train_close = math.isclose(
            float(fresh_champ["train_rmse"]),
            float(champ["train_rmse"]), rel_tol=1e-9, abs_tol=1e-12)
        holdout_close = math.isclose(
            float(fresh_champ["holdout_rmse"]),
            float(champ["holdout_rmse"]), rel_tol=1e-9, abs_tol=1e-12)
        reproduces = params_close and train_close and holdout_close
        q_grid, t_grid = grids["q_lat"], grids["t_lat"]
        qi = q_grid.index(champ["q_lat"])
        ti = t_grid.index(champ["t_lat"])
        perturbations = {
            "q_lat": _dedup_perturbation(
                [q_grid[max(0, qi - 1)],
                 q_grid[min(len(q_grid) - 1, qi + 1)]],
                champ["q_lat"]),
            "t_lat": _dedup_perturbation(
                [t_grid[max(0, ti - 1)],
                 t_grid[min(len(t_grid) - 1, ti + 1)]],
                champ["t_lat"]),
            "c_mult": _dedup_perturbation(
                sorted({c for c in (champ["c_mult"] / 2.0,
                                    champ["c_mult"] * 2.0) if c > 0}),
                champ["c_mult"]),
            "volume_m3": _dedup_perturbation(
                [args.volume_m3 / 2.0, args.volume_m3 * 2.0],
                args.volume_m3),
            "area_m2": _dedup_perturbation(
                [args.area_m2 / 2.0, args.area_m2 * 2.0], args.area_m2),
        }
        boundary_knobs = sorted(
            k for k, v in perturbations.items() if not v)
        perturbations = {k: v for k, v in perturbations.items() if v}
        document = build_uq_document(
            bundle, args.volume_m3, args.area_m2, full["all_results"],
            champ, perturbations,
            spinup_s=fit_spinup, train_frac=fit_train_frac,
            dt_s=fit_dt, band_level=args.band_level,
            tol_frac=args.tol_frac, min_members=args.min_members,
            n_bootstrap=args.n_bootstrap, seed=args.seed)
        document["singleton_grid_boundary_knobs"] = boundary_knobs
        document["reproducibility"] = {
            "fresh_champion_matches_recorded": reproduces,
            "params_close": params_close,
            "train_rmse_close": train_close,
            "holdout_rmse_close": holdout_close,
            "fit_config": {"spinup_s": fit_spinup,
                           "train_frac": fit_train_frac,
                           "dt_s": fit_dt},
            "fresh_champion": {k: fresh_champ[k] for k in
                               ("q_lat", "t_lat", "c_mult", "train_rmse",
                                "holdout_rmse")},
            "recorded_champion": {k: champ[k] for k in
                                  ("q_lat", "t_lat", "c_mult",
                                   "train_rmse", "holdout_rmse")},
        }
        write_json_atomic(args.out, document)
    except (ValueError, KeyError, ArithmeticError, OSError) as error:
        parser.exit(2, f"uncertainty failed: {error}\n")
    cov = document["holdout_coverage"]
    print(f"members: {document['ridge_rule']['n_members']} "
          f"(fallback={document['ridge_rule']['fallback_to_topn']})")
    print(f"reproduces recorded champion: "
          f"{document['reproducibility']['fresh_champion_matches_recorded']}")
    print(f"holdout coverage: {cov['coverage']:.2f} "
          f"(nominal {cov['nominal']:.2f}, n={cov['n']}, "
          f"width {cov['mean_width_c']:.2f} C)")
    print('OAT ranking (|delta holdout RMSE|):')
    for row in document["fit_oat"]["ranking"]:
        print(f"  {row['knob']}={row['value']}: "
              f"{row['holdout_rmse']:.3f} (delta {row['delta_rmse']:+.3f})")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
