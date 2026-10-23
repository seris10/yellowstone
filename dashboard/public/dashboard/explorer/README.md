# Midway terrain explorer

Explore the slopes, waterways and pools around Yellowstone’s Midway Geyser Basin, with a saved temperature simulation along the Firehole River.

## Open the explorer

Run this command from the explorer folder, then open `http://127.0.0.1:4184/`:

```sh
python3 -m http.server 4184 --bind 127.0.0.1
```

The 3D view needs JavaScript and WebGL 2. All libraries and data are included locally; the browser does not fetch them from a CDN.

## Explore the map

Drag to rotate, right-drag to pan and scroll to zoom. Click a feature for details, or select it in the right-hand panel. Reset view, North up and the viewpoint menu help you get back to a familiar position.

The opening view covers a 4.096 km square. Switch to the 1.28 km core for finer terrain around the thermal area. Heights start at **3× vertical exaggeration** to make the slopes easier to see; choose **1×** for true scale. The lighting, terrain palette and waterway glow can all be adjusted.

Turn on tree crowns to explore the LiDAR detections. The height slider filters shorter crowns. Pool outlines and mapped waterways have separate controls, as do the drainage paths calculated from elevation.

## River temperature

The colored river band shows temperatures from a saved simulation. Play the run or drag the timeline, then select a river section to see its exact temperature and history. The band is drawn over the glow so its colors stay visible.

Three color scales are available beside the legend:

- **Absolute temperature** keeps the same 17.49–18.68 °C scale throughout playback.
- **Focus** uses a 0.10 °C window to reveal smaller differences. Selecting a river section or recentering the scale sets the window around that section’s temperature. The window then stays fixed during playback.
- **Change from start** shows the difference from each section’s first saved temperature, on a fixed −0.06 to +0.06 °C scale. Blue means cooling; orange means warming.

The model has 276 river sections and 721 saved steps spanning two hours. Flow and upstream temperature were chosen for this example, and river widths and depths are estimates. The displayed band is widened for visibility. This run has not been checked against field temperature measurements and is not a forecast of current conditions.

## Terrain and drainage

The full view retains all 1,050,625 elevations in the saved 4 m USGS grid, arranged as 1025 × 1025 samples. The core uses a 640 × 640 grid at 2 m spacing, retaining every second pixel from the original 1 m elevation raster. Lighting detail comes from the actual terrain gradients: 4 m for the full view and 1 m for the core. No terrain noise or invented microtexture is added.

Drainage paths follow downhill routes calculated from that full 4 m grid. The calculation fills depressions to find their spill levels, then routes each sample toward one of its eight neighbors (D8). It accumulates the area feeding each route and assigns Strahler branch order. The displayed terrain itself stays unchanged.

The drainage detail control sets the minimum contributing area. The default 0.5 hectare threshold shows 2,948 path fragments; 2 hectares shows 1,367, and 8 hectares shows 683. These counts include fragments separated by gaps. Segments touching filled depressions, or slopes below 0.2%, are omitted rather than joined across uncertain ground.

These are possible runoff routes, not surveyed streams. Their shape depends on the elevation grid, depression handling and area threshold. Land outside the map contributes no area to this calculation, and groundwater, culverts and seasonal flow are not represented. For background, see the [Priority-Flood method](https://rbarnes.org/sci/2014_depressions.pdf) and [USGS work on drainage extraction from LiDAR terrain](https://www.usgs.gov/publications/using-selective-drainage-methods-extract-continuous-surface-flow-1-meter-lidar-derived).

## Ground layers and profiles

The analysis controls load optional layers as you use them:

- **Microbial communities** shows the saved 1 m categorical grid, with the area of each class. These classes come from temperature rules, an assumed pH and chosen class boundaries. They are not field-mapped communities.
- **Outflow temperature** shows the saved 1 m cooling calculation. Click a cell for its value. Open **Outflow transect** to choose two map points or enter local coordinates, draw a profile, and download its samples as CSV. The profile keeps gaps where the source has no data.
- **Residual canopy cover** shows the fraction of each 2 m cell covered by LiDAR canopy outside detected crown cores. Source coverage is reported separately. This complements the crown layer; it does not count trees.
- **Approximate forest** puts simple cone shapes at detected crown locations, using the recorded height and core radius. The shapes illustrate canopy structure without assigning species or inventing additional trees.

## Scenarios, habitat and weather

The scenario menu compares the original run with a hypothetical **5°C reduction in thermal inflow temperature**. Both cases use the same initial water temperatures, geometry, flow and weather. The river solver produced the comparison; the unchanged configuration reproduced every saved baseline value exactly. Choose the difference view to color each river section by its change relative to the original run, or select a section to compare both histories. The fixed difference scale is −0.20 to 0°C; values below the scale use its darkest blue. Both are illustrative simulations. Ground overlays keep the original snapshot.

**Trout feeding factor** colors the original run by the model’s species-specific thermal response, from 0 to 1. Five species are available. This is one habitat factor, not a fish abundance or complete habitat suitability map; food, cover and oxygen are outside this layer.

**Scenario weather** follows the same two-hour timeline using 121 saved one-minute samples. Air temperature and wind come from the scenario’s authored weather trajectory. Humidity and cloud fraction stay fixed. These are simulated conditions, not current weather. The optional steam display starts at the four thermal sources and leans with that saved wind. Plume shape and opacity are illustrative.

Use **Compare view** to switch between selected layers, terrain alone, mapped geography and analysis without decorative overlays. **Expand charts** opens the inspector and linked plots in a larger panel; close it with the button or Escape.

## Data sources

| Layer | Source and meaning |
| --- | --- |
| Terrain | USGS elevation data. The core LiDAR survey was flown September 29–October 9, 2020. The full grid is a saved USGS 3DEP service export. |
| Waterways, trails and roads | NPS Yellowstone GIS lines, placed on the displayed terrain. Line width is a display choice. |
| Pool outlines | Park map polygons or outlines estimated from gaps in LiDAR returns. The details panel identifies each source. Pool and river bottoms were not surveyed for this view. |
| River temperatures | Stored output from the river heat-transport model. The browser plays back values without rerunning the simulation. |
| Tree crowns | 34,303 crown detections from LiDAR. Circles show the detected core area, not full crown width. The results do not identify species or count every tree, and have not been independently checked against a field tree survey. |
| Colors and lighting | Display choices. Pool tints do not map temperature or microbial communities. The solid terrain base does not show underground geology. |

Coordinates use UTM zone 12N (EPSG:32612) and elevations use NAVD88. Local x points east, z south and y up. Before height exaggeration, one scene unit is one meter: `x=E−E0`, `z=N0−N`, `y=H−2200`. Overlay heights follow the displayed terrain triangles and stop at the grid boundary. The retained core sample centers span −639.5 to 638.5 m on each local axis.

The [data manifest](data/manifest.json) records source files, processing settings and SHA-256 checksums. The river data comes from saved build `cca3820afdd4`. The recorded input hashes identify the files used for this export.

## Rebuild and check

Python, NumPy and Pillow are required. From this folder, supply a Yellowstone checkout containing the saved build and source rasters:

```sh
python3 export.py --root /path/to/yellowstone --build cca3820afdd4 --out .
python3 export-normals.py --root /path/to/yellowstone --out .
python3 export-drainage.py --root /path/to/yellowstone --out .
python3 export-layers.py --root /path/to/yellowstone --out .
npm test
YELLOWSTONE_ROOT=/path/to/yellowstone python3 test-drainage.py
python3 independent-source-checks.py --root /path/to/yellowstone --out .
```

The normal-map exporter also runs checks on gradients and image encoding. Source comparisons check exported values against the original files, and the browser checks each data asset against the manifest before using it. Checksums establish file identity, not scientific accuracy.

With Playwright and local Chrome installed, keep the preview server running and run:

```sh
node browser-check.cjs
```

The matched scenario can also be reproduced without the original build directory. Install the Yellowstone Python package from this repository, then run `python3 rebuild-scenario.py`. The included `data/scenario-input.json` contains the full solver configuration and exact solver hash; the check compares all original and changed temperatures.

The source repository includes tests for coordinates, data integrity, profiles, scenario matching and browser controls. Desktop browser checks do not establish physical touch behavior, screen-reader usability or field accuracy.

## Add it to a generated dashboard

The integration helper copies the explorer to `/dashboard/explorer/` in a freshly generated Yellowstone dashboard. It checks the saved-build identity and asset hashes, adds a navigation link, and updates the generated worker allowlist. It refuses to overwrite an existing explorer folder.

```sh
python3 integrate.py --site /path/to/generated-site --dashboard-source /path/to/yellowstone/dashboard
DASHBOARD_PREVIEW=/path/to/generated-site node --test test-integration.mjs
```

Vendored module imports use local relative paths, so the dashboard’s content-security policy can stay unchanged. Only the integration helper’s explicit public file list is copied; test logs and review records stay out of the website.

## Credits and licenses

USGS 3DEP records identify the elevation products as U.S. Government public-domain works. NPS vectors retain credit to the Yellowstone Spatial Analysis Center. The export comes from the owner’s Yellowstone workflow, with individual sources listed in the manifest.

Three.js 0.180.0 is included under the [MIT license](vendor/three-LICENSE.txt). The Yellowstone source license is included in [yellowstone-LICENSE.txt](yellowstone-LICENSE.txt).
