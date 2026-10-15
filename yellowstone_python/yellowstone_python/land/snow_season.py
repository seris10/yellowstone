"""Snow season: weather state, accumulation/melt, and season tracking.
run_season holds the per-patch soil bucket; HydrologyProvider holds overland ground_wetness."""
from __future__ import annotations

import copy
import math

from yellowstone_python.common.checks import finite, fraction, nonnegative, positive, positive_int

SEASONS = ("summer", "autumn", "winter", "spring")
PHENOLOGY = ("dormant", "green_up", "peak_green", "senescence")
SNOW_TEMP_C = 1.0  # precip below this is snow, above is rain
# Authored snow-cover saturation depth; registered as snow.cover_full_depth_m in param_registry.
SNOW_COVER_FULL_DEPTH_M = 0.10


def degree_days(air_c: float, tbase: float = 0.0) -> float:
    return max(0.0, finite("air_c", air_c) - finite("tbase", tbase))


def date_to_season(month: int, day: int) -> str:
    """Meteorological season for month/day, northern hemisphere."""
    import datetime
    month = positive_int("month", month)
    day = positive_int("day", day)
    try:
        datetime.date(2000, month, day)
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
              wind_loss: float = 0.0, thermal_flux_mm_d: float = 0.0,
              elapsed_days: float = 1.0
              ) -> tuple[float, float, float, float, float, float]:
    """Advance snow and return melt, accumulation, rain and solid export in mm."""
    snow_mm = nonnegative("snow_mm", snow_mm)
    air_c = finite("air_c", air_c)
    precip = nonnegative("precip_mm_d", precip_mm_d)
    canopy_keep_v = fraction("canopy_keep", canopy_keep)
    aspect_retention_v = positive("aspect_retention", aspect_retention)
    k_melt_v = nonnegative("k_melt", k_melt)
    thermal_flux_v = nonnegative("thermal_flux_mm_d", thermal_flux_mm_d)
    wind_loss = nonnegative("wind_loss", wind_loss)
    days = nonnegative("elapsed_days", elapsed_days)
    precip *= days
    if air_c < SNOW_TEMP_C:
        accum = precip * canopy_keep_v
        rain = 0.0
    else:
        accum, rain = 0.0, precip
    erosion_fraction = -math.expm1(days * math.log1p(-min(0.9, wind_loss)))
    blown = (snow_mm + accum) * erosion_fraction
    avail = snow_mm + accum - blown
    dd_melt = k_melt_v * degree_days(air_c, tbase) / aspect_retention_v * days
    thermal_melt = thermal_flux_v * days
    # Actual thermal contribution is limited by what remains after degree-day.
    actual_thermal = min(thermal_melt, max(0.0, avail - min(avail, dd_melt)))
    melt = min(avail, dd_melt + actual_thermal)
    return (avail - melt, melt, accum, rain, blown, actual_thermal)


def patch_modifiers(patch: dict) -> dict:
    """Authored per-habitat modifiers."""
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


def step_soil_bucket(soil_mm: float, inflow_mm: float, air_c: float, wind_mps: float,
                     *, elapsed_days: float = 1.0, soil_cap_mm: float = 120.0,
                     field_capacity: float = 0.7, k_et: float = 0.8) -> dict:
    """Advance the soil water bucket and return storage, ET and the split drainage in mm."""
    soil = nonnegative("soil_mm", soil_mm)
    inflow = nonnegative("inflow_mm", inflow_mm)
    air = finite("air_c", air_c)
    wind = nonnegative("wind_mps", wind_mps)
    days = nonnegative("elapsed_days", elapsed_days)
    capacity = positive("soil_cap_mm", soil_cap_mm) * fraction("field_capacity", field_capacity)
    et_coefficient = nonnegative("k_et", k_et)
    if days == 0.0:
        if inflow != 0.0:
            raise ValueError("zero elapsed time requires zero inflow")
        return {"soil_mm": soil, "et_mm": 0.0, "drain_mm": 0.0,
                "surface_drain_mm": 0.0, "subsurface_drain_mm": 0.0,
                "water_residual_mm": 0.0}
    et = min(soil + inflow,
             et_coefficient * max(0.0, air) / 20.0 * (1.0 + wind / 15.0) * days)
    storage = soil + inflow - et
    drain = max(0.0, storage - capacity)
    storage -= drain
    return {"soil_mm": storage, "et_mm": et, "drain_mm": drain,
            "surface_drain_mm": drain * 0.5, "subsurface_drain_mm": drain * 0.5,
            "water_residual_mm": soil + inflow - et - drain - storage}


def step_land(patches: list, elapsed_s: float, air_c: float, precip_mm_d: float,
              wind_mps: float, *, interval_start_s: float = 0.0,
              thermal_flux_mm_d_by_patch: dict | None = None,
              k_melt: float = 3.0, tbase_c: float = 0.0,
              wind_loss: float | None = None, soil_cap_mm: float = 120.0,
              field_capacity: float = 0.7, k_et: float = 0.8) -> tuple[list, dict]:
    """Advance patch snow, soil and phenology over an identified physical interval."""
    seconds = nonnegative("elapsed_s", elapsed_s)
    start = finite("interval_start_s", interval_start_s)
    days = seconds / 86400.0
    wind = nonnegative("wind_mps", wind_mps)
    cap = positive("soil_cap_mm", soil_cap_mm)
    ids = [patch.get("id") for patch in patches]
    if not patches or any(pid is None for pid in ids) or len(ids) != len(set(ids)):
        raise ValueError("patch IDs must be present and unique")
    out = copy.deepcopy(patches)
    totals = {key: 0.0 for key in ("accum_mm", "rain_mm", "melt_mm", "thermal_melt_mm",
              "et_mm", "surface_runoff_mm", "subsurface_drain_mm", "snow_export_mm",
              "snow_residual_mm", "soil_residual_mm", "initial_mm", "final_mm")}
    for patch in out:
        snow0 = nonnegative("snow_mm", patch.get("snow_mm", 0.0))
        soil0 = nonnegative("soil_mm", patch.get("soil_mm", patch.get("moisture", .5) * cap))
        totals["initial_mm"] += snow0 + soil0
        if seconds == 0.0:
            totals["final_mm"] += snow0 + soil0
            continue
        modifiers = patch_modifiers(patch)
        loss = modifiers["wind_loss"] if wind_loss is None else wind_loss
        flux = (thermal_flux_mm_d_by_patch or {}).get(patch["id"], 0.0)
        snow, melt, accum, rain, exported, thermal = step_snow(
            snow0, air_c, precip_mm_d, k_melt=k_melt, tbase=tbase_c,
            aspect_retention=modifiers["aspect"], canopy_keep=modifiers["canopy_keep"],
            wind_loss=loss * min(2.0, .5 + wind / 4.0), thermal_flux_mm_d=flux,
            elapsed_days=days)
        bucket = step_soil_bucket(soil0, melt + rain, air_c, wind, elapsed_days=days,
                                 soil_cap_mm=cap, field_capacity=field_capacity, k_et=k_et)
        gdd = patch.get("gdd", 0.0) + degree_days(air_c) * days
        stage, stress = _phenology(gdd, bucket["soil_mm"] / cap)
        patch.update(snow_mm=snow, soil_mm=bucket["soil_mm"],
                     moisture=min(1.0, bucket["soil_mm"] / cap),
                     gdd=gdd, phenology=stage, pheno_stress=stress,
                     snow_depth_m=snow / 1000.0 * 3.0,
                     snow_cover_fraction=min(1.0, snow / 1000.0 * 3.0 / SNOW_COVER_FULL_DEPTH_M))
        values = {"accum_mm": accum, "rain_mm": rain, "melt_mm": melt,
                  "thermal_melt_mm": thermal, "snow_export_mm": exported,
                  "et_mm": bucket["et_mm"], "surface_runoff_mm": bucket["surface_drain_mm"],
                  "subsurface_drain_mm": bucket["subsurface_drain_mm"],
                  "snow_residual_mm": snow0 + accum - melt - exported - snow,
                  "soil_residual_mm": bucket["water_residual_mm"],
                  "final_mm": snow + bucket["soil_mm"]}
        for key, value in values.items():
            totals[key] += value
    totals.update(runoff_mm=totals["surface_runoff_mm"],
                  water_residual_mm=totals["snow_residual_mm"] + totals["soil_residual_mm"],
                  interval_start_s=start, interval_end_s=start + seconds,
                  window_s=seconds, modeled_patch_count=len(out),
                  units="mm water-equivalent summed over modeled patches",
                  et_owner="snow_soil_bucket", runoff_phase="liquid",
                  snow_export_phase="solid", sublimation_mm=None,
                  snow_export_destination="outside_patch_unresolved",
                  model_variant="degree_day_soil_bucket")
    return out, totals


def run_season(patches: list, days: int, air_c_by_day: list,
               precip_mm_d: float = 2.0, precip_mm_by_day: list | None = None,
               k_melt: float = 3.0, tbase_c: float = 0.0,
               wind_loss: float | None = None,
               thermal_test=None,
               soil_cap_mm: float = 120.0, field_capacity: float = 0.7,
               k_et: float = 0.8, wind_mps: float = 2.0,
               thermal_flux_mm_d: float = 8.0,
               thermal_flux_mm_d_by_patch: dict | None = None,
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
    use_series = list(precip_mm_by_day) if precip_mm_by_day else None
    if use_series is not None and days > len(use_series) and not extend_last:
        raise ValueError("precip_mm_by_day has insufficient entries for days")
    fluxes = {}
    for patch in patches:
        cx, cz = patch.get("center_xz", [0, 0])
        thermal = bool(thermal_test(cx, cz)) if thermal_test else False
        fluxes[patch["id"]] = (thermal_flux_mm_d_by_patch or {}).get(
            patch["id"], thermal_flux_mm_d if thermal else 0.0)
    _, ledger = step_land(out, 0.0, 0.0, 0.0, wind_mps, soil_cap_mm=soil_cap_mm,
                          field_capacity=field_capacity)
    for day in range(days):
        air = air_c_by_day[min(day, len(air_c_by_day) - 1)]
        precip = use_series[min(day, len(use_series) - 1)] if use_series else precip_mm_d
        out, daily = step_land(out, 86400.0, air, precip, wind_mps,
            interval_start_s=day * 86400.0, thermal_flux_mm_d_by_patch=fluxes,
            k_melt=k_melt, tbase_c=tbase_c, wind_loss=wind_loss,
            soil_cap_mm=soil_cap_mm, field_capacity=field_capacity, k_et=k_et)
        for key in ("accum_mm", "rain_mm", "melt_mm", "thermal_melt_mm", "et_mm",
                    "surface_runoff_mm", "subsurface_drain_mm", "snow_export_mm",
                    "snow_residual_mm", "soil_residual_mm", "water_residual_mm"):
            ledger[key] += daily[key]
        ledger["final_mm"] = daily["final_mm"]
    ledger.update(days=days, window_s=days * 86400.0,
                  interval_start_s=-days * 86400.0, interval_end_s=0.0,
                  interval_role="spinup", runoff_mm=ledger["surface_runoff_mm"],
                  drainage_mm=ledger["subsurface_drain_mm"],
                  storage_residual_mm=ledger["water_residual_mm"],
                  forcing_source=forcing_source, run_mode=run_mode or "unspecified")
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
    window_s = nonnegative("window_s", ledger.get("window_s", ledger.get("days", 0) * 86400.0))
    if window_s == 0.0:
        raise ValueError("ledger window must be positive to form a mean rate")
    if ledger.get("runoff_phase", "liquid") != "liquid":
        raise ValueError("river runoff requires a liquid-water ledger")
    days = window_s / 86400.0
    depth_mm = nonnegative("runoff_mm", ledger["runoff_mm"]) / count
    volume_m3 = depth_mm / 1000.0 * area
    rate = volume_m3 / window_s
    return {
        "runoff_m3_s": round(rate, 6),
        "mean_runoff_depth_mm_d": round(depth_mm / days, 6),
        "runoff_depth_mm": round(depth_mm, 6),
        "catchment_area_m2": area,
        "modeled_patch_count": count,
        "window_days": days,
        "window_s": window_s,
        "phase": "liquid",
        "interval_start_s": ledger.get("interval_start_s"),
        "interval_end_s": ledger.get("interval_end_s"),
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
    from yellowstone_python.thermal_features.pool_crust import HALF
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
