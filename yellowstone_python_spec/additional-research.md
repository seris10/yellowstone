Online research results for the missing information. Each item maps to a registry or `H(x)` field that is currently `unknown`, empty, or asserted without a source.

## 1. Water-temperature sensor accuracy (fills `measurement_error`)

Agency standards, not guesses:

- **USGS TM 1-D3** (Wagner et al. 2006, https://pubs.usgs.gov/tm/2006/tm1D3/pdf/TM1D3.pdf): modern thermistors measure to **±0.1 °C**, manufacturer accuracy must be verified for the range of application.
- **USGS NFM A6.1 v3** (2024, https://pubs.usgs.gov/publication/tm9A6.1/full): field standard is **≤ ±0.2 °C** against a traceable/certified sensor, verified at least annually. Required when the sensor corrects another parameter.
- **RMN best practices** (USFS/EPA, https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P100HNP0.TXT): minimum **±0.5 °C**, with ±0.2 °C instruments encouraged where available.
- Older **USGS TWRI 1-D1** (https://pubs.usgs.gov/twri/twri1-d1/pdf/twri_1-D1_c.pdf): station record should be within **0.5%**, fixed systems stable within **0.5 °C**, resistance-bulb best practice ~0.3 °C long-term.

Usable value: `measurement_error = ±0.2 °C` with source NFM A6.1 when the deployed sensor is documented, else ±0.5 °C as the RMN floor. Both beat the current `"unknown"`.

## 2. Discharge uncertainty (fills the Q side of `H(x)`)

- **Sauer and Meyer 1992** (https://pubs.er.usgs.gov/publication/wri20014044): individual discharge-measurement error by root-sum-square of width/depth/velocity component errors. This is the cited method behind USGS measurement grades.
- **USGS rating practice** (2020 training deck, https://www.cbrfc.noaa.gov/present/crfs/2020spring/USGS_CRFS_20200326.pdf): qualitative grades **Excellent ±2%, Good ±5%**; rating shifts handled by V-diagram, unstable channels get new base ratings.
- **Kiang, Mason and Cohn 2016** (https://pubs.usgs.gov/publication/70178008): national survey of stage-discharge rating-curve and record uncertainty, Office of Surface Water.
- **Provisional-data caveat** (https://water.usgs.gov/nwc/provisional.html): telemetry data have had little or no review and may revise significantly. Directly supports keeping `provisional: True` in the station table.

Still needed from the agency record (not literature): the per-station rating grade for 06036805/06036905 in the study window. That number goes in the bundle provenance.

## 3. Point-sensor vs cross-section mean (fills `representativeness`)

This is the strongest literature result:

- **USGS TWRI 1-D1, Water Temperature chapter**: the reported temperature should represent the **mean cross-sectional temperature** except where complex gradients exist. Rule of thumb: install **two stations when variation exceeds 2 °C more than 5% of the time**. Gives three estimators: simple mean, area-weighted mean, discharge-weighted mean `Tq = Σ(q·t)/Q`.
- **Jones 1965, California streams** (https://pubs.usgs.gov/of/1971/0048/report.pdf): 180 cross-section traverses at 24 thermograph sites. Only 11 cases where probe differed from section mean by more than 1 °F. Tolerance interval: **99% of point observations within ±1.1 °F (±0.6 °C) of the mean at 95% confidence**. Temperature extremes within a section averaged ±0.15 °F from the mean.
- **Oregon 1963 tests** (https://pubs.usgs.gov/wsp/1819k/report.pdf): at 38 of 40 sites the inlet probe was within **0.7 °F** of the section average, 29 within **0.3 °F**. The exceptions were sluggish near-bank zones (up to 3 °F local variation) — moving water itself varied little.
- Caveat for Firehole specifically: **TempEst 2** (NOAA repository, satellite-based CONUS temperature model) notes predictions inherit "wherever in the cross-section each gage was located, not a cross-section mean," i.e. gage-location scatter is real. And recent USGS practice (SIR 2023/5146, Skykomish/Snoqualmie) runs a **cross-sectional profile at deployment** to confirm the sensor is representative.
- Below thermal inflows is exactly the "complex gradient" case TWRI warns about, so the ±0.6 °C general bound is the prior, and one transect day at the downstream station (left/center/right plus depth, at two flows) replaces it with a site value.

## 4. Null-model benchmarks (justifies persistence + climatology + what RMSE scale means)

- **National-model benchmarking** (Towler et al., USGS 2023, https://www.usgs.gov/publications/benchmarking-high-resolution-hydrologic-model-performance-long-term-retrospective): NWMv2.1 and NHMv1.0 evaluated at 5,390 gages against a **seasonal climatological benchmark** with Kling-Gupta efficiency; ~80% of sites beat it, the rest get diagnostic scrutiny. Climatology-as-benchmark is community standard, which supports keeping `downstream_climatology` — with a corrected k (below).
- Scale context: **Diaz et al. 2025** (https://www.usgs.gov/publications/evaluation-daily-stream-temperature-predictions-1979-2021-across-contiguous-united) CONUS daily temperature model, reach RMSE **<2 °C**; **NorWeST** (Isaak et al. 2017, https://www.fs.usda.gov/rm/pubs_journals/2017/rmrs_2017_isaak_d004.pdf) mean-August model RMSPE **1.10 °C**, MAPE 0.72 °C, r² 0.91; **Segura et al. 2014** air-water model mean NSE 0.78 at reference sites. A holdout RMSE that beats persistence/mixing/climatology by a margin large against ~1 °C sensor-plus-representativeness noise is a defensible acceptance margin.

## 5. AIC parameter counting (settles the k-tuple)

- **Burnham and Anderson 2004** (https://sites.warnercnr.colostate.edu/wp-content/uploads/sites/73/2017/05/Burnham-and-Anderson-2004-SMR.pdf): `K` is the **total number of estimable parameters including the intercept and σ²**. Least-squares form `AIC = n·log(σ̂²) + 2K` with `σ̂² = Σ(ε̂²)/n`.
- Consequence for the `(0, 2, 0)` triple: the train-mean climatology estimates a mean, so **k=1 minimum** (plus σ² under the full counting convention), not 0. Persistence that replays lagged observations with no estimated coefficients stays k=0. Mixing-only reusing champion laterals inherits whatever was estimated on its construction path — the two code paths (`at_champion_laterals` vs `refit`) need distinct k values or one construction. If the current code omits σ² uniformly, relative rankings still hold but the absolute AIC values are off by a constant; document the convention in the artifact either way. Supporting implementation reference: **AICcmodavg** docs (https://cran.r-project.org/web/packages/AICcmodavg/refman/AICcmodavg.html), including AICc for small samples.

## 6. Firehole thermal regime (grounds regime bands in biology, not quantiles)

- **Kaeding and Kaya 1978** (https://www.osti.gov/biblio/5759538): warmest Firehole station maxima **exceeded 28 °C**, averaging **10.5 °C above** the unheated station year-round. Heated-station browns grew faster with two growth periods and shifted diets (dipterans, molluscs, emerging insects); rainbows shifted spawning spring→fall.
- **Kaya 1974–76 progress report** (https://www.osti.gov/biblio/7265240): warm section averaged **11.5 °C above** cold section; daily means **consistently exceeded the 20 °C** favorable-growth limit; maxima occasionally exceeded lethal levels; ~half of warm-station browns showed unmatured or atretic ova.
- **NPS management threshold**: fishing restrictions trigger at **68 °F (20 °C)** with low flows (e.g. https://www.nps.gov/yell/learn/news/24030.htm). NPS notes trout persisting above 75 °F (24 °C) in heated reaches with altered life functions.
- **Thermal loading context** (NPS): ~quarter of Firehole flow is hydrothermal influx over ~30 miles, up to **+25 °F (12 °C)**; Excelsior alone estimated **3,000–4,000 gpm** in the 1950s.
- **GYE air-stream sensitivity** (Alder, Hostetler and Al-Chokhachy, USGS/RegCM3): weekly air-stream slope **0.56 ± 0.20 °C/°C** May–September; projected stream warming 0.5–2.5 °C by mid-century.

Use: regime bands tied to the **20 °C stress threshold and dilution state** (low flow = stronger thermal signature) are biologically defensible; pure flow terciles of one 7-day window are not. The 668-point bundle (~7 days at 15-min) cannot span regimes by itself — another reason the locked-final window (item 7 in the prior memo) needs contrasting synoptic conditions.

## 7. Station-specific hooks (agency records to pull, not literature)

- **06036905 landing pages**: https://waterdata.usgs.gov/monitoring-location/USGS-06036905 and legacy https://waterdata.usgs.gov/nwis/uv?legacy=1&site_no=06036905. YVO station list confirms both Firehole gages: https://www.usgs.gov/volcanoes/yellowstone/science/real-time-stream-flow-data-yellowstone-national-park.
- **Thermal-relevant activity at this gage**: chloride-flux program samples at 06036905 (contact R. B. McCleskey, rbmccles@usgs.gov; https://catalog.data.gov/dataset/specific-conductance-firehole-river-near-west-yellowstone-usgs-gage-06036905). Specific conductance there tracks the same thermal loading the temperature claim models — a useful independent corroborator for the locked-final window.

## What this unlocks, concretely

| Field | Source above |
|---|---|
| `measurement_error` | NFM A6.1 ±0.2 °C (or ±0.5 °C floor) |
| `representativeness` prior | ±0.6 °C tolerance interval, TWRI two-station rule |
| Null set | climatology benchmark standard; k-tuple corrected per Burnham and Anderson |
| Regime bands | 20 °C biological threshold + dilution state |
| Station roles/datum/drainage | NWIS RDB pull + McCleskey chloride program corroboration |

Field work remaining after the literature: one transect day at the downstream station, the station rating grades for the window, and the independent locked-final fetch. Everything else on this list is now citable.