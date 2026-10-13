"""Snow season: weather state, accumulation/melt, and season tracking.
run_season holds the per-patch soil bucket; HydrologyProvider holds overland ground_wetness."""
from __future__ import annotations

import copy
import math

SEASONS = ("summer", "autumn", "winter", "spring")
PHENOLOGY = ("dormant", "green_up", "peak_green", "senescence")
SNOW_TEMP_C = 1.0  # precip below this is snow, above is rain
# Authored snow-cover saturation depth; registered as snow.cover_full_depth_m in param_registry.
SNOW_COVER_FULL_DEPTH_M = 0.10


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
    """System local date/time to game season plus clock hour.
    Default source; explicit config wins in resolve_game_clock."""
    import datetime
    local = now if now is not None else datetime.datetime.now().astimezone()
    return {"as_of_local_date": local.date().isoformat(),
            "season": date_to_season(local.month, local.day),
            "clock_hour": round(local.hour + local.minute / 60.0
                                + local.second / 3600.0, 2)}


def resolve_game_clock(season_cfg=None, clock_cfg=None, date_cfg=None,
                       now=None) -> dict:
    """Resolve (season, clock_hour, nominal date) with provenance.
    Precedence per key: explicit config, then date_cfg, then system clock."""
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
    """One day; returns (snow_mm, melt_mm, accum_mm, rain_mm, wind_runoff_mm, thermal_melt_mm).
    melt is degree-day plus thermal flux; wind strips (snow + accum) to runoff; rain stays separate."""
    def _finite_nonneg(name: str, value) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be numeric, not boolean")
        out = float(value)
        if not math.isfinite(out):
            raise ValueError(f"{name} must be finite")
        if out < 0.0:
            raise ValueError(f"{name} must be >= 0")
        return out

    def _finite_unit(name: str, value) -> float:
        out = _finite_nonneg(name, value)
        if out > 1.0:
            raise ValueError(f"{name} must be in [0, 1]")
        return out

    snow_mm = _finite_nonneg("snow_mm", snow_mm)
    air_c = float(air_c)
    if not math.isfinite(air_c):
        raise ValueError("air_c must be finite")
    precip = _finite_nonneg("precip_mm_d", precip_mm_d)
    canopy_keep_v = _finite_unit("canopy_keep", canopy_keep)
    aspect_retention_v = _finite_nonneg("aspect_retention", aspect_retention)
    if aspect_retention_v <= 0.0:
        raise ValueError("aspect_retention must be > 0")
    k_melt_v = _finite_nonneg("k_melt", k_melt)
    thermal_flux_v = _finite_nonneg("thermal_flux_mm_d", thermal_flux_mm_d)
    if air_c < SNOW_TEMP_C:
        accum = precip * canopy_keep_v
        rain = 0.0
    else:
        accum, rain = 0.0, precip
    blown = (snow_mm + accum) * min(0.9, max(0.0, float(wind_loss)))
    avail = snow_mm + accum - blown
    dd_melt = k_melt_v * degree_days(air_c, tbase) / aspect_retention_v
    thermal_melt = thermal_flux_v
    # Actual thermal contribution is limited by what remains after degree-day.
    actual_thermal = min(thermal_melt, max(0.0, avail - min(avail, dd_melt)))
    melt = min(avail, dd_melt + actual_thermal)
    return (avail - melt, melt, accum, rain, blown, actual_thermal)


def patch_modifiers(patch: dict) -> dict:
    """Authored per-habitat modifiers.
    aspect_retention > 1 slows melt; canopy_keep < 1 intercepts; wind_loss removes to runoff."""
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


def daily_air_c_from_hourly(hourly_rows: list) -> list:
    """Mean daily air temperature from met_forcing.v1 hourly rows.
    Groups by UTC calendar day; empty input returns an empty list."""
    import datetime
    if not hourly_rows:
        return []
    buckets: dict[str, list[float]] = {}
    order: list[str] = []
    for i, row in enumerate(hourly_rows):
        if (not isinstance(row, (list, tuple)) or len(row) < 2
                or not math.isfinite(float(row[0]))
                or not math.isfinite(float(row[1]))):
            raise ValueError(
                f"hourly_rows[{i}] must be [epoch, air_c, ...] of floats")
        day = datetime.datetime.fromtimestamp(
            float(row[0]), tz=datetime.timezone.utc).date().isoformat()
        if day not in buckets:
            buckets[day] = []
            order.append(day)
        buckets[day].append(float(row[1]))
    return [sum(buckets[d]) / len(buckets[d]) for d in order]


def run_season(patches: list, days: int, air_c_by_day: list,
               precip_mm_d: float = 2.0, precip_mm_by_day: list | None = None,
               k_melt: float = 3.0, tbase_c: float = 0.0,
               wind_loss: float | None = None,
               thermal_test=None,
               soil_cap_mm: float = 120.0, field_capacity: float = 0.7,
               k_et: float = 0.8, wind_mps: float = 2.0,
               thermal_flux_mm_d: float = 8.0,
               extend_last: bool = False,
               run_mode: str | None = None,
               air_hourly_c: list | None = None) -> tuple[list, dict]:
    """Advance snow, soil, and phenology with a verified water ledger.
    Returns (patches, ledger) with forcing_source recording which air series ran."""
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("days must be a nonnegative integer")
    allowed_modes = (None, "illustrative", "scenario", "hindcast",
                     "observed_replay")
    if run_mode not in allowed_modes:
        raise ValueError(
            f"run_mode {run_mode!r} must be one of {allowed_modes}")
    forcing_source = "air_c_by_day"
    if (run_mode in ("hindcast", "observed_replay")
            and air_hourly_c is not None):
        derived = daily_air_c_from_hourly(air_hourly_c)
        if days > 0 and len(derived) < 1:
            raise ValueError(
                "air_hourly_c yielded no daily means for a measured run_mode")
        air_c_by_day = derived
        forcing_source = (f"air_hourly_c (met_forcing.v1 daily mean, "
                          f"{len(derived)} days)")
    if days > 0 and not air_c_by_day:
        raise ValueError("air_c_by_day must not be empty when days > 0")
    if days > len(air_c_by_day) and not extend_last:
        raise ValueError(
            f"air_c_by_day has {len(air_c_by_day)} entries for days={days}; "
            "pass extend_last=True to reuse the last value")
    if not patches:
        raise ValueError("at least one patch is required")
    if (isinstance(soil_cap_mm, bool)
            or not math.isfinite(float(soil_cap_mm))
            or float(soil_cap_mm) <= 0.0):
        raise ValueError("soil_cap_mm must be finite and > 0")
    if (isinstance(field_capacity, bool)
            or not math.isfinite(float(field_capacity))
            or not 0.0 <= float(field_capacity) <= 1.0):
        raise ValueError("field_capacity must be finite and in [0, 1]")
    out = copy.deepcopy(patches)
    # soil_state holds unrounded values; p["soil_mm"] mirrors them at display precision.
    soil_state: dict = {}
    for p in out:
        p.setdefault("snow_mm", 0.0)
        moisture_raw = float(p.get("moisture", 0.5))
        initial_moisture = min(1.0, max(0.0, moisture_raw))
        soil_state[p.get("id", id(p))] = initial_moisture * soil_cap_mm
        p["soil_mm"] = round(initial_moisture * soil_cap_mm, 3)
    use_series = list(precip_mm_by_day) if precip_mm_by_day else None
    if (use_series is not None and days > len(use_series)
            and not extend_last):
        raise ValueError(
            f"precip_mm_by_day has {len(use_series)} entries for days={days}; "
            "pass extend_last=True to reuse the last value")
    tot = {"accum": 0.0, "rain": 0.0, "melt": 0.0, "thermal_melt": 0.0,
           "et": 0.0, "surface_drain": 0.0, "subsurface_drain": 0.0,
           "wind_runoff": 0.0}
    initial_snow = sum(float(p["snow_mm"]) for p in out)
    initial_soil = sum(soil_state[p["id"]] for p in out)
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
            soil = soil_state[p["id"]]
            inflow = melt + rain
            et = min(soil + inflow,
                     k_et * max(0.0, air) / 20.0 * (1.0 + wind_mps / 15.0))
            soil = soil + inflow - et
            cap = soil_cap_mm * field_capacity
            drain = max(0.0, soil - cap)
            soil -= drain
            soil_state[p["id"]] = soil
            p["soil_mm"] = round(soil, 3)
            p["moisture"] = round(min(1.0, soil / soil_cap_mm), 4)
            tot["accum"] += accum
            tot["rain"] += rain
            tot["melt"] += melt
            tot["wind_runoff"] += blown
            # Drain splits equally into surface runoff and subsurface drainage.
            tot["surface_drain"] += drain * 0.5
            tot["subsurface_drain"] += drain * 0.5
            tot["et"] += et
            if thermal:
                tot["thermal_melt"] += thermal_melt_actual
            gdd[p["id"]] += degree_days(air)
    final_snow = sum(float(p["snow_mm"]) for p in out)
    final_soil = sum(soil_state[p["id"]] for p in out)
    # Melt is a snow-to-soil transfer; the pack and bucket balances verify separately.
    snow_res = (initial_snow + tot["accum"] - tot["melt"] - tot["wind_runoff"]
                - final_snow)
    drain_total = tot["surface_drain"] + tot["subsurface_drain"]
    soil_res = (initial_soil + tot["melt"] + tot["rain"] - tot["et"]
                - drain_total - final_soil)
    residual = snow_res + soil_res
    for p in out:
        stage, stress = _phenology(gdd[p["id"]], float(p["moisture"]))
        p["phenology"] = stage
        p["pheno_stress"] = stress
        p["gdd"] = round(gdd[p["id"]], 1)
        # 3.0 is the authored SWE-to-depth ratio; see snow_energy.SWE_TO_DEPTH_RATIO.
        p["snow_depth_m"] = round(float(p["snow_mm"]) / 1000.0 * 3.0, 3)
        # Snow cover fraction saturates to 1 at SNOW_COVER_FULL_DEPTH_M; shared with the Godot sidecar rule.
        p["snow_cover_fraction"] = round(
            min(1.0, max(0.0, p["snow_depth_m"] / SNOW_COVER_FULL_DEPTH_M)),
            4)
    runoff_total = tot["wind_runoff"] + tot["surface_drain"]
    ledger = {"days": days,
              "initial_mm": round(initial_snow + initial_soil, 2),
              "accum_mm": round(tot["accum"], 2),
              "rain_mm": round(tot["rain"], 2),
              "melt_mm": round(tot["melt"], 2),
              "thermal_melt_mm": round(tot["thermal_melt"], 2),
              "et_mm": round(tot["et"], 2),
              "subsurface_drain_mm": round(tot["subsurface_drain"], 2),
              "surface_runoff_mm": round(tot["surface_drain"], 2),
              "wind_runoff_mm": round(tot["wind_runoff"], 2),
              # drainage_mm and runoff_mm are aggregated figures.
              "drainage_mm": round(tot["subsurface_drain"], 2),
              "runoff_mm": round(runoff_total, 2),
              "final_mm": round(final_snow + final_soil, 2),
              "snow_residual_mm": round(snow_res, 6),
              "soil_residual_mm": round(soil_res, 6),
              "storage_residual_mm": round(residual, 6),
              "units": "mm water-equivalent summed over modeled patches "
                       "(not a basin volume)",
              "note": "degree-day approximation with thermal ground as an "
                      "added melt flux",
              "forcing_source": forcing_source,
              "run_mode": run_mode or "unspecified"}
    return out, ledger


def catchment_runoff_m3_s(patches: list, ledger: dict, *,
                          catchment_area_m2: float) -> dict:
    """Snow-ledger runoff as a mean discharge increment over the basin.
    Scales mean per-patch depth to catchment_area_m2."""
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
    """World-extent snow cover with thermally-reduced holes.
    Validates shells and depth; creates the output's parent directory."""
    from pathlib import Path
    from PIL import Image, ImageDraw
    from .pool_crust import HALF
    if isinstance(size, bool) or not isinstance(size, int) or size < 2:
        raise ValueError("size must be an integer >= 2")
    snow_m = float(snow_m)
    if not math.isfinite(snow_m) or snow_m < 0.0:
        raise ValueError("snow_m must be finite and >= 0")
    for i, s in enumerate(shells):
        if not isinstance(s, dict):
            raise ValueError(f"shell {i} must be a mapping")
        center = s.get("center_xz")
        if (not isinstance(center, (list, tuple)) or len(center) != 2
                or not all(math.isfinite(float(c)) for c in center)):
            raise ValueError(
                f"shell {i} center_xz must be a finite 2-vector")
        apron = s.get("r_apron_m")
        if apron is None or not math.isfinite(float(apron)) or float(apron) < 0.0:
            raise ValueError(f"shell {i} r_apron_m must be finite and >= 0")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
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
