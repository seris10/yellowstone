"""Equation inventory: governing model and limits per component."""
from __future__ import annotations

ENTRY_FIELDS = ("component", "module", "model_level", "equations",
                "assumptions", "limits")

COMPONENTS = [
    {
        "component": "M01 six-reach mixing chain",
        "module": "hydro_thermal.py",
        "model_level": "quasi-steady reach network with constant volumes",
        "equations": "d(ViTi)/dt = inflow enthalpy + lateral enthalpy - outflow enthalpy "
                     "+ Vi(Tair-Ti)/tau_i; Qout = Qin + Qhot",
        "assumptions": "each reach fully mixed; volumes fixed; lateral sources prescribed",
        "limits": "uniform-flow resistance; backwater, jumps, floodplain exchange excluded",
    },
    {
        "component": "M01b 1-D advection-dispersion replay",
        "module": "replay/river_transport.py",
        "model_level": "1-D advection-dispersion on chainage cells, no momentum equation",
        "equations": "d(V_i T_i)/dt = Q(T_{i-1} - T_i) + D A (T_{i+1} - 2T_i + T_{i-1})/dx + Phi_i; "
                     "backward-Euler step, finite-volume cells",
        "assumptions": "prescribed upstream Q/T series; DEM-derived depths; authored roughness",
        "limits": "depths estimated from DEM transects; submerged bathymetry unmeasured",
    },
    {
        "component": "surface heat exchange",
        "module": "replay/surface_flux.py",
        "model_level": "lumped Newton exchange by default; explicit budget optional",
        "equations": "Newton: Phi = h(Tair - T); explicit: Phi = SW + LW + H + LE "
                     "with scaled turbulent coefficients c_h, c_e",
        "assumptions": "explicit-budget coefficients illustrative; ice-free surface",
        "limits": "winter ice cover outside scope; coefficients uncalibrated",
    },
    {
        "component": "2-D plume field",
        "module": "hydro_thermal.py plume_field via replay/plume2d.py",
        "model_level": "steady 2-D advection-diffusion solve on a fixed grid",
        "equations": "u dT/dz = Dx d2T/dx2 + Dz d2T/dz2 - k(T - ambient); "
                     "implicit upwind/centered solve, source cells fixed",
        "assumptions": "map overlay for field notes; velocity and diffusivities prescribed",
        "limits": "no calibration; cross-channel mixing unresolved",
    },
    {
        "component": "pool radial temperature",
        "module": "pool_crust.py",
        "model_level": "diagnostic radial profile, no heat PDE",
        "equations": "T(r) = T_edge + (T_c - T_edge)(1 - (r/rw)^2) for r <= rw; "
                     "pigment bands keyed to depth, gradient, substrate",
        "assumptions": "pigment stops authored; mapped outline preserved",
        "limits": "no universal temperature-to-color relation; bathymetry unmeasured",
    },
    {
        "component": "patch biomass",
        "module": "vegetation.py",
        "model_level": "lumped logistic growth with grazing debit per patch",
        "equations": "dB/dt = r f_light f_water B(1 - B/K) - G",
        "assumptions": "patch-mean moisture and light; suitability coefficients authored",
        "limits": "no organism counts; K and r uncalibrated",
    },
    {
        "component": "insect compartments",
        "module": "insects_birds.py",
        "model_level": "three-compartment prey with Holling-II depletion",
        "equations": "C(N) = aN/(1 + ahN); benthic degree-day development to emergence flux",
        "assumptions": "hourly substeps; shared foraging ground at refuge cell",
        "limits": "molluscs unmodeled; warm-cell food underestimated",
    },
    {
        "component": "trout suitability and refuge",
        "module": "fish.py",
        "model_level": "nondimensional suitability over chainage window",
        "equations": "Ui = wf Fi + wc Ci - wt phi(Ti) - wv Vi - wd Di; refuge by argmax in swim range",
        "assumptions": "literature anchors for thermal terms; weights authored; uniform depth 1.1 m",
        "limits": "shelter positioning, no mortality; sub-cell refuges unresolved",
    },
    {
        "component": "grazer routing",
        "module": "grazers.py",
        "model_level": "8-connected A* on eligibility grid, no movement dynamics",
        "equations": "Euclidean-heuristic shortest path with full-segment blocked checks",
        "assumptions": "thermal, water, cliff exclusion masks; sparse authored loops",
        "limits": "no abundance model; corridor re-walk covers the authored route",
    },
    {
        "component": "snow and soil water",
        "module": "snow_season.py",
        "model_level": "degree-day accumulation/melt with soil bucket",
        "equations": "melt = k_melt max(0, T - tbase) + thermal ground flux; soil bucket with ET and drainage",
        "assumptions": "per-habitat modifiers authored; thermal ground carries melt flux",
        "limits": "TAVG forcing misses plateau melt energy; soil moisture unvalidated",
    },
]


def validate_inventory() -> list:
    errors = []
    for c in COMPONENTS:
        for f in ENTRY_FIELDS:
            if f not in c:
                errors.append(f"component {c.get('component', '?')}: missing field {f}")
    names = [c["component"] for c in COMPONENTS]
    if len(names) != len(set(names)):
        errors.append("duplicate component in inventory")
    return errors
