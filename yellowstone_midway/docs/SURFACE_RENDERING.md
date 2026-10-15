# Canopy support and surface detail

Residual LiDAR coverage describes canopy area and elevation. It does not enumerate
stems. The display keeps the same residual mask and source-cell elevations. Metric
shoot cards connect through tapered woody triangles to a compact display spine.
The spine joins a nearby rendered bole, sampled along its transformed centerline.
Connections use an eight meter search radius and height eligibility. Patches without
an eligible host use a support extending to the matched ground elevation. Five
shoots in the supported atlas share a visible base. Support dimensions and branching are authored geometry with unknown local
uncertainty. Display-cell counts are not observed tree counts.

Near and middle canopy representations retain 64 and 16 crossed shoot cards per
source cell. Their respective budgets are 328 and 88 triangles, including supports.
The far proxy contains 14 triangles. Existing 45, 120, and 350 meter boundaries and
the 180 to 260 meter transition into the continuous measured-coverage skin remain.
Display patch depth is capped at two meters: an observed surface cell does not
specify a full tree crown. Near foliage samples the measured mask at each complete
shoot center, avoiding severed atlas stems at mask boundaries. Its maximum lateral
display support is 0.20 meters. Far coverage retains per-fragment source masking.
Authored wood spans connect through the masks without fragment clipping.
Coverage-preserving mipmaps retain alpha-test occupancy as needles become subpixel.

## Ground and basin

Forest litter and trail PBR maps retain their source physical widths of 3.15 and
2 meters. The mineral display uses a deterministic periodic height field on a
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

The optical display follows the three terms in
[Nugent et al. (2015)](https://www.montana.edu/jshaw/documents/YNP%20pool%20colors%20-%20Nugent%20et%20al%20-%20AO2015.pdf):
surface-reflected sky, bottom-reflected sunlight, and backward-scattered sunlight.
For each representative wavelength, k=2a+b and the column contribution is
(b/2)(1-exp(-k*z))/k. Surface transmission applies on both passes. Scattering is
zero when b is zero. The authored class palette is decoded from sRGB before
transport. Ramp RGB samples contain linear light; PNG textures receive one sRGB
encoding and the shader's source-color sampler performs its inverse.
Absorption values come from Pope and Fry (1997). Scattering, palette colors,
depth profiles, and surface reflectance remain authored approximations with unknown
local uncertainty. This display has no site spectroradiometric calibration.

Clear visibility maps to zero additional sky fog; the physical sky already models
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
and eight directions against the separate-material renderer.

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
