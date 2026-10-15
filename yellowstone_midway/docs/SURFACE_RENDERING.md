# Canopy support and surface detail

Residual LiDAR coverage describes canopy area and elevation, not individual
stems. The display preserves the same residual mask, counts and source-cell
heights. Forty near and sixteen middle bough sites use unchanged human-made
CC0 pine-shoot photographs. Each now has two crossed foliage planes and a
three-sided tapered twig, joined to a five-sided tapered main support. The
final near/middle/far budgets are 420/180/26 triangles per cell, increased
from the prior 208/88/14. Three shared meshes replace the old display geometry
at runtime; source instance records, material passes and draw-batch counts
are retained. This adds primitive cost and does not establish a speedup.
Per-instance shader distances preserve the 45, 120 and 350 m boundaries;
coarse batch ranges include their bounding-sphere radius. The continuous
coverage skin retains its 180-260 m transition.

A bounded covered-pixel anchor and guaranteed central shoot prevent empty
foliage clusters with exposed support only. An eligible nearby bole can host
a connection of at most 2 m horizontally. Other cells use explicitly authored
local supports, anchored to the actual rendered core/master triangles while
retaining measured source-ground values as provenance. The 0.48 by 0.64 m
bough dimension, branching and support sizes are authored with unknown local
uncertainty. Tapered tubes keep a visible connection at multiple azimuths;
long stems and crowns confined to source cells remain reconstruction limits.
See [canopy evidence and limits](CANOPY_DISPLAY.md) and the
[final attachment evidence](CANOPY_ATTACHMENTS.md).

## Ground and basin

Human pine-needle Forest Ground 03 and trail PBR maps use their 2 meter source
widths. The retained gravelly Forest Ground 04 substrate uses 3.15 meters
under meadow and mineral weighting. The forest branch uses separate color,
normal and ARM samples in the same texture arrays: up to four extra texture
reads, unchanged samplers and terrain draws. Forest color keeps the photograph
without the previous olive multiplier and reduces aerial canopy-green mixing.
These authored display choices do not establish field color calibration. The mineral display uses a deterministic periodic height field on a
4 meter tile. Its authored RMS relief is 0.0045 meters, with wavelengths from
0.02 to 1.5 meters and a power spectrum proportional to spatial frequency raised
to -3.4. Spectral differentiation produces surface normals in metric units.
The same field supplies bounded grain and roughness. A rotated 19 meter sample
adds intermediate variation; its normal slope scales by 4/19. These statistical
display parameters have no local surface-roughness calibration.

Normal, height, and roughness channels share a texture-array layer. Mipmaps and
anisotropic filtering limit the represented frequency band to the pixel footprint.
This adds detail without terrain subdivision or extra terrain draw calls. Details
below the image sampling bandwidth average into the surface appearance.

Mapped basin detail comes from the existing USDA NAIP image, sampled at 0.625
meters per pixel over the 1280 meter core. Color ratios use linear light and a
12 meter Gaussian local mean, with authored contrast gain 1.6 and bounds 0.45 to
1.7. Applying these ratios beneath changing model pigment preserves mapped spatial
structure during pigment transitions. The image supplies no subpixel geography.
Its canopy and shadow imprints remain a limitation of aerial display color.

White sinter, microbial pigments, and water are distinct causes of basin appearance.
The display does not infer mineral chemistry or measured microbial communities from
RGB imagery. See the [USGS hydrothermal surface explanation](https://www.usgs.gov/observatories/yvo/news/better-understanding-whats-under-your-feet-hydrothermal-areas-neutral).
The filtering principle follows [GPU Gems image reconstruction and sampling](https://developer.nvidia.com/gpugems/gpugems2/part-iii-high-quality-rendering/chapter-27-advanced-high-quality-filtering).

Terrain color mipmaps are now prepared offline in premultiplied linear sRGB,
then encoded once for source-color sampling. The previous manual RGBA8 mip
generation averaged encoded colors: a half-black, half-white patch produced
about 0.216 linear radiance instead of 0.5. The corrected filtering preserves
level-zero pixels and uses the existing GPU RGBA8 mip allocations. Eight
hash-bound buffers add 111,848,096 bytes of distributable data. Normal, ARM,
mask and scientific pigment channels retain their raw-data filtering. See
[`color_mips.json`](../assets/textures/color_mips/color_mips.json) for every
source hash and level size.

## Outflow filtering and reloads

Wet, flow-fraction, and pool fields use the original linear stencil: 0.4 at the
center and 0.15 at each cardinal neighbor. Filtering occurs once when field textures
change. A one-texel clamped guard preserves the result of five shifted bilinear
samples, including image edges. The pixel shader uses three reads for these fields
in place of fifteen. Residual terrain normals remain separate unfiltered layers.
The material retains eleven samplers. Release reloads rebuild changed filtered
fields; unchanged texture identities reuse the bound array. Pigment interpolation
and resets retain the mapped detail throughout their existing transitions.

## Spring color and sunny atmosphere

Published ramps resolve from the selected generation's `assets/textures/pool_ramps/`
directory. Schema and pool identity accompany the actual texture binding and hash.
The saved water mesh spans the complete center-to-rim range, including its shallow
yellow and orange edge. It uses the same vertices and water boundaries.

The core elevation surface includes elevations over mapped water. Those values
are not submerged bathymetry. Ground rendering excludes a triangle only when its
complete horizontal footprint is inside a rendered thermal-water polygon. Polygon
difference must be empty, including for concave boundaries. Boundary-crossing and
dry triangles remain. Source vertices, height files, and collision data stay intact;
the collision grid remains a surface-elevation proxy. The ramp contains the complete
upwelling optical color, so ramp-driven pool fragments are opaque. Native visibility
checks use an unlit water probe, a depth-disabled reference, and restoration of the
uncut terrain as a negative control. Steam is hidden only during that isolated
probe; the production captures retain it.

The optical display follows the three terms in
[Nugent et al. (2015)](https://www.montana.edu/jshaw/documents/YNP%20pool%20colors%20-%20Nugent%20et%20al%20-%20AO2015.pdf):
surface-reflected sky, bottom-reflected sunlight, and backward-scattered sunlight.
For each representative wavelength, k=2a+b and the column contribution is
(b/2)(1-exp(-k*z))/k. Surface transmission applies on both passes. Scattering is
zero when b is zero. The authored class palette is decoded from sRGB before
transport. Ramp RGB samples contain linear light; PNG textures receive one sRGB
encoding and the shader's source-color sampler performs its inverse.
The transfer curve follows the [sRGB conversion equations](https://www.w3.org/TR/css-color-4/#color-conversion-code).
Absorption values come from Pope and Fry (1997). Scattering, palette colors,
depth profiles, and surface reflectance remain authored approximations with unknown
local uncertainty. This display has no site spectroradiometric calibration.
Grand Prismatic uses the paper's uniform yellow bottom and conical optical-depth
assumptions. Its depth reaches zero at the mapped water boundary. The optical
display profile is distinct from the authored submerged shell geometry. Radial
surface temperature does not prescribe the underwater mat. Orange and brown
outflows remain separate model pigment and mapped basin features.

Clear visibility maps to zero additional sky fog; the sky model already accounts for
atmospheric scattering. Reduced visibility restores sky fog and greater turbidity.
Clear daylight uses an authored direct-light energy of 1.35 and diffuse energy of
0.25. Cloud cover reduces the direct term and increases the diffuse term. Night
retains its astronomical response. These normalized lighting energies are display
parameters, without photometric calibration. No global saturation adjustment is used.

## Distant tree batching

Four variants share each form's physical billboard frame. Sixteen original mipmapped
view images occupy a texture array. A per-instance index selects the same variant
and camera direction as the separate materials. This combines four compatible
MultiMesh batches while preserving trees, image pixels, alpha cutoffs, dimensions,
and all distance boundaries. Native validation compares five forms, four variants,
and eight directions against the separate-material renderer after mesh serialization
and reload. Baked materials store the form identity. Runtime loads and caches the
original coverage-preserving image layers once per form, avoiding GPU readback
during a headless bake.

## Reproduction

From the Python project directory:

```sh
.venv/bin/python -m tools.prepare_ground_detail
.venv/bin/python -m pytest tests/test_ground_display_detail.py -q
.venv/bin/python ../yellowstone_midway/tools/author_lodgepole.py --supported-canopy-only
```

From the Godot project directory:

```sh
godot --headless --path . --script tools/validate_outflow_filter.gd
godot --headless --path . --script tools/validate_canopy_surface.gd -- --negative --baked --data res://data/lidar_canopy/unresolved_render_canopy.json --out res://work/canopy_support.json
godot --headless --path . --script tools/check_mat_and_core.gd
godot --headless --path . --script tools/bake_world.gd -- --vegetation-only --water
godot --headless --path . --script tools/validate_display_color.gd
godot --path . --rendering-method mobile --rendering-driver metal --script tools/validate_impostor_batches.gd
godot --path . --rendering-method mobile --rendering-driver metal --script tools/validate_terrain_render.gd -- --out=res://work/surface_render
```

The capture command records three fixed views under three sun angles and a complete
moving-camera sample with the residual canopy visible. Wall-frame timing includes
display synchronization. CPU numerical checks, image inspection, native frame
timing, source-data accuracy, and ecological validation have separate scopes.

The production default is the Mobile renderer. Godot selects Metal on Apple Silicon
through its [platform driver setting](https://docs.godotengine.org/en/4.5/classes/class_projectsettings.html#class-projectsettings-property-rendering-rendering-device-driver-macos).
The Compatibility renderer remains selectable with its command-line override.

The daylight sky evaluates an analytic single-scattering integral in linear light.
Its molecular spectrum and ozone absorption use three representative wavelength
bands from the [Bruneton atmospheric reference](https://github.com/ebruneton/precomputed_atmospheric_scattering/blob/master/atmosphere/demo/demo.cc).
Rayleigh density uses an 8000 meter scale height and 2200 meter site elevation.
The upper ozone column attenuates the incident sunlight before lower-atmosphere scattering.
The display uses an authored aerosol column, phase asymmetry 0.76, and radiance
scale 32 followed by luminance compression. RGB ratios remain unchanged by that
compression. Stars fade out in daylight and remain available at night. The sun
disk and weather-driven clouds remain present. This plane-parallel approximation
clamps grazing directions; multiple scattering, local aerosol calibration, and
curved-horizon transport are absent. A native zenith check requires blue/red above
1.3 and green/red above 1.05; it establishes a display contract, without field color
calibration.

## Spring terrace contrast

The spring terrace texture stores an authored radial height derivative and a
repeated edge mask. Applying that edge mask as a 42 percent albedo reduction
created continuous dark circles around the spring. The material retains the
complete normal contribution and limits the albedo accent to 7.5 percent.
Its weight is the larger of the existing flow fraction or a smooth transition
from 0.06 to 0.24 in the absolute mapped linear-light luminance ratio difference
from one. The aerial ratio is already sampled by the ground material. These
thresholds and the edge strength are authored display parameters with unknown
local uncertainty. Aerial contrast is not a terrace survey.

The correction adds no texture fetches, changes no generated texture, and
retains terrain, collision, source rasters, mapped colors and scientific inputs.
Eight native before/after captures in
[`evidence/terrace-contrast`](../../evidence/terrace-contrast/report.json)
cover the wide view, the 40 degree overlook, the apron and an orthographic
control. Draw calls and submitted primitives are identical within each pair.
The [`source review`](../../evidence/terrace-contrast/review.json) verifies
seven input hashes against the source commit and retains the normal term.
A diagnostic annulus shows the association between image luminance and the
periodic edge mask decreasing from -0.537 to -0.058. That diagnostic describes
the artificial ring pattern; it is not a photographic-quality or field-accuracy
score. Native inspection shows irregular runoff dominating the apron while
shallow normal-based relief remains. The authored radial relief field itself
remains uncalibrated, and human acceptance is separate from these checks.
