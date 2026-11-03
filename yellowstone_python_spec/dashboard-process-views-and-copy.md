# Dashboard process views and copy

Requested 2026-10-18. Scope: the public Yellowstone dashboard, its copy, process data views, and system analysis. Preserve the existing visual design and unrelated work in progress.

## Findings

The explorer assigned steam and weather the same ambient weather preview. That preview contained only the 60-second diagnostic, although the checked build has 721 weather samples across 7,200 physical seconds. In build `f75347b772fd`, air temperature changes from 21.2658477444 to 17.0369590954 °C across the full run. A zero-based chart of its first minute concealed most useful variation.

Several process views substituted a related process's result: snow storage for reference evapotranspiration; vegetation biomass for grazing and mammals; river shading for canopy structure; pool parameters for outflow cooling and its food web; and temperature or oxygen for fish feeding and benthic insects. These substitutions were labeled as context but displaced available process-specific outputs. Several processes with checked outputs had no plot.

The steam output is a single plume diagnostic. It supplies upwind/downwind air temperature and humidity, warming, moisture increase, and heat fluxes. It does not contain a plume trajectory, measured air transect, or evolving plume field. Extending it to a day or animating it with the river clock would fabricate temporal support.

## Requirements

1. Use direct saved outputs or explicitly prescribed inputs for the selected process. Do not silently replace missing results with a neighboring process's chart.
2. Use all saved times for weather and other exported trajectories. Show physical elapsed time and the actual recorded span. No new forecast, fabricated daily cycle, interpolation, or model rerun is part of this change.
3. For constant series, show the value, sample count, window, and missing count instead of a flat interactive. For static diagnostics, show their values or spatial field without playback.
4. Prefer a relevant plot to repeated generic layouts. Hide maps with no spatial values, distributions without variation, and comparisons without meaningful paired variation.
5. Preserve source hashes, units, missing samples, native cell orientation, and spatial aspect ratio. Verify content-addressed dataset bytes before displaying them. Loading or identity failures must be explicit and retryable.
6. Keep process quantity/entity selections in URLs. A full-system link must open the matching native quantity and selected entity when a corresponding system dataset exists.
7. Retain the existing scene, palette, fonts, and zoom navigation. Provide keyboard or range-input access to samples and native cells, and paginated tables.
8. Rewrite promotional language, vague abstractions, and repetitive rhetorical lists. Keep a list when it names the actual modeled constituents or interface controls; do not turn a partial example list into a claim of comprehensive coverage. Preserve uncertainty and authorship distinctions.

## Process coverage

| Process | Implemented data view | Time/support limits |
|---|---|---|
| Weather forcing | Full air-temperature and wind trajectories; humidity, clouds, precipitation | All 721 saved times; constant variables stated explicitly |
| Steam microclimate | Upwind/downwind temperature and humidity; warming, moisture increase, latent/sensible flux | One saved plume calculation; no playback |
| Surface heat exchange | Cumulative net river-surface heat transfer | Recorded river budget; selected run uses lumped Newton exchange |
| Heat transport | Existing linked distance/time field and profiles | Saved river states; full dataset retains every frame |
| Reach mixing | Per-reach temperature trajectories | Flow-weighted reporting reaches from channel solver, not a separate six-reach experiment |
| Upstream boundary | Prescribed discharge and temperature | Constant values or native forcing samples |
| Lateral inflows | Baseline source temperatures and discharge | Prescribed source connections; baseline excludes a timed intervention |
| Downstream export | Last-cell temperature, cumulative water and sensible heat export | Saved downstream budget; heat uses solver reference |
| Channel-bed exchange | Cumulative exchange and final storage-zone temperature profile | Recorded river budget; final profile labeled separately |
| Solute transport | Chloride, arsenic, and boron concentration profiles | Final saved solute window; cell IDs matched to channel geometry |
| Shading | Existing shortwave transmission by river cell | Static diagnostic with its own support |
| Ground heat | Native ground-heat raster | Authored steady heat field |
| Thermal plume | Native two-dimensional temperature raster | Steady plume calculation, separate from river playback |
| Pool temperature | Selectable radial profiles and center/edge parameters | Authored radial shape; no pool evolution or measured radial transect |
| Outflow cooling | Native outflow-temperature raster with missing dry cells | Steady routed water-film calculation |
| Snow and soil | Snow/soil trajectories by patch; spin-up accounting | Scenario trajectories and earlier spin-up remain separate |
| Reference evapotranspiration | Actual reference demand | A diagnostic, distinct from bucket water removal |
| Vegetation | Biomass, moisture, nutrients, trampling, resources, capacity | Saved patch series; authored capacity identified |
| Grazers | Selectable authored route geometry | No tracked animal positions or trajectory playback |
| Mammals | Activity, population equivalents, predation risk | Saved guild/representative trajectories; no observed abundance claim |
| Canopy | Crown heights/core areas and native residual-canopy/support grids | 2020 LiDAR support, separate from scenario epoch |
| Dissolved oxygen | Native cell concentration profile | Static diagnostic; no river-clock animation |
| Periphyton | Native cell biomass profile | Static diagnostic with separate numerical increment |
| Fish | Brown-trout feeding response; stressor factors; species thermal anchors | Saved feeding series; authored response scores, not consumption measurements |
| Benthic invertebrates | Stocks, emergence, disturbance loss, food resources | Independent increments/windows remain labeled |
| Insect compartments | Actual final compartment stocks | Relative model stocks, not field counts |
| Above-water consumers | Accumulated insect consumption by consumer | Model stocks; no invented rate or observation window |
| Piscivore predation | Mortality rates by trout refuge and refuge depths | Authored predation model, not measured mortality |
| Outflow food web | Fly recruitment, predation and parasitism rates; modeled stock | Per-day rates and standing stock have separate units; authored biomass |
| Microbial mats | Native classified area by modeled surface class | Cell counts × cell area; includes non-mat classes; no measured biomass claim |

## Implementation

`dashboard/process_data.py` creates a catalog from checked artifacts and native system exports. Native system fields are referenced rather than copied into the snapshot. Small process-specific budgets, profiles, prescribed values, and route geometry retain their source hashes in the public catalog.

`dashboard/public/process-data.js` resolves each quantity, loads native data on demand, and selects a suitable plot or scalar/table view. Where an entity has a saved trajectory, the default entity is the one with the largest saved range; its identity is displayed and can be changed. Full saved samples are retained, including explicit missing values. Static spatial maps preserve native orientation and equal aspect. Source tables paginate at 25 rows.

The summer snapshot opens with soil-water storage rather than constant zero snow. The geothermal workbench opens the outflow-temperature field. Quantity comparisons are opt-in and cannot default to a self-comparison. The existing river transport and direct shading views remain in place. Research extensions produce no numerical views. The system workbench removes empty or constant charts rather than filling a fixed layout with uninformative copies.

## Acceptance and evidence

- Export checks compare process values against the selected checked artifacts, including every weather time, steam values, budget signs/units, native raster hashes, and mat cell counts. Corrupt artifacts and mismatched dimensions must fail.
- JavaScript checks cover missing data, constant detection, quantity-to-entity selection, and profile/trajectory identity. Existing dashboard tests must continue to pass.
- Browser checks exercise the actual staged release: weather, steam, static/constant data, pool profiles, raster probes, routes, process-specific ecology, deep links, and full system analysis. Check representative narrow layouts separately.
- Verify canonical production deployment metadata and fetch the plain production URL and changed assets after release. Source changes or successful upload alone do not establish publication.
- This change does not establish ecological validity, field accuracy, physical-device behavior, or scientific acceptance. Human judgment of the wording remains separate from automated checks.

## Verified release

Published to `yellowstone-dashboard.pages.dev` on 2026-10-18, production deployment `eb806f9c-711a-45ef-8937-557fab35c546`, branch `main`. Canonical deployment metadata reports success. The production weather and steam views were checked in the browser. All 39 public dashboard assets match the reviewed stage byte for byte. Unknown routes return 404 and unsupported methods return 405.

Validation: 36 Python tests and 57 JavaScript tests passed. Browser checks covered all 30 implemented processes, all seven system workbenches, the other dashboard pages, constant values, native raster probes, pool selections, paginated tables, optional comparisons, and links into full datasets. Representative controls were checked at a 390 px viewport width; overlapping chart-unit labels found during review were corrected and rechecked. Physical devices and Safari/WebKit were not tested.

The seven existing system datasets retain all numeric values; native river dataset bytes are unchanged. The new views reuse checked outputs from build `f75347b772fd`. Steam remains a single saved plume calculation; no plume time series was created. Unrelated repository changes were excluded from publication.
