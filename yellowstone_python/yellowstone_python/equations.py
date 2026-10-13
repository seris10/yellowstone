"""Equation inventory: governing model and limits per component."""
from __future__ import annotations

from pathlib import Path

ENTRY_FIELDS = ("component", "module", "model_level", "equations",
                "variables", "units", "assumptions", "limits",
                "validation_status")

COMPONENTS = [
    {
        "component": "M01 six-reach mixing chain",
        "module": "hydro_thermal.py",
        "model_level": "quasi-steady reach network with constant volumes",
        "equations": ("rho*cp*d(V_i*T_i)/dt = "
                      "rho*cp*(Q_in*T_in - Q_out*T_i) + "
                      "rho*cp*sum(Q_l*T_l - Q_l*T_i) + "
                      "A_i*h_i*(T_air - T_i); "
                      "Q_out = Q_in + sum(Q_l)"),
        "variables": ("V_i: reach volume m3; T_i: reach temperature C; "
                      "Q_in, Q_out, Q_l: discharges m3/s; T_in, T_l: "
                      "upstream and lateral temperatures C; A_i: reach "
                      "surface area m2; h_i: Newton coefficient W/m2/K; "
                      "T_air: air temperature C"),
        "units": ("time s; temperature C; discharge m3/s; volume m3; "
                  "coefficient W/m2/K; area m2"),
        "assumptions": ("each reach fully mixed; volumes fixed; lateral "
                        "sources prescribed; rho and cp constant"),
        "limits": "uniform-flow resistance; backwater, jumps, floodplain exchange excluded",
        "validation_status": "numerical_mixing_tested_not_field_validated",
    },
    {
        "component": "M01b 1-D advection-dispersion replay",
        "module": "replay/river_transport.py",
        "model_level": ("1-D advection-dispersion on chainage cells, no "
                        "momentum equation"),
        "equations": ("rho*cp*V_i*dT_i/dt = "
                      "rho*cp*(F_in,i - F_out,i) + "
                      "rho*cp*sum(Q_l*T_l) + "
                      "A_surface,i*Phi_surface,i + P_cell,i; "
                      "F_j = Q_j*T_upwind + G_j*(T_left - T_right); "
                      "G_j = harmonic dispersion conductance; "
                      "backward Euler, tridiagonal solve"),
        "variables": ("V_i: cell water volume m3; Q_j: face discharge "
                      "m3/s; G_j: face dispersive conductance m3/s; "
                      "Phi_surface: surface heat flux W/m2; P_cell: "
                      "cell heat power W; A_surface,i: cell surface "
                      "area m2"),
        "units": ("time s; temperature C; discharge m3/s; conductance "
                  "m3/s; flux W/m2; power W; area m2; volume m3"),
        "assumptions": ("prescribed upstream Q/T series; DEM-derived depths; "
                        "authored roughness; rho and cp constant"),
        "limits": "depths estimated from DEM transects; submerged bathymetry unmeasured",
        "validation_status":
            "numerical_conservation_tested_not_field_validated",
    },
    {
        "component": "surface heat exchange",
        "module": "replay/surface_flux.py",
        "model_level": ("lumped Newton exchange by default; explicit "
                        "nonlinear surface budget solved by damped "
                        "Newton iteration"),
        "equations": ("Newton: Phi = h(Tair - T); explicit: "
                      "Phi = SW + LW + H + LE with scaled turbulent "
                      "coefficients c_h, c_e; nonlinear closure solved "
                      "by damped Newton iteration"),
        "variables": ("Phi: surface heat flux W/m2; T, Tair: surface "
                      "and air temperatures C; h: Newton coefficient "
                      "W/m2/K; SW, LW, H, LE: shortwave, longwave, "
                      "sensible, latent fluxes W/m2"),
        "units": "temperature C; flux W/m2; coefficient W/m2/K",
        "assumptions": "explicit-budget coefficients illustrative; ice-free surface",
        "limits": ("winter ice cover outside scope; radiation and "
                   "transfer coefficients require local calibration; "
                   "convergence is numerical, not validation"),
        "validation_status": "numerical_only_not_field_validated",
    },
    {
        "component": "2-D plume field",
        "module": "hydro_thermal.py plume_field via replay/plume2d.py",
        "model_level": "steady 2-D advection-diffusion solve on a fixed grid",
        "equations": "u dT/dz = Dx d2T/dx2 + Dz d2T/dz2 - k(T - ambient); "
                     "implicit upwind/centered solve, source cells fixed",
        "variables": ("u: streamwise velocity m/s; Dx, Dz: diffusivities "
                      "m2/s; k: relaxation to ambient 1/s; T, ambient: "
                      "temperatures C"),
        "units": "velocity m/s; diffusivity m2/s; rate 1/s; temperature C",
        "assumptions": "map overlay for field notes; velocity and diffusivities prescribed",
        "limits": "no calibration; cross-channel mixing unresolved",
        "validation_status": "illustrative_overlay_not_validated",
    },
    {
        "component": "pool radial temperature",
        "module": "pool_crust.py",
        "model_level": "diagnostic radial profile, no heat PDE",
        "equations": ("T(r) = T_edge + (T_center - T_edge)*(1-(r/r_water)^2) "
                      "for 0 <= r <= r_water; T = T_edge for r > r_water; "
                      "pigment bands authored"),
        "variables": ("r: radial coordinate m; r_water: water edge radius "
                      "m; T_center, T_edge: center and edge temperatures C"),
        "units": "radius m; temperature C",
        "assumptions": "pigment stops authored; mapped outline preserved",
        "limits": "no universal temperature-to-color relation; bathymetry unmeasured",
        "validation_status": "authored_profile_not_validated",
    },
    {
        "component": "patch biomass",
        "module": "vegetation.py",
        "model_level": "lumped logistic growth with grazing debit per patch",
        "equations": "dB/dt = r f_light f_water B(1 - B/K) - G",
        "variables": ("B: biomass kg/m2; K: carrying capacity kg/m2; "
                      "r: intrinsic growth rate 1/s; f_light, f_water: "
                      "modifiers dimensionless; G: grazing debit "
                      "kg/m2/s"),
        "units": "biomass kg/m2; capacity kg/m2; rate 1/s; grazing kg/m2/s",
        "assumptions": "patch-mean moisture and light; suitability coefficients authored",
        "limits": "no organism counts; K and r uncalibrated",
        "validation_status": "illustrative_not_validated",
    },
    {
        "component": "insect compartments",
        "module": "insects_birds.py",
        "model_level": "three-compartment prey with Holling-II depletion",
        "equations": "C(N) = aN/(1 + ahN); benthic degree-day development to emergence flux",
        "variables": ("N: prey density dimensionless; a: attack rate; "
                      "h: handling time; degree_days: accumulated TAVG "
                      "above base C*day"),
        "units": "density dimensionless; time s; temperature C",
        "assumptions": "hourly substeps; shared foraging ground at refuge cell",
        "limits": "molluscs unmodeled; warm-cell food underestimated",
        "validation_status": "illustrative_not_validated",
    },
    {
        "component": "trout suitability and refuge",
        "module": "fish.py",
        "model_level": "nondimensional suitability over chainage window",
        "equations": "Ui = wf Fi + wc Ci - wt phi(Ti) - wv Vi - wd Di; refuge by argmax in swim range",
        "variables": ("Fi, Ci, Ti, Vi, Di: food, cover, temperature "
                      "penalty, velocity, depth terms; w_*: authored "
                      "weights; U_i: nondimensional suitability"),
        "units": "temperature C; depth m; velocity m/s; weights dimensionless",
        "assumptions": "literature anchors for thermal terms; weights authored; uniform depth 1.1 m",
        "limits": "shelter positioning, no mortality; sub-cell refuges unresolved",
        "validation_status": "illustrative_not_validated",
    },
    {
        "component": "trout placement at replay refuge",
        "module": "fish.py place_trout_at_chainage",
        "model_level": ("deterministic placement of each trout at the "
                        "replay food-web refuge cell"),
        "equations": ("i = argmin_i |chainage_i - (s_m - chainage_offset_m)|; "
                      "start = clip(i - width//2, 0, N-1-width); "
                      "reach_temp_c = selection.temperature_c"),
        "variables": ("s_m: refuge chainage from replay, m; "
                      "chainage_offset_m: polyline-to-replay offset, m; "
                      "width: trout segment span, points; chainage_i: "
                      "polyline chainage at point i, m; N: polyline length, "
                      "points"),
        "units": "chainage m; temperature C",
        "assumptions": ("replay food web selects the refuge cell; "
                        "placement clamps to the polyline when the refuge "
                        "lies off it"),
        "limits": ("one refuge per trout; sub-cell position unresolved; "
                   "no displacement dynamics"),
        "validation_status": "deterministic_placement_not_validated",
    },
    {
        "component": "grazer routing",
        "module": "grazers.py",
        "model_level": "8-connected A* on eligibility grid, no movement dynamics",
        "equations": "Euclidean-heuristic shortest path with full-segment blocked checks",
        "variables": ("waypoints: (x, z) m; cell_m: grid spacing m; "
                      "eligibility: boolean mask"),
        "units": "length m; grid spacing m",
        "assumptions": "thermal, water, cliff exclusion masks; sparse authored loops",
        "limits": "no abundance model; corridor re-walk covers the authored route",
        "validation_status": "authored_route_check_only",
    },
    {
        "component": "snow and soil water",
        "module": "snow_season.py",
        "model_level": "degree-day accumulation/melt with soil bucket",
        "equations": ("SWE_{t+1} = max(0, SWE_t + P_t - M_t); "
                      "M_t = k_melt*max(0, TAVG_t - T_base) + "
                      "ground_energy_mm_d; "
                      "soil_{t+1} = clip(soil_t + infiltration - ET - "
                      "drainage)"),
        "variables": ("SWE: snow water equivalent mm; P: precipitation "
                      "liquid-equivalent daily accumulation mm/day; "
                      "M: daily melt mm/day; k_melt: mm/C/day; TAVG: "
                      "daily mean air temperature C; T_base: 0 C; "
                      "ground_energy_mm_d: mm/day; soil: soil water mm"),
        "units": ("SWE mm; precipitation mm/day; melt mm/day; "
                  "temperature C; soil mm"),
        "assumptions": ("daily TAVG forcing; precipitation is "
                        "liquid-equivalent daily accumulation; habitat "
                        "modifiers authored; thermal ground carries melt flux"),
        "limits": "TAVG forcing misses plateau melt energy; soil moisture unvalidated",
        "validation_status": "degree_day_fit_tested_not_locked",
    },
]


def validate_inventory(root: Path | None = None) -> list[str]:
    """Field presence, nonempty strings, duplicate detection, and an
    optional on-disk check that each declared module exists."""
    errors: list[str] = []
    for entry in COMPONENTS:
        name = entry.get("component", "?")
        for field in ENTRY_FIELDS:
            value = entry.get(field)
            if value is None:
                errors.append(f"component {name}: missing {field}")
            elif isinstance(value, str) and not value.strip():
                errors.append(f"component {name}: empty {field}")
        module = entry.get("module")
        if root is not None and isinstance(module, str):
            first = module.split()[0]
            module_path = root / first
            if not module_path.is_file():
                errors.append(
                    f"component {name}: module not found: {module_path}")
    names = [entry.get("component") for entry in COMPONENTS
             if entry.get("component") is not None]
    if len(names) != len(set(names)):
        errors.append("duplicate component in inventory")
    return errors
