"""Fit an illustrative reach model to the bundled gauge observations."""
import json
import os
from pathlib import Path

from yellowstone_python.river import calibrate, figures, uncertainty
from yellowstone_python.river.hydraulics import (
    residual_diagnostics,
    skill_scores,
)

ROOT = Path(calibrate.__file__).resolve().parents[2]

OBS = Path(os.environ.get(
    "OBS", str(ROOT / "derived" / "firehole_obs.json")))
FIG_DIR = Path(os.environ.get("FIG_DIR", str(ROOT / "figs" / "reach_fit")))
VOLUME_M3 = 300000.0
AREA_M2 = 600000.0  # authored 2xV (0.5 m effective depth)
Q_GRID = [2.5, 3.5, 4.5]
T_GRID = [20.0, 30.0, 40.0]
C_GRID = [0.5, 1.0, 2.0]

bundle = json.loads(OBS.read_text(encoding="utf-8"))
assert bundle.get("schema") == "yellowstone.firehole_obs.v1", "wrong bundle"
print("bundle:", OBS)
print("fetched_at_utc:", bundle.get("fetched_at_utc"))
print("schema: yellowstone.firehole_obs.v1")


fit = calibrate.reach_heat_fit(
    bundle, VOLUME_M3, AREA_M2, Q_GRID, T_GRID, C_GRID, return_all=True)
champ = fit["champion"]
print(f"champion: Q={champ['q_lat']} T={champ['t_lat']} c={champ['c_mult']}")
print(f"  train RMSE {champ['train_rmse']:.3f} "
      f"holdout RMSE {champ['holdout_rmse']:.3f}")
for null in fit["null_models"]:
    print(f"  null {null['name']}: train {null['train_rmse']:.3f} "
          f"holdout {null['holdout_rmse']:.3f}")


polished = calibrate.least_squares_fit(
    bundle, VOLUME_M3, AREA_M2,
    (champ["q_lat"], champ["t_lat"], champ["c_mult"]))
print(f"polished: Q={polished['q_lat']:.3f} T={polished['t_lat']:.3f} "
      f"c={polished['c_mult']:.3f} ({polished['nfev']} evals)")
print(f"  train RMSE {polished['train_rmse']:.3f} "
      f"holdout RMSE {polished['holdout_rmse']:.3f}")

fwd = calibrate.run_fit_forward(
    bundle, VOLUME_M3, AREA_M2, polished["q_lat"], polished["t_lat"],
    polished["c_mult"])
grid, modeled = fwd["grid"], fwd["modeled_c"]
target = calibrate.interp_series(
    bundle["sites"]["06036905"]["series"]["temperature_c"], grid)
upstream = calibrate.interp_series(
    bundle["sites"]["06036805"]["series"]["temperature_c"], grid)
start = next(i for i, g in enumerate(grid) if g - grid[0] >= 86400.0)
split = start + int((len(grid) - start) * 0.7)
train, holdout = slice(start, split), slice(split, len(grid))
n_train = split - start

models = [{"name": "lumped_fit_k3",
           **calibrate.aic_bic(sum((m - t) ** 2 for m, t in
                                   zip(modeled[train], target[train])),
                               n_train, 3),
           "train_rmse": polished["train_rmse"],
           "holdout_rmse": polished["holdout_rmse"]}]
for null, k in zip(fit["null_models"], (0, 2, 0)):
    models.append({"name": null["name"],
                   **calibrate.aic_bic(null["train_rmse"] ** 2 * n_train,
                                       n_train, k),
                   "train_rmse": null["train_rmse"],
                   "holdout_rmse": null["holdout_rmse"]})
for row in sorted(models, key=lambda r: r["aic"]):
    print(f"  {row['name']}: AIC {row['aic']:.1f} BIC {row['bic']:.1f}")


for name, sl in (("train", train), ("holdout", holdout)):
    skill = skill_scores(modeled[sl], target[sl])
    print(f"{name}: NSE {skill['nse']:.3f} KGE {skill['kge']:.3f} "
          f"(r={skill['correlation']:.3f} "
          f"alpha={skill['alpha']:.3f} beta={skill['beta']:.3f})")
diag = residual_diagnostics(modeled[train], target[train])
print("train residual lag-1..3:",
      [round(diag["autocorr"][lag], 3) for lag in (1, 2, 3)])
print("train max Q-Q gap:", round(diag["max_qq_gap"], 3))


members = uncertainty.ridge_members(
    fit["all_results"], champ["train_rmse"])
fallback = any(m["fallback_member"] for m in members)
print(f"ridge members: {len(members)} (fallback={fallback})")
if fallback:
    print("note: fallback top-5 on this coarse grid spans distant fits, "
          "so coverage on this coarse grid is not evidence of calibrated uncertainty; "
          "evaluate holdout coverage before interpreting bands.")
for m in members:
    print(f"  Q={m['q_lat']} T={m['t_lat']} c={m['c_mult']} "
          f"train {m['train_rmse']:.3f}")
trajs = uncertainty.member_trajectories(
    bundle, VOLUME_M3, AREA_M2, members)
bands = uncertainty.ensemble_bands(trajs["trajectories"])
cov = uncertainty.band_coverage(
    bands["lo"][holdout], bands["hi"][holdout], target[holdout])
print(f"holdout coverage: {cov['coverage']:.2f} at nominal 0.90 "
      f"(n={cov['n']}, band width {cov['mean_width_c']:.2f} C)")


FIG_DIR.mkdir(parents=True, exist_ok=True)
p1 = figures.fit_holdout_figure(
    grid, modeled, target, upstream, train, holdout,
    "Reach heat-budget fit vs downstream gauge",
    FIG_DIR / "fit_holdout.png")
level = 0.90
p2 = figures.bands_figure(
    grid, bands["lo"], bands["mid"], bands["hi"], target[holdout],
    holdout, level, cov["coverage"], "Ridge-ensemble bands",
    FIG_DIR / "bands.png")
p3 = figures.ridge_figure(fit["all_results"], champ, polished,
                          FIG_DIR / "ridge.png")
for p in (p1, p2, p3):
    print(f"Wrote {p} ({p.stat().st_size} bytes)")

