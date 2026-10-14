"""validation: snow and soil-water model against NRCS SNOTEL observations."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite_param

from yellowstone_python.common.io import write_json_atomic

import datetime
import json
import math
from pathlib import Path

from yellowstone_python.river.hydraulics import score_paired_series
from yellowstone_python.land.snow_season import run_season

SPLIT_DATE = "2026-03-01"  # train: accumulation season; holdout: melt season
MAX_FILL_DAYS = 3  # longest imputable forcing gap; longer refuses the run
STATUS = "fitted_not_validated_single_window"
# Day-0 SWE still counting as spun up (small starting pack per NRCS practice).
SPINUP_THRESHOLD_MM = 25.4 * 0.04


def _validate_site_dates(dates: list, context: str = "site dates") -> None:
    """Reject malformed ISO dates and duplicates in a site record."""
    import datetime
    if not dates:
        raise ValueError(f"{context}: empty")
    prior = None
    seen = set()
    for d in dates:
        try:
            parsed = datetime.date.fromisoformat(str(d))
        except ValueError as exc:
            raise ValueError(f"{context}: invalid ISO date {d!r}") from exc
        if d in seen:
            raise ValueError(f"{context}: duplicate date {d!r}")
        seen.add(d)
        if prior is not None and (parsed - prior).days > 1:
            # Non-contiguous days are allowed; fits use sorted order.
            pass
        prior = parsed  # 0.04 in, named and recorded in output
# First-listed grid point wins equal train RMSE (deterministic ordering).
TIE_RULE = "first_grid_point_in_scan_order_wins_on_equal_train_rmse"


def f_to_c(f: float) -> float:
    return (float(f) - 32.0) * 5.0 / 9.0


def in_to_mm(inches: float) -> float:
    return float(inches) * 25.4


def prepare_forcing(dates: list[str], tavg_f: list, prcp_in: list,
                    max_fill: int = MAX_FILL_DAYS) -> tuple[list, list, dict]:
    """Daily air-C and precip-mm series with documented gap rules.
Returns (air_c, precip_mm, {"tavg_filled": n, "prcp_zeroed": n})."""
    air_c: list[float] = []
    filled = 0
    gap = 0
    for v in tavg_f:
        if v is None:
            gap += 1
            if gap > max_fill or not air_c:
                raise ValueError("TAVG gap exceeds imputable range")
            air_c.append(air_c[-1])
            filled += 1
        else:
            gap = 0
            air_c.append(f_to_c(v))
    precip_mm: list[float] = []
    zeroed = 0
    for v in prcp_in:
        if v is None:
            precip_mm.append(0.0)
            zeroed += 1
        else:
            precip_mm.append(in_to_mm(v))
    return air_c, precip_mm, {"tavg_filled": filled, "prcp_zeroed": zeroed}


def train_holdout_split(dates: list[str],
                         split: str = SPLIT_DATE) -> tuple[list, list]:
    if not dates:
        raise ValueError("no dates supplied")
    idx = next((i for i, d in enumerate(dates) if d >= split), len(dates))
    if idx == 0:
        raise ValueError("split produces an empty training set")
    if idx == len(dates):
        raise ValueError("split produces an empty holdout set")
    return list(range(idx)), list(range(idx, len(dates)))


def daily_swe_series(patch: dict, air_c: list, precip_mm: list,
                     k_melt: float,
                     wind_loss: float | None = None) -> tuple[list, list]:
    """Chained one-day run_season calls returning (swe_mm, soil_mm) series.
wind_loss (None keeps the habitat default) is the site-effective seasonal loss."""
    state = dict(patch)
    state["snow_mm"] = 0.0
    swe, soil = [], []
    for day in range(len(air_c)):
        out, led = run_season([state], days=1,
                              air_c_by_day=[air_c[day]],
                              precip_mm_by_day=[precip_mm[day]],
                              k_melt=k_melt, wind_loss=wind_loss)
        residual = abs(led["storage_residual_mm"])
        if residual >= 0.01:
            raise RuntimeError(f"water ledger residual {residual} mm")
        state = out[0]
        swe.append(float(state["snow_mm"]))
        soil.append(float(state["soil_mm"]))
    return swe, soil


def peak_timing_error_days(dates: list[str], modeled: list,
                           observed: list) -> int:
    """Signed day difference between modeled and observed SWE peaks (model minus obs).
Series must be equal length and carry no missing values."""
    if len(dates) != len(modeled) or len(dates) != len(observed):
        raise ValueError("dates, modeled, and observed must share a length")
    if not dates:
        raise ValueError("peak timing needs at least one day")
    for d in dates:
        try:
            datetime.date.fromisoformat(str(d))
        except ValueError as exc:
            raise ValueError(f"date {d!r} is not ISO YYYY-MM-DD") from exc
    if any(v is None for v in observed) or any(v is None for v in modeled):
        raise ValueError("peak timing refuses series with missing values")
    m_peak = dates[modeled.index(max(modeled))]
    o_peak = dates[observed.index(max(observed))]
    return (ord_day(m_peak) - ord_day(o_peak))


def ord_day(iso: str) -> int:
    try:
        return datetime.date.fromisoformat(str(iso)).toordinal()
    except ValueError as exc:
        raise ValueError(f"date {iso!r} is not ISO YYYY-MM-DD") from exc


def peak_timing_on_observed(dates: list[str], modeled: list,
                            observed: list) -> tuple[int, int]:
    """(error_days, n_used) with missing-observation days excluded."""
    keep = [i for i in range(len(observed)) if observed[i] is not None]
    if len(keep) < 2:
        raise ValueError("peak timing needs at least two observed values")
    return (peak_timing_error_days([dates[i] for i in keep],
                                   [modeled[i] for i in keep],
                                   [observed[i] for i in keep]),
            len(keep))


def _scored_pairs(idx: list, modeled: list, observed: list):
    """Return (positions, modeled, observed) for pairs with both values."""
    keep = [i for i in idx if observed[i] is not None]
    return keep, [modeled[i] for i in keep], [observed[i] for i in keep]


K_GRID = [round(0.5 + 0.25 * i, 2) for i in range(23)]  # 0.5..6.0
WIND_GRID = (0.0, 0.02, 0.05, 0.1, 0.15)


def _on_grid(value: float, grid) -> bool:
    return any(abs(float(value) - float(g)) <= 1e-9 for g in grid)




def fit_snow_params(patch: dict, air_c: list, precip_mm: list,
                    obs_swe: list, train_idx: list,
                    k_grid=K_GRID,
                    wind_grid=WIND_GRID) -> dict:
    """Joint grid fit of (k_melt, wind_loss) on train RMSE.
Returns best values, grid info, and tie count."""
    k_grid = list(k_grid)
    wind_grid = list(wind_grid)
    if not k_grid or not wind_grid:
        raise ValueError("fit grids must be nonempty")
    keep, _, obs_kept = _scored_pairs(train_idx, obs_swe, obs_swe)
    if not keep:
        raise ValueError("training split has no scored observations")
    best = (k_grid[0], wind_grid[0], float("inf"))
    ties = 0
    for k in k_grid:
        for w in wind_grid:
            swe, _ = daily_swe_series(patch, air_c, precip_mm, k,
                                      wind_loss=w)
            rmse = score_paired_series([swe[i] for i in keep],
                                       obs_kept)["rmse"]
            if rmse < best[2]:
                best = (k, w, rmse)
                ties = 0
            elif rmse == best[2]:
                ties += 1
    return {"best_k": best[0], "best_wind": best[1],
            "train_rmse_mm": round(best[2], 2),
            "grid": {"k_grid": k_grid, "wind_grid": wind_grid,
                     "n_candidates": len(k_grid) * len(wind_grid),
                     "tie_rule": TIE_RULE},
            "tie_count": ties,
            "train_n": len(train_idx), "train_scored_n": len(keep)}


def validate_site(triplet: str, site: dict,
                  split: str = SPLIT_DATE,
                  bundle: dict | None = None) -> dict:
    """Full train/holdout/null validation for one SNOTEL site.
bundle supplies the window label used in fit provenance."""
    # SNOTEL instruments sit in clearings; dry_meadow modifiers apply.
    patch = {"id": "snotel", "habitat": "dry_meadow",
             "center_xz": [0, 0], "moisture": 0.5}
    dates = sorted(site["days"])
    _validate_site_dates(dates, context=f"{triplet} dates")
    get = lambda code: [site["days"][d][code] for d in dates]  # noqa: E731
    if (get("WTEQ")[0] or 0.0) > SPINUP_THRESHOLD_MM:
        raise ValueError(f"{triplet}: day-0 SWE exceeds spin-up threshold {SPINUP_THRESHOLD_MM} mm")
    air_c, precip_mm, fills = prepare_forcing(
        dates, get("TAVG"), get("PRCP"))
    obs_swe = [in_to_mm(v) if v is not None else None for v in get("WTEQ")]
    obs_depth_mm = [in_to_mm(v) if v is not None else None for v in get("SNWD")]
    train_idx, hold_idx = train_holdout_split(dates, split=split)
    fit = fit_snow_params(patch, air_c, precip_mm, obs_swe, train_idx)
    best_k, best_wind, train_rmse = (fit["best_k"], fit["best_wind"],
                                     fit["train_rmse_mm"])
    swe, _ = daily_swe_series(patch, air_c, precip_mm, best_k,
                              wind_loss=best_wind)
    hold_keep, hold_mod, hold_obs = _scored_pairs(hold_idx, swe, obs_swe)
    train_keep, _, _ = _scored_pairs(train_idx, swe, obs_swe)
    if not hold_keep:
        raise ValueError(
            f"{triplet}: holdout has no scored observations")
    holdout = score_paired_series(hold_mod, hold_obs)
    # Null 1: persistence of last train observation through holdout.
    persist_source = next(obs_swe[i] for i in reversed(train_idx)
                          if obs_swe[i] is not None)
    persist = [persist_source] * len(hold_keep)
    null_persist = score_paired_series(persist, hold_obs)
    # Null 2: accumulation-only run at the fitted wind (melt switched off).
    swe_nomelt, _ = daily_swe_series(patch, air_c, precip_mm, 0.0,
                                     wind_loss=best_wind)
    nomelt_keep, nomelt_mod, _ = _scored_pairs(hold_idx, swe_nomelt,
                                               obs_swe)
    null_nomelt = score_paired_series(nomelt_mod, hold_obs)
    # Secondary: modeled depth vs observed SNWD (authored 3.0 factor check).
    depth_keep, depth_mod, depth_obs = _scored_pairs(list(range(len(swe))),
                                                     [s * 3.0 for s in swe],
                                                     obs_depth_mm)
    depth = score_paired_series(depth_mod, depth_obs)
    # Full-window ledger + phenology from one unchained run at fitted params.
    _, ledger = run_season([dict(patch, snow_mm=0.0)], days=len(dates),
                           air_c_by_day=air_c, precip_mm_by_day=precip_mm,
                           k_melt=best_k, wind_loss=best_wind)
    missing_obs = sum(1 for v in obs_swe if v is None)
    peak_err, peak_used = peak_timing_on_observed(dates, swe, obs_swe)
    return {
        "triplet": triplet,
        "n_days": len(dates),
        "train_n": len(train_idx),
        "holdout_n": len(hold_idx),
        "train_scored_n": len(train_keep),
        "holdout_scored_n": len(hold_keep),
        "missing_obs_n": missing_obs,
        "forcing_gaps": fills,
        "fitted": {"k_melt_mm_per_deg_day": best_k,
                   "wind_loss_effective": best_wind,
                    "provenance": (f"fitted_single_window_"
                                   f"{(bundle or {}).get('window', 'unknown')}_"
                                   f"split_{split}"),
                   "game_default_untouched": True,
                   "train_rmse_mm": train_rmse,
                   "grid": fit["grid"],
                   "tie_count": fit["tie_count"]},
        "holdout_swe_mm": {k: round(v, 2) for k, v in holdout.items()},
        "null_persistence_rmse_mm": round(null_persist["rmse"], 2),
        "null_nomelt_rmse_mm": round(null_nomelt["rmse"], 2),
        "peak_timing_error_days": peak_err,
        "peak_timing_scored_n": peak_used,
        "depth_check_rmse_mm": round(depth["rmse"], 2),
        "depth_scored_n": len(depth_keep),
        "ledger_residual_mm": ledger["storage_residual_mm"],
        "status": STATUS,
    }


def run_validation(bundle_path: str, split: str = SPLIT_DATE) -> dict:
    """Validate all sites in a frozen SNOTEL bundle -> artifact dict."""
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    sites = {t: validate_site(t, s, split=split, bundle=bundle)
             for t, s in bundle["sites"].items()}
    return {
        "schema": "yellowstone.snow_snotel_fit.v1",
        "status": STATUS,
        "bundle": str(bundle_path),
        "bundle_fetched_at_utc": bundle.get("fetched_at_utc"),
        "window": bundle.get("window"),
        "split_date": split,
        "provenance": {
            "forcing_swe_depth": "measured_NRCS_AWDB_daily",
            "k_melt_wind_loss": (f"fitted_"
                                  f"{bundle.get('window', 'unknown')}_"
                                  f"split_{split}"),
            "wind_loss_meaning": ("site_effective_seasonal_loss_"
                                  "redistribution_plus_undercatch_plus_"
                                  "sublimation_game_default_retained"),
            "snow_temp_threshold_phase_split_canopy_aspect_depth_factor":
                "authored_stated_in_snow_season",
            "soil_moisture": "not_validated_no_observations",
            "patch_choice": ("authored_dry_meadow_SNOTEL_sites_are_"
                             "clearings_not_forest"),
        },
        "sites": sites,
    }


def load_fixed_params(path: str) -> dict[str, dict[str, float]]:
    """Read frozen {triplet: {k_melt, wind_loss}} from a prior fit artifact.
Accepts a full artifact (sites[].fitted) or a plain mapping; k_melt must sit on the fit grid."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("fixed artifact: top level must be an object or "
                         "hold a 'sites' mapping")
    if isinstance(doc.get("sites"), dict):
        raw = doc["sites"]
        if not all(isinstance(v, dict) and "fitted" in v
                   for v in raw.values()):
            raise ValueError("fixed artifact: every site needs a 'fitted' "
                             "record")
        out = {t: {"k_melt_mm_per_deg_day":
                   _finite_param(f"{t} k_melt",
                                 v["fitted"]["k_melt_mm_per_deg_day"]),
                   "wind_loss_effective":
                   _finite_param(f"{t} wind_loss",
                                 v["fitted"]["wind_loss_effective"])}
               for t, v in raw.items()}
    elif isinstance(doc, dict):
        out = {}
        for t, v in doc.items():
            if not isinstance(v, dict):
                raise ValueError(f"fixed artifact: entry {t!r} is "
                                 f"{type(v).__name__}, expected an object")
            for key in ("k_melt_mm_per_deg_day", "wind_loss_effective"):
                if key not in v:
                    raise ValueError(f"fixed artifact: entry {t!r} missing "
                                     f"{key!r}")
            out[t] = {
                "k_melt_mm_per_deg_day": _finite_param(
                    f"{t} k_melt", v["k_melt_mm_per_deg_day"]),
                "wind_loss_effective": _finite_param(
                    f"{t} wind_loss", v["wind_loss_effective"])}
    else:
        raise ValueError("fixed artifact: top level must be an object or "
                         "hold a 'sites' mapping")
    for triplet, params in out.items():
        k, w = (params["k_melt_mm_per_deg_day"],
                params["wind_loss_effective"])
        if not _on_grid(k, K_GRID):
            raise ValueError(f"{triplet}: frozen k_melt {k} is not on the "
                             f"fit grid {K_GRID}")
        if not _on_grid(w, WIND_GRID):
            raise ValueError(f"{triplet}: frozen wind_loss {w} is not on "
                             f"the fit grid {list(WIND_GRID)}")
    return out


def evaluate_fixed_params(bundle_path: str, fixed: dict[str, dict[str, float]],
                          split: str = SPLIT_DATE) -> dict:
    """Out-of-sample test with frozen params and a new window.
Status stays fitted_not_validated_single_window; verdict fields carry the evidence."""
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    if not isinstance(bundle.get("sites"), dict):
        raise ValueError("evaluation bundle: 'sites' must be a mapping")
    patch = {"id": "snotel", "habitat": "dry_meadow",
             "center_xz": [0, 0], "moisture": 0.5}
    sites = {}
    for triplet, site in bundle["sites"].items():
        if triplet not in fixed:
            raise ValueError(f"{triplet}: no frozen params supplied")
        k = fixed[triplet]["k_melt_mm_per_deg_day"]
        w = fixed[triplet]["wind_loss_effective"]
        dates = sorted(site["days"])
        get = lambda code: [site["days"][d][code] for d in dates]  # noqa: E731
        if (get("WTEQ")[0] or 0.0) > SPINUP_THRESHOLD_MM:
            raise ValueError(f"{triplet}: day-0 SWE exceeds spin-up "
                             f"threshold {SPINUP_THRESHOLD_MM} mm")
        air_c, precip_mm, fills = prepare_forcing(
            dates, get("TAVG"), get("PRCP"))
        # Missing WTEQ stays missing; scored pairs are counted separately.
        obs_swe = [in_to_mm(v) if v is not None else None for v in get("WTEQ")]
        obs_depth_mm = [in_to_mm(v) if v is not None else None
                        for v in get("SNWD")]
        train_idx, hold_idx = train_holdout_split(dates, split=split)
        swe, _ = daily_swe_series(patch, air_c, precip_mm, k,
                                  wind_loss=w)
        hold_keep, hold_mod, hold_obs = _scored_pairs(hold_idx, swe,
                                                      obs_swe)
        if not hold_keep:
            raise ValueError(f"{triplet}: holdout has no scored "
                             "observations")
        holdout = score_paired_series(hold_mod, hold_obs)
        persist_source = next(obs_swe[i] for i in reversed(train_idx)
                              if obs_swe[i] is not None)
        persist = [persist_source] * len(hold_keep)
        null_persist = score_paired_series(persist, hold_obs)
        swe_nomelt, _ = daily_swe_series(patch, air_c, precip_mm, 0.0,
                                         wind_loss=w)
        nomelt_keep, nomelt_mod, _ = _scored_pairs(hold_idx, swe_nomelt,
                                                   obs_swe)
        null_nomelt = score_paired_series(nomelt_mod, hold_obs)
        depth_keep, depth_mod, depth_obs = _scored_pairs(
            list(range(len(swe))), [s * 3.0 for s in swe], obs_depth_mm)
        depth = score_paired_series(depth_mod, depth_obs)
        beats = (holdout["rmse"] < null_persist["rmse"]
                 and holdout["rmse"] < null_nomelt["rmse"])
        missing_obs = sum(1 for v in obs_swe if v is None)
        peak_err, peak_used = peak_timing_on_observed(dates, swe, obs_swe)
        sites[triplet] = {
            "triplet": triplet,
            "n_days": len(dates),
            "train_n": len(train_idx),
            "holdout_n": len(hold_idx),
            "holdout_scored_n": len(hold_keep),
            "missing_obs_n": missing_obs,
            "forcing_gaps": fills,
            "frozen": {"k_melt_mm_per_deg_day": k,
                       "wind_loss_effective": w,
                       "provenance": "frozen_prior_window_fit_no_refit"},
            "holdout_swe_mm": {kk: round(v, 2)
                               for kk, v in holdout.items()},
            "null_persistence_rmse_mm": round(null_persist["rmse"], 2),
            "null_nomelt_rmse_mm": round(null_nomelt["rmse"], 2),
            "beats_both_nulls": beats,
            "peak_timing_error_days": peak_err,
            "peak_timing_scored_n": peak_used,
            "depth_check_rmse_mm": round(depth["rmse"], 2),
            "depth_scored_n": len(depth_keep),
            "status": STATUS,
        }
    unused = sorted(t for t in fixed if t not in sites)
    return {
        "schema": "yellowstone.snow_snotel_fit.v1",
        "status": STATUS,
        "bundle": str(bundle_path),
        "bundle_fetched_at_utc": bundle.get("fetched_at_utc"),
        "window": bundle.get("window"),
        "split_date": split,
        "unused_fixed_triplets": unused,
        "provenance": {
            "forcing_swe_depth": "measured_NRCS_AWDB_daily",
            "k_melt_wind_loss": "frozen_prior_window_fit_no_refit",
            "wind_loss_meaning": ("site_effective_seasonal_loss_"
                                  "redistribution_plus_undercatch_plus_"
                                  "sublimation_game_default_retained"),
            "snow_temp_threshold_phase_split_canopy_aspect_depth_factor":
                "authored_stated_in_snow_season",
            "soil_moisture": "not_validated_no_observations",
            "patch_choice": ("authored_dry_meadow_SNOTEL_sites_are_"
                             "clearings_not_forest"),
        },
        "sites": sites,
    }






def main() -> int:
    """Run the command-line interface."""
    from yellowstone_python.cli.snow_validate import main as command
    return command()


if __name__ == "__main__":
    raise SystemExit(main())
