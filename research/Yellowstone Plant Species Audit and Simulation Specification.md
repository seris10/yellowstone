# Yellowstone plant-species audit and simulation specification

## Executive summary

The supplied inventory should not be loaded directly as Yellowstone species data. It mixes plausible regional taxa with species and even taxonomic groups that are plainly not validated as Yellowstone flora, and it treats family-level guilds as if they were species. The highest-confidence starting point is a locally documented core of functional groups—lodgepole forest, subalpine/alpine, sagebrush steppe, riparian woody vegetation, wetland/fen, and aquatic macrophytes—expanded only from park-specific floras and occurrence records. The source file itself labels its current implementation as three broad guilds, not a verified count of species.[^1]

A defensible first simulation should use spatially explicit plant functional types (PFTs) with species-level records only where occurrence and parameters are documented. Yellowstone-specific sources establish substantial alpine and aquatic floristic diversity, strong environmental sorting in fens, and marked phenological shifts; they do not provide a complete, harmonized set of species-level growth rates, photosynthetic efficiencies, or canopy parameters. [^2][^3][^4][^5] Those quantities should therefore be stored as measured values with provenance or explicit uncertain priors—not invented point estimates.

## 1. Scope and data-quality audit

The uploaded list is a candidate-generation document, not an authoritative flora. It sets a goal of 500+ additional species but lists numerous names as putative Yellowstone taxa without evidence and includes conspicuously mismatched examples. For example, the list associates desert cacti with Yellowstone, places *Oenothera biennis* under Heliotropaceae, gives “mountain mahogany” as *Cercidiphyllum japonolabile*, and lists “snow mites” and Protura in a plant inventory. Treat these as validation failures; do not assign them park occurrence or plant parameters pending authoritative voucher or floristic evidence.[^1]

| Audit class | Examples in submitted file | Simulation treatment |
|---|---|---|
| Plausible park-relevant targets | *Pinus contorta*, *Pinus albicaulis*, *Abies lasiocarpa*, *Populus tremuloides*, *Salix* spp., *Artemisia tridentata*, sedges, pondweeds | Keep as candidate taxa; require park occurrence, habitat, and taxonomic validation before enabling cells. [^1] |
| Geographic / identity validation required | *Pinus longaeva*, *Pinus banksiana*, *Acer macrophyllum*, *Acer rubrum*, *Acer saccharum*, *Platanus occidentalis*, saguaro and other desert cacti | Default to excluded from the Yellowstone domain until an authoritative local record confirms them. The provided list is not evidence of occurrence. [^1] |
| Taxonomy or category errors | “Mountain mahogany” assigned *Cercidiphyllum japonolabile*; *Oenothera biennis* placed in Heliotropaceae; Protura/snow mites included as plants | Reject these rows; resolve accepted scientific names and ranks against a current flora/taxonomic backbone. [^1] |
| Ambiguous aggregates | “Willow,” “sedge,” “pondweed,” and “Indian paintbrush” at genus/family level | Model as PFTs only if species-level identification is unavailable; do not report these as species counts. [^1] |

Park-specific floristic studies show why local curation matters. Mount Washburn’s annotated alpine vascular flora contains 126 species across 75 genera and 28 families, rather than an unbounded generic alpine list.[^2] A Yellowstone aquatic inventory sampled more than 224 locations, documenting 26 noteworthy taxa from 151 collections; several records were newly located or had previously been misidentified in herbarium records.[^3] The park’s flora also includes a substantial exotic component: a 2001 annotated checklist reported 187 exotic vascular plant species, 14.8% of the flora. This historical estimate is a baseline, not a current census.[^6]

## 2. Yellowstone-centered functional species set

Use these as an initial ecological model structure, not as a claim of exhaustive coverage. Species instances should be added from park floras, monitoring records, and verified occurrence data; where resolution is uncertain, keep records at the functional-guild level. [^2][^3]

| Functional group / candidate taxa | Yellowstone evidence and ecological role | State variables and key constraints |
|---|---|---|
| Lodgepole pine forest: *Pinus contorta* | Present in the uploaded implementation as a conifer group. Yellowstone greenness/productivity trends include lodgepole re-establishment and growth following the 1988 fires, so disturbance and stand age matter. [^1][^7] | Live woody biomass, age/size class, canopy fraction, recruitment, fire mortality, soil moisture, growing-season temperature. |
| Whitebark pine: *Pinus albicaulis*; limber pine: *P. flexilis* | Whitebark pine is a conservation-priority candidate in the source audit; the species requires its own elevation/climate and disturbance response rather than a generic conifer parameter set. [^1] | Adult and seedling pools, cone/seed production, establishment limitation, mortality and disturbance; attach local monitoring values before quantitative calibration. |
| Subalpine/alpine herbaceous and dwarf-shrub communities | The Mount Washburn inventory demonstrates a diverse, locally specific alpine flora and vulnerability to subalpine encroachment under climate change. [^2] | Snow-free date, growing degree days, soil water, exposure, phenological stage, recruitment, cover; include elevational suitability and snow duration. |
| Sagebrush steppe forbs and shrubs: *Artemisia* communities plus associated species | A Greater Yellowstone sagebrush community study tracked first flowering for 51 species and found responses differed by flowering season and growth form. [^5] | Species-specific flowering thermal/snowmelt response; forb/shrub cover; herbivory; seed bank and establishment. |
| Riparian willow and aspen: *Salix* spp., *Populus tremuloides* | Yellowstone Northern Range work documents stand classes by browsing/growth condition; a 2006 report found tall willow stands had three times the cover of short stands and greater willow richness. [^8] | Height/age structure, browsing pressure, floodplain water table, recruitment, stem density and canopy cover; distinguish suppressed, released, and protected stands. |
| Fens and wet meadows: sedges, rushes, bryophytes, associated forbs | A Yellowstone fen analysis included 476 relevés in 166 fens and identified 28 plant communities. Both regional gradients and local landform/topography were important; groundwater pH ranged 2.89–7.98. [^4] | Hydroperiod, water-table depth, groundwater chemistry/pH, microtopography, soil, elevation and precipitation; community identity must be conditioned on hydrology. |
| Aquatic macrophytes: locally verified pondweeds, bladderworts, waterweeds, etc. | The park inventory found rare/under-collected records and new park or state records; aquatic taxa should be spatially tied to waterbody, depth, substrate, and water chemistry. [^3] | Littoral depth, light attenuation, temperature, nutrients, substrate, water level, propagule presence, native/non-native status. |
| Exotic vascular plants | Yellowstone’s exotic component is ecologically relevant but should not be conflated with native biodiversity or planted as ubiquitous. [^6] | Explicit introduction/propagule process, habitat suitability, spread, control, and observation uncertainty; species-specific occurrence polygons. |

## 3. Data schema for a Python implementation

Store an occurrence layer separately from trait values: presence in the park is not equivalent to suitability in every grid cell. Suggested record fields:

```python
PlantTaxon(
    accepted_name, taxon_rank, synonym_names, native_status,
    evidence_source, evidence_date, evidence_grade,
    pft, habitat_affinities, elevation_min_m, elevation_max_m,
    thermal_response, snowmelt_response, hydroperiod,
    rooting_depth_m, shade_tolerance, drought_tolerance,
    growth_form, max_height_m, specific_leaf_area_m2_kg,
    seed_or_clonal_recruitment, dispersal_kernel,
    phenology_parameters, browsing_response,
    fire_response, mortality_parameters, uncertainty
)
```

Use `None`/missing with a provenance flag for unmeasured traits. Avoid silently substituting a congener’s value. Each trait should have a value, unit, spatial/temporal context, source, method, and uncertainty distribution. Keep taxonomic identity, occurrence confidence, and ecological parameter confidence as separate fields.

## 4. Ecological equations suitable for a first model

These are candidate model forms, not Yellowstone-calibrated parameterizations. The cited literature supports dynamic PFT competition and cautions that simple Lotka–Volterra competition can behave unrealistically or fail to represent coexistence without mechanisms such as environmental variation and disturbance.[^9] A dynamic vegetation model has used modified Lotka–Volterra competition to simulate fractional PFT cover, while also noting limitations from coarse resolution and too few PFTs.[^10]

### 4.1 Temperature and seasonal growth

Daily growing-degree accumulation for taxon *i*:

$$GDD_i(t)=\sum_{d=1}^{t}\max(0,T_d-T_{b,i})$$

A temperature response suitable for smooth integration:

$$f_{T,i}(T)=\max\left(0,\min\left(1,\frac{T-T_{min,i}}{T_{opt,i}-T_{min,i}},\frac{T_{max,i}-T}{T_{max,i}-T_{opt,i}}\right)\right)$$

Phenology can use observed snowmelt and thermal cues rather than fixed calendar dates. This is important in Greater Yellowstone: early spring flowers averaged 17 days earlier in the contemporary observations than in historical observations, while late-summer flowering showed no shift; snowmelt was on average 21 days earlier in the comparison period.[^5]

### 4.2 Light interception, water limitation, and biomass

For vertically layered canopy *z*, Beer–Lambert light attenuation:

$$I_z=I_{z-1}\exp(-k_i\,LAI_{i,z})$$

A simple light-use production function:

$$GPP_i=\epsilon_i\,PAR\left(1-e^{-k_i LAI_i}\right)f_{T,i}f_{W,i}f_{N,i}$$

where `epsilon` is calibrated light-use efficiency, `fW` and `fN` are unit-interval water and nutrient stress scalars. Soil moisture limitation can be represented as:

$$f_{W,i}=\operatorname{clip}\left(\frac{\theta-\theta_{w,i}}{\theta_{c,i}-\theta_{w,i}},0,1\right)$$

Daily biomass/carbon balance:

$$B_i(t+1)=B_i(t)+\eta_iGPP_i-R_{m,i}-R_{g,i}-L_i$$

where maintenance/growth respiration and tissue loss must be distinguished. A coupled soil-water balance should include precipitation, evapotranspiration, runoff, drainage, and uptake; this is especially important because Yellowstone fen plant distributions vary with groundwater chemistry, landform, and microtopography.[^4]

### 4.3 Competition and spatial cover

A transparent baseline for nonnegative biomass densities is a generalized competition model:

$$\frac{dB_i}{dt}=r_iB_i\left(1-\frac{\sum_j\alpha_{ij}B_j}{K_i}\right)-m_iB_i+D_i(t)$$

Here `alpha_ij` is the effect of competitor *j* on *i*, `K_i` is effective carrying capacity, `m_i` mortality, and `D_i(t)` disturbance/recruitment forcing. Constrain or test the coefficients; do not assume the classical form guarantees realistic coexistence. Include temporal variation, disturbance, and species-specific establishment limitation, then validate coexistence and exclusion patterns against observed community composition.[^9]

For cell-level fractional cover, enforce the simplex constraint:

$$0\le c_i(x,t)\le1,\qquad \sum_i c_i(x,t)\le1$$

Use suitability as a multiplicative filter:

$$S_i(x,t)=f_{T,i}f_{W,i}f_{snow,i}f_{soil,i}f_{disturbance,i}$$

and model recruitment/cover transitions conditional on seed availability and local habitat, rather than assigning every species to every cell. PFT-only models can miss niche distributions when spatial resolution or functional diversity is inadequate.[^10]

### 4.4 Phenology as a climate-sensitive state

A degree-day flowering threshold model can be written:

$$\tau_{flower,i}=\min\{t:GDD_i(t)\ge GDD^*_{i}\}\ ;\quad GDD_i(t)=\sum_{d\le t}\max(0,T_d-T_{b,i})$$

For snow-dependent taxa, add a snowmelt gate, e.g. flowering cannot begin before `snow_free_day_i`; estimate species-specific thresholds from local repeated observations. Greater Yellowstone evidence links early/midsummer flowering to spring temperature and snowmelt, and shows different responses across phenological groups, so one park-wide shift parameter is not defensible.[^5]

## 5. Calibration and validation priorities

1. **Validate taxa and occurrences first.** Use park-specific flora, herbarium vouchers, aquatic inventories, and monitoring records; preserve historical taxonomic corrections. Never use the candidate spreadsheet as the occurrence layer. Aquatic survey records show that misidentifications and overlooked taxa are real data issues.[^3]
2. **Represent spatial heterogeneity explicitly.** Elevation, snow regime, moisture, bedrock/groundwater chemistry, and microtopography are major controls; a single “Yellowstone climate” parameter set is inadequate.[^11][^4]
3. **Calibrate phenology to local observations.** Fit flowering timing against spring temperature, snowmelt day, and growing-degree accumulation, with separate group/species slopes where data permit.[^5]
4. **Validate disturbance and herbivory responses.** Separate wildfire/stand-recovery effects from climate trends and browsing effects; remote-sensing evidence reports post-1988-fire lodgepole recovery as a contributor to productivity trends.[^7]
5. **Report uncertainty instead of false precision.** Parameter ranges should be traceable to species-level measurements or calibrated posterior distributions. The retrieved Yellowstone-specific materials do not supply a complete parameter table for maximum growth, photosynthetic efficiency, root depth, or mortality for all listed taxa; these remain data gaps, not values to impute.

## References

Citations link directly to indexed source passages. Key primary/regional sources include the Mount Washburn alpine flora; the Yellowstone aquatic vascular plant inventory; the Yellowstone exotic-plant checklist; the Yellowstone fen community analysis; and the Greater Yellowstone sagebrush phenology study.[^2][^3][^6][^4][^5]


[^1]: plant_species_audit.md.

[^2]: Aho & Bała, 2012. Vascular Alpine Flora of Mount Washburn, Yellowstone National Park, USA.

[^3]: Hellquist et al., 2014. New Records for Rare and Under-Collected Aquatic Vascular Plants of Yellowstone National Park.

[^4]: Lemly, 2007. Fens of Yellowstone National Park, USA : regional and local controls over plant species distribution.

[^5]: Bloom et al., 2022. Flowering time advances since the 1970s in a sagebrush steppe community: implications for management and restoration. Ecological Applications.

[^6]: Whipple, 2001. Annotated checklist of exotic vascular plants in Yellowstone National Park. Western North American Naturalist.

[^7]: Notaro et al., 2019. Spatio-Temporal Variability in Remotely Sensed Vegetation Greenness Across Yellowstone National Park. Remote Sensing.

[^8]: Hansen & Baril, 2007. Avian response to willow height growth (Salix spp.) in Yellowstone’s Northern Range Progress Report of MSU- 23/97.

[^9]: Arora & Boer, 2006. Simulating Competition and Coexistence between Plant Functional Types in a Dynamic Vegetation Model. Earth Interactions.

[^10]: Melton & Arora, 2015. Competition between plant functional types in the Canadian Terrestrial Ecosystem Model (CTEM) v. 2.0. Geoscientific Model Development.

[^11]: Piekielek et al., 2016. Past, Present, and Future Impacts of Climate on the Vegetation Communities of the Greater Yellowstone Ecosystem across Elevation Gradients.