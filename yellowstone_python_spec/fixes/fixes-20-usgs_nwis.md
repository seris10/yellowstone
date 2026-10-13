## Assessment

`usgs_nwis.py` is relevant and useful as a **raw USGS acquisition layer**, but it is not currently wired cleanly to the other scripts.

Current data flow is fragmented:

```text
usgs_nwis.py
    ├── measurements
    ├── discharge_iv
    └── temperature_iv

fetch_yellowstone_tributaries.py
    expects:
    └── series.temperature_c / series.discharge_m3_s

channel_geometry.py
    expects:
    └── measurements[].area_sqft / width_ft

calibrate.py
    expects:
    └── yellowstone.firehole_obs.v1 bundle:
        sites[site].series[...]

river_world.py
    expects:
    └── ecosystem/world configuration, not this raw artifact directly
```

The biggest issue is not the HTTP fetching itself. It is the absence of a **single normalized observation schema** between acquisition and modeling.

---

# High-priority issues

## 1. Output schema is incompatible with consumers

This script writes:

```json
{
  "measurements": [],
  "discharge_iv": [],
  "temperature_iv": []
}
```

But `fetch_yellowstone_tributaries.py` expects:

```python
usgs_data["series"]["temperature_c"]
usgs_data["series"]["discharge_m3_s"]
```

And `calibrate.py` expects a larger bundle:

```python
bundle["sites"]["06036805"]["series"]["temperature_c"]
bundle["met"]["hourly"]
```

Therefore, `usgs_nwis.py` output cannot be passed directly into either script.

### Recommended solution

Keep this file as the raw acquisition artifact, then add a normalization function or module:

```python
def normalize_site_result(raw: dict) -> dict:
    ...
```

Output:

```json
{
  "schema": "yellowstone.usgs_site_observations.v1",
  "site_id": "06036805",
  "site": {},
  "retrieved_at_utc": "...",
  "series": {
    "temperature_c": [
      [1770000000.0, 12.4]
    ],
    "discharge_m3_s": [
      [1770000000.0, 2.8]
    ]
  },
  "measurements": [],
  "quality": {},
  "provenance": {}
}
```

Then create a separate bundle assembler for calibration:

```text
usgs_nwis.py
    → normalized site artifact
        ↓
assemble_firehole_obs.py
    → yellowstone.firehole_obs.v1
```

Do not make every consumer understand a different raw USGS format.

---

## 2. `_safe_float()` allows invalid values into output

Current code:

```python
def _safe_float(val: str) -> float | None:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
```

Then `_fetch_iv()` appends:

```python
{
    "datetime": ...,
    "value": None,
}
```

That creates malformed observations which later code may fail on or silently mishandle.

### Better behavior

Skip invalid values during ingestion and count them:

```python
def _parse_float(value: Any, field: str) -> float | None:
    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(result):
        return None

    return result
```

In `_fetch_iv()`:

```python
value = _parse_float(v.get("value"), "value")
timestamp = parse_usgs_timestamp(v.get("dateTime"))

if value is None or timestamp is None:
    continue

results.append({
    "epoch_unix": timestamp,
    "datetime_utc": datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    ).isoformat().replace("+00:00", "Z"),
    "value": value,
    "qualifiers": list(v.get("qualifiers", [])),
})
```

Return ingestion counters:

```json
{
  "quality": {
    "rows_received": 1000,
    "rows_retained": 998,
    "rows_rejected": 2
  }
}
```

---

## 3. Timestamp handling is incomplete

The script currently preserves USGS timestamps as strings:

```python
"datetime": v.get("dateTime", "")
```

Other scripts use epoch timestamps, for example:

```python
[t, value]
```

You need one canonical internal representation. Use UTC epoch seconds for computation and retain the original string for provenance.

Add:

```python
from datetime import datetime, timezone
```

Then:

```python
def parse_usgs_timestamp(value: str) -> float:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("USGS timestamp must be a nonempty string")

    text = value.strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = datetime.fromisoformat(text)

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            "USGS timestamp must include a timezone"
        )

    return parsed.astimezone(timezone.utc).timestamp()
```

This avoids the common bug of attaching UTC to an already offset-aware datetime instead of converting it.

---

## 4. `datetime.utcnow()` is naive

Current code:

```python
datetime.utcnow().isoformat() + "Z"
```

Use:

```python
retrieved_at = datetime.now(timezone.utc).isoformat()
```

or normalized:

```python
retrieved_at = (
    datetime.now(timezone.utc)
    .isoformat()
    .replace("+00:00", "Z")
)
```

---

## 5. The RDB parser is fragile

This logic:

```python
if col_line.split("\t")[0].strip() in ("5s", "15s", "20s"):
```

assumes a particular RDB units-line format. It may silently treat a units row as a data row if the format differs.

Improve parsing by:

- checking the response content type;
- recognizing the column header explicitly;
- validating required columns;
- rejecting rows whose date cannot be parsed;
- recording malformed-row counts.

Also, `_fetch_rdb()` should verify that the response is actually tabular RDB data rather than HTML:

```python
if "<html" in raw[:1000].lower():
    raise RuntimeError(
        "NWIS returned HTML instead of RDB data"
    )
```

Do not rely solely on status code.

---

# USGS parameter code issue

You define:

```python
PARAM_DISCHARGE = "000060"   # Actually 00060
```

This constant is wrong and unused, while the actual calls use:

```python
_fetch_iv(site_no, "00060", period_days)
```

Fix it:

```python
PARAM_DISCHARGE = "00060"
```

Then use constants consistently:

```python
result["discharge_iv"] = _fetch_iv(
    site_no,
    PARAM_DISCHARGE,
    period_days,
)
```

Likewise:

```python
result["temperature_iv"] = _fetch_iv(
    site_no,
    PARAM_TEMP,
    period_days,
)
```

The six-digit spelling could eventually cause a bug if someone uses the constant rather than the hardcoded literal.

---

# `period_days` needs validation

The CLI accepts arbitrary values:

```python
parser.add_argument("--period-days", type=int, default=30)
```

But no range is enforced.

Add:

```python
def validate_period_days(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("period-days must be an integer")
    if not 1 <= value <= 366:
        raise ValueError(
            "period-days must be between 1 and 366"
        )
    return value
```

Use it in both `main()` and `fetch_all()`.

If the service has a shorter practical limit, use that limit explicitly.

---

# Important: field measurements and IV observations are different datasets

This script correctly separates:

```python
measurements
discharge_iv
temperature_iv
```

That distinction should remain.

## Field measurements

These are irregular survey observations and may contain:

- width;
- cross-sectional area;
- velocity;
- discharge;
- measurement date;
- channel geometry.

They are relevant to:

```text
channel_geometry.py
```

## Instantaneous values

These are time-series data and are relevant to:

```text
fetch_yellowstone_tributaries.py
calibrate.py
```

Do not combine them into one generic `series` object without preserving the source type and units.

---

# Problem with `channel_geometry.py` integration

`channel_geometry.py` expects:

```python
m.get("area_sqft")
m.get("width_ft")
```

That is compatible with the intended `_fetch_rdb()` conversion:

```python
row["area_sqft"]
row["width_ft"]
```

However, the RDB endpoint currently often returns no measurements according to the docstring. Therefore:

```python
channel_geometry.py
```

will fall back to DEM-derived transects.

That is fine, provided the output states:

```text
USGS field measurements unavailable; geometry is DEM-derived
```

Do not mark the resulting profile as field-measured.

Also, `channel_geometry.py` currently applies one USGS result to every Firehole feature. Even if this fetcher returns valid field measurements, that remains scientifically inappropriate unless the measurements are explicitly mapped to a feature or used as a regional prior.

---

# Problem with `fetch_yellowstone_tributaries.py` integration

That script expects a structure like:

```python
{
    "site_id": "...",
    "series": {
        "temperature_c": [[epoch, value]],
        "discharge_m3_s": [[epoch, value]]
    }
}
```

Normalize the raw result with:

```python
def normalized_series(raw: dict) -> dict:
    temperature = []
    for row in raw.get("temperature_iv", []):
        if row.get("epoch_unix") is not None:
            temperature.append([
                row["epoch_unix"],
                row["value"],
            ])

    discharge = []
    for row in raw.get("discharge_iv", []):
        if row.get("epoch_unix") is not None:
            # USGS discharge IV values are cfs.
            discharge.append([
                row["epoch_unix"],
                row["value"] * 0.028316846592,
            ])

    return {
        "temperature_c": temperature,
        "discharge_m3_s": discharge,
    }
```

But do this in a named adapter, not by changing the raw acquisition shape invisibly.

---

# Unit metadata is missing

The raw output should record units and parameter codes:

```json
{
  "parameter": "00060",
  "name": "discharge",
  "source_units": "ft3/s",
  "output_units": "m3/s",
  "conversion": 0.028316846592
}
```

Currently, `discharge_iv` values remain in cfs, while other parts of the project use `m3/s`. That is a major wiring hazard.

At minimum, include:

```python
"units": {
    "discharge_iv": "ft3/s",
    "temperature_iv": "degC",
    "measurements.width_ft": "ft",
    "measurements.area_sqft": "ft2",
    "measurements.velocity_fps": "ft/s",
}
```

Prefer converting discharge at ingestion and retaining the source value:

```json
{
  "value": 80.0,
  "value_m3_s": 2.265,
  "source_units": "cfs",
  "normalized_units": "m3/s"
}
```

---

# `_fetch_iv()` only uses the first time series

Current code:

```python
series = data.get("value", {}).get("timeSeries", [])
...
values = series[0].get("values", [{}])[0].get("value", [])
```

A response may contain multiple time series for:

- different statistics;
- different sensors;
- multiple methods;
- qualifiers;
- duplicate parameter variants.

Select by parameter code and method explicitly:

```python
def _select_time_series(
    time_series: list[dict],
    parameter_cd: str,
) -> dict | None:
    candidates = []

    for series in time_series:
        variable = series.get("variable", {})
        codes = {
            item.get("value")
            for item in variable.get("variableCode", [])
            if isinstance(item, dict)
        }

        if parameter_cd in codes:
            candidates.append(series)

    if not candidates:
        return None

    if len(candidates) > 1:
        # Record this rather than silently choosing one.
        ...
```

At minimum, preserve selection metadata:

```python
"series_selection": {
    "parameter_cd": parameter_cd,
    "candidate_count": len(candidates),
    "selected_index": 0
}
```

---

# Qualifiers should affect quality status

The script preserves:

```python
"qualifiers": v.get("qualifiers", [])
```

but no consumer uses them.

Qualifiers may indicate:

- provisional values;
- estimated values;
- ice effects;
- sensor problems;
- partial records.

Do not discard them. Add a quality classification:

```python
def classify_qualifiers(qualifiers: list[str]) -> str:
    if not qualifiers:
        return "unqualified"

    lowered = {str(q).lower() for q in qualifiers}

    if "e" in lowered:
        return "estimated"

    if "p" in lowered:
        return "provisional"

    return "qualified_with_flags"
```

Then use quality filters in calibration:

```python
if row["quality_status"] == "estimated":
    ...
```

At minimum, summarize:

```json
{
  "quality": {
    "qualifier_counts": {
      "P": 300,
      "A": 2
    }
  }
}
```

---

# Add continuity and coverage diagnostics

For each series, calculate:

```python
def series_quality(rows: list[dict]) -> dict:
    times = [
        row["epoch_unix"]
        for row in rows
    ]

    if len(times) < 2:
        return {
            "n": len(times),
            "coverage_fraction": None,
            "max_gap_s": None,
            "nominal_interval_s": None,
        }

    intervals = [
        later - earlier
        for earlier, later in zip(times, times[1:])
    ]

    return {
        "n": len(times),
        "start_epoch_unix": times[0],
        "end_epoch_unix": times[-1],
        "nominal_interval_s": sorted(intervals)[len(intervals) // 2],
        "max_gap_s": max(intervals),
        "duplicate_timestamps": any(
            interval <= 0
            for interval in intervals
        ),
    }
```

This directly supports `calibrate.py`, whose `check_continuity()` currently rejects large gaps.

---

# Atomic output writing

Current code writes directly:

```python
out_path.write_text(...)
```

A partial process termination can leave invalid JSON.

Use the project’s existing atomic pattern:

```python
text = json.dumps(
    result,
    indent=2,
    allow_nan=False,
) + "\n"

tmp = out_path.with_name(
    out_path.name + ".tmp"
)

tmp.write_text(
    text,
    encoding="utf-8",
)

tmp.replace(out_path)
```

Also include a content hash:

```python
result["artifact_sha256"] = hashlib.sha256(
    text.encode("utf-8")
).hexdigest()
```

If the hash is included inside the document, calculate it over the canonical payload before adding the hash itself.

---

# The comments about October 2026 are problematic

The module says:

```text
Oct 2026
```

That is a future-dated operational claim unless this project is explicitly being maintained after that date. It should not be hardcoded as a factual API history without a source or test.

Replace with something more durable:

```text
The legacy measurements endpoint may return HTML or a JavaScript page
rather than machine-readable RDB. Treat an empty or non-tabular response
as unavailable and rely on the Water Services endpoint for IV data.
```

If an endpoint behavior matters, test it or record the observed retrieval date in metadata.

---

# Site metadata should be separated from observations

This is useful:

```python
SITES = {
    "06036805": {
        "name": ...,
        "drainage_area_sqmi": ...,
        "latitude": ...,
        ...
    }
}
```

But consumers should know whether values are:

- official station metadata;
- manually entered;
- retrieved from an API;
- approximate.

Add:

```python
"site_metadata_provenance": {
    "source": "authored_station_registry",
    "retrieved_at_utc": None,
    "status": "requires_verification"
}
```

For a scientific artifact, retrieve station metadata from NWIS where possible and preserve the API response or hash.

---

# Recommended normalized output

A better `fetch_all()` result would look like:

```json
{
  "schema": "yellowstone.usgs_site_observations.v1",
  "site_id": "06036805",
  "site": {
    "name": "Firehole River at Old Faithful, YNP",
    "latitude_deg": 44.459333,
    "longitude_deg": -110.822272,
    "drainage_area_sqmi": 39.5
  },
  "retrieved_at_utc": "2026-07-15T22:20:00Z",
  "measurements": {
    "records": [],
    "units": {
      "width": "ft",
      "area": "ft2",
      "velocity": "ft/s",
      "discharge": "ft3/s"
    },
    "quality": {}
  },
  "series": {
    "temperature_c": [
      {
        "epoch_unix": 1784154000.0,
        "value": 17.3,
        "source_value": 17.3,
        "units": "degC",
        "qualifiers": [],
        "quality_status": "unqualified"
      }
    ],
    "discharge_m3_s": [
      {
        "epoch_unix": 1784154000.0,
        "value": 2.27,
        "source_value": 80.0,
        "source_units": "ft3/s",
        "qualifiers": [],
        "quality_status": "unqualified"
      }
    ]
  },
  "quality": {
    "temperature": {},
    "discharge": {},
    "status": "usable_for_screening"
  },
  "provenance": {
    "agency": "USGS",
    "source_url": "...",
    "parameter_codes": ["00010", "00060"]
  }
}
```

This is more verbose than the current output but prevents unit and schema mistakes.

---

# How it should connect to the rest of the project

```text
usgs_nwis.py
    raw/normalized site observations
        ↓
observation assembly / normalization
        ↓
yellowstone.firehole_obs.v1
        ↓
calibrate.py
        ↓
fitted effective parameters
        ↓
river_transport.py / river_world.py
```

For geometry:

```text
usgs_nwis.py measurements
    ↓
channel_geometry.py
    ↓
cross_sections.json
    ↓
river_world.py
```

For tributaries:

```text
usgs_nwis.py normalized site observations
    ↓
verified stream/confluence association
    ↓
fetch_yellowstone_tributaries.py analysis
    ↓
tributary evidence artifact
    ↓
solver source OR landscape pocket
```

Do not directly feed raw `usgs_nwis.py` JSON into `run_hot_lowflow_with_tributaries_v2.py`.

---

# Priority fixes

1. Add timezone-aware epoch timestamps.
2. Reject or skip `None` values.
3. Normalize discharge from cfs to m³/s.
4. Produce a schema compatible with tributary consumers.
5. Add continuity, duplicate, qualifier, and coverage diagnostics.
6. Select and document the correct NWIS time series.
7. Write output atomically.
8. Fix the discharge parameter constant.
9. Validate `period_days`.
10. Separate raw acquisition from calibration-bundle assembly.
11. Do not apply one site’s field geometry to every channel feature.
12. Add explicit provenance for station metadata and endpoint behavior.

The script is a good foundation for data acquisition, but it should remain an **evidence-ingestion tool**, not also serve as the calibration bundle builder, geometry mapper, or tributary refuge generator.