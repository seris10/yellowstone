# fixes-14.4 ledger
Doc: fixes/fixes-14.4-yellowstone_cloud_shell.gdshader | read 2026-10-12, open rows re-verified 2026-10-13 | targets: yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader ; yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd ; yellowstone_midway/shaders/yellowstone_cloud_shell.gdshader ; yellowstone_midway/scripts/yellowstone_atmosphere.gd
Summary: 10 items: 10 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

The doc is a proposed replacement shader; it bundles a drop-in file, a controller-change list and a scale-min note. Items are the intro bullet list, then the controller/scale sub-items.

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | Fix inside-sphere culling (not cull_back) | implemented | yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader:8 | `render_mode blend_mix, depth_draw_never, cull_front, unshaded` | cheap |
| 2 | Vertical cloud base/top density falloff | implemented | yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader:17-19,58-63,83-95,114 | cloud_base_agl_m / cloud_top_agl_m uniforms, vertical_layer_density, applied to body | cheap |
| 3 | Multi-scale cloud structure | implemented | yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader:65-76 | three fbm scales mixed by cloud_detail | cheap |
| 4 | Separate coverage and density behavior | implemented | yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader:10-12,100-114,155-158 | cloud_cover drives threshold, cloud_density/cloud_opacity multiply alpha | cheap |
| 5 | Cloud self-shadowing approximation | implemented | yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader:116-132 | offset fbm sample feeds self_shadow curve into luminance | cheap |
| 6 | Weather-responsive silver lining | implemented | yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader:121-131 | silver_lining = smoothstep(0.50, 0.95, view_light) * sun_up | cheap |
| 7 | Stable world-space noise while shell follows player | implemented | yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader:78-98 ; yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:504-511 | world_pos.xz * cloud_scale + cloud_offset, _cloud_offset advanced by wind | cheap |
| 8 | Day/night and sun-direction response | implemented | yellowstone_atmosphere/shaders/yellowstone_cloud_shell.gdshader:121-147 | sun_vector.y gates daylight tint, sun_tint mixes into lit color | cheap |
| 9 | Controller-side uniforms (cloud_density, cloud_base_agl_m, cloud_top_agl_m, cloud_vertical_edge_softness) in both _create_cloud_shell and _update_atmosphere | implemented | yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd:402-411,514-520 | both the setup block and the per-tick block push the four uniforms | cheap |
| 10 | Shell scale uses `maxf(cloud_thickness, 100.0)` minimum | implemented | yellowstone_midway/scripts/yellowstone_atmosphere.gd:_update_atmosphere ; yellowstone_midway/scripts/yellowstone_atmosphere.gd:_create_cloud_shell | cloud_thickness clamped by `maxf(..., 100.0)` and scale.y = thickness * 0.5 so the shell spans a 100 m total vertical range at the floor, which is the doc's `safe_thickness` intent; the shell mesh is now a CylinderMesh so this height applies across the full radius | cheap |

## Cross-project issues
- yellowstone_midway/shaders/ does not include yellowstone_cloud_shell.gdshader, and yellowstone_midway/scripts/world.gd never loads the atmosphere controller, so the shader is only reachable from the standalone yellowstone_atmosphere scripts tree.
- Shader's `cull_front` fallback note (doc "If cull_front does not render correctly") never had a Compatibility smoke run captured anywhere under yellowstone_atmosphere or yellowstone_midway/tests, so the recommended smoke checks are only paper evidence.
- The shader expects controller to send `sun_tint` as a vec3 (yellowstone_atmosphere.gd:522) built from `_sun.light_color`, which is affected by `cloud_fraction` dimming earlier in _update_environment_from_weather (yellowstone_atmosphere.gd:581); the "lit cloud" tint therefore darkens with coverage before the shader applies coverage again.

## Scientific validity flags
- `cloud_density : hint_range(0.0, 2.0)` is unitless and multiplies alpha; a shader "density" that can double alpha has no physical cloud-optical-depth meaning.
- `vertical_layer_density` applies a symmetric smoothstep (base and top fade with the same softness); real stratiform cloud layers have an anvil-top asymmetry that this does not model.
- Self-shadow mix `mix(0.68, 1.08, ...)` can lift luminance above 1.0 before the `clamp(luminance, 0.0, 1.0)` on line 152 clips it, so the shader shows a hard-shaded ceiling instead of highlighting bright edges in overcast conditions.
