# Yellowstone **Species Parameters** for **Ecological Simulation**

The attached Yellowstone audit supports building the simulation around dynamic, seasonal, state-dependent species modules, with elk, wolves, vegetation, bison, and priority birds first, and it explicitly asks for species-level parameterization of habitat, diet, phenology, thermal limits, interactions, and code mappings into `insects_birds.py`, `traits_birds.json`, `wildlife[]`, and `patches[]` .

## Core Simulation Claims

| Evidence Strength | Claim |
|---|---|
| Evidence strength: Strong (9/10) | **Northern Yellowstone elk are density regulated**, and models improve when spring precipitation, snow depth, winter temperature, disturbance history, and dynamic winter range are included rather than a fixed carrying capacity (Taper & Gogan, 2002; Varley & Boyce, 2006) |
| Evidence strength: Strong (8/10) | **Wolf effects on elk are substantial but context dependent**: adaptive and bioenergetic models predict ~21% elk reduction in one model and a 61% equilibrium reduction in another, while the vegetation response depends on whether density-mediated browsing release is sufficient or whether hydrology and beaver feedbacks must also recover (Varley & Boyce, 2006; Passoni et al., 2022; Brice et al., 2024; Hobbs et al., 2024) |
| Evidence strength: Strong (8/10) | **Bird modules should be weather- and detection-aware**, because thermal stress alters foraging and space use, occupancy estimates depend on imperfect detection, and nest success often varies with daily weather and habitat covariates (Conradie et al., 2023; Saab et al., 2021; Dinsmore et al., 2002; Mizel & Flamme, 2025) |

**Figure 1:** Evidence strength for main Yellowstone simulation claims

## System Architecture

The attached parameterization memo already defines the immediate modeling scope more clearly than the broader corpus: species entries need taxonomy, habitat, diet, phenology, thermal tolerance, interactions, provenance, uncertainty labels, and explicit mapping into existing Python data structures rather than only natural-history summaries .

A robust architecture should separate **state variables**, **process equations**, and **observation models**. That separation is necessary because Yellowstone bird monitoring and raptor surveys are detection-limited, not census-perfect, and occupancy or abundance inference improves when detection is modeled explicitly (Fagre et al., 2022; Kéry, 2018; Joseph et al., 2009).

A practical species schema for Python is:

| Field | Meaning | Best-supported source type |
|---|---|---|
| `body_mass_kg` | Morphology, heat scaling | AVONET species means |
| `habitat_weights` | Patch suitability by habitat | Yellowstone occurrence or regional habitat models |
| `diet_profile` | Seasonal prey fractions | Yellowstone diet studies where available |
| `phenology` | Lay, hatch, fledge, migrate windows | Yellowstone or Rocky Mountain breeding studies |
| `thermal_params` | Biophysical or tolerance parameters | NicheMapR + species physiology |
| `demography` | Survival, fecundity, occupancy | Local monitoring or transfer studies |
| `obs_model` | Detection per survey context | Occupancy / N-mixture literature |

**Figure 2:** Recommended per-species parameter schema for Python simulation

## Elk, Wolves, and Vegetation

A defensible elk population core is a climate-driven Ricker model with explicit predation and extra-park mortality, because the northern Yellowstone elk series strongly supported density dependence and improved with weather covariates and period-specific structure (Taper & Gogan, 2002).

\[
N_{elk,t+1}=N_{elk,t}\exp\left(r_t\left(1-\frac{N_{elk,t}}{K_{elk}(t)}\right)-P_t-H_t\right)
\]

This exact form is recommended in the attached audit, with \(r_t\) absorbing climate anomalies, \(P_t\) predation loss, and \(H_t\) harvest or extra-park mortality .

A Yellowstone wolf-elk interaction should not use plain Lotka-Volterra alone, because Yellowstone-focused synthesis and functional-response literature both support saturation, prey defense, and temperature-sensitive attack processes (Uiterwaal & Delong, 2020).

\[
\frac{dE}{dt}=r_EE\left(1-\frac{E}{K_{elk}(t)}\right)-\frac{a(T,s)WE}{1+a(T,s)hE}
\]
\[
\frac{dW}{dt}=c\frac{a(T,s)WE}{1+a(T,s)hE}-mW
\]

The attached memo gives this Holling type II structure for elk \(E\) and wolves \(W\), and ties \(a(T,s)\) to temperature and season because space-clearance and handling are generally maximized at intermediate, not ever-warmer, temperatures (Uiterwaal & Delong, 2020).

Parameter targets already constrained by Yellowstone data include elk decline after wolf restoration from roughly 17,000 in 1995 to 8,335 in 2004, prime-age female survival near 0.85, and wolf off-take exceeding 1,000 elk annually by 2003 in one assessment (White & Garrott, 2005). Another Yellowstone recovery model estimated wolf consumption at about 1,035 elk per year and a 21% reduction in herd size with stabilizing density-dependent effects of predation and harvest (Varley & Boyce, 2006).

Calf recruitment should be modeled separately from adult survival. Recruitment declined as wolf:elk ratio increased, decreased after severe winters, and increased as elk density decreased, while adult pregnancy tracked age and summer precipitation more than carnivore density (Proffitt et al., 2014). Broader western elk data also show calf mortality rises with deeper snow and larger surrounding wolf packs, while adult female mortality is strongly shaped by age, pack size, and snow depth (Horne et al., 2019).

Vegetation should be split into at least grassland forage and woody riparian browse. The bioenergetic tri-trophic model predicts wolf restoration can raise vegetation biomass by about 25% in the growing season and more than threefold in the nongrowing season (Passoni et al., 2022). But Yellowstone vegetation evidence is not monolithic: aspen studies increasingly support stronger density-mediated than risk-mediated effects of wolves on browsing, while willow recovery can still require both reduced browsing and restored hydrology or beaver engineering (Brice et al., 2024; Hobbs et al., 2024).

A minimal woody browse submodel is therefore:

\[
B_{t+1}=B_t + g(B_t,\,season,\,water_t)-c\,U_t\,B_t
\]

where ungulate browsing pressure \(U_t\) is driven more by elk density than by simple spatial fear fields in current Yellowstone evidence (Brice et al., 2024).

## Raptors, Waterbirds, and Lake-Linked Species

The attached audit prioritizes bald eagle, osprey, golden eagle, red-tailed hawk, sandhill crane, great blue heron, pelican, common loon, bufflehead, and hooded merganser first because they already have monitoring value or tractable data pathways .

For **bald eagle**, Yellowstone-specific breeding data already support explicit phenology and reproduction fields: occupied territories produced 0.92 young per year in one Grand Teton–Yellowstone study, nesting began from early March to mid-April, and cold wet springs reduced reproduction strongly (Alt, 1980). Diet must be spatially explicit because lake nesters used more waterfowl, river nesters more fish, and Yellowstone Lake nesters shifted from cutthroat trout in June–early July to waterfowl in August (Alt, 1980).

For **osprey**, Yellowstone Lake dependence on cutthroat trout is much tighter. Osprey historically fed about 93% on cutthroat trout at Yellowstone Lake, nested later on lakes than streams after ice-out, and lake nests had lower success and productivity than stream nests in the 1970s (Swenson, 1975). Later work shows steep declines in cutthroat trout abundance coincided with major declines in osprey breeding pairs, nesting success, and productivity, with reproduction positively correlated with trout abundance and spring temperature (Baril et al., 2013; Koel et al., 2019).

For **red-tailed hawk**, Yellowstone baseline data are unusually strong for a raptor. From 2011–2015, at least 60 territories were documented on the northern range; 87% of pairs laid eggs on average; breeding success averaged 63%; reproductive rate averaged 1.07 young per occupied territory; and brood size averaged 1.73 young per successful nest (Walker et al., 2019). Territorial quality should depend more on perch distribution and accessible prey than territory area per se in transferable hawk models (Janes, 1984).

For **golden eagle** and migratory raptors, Yellowstone has strong passage data but weaker local breeding demography in this corpus. Hayden Valley counts recorded 6,441 raptors of 17 species across 170 days and 907 hours, with red-tailed hawks, Swainson’s hawks, and golden eagles making up 51% of individuals (Baril et al., 2018).

For **trumpeter swan**, Yellowstone-specific demographic inputs exist and should be used instead of generic swan values. Average clutch size was 4.2 eggs, fledging success increased with historical territory quality and decreased with April precipitation, and predicted fledging success ranged from 0.062 at poor sites to 0.275 at the best historically used sites (Proffitt et al., 2010). Movement structure also matters because Greater Yellowstone swans include nonmigratory summers in 22% of swan-years and otherwise move up to 473 km, with U.S. birds favoring high-elevation breeding lakes (Poessel et al., 2025). Long-term conservation context is severe: resident Yellowstone trumpeter swans fell from 60–87 birds in the 1950s to fewer than 10 annually since 2007 (White et al., 2011).

For **common loon** and **pelican**, the corpus is more indirect. Loon productivity elsewhere declines with interacting lake chemistry, mercury, area, and April temperature, so any Yellowstone loon module should remain low-confidence until local breeding data are added (Bianchini et al., 2020). Pelicans are clearly tied to Yellowstone cutthroat trout dynamics in the broader region and can impose substantial trout mortality, but the strongest quantified predation rates in this corpus come from Idaho rather than Yellowstone Lake proper (McCormick et al., 2021; Teuscher et al., 2015).

Priority species parameters are summarized below.

| Species | Yellowstone-ready numeric fields | Key caveat |
|---|---|---|
| Bald eagle | 0.92 young/occupied territory; nest chronology; diet split by site | Reproduction sensitive to spring weather |
| Osprey | 93% cutthroat diet at Yellowstone Lake; stream-vs-lake success; trout-linked productivity | Strong fish dependence makes prey module essential |
| Red-tailed hawk | 60 territories; 0.87 laying probability; 0.63 breeding success; 1.07 young/territory | Local demography good, prey data thinner |
| Trumpeter swan | clutch 4.2; fledging success 0.062–0.275 by territory quality | Resident population sharply reduced |
| Golden eagle | migration abundance strong | breeding parameters sparse in this corpus |
| Common loon | only indirect demographic drivers | Yellowstone-specific breeding data missing |

**Figure 3:** Priority bird species with simulation-ready numeric parameters

## Waterfowl, Forest Birds, and Small Passerines

The attached avian audit can be expanded most safely by grouping taxa into functional modules rather than pretending equal species-specific certainty across all 100+ missing birds .

For **dabbling ducks**, breeding productivity is consistently linked to wetland conditions. Blue-winged teal diets shift from about 45% invertebrates on arrival to 95% at nesting onset, and feeding tracks temporary versus semipermanent wetlands as hydrology changes (Swanson et al., 1974). Across species, pond counts and wetland chronology are strong drivers of productivity, including positive pond effects for mallard and green-winged teal and higher nest survival for lesser scaup when water levels rise gradually to a late breeding-season maximum (Hsiung et al., 2026; Navarre et al., 2022).

For **diving ducks**, lesser scaup consumed about 66% animal food in one breeding-habitat study, while blue-winged teal used roughly equal animal and plant foods, implying separate prey kernels by guild rather than a single duck diet template (Dirschl, 1969). Canvasback and redhead females both deplete lipid reserves through laying and incubation, but with species differences in timing and magnitude, which matters if the simulation tracks body condition and renesting (Noyes & Jarvis, 1985). Juvenile canvasback recruitment varies strongly with hatch date, duckling weight, and wetland condition, with juvenile breeding probability spanning 0.54–0.94 and recruitment probability 0.12–0.28 at mean covariates (Anderson et al., 2001).

For **swallows and aerial insectivores**, the attached bird model request for `forage_probability = g(insect_activity, patch, time_of_day)` is well aligned with the literature because survival and breeding both track conditions favorable for insect availability (Imlay et al., 2022). Long-term swallow phenology has advanced 8–10 days in most species studied, and colder or drier conditions can reduce performance depending on species and site (Imlay et al., 2018; Gherbaoui et al., 2025).

For **forest fire specialists**, Yellowstone-region data strongly justify explicit postfire habitat states. Recently burned conifer forests in the northern Rockies supported distinct bird communities, with black-backed woodpeckers nearly restricted to standing dead forests created by stand-replacement fire (Hutto, 1995). In the Yellowstone area, active Picoides cavities were more likely in postfire lodgepole than undisturbed or human-disturbed strata (Rotella & Vyse; Hoffman, 1997). But fledgling survival for burned-forest specialists can peak in lower-severity adjacent habitat, so one burn severity class is too crude for juvenile stages (Stillman et al., 2021).

For **small winter passerines** such as chickadees, juncos, and nuthatch analogs, thermal performance should be condition- and season-dependent. Black-capped chickadees increase winter summit metabolism by 36% and mountain chickadees increase it by 26.1%, with winter increases in BMR and muscle mass rather than large conductance changes alone (Cooper & Swanson, 1994; Cooper, 2002; Schweizer et al., 2023). Chickadees also lower daytime body temperature and increase feeder visitation in colder weather, but foraging and diurnal body-temperature regulation are only weakly coupled at the individual level (Hawkshaw et al., 2025).

## Thermal and Observation Equations

The attached audit is right to warn against fixed thermal thresholds. Reviews show TNZ, LCT, and UCT are often misused as direct tolerance limits, and dataset quality for reported LCT/UCT values can be poor . For Yellowstone birds, the strongest general solution is a mechanistic heat-budget layer plus species-specific morphology and behavior, because NicheMapR’s endotherm model solves metabolic rate, water loss, feather temperature, and skin temperature jointly from microclimate and trait data (Kearney et al., 2021; Conradie et al., 2023).

A simulation-ready bird activity equation is:

\[
p_{\text{forage}}=\sigma(\beta_0+\beta_1 I+\beta_2 Sun-\beta_3 Wind-\beta_4 HeatStress+\beta_5 Social)
\]

where the attached memo ties \(I\) to insect activity and notes that social partners can affect winter morning foraging beyond temperature alone .

For species lacking direct heat-tolerance experiments, allometric priors are available:

\[
T_b^{max}=-0.814\log_{10}M_b+45.734
\]
\[
HTL=4.867\log_{10}M_b+43.040
\]

with substantial among-species residual variation, so these should be priors, not locked constants .

The underlying heat budget should balance metabolism with radiative, convective, conductive, and evaporative exchange, which is exactly the framework used in NicheMapR endotherm modeling (Kearney et al., 2021).

\[
M + R_{abs} - R_{emit} - C - K - E = 0
\]

This generic steady-state form is justified by the NicheMapR documentation and validation studies showing tight correspondence between predicted and observed evaporative water loss, metabolic rate, and body temperature across 10–50°C in birds (Kearney et al., 2021; Conradie et al., 2023).

Observation equations are equally important for calibration. For occupancy:

\[
z_{i,j,k}\sim \text{Bernoulli}(\psi_{i,j,k}), \qquad y_{i,j,k,v}\sim \text{Bernoulli}(z_{i,j,k}p_{i,j,k,v})
\]

because repeated-visit occupancy models explicitly separate presence from imperfect detection and improve estimation for rare Yellowstone birds (Fagre et al., 2022; Saab et al., 2021).

For count data:

\[
N_j \sim \text{Poisson}(\lambda_j), \qquad y_{j,v}\sim \text{Binomial}(N_j,p_{j,v})
\]

with Poisson or ZIP mixtures preferred over negative-binomial mixtures unless identifiability is checked carefully (Kéry, 2018; Joseph et al., 2009).

For nest survival:

\[
\text{logit}(DSR_t)=\alpha_0+\alpha_1\,Temp_t+\alpha_2\,Precip_t+\alpha_3\,NestAge_t+\alpha_4\,Habitat
\]

because modern nest-survival models are built around daily survival with time-varying covariates, not apparent success alone (Dinsmore et al., 2002; Miller et al., 2017).

| Equation | Use in Python sim | Yellowstone-relevant taxa |
|---|---|---|
| Climate Ricker | annual ungulate abundance | elk, bison |
| Saturating predator-prey ODE | wolf-elk predation | wolf, elk |
| Seasonal browse growth | woody plant recovery | willow, aspen |
| Logistic forage probability | weather-driven bird behavior | passerines, swallows |
| Heat-budget balance | thermal stress and water cost | all birds |
| Occupancy / N-mixture | calibration to surveys | most monitored birds |
| Daily nest survival logit | breeding productivity | raptors, waterfowl, songbirds |

**Figure 4:** Core equations for Yellowstone ecological simulation modules

## Immediate Per-Species Build Priorities

The highest-value next step is not adding 100 birds at equal resolution, but filling species records in descending evidence order with explicit confidence labels, because the attached audit already requires provenance, run mode, and unknowns to remain unknown .

1. **Tier 1 local-data species:** elk, wolf, vegetation, bald eagle, osprey, red-tailed hawk, trumpeter swan, Yellowstone Lake fish-linked birds (Alt, 1980; Walker et al., 2019; Proffitt et al., 2010).  
2. **Tier 2 transferable guild models:** teal, scaup, canvasback, redhead, swallows, chickadee-like winter passerines, fire-specialist woodpeckers (Swanson et al., 1974; Dirschl, 1969; Anderson et al., 2001; Imlay et al., 2022; Cooper, 2002; Hutto, 1995).  
3. **Tier 3 occurrence-first species:** western screech-owl, many rare ducks, loons, finches, and marginal breeders where this corpus supports checklist status or regional analogs better than Yellowstone vital rates (Fitton, 1993).

A compact JSON-ready record should therefore hold `value`, `units`, `source_scope`, `confidence`, and `citation`, with `source_scope` set to `yellowstone`, `greater_yellowstone`, `rocky_mountains`, or `north_america_transfer`. AVONET can supply mass and morphology for nearly all birds, but it does not replace Yellowstone demography or habitat use (Tobias et al., 2022).

The single most important shift in the evidence is from fixed-threshold, single-equation wildlife rules to **dynamic coupled models** that integrate climate, predation, body condition, thermal biophysics, and imperfect detection. The biggest open question is not whether Yellowstone species interact strongly, but where local Yellowstone measurements end and regional transfer assumptions begin for each species record.
 
_These search results were found and analyzed using Consensus, an AI-powered search engine for research. Try it at https://consensus.app. © 2026 Consensus NLP, Inc. Personal, non-commercial use only; redistribution requires copyright holders’ consent._
 
## References
 
Yellowstone Species-Simulation Parameterization.
 
Phase 2: Avian Diversity Audit and Documentation.
 
Alt, K. L. (1980). Ecology of the breeding bald eagle and osprey in the Grand Teton-Yellowstone National Parks complex. 1-107.
 
Anderson, M. G., Lindberg, M., & Emery, R. B. (2001). Probability of survival and breeding for juvenile female canvasbacks. *Journal of Wildlife Management, 65*, 385-397. https://doi.org/10.2307/3803090
 
Baril, L. M., Smith, D. W., Drummer, T., & Koel, T. (2013). Implications of Cutthroat Trout Declines for Breeding Ospreys and Bald Eagles at Yellowstone Lake. 234 - 245. https://doi.org/10.3356/jrr-11-93.1
 
Baril, L. M., Haines, D. B., Walker, L., & Smith, D. W. (2018). Autumn Raptor Migration in Yellowstone National Park, 2011–2015. *Canadian Field-Naturalist, 131*, 303-311. https://doi.org/10.22621/cfn.v131i4.1909
 
Bianchini, K., Tozer, D. C., Alvo, R., Bhavsar, S., & Mallory, M. (2020). Drivers of declines in common loon (Gavia immer) productivity in Ontario, Canada.. *The Science of the total environment, 738*, 139724. https://doi.org/10.1016/j.scitotenv.2020.139724
 
Brice, E. M., Larsen, E. J., Stahler, D., & MacNulty, D. (2024). The primacy of density‐mediated indirect effects in a community of wolves, elk, and aspen. *Ecological Monographs*. https://doi.org/10.1002/ecm.1627
 
Conradie, S. R., Kearney, M., Wolf, B., Cunningham, S., Freeman, M. T., Kemp, R., & McKechnie, A. (2023). An evaluation of a biophysical model for predicting avian thermoregulation in the heat.. *The Journal of experimental biology*. https://doi.org/10.1242/jeb.245066
 
Cooper, S. J., & Swanson, D. (1994). Seasonal Acclimatization of Thermoregulation in the Black-Capped Chickadee. *The Condor, 96*, 638-646. https://doi.org/10.2307/1369467
 
Cooper, S. J. (2002). Seasonal Metabolic Acclimatization in Mountain Chickadees and Juniper Titmice. *Physiological and Biochemical Zoology, 75*, 386 - 395. https://doi.org/10.1086/342256
 
Dinsmore, S., White, G., & Knopf, F. (2002). ADVANCED TECHNIQUES FOR MODELING AVIAN NEST SURVIVAL. *Ecology, 83*, 3476-3488. https://doi.org/10.1890/0012-9658(2002)083[3476:atfman]2.0.co;2
 
Dirschl, H. J. (1969). FOODS OF LESSER SCAUP AND BLUE-WINGED TEAL IN THE SASKATCHEWAN RIVER DELTA. *Journal of Wildlife Management, 33*, 77-87. https://doi.org/10.2307/3799652
 
Fagre, D. A., Janousek, W. M., & Dreitz, V. J. (2022). Avian species richness and abundance show stronger responses to bison grazing intensity than to ecosystem productivity. *Ecosphere*. https://doi.org/10.1002/ecs2.4299
 
Fitton, S. (1993). SCREECH-OWL DISTRIBUTION IN WYOMING.
 
Gherbaoui, F., Bensouilah, T., Pagani‐Núñez, E., & Houhamdi, M. (2025). Temperature and Rainfall Shape the Breeding Ecology of Barn Swallows Hirundo rustica in an Arid Region. *Ecology and Evolution, 15*. https://doi.org/10.1002/ece3.72661
 
Hawkshaw, D. M., Wijmenga, J. J., & Mathot, K. J. (2025). Individual variation in diurnal body temperature and foraging activity in overwintering black-capped chickadees (Poecile atricapillus).. *Journal of thermal biology, 127*, 104059. https://doi.org/10.1016/j.jtherbio.2025.104059
 
Hobbs, N. T., Johnston, D. B., Marshall, K. N., Wolf, E. C., & Cooper, D. J. (2024). Does restoring apex predators to food webs restore ecosystems? Large carnivores in Yellowstone as a model system. *Ecological Monographs*. https://doi.org/10.1002/ecm.1598
 
Hoffman, N. (1997). Distribution of Picoides woodpeckers in relation to habitat disturbance within the Yellowstone area. 1-84.
 
Horne, J. S., Hurley, M. A., White, C., & Rachael, J. S. (2019). Effects of wolf pack size and winter conditions on elk mortality. *The Journal of Wildlife Management*. https://doi.org/10.1002/jwmg.21689
 
Hsiung, A. C., Ross, B., Hagy, H., & Anderson, J. T. (2026). Drivers of mallard and green‐winged teal population dynamics in North America. *Ecosphere*. https://doi.org/10.1002/ecs2.70744
 
Hutto, R. (1995). Composition of Bird Communities Following Stand-Replacement Fires in Northern Rocky Mountain (U.S.A.) Conifer Forests.. *Conservation biology : the journal of the Society for Conservation Biology, 9 5*, 1041-1058. https://doi.org/10.1046/j.1523-1739.1995.9051033.x-i1
 
Imlay, T. L., Mann, H. A., Ding, A. C., Thomas, P. W., Whittam, R. M., Leonard, M., & Zhao, Q. (2022). Annual adult survival rates for four sympatric breeding swallow species: effects of environmental factors and density-dependence. *Canadian Journal of Zoology*. https://doi.org/10.1139/cjz-2021-0207
 
Imlay, T. L., Flemming, J., Saldanha, S., Wheelwright, N., & Leonard, M. (2018). Breeding phenology and performance for four swallows over 57 years: relationships with temperature and precipitation. *Ecosphere, 9*. https://doi.org/10.1002/ecs2.2166
 
Janes, S. (1984). Influences of Territory Composition and Interspecific Competition on Red‐Tailed Hawk Reproductive Success. *Ecology, 65*, 862-870. https://doi.org/10.2307/1938060
 
Joseph, L. N., Elkin, C., Martin, T., & Possingham, H. (2009). Modeling abundance using N-mixture models: the importance of considering ecological mechanisms.. *Ecological applications : a publication of the Ecological Society of America, 19 3*, 631-42. https://doi.org/10.1890/07-2107.1
 
Kearney, M., Briscoe, N. J., Mathewson, P., & Porter, W. (2021). NicheMapR – an R package for biophysical modelling: the endotherm model. *Ecography*. https://doi.org/10.1111/ecog.05550
 
Kéry, M. (2018). Identifiability in N-mixture models: a large-scale screening test with bird data.. *Ecology, 99 2*, 281-288. https://doi.org/10.1002/ecy.2093
 
Koel, T., Tronstad, L., Arnold, J. L., Gunther, K., Smith, D. W., Syslo, J., & White, P. J. (2019). Predatory fish invasion induces within and across ecosystem effects in Yellowstone National Park. *Science Advances, 5*. https://doi.org/10.1126/sciadv.aav1139
 
McCormick, J., Brimmer, A. F., & Watkins, C. J. (2021). Evaluating Target Levels of American White Pelican Abundance to Achieve Management Objectives for Adfluvial Yellowstone Cutthroat Trout. *North American Journal of Fisheries Management*. https://doi.org/10.1002/nafm.10663
 
Miller, M. W., Leech, D., Pearce-Higgins, J., & Robinson, R. (2017). Multi-state, multi-stage modeling of nest-success suggests interaction between weather and land-use.. *Ecology, 98 1*, 175-186. https://doi.org/10.1002/ecy.1629
 
Mizel, J. D., & Flamme, M. J. (2025). Estimating occupancy and nest survival of cliff-nesting raptors in an open population framework.. *Ecological applications : a publication of the Ecological Society of America, 35 4*, e70051. https://doi.org/10.1002/eap.70051
 
Navarre, K. L., Warren, J., & Koons, D. (2022). Hydrology management influences nest survival but not clutch size in Lesser Scaup. *Avian Conservation and Ecology*. https://doi.org/10.5751/ace-02268-170229
 
Noyes, J., & Jarvis, R. (1985). Diet and nutrition of breeding female redhead and canvasback ducks in Nevada. *Journal of Wildlife Management, 49*, 203-211. https://doi.org/10.2307/3801872
 
Passoni, G., Coulson, T., Cagnacci, F., Hudson, P., Stahler, D., Smith, D. W., & Lachish, S. (2022). Investigating tri-trophic interactions using bio-energetic demographic models. *bioRxiv*. https://doi.org/10.1101/2022.04.07.487507
 
Poessel, S. A., Sanders, T. A., Long, W. R., Kristóf, A., Reishus, B., Proett, M., Gower, C. N., Ibrahim, N., & Katzner, T. (2025). Movements and habitat use of the Rocky Mountain Population of trumpeter swans. *The Journal of Wildlife Management*. https://doi.org/10.1002/jwmg.70096
 
Proffitt, K. M., Cunningham, J. A., Hamlin, K., & Garrott, R. (2014). Bottom‐up and top‐down influences on pregnancy rates and recruitment of northern Yellowstone elk. *Journal of Wildlife Management, 78*, 1383-1393. https://doi.org/10.1002/jwmg.792
 
Proffitt, K. M., Mceneaney, T. P., White, P. J., & Garrott, R. (2010). Productivity and Fledging Success of Trumpeter Swans in Yellowstone National Park, 1987–2007. 341 - 348. https://doi.org/10.1675/063.033.0310
 
Rotella, J., & Vyse, E. Distribution of Picoides woodpeckers in relation to habitat disturbance within the Yellowstone area by Nancy.
 
Saab, V., Latif, Q. R., Block, W., & Dudley, J. (2021). Short-term benefits of prescribed fire to bird communities of dry forests. *Fire Ecology, 18*. https://doi.org/10.1186/s42408-022-00130-x
 
Schweizer, R., Romero, A., Tobalske, B., Semenov, G. A., Carling, M., Rice, A. M., Taylor, S. A., & Cheviron, Z. (2023). Thermal acclimation in a non-migratory songbird occurs via changes to thermogenic capacity, but not conductance.. *The Journal of experimental biology*. https://doi.org/10.1242/jeb.245208
 
Stillman, A. N., Lorenz, T. J., Fischer, P. C., Siegel, R., Wilkerson, R. L., Johnson, M., & Tingley, M. (2021). Juvenile survival of a burned forest specialist in response to variation in fire characteristics.. *The Journal of animal ecology*. https://doi.org/10.1111/1365-2656.13456
 
Swanson, G., Meyer, M. I., & Serie, J. R. (1974). Feeding Ecology of Breeding Blue-Winged Teals. *Journal of Wildlife Management, 38*, 396. https://doi.org/10.2307/3800869
 
Swenson, J. (1975). Ecology of the bald eagle and osprey in Yellowstone National Park. 1-160.
 
Taper, M., & Gogan, P. (2002). The northern Yellowstone elk: density dependence and climatic conditions. *Journal of Wildlife Management, 66*, 106-122. https://doi.org/10.2307/3802877
 
Teuscher, D., Green, M., Schill, D., Brimmer, A. F., & Hillyard, R. W. (2015). Predation by American White Pelicans on Yellowstone Cutthroat Trout in the Blackfoot River Drainage, Idaho. *North American Journal of Fisheries Management, 35*, 454-463. https://doi.org/10.1080/02755947.2015.1017118
 
Tobias, J., Sheard, C., Pigot, A., Devenish, A., Yang, J., Sayol, F., Neate-Clegg, M. H. C., Alioravainen, N., Weeks, T. L., Barber, R. A., Walkden, P. A., MacGregor, H. E. A., Jones, S. E. I., Vincent, C., Phillips, A. G., Marples, N., Montaño-Centellas, F. A., Leandro‐Silva, V., Claramunt, S., . . . Schleuning, M. (2022). AVONET: morphological, ecological and geographical data for all birds.. *Ecology letters, 25 3*, 581-597. https://doi.org/10.1111/ele.13898
 
Uiterwaal, S. F., & Delong, J. P. (2020). Functional responses are maximized at intermediate temperatures.. *Ecology*, e02975. https://doi.org/10.1002/ecy.2975
 
Varley, N., & Boyce, M. (2006). Adaptive management for reintroductions: Updating a wolf recovery model for Yellowstone National Park. *Ecological Modelling, 193*, 315-339. https://doi.org/10.1016/j.ecolmodel.2005.09.001
 
Walker, L., Baril, L. M., Haines, D. B., & Smith, D. W. (2019). Reproductive Characteristics of Red-Tailed Hawks in Yellowstone National Park, an Intact Temperate Landscape. *Journal of Raptor Research, 53*, 309 - 318. https://doi.org/10.3356/jrr-18-103
 
White, P. J., & Garrott, R. (2005). Northern Yellowstone elk after wolf restoration. 942 - 955. https://doi.org/10.2193/0091-7648(2005)33[942:nyeawr]2.0.co;2
 
White, P. J., Proffitt, K. M., McEneaney, T., Garrott, R., & Smith, D. M. (2011). Yellowstone ’ s Trumpeter Swans in Peril ? Drastic Decrease in Resident Swans over the Past 40 Years.
 
