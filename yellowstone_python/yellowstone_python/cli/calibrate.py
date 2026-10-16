"""Command-line interface for calibrate."""
from __future__ import annotations
from yellowstone_python.river.obs_model import UPSTREAM_GAUGE, DOWNSTREAM_GAUGE

import argparse
from yellowstone_python.common.io import write_json_atomic
from yellowstone_python.common.checks import finite as _finite
import hashlib
import json
import math
from pathlib import Path
from typing import Any
from yellowstone_python.river.hydraulics import score_paired_series
from yellowstone_python.river.river_transport import River, Series
from yellowstone_python.river.surface_flux import BudgetParams
from yellowstone_python.registry.run_mode import PRESCRIBED_DISCHARGE, PRESCRIBED_UPSTREAM_TEMPERATURE, check_split
from yellowstone_python.river.calibrate import *

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    disp = sub.add_parser("dispersion", help="method-of-moments D sweep")
    disp.add_argument("--out", type=Path, required=True)
    disp.add_argument("--d", type=float, nargs="+",
                      default=[0.0, 1.0, 10.0, 85.0],
                      help=('dispersions to test; D above ~10 needs a longer channel than the 3000 m default to keep the pulse off the downstream boundary : use the API with length_m=6000.0'))

    fit = sub.add_parser("fit", help="lumped reach fit to an obs bundle")
    fit.add_argument("--obs", type=Path, required=True)
    fit.add_argument("--out", type=Path, required=True)
    fit.add_argument("--volume-m3", type=float, required=True)
    fit.add_argument("--area-m2", type=float, required=True)
    fit.add_argument("--q-lat", type=float, nargs="+",
                     default=[3.5, 4.0, 4.37, 4.75, 5.0])
    fit.add_argument("--t-lat", type=float, nargs="+",
                     default=[5.0, 10.0, 15.0, 19.5, 25.0, 35.0, 50.0])
    fit.add_argument("--c-mult", type=float, nargs="+",
                     default=[0.0, 0.5, 1.0, 2.0, 4.0])
    lsfit = sub.add_parser("lsfit", help="grid fit + least-squares polish"
                                         " + AIC/BIC selection")
    lsfit.add_argument("--obs", type=Path, required=True)
    lsfit.add_argument("--out", type=Path, required=True)
    lsfit.add_argument("--volume-m3", type=float, required=True)
    lsfit.add_argument("--area-m2", type=float, required=True)
    lsfit.add_argument("--q-lat", type=float, nargs="+",
                       default=[3.5, 4.0, 4.37, 4.75, 5.0])
    lsfit.add_argument("--t-lat", type=float, nargs="+",
                       default=[5.0, 10.0, 15.0, 19.5, 25.0, 35.0, 50.0])
    lsfit.add_argument("--c-mult", type=float, nargs="+",
                       default=[0.0, 0.5, 1.0, 2.0, 4.0])
    ivp = sub.add_parser("ivp", help="RK45 cross-check of backward-Euler")
    ivp.add_argument("--obs", type=Path, required=True)
    ivp.add_argument("--volume-m3", type=float, required=True)
    ivp.add_argument("--area-m2", type=float, required=True)
    ivp.add_argument("--q-lat", type=float, required=True)
    ivp.add_argument("--t-lat", type=float, required=True)
    ivp.add_argument("--c-mult", type=float, required=True)
    args = parser.parse_args()

    try:
        if args.command == "dispersion":
            document = dispersion_sweep(args.d)
        elif args.command == "ivp":
            bundle = json.loads(args.obs.read_text(encoding="utf-8"))
            if bundle.get("schema") != "yellowstone.firehole_obs.v1":
                raise ValueError("obs bundle has wrong schema")
            check = ivp_crosscheck(bundle, args.volume_m3, args.area_m2,
                                   args.q_lat, args.t_lat, args.c_mult)
            print(f"RK45 vs backward-Euler over {check['n_steps']} steps "
                  f"({check['rk_nfev']} RHS evals):")
            print(f"  max |delta| {check['max_abs_diff_c']:.4f} C "
                  f"at t={check['argmax_s']:.0f} s, "
                  f"mean {check['mean_abs_diff_c']:.4f} C")
            print(f"  finals: RK45 {check['rk_final_c']:.3f} C, "
                  f"Euler {check['euler_final_c']:.3f} C, "
                  f"Euler budget_ok={check['budget_ok']}")
            return 0
        elif args.command == "lsfit":
            from yellowstone_python.river.hydraulics import residual_diagnostics, skill_scores
            bundle = json.loads(args.obs.read_text(encoding="utf-8"))
            if bundle.get("schema") != "yellowstone.firehole_obs.v1":
                raise ValueError("obs bundle has wrong schema")
            fit_doc = reach_heat_fit(
                bundle, args.volume_m3, args.area_m2,
                args.q_lat, args.t_lat, args.c_mult)
            champ = fit_doc["champion"]
            polished = least_squares_fit(
                bundle, args.volume_m3, args.area_m2,
                (champ["q_lat"], champ["t_lat"], champ["c_mult"]))
            fwd = run_fit_forward(bundle, args.volume_m3, args.area_m2,
                                  polished["q_lat"], polished["t_lat"],
                                  polished["c_mult"])
            grid = fwd["grid"]
            target = interp_series(
                bundle["sites"][DOWNSTREAM_GAUGE]["series"]["temperature_c"],
                grid)
            start = next(i for i, g in enumerate(grid)
                         if g - grid[0] >= 86400.0)
            split = start + int((len(grid) - start) * 0.7)
            train = slice(start, split)
            holdout = slice(split, len(grid))
            n_train = split - start
            rss = sum((m - t) ** 2
                      for m, t in zip(fwd["modeled_c"][train],
                                      target[train]))
            models = [{
                "name": "lumped_fit_k3", **information_criteria(
                    [m - t for m, t in zip(fwd["modeled_c"][train], target[train])], 3),
                "train_rmse": polished["train_rmse"],
                "holdout_rmse": polished["holdout_rmse"]}]
            for null in fit_doc["null_models"]:
                k = null["k"]
                rss_n = (null["train_rmse"] ** 2) * n_train
                if null["name"] == "upstream_persistence":
                    modeled_null = interp_series(bundle["sites"][UPSTREAM_GAUGE]["series"]["temperature_c"], grid)
                elif null["name"] == "downstream_climatology":
                    modeled_null = [math.fsum(target[train]) / n_train] * len(grid)
                else:
                    modeled_null = run_fit_forward(bundle, args.volume_m3, args.area_m2,
                                                   null["q_lat"], null["t_lat"], 0.0)["modeled_c"]
                residuals = [m - t for m, t in zip(modeled_null[train], target[train])]
                models.append({"name": null["name"],
                               **information_criteria(residuals, k),
                               "train_rmse": null["train_rmse"],
                               "holdout_rmse": null["holdout_rmse"]})
            models.sort(key=lambda m: m["aic_effective"])
            document = {
                "schema": "yellowstone.reach_lsfit.v1",
                "status": "fitted_not_validated_single_window",
                "fetched_at_utc": bundle.get("fetched_at_utc"),
                "effective_geometry": {
                    "volume_m3": args.volume_m3,
                    "area_m2": args.area_m2,
                    "surface_area_m2": args.area_m2,
                    "status": ('authored_illustrative_effective_mixing_volume; surface area is area_m2, not cross-sectional')},
                "grid_champion": champ, "polished": polished,
                "selection": models,
                "train_skill": skill_scores(fwd["modeled_c"][train],
                                            target[train]),
                "holdout_skill": skill_scores(fwd["modeled_c"][holdout],
                                              target[holdout]),
                "train_residuals": residual_diagnostics(
                    fwd["modeled_c"][train], target[train]),
                "holdout_residuals": residual_diagnostics(
                    fwd["modeled_c"][holdout], target[holdout])}
        else:
            bundle = json.loads(args.obs.read_text(encoding="utf-8"))
            if bundle.get("schema") != "yellowstone.firehole_obs.v1":
                raise ValueError("obs bundle has wrong schema")
            document = reach_heat_fit(
                bundle, args.volume_m3, args.area_m2,
                args.q_lat, args.t_lat, args.c_mult)
        write_json_atomic(args.out, document)
    except (ValueError, KeyError, ArithmeticError, OSError) as error:
        parser.exit(2, f"calibration failed: {error}\n")

    if args.command == "dispersion":
        for run in document["runs"]:
            print(f"D={run['specified_d_m2_s']:>6}: "
                  f"D_eff={run['effective_d_m2_s']:8.3f} "
                  f"(num {run['numerical_d_m2_s']:+.3f}), "
                  f"adv err {run['advection_error_pct']:+.2f}%, "
                  f"peak {run['peak_attenuation']:.3f}")
    elif args.command == "lsfit":
        pol = document["polished"]
        print(f"polished: Q_lat={pol['q_lat']:.3f} T_lat={pol['t_lat']:.3f} "
              f"c_mult={pol['c_mult']:.3f} ({pol['nfev']} evals)")
        print(f"  train RMSE {pol['train_rmse']:.3f} "
              f"holdout RMSE {pol['holdout_rmse']:.3f}")
        print("selection (effective AIC):")
        for model in document["selection"]:
            print(f"  {model['name']}: effective AIC {model['aic_effective']:.1f} "
                  f"n_eff {model['n_eff']:.1f}, raw AIC {model['aic']:.1f}, "
                  f"raw BIC {model['bic']:.1f} "
                  f"(train {model['train_rmse']:.3f}, "
                  f"holdout {model['holdout_rmse']:.3f})")
        for window in ("train_skill", "holdout_skill"):
            skill = document[window]
            kge = ("n/a (constant model)" if skill["kge"] is None
                   else f"{skill['kge']:.3f}")
            print(f"  {window}: NSE {skill['nse']:.3f} KGE {kge}")
    else:
        champ = document["champion"]
        print(f"champion: Q_lat={champ['q_lat']} T_lat={champ['t_lat']} "
              f"c_mult={champ['c_mult']}")
        print(f"  train RMSE {champ['train_rmse']:.3f} "
              f"holdout RMSE {champ['holdout_rmse']:.3f}")
        for null in document["null_models"]:
            print(f"  null {null['name']}: train {null['train_rmse']:.3f} "
                  f"holdout {null['holdout_rmse']:.3f}")
        print(f"measured lag: {document['measured_lag']}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
