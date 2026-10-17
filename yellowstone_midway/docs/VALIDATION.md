# Validation record

Test environment: **Godot 4.5.1 stable, official build f62fdbde1**. CPU-side checks use the headless engine and the actual saved project resources. Rendered previews use Godot's Compatibility renderer through Mesa llvmpipe software OpenGL at **1440 x 900**, with 4x MSAA. The software renderer is suitable for inspecting output; these captures are **not a gaming-GPU performance benchmark**.

## Scope of the verified build

This is a fixed, georeferenced, playable landscape foundation. It loads saved terrain, roads, trails, water and vegetation. Python is not required to play. The original source raster remains unchanged, while the playable raster contains documented road grading, channel support and underwater adaptations.

| Check | Result / evidence |
|---|---|
| Geographic extent and unit convention | 4,096 m x 4,096 m; 1 unit = 1 m; 1,025 samples at 4 m spacing |
| Shared route endpoint elevations | 0 m discrepancy; `tests/data_validation.json` |
| Shared river endpoint elevations | 0 m discrepancy; same report |
| Rendered terrain tile borders | 0 m discrepancy across all 256 tiles; `tests/baked_validation.json` |
| Terrain normals across tile borders | 0 discrepancy; same report |
| HeightMap collision vs. terrain vertices | 0 m discrepancy; same report |
| Water above terrain | 78,083 sampled channel center/quarter/edge points; 0 buried; minimum clearance 0.12 m; `references/channel_support_qa.json` |
| Saved vegetation/steam buffers | 11,494 MultiMeshes, 128,921 instance slots, 2,062,736 finite floats; `tests/multimesh_validation.json` |
| Vegetation coordinates after serialization | Maximum discrepancy about 0.0000153 m relative to the fixed records; no bounds protrusions |
| Initial standing positions | All four saved starting places settle on collision; see smoke command below |
| Ecology | Conservation, state, feeding and aquatic-route checks pass; `tests/ecology_validation.json` |
| Botanical scene | Thirty fixed clumps, 52,128 triangles; per-stem terrain contact and habitat exclusions checked; `tests/botany_bake.json` |

These numerical checks measure implementation consistency. They do not establish the positional accuracy of the source GIS, surveyed dimensions of authored structures, biological calibration or a finished visual-art standard.

### Fixed placements and representation counts

There are **36,225 initial placement records**: 30,862 pines, 4,210 grass tufts, 718 rocks and 435 logs. Each pine has four distance representations. The 128,921 total instance slots therefore do **not** mean that 128,921 separate organisms were placed. The botanical detail scene is separate and contains 6 willow shrubs, 12 sedge clumps and 12 lupine clumps.

The buffer validator decodes the saved CPU arrays, checks every instance transform, compares placement origins with the fixed records, and verifies that transformed source-mesh bounds fit the explicit batch bounds. It avoids the dummy renderer's transform/AABB getters. This test caught the early bake's missing instance buffers before delivery.

## Ecological verification

The reduced heat model was run for one physical hour. Maximum per-substep heat-ledger residual was approximately **2.55e-10 m3*C**, with a water-volume residual of zero. Density and specific heat are omitted consistently from the reported heat ledger; these units are not joules. A separate uniform-temperature case preserved 20 C exactly. A large elapsed-time call matched the equivalent stable substeps.

A 180-second actor run checked the twelve authored wildlife records, expected behavior transitions, route confinement, fish clearance above the bed, forage removal by grazers and insect-resource removal by foragers. These are bounded observational proxies. They are not population dynamics, animal intelligence, a calibrated thermal plume or verified individual wildlife sightings.

## Moving-body verification

`tools/validate_walk.gd` runs the actual player capsule and movement settings against the baked scene. It uses the player's capsule, floor angle, floor snap, safe margin, acceleration and gravity. It uses one initial placement per case, then velocity and `move_and_slide()` through the saved waypoints. The focused cases cover the Midway bridge in both directions, the Fairy Falls bridge in both directions, the upper overlook approach/deck entry, and a boardwalk junction. They check progress, floor contact, corridor confinement and falling below the intended surface.

The first run caught a rail chord cutting a bend, an abrupt bridge exit and a raised deck lip. Those findings drove explicit geometry repairs. The final result and source hashes are in `tests/walking_validation.json`: all six cases pass, covering **415.772 m** over **252.717 simulated seconds**, with **zero airborne intervals**, all finishes on the floor, and maximum cross-track deviation **0.240 m**. Both Midway bridge directions have zero wall contacts. The initial diagnostic report is retained separately as historical evidence and is not the current acceptance result.

The walking tests cover these selected transitions. They do not claim that every metre of every mapped route has been walked or that all off-trail travel is free of obstructions.

## Visual review

The project includes real in-engine captures from the overlook, boardwalk, Firehole bridge and Fairy Falls approach. Reviews checked visible terrain borders, material exposure, plant instance visibility, cutout foliage, bridge/overlook geometry, native trail color and distant plank seams. Corrections included explicit MultiMesh buffers, reduced clipping, real timber rail members, filtered plank gaps, a native-trail material and separate shallow outflow settings. A final close view removed overly regular foam bands in favor of faint ripple-driven breakup.

No generated concept image is used as evidence of the engine's output. The reference map is a geospatial visualization of the supplied sources.

### Material limitations still visible

- The four-metre terrain cannot resolve close bank cross-sections or thermal crust details. Wide support cuts keep narrow water ribbons exposed but produce angular, over-simple banks in some close views. Replacing these with reviewed local meshes is a priority.
- The aerial macrocolor contains canopy and shadow imprints. It is not a reconstructed ground albedo underneath the added trees.
- The pine is one generic creator-made form with reduced detail levels and scale/orientation variations. It is not a reviewed set of native lodgepole growth forms.
- Animal and botanical meshes are original development stand-ins. The species catalog records broader research diversity; model completion requires separate asset evidence.
- Water stages, underwater floors, bridges, road widths and the representative Excelsior branch include authored approximations.
- Trunk collision is concentrated around the central walking region. Peripheral tree instances, rocks, logs and ecological stand-ins do not yet have a complete streamed collision system; terrain and the saved transport surfaces do have collision across the domain.
- The current local scene loads in full. GPU frame times, memory budgets, console/mobile operation, full-park streaming and long-duration play are unverified.

## Reproduce the checks

Run from the project directory with a Godot 4.5.1 executable named `godot` or substitute its absolute path:

```sh
python tools/validate_world.py
godot --headless --path . --script tools/validate_baked.gd
godot --headless --path . --script tools/validate_multimesh.gd
godot --headless --path . --script tools/validate_ecology.gd
godot --headless --path . --fixed-fps 60 --script tools/validate_walk.gd
godot --headless --path . -- --smoke-test
```

The report JSON files contain the applicable metrics, failures and available source hashes. A passing report corresponds to the recorded inputs; rerun it after editing those inputs. `--smoke-test` prints whether the character is on the floor at each starting place and exits.

For fresh screenshots, run on a desktop with a working graphics driver:

```sh
godot --path . -- --capture-all
```

This writes four `docs/preview_*.png` images and exits. Regular play is simply F5 in the editor.
