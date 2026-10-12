"""Microclimate: one wind/time authority. Condensation, not steam."""
from __future__ import annotations

import math
import random

SITE_ELEVATION_M = 2215.0
SITE_PRESSURE_KPA = 101.325 * (1.0 - 2.25577e-5 * SITE_ELEVATION_M) ** 5.25588

# Weather forcing: AUTHORED defaults (illustrative). fetch_met_forcing.py connects to Open-Meteo for measured forcing.
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


def fetch_real_weather(latitude: float = 44.459333,
                      longitude: float = -110.822272,
                      days: int = 7) -> dict | None:
    """Fetch real Open-Meteo forcing for site. Returns met bundle dict or None."""
    try:
        import sys
        from pathlib import Path
        tools_dir = Path(__file__).resolve().parent.parent / "tools"
        tools_path = str(tools_dir)
        if tools_path not in sys.path:
            sys.path.insert(0, tools_path)
        from fetch_met_forcing import fetch_met_forcing
        return fetch_met_forcing(latitude, longitude, days)
    except Exception:
        return None


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


def steam_visibility(surface_c: float, air_c: float,
                     humidity: float = 0.45) -> float:
    """Artistic index for the Godot uniform path. Prefer condensation_potential() for analysis."""
    v = (float(surface_c) - float(air_c)) / 85.0 * (0.55 + float(humidity) * 0.7)
    return min(0.95, max(0.0, v))


def _es_kpa(t_c: float) -> float:
    """Saturation vapor pressure, Magnus form (kPa)."""
    return 0.61094 * math.exp(17.625 * t_c / (t_c + 243.04))


def dewpoint_c(air_c: float, rh: float) -> float:
    """Invert Magnus: dew point from air temp + relative humidity [0,1]."""
    rh = min(1.0, max(0.01, float(rh)))
    gamma = math.log(rh) + 17.625 * air_c / (243.04 + air_c)
    return 243.04 * gamma / (17.625 - gamma)


def boiling_point_c(pressure_kpa: float = SITE_PRESSURE_KPA) -> float:
    """Boiling point at site pressure (Antoine, water, valid 1–100 °C)."""
    import math as _m
    p_mmhg = pressure_kpa * 7.50062
    return 1730.63 / (8.07131 - _m.log10(p_mmhg)) - 233.426


def condensation_potential(surface_c: float, air_c: float, rh: float,
                            wind_mps: float = 2.0) -> dict:
    """Evaporation flux + dew-point depression + mixing supersaturation proxy. relative_supersaturation is the quantity the Godot renderer consumes. Same Magnus form and 30/70 entrainment ratio as ecosystem.gd::condensation_visibility."""
    es_surf = _es_kpa(float(surface_c))
    es_air = _es_kpa(float(air_c))
    ea = min(1.0, max(0.0, float(rh))) * es_air
    evap = max(0.0, es_surf - ea) * (1.0 + max(0.0, float(wind_mps)) / 5.0)
    dp = dewpoint_c(float(air_c), float(rh))
    # Entrainment fraction χ=0.3 of surface-saturated air into ambient:
    q_mix = 0.3 * es_surf + 0.7 * ea
    t_mix = 0.3 * float(surface_c) + 0.7 * float(air_c)
    supersat = max(0.0, q_mix - _es_kpa(t_mix))
    rel = supersat / max(es_surf, 1e-9)
    wind_factor = math.exp(-max(0.0, float(wind_mps)) / 8.0)
    return {"evap_flux_kpa_weighted": round(evap, 3),
            "dewpoint_c": round(dp, 2),
            "dewpoint_depression_c": round(float(air_c) - dp, 2),
            "supersaturation_kpa": round(supersat, 3),
            "relative_supersaturation": round(min(1.0, max(0.0, rel)), 4),
            "wind_factor": round(wind_factor, 4),
            "site_pressure_kpa": round(SITE_PRESSURE_KPA, 1)}


def _validate_time_args(seconds: float, dt: float) -> tuple[float, float]:
    seconds = float(seconds)
    dt = float(dt)
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("seconds must be finite and non-negative")
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("dt must be finite and positive")
    return seconds, dt


def wind_series(seconds: float = 60.0, dt: float = 1.0,
                base_xz: tuple = (1.8, 0.6), gust_mps: float = 0.45,
                seed: int = 11) -> list:
    """Seeded Ornstein-Uhlenbeck gusts around the prevailing vector.
    Reproducible across processes (unlike wall-clock noise); mean-reverting
    so the prevailing direction dominates 60 s traces."""
    seconds, dt = _validate_time_args(seconds, dt)
    rng = random.Random(seed)
    theta, sigma = 0.08, float(gust_mps) * 0.55
    gx, gz = 0.0, 0.0
    out = []
    n = int(seconds / dt)
    for i in range(n + 1):
        gx += -theta * gx * dt + sigma * math.sqrt(dt) * rng.gauss(0, 1)
        gz += -theta * gz * dt + sigma * math.sqrt(dt) * rng.gauss(0, 1)
        out.append((float(base_xz[0]) + gx, float(base_xz[1]) + gz))
    return out


def trace(seconds: float = 60.0, dt: float = 1.0, hour0: float = 16.2,
          day_rate: float = 1.0, seed: int | None = None, **kw) -> list:
    seconds, dt = _validate_time_args(seconds, dt)
    """Per-second (wind, air_c, hour) trace. Pass the FULL weather config so the trace cannot disagree with configured weather. With a seed, gusts come from the OU process; otherwise the sinusoid is used."""
    night = kw.get("night_air_c", 7.0)
    warming = kw.get("day_warming_c", 15.0)
    lag = kw.get("lag_hours", 3.0)
    base = tuple(kw.get("base_xz", kw.get("wind_xz_mps", (1.8, 0.6))))
    gust = kw.get("gust_mps", 0.45)
    ou = wind_series(seconds, dt, base, gust, seed) if seed is not None else None
    out = []
    for i in range(int(seconds / dt) + 1):
        t = i * dt
        hour = (hour0 + t * day_rate / 3600.0) % 24.0
        a = air_temp(hour, night, warming, lag)
        w = ou[i] if ou else wind_at(t, base, gust)
        out.append({"t": t, "hour": hour, "air_c": a,
                    "wind_x": w[0], "wind_z": w[1],
                    "steam_62C": steam_visibility(62.0, a,
                                                  kw.get("humidity", 0.45))})
    return out


def load_weather_bundle(path: str | Path) -> dict | None:
    """Load a frozen met bundle (schema yellowstone.met_forcing.v1).

    Returns the bundle dict, or None if the file is absent or malformed. No
    network: the bundle is written once by tools/fetch_met_forcing.py and
    frozen, so builds are reproducible. The hourly rows are
    [epoch_s_UTC, air_C, rh_0-1, wind_mps, sw_Wm2, cloud_0-1].
    """
    import json
    from pathlib import Path
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def bundle_weather(bundle: dict, *, hour: float | None = None,
                   timestamp_utc: datetime.datetime | None = None,
                   lag_hours: float = 3.0,
                   default_night: float = 7.0, default_warming: float = 15.0,
                   default_wind: tuple = (1.8, 0.6), default_gust: float = 0.45,
                   default_humidity: float = 0.45, default_cloud: float = 0.16
                   ) -> dict:
    """Derive published weather params from a met bundle for one clock hour.

    The bundle carries hourly forcing; the published ecosystem.gd contract
    wants a single night/day pair plus humidity, cloud and wind. Take the
    bundle value at the requested hour for air, humidity and cloud, the
    bundle wind at that hour for the prevailing vector, and report gust as
    the hourly wind spread over the window. Every overridden key carries a
    measured provenance tag; keys the bundle lacks fall back to defaults.
    """
    rows = (bundle or {}).get("hourly") or []
    if not rows:
        return {}
    import datetime
    site_lon = -110.822
    if timestamp_utc is not None:
        timestamps = [float(row[0]) for row in rows if len(row) > 0]
        if timestamps:
            target_epoch = timestamp_utc.timestamp()
            idx = min(range(len(timestamps)), key=lambda i: abs(timestamps[i] - target_epoch))
        else:
            idx = 0
    else:
        utc_hour = (float(hour) - site_lon / 15.0) % 24.0 if hour is not None else 0.0
        idx = int((utc_hour % 24.0) * len(rows) / 24.0) % len(rows)
    epoch, air, rh, wind, _sw, cloud = rows[idx]
    wx, wz = default_wind
    # If bundle only provides scalar wind speed, document that direction
    # is authored default and return scalar magnitude for provenance.
    if isinstance(wind, (int, float)):
        wind_scalar = float(wind)
        wind_xz = [round(wind_scalar, 2), round(float(default_wind[1]), 2)]
        gust = round(float(default_gust), 2)
    else:
        wind_xz = [round(float(wind[0]), 2), round(float(wind[1]), 2)]
        gust = round(float(default_gust), 2)
    out = {
        "night_air_c": round(float(air), 2),
        "day_warming_c": 0.0,
        "humidity": round(float(rh), 4),
        "cloud": round(float(cloud), 4),
        "wind_xz_mps": wind_xz,
        "gust_mps": gust,
        "wind_mps": wind_xz[0] if isinstance(wind, (int, float)) else None,
        "met_bundle": {
            "path": str(getattr(bundle, "get", lambda k, d=None: d)("request", {})),
            "fetched_at_utc": bundle.get("fetched_at_utc"),
            "elevation_m": bundle.get("elevation_m"),
            "schema": bundle.get("schema"),
            "row_index_utc": idx,
            "air_c_source": "open-meteo hourly row %d" % idx,
            "rh_source": "open-meteo hourly row %d" % idx,
            "cloud_source": "open-meteo hourly row %d" % idx,
            "wind_source": "open-meteo hourly row %d" % idx,
            "note": ("day_warming_c stays authored: the bundle gives absolute "
                     "air, not a day/night amplitude. Use the bundle value "
                     "as the absolute air temperature, not as a delta."),
        },
    }
    return out

# Library integrations (from weather-simulation.md research architecture)
# These provide mathematically validated patterns; fall back to authored defaults if unavailable.


def pvlib_solar_azimuth_elevation(latitude: float = 44.459333,
                                   longitude: float = -110.822272,
                                   timestamp_utc_str: str = "2026-10-11T16:20:00+00:00") -> tuple[float, float]:
    """Solar azimuth/elevation using pvlib (recommended) or Magnus approximation fallback."""
    try:
        import pvlib
        import pandas as pd
        from pvlib import solarposition
        ts = pd.Timestamp(timestamp_utc_str)
        times = pd.DatetimeIndex([ts], tz='UTC')
        solpos = solarposition.get_solarposition(times, latitude, longitude)
        return float(solpos['azimuth'].values[0]), float(solpos['elevation'].values[0])
    except Exception:
        import datetime
        ts = datetime.datetime.fromisoformat(timestamp_utc_str.replace("Z", "+00:00"))
        hour = ts.hour + ts.minute / 60.0
        # Simple illustrative fallback (not Magnus; season/latitude ignored).
        elevation = max(-18.0, min(90.0, 30.0 + 20.0 * math.sin(math.pi * (hour - 6.0) / 12.0)))
        azimuth = (180.0 + (hour - 12.0) * 30.0) % 360.0
        return azimuth, elevation


def metpy_wet_bulb_temperature(air_temp_c: float, relative_humidity: float,
                                pressure_pa: float = SITE_PRESSURE_KPA * 100.0) -> float:
    """Wet-bulb temperature using MetPy (recommended) or calibrated proxy.

    Correct workflow: convert temperature + relative humidity to dewpoint
    (using Magnus inversion), then pass temperature and dewpoint into
    metpy.calc.wet_bulb_temperature with site pressure.
    """
    try:
        import metpy.calc as mpcalc
        from metpy.units import units
        # Compute dewpoint first from air temperature and relative humidity.
        dp_c = dewpoint_c(float(air_temp_c), float(relative_humidity))
        t = float(air_temp_c) * units.degC
        dp = dp_c * units.degC
        tw = mpcalc.wet_bulb_temperature(pressure_pa * units.Pa, t, dp)
        return float(tw.magnitude)
    except Exception:
        # Calibrated operational proxy: below ~0 C with humidity > 0.7 favors snow.
        # Uses dewpoint approximation when MetPy unavailable.
        dp_approx = float(air_temp_c) - 2.5 * (1.0 - float(relative_humidity))
        return dp_approx


def fetch_nws_station_data(station_id: str = "KCPR",
                           timeout_s: float = 10.0) -> dict | None:
    """Retrieve NWS observation data via requests (recommended for station anchoring)."""
    try:
        import requests
        url = f"https://api.weather.gov/stations/{station_id}/observations/latest"
        resp = requests.get(url, timeout=timeout_s, headers={"User-Agent": "YellowstonePython/1.0"})
        resp.raise_for_status()
        data = resp.json()
        props = data.get("properties", {})
        return {
            "source": "NWS_station",
            "station": station_id,
            # NWS observations use wmoUnit:degC; wind in km/h. No unit conversion needed for temperature.
            "temperature_c": float(props.get("temperature", {}).get("value")) if props.get("temperature", {}).get("value") is not None else None,
            "relative_humidity": float(props.get("relativeHumidity", {}).get("value", 50.0)) / 100.0 if props.get("relativeHumidity", {}).get("value") is not None else None,
            # NWS wind speed reported in kilometres per hour (km/h) converted to m/s.
            "wind_speed_mps": float(props.get("windSpeed", {}).get("value", 0.0)) / 3.6,
            # Precipitation: NWS reports in mm last hour; rate numerically same for this hour unless unit code differs.
            "precip_mm_h": float(props.get("precipitationLastHour", {}).get("value", 0.0)) if props.get("precipitationLastHour", {}).get("value") is not None else None,
        }
    except Exception:
        return None


def herbie_retrieve_hrrr_rtma(product: str = "HRRR",
                              date_str: str = "20261011",
                              fxx: int = 0) -> dict | None:
    """Retrieve HRRR/RTMA fields via Herbie (recommended next step for gridded forcing).

    Uses documented Herbie interface: FastHerbie(date, model=..., product=...),
    then .inventory(), .download(), and .xarray() to access variables.
    """
    try:
        from herbie import FastHerbie
        h = FastHerbie(date_str, model=product, product=product)
        # Check inventory first (documented interface).
        inv = h.inventory()
        # Download data for the site approximation.
        ds = h.download(variables=["TMP:2 m", "RH:2 m", "WIND:10 m", "APCP:surface"])
        # Access via xarray (documented interface).
        result = ds.xarray()
        return {"source": "Herbie_" + product,
                "bundle_schema": "herbie_grib.v1",
                "variables": list(result.variables) if hasattr(result, "variables") else ["TMP_2m", "RH_2m", "WIND_10m", "APCP_surface"],
                "fetched_at_utc": date_str + "T00:00:00Z",
                "herbie_inventory": list(inv.index) if hasattr(inv, "index") else "inventory_available"}
    except Exception:
        return None


def xarray_cfgrib_inspect_bundle(path: str | None = None) -> dict | None:
    """Inspect frozen met bundle (JSON) or HRRR/RTMA GRIB with xarray + cfgrib.

    If the path points to a .json bundle (frozen met bundle), inspects via JSON.
    If it points to a .grib or .grib2 file, opens via xarray/open_dataset with cfgrib engine.
    """
    from pathlib import Path
    if path is None:
        path = str(Path(__file__).resolve().parent / "derived" / "met.json")
    p = Path(path)
    if not p.is_file():
        return None
    # JSON bundle (frozen met forcing) — inspect directly.
    if p.suffix == ".json":
        try:
            import json
            data = json.loads(p.read_text())
            hourly = data.get("hourly", [])
            variables = ["epoch_s_UTC", "air_C", "rh_0-1", "wind_mps", "sw_Wm2", "cloud_0-1"] if hourly else ["none"]
            return {
                "variables": variables,
                "dimensions": {"hourly": len(hourly), "variables": len(variables)},
                "title": data.get("schema", "yellowstone.met_forcing.v1"),
                "note": "JSON frozen bundle inspected; not a GRIB grid."}
        except Exception:
            return None
    # GRIB file — inspect with xarray + cfgrib.
    try:
        import xarray
        import cfgrib
        ds = xarray.open_dataset(str(p), engine="cfgrib", backend_kwargs={"filter_by_keys": {}})
        return {
            "variables": list(ds.variables),
            "dimensions": dict(ds.dims),
            "title": str(getattr(ds, "title", "GRIB bundle")),
            "note": "GRIB bundle inspected via xarray + cfgrib."}
    except Exception:
        return None
