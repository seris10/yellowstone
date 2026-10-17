"""Microclimate: wind/time authority with a condensation model."""
from __future__ import annotations

from yellowstone_python.common.site import SITE_LAT_DEG, SITE_LON_DEG, SITE_UTC_OFFSET_HOURS

from yellowstone_python.common.checks import finite as _finite, nonnegative, positive, positive_int

import logging
import math
import random
import warnings
from datetime import datetime, timezone
from functools import lru_cache

from yellowstone_python.common.site import SITE_ELEVATION_M, SITE_PRESSURE_KPA

__all__ = [
    "SITE_ELEVATION_M", "SITE_PRESSURE_KPA",
    "air_temp", "boiling_point_c", "bundle_weather",
    "condensation_potential", "dewpoint_c",
    "fetch_nws_station_data", "fetch_real_weather",
    "herbie_retrieve_hrrr_rtma",
    "load_real_weather", "load_weather_bundle",
    "metpy_wet_bulb_temperature", "prevailing_direction",
    "pvlib_solar_azimuth_elevation", "solar_snapshot",
    "steam_visibility", "sunlight", "trace", "wind_at",
    "wind_from_direction", "wind_series",
    "xarray_cfgrib_inspect_bundle",
]

logger = logging.getLogger(__name__)


def wet_bulb_c(air_c: float, rh: float) -> tuple[float | None, str]:
    """Return wet-bulb temperature and method, or unavailable outside approximation bounds."""
    air = _finite("air_c", air_c)
    humidity = _validate_rh("humidity", rh)
    if humidity == 0.0:
        return None, "unavailable_zero_humidity"
    try:
        return metpy_wet_bulb_temperature(air, humidity), "metpy_wet_bulb"
    except ImportError:
        pass
    percent = humidity * 100.0
    if not (-20.0 <= air <= 50.0 and 5.0 <= percent <= 99.0):
        return None, "unavailable_outside_stull_2011_validity_range"
    # Stull (2011), doi:10.1175/JAMC-D-11-0143.1.
    wet = (air * math.atan(0.151977 * math.sqrt(percent + 8.313659))
           + math.atan(air + percent) - math.atan(percent - 1.676331)
           + 0.00391838 * percent ** 1.5 * math.atan(0.023101 * percent)
           - 4.686035)
    return wet, "stull_2011_wet_bulb"


def weather_snapshot(epoch_unix: float, weather_cfg: dict,
                     met_bundle: dict | None = None) -> dict:
    """Evaluate schema-2 weather at simulated time with source classes for authored fields."""
    epoch = _finite("epoch_unix", epoch_unix)
    weather = dict(weather_cfg)
    row_index = None
    if met_bundle is not None:
        weather.update(bundle_weather(met_bundle, epoch_s_utc=epoch))
        row_index = weather["met_bundle"]["row_index_utc"]
    offset = float(weather.get("utc_offset_hours", SITE_UTC_OFFSET_HOURS))
    hour = ((epoch + offset * 3600.0) / 3600.0) % 24.0
    air = air_temp(hour, weather.get("night_air_c", 7.0),
                   weather.get("day_warming_c", 15.0), weather.get("lag_hours", 3.0))
    rh = _validate_rh("humidity", weather.get("humidity", 0.45))
    cloud = _validate_rh("cloud", weather.get("cloud", 0.16))
    vector = weather.get("wind_xz_mps", [1.8, 0.6])
    if not isinstance(vector, (tuple, list)) or len(vector) != 2:
        raise ValueError("wind_xz_mps must contain two components")
    wx, wz = [_finite("wind_xz_mps", component) for component in vector]
    speed = math.hypot(wx, wz)
    precip = weather.get("precip_mm_h")
    precip_status = "authored" if precip is not None else "unavailable"
    if met_bundle is not None:
        values = met_bundle.get("precipitation_mm_h")
        if isinstance(values, list) and row_index < len(values):
            precip = values[row_index]
            precip_status = "meteorological_model_forcing" if precip is not None else "unavailable"
    if precip is not None:
        precip = _finite("precipitation_rate_mm_h", precip)
        if precip < 0.0:
            raise ValueError("precipitation_rate_mm_h must be >= 0")
    wet, wet_method = wet_bulb_c(air, rh)
    snow_fraction = (min(1.0, max(0.0, (3.0 - wet) / 4.0)) if wet is not None else 0.0)
    solar = {"source": "unavailable", "latitude_deg": SITE_LAT_DEG,
             "longitude_deg": SITE_LON_DEG}
    try:
        solar = solar_snapshot(epoch)
    except ImportError:
        pass
    return {
        "schema_version": 2,
        "generated_at_unix": int(datetime.now(timezone.utc).timestamp()),
        "valid_time_unix": int(epoch) if epoch.is_integer() else epoch,
        "simulation_time_unix": int(epoch) if epoch.is_integer() else epoch,
        "weather": {
            "air_temperature_c": air, "relative_humidity": rh,
            "wind_speed_mps": speed,
            "wind_direction_deg": (wind_from_direction((wx, wz)) if speed else 0.0),
            "wind_xz_mps": [wx, wz], "cloud_fraction": cloud,
            "precipitation_rate_mm_h": precip if precip is not None else 0.0,
            "snow_fraction": snow_fraction,
            "snow_partition_source": wet_method,
            "dewpoint_c": dewpoint_c(air, rh) if rh > 0.0 else None,
            "visibility_m": float(weather.get("visibility_m", 24000.0)),
            "cloud_base_agl_m": float(weather.get("cloud_base_agl_m", 1050.0)),
            "cloud_thickness_m": float(weather.get("cloud_thickness_m", 600.0)),
        },
        "solar": solar,
        "source": {
            "endpoint": "open-meteo_hourly_bundle" if met_bundle else "authored_defaults",
            "forcing_mode": weather.get("forcing_mode", "authored_defaults"),
            "air_temperature_class": "meteorological_model_forcing" if met_bundle else "authored",
            "visibility_class": "authored", "cloud_base_class": "authored",
            "cloud_thickness_class": "authored", "wind_direction_class": "authored",
            "snow_partition_source": wet_method, "snow_partition_class": "authored",
            "precipitation_status": precip_status, "row_index_utc": row_index,
        },
    }

# Authored weather defaults; fetch_met_forcing.py supplies Open-Meteo model forcing.
WEATHER_PROVENANCE = {
    "night_air_c": "authored_illustrative_7C",
    "day_warming_c": "authored_illustrative_15C",
    "wind_xz_mps": "authored_illustrative_prevailing_1_8_0_6",
    "gust_mps": "authored_illustrative_0_45",
    "humidity": "authored_illustrative_0_45",
    "cloud": "authored_illustrative_0_16",
    "real_data_path": "tools/fetch_met_forcing.py (Open-Meteo API)",
    "integration_notes": ("Real weather forcing requires either config override "
                          "with fetched met bundle or dynamic fetch at build time. "
                          "Current baseline.yaml uses authored defaults only."),
}


def fetch_real_weather(latitude: float = SITE_LAT_DEG,
                       longitude: float = SITE_LON_DEG,
                       days: int = 7) -> dict | None:
    """Fetch real Open-Meteo forcing for site. Returns met bundle dict or None."""
    from yellowstone_python.observations.met import fetch_met_forcing
    return fetch_met_forcing(latitude, longitude, days)




def _validate_rh(name: str, value: object, *,
                 lower: float = 0.0, upper: float = 1.0,
                 inclusive_lower: bool = True) -> float:
    """Shared relative-humidity validator; returns the value as a float.
Raises ValueError on non-finite values or those outside the allowed interval."""
    rh = _finite(name, value)
    if inclusive_lower:
        if rh < lower or rh > upper:
            raise ValueError(f"{name} must be in [{lower}, {upper}]")
    else:
        if rh <= lower or rh > upper:
            raise ValueError(f"{name} must be in ({lower}, {upper}]")
    return rh


def _validate_met_bundle(bundle: object) -> dict:
    if not isinstance(bundle, dict):
        raise ValueError("Met bundle must be a JSON object")
    if bundle.get("schema") != "yellowstone.met_forcing.v1":
        raise ValueError("Unsupported met bundle schema")
    rows = bundle.get("hourly")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Met bundle requires nonempty hourly rows")
    normalized = []
    previous_epoch = -math.inf
    for i, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) != 6:
            raise ValueError(f"hourly[{i}] must contain six values")
        epoch, air, rh, wind, sw, cloud = [
            _finite(f"hourly[{i}][{j}]", value) for j, value in enumerate(row)
        ]
        if epoch <= previous_epoch:
            raise ValueError("Hourly timestamps must be strictly increasing")
        _validate_rh(f"hourly[{i}].rh", rh)
        _validate_rh(f"hourly[{i}].cloud", cloud)
        if wind < 0.0 or sw < 0.0:
            raise ValueError("Wind speed and shortwave radiation must be nonnegative")
        normalized.append([epoch, air, rh, wind, sw, cloud])
        previous_epoch = epoch
    return {**bundle, "hourly": normalized}


def sunlight(hour: float) -> float:
    return max(0.0, math.sin((float(hour) - 6.0) * math.pi / 12.0))


def air_temp(hour: float, night_air_c: float = 7.0,
             day_warming_c: float = 15.0, lag_hours: float = 3.0) -> float:
    shape = max(0.0, math.sin((float(hour) - 6.0 - lag_hours) * math.pi / 12.0))
    return float(night_air_c) + float(day_warming_c) * shape


def wind_at(elapsed_s: float, base_xz: tuple = (1.8, 0.6),
            gust_mps: float = 0.45) -> tuple[float, float]:
    return (float(base_xz[0]) + math.sin(elapsed_s / 61.0) * gust_mps,
            float(base_xz[1]) + math.cos(elapsed_s / 87.0) * gust_mps)


def prevailing_direction(base_xz: tuple = (1.8, 0.6)) -> float:
    """Compass degrees of the low-frequency prevailing wind (no gust)."""
    return (math.degrees(math.atan2(base_xz[0], -base_xz[1])) + 360.0) % 360.0


def wind_from_direction(base_xz: tuple = (1.8, 0.6)) -> float:
    """Meteorological from-direction, degrees."""
    if math.hypot(*base_xz) == 0.0:
        raise ValueError("Calm wind has no direction")
    return (prevailing_direction(base_xz) + 180.0) % 360.0


def steam_visibility(surface_c: float, air_c: float,
                     humidity: float = 0.45) -> float:
    """Artistic index for the Godot uniform path. Prefer condensation_potential() for analysis."""
    v = (float(surface_c) - float(air_c)) / 85.0 * (0.55 + float(humidity) * 0.7)
    return min(0.95, max(0.0, v))


def _es_kpa(t_c: float) -> float:
    """Saturation vapor pressure, Magnus form (kPa)."""
    return 0.61094 * math.exp(17.625 * t_c / (t_c + 243.04))


def dewpoint_c(air_c: float, rh: float) -> float:
    """Invert Magnus: dew point from air temp + relative humidity (0, 1]."""
    rh_f = _validate_rh("relative_humidity", rh,
                        inclusive_lower=False)
    gamma = math.log(rh_f) + 17.625 * float(air_c) / (243.04 + float(air_c))
    return 243.04 * gamma / (17.625 - gamma)


def boiling_point_c(pressure_kpa: float = SITE_PRESSURE_KPA) -> float:
    """Boiling point at site pressure (Antoine, water, valid 1-100 C input)."""
    p = _finite("pressure_kpa", pressure_kpa)
    if p <= 0.0:
        raise ValueError("pressure_kpa must be positive")
    p_mmhg = p * 7.50062
    bp = 1730.63 / (8.07131 - math.log10(p_mmhg)) - 233.426
    if not 1.0 <= bp <= 100.0:
        raise ValueError("Antoine approximation valid for 1-100 C; result %.2f C" % bp)
    return bp


def condensation_potential(surface_c: float, air_c: float, rh: float,
                           wind_mps: float = 2.0) -> dict:
    """Vapor-pressure proxies for condensation visibility."""
    surface_c_f = _finite("surface_c", surface_c)
    air_c_f = _finite("air_c", air_c)
    rh_f = _validate_rh("relative_humidity", rh)
    es_surf = _es_kpa(surface_c_f)
    es_air = _es_kpa(air_c_f)
    ea = rh_f * es_air
    evap = max(0.0, es_surf - ea) * (1.0 + max(0.0, float(wind_mps)) / 5.0)
    dp = dewpoint_c(air_c_f, rh_f) if rh_f > 0.0 else float("nan")
    # Vapor partial pressure mixture.
    e_mix = 0.3 * es_surf + 0.7 * ea
    t_mix = 0.3 * surface_c_f + 0.7 * air_c_f
    supersat = max(0.0, e_mix - _es_kpa(t_mix))
    es_mix = _es_kpa(t_mix)
    physical_excess = (max(0.0, e_mix / es_mix - 1.0)
                       if es_mix > 0 else 0.0)
    rel_proxy = supersat / max(es_surf, 1e-9)
    wind_factor = math.exp(-max(0.0, float(wind_mps)) / 8.0)
    return {"evap_pressure_index_kpa_weighted": evap,
            "dewpoint_c": dp,
            "dewpoint_depression_c": air_c_f - dp,
            "supersat_pressure_kpa": supersat,
            "relative_supersaturation": min(1.0, max(0.0, rel_proxy)),
            "mixed_relative_supersaturation": min(
                1.0, max(0.0, physical_excess)),
            "wind_factor": wind_factor,
            "site_pressure_kpa": SITE_PRESSURE_KPA}


def _validate_time_args(seconds: float, dt: float) -> tuple[float, float]:
    return nonnegative("seconds", seconds), positive("dt", dt)


def _sample_count(seconds: float, dt: float) -> int:
    seconds = _finite("seconds", seconds)
    dt = _finite("dt", dt)
    if seconds < 0.0:
        raise ValueError("seconds must be nonnegative")
    if dt <= 0.0:
        raise ValueError("dt must be positive")
    return math.floor(seconds / dt)


WIND_SERIES_DEFAULT_MAX_SAMPLES = 1_000_000


def wind_series(seconds: float = 60.0, dt: float = 1.0,
                base_xz: tuple = (1.8, 0.6), gust_mps: float = 0.45,
                seed: int = 11,
                max_samples: int = WIND_SERIES_DEFAULT_MAX_SAMPLES) -> list:
    """Seeded Ornstein-Uhlenbeck gusts around the prevailing vector."""
    seconds, dt = _validate_time_args(seconds, dt)
    n = _sample_count(seconds, dt)
    cap = positive_int("max_samples", max_samples)
    if n + 1 > cap:
        raise ValueError(
            f"wind_series would allocate {n + 1} samples (cap {cap})"
        )
    dt_f = float(dt)
    bx = _finite("base_x", base_xz[0])
    bz = _finite("base_z", base_xz[1])
    gust = _finite("gust_mps", gust_mps)
    if gust < 0.0:
        raise ValueError("gust_mps must be nonnegative")
    rng = random.Random(seed)
    theta = 0.08
    sigma = gust * 0.55
    decay = math.exp(-theta * dt_f)
    noise_sd = sigma * math.sqrt(
        -math.expm1(-2.0 * theta * dt_f) / (2.0 * theta))
    gx = gz = 0.0
    out = [(bx, bz)]
    for _ in range(n):
        gx = decay * gx + noise_sd * rng.gauss(0.0, 1.0)
        gz = decay * gz + noise_sd * rng.gauss(0.0, 1.0)
        out.append((bx + gx, bz + gz))
    return out


def trace(seconds: float = 60.0, dt: float = 1.0, hour0: float = 16.2,
          day_rate: float = 1.0, seed: int | None = None, **kw) -> list:
    """Per-second (wind, air_c, hour) trace for the renderer.
steam_62C is an artistic visibility index."""
    seconds, dt = _validate_time_args(seconds, dt)
    night = kw.get("night_air_c", 7.0)
    warming = kw.get("day_warming_c", 15.0)
    lag = kw.get("lag_hours", 3.0)
    base = tuple(kw.get("base_xz", kw.get("wind_xz_mps", (1.8, 0.6))))
    gust = kw.get("gust_mps", 0.45)
    ou = wind_series(seconds, dt, base, gust, seed) if seed is not None else None
    out = []
    n = _sample_count(seconds, dt)
    for i in range(n + 1):
        t = i * dt
        hour = (hour0 + t * day_rate / 3600.0) % 24.0
        a = air_temp(hour, night, warming, lag)
        w = ou[i] if ou is not None else wind_at(t, base, gust)
        out.append({"t": t, "hour": hour, "air_c": a,
                    "wind_x": w[0], "wind_z": w[1],
                    "steam_62C": steam_visibility(62.0, a,
                                                  kw.get("humidity", 0.45))})
    return out


def load_weather_bundle(path: str) -> dict | None:
    import json
    from pathlib import Path
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return _validate_met_bundle(data)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Cannot load met bundle %s: %s", path, exc)
        return None


def load_real_weather(path: str) -> dict | None:
    """Deprecated alias for load_weather_bundle; prefer the new name."""
    warnings.warn(
        "load_real_weather is deprecated; call load_weather_bundle",
        DeprecationWarning,
        stacklevel=2,
    )
    return load_weather_bundle(path)


def bundle_weather(
    bundle: dict,
    *,
    hour: float | None = None,
    epoch_s_utc: float | None = None,
    timestamp_utc: datetime | None = None,
    default_wind: tuple[float, float] = (1.8, 0.6),
    default_gust: float = 0.45,
    max_distance_s: float = 3600.0,
) -> dict:
    """Nearest-row weather snapshot keyed by timestamp_utc, epoch_s_utc, or hour (deprecated).
Static row (no daily curve)."""
    bundle = _validate_met_bundle(bundle)
    rows = bundle.get("hourly", [])
    if not rows:
        raise ValueError("Bundle requires nonempty hourly rows")
    provided = sum(
        1 for arg in (timestamp_utc, epoch_s_utc, hour) if arg is not None)
    if provided == 0:
        raise ValueError(
            "bundle_weather requires timestamp_utc, epoch_s_utc, or hour")
    if provided > 1:
        raise ValueError(
            "bundle_weather accepts only one time argument")
    if timestamp_utc is not None:
        if not isinstance(timestamp_utc, datetime):
            raise TypeError("timestamp_utc must be a datetime")
        if (timestamp_utc.tzinfo is None
                or timestamp_utc.utcoffset() is None):
            raise ValueError("timestamp_utc must be timezone-aware")
        target = _finite(
            "timestamp_utc",
            timestamp_utc.astimezone(timezone.utc).timestamp(),
        )
    elif epoch_s_utc is not None:
        target = _finite("epoch_s_utc", epoch_s_utc)
    else:
        warnings.warn(
            "bundle_weather(hour=) is deprecated; "
            "pass timestamp_utc or epoch_s_utc",
            DeprecationWarning,
            stacklevel=2,
        )
        first_epoch = float(rows[0][0])
        assert hour is not None
        target = first_epoch + float(hour) * 3600.0
    tolerance = _finite("max_distance_s", max_distance_s)
    if tolerance < 0.0:
        raise ValueError("max_distance_s must be nonnegative")
    idx = min(range(len(rows)), key=lambda i: abs(rows[i][0] - target))
    epoch, air, rh, speed, sw, cloud = rows[idx]
    if abs(float(epoch) - target) > tolerance:
        raise ValueError("No sufficiently close weather row")
    wx, wz = default_wind
    magnitude = math.hypot(wx, wz)
    if magnitude == 0.0 and float(speed) > 0.0:
        raise ValueError("Nonzero wind speed requires a fallback direction")
    scale = float(speed) / magnitude if magnitude else 0.0
    gust = _finite("default_gust", default_gust)
    if gust < 0.0:
        raise ValueError("default_gust must be nonnegative")
    wind_xz = [wx * scale, wz * scale]
    return {
        "forcing_mode": "measured_absolute_temperature",
        "night_air_c": round(float(air), 2),
        "day_warming_c": 0.0,
        "humidity": round(float(rh), 4),
        "cloud": round(float(cloud), 4),
        "wind_xz_mps": [round(wind_xz[0], 2), round(wind_xz[1], 2)],
        "gust_mps": round(float(gust), 2),
        "met_bundle": {
            "schema": bundle.get("schema"),
            "request": bundle.get("request"),
            "fetched_at_utc": bundle.get("fetched_at_utc"),
            "elevation_m": bundle.get("elevation_m"),
            "row_index_utc": idx,
            "row_epoch_s_utc": float(epoch),
            "forcing_mode": "measured_absolute_temperature",
            "air_c_source": "bundle hourly temperature",
            "rh_source": "bundle hourly humidity",
            "cloud_source": "bundle hourly cloud",
            "wind_speed_source": "bundle hourly wind speed",
            "wind_direction_source": "authored fallback",
            "gust_source": "authored fallback",
            "note": ("Absolute-temperature snapshot: night_air_c carries the "
                     "measured value; day_warming_c is held at zero so a "
                     "diurnal curve is not fabricated."),
        },
    }


def pvlib_solar_azimuth_elevation(
    latitude: float = SITE_LAT_DEG,
    longitude: float = SITE_LON_DEG,
    *,
    timestamp_utc_str: str = "2026-10-11T16:20:00+00:00",
) -> tuple[float, float]:
    """Solar azimuth/elevation (deg) via pvlib with an explicitly timezone-aware timestamp."""
    import pandas as pd
    from pvlib import solarposition
    ts = datetime.fromisoformat(timestamp_utc_str.replace("Z", "+00:00"))
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("Solar timestamp must include a timezone")
    times = pd.DatetimeIndex([ts.astimezone(timezone.utc)])
    result = solarposition.get_solarposition(times, latitude, longitude)
    azimuth = float(result["azimuth"].iloc[0]) % 360.0
    elevation = float(result["elevation"].iloc[0])
    return azimuth, elevation


@lru_cache(maxsize=128)
def _solar_day_events(day: str, latitude: float, longitude: float) -> tuple:
    """Return cached sunrise and sunset epochs for a UTC date and site."""
    import pandas as pd
    from pvlib import solarposition
    result = solarposition.sun_rise_set_transit_spa(
        pd.DatetimeIndex([pd.Timestamp(day, tz="UTC")]), latitude, longitude)
    return tuple(float(result[key].iloc[0].timestamp())
                 if not pd.isna(result[key].iloc[0]) else None
                 for key in ("sunrise", "sunset"))


def solar_snapshot(
    epoch_unix: float,
    *,
    latitude: float = SITE_LAT_DEG,
    longitude: float = SITE_LON_DEG,
) -> dict:
    """Weather-snapshot solar block for the Godot reader.
Field names match weather_snapshot_reader.gd; sunrise/sunset epochs are pvlib daily values."""
    import pandas as pd
    from pvlib import solarposition
    epoch = float(epoch_unix)
    if not math.isfinite(epoch):
        raise ValueError("epoch_unix must be finite")
    ts = datetime.fromtimestamp(epoch, tz=timezone.utc)
    times = pd.DatetimeIndex([ts])
    position = solarposition.get_solarposition(times, latitude, longitude)
    azimuth = float(position["azimuth"].iloc[0]) % 360.0
    elevation = float(position["elevation"].iloc[0])
    sunrise, sunset = _solar_day_events(ts.date().isoformat(), latitude, longitude)
    return {
        "solar_azimuth_deg": round(azimuth, 2),
        "solar_elevation_deg": round(elevation, 2),
        "sunrise_epoch_unix": sunrise,
        "sunset_epoch_unix": sunset,
        "source": "pvlib",
        "latitude_deg": float(latitude),
        "longitude_deg": float(longitude),
    }


def metpy_wet_bulb_temperature(air_temp_c: float, relative_humidity: float,
                               pressure_pa: float = SITE_PRESSURE_KPA * 1000.0
                               ) -> float:
    """Wet-bulb temperature via metpy.calc with site pressure.
Dewpoint from Magnus inversion of air temperature and relative humidity."""
    import metpy.calc as mpcalc
    from metpy.units import units
    temperature = _finite("air_temp_c", air_temp_c)
    rh = _validate_rh("relative_humidity", relative_humidity,
                      inclusive_lower=False)
    pressure = _finite("pressure_pa", pressure_pa)
    if pressure <= 0.0:
        raise ValueError("pressure_pa must be positive")
    dewpoint = dewpoint_c(temperature, rh)
    result = mpcalc.wet_bulb_temperature(
        units.Quantity(pressure, "Pa"),
        units.Quantity(temperature, "degC"),
        units.Quantity(dewpoint, "degC"),
    )
    return float(result.to("degC").magnitude)


def _nws_quantity(
    properties: dict,
    key: str,
    factors: dict[str, float],
) -> float | None:
    reading = properties.get(key) or {}
    value = reading.get("value")
    if value is None:
        return None
    unit = reading.get("unitCode")
    if unit not in factors:
        raise ValueError(f"Unsupported {key} unit: {unit!r}")
    return _finite(key, value) * factors[unit]


NWS_DEFAULT_USER_AGENT = (
    "yellowstone-microclimate/1.0 (operator-provides-contact)"
)


def fetch_nws_station_data(station_id: str,
                           timeout_s: float = 10.0,
                           user_agent: str = NWS_DEFAULT_USER_AGENT
                           ) -> dict | None:
    """Retrieve NWS observation data via requests.
station_id is required; user_agent should identify the application and a contact."""
    if not isinstance(station_id, str) or not station_id.strip():
        raise ValueError("station_id must be a nonempty string")
    try:
        import requests
        url = (
            f"https://api.weather.gov/stations/{station_id}"
            "/observations/latest"
        )
        resp = requests.get(
            url,
            timeout=timeout_s,
            headers={"User-Agent": user_agent},
        )
        resp.raise_for_status()
        data = resp.json()
        props = data.get("properties", {})
        return {
            "source": "NWS_station",
            "station": station_id,
            "observed_at_utc": props.get("timestamp"),
            "temperature_c": _nws_quantity(
                props, "temperature", {"wmoUnit:degC": 1.0}
            ),
            "relative_humidity": _nws_quantity(
                props, "relativeHumidity", {"wmoUnit:percent": 0.01}
            ),
            "wind_speed_mps": _nws_quantity(
                props,
                "windSpeed",
                {
                    "wmoUnit:km_h-1": 1.0 / 3.6,
                    "wmoUnit:m_s-1": 1.0,
                },
            ),
            "precip_mm_h": _nws_quantity(
                props,
                "precipitationLastHour",
                {
                    "wmoUnit:mm": 1.0,
                    "wmoUnit:m": 1000.0,
                    "wmoUnit:in": 25.4,
                },
            ),
        }
    except Exception as exc:
        logger.warning("NWS station %s fetch/parsing failed: %s", station_id, exc)
        return None


def herbie_retrieve_hrrr_rtma(
    date_str: str,
    model: str = "hrrr",
    product: str = "sfc",
    fxx: int = 0,
) -> dict | None:
    """Retrieve HRRR/RTMA inventory metadata via Herbie.
Returns a variable list; status marks that site-point forcing is absent."""
    if not isinstance(date_str, str) or not date_str.strip():
        raise ValueError("date_str must be a nonempty string")
    try:
        from herbie import Herbie
        h = Herbie(
            date_str,
            model=model,
            product=product,
            fxx=fxx,
        )
        search = r":(?:TMP|RH):2 m|:(?:UGRD|VGRD):10 m|:APCP:surface"
        inventory = h.inventory(search)
        h.download(search)
        result = h.xarray(search)
        fetched_at_utc = datetime.now(timezone.utc).isoformat(
            timespec="seconds")
        try:
            variables = (
                list(result.variables) if hasattr(result, "variables")
                else ["TMP_2m", "RH_2m", "WIND_10m", "APCP_surface"]
            )
            inv_index = (
                list(inventory.index) if hasattr(inventory, "index")
                else "inventory_available"
            )
            return {
                "source": "Herbie_" + model,
                "bundle_schema": "herbie_grib.v1",
                "status": "variables_only_not_site_forcing",
                "variables": variables,
                "fetched_at_utc": fetched_at_utc,
                "model_run_utc": date_str,
                "model_run_fxx_hours": int(fxx),
                "herbie_inventory": inv_index,
                "note": (
                    "Variable list only. "
                    "Site-point extraction is not performed here."
                ),
            }
        finally:
            if hasattr(result, "close"):
                result.close()
    except Exception as exc:
        logger.warning(
            "Herbie retrieval failed (model=%s, product=%s, date=%s): %s",
            model, product, date_str, exc,
        )
        return None


def xarray_cfgrib_inspect_bundle(path: str) -> dict | None:
    """Inspect frozen met bundle (JSON) or Herbie grib with xarray + cfgrib."""
    from pathlib import Path
    p = Path(path)
    if not p.is_file():
        return None
    if p.suffix == ".json":
        try:
            import json
            data = json.loads(p.read_text(encoding="utf-8"))
            hourly = data.get("hourly", [])
            variables = ["epoch_s_UTC", "air_C", "rh_0-1", "wind_mps", "sw_Wm2", "cloud_0-1"] if hourly else ["none"]
            return {
                "variables": variables,
                "dimensions": {"hourly": len(hourly), "variables": len(variables)},
                "title": data.get("schema", "yellowstone.met_forcing.v1"),
                "note": "JSON frozen bundle inspected; not a GRIB grid.",
            }
        except Exception as exc:
            logger.warning("JSON bundle inspection failed for %s: %s", path, exc)
            return None
    try:
        import xarray
        import cfgrib
        with xarray.open_dataset(str(p), engine="cfgrib") as ds:
            return {
                "variables": list(ds.variables),
                "dimensions": dict(ds.sizes),
                "title": str(ds.attrs.get("title", "GRIB bundle")),
                "note": "GRIB bundle inspected via xarray + cfgrib.",
            }
    except Exception as exc:
        logger.warning("GRIB inspection failed for %s: %s", path, exc)
        return None
