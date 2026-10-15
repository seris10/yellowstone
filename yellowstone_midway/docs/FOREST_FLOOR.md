# Forest-floor display

The independent authored floor layer contains 18,000 plant patches, 24,000
needle, twig and bark-fragment patches, 1,600 fallen logs and 24 snags within
the supported canopy window. These are display budgets and authored positions.
They are not a stem census, local species survey or mortality reconstruction.
Observed tree records, mapped exclusions and terrain remain separate inputs.

NPS describes lodgepole forest understory as often sparse, with elk sedge and
grouse whortleberry. Pinegrass has a wider forest association, especially on
better-developed or moist soil. The display retains patchy plants and increases
litter and downed wood under canopy. Kinnikinnick remains a representative
regional guild with unknown local occurrence. Fern occurrence at the overlook
is unverified and no fern layer is present.

The producer samples a deterministic 2.5 m candidate grid with jitter. Each
patch requires valid canopy support, mapped route/water/mineral clearance,
and a bounded slope. Plant occurrence follows an authored moderate-cover
response; litter can also occur under closed canopy. Candidate order is
seeded before budget limits, avoiding preferential filling at one map edge.

Inside the core window, contact uses the runtime 2 m triangle mesh made from
the float32 core height plus float32 microrelief. Outside it, contact uses the
master 4 m terrain triangles. Sampling the master alone inside the core had
placed some earlier patches above or below the visible ground; these records
were regenerated. The three core inputs retain hashes in source provenance.

Plant and litter patches align to sampled terrain normals. Sixteen inner-ring and sixteen perimeter
samples reject footprints with a plane residual above 0.008 m. Fallen logs
follow a straight fitted axis above samples no more than 0.25 m apart. The
producer rejects protected crossings and under-log gaps above 0.24 m. A log
contacts at least one sampled terrain location. These tests bound contact
against the rendering terrain; sub-grid natural ground roughness is unknown.

Live plants use bent opaque blades or cambered leaves and segmented stems.
Wind weights are zero at roots. Leaf attachment weights match the stem at
those heights. Static litter uses uniform scale, retaining round twig cross
sections instead of compressing them with plant-height transforms. A shallow,
irregular bed carries the human-made CC0
[pine-needle photograph and normal map](https://polyhaven.com/a/forrest_ground_03).
Each bed occupies 60-64% of its validated 1.1-3 m square footprint. Its center
rises 4.4-12 mm, with separate 3D needles, twigs and bark fragments supported
above it. Needles span an authored 1.1-7.8 cm. The edge feathers through a shared
coverage threshold so the two LODs do not double its opacity during a fade.
Texture coordinates retain the source 2 m repeat with seeded phase variation.

The 24,000-patch cap is unchanged. Preferred widths are 2-3 m. When a wide
footprint fails the same contact or exclusion checks, the producer tests a
1.1-1.9 m footprint at that candidate. It accepts 12,358 compact fallbacks.
The 24,000 accepted beds sum to 59,424 square meters at the near LOD, compared
with 32,134 for the smaller prototype. Within 40 m of the overlook, fallback
restores 49 beds and 58.24 nominal square meters; the wide-only attempt had
four beds and 9.97 square meters. Nearest litter is 8.39 m from the overlook.
These are geometric sums before overlap, edge feather, occlusion and distance
culling. They are not measured field cover fractions or union-area estimates.

The underlying forest terrain also uses the new pine-needle photograph, so
needle content continues between the raised debris beds. Poly Haven identifies
Rob Tuytel as its photographer and gives a 2 m source width. The old gravelly
Forest Ground 04 remains the meadow substrate at 3.15 m; trail and mineral
sources remain intact. Forest material removes the previous olive tint and
reduces aerial canopy-color mixing by up to 80 percent according to forest
weight. This is an authored display correction, not field color calibration.
The existing texture arrays gain one layer each, keeping sampler and draw
counts unchanged. Forest pixels add up to four texture reads for separate
needle color, normals and ARM; nonforest pixels skip those reads.

Logs use
the existing human-made Poly Haven pine bark texture under CC0, with cylindrical coordinates that keep grain aligned along the log
and a 0.5 m authored texture repeat. The matching normal map provides bark
relief. Both imported maps now retain mipmaps; source RGB is unchanged. Exposed ends have band-limited authored growth-ring variation; ring
spacing is decorative and does not estimate tree age. Procedural geometry and display colors are authored;
they are not species-diagnostic scans.

MultiMesh batches share geometry within spatial bins. Near geometry transitions
to simpler meshes over 20-28 m using complementary screen-door coverage.
Litter disappears over 57-65 m and live patches over 102-110 m. Floor vegetation
and litter cast no dynamic shadows; logs retain shadows and simpler distant
geometry. The new opaque surfaces avoid alpha-texture overdraw. No CPU update
iterates individual plants each frame. These choices constrain rendering work;
frame-time improvement requires a native world benchmark.

Godot culls a MultiMesh batch by distance to its bounding-box center. Plant
and litter batches therefore expand their coarse visibility ranges by half
the bounding-box diagonal, while the shader keeps the stated per-root fade
distances. Every root lies inside that sphere. The triangle inequality then
guarantees that coarse culling cannot hide a nearby patch at a tile edge.
This avoids missing near detail in 64 m batches without disabling distance
culling for the whole layer. Floor snag meshes and materials are isolated
from the tree asset cache. They explicitly disable tree per-instance LOD,
which requires custom data that floor batches do not carry. A maintained
load-order regression binds tree LOD first, then verifies independent floor
resources and unchanged tree materials across all variants and detail levels.

| Family | Near triangles | Mid triangles |
| --- | ---: | ---: |
| Sedge or pinegrass patch | 192 | 48 |
| Broadleaf patch | 760 | 288 |
| Litter patch | 640 | 172 |

`validate_floor_geometry.gd` checks finite geometry, unit normals, footprint
bounds, anchored wind weights and lower distant triangle counts.
`validate_forest_floor.gd` checks packed instance transforms, source identity,
terrain alignment, record limits and invalid-input preservation. The Python
checks include analytic slopes, an interior protected-route crossing, terrain
humps, corrupted contact records and deterministic placement. Native closeups
and the world benchmark provide separate appearance and performance evidence.

Source records preserve per-record provenance and round numeric values to ten
decimal places before compact JSON serialization. Validation runs on those
serialized values. No raw observation is rounded or modified.

The 2026-10-15 Godot 4.5.1 headless validation passed 625,181 checks over all
43,624 source records, including invalid-input controls. The independent
geometry validator passed 33,595 checks. Those include scalar contact checks
near both map boundaries and shallow terrain slopes. Source contact validation
uses scalar double precision before the render transforms are packed as
float32. A native Metal closeup compiled both floor shaders and showed the
rounded leaves, litter depth and mapped bark without runtime errors. These
receipts establish geometry and source consistency, not full-world frame time
or photographic equivalence.

The separate `validate_floor_contact.gd` passed 166,603 comparisons against the
runtime core height loader and independently evaluated triangle planes. It
checked 2,197 anchors inside the core and 37,355 log profile samples across
both terrain authorities, plus 1,344,000 independent inner/perimeter plane
probes. The maximum sampled plane residual remains below 8 mm. The maximum discrepancy was 0.00000762 m, below
the 0.00001 m numeric tolerance. This checks agreement with rendered terrain,
not ground-survey accuracy. The regenerated source SHA-256 is
`6e534dc0e446f74c9e6347a30cfd8140ffce38160e6ae7ec7444c3a69b6d6ea3`.

The final saved-scene Metal captures are in
[`evidence/forest-render`](../../evidence/forest-render/report.json). They include
walking views and the same overlook camera at 72, 40 and 30 degree vertical
fields of view, with input hashes and a residual-canopy control. Fine needle
content now continues across the ground between raised debris beds. The
subsequent [canopy attachment revision](CANOPY_ATTACHMENTS.md) replaces
edge-on support strips with tapered tubes and crossed bough planes. Some
residual cells retain long authored stems and shallow crowns; log geometry
remains a simplified straight solid. These appearance checks do not establish local
botanical accuracy or frame-time performance. The Python producer tests passed
27 cases; the numerical receipts remain separate from the visual review.

Sources:

- [NPS Yellowstone forests](https://www.nps.gov/yell/learn/nature/forests.htm).
- [USDA FEIS kinnikinnick](https://research.fs.usda.gov/feis/species-reviews/arcuva).
- [Poly Haven pine tree](https://polyhaven.com/a/pine_tree_01).
- [Poly Haven forest ground](https://polyhaven.com/a/forrest_ground_03).
- [Poly Haven CC0 asset license](https://polyhaven.com/license).
- [Godot visibility range distance convention](https://docs.godotengine.org/en/4.5/tutorials/3d/visibility_ranges.html).
