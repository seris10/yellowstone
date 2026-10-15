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
