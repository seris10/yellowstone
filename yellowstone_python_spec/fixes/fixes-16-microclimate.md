The main problems are **incorrect units, broken API definitions, incorrect time selection, and silent failures that hide invalid results**. Several functions also claim to provide measured or physically validated behavior when they actually return proxies.

This is a static audit of the supplied file; I haven’t executed it or checked the companion Godot code.

## Highest-priority findings

| Priority | Issue | Consequence |
|---|---|---|
| Critical | `load_real_weather()` is defined twice | The second definition completely replaces the network-fetch function. Calls using `latitude=...` fail. |
| Critical | Wet-bulb pressure uses `kPa * 100` | MetPy receives pressure **10× too low**. Use `* 1000`. |
| Critical | Bundle row selection ignores timestamps and reverses the longitude conversion | Multi-day bundles select unrelated hours/dates. |
| High | NWS precipitation is multiplied by `25.4` despite being documented as millimeters | Rainfall is inflated 25.4× when the reported unit is millimeters. |
| High | Solar fallback ignores latitude, longitude, and season | Its elevation is always between 10° and 50°, including midnight. |
| High | Herbie uses the wrong object/API flow | `fxx` is ignored; model and product are conflated; a download result is treated as a Herbie object. |
| High | JSON loader does not validate the schema or rows | Lists, malformed rows, `null`, and nonfinite values can pass through and fail later. |
| Medium | OU gusts advance before the first sample | The value labeled `t=0` already contains one timestep of evolution. |
| Medium | Broad exception handlers return plausible-looking fallbacks | Missing dependencies, invalid inputs, and implementation bugs become indistinguishable. |

---

## 1. Separate fetching from loading, and validate bundles

Keep the frozen-file loader named `load_real_weather()`. Rename the first function to `fetch_real_weather()` and remove the `sys.path.insert()` modification.

Assuming `tools` is importable as a project package:

```python
def fetch_real_weather(
    latitude: float = 44.459333,
    longitude: float = -110.822272,
    days: int = 7,
) -> dict | None:
    from tools.fetch_met_forcing import fetch_met_forcing
    return fetch_met_forcing(latitude, longitude, days)
```

Configure the project’s import path/package installation instead of mutating global import resolution on every call.

Add shared validation:

```python
import logging

logger = logging.getLogger(__name__)


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not bool")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


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
            _finite(f"hourly[{i}][{j}]", value)
            for j, value in enumerate(row)
        ]

        if epoch <= previous_epoch:
            raise ValueError("Hourly timestamps must be strictly increasing")
        if not 0.0 <= rh <= 1.0 or not 0.0 <= cloud <= 1.0:
            raise ValueError("Humidity and cloud must be fractions in [0, 1]")
        if wind < 0.0 or sw < 0.0:
            raise ValueError("Wind speed and shortwave radiation must be nonnegative")

        normalized.append([epoch, air, rh, wind, sw, cloud])
        previous_epoch = epoch

    return {**bundle, "hourly": normalized}
```

Replace the second loader with:

```python
def load_real_weather(path: str) -> dict | None:
    import json
    from pathlib import Path

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return _validate_met_bundle(data)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Cannot load met bundle %s: %s", path, exc)
        return None
```

This intentionally rejects incomplete rows rather than pretending defaults were applied. If partial bundles are a requirement, implement field-by-field fallback explicitly and record which fields were substituted.

---

## 2. Select weather by UTC timestamp—not array position

This expression is fundamentally wrong:

```python
idx = int((utc_hour % 24.0) * len(rows) / 24.0) % len(rows)
```

For a seven-day bundle, it stretches one clock day across all seven days. It never examines the row timestamps.

Also, for local **solar** time:

```text
local = UTC + longitude / 15
UTC   = local - longitude / 15
```

The code uses the opposite sign. Civil local time requires a timezone such as `America/Denver`, not a longitude adjustment.

### Recommended API change

Replace `hour=` with `epoch_s_utc=`. Update callers to provide an actual date and time.

A suitable snapshot implementation is:

```python
def bundle_weather(
    bundle: dict,
    *,
    epoch_s_utc: float,
    default_wind: tuple[float, float] = (1.8, 0.6),
    default_gust: float = 0.45,
    max_distance_s: float = 3600.0,
) -> dict:
    """Return a nearest-row weather snapshot, not a dynamic daily curve."""
    bundle = _validate_met_bundle(bundle)
    rows = bundle["hourly"]

    target = _finite("epoch_s_utc", epoch_s_utc)
    tolerance = _finite("max_distance_s", max_distance_s)
    if tolerance < 0.0:
        raise ValueError("max_distance_s must be nonnegative")

    idx = min(
        range(len(rows)),
        key=lambda i: abs(rows[i][0] - target),
    )
    epoch, air, rh, speed, sw, cloud = rows[idx]

    if abs(epoch - target) > tolerance:
        raise ValueError("No sufficiently close weather row")

    # The schema provides speed, but no direction. Preserve the authored
    # direction while matching the supplied speed.
    wx, wz = (
        _finite("default_wind_x", default_wind[0]),
        _finite("default_wind_z", default_wind[1]),
    )
    magnitude = math.hypot(wx, wz)

    if magnitude == 0.0 and speed > 0.0:
        raise ValueError("Nonzero wind speed requires a fallback direction")

    scale = speed / magnitude if magnitude else 0.0
    gust = _finite("default_gust", default_gust)
    if gust < 0.0:
        raise ValueError("default_gust must be nonnegative")

    return {
        "night_air_c": air,
        "day_warming_c": 0.0,
        "humidity": rh,
        "cloud": cloud,
        "wind_xz_mps": [wx * scale, wz * scale],
        "gust_mps": gust,
        "met_bundle": {
            "schema": bundle["schema"],
            "request": bundle.get("request"),
            "fetched_at_utc": bundle.get("fetched_at_utc"),
            "elevation_m": bundle.get("elevation_m"),
            "row_index_utc": idx,
            "row_epoch_s_utc": epoch,
            "air_c_source": "bundle hourly temperature",
            "rh_source": "bundle hourly humidity",
            "cloud_source": "bundle hourly cloud",
            "wind_speed_source": "bundle hourly wind speed",
            "wind_direction_source": "authored fallback",
            "gust_source": "authored fallback",
            "note": "Absolute-temperature snapshot; day_warming_c is zero.",
        },
    }
```

This also fixes three existing inconsistencies:

- `[wind, wz]` does **not** have magnitude `wind`; normalization does.
- The current gust value is authored, not calculated from the bundle.
- The existing provenance note says warming stays authored, contradicting `day_warming_c = 0.0`.

**Important:** This still creates a snapshot. If `trace()` should follow real hourly weather, select/interpolate bundle values at each trace timestamp. A single snapshot with zero warming freezes temperature for the entire trace.

Also, use **“Open-Meteo forcing”** rather than universally calling it **“measured”**: forecast and reanalysis products are not necessarily station observations.

---

## 3. Fix wet-bulb units and remove the misleading fallback

Replace this function with:

```python
def metpy_wet_bulb_temperature(
    air_temp_c: float,
    relative_humidity: float,
    pressure_pa: float = SITE_PRESSURE_KPA * 1000.0,
) -> float:
    import metpy.calc as mpcalc
    from metpy.units import units

    temperature = _finite("air_temp_c", air_temp_c)
    rh = _finite("relative_humidity", relative_humidity)
    pressure = _finite("pressure_pa", pressure_pa)

    if not 0.0 < rh <= 1.0:
        raise ValueError("relative_humidity must be in (0, 1]")
    if pressure <= 0.0:
        raise ValueError("pressure_pa must be positive")

    dewpoint = dewpoint_c(temperature, rh)

    result = mpcalc.wet_bulb_temperature(
        units.Quantity(pressure, "Pa"),
        units.Quantity(temperature, "degC"),
        units.Quantity(dewpoint, "degC"),
    )
    return float(result.to("degC").magnitude)
```

The existing fallback:

```python
air_temp_c - 2.5 * (1.0 - relative_humidity)
```

is neither a reliable dew-point approximation nor a wet-bulb calculation. Remove it unless you implement a documented approximation with stated validity limits.

Let dependency errors propagate, or catch `ImportError` at the application boundary. Do not silently replace failed physics with unrelated numbers.

---

## 4. Read NWS units and preserve missing values

The current code has two separate problems:

```python
float(None)                       # fails on normal missing observations
float(...value..., 999.0)          # invents an extreme temperature
```

And this is wrong for millimeter-valued precipitation:

```python
precipitation_value * 25.4
```

Use the response’s `unitCode`:

```python
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
```

Replace the returned measurements with:

```python
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
```

A last-hour accumulation in millimeters has the same numerical value as its average rate in mm/h.

Additional changes:

- Log request/parsing failures instead of silently returning `None`.
- Replace the generic User-Agent with an identifiable application/contact.
- Do not default to `KCPR` as a Yellowstone site anchor without justification; it is Casper, Wyoming.
- Let consumers distinguish **missing observation** from **zero wind/rain**.

---

## 5. Correct OU sampling and validate durations

The Euler update becomes unstable for sufficiently large `dt`. An exact OU transition avoids that and fixes the initial timestamp.

```python
def _sample_count(seconds: float, dt: float) -> int:
    seconds = _finite("seconds", seconds)
    dt = _finite("dt", dt)

    if seconds < 0.0:
        raise ValueError("seconds must be nonnegative")
    if dt <= 0.0:
        raise ValueError("dt must be positive")

    # Grid includes t=0; includes the endpoint only if it lies on the grid.
    return math.floor(seconds / dt)


def wind_series(
    seconds: float = 60.0,
    dt: float = 1.0,
    base_xz: tuple[float, float] = (1.8, 0.6),
    gust_mps: float = 0.45,
    seed: int = 11,
) -> list[tuple[float, float]]:
    n = _sample_count(seconds, dt)
    dt = float(dt)
    bx = _finite("base_x", base_xz[0])
    bz = _finite("base_z", base_xz[1])
    gust = _finite("gust_mps", gust_mps)

    if gust < 0.0:
        raise ValueError("gust_mps must be nonnegative")

    rng = random.Random(seed)
    theta = 0.08
    sigma = gust * 0.55  # Retains the original diffusion coefficient.
    decay = math.exp(-theta * dt)
    noise_sd = sigma * math.sqrt(
        -math.expm1(-2.0 * theta * dt) / (2.0 * theta)
    )

    gx = gz = 0.0
    out = [(bx, bz)]

    for _ in range(n):
        gx = decay * gx + noise_sd * rng.gauss(0.0, 1.0)
        gz = decay * gz + noise_sd * rng.gauss(0.0, 1.0)
        out.append((bx + gx, bz + gz))

    return out
```

In `trace()`, change:

```python
for i in range(int(seconds / dt) + 1):
```

to:

```python
n = _sample_count(seconds, dt)
for i in range(n + 1):
```

And change:

```python
w = ou[i] if ou else wind_at(t, base, gust)
```

to:

```python
w = ou[i] if ou is not None else wind_at(t, base, gust)
```

Document that `gust_mps` is **not a maximum gust**: Gaussian OU fluctuations are unbounded. Its meaning also differs from the sinusoidal amplitude used by `wind_at()`.

For untrusted configuration, impose a maximum sample count to prevent excessive allocation.

---

## 6. Remove the fake solar fallback

The fallback’s minimum elevation is 10°:

```python
30.0 + 20.0 * sin(...)
```

Therefore, the sun never sets. “Magnus approximation” is also incorrect terminology here; Magnus is the vapor-pressure approximation used elsewhere.

Use pvlib directly, with an explicitly timezone-aware timestamp:

```python
def pvlib_solar_azimuth_elevation(
    latitude: float = 44.459333,
    longitude: float = -110.822272,
    *,
    timestamp_utc_str: str,
) -> tuple[float, float]:
    from datetime import datetime, timezone

    import pandas as pd
    from pvlib import solarposition

    ts = datetime.fromisoformat(
        timestamp_utc_str.replace("Z", "+00:00")
    )
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("Solar timestamp must include a timezone")

    times = pd.DatetimeIndex([ts.astimezone(timezone.utc)])
    result = solarposition.get_solarposition(
        times, latitude, longitude
    )

    return (
        float(result["azimuth"].iloc[0]),
        float(result["elevation"].iloc[0]),
    )
```

If pvlib must be optional, implement a real solar-position approximation using date, latitude, longitude, and UTC—not this fallback.

---

## 7. Repair the Herbie integration and close datasets

For a single model initialization, use `Herbie`, not the batch-oriented `FastHerbie`. Separate model from product, and pass `fxx`.

For example, the core HRRR flow should resemble:

```python
from herbie import Herbie

h = Herbie(
    date_str,
    model="hrrr",
    product="sfc",
    fxx=fxx,
)

search = r":(?:TMP|RH):2 m|:(?:UGRD|VGRD):10 m|:APCP:surface"

inventory = h.inventory(search)
h.download(search)
result = h.xarray(search)
```

Pin and test against your installed Herbie version; search argument names and return details can vary.

Specific changes:

- Rename the argument to `model`; add a separate `product` argument.
- Configure RTMA separately rather than using `"RTMA"` as both values.
- Do not call `.xarray()` on the return value of `.download()`.
- Separate `model_run_utc` from the actual retrieval timestamp.
- Close returned datasets after extracting metadata.
- If this is supposed to return **site forcing**, extract the site grid point. Listing grid variables alone is not a forcing bundle.

For `xarray_cfgrib_inspect_bundle()`, remove the machine-specific default path and use:

```python
with xarray.open_dataset(
    path,
    engine="cfgrib",
) as ds:
    return {
        "variables": list(ds.variables),
        "dimensions": dict(ds.sizes),
        "title": str(ds.attrs.get("title", "GRIB bundle")),
        "note": "GRIB bundle inspected via xarray + cfgrib.",
    }
```

Use `ds.sizes`, not `ds.dims`, for dimension sizes. Mixed GRIB messages may require meaningful `filter_by_keys` or inspection through `cfgrib.open_datasets()`; an empty filter does not solve incompatible message groups.

---

## 8. Clarify the physical and renderer contracts

### `relative_supersaturation` is not the standard physical quantity

Currently:

```python
rel = supersat / es_surf
```

Physical excess relative to saturation at the mixture temperature is:

```python
es_mix = _es_kpa(t_mix)
physical_excess = max(0.0, q_mix / es_mix - 1.0)
```

**Do not silently replace the existing renderer field.** Keep it for compatibility and add a separately named output:

```python
"mixed_relative_supersaturation": physical_excess,
```

The current mixing calculation is also a proxy: `q_mix` mixes vapor partial pressures, not humidity ratios or moist-air enthalpy. Rename it to `e_mix` and document the approximation. A physical mixing model should conserve water mass and enthalpy at the specified pressure.

### Dew point silently manufactures humidity

This line:

```python
rh = min(1.0, max(0.01, float(rh)))
```

turns 0% RH into 1% RH, while `condensation_potential()` uses actual 0% for vapor pressure.

Choose one explicit policy:

- Reject `rh <= 0` for dew-point calculations; or
- Return a documented undefined result for completely dry air.

Reject values outside `[0, 1]` rather than silently clipping invalid configuration. Add finite-input checks and documented temperature limits to the Magnus functions.

### Wind direction needs a convention

With Godot-style `+X=east`, `-Z=north`, the existing direction is the direction the air moves **toward**. Meteorological wind direction means **from**.

Preserve the existing function, clarify its docstring, and add:

```python
def wind_from_direction(
    base_xz: tuple[float, float] = (1.8, 0.6),
) -> float:
    if math.hypot(*base_xz) == 0.0:
        raise ValueError("Calm wind has no direction")
    return (prevailing_direction(base_xz) + 180.0) % 360.0
```

### Other inexpensive fixes

- Validate positive pressure and the supported Antoine range in `boiling_point_c()`.
- Do not call `evap_flux_kpa_weighted` a mass flux; it is a weighted pressure-difference index.
- Avoid rounding inside analytical functions. Round at serialization/display boundaries.
- Either document `trace()` as renderer-only or include condensation outputs; it currently uses only the artistic `steam_visibility()` path.

---

## Regression tests to add

At minimum:

```python
import inspect

import pytest

import microclimate as m


def test_wet_bulb_pressure_default():
    default = inspect.signature(
        m.metpy_wet_bulb_temperature
    ).parameters["pressure_pa"].default
    assert default == pytest.approx(m.SITE_PRESSURE_KPA * 1000.0)


def test_site_boiling_point():
    assert 92.0 < m.boiling_point_c() < 94.0


def test_wind_initial_sample():
    assert m.wind_series(seconds=0.0) == [(1.8, 0.6)]


@pytest.mark.parametrize(
    "seconds, dt",
    [(-1.0, 1.0), (60.0, 0.0), (60.0, -1.0)],
)
def test_invalid_sampling(seconds, dt):
    with pytest.raises(ValueError):
        m.wind_series(seconds=seconds, dt=dt)


def test_seeded_wind_is_repeatable():
    assert m.wind_series(seed=11) == m.wind_series(seed=11)
```

Also test:

- Multi-day bundle selection by actual epoch.
- Output wind-vector magnitude equals bundle wind speed.
- Malformed schema, missing row fields, `NaN`, and out-of-range RH.
- NWS null values and precipitation unit conversions.
- Saturated-air wet bulb approximately equals air temperature.
- Solar elevation is negative at a known site/night timestamp.

**Recommended order:** fix pressure units and duplicate definitions first, then timestamp selection and NWS units, then remove silent scientific fallbacks and repair the integrations.