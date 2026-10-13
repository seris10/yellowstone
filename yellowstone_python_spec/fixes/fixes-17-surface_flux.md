`surface_flux.py` is the physics layer beneath both:

```text
calibrate.py
    → build_fit_river()
        → River(surface_budget=...)
            → surface_flux.flux_at()
            → surface_flux.linearized()
            → damped Newton iteration
```

It defines the surface heat flux that calibration is trying to fit. `calibrate.py` currently fits only a common multiplier over `c_h` and `c_e`; it does not independently calibrate the other parameters in `BudgetParams`.

## Main issues

### 1. The module docstring is now outdated

It currently says:

```text
The solver linearizes F(T_water) analytically around the old temperature
...
Use linearized() for the matrix and flux_at() with the NEW temperature
for budget accounting, so closure measures the actual energy change.
```

After damped Newton, the solver should linearize around the **current Newton iterate**, and final accounting should use `flux_at()` at the converged temperature.

Update it to:

```python
"""Explicit surface energy budget for the 1-D river-temperature solver.

All returned fluxes are W/m2 and positive into the water:

    shortwave = (1 - albedo) * SW_down
    longwave  = LW_down - emissivity * sigma * T_water_K**4
    sensible  = rho_air * cp_air * C_H * U * (T_air - T_water)
    latent    = rho_air * L_v * C_E * U * (q_air - q_sat(T_water))

For an active surface budget, River uses ``linearized()`` during each
damped-Newton iteration and evaluates ``flux_at()`` at the converged
temperature for final accounting.

The defaults are illustrative and must not be treated as calibrated
surface-flux parameters.
"""
```

---

# 1. Fix numerical-domain validation

## Problem

`es_kpa()` accepts any finite temperature:

```python
def es_kpa(t_c: float) -> float:
    return 0.61094 * math.exp(
        17.625 * t_c / (t_c + 243.04)
    )
```

Near `-243.04°C`, this becomes singular. More realistically, extremely cold or hot values can produce invalid or meaningless vapor pressures.

Also, `_specific_humidity()` can produce a zero or negative denominator:

```python
return 0.622 * es / (pressure_kpa - 0.378 * es)
```

## Fix

Define explicit supported temperature limits:

```python
MIN_THERMODYNAMIC_C = -80.0
MAX_THERMODYNAMIC_C = 80.0
```

Add:

```python
def _temperature_c(value: Any, name: str) -> float:
    result = float(value)

    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")

    if not MIN_THERMODYNAMIC_C <= result <= MAX_THERMODYNAMIC_C:
        raise ValueError(
            f"{name} must be in "
            f"[{MIN_THERMODYNAMIC_C}, {MAX_THERMODYNAMIC_C}] C"
        )

    return result
```

Replace `es_kpa()` with:

```python
def es_kpa(t_c: float) -> float:
    """Saturation vapor pressure, Magnus form, in kPa.

    Validated here for the temperature range used by this model. The
    Magnus approximation should not be extrapolated arbitrarily.
    """
    t_c = _temperature_c(t_c, "temperature")

    denominator = t_c + 243.04
    if denominator <= 1.0:
        raise ValueError(
            "temperature is outside the valid Magnus domain"
        )

    result = 0.61094 * math.exp(
        17.625 * t_c / denominator
    )

    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(
            "saturation vapor pressure is nonfinite or nonpositive"
        )

    return result
```

Harden humidity calculations:

```python
def _specific_humidity(
    vapor_pressure_kpa: float,
    pressure_kpa: float,
) -> float:
    denominator = pressure_kpa - 0.378 * vapor_pressure_kpa

    if denominator <= 0.0:
        raise ValueError(
            "vapor pressure is incompatible with total pressure"
        )

    result = 0.622 * vapor_pressure_kpa / denominator

    if not math.isfinite(result) or result < 0.0:
        raise ValueError("specific humidity is invalid")

    return result
```

The current parameter name `es` is misleading because this function is used with both ambient vapor pressure and saturation vapor pressure. Rename it to `vapor_pressure_kpa`.

---

# 2. Validate the physical pressure range

`BudgetParams` checks only:

```python
pressure > 0
```

That permits physically nonsensical values such as `0.001 kPa` or `10,000 kPa`.

Add:

```python
MIN_PRESSURE_KPA = 40.0
MAX_PRESSURE_KPA = 110.0
```

Then:

```python
pressure = float(self.pressure_kpa)

if not math.isfinite(pressure):
    raise ValueError("pressure_kpa must be finite")

if not MIN_PRESSURE_KPA <= pressure <= MAX_PRESSURE_KPA:
    raise ValueError(
        f"pressure_kpa must be in "
        f"[{MIN_PRESSURE_KPA}, {MAX_PRESSURE_KPA}]"
    )

object.__setattr__(
    self,
    "pressure_kpa",
    pressure,
)
```

For Yellowstone, the approximate pressure is reasonable, but it should be derived from the configured elevation rather than independently hard-coded in two modules.

---

# 3. Unify site pressure with `microclimate.py`

Currently:

```python
# surface_flux.py
SITE_PRESSURE_KPA = 77.8
```

while `microclimate.py` calculates pressure from:

```python
SITE_ELEVATION_M = 2215.0
SITE_PRESSURE_KPA = ...
```

These can drift apart.

Create a shared module:

```python
# atmospheric_constants.py
from __future__ import annotations

import math

SITE_ELEVATION_M = 2215.0

SITE_PRESSURE_KPA = (
    101.325
    * (1.0 - 2.25577e-5 * SITE_ELEVATION_M) ** 5.25588
)
```

Then import it in both modules:

```python
from .atmospheric_constants import (
    SITE_ELEVATION_M,
    SITE_PRESSURE_KPA,
)
```

This ensures that:

- dewpoint;
- vapor pressure;
- air density;
- surface radiation;
- wet-bulb calculations

use the same atmospheric pressure.

---

# 4. Do not silently alter wind forcing

Current `MetState` changes the input:

```python
object.__setattr__(
    self,
    "wind_mps",
    max(wind, WIND_FLOOR_MPS),
)
```

Thus an input wind of `0.0 m/s` becomes `0.5 m/s` without preserving that fact in the output. This affects calibration: the model cannot distinguish calm observations from the imposed transfer floor.

## Better design

Keep the observed wind unchanged and apply the floor only in the transfer calculation.

Replace:

```python
object.__setattr__(
    self,
    "wind_mps",
    max(wind, WIND_FLOOR_MPS),
)
```

with:

```python
object.__setattr__(
    self,
    "wind_mps",
    wind,
)
```

Add:

```python
def _transfer_wind_mps(wind_mps: float) -> float:
    return max(float(wind_mps), WIND_FLOOR_MPS)
```

Then in `flux_at()`:

```python
transfer_wind = _transfer_wind_mps(met.wind_mps)
```

Use `transfer_wind` in sensible and latent flux:

```python
sensible = (
    rho
    * CP_AIR_J_KG_K
    * params.c_h
    * transfer_wind
    * (met.air_c - t_c)
)

latent = (
    rho
    * L_VAPOR_J_KG
    * params.c_e
    * transfer_wind
    * (q_air - q_sat)
)
```

Do the same in `linearized()`.

Add the effective wind to diagnostics if useful:

```python
"transfer_wind_mps": transfer_wind
```

The distinction becomes:

```text
wind_mps
    measured/forcing wind

transfer_wind_mps
    wind used by the bulk-transfer parameterization
```

---

# 5. Make shortwave and longwave assumptions explicit parameters

Currently:

```python
shortwave = (1.0 - params.albedo) * met.shortwave_w_m2
```

and:

```python
return eps_clear * (1.0 + 0.22 * cloud ** 2) * sigma * T**4
```

This makes calibration difficult because radiation corrections are hard-coded.

Add parameters:

```python
@dataclass(frozen=True)
class BudgetParams:
    albedo: float = 0.08
    emissivity: float = 0.97
    c_h: float = 1.5e-3
    c_e: float = 1.5e-3
    pressure_kpa: float = SITE_PRESSURE_KPA

    shortwave_multiplier: float = 1.0
    longwave_multiplier: float = 1.0
    longwave_offset_w_m2: float = 0.0
    cloud_longwave_factor: float = 0.22
```

Validate:

```python
for name in (
    "shortwave_multiplier",
    "longwave_multiplier",
):
    value = float(getattr(self, name))
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be >= 0")
    object.__setattr__(self, name, value)

offset = float(self.longwave_offset_w_m2)
if not math.isfinite(offset):
    raise ValueError(
        "longwave_offset_w_m2 must be finite"
    )
object.__setattr__(
    self,
    "longwave_offset_w_m2",
    offset,
)

cloud_factor = float(self.cloud_longwave_factor)
if not math.isfinite(cloud_factor) or cloud_factor < 0.0:
    raise ValueError(
        "cloud_longwave_factor must be >= 0"
    )
object.__setattr__(
    self,
    "cloud_longwave_factor",
    cloud_factor,
)
```

Update `_lw_in_w_m2()`:

```python
def _lw_in_w_m2(
    air_c: float,
    rh: float,
    cloud: float,
    *,
    cloud_factor: float = 0.22,
) -> float:
    """Estimate downwelling longwave radiation in W/m2."""
    t_c = _temperature_c(air_c, "air temperature")
    rh = float(rh)
    cloud = float(cloud)

    if not 0.0 <= rh <= 1.0:
        raise ValueError("rh must be in [0, 1]")
    if not 0.0 <= cloud <= 1.0:
        raise ValueError("cloud must be in [0, 1]")

    t_k = t_c + 273.15
    ea_hpa = max(rh, 0.01) * es_kpa(t_c) * 10.0

    eps_clear = 0.642 * (ea_hpa / t_k) ** 0.142

    result = (
        eps_clear
        * (1.0 + cloud_factor * cloud ** 2)
        * SIGMA_W_M2_K4
        * t_k ** 4
    )

    return finite_flux(result, "incoming longwave")
```

Add:

```python
def finite_flux(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result
```

Then in `flux_at()`:

```python
shortwave = (
    (1.0 - params.albedo)
    * params.shortwave_multiplier
    * met.shortwave_w_m2
)

longwave_in = (
    _lw_in_w_m2(
        met.air_c,
        met.rh,
        met.cloud,
        cloud_factor=params.cloud_longwave_factor,
    )
    * params.longwave_multiplier
    + params.longwave_offset_w_m2
)

longwave = (
    longwave_in
    - params.emissivity
    * SIGMA_W_M2_K4
    * t_k ** 4
)
```

This lets `calibrate.py` estimate radiation corrections without modifying the physics function.

---

# 6. Expose all effective component terms

`flux_at()` currently returns only:

```python
shortwave
longwave
sensible
latent
net
```

For calibration and diagnostics, return the intermediate terms:

```python
return {
    "shortwave": shortwave,
    "longwave_in": longwave_in,
    "longwave_out": (
        params.emissivity
        * SIGMA_W_M2_K4
        * t_k ** 4
    ),
    "longwave": longwave,
    "sensible": sensible,
    "latent": latent,
    "net": (
        shortwave
        + longwave
        + sensible
        + latent
    ),
    "air_vapor_pressure_kpa": ea,
    "water_saturation_vapor_pressure_kpa": es_w,
    "air_specific_humidity": q_air,
    "water_saturation_specific_humidity": q_sat,
    "air_density_kg_m3": rho,
    "transfer_wind_mps": transfer_wind,
}
```

This is valuable when a fit looks good but one component is physically implausible.

---

# 7. Check the derivative against finite differences

The analytic derivative is central to damped Newton:

```python
slope = (
    -4 * emissivity * sigma * T**3
    - sensible_coefficient
    - latent_coefficient * dq_sat
)
```

That is structurally correct if:

- air density is independent of water temperature;
- wind is independent of water temperature;
- incoming longwave is independent of water temperature;
- only outgoing longwave and water saturation humidity depend on `T_water`.

Add a test:

```python
def test_linearized_derivative_matches_finite_difference():
    met = MetState(
        air_c=10.0,
        rh=0.65,
        wind_mps=3.0,
        shortwave_w_m2=400.0,
        cloud=0.4,
    )
    params = BudgetParams()

    temperature = 20.0
    step = 1e-4

    plus = flux_at(
        temperature + step,
        met,
        params,
    )["net"]

    minus = flux_at(
        temperature - step,
        met,
        params,
    )["net"]

    numerical = (plus - minus) / (2.0 * step)
    _value, analytic = linearized(
        temperature,
        met,
        params,
    )

    assert analytic == pytest.approx(
        numerical,
        rel=1e-5,
        abs=1e-7,
    )
```

This test should run across several temperatures, humidity values, and wind speeds.

---

# 8. Avoid calibration parameter coupling

`calibrate.py` currently does:

```python
params = BudgetParams(
    c_h=BudgetParams.c_h * c_mult,
    c_e=BudgetParams.c_e * c_mult,
)
```

This means the calibration can only estimate a common turbulent multiplier.

That is a reasonable initial model, but the output should say explicitly:

```python
"c_mult": {
    "meaning": (
        "common multiplier applied to baseline sensible and "
        "latent transfer coefficients"
    ),
    "not_identified_independently": [
        "c_h",
        "c_e",
    ],
}
```

If independent calibration is justified later, extend `BudgetParams` usage:

```python
params = BudgetParams(
    c_h=BudgetParams.c_h * c_h_mult,
    c_e=BudgetParams.c_e * c_e_mult,
    shortwave_multiplier=sw_mult,
    longwave_offset_w_m2=lw_bias,
)
```

But only fit these independently when there are enough observations to distinguish them.

---

# 9. Improve `MetState` for timestamp/provenance

`MetState` contains values but no metadata about:

- measurement height;
- source;
- timestamp;
- pressure source;
- corrections applied.

The physical solver should remain lightweight, but the calibration pipeline should preserve metadata outside `MetState`.

For example:

```python
{
    "air_c": ...,
    "rh": ...,
    "wind_mps": ...,
    "shortwave_w_m2": ...,
    "cloud": ...,
    "timestamp_epoch_unix": ...,
    "source": "RTMA_plus_station_correction",
    "wind_height_m": 10.0,
}
```

Do not put arbitrary metadata into the dataclass if it is used in tight numerical loops. Store it in the replay/configuration document.

---

# 10. Improve cloud forcing scientifically

The current cloud term:

```python
1.0 + 0.22 * cloud ** 2
```

is a visual/empirical approximation. It may be acceptable as an illustrative default, but it should not be called calibrated unless compared with downwelling longwave observations.

Add an explicit status:

```python
"cloud_longwave_factor_status": (
    "illustrative_uncalibrated"
)
```

When measured longwave is available, prefer using it directly:

```python
MetState(
    ...,
    longwave_down_w_m2=measured_value,
)
```

That is better than inferring longwave from cloud fraction.

Extend `MetState`:

```python
@dataclass(frozen=True)
class MetState:
    air_c: float
    rh: float
    wind_mps: float
    shortwave_w_m2: float
    cloud: float
    longwave_down_w_m2: float | None = None
```

Validate it:

```python
if self.longwave_down_w_m2 is not None:
    longwave = float(self.longwave_down_w_m2)
    if not math.isfinite(longwave) or longwave < 0.0:
        raise ValueError(
            "longwave_down_w_m2 must be finite and >= 0"
        )
    object.__setattr__(
        self,
        "longwave_down_w_m2",
        longwave,
    )
```

Then:

```python
if met.longwave_down_w_m2 is None:
    longwave_in = _lw_in_w_m2(...)
else:
    longwave_in = met.longwave_down_w_m2
```

This cleanly separates:

```text
measured radiation
estimated radiation
```

---

# 11. Add measurement-based sensible and latent flux inputs

If direct flux estimates are available, permit them as observations but do not mix them into the model flux silently.

For calibration, return predicted components and compare them externally:

```python
predicted = flux_at(...)
observed = {
    "sensible_w_m2": ...,
    "latent_w_m2": ...,
}
```

Do not force the model to accept observed sensible/latent flux as forcing unless you intentionally want a prescribed-flux mode.

---

# 12. Improve `spec_from_series()`

Current implementation parses each input repeatedly:

```python
Series.parse(rh)
Series.parse(rh)
```

Normalize once:

```python
def spec_from_series(
    rh: Any,
    wind_mps: Any,
    shortwave_w_m2: Any,
    cloud: Any,
    params: dict | BudgetParams | None = None,
) -> dict:
    from .river_transport import Series

    rh_series = Series.parse(rh)
    wind_series = Series.parse(wind_mps)
    shortwave_series = Series.parse(shortwave_w_m2)
    cloud_series = Series.parse(cloud)

    if isinstance(params, BudgetParams):
        params_dict = {
            "albedo": params.albedo,
            "emissivity": params.emissivity,
            "c_h": params.c_h,
            "c_e": params.c_e,
            "pressure_kpa": params.pressure_kpa,
            "shortwave_multiplier": (
                params.shortwave_multiplier
            ),
            "longwave_multiplier": (
                params.longwave_multiplier
            ),
            "longwave_offset_w_m2": (
                params.longwave_offset_w_m2
            ),
            "cloud_longwave_factor": (
                params.cloud_longwave_factor
            ),
        }
    else:
        params_dict = dict(params or {})

    return {
        "rh": {
            "times_s": list(rh_series.times_s),
            "values": list(rh_series.values),
        },
        "wind_mps": {
            "times_s": list(wind_series.times_s),
            "values": list(wind_series.values),
        },
        "shortwave_w_m2": {
            "times_s": list(shortwave_series.times_s),
            "values": list(shortwave_series.values),
        },
        "cloud": {
            "times_s": list(cloud_series.times_s),
            "values": list(cloud_series.values),
        },
        "params": params_dict,
    }
```

Also validate that all surface-budget series begin at zero and that their time domains cover the intended replay.

---

# 13. Tie it into damped Newton correctly

With damped Newton, the sequence should be:

```text
River._solve_implicit_step()
    guess = previous timestep temperature
        ↓
    surface_flux.linearized(guess, met)
        ↓
    solve tridiagonal system
        ↓
    damp candidate update
        ↓
    repeat
        ↓
    converged temperature
        ↓
    surface_flux.flux_at(converged temperature, met)
        ↓
    final energy accounting
```

Therefore:

- `linearized()` must be stable and accurate;
- `flux_at()` must be the authoritative nonlinear flux;
- `linearized()` must agree with the finite-difference derivative of `flux_at()`;
- `River` must report iteration failures;
- calibration should reject failed forward candidates.

In `calibrate.py`, update:

```python
"budget_ok": budget["heat_relative_residual"] <= 1e-5
```

to:

```python
"budget_ok": (
    budget["heat_relative_residual"] <= 1e-5
    and budget["surface_iteration_failures"] == 0
)
```

---

# 14. Calibration parameter hierarchy

A sensible progression is:

## Level 1: current restrained fit

Fit:

```text
Q_lat
T_lat
common c_h/c_e multiplier
```

Keep fixed:

```text
albedo
emissivity
cloud_longwave_factor
pressure
bathymetry
```

## Level 2: radiation calibration

If radiometer observations exist, fit:

```text
shortwave_multiplier
longwave_offset
```

## Level 3: separate turbulent coefficients

Only with enough humidity, wind, and flux information:

```text
c_h_multiplier
c_e_multiplier
```

## Level 4: geometry uncertainty

Use surveyed cross sections or an ensemble:

```text
volume_m3
surface_area_m2
```

Do not allow geometry and heat-transfer coefficients to vary freely at the same time without strong priors.

---

# 15. Suggested output metadata

Every calibrated replay should preserve the effective surface model:

```json
{
  "surface_flux": {
    "method": "explicit_budget",
    "sign_convention": "positive_into_water",
    "parameters": {
      "albedo": 0.08,
      "emissivity": 0.97,
      "c_h": 0.0015,
      "c_e": 0.0015,
      "pressure_kpa": 77.8,
      "shortwave_multiplier": 1.0,
      "longwave_multiplier": 1.0,
      "longwave_offset_w_m2": 0.0,
      "cloud_longwave_factor": 0.22
    },
    "parameter_status": {
      "albedo": "illustrative",
      "emissivity": "literature_or_assumed",
      "c_h": "scaled_by_calibration",
      "c_e": "scaled_by_calibration",
      "pressure_kpa": "derived_from_site_elevation",
      "shortwave_multiplier": "illustrative",
      "longwave_multiplier": "illustrative",
      "longwave_offset_w_m2": "illustrative",
      "cloud_longwave_factor": "illustrative"
    }
  }
}
```

---

## Priority order

1. Update the module documentation for damped Newton.
2. Preserve raw wind while applying a separate transfer floor.
3. Share site pressure with `microclimate.py`.
4. Add domain validation for vapor pressure and humidity.
5. Add finite-difference derivative tests.
6. Expose radiation correction parameters.
7. Support measured downwelling longwave when available.
8. Add component diagnostics and provenance.
9. Reject failed Newton candidates during calibration.
10. Only then expand calibration from a common `c_mult` to separate coefficients.

The key point is that `surface_flux.py` defines the model being calibrated; `calibrate.py` searches its parameters; and damped Newton only ensures that the nonlinear version of that model is solved consistently at each timestep.