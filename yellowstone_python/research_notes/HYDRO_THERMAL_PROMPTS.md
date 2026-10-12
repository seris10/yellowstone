# Phase A: Hydro-Thermal System Research (Scientific Report)

## Deliverable
A single markdown research report documenting river thermal mixing physics, measurement gaps, and equation relationships for the Yellowstone thermal river simulation.

## Report Structure
1. Physical system description (6-reach Firehole chain, Excelsior plume, tributary dilution).
2. Governing equations with full mathematical notation:
   - Per-reach energy balance: d(Vi·Ti)/dt = ΣQji·Tj + Qhot,i·Thot,i − Qout,i·Ti + Vi·(Tair − Ti)/τi
   - Constant-volume constraint: Qout = ΣQin + Qhot
   - Mixing relationship: Tmixed = (Q1·T1 + Q2·T2)/(Q1 + Q2)
   - 1-D thermal profile: T(x) = Ta + (T0 − Ta)·exp(−he·b·x/(ρ·cp·Q))
   - Newton cooling: heat loss coefficient τi, substep stability dt ≤ 0.45/rate
3. Parameter tables (value, source, status: calibrated / illustrative / unknown, units, citation URL).
4. Missing measurements (bathymetry, dated T/Q series, branch discharges, bed temperature/salinity, soil Ksat) with impact assessment.
5. Validation criteria (volume conservation <1e-9 m³, heat residual ~1e-10 m³·°C, downstream temperature monotone, plume geometry verification).
6. Equations relating thermal profile to habitat suitability and fish refuge selection.
