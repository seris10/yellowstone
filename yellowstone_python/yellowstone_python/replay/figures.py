"""Publication-style diagnostic figures (matplotlib, headless Agg).

A3 of the science-demo backlog. Every figure renders from frozen
artifacts + the frozen obs bundle — no network, no Godot, no PIL
sketches. Functions take data, write one PNG, return its path; the
CLI rebuilds the full set under figs/.

Backend discipline: pyplot is imported only inside _pyplot() after
forcing Agg, so importing this module never steals a display backend
from anything else.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

STATUS_NOTE = "fitted_not_validated_single_window"


def _pyplot():  # type: ignore[no-untyped-def]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _save(fig: Any, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    figure = fig
    import matplotlib.pyplot as plt
    plt.close(figure)
    return out


def fit_holdout_figure(grid: Sequence[float],
                       modeled: Sequence[float],
                       target: Sequence[float],
                       upstream: Sequence[float],
                       train: slice, holdout: slice,
                       title: str, out: Path) -> Path:
    """Observed vs modeled over train/holdout + persistence null."""
    plt = _pyplot()
    hours = [(g - grid[0]) / 3600.0 for g in grid]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(hours, target, color="black", lw=1.2, label="downstream obs")
    ax.plot(hours, modeled, color="#1f77b4", lw=1.0,
            label="lumped fit")
    ax.plot(hours, upstream, color="gray", lw=0.8, alpha=0.7,
            label="null: upstream persistence")
    ax.axvspan(hours[0], hours[train.start], color="gray", alpha=0.15)
    ax.axvline(hours[train.stop], color="black", ls="--", lw=0.8)
    top = ax.get_ylim()[1]
    span = top - ax.get_ylim()[0]
    ax.text(hours[train.stop], top - 0.03 * span, " holdout",
            va="top", fontsize=8)
    ax.set_xlabel("hours since window start")
    ax.set_ylabel("temperature (C)")
    ax.set_title(title + f"\n({STATUS_NOTE})", fontsize=10)
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    return _save(fig, out)


def bands_figure(grid: Sequence[float],
                 lo: Sequence[float], mid: Sequence[float],
                 hi: Sequence[float], target_holdout: Sequence[float],
                 holdout: slice, level: float, coverage: float,
                 title: str, out: Path) -> Path:
    """Ensemble bands over the holdout window + empirical coverage."""
    plt = _pyplot()
    hours = [(g - grid[0]) / 3600.0 for g in grid]
    h_hold = hours[holdout]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.fill_between(h_hold, lo[holdout], hi[holdout],
                    color="#1f77b4", alpha=0.3,
                    label=f"{level:.0%} ensemble band")
    ax.plot(h_hold, mid[holdout], color="#1f77b4", lw=1.0,
            label="ensemble median")
    ax.plot(h_hold, target_holdout, color="black", lw=1.0,
            label="holdout obs")
    ax.set_xlabel("hours since window start (holdout only)")
    ax.set_ylabel("temperature (C)")
    ax.set_title(f"{title}\nholdout coverage {coverage:.2f} "
                 f"at nominal {level:.2f} ({STATUS_NOTE})", fontsize=10)
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    return _save(fig, out)


def residual_figure(resid_train: Sequence[float],
                    resid_holdout: Sequence[float],
                    qq_empirical: Sequence[float],
                    qq_normal: Sequence[float],
                    title: str, out: Path) -> Path:
    """Residual series (both windows) + normal Q-Q of train residuals."""
    plt = _pyplot()
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(9, 6))
    top.plot(list(resid_train), color="#1f77b4", lw=0.8,
             label="train residuals")
    top.plot(range(len(resid_train), len(resid_train) + len(resid_holdout)),
             list(resid_holdout), color="#d62728", lw=0.8,
             label="holdout residuals")
    top.axhline(0.0, color="black", lw=0.8)
    top.set_xlabel("sample index (train then holdout)")
    top.set_ylabel("residual (C)")
    top.legend(fontsize=8, loc="best")
    bottom.scatter(list(qq_normal), list(qq_empirical), s=8,
                   color="#1f77b4")
    limits = [min(min(qq_normal), min(qq_empirical)),
              max(max(qq_normal), max(qq_empirical))]
    bottom.plot(limits, limits, color="black", lw=0.8)
    bottom.set_xlabel("theoretical normal quantiles")
    bottom.set_ylabel("empirical standardized quantiles")
    fig.suptitle(title + f" ({STATUS_NOTE})", fontsize=10)
    fig.tight_layout()
    return _save(fig, out)


def ridge_figure(rows: Sequence[dict[str, Any]],
                 champion: dict[str, Any],
                 polished: dict[str, Any] | None,
                 out: Path) -> Path:
    """Joint (Q_lat, T_lat) distribution colored by train RMSE."""
    plt = _pyplot()
    best_c = champion["c_mult"]
    pts = [r for r in rows if r["c_mult"] == best_c]
    fig, ax = plt.subplots(figsize=(6, 5))
    scatter = ax.scatter([r["q_lat"] for r in pts],
                         [r["t_lat"] for r in pts],
                         c=[r["train_rmse"] for r in pts],
                         cmap="viridis_r", s=28)
    fig.colorbar(scatter, ax=ax, label="train RMSE (C)")
    ax.scatter([champion["q_lat"]], [champion["t_lat"]], marker="*",
               s=160, color="red", label="grid champion", zorder=3)
    if polished is not None:
        ax.scatter([polished["q_lat"]], [polished["t_lat"]],
                   marker="x", s=100, color="black",
                   label="least-squares polish", zorder=4)
        xs = [r["q_lat"] for r in pts] + [polished["q_lat"]]
        ts = [r["t_lat"] for r in pts] + [polished["t_lat"]]
        pad_q = 0.05 * (max(xs) - min(xs) or 1.0)
        pad_t = 0.05 * (max(ts) - min(ts) or 1.0)
        ax.set_xlim(min(xs) - pad_q, max(xs) + pad_q)
        ax.set_ylim(min(ts) - pad_t, max(ts) + pad_t)
    ax.set_xlabel("lateral inflow Q_lat (m3/s)")
    ax.set_ylabel("lateral temperature T_lat (C)")
    ax.set_title(f"Q-T ridge at c_mult={best_c} ({STATUS_NOTE})",
                 fontsize=10)
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    return _save(fig, out)


def refuge_profile_figure(chainage_m: Sequence[float],
                          temperature_c: Sequence[float],
                          refuge_s_m: float,
                          refuge_label: str,
                          out: Path) -> Path:
    """Thermal landscape profile with the refuge cell + Kaya 24 C line."""
    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(list(chainage_m), list(temperature_c), color="#d62728",
            lw=1.0, label="landscape temperature")
    ax.axhline(24.0, color="black", ls=":", lw=1.0,
               label="Kaya refuge-drive threshold (24 C)")
    ax.axvline(refuge_s_m, color="#1f77b4", lw=1.2, ls="--",
               label=f"trout refuge {refuge_label}")
    ax.set_xlabel("chainage (m)")
    ax.set_ylabel("temperature (C)")
    ax.set_title("Refuge selection on the thermal landscape "
                 f"({STATUS_NOTE})", fontsize=10)
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    return _save(fig, out)


def build_all(bundle: dict[str, Any], uq_doc: dict[str, Any],
              lsfit_doc: dict[str, Any], fit_doc: dict[str, Any],
              landscape: list[dict],
              refuge_s_m: float, refuge_label: str,
              out_dir: Path) -> list[Path]:
    """Rebuild the figure set from the recorded artifacts."""
    from . import calibrate, uncertainty
    from .hydraulics import residual_diagnostics
    volume = uq_doc["effective_geometry"]["volume_m3"]
    area = uq_doc["effective_geometry"]["area_m2"]
    champ = lsfit_doc["grid_champion"]
    polished = lsfit_doc["polished"]
    fwd = calibrate.run_fit_forward(
        bundle, volume, area, polished["q_lat"], polished["t_lat"],
        polished["c_mult"])
    grid, modeled = fwd["grid"], fwd["modeled_c"]
    target = calibrate.interp_series(
        bundle["sites"]["06036905"]["series"]["temperature_c"], grid)
    upstream = calibrate.interp_series(
        bundle["sites"]["06036805"]["series"]["temperature_c"], grid)
    train, holdout = uncertainty.fit_masks(grid, 86400.0, 0.7)
    paths = [fit_holdout_figure(
        grid, modeled, target, upstream, train, holdout,
        "Reach heat-budget fit vs downstream gauge",
        out_dir / "fit_holdout.png")]
    trajs = uncertainty.member_trajectories(
        bundle, volume, area, uq_doc["members"])
    level = uq_doc["bands"]["level"]
    tail = (1.0 - level) / 2.0
    bands = uncertainty.ensemble_bands(
        trajs["trajectories"], quantiles=(tail, 0.5, 1.0 - tail),
        seed=uq_doc["bands"]["seed"])
    paths.append(bands_figure(
        grid, bands["lo"], bands["mid"], bands["hi"],
        target[holdout], holdout, level,
        uq_doc["holdout_coverage"]["coverage"],
        "Ridge-ensemble bands", out_dir / "bands.png"))
    resid = residual_diagnostics(modeled[train], target[train])
    qq_levels = sorted(resid["qq"])
    paths.append(residual_figure(
        [m - t for m, t in zip(modeled[train], target[train])],
        [m - t for m, t in zip(modeled[holdout], target[holdout])],
        [resid["qq"][lv]["empirical"] for lv in qq_levels],
        [resid["qq"][lv]["normal"] for lv in qq_levels],
        "Fit residuals and Q-Q", out_dir / "residuals.png"))
    grids = fit_doc["grids"]
    fresh = calibrate.reach_heat_fit(
        bundle, volume, area, grids["q_lat"], grids["t_lat"],
        grids["c_mult"], return_all=True)
    paths.append(ridge_figure(
        fresh["all_results"], champ, polished,
        out_dir / "ridge.png"))
    paths.append(refuge_profile_figure(
        [c["s_m"] for c in landscape],
        [c["temperature_c"] for c in landscape],
        refuge_s_m, refuge_label,
        out_dir / "refuge_profile.png"))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obs", type=Path, required=True)
    parser.add_argument("--uq", type=Path, required=True)
    parser.add_argument("--lsfit", type=Path, required=True)
    parser.add_argument("--fit", type=Path, required=True,
                        help="reach_heat_fit artifact (carries the grids)")
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--intervention", type=Path, required=True,
                        help="aquatic_intervention artifact (refuge marker)")
    parser.add_argument("--out-dir", type=Path, default=Path("figs"))
    args = parser.parse_args()
    try:
        bundle = json.loads(args.obs.read_text(encoding="utf-8"))
        uq_doc = json.loads(args.uq.read_text(encoding="utf-8"))
        lsfit_doc = json.loads(args.lsfit.read_text(encoding="utf-8"))
        fit_doc = json.loads(args.fit.read_text(encoding="utf-8"))
        replay = json.loads(args.replay.read_text(encoding="utf-8"))
        intervention = json.loads(args.intervention.read_text(
            encoding="utf-8"))
        from ..aquatic_foodweb import thermal_landscape
        landscape = thermal_landscape(replay)
        control = intervention["control"]
        for path in build_all(bundle, uq_doc, lsfit_doc, fit_doc,
                              landscape, control["s_m"],
                              control["cell_id"], args.out_dir):
            print(f"Wrote {path} ({path.stat().st_size} bytes)")
    except (ValueError, KeyError, ArithmeticError, OSError) as error:
        parser.exit(2, f"figures failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
