# Worker brief: SNOTEL site discovery for Firehole/Madison validation

You are a parallel research worker in the OpenCode CLI. Your ONLY job is described below.
Work straight through without checking in. Do not touch anything outside what is named here.

## Context

Project: yellowstone_python at yellowstone/yellowstone_python/
The main session is validating a snow + soil-water model (file yellowstone_python/snow_season.py,
a degree-day snowmelt plus soil-bucket module) against real SNOTEL observations. Your discovery
output is the input to that validation. Prior sessions already fetch USGS streamflow plus
Open-Meteo forcing with Python stdlib urllib; the pattern to imitate lives in
yellowstone/yellowstone_python/tools/fetch_firehole_obs.py (read it, do not modify it).

## Your task (research only, no code changes)

1. Find 1-2 NRCS SNOTEL sites in or near the Firehole River / Madison River drainage
   (Yellowstone National Park and vicinity, e.g. near Old Faithful, Madison Junction,
   West Yellowstone). Discover real site numbers via web search and NRCS sources.
   Never invent a site number. Verify each candidate actually exists (station page,
   coordinates, period of record).
2. For each site record: site number, name, latitude/longitude, elevation,
   drainage it represents, variables available at daily resolution
   (precipitation, SWE, snow depth, air temperature), and period of record.
3. Work out the exact data-access pattern: NWCC AWDB REST endpoints or report URLs,
   query parameters for a daily time series over a recent window, units returned.
   Prefer a pattern fetchable with stdlib urllib (plain HTTPS GET returning CSV or JSON).
4. Record one concrete recent window (e.g. water year 2025 Oct-2025 through melt-out 2026,
   or whatever the record supports) that has all four variables present.

## Deliverable

Write exactly one file, nothing else:

yellowstone/yellowstone_python/worker_briefs/snotel_sites_2026-10-10.md

Contents: a table of the 1-2 sites with all fields from step 2, the exact fetch URLs
or endpoint-plus-parameters from step 3 (with units and fetched_at_utc provenance notes),
the recommended validation window from step 4, and anything that did NOT verify
(mark unverified items clearly). Keep it under 120 lines.

## Bounds

- Do NOT edit, create, or delete any other file in the repo or elsewhere.
- Do NOT run anything that spends money, sends email, or posts data anywhere.
- Reads and web fetches are fine. If a tool call asks for an approval you cannot
  obtain, stop there and report what you found so far in your final reply text.
- When the report file is written, reply with a 5-line summary and stop.
  Do not dispatch follow-up work. Do not start modeling.
