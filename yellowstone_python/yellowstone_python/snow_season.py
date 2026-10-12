"""Snow season: weather state, snow accumulation/melt, and season tracking."""
from __future__ import annotations

import copy
import math

SEASONS = ("summer", "autumn", "winter", "spring")
PHENOLOGY = ("dormant", "green_up", "peak_green", "senescence")
SNOW_TEMP_C = 1.0  # precip below this is snow, above is rain


def degree_days(air_c: float, tbase: float = 0.0) -> float:
    return max(0.0, float(air_c) - float(tbase))


def date_to_season(month: int, day: int) -> str:
    """Meteorological season for month/day, northern hemisphere."""
    import datetime
    try:
        datetime.date(2000, int(month), int(day))
    except ValueError as exc:
        raise ValueError("invalid calendar date") from exc
    if not (1 <= int(month) <= 12):
        raise ValueError(f"month {month!r} outside [1, 12]")
    if not (1 <= int(day) <= 31):
        raise ValueError(f"day {day!r} outside [1, 31]")
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


def game_clock_now(now=None) -> dict:
    """System local date/time -> game season + clock hour.

    Default source only: explicit config always wins (see
    resolve_game_clock). Range-safe by construction (month/day validated,
    hour in [0, 24))."""
    import datetime
    local = now if now is not None else datetime.datetime.now().astimezone()
    return {"as_of_local_date": local.date().isoformat(),
            "season": date_to_season(local.month, local.day),
            "clock_hour": round(local.hour + local.minute / 60.0
                                + local.second / 3600.0, 2)}


def resolve_game_clock(season_cfg=None, clock_cfg=None, date_cfg=None,
                       now=None) -> dict:
    """Resolve (season, clock_hour, nominal date) with provenance.

    Precedence per key, explicit settings always win:
      season: season_cfg > derived from date_cfg > system clock
      clock_hour: clock_cfg > system clock (a date carries no time of day)
      nominal date: date_cfg > system clock date (stamped either way: it
        dates the run and anchors season.json).
    date_cfg is YYYY-MM-DD (settings key snow.as_of_date); malformed dates
    raise instead of guessing. Sources: config / config_date / system_clock.
    Raises on an out-of-range explicit clock_hour or unknown season."""
    import datetime
    tick = game_clock_now(now)
    if date_cfg is None:
        nominal_date, date_source = tick["as_of_local_date"], "system_clock"
    else:
        try:
            nominal_date = datetime.date.fromisoformat(
                str(date_cfg)).isoformat()
        except ValueError:
            raise ValueError(f"as_of_date {date_cfg!r} is not YYYY-MM-DD")
        date_source = "config_date"
    if season_cfg is None:
        if date_cfg is None:
            season, season_source = tick["season"], "system_clock"
        else:
            parts = [int(x) for x in nominal_date.split("-")]
            season = date_to_season(parts[1], parts[2])
            season_source = "config_date"
    else:
        if season_cfg not in SEASONS:
            raise ValueError(f"unknown season {season_cfg!r}")
        season, season_source = season_cfg, "config"
    if clock_cfg is None:
        clock_hour, clock_source = tick["clock_hour"], "system_clock"
    else:
        clock_hour = float(clock_cfg)
        if not (0.0 <= clock_hour < 24.0):
            raise ValueError(f"clock_hour {clock_hour} outside [0, 24)")
        clock_source = "config"
    return {"season": season, "season_source": season_source,
            "clock_hour": clock_hour, "clock_source": clock_source,
            "as_of_local_date": nominal_date, "date_source": date_source}


def step_snow(snow_mm: float, air_c: float, precip_mm_d: float,
              k_melt: float = 3.0, tbase: float = 0.0,
              aspect_retention: float = 1.0, canopy_keep: float = 1.0,
              wind_loss: float = 0.0, thermal_flux_mm_d: float = 0.0
              ) -> tuple[float, float, float, float, float, float]:
    """One day. Returns (snow_mm, melt_mm, accum_mm, rain_mm, wind_runoff_mm,
    thermal_melt_mm).

    melt includes surface degree-day melt (÷ retention) + thermal ground flux.
    The final term reports how much of the melt the thermal flux actually
    delivered after degree-day melt took the first share of the pack.
    Wind strips a fraction of (snow + fresh accum) to runoff. Rain never
    enters the snowpack."""
    snow_mm = max(0.0, float(snow_mm))
    if not math.isfinite(snow_mm) or snow_mm < 0:
        raise ValueError("snow_mm must be finite and >= 0")
    air_c = float(air_c)
    precip = float(precip_mm_d)
    if not math.isfinite(precip) or precip < 0:
        raise ValueError("precip_mm_d must be finite and >= 0")
    if float(air_c) < SNOW_TEMP_C:
        accum = float(precip_mm_d) * float(canopy_keep)
        rain = 0.0
    else:
        accum, rain = 0.0, float(precip_mm_d)
    blown = (snow_mm + accum) * min(0.9, max(0.0, float(wind_loss)))
    avail = snow_mm + accum - blown
    dd_melt = float(k_melt) * degree_days(air_c, tbase) / max(0.2, float(aspect_retention))
    thermal_melt = max(0.0, float(thermal_flux_mm_d))
    melt_request = min(avail, dd_melt + thermal_melt)
    # Actual thermal contribution is limited by what remains after degree-day.
    actual_thermal = min(thermal_melt, max(0.0, avail - min(avail, dd_melt)))
    melt = min(avail, dd_melt + actual_thermal)
    return (avail - melt, melt, accum, rain, blown, actual_thermal)


def patch_modifiers(patch: dict) -> dict:
    """Authored per-habitat modifiers (stated, not measured).
    aspect_retention > 1 slows melt; canopy_keep < 1 intercepts snow;
    wind_loss removes snow to runoff."""
    hab = patch.get("habitat", "")
    if hab in ("forest_lodgepole", "forest_moist", "forest_edge"):
        return {"aspect": 1.15, "canopy_keep": 0.7, "wind_loss": 0.02}
    if hab in ("dry_meadow",):
        return {"aspect": 1.0, "canopy_keep": 1.0, "wind_loss": 0.15}
    return {"aspect": 1.0, "canopy_keep": 0.9, "wind_loss": 0.05}


def _phenology(gdd: float, moisture: float) -> tuple[str, str]:
    stress = "drought_delay" if moisture < 0.25 and gdd > 50 else "none"
    if gdd < 50:
        stage = "dormant"
    elif gdd < 250:
        stage = "green_up" if stress == "none" else "dormant"
    elif gdd < 900:
        stage = "peak_green"
    else:
        stage = "senescence"
    return stage, stress


def run_season(patches: list, days: int, air_c_by_day: list,
               precip_mm_d: float = 2.0, precip_mm_by_day: list | None = None,
               k_melt: float = 3.0, tbase_c: float = 0.0,
               wind_loss: float | None = None,
               thermal_test=None,
               soil_cap_mm: float = 120.0, field_capacity: float = 0.7,
               k_et: float = 0.8, wind_mps: float = 2.0,
               thermal_flux_mm_d: float = 8.0) -> tuple[list, dict]:
    """Advance snow + soil + phenology with a verified water ledger. thermal_test(x, z) -> True where ground is hydrothermal: those cells get the ground-heat melt flux. precip_mm_by_day optionally overrides the scalar. Returns (patches, ledger). Ledger residual must be ~0."""
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("days must be a nonnegative integer")
    if days > 0 and not air_c_by_day:
        raise ValueError("air_c_by_day must not be empty when days > 0")
    if not patches:
        raise ValueError("at least one patch is required")
    out = copy.deepcopy(patches)
    for p in out:
        p.setdefault("snow_mm", 0.0)
        moisture_raw = float(p.get("moisture", 0.5))
        initial_moisture = min(1.0, max(0.0, moisture_raw))
        p["soil_mm"] = initial_moisture * soil_cap_mm
    use_series = list(precip_mm_by_day) if precip_mm_by_day else None
    tot = {"accum": 0.0, "rain": 0.0, "melt": 0.0, "thermal_melt": 0.0,
            "et": 0.0, "drain": 0.0, "runoff": 0.0, "blown": 0.0}
    initial_snow = sum(float(p["snow_mm"]) for p in out)
    initial_soil = sum(float(p["soil_mm"]) for p in out)
    ids = [p.get("id") for p in out]
    if any(i is None for i in ids) or len(ids) != len(set(ids)):
        raise ValueError("patch IDs must be present and unique")
    gdd = {p["id"]: 0.0 for p in out}
    mods = {p["id"]: patch_modifiers(p) for p in out}
    for d in range(days):
        air = float(air_c_by_day[d] if d < len(air_c_by_day)
                    else air_c_by_day[-1])
        if use_series is None:
            precip = float(precip_mm_d)
        else:
            precip = float(use_series[d] if d < len(use_series)
                           else use_series[-1])
        for p in out:
            cx, cz = p.get("center_xz", [0, 0])
            thermal = bool(thermal_test(cx, cz)) if thermal_test else False
            m = mods[p["id"]]
            wl = m["wind_loss"] if wind_loss is None else float(wind_loss)
            snow, melt, accum, rain, blown, thermal_melt_actual = step_snow(
                p["snow_mm"], air, precip,
                k_melt=k_melt, tbase=tbase_c,
                aspect_retention=m["aspect"], canopy_keep=m["canopy_keep"],
                wind_loss=(wl * min(2.0, 0.5 + wind_mps / 4.0)),
                thermal_flux_mm_d=(thermal_flux_mm_d if thermal else 0.0))
            p["snow_mm"] = round(snow, 3)
            inflow = melt + rain
            et = min(p["soil_mm"] + inflow,
                     k_et * max(0.0, air) / 20.0 * (1.0 + wind_mps / 15.0))
            soil = p["soil_mm"] + inflow - et
            cap = soil_cap_mm * field_capacity
            drain = max(0.0, soil - cap)
            soil -= drain
            p["soil_mm"] = round(soil, 3)
            p["moisture"] = round(min(1.0, soil / soil_cap_mm), 4)
            tot["accum"] += accum
            tot["rain"] += rain
            tot["melt"] += melt
            tot["blown"] += blown
            tot["runoff"] += blown + drain * 0.5
            tot["drain"] += drain * 0.5
            tot["et"] += et
            if thermal:
                tot["thermal_melt"] += thermal_melt_actual
            gdd[p["id"]] += degree_days(air)
    final_snow = sum(float(p["snow_mm"]) for p in out)
    final_soil = sum(float(p["soil_mm"]) for p in out)
    # Melt is an INTERNAL snow→soil transfer: snowpack and soil balances
    # verify separately (melt cancels in the joint balance).
    snow_res = (initial_snow + tot["accum"] - tot["melt"] - tot["blown"]
                - final_snow)
    soil_res = (initial_soil + tot["melt"] + tot["rain"] - tot["et"]
                - 2.0 * tot["drain"] - final_soil)
    residual = snow_res + soil_res
    for p in out:
        stage, stress = _phenology(gdd[p["id"]], float(p["moisture"]))
        p["phenology"] = stage
        p["pheno_stress"] = stress
        p["gdd"] = round(gdd[p["id"]], 1)
        p["snow_depth_m"] = round(float(p["snow_mm"]) / 1000.0 * 3.0, 3)
    ledger = {"days": days,
              "initial_mm": round(initial_snow + initial_soil, 2),
              "accum_mm": round(tot["accum"], 2),
              "rain_mm": round(tot["rain"], 2),
              "melt_mm": round(tot["melt"], 2),
              "thermal_melt_mm": round(tot["thermal_melt"], 2),
              "et_mm": round(tot["et"], 2),
              "drainage_mm": round(tot["drain"], 2),
              "runoff_mm": round(tot["runoff"], 2),
              "final_mm": round(final_snow + final_soil, 2),
              "snow_residual_mm": round(snow_res, 6),
              "soil_residual_mm": round(soil_res, 6),
              "storage_residual_mm": round(residual, 6),
              "units": "mm water-equivalent summed over modeled patches "
                       "(not a basin volume)",
              "note": "degree-day approximation; thermal ground carries a "
                      "melt flux, not an absolute bare rule"}
    return out, ledger


def catchment_runoff_m3_s(patches: list, ledger: dict, *,
                          catchment_area_m2: float) -> dict:
    """Snow-ledger runoff as a mean discharge increment over the basin.

    runoff_mm is a depth summed over the modeled patches, so the mean patch
    depth is the sum divided by the patch count. Scaling that depth to the
    catchment area assumes the modeled patches represent the basin.
    """
    area = float(catchment_area_m2)
    if not math.isfinite(area) or area <= 0.0:
        raise ValueError("catchment_area_m2 must be finite and > 0")
    count = len(patches)
    if count < 1:
        raise ValueError("at least one patch is required")
    days = int(ledger.get("days", 0))
    if days < 1:
        raise ValueError("ledger days must be >= 1 to form a mean rate")
    depth_mm = float(ledger["runoff_mm"]) / count
    volume_m3 = depth_mm / 1000.0 * area
    rate = volume_m3 / (days * 86400.0)
    return {
        "runoff_m3_s": round(rate, 6),
        "mean_runoff_depth_mm_d": round(depth_mm / days, 6),
        "runoff_depth_mm": round(depth_mm, 6),
        "catchment_area_m2": area,
        "modeled_patch_count": count,
        "window_days": days,
        "status": "illustrative_not_calibrated",
        "assumption": ("runoff depth uniform from the modeled patches to the "
                       "catchment; the patches cover a small fraction of the "
                       "basin area"),
        "ledger_runoff_basis": ledger.get("units"),
    }


def render_snow_map(shells: list, size: int, path: str,
                    snow_m: float = 0.3) -> str:
    """World-extent snow cover with thermally-reduced holes (illustrative)."""
    from PIL import Image, ImageDraw
    from .pool_crust import HALF
    img = Image.new("L", (size, size), int(min(255, snow_m * 600)))
    dr = ImageDraw.Draw(img)

    def px(x):
        return (x + HALF) / (2 * HALF) * (size - 1)
    for s in shells:
        cx, cz = s["center_xz"]
        r = s["r_apron_m"] / (2 * HALF) * (size - 1)
        dr.ellipse([px(cx) - r, px(cz) - r, px(cx) + r, px(cz) + r], fill=0)
    img.save(path)
    return path
