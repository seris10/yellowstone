## Overall assessment

These three fetchers are relevant and form a sensible acquisition layer:

```text
fetch_firehole_obs.py
    USGS upstream/downstream discharge and water temperature
    Open-Meteo meteorological forcing
        ↓
    calibrate.py

fetch_met_forcing.py
    shared meteorological bundle builder
        ↓
    fetch_firehole_obs.py
    river_world.py
    surface_flux.py

fetch_snotel_obs.py
    snow and soil-water observations
        ↓
    snow calibration/validation
```

The architecture is good, but the scripts need a stronger normalization and quality layer before their output is used for calibration. The most important issues are:

1. **Timestamp timezone bugs.**
2. **Open-Meteo row-builder assumptions are not enforced.**
3. **USGS series selection and quality handling are incomplete.**
4. **The Firehole bundle mixes observations and model forcing without enough metadata.**
5. **SNOTEL raw values are preserved correctly, but dates, units, and missingness need stronger validation.**
6. **No shared observation schema or artifact hash is used consistently.**

---

# 1. `fetch_firehole_obs.py`

## Good aspects

This script makes several sound choices:

- USGS discharge is converted from cfs to m³/s.
- Upstream and downstream station roles are explicit.
- Open-Meteo is labeled as forcing rather than observation.
- Output is atomically replaced.
- The bundle is versioned:

```python
"schema": "yellowstone.firehole_obs.v1"
```

- The distinction between upstream boundary data and downstream calibration target is documented.

Those choices align well with `calibrate.py`.

## Problem: timestamp parsing is unsafe

Current code:

```python
def _parse_iso_epoch(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()
```

If the timestamp is naive, Python interprets it in the machine’s local timezone. That can shift observations by several hours.

### Fix

```python
def _parse_iso_epoch(text: str) -> float:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("timestamp must be a nonempty string")

    normalized = text.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            f"timestamp lacks timezone information: {text!r}"
        )

    return parsed.astimezone(timezone.utc).timestamp()
```

This matters because `calibrate.py` aligns USGS and meteorological data by epoch time.

---

## Problem: USGS series selection is implicit

Current code loops over all series and overwrites:

```python
if "00060" in codes:
    out["discharge_m3_s"] = ...
elif "00010" in codes:
    out["temperature_c"] = pairs
```

A response may contain multiple series for the same parameter, such as different methods or statistics. The final one silently wins.

### Improve

Select and record the chosen series:

```python
def _series_codes(series: dict) -> set[str]:
    return {
        str(code.get("value"))
        for code in series.get("variable", {}).get(
            "variableCode", []
        )
        if isinstance(code, dict) and code.get("value") is not None
    }
```

Then:

```python
selected = {}

for series in data.get("value", {}).get("timeSeries", []):
    codes = _series_codes(series)

    if "00060" in codes and "discharge" not in selected:
        selected["discharge"] = series

    if "00010" in codes and "temperature" not in selected:
        selected["temperature"] = series
```

If multiple candidates exist, preserve the count and metadata:

```python
"series_selection": {
    "discharge_candidates": 2,
    "temperature_candidates": 1,
    "selection_policy": "first_matching_parameter_series",
}
```

For serious calibration, selection should also consider method and statistic metadata.

---

## Problem: invalid numeric rows are silently discarded without quality reporting

Current behavior:

```python
except (ValueError, KeyError):
    continue
```

This is safe operationally but weak scientifically. You do not know whether 2 rows or 20% of the data were discarded.

Return ingestion statistics:

```python
{
    "rows_seen": 1000,
    "rows_retained": 994,
    "rows_rejected": 6,
    "rejection_reasons": {
        "missing_timestamp": 1,
        "missing_value": 2,
        "invalid_timestamp": 1,
        "invalid_numeric_value": 2
    }
}
```

The calibration pipeline should be able to reject a bundle with poor coverage.

---

## Problem: duplicate and non-monotonic timestamps are not rejected

You sort pairs:

```python
pairs.sort()
```

but do not detect duplicates.

Add:

```python
def validate_pairs(
    pairs: list[list[float]],
    label: str,
) -> None:
    times = [float(pair[0]) for pair in pairs]

    if any(
        later <= earlier
        for earlier, later in zip(times, times[1:])
    ):
        raise ValueError(
            f"{label} timestamps must be strictly increasing"
        )
```

Use after sorting and deduplication.

If duplicate timestamps occur, retain the original rows in a quality artifact rather than silently selecting one.

---

## Problem: qualifiers are discarded

`fetch_firehole_obs.py` does not preserve USGS qualifiers, unlike `usgs_nwis.py`.

That loses information about:

- provisional values;
- estimated discharge;
- sensor problems;
- ice conditions;
- quality flags.

Change the output to retain records such as:

```python
{
    "epoch_unix": epoch,
    "value": value,
    "qualifiers": row.get("qualifiers", [])
}
```

You can still provide the calibration-friendly pair view:

```python
"temperature_c": [[epoch, value], ...]
```

but preserve a richer raw or quality view alongside it.

---

## Problem: Open-Meteo forcing is labeled correctly in prose but not structurally

The bundle contains:

```python
"met": met
```

and a prose note:

```python
"forcing for the surface budget, not an observation..."
```

Make this machine-readable:

```python
"met": {
    **met,
    "role": "forcing",
    "measurement_status": "model_analysis_or_forecast",
    "observation_status": "not_observation",
}
```

Similarly:

```python
"sites": {
    site: {
        ...
        "role": "boundary" or "calibration_target",
        "measurement_status": "observed_remote",
    }
}
```

This prevents a later consumer from treating Open-Meteo air temperature as measured local meteorology.

---

## Problem: all meteorology is fetched only at the upstream gauge

This is acceptable for an initial effective-reach calibration, but it should be explicit:

```python
"met": {
    "location_role": "upstream_boundary_proxy",
    "latitude": ...,
    "longitude": ...,
    "distance_to_downstream_target_m": ...,
}
```

A downstream reach-scale model may need meteorology along the reach or at least a correction for elevation and exposure. Current calibration should call this:

```text
single-location meteorological forcing
```

not reach-wide observed meteorology.

---

# 2. `fetch_met_forcing.py`

## Good aspects

The shared module is the right direction:

```python
fetch_firehole_obs.fetch_met
    → fetch_met_forcing.fetch_met
```

The frozen six-column row format is also compatible with `calibrate.py`:

```python
[epoch_s_UTC, air_C, rh_0-1, wind_mps, sw_Wm2, cloud_0-1]
```

The explicit schema note is valuable.

## Critical bug: `build_met_rows()` accepts arbitrary variables but assumes exactly five

Current code:

```python
cols = [hourly.get(var, []) for var in variables]
...
air, rh_pct, wind_kmh, sw, cloud = (
    float(cols[j][i]) for j in range(5)
)
```

If the caller passes a tuple with more or fewer than five variables, the code either:

- ignores extra variables;
- raises unpacking/index errors;
- maps columns incorrectly.

The CLI attempts to enforce this, but the public function does not.

### Fix

For schema v1:

```python
EXPECTED_MET_VARS = (
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "shortwave_radiation",
    "cloud_cover",
)

if tuple(variables) != EXPECTED_MET_VARS:
    raise ValueError(
        "schema v1 requires the canonical five variables "
        "in the documented order"
    )
```

Then use named variables rather than positional assumptions:

```python
air_values = hourly.get("temperature_2m", [])
rh_values = hourly.get("relative_humidity_2m", [])
wind_values = hourly.get("wind_speed_10m", [])
sw_values = hourly.get("shortwave_radiation", [])
cloud_values = hourly.get("cloud_cover", [])
```

---

## Critical bug: timezone handling can overwrite an existing offset

Current code:

```python
datetime.fromisoformat(
    stamp.replace("Z", "+00:00")
).replace(tzinfo=timezone.utc).timestamp()
```

If the timestamp already contains an offset, `.replace(tzinfo=timezone.utc)` overwrites it instead of converting it.

### Fix

```python
def _parse_iso_epoch(stamp: str) -> float:
    normalized = stamp.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            f"Open-Meteo timestamp lacks timezone: {stamp!r}"
        )

    return parsed.astimezone(timezone.utc).timestamp()
```

Use this in `build_met_rows()`.

---

## Problem: null Open-Meteo values become exceptions

Current code:

```python
air, rh_pct, wind_kmh, sw, cloud = (
    float(cols[j][i]) for j in range(5)
)
```

If any value is `None`, `"null"`, or missing, the entire fetch fails.

That may be preferable to silently fabricating data, but it should produce a clear error with the row and variable name.

```python
def _finite_float(value, name: str, index: int) -> float:
    if value is None:
        raise RuntimeError(
            f"Open-Meteo null {name} at hourly row {index}"
        )

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Open-Meteo invalid {name} at hourly row {index}"
        ) from exc

    if not math.isfinite(result):
        raise RuntimeError(
            f"Open-Meteo nonfinite {name} at hourly row {index}"
        )

    return result
```

Whether to reject the whole bundle or preserve gaps as null should be an explicit policy. For calibration, preserving gaps and letting `check_continuity()` reject them is often better than hiding them.

---

## Problem: input coordinates and days are not validated

`fetch_met_forcing()` accepts:

```python
latitude
longitude
days
```

without checking ranges.

Add:

```python
def _validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    latitude = float(latitude)
    longitude = float(longitude)

    if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
        raise ValueError("latitude must be in [-90, 90]")

    if not math.isfinite(longitude) or not -180.0 <= longitude <= 180.0:
        raise ValueError("longitude must be in [-180, 180]")

    return latitude, longitude
```

Also validate:

```python
if isinstance(days, bool) or not isinstance(days, int):
    raise ValueError("days must be an integer")
if not 1 <= days <= 16:
    raise ValueError("days must be in [1, 16]")
```

---

## Problem: conversions assume provider units without verifying response metadata

The comments say:

```python
rh_pct/100
wind_kmh/3.6
cloud_pct/100
```

This is valid for the requested Open-Meteo variables, but the output should preserve the provider units and requested variables:

```python
"units": {
    "temperature_2m": "degC",
    "relative_humidity_2m": "%",
    "wind_speed_10m": "km/h",
    "shortwave_radiation": "W/m2",
    "cloud_cover": "%",
},
"normalized_units": {
    "air_c": "degC",
    "rh": "fraction",
    "wind_mps": "m/s",
    "shortwave_w_m2": "W/m2",
    "cloud": "fraction",
}
```

Also include:

```python
"provider_timezone": data.get("timezone"),
"utc_offset_seconds": data.get("utc_offset_seconds"),
```

Since you request `timezone=UTC`, verify that the response actually reports UTC.

---

## Problem: API model/run provenance is not pinned

The script correctly admits:

```python
"model-unpinned"
```

That is important. For reproducible calibration, try to capture:

- API request URL;
- response metadata;
- model name, if returned;
- generation time;
- forecast/analysis classification;
- elevation;
- coordinates.

If Open-Meteo does not guarantee a stable historical model archive for your use, consider storing the complete response or a hash.

---

## Problem: re-export assignment is confusing

In `fetch_firehole_obs.py`:

```python
from tools.fetch_met_forcing import MET_VARS, OPEN_METEO
...
MET_VARS = MET_VARS
```

This is legal but confusing and fragile.

Use:

```python
from tools import fetch_met_forcing as met_forcing
```

Then:

```python
OPEN_METEO = met_forcing.OPEN_METEO
MET_VARS = met_forcing.MET_VARS
```

Or do not re-export these names at all.

---

# 3. `fetch_snotel_obs.py`

## Good aspects

This is the strongest of the three in terms of provenance discipline:

- raw values are preserved;
- units are retained;
- missing values remain null;
- PRCP semantics are explicitly flagged;
- the window is recorded;
- output is atomically replaced;
- site roles are documented.

That is the right approach for scientific observation bundles.

## Problem: input dates are parsed but original strings are used

Current code:

```python
begin = date.fromisoformat(args.begin)
end = date.fromisoformat(args.end)
...
result = fetch_site_daily(triplet, args.begin, args.end)
```

The parsed `begin` and `end` are not used to normalize the values. Use canonical ISO strings:

```python
begin_text = begin.isoformat()
end_text = end.isoformat()
```

Then pass those:

```python
result = fetch_site_daily(
    triplet,
    begin_text,
    end_text,
)
```

This ensures the URL and bundle use normalized dates.

---

## Problem: no date validation inside `fetch_site_daily()`

The public function can be called directly with invalid dates.

Add:

```python
def validate_date_window(begin: str, end: str) -> tuple[str, str]:
    begin_date = date.fromisoformat(begin)
    end_date = date.fromisoformat(end)

    if end_date < begin_date:
        raise ValueError("end precedes begin")

    if (end_date - begin_date).days > 400:
        raise ValueError("window exceeds 400 days")

    return begin_date.isoformat(), end_date.isoformat()
```

Call from both `main()` and `fetch_site_daily()`.

---

## Problem: dates are not validated as actual dates

The API response is trusted:

```python
day = row.get("date")
if not day:
    continue
```

Validate:

```python
try:
    normalized_day = date.fromisoformat(day).isoformat()
except (TypeError, ValueError):
    continue
```

This prevents malformed dates from entering the bundle.

---

## Problem: numeric values are not validated

Current code stores:

```python
days.setdefault(day, {})[code] = row.get("value")
```

AWDB may return:

- `None`;
- strings;
- sentinel values;
- nonfinite numbers;
- negative values where impossible.

Create an element-aware parser:

```python
def parse_awdb_value(
    element: str,
    value: object,
) -> float | None:
    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(result):
        return None

    if element in {"WTEQ", "PRCP", "SNWD"} and result < 0.0:
        return None

    return result
```

Then:

```python
days.setdefault(day, {})[code] = parse_awdb_value(
    code,
    row.get("value"),
)
```

Keep a rejected-value count.

---

## Problem: unit metadata can be incomplete

You use:

```python
units[code] = el.get("storedUnitCode", "unknown")
```

Good, but this should be validated before consumers convert values.

Add a required-unit map:

```python
EXPECTED_UNITS = {
    "WTEQ": {"in"},
    "PRCP": {"in"},
    "SNWD": {"in"},
    "TAVG": {"degF"},
    "TMAX": {"degF"},
    "TMIN": {"degF"},
}
```

Do not necessarily reject unfamiliar codes, but mark:

```python
"unit_validation": "unexpected"
```

instead of silently assuming inches or Fahrenheit.

---

## Problem: missing date rows are not represented

The bundle includes only dates returned by AWDB:

```python
days[day]
```

If an entire day is absent, it disappears rather than appearing as:

```json
{
  "WTEQ": null,
  "PRCP": null,
  ...
}
```

For coverage analysis, generate the complete requested date range:

```python
current = begin_date
while current <= end_date:
    days.setdefault(
        current.isoformat(),
        {code: None for code in ELEMENTS},
    )
    current += timedelta(days=1)
```

This makes missing days distinguishable from a station simply not returning the date.

---

## Problem: PRCP interpretation is correctly flagged but not enforced

The bundle says:

```text
PRCP is a daily accumulation increment
```

That is important. The consuming snow model must not assume it is a cumulative snow depth.

Add machine-readable metadata:

```python
"semantics": {
    "WTEQ": "snow_water_equivalent_state",
    "PRCP": "daily_precipitation_accumulation",
    "SNWD": "snow_depth_state",
    "TAVG": "daily_mean_air_temperature",
}
```

Before calibration, verify the `PRCP` API semantics and document the verification source. Do not use `PRCP` in a water balance without this check.

---

# 4. Cross-script compatibility

## `fetch_firehole_obs.py` → `calibrate.py`

This is mostly compatible:

```python
sites[site]["series"]["temperature_c"]
sites[site]["series"]["discharge_m3_s"]
met["hourly"]
```

But fix:

- timezone parsing;
- duplicate timestamps;
- missing-value handling;
- quality metadata;
- Open-Meteo provenance.

`calibrate.py` then uses:

```python
t0 = max(
    up["temperature_c"][0][0],
    met_rows[0][0],
)
```

That assumes each series is sorted and nonempty. The fetcher should guarantee this or the assembler should validate it.

## `fetch_met_forcing.py` → `river_world.py`

The six-column rows are compatible with:

```python
r[0] epoch
r[1] air
r[2] RH
r[3] wind
r[4] shortwave
r[5] cloud
```

But this positional contract is fragile. Add a schema-level column declaration:

```python
"columns": [
    "epoch_s_UTC",
    "air_C",
    "rh_0_1",
    "wind_mps",
    "sw_Wm2",
    "cloud_0_1",
]
```

Then consumers can validate the row width and names.

## `fetch_snotel_obs.py` → `snow_season.py`

The SNOTEL fetcher intentionally stores raw units, which is appropriate. The consumer must explicitly convert:

```python
WTEQ_mm = WTEQ_in * 25.4
TAVG_C = (TAVG_F - 32.0) * 5.0 / 9.0
```

Do not hide these conversions in generic code. Include a conversion record in the fitted artifact.

---

# 5. Strongly recommended shared utilities

Create a module such as:

```text
yellowstone_python/observation_io.py
```

with shared functions:

```python
parse_utc_timestamp()
validate_epoch_pairs()
validate_date_window()
atomic_write_json()
canonical_json_hash()
quality_summary()
```

This avoids the current duplication and inconsistency across:

- `usgs_nwis.py`;
- `fetch_firehole_obs.py`;
- `fetch_met_forcing.py`;
- `fetch_snotel_obs.py`;
- `fetch_yellowstone_tributaries.py`.

---

# 6. Recommended artifact status model

Current statuses are useful but could be more precise.

For the Firehole bundle:

```json
{
  "status": "measured_boundary_and_target_with_model_forcing",
  "components": {
    "usgs": {
      "kind": "observation",
      "status": "provisional_remote"
    },
    "open_meteo": {
      "kind": "model_forcing",
      "status": "unvalidated_for_local_flux"
    }
  }
}
```

For SNOTEL:

```json
{
  "status": "measured_remote_raw_units",
  "components": {
    "WTEQ": "observation",
    "PRCP": "observation",
    "TAVG": "observation"
  }
}
```

This is better than labeling an entire mixed bundle simply:

```python
"measured_remote_not_calibrated"
```

---

# 7. Suggested minimum patches

## Shared timestamp parser

Use in all fetchers:

```python
def parse_utc_epoch(text: str) -> float:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("timestamp must be a nonempty string")

    normalized = text.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            f"timestamp lacks timezone: {text!r}"
        )

    return parsed.astimezone(timezone.utc).timestamp()
```

## Atomic JSON writer

```python
def atomic_write_json(path: Path, document: dict) -> None:
    text = json.dumps(
        document,
        indent=1,
        allow_nan=False,
    ) + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
```

## Shared continuity validation

```python
def validate_time_value_pairs(
    pairs: list[list[float]],
    label: str,
) -> None:
    if not pairs:
        raise ValueError(f"{label} is empty")

    previous = None

    for index, pair in enumerate(pairs):
        if len(pair) != 2:
            raise ValueError(
                f"{label}[{index}] must be [epoch, value]"
            )

        epoch = float(pair[0])
        value = float(pair[1])

        if not math.isfinite(epoch):
            raise ValueError(
                f"{label}[{index}] has nonfinite time"
            )

        if not math.isfinite(value):
            raise ValueError(
                f"{label}[{index}] has nonfinite value"
            )

        if previous is not None and epoch <= previous:
            raise ValueError(
                f"{label} timestamps must be strictly increasing"
            )

        previous = epoch
```

---

# Final assessment

These fetchers are directionally correct and fit the project’s provenance-oriented design, but they are still **acquisition scripts rather than fully reliable observation products**.

The correct data flow should be:

```text
USGS / Open-Meteo / AWDB fetchers
        ↓
raw immutable artifacts
        ↓
validated normalized observation bundles
        ↓
calibration and model-specific adapters
        ↓
river, snow, hydrology, and atmosphere models
```

The highest-priority fixes are:

1. Correct all timezone-aware timestamp conversions.
2. Add explicit normalized schemas and column/unit metadata.
3. Preserve or summarize rejected rows and quality qualifiers.
4. Validate ordering, duplicates, gaps, and coverage.
5. Keep Open-Meteo clearly separated as model forcing, not observation.
6. Normalize USGS discharge to m³/s consistently.
7. Preserve SNOTEL missing dates and raw units.
8. Add artifact hashes and shared atomic-writing utilities.
9. Assemble calibration bundles in a separate step rather than making fetchers serve every consumer directly.