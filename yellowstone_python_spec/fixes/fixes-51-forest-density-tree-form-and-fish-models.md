# fixes-51: forest density, lodgepole form, groundcover and fish models

Scope: why the land around the Grand Prismatic overlook looks barren next to the real view, why the trees do not read as lodgepole pine, and whether the fish models are usable. Triggered by KJR's comparison of two July 2023 photos from the overlook with in-game captures from the same area, 2026-10-13. Targets `yellowstone_python/canopy_census.py`, `gen_flora.py`, `yellowstone_midway/data/placements.json`, `placement_overrides.json`, `tools/bake_world.gd`, `assets/imported/pine_tree_01/`, `assets/imported/fauna/trout/`. Audit 2026-10-13 at the request of KJR.
Method: placement counts with `jq` inside the census zone `overlook_knoll_r120` (center x -252, z 159, radius 120 m, 4.52 ha; `canopy_census.py:386`); census densities from `yellowstone_python/derived/census.json`; `canopy_census.detect` and `detect_v2` read in full; tree and fish asset metadata from their glTF JSON; one frame of `~/Downloads/fish_swim_preview.mp4` viewed.

## Measured state

| quantity | value |
|---|---|
| pines placed in the overlook knoll zone (base kept plus overrides added) | 60 + 19 = 79, about 17 per ha |
| census crowns in the same zone | 1,175, about 260 per ha |
| census crowns, outwash ring 200 to 400 m from the spring | 143 per ha |
| pines in `placements.json` over the 4,096 m world | 30,862 (about 18 per ha), with 2,663 removed and 10,271 added by overrides |
| census coverage | the 1,280 m NAIP detail window only (`canopy_census.py:17`) |
| lodgepole sapling density 10 years after the 1988 fires | 0 to more than 500,000 per ha, more than 60 percent of burned area below 5,000 per ha (Kashian et al. 2004) |
| mean density in 25-year post-fire stands | 21,738 stems per ha, range 0 to 344,067 (Turner, summary handout) |

Mature-stand densities by age class are in Kashian et al. (2005) tables and were not retrieved here. Whatever the mature figure, the placed density is about a fifteenth of what the census detected, and the census detects only crowns visible from above.

## Items

### 1. Placement density is a fraction of the census
The game places about 17 pines per ha where the census found about 260 per ha. The census is not the placement authority (`census.json` status: "not a placement authority"), and the placement layers (`placements.json`, overrides from `gen_flora`, reviewed proposals) were built with their own density rules; fixes-42 also removed 19,500 pines that stood on mineral ground.
### Fix
Make placement density a function of a measured canopy field: per 10 m cell, target stem count from the canopy layer (item 2), with stems placed by a seeded Poisson-disk process at the spacing implied by the target density and the species' crown radius. `gen_flora` reads that field instead of its own density constants; the thermal and mineral exclusion from fixes-42 item 3 stays. Record per-zone placed density against census density in the build.
### Test
Per census zone, placed stems per ha equal the target within 10 percent; no stems on mineral or thermal-exclusion cells.
### Cost
Medium.

### 2. The census undercounts dense forest by construction of the method
`detect` finds local maxima of excess green (ExG) inside a mask of green and dark pixels (`exg > 0.05`, brightness `< 0.55`) on 0.625 m NAIP, and suppresses any peak within 2 m of a stronger one (`canopy_census.py:45-97`). `detect_v2` adds stems to large blobs at the area of a median isolated crown (`:440-488`). In a closed lodgepole stand:
- crowns touch, so many trees share one ExG peak inside the 2 m suppression radius;
- shaded crown sides fall outside the darkness and greenness gates;
- the area top-up divides blob area by the median isolated crown, and open-grown isolated trees have wider crowns than trees in dense stands, so the implied stem count is low;
- subcanopy and understory trees are invisible from above.
So each detection is closer to a crown cluster than a tree, which matches what the screenshots suggest.
### Fix
Use canopy cover and canopy height as the observed quantities, and derive stem density from them:
- Canopy cover fraction per 10 m cell from NAIP (the crown mask already computed) and, where available, from a canopy height model.
- Canopy height model from the USGS 3DEP lidar point cloud (first returns minus the bare-earth surface already used for `dem_1m_core.tif`); coverage of the 3DEP point cloud over Midway is not verified and is the first thing to check. With a canopy height model, individual-tree detection uses a height-dependent local-maximum window, which separates touching crowns far better than ExG on an orthophoto.
- Stem density from cover through a lodgepole crown-radius and height allometry from the literature, labeled `transferred`, with the subcanopy fraction authored until plot data (FIA plots or park inventory) are found.
- Extend `census_validate` with hand-counted blind crops in dense stands and report detection recall by density class.
### Test
Recall against hand counts in at least three dense crops; canopy cover from placed crowns matches the observed cover per zone within 10 percent.
### Cost
Medium to refactor (lidar acquisition is the unknown).

### 3. The tree model is not a lodgepole pine
All pines use Poly Haven "Pine Tree 01" variant b with three LODs and billboards (`tools/bake_world.gd:632-646`). That model is an open-grown pine with a broad, irregular crown and heavy low limbs. Lodgepole pine (Pinus contorta var. latifolia) in Yellowstone stands has a straight, slender, self-pruned bole, a narrow crown confined to the upper part of the stem in dense stands, and short branches; the overlook photos show exactly this: tall narrow spires with bare lower trunks.
### Fix
Generate lodgepole meshes in Python from stand-dependent allometry, which also demonstrates the project's aim: inputs height, diameter, crown ratio and crown radius per tree, with crown ratio falling as stand density rises; outputs a trunk, whorled branch skeleton and needle cards per LOD, plus impostor cards. Parameters from published lodgepole allometry, registered in `param_registry` with status `literature` or `transferred`. A handful of archetypes (open-grown, edge, dense-stand, sapling, snag) covers the stands. Alternatively source a licensed lodgepole model; record license and provenance in `asset_manifest.json` either way.
### Test
Rendered silhouette metrics per archetype (crown width to height ratio, clear-bole fraction) fall within the literature ranges; a side-by-side capture from the overlook against the 2023 photo, reviewed by KJR.
### Cost
Medium.

### 4. Groundcover and dead wood are missing
The real view between the overlook and the spring shows a forest floor of downed logs, standing dead trees (thermally killed lodgepole near the pools) and patchy grass, and the hill (Midway Bluff) is forested on top above a bare scarp. The game shows smooth green-tan terrain with scattered trees.
### Fix
Add `snag` and `log` placement kinds driven by thermal ground (`ground_heat.json`, fixes-41 item 6) and stand density (self-thinning mortality); a lodgepole understory layer (grouse whortleberry, elk sedge, pinegrass, kinnikinnick as cards) where canopy cover is moderate; bare scarp only where slope or the habitat mask says so. Sources for understory composition go in `param_registry`.
### Test
Snags appear within the thermal ground band and not elsewhere; understory density follows canopy cover; overlook capture review by KJR.
### Cost
Medium.

### 5. Rendering many more trees
Matching even the census density means about 260 stems per ha in forest, several hundred thousand over the world. The bake already uses MultiMesh with LOD meshes and billboards.
### Fix
Measure frame time at 1x, 3x and 10x the current density with the existing LOD ranges (65 m, 210 m, 800 m); beyond the instanced range draw forest as impostor cards per cell or a canopy-height-driven terrain layer. Set the density ceiling from the measurement, not by guess.
### Test
Frame time at the overlook with the new density stays under the project target on the reference machine.
### Cost
Medium.

### 6. Fish models
- In game: `assets/imported/fauna/trout/trout.glb` has 562 vertices, no skin and a 115-byte texture (a flat color); brown trout are the same mesh tinted. It does not read as a trout up close.
- Candidate: `~/Downloads/cutthroat-fish_swim_animated.glb`. One frame of its preview shows a convincing salmonid: correct fin set and placement, adipose fin, spotting, a natural head and eye, and a believable dorsal outline. The cutthroat throat slash is not visible from the side view, and the spot pattern sits between cutthroat and rainbow. Usable as the base body for brown and rainbow trout with species textures (fixes-44 item 14), after decimation and texture downsizing (59 MB as delivered).
### Fix
See fixes-44 item 14; species textures from reference photographs of Firehole brown and rainbow trout, with the source of each recorded.
### Test
Side-by-side render of each species texture against a reference photo, reviewed by KJR.
### Cost
Medium.

## Sources
- Kashian, D. M., Tinker, D. B., Turner, M. G., and Scarpace, F. L. (2004). Spatial heterogeneity of lodgepole pine sapling densities following the 1988 fires in Yellowstone National Park. Canadian Journal of Forest Research. https://s.wayne.edu/kashianforest/files/2020/01/Kashian_et_al_2004_CJFR.pdf
- Kashian, D. M., Turner, M. G., Romme, W. H., and Lorimer, C. G. (2005). Variability and convergence in stand structural development on a fire-dominated subalpine landscape. Ecology 86(3), 643-654. https://s.wayne.edu/kashianforest/files/2020/01/Kashian_et_al_2005_Ecology.pdf
- Turner, M. G. 1988 fires summary handout (2015). https://www.nrfirescience.org/sites/default/files/documents/Turner_1988FiresHandout_21Sep2015.pdf

## Order
Item 2 (what the density should be) before item 1 (placing it); item 3 alongside; item 5 measured before densities rise; items 4 and 6 after.
