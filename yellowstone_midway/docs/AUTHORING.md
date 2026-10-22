# Authoring and architecture

## Ownership of data

| Authority | Files | Change policy |
|---|---|---|
| Original geography | `references/dem.tif`, source GIS JSON, source imagery and provenance | Retain unmodified. Record new acquisitions as new source versions. |
| Geographic adaptation | `tools/prepare_world.py`, `data/world.json`, `data/terrain.f32` | Rebuild deliberately after source/engineering changes; inspect the resulting geometry report. |
| Initial planting arrangement | `data/placements.json` | Fixed transforms and IDs; the compiler retains the file by default. |
| Persistent planting changes | `data/placement_overrides.json` | Remove, replace or add explicit records; independent of the proposal layer. |
| Native hand placements | `scenes/handcrafted_details.tscn` | Edit normally in Godot. The bake does not overwrite it. |
| Botanical detail layer | `data/botanical_placements.json`, `scenes/botanical_details.tscn` when present | Authored genus/guild stand-ins; retain the record IDs and replace visuals independently. |
| Baked visual/collision assets | `scenes/authored_world.tscn`, `assets/meshes/terrain` | Output of the explicit offline bake. Save a copy before directly editing generated geometry. |
| Ecology configuration | `data/ecosystem.json`, `data/species_catalogue.json` | Scenario parameters and research evidence remain distinct. |
| Ecology runtime | `scripts/ecosystem.gd`, `scripts/wildlife_actor.gd` | A shared state drives activity; it does not generate geography. |
| Runtime presentation | `scripts/world.gd`, `player.gd`, `map_view.gd`, shaders | Loads fixed scenes; presents movement, atmosphere, field notes and map. |

The project uses an offline geography compiler, native scene bakers and normal Godot scene loading. `prepare_world.py` transforms and adapts the saved geographic inputs. `bake_world.gd` compiles those fixed data into saved meshes, collision and instances. The separate `bake_botany.gd` compiles the saved botanical detail layer. None of these tools is called by the game.

## Tool commands

Run these commands from `yellowstone_midway` with Godot 4.5.1:

```sh
godot --headless --path . --script tools/bake_botany.gd
godot --path . --script tools/capture_river_views.gd -- --out="$PWD/work/river-views"
godot --headless --path . --script tools/inspect_fauna_glb.gd
godot --fixed-fps 60 --path . --script tools/recolor_goose_texture.gd
godot --headless --fixed-fps 60 --path . --script tools/render_fauna_preview.gd
godot --headless --path . --script tools/validate_atmosphere_canonical.gd
```

The botanical bake runs after terrain changes. Each JSON clump retains its fixed
record ID and creates genus/guild shape proxies. The river capture uses a visible
window and an absolute output directory. GLB inspection reports combined bounds
and mesh/material inventory; previews support orientation review.

The CC-BY mallard recolor creates an illustrative Canada goose palette: green
head, orange bill, and orange feet become black; the gray-brown body becomes
Canada brown; the white ring is retained. The atmosphere validator compares the
package in `yellowstone_atmosphere` with the canonical runtime scripts and
shaders in `yellowstone_midway`.

## Add an object by hand

Open `scenes/handcrafted_details.tscn`. Add a Node3D with the `MidwayAuthoredPlacement` script, assign a stable ID and choose an imported PackedScene in the Asset inspector. Translate, rotate and scale it using normal Godot editing tools. Set its habitat and an author note. Save the scene. The runtime loads it in the same metre coordinate frame as the baked terrain.

For direct native scene editing, open a new scene containing an instance of `authored_world.tscn` and the handcrafted-detail scene. Make the reference world non-editable while composing details. This keeps accidental terrain edits separate from intentional authored additions. The wrapper's preview node is not serialized as a duplicate of its source asset.

## Edit a planting record

Find its stable ID in `placements.json`, using its position or patch location. Add the ID to `remove` to suppress it. For a replacement, supply a complete record in `replace`, keyed by the original ID. For a new draft-layer instance, add a complete record to `add`.

```json
{
  "schema": 1,
  "remove": ["pine_120_125"],
  "replace": {
    "pine_120_126": {
      "id": "pine_120_126",
      "kind": "pine",
      "position": [-160.0, 28.5, 275.0],
      "yaw": 1.2,
      "scale": 0.85,
      "variant": 0
    }
  },
  "add": []
}
```

This example illustrates the schema only; its coordinates and ID are not a recommended planting location. Replacement position y is local elevation, not latitude, and should be checked against the actual adapted terrain. Inspect it at standing height after baking. The `kind` field selects an implemented asset category; a catalog species name alone supplies no model.

## Terrain sampling and seams

The master raster has row zero at the northern edge. Its coordinate mapping is `(x+2048)/4` and `(z+2048)/4`. `height_field.gd` uses the same diagonal as the rendered grid and Godot's heightmap collision. A bilinear interpolator differs from piecewise-linear triangle interpolation on a non-planar cell. Use the shared GDScript sampler for precise contact during play; use explicit supports or terrain fitting when composing close-range assets.

Each tile's HeightMapShape has uniform scale `(4,4,4)`, local center `(128,0,128)` and heights divided by four. The resulting collision vertices coincide with the rendered world-unit vertices. Uniform scaling preserves this contract across backends with differing support for non-uniform x/z physics scaling. [Godot HeightMapShape3D documentation](https://docs.godotengine.org/en/4.5/classes/class_heightmapshape3d.html).

All terrain normals derive from the shared raster, including a neighbor sample across tile borders. The terrain shader also uses the same global local-world x/z coordinates for texture lookup, so the texture does not restart at every tile. The current world has a fixed-resolution surface; it does not mix incompatible terrain LOD tessellations at tile edges.

## Transport joins

Independent sampling and smoothing produced different elevations at shared endpoints in the initial source adaptation. The compiler reconciles these into common nodes and grades short approaches. River fitting enforces downstream-monotone profiles and shared confluence levels. Widths and bridge design are still approximate and need visual review. NPS source accuracy values describe the linework. Authored engineering requires separate validation.

A narrow channel can be numerically connected but buried beneath the terrain triangles. The compiler includes a support-aware terrain cut to keep the channel visible. This is an interim geometric adaptation; a production near-view channel should have an authored bed/bank mesh or a finer local terrain patch with an explicit border contract. Channel width follows mapped or authored geometry; finer meshes address raster-resolution gaps.

## Materials

`terrain.gdshader` combines the licensed macro orthophoto with forest-ground and rock scans and a fixed habitat mask. Its procedural microvariation changes material appearance only. `water.gdshader` adds drifting normal detail to the saved water mesh; the visual ripple is not a fluid solver. `steam.gdshader` provides lightweight drifting cutout vapour. `foliage.gdshader` receives shared wind and anchors deformation near plant bases. `boardwalk.gdshader` creates measured plank repetition on the saved deck surfaces, with derivative filtering for distant seams. `trail.gdshader` combines a mineral-dust tint with the human-created ground texture. The Excelsior outflow uses a shallow-water material and an illustrative slope-dependent foam effect; it is not a resolved multiphase flow model.

The project retains an experimental thermal-apron shader for further material work; it is not a calibrated microbial simulation. The currently visible drainage coloring is largely the georeferenced imagery, with a modest pigment-selective warm color adjustment inside the saved thermal mask. This adjustment has artistic provenance and provides no temperature inversion. Replace it with hand-authored high-resolution material masks and actual microrelief when finishing the thermal core.

Lodgepole detail levels share an authored branch graph with irregular ascending shoots and a tapered leader. Height, DBH and crown-envelope inputs retain their source classes. Crown fullness, branch survival and shoot distributions are authored; local leaf area and biomass are uncalibrated. The bark uses the existing human-made CC0 scan. Grass uses verified creator meshes, and the animal meshes belong to KJR.

Tree LOD selection uses the distance from the main camera to each tree's common half-height center, stored in the instance custom data. Boundaries remain 18, 65 and 180 m. Adjacent levels use complementary screen-space dithering over a half-width of `clamp(0.1 * boundary, 2, 18)` m. This reduces abrupt switches without changing tree count, dimensions or distance limits. Batch bounds include a half-diagonal plus the maximum transition half-width, so batch-center culling cannot remove nearby trees. Shadow rendering uses the main-camera distance. The baked root remains in the georeferenced identity frame.

Cutout mipmaps filter premultiplied RGB in linear light and calibrate alpha against bilinear and trilinear samples. This preserves visible coverage more closely than counting opaque texel centers. The smallest levels still have finite sampling limits, and the mesh-to-impostor silhouette budgets remain separately assessed. No biological precision follows from these rendering controls.

The baker writes full `PackedFloat32Array` MultiMesh buffers and explicit bounds on the CPU. This matters for reproducible headless bakes: the Godot 4.5.1 dummy rendering backend drops individual rendering-server transform setters. `tools/validate_tree_instance_lod.gd -- --baked` validates saved tree buffers, common centers, material ranges and culling padding. Run the same tool on a native renderer without `--baked` for per-instance selection and complementary transition checks. Dummy-backend transform/AABB getters are not a valid verification method.

## Simulation and observation

One ecosystem node owns time, weather signals, river-reach state and patch state. Actors consult this node and return grazing/foraging effects. Model coefficients carry provenance or an explicit illustrative label. Time does not secretly accelerate plant growth during ordinary exploration.

### Replay water levels

`python_river_replay.gd` initializes the displayed water surface from authored
`position_xyz.y`. The per-frame `water_surface_m` contract is
`bed_elevation_m + depth_m`, requiring both components from the publisher. The
authored position supplies a display level when those components are unavailable.

Rendering and transport use different representations of the same landscape. The river mesh follows geographic curves; the reduced thermal solver uses a reach graph. Refine the spatial mapping between those representations as the simulation becomes more detailed. Rendered side channels must correspond to the hydrology graph.

The ordinary scene is observation-only. Walking, a small jump, menus and authoring camera controls are implemented. Swimming, survival, wildlife approach reactions and visitor restrictions are not game mechanics in this release. If those are added, keep them optional or mode-specific and document their scope.

## Performance and expansion

Vegetation groups are spatially split because a MultiMesh is culled as a whole. [Godot MultiMesh guidance](https://docs.godotengine.org/en/4.5/tutorials/performance/using_multimesh.html). The current implementation loads this whole local scene. It is a testable base for streaming; full-park streaming remains unimplemented.

For new regions, retain the UTM authority and use explicit tile metadata. Introduce a generic tile loader only after the local content and frame budgets are understood. Save state by stable actor/patch/feature IDs. A tile unload must not reset thermal state or make a grazed patch new again. Far views should continue to use the actual terrain silhouette.

## Rebuild discipline

Before rebuilding, preserve hand-edited source records and direct scene changes. Run the geography compiler, import assets, then run the offline Godot bake. The documentation lists verification commands. Stop if source metadata are missing or the compiler changes expected scale. Treat validation failures as actionable evidence: a road join, shoreline, collision grid or actor route can be wrong even if the editor opens successfully.

Routine cleanup retains the fixed draft arrangement. The `--placements-replace` option explicitly replaces it. It does not mean the user's reviewed transforms have been retained. Preserve the overrides and handcrafted scene even when intentionally replacing the draft.
