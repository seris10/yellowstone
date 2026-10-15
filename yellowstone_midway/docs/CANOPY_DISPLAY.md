# Residual canopy display anchors

Residual canopy is a coverage layer derived from the supplied LiDAR products.
Its 2 m cells are display units, not inferred trees. The underlying mask uses
0.5 m pixels. Source cell indices, coverage fractions, canopy elevations,
ground elevations, observation files and represented area remain unchanged.

An authored cluster origin lies at the nearest covered native pixel center
inside its original cell. Ties follow stable row-major order. The maximum
possible displacement from the source cell center is
`(cell_size - mask_pixel_size) / sqrt(2)`, or approximately 1.061 m for these
inputs. This placement is explicitly marked `authored_display_placement`.
The chosen pixel must also have valid source support. Pixel centers avoid
ambiguous sampling on a coverage boundary.

Both close foliage meshes place one complete needle shoot at the cluster
origin. The remaining shoots retain their seeded distribution. A woody twig
and its foliage share the same coverage sample. This prevents a sparse cell
from retaining bare support geometry after all of its needle shoots were
discarded. That earlier anchor-only correction added no geometry or material
passes. The final attachment revision separately increases geometry as described
below; its three shared meshes retain the existing draw-batch count. Source-cell heights and vertical display-depth rules remain
in force; grounded or rendered-bole connections are recomputed at the new
horizontal origin.

The close cutout now isolates a human-made pine shoot from the existing
[Poly Haven pine tree atlas](https://polyhaven.com/a/pine_tree_01), licensed
[CC0](https://polyhaven.com/license). The connected alpha component keeps
the original visible RGB and opacity. Transparent RGB is dilated to prevent
dark filtering fringes. Source hashes, component selection and root placement
are saved in `assets/imported/canopy_shoot/pine_shoot.json`; the preparation
script reproduces the derivative. This representative pine image does not
establish local species identity.

Five copies of that original 0.18 by 0.36 m shoot, including transparent
padding, form an authored connected bough. The composite card is 0.48 by
0.64 m. Its branch arrangement and dimensions are explicit authored choices,
not botanical measurements or generated foliage imagery. Cards use
65-100 degree inclinations from vertical in the final attachment revision.
Each bough site has two crossed foliage planes, with its stem endpoint joined
to a tapered three-sided twig after vertical compression. Forty near and
sixteen middle bough sites remain per residual cell; the main connection uses
five-sided tapered tubes. Near/middle/far budgets increase from 208/88/14 to
420/180/26 triangles per cell. Only three shared meshes change, preserving
instance buffers and material passes; the added primitives still incur a cost.
The shader selects LOD using each source canopy top, with complementary
8 m transitions at 45 and 120 m. Each batch extends its coarse range by half
its bounds diagonal, ensuring a close patch at a 64 m bin edge keeps near
detail. Distance rejection precedes the three texture samples. The skin
transition remains 180-260 m and does not alter the underlying coverage mask.

Complete mip chains use linear-light, alpha-weighted color filtering and
calibrated alpha coverage with clamp-to-edge sampling. Tiny mip levels cannot
retain every shape; the metadata records this limitation.

Connections to resolved boles have a maximum authored horizontal span of
2 m. A patch beyond that limit receives a local support at its source ground
elevation in synthetic fixtures. Production local supports instead use the
visible core terrain triangles, including microrelief, or master triangles
outside the core, embedded 4 cm below that surface. Source ground and canopy
elevations remain unchanged; the render contact has separate provenance and
terrain hashes. This matters because covered-pixel relocation can move the
origin across a slope. Before the correction, source ground differed from
visible terrain by -0.609 to +0.477 m among 893 anchors within 40 m of the
overlook. These supports are explicit display geometry and do not add
measured stems to the census. This removes the previous possibility of an
8 m diagonal connection crossing a visible opening. Native scene inspection
remains necessary to judge the appearance of close residual foliage.

`validate_canopy_surface.gd` checks covered anchors, the displacement bound,
nearest-pixel placement, unchanged source heights, refreshed support endpoints,
and the number of retained shoots for every close and middle LOD instance.
Its report includes the minimum retained shoot count and count of supports
with no retained shoots. Native shader, appearance and performance checks are
separate from this geometry validation. Foliage render coverage and local
stem count remain unmeasured; this repair does not constitute a field-validated
canopy reconstruction.

The earlier anchor/coverage Godot 4.5.1 headless run passed 16,124,882 checks across all
159,157 active cells, retaining the original 329,939 square meters of mask
coverage. Every cluster retained foliage at both close detail levels: the
minimum retained shoot counts were 5 and 3, with zero support-only clusters.
The input metadata SHA-256 was
`d9a68973162322b275bf21b2db268638cbbb30f2a84b90765967f4f497a4abde`.
These counts describe mask-supported shoot anchors, not visible pixel area.

The final attachment revision has separate [implementation and native evidence](CANOPY_ATTACHMENTS.md). Its native checks inspect visible connections from eight azimuths and three world views; they supplement source contact checks. Residual cells remain coverage units, so long authored stems and crowns confined to narrow cells can still look unlike measured individual trees. Geometry/contact success does not establish field or human visual acceptance.
