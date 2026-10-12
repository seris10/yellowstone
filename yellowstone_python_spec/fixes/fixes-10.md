## Audit summary

These are substantially stronger than the earlier versions, especially around validation, provenance, atomic output, and conservation reporting. The main issues are:

1. **Critical:** explicit surface-budget forcing changes are not included in the solver’s forcing-change schedule.
2. **Critical:** explicit-budget energy accounting uses the nonlinear flux at the new temperature while the solver uses a linearized flux, so budget residuals can be nonzero even when the numerical solve is correct.
3. **High:** `river_from_config()` does not support the existing `cell_heat_w` feature.
4. **High:** `physical_weather()` and `energy_met_series()` do not reliably produce forcing samples covering the requested duration.
5. **High:** mapped source temperatures are forced to scalar values even though `river_transport.Source` supports scheduled temperatures.
6. **Medium:** geometry/configuration validation is incomplete and some functions can fail with raw `KeyError` or `AttributeError`.
7. **Medium:** hydraulic diagnostics and solver geometry are deliberately different, but the output should make that distinction more explicit.

---

# `river_transport.py`

## 1. Critical: surface-budget forcing changes are not scheduled

`River._forcing` currently contains:

```python
self._forcing = (
    self.boundary_c,
    self.air_c,
    self.net_heat_flux,
    *(s.temperature_c for s in self.sources),
    *(s for s in self._cell_heat if s is not None),
)
```

It does **not** include:

```python
self.surface_budget.rh
self.surface_budget.wind_mps
self.surface_budget.shortwave_w_m2
self.surface_budget.cloud
```

Therefore `run()` and `step()` can integrate across a surface-budget discontinuity without splitting the interval.

This is especially important because `river_world.py` creates weather series with 60-second changes, while the solver may use a 2-second time step and longer sample intervals.

### Fix

```python
forcing = [
    self.boundary_c,
    self.air_c,
    self.net_heat_flux,
    *(source.temperature_c for source in self.sources),
    *(series for series in self._cell_heat if series is not None),
]

if self.surface_budget is not None:
    forcing.extend([
        self.surface_budget.rh,
        self.surface_budget.wind_mps,
        self.surface_budget.shortwave_w_m2,
        self.surface_budget.cloud,
    ])

self._forcing = tuple(forcing)
```

Add a regression test:

```python
def test_surface_budget_change_splits_run():
    river = River(
        cells=(Cell(
            id="c0",
            length_m=10.0,
            width_m=2.0,
            volume_m3=20.0,
            initial_c=10.0,
        ),),
        boundary_m3_s=1.0,
        boundary_c=10.0,
        surface_budget={
            "rh": 0.5,
            "wind_mps": {
                "times_s": [0.0, 5.0],
                "values": [1.0, 4.0],
            },
            "shortwave_w_m2": 0.0,
            "cloud": 0.5,
        },
    )

    frames = river.run(duration_s=10.0, dt_s=10.0, sample_s=10.0)

    assert river.steps == 2
    assert river.time_s == 10.0
```

Without the fix, the solver can take one 10-second step across the change.

---

## 2. Critical: explicit-budget closure is internally inconsistent

The solver state is calculated using a linearized flux:

```python
flux0, slope = linearized(
    self._temperature_c[i], met,
    self.surface_budget.params)

exchange = -slope * area / self.rho_cp
surface_rhs = (
    (flux0 - slope * self._temperature_c[i])
    * area / self.rho_cp
)
```

But accounting uses the nonlinear flux evaluated at the new temperature:

```python
fluxes = [flux_at(temperature, met_now,
                  self.surface_budget.params)
          for temperature in new]
```

The resulting state solves one equation, while the reported energy budget evaluates another. Therefore:

```python
heat_residual_j
```

can be nonzero even when the numerical method is behaving correctly.

The comment says:

```python
# Accounting uses the flux at the NEW temperature, so closure
# measures actual energy change, not the linearized estimate.
```

That is scientifically defensible as a diagnostic, but it is incompatible with this acceptance check:

```python
budget["heat_relative_residual"] <= 1e-9
```

### Choose one of these designs

### Option A: report solver closure

Use the same linearized flux in both the state update and the budget accounting. This should produce near-machine-precision closure.

### Option B: report physical nonlinear residual

Keep the current accounting, but loosen the tolerance and label it clearly:

```python
"heat_residual_kind": "nonlinear_flux_vs_linearized_state_update"
```

This residual is then a discretization/nonlinearity diagnostic, not a pure conservation check.

### Option C: iterate the implicit nonlinear solve

For a genuinely implicit nonlinear budget:

1. Guess `T_new`.
2. Evaluate flux and derivative at that guess.
3. Solve the linearized system.
4. Repeat until temperatures converge.
5. Account using the converged flux.

That is the most physically consistent approach but more computationally expensive.

---

## 3. `_system()` and `_advance_to()` should share the same surface-power calculation

The duplicated surface-flux logic is risky:

- `_system()` computes a linearized forcing.
- `_advance_to()` computes a separate accounting forcing.
- Newton exchange and explicit budget have separate branches.

A future change can easily update one path but not the other.

Create helpers such as:

```python
def _linearized_surface_terms(
    self,
    cell_index: int,
    time_s: float,
    dt_s: float,
) -> tuple[float, float]:
    """Return matrix coefficient and RHS heat term."""
```

and:

```python
def _surface_power_at(
    self,
    temperatures: list[float],
    time_s: float,
) -> tuple[list[float], dict[str, list[float]] | None]:
    """Return physical surface powers and component breakdown."""
```

This makes the numerical equation and budget semantics easier to audit.

---

## 4. `cell_heat_w` is implemented by `River` but unusable through config

`River.__init__()` supports:

```python
cell_heat_w: dict[str, Any] | None = None
```

But `river_from_config()` does not allow or pass it:

```python
allowed = {
    "cells", "sources", "boundary_m3_s", "boundary_c",
    "air_c", "net_heat_flux_w_m2", "rho_cp_j_m3_k",
    "surface_budget",
    ...
}
```

A config containing `cell_heat_w` is rejected as an unknown key.

### Fix

Add it to the allowed keys and kwargs:

```python
allowed = {
    "cells", "sources", "boundary_m3_s", "boundary_c",
    "air_c", "net_heat_flux_w_m2", "rho_cp_j_m3_k",
    "surface_budget", "cell_heat_w",
    ...
}
```

```python
"cell_heat_w": config.get("cell_heat_w"),
```

Also include it in replay provenance:

```python
"cell_heat_w": {
    cell_id: asdict(series)
    for cell_id, series in river._cell_heat_by_id.items()
}
```

Avoid exposing the private `_cell_heat` list directly if possible; retain the original mapping as a public or serialization-friendly structure.

---

## 5. `explicit_budget` is determined from config presence instead of effective state

In `make_replay()`:

```python
explicit_budget = "surface_budget" in config
```

A config containing:

```json
{
  "surface_budget": null
}
```

will be labeled:

```python
"surface_flux": "explicit_budget"
```

even though `River.surface_budget` is `None`.

### Fix

Build the river first and inspect it:

```python
explicit_budget = river.surface_budget is not None
```

This also makes the replay metadata reflect actual behavior rather than input syntax.

---

## 6. The solver documentation overstates downstream discharge behavior

The module docstring says:

```text
prescribed downstream discharge
```

But the implementation derives face flows from:

```python
q = [self.boundary_m3_s]
for lateral_q in self._lateral_q:
    q.append(q[-1] + lateral_q)
```

The downstream flow is therefore:

```text
boundary flow + all lateral flows
```

It is not independently prescribed.

### Fix the documentation

```text
prescribed upstream discharge; downstream discharge is derived from
upstream and lateral inflows
```

If an independently prescribed downstream flow is needed, add an explicit boundary condition and validate water balance.

---

## 7. `Source.temperature_c` supports schedules, but replay serialization is not normalized

`Source.__post_init__()` converts:

```python
temperature_c
```

to a `Series`.

Then:

```python
"source": [asdict(source) for source in river.sources]
```

serializes the dataclass as:

```python
{
    "temperature_c": {
        "times_s": (...),
        "values": (...)
    }
}
```

Tuples are JSON-serializable through `json.dumps`, but the output format is inconsistent with other explicit list-based series such as:

```python
"boundary_c": asdict(river.boundary_c)
```

which also contains tuples.

### Recommendation

Normalize all serialized series:

```python
def series_dict(series: Series) -> dict[str, list[float]]:
    return {
        "times_s": list(series.times_s),
        "values": list(series.values),
    }
```

Use it consistently for boundary, air, heat flux, source temperatures, and cell heat.

---

## 8. `Series.at()` accepts times before the series origin

The class requires the first time to be zero, so this is normally fine:

```python
bisect_right(self.times_s, time_s) - 1
```

However, `at(-1)` clamps only through `finite(..., 0.0)`, which rejects it. Good. Add tests for exact transition behavior:

```python
def test_series_is_right_continuous():
    series = Series((0.0, 10.0), (1.0, 2.0))

    assert series.at(9.999) == 1.0
    assert series.at(10.0) == 2.0
```

---

## 9. Matrix coefficient checks should validate physical signs

`Cell` allows:

```python
dispersion_m2_s >= 0
exchange_w_m2_k >= 0
```

which is reasonable. But `Source.flow_m3_s` and `boundary_m3_s` also allow zero and no upper bound, which may be intended.

The solver should nevertheless check that generated matrix coefficients are finite and physically valid before solving:

```python
if diagonal[i] <= 0.0:
    raise ArithmeticError(...)
```

The tridiagonal solver does this for pivots, but reporting the offending cell’s physical inputs would make failures easier to diagnose.

---

## 10. Stability diagnostics are not stability criteria

The replay reports:

```python
"max_advective_courant"
"max_diffusive_number"
```

but does not use them to warn or fail. Backward Euler is stable for many conditions, but large values can produce severe numerical smearing.

Add warning thresholds:

```python
numerical_warnings = []

if budget["max_advective_courant"] > 1.0:
    numerical_warnings.append(
        "advective Courant number exceeds 1; fronts may be strongly smeared"
    )
```

Do not call the result “numerically acceptable” solely because the budget closes.

---

# `river_world.py`

## 1. Critical interaction: explicit weather changes are not honored by `river_transport`

As noted above, `energy_met_series()` creates changing series, but `River._forcing` omits those series.

This means a mapped energy-budget replay may use the initial meteorological values over a whole solver interval or sample period instead of splitting at every weather change.

Fixing `river_transport.py` is essential for `river_world.py` to behave as documented.

---

## 2. `physical_weather()` does not guarantee a row at the requested final time

Current code:

```python
times = [
    index * interval_s
    for index in range(int(duration_s // interval_s) + 1)
]
```

For `duration_s=125` and `interval_s=60`, this produces:

```python
[0, 60, 120]
```

The forcing remains valid after 120 seconds because the final value is held indefinitely, but the actual final time is not represented.

For clearer provenance and exact endpoint behavior, include the final duration:

```python
times = list(range(0, int(duration_s), int(interval_s)))
if not times or times[-1] != duration_s:
    times.append(duration_s)
```

Use floating-point-safe generation for noninteger intervals:

```python
times = []
time_s = 0.0

while time_s < duration_s:
    times.append(time_s)
    time_s += interval_s

if not times or not math.isclose(times[-1], duration_s):
    times.append(duration_s)
else:
    times[-1] = duration_s
```

---

## 3. Validate `interval_s`

`physical_weather()` does not validate:

```python
interval_s
```

A zero or negative interval can cause division or range errors.

Add:

```python
duration_s = finite(duration_s, "weather duration", 0.0)
interval_s = positive(interval_s, "weather interval")
```

Likewise validate `duration_s` before using it in `energy_met_series()`.

---

## 4. Weather forcing is duplicated instead of using the microclimate authority

The module docstring says:

```text
Use the existing weather approximation
```

but `river_world.py` reimplements:

```python
sun = max(0.0, math.sin((hour - 6.0) * math.pi / 12.0))
air = night + warming * sun
```

This duplicates logic from `microclimate.py`.

That creates a risk that the ecosystem and river replay use different weather semantics.

### Fix

Use a shared function:

```python
from .microclimate import air_temp, wind_at
```

For a physical-clock series:

```python
air = air_temp(hour, night, warming)
wind = wind_at(time_s, (wx, wz), gust)
```

Or create a shared forcing builder that returns air, wind, humidity, cloud, and shortwave consistently.

---

## 5. Weather data fields are read from inconsistent locations

`physical_weather()` reads:

```python
weather = ecosystem.get("weather", {})
```

and:

```python
weather.get("wind_xz_mps", ...)
```

But the final document stores:

```python
"humidity": ecosystem.get("humidity", 0.45),
"cloud": ecosystem.get("cloud", 0.16),
```

The energy-budget path reads humidity and cloud from `ecosystem["weather"]`, while the top-level output reads them from the root ecosystem object.

This can produce metadata that does not describe the actual forcing.

### Fix

Use one canonical location:

```python
weather = ecosystem.get("weather", {})
humidity = weather.get("humidity", 0.45)
cloud = weather.get("cloud", 0.16)
```

Then serialize those exact effective values from the generated budget or weather records.

---

## 6. `energy_met_series()` can create invalid zero-length or incomplete series

It relies on `weather_records` being nonempty:

```python
times = [record["t_s"] for record in weather_records]
```

Usually it is nonempty, but validate it:

```python
if not weather_records:
    raise ValueError("weather_records must not be empty")
```

Also validate that times are strictly increasing and begin at zero before constructing `Series`.

---

## 7. Mapped source temperatures do not support scheduled forcing

The generic solver accepts:

```python
Source.temperature_c: Any
```

and supports a `Series`, but the mapped builder does:

```python
temperature = finite(source["temperature_c"], "entry temperature")
```

This rejects a scheduled ecosystem source temperature.

### Fix

Use `Series.parse()`:

```python
temperature = Series.parse(
    source["temperature_c"]
)
```

For the pulse, either:

- reject scheduled temperatures explicitly, or
- compose the pulse with an existing schedule.

For a scalar source:

```python
base_series = Series.parse(source["temperature_c"])
```

Then create a pulse-adjusted schedule only if the base series is constant or define the intended composition clearly.

---

## 8. Pulse semantics need clearer naming

The documentation says:

```text
The pulse changes temperature at the river-entry boundary.
```

But the implementation applies it to:

```python
source["temperature_c"]
```

for the selected lateral source. That is not the upstream boundary condition.

### Fix the wording

```text
The pulse changes the selected lateral source temperature at its mapped
river-entry cell. It does not alter the upstream boundary forcing.
```

Alternatively, implement a separate boundary pulse option.

---

## 9. Pulse values are not checked for physically plausible temperature

This is allowed:

```python
temperature + pulse_delta_c
```

with no upper or lower bound. That may be intentional for synthetic scenarios, but add provenance and optional limits:

```python
pulse_temperature = temperature + pulse_delta_c
if pulse_temperature > 100.0:
    raise ValueError("pulse temperature exceeds configured physical limit")
```

At minimum, check it is finite.

---

## 10. Cross-section optional fields are preserved without validation

`parse_cross_sections()` preserves:

```python
"real_measurement_site"
"dem_cross_check_depth_m"
```

but does not check types or values.

For example, this is accepted:

```json
{
  "depth_m": 1.1,
  "status": "measured",
  "real_measurement_site": "yes",
  "dem_cross_check_depth_m": -50
}
```

Add validation:

```python
if "real_measurement_site" in record:
    if not isinstance(record["real_measurement_site"], bool):
        raise ValueError("real_measurement_site must be boolean")

if "dem_cross_check_depth_m" in record:
    positive(
        record["dem_cross_check_depth_m"],
        f"{feature_id} dem_cross_check_depth_m",
    )
```

---

## 11. `parse_cross_sections()` can raise `AttributeError` for non-string keys

Current code:

```python
for feature_id, record in value.items():
    if feature_id.startswith("_"):
```

If called with a Python dictionary containing a non-string key, it fails before producing a useful validation error.

### Fix

```python
for feature_id, record in value.items():
    if not isinstance(feature_id, str) or not feature_id:
        raise ValueError("cross-section feature ids must be nonempty strings")
    if feature_id.startswith("_"):
        continue
```

---

## 12. Unknown reach anchors are not explicitly rejected

This code:

```python
anchor = reach_anchors.get(reach["id"])
```

ignores anchors for nonexistent ecosystem reaches. It also gives raw `KeyError` for an unknown `river_id`:

```python
feature = channel.features[anchor["river_id"]]
```

Validate the anchor schema and reject unused anchors:

```python
known_reach_ids = {reach["id"] for reach in ecosystem["river_reaches"]}
unknown_anchor_ids = set(reach_anchors) - known_reach_ids
if unknown_anchor_ids:
    raise ValueError(
        f"anchors reference unknown reaches: {sorted(unknown_anchor_ids)}"
    )
```

Also validate:

- `river_id` is a string,
- `vertex_index` is an integer but not `bool`,
- required fields are present.

---

## 13. `source_connection()` assumes unvalidated source and outlet schemas

These accesses can raise raw errors:

```python
source["id"]
source["flow_m3s"]
source["temperature_c"]
outlet["target_river_id"]
outlet["target_vertex_index"]
outlet["points"]
```

Add explicit schema validation before building connections, especially because this adapter is the boundary between two JSON documents.

---

## 14. Source-flow consistency should be reported

The adapter deliberately says:

```python
"ecosystem values define river-entry forcing; "
"world outlet defines connection geometry only"
```

That is a valid authority decision. However, if both records include flow and temperature, the output should report discrepancies:

```python
"flow_comparison": {
    "ecosystem_m3_s": source["flow_m3s"],
    "world_m3_s": outlet.get("flow_m3_s"),
    "difference_m3_s": ...
}
```

Do not silently discard potentially important conflicts.

---

## 15. Hydraulic diagnostic fields need stronger status labeling

The solver uses rectangular volumes:

```python
volume_m3 = length * width * depth
```

while hydraulic diagnostics use trapezoidal geometry. That is clearly documented in notes, but each hydraulic record should repeat the distinction:

```python
"volume_authority": "solver_rectangular_volume",
"hydraulics_authority": "diagnostic_trapezoidal_geometry",
```

Otherwise consumers may assume hydraulic cross-sectional area was used by the thermal solver.

---

## 16. `feature_at()` depends on dictionary insertion order

This code:

```python
self._feature_ends = [
    record["end_s_m"] for record in self.features.values()
]
```

works because `firehole_chain()` returns ordered features and dictionaries preserve insertion order. However, the correctness is implicit.

Make it explicit:

```python
self._feature_records = sorted(
    self.features.values(),
    key=lambda record: record["start_s_m"],
)
self._feature_ends = [
    record["end_s_m"] for record in self._feature_records
]
```

This avoids future breakage if `self.features` is constructed differently.

---

## 17. `feature_at()` needs chainage validation

Current code accepts arbitrary values:

```python
def feature_at(self, s_m: float) -> dict:
```

A negative chainage can be mapped to the first feature, and a chainage beyond the channel can map to the last feature.

### Fix

```python
s_m = finite(s_m, "chainage", 0.0)
if s_m > self.length_m:
    raise ValueError("chainage outside channel")
```

---

## 18. `Channel` does not validate feature IDs or width consistency

It validates width positivity, but not:

- feature ID type/nonempty,
- duplicate feature IDs,
- missing `points`,
- missing endpoint metadata before earlier functions use it.

Add explicit checks in `Channel.__init__()` or a separate world-schema validator.

---

## 19. Atomic output handling should clean up temporary files

The pattern:

```python
temporary.write_text(...)
temporary.replace(args.out)
```

is good, but if writing fails, `.tmp` remains. Use a `try/finally` cleanup or a reusable atomic-write helper.

Also consider opening with an explicit encoding, which is already done for input but not here:

```python
temporary.write_text(text, encoding="utf-8")
```

---

## Recommended priority order

1. Add surface-budget series to `River._forcing`.
2. Resolve the explicit-budget residual/accounting mismatch.
3. Add `cell_heat_w` to configuration parsing and replay serialization.
4. Fix `explicit_budget` detection to use `river.surface_budget`.
5. Support scheduled source temperatures in `river_world.py`.
6. Unify weather generation with `microclimate.py`.
7. Normalize weather field locations and output effective values.
8. Validate cross-section, anchor, source, and outlet schemas.
9. Clarify lateral-pulse semantics.
10. Add diagnostic metadata distinguishing solver geometry from hydraulic geometry.

The most important regression tests should cover:

```python
def test_surface_budget_changes_split_integration():
    ...
```

```python
def test_explicit_budget_residual_semantics_are_documented():
    ...
```

```python
def test_cell_heat_w_round_trips_through_config():
    ...
```

```python
def test_scheduled_lateral_temperature_is_preserved():
    ...
```

```python
def test_weather_metadata_matches_effective_forcing():
    ...
```

```python
def test_unknown_reach_anchor_is_rejected():
    ...
```