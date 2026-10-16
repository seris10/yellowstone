"""Energy-balance snowmelt vs SNOTEL observations.
Daily budget on top of snow_season accumulation; s_rad and c_t fitted per site."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite_param

from yellowstone_python.common.io import write_json_atomic

import json
import math
from pathlib import Path

from yellowstone_python.river.hydraulics import score_paired_series
from yellowstone_python.land.snow_season import SNOW_TEMP_C, step_snow
from yellowstone_python.land.snow_validate import SPLIT_DATE, STATUS, in_to_mm, peak_timing_error_days, train_holdout_split

SOLAR_W_M2 = 1361.0
L_F_J_KG = 334000.0
SEC_DAY = 86400.0
C0_W_M2 = -10.0
C0_PROVENANCE = "authored_net_longwave_deficit"
ALB_FRESH = 0.85
ALB_FLOOR = 0.45
ALB_DECAY_DAY = 0.008
ALB_PROVENANCE = "authored_reset_and_decay"
DTR_REF_C = 20.0
DTR_PROVENANCE = "authored_diurnal_range_cloud_shape"
# Reference air temperature for the turbulent flux term: 0 C anchors c_t at W/m2/K.
T_REF_C = 0.0
T_REF_PROVENANCE = "authored_melting_point_anchor"
# SWE-to-depth conversion for the depth check: density ratio of ~333 kg/m3.
SWE_TO_DEPTH_RATIO = 3.0
SWE_TO_DEPTH_PROVENANCE = (
    "authored_illustrative_density_ratio_333_kg_m3_not_measured")

S_GRID = [0.0] + [round(0.02 + 0.02 * i, 2) for i in range(50)]
CT_GRID = [round(0.0 + 2.0 * i, 1) for i in range(16)]


def clear_sky_toa_w_m2(day_of_year: int, lat_deg: float) -> float:
    """Daily-mean TOA insolation on a horizontal surface, from solar geometry."""
    lat = math.radians(float(lat_deg))
    doi = int(day_of_year)
    dec = math.radians(-23.44 * math.cos(2 * math.pi
                                         * (doi + 10) / 365.0))
    ecc = 1.0 + 0.033 * math.cos(2 * math.pi * doi / 365.0)
    cos_h = -math.tan(lat) * math.tan(dec)
    if cos_h <= -1.0:
        # Polar day (24 h sun): h0 = pi; sin(pi) = 0 drops the second term.
        h0 = math.pi
    elif cos_h >= 1.0:
        return 0.0
    else:
        h0 = math.acos(cos_h)
    return (SOLAR_W_M2 * ecc / math.pi
            * (h0 * math.sin(lat) * math.sin(dec)
               + math.cos(lat) * math.cos(dec) * math.sin(h0)))


def cloud_factor(dtr_c: float) -> float:
    """Authored overcast-to-clear modulation from diurnal range."""
    return 0.25 + 0.75 * min(1.0, math.sqrt(max(0.0, float(dtr_c))
                                            / DTR_REF_C))


def day_of_year(iso: str) -> int:
    """Day-of-year for an ISO date string."""
    import datetime
    d = datetime.date.fromisoformat(str(iso))
    return d.timetuple().tm_yday


def _fill_temps(vals: list, max_fill: int = 3) -> list[float]:
    """Forward-fill missing temperatures up to max_fill consecutive days.
Leading None values are refused."""
    out: list[float] = []
    gap = 0
    for v in vals:
        if v is None:
            gap += 1
            if gap > max_fill or not out:
                raise ValueError("temperature gap exceeds imputable range")
            out.append(out[-1])
        else:
            gap = 0
            out.append(float(v))
    return out


def prepare_forcing_eb(dates: list[str], tavg_f: list, tmax_f: list,
                       tmin_f: list, prcp_in: list,
                       max_fill: int = 3) -> tuple[list, list, list, list,
                                                  list, dict]:
    """Daily air/dmax/dmin-C + precip-mm with snow_validate gap rules."""
    from yellowstone_python.land.snow_validate import f_to_c, prepare_forcing
    air_c, precip_mm, fills = prepare_forcing(dates, tavg_f, prcp_in,
                                              max_fill=max_fill)
    tmax_c = [f_to_c(v) for v in _fill_temps(tmax_f, max_fill)]
    tmin_c = [f_to_c(v) for v in _fill_temps(tmin_f, max_fill)]
    n_filled = sum(1 for a, b in zip(tmax_f, tmin_f)
                   if a is None or b is None)
    fills = dict(fills)
    fills["tmax_tmin_filled"] = n_filled
    dois = [day_of_year(d) for d in dates]
    return air_c, tmax_c, tmin_c, precip_mm, dois, fills


def step_snow_eb(snow_mm: float, albedo: float, air_c: float,
                 tmax_c: float, tmin_c: float, precip_mm_d: float,
                 toa_w_m2: float, s_rad: float, c_t: float,
                 wind_loss: float = 0.0) -> tuple[float, float, float,
                                                 float, float, float]:
    """One day. Returns (snow, melt, accum, rain, blown, albedo)."""
    avail, _, accum, rain, blown, _thermal = step_snow(
        snow_mm, air_c, precip_mm_d, k_melt=0.0, tbase=0.0,
        aspect_retention=1.0, canopy_keep=1.0, wind_loss=wind_loss,
        thermal_flux_mm_d=0.0)
    if accum > 2.0:
        albedo = ALB_FRESH
    else:
        albedo = max(ALB_FLOOR, albedo - ALB_DECAY_DAY)
    sw = (s_rad * toa_w_m2 * cloud_factor(tmax_c - tmin_c)
          * (1.0 - albedo))
    # Sensible-heat exchange anchored at T_REF_C gives c_t units W/m2/K.
    net = sw + C0_W_M2 + c_t * (air_c - T_REF_C)
    melt = min(avail, max(0.0, net) * SEC_DAY / L_F_J_KG)
    return (avail - melt, melt, accum, rain, blown, albedo)


def daily_swe_series_eb(lat_deg: float, air_c: list, tmax_c: list,
                        tmin_c: list, precip_mm: list, dois: list,
                        s_rad: float, c_t: float,
                        wind_loss: float = 0.0) -> list:
    """Chained 1-day EB steps to a daily SWE series."""
    snow, albedo, swe = 0.0, ALB_FRESH, []
    for k in range(len(air_c)):
        toa = clear_sky_toa_w_m2(dois[k], lat_deg)
        snow, _, _, _, _, albedo = step_snow_eb(
            snow, albedo, air_c[k], tmax_c[k], tmin_c[k],
            precip_mm[k], toa, s_rad, c_t, wind_loss=wind_loss)
        swe.append(snow)
    return swe


def fit_eb_params(lat_deg: float, air_c: list, tmax_c: list,
                  tmin_c: list, precip_mm: list, dois: list,
                  obs_swe: list, train_idx: list,
                  s_grid=S_GRID,
                  ct_grid=CT_GRID,
                  tie_rel_tol: float = 0.01) -> dict:
    """Joint grid fit of (s_rad, c_t) on train RMSE.
Returns best, runners_up, parameter_at_grid_boundary, near_tie_count."""
    scored = []
    for s in s_grid:
        for c in ct_grid:
            swe = daily_swe_series_eb(lat_deg, air_c, tmax_c, tmin_c,
                                      precip_mm, dois, s, c)
            rmse = score_paired_series([swe[i] for i in train_idx],
                                       [obs_swe[i] for i in train_idx])["rmse"]
            scored.append((rmse, s, c))
    scored.sort(key=lambda r: r[0])
    (rmse, s, c) = scored[0]
    runners = [{"s_rad": rs, "c_turb_w_m2_k": rc,
                "train_rmse_mm": round(rr, 2)}
               for rr, rs, rc in scored[1:3]]
    threshold = rmse * (1.0 + float(tie_rel_tol)) if rmse > 0 else rmse
    near_tie_count = sum(1 for rr, _, _ in scored if rr <= threshold)
    at_boundary = bool(s == s_grid[0] or s == s_grid[-1]
                       or c == ct_grid[0] or c == ct_grid[-1])
    return {
        "best_s_rad": s,
        "best_c_turb_w_m2_k": c,
        "train_rmse_mm": round(rmse, 2),
        "runners_up": runners,
        "parameter_at_grid_boundary": at_boundary,
        "near_tie_count": near_tie_count,
        "tie_rel_tol": tie_rel_tol,
        "grid": {"s_rad_min": s_grid[0], "s_rad_max": s_grid[-1],
                 "c_turb_min": ct_grid[0], "c_turb_max": ct_grid[-1],
                 "n_s": len(s_grid), "n_c": len(ct_grid)},
    }


def validate_site_eb(triplet: str, site: dict,
                     split: str = SPLIT_DATE) -> dict:
    """Full train/holdout/null/degree-day validation for one site."""
    from yellowstone_python.land.snow_validate import daily_swe_series, fit_snow_params, prepare_forcing
    lat = float(site["latitude"])
    dates = sorted(site["days"])
    get = lambda code: [site["days"][d][code] for d in dates]  # noqa: E731
    if (get("WTEQ")[0] or 0.0) > in_to_mm(0.04):
        raise ValueError(f"{triplet}: day-0 SWE nonzero, needs spin-up")
    air_c, tmax_c, tmin_c, precip_mm, dois, fills = prepare_forcing_eb(
        dates, get("TAVG"), get("TMAX"), get("TMIN"), get("PRCP"))
    obs_swe = [in_to_mm(v or 0.0) for v in get("WTEQ")]
    obs_depth_mm = [in_to_mm(v or 0.0) for v in get("SNWD")]
    train_idx, hold_idx = train_holdout_split(dates, split=split)
    _validate_unique_iso_dates(dates, context=f"{triplet} dates")
    fit = fit_eb_params(lat, air_c, tmax_c, tmin_c, precip_mm, dois,
                        obs_swe, train_idx)
    s_rad = fit["best_s_rad"]
    c_t = fit["best_c_turb_w_m2_k"]
    train_rmse = fit["train_rmse_mm"]
    runners = fit["runners_up"]
    swe = daily_swe_series_eb(lat, air_c, tmax_c, tmin_c, precip_mm,
                              dois, s_rad, c_t)
    holdout = score_paired_series([swe[i] for i in hold_idx],
                                  [obs_swe[i] for i in hold_idx])
    train = score_paired_series([swe[i] for i in train_idx],
                                [obs_swe[i] for i in train_idx])
    persist = [obs_swe[train_idx[-1]]] * len(hold_idx)
    null_persist = score_paired_series(
        persist, [obs_swe[i] for i in hold_idx])
    swe_nomelt, _ = daily_swe_series(
        {"id": "snotel", "habitat": "dry_meadow",
         "center_xz": [0, 0], "moisture": 0.5},
        air_c, precip_mm, 0.0, wind_loss=0.0)
    null_nomelt = score_paired_series([swe_nomelt[i] for i in hold_idx],
                                      [obs_swe[i] for i in hold_idx])
    patch = {"id": "snotel", "habitat": "dry_meadow",
             "center_xz": [0, 0], "moisture": 0.5}
    dd_fit = fit_snow_params(patch, air_c, precip_mm, obs_swe, train_idx)
    dd_k = dd_fit["best_k"]
    dd_w = dd_fit["best_wind"]
    dd_train = dd_fit["train_rmse_mm"]
    swe_dd, _ = daily_swe_series(patch, air_c, precip_mm, dd_k,
                                 wind_loss=dd_w)
    dd_holdout = score_paired_series([swe_dd[i] for i in hold_idx],
                                     [obs_swe[i] for i in hold_idx])
    # Depth check and peak-timing error restricted to the holdout window.
    depth_mm_holdout = [swe[i] * SWE_TO_DEPTH_RATIO for i in hold_idx]
    obs_depth_mm_holdout = [obs_depth_mm[i] for i in hold_idx]
    depth = score_paired_series(depth_mm_holdout, obs_depth_mm_holdout)
    hold_dates = [dates[i] for i in hold_idx]
    hold_swe = [swe[i] for i in hold_idx]
    hold_obs_swe = [obs_swe[i] for i in hold_idx]
    peak_timing = peak_timing_error_days(hold_dates, hold_swe, hold_obs_swe)
    return {
        "triplet": triplet,
        "n_days": len(dates),
        "train_n": len(train_idx),
        "holdout_n": len(hold_idx),
        "forcing_gaps": fills,
        "fitted": {"s_rad": s_rad, "c_turb_w_m2_k": c_t,
                    "provenance": "fitted_single_window_WY2026_joint_grid",
                    "wind_loss_effective": 0.0,
                    "wind_provenance": "transferred_degree_day_fit_zero",
                    "c0_w_m2": C0_W_M2, "c0_provenance": C0_PROVENANCE,
                    "albedo_provenance": ALB_PROVENANCE,
                    "dtr_provenance": DTR_PROVENANCE,
                    "t_ref_c": T_REF_C,
                    "t_ref_provenance": T_REF_PROVENANCE,
                    "game_default_untouched": True,
                    "train_rmse_mm": train_rmse,
                    "runners_up": runners,
                    "parameter_at_grid_boundary": fit["parameter_at_grid_boundary"],
                    "near_tie_count": fit["near_tie_count"],
                    "fit_grid": fit["grid"]},
        "holdout_swe_mm": {k: round(v, 2) for k, v in holdout.items()},
        "train_swe_mm": {k: round(v, 2) for k, v in train.items()},
        "null_persistence_rmse_mm": round(null_persist["rmse"], 2),
        "null_nomelt_rmse_mm": round(null_nomelt["rmse"], 2),
        "degree_day_holdout_rmse_mm": round(dd_holdout["rmse"], 2),
        "degree_day_fitted": {"k_melt": dd_k, "wind_loss": dd_w,
                              "train_rmse_mm": dd_train,
                              "parameter_policy": "comparator_refit_each_window"},
        "beats_both_nulls": bool(
            holdout["rmse"] < null_persist["rmse"]
            and holdout["rmse"] < null_nomelt["rmse"]),
        "beats_degree_day": bool(holdout["rmse"] < dd_holdout["rmse"]),
        "peak_timing_error_days": peak_timing,
        "peak_timing_window": "holdout",
        "depth_check_rmse_mm": round(depth["rmse"], 2),
        "depth_check_window": "holdout",
        "swe_to_depth_ratio": SWE_TO_DEPTH_RATIO,
        "swe_to_depth_provenance": SWE_TO_DEPTH_PROVENANCE,
        "status": STATUS,
    }


def _validate_unique_iso_dates(dates: list, context: str = "dates") -> None:
    """Ensure dates are ISO yyyy-mm-dd strings with no duplicates."""
    import datetime
    seen = set()
    for d in dates:
        try:
            datetime.date.fromisoformat(str(d))
        except ValueError as exc:
            raise ValueError(f"{context}: invalid ISO date {d!r}") from exc
        if d in seen:
            raise ValueError(f"{context}: duplicate date {d!r}")
        seen.add(d)


def run_validation(bundle_path: str, split: str = SPLIT_DATE) -> dict:
    """Validate all sites in a frozen SNOTEL bundle. Offline."""
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    sites = {t: validate_site_eb(t, s, split=split)
             for t, s in bundle["sites"].items()}
    return {
        "schema": "yellowstone.snow_energy_fit.v1",
        "status": STATUS,
        "bundle": str(bundle_path),
        "bundle_fetched_at_utc": bundle.get("fetched_at_utc"),
        "window": bundle.get("window"),
        "split_date": split,
        "provenance": {
            "forcing_swe_depth_tmax_tmin":
                "measured_NRCS_AWDB_daily",
            "toa_insolation": "deterministic_solar_geometry",
            "s_rad_c_turb": "fitted_single_window_WY2026_joint_grid",
            "accumulation_phase_split_canopy_wind":
                "shared_with_degree_day_snow_season",
            "albedo_c0_cloud_shape": "authored_stated_in_snow_energy",
            "soil_moisture": "not_validated_no_observations",
        },
        "sites": sites,
    }




def _on_grid(value: float, grid: list[float], name: str, context: str) -> None:
    if value not in grid:
        raise ValueError(
            f"{context}: frozen {name} {value!r} not on fit grid "
            f"[{grid[0]}..{grid[-1]}]")


def load_fixed_params(path: str) -> dict[str, dict[str, float]]:
    """Read frozen {triplet: {s_rad, c_turb}} from a prior fit artifact."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(
            f"{path}: fixed-params doc must be a JSON object, got "
            f"{type(doc).__name__}")
    if isinstance(doc.get("sites"), dict) and all(
            isinstance(v, dict) and "fitted" in v
            for v in doc["sites"].values()):
        source = doc["sites"]
        extract = lambda rec: (rec["fitted"]["s_rad"],
                               rec["fitted"]["c_turb_w_m2_k"])
    else:
        source = doc
        extract = lambda rec: (rec["s_rad"], rec["c_turb_w_m2_k"])
    out: dict[str, dict[str, float]] = {}
    for triplet, rec in source.items():
        if not isinstance(rec, dict):
            raise ValueError(
                f"{triplet}: fixed-params record must be an object")
        try:
            raw_s, raw_c = extract(rec)
        except KeyError as exc:
            raise ValueError(
                f"{triplet}: fixed-params record missing {exc}") from exc
        s = _finite_param(f"{triplet}.s_rad", raw_s)
        c = _finite_param(f"{triplet}.c_turb_w_m2_k", raw_c)
        _on_grid(s, S_GRID, "s_rad", triplet)
        _on_grid(c, CT_GRID, "c_turb_w_m2_k", triplet)
        out[triplet] = {"s_rad": s, "c_turb_w_m2_k": c}
    return out


def evaluate_fixed_params(bundle_path: str, fixed: dict[str, dict[str, float]],
                          split: str = SPLIT_DATE) -> dict:
    """True out-of-sample test: frozen params, new window, no refit."""
    from yellowstone_python.land.snow_validate import daily_swe_series, fit_snow_params
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    sites = {}
    for triplet, site in bundle["sites"].items():
        if triplet not in fixed:
            raise ValueError(f"{triplet}: no frozen params supplied")
        s_rad = fixed[triplet]["s_rad"]
        c_t = fixed[triplet]["c_turb_w_m2_k"]
        lat = float(site["latitude"])
        dates = sorted(site["days"])
        get = lambda code: [site["days"][d][code] for d in dates]  # noqa: E731
        if (get("WTEQ")[0] or 0.0) > in_to_mm(0.04):
            raise ValueError(f"{triplet}: day-0 SWE nonzero, needs spin-up")
        air_c, tmax_c, tmin_c, precip_mm, dois, fills = prepare_forcing_eb(
            dates, get("TAVG"), get("TMAX"), get("TMIN"), get("PRCP"))
        obs_swe = [in_to_mm(v or 0.0) for v in get("WTEQ")]
        obs_depth_mm = [in_to_mm(v or 0.0) for v in get("SNWD")]
        train_idx, hold_idx = train_holdout_split(dates, split=split)
        swe = daily_swe_series_eb(lat, air_c, tmax_c, tmin_c, precip_mm,
                                  dois, s_rad, c_t)
        holdout = score_paired_series([swe[i] for i in hold_idx],
                                      [obs_swe[i] for i in hold_idx])
        persist = [obs_swe[train_idx[-1]]] * len(hold_idx)
        null_persist = score_paired_series(
            persist, [obs_swe[i] for i in hold_idx])
        patch = {"id": "snotel", "habitat": "dry_meadow",
                 "center_xz": [0, 0], "moisture": 0.5}
        swe_nomelt, _ = daily_swe_series(patch, air_c, precip_mm, 0.0,
                                         wind_loss=0.0)
        null_nomelt = score_paired_series([swe_nomelt[i] for i in hold_idx],
                                          [obs_swe[i] for i in hold_idx])
        dd_fit = fit_snow_params(patch, air_c, precip_mm, obs_swe, train_idx)
        dd_k, dd_w = dd_fit["best_k"], dd_fit["best_wind"]
        dd_train = dd_fit["train_rmse_mm"]
        swe_dd, _ = daily_swe_series(patch, air_c, precip_mm, dd_k,
                                     wind_loss=dd_w)
        dd_holdout = score_paired_series([swe_dd[i] for i in hold_idx],
                                         [obs_swe[i] for i in hold_idx])
        # Depth check and peak-timing error restricted to the holdout window.
        depth_mm_holdout = [swe[i] * SWE_TO_DEPTH_RATIO for i in hold_idx]
        obs_depth_mm_holdout = [obs_depth_mm[i] for i in hold_idx]
        depth = score_paired_series(depth_mm_holdout, obs_depth_mm_holdout)
        _validate_unique_iso_dates(dates, context=f"{triplet} dates")
        hold_dates = [dates[i] for i in hold_idx]
        hold_swe = [swe[i] for i in hold_idx]
        hold_obs_swe = [obs_swe[i] for i in hold_idx]
        peak_timing = peak_timing_error_days(hold_dates, hold_swe, hold_obs_swe)
        beats = (holdout["rmse"] < null_persist["rmse"]
                 and holdout["rmse"] < null_nomelt["rmse"])
        sites[triplet] = {
            "triplet": triplet,
            "n_days": len(dates),
            "train_n": len(train_idx),
            "holdout_n": len(hold_idx),
            "forcing_gaps": fills,
            "frozen": {"s_rad": s_rad, "c_turb_w_m2_k": c_t,
                       "provenance": "frozen_prior_window_fit_no_refit"},
            "holdout_swe_mm": {k: round(v, 2)
                               for k, v in holdout.items()},
            "null_persistence_rmse_mm": round(null_persist["rmse"], 2),
            "null_nomelt_rmse_mm": round(null_nomelt["rmse"], 2),
            "beats_both_nulls": beats,
            "degree_day_holdout_rmse_mm": round(dd_holdout["rmse"], 2),
            "degree_day_fitted": {"k_melt": dd_k, "wind_loss": dd_w,
                                  "train_rmse_mm": dd_train,
                                  "parameter_policy": "comparator_refit_each_window"},
            "beats_degree_day": bool(holdout["rmse"] < dd_holdout["rmse"]),
            "peak_timing_error_days": peak_timing,
            "peak_timing_window": "holdout",
            "depth_check_rmse_mm": round(depth["rmse"], 2),
            "depth_check_window": "holdout",
            "swe_to_depth_ratio": SWE_TO_DEPTH_RATIO,
            "swe_to_depth_provenance": SWE_TO_DEPTH_PROVENANCE,
            "status": STATUS,
        }
    return {
        "schema": "yellowstone.snow_energy_fit.v1",
        "status": STATUS,
        "bundle": str(bundle_path),
        "bundle_fetched_at_utc": bundle.get("fetched_at_utc"),
        "window": bundle.get("window"),
        "split_date": split,
        "provenance": {
            "forcing_swe_depth_tmax_tmin":
                "measured_NRCS_AWDB_daily",
            "toa_insolation": "deterministic_solar_geometry",
            "s_rad_c_turb": "frozen_prior_window_fit_no_refit",
            "accumulation_phase_split_canopy_wind":
                "shared_with_degree_day_snow_season",
            "albedo_c0_cloud_shape": "authored_stated_in_snow_energy",
            "soil_moisture": "not_validated_no_observations",
        },
        "sites": sites,
    }






def main() -> int:
    """Run the command-line interface."""
    from yellowstone_python.cli.snow_energy import main as command
    return command()


if __name__ == "__main__":
    raise SystemExit(main())
