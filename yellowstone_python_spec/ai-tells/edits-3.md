Update the three AI tell audit docs to include the proposed fixed comment wording alongside the original comments and AI tell annotations. Do NOT delete any existing content.

**For each file below, read it, then add a "Proposed Fix" column to the existing tables and/or add a "Proposed Fixes" section at the end.**

### File 1: `/Users/kreed/Downloads/yellowstone_python_spec/ai-tells/ai-tells-1.md`

Add a new section at the end titled "Proposed Comment Fixes" with a table mapping each AI tell to its proposed replacement:

| File | Line | Original (AI TELL) | Proposed Fix |
|------|------|-------------------|--------------|
| analysis_store.py | L1-41 | 41-line module docstring | `"""SQLite-backed analysis store for derived artifacts. Read-only queries over allow-listed tables/columns."""` |
| analysis_store.py | L56-58 | `# Unit factors, stated once (see module docstring)...` | `# Unit factors: SNOTEL stores WTEQ/PRCP/SNWD in inches, TAVG/TMAX/TMIN in degF.` |
| analysis_store.py | L355-360 | `"""Build a store file from ONE build dir...` | `"""Build a store file from one build dir + obs inputs. Atomic write. Refuses to overwrite existing files."""` |
| analysis_store.py | L434-435 | `# Single source of truth for circle-radius bounds...` | `# Circle-radius bounds single-sourced here; llm_backend aliases these.` |
| analysis_store.py | L586 | `filters[k] = v  # validated; consumed below (was: dropped)` | `filters[k] = v  # validated; consumed below` |
| analysis_store.py | L633-638 | `"""Circle crown count via the R-tree...` | `"""Circle crown count via R-tree. Used by /api/density when a store file is present."""` |
| aquatic_foodweb.py | L1-23 | 23-line module docstring | `"""Multi-day insect + trout + dipper dynamics on a thermal landscape."""` |
| aquatic_foodweb.py | L57-64 | `"""Per-cell quasi-steady thermal + hydraulic habitat...` | `"""Per-cell quasi-steady thermal + hydraulic habitat from replay frames. t_min_s/t_max_s restrict to a window for intervention comparison."""` |
| aquatic_foodweb.py | L130-142 | `"""Multi-day insect + trout + dipper dynamics...NOTE (2026-10-10)...` | `"""Multi-day insect + trout + dipper dynamics. shear_disturbance ramps 0 at threshold to 1 at twice it. None shear maps to zero; None threshold switches coupling off. Default 20 Pa."""` |
| aquatic_foodweb.py | L151-155 | `# Consumption runs on HOURLY substeps...` | `# Consumption runs on HOURLY substeps. Daily-step Holling demands saturate and collapse competition to a fixed split.` |
| aquatic_foodweb.py | L203-210 | `# Consumption at the refuge cell...verified failure, Oct 2026.)` | `# Consumption at the refuge cell. Exploitative competition on HOURLY substeps: demands computed from the same pre-consumption stocks, scaled pro-rata if combined demand exceeds availability. Sequential ordering would hand the outcome to whoever eats first.` |
| aquatic_foodweb.py | L240-242 | `# Adult turnover...verified failure, Oct 2026).` | `# Adult turnover: emergent insects die/disperse within days (authored mean residence ne_turnover_days).` |
| aquatic_foodweb.py | L331-332 | `window_note = ("full-run means; short pulses are diluted — "...` | `window_note = ("full-run means; short pulses are diluted. "...` |
| build.py | L1-17 | Module docstring with audit references | `"""Build pipeline: runs all modules and writes derived artifacts."""` |
| build.py | L257-260 | `"godot_divergence_note": ("...— residual documented, not hidden")` | `"godot_divergence_note": ("...Residual documented.")` |
| build.py | L290 | `# --- M01b 1-D advection-dispersion replay (Phase 2 flagship) ---` | `# --- M01b 1-D advection-dispersion replay ---` |
| build.py | L293-296 | `# --- M05b aquatic food web (audit Phase 2 vertical slice)...` | `# --- M05b aquatic food web: replay heat -> insect prey -> trout refuge -> dipper intake, 14-day run ---` |
| canopy_census.py | L1-22 | Module docstring | `"""Canopy census: detect trees from NAIP imagery and produce stable records."""` |
| canopy_census.py | L196 | `"""Record x/z: dict key or tuple index — both call sites use either."""` | `"""Record x/z: dict key or tuple index."""` |
| canopy_census.py | L332-334 | `"""Measure single isolated crowns...the ruler every larger blob is split against."""` | `"""Measure single isolated crowns: components with no neighbor centroid within isolation_m."""` |
| canopy_census.py | L369-372 | `"""v1 peaks PLUS area-based top-up...` | `"""Peaks plus area-based top-up: blobs larger than lone trees are split to their area-implied stem count. Each record carries splitting_basis: peak | area_topup."""` |
| exporters/to_map.py | L6-9 | `"""Phase 0: fields are already authored...` | `"""Fields are already authored in macro extent; plain copy."""` |
| fish.py | L1-21 | 21-line module docstring | `"""Trout thermal suitability and refuge selection."""` |
| fish.py | L35-43 | `# Cold-water trout thermal optimum band...LEGACY...New work uses...` | `# Cold-water trout thermal optimum band (illustrative). Two-sided: below the band is too cold, above is stressful. A one-sided penalty cannot discriminate reaches all below 20 C. Kept for ecosystem.gd parity. THERMAL_SPECIES + thermal_performance() provides the literature-based path.` |
| fish.py | L48-75 | Large comment block about literature-transferred thermal performance | `# Literature-transferred thermal performance. Anchor points from measurement; piecewise-linear shapes between them are authored.` |
| fish.py | L133-138 | `# --- Real-data integration point for laboratory thermal measurements ---...` | `# Lab thermal measurements integration point. REAL_LAB_DATA_PATH = None  # Set to file path when measurements are available.` |
| fish.py | L141-148 | `"""Load real laboratory thermal-performance measurements...` | `"""Load laboratory thermal-performance measurements. Returns dict with measured curves, or None if no real data is configured."""` |
| fish.py | L155-157 | `# Integration hook: read measured curves here...` | `# Returns None until real data path is configured.` |
| fish.py | L184-188 | `"""Two-sided preference in [0, 1]...LEGACY...new work uses...` | `"""Two-sided preference in [0, 1]: 1.0 inside the optimum band, falling linearly to 0 outside. Kept for ecosystem.gd parity; thermal_performance() provides the literature path."""` |
| fish.py | L201-210 | `"""Nondimensional U: preferred velocity/depth ranges...` | `"""Nondimensional U: preferred velocity/depth ranges, two-sided thermal preference. species=None keeps the authored band; a species name selects the literature performance path."""` |
| fish.py | L219-222 | `# Feeding loss saturates at feed_zero...backwards).` | `# Feeding loss saturates at feed_zero; stress keeps the gradient worsening with temperature above it.` |
| fish.py | L231-240 | `"""Literature-anchored performance at one water temperature...` | `"""Literature-anchored performance at one water temperature. Returns {feeding, stress, refuge_drive, lethal_flag} in [0, 1]. Anchor points from measurement; piecewise-linear shapes authored. refuge_drive from Kaya et al. 1977. lethal_flag marks water above UILT; shelter, never mortality."""` |
| fish.py | L276 | `"""Nearest reach by z — mirrors ecosystem.gd::reach_at (kept for runtime)."""` | `"""Nearest reach by z. Mirrors ecosystem.gd::reach_at."""` |
| fish.py | L290-297 | `"""Per-point reach id table...the old assign_reach path...` | `"""Per-point reach id table using the declared upstream chain order. z-nearestness fails for looping or U-shaped channels. Walk the declared chain and assign every point to the reach whose z-window contains it."""` |
| fish.py | L378-383 | `"""Move the holding window toward max suitability...` | `"""Move the holding window toward max suitability within swim range. Returns {start,end,reach_id,U,reason}. Window length preserved; river route never redrawn through unlisted water."""` |
| fish.py | L498-501 | `"""Deterministic refuge map...no hashes, no RNG...` | `"""Deterministic refuge map: Firehole centerline in world position, pool polygons, trout holding midpoints + selected-refuge markers. Every dot is a world coordinate; reproducible across processes and seeds."""` |
| gen_flora.py | L124-126 | `"""Truly bare pale ground...the old mask gate."""` | `"""Truly bare pale ground (bright AND greenless). Vegetated bright slopes fail this test and stay plantable."""` |
| gen_flora.py | L481-485 | `"""Art-directed density ring around the overlook deck...Answers the visible-hill sparseness...` | `"""Art-directed density ring around the overlook deck. Planted where slope is walkable and ground is not water, sinter apron, trail, or road. Ledger-marked as enhancement."""` |
| grazers.py | L1-17 | Module docstring | `"""Bison/elk habitat-constrained movement."""` |
| grazers.py | L50 | `"""Waypoints alone miss crossings — sample the full segment."""` | `"""Sample the full segment; waypoints alone miss crossings."""` |
| grazers.py | L60-62 | `"""Rich patch -> longer graze...not absolute index — patches...` | `"""Rich patch -> longer graze; poor patch -> sooner walk. Driven by fraction of capacity, not absolute index."""` |
| grazers.py | L117-127 | `"""8-connected A* with Euclidean heuristic...` | `"""8-connected A* with Euclidean heuristic on an eligibility grid. Endpoints must be unblocked. Returned waypoints are cell centers. Each accepted step is re-sampled along its true segment and rejected if any sample is blocked."""` |
| hydro_thermal.py | L129-133 | `"""Run fixed-dt transport...Ledger now carries FULL budget history...` | `"""Run fixed-dt transport (physical seconds). air_c may be const or fn(t). Ledger carries full budget history (cumulative in/out/exchange/storage)."""` |
| insects_birds.py | L1-18 | Module docstring | `"""Three-compartment prey + bird diets."""` |
| insects_birds.py | L76-81 | `"""LEGACY interface: retune dipper/raven cadence...` | `"""Retune dipper/raven cadence from shared activity. Kept because wildlife_actor.gd reads timer values from records. Prefer update_wildlife_from_intake() for intake-driven timing."""` |
| insects_birds.py | L95 | `# --- Three-compartment prey dynamics (the actual model) ---` | `# --- Three-compartment prey dynamics ---` |
| insects_birds.py | L109-116 | `"""Benthic larvae: degree-day development...legacy no-ceiling path."""` | `"""Benthic larvae: degree-day development -> emergence flux; flood/hydraulic disturbance removes a fraction. Returns (nb_new, emergence). t_cutoff: development stupor above this temperature, dd forced to 0. None keeps the no-ceiling path."""` |
| insects_birds.py | L130-144 | Large comment block about benthic insect groups | `# Benthic insect groups: transferred thermal structure. Relative rates (dipteran faster, multivoltine) are an authored ordering.` |
| insects_birds.py | L170-178 | `"""Trout benthic-vs-emergent shares shift with temperature...documented limitation."""` | `"""Trout benthic-vs-emergent shares shift with temperature. Cold water: almost entirely benthic; warm water: heavily emerging (Kaeding & Kaya 1978). Linear transition 15 -> 21 C; shape authored, endpoints transferred. Molluscs not modeled."""` |
| llm_backend.py | L1-30 | 30-line module docstring | `"""HTTP backend for census analysis and proposal review. Stdlib only."""` |
| llm_backend.py | L61-66 | `ACCURACY_NOTES` list with cross-check narrative | `ACCURACY_NOTES = ["Pretrained DeepForest underdetects vs census (~1,175 crowns)."]` |
| llm_backend.py | L69-72 | `# Hardening limits (adversarial review 2026-10-09)...` | `# Density circles outside [MIN_RADIUS_M, MAX_RADIUS_M] are rejected. Bounds single-sourced from analysis_store.` |
| llm_backend.py | L186-192 | `"""Circle crown count, store-backed...cross-check test pins equality...` | `"""Circle crown count, store-backed when a store file exists. Store path and JSON path share one answer contract."""` |
| microclimate.py | L1-17 | Module docstring | `"""Microclimate: one wind/time authority. Condensation, not steam."""` |
| microclimate.py | L26-33 | `# --- Weather forcing provenance ---...STATUS:...` | `# Weather forcing: AUTHORED defaults (illustrative). fetch_met_forcing.py connects to Open-Meteo for measured forcing.` |
| microclimate.py | L51-56 | `"""Integration point: load real Open-Meteo forcing...` | `"""Load real Open-Meteo forcing for site. Returns met bundle dict or None if fetch fails / not configured."""` |
| microclimate.py | L88-89 | `"""LEGACY artistic index for the old Godot uniform path...` | `"""Artistic index for the Godot uniform path. Prefer condensation_potential() for analysis."""` |
| microclimate.py | L115-126 | `"""Evaporation flux + dew-point depression...cannot drift apart."""` | `"""Evaporation flux + dew-point depression + mixing supersaturation proxy. relative_supersaturation is the quantity the Godot renderer consumes. Same Magnus form and 30/70 entrainment ratio as ecosystem.gd::condensation_visibility."""` |
| microclimate.py | L167-171 | `"""Per-second (wind, air_c, hour) trace...(audit fix)...` | `"""Per-second (wind, air_c, hour) trace. Pass the FULL weather config so the trace cannot disagree with configured weather. With a seed, gusts come from the OU process; otherwise the sinusoid is used."""` |
| pool_crust.py | L44-46 | `# Base pigment bands...— there is no universal...` | `# Base pigment bands (fraction of r_water, color, meaning). Per-pool copies adjusted by make_ramp_stops(). Authored bands keyed to depth + gradient + substrate.` |
| pool_crust.py | L326 | `f"{shell['name']} — authored section (illustrative, not survey)"` | `f"{shell['name']} - authored section (illustrative, not survey)"` |
| replay/river_world.py | L57-63 | `"""Validate per-feature mean-depth profiles...never silently labeled...` | `"""Validate per-feature mean-depth profiles. Format: {feature_id: {"depth_m": positive float, "status": str}}. Unknown feature ids rejected."""` |
| replay/river_world.py | L251-255 | `"""Translate an old reach anchor...old six-reach display...` | `"""Translate a reach anchor, refusing ambiguous crossings. Exists for compatibility with the six-reach display."""` |
| replay/river_world.py | L628-631 | `"initial_condition": ("...not the legacy six-reach temperature snapshot.")` | `"initial_condition": ("Calculated steady state at t=0 forcing.")` |
| replay/uncertainty.py | L1-27 | Module docstring with "A1" reference | `"""Uncertainty quantification for the lumped reach fit and authored-knob sensitivity."""` |
| replay/uncertainty.py | L43-53 | `# --- Uncertainty quantification provenance ---...REAL DATA NEEDED:...` | `# All parameters AUTHORED (not derived from measurement error): ENSEMBLE_SEED, tol_frac, min_members, n_bootstrap, spinup_s, train_frac, band_level. Module reports fit ambiguity, not predictive calibration.` |
| replay/uncertainty.py | L133-139 | `"""Percentile bands + seeded-bootstrap...the Monte Carlo in this module."""` | `"""Percentile bands + seeded-bootstrap standard error of the edges. Bands are cross-member percentiles at each timestep. Bootstrap resamples members with replacement."""` |
| replay/uncertainty.py | L281-287 | `"""Median Manning-consistency-ratio response...must not silently change the sample."""` | `"""Median Manning-consistency-ratio response to z and n. Recomputes cell_hydraulics per recorded cell with one authored knob varied; cells where Manning is undefined stay excluded."""` |
| replay/uncertainty.py | L344 | `"""Full A1 pass: ensemble bands + coverage + fit OAT ranking."""` | `"""Full pass: ensemble bands + coverage + fit OAT ranking."""` |
| snow_season.py | L1-20 | Module docstring with "audit fixes" | `"""Snow season: weather state, snow accumulation/melt, and season tracking."""` |
| snow_season.py | L171-184 | `"""Advance snow + soil + phenology...fit hook for site-effective...` | `"""Advance snow + soil + phenology with a verified water ledger. thermal_test(x, z) -> True where ground is hydrothermal: those cells get the ground-heat melt flux. precip_mm_by_day optionally overrides the scalar. Returns (patches, ledger). Ledger residual must be ~0."""` |
| study_mode.py | L110-111 | `"about": "COUNTEREXAMPLE...Trout barely move — short-term..."` | `"about": "COUNTEREXAMPLE...Trout barely move. Short-term river response follows residence time and forcing, not air alone."` |
| vegetation.py | L32-35 | `# Per-guild coefficients: ARTIST/SCIENCE INPUTS...REAL DATA GAP:...Integration point:...` | `# Per-guild coefficients: authored inputs, not inferred from field data.` |
| vegetation.py | L53-60 | `# Real-data provenance for vegetation parameters...real_data_gap` | `# Coefficients are authored, not inferred from field data.` |
| vegetation.py | L127-136 | `"""Deterministic proposal grid+jitter...LEGACY wrapper...the old behaviour...` | `"""Deterministic proposal grid+jitter with per-guild min separation. Separation is best-effort here; prefer propose_plantings_reviewed() for enforced output. Preserves stable ids verbatim."""` |
| tools/audit_provenance.py | L16 | `# Exact vocabulary measured across derived/*.json (28 occurrences, 2026-10-10).` | `# Exact vocabulary measured across derived/*.json.` |
| tools/fetch_firehole_obs.py | L1-19 | Module docstring with em dash | `"""Fetch a frozen Firehole observation bundle for reach-scale calibration. All sources measured, all remote."""` |
| tools/fetch_snotel_obs.py | L1-29 | Module docstring with "parallel worker" | `"""Fetch a frozen SNOTEL observation bundle. Site selection and WY2026 window verified live."""` |
| tools/fetch_yellowstone_tributaries.py | L1-14 | Module docstring with "replacing the authored/temporary values" and "TASK COMPLIANCE:" | `"""Fetch real tributary data for cold-refuge implementation."""` |
| tools/fetch_yellowstone_tributaries.py | L62-67 | `"""Fallback data using the previous authored approach...` | `"""Fallback data. Returns: Dictionary with fallback tributary data"""` |
| tools/plot_fit.py | L1-8 | Module docstring with em dash | `"""Diagnostic PNGs from fit artifacts (Pillow only)."""` |
| tools/run_hot_lowflow_with_tributaries.py | L1-20 | Module docstring with task list | `"""Add tributary refuge cells to hot low-flow scenario."""` |
| tools/run_hot_lowflow_with_tributaries_v2.py | L1-24 | Module docstring with "replacing the authored/temporary values used in the previous implementation" | `"""Add tributary refuge cells to hot low-flow scenario using real USGS data."""` |
| tools/usgs_nwis.py | L1-18 | Module docstring with "earlier docstring versions advertised" | `"""Fetch USGS field measurements and time-series data for Firehole River sites. IV via waterservices; RDB returns [] since waterdata.usgs.gov moved to JS/HTML."""` |
| tools/usgs_nwis.py | L31-33 | `# Modern Water Services endpoint...The legacy /usa/nwis/iv/...` | `# Water Services endpoint for instantaneous values. Returns WaterML-JSON timeSeries schema.` |
| tools/usgs_nwis.py | L74-81 | `"""Fetch RDB-format data from NWIS...NOTE (Oct 2026)...currently unfetchable...` | `"""Fetch RDB-format data from NWIS. Returns list of dicts. waterdata.usgs.gov serves JS/HTML now, so this returns [] for field-measurement queries. IV via waterservices works."""` |
| tests/test_reach_notebook.py | L34-35 | `# NOTE: inverse crime — same forward model...` | `# Inverse crime: same forward model generates and fits. Proves the notebook machinery runs, not model validity.` |
| tests/test_llm_backend.py | L261 | `"""Adversarial finding #1: a corrupt census.json...` | `"""A corrupt census.json must not silently return"""` |
| requirements.txt | L6 | `# sympy is test-only (A4 Jacobian verification); the test skips where absent.` | `# sympy is test-only; the test skips where absent.` |
| requirements.txt | L8-9 | `# pandas is the obs-alignment backend (B1); NOT installed...— install it...` | `# pandas is the obs-alignment backend; NOT installed on the project interpreter (externally managed). Install it to flip the fit default.` |
| notebooks/reach_fit.ipynb | Markdown cell 1 | "Coarse-grid caveat...— the production tight ridge under-covers (A1)." | "Coarse-grid caveat: fallback top-5 spans distant fits, so wide bands cover easily. The production tight ridge under-covers." |
| notebooks/reach_fit.ipynb | Markdown cell 2 | "The fit must beat both nulls...— do not widen the ridge rule to hide it." | "The fit must beat both nulls on holdout. Bands describe fit ambiguity. If holdout coverage misses nominal badly, the error is structural bias (check residual lag-1), not parametric spread. Do not widen the ridge rule to hide it." |
| SECURITY_HARDENED_TRIBUTARY_IMPL.md | Entire file | Remove emojis, replace "TASK COMPLIANCE:" with "Implementation:", "SECURITY COMPLIANCE" with "Security", "PROVENANCE DOCUMENTATION" with "Provenance" | (Apply throughout) |
| TASK_1_TTRIBUTARY_COLD_REFUGE_SUMMARY.md | Entire file | Remove emojis, replace "Key Achievements" with "Summary", "Success Metrics" with "Results", "Critical Insights" with "Notes" | (Apply throughout) |

### File 2: `/Users/kreed/Downloads/yellowstone_python_spec/ai-tells/ai-tells-2.md`

Add a new section at the end titled "Proposed Document Fixes" with recommendations for each file:

| File | Issue | Proposed Fix |
|------|-------|--------------|
| improvements.md | 30+ AI tells: "I'd"/"I would" suggestions, "Yes." openers, "Crucially", "important distinction", em dashes, first-person narrative | Rewrite as a technical document. Remove all first-person narrative. Replace "I'd" with "The recommended approach is". Replace "Yes." openers with direct statements. Remove "Crucially", "importantly", "notably". Replace em dashes with periods. |
| addons.md | 10 AI tells: "I researched", "my implementation", "I would add next", em dashes | Rewrite as a technical document. Remove first-person narrative. Replace "I researched" with "Research areas:". Remove "my implementation". |
| waterway-research.md | 14 AI tells: first-person narrative, "my arithmetic", "I haven't verified", "your summary" | Rewrite as a research log. Remove first-person narrative. Replace "my arithmetic" with "calculated". Replace "I haven't verified" with "Unverified". Remove "your summary". |
| python-audit.txt | 28 AI tells: "My recommendation", "Important limitations/issues", "would make" hedging, first-person narrative | Rewrite as an audit report. Remove first-person narrative. Replace "My recommendation" with "Recommendation". Replace "Important limitations" with "Limitations". Replace "would make" with "requires". |
| 00_OVERVIEW_AND_VERDICT.md | 4 AI tells: em dashes, "You are doing", "Hand this to", "so you don't" | Replace em dashes with periods. Remove "You are doing the Yellowstone pilot." Remove "Hand this to art/acquisition." Replace "so you don't re-hunt" with "to avoid re-hunting". |
| 01_PYTHON_BUILD_SPEC.md | 13 AI tells: em dashes in section headings | Replace all em dashes in section headings with colons or periods. |
| 02_PREREQS_ASSETS_CHECKLIST.md | 7 AI tells: em dashes | Replace all em dashes with periods or colons. |
| 03_AUDIT_RESPONSE.md | 2 AI tells: em dashes | Replace em dashes with periods. |
| tooling-spec-*.md (9 files) | "Status: spec (authored...)" headers, "No code written; no deletions.", em dashes | Remove "Status: spec" headers. Remove "No code written; no deletions." lines. Replace em dashes with periods. |

### File 3: `/Users/kreed/Downloads/yellowstone_python_spec/ai-tells/ai-tells-3.md`

Add a new section at the end titled "Proposed Comment Fixes" with a table mapping each AI tell to its proposed replacement:

| File | Line | Original (AI TELL) | Proposed Fix |
|------|------|-------------------|--------------|
| scripts/ecosystem.gd | L3-6 | `## A reduced observational model, not a calibrated Yellowstone forecast.` etc. | `## Reduced observational model. Transport units: seconds, m3/s, m3, Celsius. Water geometry fixed. River internal heat flux paired. Unknown tributary flows omitted from ecosystem.json.` |
| scripts/ecosystem.gd | L25 | `# Kept for interface compatibility; transport is always 1:1.` | `# Transport is 1:1.` |
| scripts/ecosystem.gd | L75 | `# This compact model deliberately supports one chain, not arbitrary branching.` | `# Supports one chain.` |
| scripts/ecosystem.gd | L102 | `# Retain elapsed-time debt after a slow frame; never silently lose physical time.` | `# Retain elapsed-time debt after a slow frame.` |
| scripts/ecosystem.gd | L171 | `# Newton exchange is an illustrative lumped heat-loss term, not full surface physics.` | `# Newton exchange is a lumped heat-loss term.` |
| scripts/ecosystem.gd | L181 | `# Relative visual suitability only: this is not a mortality prediction.` | `# Relative visual suitability only.` |
| scripts/ecosystem.gd | L263 | `# Missing habitat cannot silently become the first patch.` | `# Missing habitat raises.` |
| scripts/ecosystem.gd | L267 | `# Artistic condensation visibility proxy; not a steam mass or thermal-hazard model.` | `# Artistic condensation visibility proxy.` |
| scripts/ecosystem.gd | L271-272 | `# Magnus form, same convention as yellowstone_python.microclimate so the two sides of the project cannot drift apart.` | `# Magnus form, same convention as yellowstone_python.microclimate.` |
| scripts/ecosystem.gd | L276-288 | 13-line comment block with CONDENSED DROPLETS, em dashes, "vapour", "legacy", "now matter" | `# Visible plume is condensed droplets. Mirrors yellowstone_python.microclimate.condensation_potential: entrained mixed parcel (30% surface-saturated, 70% ambient) is supersaturated when its vapor exceeds saturation. Returns relative supersaturation of the mixed parcel: (q_mix - es(t_mix)) / es_surf, bounded in [0,1]. Model output; renderer scales it (see STEAM_DENSITY_SCALE).` |
| scripts/python_river_replay.gd | L4-7 | `## Python owns river thermal state...` / `## Empty path preserves the original ecosystem.` etc. | `## Python owns river thermal state when replay_path is nonempty.` / `## Empty path uses the built-in ecosystem.` / `## Replay interpolation is presentation, not a second solver.` |
| scripts/python_river_replay.gd | L290 | `# Legacy z-only callers remain compatible. New fish calls use position.` | `# z-only callers use z; fish calls use position.` |
| scripts/world.gd | L2-3 | `## Runtime assembles only saved authored assets; it never scatters scenery or generates terrain.` | `## Runtime assembles saved authored assets.` |
| scripts/world.gd | L121-122 | `# Season switch alters surfaces only: snow cover from the published season.json. Without the sidecar every default keeps the legacy look.` | `# Season switch alters surfaces only: snow cover from season.json.` |
| scripts/world.gd | L402-403 | `# Condensation model (mirrors yellowstone_python.microclimate): humidity and wind now drive the plume, not just surface-minus-air.` | `# Condensation model (mirrors yellowstone_python.microclimate): humidity and wind drive the plume.` |
| scripts/wildlife_actor.gd | L3-5 | `## Original articulated shape proxies...` | `## Articulated shape proxies at approximate real dimensions.` / `## Routes and counts authored in JSON.` / `## Actors never sample new habitat at runtime.` |
| tools/bake_botany.gd | L2-4 | `## OFFLINE AUTHORING TOOL. Every clump has a fixed JSON record and identity.` etc. | `## Offline authoring tool. Every clump has a fixed JSON record and identity.` / `## Creates genus/guild shape proxies.` / `## Run after terrain changes: godot --headless --path . --script tools/bake_botany.gd` |
| tools/bake_world.gd | L2-3 | `## OFFLINE ONLY. Produces native .tscn/.res assets, not generated at play time.` | `## Offline only. Produces native .tscn/.res assets.` |
| tools/validate_walk.gd | L2-6 | `## Focused collision integration test, not whole-route or whole-park certification.` etc. | `## Focused collision integration test.` / `## godot --headless --fixed-fps 60 --path . --script tools/validate_walk.gd` / `## The player class supplies its capsule, floor angle, snap and safe margin.` / `## Acceleration/gravity driven by deterministic waypoint input.` |
| shaders/terrain.gdshader | L10-12 | `// snow_amount 0 preserves the legacy look...` | `// snow_amount 0 uses the default look; mask is world-extent with bare thermal holes.` |
| shaders/water.gdshader | L12-15 | `// ramp_mix 0 preserves the legacy two-color look...` | `// ramp_mix 0 uses the default two-color look. Ramp x=0 is hot center, x=1 outer rim.` |
| shaders/steam.gdshader | L10-11 | `// Camera-facing vapor cards advect in the shared WORLD wind...` | `// Camera-facing vapor cards advect in the shared world wind. Rotating the card must not rotate its wind direction.` |
| shaders/boardwalk.gdshader | L16-17 | `// Weathered-gray composite decking...Seams read as narrow shadow gaps, not black cuts.` | `// Weathered-gray composite decking, dark timber rails on bark_mat. Seams read as narrow shadow gaps.` |
| shaders/trail.gdshader | L4-5 | `// Saved ribbon UV.y is metres. The tread sits 3 cm proud of the ground; darkened worn edges seat it visually instead of a hard cut line.` | `// Saved ribbon UV.y is metres. The tread sits 3 cm proud of the ground.` |
| shaders/foliage.gdshader | L13 | `// Wind is east/south in world space, independent of an authored plant's yaw.` | `// Wind is east/south in world space.` |
| assets/imported/render_pine_billboards.py | L2-6 | `"""Render CC0 source-derived distant tree impostors...not AI-generated images..."""` | `"""Render CC0 source-derived distant tree impostors. Run offline.` / `Requires trimesh, pyrender, Pillow, numpy; EGL.` |
| tools/prepare_world.py | L2-6 | `"""Offline authoring compiler...No synthetic terrain..."""` | `"""Offline authoring compiler. Never run at game start.` / `Reads saved geodata, writes an explicit static world and reviewable placement list.` / `No synthetic terrain. --placements-replace required before overwriting existing placement authorship.` |

Make these edits to all three files. Read each file first, then edit.