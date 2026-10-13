# fixes-41: missing couplings and unrepresented species

Scope: which physical, chemical and ecological relationships at Midway Geyser Basin and the Firehole River the simulation does not couple, and which species it does not represent as simulated processes. Audit by syn, 2026-10-13, at the request of KJR. Complements fixes-33 (cross-domain wiring), fixes-40 (microbial mats and thermal-core terrain) and `yellowstone_species_gen/00_RESEARCH_SPEC.md` (trait library gap analysis).
Method: the coupling graph in `dashboard/data/inventory-*.json` (41 wired, 7 partial, plus proposed) was compared with processes documented for the site; each absence below was checked with a keyword sweep of `yellowstone_python/yellowstone_python/*.py` (tests excluded), and a zero is stated as a zero for that search, not as proof. Species were taken from `yellowstone_midway/data/ecosystem.json` (live actors), `fish.py` THERMAL_SPECIES, `insects_birds.py`, `species_catalogue.json` and the species-generator spec.

## Sources
- McCleskey, R. B., et al. (2012). Applied Geochemistry, doi:10.1016/j.apgeochem.2012.07.019 (chloride flux from continuous discharge and specific conductance as a measure of geothermal output; Firehole thermal-water output down about 10 percent from 1983 to 2011). USGS chloride-flux program: https://www.usgs.gov/publications/solute-and-geothermal-flux-monitoring-using-electrical-conductivity-madison-firehole. Specific conductance is published for the two gauges this project already uses, 06036805 and 06036905 (data.gov).
- Nimick, D. A., Moore, J. N., Dalby, C. E., and Savka, M. W. (1998). The fate of geothermal arsenic in the Madison and Missouri Rivers, Montana and Wyoming. Water Resources Research 34(11), 3051-3067, doi:10.1029/98WR01704 (geothermal arsenic 10 to 370 ug/L downstream; transport largely conservative in the upper basin; diurnal pH-driven sorption cycling of 10 to 20 percent).
- Goldstein (2001), Firehole salmonids, already in the project (`yellowstone_python_spec/fish-spec.md`): trout absence at the hottest geothermally influenced sites, with boron and arsenic not excluded as co-causes.
- Brock, T. D., Wiegert, R. G., and Brock, M. L. (1969). Feeding by Paracoenia and Ephydra on the microorganisms of hot springs. Ecology 50, 192-200. Collins, Mitchell and Wiegert (1976), functional analysis of a thermal spring ecosystem. Kuenzel and Wiegert (1973), spotted sandpipers feeding on Paracoenia larvae (https://sora.unm.edu/node/129007). The hot-spring food web: mats, grazing ephydrid flies, parasitic water mites, predators.
- NPS Old Faithful Virtual Visitor Center, thermal insects: https://www.nps.gov/features/yell/ofvec/exhibits/ecology/wildlife/insects.htm.

## Part A: missing couplings

### 1. Geothermal solutes are not transported in the river
Hydrothermal inflows add heat and solutes (chloride, arsenic, boron, silica, sodium). The model carries heat only. A sweep for chloride, arsenic, boron and fluoride finds one descriptive line in `geochemistry.py`.
### Fix
Add conservative solute transport (chloride, arsenic, boron) on the replay cells, with source concentrations per hydrothermal inflow (labeled authored until sampled) and the same advection the heat solver uses. Use chloride as an independent check on the geothermal heat inputs: predicted chloride flux against specific conductance at gauges 06036805 and 06036905. Feed arsenic and boron to fish habitat as a separate stressor from temperature, so the Goldstein co-cause can be represented instead of folded into thermal suitability.
### Test
Mass balance of each solute closes along the reach; with zero sources the downstream concentration equals the upstream boundary; predicted chloride at the downstream gauge is scored against the conductance record.
### Cost
Medium.

### 2. No dissolved oxygen
Warm water holds less oxygen and thermal stress in trout depends on both. No oxygen model exists (the sweep hits only unrelated lines in `census_validate.py` and `llm_backend.py`).
### Fix
Per-cell dissolved oxygen: temperature- and pressure-dependent saturation at site elevation, reaeration from the hydraulics already computed, and a metabolism term from item 3. Couple to fish suitability and to insect survival.
### Test
Saturation matches a standard solubility table at the site pressure; a warmer reach at equal reaeration holds less oxygen; fish suitability falls with oxygen at fixed temperature.
### Cost
Medium (needs item 3 for the metabolism term; saturation and reaeration alone are cheap).

### 3. The river food web has no primary producers
Prey compartments start at invertebrates. Periphyton, algae and aquatic plants, which are driven by light, temperature and geothermal nutrients and feed the grazing invertebrates, are absent (sweep: zero hits for periphyton, algae, primary production, biofilm, nutrient).
### Fix
Add a periphyton compartment per cell (light from the surface shortwave already in the forcing, temperature response, nutrient limitation as an authored term until data exist) as the food base for grazing invertebrates, and its oxygen production and respiration for item 2.
### Test
Producer biomass rises with light at fixed temperature and saturates; removing producers starves the grazer compartment over the declared time scale.
### Cost
Medium.

### 4. The hot-spring outflow food web is missing
On the outflow mats, ephydrid flies (Paracoenia, Ephydra) graze the mats, water mites parasitize the flies, and tiger beetles, spiders, dolichopodid flies and shorebirds such as spotted sandpipers and killdeer prey on them (Brock, Wiegert and Brock 1969; Kuenzel and Wiegert 1973). Sweep: zero hits for ephydrid or brine fly. `species_catalogue.json` lists `ephydrid_flies` and `wetsalts_tiger_beetle` but nothing simulates them.
### Fix
After fixes-40 provides mat biomass and temperature per cell: a fly population on the mats with temperature-limited occupancy, mite parasitism, and predation by beetles and shorebirds; flies as prey for swallows (item 9).
### Test
Fly density follows mat area and the temperature window; an unstable outflow (variable flow) lowers mite parasitism, as the cited studies report.
### Cost
Medium, after fixes-40.

### 5. Snow does not affect the grazers, and thermal ground is not a winter refuge
Snow depth and water equivalent raise movement and cratering costs for bison and elk, and geothermally warmed ground stays snow-free and is used in winter. Sweep: zero hits linking snow to grazing or foraging; zero hits for ground heat flux or soil temperature.
### Fix
Pass snow depth and water equivalent per patch from `snow_season` to `grazers` as movement and forage-access costs; add item 6's ground heat flux so thermal ground melts snow and appears as a refuge.
### Test
Route cost rises with snow depth; with a warm-ground patch available in deep snow, grazing time shifts to it.
### Cost
Medium.

### 6. No geothermal ground heat flux or soil temperature field
The apron is a binary mask. Heat conducted through thermal ground warms soil, melts snow, controls which plants survive (thermal-soil grasses, Part B item 7) and kills lodgepole pine where thermal ground expands.
### Fix
A ground heat flux and near-surface soil temperature field over the basin, authored from the apron mask and thermal imagery until measured, feeding `snow_season`, `vegetation` and tree mortality.
### Test
Snow-free duration increases with ground heat flux; tree suitability is zero above a declared soil temperature.
### Cost
Medium.

### 7. River shortwave is not shaded by terrain or vegetation
Shade exists only as a study-mode slider (`study_mode.py:2`). Terrain horizon and riparian canopy shading of the river are not computed.
### Fix
Compute per-cell sky view and direct-beam shading from the DEM and canopy census, and scale shortwave in the surface budget.
### Test
A cell under a modeled bank or canopy receives less direct beam at the same solar position; daily shortwave sums are lower in narrow sections.
### Cost
Cheap to medium.

### 8. Steam has no effect on the microclimate
`microclimate.condensation_potential` produces a one-way index for the steam visuals (`build.py:828-844`). Hydrothermal heat and vapor do not raise local humidity, form fog, cut shortwave, or deposit rime on trees in winter.
### Fix
Plume heat and vapor flux from pool and outflow surfaces (fixes-40 item 2) into a local air temperature and humidity adjustment downwind, with fog and rime as derived states.
### Test
Downwind humidity rises with pool heat flux and falls with wind speed; rime forms only below freezing with fog present.
### Cost
Medium.

### 9. Emergent insects do not feed terrestrial consumers other than the dipper and raven
Aquatic insect emergence is a major subsidy to swallows, bats and riparian spiders; the model routes prey to the dipper, raven and trout only.
### Fix
Add aerial insectivores (swallows, bats) and riparian spiders as consumers of the emergent compartment.
### Test
Emergent prey consumed equals the sum over consumers; removing aerial consumers raises emergent survival.
### Cost
Cheap.

### 10. Nothing preys on the trout
Osprey, bald eagle, common merganser, belted kingfisher and river otter take trout in this system. `grazers.py:15-18` lists predation risk only as an unknown.
### Fix
A predation mortality term on trout by size class from piscivore presence (authored densities, labeled), coupled to fish refuge use.
### Test
Trout mortality rises with piscivore density; deeper refuge cells lower it.
### Cost
Cheap to medium.

### 11. Grazers do not return nutrients or disturb ground
Dung and urine return nitrogen to patches; trampling and wallowing disturb vegetation and thin sinter crust. Sweep: zero hits for dung, nutrient, nitrogen, trampling, wallow.
### Fix
After fixes-33 item 9 (grazing feedback), add nutrient return and trampling disturbance per patch.
### Test
Patch productivity rises with nutrient return at equal grazing; trampled cells recover over the declared time scale.
### Cost
Medium.

### 12. Plants do not take up water, and the river has no hyporheic exchange
Sweep: zero hits for evapotranspiration, transpiration and hyporheic. Soil water in `snow_season` and `overland_flow` loses nothing to plants, and stream water does not exchange with bed sediments, which buffers temperature and creates refuges.
### Fix
Evapotranspiration from vegetation using the met forcing (a standard reference-ET method with a crop coefficient per patch type), and a hyporheic exchange term on the replay cells with authored exchange rates until measured.
### Test
Soil water declines faster under vegetation in warm, dry weather; hyporheic exchange damps the diurnal temperature range in the cells that have it.
### Cost
Medium.

## Part B: species not represented

Represented today as simulated processes: bison (grazers), brown trout and rainbow trout (fish, aquatic foodweb), American dipper, Canada goose and common raven (wildlife actors and consumers), three insect compartments (benthic, emergent, terrestrial), five plant proxies (generic pine, generic grass, willow, sedge and lupine forms), and the pool mat color ramps. Elk exists in code only. `species_catalogue.json` holds 56 researched entries, none spawned or simulated. `yellowstone_species_gen` holds a 270-entry trait library with no sampler and no link to the simulation.

Missing, ranked by what they add to the couplings above:
1. Thermophilic microbes as communities (Synechococcus, Chloroflexus and Roseiflexus, Thermus, Thermocrinis ruber, Sulfurihydrogenibium): fixes-40.
2. Hot-spring invertebrates: ephydrid flies, water mites, wetsalts tiger beetle, spiders (item 4).
3. River invertebrates by taxon instead of one guild: mayflies, caddisflies, stoneflies, midges; and the invasive New Zealand mudsnail, which competes with native grazers (the species catalog has an entry).
4. Fish: brook trout (papers already in the project, no thermal profile), mountain whitefish, and native Yellowstone cutthroat and Arctic grayling with their documented reach status (`fish-spec.md` records no evidence of cutthroat in the modeled reach, so their absence there may be correct); longnose dace, mottled sculpin and longnose sucker pending site confirmation.
5. Birds: piscivores (osprey, bald eagle, common merganser, belted kingfisher; item 10), outflow shorebirds (spotted sandpiper, killdeer; item 4), aerial insectivores (swallows; item 9), and wintering waterfowl on geothermally warmed water (trumpeter swan, which the species catalog lists; Barrow's goldeneye).
6. Mammals: elk as a simulated grazer (code exists), river otter (item 10), bats (item 9), coyote and small mammals; wolf only as a regional factor.
7. Plants: thermal-soil specialists (Ross's bentgrass, a Yellowstone thermal endemic listed in the species catalog; hot springs panic grass with its heat-tolerance fungal symbiosis, entry `thermal_grass_symbiosis`), thermal mosses, lodgepole pine as stands with hydrothermal die-off (item 6), riparian sedge and willow as real species, and aquatic plants in the Firehole (item 3).
8. Fungi and lichens: none represented; the trait library lists 19 fungi and 10 lichens.

## Order
Items 1, 2, 3 and 7 first (they sharpen the river model the project is built around and have gauge data for validation), then 5 and 6 (winter ecology), then 4 after fixes-40, then 9, 10, 11, 8 and 12. Species follow the couplings that need them: a species is added when a process uses it, not as decoration.

## Data to obtain
- Specific conductance and, if collected, dissolved oxygen at gauges 06036805 and 06036905 for the simulation windows.
- Arsenic, boron and chloride concentrations of the Midway inflows (published sampling, or labeled authored values).
- Piscivore and wintering waterfowl counts for the Firehole (park bird surveys), and invertebrate taxa lists for the reach.
