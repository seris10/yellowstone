"""Publication-style diagnostic figures (matplotlib, headless Agg)."""
from __future__ import annotations
from yellowstone_python.river.obs_model import UPSTREAM_GAUGE, DOWNSTREAM_GAUGE

import json
import math
from pathlib import Path
from typing import Any, Sequence

DEFAULT_STATUS_NOTE = "fitted_not_validated_single_window"
STATUS_NOTE = DEFAULT_STATUS_NOTE


def _resolve_status_note(*docs: dict[str, Any]) -> str:
    """Pick the first explicit status string across the provided artifacts."""
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        candidate = doc.get("status")
        if isinstance(candidate, str) and candidate:
            return candidate
    return DEFAULT_STATUS_NOTE


def _validate_slice(name: str, span: slice, length: int) -> None:
    """Reject a slice that falls outside the provided series length."""
    start = 0 if span.start is None else int(span.start)
    stop = length if span.stop is None else int(span.stop)
    if start < 0 or stop < 0 or start > length or stop > length:
        raise ValueError(
            f"{name} slice [{start}, {stop}) outside [0, {length}]")
    if start > stop:
        raise ValueError(f"{name} slice start exceeds stop")


def _pyplot():  # type: ignore[no-untyped-def]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _save(fig: Any, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    fig.clf()
    return out


def _check_sizes(**series: Sequence[float]) -> None:
    """All provided series must share the length of the first one."""
    items = list(series.items())
    if not items:
        return
    name0, s0 = items[0]
    n = len(s0)
    for name, s in items[1:]:
        if len(s) != n:
            raise ValueError(
                f"{name} length {len(s)} differs from {name0} length {n}")


def fit_holdout_figure(grid: Sequence[float],
                       modeled: Sequence[float],
                       target: Sequence[float],
                       upstream: Sequence[float],
                       train: slice, holdout: slice,
                       title: str, out: Path) -> Path:
    """Observed vs modeled over train/holdout + persistence null."""
    plt = _pyplot()
    _check_sizes(grid=grid, modeled=modeled, target=target,
                 upstream=upstream)
    _validate_slice("train", train, len(grid))
    _validate_slice("holdout", holdout, len(grid))
    if not grid:
        raise ValueError("grid must be nonempty")
    hours = [(g - grid[0]) / 3600.0 for g in grid]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(hours, list(target), color="black", lw=1.2,
            label="downstream obs")
    ax.plot(hours, list(modeled), color="#1f77b4", lw=1.0,
            label="lumped fit")
    ax.plot(hours, list(upstream), color="gray", lw=0.8, alpha=0.7,
            label="null: upstream persistence")
    holdout_start = train.stop
    holdout_end = len(hours) - 1
    ax.axvspan(hours[holdout_start], hours[holdout_end],
               color="gray", alpha=0.15)
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
    qq_normal = list(qq_normal)
    qq_empirical = list(qq_empirical)
    if len(qq_normal) != len(qq_empirical):
        raise ValueError(
            "qq_empirical and qq_normal must have equal length")
    if qq_normal and qq_empirical:
        bottom.scatter(qq_normal, qq_empirical, s=8, color="#1f77b4")
        limits = [min(min(qq_normal), min(qq_empirical)),
                  max(max(qq_normal), max(qq_empirical))]
        bottom.plot(limits, limits, color="black", lw=0.8)
    else:
        bottom.text(0.5, 0.5,
                    "Q-Q unavailable (perfect or constant residual)",
                    ha="center", va="center",
                    transform=bottom.transAxes, fontsize=10)
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
    pts = [r for r in rows
           if math.isclose(r["c_mult"], best_c, rel_tol=0.0, abs_tol=1e-12)]
    if not pts:
        raise ValueError(f"no ridge rows found for c_mult={best_c}")
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
    from yellowstone_python.validation.checks import check_uq_document
    from yellowstone_python.river import calibrate, uncertainty
    from yellowstone_python.river.hydraulics import residual_diagnostics
    # Fail-closed on uq_doc shape before any field is read.
    uq_failures = check_uq_document(uq_doc)
    if uq_failures:
        raise ValueError(
            "uq_doc invalid: " + "; ".join(uq_failures))
    # STATUS_NOTE comes from the artifacts so a differing run status shows up.
    global STATUS_NOTE
    STATUS_NOTE = _resolve_status_note(uq_doc, lsfit_doc, fit_doc)
    volume = uq_doc["effective_geometry"]["volume_m3"]
    area = uq_doc["effective_geometry"]["area_m2"]
    champ = lsfit_doc["grid_champion"]
    polished = lsfit_doc["polished"]
    fwd = calibrate.run_fit_forward(
        bundle, volume, area, polished["q_lat"], polished["t_lat"],
        polished["c_mult"])
    grid, modeled = fwd["grid"], fwd["modeled_c"]
    target = calibrate.interp_series(
        bundle["sites"][DOWNSTREAM_GAUGE]["series"]["temperature_c"], grid)
    upstream = calibrate.interp_series(
        bundle["sites"][UPSTREAM_GAUGE]["series"]["temperature_c"], grid)
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
    qq_levels = sorted(resid.get("qq") or {})
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
