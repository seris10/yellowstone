# Human-created assets for Yellowstone Midway

**Research reviewed 7 October 2026.** This document covers third-party art and sound, the files actually included, their conversion, and the work needed to raise the landscape's art quality. Read it with [ecology-research.md](ecology-research.md) and the geographic provenance documentation. The machine-readable record is [asset_manifest.json](../data/asset_manifest.json); download receipts and original Poly Haven metadata are retained under `assets/imported`.

## 1. Decisions and present limits

The strongest immediately usable free sources found were **Poly Haven's photographed materials and human-authored vegetation**, together with **the National Park Service's Yellowstone field recordings**. They offer actual downloadable source files and clear permission to package the resulting project. The included pine and grass are converted from those sources. Their textures and silhouettes come from photographs. The distant pine images are ordinary renders of the included 3D asset.

Source quality and ecological accuracy are separate tests. Poly Haven calls its tree “Pine Tree 01”; it does not identify it as lodgepole pine. Its grass asset likewise has no botanical identification. These provide substantially richer material and shape than geometric stand-ins, but they do not establish a botanically exact reconstruction. A distinctive adult lodgepole, a young regeneration cohort, a thermal-killed snag, and a forest-edge shrub each need deliberate authoring against local references. Changing the label on a generic model would not accomplish that.

**No downloaded rigged wildlife model is represented as a finished, realistic Yellowstone animal in this delivery.** The animal candidates below have useful animation, licensing, or reference value, but still need download inspection, anatomy review, material work, or rigging. This is a concrete production gap, not a claim that suitable free models cannot exist. Keep ecological agents and species IDs independent of their visible model so that better art can replace provisional visuals without rewriting the simulation.

The user's personal, noncommercial scope permits considering noncommercial licenses. It does not require preferring them to better CC0 sources. A zero-dollar product, an asset visible in a web viewer, and a redistributable source file are different things. This research therefore records license and acquisition status independently.

## 2. Files actually included

| Source asset | Creator and permission | Included form | Fidelity notes |
|---|---|---|---|
| NAIP orthophoto and geographic color derivatives | USDA-FSA-APFO, distributed by USGS/The National Map; public domain | `references/orthophoto.jpg`, `midway_macro.jpg`, `thermal_reference.jpg` | Source catalog identifies 19 July 2022, 0.6 m NAIP tiles; exported/cropped derivatives have their own resolution. Credit: USGS, USDA, The National Map: Orthoimagery. [A38] |
| [Pine Bark](https://polyhaven.com/a/pine_bark) | Dimitrios Savva; CC0 | 1K diffuse and OpenGL normal JPEGs in `assets/textures` | Source's physical texture width is 2 m. Do not make every trunk share the same conspicuous scar. [A01] |
| [Forest Ground 04](https://polyhaven.com/a/forest_ground_04) | Rob Tuytel; minor adjustment by Rico Cilliers; CC0 | 1K diffuse and OpenGL normal JPEGs | Source width 3.2 m; rocky, dry ground. It is one substrate component, not a complete Yellowstone forest floor. [A02] |
| [Rock Boulder Dry](https://polyhaven.com/a/rock_boulder_dry) | Dimitrios Savva, photography; Rico Cilliers, processing; CC0 | 1K diffuse JPEG | Weathered rock detail. This is not a surveyed sample of Midway silica sinter. [A03] |
| [Pine Tree 01](https://polyhaven.com/a/pine_tree_01) | Rico Cilliers, modeling; Rob Tuytel, photography; CC0 | Source-derived variant b, three glTF detail levels, original texture maps, isolated needle card, four distant renders | Species unspecified. Source shape and materials retained where practical; fine foliage approximated during optimization. [A04] |
| [Grass Medium 01](https://polyhaven.com/a/grass_medium_01) | Rico Cilliers, modeling; Rob Tuytel, photography; CC0 | Eleven selected glTF clumps sharing a source buffer and 1K maps | Generic grass visual. Do not relabel as elk sedge, pinegrass, or Ross's bentgrass without botanical remodeling. [A05] |
| Geyser Hill water outflow | NPS/Peter Comley; public domain | `nps_geyser_hill_water.mp3`, 63.34 s | Water under a boardwalk with geothermal background; **not a main-channel Firehole river recording**. Recorded 22 March 2015. [A06][A07] |
| Geyser Hill birds | NPS/Peter Comley; public domain | `nps_geyser_hill_birds.mp3`, 216.39 s | Raven, mountain bluebird, Clark's nutcracker and kestrel, with distant geysers. Recorded 22 March 2015. [A06] |
| Lower Geyser Basin strong wind | NPS/Peter Comley; public domain | `nps_lower_basin_wind.mp3`, 299.34 s | Wind through trees, recorded 21 March 2015. Match playback to represented wind strength. [A06] |
| Firehole dipper and geese | NPS & MSU Acoustic Atlas/Jennifer Jerrett; public domain | `nps_firehole_dipper_geese.mp3`, 43.25 s | Actual Firehole location, but a bird-dominated February recording, not an isolated summer water loop. Recorded 26 February 2014. [A08] |

Audio durations, triangle counts, binary sizes and hashes in this document are measurements of the downloaded files. They are not performance claims. All four MP3s were inspected with `ffprobe`; they are 44.1 kHz stereo. The sound library explicitly permits downloading and unrestricted use and asks for NPS credit where appropriate. Keep the named recordists in the project's credits as well. [A07]

## 3. The pine conversion, and why it matters

The original 1K glTF describes three very detailed tree variants. Variant b alone contains **4,234,432 triangles**. Its source buffer is shared with the other variants and is approximately **949 MB**. The original source buffer was downloaded and checked against the supplier's MD5, used offline, and deliberately kept outside the game project. It is unnecessary to ship that buffer to explore the landscape.

`assets/imported/prepare_pine_asset.py` produces compact glTF files. At the highest included level, it preserves 97,482 original woody triangles. It samples the existing source needle geometry into density cells, finds the local orientation from their covariance, and represents those occupied regions with photographed needle cards. This is an **offline conversion of an existing authored asset**, not a terrain generator or a runtime system for inventing forest placement. Lower levels simplify wood and use fewer, larger foliage representations.

| File, under `assets/imported/pine_tree_01` | Wood triangles | Foliage triangles | Total | Mesh buffer, excluding shared textures | Intended use |
|---|---:|---:|---:|---:|---|
| `pine_b_compact.gltf` | 97,482 | 7,180 | 104,662 | 3,379,880 bytes | Select nearby showcase trees, subject to profiling |
| `pine_b_lod1.gltf` | 5,169 | 2,016 | 7,185 | 319,788 bytes | Ordinary nearby and middle-distance trees |
| `pine_b_lod2.gltf` | 854 | 424 | 1,278 | 61,672 bytes | Distant geometry before silhouette cards |
| `pine_billboard_0.png` through `_3.png` | — | — | Quad supplied by renderer | Four 512 × 768 RGBA images | Distant forest only |

All three meshes use a ground-centered origin and the same measured canopy bounds, in meters: X −3.5409 to 3.6828; Y 4.5852 to 14.7945; Z −3.5275 to 4.0695. The original root reaches roughly 8 cm below the ground plane. Foliage bounds are explicitly normalized between levels so a detail switch does not enlarge the tree. Trunk collision should use the authored trunk, not the canopy bounding box. Uniform scale preserves the original proportions; restrained nonuniform variation is an artistic alteration and should be reviewed.

The four distant views have a **10.6667 m wide × 16 m tall** frame with its bottom at Y = −0.3 m. Their camera azimuths are 0°, 90°, 180° and 270°. `billboard_metadata.json` retains these numbers. For a rotated tree, select the view relative to the tree's authored yaw, not just the global camera direction. A later eight- or sixteen-view impostor can reduce transitions. These images contain baked diffuse lighting, so indiscriminately multiplying them by dark lighting a second time makes the forest unnaturally black.

A real visual defect was found during conversion: the source twig atlas contains opaque padding for other UV islands. Taking a rectangle around a twig alone brought that padding into the canopy as gray fragments. The converter now isolates the connected photographed twig, preserves its antialiased edge, and writes `pine_tree_01_twig_card.png`. This is why source inspection and an engine render are required even when a material is labeled PBR. Final LOD1 was rendered and inspected in **Godot 4.5.1 Compatibility**; the alpha fragments were corrected. That asset check does not substitute for profiling an entire forest.

Quadric simplification uses approximate UV and normal transfer at reduced levels. Close silhouettes, branch junctions and bark seams therefore still deserve an artist's pass. The highest level is not the original four-million-triangle foliage. Its filename should not be read as a promise of film-quality close-up needles. `render_pine_billboards.py` preserves the reproducible technical rendering step; Python packages are needed only to rebuild these assets, not to run the game.

## 4. Ground cover and material handling

The grass selections range from 28 to 1,257 triangles: `grass_tiny_b` 28, `grass_tiny_d` 32, `grass_tiny_c` 40, `grass_tiny_f` 60, `grass_tiny_e` 62, `grass_tiny_a` 79, `grass_tall_a` 290, `grass_tall_b` 310, `grass_small_b` 653, `grass_small_a` 833, and `grass_mid_b` 1,257. Names describe source variants, not species. Their source transforms were removed so each clump can be placed from its own base rather than from an asset-pack display layout. The source RGB and alpha were packed together without inventing photographic content.

Use separate ground materials for mineral substrate, dry litter, exposed gravel, damp bank, living cover and siliceous deposit. Wetness should alter roughness and darkening locally and continuously. It should not make dry lodgepole forest glossy merely because a hot spring is nearby. Photograph-derived rock detail can contribute small-scale variation, while the larger thermal apron's shape, flow ridges and mat masks remain specifically authored from geographic references.

For repeated terrain material, establish meter-based UV density before judging sharpness. Blend long-range geographic color, medium-scale substrate patches and close detail at distinct scales. Preserve one world-space coordinate convention across chunk borders so a material does not restart its phase on each tile. Repeated obvious stones in a scan need additional material variants or carefully authored breakup; arbitrary per-tile hue changes tend to advertise the seam instead.

Godot's standard material expects OpenGL-style normal maps. Its alpha-scissor mode avoids ordinary transparency sorting and supports cutout shadows; alpha-to-coverage can help foliage edges with MSAA. Use sRGB sampling for color and linear interpretation for data maps, and verify the AO/roughness/metallic channel convention instead of assuming every supplier packs channels alike. The included `.gltf` uses a cutout alpha mode rather than default blended transparency. [A09]

Do not turn every grass blade into a physics object. Keep a few low-cost collision shapes for substantial trunks, logs, railings and terrain. Wind should hold grass roots and tree trunks still while moving upper leaves and branches. A global gust field gives adjacent plants coherent timing; per-instance phase and stiffness prevent perfect synchronization. This is a rendering contract for later vegetation shaders, not a claim that detailed branch mechanics are already implemented.

## 5. Highest-value additional environment assets

These are **researched candidates, not included files**. Follow the creator page when acquiring them; save the exact archive and license record with its date.

| Candidate | Source facts | Recommended use and required work |
|---|---|---|
| [Pine Sapling Small](https://polyhaven.com/a/pine_sapling_small) | Rico Cilliers/Rob Tuytel; CC0; page lists about 398K triangles. [A10] | Regeneration reference. Establish species fit, reduce geometry and create several age/shape variants before using repeatedly. |
| [Pine Roots](https://polyhaven.com/a/pine_roots) | Rob Tuytel; CC0; about 163K triangles, 1.9 m wide. [A11] | Select exposed roots along a verified eroded trail edge. Retopologize; bury portions and blend root contact into soil. |
| [Dead Tree Trunk](https://polyhaven.com/a/dead_tree_trunk) | Rob Tuytel; CC0; about 102K triangles, 3.1 m wide. [A12] | Grounded fallen logs, shelter and decomposition patches. Review decay, moss and bark against the chosen habitat. |
| [Dry Branches Medium 01](https://polyhaven.com/a/dry_branches_medium_01) | Rico Cilliers; CC0; photographed branch set, about 17K triangles. [A13] | Sparse near-path litter and log details. Avoid an evenly distributed decoration layer. |
| [Rock Moss Set 02](https://polyhaven.com/a/rock_moss_set_02) | Kless Gyzen; CC0; about 58K triangles for the listed set. [A14] | Damp, shaded pockets only; create dry counterparts. Moss-covered boulders are a poor universal thermal-basin material. |
| [Ground037](https://ambientcg.com/view?id=Ground037) | ambientCG; CC0; surface photogrammetry, damp forest/moss ground, 2.1 m square. [A15][A16] | Optional moist substrate accent. Do not spread it over dry sinter or exposed road shoulders. |
| [Rocky Trail](https://polyhaven.com/a/rocky_trail) | Amal Kumar; CC0; 2 m texture width. Creator describes the photography/scanning process. [A17][A18] | Close gravel texture for an appropriately authored path surface; does not define path alignment or width. |
| [Noon Grass HDRI](https://polyhaven.com/a/noon_grass) | Greg Zaal; CC0; clear-day HDR environment. [A19] | Lighting reference or a sky treatment with its foreign ground horizon excluded. Keep the Yellowstone horizon from the actual terrain. |

Poly Haven's Pine Forest collection is a productive acquisition pool, but collection membership does not prove that every fern, fir, moss or leaf scan belongs in this particular basin. Similarly, ambientCG explicitly distinguishes photogrammetry from multilight captures and procedurally authored materials. Select the creation method per asset instead of calling an entire mixed library “photoscanned.” [A20][A21]

**Flower and shrub leads:** rufusrockwell's [Lupine Plant](https://sketchfab.com/3d-models/lupine-plant-bf30f1110c174d4baedda0ed63778439) is a 2017 human-authored low-poly model, about 2.1K triangles, with a Creative Commons Attribution label. It is a promising small flower acquisition lead, but the archive and exact species were not inspected. The TreeIt creator evolveduk also lists a [9.1K-triangle Willow](https://sketchfab.com/3d-models/willow-422de2372f3d46dfb314a0cd5da512fe) under Attribution; this is a tree, not proof of an appropriate Yellowstone shrub-willow species. Both remain optional. A deliberate original willow or lupine stand-in should be identified as provisional until its diagnostic features and habitat are reviewed. PlantCatalog's yellow bush lupine identifies *Lupinus arboreus* and warm-temperate/Mediterranean habitats; a shared common-name word does not make it a suitable local replacement. [A39][A40][A41]

**TreeIt** is a useful free authoring-tool candidate for producing editable conifer meshes, with branch controls, exports and LOD support. Its creator permits use of generated trees in one's projects, including commercial projects. It can support a deliberately edited, fixed lodgepole asset library; it should not become a runtime forest generator. Inspect supplied example-tree terms separately from the software page, bake any wind metadata into a documented Godot convention, and prefer an export format that carries the required data. [A22]

## 6. Fauna: usable leads and the remaining quality gap

For the following Sketchfab candidates, indexed **creator pages** exposed the descriptions and license labels during research. Direct model-page retrieval was blocked, and no archive was downloaded. Therefore the exact license version, downloadable archive contents, texture provenance, bone weights and animation quality remain unverified. Their manifest status is intentionally conditional. Do not silently promote a preview into a cleared, integrated asset.

| Candidate | What the primary listing supports | Assessment for this project |
|---|---|---|
| [American Bison — Damco](https://sketchfab.com/3d-models/american-bison-88fbc7cb875444669bd45ac3597bc579) | 858 triangles, animated, baked texture; Creative Commons Attribution label. [A23] | Useful behavior or distant prototype. Too simple to claim a finished close-range realistic bison. Needs anatomy, fur, eye and hoof review. |
| [Animated Free Bison — Anees Animates](https://sketchfab.com/3d-models/animated-free-bison-be2dcd97db1c4b9c91a7728d9bc89925) | Animated downloadable listing; author advertises PBR materials; Attribution label. [A24] | A higher-priority inspection lead, not a verified quality upgrade. Check original human creation, actual textures and rig before adopting. |
| [Rainbow trout — Natural History Museum of Los Angeles County](https://sketchfab.com/3d-models/low-poly-rainbow-trout-oncorhynchus-mykiss-e2c052bd12fd492d9abf0a1c05cff175) | Identified *Oncorhynchus mykiss*, low-poly reconstruction; Attribution–NonCommercial–ShareAlike label. [A25] | Personal-use candidate compatible in principle with this brief. Keep its NC/SA obligations on any derivative. Museum provenance is useful, but the reconstruction still needs present-day living appearance review. |
| [Trout Fish Animated — SbaStuff](https://sketchfab.com/3d-models/trout-fish-animated-4fa0cb7afc004d65bd49f406bffd5b2b) | Creator describes modeling, projected photographic texture and bone animation; about 3.2K triangles; Attribution label. [A26] | Reasonable animation prototype. Track the source photograph's permission chain and validate fish anatomy, fin transparency and swimming speed. |
| [Frog — SpaceScapes](https://sketchfab.com/3d-models/frog-b386e33f44b344bab07a17b0c02f9f1b) | Creator's low-poly painted frog with idle/jump animation; Attribution label. [A27] | Generic prototype only. Native frog identity, skin, posture and size require remodeling; no implication that a frog belongs in hot water. |
| [Sparrow Raven, 9 animations — Prizrakh](https://sketchfab.com/3d-models/sparrow-raven-9-animations-27587d3c71ad46518cad2cdf245aa35e) | Nine-animation bird listing; Attribution label. [A28] | Inspectable rig lead. The ambiguous name cannot establish either a sparrow or a raven; verify silhouette, bill, tail and motion. |
| [Ultimate Animated Animals — Quaternius](https://quaternius.com/packs/ultimateanimatedanimals.html) | Twelve animal models, more than twelve animations per animal; glTF/FBX/OBJ/Blend; CC0. [A29] | Clean-license, human-created behavior scaffolding with direct creator provenance. Its stylized art direction does not meet the requested realistic animal finish. |

A high-quality native gartersnake, dipper, small terrestrial mammal, thermal shore fly and local amphibian were not cleared as downloadable, realistic, animation-ready assets in this review. Allocate explicit authoring time for them. A generic cobra, tropical tree frog, fossil bison, or robotic dragonfly is a visual and ecological mismatch even when its file costs nothing. Search by scientific name and diagnostic anatomy, not just “free animal.”

A small number of convincing animals will contribute more than an unreviewed zoo. Give a bison natural body mass, a grazing muzzle that meets the ground, independent ears, weight-bearing hooves and a smooth walk-to-graze transition. Give a dipper appropriate perches and a plausible route to shallow water. Let fish remain mostly difficult to see under reflection. Tiny insects often need only a few correctly moving near-field meshes, tied to food and emergence conditions; they do not require millions of animated bodies.

### Sources evaluated but not adopted

- **Maxtree Plant Models Vol. 60** is a real zero-price pack with a creator storefront and multiple formats, but the page explicitly says its high-detail models are not intended for games. Its fifteen listed species also include many horticultural or geographically unsuitable choices. The linked license PDF returned an access error during this review. It is not treated as a cleared, raw-redistributable Yellowstone pack. [A30]
- **Graswald/GScatter** has a historical reputation for photographed vegetation, but the previously advertised GScatter page returned 404. The accessible creator EULA describes proprietary individual/studio licenses; it did not establish a current, downloadable free personal-use asset entitlement. Inspect the current product and exact download agreement before planning production around an old “free” article. [A31]
- **Zacxophone's Animated Insect Pack** is a human-authored, rigged commercial pack, but the actual creator storefront lists a price rather than a free download. It is excluded by the budget constraint. Third-party “free download” mirrors are not permission. [A32]

## 7. Import, authoring and integration contract

Prefer a clean **glTF 2.0** handoff, with source `.blend` files retained outside runtime content when available. Godot's documentation recommends glTF; direct `.blend` import depends on a local Blender installation, and OBJ lacks the animation and full material information needed here. Godot 4.3 and later support FBX import through ufbx, but a successful import still needs material and animation inspection. Bake procedural materials and exportable deformation before handoff. [A33]

For each vegetation asset, record species confidence, life stage, dimensions, pivot, soil-contact region, material slots, wind weights, collision proxy, bounds at every detail level and the atlas's physical scale. For fauna add forward axis, skeleton mapping, animation names, root-motion policy, support-foot events, mouth/feeding point, audible-event points and body dimensions. A fish should not acquire a new length when the model is swapped; a bird's animation should not determine its simulated identity.

Imported mesh LOD and authored visibility ranges solve related but different problems. Godot can derive mesh simplifications on import. Its MultiMesh LOD selection uses a group's bounding box, with a shared selected level, so a single forest-sized MultiMesh gives poor control. Use spatially bounded groups and explicit hand-reviewed high/medium/low/impostor representations where canopy silhouette matters. Automatic simplification may damage fine foliage or skinning, so compare the actual switch in motion. [A34][A35]

Suggested initial allocation, **to be profiled rather than promised**: reserve the heavy tree for a few conspicuous foreground placements; use LOD1 in the nearby stand, LOD2 farther out, and impostors for the distant wall of forest. Start grass with small local groups, shorten its shadow distance, and reduce translucent layers before adding more triangles. Review frame time while looking through a dense stand, across water and steam, and along the road at once. Those overlapping systems often cost more than an isolated attractive model.

Every substantial object needs a relationship to its surroundings. Root bases should intersect soil naturally without covering a boardwalk. Fallen logs should have stable support and a corresponding depression, litter edge or vegetation response. River stones need an authored wet line; reeds need an actual appropriate root zone. At chunk borders, keep placements in global coordinates with a unique owner. A log or reed bed can cross a tile without being duplicated. Rebuilding a tile must not erase a hand-edited object adjustment.

Sound should obey the same habitat state. Keep the long stereo field recordings as low-level environmental beds or localized zones. Use separately licensed short calls for visible individual emitters. The included binaural recordings already contain spatial cues; repeatedly applying another aggressive headphone spatialization can give misleading direction. Avoid using one chorus simultaneously as background and as several nearby animals. Keep season, hour, weather and species in the audio metadata, and allow stretches of quiet between events.

## 8. Licensing and acquisition record

Poly Haven states that its assets are original staff work or material donated or sold directly by artists, and releases those assets under CC0. It distinguishes downloadable assets from website text, logos and preview material. ambientCG also releases its downloadable assets under CC0 and permits redistribution of raw files. The manifest credits artists even where attribution is optional. [A36][A16]

For every new download, retain creator name, original URL, asset ID, exact license URL/version, acquisition date, source checksum, any source-photo dependency, and the modifications performed. Mark `included: true` only after the file exists in the project. Keep source archives outside runtime content when they contain enormous high-resolution intermediates, unrelated assets or prohibited redistributable components. Keep a rebuild script or written conversion recipe alongside each optimized derivative.

For a noncommercial or share-alike asset, preserve the exact terms with the derivative and keep its files separately identifiable. Do not label the entire art library CC0 because most of it is. “Royalty-free” describes a licensing arrangement and does not mean free of charge or permission to republish a source archive. Avoid no-derivatives assets when the planned pipeline requires retopology, texture edits or rigging unless the rights holder supplies an appropriate separate permission.

The game does not need an online asset-service dependency. The actual files are included locally. Poly Haven's API terms are separate from the CC0 assets; if a future editor directly presents live API results, recheck its then-current identification and credit requirements. [A37]

## 9. Next art passes and implementation prompts

**First pass: native forest identity.** Replace the one generic source phenotype with deliberately authored lodgepole variants: closed-stand adults with bare lower trunks, exposed edge trees, small regeneration, leaning or broken individuals, snags and fallen wood. Preserve measured site placements and a documented reference date. Verify where moist-forest trees actually belong before adding spruce or fir. The highest return is meaningful stand structure and correct silhouettes, followed by needle detail.

> Implement a hand-editable lodgepole asset family for the existing fixed world. Read the ecology evidence classes and preserve every authored placement ID. Use licensed human-created references, record scientific-name confidence, and deliver six reviewed forms with identical scale and origin conventions across LODs. Include ground-contact meshes, branch stiffness weights, and source/derivative hashes. Render the same three trees at 5, 30, 100 and 300 meters and check silhouette, alpha, bark scale and switching continuity.

**Second pass: a few native understory patches.** Prioritize a verified wet meadow, a dry forest floor and a slightly warm mineral margin. Build species-specific leaves, flowers and stems for their relevant seasonal state. Yellowstone sulphur flower and the unusual seasonal appearance of Ross's bentgrass need more care than adding a colorful generic flower pack; their evidence and timing are covered in the ecology document.

> Author a small native plant library for three existing habitat polygons. Select taxa using the project's source confidence, substrate and season constraints. Produce botanically reviewed clumps with roots at Y=0, ordinary and senescent states, clean alpha atlases, and three detail levels. Hand-place a showcase patch, including bare soil, litter, age variation and plausible clonal clustering. Do not regenerate road, river or thermal boundaries.

**Third pass: ecological animation.** Acquire and inspect a bison model, a small river bird and a trout before expanding the visible animal list. Reuse the existing agent IDs and state. Make foraging and resting observable through body motion, local food depletion and a few well-timed sounds; avoid continuous busy activity.

> Replace the provisional visuals for one grazer, one dipper and one fish with cleared human-made models. Validate dimensions, forward axis, root motion, terrain contact and water depth. Map the existing ecological states to idle, move, feed and rest clips; preserve population and food budgets during model LOD or scene streaming. Add diagnostic overlays for support points and target habitat. Document unresolved anatomy or animation quality rather than disguising it with distance.

**Fourth pass: close-range environmental joins.** Review every boardwalk entrance, bridge end, path/road intersection, spring overflow and conspicuous river bend at walking speed. Place roots, stones, litter and bank plants to support those joins. This pass can make a modest asset library feel substantially more convincing, because it resolves the places where the player understands scale and gravity most clearly.

## Sources

All links below were reviewed or retrieved through the original creator/publisher listing on the review date. Conditional Sketchfab status is described in section 6.

- [A01] Poly Haven, [Pine Bark](https://polyhaven.com/a/pine_bark).
- [A02] Poly Haven, [Forest Ground 04](https://polyhaven.com/a/forest_ground_04).
- [A03] Poly Haven, [Rock Boulder Dry](https://polyhaven.com/a/rock_boulder_dry).
- [A04] Poly Haven, [Pine Tree 01](https://polyhaven.com/a/pine_tree_01), [file metadata](https://api.polyhaven.com/files/pine_tree_01).
- [A05] Poly Haven, [Grass Medium 01](https://polyhaven.com/a/grass_medium_01), [file metadata](https://api.polyhaven.com/files/grass_medium_01).
- [A06] NPS, [Yellowstone Soundscapes](https://www.nps.gov/yell/learn/photosmultimedia/sounds-soundscapes.htm).
- [A07] NPS, [Yellowstone Sound Library and reuse statement](https://www.nps.gov/yell/learn/photosmultimedia/soundlibrary.htm).
- [A08] NPS, [American Dipper and Canada Geese](https://www.nps.gov/yell/learn/photosmultimedia/sounds-dipper.htm).
- [A09] Godot, [Standard Material 3D](https://docs.godotengine.org/en/stable/tutorials/3d/standard_material_3d.html).
- [A10] Poly Haven, [Pine Sapling Small](https://polyhaven.com/a/pine_sapling_small).
- [A11] Poly Haven, [Pine Roots](https://polyhaven.com/a/pine_roots).
- [A12] Poly Haven, [Dead Tree Trunk](https://polyhaven.com/a/dead_tree_trunk).
- [A13] Poly Haven, [Dry Branches Medium 01](https://polyhaven.com/a/dry_branches_medium_01).
- [A14] Poly Haven, [Rock Moss Set 02](https://polyhaven.com/a/rock_moss_set_02).
- [A15] ambientCG, [Ground037](https://ambientcg.com/view?id=Ground037).
- [A16] ambientCG, [License](https://docs.ambientcg.com/license/).
- [A17] Poly Haven, [Rocky Trail](https://polyhaven.com/a/rocky_trail).
- [A18] Amal Kumar, [Rocky Trail material creation](https://amalbubble.artstation.com/projects/LRZZ6k).
- [A19] Poly Haven, [Noon Grass](https://polyhaven.com/a/noon_grass).
- [A20] Poly Haven, [Pine Forest collection](https://polyhaven.com/collections/pine_forest).
- [A21] ambientCG, [Creation methods](https://docs.ambientcg.com/creation-methods/).
- [A22] Evolved Software, [TreeIt](https://www.evolved-software.com/treeit/treeit).
- [A23] Damco, [American Bison](https://sketchfab.com/3d-models/american-bison-88fbc7cb875444669bd45ac3597bc579).
- [A24] Anees Animates, [Animated Free Bison](https://sketchfab.com/3d-models/animated-free-bison-be2dcd97db1c4b9c91a7728d9bc89925).
- [A25] Natural History Museum of Los Angeles County, [Rainbow trout](https://sketchfab.com/3d-models/low-poly-rainbow-trout-oncorhynchus-mykiss-e2c052bd12fd492d9abf0a1c05cff175).
- [A26] SbaStuff, [Trout Fish Animated](https://sketchfab.com/3d-models/trout-fish-animated-4fa0cb7afc004d65bd49f406bffd5b2b).
- [A27] SpaceScapes, [Frog](https://sketchfab.com/3d-models/frog-b386e33f44b344bab07a17b0c02f9f1b).
- [A28] Prizrakh, [Sparrow Raven, 9 animations](https://sketchfab.com/3d-models/sparrow-raven-9-animations-27587d3c71ad46518cad2cdf245aa35e).
- [A29] Quaternius, [Ultimate Animated Animals](https://quaternius.com/packs/ultimateanimatedanimals.html).
- [A30] Maxtree, [Plant Models Vol. 60](https://maxtree.org/products/plant-models-vol-60/).
- [A31] Graswald, [End User License Agreement](https://graswald.notion.site/End-User-License-Agreement-508b4d0a39714035a9061c569723d5c3); former [GScatter landing page](https://www.graswald3d.com/gscatter), unavailable during review.
- [A32] Zacxophone, [Animated Insect Pack](https://superhivemarket.com/products/animated-insect-pack).
- [A33] Godot, [Available 3D formats](https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/available_formats.html).
- [A34] Godot, [Mesh LOD](https://docs.godotengine.org/en/stable/tutorials/3d/mesh_lod.html).
- [A35] Godot, [Visibility ranges/HLOD](https://docs.godotengine.org/en/stable/tutorials/3d/visibility_ranges.html).
- [A36] Poly Haven, [Asset license and provenance](https://polyhaven.com/license).
- [A37] Poly Haven, [Public API terms](https://github.com/Poly-Haven/Public-API/blob/master/ToS.md).

- [A38] USGS, [NAIP Plus ImageServer description and reuse status](https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer); exact tile attributes and export URL retained in `references/imagery_source_catalog.json` and `references/orthophoto.jpg.provenance.json`.
- [A39] rufusrockwell, [Lupine Plant](https://sketchfab.com/3d-models/lupine-plant-bf30f1110c174d4baedda0ed63778439).
- [A40] evolveduk, [Willow](https://sketchfab.com/3d-models/willow-422de2372f3d46dfb314a0cd5da512fe).
- [A41] PlantCatalog, [Yellow bush lupine](https://sketchfab.com/3d-models/realistic-hd-yellow-bush-lupine-2525-1e35ce459fec4ab8ad88df5e2a1791a2).
