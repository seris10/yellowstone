"""Equation inventory: governing model and limits per component."""
from __future__ import annotations

from pathlib import Path

ENTRY_FIELDS = ("component", "module", "model_level", "equations",
                "variables", "units", "assumptions", "limits",
                "validation_status")

COMPONENTS = [
    {'component': 'rainbow geometric display',
     'module': '../../yellowstone_midway/scripts/atmosphere_optics.gd',
     'model_level': 'spherical-drop stationary ray geometry and authored finite rain curtain',
     'equations': 'cos(i)^2=(n^2-1)/((k+1)^2-1); r=asin(sin(i)/n); D=k*pi+2*i-2*(k+1)*r; radius=abs(pi-D); '
                  'energy=mean((1-Rs)^2*Rs^k,(1-Rp)^2*Rp^k); '
                  'tau_next=target+(tau-target)*exp(-dt/timescale)',
     'variables': 'n: refractive index; k: internal reflection count; Rs,Rp: Fresnel power reflectance; '
                  'tau: rain-curtain optical-depth proxy',
     'units': 'angles rad; time s; dimensionless optical depth',
     'assumptions': 'three authored representative visible-water indices; secondary radiance divided by '
                    'angular solid-angle width; local forcing drives remote cylindrical curtain; liquid '
                    'history and cloud transmission gate illumination',
     'limits': 'no calibrated frequency, measured regional rain field, full Mie scattering, nonspherical '
               'droplets or terrain shadows at remote curtain; display Gaussian and radiance gain authored',
     'validation_status': 'native_independent_Snell_sweep_history_and_negative_cases_tested_not_field_validated'},
    {'component': 'cloud slab display',
     'module': '../../yellowstone_midway/shaders/yellowstone_cloud_shell.gdshader',
     'model_level': 'four-sample authored cloud-layer optical column',
     'equations': 'tau=3.4*density*mean(body*vertical_profile)/max(ray_y,0.15); '
                  'alpha=(1-exp(-tau))*opacity*horizon_fade; body=thresholded_cached_three_octave_Simplex_noise',
     'variables': 'body: authored cloud density; ray_y: view elevation sine; vertical_profile: softened '
                  'slab edges; tau: optical-depth proxy',
     'units': 'cloud geometry m; optical depth dimensionless',
     'assumptions': 'horizontal layer; analytic height intersections rendered at sky depth; weather '
                    'supplies base, thickness, cover and drift; camera far plane does not bound cloud '
                    'altitude',
     'limits': 'no cloud microphysics or multiple scattering; shape and radiance authored; sky-depth layer '
               'assumes terrain below cloud base',
     'validation_status': 'native_cloud_visibility_and_sun_occlusion_checks_not_field_validated'},
    {'component': 'spring image-informed display',
     'module': '../../yellowstone_midway/data/display/prismatic.json',
     'model_level': 'authored image-informed radial color profile and band-limited terrace relief',
     'equations': 'E(r)=lerp(sRGBdecode(c_i),sRGBdecode(c_j)); terrace relief is an eight-harmonic '
                  'softened sawtooth plus 17 m low-amplitude waviness',
     'variables': 'r: normalized mapped polygon radius; c_i: supplied image color; terrace spacing 6.5 m '
                  'and height scale 0.065 m',
     'units': 'linear RGB; m',
     'assumptions': 'image samples have unknown camera response and illumination; ring stops and terrace '
                    'wavelengths authored; no terrain rescaling',
     'limits': 'display-only lookup does not validate pigment species, optical radiometry, measured band '
               'widths or subpixel terrain; published scientific fields unchanged',
     'validation_status': 'analytic_gradient_and_transform_checks_not_field_validated'},

    {
        "component": "daylight sky display",
        "module": "../../yellowstone_midway/shaders/physical_daylight.gdshader",
        "model_level": "three-band plane-parallel single scattering with Rayleigh, aerosol, and ozone optical depths",
        "equations": "I=(exp(-tau/mu_s)-exp(-tau/mu))/(1-mu/mu_s); limit at mu=mu_s is tau/mu*exp(-tau/mu); phase_R=3*(1+cos(theta)^2)/(16*pi); Henyey-Greenstein aerosol phase",
        "variables": "mu: viewing elevation sine; mu_s: solar elevation sine; tau: total vertical optical depth; tau_R: molecular scattering; tau_M: aerosol scattering; tau_O: ozone absorption",
        "units": "dimensionless optical depth; scattering 1/m; representative wavelengths 680, 550, 440 nm",
        "assumptions": "Rayleigh reference spectrum from Bruneton atmospheric reference; 8000 m molecular scale height; 2200 m elevation; effective lower scattering slab with incident sunlight attenuated by the upper ozone column; authored aerosol column and display exposure",
        "limits": "multiple scattering, curved horizon, and measured local aerosol spectrum absent; grazing angle clamped; display radiance normalized by luminance; no photometric calibration",
        "validation_status": "native_blue_zenith_weather_and_day_night_checks_not_field_validated",
    },
    {
        "component": "pool optical display",
        "module": "thermal_features/microbial_mats.py",
        "model_level": "three-band continuum approximation of Nugent et al. (2015), doi:10.1364/AO.54.00B128",
        "equations": "k=2a+b; T=exp(-k*z); E/Esun=Rw*Esky/Esun+(1-Rw)^2*(Rmat*T+(b/2)*(1-T)/k)",
        "variables": "a: absorption; b: total scattering; z: equal down/up depth; Rw: surface reflectance; Rmat: linear-light bottom reflectance proxy",
        "units": "a and b 1/m; z m; reflectance and normalized irradiance dimensionless",
        "assumptions": "equal forward/backward scattering; Lambertian bottom; no direct sun glint; Grand Prismatic yellow bottom and conical optical depth per Nugent Section 3A; authored sRGB palette decoded before transport; one sRGB encoding for texture storage",
        "limits": "three representative wavelengths; authored scattering and palette; no local spectral or viewing-angle calibration",
        "validation_status": "analytical_limits_and_independent_quadrature_tested_not_field_validated",
    },
    {
        "component": 'six-reach mixing chain',
        "module": "river/reach_reference.py",
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
        "component": "1-D advection-dispersion replay",
        "module": "river/river_transport.py",
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
        "module": "river/surface_flux.py",
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
        "module": "thermal_features/plume.py plume_field via river/plume2d.py",
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
        "module": "thermal_features/pool_crust.py",
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
        "module": "land/vegetation.py",
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
        "module": "aquatic/fish.py",
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
        "module": "aquatic/fish.py place_trout_at_chainage",
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
        "module": "land/grazers.py",
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
        "component": "replay solute transport",
        "module": "river/solute_transport.py",
        "model_level": "1-D advection-dispersion on chainage cells, "
                       "backward Euler, three conservative solutes",
        "equations": ("V_i dC_i/dt = Q_j C_upwind - Q_{j+1} C_i "
                      "+ G_j (C_left - C_right) + sum(Q_l C_l)"),
        "variables": ("C_i: cell concentration mg/L or ug/L; Q: face "
                      "discharge m3/s; G: dispersive conductance m3/s; "
                      "Q_l C_l: lateral source mass flux"),
        "units": "concentration mg/L or ug/L; discharge m3/s",
        "assumptions": "chloride and boron conservative; arsenic conservative in scope",
        "limits": "no photochemistry, no pH-driven sorption cycling",
        "validation_status": "fitted_not_validated_single_window",
    },
    {
        "component": "river dissolved oxygen",
        "module": "aquatic/river_oxygen.py",
        "model_level": "implicit upwind reach with Covar reaeration regime",
        "equations": ("V_i dC_i/dt = Q (C_up - C_i) + V_i k2 (C_sat - C_i) "
                      "+ V_i (GPP - R); C_sat Benson Krause 1984"),
        "variables": ("C_i: DO mg/L; k2: reaeration 1/day; GPP, R: "
                      "periphyton metabolism mg O2 per L per s"),
        "units": "concentration mg/L; rate 1/day; metabolism mg/L/s",
        "assumptions": "ice free surface; Covar regime selects formula",
        "limits": "no sediment oxygen demand; no reactive transport",
        "validation_status": "illustrative_not_validated",
    },
    {
        "component": "periphyton biomass",
        "module": "aquatic/periphyton.py",
        "model_level": "logistic biomass with Platt-Jassby light response "
                       "and Eppley temperature factor",
        "equations": ("dB/dt = (P_max tanh(I/Ik) f_T(T) f_shade(B) "
                      "- R(T, B) - G(B, grazer)) B"),
        "variables": ("B: biomass mg C/m2; P_max: specific GPP 1/day; "
                      "Ik: saturation light W/m2; I: PAR W/m2"),
        "units": "biomass mg C/m2; light W/m2; rates 1/day",
        "assumptions": "photosynthetic quotient 1.2; Eppley slope 0.0633 per C",
        "limits": "no nutrient dynamics beyond authored factor; no sloughing event",
        "validation_status": "illustrative_not_validated",
    },
    {
        "component": "river shading",
        "module": "aquatic/river_shading.py",
        "model_level": "DEM horizon sampling with canopy direct beam blocking",
        "equations": ("shortwave_multiplier = 0.8 direct_beam_fraction "
                      "+ 0.2 sky_view_factor"),
        "variables": ("sky view factor: hemispherical integral of blocked "
                      "sky; direct beam fraction: canopy transmissivity "
                      "along sun bearing"),
        "units": "dimensionless multipliers",
        "assumptions": "0.8 direct 0.2 diffuse clear-sky midday split (Reindl 1990)",
        "limits": "aerosol and multiple scattering absent",
        "validation_status": "illustrative_not_validated",
    },
    {
        "component": "ground heat flux and soil temperature",
        "module": "thermal_features/ground_heat.py",
        "model_level": "mask-selected heat flux with steady conductive profile",
        "equations": ("T(z) = T_surface + Q z / k capped at local boiling "
                      "point; melt_mm_d = Q / (rho_water L_f) in mm/day"),
        "variables": ("Q: ground heat flux W/m2; k: sinter conductivity "
                      "W/m/K; z: depth m; L_f: latent heat of fusion J/kg"),
        "units": "flux W/m2; conductivity W/m/K; depth m; melt mm/day",
        "assumptions": "steady state; boiling cap at FAO-56 Eq 7 pressure",
        "limits": "no transient heat storage; no fumarole venting",
        "validation_status": "authored_profile_not_validated",
    },
    {
        "component": "reference evapotranspiration",
        "module": "land/evapotranspiration.py",
        "model_level": "FAO-56 Penman-Monteith reference and Kc crop coefficients",
        "equations": ("ET0 = (0.408 Delta (Rn - G) + gamma 900/(T+273) u2 "
                      "(es - ea)) / (Delta + gamma (1 + 0.34 u2))"),
        "variables": ("Delta: slope svp kPa/C; gamma: psychrometric kPa/C; "
                      "Rn: net radiation MJ/m2/day; es, ea: svp and vapor "
                      "pressure kPa; u2: wind at 2 m m/s"),
        "units": "ET0 mm/day; temperature C; radiation MJ/m2/day; wind m/s",
        "assumptions": "short grass reference; Kc authored per patch type",
        "limits": "no stress formulation beyond relative soil water scaling",
        "validation_status": "fao56_example_18_match",
    },
    {
        "component": "piscivore predation",
        "module": "aquatic/piscivores.py",
        "model_level": "per predator Holling II with depth refuge factor",
        "equations": ("mortality = sum_i density_i intake_i(N) share_i "
                      "exp(-depth / depth_scale_i) / N"),
        "variables": ("density: per m river; intake: per capita per day; "
                      "share: size class fraction; depth_scale: m"),
        "units": "mortality 1/day; density 1/m; depth m",
        "assumptions": "authored illustrative densities; exponential depth refuge",
        "limits": "no spatial pursuit; no diel visitation",
        "validation_status": "illustrative_not_validated",
    },
    {
        "component": "aerial insectivores",
        "module": "insects_birds.py AERIAL_INSECTIVORE_DIETS",
        "model_level": "Holling II offtake on emergent prey compartment",
        "equations": "C(N) = aN/(1 + ahN) with per-consumer attack and handling",
        "variables": ("N: emergent prey density; a: attack rate; h: "
                      "handling time per capita"),
        "units": "density dimensionless; time days",
        "assumptions": "swallow bat and riparian spider diet shares authored",
        "limits": "no breeding phenology; no colony-size dynamics",
        "validation_status": "illustrative_not_validated",
    },
    {
        "component": "outflow food web",
        "module": "thermal_features/outflow_foodweb.py",
        "model_level": "logistic brine fly recruitment with mite parasitism "
                       "and Holling II predators",
        "equations": ("dN/dt = r_max N (1 - N/K) - m(flow_cv) N "
                      "- sum predators Holling II; K from fly window and mat"),
        "variables": ("N: fly density per m2; m: mite parasitism rate 1/day; "
                      "flow_cv: outflow discharge CV; K: carrying density"),
        "units": "density 1/m2; rate 1/day",
        "assumptions": "Paracoenia and Ephydra windows below 40 C",
        "limits": "no spatial propagation; no sediment feedback",
        "validation_status": "transferred_structure_authored_rates",
    },
    {
        "component": "steam microclimate plume",
        "module": "atmosphere/steam_microclimate.py",
        "model_level": "bulk aerodynamic plume with internal boundary layer",
        "equations": ("Phi_s = rho c_h |U| (T_s - T_a); "
                      "Phi_e = rho L c_e |U| (q_s - q_a); "
                      "h_i = A z0 (fetch/z0)^B"),
        "variables": ("Phi_s, Phi_e: sensible and latent fluxes W/m2; "
                      "h_i: internal boundary layer m; A, B: authored "
                      "power-law coefficients"),
        "units": "flux W/m2; temperature C; humidity dimensionless; "
                 "fetch m; roughness m",
        "assumptions": "ice-free; flat terrain; shared surface flux defaults",
        "limits": "no three dimensional advection; no convective plume",
        "validation_status": "transferred_structure_authored_rates",
    },
    {
        "component": "invertebrate taxa foodweb",
        "module": "aquatic/aquatic_foodweb.py run_taxon_foodweb",
        "model_level": "per taxon degree day emergence with DO survival ramp",
        "equations": ("B_new = B exp(-decay dt) + emergence(T, dd); "
                      "survival = ramp(DO, lethal, sensitive); "
                      "grazer competition = 1 + weight mudsnail density"),
        "variables": ("B: taxon biomass; dd: degree days above tbase; "
                      "DO: oxygen mg/L; mudsnail density: competitor state"),
        "units": "biomass dimensionless; time days; DO mg/L",
        "assumptions": "Davis 1975 DO anchors; Mackey 1977 chironomid envelope",
        "limits": "no life stage structure; no drift",
        "validation_status": "illustrative_not_validated",
    },
    {
        "component": "snow and soil water",
        "module": "land/snow_season.py",
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


COMPONENTS.append({
    "component": "mammal guild ecology",
    "module": "land/mammals.py",
    "model_level": "bounded authored population equivalents with habitat, resource, weather and predator-prey response",
    "equations": "activity = food*water_access*thermal_response*snow_access*season*diel; birth = N*(1-N)*(1-exp(-birth_rate*activity*dt/year)); mortality and predation remove bounded fractions using exponential hazards; forage_consumed = min(available_stock, authored_demand)",
    "variables": "N: authored population equivalent per species and patch; activity: relative index; dt: physical elapsed seconds; rates: authored per-year hazards; forage: normalized vegetation biomass index",
    "units": "time s; hazard 1/year; population and vegetation relative indices",
    "assumptions": "primary park occurrence records constrain roster; habitat traits, local populations, resource conversion, hazards and display encounter probabilities are authored",
    "limits": "no field-fitted local abundance, mortality, energy transfer or sighting frequencies; observation encounters are separate from ecological populations; unconfirmed and unsuitable local taxa are gated",
    "validation_status": "bounded_response_and_checkpoint_replay_tested_not_field_validated",
})

COMPONENTS.append({
    "component": "lodgepole branch architecture",
    "module": "authoring/tree_architecture.py",
    "model_level": "rooted geometric branch graph with constrained stochastic lateral growth units",
    "equations": "LCW_ft = -1.1994 + 1.5154*D_in - 0.0232*D_in^2; radius_m = 0.3048*LCW_ft/2; branch stations and shoots sampled from explicit bounded authored distributions",
    "variables": "D_in: DBH in inches; LCW_ft: mean horizontal crown diameter in feet; graph axes and shoot vectors in meters",
    "units": "length m; DBH in; source crown diameter ft",
    "assumptions": "Bechtold (2004) Table 3 Equation 3 transfers regional stand-grown lodgepole relationships; original LiDAR core and source DBH/CR are retained separately",
    "limits": "crown equation only within DBH 5.0 to 62.2 in; unknown local error; photographs have unknown scale and camera pose; branch survival, foliage volume, leaf area and biomass are not locally calibrated",
    "validation_status": "graph_connectivity_and_repeatability_tested_not_field_validated",
})


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






IMPLEMENTATION_DETAILS = {'hydro_thermal.run_simulation': 'Run fixed-dt transport (physical seconds). air_c may be const or fn(t). Ledger carries full budget history (cumulative in/out/exchange/storage).', 'steam_microclimate.module': 'Downwind microclimate adjustment from hydrothermal plume heat and vapor, with fog and rime diagnostics.', 'steam_microclimate.internal_boundary_layer_m': 'Diffusion-type internal boundary layer depth as reviewed by Garratt (1990) BLM 50:171.\n h_i = IBL_COEFFICIENT_A * z0 * (fetch/z0)**IBL_EXPONENT_B; raises outside [FETCH_MIN_M, FETCH_MAX_M].', 'steam_microclimate.downwind_adjustment': 'Downwind air-temperature and humidity adjustment from a plume source.\n Residence time is sqrt(source_area_m2)/wind; internal boundary layer depth grows with fetch (Garratt (1990)).', 'steam_microclimate.plume_microclimate_adjustment': 'Combined pool and outflow plume adjustment on downwind air temperature and humidity.\n latent_flux_outflow_w_m2 overrides the outflow latent flux; pass the replay.surface_flux value when available.', 'groundwater_provider.authored_reaches_to_sources': 'Per-receiving-cell lateral dicts from authored reach inflows.\n Flow is positive out of the aquifer into the river; MF6 RIV budget per Langevin et al. (2017) USGS 6-A55 ch 6.', 'outflow_foodweb.outflow_cell_population': 'Steady-state fly population on a mat cell under logistic recruitment, mite parasitism and Holling II predation.\n Solves r_max*(1 - N/K) = mite_rate*N + holling_ii(N) for N by bisection in [0, K].', 'outflow_foodweb.outflow_foodweb_from_files': 'Reduce real model artifacts to per-cell fly populations.\n Reads outflow_temperature.json + its .f32 raster, and mat_state.json + its community int16 raster, per interfaces.md.', 'piscivores.module': 'Trout predation by piscivorous birds and river otter, with a depth-refuge term and a Holling type II response.', 'microclimate.prevailing_direction': 'Compass degrees of the low-frequency prevailing wind (no gust). Direction is the direction air moves toward (+X=east, -Z=north).', 'microclimate.condensation_potential': 'Vapor-pressure proxies for condensation visibility.\n evap_pressure_index_kpa_weighted is wind-weighted; supersat_pressure_kpa and relative/mixed terms are pressure proxies.', 'microclimate.wind_series': 'Seeded Ornstein-Uhlenbeck gusts around the prevailing vector.\n sigma = 0.55 * gust_mps; samples are unbounded; max_samples caps allocation.', 'hydrology_provider.module': "Cached hydrosim run on Midway terrain.f32 that reports soil wetness from caller rain.\n\nground_wetness_fraction is the overland-runoff authority; snow_season's per-patch bucket is the phenology authority.", 'review_proposals.module': 'Machine review gate for planting proposals to placement_overrides.json.\nChecks: thermal/water exclusion, slope cap, suitability floor, pairwise spacing, existing-stand proximity.', 'canopy_census.density_stats': 'Trees/ha per named zone.\n Zone spec: circle (cx,cz,r); ring (cx,cz,r0,r1); box (x0,z0,x1,z1). Records are dicts or (x,z) tuples.', 'canopy_census.detect_v2': 'Peaks plus area-based top-up: blobs larger than lone trees are split to their area-implied stem count. Each record carries splitting_basis: peak | area_topup.', 'overland_flow.run_overland': 'Drive hydrosim on the midway terrain and return a renderable field.\n Field is surface-water depth in meters (dst x dst, row-major); empty when hydrosim or numpy is absent.', 'compare.module': 'A/B outcome comparison between two build dirs: endpoint deltas plus a compatibility report.\nTrajectory mode reads replay frames for exposure and peak metrics; endpoint mode uses outcome records.', 'compare._interpretation': 'Named uncertainty, calibration and significance context.\n difference_significance ranks the largest reach delta against calibration rmse; absence yields not_assessed.', 'overland_provider.predict_discharge': 'Runoff-coefficient discharge with an authored symmetric band.\n routing_tau_s optionally lags through a linear reservoir; runoff_temperature_c records a scenario value.', 'overland_provider.predict_discharge_landlab': 'Landlab-routed drainage area feeding the discharge interface.\n Edges are closed; the chosen node is opened; an interior outlet is recorded as a sink.', 'periphyton.module': 'River periphyton compartment: biomass driven by light, temperature and nutrients, with grazing loss.\nLight response: Platt-Jassby saturation; temperature: Eppley Q10; oxygen metabolism via photosynthetic quotient.', 'exporters/godot_sidecars.module': 'Producers for Godot-side sidecar files from a published build directory.\nEach producer writes JSON with schema id, units and status, or raises MissingSourceError on absent inputs.', 'exporters/godot_sidecars.write_plume_field_json': 'Write a 2-D plume field sidecar from the mapped river state.\n Grid matches hydro_thermal.plume_map.png; traces to Excelsior mouth and Firehole bridge temperatures.', 'exporters/godot_sidecars.write_calibration_summary_json': "Reach heat fit scalars plus the observed USGS gauge trace.\n Searches derived/ when fit_path or obs_path is absent; trace reduces to the first gauge site's series.", 'exporters/godot_sidecars.write_pools_state_json': 'Per-pool thermal state exported for the Godot pool overlay.\n Reads pool_shells.json and emits center and edge temperatures per pool; status labels authored-steady and names the dynamic coupling that will replace it.', 'exporters/godot_sidecars.write_snow_cover_sidecar': 'Per-patch snow_cover_fraction sidecar ( ).\n Prefers the explicit snow_cover_fraction field in season.json; otherwise derives it from snow_depth_m via SNOW_COVER_FULL_DEPTH_M.', 'exporters/godot_sidecars.validate_weather_snapshot_doc': "Return a list of validation errors; empty means the doc passes the Godot reader's gates.\n Mirrors weather_snapshot_reader.gd checks for schema version, timestamps, required weather fields, and ranges.", 'validation/claims.module': 'Skill gates for the seed thermal and snow claims: each evidence fit must beat its recorded null models.\nThermal: champion holdout rmse in the reach fit artifact; snow: per-site holdout SWE rmse.', 'validation/claims.check_reach_rmse': 'Reach gate for reach_water_temperature_ice_free: champion holdout rmse below every recorded null.', 'validation/claims.check_snotel_rmse': "Snow gate for snow_swe_clearings: each site's holdout SWE rmse below its persistence and no-melt nulls.\n Evidence without per-site holdout rmse and both nulls fails.", 'pipeline/stages/thermal._run_outflow_chain': "Load the model outflow network and run model's temperature chain at start_epoch_s (UTC seconds).\n Returns network, rasters, DEM, outflow raster and sidecar, mat state, insolation and forcing records.", 'pipeline/stages/thermal._excelsior_lateral_override': "Discharge-weighted river-entry lateral override for the Excelsior reach.\n Aggregates every spring's Q times river_inflow_fraction and takes the Q-weighted mean of its outflow temperature across wet cells adjacent to the Firehole mask.", 'pipeline/stages/river._hyporheic_zones_dict': 'Per-cell hyporheic zone dict with authored Bencala and Walters defaults.\n cfg.enabled false yields an empty dict; cfg.storage_volume_fraction and alpha_per_s override authored values.', 'pipeline/stages/vegetation._canopy_from_census': 'Canopy fraction in a circle from census.json crowns, or the fallback.\n Returns (canopy_in_[0,1], source_label); crown-area sum is an upper bound since overlaps are not deducted.', 'gen_flora.module': 'Flora density pass: generate, machine-review, and stage grass and pine infill.\nRecords land in placement_overrides.json::{add} for the next bake; placements.json is left alone.', 'hydro_thermal.steady_state': 'Exact fixed point of the mixing step: T*i = (Qin*Tup + sum QlTl + (V/tau)*Tair) / (Qout + V/tau).\n Feedforward chain, so a single upstream-first pass is exact.', 'steam_microclimate.plume_sensible_flux_w_m2': 'Bulk-aerodynamic sensible flux from a hot water surface into the air (W/m2).\n Positive when the surface is warmer than air; wind is floored at replay.surface_flux.WIND_FLOOR_MPS.', 'steam_microclimate.plume_latent_flux_w_m2': 'Bulk-aerodynamic latent flux from the water surface into the air (W/m2).\n Vapor-pressure deficit sets the direction; wind is floored at replay.surface_flux.WIND_FLOOR_MPS.', 'groundwater_provider.module': 'Authored lateral inflows mapped to river Source dicts.\nhead_gradient_exchange returns gaining-reach solver sources and a separate losing-reach record list.', 'outflow_foodweb.recruitment_per_m2_per_day': 'Logistic recruitment onto 1 m2 of mat per day.\n r_max * max(0, 1 - N/K) with r_max = carrying/generation; falls to zero as density reaches carrying.', 'insects_birds.step_compartments': 'Advance {Nt, Nb, Ne} one step.\n Returns (new_state, ledger{emergence, consumed_by, activity, state, wind_loss, disturbance_loss}).', 'snow_validate.module': 'validation: snow and soil-water model against NRCS SNOTEL observations.\nGrid-fits k_melt and wind_loss on a train split; reports holdout RMSE, bias, peak timing, two nulls.', 'exporters/to_map.reproject_to_macro': 'Copy a field PNG whose grid is the macro frame; verify its pixel size.\n expected_size_px is required in production; the optional default keeps the stub call site working.', 'exporters/to_ecosystem.merge_fragments': 'Return a deep-copied ecosystem dict with fragments merged in.\n humidity and cloud lift to the top level for ecosystem.gd; boundary_* carry solver upstream forcing.', 'exporters/to_ecosystem.validate_for_godot': 'List contract violations ecosystem.json would hit in Godot.\n An empty list means ecosystem.gd, thermal_probe_overlay.gd, and python_river_replay.gd read it fine.', 'pipeline/stages/river.check_cross_sections': 'Validate cross-sections against world river features; returns a report.\n Status is covers when every ecosystem river feature has a profile; otherwise lists missing/unknown.', 'pipeline/stages/river._run_solute_transport': 'Advance solute transport across replay cells; return (summary doc, per-cell concentrations dict).\n An empty mapped-sources replay returns an empty concentrations dict.', 'pipeline/stages/land._overland_runoff_to_boundary': 'Convert the overland outlet volume into a mean boundary discharge in m3/s.\n Returns (rate_m3_s, report); rate_m3_s is 0 when no outflow was produced or sim_s is nonpositive.'}
