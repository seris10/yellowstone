# Cutout texture filtering

The offline lodgepole exporter preserves the source RGBA image at mip level zero.
Lower levels average RGB in linear sRGB with premultiplied alpha, then unpremultiply
and encode back to sRGB. This avoids dark color fringes and gamma-space averaging.
The source photographs, authored needle images, geometry and tree counts remain
independent of this filtering operation.

Alpha calibration evaluates the same bilinear operation as the texture sampler.
A fixed, stratified set of 36,864 UV positions estimates the source coverage at
the runtime cutoff of 0.32. Each lower level searches a scalar alpha adjustment
with 22 bisection steps. The objective includes bilinear samples and trilinear
blends with the preceding level at fractions 0.25, 0.5 and 0.75, including the
actual RGBA8 quantization. Runtime samplers use clamp-to-edge addressing.

This extends the alpha-coverage scaling method described by
[Ignacio Castano](https://www.ludicon.com/castano/blog/articles/computing-alpha-mipmaps/).
Texel-center occupancy alone can be misleading: an earlier needle mip had 18.75%
of texels above the cutoff but only 11.57% bilinear UV coverage. Filtering between
levels could reduce it further. The current checks use an independent SciPy
bilinear sampler with held-out UV positions and preserve the original source bytes.

Very small mips have insufficient spatial information to reproduce every coverage
fraction. In particular, one alpha-tested texel can only produce zero or complete
texture coverage. A nonempty source therefore receives a conservatively opaque
terminal texel, explicitly identified in metadata. This avoids complete foliage
loss; it is not a claim of exact subpixel coverage. Empty source images remain
transparent at every level.

The calibration adds offline work and no runtime texture samples, geometry, draw
calls or texture memory. Native LOD transition captures remain necessary because
projected card size, occlusion, anisotropy and geometry changes are outside this
texture-domain test. Raw failing silhouette tests remain failures; improving alpha
coverage does not establish geometric or botanical acceptance.
