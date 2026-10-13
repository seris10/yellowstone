# fixes-37: shaders
Scope: yellowstone_midway/shaders/boardwalk.gdshader sha256:4787c3556206 ; yellowstone_midway/shaders/foliage.gdshader sha256:f5866890d3e5 ; yellowstone_midway/shaders/steam.gdshader sha256:ef887b897f9c ; yellowstone_midway/shaders/terrain.gdshader sha256:224d77e4d9e3 ; yellowstone_midway/shaders/thermal_apron.gdshader sha256:1e6d71019c0e ; yellowstone_midway/shaders/trail.gdshader sha256:1437e54a51eb ; yellowstone_midway/shaders/water.gdshader sha256:b8e096e8d1f7
Callers read: yellowstone_midway/scripts/world.gd ; yellowstone_midway/scripts/ecosystem.gd ; yellowstone_midway/scripts/yellowstone_atmosphere.gd ; yellowstone_midway/tools/bake_world.gd ; yellowstone_midway/tools/bake_botany.gd

## Main problems

### 1. terrain shader wetness uniform does not match the controller contract
terrain.gdshader:9 declares `uniform float wetness = 0.12`. The atmosphere controller writes `ground_wetness` only when the shader exposes that exact name (yellowstone_atmosphere.gd:583-589). The two names never meet, so a hydrology-sourced wetness never reaches the terrain look even if a mesh were in the `weather_wetness` group (see fixes-34 item 2).
### Fix
Rename `wetness` to `ground_wetness` in terrain.gdshader and update bake_world.gd:37 to call `terrain_mat.set_shader_parameter("ground_wetness", .12)`. The saved `.tres` material carries the old key; it is dropped silently when the uniform is renamed and takes the new default on next read. A rebake is not required for Compatibility runtime because `set_shader_parameter` at bake time sets the ShaderMaterial parameter, not the shader source.
### Test
`validate_baked.gd` or a scene-smoke: call `atmosphere_controller.set_weather_state({"ground_wetness_fraction": 0.6})` then assert the terrain `ground_wetness` uniform reads `0.6`.

### 2. foliage shader inverts MODEL_MATRIX per fragment-adjacent vertex call
foliage.gdshader:11-15. `inverse(mat3(MODEL_MATRIX)) * vec3(bend*wind_vector.x,0.0,bend*wind_vector.y)` applies the model-matrix inverse to a world-space wind offset so the added vertex offset is in local space. For non-uniform MultiMesh instance scales, `inverse(mat3(...))` can become numerically unstable at near-zero scales. A GPU uniformly-scaled instance costs only one inverse, but bake_botany emits per-species scale ranges (0.6-1.3), so the inverse differs per instance.
### Fix
Document the risk inline and leave the current form, since none of the baked scales approach zero. A robust refactor passes the instance basis as INSTANCE_CUSTOM.
### Test
Visually NOT TESTED (no windowed Godot per this helper). Mark as a watch item.

### 3. steam shader uses INSTANCE_CUSTOM.x without declaring the layout
steam.gdshader:7 reads `phase = INSTANCE_CUSTOM.x`. bake_world.gd `append_instance(buffer, xf, extra)` appends `extra.r/g/b/a` as the custom color per instance (bake_world.gd:62-66). The convention: `extra.r` is the per-steam-plume phase in [0, 1]. This is undocumented in bake_world.gd and in the shader.
### Fix
Add a one-line comment at steam.gdshader:7:
```glsl
// INSTANCE_CUSTOM.x is the per-plume phase in [0, 1], written by bake_world.append_instance.
```
### Test
`validate_multimesh.gd` already enforces the buffer layout. Keep.

### 4. water shader hardcodes shallow/deep colors and reads temperature but discards it
water.gdshader:3-4,9. `shallow_color` and `deep_color` are uniforms, but the shader never reads `temperature_c` after line 9 except through the `cascade > 0.5` branch (lines 41-50), which uses a fixed hot/cool pair. Water color is therefore independent of temperature outside cascades. For a scientific-grade sim this is a visible gap: the Firehole temperature range (ecosystem.gd clamps to [7.0, 62.0]) is a key value and should modulate color.
### Fix
Add a temperature mix in the main branch:
```glsl
// Firehole color modulated by temperature between 7 degC and 32 degC.
float warmth = clamp((temperature_c - 7.0) / 25.0, 0.0, 1.0);
color = mix(color, mix(color, vec3(0.33, 0.37, 0.26), 0.25), warmth);
```
Primary source: NPS 2023 Yellowstone water temperature narratives; the color choice remains an authored artistic value, not a radiometric measurement.
### Test
Scene-smoke: set reach temperature to 32 degC via `ecosystem.reach_at(z).temperature_c`, verify the river material receives it (world.gd:426).

### 5. steam shader density default 0.30 and ecosystem.condensation_visibility scale differ
steam.gdshader:4 `uniform float density = 0.30`. world.gd:417-419 sets `density = ecosystem.condensation_visibility(surface_c) * .40`. The 0.40 constant has no source. ecosystem.gd:272 says "renderer scales it (see STEAM_DENSITY_SCALE)" but no such constant exists; the 0.40 is inline.
### Fix
Promote the inline constant to a world.gd const `STEAM_DENSITY_SCALE := 0.40`, cite it from the ecosystem.gd comment, and reference the number in a one-line note.
### Test
None; constant rename.

### 6. thermal_apron shader never reads surface temperature
thermal_apron.gdshader uses `surface_map` and `mineral_texture` only. The baked `surface_map.a` acts as a roughness ramp (lines 10-11). For the educational sim, the apron should respond to the Firehole runoff temperature or at least to a baked temperature band encoded in `surface_map.a`.
### Fix
Document the current authored-only path with a comment: `// surface_map.a is a baked roughness proxy for the mineral band; not a live temperature.`
### Test
None.

### 7. trail shader edge soften is UV-local
trail.gdshader:5. `float edge = min(UV.x, 1.0 - UV.x)` makes the trail darker toward the edge, but a trail that is 3 m wide in world units has the same visual blend as one that is 30 cm. Width should be in meters so the edge width stays consistent on narrow switchbacks.
### Fix
Pass a `uniform float width_m` and compute `edge = min(UV.x, 1.0 - UV.x) * width_m` normalized by a target `edge_width_m = 0.12`. Update bake_world.gd to feed the width when building the trail ribbon.
### Test
Visual NOT TESTED. Note as watch.

# Wiring and rendering
- terrain.gdshader is created at bake time, saved to `assets/materials/terrain.tres`. Only wetness and snow uniforms are dynamic; season.json drives snow in world.apply_season.
- foliage.gdshader is used by bake_botany and by baked flora MultiMeshes; world.update_environment writes `wind_vector` to its material each frame.
- steam.gdshader is driven by world.refresh_env_caches / world.update_environment (world.gd:410-419) with `wind` and `density`.
- water.gdshader is driven by world.update_environment per river surface (world.gd:420-426) with only `temperature_c`.
- boardwalk, thermal_apron, trail: static authored look, no runtime updates.
- yellowstone_cloud_shell.gdshader is driven by the atmosphere controller; see fixes-14.4.

# Comment-style violations
Shader comments are inline `//` or block `/* */`. Where a comment violates the style:
| file:line | text | rule |
| yellowstone_midway/shaders/boardwalk.gdshader:9 | `// Below one pixel, use area-averaged seam/color.` | passable |
| yellowstone_midway/shaders/boardwalk.gdshader:14 | `// Weathered-gray composite decking, dark timber rails on bark_mat. Seams read as narrow shadow gaps.` | borderline, two sentences on one line |
| yellowstone_midway/shaders/foliage.gdshader:14 | `// Wind is east/south in world space.` | passable |
| yellowstone_midway/shaders/steam.gdshader:11 | `// Camera-facing vapor cards advect in the shared world wind. Rotating the card must not rotate its wind direction.` | hypothetical-failure ("must not") |
| yellowstone_midway/shaders/terrain.gdshader:10-11 | `// Optional snow overlay (season.json + snow_map.png). snow_amount 0 uses the default look; mask is world-extent with bare thermal holes.` | multi-line; borderline |
| yellowstone_midway/shaders/terrain.gdshader:14 | `// Foot-trail tread painted from mapped polylines (2 m/px). Dirt trails are ground here.` | borderline |
| yellowstone_midway/shaders/terrain.gdshader:40 | `// Art direction of the photographed mat colors.` | passable |
| yellowstone_midway/shaders/water.gdshader:12-13 | `// Optional per-pool authored pigment ramp (pool_shells.json + pool_ramps/). ramp_mix 0 uses the default two-color look. Ramp x=0 is hot center, x=1 outer rim.` | multi-line |
| yellowstone_midway/shaders/water.gdshader:25 | `// Pools use slow local wind ripples.` | passable |
| yellowstone_midway/shaders/water.gdshader:42 | `// Thermal outflow ribbon: tinted COLOR.r runs 1 at source to 0 at mouth.` | borderline |
| yellowstone_midway/shaders/trail.gdshader:4 | `// Saved ribbon UV.y is meters. The tread sits 3 cm proud of the ground.` | borderline |

# Priority order
1. item 1 (wetness uniform rename) - cheap
2. item 3 (steam INSTANCE_CUSTOM comment) - cheap
3. item 5 (STEAM_DENSITY_SCALE constant) - cheap
4. item 4 (water temperature color) - medium
5. item 6 (thermal_apron comment) - cheap
6. item 7 (trail edge in meters) - medium; depends on bake_world
7. item 2 (foliage inverse MODEL_MATRIX) - refactor; depends on INSTANCE_CUSTOM budget
