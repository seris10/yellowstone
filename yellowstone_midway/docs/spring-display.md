# Spring display and overlook projection

Grand Prismatic uses an image-informed display palette independent of the
published radiative-transfer ramp. The original numerical water and microbial
pigment outputs remain intact. `data/display/prismatic.json` identifies the
palette as authored, with unknown uncertainty, camera processing and lighting.
Steam-whitened blue samples remain reference observations; they do not tint the
water beneath the steam a second time.

The water mesh retains its mapped boundary and normalized polygon radius.
Blue and cyan occupy most of the radius. The green transition spans radius
fractions 0.84-0.974, followed by a thin yellow edge at 0.974-1.0. These widths
are authored display choices, not measured microbial boundaries. The apron
profile includes yellow, tan, a short brown-purple interval, orange, and outer
gray-purple. NAIP chroma modulates the outer orange support so the mapped
runoff paths retain their spatial differences. Terrain illumination, wetness,
snow and the evolving scientific pigment field continue to affect the apron.

Moisture darkening uses the wet mask and flow support. Smooth-film roughness and
specular response require positive flow or mapped pool support. The binary wet
mask alone does not establish a continuous water film. This removes isolated
mirror-bright hillside marks while retaining gloss along supported outflows.
These material responses remain authored display parameters; the wet and flow
rasters are unchanged.

NPS describes yellow organisms in the hotter water and orange, brown and green
communities in cooler water. Nugent et al. (2015) distinguish water-column
optics from bottom reflectance. Neither source supplies camera-independent
RGB values for every viewing condition.

The terrace display contains authored relief aligned outward from the pool,
with irregular phase along the flow fronts. Its 6.5 m characteristic spacing,
0.8 m ridge width and 0.065 m height scale are unmeasured. The softened Fourier
profile produces approximately +/-0.0282 m height and a maximum gradient
of 0.0431 on the 0.625 m source grid. Normal and edge maps use mipmaps and
anisotropic filtering. The terrain vertices and collision do not move.
The image maps add two apron texture samples and one water-ramp sample;
they add no geometry or draw calls.

## Water boundary visibility

The render mesh subtracts the exact mapped thermal-water polygons, including
partially intersecting boundary triangles. Each pool polygon is triangulated;
convex half-plane partitions remove those triangles without filling enclosed
holes. New boundary positions and attributes use barycentric interpolation on
the original terrain triangles. Stable relative-coordinate interpolation and
explicit emitted winding checks bound float-roundoff slivers. Original mesh
vertices remain as an unchanged prefix, and the original mesh resource supplies
idempotent cuts and restoration. Collision retains its source surface proxy.
Unsupported auxiliary LODs and non-finite coordinates are rejected.

A separate vertical render interface closes the gap between that interpolated
terrain edge and the mapped flat water elevation. Top vertices retain source
heights; bottom vertices meet the water plane at identical horizontal positions.
The interface retains interpolated colors and texture coordinates. Its 711
segments cover 616.949 m of mapped shoreline and add 2844 double-sided triangles
in one draw. It supplies an authored visual seam, with no collision or bathymetry
interpretation. The source terrain vertices remain unchanged.

For the actual core, 722 partial triangles are clipped and 3263 boundary
vertices are added. The render mesh has 176044 triangles, 682 more than the
previous conservative whole-triangle cut. Removed horizontal area is
9962.3563 m2; its difference from independent Clipper intersections is below
0.0004 m2. These are arithmetic consistency checks, not accuracy estimates for
the source shoreline survey.

## Reference sampling

`tools.sample_image_gradient` samples linear-light transects from supplied
images. It retains image SHA-256, pixel coordinates, sRGB assumptions,
illumination notes, valid strip fraction and color gradients. JSON and CSV
outputs preserve raw color observations and their units. Out-of-image samples
remain missing, rather than becoming black or repeated edge pixels.

A specification contains named transects:

```json
{
  "illumination": "sunlit; steam crosses the water; exposure unknown",
  "transects": {
    "water_to_apron": {
      "start": [770, 235], "end": [285, 235],
      "count": 256, "half_width": 3, "strip_samples": 7
    }
  }
}
```

Run from the Python project:

```sh
.venv/bin/python -m tools.sample_image_gradient reference.png transects.json \
  --out work/reference-gradient.json
.venv/bin/python -m tools.prepare_spring_display
```

Optional `planar_controls` contains four or more corresponding `plane` and
`pixel` coordinate pairs plus `units`. The normalized DLT homography makes
sampling uniform in the supplied plane, rather than uniform in perspective
pixels. The report includes control-point reprojection RMS. Correspondences
must refer to the same physical plane. Steam, foliage, surface relief and
incorrect point matches invalidate that geometric interpretation. The supplied
overlook photograph lacks calibrated camera pose or surveyed correspondences,
so its published transects remain in pixels. Their ring widths are not labeled
as meters. Local screenshot files remain outside distributed assets.

## Apparent scale

The mapped pool bounding dimensions are 93.93 by 101.74 m. Its equivalent-area
diameter is 92.53 m, consistent with the scale of the NPS diameter description
(200-330 ft). That agreement is a scale check, not a new boundary survey.
The overlook eye position is 233.65 m from the pool center, including
231.32 m horizontal distance. The pool subtends 24.34 degrees horizontally.

Godot's `KEEP_HEIGHT` camera uses vertical FOV. At 16:10, the 72-degree gameplay
setting covers 98.59 degrees horizontally. That makes the pool occupy only
18.55% of screen width when centered. The same geography occupies 37.03% at
40 degrees vertical and 50.30% at 30 degrees vertical. The latter is 2.71 times
as wide on screen without moving the camera or altering the land.

This supports projection and photographic framing as a major cause of the
apparent distance discrepancy. Panorama zoom, crop and exact viewpoint are
unknown, so the photograph cannot establish a unique replacement FOV.
Gameplay FOV remains unchanged. An adjustable photo-view FOV is the appropriate
next camera control; terrain rescaling has no evidential basis here. Fuller
crowns address transparency independently of this projection effect.

## Evidence

- `evidence/open-water-boundary.json`: source-preserving boundary cuts and area checks.
- `evidence/open-water-boundary-independent.json`: 160 independent randomized Clipper comparisons.
- `tools/validate_water_cut_geometry.gd`: repeatable randomized geometry check.
- `evidence/overlook-projection.json`: independent pinhole projection sweep.
- `evidence/spring-display-native.json`: five source-bound native captures,
  visual seam review and projection agreement within 0.000000062 screen width.
- `evidence/spring-reference-gradient.json`: source-bound image transects.
- `assets/textures/prismatic_display.json`: generated-map identities and units.
- `tools/validate_spring_display.gd`: native material bindings and matching
  72-, 40- and 30-degree overlook captures.

The native review confirms that the black shoreline wedges are gone and that
the outward terrace edges are visible. These captures precede the final forest
bake. The checks establish interpolation, homography, metric texture generation,
material binding and projection. They do not establish measured reflectance,
local bathymetry, a calibrated camera match or human visual acceptance.

Sources:

- NPS Grand Prismatic Spring:
  https://www.nps.gov/places/000/grand-prismatic-spring.htm
- Nugent et al. (2015), doi:10.1364/AO.54.00B128:
  https://www.montana.edu/jshaw/documents/YNP%20pool%20colors%20-%20Nugent%20et%20al%20-%20AO2015.pdf
- Godot 4.5 Camera3D:
  https://docs.godotengine.org/en/4.5/classes/class_camera3d.html
