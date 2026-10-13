Calibration means estimating uncertain parameters from observations while testing whether the model generalizes to withheld conditions. For this system, calibrate in stages rather than fitting every parameter simultaneously.

## 1. Separate what can and cannot be calibrated

### Calibratable or estimable

- Newton exchange coefficient `h`.
- Turbulent transfer coefficients `c_h`, `c_e`.
- Longwave/emissivity/albedo corrections.
- Cloud-radiation attenuation.
- Dispersion coefficient `D`.
- Manning roughness `n`.
- Effective channel depth/area.
- Lateral inflow discharge and temperature.
- Soil infiltration and drainage parameters.
- Local weather bias corrections.

### Not directly identifiable from temperature alone

Several parameters can produce similar temperature effects. For example:

- larger `h`;
- stronger shortwave radiation;
- warmer air;
- lower flow;
- shallower channel volume.

All may increase water temperature. Therefore, water temperature alone cannot reliably estimate all of them simultaneously. You need independent observations or fixed priors.

---

# 2. Build an observation hierarchy

Use observations that isolate different processes.

## Meteorology

At or near the modeled reach:

- air temperature;
- relative humidity;
- wind speed and direction;
- incoming shortwave radiation;
- incoming/outgoing longwave radiation;
- cloud fraction or cloud-base observations;
- precipitation;
- atmospheric pressure.

Potential sources:

- NOAA/NWS stations;
- RAWS stations;
- SNOTEL;
- nearby weather stations;
- RTMA/HRRR;
- Open-Meteo as a convenience source;
- a temporary field station at the river.

For surface-flux calibration, a weather station several kilometers away may be insufficient, especially in geothermal terrain.

## Hydrology and hydraulics

Measure:

- upstream discharge;
- downstream discharge;
- lateral-source discharge;
- stage;
- cross-section width and depth;
- velocity;
- water-surface slope;
- channel geometry;
- tributary entry locations.

Useful instruments:

- pressure transducers;
- staff gauges;
- acoustic Doppler velocimeters;
- tracer dilution;
- surveyed cross sections;
- thermal infrared observations for lateral inflows.

## Water temperature

Use synchronized temperature loggers:

- upstream boundary;
- each major lateral source;
- downstream outlet;
- intermediate reaches;
- high-frequency logging, ideally 1–5 minutes.

A few daily measurements are inadequate for calibrating hourly thermal dynamics.

## Surface heat flux

For stronger calibration, deploy:

- net radiometer;
- pyranometer;
- longwave radiometer;
- anemometer;
- temperature/humidity sensor;
- water-surface temperature sensor;
- water temperature at representative depth.

Without heat-flux observations, `h`, `c_h`, `c_e`, radiation corrections, and cloud effects will be weakly identifiable.

---

# 3. Fix geometry before calibrating thermal physics

Do not calibrate heat parameters against incorrect volume or flow geometry.

The model uses:

```python
volume_m3 = length_m * width_m * depth_m
```

Before estimating `h` or `D`, improve:

- channel length;
- wetted width;
- mean depth;
- cross-sectional area;
- exposed water-surface area;
- discharge;
- reach slope.

Otherwise the optimizer may compensate for a wrong volume by estimating a wrong heat coefficient.

For each cell, distinguish:

```text
solver volume       = water storage volume
surface area        = area receiving heat flux
bed/wetted perimeter = area relevant to exchange or friction
```

Do not use a single width/depth value for all processes unless justified.

---

# 4. Calibrate in stages

## Stage A: calibrate hydraulics and travel time

Before temperature calibration, fit the hydraulic representation.

Use observed discharge and travel-time data.

Estimate:

- `manning_n`;
- effective depth;
- effective cross-sectional area;
- dispersion-independent travel time;
- lateral discharge contributions.

A tracer experiment is particularly useful. Release a conservative tracer or use a natural thermal pulse and measure arrival times downstream.

Objective function:

\[
J_\text{travel}
=
w_t(\tau_\text{model}-\tau_\text{obs})^2
+
w_q(Q_\text{model}-Q_\text{obs})^2
\]

Do not use thermal parameters to compensate for hydraulic errors.

---

## Stage B: calibrate longitudinal dispersion

Use a tracer or a sharp temperature pulse.

Estimate `D` from:

- pulse arrival time;
- pulse width;
- peak attenuation;
- downstream concentration/temperature variance.

A useful objective is:

\[
J_D =
w_\text{arrival}(\tau_m-\tau_o)^2
+
w_\text{width}(\sigma_m-\sigma_o)^2
+
w_\text{peak}(C_m-C_o)^2
\]

Calibrate `D` before surface heat exchange. Otherwise dispersion can absorb errors in thermal forcing.

Use reach-specific or flow-dependent dispersion if the data support it:

```text
D(Q, depth, velocity)
```

Do not automatically use a single fitted value across all flow regimes.

---

## Stage C: calibrate boundary and lateral sources

For each source, estimate:

- discharge;
- temperature;
- timing;
- mixing location.

Use observations immediately upstream and downstream of the source.

A lateral source should be calibrated against:

```text
mass balance:
Q_down = Q_up + Q_lateral
```

and thermal mixing:

\[
T_\text{mixed}
=
\frac{
Q_\text{up}T_\text{up}
+
Q_\text{lat}T_\text{lat}
}{
Q_\text{up}+Q_\text{lat}
}
\]

This is often more informative than trying to infer source flow from downstream temperature alone.

---

## Stage D: calibrate the Newton coefficient

For Newton mode:

\[
F_\text{surface}
=
h(T_\text{air}-T_\text{water})
\]

Estimate `h` only after:

- geometry is constrained;
- flow and lateral sources are known;
- dispersion is calibrated;
- air temperature is measured;
- shortwave/radiation forcing is either negligible or separately accounted for.

Use multiple reaches and multiple weather conditions. A single hot afternoon cannot identify a robust coefficient.

Fit `h` using a residual such as:

\[
J_h =
\sum_{r,t}
w_{r,t}
\left[
T_\text{model}(r,t)
-
T_\text{obs}(r,t)
\right]^2
\]

Use a physically plausible parameter range, for example:

```text
h > 0
```

with the actual upper/lower bounds based on the intended model and literature prior.

A better approach is to include a regularization or prior:

\[
J =
J_\text{temperature}
+
\lambda_h(h-h_\text{prior})^2
\]

This prevents `h` from compensating for unmodeled radiation or geometry.

---

# 5. Calibrate the explicit surface budget separately

The explicit budget includes something like:

```text
net_flux =
shortwave
+ longwave
+ sensible
+ latent
```

A generic form is:

\[
F =
(1-\alpha)SW
+
LW_\downarrow
-
\epsilon\sigma T_w^4
+
H
+
LE
\]

where:

- `SW` is incoming shortwave;
- `LW_down` is incoming longwave;
- `α` is albedo;
- `ε` is emissivity;
- `H` is sensible heat;
- `LE` is latent heat.

## Calibrate radiation inputs first

Compare modeled radiation terms against measured radiometer data.

Estimate:

- shortwave bias or multiplicative correction;
- longwave bias;
- cloud attenuation factor;
- albedo;
- emissivity;
- shading correction.

For example:

\[
SW_\text{effective}
=
c_{sw}(1-f_\text{shade})SW_\text{measured}
\]

and:

\[
LW_\downarrow^\text{effective}
=
LW_\downarrow^\text{measured}
+
b_{lw}
\]

Fit these against radiometer observations before fitting water temperature.

## Calibrate turbulent transfer coefficients

For sensible and latent flux:

\[
H =
\rho_a c_p C_H U(T_a-T_w)
\]

\[
LE =
\rho_a L_v C_E U(q_a-q_s)
\]

Estimate:

- `C_H`;
- `C_E`;
- roughness length;
- wind-height correction;
- humidity bias;
- surface resistance, if applicable.

The coefficients should not be fitted independently from sparse water-temperature data. Use eddy-covariance or bulk-flux observations if available.

If direct flux measurements are unavailable, use literature priors and fit only a constrained multiplier:

```python
c_h = c_h_prior * multiplier_h
c_e = c_e_prior * multiplier_e
```

with limited bounds.

---

# 6. Calibrate humidity corrections

Humidity affects latent heat strongly. Before fitting a correction, determine whether the error comes from:

- relative humidity;
- air temperature;
- pressure;
- vapor-pressure formula;
- wind speed;
- water-surface temperature.

Use dewpoint observations rather than relative humidity alone when possible.

A simple bias model could be:

\[
RH_\text{corrected}
=
\operatorname{clip}(a_{RH}RH_\text{provider}+b_{RH},0,1)
\]

Fit `a_RH` and `b_RH` against local observations, then freeze them before thermal calibration.

Do not fit arbitrary humidity correction and latent coefficient simultaneously unless you have enough independent observations.

---

# 7. Calibrate cloud effects

Clouds affect the model through:

- shortwave attenuation;
- longwave downwelling;
- nighttime cooling;
- air temperature;
- precipitation likelihood;
- visual cloud rendering.

Separate **physical cloud forcing** from **visual cloud appearance**.

For physics, estimate cloud corrections using measured radiation:

```text
cloud_fraction → shortwave multiplier
cloud_fraction + humidity + cloud_base → longwave estimate
```

For example:

\[
SW_\text{surface}
=
SW_\text{clear}
\left[
1-c_1 f_c^{c_2}
\right]
\]

Fit `c1` and `c2` against pyranometer data, preferably by season.

For the renderer, the weather snapshot should contain the already-normalized:

```json
{
  "cloud_fraction": 0.74,
  "shortwave_w_m2": 180.0,
  "longwave_down_w_m2": 310.0
}
```

The Godot shader should not attempt to infer physical radiation from cloud fraction.

---

# 8. Calibrate bathymetry and effective volume

Bathymetry is especially important because the thermal storage term is:

\[
\rho c_p V \frac{dT}{dt}
\]

If `V` is wrong, the model’s response speed is wrong.

Estimate:

- width;
- depth;
- cross-sectional shape;
- wetted area;
- storage volume;
- surface area.

Use:

- surveyed cross sections;
- sonar;
- wading measurements;
- stage-discharge relations;
- DEM only as a prior or lateral constraint.

For sparse data, use uncertain geometry rather than one false precise number:

```python
depth_m ~ Normal(depth_prior, depth_sigma)
width_m ~ Normal(width_prior, width_sigma)
```

Then propagate geometry uncertainty into temperature predictions.

Do not “calibrate depth” solely by fitting temperature if depth can be measured independently.

---

# 9. Use a calibration objective with multiple metrics

Do not optimize only RMSE. Combine:

## Temperature metrics

- bias;
- MAE;
- RMSE;
- peak error;
- timing error;
- correlation;
- thermal-gradient error.

## Hydrologic metrics

- discharge bias;
- volume-balance error;
- travel-time error;
- source mixing error.

## Energy metrics

- heat-budget residual;
- surface-flux component error;
- radiation residual.

Example:

\[
J =
w_T J_T
+
w_Q J_Q
+
w_\tau J_\tau
+
w_F J_F
+
\lambda J_\text{prior}
\]

where:

```text
J_T = temperature residual
J_Q = discharge residual
J_τ = travel-time residual
J_F = surface-flux residual
J_prior = parameter regularization
```

Normalize each term so one unit system does not dominate:

```python
normalized = residual / observational_uncertainty
```

That turns the objective into something closer to a weighted likelihood.

---

# 10. Use time-blocked and event-blocked validation

Do not randomly split hourly observations. That leaks temporal structure.

Use:

```text
calibration:
    early-season days or selected events

validation:
    later days

locked evaluation:
    unseen heat/rain/cloud events
```

For the claim registry, retain:

```text
train
holdout
locked-final
```

For example:

```text
train:
    clear and partly cloudy ice-free periods

holdout:
    separate weather days

locked-final:
    an independent hot pulse, rain event, or cloud transition
```

A parameter set that works only on clear weather is not a general heat-budget calibration.

---

# 11. Estimate uncertainty, not just one best fit

Useful methods:

- profile likelihood;
- bootstrap by day/event;
- ensemble calibration;
- Bayesian posterior sampling;
- Markov chain Monte Carlo;
- differential evolution followed by local least squares;
- ensemble Kalman methods for sequential data.

A practical workflow:

1. Generate physically plausible parameter samples.
2. Run the model for each sample.
3. Rank using the multi-objective score.
4. Retain the top ensemble.
5. Report prediction intervals.

Example output:

```json
{
  "parameter": "replay.exchange_w_m2_k",
  "estimate": 8.7,
  "interval_90": [5.1, 14.3],
  "calibration_dataset": "derived/firehole_obs.json:train",
  "posterior_predictive_rmse_c": 0.84,
  "status": "calibrated_not_accepted"
}
```

Avoid reporting `h=8.7` without its uncertainty.

---

# 12. Recommended tools

For a first implementation:

```python
scipy.optimize.least_squares
scipy.optimize.differential_evolution
scipy.stats.qmc
```

For Bayesian calibration:

```python
emcee
numpyro
pymc
```

For global sensitivity:

```python
SALib
```

For solar/radiation:

```python
pvlib
```

For astronomy:

```python
astropy
skyfield
```

---

# 13. A practical calibration runner

Create a separate script rather than embedding calibration inside the simulator:

```text
tools/calibrate_river_transport.py
```

Conceptual structure:

```python
from dataclasses import dataclass
import numpy as np
from scipy.optimize import differential_evolution


@dataclass(frozen=True)
class CalibrationParams:
    exchange_w_m2_k: float
    dispersion_m2_s: float
    depth_scale: float
    shortwave_scale: float
    longwave_bias_w_m2: float
    humidity_bias: float
    c_h_scale: float
    c_e_scale: float


def simulate(params, forcing, observations):
    config = build_config_from_params(params, forcing)
    replay = make_replay(config)
    return extract_predictions(replay)


def objective_vector(x, forcing, observations):
    params = CalibrationParams(
        exchange_w_m2_k=x[0],
        dispersion_m2_s=x[1],
        depth_scale=x[2],
        shortwave_scale=x[3],
        longwave_bias_w_m2=x[4],
        humidity_bias=x[5],
        c_h_scale=x[6],
        c_e_scale=x[7],
    )

    prediction = simulate(params, forcing, observations)

    return normalized_residuals(
        prediction,
        observations,
    )


def objective_scalar(x, forcing, observations):
    residuals = objective_vector(
        x,
        forcing,
        observations,
    )
    return float(np.dot(residuals, residuals))
```

Use staged parameter groups:

```python
# Stage 1
fit = ["manning_n", "depth_scale"]

# Stage 2
fit = ["dispersion_m2_s"]

# Stage 3
fit = ["exchange_w_m2_k"]

# Stage 4
fit = ["shortwave_scale", "longwave_bias_w_m2"]

# Stage 5
fit = ["c_h_scale", "c_e_scale"]
```

Do not fit all eight parameters from the beginning.

---

# 14. Recommended initial calibration sequence for Yellowstone

## Minimum viable program

### Field/data preparation

1. Install synchronized water-temperature loggers.
2. Obtain discharge at upstream and downstream boundaries.
3. Measure or estimate lateral-source flows.
4. Gather local air temperature, humidity, wind, and radiation.
5. Survey representative cross sections.
6. Record exact sensor locations and timestamps in UTC.

### Modeling sequence

1. Fit effective geometry against stage/discharge.
2. Fit Manning roughness against velocity/travel time.
3. Fit dispersion using tracer or thermal-pulse width.
4. Fit source mixing and source temperatures.
5. Fit Newton `h` during periods with weak radiation uncertainty.
6. Add explicit radiation budget.
7. Fit radiation correction factors.
8. Fit turbulent transfer multipliers.
9. Validate against held-out weather events.
10. Quantify uncertainty.

---

# 15. What to do if field data are limited

If you only have:

- upstream/downstream water temperature;
- air temperature;
- discharge;
- no radiometer;
- no source-flow measurements;

then do not claim full calibration of the explicit energy budget.

An analyst can estimate an effective thermal exchange parameter, but not uniquely separate:

```text
h
shortwave correction
longwave correction
latent transfer
humidity bias
bathymetry
```

In that situation:

- use literature priors;
- calibrate one effective parameter at a time;
- label results `effective` or `assumed`;
- perform sensitivity analysis;
- avoid calling all components independently calibrated.

For example:

```text
calibrated:
    effective_exchange_w_m2_k

assumed:
    albedo
    emissivity
    c_h
    c_e
    bathymetry

observed:
    air temperature
    discharge
    upstream/downstream water temperature
```

That is scientifically more defensible than fitting seven unconstrained knobs.

---

## Bottom line

The right strategy is:

```text
measure geometry and flow
    ↓
calibrate travel time and dispersion
    ↓
measure/calibrate lateral mixing
    ↓
calibrate effective heat exchange
    ↓
add radiation and turbulent components
    ↓
validate on independent events
    ↓
report uncertainty and identifiability
```

Damped Newton iteration improves the numerical solution of the chosen surface-budget equations. Calibration determines whether those equations and their parameters represent the Firehole. They are separate steps and should remain separate in the code, metadata, and claims registry.