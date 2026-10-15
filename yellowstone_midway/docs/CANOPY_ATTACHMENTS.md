# Residual canopy attachments

Residual coverage cells are display geometry, not additional measured trees.
Their source anchors, top elevations, native coverage/support masks and host or
terrain endpoints remain unchanged. An upright photo bough on a crossed strip
could appear as a floating miniature tree because the support disappeared
edge-on. Geometry revision 2 gives those connections a three-dimensional
cross-section and rotates the bough axes laterally.

The near and middle LODs retain 40 and 16 boughs per cell. Each bough uses the
existing human-made CC0 pine photo texture, two crossed cards and a tapered
three-sided twig. Five-sided tapered tubes form the central support and its
connection to an existing rendered bole or the rendered terrain. Bough axes
range from 65 to 100 degrees from vertical. These orientations and dimensions
are authored with unknown local uncertainty.

Unattached support diameter follows source height/80, clamped to 0.05-0.28 m.
Attached branch diameter follows horizontal span*0.06, clamped to 0.036-0.13 m.
Twig diameter tapers from 0.028 to 0.010 m. These metric dimensions do not vary
with camera distance. Source terrain endpoints remain 0.04 m below the rendered
terrain triangle. The support diameter rules do not infer a stem census.

`CanopySurface.refresh_geometry` replaces only three shared meshes in memory
when an older baked group is loaded. It shallow-clones each MultiMesh, retains
all transform/custom records and bounds, and leaves the original resources
unchanged. The canonical builder produces the same revision for future bakes.
A second upgrade call leaves mesh identities unchanged. A material revision
parameter preserves the interpretation of older geometry.

Triangles per displayed cell increase from 208/88/14 to 420/180/26 across the
three LODs. Instance records, batch count, distance transitions, masks and the
existing no-shadow policy are unchanged. The clone capacity adds approximately
30.56 MB of renderer instance-buffer storage; engine overhead is not included.
Three frozen native views show approximately 0.83-1.14 million additional
submitted primitives. Timing is reported separately by the fixed-forcing world
benchmark.

`evidence/canopy-visible-attachments.json` binds 17 native images and the source
receipt. It covers three original/new world pairs, eight azimuths, a full-height
support and two mask controls. The zero-coverage and zero-support fixtures are
pixel-identical; the positive fixture adds visible foliage and twig pixels.
All 477,471 records across three LODs preserve their exact source buffers and
indices. All 159,157 display cells remain represented at each LOD. The 77,273
unattached endpoint checks agree with rendered terrain contact within 0.000005 m.

`evidence/canopy-tube-geometry.json` checks finite/unit normals, nondegenerate
clockwise geometry, woody twig-to-card contact after scaling, native footprint
sampling and positive foliage retention. Near/middle minimum retained boughs
are 5/3; no cell becomes support-only under the source masks.

The inspected views show materially clearer branch connections. Some source
cells still display long bare authored supports below shallow crowns. These
supports retain the existing no-shadow policy. This is a visible attachment
correction, not field validation of reconstructed branch form or local stem
counts. Other renderer backends and human field acceptance remain untested.
