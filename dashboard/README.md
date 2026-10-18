# Yellowstone dashboard

The explorer displays saved model outputs from scenario `f75347b772fd`. Playback selects saved results; it does not run the model or display current weather.

## Build

```sh
python3 -m pip install -r dashboard/requirements-dev.txt
python3 dashboard/build_public.py --out work/site
python3 -m http.server 8427 --directory work/site
```

Open `/dashboard/` on that server. The build verifies the bundled inputs against `input-manifest.json`. `src/` contains editable browser assets; `public/` is the generated Pages deployment. A rebuild must reproduce the committed public files byte for byte. Extracting a different scientific generation requires its original checked artifacts and mapped inputs; the default build uses the public bundle.

## Process visuals

| Process | Visual and interaction | Data support |
|---|---|---|
| Steam microclimate | Source-to-downwind schematic; temperature/humidity quantity selector; pool/outflow contribution inspection | One bulk diagnostic. Source power is flux density multiplied by source area. No invented spatial gradient or time slider. |
| Pool temperature | Colored concentric rings linked to the radial profile; radius probe; pool selector | Saved authored radial temperature samples. The circular diagram does not represent measured bathymetry or shoreline. |
| Outflow cooling | Native temperature map with two editable transect endpoints and a linked distance profile | Steady raster at native cell resolution. Initial endpoints select a continuous, varying stretch. User transects retain dry-cell gaps; distance follows the straight transect, not routed flow. |
| Microbial mats | Native classified map; class highlighting; cell inspection; class counts and area | Exact saved class raster and authored display legend. Includes water and dry sinter. Area is cell count times cell area. |
| Channel-bed exchange | Paired water/bed profiles through all saved times; channel-cell probe and paired-store diagram | Exact saved channel and transient-storage temperatures. Opens the final frame at the largest paired temperature difference. The bed store is modeled water, not a sediment-depth section. |
| Trout habitat | Linked channel map and downstream feeding profile with saved-time and cell selection; factor breakdown | Brown-trout relative feeding response across 721 saved times. Separate diagnostic factors are multiplicative, not shares of a total. |
| Canopy structure | Linked crown map and distribution; numeric range filters and bin selection; individual crown inspection | All 34,303 LiDAR dominant-crown detections. Height/core-area colors use the saved numeric range. These detections do not identify species or count every stem. |

The other process quantities remain available. Weather uses the complete saved two-hour trajectory. Missing samples remain missing, and independent diagnostic windows stay separate. Sources, support, and unquantified uncertainty remain available under **Source and limits**.

Each additional process field is loaded separately when requested. The browser verifies its actual response bytes against the catalog SHA-256 before parsing or rendering. A failed load is retryable. Navigating away disposes chart observers and prevents a delayed response from mounting in a newer view.

## Verification

```sh
python3 -m pytest dashboard/test_public.py dashboard/test_domain_data.py dashboard/test_process_data.py dashboard/test_process_visuals.py -q -p no:cacheprovider
node --test dashboard/test_*.mjs
```

Tests cover native-value preservation, coordinate orientation, transect gaps, class area, temporal support, altered/stale data rejection, and chart disposal. Public clones can validate the bundled scenario; tests requiring original checked artifacts skip when those local artifacts are unavailable. Browser review additionally exercises the integrated controls and representative narrow layouts. These checks establish implementation behavior, not field accuracy or ecological forecast validity.
