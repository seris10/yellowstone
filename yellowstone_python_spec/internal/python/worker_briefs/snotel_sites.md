# SNOTEL sites for Firehole/Madison snow validation — 2026-10-10

Both sites verified live against AWDB REST on 2026-10-10 (fetched_at_utc ~2026-10-10T05:50Z).
Station metadata + daily data both confirmed via plain HTTPS GET (stdlib urllib compatible).

## Site table

| # | Triplet | Name | Lat / Lon | Elev | HUC (drainage) | County / SHEF | Record |
|---|---------|------|-----------|------|----------------|---------------|--------|
| 609 | 609:MT:SNTL | Madison Plateau | 44.58623, -111.11627 | 7710 ft (2350 m) | 100200070204 — upper Madison, plateau snow source ~15 km SE of West Yellowstone, between Firehole and Madison arms | Gallatin, MT / MPLM8 | 1967-10-01 – present |
| 924 | 924:MT:SNTL | West Yellowstone | 44.65866, -111.09199 | 6680 ft (2036 m) | 100200070205 — Madison R at West Yellowstone, valley floor ~5 km from Madison Junction / Firehole confluence | Gallatin, MT / WYSM8 | 1966-10-01 – present |

Station pages (HTTP 200, verified): https://wcc.sc.egov.usda.gov/nwcc/site?sitenum=609&state=mt and ...?sitenum=924&state=mt

## Daily variables (both sites, DAILY duration)

| Element | Meaning | Units (storedUnitCode) | 609 POR | 924 POR |
|---------|---------|------------------------|---------|---------|
| WTEQ | snow water equivalent | in | 1967-10-01 – | 1966-10-01 – |
| PRCP | precipitation accumulation | in | 1988-10-01 – | 1998-08-24 – |
| SNWD | snow depth | in | 1998-12-09 – | 2003-09-24 – |
| TAVG/TMAX/TMIN | air temp avg/max/min | degF | 1988-09-30 – | 1998-08-24 – |

All-elements overlap: 2003-09-24 – present at both sites.

## Fetch pattern (AWDB REST, plain GET, JSON)

Base: `https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data`

Params: `stationTriplets=<triplet, URL-encoded>` `elements=WTEQ,PRCP,SNWD,TAVG,TMAX,TMIN`
`duration=DAILY` `beginDate=YYYY-MM-DD` `endDate=YYYY-MM-DD`

Example (Madison Plateau, March 2026):
`.../data?stationTriplets=609%3AMT%3ASNTL&elements=WTEQ,PRCP,SNWD,TAVG,TMAX,TMIN&duration=DAILY&beginDate=2026-03-01&endDate=2026-03-05`

Response: `[{"stationTriplet":..., "data":[{"stationElement":{"elementCode","durationName":"DAILY","storedUnitCode",...}, "values":[{"date":"2026-03-01","value":16.8},...]}]}]`.
Null `value` = missing day. Convert in→mm (×25.4), degF→degC. No key required. Colons may be left unencoded; both forms tested OK.

## Recommended validation window: WY2026, 2025-10-01 – 2026-07-31

Verified coverage (304 days): 609 — WTEQ/SNWD/TAVG 304/304 non-null, PRCP 303/304 (only 2026-06-05 absent, post-melt);
924 — WTEQ/PRCP/SNWD 304/304, TAVG 303/304 (only 2026-07-28 null, post-melt). Neither gap affects snow physics.
Snow season: 609 first WTEQ>0 2025-10-11, peak 17.4 in (2026-03-10), melt-out after 2026-05-27;
924 first WTEQ>0 2025-10-27, peak 8.1 in (2026-03-04), melt-out after 2026-04-22.
Pair gives ~314 m elevation contrast on the same Madison-arm forcing.

## Not verified / notes

- Old Faithful snow course 10E18:WY:SNOW (44.45438,-110.82235, HUC 100200070102, in the Firehole drainage proper) exists but is a manual SNOW course, not automated SNOTEL — no daily series; rejected for daily validation.
- Black Bear (347) and Whiskey Creek (858) also exist in HUC 1002000702 but were not element-checked; fallback candidates only.
- PRCP is a daily accumulation increment; confirm accumulation-vs-increment semantics in consuming fetch code before water-balance use.
