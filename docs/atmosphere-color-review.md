# Color filtering and distant-tree lighting

Terrain color textures use precomputed RGBA8 mip chains. The producer
`yellowstone_python/tools/prepare_color_mips.py` decodes sRGB, averages
premultiplied linear RGB and alpha, then encodes RGB back to sRGB. Base pixels
remain byte-identical to the original image. The eight buffers and their source
hashes are listed in `assets/textures/color_mips/color_mips.json` in the Godot
project. Normal, ARM, mask and scientific pigment paths retain their existing
treatment. A packed mineral normal/grain/roughness texture is numerical data;
color conversion or normal renormalization across all four channels is invalid.

Godot 4.5.1 `Image.generate_mipmaps()` averages RGBA8 channel values directly.
A two-black/two-white control produces byte 128, which decodes to linear
0.215861. The correct linear mean is 0.5, encoded as byte 188. The focused
Python tests require 188, transparent-edge premultiplication, complete
rectangular chains, rejected invalid inputs and source-bound production bytes.
`evidence/atmosphere-color-mips.json` records 139 native checks for buffer
layout, byte-preserving loading and actual material bindings.

The eight offline buffers occupy 111,848,096 raw disk bytes. Their dimensions,
RGBA8 GPU representation, mip counts, sampler count and shader sampling cost
match the corresponding runtime-generated color images. Startup reads and
authenticates the buffers; it performs no per-pixel color conversion. Native
whole-world timing and appearance remain separate evidence.

The distant tree impostor path has no duplicate sRGB decode. Blender exports
Standard-view PNGs; the offline cutout producer filters in linear light and
re-encodes; Godot loads the raw encoded bytes and samples with `source_color`.
The native mesh and impostor luminance mismatch remains: the impostor contains
authored Blender lighting and is unshaded, while close geometry receives
runtime ambient/direct lighting, diffuse wrap and backlighting. The fixture's
ambient energy 0.7 and directional energy 1.5 differ from the Blender bake.
The reported approximate 44% luminance ratio therefore does not identify a
second color conversion. Unshaded impostors do not reproduce changing local
illumination, and this limitation remains explicit in endpoint fidelity results.

Godot documents the distinction between color and numerical texture samplers
in [Using source_color](https://docs.godotengine.org/en/4.5/tutorials/shaders/shader_reference/shading_language.html#using-source-color).
The [W3C sRGB conversion equations](https://www.w3.org/TR/css-color-4/#color-conversion-code)
define the transfer function. NVIDIA explains the linear-light filtering
requirement in [The Importance of Being Linear](https://developer.nvidia.com/gpugems/gpugems3/part-iv-image-effects/chapter-24-importance-being-linear).
