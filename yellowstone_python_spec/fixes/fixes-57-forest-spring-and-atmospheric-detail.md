# Forest, spring and atmospheric detail

## Scope

Retain mapped land, pool boundaries, terrain elevation and observed tree records.
Improve authored display geometry, image-informed color, camera interpretation
and weather optics. Source photographs remain reference inputs; image colors
have unknown illumination, camera processing and uncertainty.

## Findings and implementation

- Residual canopy cells expose radial wood where the footprint mask removes
  foliage. Replace the independent cell scaffolds with foliated bough volumes
  attached to the existing support; bound wood to the foliage footprint.
- Lodgepole shoots lie in narrow horizontal whorls. Use irregular ascending
  shoots and a tapered leader, with overlapping foliage between whorls. Preserve
  graph attachments and independent DBH, height and crown dimensions.
- Authored snags have many intact radial branches. Represent irregular broken
  stubs and retain their leafless state.
- Forest-floor candidates are sparse and mostly crossed cards. Increase the
  authored litter and downed-wood display, terrain-align logs, and add bent
  blade/leaf geometry with anchored wind. Respect water, mineral and route
  exclusions. Local fern occurrence remains unverified.
- Pool radiometry and display lighting compound the dark appearance. Preserve
  the scientific optical outputs; add an explicitly image-informed display
  palette and radial profile for Grand Prismatic. Retain changing illumination
  and steam. Preserve mapped orange runoff and outer gray-purple areas.
- Basin sheet edges need spatially coherent, band-limited relief at meter scales.
  Add flow-oriented terrace normals without changing terrain or collision.
- The cloud shell underside lies at zero vertical density. Integrate the
  visible layer through its thickness and retain weather-dependent coverage.
- Rainbows require liquid drops, direct sunlight and antisolar viewing geometry.
  Implement primary and weaker reversed secondary angular spectra with a
  finite-lived, advected rain curtain. Clear startup contains no curtain.
  Repeated weather toggles do not reseed the atmosphere or guarantee a bow.
- Measure pool angular size, camera field of view and reference framing. Report
  perspective limits; geography remains fixed.

## Verification

Check geometry attachment, crown vertical occupancy, snag stub lengths,
terrain contact, exclusions, finite transforms, and LOD triangle counts.
Test image sampling on analytic gradients and homographies. Check rainbow
angles against Snell's law, color reversal, history dependence, decay, sun
occlusion and clear-start absence. Capture actual native renders of the
overlook, nearby forest floor, clouds and controlled rainbow cases. Record
frame-time and primitive/draw counts using fixed forcing and camera paths.
Run the Python scopes, baseline build, provenance and style checks. Preserve
unaccepted scientific claims and disclose unmeasured appearance/performance
limitations. Verify pushed commit and packaged release contents.

## Sources

- NPS Yellowstone, Forests: https://www.nps.gov/yell/learn/nature/forests.htm
- Lotan and Critchfield (1990): https://research.fs.usda.gov/silvics/lodgepole-pine
- NOAA NESDIS, What Causes a Rainbow:
  https://www.nesdis.noaa.gov/about/k-12-education/optical-phenomena/what-causes-rainbow
- Nugent et al. (2015), doi:10.1364/AO.54.00B128.

Display distributions and local species placement are authored. Optical
geometry is analytical; rainbow frequency is not locally calibrated.

## Submission cost audit

The fixed-path ABBA comparison submits about 23.40 million primitives for the
published surface scene and 50.85 million for the detailed scene. The detailed
scene measures 107.212/133.058 ms median versus 52.247/89.916 ms for the baseline;
desktop contention is uncontrolled, but the repeatable primitive increase is a
structural regression. Conservatively padded tree batches submit detailed meshes
for instances whose shader distance test subsequently rejects every vertex.
The raw results remain in the performance evidence.

Reduce this unused submission before release. A conservative per-instance
selection may compact immutable transform/color/custom-data records into the
visible prefix of a MultiMesh. Its distance envelope must contain every instance
that can survive the existing shader LOD interval, including transitions and
camera motion between updates. Camera changes and teleports require selection
updates before rendering. Preserve shadows, geometry, render distances, source
records and complementary transitions. Avoid changing shared source buffers or
mutating serialized geometry. Verify frozen-view image equivalence, boundary
motion and teleport coverage, and record submitted primitives and native timing.
The optimization must remain active when model playback is paused or a capture
harness disables world simulation processing.

## Terrace repetition audit

Native wide views expose broad, regularly spaced dark rings across the spring
apron. The authored radial terrace phase has insufficient variation, and its
edge channel multiplies albedo strongly enough to read as a concentric target.
The supplied reference shows irregular sheet margins and flowing transitions.
This visible mismatch requires correction before release.

Preserve measured geography, pool geometry, source rasters, scientific outputs
and terrain collision. Modify the display treatment to interrupt coherent
circular bands and retain irregular, directional sheet-edge and normal detail.
Keep authored procedural structure distinct from surveyed microtopography.
Check the actual saved world from the overlook and close to the apron, preserve
source hashes, and include the final shader in runtime and performance checks.
