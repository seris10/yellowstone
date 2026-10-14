# Phase B: Microclimate and Weather Authority Research (Scientific Report)

## Deliverable
A single markdown report defining the weather-state equations that govern thermal ecology, wind dynamics, and their coupling to river temperature, vegetation, insect activity, snow state, and audio/visual proxies.

## Equations and Relationships
- Air temperature: Tair(t) = Tnight + ΔTday·sin(2π·(hour − 9)/24)
- Steam visibility proxy: f(Tsurface, humidity, wind) — artistic but thermally consistent with river surface temperature.
- Wind vector authority: prevailing direction (low-frequency) + gust amplitude; drives foliage displacement, steam drift, insect exposure, and acoustic gain uniformly.
- Thermal range constraint: 5–24 °C; weather parameters must stay within this envelope for all coupled subsystems.

## Report Sections
1. Measurement sources (NPS, USGS, NOAA) with temporal/geographic coverage.
2. Parameter quantification (night air, day warming, prevailing wind vector, gust, humidity, cloud) with units, ranges, uncertainty.
3. Cross-system consistency requirements: same weather state must simultaneously drive river cooling, vegetation response, insect activity, snow accumulation, and steam density without phase divergence.
4. Seasonal transition parameters linking weather to snow season (degree-day trigger, aspect/wind/canopy modifiers).
5. Validation criteria (single prevailing direction across 60 s trace, no independent subsystem clocks).
