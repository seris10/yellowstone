# Lodgepole crown continuity

The close overlook trees exposed horizontal gaps between branch whorls. An
actual-world comparison with automatic mesh-index LOD disabled retained those
gaps, so the repair changes the authored branch architecture itself. Source tree
positions, heights, crown dimensions, terrain and census counts are retained.

The authored whorl-spacing parameter is now 0.30 m rather than the immediately
preceding 0.48 m candidate. The upward tip-turn fraction is 0.50 rather than 0.32.
Each lateral carries two to three needle shoots instead of three to five. These
values distribute approximately the same foliage budget across more vertically
overlapping branches. Seeded variation, attached branches, the upper taper and
the attached terminal leader retain irregular holes and a pointed crown.
These are bounded display choices, not measured local growth increments or a
calibrated leaf-area model. A whorl count does not establish tree age.

Straight secondary axes previously used a redundant middle tube ring. The
exporter now omits that ring only when all source points match the corresponding
linear interpolation within 1e-10 m; curved source axes keep their intermediate
rings. The source branch graph is preserved. This removes redundant triangles
without moving the twig surface and offsets much of the cost of the added
primary branches.

The paired native preview used the actual overlook sapling variant 2 at height
6.096 m, radius 1.093 m and yaw 5.746245 rad, plus dense variant 0. Agent inspection
found overlapping pointed crowns with holes instead of full empty horizontal
strata. Those preview renders preceded the exact-surface twig-ring optimization;
the final imported library and baked world require their separate release checks.

| Local comparison | Prior candidate | Final export | Change |
| --- | ---: | ---: | ---: |
| Sapling variant 2 needle cards | 3,130 | 3,102 | -0.9% |
| Sapling variant 2 triangles | 13,836 | 14,230 | +2.8% |
| Dense variant 0 needle cards | 8,584 | 8,604 | +0.2% |
| Dense variant 0 triangles | 37,724 | 39,188 | +3.9% |

These counts compare the two local architecture candidates, not the published
release. They do not establish frame time. Asset topology, source attachment,
filtered alpha coverage, raw LOD endpoint silhouettes, per-instance transitions
and final world performance have distinct checks. Failing endpoint silhouette
limits remain failures even when the transition shader is continuous.
