# fixes-39: rendering gaps (Python simulates, Godot does not draw)

Scope: for each component with `status` other than `rendered` in `dashboard/data/inventory-godot.json` sha256:(see inventory-godot `generated_from`), and for each cross-domain output flagged `python_only` or `partial_unwired` in `dashboard/data/inventory-python.json` and in `fixes-33` section "Wiring and rendering", state what Godot should draw, from which published Python field, and the cost.
Callers read: `yellowstone_midway/scripts/world.gd` sha256:b0593a402d4f ; `yellowstone_midway/scripts/ecosystem.gd` sha256:18e1dec0bdbb ; `yellowstone_midway/scripts/python_river_replay.gd` sha256:b98fd984882f ; `yellowstone_midway/shaders/water.gdshader` sha256:b8e096e8d1f7 ; `yellowstone_midway/shaders/terrain.gdshader` sha256:ddb37e82576f ; `yellowstone_midway/data/firehole_pulse.json` sha256:185ccb3d6486 ; `yellowstone_midway/data/season.json` sha256:b44e16d1cdde ; `yellowstone_midway/data/pool_shells.json` sha256:043c84e36b45.
Related documents: fixes-33 (cross-domain wiring, Python side), fixes-14 series (atmosphere), fixes-34 (world and environment), fixes-37 (shaders), fixes-38 (tools and validators).

Terminology: "visible" means a user walking the main scene can see the field change; "study-visible" means visible only in `scenes/study.tscn` with a replay. "Pycl handoff" means Python must publish a new field before Godot can draw it; the item lists the field.

## Main problems

### 1. Water shader ignores reach temperature outside the cascade branch
`water.gdshader:3-50` declares `uniform float temperature_c` and `world.gd:482-488` writes it per Firehole river MeshInstance each frame, but the main (non-cascade) fragment branch at lines 32-38 derives color only from `shallow_color`, `deep_color` and `COLOR.r`. The uniform is unused on the river surfaces that are not tagged `cascade`.
### Fix
Mix in a temperature-driven warming between the authored shallow/deep look at 7 degC and a warmer riverine tint at 32 degC, inside the non-pool, non-cascade branch:
```glsl
float warmth = clamp((temperature_c - 7.0) / 25.0, 0.0, 1.0);
color = mix(color, mix(color, vec3(0.33, 0.37, 0.26), 0.25), warmth);
```
No pycl handoff: `ecosystem.reach_at(sample_z).temperature_c` already drives the uniform in both live and replay modes. The static authored shallow/deep still dominates; the temperature mix only tints the warmer reaches. Primary source: Yellowstone water temperature narratives at National Park Service, Thermal Features of the Firehole River, 2023. The color choice is an authored artistic value, not a radiometric measurement.
### Draw from
`ecosystem.reach_at(sample_z).temperature_c` (lives), `_at_s(s_m).temperature_c` (replay).
### Cost
Cheap (one shader mix in the main branch).

### 2. Pool water temperature is set once at bake and never updated
`tools/bake_world.gd:456` sets the pool shader's `temperature_c` uniform at bake time from `data/world.json pools[].temperature_c`. The runtime never updates it. For pools whose temperature is modeled or measured, a diurnal or weather-driven change is lost. `pool_shells.json` publishes `t_center_c` and `t_edge_c` per pool (static authored). No per-step pool temperature is published.
### Fix
Two-step. First, read `pool_shells.json` `t_center_c` at `_ready` and write it into each pool's water material under the pool's `metadata/feature_name`, so pool temperature at least reads from the published shell data rather than from `world.json` alone. Pycl handoff for live updates: publish a per-step `pools_state.json` with `[{id, temperature_c_center, temperature_c_edge, timestamp_s}]`, written from the same thermal pool model that drives steam density. Godot then updates the pool shader per frame as it already does for the river.
### Draw from
Phase 1: `pool_shells.json pool_shells[].t_center_c` (surgical, static reinforcement).
Phase 2 (pycl handoff): per-step pool thermal state (new).
### Cost
Phase 1 cheap. Phase 2 medium on the Python side; cheap on Godot.

### 3. Per-reach river flow over time never updates the water shader
`ecosystem.gd:116-134` accumulates lateral sources into `r.flow_m3s` and `tools/bake_world.gd:384-408` sets each river's `flow_speed` shader parameter from the authored `r.flow_mps`. The runtime `flow_m3s` is used only for the HUD and the info panel; river shader animation speed never responds. For a scientific-grade simulation the visible river current should track flow at least qualitatively.
### Fix
In `world.gd.refresh_env_caches` loop, additionally compute `flow_speed = clamp(reach.flow_m3s / baseline_m3s, 0.5, 2.0) * baseline_flow_speed` and set the uniform. `baseline_flow_speed` is the authored value already saved to the material at bake. The clamp bounds the aliasing in the ripple animation.
### Draw from
`ecosystem.reach_at(sample_z).flow_m3s` plus the authored `flow_speed` material default. No pycl handoff.
### Cost
Cheap.

### 4. Snow cover fraction uses only the max patch depth and ignores SWE
`world.gd.apply_season` reads `data/season.json patches[].snow_depth_m`, takes the maximum, scales by 0.3 m and writes `snow_amount` to all terrain materials. The season JSON also publishes per-patch `snow_mm` (SWE). A single global `snow_amount` means a patch that is bare while others are covered looks the same on-screen; and SWE is the glaciological quantity, depth is a derived density-dependent surrogate.
### Fix
Two-step. Phase 1: expose `snow_amount` from mean of `snow_depth_m` instead of max, and additionally expose `snow_mm` as `snow_swe_mm` on the terrain material for use by future shaders. Phase 2 (pycl handoff): publish a per-patch `snow_cover_fraction` in [0, 1] from the snow model (fractional cover of the patch, not depth), and have `terrain.gdshader` sample a per-patch coverage texture or the biome map's blue channel to blend coverage spatially rather than uniformly.
### Draw from
Phase 1: `data/season.json patches[].snow_depth_m` (mean), `patches[].snow_mm`.
Phase 2 (pycl handoff): `patches[].snow_cover_fraction` and a per-patch mask texture `snow_patch_mask.png` keyed by `biome_map.b`.
### Cost
Phase 1 cheap. Phase 2 medium (requires a baked per-patch mask).

### 5. Ground wetness never reaches the terrain shader
See fixes-37 item 1 and fixes-34 item 2. The uniform in `terrain.gdshader` was named `wetness` while the atmosphere controller writes `ground_wetness`. The owning mesh instances were not in the `weather_wetness` group that the controller scans.
### Fix
Rename the shader uniform to `ground_wetness`, add owning `MeshInstance3D` nodes to the `weather_wetness` group in `world._ready`, and call `atmosphere_controller.refresh_wetness_material_cache()` after `collect_terrain_materials`. No pycl handoff.
### Draw from
`weather_snapshot_reader` -> atmosphere controller `ground_wetness_fraction`. Current snapshot producer writes it (fixes-14 ledger).
### Cost
Cheap (name alignment and group add).

### 6. Cloud shadows do not darken the terrain
Atmosphere controller renders a procedural cloud shell (`yellowstone_cloud_shell.gdshader`) above the player; this shell is unshaded and casts no shadows. On an overcast reading from the snapshot, the ground remains fully sunlit.
### Fix
Not surgical. The cloud shell is intentionally unshaded for the Compatibility renderer (`yellowstone_atmosphere/README.md`). Phase 1 (cheap): dim `DirectionalLight3D.light_energy` by `clampf(1.0 - cloud_fraction * 0.4, 0.4, 1.0)` as a flat ambient attenuation driven by the weather state. Phase 2 (medium): add a slow-moving cloud-shadow mask texture to `terrain.gdshader` driven by UV scrolled with `wind` and attenuated by `cloud_fraction`. The mask is a baked tileable gray noise, not a projection of the cloud shell geometry.
### Draw from
`atmosphere_controller.get_render_state().weather.cloud_fraction` (already published).
### Cost
Phase 1 cheap. Phase 2 medium (asset addition and shader change).

### 7. Plume field is drawn to a PNG the game never ships
fixes-33 item 6: `build.py:674` calls `plume_field(...)` and `publish.py:28` does not ship `plume_map.png`. The 2-D plume is not available to Godot.
### Fix (pycl handoff)
Publish the plume field as data, not as a bitmap: `plume_field.json` with `{axes_x_m, axes_z_m, origin_xz, temperature_grid_c, hot_source_c, river_c, status: "illustrative"}`. Godot then builds a `MeshInstance3D` with a quad over the plume footprint and a shader that samples a `ImageTexture` created from `temperature_grid_c` with a hot-to-cool ramp.
### Draw from
`plume_field.json temperature_grid_c` (new, pycl handoff per fixes-33 item 6).
### Cost
Cheap on Godot once the file lands.

### 8. Geochemistry bands beyond the pool ramp are not surfaced
`geochemistry.py` publishes silica saturation index and other bands only to the analysis store; `publish.py` does not ship a geochemistry sidecar. The pool ramp textures are a bake-time derivative. No live geochemistry overlay exists.
### Fix (pycl handoff plus Godot overlay)
Phase 1: `build.py` writes `geochemistry.json` with per-cell SI, pH, and temperature along the river's main chain, keyed by `firehole_cell_<nnnnn>` (per fixes-33 item 5). Phase 2: add a Godot `GeochemistryOverlay` script that reads the sidecar at `_ready`, color-codes markers along the river surface at authored anchor points, and toggles with key G. No change to pool ramp textures.
### Draw from
`geochemistry.json cells[].silica_saturation_index` (pycl handoff).
### Cost
Medium on both sides.

### 9. Insect and bird catalog data is loaded but not drawn
`insect_bird.json` publishes compartment totals (`Nb`, `Ne`, `Nt`), consumption shares (dipper, raven, trout), and activity. The data reaches no Godot reader (inventory-godot `insects` is rendered as actor count only; HUD shows one bank-insect activity number).
### Fix
Add a `BiologicalLedger` panel in the info panel: on `I` press, read `insect_bird.json` once at `_ready`, show a block with current activity, emergence rate, and consumption share per predator. For bird state (dipper/raven), surface the same consumption share next to the bird actor count. No visualization change to the sim; this surfaces published data to the HUD.
### Draw from
`insect_bird.json compartments.final.Nb/Ne/Nt`, `compartments.consumed_total`, `activity`.
### Cost
Cheap.

### 10. Census overlay has no renderer
Inventory status `not_started`. `census.json` published per fixes-26 covers tree crowns and DBH per polygon. Godot renders trees from `placements.json` only; census is not drawn.
### Fix
Add a `CensusOverlay` script that reads `census.json` at `_ready`, draws a flat overlay (map or world) with crown polygons color-coded by DBH quartile, and toggles with key U. The in-world overlay uses a semi-transparent quad with vertex colors; the map variant renders in `map_view.gd`.
### Draw from
`census.json trees[].polygon_xz`, `trees[].dbh_cm`.
### Cost
Medium. Requires `census.json` to be shipped by `publish.py` (pycl handoff per fixes-26 and fixes-33 item 10).

### 11. Study-mode toggle is missing from main scene
`world.gd:394` binds KEY_C to `toggle_replay`, which does nothing when `replay_path_alt` is empty. `main.tscn` leaves `replay_path` empty, so KEY_C has no effect in the live world. A player who sees `study.tscn` features (thermal probes, Python replays) has no in-world path to them from main.
### Fix
Add KEY_S handler in `_unhandled_input` that reloads the scene with `study.tscn`:
```gdscript
KEY_S:
    if Input.is_physical_key_pressed(KEY_CTRL):
        get_tree().change_scene_to_file("res://scenes/study.tscn")
```
Document the KEY_S binding in the help label. The toggle writes a boot-time scene change, not a runtime graft, so the author-time study scene remains the one that owns `thermal_probe_overlay`.
### Draw from
Existing: `scenes/study.tscn`, `data/firehole_pulse.json`, `data/firehole_control.json`.
### Cost
Cheap.

### 12. Fetchers and calibration diagnostics have no in-game surface
Inventory status `not_started`. `fetchers_calibration` covers USGS gauge pulls and the reach heat fit. The Firehole gauge trace is not shown anywhere in the game.
### Fix (pycl handoff plus Godot overlay)
Phase 1 pycl: `publish.py` ships `calibration_summary.json` with `{reach_fit: {k, se, r2}, gauge_trace: [{t_s, discharge_m3s, temp_c}]}` extracted from the analysis store. Phase 2 Godot: a `CalibrationPanel` under `info_panel` on key K draws the time series as a line chart (no new library; `_draw` on a Control).
### Draw from
`calibration_summary.json` (pycl handoff).
### Cost
Medium.

### 13. Groundwater and overland fields have no renderer
Inventory status `not_started`. fixes-33 item 1 (overland) and item 2 (groundwater) treat the physical wiring. On the Godot side, even once the fields are produced, no surface shows them.
### Fix (deferred)
Not surgical this pass. When fixes-33 item 1 lands and overland produces a per-cell depth field in `overland_flow.json`, the terrain shader can mix a transient wet-sheen color based on cell depth, like the ground wetness path. Not implemented here; parked after the physics is correct.
### Draw from
Deferred.
### Cost
Deferred.

# Wiring and rendering

Items 1, 3, 4 (phase 1), 5, 6 (phase 1), 11 draw data that Python already publishes and can be implemented in this pass. Items 2 (phase 1) and 9 draw static authored data already on disk. Items 2 (phase 2), 7, 8, 10, 12 require Python-side publishes first and are pycl handoffs below. Item 13 is deferred until fixes-33 items 1 and 2 land.

# Pycl handoffs (new publishes requested)

- `pools_state.json` per-step pool thermal state: `{id, temperature_c_center, temperature_c_edge, timestamp_s}` (fixes-39 item 2 phase 2).
- `patches[].snow_cover_fraction` in `season.json` plus `snow_patch_mask.png` baked once (fixes-39 item 4 phase 2).
- `plume_field.json` for the 2-D plume (fixes-39 item 7, see fixes-33 item 6).
- `geochemistry.json` with per-cell SI, pH and temperature (fixes-39 item 8, see fixes-33 item 5).
- `calibration_summary.json` extracted from the analysis store (fixes-39 item 12).
- Per-frame per-cell `q_cells_m3s` in the mapped river replay (also requested by fixes-35 item 4 and fixes-36 item 6).

# Comment-style violations

None added. New GDScript added by this document carries one-line comments only.

# Priority order

1. Item 1 (water temperature in main branch) - cheap, visible.
2. Item 5 (ground wetness name and group) - cheap, visible; see fixes-34/37.
3. Item 3 (river flow speed per reach at runtime) - cheap, visible.
4. Item 11 (study-mode toggle in main) - cheap.
5. Item 9 (insect/bird data in HUD) - cheap.
6. Item 2 phase 1 (pool temperature from pool_shells) - cheap.
7. Item 4 phase 1 (snow mean/SWE expose) - cheap.
8. Item 6 phase 1 (cloud attenuates sun energy) - cheap.
9. Item 7 (plume field) - medium, pycl handoff first.
10. Item 10 (census overlay) - medium, pycl handoff first.
11. Item 8 (geochemistry overlay) - medium, pycl handoff first.
12. Item 12 (calibration panel) - medium, pycl handoff first.
13. Item 2 phase 2, item 4 phase 2, item 6 phase 2 - medium, pycl handoff first.
14. Item 13 (overland/groundwater renderer) - deferred until physics lands.
