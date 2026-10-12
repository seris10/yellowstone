Here is the running URL list, grouped by how much weight each source can bear. I'll append to it each time I add sources.

## Primary and official sources

**USGS gauges**
- https://waterdata.usgs.gov/usa/nwis/uv?site_no=06036905 - Firehole near West Yellowstone, at Firehole Canyon (fetched today). Temperature since 2011, discharge since 1994, stage since 2007, specific conductance 2010-2017 only.
- https://nwis.waterdata.usgs.gov/nwis/uv?cb_00065=on&cb_00060=on&cb_00010=on&cb_00021=on&format=gif_stats&site_no=06036805 - Firehole at Old Faithful. Temperature since 2011, discharge and stage since 2007.
- https://nwis.waterdata.usgs.gov/nwis/dv?site_no=06036805 - Station metadata: gage datum 7,339.88 ft NAVD88, drainage area 39.5 sq mi, field measurements back to 1929.
- https://pubs.usgs.gov/ds/632/ds632_text.pdf - USGS Data Series 632. Describes both Firehole gauges, 15-minute logger data, and Lone Star Geyser as the only substantial thermal source upstream of the Old Faithful gauge.
- https://catalog.data.gov/dataset/firehole-river-near-old-faithful-wy-yfof - Chemistry samples near gauge 06036905. The title says Old Faithful but the description says Madison Junction, so check which site it really is.

**NPS**
- https://www.nps.gov/yell/learn/news/26015.htm - 2026 closure and reopening release.
- https://www.nps.gov/places/000/excelsior-geyser-crater.htm - Excelsior discharges more than 4,000 gal/min.

**Lidar and terrain**
- https://ftpgeoinfo.msl.mt.gov/Data/Spatial/MSDI/Elevation/Lidar/Reports/YELLOWSTONENP_2020_QL1northUTM.pdf - 2020 3DEP report. The 0.5 m DEM is hydro-flattened.
- https://www.usgs.gov/observatories/yvo/news/yellowstone-exposed-new-elevation-map-reveals-parks-complex-geologic-history - Overview of the 2020 lidar.
- https://www.researchgate.net/publication/267098180_Using_Thermal_Infrared_Imagery_and_LiDAR_in_Yellowstone_Geyser_Basins - 2008 lidar plus thermal infrared in the three basins.

## Peer-reviewed literature

**Firehole-specific**
- https://pubs.usgs.gov/publication/70023441 (open copy: https://zenodo.org/record/1236403) - Goldstein et al. 2001. Sites up to 30°C; rainbow trout present at the hottest sites, brown trout absent.
- https://www.tandfonline.com/doi/abs/10.1577/1548-8659(1978)107%3C432:GADOTF%3E2.0.CO;2 - Kaeding & Kaya 1978. Growth and diets of brown and rainbow trout in heated versus unheated reaches.
- https://link.springer.com/article/10.1007/BF02783136 - Boron and trout. Its reference list is useful for the chain back to Burkhalter (1979 PhD thesis on thermal and hydraulic characteristics) and Kaya's reproduction work.
- https://agris.fao.org/search/fr/records/65dee0a963b8185d9ca9e2fd - Zeikus & Brock 1972, longitudinal temperature through the basins.
- https://home.nps.gov/features/yell/ofvec/resources/ecology.htm - Reference list including "summer use of coolwater tributaries" (a refuge-use paper to chase down).

**General salmonid thermal physiology**
- https://doi.org/10.3390/fishes8070337 - Review table of growth optima and critical maxima for brown, rainbow, and brook trout.
- https://journals.biologists.com/jeb/article/220/21/3976/33742/Upper-thermal-limits-of-growth-in-brook-trout-and - Brook trout growth limits.
- https://journals.biologists.com/jeb/article/218/5/803/14656/Selection-for-upper-thermal-tolerance-in-rainbow - Heat-selected rainbow trout strain.
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5146681/ - Rainbow trout, southern-range thermal tolerance.
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9773365/ - Westslope cutthroat CTmax (a different subspecies from Yellowstone cutthroat, so not directly transferable).
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11959187/ - Field CTmax in brook trout populations.

**Bathymetry methods**
- https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2025WR041177 - Legleiter 2026, approximating channel shape from a national cross-section database.
- https://arxiv.org/pdf/2312.11476 - Uses the HYDRoSWOT dataset of USGS hydraulic geometry.
- https://www.sciencedirect.com/science/article/abs/pii/S002216941930530X - Cross-sectional area matters more than shape for hydraulic outputs.

## Weak or secondary sources (use only as leads)
- https://en.wikipedia.org/wiki/Grand_Prismatic_Spring - 560 gal/min, 70°C. Cites geyserstudy.org, not a measurement series.
- https://en.wikipedia.org/wiki/Excelsior_Geyser - 4,000-4,500 gal/min at 93°C.
- https://bioinfo.bact.wisc.edu/themicrobialworld/LAHT/b24.html - Excelsior raises river temperature 3-4°C, river warms about 15°C overall.
- https://www.kunc.org/regional-news/2026-07-16/yellowstone-temporarily-closes-fishing-on-three-rivers-due-to-heat
- https://localnews8.com/news/2026/07/16/heatwave-triggers-emergency-fishing-closures-on-select-rivers-in-yellowstone/ - Source of the 86°F peak figure, which is reported secondhand with no measurement location.
- https://grokipedia.com/page/Firehole_River - The 261 sq mi downstream drainage area comes from here. I haven't verified it against USGS.

## Interim findings and my confidence

1. **Station coverage (high confidence).** Two continuous gauges bracket the whole thermal reach, and neither sits at Midway. Grand Prismatic is therefore ungauged, and between the two gauges there are only tributaries and discrete surveys. Temperature records start in 2011 at both. No continuous conductivity record exists at Old Faithful.

2. **Source terms (medium confidence).**
   - Excelsior is a documented NPS figure. Grand Prismatic is single-point secondary data.
   - My arithmetic: 4,050 gal/min is about 9 cfs, and 560 gal/min is about 1.2 cfs.
   - Mixing 9 cfs at 93°C into about 200 cfs at 12°C gives roughly +3.5°C. That matches the 3-4°C literature claim, but it assumes a river flow I picked, so treat it as a sanity check, not a result.
   - It would make a natural two-stream mixing fixture for the spec.

3. **Bathymetry (medium confidence, unfinished).** The 2020 lidar is hydro-flattened, so it won't resolve the channel bed. The spec already warns about this. I found no surveyed Firehole cross-sections beyond gauge field measurements. I haven't checked whether the gauge field-measurement records have usable width, depth and velocity.

4. **Species literature (medium confidence).**
   - Lab thermal optima and field occupancy disagree. Rainbow trout occupy sites up to about 30°C in the Firehole, well above lab optima.
   - Brown trout are absent from the hottest sites, though Goldstein et al. say boron and arsenic can't be excluded as a cause.
   - For `fish.py`, that argues for separate survival, growth, and occupancy endpoints.

5. **2026 event (medium confidence).** Closure dates are NPS-confirmed (July 9, July 15, July 29, lifted September 4). Dead trout were reported. The Oct 10 daily flow at gauge 06036905 is the lowest in the 37-year record. That makes 2026 a good hindcast candidate, but it can't be both a calibration year and the independent test, and the data are provisional.

## Still open
- Burkhalter's thesis (the closest prior work to your hydraulic and thermal core) hasn't been located online.
- Tributary gauges, NPS loggers, and weather stations (SNOTEL, RAWS) are unchecked.
- Whether Yellowstone cutthroat or mountain whitefish are in this reach is unverified.

---

That scope settles the reach: the two gauges are the chain endpoints, with Midway in between. I'll verify the Kaya refuge-behavior claim first, since the sim's `fish.py` cites it and the 24°C figure needs checking against the paper.The refuge-use literature is split across several papers, so I'll read the Kaeding 1996 full text to see which paper supports which temperature claim.I'll check the downstream gauge's inventory record for drainage area and datum, then see whether discrete field measurements (width, area, velocity) are retrievable for the bathymetry question.The Water Quality Portal lists discrete USGS sites between the two gauges, including one below the Upper Geyser Basin and one below the Lower. I'll check what those sites actually measured and when.One more check on which fish actually occupy this reach, since the species list drives which experimental literature applies.That scope fits what I found, with some caveats. I'm working from your summary, not the files, so anything about `fish.py` or the sim's internals below is inferred.

## New findings this round

**1. The serial chain has a large unexplained mass gain.**
- Drainage area is 39.5 sq mi at the Old Faithful gauge and 261 sq mi at the downstream gauge, so about 85% of the downstream basin enters between them.
- On Oct 2, 2026, Old Faithful read 34.6 cfs and the downstream gauge about 192 cfs, roughly 5.5x. The 192 figure is from a secondary aggregator, so confirm it against USGS.
- Excelsior discharges 4,050 gal/min, or about 9 cfs by my arithmetic. Grand Prismatic's 560 gal/min is about 1.2 cfs (single-source figure). Both are small next to a roughly 150 cfs lateral gain, so most lateral inflow is tributaries and diffuse springs or groundwater, none of which the chain models explicitly.
- If tributaries are folded into an uncalibrated boundary, the water and energy budgets only close through that term. The 5.5x gap is a concrete conservation-check target.

**2. The downstream gauge datum is inconsistent between USGS records.**
- The current monitoring-location page gives zero gage height as 7,056.08 ft NAVD88 (survey-grade GNSS, ±0.13 ft). Older inventory and Water Quality Portal records give 7,050 ft, interpolated from a topo map (±10 ft).
- The upstream gauge is 7,339.88 ft. Any stage-to-elevation step needs the current value.

**3. Record lengths overlap less than they look.**
- Continuous temperature at both gauges starts 2011-10-01, and discharge overlaps from 2007-10-01.
- A 2023 inventory snapshot suggests daily temperature at the downstream gauge goes back to 2002, which I haven't confirmed.
- Specific conductance at the downstream gauge is 2010-2017 only. USGS Data Series 632 describes the 2010 monitoring installs at both gauges (conductivity and temperature at 15-minute intervals).
- Downstream field measurements: 241 between 1983 and 2023 (per the snapshot). Whether they include usable width, area and velocity is unchecked.
- The Water Quality Portal notes that its interface excludes USGS data added after March 11, 2024, and that it migrates to a new system in September 2026. Ingestion should use the USGS Water Data APIs directly, not the Portal, for recent data.

**4. There are discrete USGS sites between the gauges.**
- Names: Firehole below Upper Geyser Basin, Firehole below Lower Geyser Basin, Fairy, Sentinel, and Nez Perce creeks, Iron Spring Creek, and Tangled Creek.
- I parsed the ID pairing from a flattened list, so I'd verify each ID before using it. I haven't checked variables or periods of record. These are water-quality sites, not necessarily continuous.
- A 2026 USGS data release has continuous specific conductance and Firehole streamflow from April 2025 for Upper Geyser Basin geysers. That's a rare independent upstream dataset.

**5. Two citation problems in the fish literature.**
- The refuge-use paper is Kaya, Kaeding & Burkhalter 1977, *Progressive Fish-Culturist* 39:37-39. Kaya 1977 (*Trans. Am. Fish. Soc.* 106:354-361) is the reproduction paper, and a related coolwater-tributary paper is Kaeding 1996.
- I couldn't read the refuge paper. One secondary source (Sullivan 2023) cites it for a threshold of about 23°C. I couldn't confirm the >24°C figure, so check it against the original before it stays in `fish.py`.
- Kaya 1978, "Thermal resistance of rainbow trout from a permanently heated stream, and of two hatchery strains" (*Prog. Fish-Cult.* 40:138-142), exists and is lab data on Firehole-origin fish. I couldn't find its results.

**6. Which species belong in the chain (medium confidence).**
- Brown and rainbow trout are the main species. Brook trout are mostly upstream of Kepler Cascades, which is above the Old Faithful gauge and so outside the chain.
- Mountain whitefish and grayling occur below Firehole Falls. I haven't confirmed whether the downstream gauge is below the falls, as your summary says. USGS describes it as "at Firehole Canyon."
- I found no evidence that Yellowstone cutthroat inhabit this reach.

**7. The 2026 summer is a candidate extreme-event test.**
- NPS-confirmed dates: closure after 2 p.m. on July 9, full closure July 15, daily closure again from July 29, restrictions lifted September 4. Dead trout were reported.
- Flow at the downstream gauge on Oct 10 is the lowest in its 37-year record for that date. Data are provisional.
- It could serve as an independent test year if calibration stays on earlier years, but the 86°F peak figure is secondhand with no measurement location.

## Cumulative URL list

**USGS and NPS primary**
- https://waterdata.usgs.gov/usa/nwis/uv?site_no=06036905
- https://waterdata.usgs.gov/monitoring-location/USGS-06036905/ (current datum, 261 sq mi)
- https://waterdata.usgs.gov/mt/nwis/inventory/?site_no=06036905&agency_cd=USGS (2023 snapshot)
- https://www.waterqualitydata.us/provider/NWIS/USGS-MT/USGS-06036905/ (older 7,050 ft datum)
- https://nwis.waterdata.usgs.gov/nwis/uv?cb_00065=on&cb_00060=on&cb_00010=on&cb_00021=on&format=gif_stats&site_no=06036805
- https://nwis.waterdata.usgs.gov/nwis/dv?site_no=06036805
- https://water.noaa.gov/gauges/06036905 (NWS record flow and bankfull stage)
- https://pubs.usgs.gov/ds/632/ds632_text.pdf
- https://catalog.data.gov/dataset/specific-conductance-firehole-river-near-west-yellowstone-usgs-gage-06036905
- https://catalog.data.gov/dataset/firehole-river-near-old-faithful-wy-yfof
- https://catalog.data.gov/dataset/specific-conductance-water-chemistry-and-streamflow-data-from-upper-geyser-basin-yellowsto
- https://data.usgs.gov/datacatalog/data/USGS:6827617bd4be02693eeaad8b
- https://www.sciencebase.gov/catalog/item/6668a566d34e9bcc607b7f61
- https://www.waterqualitydata.us/provider/NWIS/USGS-WY/ (discrete site list)
- https://www.waterqualitydata.us/publications/ (March 2024 data cutoff note)
- https://www.nps.gov/yell/learn/news/26015.htm
- https://www.nps.gov/places/000/excelsior-geyser-crater.htm
- https://www.nps.gov/yell/planyourvisit/upload/2026-Fishing-Regulations-digital.pdf
- https://www.nps.gov/yell/planyourvisit/fishing.htm

**Terrain and bathymetry**
- https://ftpgeoinfo.msl.mt.gov/Data/Spatial/MSDI/Elevation/Lidar/Reports/YELLOWSTONENP_2020_QL1northUTM.pdf
- https://www.usgs.gov/observatories/yvo/news/yellowstone-exposed-new-elevation-map-reveals-parks-complex-geologic-history
- https://www.researchgate.net/publication/267098180_Using_Thermal_Infrared_Imagery_and_LiDAR_in_Yellowstone_Geyser_Basins
- https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2025WR041177
- https://arxiv.org/pdf/2312.11476
- https://www.sciencedirect.com/science/article/abs/pii/S002216941930530X

**Firehole fish and thermal literature**
- https://pubs.usgs.gov/publication/70023441 (open copy: https://zenodo.org/record/1236403)
- https://www.tandfonline.com/doi/abs/10.1577/1548-8659(1978)107%3C432:GADOTF%3E2.0.CO;2
- https://link.springer.com/article/10.1007/BF02783136 (reference chain to Burkhalter 1979 and Kaya)
- https://agris.fao.org/search/fr/records/65dee0a963b8185d9ca9e2fd
- https://home.nps.gov/features/yell/ofvec/resources/ecology.htm
- https://www.researchgate.net/publication/227626172_Naturalized_salmonid_populations_occur_in_the_presence_of_elevated_trace_element_concentrations_and_temperatures_in_the_Firehole_River_Yellowstone_National_Park_Wyoming_USA (Kaeding 1996 abstract)
- https://esajournals.onlinelibrary.wiley.com/doi/10.1002/ecs2.4727 (cites Kaya 1977 for about 23°C)
- https://onlinelibrary.wiley.com/doi/10.1577/T06-072.1 (rainbow vs westslope cutthroat lethal limits)
- https://onlinelibrary.wiley.com/doi/10.1577/T02-127 and https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1095-8649.2010.02762.x (confirm Kaya citation details)

**General salmonid thermal physiology**
- https://doi.org/10.3390/fishes8070337
- https://journals.biologists.com/jeb/article/220/21/3976/33742/Upper-thermal-limits-of-growth-in-brook-trout-and
- https://journals.biologists.com/jeb/article/218/5/803/14656/Selection-for-upper-thermal-tolerance-in-rainbow
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5146681/
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9773365/
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11959187/

**Weak or secondary (leads only)**
- https://en.wikipedia.org/wiki/Grand_Prismatic_Spring
- https://en.wikipedia.org/wiki/Excelsior_Geyser
- https://bioinfo.bact.wisc.edu/themicrobialworld/LAHT/b24.html
- https://snoflo.org/report/flow/wyoming/firehole-river-near-west-yellowstone-mt/ (source of the 192 cfs figure)
- https://npshistory.com/publications/yell/smith-kendall/sec3.htm (historical fish list)
- https://en.wikipedia.org/wiki/List_of_fishes_of_Yellowstone_National_Park
- https://norrik.com/yellowstone-national-park-fish-species/
- https://www.kunc.org/regional-news/2026-07-16/yellowstone-temporarily-closes-fishing-on-three-rivers-due-to-heat
- https://localnews8.com/news/2026/07/16/heatwave-triggers-emergency-fishing-closures-on-select-rivers-in-yellowstone/
- https://grokipedia.com/page/Firehole_River

## Still unresearched
- Weather forcing stations (SNOTEL, RAWS, NOAA cooperative stations near Old Faithful).
- Burkhalter's 1979 thesis (not found online).
- The contents of the gauge field-measurement records.
- Per-site variables and periods for the discrete sites above.

Does `fish.py` include any species beyond brown, rainbow and brook trout, such as cutthroat or whitefish? That decides how much of the species literature I should chase next.

