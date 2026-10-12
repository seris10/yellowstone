## Audit summary

These files are mostly well documented, but there are several important correctness issues:

- **Critical:** `microclimate.py` defines `load_real_weather()` twice; the network-fetching implementation is silently overwritten.
- **Critical:** `overland_flow.py` accepts a `soil` argument but never uses it.
- **High:** the weather bundle’s local/UTC hour conversion is incorrect.
- **High:** grid downsampling silently drops data for the default `1025 → 256` conversion.
- **High:** NWS precipitation conversion appears incorrect and the wind-unit assumption needs verification.
- **Medium:** most validators lack type, range, and malformed-input checks.
- **Medium:** pool apron buffering is not guaranteed to be conservative for concave or non-star-shaped outlines.

---

# `microclimate.py`

## 1. Duplicate `load_real_weather()` definition

This is the largest issue.

The first definition fetches Open-Meteo data dynamically:

```python
def load_real_weather(latitude: float = 44.459333,
                      longitude: float = -110.822272,
                      days: int = 7) -> dict | None:
```

Later, the same name is redefined:

```python
def load_real_weather(path: str) -> dict | None:
```

The second definition replaces the first at module load time. Therefore:

```python
load_real_weather(latitude, longitude, days)
```

no longer performs a network fetch; it interprets the latitude as a file path.

### Fix

Give the functions distinct names:

```python
def fetch_real_weather(
    latitude: float = 44.459333,
    longitude: float = -110.822272,
    days: int = 7,
) -> dict | None:
    ...
```

```python
def load_weather_bundle(path: str | Path) -> dict | None:
    ...
```

Prefer explicit dependency injection over modifying `sys.path` inside a library function.

---

## 2. `sys.path` is modified globally and repeatedly

Current code:

```python
sys.path.insert(0, str(tools_dir))
```

Every call can add another entry to `sys.path`, and the modification affects the entire process.

### Better approach

Package `tools` properly and import it normally. If that is not possible, at least avoid duplicate insertion:

```python
tools_path = str(tools_dir)
if tools_path not in sys.path:
    sys.path.insert(0, tools_path)
```

However, this remains less desirable than making the dependency part of the package.

---

## 3. Weather bundle UTC conversion is wrong

Current code:

```python
utc_hour = hour + site_lon / 15.0
```

For a site west of Greenwich, local solar time is approximately:

```text
local = UTC + longitude / 15
```

Therefore:

```text
UTC = local - longitude / 15
```

At longitude `-110.822`, local time is roughly UTC−7.39. To convert local hour to UTC, the code should add approximately 7.39 hours, not subtract it.

### Fix

```python
utc_hour = (float(hour) - site_lon / 15.0) % 24.0
```

Also, using only a longitude offset is not a proper time-zone conversion. For reproducible weather selection, use a timezone-aware timestamp and `zoneinfo`, especially across daylight-saving transitions.

---

## 4. `bundle_weather()` ignores actual row timestamps

The bundle rows contain:

```text
[epoch_s_UTC, air_C, rh_0-1, wind_mps, sw_Wm2, cloud_0-1]
```

But the function chooses a row using only:

```python
idx = int((utc_hour % 24.0) * len(rows) / 24.0) % len(rows)
```

This assumes:

- rows cover exactly one 24-hour period,
- rows are evenly spaced,
- the first row begins at midnight,
- the requested date is irrelevant.

That is unlikely to be correct for a multi-day, seven-day bundle.

### Fix

Select by actual epoch timestamps:

```python
from bisect import bisect_left
from datetime import datetime, timezone

timestamps = [float(row[0]) for row in rows]
target_epoch = target_datetime.timestamp()
idx = min(
    range(len(timestamps)),
    key=lambda i: abs(timestamps[i] - target_epoch),
)
```

Change the API to accept a timestamp rather than only a clock hour:

```python
def bundle_weather(bundle: dict, *, timestamp_utc: datetime, ...) -> dict:
```

---

## 5. Measured absolute air temperature is incompatible with the published `air_temp()` model

The function correctly comments that a measured row is an absolute temperature:

```python
"day_warming_c": 0.0,
```

However, returning:

```python
"night_air_c": measured_air_temperature
```

is misleading because callers may later pass those parameters to:

```python
air_temp(hour, night_air_c, day_warming_c, lag)
```

This happens to avoid double-counting only because warming is zero, but the field name implies a night-time baseline.

### Better design

Represent weather mode explicitly:

```python
{
    "forcing_mode": "absolute_hourly",
    "air_c": float(air),
    "humidity": float(rh),
    "cloud": float(cloud),
    ...
}
```

Then make downstream code choose either:

- synthetic diurnal forcing, or
- measured absolute forcing.

Do not encode two incompatible semantics in the same parameter names.

---

## 6. Wind direction is not preserved when bundling measured wind

Current code:

```python
wx, wz = default_wind
...
"wind_xz_mps": [round(float(wind), 2), round(wz, 2)],
```

The bundle contains only `wind_mps`, which is a scalar magnitude. The implementation puts the measured magnitude into the x component and leaves the z component at the authored default. This creates a vector whose magnitude is not the measured wind speed and whose direction is arbitrary.

### Fix options

If only speed is measured, return a scalar:

```python
"wind_mps": round(float(wind), 2)
```

If a vector is required, document and apply an explicit direction:

```python
direction_rad = math.radians(default_direction_deg)
"wind_xz_mps": [
    round(float(wind) * math.cos(direction_rad), 2),
    round(float(wind) * math.sin(direction_rad), 2),
]
```

Do not represent a measured scalar as a partially measured vector.

---

## 7. `gust_mps` is not derived from the weather bundle

The documentation says:

```text
report gust as the hourly wind spread over the window
```

but the implementation does:

```python
"gust_mps": round(float(default_gust), 2),
```

This is an authored default, not a measured spread.

Either calculate it from hourly/subhourly data or change the provenance note:

```python
"gust_source": "authored default; no gust field in bundle"
```

---

## 8. Condensation calculations are useful as a visual proxy, but not physically dimensional

This line:

```python
evap = max(0.0, es_surf - ea) * (1.0 + wind / 5.0)
```

returns a pressure-difference-like quantity in kPa, not an evaporation flux. The output key says:

```python
"evap_flux_kpa_weighted"
```

That is internally descriptive, but the term “flux” is misleading unless the result is converted using an aerodynamic mass-transfer model.

Likewise:

```python
q_mix = 0.3 * es_surf + 0.7 * ea
```

mixes vapor pressures directly. A physically meaningful humidity mixing calculation should use humidity ratio or specific humidity, accounting for total pressure.

### Recommendation

Rename this as a visualization diagnostic:

```python
"evaporation_pressure_deficit_kpa_weighted"
```

and:

```python
"supersaturation_proxy_kpa"
```

If it is intended for scientific analysis, use:

- saturation vapor pressure,
- vapor pressure,
- mixing ratio or specific humidity,
- total site pressure,
- an explicit mass-transfer coefficient.

---

## 9. Relative humidity handling is inconsistent

`dewpoint_c()` clamps RH to `[0.01, 1.0]`:

```python
rh = min(1.0, max(0.01, float(rh)))
```

`condensation_potential()` clamps RH to `[0.0, 1.0]`:

```python
ea = min(1.0, max(0.0, float(rh))) * es_air
```

Thus RH=0 produces:

- dew point based on RH=0.01,
- vapor pressure based on RH=0.

### Fix

Validate RH once:

```python
def _validate_rh(rh: float) -> float:
    rh = float(rh)
    if not math.isfinite(rh) or not 0.0 <= rh <= 1.0:
        raise ValueError("relative humidity must be finite and in [0, 1]")
    return rh
```

Then make the low-RH dewpoint behavior explicit. If RH=0 is allowed, dew point mathematically tends toward negative infinity; clamp only for numerical purposes and document it.

---

## 10. Time-series functions need argument validation

These functions can fail or behave unexpectedly for invalid inputs:

```python
wind_series(seconds, dt)
trace(seconds, dt)
```

Examples:

- `dt=0` → division by zero.
- `dt<0` → empty or nonsensical output.
- `seconds<0` → inconsistent output.
- `gust_mps<0` → negative noise scale.
- non-finite values → invalid trigonometric calculations.

Add:

```python
def _validate_time_args(seconds: float, dt: float) -> tuple[float, float]:
    seconds = float(seconds)
    dt = float(dt)
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("seconds must be finite and non-negative")
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("dt must be finite and positive")
    return seconds, dt
```

---

## 11. `wind_series()` starts with a random gust at time zero

The function initializes:

```python
gx, gz = 0.0, 0.0
```

but immediately updates them before appending the first value. Consequently, the first sample is already random rather than equal to the prevailing wind.

If the trace is intended to start from the configured baseline:

```python
out = [(float(base_xz[0]), float(base_xz[1]))]
for _ in range(n):
    gx += ...
    ...
    out.append(...)
```

This also makes the output length `n + 1` explicit.

---

## 12. NWS precipitation conversion is likely wrong

Current code:

```python
"precip_mm_h": float(...) * 25.4,
```

NWS observation precipitation values are generally reported in millimeters when the unit code is `wmoUnit:mm`. Multiplying by `25.4` converts millimeters to inches, not to millimeters per hour.

The comment says:

```python
# Precipitation in mm (last hour), converted to mm/h rate.
```

If it is already the last-hour amount in mm, the rate is numerically the same:

```python
precip_mm_h = precip_mm
```

### Fix

Inspect the API’s `unitCode` and convert based on the declared unit:

```python
precip = props.get("precipitationLastHour", {})
value = precip.get("value")
unit = precip.get("unitCode")

if value is None:
    precip_mm_h = None
elif unit == "wmoUnit:mm":
    precip_mm_h = float(value)
else:
    raise ValueError(f"unsupported precipitation unit: {unit}")
```

Do the same for wind rather than relying on comments.

---

## 13. NWS missing values should not become physical values

Current defaults include:

```python
"temperature_c": 999.0
"relative_humidity": 50.0
```

A missing temperature represented as `999.0°C` can silently poison calculations.

Use `None` for missing values or reject the observation:

```python
def _numeric_or_none(value):
    return None if value is None else float(value)
```

Then require callers to handle missing measurements explicitly.

---

## 14. The solar fallback is mislabeled and scientifically weak

The function says:

```python
"""Solar azimuth/elevation using pvlib ... or Magnus approximation fallback."""
```

The fallback is not a Magnus approximation. It is a simple sinusoidal hour-of-day approximation:

```python
elevation = 30.0 + 20.0 * math.sin(...)
azimuth = ...
```

It also ignores:

- date/season,
- latitude,
- longitude except through the timestamp’s hour,
- timezone,
- solar declination,
- equation of time.

Rename it:

```python
"or simple illustrative fallback"
```

and label the returned values as illustrative when `pvlib` is unavailable.

---

# `overland_flow.py`

## 1. The `soil` parameter is ignored

The public API accepts:

```python
soil=DEFAULT_SOIL
```

but then calls:

```python
smap, names = default_soil_map(zc)
```

The requested soil is never applied. The returned metadata can claim:

```python
"soil": soil
```

even though the simulation used the default soil map.

This is a serious reproducibility problem.

### Fix

Either pass the selected soil into the hydrosim API, if supported:

```python
smap, names = default_soil_map(zc, soil=soil)
```

or construct a uniform soil map explicitly:

```python
if soil not in ALLOWED_SOILS:
    raise ValueError(f"unknown soil type: {soil}")

smap = make_uniform_soil_map(zc.shape, soil)
names = [soil]
```

If hydrosim cannot select soil, remove the parameter until it is functional.

---

## 2. `_downsample()` silently drops the final row and column

With the defaults:

```python
src = 1025
dst = 256
step = src // dst  # 4
```

Only `256 * 4 = 1024` source cells are used in each dimension. The final source row and column are discarded.

This is especially problematic because `1025` is likely intended to represent a `1024`-cell grid plus a boundary/sample vertex.

### Fix options

If the source is a vertex grid, explicitly remove the final row and column:

```python
z = z[:GRID - 1, :GRID - 1]
```

and then downsample `1024 → 256`.

If it is a cell grid, use variable-sized blocks or interpolation. Do not silently drop data.

A robust block-mean implementation should calculate source bounds per destination cell:

```python
def block_mean(field, src, dst):
    out = []
    for r in range(dst):
        r0 = r * src // dst
        r1 = (r + 1) * src // dst
        for c in range(dst):
            c0 = c * src // dst
            c1 = (c + 1) * src // dst
            block = field[r0:r1, c0:c1]
            out.append(float(block.mean()))
    return out
```

---

## 3. `_downsample()` does not validate dimensions

Problems include:

- `dst > src` → `step == 0`, resulting in empty blocks and division by zero.
- `src <= 0` or `dst <= 0`.
- non-square source arrays.
- `len(field) != src * src`.

Add validation and use arrays directly:

```python
def _downsample(field, src: int, dst: int):
    if src <= 0 or dst <= 0:
        raise ValueError("src and dst must be positive")
    if field.size != src * src:
        raise ValueError("field size does not match src grid")
```

---

## 4. Returned `seconds` may not equal the actual simulation duration

Current code:

```python
steps = max(1, int(sim_s / dt_s))
for _ in range(steps):
    sim.step(dt_s, rain_mm_h)
...
"seconds": sim_s
```

If `sim_s` is not divisible by `dt_s`, the actual duration is:

```python
steps * dt_s
```

Also, `sim_s=0` still runs one step because of `max(1, ...)`.

### Fix

Either require divisibility:

```python
if sim_s < 0 or dt_s <= 0:
    raise ValueError(...)
if not math.isclose(sim_s / dt_s, round(sim_s / dt_s)):
    raise ValueError("sim_s must be divisible by dt_s")
```

or run a final partial step:

```python
remaining = float(sim_s)
while remaining > 0:
    step = min(dt_s, remaining)
    sim.step(step, rain_mm_h)
    remaining -= step
```

Return the actual elapsed time.

---

## 5. Input values are not validated

Validate:

- `rain_mm_h >= 0`,
- `dt_s > 0`,
- `sim_s >= 0`,
- `grid > 0`,
- `cell_m > 0`,
- soil name allowed,
- all values finite.

Currently negative rainfall, zero cell size, or `grid=0` can produce undefined or misleading results.

---

## 6. `numpy` is an undeclared hard dependency after hydrosim import

The function catches missing `hydrosim`, but then imports NumPy unconditionally:

```python
import numpy as _np
```

If NumPy is absent, the function crashes rather than returning a useful status.

Either declare NumPy as a dependency or handle it consistently:

```python
try:
    import numpy as np
except ImportError:
    return {
        ...,
        "status": "not_available",
        "provenance": "numpy is required",
    }
```

---

## 7. Import fallback mutates global `sys.path`

As with `microclimate.py`, this is fragile:

```python
sys.path.insert(0, d)
```

Prefer package installation or a configured dependency path. At minimum, avoid duplicate insertion and record which implementation was loaded.

---

## 8. `terrain_fns()` is called but its results are unused

```python
_sample, _slope = terrain_fns(z)
```

This incurs work without affecting the model.

Remove it unless it is intended as a validation step. If slope is important to hydrology, use it explicitly and document how.

---

## 9. The output does not record effective model configuration

The result records:

```python
"rain_mm_h": rain_mm_h,
"soil": soil,
"cell_m": cell_m,
```

but not important effective settings such as:

- infiltration method,
- Manning coefficient,
- ET enabled,
- initial wetness,
- `perc_factor`,
- maximum substeps,
- source DEM dimensions,
- downsampling method.

Add a configuration block:

```python
"configuration": {
    "infiltration": "green_ampt",
    "manning_overland": 0.08,
    "enable_et": True,
    "perc_factor": 1.0,
    "init_wetness": 0.5,
    "max_substeps": 40,
    "downsampling": "block_mean",
}
```

---

## 10. Balance values should be validated before serialization

Current output may include NaN or infinite values:

```python
"rel_error": b["rel_error"]
```

Require finite values and report a failed status if the balance is invalid.

---

# `param_registry.py`

## 1. Validation should check types and nonempty values

Current validation only checks field existence and class membership. It accepts:

```python
{"param_id": None, "meaning": [], ...}
```

Add checks for:

- all fields being nonempty strings,
- `param_id` format,
- valid review states,
- uniqueness without crashing on missing IDs.

Example:

```python
REVIEW_STATES = {"not_yet_accepted", "accepted"}

for field in ENTRY_FIELDS:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(
            f"param {entry.get('param_id', '?')}: "
            f"{field} must be a non-empty string"
        )

if entry.get("review") not in REVIEW_STATES:
    errors.append(...)
```

---

## 2. `registry_errors()` can raise `KeyError`

Current code:

```python
ids = [e["param_id"] for e in PARAMS]
```

A malformed entry causes the validator to crash.

Use:

```python
ids = [e.get("param_id") for e in PARAMS if e.get("param_id")]
```

and report missing IDs through `validate_entry()`.

---

## 3. Parameter metadata is not cross-checked against implementation

The registry claims values such as:

```text
authored 0.035 in configs/baseline.yaml
```

but there is no validation that:

- the file exists,
- the setting exists,
- the setting currently equals the claimed value,
- the implementation consumes that setting.

A stronger registry should optionally include structured evidence:

```python
"source_refs": [
    {
        "path": "configs/baseline.yaml",
        "key": "replay.hydraulics.manning_n",
        "expected": 0.035,
    }
]
```

Then a test can detect stale documentation.

---

## 4. Units should be structured where possible

This entry is difficult to parse:

```python
"units": "m3/s, C"
```

for a parameter representing both discharge and temperature.

Prefer separate parameter records:

```python
"hydro.excelsior_discharge_m3s"
"hydro.excelsior_temperature_c"
```

This improves validation, sensitivity analysis, and configuration lookup.

---

## 5. `review` semantics are underspecified

The registry includes `"review": "not_yet_accepted"` but does not define allowed review statuses or acceptance requirements. Align this with the claim registry or centralize the status vocabulary.

---

# `pool_crust.py`

## 1. Radial buffering is not guaranteed to be conservative

The implementation says:

```python
"""Radial buffer ... conservative for these compact thermal outlines."""
```

But radial expansion around the centroid is not a true Minkowski buffer. For concave, asymmetric, or non-star-shaped polygons it can:

- miss portions of the true buffer,
- create self-intersections,
- over-expand some regions,
- produce invalid polygons.

This matters because the result is used for exclusion masks:

```python
exclusion_violations()
render_apron_mask()
```

### Fix

Use Shapely when available:

```python
from shapely.geometry import Polygon

def buffered_ring_exact(ring, margin_m):
    polygon = Polygon(ring)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    return list(polygon.buffer(margin_m).exterior.coords)
```

If Shapely is unavailable, label the fallback clearly:

```python
"buffer_method": "radial_approximation_not_guaranteed"
```

Do not call it conservative unless tested for that specific geometry.

---

## 2. `render_apron_tiles()` does not fill the apron

Current code:

```python
dr.polygon([px(x, z) for x, z in s["ring"]], fill=200)
...
dr.polygon([px(x, z) for x, z in buf], outline=255, width=2)
```

It fills the mapped water ring but only outlines the buffered ring. The output does not show the apron as a filled mask.

### Fix

```python
dr.polygon([px(x, z) for x, z in buf], fill=255)
dr.polygon([px(x, z) for x, z in s["ring"]], fill=200)
```

If the intent is to distinguish water, rim, and apron, draw them in separate layers or colors.

---

## 3. Geometry inputs are insufficiently validated

Potential failures include:

- `ring` with fewer than three points,
- malformed point coordinates,
- duplicate points,
- zero or negative `area_m2`,
- center not containing three values,
- invalid or self-intersecting polygons,
- `shelf_mult <= 1`,
- negative recipe dimensions.

Add validation before building shells:

```python
def validate_ring(ring):
    if len(ring) < 3:
        raise ValueError("pool ring requires at least three points")
    for point in ring:
        if len(point) < 2:
            raise ValueError("ring point must contain x and z")
        if not all(math.isfinite(float(v)) for v in point[:2]):
            raise ValueError("ring coordinates must be finite")
```

---

## 4. `depth_at()` can divide by zero

Current code:

```python
if r <= r_water * shelf_mult:
    f = (r - r_water) / (r_water * (shelf_mult - 1.0))
```

If `shelf_mult == 1`, this divides by zero. Negative or less-than-one values are also invalid.

Validate:

```python
if r_water <= 0:
    raise ValueError("r_water must be positive")
if shelf_mult <= 1:
    raise ValueError("shelf_mult must be greater than 1")
```

Also validate depth values are nonnegative.

---

## 5. `radial_temp()` does not implement the documented “beyond edge relaxes toward edge”

The function uses:

```python
f = max(0.0, 1.0 - (r / r_water) ** 2)
```

For `r > r_water`, `f=0`, so the result is exactly `t_edge`. It does not “relax toward edge”; it jumps to edge and stays there.

Either change the docstring:

```python
"""Quadratic falloff to t_edge at and beyond the water edge."""
```

or implement a separate apron relaxation profile.

Also validate:

```python
if r_water <= 0:
    raise ValueError(...)
```

---

## 6. `make_ramp_stops()` mutates its input

This line modifies the shell:

```python
shell["ramp_params"] = ...
```

That creates hidden side effects. Calling the function can change serialized output or affect later rendering.

### Fix

Return parameters separately or copy:

```python
result = {
    "stops": stops,
    "ramp_params": {
        "depth_f": round(depth_f, 3),
        "gradient_f": round(grad_f, 3),
    },
}
```

Alternatively:

```python
shell = dict(shell)
```

but a pure function is preferable.

---

## 7. Ramp stop fractions should be validated and clamped

The gradient adjustment can change a stop fraction. Future recipe changes could produce:

- fractions below zero,
- fractions above `1.3`,
- duplicate or unsorted positions.

Use:

```python
fraction = min(1.3, max(0.0, adjusted_fraction))
```

and validate monotonicity before rendering.

---

## 8. Pool area and mapped geometry can conflict without being reported

`r_water_from_area()` derives a circular-equivalent radius from `area_m2`, while `in_water()` uses the mapped polygon:

```python
if shell.get("ring"):
    return point_in_ring(...)
```

Thus:

- shell radii and cross-sections are based on `area_m2`,
- actual water inclusion is based on `ring`.

If those disagree substantially, the shell’s dimensions are internally inconsistent.

The existing `outline_circularity` is useful, but add a diagnostic comparing mapped polygon area and declared area. If Shapely is unavailable, implement a shoelace area calculation.

---

## 9. `render_ramp()` can fail for `w=1`

Current code:

```python
f = ix / (w - 1)
```

With `w=1`, this divides by zero. Validate:

```python
if w < 2:
    raise ValueError("ramp width must be at least 2")
```

Also ensure the parent directory exists before saving.

---

## 10. The hard-coded outflow ID should be data-driven

Current code:

```python
"outflow_channel": (
    "authored_excelsior_outflow_01"
    if pool.get("id") == "pool_1030_0" else None
),
```

This makes a general pool builder depend on one specific ID.

Prefer source data:

```python
"outflow_channel": pool.get("outflow_channel")
```

or a registry keyed by stable `source_id`, with validation that the referenced pool exists.

---

## 11. `render_cross_section()` displays a conceptual section, not the mapped outline

That is acceptable given the module documentation, but the output should make clear that:

- the section is radial,
- it is based on circular-equivalent radii,
- it does not represent the actual polygon outline,
- depth is illustrative.

The title communicates some of this, but including an explicit metadata block alongside the image would reduce misuse.

---

# Recommended implementation order

1. Rename the duplicate weather loaders.
2. Fix `bundle_weather()` timestamp and UTC/local handling.
3. Fix or remove the ignored `soil` parameter.
4. Replace the lossy `1025 → 256` downsampling.
5. Correct NWS unit handling and missing-value behavior.
6. Add argument validation to weather, hydrology, and pool functions.
7. Replace or clearly label radial polygon buffering.
8. Fill the apron in `render_apron_tiles()`.
9. Make registries strict and non-crashing.
10. Add cross-file provenance/configuration tests.

The highest-value regression tests are:

```python
def test_weather_loader_names_are_distinct():
    assert callable(fetch_real_weather)
    assert callable(load_weather_bundle)
```

```python
def test_soil_parameter_changes_effective_configuration():
    result = run_overland(..., soil="sandy_loam")
    assert result["configuration"]["soil"] == "sandy_loam"
```

```python
def test_downsample_uses_all_source_cells():
    source = np.arange(1025 * 1025).reshape(1025, 1025)
    result = downsample(source, 256)
    assert result.shape == (256, 256)
```

```python
def test_bundle_weather_uses_actual_timestamp():
    # Verify a known UTC row is selected for a known local timestamp.
    ...
```

```python
def test_apron_tile_is_filled():
    # Verify pixels between the mapped outline and buffered outline are nonzero.
    ...
```