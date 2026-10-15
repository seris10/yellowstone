# Third-party credits and source permissions

The release-specific `ASSET_INVENTORY.json` records inclusion decisions and exact bytes. KJR confirmed ownership of all animal meshes and authorized project release inclusion on 14 October 2026. The authoritative file inventory, creator names, acquisition status and SHA-256 checksums are in [data/asset_manifest.json](data/asset_manifest.json). Geographic download receipts and source metadata are in [references/geodata_manifest.json](references/geodata_manifest.json) and the accompanying provenance files. An included file is present in the project; inclusion does not mean every variant is used by the running scene.

## Original project work

Copyright © 2026 Yellowstone Midway project contributors. Original GDScript, Python authoring tools, shaders, documentation, source-independent proxy art and project-authored structures are supplied under the [MIT License](LICENSE). This includes the original wildlife and botanical stand-ins, deck/support geometry and scene assembly. Retain the MIT copyright and permission notice when redistributing substantial portions of that work.

MIT does not relicense the third-party assets or government source data below. **No claim to original U.S. Government works.** Project modifications are identified separately from the source measurements and artworks. This is an independent landscape project; agency and creator credits identify the sources rather than an endorsement.

## Animal meshes and motion software

KJR owns all animal meshes in this project and authorized their inclusion in the project release. The ownership statement covers supplied mammal, bird and fish geometry as well as authored shape proxies. It preserves existing source-method and generation records. Motion software uses MIT; Python adapters use Apache-2.0. Original files with explicit asset licenses retain those licenses. Owner-authorized inclusion does not assign a blanket open license to every supplied mesh.

Rig/contact checks are numerical execution evidence. Local species identification, biomechanics and ecological forecast acceptance remain separate and unaccepted. Per-file inventory fields distinguish presence, runtime use, geometry checks, source permissions, modifications and the release decision.

## Included Poly Haven artwork — CC0 1.0

[Poly Haven's asset license](https://polyhaven.com/license) places its downloadable models, textures and HDRIs under [Creative Commons Zero 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/). This permits modification and redistribution, including commercial use, without mandatory attribution. The following credits acknowledge the named artists. The asset license applies to the assets themselves; it does not assign the same permission to unrelated website content or example renders.

| Included source | Creator credit | Files and project modifications |
|---|---|---|
| [Pine Bark](https://polyhaven.com/a/pine_bark) | Dimitrios Savva / Poly Haven | `assets/textures/pine_bark_*`: 1K diffuse and OpenGL normal textures, assigned to project materials. |
| [Forest Ground 04](https://polyhaven.com/a/forest_ground_04) | Rob Tuytel; Rico Cilliers / Poly Haven | `assets/textures/forest_ground_04_*`: 1K diffuse and OpenGL normal textures, used in the terrain material. |
| [Rock Boulder Dry](https://polyhaven.com/a/rock_boulder_dry) | Dimitrios Savva; Rico Cilliers / Poly Haven | `assets/textures/rock_boulder_dry_diff_1k.jpg`: diffuse material reference/texture. |
| [Pine Tree 01](https://polyhaven.com/a/pine_tree_01) | Rico Cilliers; Rob Tuytel / Poly Haven | `assets/imported/pine_tree_01/`: selected variant b, compact glTF buffers, reduced woody geometry, replacement foliage cards derived from the source photographs, repacked alpha, three geometry levels and four rendered distant views. The large shared source binary is not packaged; retained metadata and conversion scripts document the derivative. |
| [Grass Medium 01](https://polyhaven.com/a/grass_medium_01) | Rico Cilliers; Rob Tuytel / Poly Haven | `assets/imported/grass_medium_01/`: selected clumps, removed display-layout transforms, repacked RGB/alpha and adjusted cutout materials. The shared source geometry buffer is included. |

The distant pine images are technical renders of the credited derivative model. The pine and grass sources have generic botanical labels; these credits do not establish a species identification. Conversion details are in [docs/asset-research.md](docs/asset-research.md) and the per-asset metadata.

## Included Yellowstone field recordings — public domain

The [NPS Yellowstone Sound Library](https://www.nps.gov/yell/learn/photosmultimedia/soundlibrary.htm) explicitly identifies its available recordings as public domain, permits downloading and reuse, and requests National Park Service credit where appropriate. The project preserves both the agency and individual recordist credits.

| Included file in `assets/audio/` | Recording and creator credit | Original location/date |
|---|---|---|
| `nps_geyser_hill_water.mp3` | [Geyser Hill water outflow](https://www.nps.gov/yell/learn/photosmultimedia/sounds-soundscapes.htm), **NPS/Peter Comley** | Geyser Hill, Upper Geyser Basin; 22 March 2015 |
| `nps_geyser_hill_birds.mp3` | [Geyser Hill birds](https://www.nps.gov/yell/learn/photosmultimedia/sounds-soundscapes.htm), **NPS/Peter Comley** | Geyser Hill, Upper Geyser Basin; 22 March 2015 |
| `nps_lower_basin_wind.mp3` | [Lower Geyser Basin strong wind](https://www.nps.gov/yell/learn/photosmultimedia/sounds-soundscapes.htm), **NPS/Peter Comley** | Lower Geyser Basin; 21 March 2015 |
| `nps_firehole_dipper_geese.mp3` | [American Dipper and Canada Geese](https://www.nps.gov/yell/learn/photosmultimedia/sounds-dipper.htm), **NPS & MSU Acoustic Atlas/Jennifer Jerrett** | Firehole River; 26 February 2014 |

The supplied MP3s retain their source recording content. Playback position, gain, looping and environmental use are project adaptations. Recordings made elsewhere in Yellowstone retain their original location/date; placement in this scene does not make them recordings of Midway in the represented season.

## Included geographic sources

### Elevation — U.S. Geological Survey

Credit: **U.S. Geological Survey, 3D Elevation Program (3DEP), The National Map**. The supplied `references/dem.tif` and `terrain_source.f32` contain the retained four-metre export; source catalog entries identify the Yellowstone `WY_YellowstoneNP_2020_D20` coverage. Source: [3DEP Elevation ImageServer](https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer).

The [3DEP products policy](https://www.usgs.gov/3d-elevation-program/about-3dep-products-services) makes these products available without use restrictions. The [USGS copyright policy](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits) identifies USGS-authored or produced data as U.S. public domain. Project changes include reprojection/resampling, a local vertical offset, road grading and explicitly approximate water-bed/support cuts. The original source raster remains separate from the authored terrain.

### Orthoimagery — USDA / USGS

Credit: **USDA NAIP 2022, distributed by USGS The National Map; public domain. Reprojected and resampled for this project.** Service credit: **USGS, USDA, The National Map: Orthoimagery.**

The selected Wyoming imagery was acquired **19 July 2022** by USDA-FSA-APFO at native 0.6-metre resolution. The [USGS NAIP Plus service](https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer) describes its public-domain orthoimagery; the actual resolved tile records are retained in `references/imagery_source_catalog.json`. Included exports are `references/orthophoto.jpg` and `midway_orthophoto_detail.jpg`. Derivatives include `assets/textures/midway_macro.jpg`, `thermal_reference.jpg`, habitat support rasters and the geographic reference maps. Cropping, export resolution, reprojection, JPEG encoding and map annotations are project changes. The service publication date is separate from the photograph's acquisition date.

### Vector geography — National Park Service

Credit: **National Park Service, Yellowstone National Park, Spatial Analysis Center**. The broad land-cover source additionally credits **USGS collection and EPA conversion**. The retained park-specific datasets are:

| Included extract | NPS source layer |
|---|---|
| `yell_roads_utm12.json` | [Yellowstone roads](https://services1.arcgis.com/fBc8EJBxQRMcHlei/ArcGIS/rest/services/YELL_ROADS/FeatureServer/0) |
| `yell_trails_utm12.json` | [Yellowstone trails](https://services1.arcgis.com/fBc8EJBxQRMcHlei/ArcGIS/rest/services/YELL_TRAILS/FeatureServer/0) |
| `yell_hydro_rivers_utm12.json` | [Yellowstone rivers](https://services1.arcgis.com/fBc8EJBxQRMcHlei/ArcGIS/rest/services/YELL_HYDRO_RIVERS/FeatureServer/0) |
| `yell_hydro_lakes_utm12.json` | [Yellowstone lakes](https://services1.arcgis.com/fBc8EJBxQRMcHlei/ArcGIS/rest/services/YELL_HYDRO_LAKES/FeatureServer/0) |
| `yell_points_of_interest_utm12.json` | [Yellowstone points of interest](https://services1.arcgis.com/fBc8EJBxQRMcHlei/ArcGIS/rest/services/YELL_POINTS_OF_INTEREST/FeatureServer/0) |
| `yell_trailheads_public_view_utm12.json` | [Public trailheads view](https://services1.arcgis.com/fBc8EJBxQRMcHlei/ArcGIS/rest/services/YELL_TRAILHEADS_public_view/FeatureServer/0) |
| `yell_veg_land_cover_utm12.json` | [Yellowstone land cover](https://services1.arcgis.com/fBc8EJBxQRMcHlei/ArcGIS/rest/services/YELL_VEG_LAND_COVER/FeatureServer/0) |
| `yell_soils_utm12.json` | [Yellowstone soil types, layer 4](https://services1.arcgis.com/fBc8EJBxQRMcHlei/ArcGIS/rest/services/YELL_Soil_Types/FeatureServer/4) |

The associated ArcGIS items are publicly distributed by `yell_gis`, credit Yellowstone/NPS and carry the NPS public-data disclaimer. Where present, feature attributes specify unrestricted access and public map display. Their treatment as U.S. government source data follows the [NPS ownership policy](https://www.nps.gov/aboutus/disclaimer.htm); the [standard GIS disclaimer](https://www.nps.gov/subjects/gisandmapping/data-disclaimers.htm) preserves the source accuracy and warranty limitations. NPS also explicitly identifies its [maps as public domain](https://www.nps.gov/subjects/gisandmapping/data-sources-and-accuracy.htm). This is a source-specific assessment, not a blanket claim about everything hosted by a federal agency.

Some road attributes identify Bing imagery as a historical tracing reference. This project includes the released NPS vector coordinates and their metadata; it includes no Bing imagery. Preliminary national NPS route extracts and service metadata, where retained in `references/`, have the same NPS source credit.

The game clips/reprojects the vectors, densifies centre lines, joins route elevations and water profiles, assigns approximate widths, and adds a representative hand-traced Excelsior outflow. These are project-authored adaptations. They are not revised NPS surveys. Full accuracy, modification and source-date details are in [docs/geography-research.md](docs/geography-research.md).

## Researched candidates — not included

Entries marked `included: false` in the asset manifest are research leads, not supplied assets or cleared runtime dependencies. They include additional Poly Haven vegetation/rocks/HDRI, ambientCG Ground037, the listed Sketchfab bison, trout, frog, bird, lupine and willow models, and Quaternius Ultimate Animated Animals. Other discussed Maxtree, Graswald and insect-pack options are also not included. Their availability, exact archive licenses and suitability must be checked when acquired; a creator preview is not a downloaded asset.

Candidate links and qualifications are maintained in [docs/asset-research.md](docs/asset-research.md), rather than duplicated here. No noncommercial-only candidate model is bundled in the present project. Original proxy animals and plants remain project-authored stand-ins.
