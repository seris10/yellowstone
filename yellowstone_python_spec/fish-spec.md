---
SCHEMA: yellowstone.fish_data.v1
SOURCE_FILES: yellowstone_python/fish.py; derived/ecosystem.godot.json; derived/ecosystem.variant.json; papers/Goldstein_2001_Firehole_salmonids.pdf; papers/fishes8070337_review.pdf; papers/jeb161224_brook_trout.pdf; papers/ecs2.4727_ecosphere.pdf; papers/PMC9773365_westslope_CTmax.pdf; papers/PMC5146681_rainbow_southern_range.pdf; papers/PMC11959187_brook_field_CTmax.pdf; papers/jeb113993_rainbow_thermal.pdf; waterway-research.md; NPS fishing regulations (nps.gov/yell/planyourvisit/fishing.htm, 2026)
---

## Species presence — configured vs real

| Species | Code in fish.py / ecosystem.godot.json | Configured thermal_profile | Real presence Firehole (NPS/reg/regulation) | Real presence literature | Status
|---|---|---|---|---|---|
| Brown trout | brown_trout; species_id: brown_trout | Y — THERMAL_SPECIES (Elliott 1975; Hokanson 1977; EPA 1977; Kaya 1977) | Present (nonnative); stocked 1889+; observed at hottest sites >30C per Goldstein 2001; absent from hottest geothermally-influenced sites per Goldstein 2001 (boron/arsenic not excluded as co-cause) | Goldstein 2001; Kaeding & Kaya 1978 | Configured
| Rainbow trout | rainbow_trout; species_id: rainbow_trout | Y — THERMAL_SPECIES (Hokanson 1977; EPA 1977; Kaya 1977) | Present (nonnative); stocked 1889+; occupies hottest sites up to ~30C with elevated boron/arsenic; spawns at hottest sites per Goldstein 2001 | Goldstein 2001; Kaeding 1976; Kaya 1978 | Configured
| Yellowstone Cutthroat Trout | NONE | NONE — no THERMAL_SPECIES entry | Native (sole native trout of park per NPS); historically dominant; reduced by nonnative competition/hybridization; no evidence this specific reach (between 06036805/06036905) holds YCT per waterway-research.md line 111 ("I found no evidence that Yellowstone cutthroat inhabit this reach"); native below/confluence may include YCT | NPS regulations; Gresswell 2011; Rogers 2022 (thermal tolerance 16.5-16.9C); Heinle 2025 (growth/survival driven by warming) | MISSING — must add for native-species claim
| Arctic Grayling | NONE | NONE | Native (NPS list); occurs below Firehole Falls; not confirmed between gauges per waterway-research.md line 111 | NPS regulations | MISSING
| Mountain Whitefish | NONE | NONE | Native (NPS list); Madison/Firehole; release required | NPS regulations | MISSING
| Brook trout | NONE (mentioned in literature only) | NONE — no THERMAL_SPECIES profile (despite papers present: jeb161224_brook_trout.pdf; PMC11959187_brook_field_CTmax.pdf; fishes8070337_review.pdf) | Mostly upstream of Kepler Cascades (above Old Faithful gauge 06036805) = outside chain per NPS/regulations; possession of up to 5 allowed in Firehole/Madison/Gibbon below falls; must release in some zones | Chadwick 2017 (growth decreases >16C; negative at 24C; upper positive growth 23.4C; cortisol 12-18x at 22/24C; HSP70 56x at 24C); review Jonsson 2023 (optimal 13-16C; UILT ~25.3C) | MISSING PROFILE — papers exist; should configure if included in chain scope
| Lake trout | NONE | NONE | Present (nonnative) in Yellowstone Lake; must kill if caught; not in Firehole chain per scope; mentioned in regulations only | NPS regulations | Out of scope (lake, not river chain)
| Smallmouth bass | NONE | NONE | Present (nonnative); must kill/report; not fish-profile relevant | NPS regulations | Not configured; out of thermal-ecology scope
| Cutthroat/rainbow hybrid | NONE | NONE | Present (hybridization documented) | NPS regulations (must kill in Lamar River drainage) | Not configured; requires separate profile or exclusion rule

## Thermal performance — configured (brown_trout / rainbow_trout)

Source files: fish.py THERMAL_SPECIES; THERMAL_SPECIES_PROVENANCE
Status: literature-anchored anchors (REAL measurements); piecewise-linear curve shapes between anchors (AUTHORED choice). Not validated against independent Firehole observation set.

| Species | t_opt_lo_c | t_opt_hi_c | t_feed_zero_c | t_refuge_c | t_uilt_c | Anchor sources (primary) | Curve-shape status | Refuge behavior anchor | Key discrepancy / gap
|---|---|---|---|---|---|---|---|---|---|
| Brown trout | 12.0 | 16.0 | 20.0 | 24.0 | 26.0 | Elliott 1975 (growth optimum 12.8-13.6C); Elliott & Hurley 1999 (zero growth 18.7C); EPA 1977 chronic 17C; NDEP BrownTTA UILT 24.4-26.5C; Kaya Kaeding Burkhalter 1977 (VERIFIED — original abstract retrieved: "mean daily temperatures exceeding 24°C, or daily maximums exceeding 25°C"; full text unretrieved/paywalled) | Authored piecewise-linear between anchors; linear interpolation not measured | Kaya 1977 (behavioral refuge drive >24C mean, verified by abstract; mortality never simulated — shelter rule) | No fine-resolution lab feeding/stress curves at 1C steps; REAL_LAB_DATA_PATH = None; curve between optimum and feed-zero is authored interpolation
| Rainbow trout | 13.0 | 17.0 | 22.0 | 24.0 | 26.0 | Hokanson et al. 1977 (optimum 15-17C, growth to ~22C); EPA 1977 chronic 19C; NDEP RainbowTTA UILT 24.3-26.7C; Kaya 1977 (VERIFIED — same abstract confirms >24C mean / >25C max for both brown and rainbow) | Authored piecewise-linear between anchors | Same Kaya 1977 claim (verified); species share refuge threshold in model | No fine-resolution feeding-rate measurements between 13-17C optimum and 22C feed-zero

Legacy authored thermal band (species=None in suitability()): T_OPT_LO_C=12.0, T_OPT_HI_C=18.0, one-sided stress max(0,(T-20)/10). Used for ecosystem.gd parity and existing tests. Replaced by THERMAL_SPECIES path when species parameter set.

## Species to add (priority, with data sources available in papers/spec)

| Species | Priority reason | Real presence (confirmed) | Available papers / sources | Required data points (per endpoint: survival, growth, activity, reproduction, habitat) | Provenance target
|---|---|---|---|---|---|
| Yellowstone Cutthroat Trout (Oncorhynchus clarkii bouvieri) | Native species of park; core to native-fish claim; no profile = model cannot make native-species predictions | Confirmed native; historically dominant; reduced by nonnatives; no evidence specifically in this reach per waterway-research.md but native below confluence | Rogers 2022 (thermal tolerance 16.5-16.9C); Heinle 2025 (growth/survival driven by warming); Johnstone 2003 (temperature tolerance cycling); Gresswell 2011 (biology/status); NPS regulations (native release required) | Survival: thermal limits (16.5-16.9C critical); Growth: temperature-growth curve (not yet extracted from papers); Activity/behavior: refuge selection (similar to brown/rainbow but native); Reproduction: spawning temperature (not extracted) | Literature-transferred anchors; curve shape authored between points until lab curves available; separate endpoint tracking per spec 5.5
| Arctic Grayling (Thymallus arcticus) | Native species; occurs below Firehole Falls (downstream of chain); needed if ecological claim extends to lower Madison/confluence | Confirmed native below falls; release required | Not in downloaded papers; requires additional source retrieval (NPS/ecology references) | Thermal optimum/growth limits; cold-water specialist; likely narrower thermal window than trout | Literature-transferred; lower priority (downstream of chain endpoint unless scope expanded)
| Mountain Whitefish (Prosopium williamsoni) | Native; Madison/Firehole; release required; no profile | Confirmed native | Not in downloaded papers | Thermal preference; growth limits; cold-water | Literature-transferred; lower priority
| Brook trout (Salvelinus fontinalis) | Non-native; mostly upstream of Kepler Cascades (outside chain); possession limits apply; papers present in folder (jeb161224; PMC11959187) | Mostly upstream of chain start (above Old Faithful gauge); not in chain unless extended upstream | Chadwick 2017 (growth >16C decreases, negative at 24C, positive growth upper limit 23.4C, stress hormones); Jonsson 2023 review (optimal 13-16C, UILT ~25.3C); PMC11959187 (field CTmax) | Survival/growth limits well-documented; activity/refuge similar model structure; reproduction temperature shift possible | Literature-transferred; can configure THERMAL_SPECIES if included in simulation scope; note upstream limitation per NPS/regulations

## Numerical verification fixtures (required per spec 5.1 / 7.1)

Analytical reference for thermal core (two-stream mixing): T_mix = (Q1*T1 + Q2*T2)/(Q1+Q2) (equal specific heat; single-phase; no geothermal/additional heat). Used for integration tests only; does not validate full geothermal/evaporative model.

Hydraulic benchmarks: rectangular/trapezoidal geometry area/perimeter; mass conservation (upstream + inflows - outflows - sources = stored change); zero-flow/shallow-flow stability; wet/dry numerical handling (not silent clip); convergence with resolution/time-step refinement.

Conservation reporting: absolute and scaled residual R_M = ΔM - (M_in - M_out + M_sources). Scaled residual uses documented reference scale with floor to avoid misleading near-zero denominators.

## Provenance rules (per spec 4.1 / 4.2 / 2.2 mode rules)

Every numeric parameter in THERMAL_SPECIES must classify as one of:
- observed (direct measurement: requires station/measurement citation)
- derived (calculated from observations with documented method)
- literature-transferred (cited study with conditions/applicability)
- calibrated (fitted to observations with fitting procedure recorded)
- assumed (missing evidence; justification + uncertainty recorded)
- illustrative (visualization/experiment; visibly labeled, never presented as measured)

Current fish.py status:
- THERMAL_SPECIES anchors: literature-transferred (VERIFIED: Elliott 1975; Hokanson 1977; EPA 1977; Kaya 1977 abstract confirmed — full text unretrieved); piecewise-linear curve shapes remain AUTHORED (not measured at intermediate temperatures)
- Piecewise-linear curve shapes: authored (assumed interpolation, not measured at intermediate temperatures)
- REFUGE_WEIGHT = 0.6: authored model choice (anchors real, weight not)
- REFUGE_RAMP_C = 2.0: authored
- T_OPT_LO_C / T_OPT_HI_C (legacy band): authored for ecosystem.gd parity
- REAL_LAB_DATA_PATH = None: no fine-resolution lab curves loaded; integration point exists (load_lab_thermal) but returns None
- Missing measurement must not become zero flow/plausible temperature silently.
- Calibration dataset must not serve as independent validation dataset.
- Illustrative fallback must remain visibly illustrative through Godot export.

Operating mode distinction (spec 2.2):
- observed_replay: prescribed discharge/temperature; cannot validate same variable at same location
- hindcast: frozen parameters; independent historical comparison
- scenario: hypothetical boundary conditions; conditional, not forecast accuracy claim
- illustrative: authored/synthetic conditions; no empirical accuracy claim
- forecast: requires forecast-specific evaluation; unavailable until evaluation completed

## Key discrepancies / open verification (from papers + doc + source audit)

1. Kaya 1977 refuge claim (>24°C) VERIFIED — original abstract retrieved via Scholar (Taylor & Francis / Progressive Fish-Culturist 39:37-39); confirms "mean daily temperatures exceeding 24°C, or daily maximums exceeding 25°C". Full text still unretrieved (paywall/block). Secondary Sullivan 2023 reports ~23°C — likely rounding or different metric; primary abstract takes precedence. Provenance label updated: literature-transferred, verified by abstract.
2. Fish thermal curves are piecewise-linear authored interpolation; no 1°C-resolution lab feeding/stress curves loaded (REAL_LAB_DATA_PATH = None). Integration point exists but unpopulated.
3. No continuous temperature record at either gauge before 2011; specific conductance only 2010-2017 at downstream; discrete field measurements exist (241 at downstream 1983-2023) but bathymetry content unverified (spec 5.1 geometry requirements).
4. Cross-section geometry inferred from DEM (hydro-flattened 2020 lidar) not surveyed bathymetry; provenance must distinguish DEM-derived from surveyed.
5. Species thermal endpoints must remain separate (survival, growth, activity, reproduction, habitat) — combining into one weighted score conceals biology (spec 5.5 / fish.py comment line 74-75).
6. Goldstein 2001 confirms rainbow at hottest sites (~30°C), brown absent — supports separate species profiles; boron/arsenic co-effect not excluded, so thermal-only model is incomplete.
7. 2026 event (closure July 9/15/29, lifted Sept 4; lowest Oct 10 flow in 37-year record; provisional data) is candidate extreme-test but cannot serve as both calibration and independent test.

## File format / delivery

File: yellowstone_python_spec/fish-spec.md
Schema: dense table + key points; no agent/user first/second/third-person prose; data-first; provenance labels embedded; gap flags explicit.
