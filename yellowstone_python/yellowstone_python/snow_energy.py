"""Energy-balance snowmelt vs SNOTEL observations.

Replaces the degree-day melt rate with a daily energy budget while
reusing the degree-day accumulation, phase split, canopy, and wind
rules from snow_season.step_snow. Melt energy per day:

    SW_down = S_RAD * TOA(doi, lat) * cloud(dtr)
    net = (1 - albedo(age)) * SW_down + C0 + C_T * TAVG
    melt = max(0, net) * 86400 / L_F

TOA is deterministic top-of-atmosphere insolation. cloud(dtr) is an
authored diurnal-range modulation. Fitted per site on the train
window: s_rad (scales radiation to net shortwave) and c_t
(turbulent W/m2/K). Albedo resets on fresh snow and decays to a
floor, all authored. C0 is an authored net longwave deficit.

Same train/holdout/null machinery as snow_validate: train Oct-Feb,
holdout Mar-Jul melt season, persistence + no-melt nulls, plus the
fitted degree-day champion as a reference. Offline: reads only the
frozen bundle.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .replay.hydraulics import score_paired_series
from .snow_season import SNOW_TEMP_C, step_snow
from .snow_validate import (SPLIT_DATE, STATUS, in_to_mm,
                            peak_timing_error_days, train_holdout_split)

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

S_GRID = [0.0] + [round(0.02 + 0.02 * i, 2) for i in range(50)]
CT_GRID = [round(0.0 + 2.0 * i, 1) for i in range(16)]


def clear_sky_toa_w_m2(day_of_year: int, lat_deg: float) -> float:
    """Daily-mean TOA insolation from solar geometry."""
    lat = math.radians(float(lat_deg))
    dec = math.radians(-23.44 * math.cos(2 * math.pi
                                         * (int(day_of_year) + 10) / 365.0))
    cos_h = -math.tan(lat) * math.tan(dec)
    if cos_h <= -1.0:
        return SOLAR_W_M2 * (1.0 + 0.033
                             * math.cos(2 * math.pi * day_of_year / 365.0))
    if cos_h >= 1.0:
        return 0.0
    h0 = math.acos(max(-1.0, min(1.0, cos_h)))
    ecc = 1.0 + 0.033 * math.cos(2 * math.pi * day_of_year / 365.0)
    return (SOLAR_W_M2 * ecc / math.pi
            * (h0 * math.sin(lat) * math.sin(dec)
               + math.cos(lat) * math.cos(dec) * math.sin(h0)))


def cloud_factor(dtr_c: float) -> float:
    """Authored overcast-to-clear modulation from diurnal range."""
    return 0.25 + 0.75 * min(1.0, math.sqrt(max(0.0, float(dtr_c))
                                            / DTR_REF_C))


def day_of_year(iso: str) -> int:
    import datetime
    y, m, d = (int(x) for x in iso.split("-"))
    return datetime.date(y, m, d).timetuple().tm_yday


def _fill_temps(vals: list, max_fill: int = 3) -> list[float]:
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
    from .snow_validate import f_to_c, prepare_forcing
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
    net = sw + C0_W_M2 + c_t * air_c
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
                  ct_grid=CT_GRID) -> tuple[float, float, float, list]:
    """Joint grid fit of (s_rad, c_t) on train RMSE.

    Returns (best_s, best_c, best_rmse, runners_up) where runners_up
    holds the next two grid points by train RMSE, so near-ties and
    train/holdout tension stay visible in the artifact."""
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
    return s, c, round(rmse, 2), runners


def validate_site_eb(triplet: str, site: dict,
                     split: str = SPLIT_DATE) -> dict:
    """Full train/holdout/null/degree-day validation for one site."""
    from .snow_validate import (daily_swe_series, fit_snow_params,
                                prepare_forcing)
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
    s_rad, c_t, train_rmse, runners = fit_eb_params(
        lat, air_c, tmax_c, tmin_c, precip_mm, dois, obs_swe, train_idx)
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
    dd_k, dd_w, dd_train = fit_snow_params(patch, air_c, precip_mm,
                                           obs_swe, train_idx)
    swe_dd, _ = daily_swe_series(patch, air_c, precip_mm, dd_k,
                                 wind_loss=dd_w)
    dd_holdout = score_paired_series([swe_dd[i] for i in hold_idx],
                                     [obs_swe[i] for i in hold_idx])
    depth_mm = [s * 3.0 for s in swe]
    depth = score_paired_series(depth_mm, obs_depth_mm)
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
                    "game_default_untouched": True,
                    "train_rmse_mm": train_rmse,
                    "runners_up": runners},
        "holdout_swe_mm": {k: round(v, 2) for k, v in holdout.items()},
        "train_swe_mm": {k: round(v, 2) for k, v in train.items()},
        "null_persistence_rmse_mm": round(null_persist["rmse"], 2),
        "null_nomelt_rmse_mm": round(null_nomelt["rmse"], 2),
        "degree_day_holdout_rmse_mm": round(dd_holdout["rmse"], 2),
        "degree_day_fitted": {"k_melt": dd_k, "wind_loss": dd_w,
                              "train_rmse_mm": dd_train},
        "beats_both_nulls": bool(
            holdout["rmse"] < null_persist["rmse"]
            and holdout["rmse"] < null_nomelt["rmse"]),
        "beats_degree_day": bool(holdout["rmse"] < dd_holdout["rmse"]),
        "peak_timing_error_days": peak_timing_error_days(
            dates, swe, obs_swe),
        "depth_check_rmse_mm": round(depth["rmse"], 2),
        "status": STATUS,
    }


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


def load_fixed_params(path: str) -> dict[str, dict[str, float]]:
    """Read frozen {triplet: {s_rad, c_turb}} from a prior fit artifact."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(doc.get("sites"), dict) and all(
            isinstance(v, dict) and "fitted" in v
            for v in doc["sites"].values()):
        out = {t: {"s_rad": float(v["fitted"]["s_rad"]),
                   "c_turb_w_m2_k": float(v["fitted"]["c_turb_w_m2_k"])}
               for t, v in doc["sites"].items()}
    else:
        out = {t: {"s_rad": float(v["s_rad"]),
                   "c_turb_w_m2_k": float(v["c_turb_w_m2_k"])}
               for t, v in doc.items()}
    for triplet, params in out.items():
        s, c = params["s_rad"], params["c_turb_w_m2_k"]
        if s not in S_GRID:
            raise ValueError(f"{triplet}: frozen s_rad {s} not on fit grid")
        if c not in CT_GRID:
            raise ValueError(f"{triplet}: frozen c_t {c} not on fit grid")
    return out


def evaluate_fixed_params(bundle_path: str, fixed: dict[str, dict[str, float]],
                          split: str = SPLIT_DATE) -> dict:
    """True out-of-sample test: frozen params, new window, no refit."""
    from .snow_validate import daily_swe_series, fit_snow_params
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
        depth_mm = [s * 3.0 for s in swe]
        depth = score_paired_series(depth_mm, obs_depth_mm)
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
                                  "train_rmse_mm": dd_train},
            "beats_degree_day": bool(holdout["rmse"] < dd_holdout["rmse"]),
            "peak_timing_error_days": peak_timing_error_days(
                dates, swe, obs_swe),
            "depth_check_rmse_mm": round(depth["rmse"], 2),
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--split-date", default=SPLIT_DATE)
    parser.add_argument("--fixed-params", type=Path, default=None,
                        help="prior fit artifact for a no-refit "
                             "second-window test; omit to fit")
    args = parser.parse_args()
    if args.fixed_params is not None:
        fixed = load_fixed_params(str(args.fixed_params))
        artifact = evaluate_fixed_params(str(args.bundle), fixed,
                                         split=args.split_date)
    else:
        artifact = run_validation(str(args.bundle), split=args.split_date)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text(json.dumps(artifact, indent=1) + "\n", encoding="utf-8")
    tmp.replace(args.out)
    for triplet, site in artifact["sites"].items():
        params = site.get("fitted", site.get("frozen", {}))
        dd = site.get("degree_day_holdout_rmse_mm", "n/a")
        print(f"{triplet}: s_rad={params.get('s_rad')} "
              f"c_t={params.get('c_turb_w_m2_k')} "
              f"holdout_rmse={site['holdout_swe_mm']['rmse']}mm "
              f"vs persist={site['null_persistence_rmse_mm']}mm "
              f"vs nomelt={site['null_nomelt_rmse_mm']}mm "
              f"vs degreeday={dd}mm "
              f"peak_err={site['peak_timing_error_days']}d"
              + (" beats_nulls=" + str(site["beats_both_nulls"])
                 if "beats_both_nulls" in site else "")
              + (" beats_dd=" + str(site["beats_degree_day"])
                 if "beats_degree_day" in site else ""))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
