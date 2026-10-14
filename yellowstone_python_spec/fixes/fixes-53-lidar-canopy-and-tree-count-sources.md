# fixes-53: lidar canopy and tree count sources

Scope: the data sources for a tree count that holds up in dense lodgepole, following fixes-51 item 2, which left 3DEP point cloud coverage over Midway unverified. Targets `yellowstone_python/census/canopy_census.py`, `census_validate.py`, `registry/param_registry.py`, `yellowstone_midway/references/dem_1m_core.tif.provenance.json`. Audit 2026-10-13 at the request of KJR.
Method: USGS The National Map products API queried for Lidar Point Cloud and 1 m DEM products over E 512,312 to 513,592, N 4,929,559 to 4,930,839 (EPSG:32612, the census detail window); USGS project report and the block 3 LazQC report read; the 375-byte LAS header of tile `12TWQ125300` read by HTTP range request; world origin from `yellowstone_midway/README.md`; literature located by web search.

## Measured state

| quantity | value |
|---|---|
| point cloud project over Midway | USGS 3DEP `WY_YellowstoneNP_2020_D20`, block `WY_YellowstoneNP_3_2020`, work unit 218558 |
| quality level of that block | QL1 (USGS project report) |
| acquisition of that block | 2020-09-29 to 2020-10-09 (LazQC GPS time range) |
| sensor | Leica TerrainMapper, linear-mode, oscillating mirror |
| tile `12TWQ125300` (E 512,500 to 513,000, N 4,930,000 to 4,930,500) | 8,268,421 points, LAS 1.4, point format 6; about 33 points per m2 all returns, about 29 first returns per m2, overlap points included |
| tiles over the census detail window | 16 tiles of 500 m, columns 120 to 135, rows 295 to 310; about 1.1 GB LAZ |
| tiles over census zone `overlook_knoll_r120` (E 512,580 to 512,820, N 4,929,920 to 4,930,160) | `12TWQ125295`, `12TWQ125300` |
| classes delivered | 1 unclassified, 2 ground, 7 low noise, 9 water, 17 bridge deck, 18 high noise, 20 ignored ground, 21 snow; no vegetation classes |
| bare earth already in the project | `dem_1m_core.tif` is the 1 m DEM from the same project (tile `x51y494`, provenance file) |
| post-fire lodgepole density, 11 years after 1988 | 0 to 535,000 saplings per ha across 90 stands (Turner et al. 2004) |
| post-fire lodgepole density, 24 years after 1988 | mean 21,738 stems per ha, range 0 to 344,067 (Turner handout; Turner et al. 2016 data) |

Point density is from one tile. QL1 specifies at least 8 points per m2 aggregate nominal density; the block report with the achieved figure (`WY_Yellowstone_Lidar_Mapping_Report_218558.pdf`) timed out on rockyweb and was not read. The LAZ tiles are served from rockyweb only; the metadata and reports are mirrored at `prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/`.

Trail descriptions report that the Fairy Falls trail and the overlook hillside burned in 1988. That is not confirmed against the NPS fire perimeter layer.

## Items

### 1. Canopy height model from the 3DEP point cloud
Coverage is confirmed, so the ExG-on-NAIP detector is no longer the only observation available. Vegetation is not classified, so the canopy surface comes from first returns in classes 1 and 2 with noise (7, 18) and withheld points dropped. The ground surface is the project's own bare-earth model, already matched to `dem_1m_core.tif`.
### Fix
Add a fetch tool for the 16 detail-window tiles with checksums and a provenance record per tile. Build a 0.5 m canopy height model: highest first return per cell minus `dem_1m_core.tif` resampled to 0.5 m, pit-filled. Record the source, tile list, acquisition window and point density in the provenance file. The canopy height model is observed data with status `measured`. Python options are `laspy` with `lazrs`, or PDAL; neither is installed on the operator machine.
### Test
Canopy height over the Grand Prismatic mineral apron and the Firehole channel is below 0.5 m in at least 99 percent of cells. Canopy height at 20 hand-picked NAIP crowns is above 2 m.
### Cost
Small to medium; the 1.1 GB download is the slow step.

### 2. Individual-tree detection on the canopy height model
The detector looks for local maxima with a search window that grows with height, then splits the canopy into crowns by marker-controlled watershed. This separates touching crowns that share one ExG peak (fixes-51 item 2).
### Fix
`detect_lidar` in `canopy_census.py`: smooth the canopy height model with a 3 x 3 Gaussian, find local maxima above 2 m with window radius from a lodgepole crown-radius-to-height relation (status `transferred`, source registered in `param_registry`), and split crowns by watershed. Emit the same stable record schema as `detect_v2` with height and crown area per tree, plus `method: lidar_lmf`.
### Test
Recall and precision against hand counts in blind crops. The crops are stratified by density class (under 600, 600 to 2,200, over 2,200 stems per ha), and recall is reported per class. Counts in the overlook knoll zone are reported against the 1,175 ExG crowns.
### Cost
Medium.

### 3. Detection from above fails in dense young stands
Published tests of local-maximum detection report about 26 percent of stems missed above 600 trees per ha, and no workable setting above about 2,200 stems per ha. Those figures come from abstracts, not from full text. Post-1988 lodgepole at 24 years averages tens of thousands of stems per ha. The lidar count is therefore a count of canopy-dominant trees. The subcanopy stems in doghair patches have to come from field density data.
### Fix
Treat lidar trees as the dominant layer. Per 10 m cell, set total stem density from canopy cover and mean canopy height through a density relation fitted to the Turner et al. 2016 permanent-plot data (Dryad doi:10.5061/dryad.1pr7k; 72 plots resampled in 2012). Status is `transferred`, and per-cell uncertainty comes from the plot scatter. Check whether any of the 72 plots fall inside the 4,096 m world, and use them for validation only. Kashian et al. 2004 patch statistics (mean patch about 1.5 ha) set the spatial grain of density patches.
### Test
Fitted relation reproduces the plot densities with stated residuals. Generated stems per cell are never fewer than the lidar trees in that cell.
### Cost
Medium; the Dryad workbooks have not been opened.

### 4. Size and species distribution from TreeMap 2020
TreeMap 2020 (USFS, RDS-2025-0031) assigns each 30 m pixel an FIA plot identifier. Joined to the plot tree table, it gives trees per acre by species and diameter. That supplies the diameter and height spread that item 3 does not.
### Fix
Extract the TreeMap pixels over the world, join to the FIA tree table, and register diameter and height distributions per pixel with status `transferred`, labeled as imputed from plots elsewhere. Use them to draw stem sizes. Do not use them to set counts where lidar or item 3 applies.
### Test
Drawn size distributions match the joined tree table per pixel. No count in the placement layer traces to TreeMap.
### Cost
Small to medium; the national archive is about 4.5 GB, and Earth Engine hosts the same raster.

### 5. Sources not to use for counts
The Meta and WRI 1 m global canopy height map (Tolan et al. 2024) is inferred from Maxar RGB imagery. An Alps validation found it overcounts by 200 to 750 trees per ha and does not place individual trees reliably. The 3DEP lidar is direct measurement of the same quantity.
### Fix
Do not add it. If NAIP stays in use for canopy cover outside lidar coverage, read the 4-band NAIP with near-infrared so NDVI separates crowns from shadow; RGB ExG does not.
### Test
None.
### Cost
None.

### 6. DEM provenance quotes the wrong quality level
`dem_1m_core.tif.provenance.json` cites the "USGS 3DEP QL2 1 m lidar DEM product specification" for its 10 cm vertical accuracy. The Midway blocks are QL1. Both levels specify RMSEz of 10 cm, so the number stands and the label is wrong. The project report gives tested accuracy for the whole project: 7.79 cm non-vegetated (95 percent) and 20.39 cm vegetated (95th percentile).
### Fix
Change the source label to QL1 and add the tested values with the project report as citation.
### Test
`audit_provenance` passes.
### Cost
Small.

## Sources
- USGS (2022). WY_YellowstoneNP_2020_D20 project report. https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/metadata/WY_YellowstoneNP_2020_D20/USGS_WY_YellowstoneNP_2020_D20_Project_Report.pdf
- USGS. WY_YellowstoneNP_3_2020 LazQC point cloud report. https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/reports/USGS_WY_YellowstoneNP_3_2020_FINAL_LPC_Report.txt
- USGS. Point cloud tiles. https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/WY_YellowstoneNP_2020_D20/WY_YellowstoneNP_3_2020/LAZ/
- Turner, M. G., Tinker, D. B., Romme, W. H., Kashian, D. M., and Litton, C. M. (2004). Landscape patterns of sapling density, leaf area, and aboveground net primary production in postfire lodgepole pine forests, Yellowstone National Park. Ecosystems 7, 751-775. https://s.wayne.edu/kashianforest/files/2020/01/Turner_et_al_2004_Ecosystems.pdf
- Turner, M. G., et al. (2016). Twenty-four years after the Yellowstone fires, data. Dryad. https://doi.org/10.5061/dryad.1pr7k
- Kashian, D. M., Tinker, D. B., Turner, M. G., and Scarpace, F. L. (2004). Spatial heterogeneity of lodgepole pine sapling densities following the 1988 fires in Yellowstone National Park. Canadian Journal of Forest Research 34, 2263-2276. https://s.wayne.edu/kashianforest/files/2020/01/Kashian_et_al_2004_CJFR.pdf
- Turner, M. G. 1988 fires summary handout (2015). https://www.nrfirescience.org/sites/default/files/documents/Turner_1988FiresHandout_21Sep2015.pdf
- USDA Forest Service. TreeMap 2020, RDS-2025-0031. https://www.fs.usda.gov/rds/archive/catalog/RDS-2025-0031
- Local-maximum detection by stand density: University of Montana thesis, https://scholarworks.umt.edu/etd/65 ; USFS Black Hills study, https://research.fs.usda.gov/treesearch/48221
- Validation of the Meta 1 m canopy height map in the Alps. https://bia.unibz.it/esploro/outputs/journalArticle/Evaluating-the-reliability-of-the-1-meter/991007384663701241

## Order
Item 1 first; item 2 on its output; item 3 alongside item 2, since it decides what the lidar count means; item 4 after item 3; item 6 any time. This document supplies the observed density that fixes-51 item 1 places.
