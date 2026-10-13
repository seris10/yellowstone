# fixes-37 ledger
Doc: fixes/fixes-37-shaders.md | read 2026-10-12 | targets: yellowstone_midway/shaders/boardwalk.gdshader sha256:4787c3556206 ; yellowstone_midway/shaders/foliage.gdshader sha256:f5866890d3e5 ; yellowstone_midway/shaders/steam.gdshader sha256:c604fadf723c ; yellowstone_midway/shaders/terrain.gdshader sha256:ddb37e82576f ; yellowstone_midway/shaders/thermal_apron.gdshader sha256:70fd123eb15b ; yellowstone_midway/shaders/trail.gdshader sha256:1437e54a51eb ; yellowstone_midway/shaders/water.gdshader sha256:95b2a2fc68af
Summary: 7 items: 7 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | terrain shader wetness uniform renamed to ground_wetness | implemented | shaders/terrain.gdshader:9 "uniform float ground_wetness = 0.12;" ; tools/bake_world.gd:37 set_shader_parameter("ground_wetness",...) | Also wires terrain tiles into weather_wetness group (see fixes-34 item 2). | cheap |
| 2 | foliage shader MODEL_MATRIX inverse: document and leave | implemented | shaders/foliage.gdshader:14-17 three-line inline note on the per-instance inverse and the baked [0.6, 1.3] scale range | Visual effect NOT TESTED; the risk is documented and left as written. | refactor |
| 3 | steam shader INSTANCE_CUSTOM layout comment | implemented | shaders/steam.gdshader:6 "// INSTANCE_CUSTOM.x is the per-plume phase in [0, 1], written by bake_world.append_instance." | Documents the per-instance payload. | cheap |
| 4 | water shader reads temperature_c in the main (non-cascade) branch | implemented | shaders/water.gdshader:36-39 "Firehole river tint between 7 and 32 degC. Authored, not radiometric." mix | Authored tint; not a radiometric derivation. | medium |
| 5 | Promote STEAM_DENSITY_SCALE to a named constant | implemented | scripts/world.gd:46 const STEAM_DENSITY_SCALE: float = 0.40 and world.gd:570 uses it | Pulls the inline 0.40 out of refresh_env_caches. | cheap |
| 6 | thermal_apron shader surface_map.a comment | implemented | shaders/thermal_apron.gdshader:9 "// surface_map.a is a baked roughness proxy for the mineral band, not a live temperature." | Documents the authored-only path. | cheap |
| 7 | Trail shader edge soften in meters, not UV | implemented | shaders/trail.gdshader:4-7 declare `width_m` and `edge_width_m`; shaders/trail.gdshader:12 computes edge in meters; tools/bake_world.gd:212-215 duplicate gravel_mat per trail and set width_m from `r.width` | Takes effect after the next bake (Godot 4.5.1 per README); baked materials in the current scene still carry the old uniform set, so the shader default `width_m = 2.0` applies to them. Visual NOT TESTED. | medium |

## Cross-project issues
- Item 7: baked trail scenes carry the old gravel_mat; the shader default `width_m = 2.0` applies until the next bake runs on Godot 4.5.1.

## Scientific validity flags
- Item 4's temperature mix is authored. The water color is not a radiometric model.
