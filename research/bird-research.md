# Yellowstone **Species-Simulation** Parameterization

The attached Yellowstone avian audit defines the immediate simulation need as **species-level parameterization** for taxonomy, habitat, diet, phenology, thermal tolerance, interactions, and explicit mapping into `insects_birds.py`, `traits_birds.json`, `wildlife[]`, and `patches[]` for more than 100 missing bird species . For an ecologically robust Yellowstone sim, the literature supports three linked species modules: **wolf-elk vegetation dynamics**, **ungulate climate-density regulation**, and **bird weather-foraging-thermal behavior**, with caveats that thermal limits and trophic effects should not be reduced to single fixed thresholds (Passoni et al., 2022; Varley & Boyce, 2006; Taper & Gogan, 2002; Uiterwaal & Delong, 2020; Mitchell et al., 2018; Welman et al., 2024).

## Core Species Table

| Species / Guild | Yellowstone-Relevant State Variables | Quantitative Findings To Encode | Simulation Implication |
|---|---|---|---|
| **Elk** | abundance, age/sex or body mass, winter range, migration state | Wolves reduced herd size by **21%** in one adaptive model, with wolf consumption averaging **~1035 elk/year** (Varley & Boyce, 2006) | Predation mortality should be density-dependent, seasonal, and coupled to migration/hunter exposure |
| **Wolf** | abundance, pack effect, hunting efficiency, territory | Bioenergetic tri-trophic equilibrium produced **99 wolves** with elk reduced from **14,948 to 5,823** (Passoni et al., 2022) | Predator module should include hunting efficiency and stabilizing feedbacks |
| **Vegetation** | biomass, seasonal growth phase, browse pressure | Wolf addition increased vegetation biomass **~25% in growing season** and **>3-fold in non-growing season** (Passoni et al., 2022) | Use explicit seasonal producer dynamics rather than static carrying capacity |
| **Bison** | abundance, group count, group size, spring climate sensitivity | Population growth can be strongly climate-sensitive; early spring temperature had larger equilibrium effects than harvest or density dependence in one state-space model (Koons et al., 2015) | Bison should respond to climate and competition, not only predation |
| **Birds** | occupancy, foraging probability, thermal state, social state | High temperatures reduced foraging, shifted birds toward water/shade, and altered social aggregation (Funghi et al., 2019; Madsen & Shizuka, 2021) | Bird behavior should be weather-driven and optionally socially coupled |

**Figure 1:** Core Yellowstone species modules and simulation variables

## Population Equations

A defensible elk equation starts with **density dependence plus climate covariates**, because northern Yellowstone elk time series strongly supported density dependence and the best-performing formulation was a **Ricker model** with weather terms including spring precipitation, snow depth, winter temperature, and disturbance history (Taper & Gogan, 2002). A second Yellowstone wolf-elk model used a **dynamic elk carrying capacity** \(K_{elk}(t)\) that varies with winter severity and summer forage production, and also included density-dependent migration outside the park during severe winters (Varley & Boyce, 2006).

Use:
\[
N_{elk,t+1}=N_{elk,t}\exp\Big(r_t\Big(1-\frac{N_{elk,t}}{K_{elk}(t)}\Big)-P_t-H_t\Big)
\]
where \(r_t\) can absorb climate anomalies, \(P_t\) is predation loss, and \(H_t\) is harvest or extra-park mortality (Taper & Gogan, 2002; Varley & Boyce, 2006). If a Gompertz form is preferred for ungulates, a Bayesian state-space version with extractions is also supported, and elasticity analysis showed **early spring temperature** can exceed harvest and density dependence in impact on equilibrium abundance (Koons et al., 2015).

A minimal predator term can begin with Lotka-Volterra structure, but Yellowstone-focused modeling shows plain LV fits can be unstable or converge to extinction equilibria, so saturation and social hunting terms are better justified for wolves (Menden, 2019; Kumari et al., 2025). The long-run elk-wolf literature supports including direct predation, saturation, cooperative hunting, and prey defense thresholds (Kumari et al., 2025).

\[
\frac{dE}{dt}=r_EE\Big(1-\frac{E}{K_{elk}(t)}\Big)-\frac{a(T,s)WE}{1+a(T,s)hE}
\]

\[
\frac{dW}{dt}=c\frac{a(T,s)WE}{1+a(T,s)hE}-mW
\]

Here \(a(T,s)\) is a temperature- and season-dependent attack rate, \(h\) is handling time, \(c\) conversion efficiency, and \(m\) wolf mortality (Uiterwaal & Delong, 2020; Kumari et al., 2025). The reason to make \(a\) and \(h\) temperature-dependent is that the largest functional-response synthesis found both **space clearance rate and handling time are optimized at intermediate temperatures**, not monotonic with warming (Uiterwaal & Delong, 2020). The temperature-performance shape is shown directly in the partial regressions for handling time and space clearance. **Figure 2:** Unimodal temperature dependence of functional response parameters (Uiterwaal & Delong, 2020)


## Behavioral And Thermal Equations

For birds, the attached audit explicitly asks for species-specific **forage probability**, **insect activity sensitivity**, **thermal tolerance**, **behavior durations**, and **seasonal habitat shifts** compatible with an existing weather-authoritative framework . The evidence base supports making foraging decline at high temperatures, with threshold-like deterioration above about **35–35.5°C** in arid birds, plus increased use of shade, water, and cooler microsites (Funghi et al., 2019; Van De Ven et al., 2019; Du Plessis et al., 2012; Van De Ven et al., 2019).

A practical bird activity function is:
\[
p_{forage}= \sigma(\beta_0+\beta_1 I+\beta_2 Sun-\beta_3 Wind-\beta_4 HeatStress+\beta_5 Social)
\]
where \(I\) is insect or food activity, `HeatStress = max(0, T_{air}-T_{ref})`, and `Social` captures the finding that social partners can predict winter morning feeder activity better than overnight temperature alone (Madsen & Shizuka, 2021). This same structure matches the audit’s requested mapping `forage_probability = g(insect_activity, patch, time_of_day)` and weather-linked behavior validation .

For thermal traits, use **TNZ, LCT, and UCT/Tuc cautiously**. Reviews of mammals argue TNZ is often misused as a zone of thermal tolerance, and UCT is often confused with critical thermal maxima (Mitchell et al., 2018). A critique of endotherm compilations found major dataset errors in reported LCT and UCT values, and newer bat work argues **TUC based on metabolism alone is not an appropriate indicator of thermal tolerance** (Wolf et al., 2017; Welman et al., 2024). For birds, species-specific heat tolerance should instead combine body mass scaling with evaporative performance, because passerine maximum body temperature and heat tolerance limit scale with mass as:
\[
T_b^{max}= -0.814\log_{10}M_b + 45.734
\]
\[
HTL=4.867\log_{10}M_b + 43.040
\]
with substantial among-species variation around these regressions (McKechnie et al., 2021).

## Implementation Priorities

- **Prioritize elk, wolves, bison, vegetation, and monitored birds first**, because the attached audit flags bald eagle, osprey, golden eagle, red-tailed hawk, sandhill crane, great blue heron, pelican, common loon, bufflehead, and hooded merganser as highest-priority monitored taxa .
- Encode **spatial behavior shifts** for elk, because predation risk pushes elk from preferred grasslands into forests, increases vigilance, reduces foraging, and lowers diet quality and calf recruitment (Mosley & Mundinger, 2018).
- Encode **system complexity beyond elk-wolf only**, because Yellowstone trophic cascades now include stronger influences from grizzlies, cougars, and bison, making spatially variable outcomes more realistic than a single park-wide cascade (Boyce, 2018).
- Treat **bison grouping seasonally rather than density-driven**, because group size did not increase despite a three-fold abundance increase, but did vary strongly by season (Jung, 2020).

For a Yellowstone Python sim, the strongest evidence supports **dynamic, seasonal, state-dependent equations** rather than fixed carrying capacities, monotonic warming effects, or single-threshold thermal rules. The attached audit’s architecture is consistent with that literature: species modules should carry provenance, uncertainty status, weather-coupled behavior, and observable validation targets before broader avian expansion proceeds .
 
_These search results were found and analyzed using Consensus, an AI-powered search engine for research. Try it at https://consensus.app. © 2026 Consensus NLP, Inc. Personal, non-commercial use only; redistribution requires copyright holders’ consent._
 
## References
 
Phase 2: Avian Diversity Audit and Documentation.
 
Boyce, M. (2018). Wolves for Yellowstone: dynamics in time and space. *Journal of Mammalogy, 99*, 1021 - 1031. https://doi.org/10.1093/jmammal/gyy115
 
Du Plessis, K., Martin, R. O., Hockey, P., Cunningham, S., & Ridley, A. (2012). The costs of keeping cool in a warming world: implications of high temperatures for foraging, thermoregulation and body condition of an arid‐zone bird. *Global Change Biology, 18*. https://doi.org/10.1111/j.1365-2486.2012.02778.x
 
Funghi, C., McCowan, L. S. C., Schuett, W., & Griffith, S. (2019). High air temperatures induce temporal, spatial and social changes in the foraging behaviour of wild zebra finches. *Animal Behaviour*. https://doi.org/10.1016/j.anbehav.2019.01.004
 
Jung, T. (2020). Investigating local concerns regarding large mammal restoration: group size in a growing population of reintroduced bison (Bison bison). *Global Ecology and Conservation, 24*. https://doi.org/10.1016/j.gecco.2020.e01303
 
Koons, D., Colchero, F., Hersey, K. R., & Gimenez, O. (2015). Disentangling the effects of climate, density dependence, and harvest on an iconic large herbivore's population dynamics.. *Ecological applications : a publication of the Ecological Society of America, 25 4*, 956-67. https://doi.org/10.1890/14-0932.1
 
Kumari, N., Singh, A., & Kumar, A. (2025). The first mathematical model for elk–wolf interaction in Yellowstone National Park using the E-SINDy algorithm. *Ecological Modelling*. https://doi.org/10.1016/j.ecolmodel.2026.111574
 
Madsen, A. E., & Shizuka, D. (2021). Social partners and temperature jointly affect morning foraging activity of small birds in winter. *Behavioral Ecology*. https://doi.org/10.1093/beheco/araa134
 
McKechnie, A., Gerson, A., & Wolf, B. (2021). Thermoregulation in desert birds: scaling and phylogenetic variation in heat tolerance and evaporative cooling. *Journal of Experimental Biology, 224*. https://doi.org/10.1242/jeb.229211
 
Menden, E. (2019). Computationally Modeling the Trophic Cascade in Yellowstone National Park.
 
Mitchell, D., Snelling, E. P., Hetem, R., Maloney, S., Strauss, W. M., & Fuller, A. (2018). Revisiting concepts of thermal physiology: Predicting responses of mammals to climate change. *Journal of Animal Ecology, 87*, 956–973. https://doi.org/10.1111/1365-2656.12818
 
Mosley, J., & Mundinger, J. G. (2018). History and Status of Wild Ungulate Populations on the Northern Yellowstone Range. *Rangelands, 40*, 189 - 201. https://doi.org/10.1016/j.rala.2018.10.006
 
Passoni, G., Coulson, T., Cagnacci, F., Hudson, P., Stahler, D., Smith, D. W., & Lachish, S. (2022). Investigating tri-trophic interactions using bio-energetic demographic models. *bioRxiv*. https://doi.org/10.1101/2022.04.07.487507
 
Taper, M., & Gogan, P. (2002). The northern Yellowstone elk: density dependence and climatic conditions. *Journal of Wildlife Management, 66*, 106-122. https://doi.org/10.2307/3802877
 
Uiterwaal, S. F., & Delong, J. P. (2020). Functional responses are maximized at intermediate temperatures.. *Ecology*, e02975. https://doi.org/10.1002/ecy.2975
 
Van De Ven, T. V. D., McKechnie, A. E., & Cunningham, S. J. (2019). The costs of keeping cool: behavioural trade-offs between foraging and thermoregulation are associated with significant mass losses in an arid-zone bird. *Oecologia, 191*, 205 - 215. https://doi.org/10.1007/s00442-019-04486-x
 
Varley, N., & Boyce, M. (2006). Adaptive management for reintroductions: Updating a wolf recovery model for Yellowstone National Park. *Ecological Modelling, 193*, 315-339. https://doi.org/10.1016/j.ecolmodel.2005.09.001
 
Welman, S., Breit, A. M., Levesque, D., & Nowack, J. (2024). The upper limit of thermoneutrality is not indicative of thermotolerance in bats.. *Journal of thermal biology, 124*, 103933. https://doi.org/10.1016/j.jtherbio.2024.103933
 
Wolf, B., Coe, B. H., Gerson, A., & McKechnie, A. (2017). Comment on an analysis of endotherm thermal tolerances: systematic errors in data compilation undermine its credibility. *Proceedings of the Royal Society B: Biological Sciences, 284*. https://doi.org/10.1098/rspb.2016.2523
 
