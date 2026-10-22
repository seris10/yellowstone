# 05. Sources and design notes

## Inspected repository baseline

`seris10/yellowstone`, commit `c2b4c7923a6eeed61e2feca3946555826849ec67`.
The GitHub connector reconfirmed this HEAD while preparing the package. The migration
anchors include world/player/height-field code and the live engine. The previous
inspection also covered terrain generation/cuts, canopy/forest-floor and tree
submission, shaders, atmosphere, native replay/client, and fixed-grid hydrology.

Pinned source links:

- https://github.com/seris10/yellowstone/blob/c2b4c7923a6eeed61e2feca3946555826849ec67/yellowstone_midway/scripts/world.gd
- https://github.com/seris10/yellowstone/blob/c2b4c7923a6eeed61e2feca3946555826849ec67/yellowstone_midway/scripts/player.gd
- https://github.com/seris10/yellowstone/blob/c2b4c7923a6eeed61e2feca3946555826849ec67/yellowstone_midway/scripts/height_field.gd
- https://github.com/seris10/yellowstone/blob/c2b4c7923a6eeed61e2feca3946555826849ec67/yellowstone_midway/scripts/core_terrain.gd
- https://github.com/seris10/yellowstone/blob/c2b4c7923a6eeed61e2feca3946555826849ec67/yellowstone_midway/scripts/tree_submission.gd
- https://github.com/seris10/yellowstone/blob/c2b4c7923a6eeed61e2feca3946555826849ec67/yellowstone_midway/scripts/canopy_surface.gd
- https://github.com/seris10/yellowstone/blob/c2b4c7923a6eeed61e2feca3946555826849ec67/yellowstone_midway/shaders/ground_surface.gdshaderinc
- https://github.com/seris10/yellowstone/blob/c2b4c7923a6eeed61e2feca3946555826849ec67/yellowstone_python/yellowstone_python/service/live/engine.py
- https://github.com/seris10/yellowstone/blob/c2b4c7923a6eeed61e2feca3946555826849ec67/yellowstone_python/yellowstone_python/river/river_world.py
- https://github.com/seris10/yellowstone/blob/c2b4c7923a6eeed61e2feca3946555826849ec67/yellowstone_python/yellowstone_python/land/overland_flow.py

## Engine references checked against the 4.5 branch

**Thread safety.** Active scene-tree mutation and GPU-facing work require care.
The package confines worker tasks to private CPU arrays and commits resources on
main/physics threads. This is a conservative implementation choice, not a claim that
all server APIs are unusable from threads.
https://docs.godotengine.org/en/4.5/tutorials/performance/thread_safe_apis.html

**Worker task lifecycle.** Completed/cancelled jobs are eventually waited/joined so
engine task resources can be released. No blocking wait occurs in normal frames
until `is_task_completed` is true; shutdown waits for remaining work.
https://docs.godotengine.org/en/4.5/classes/class_workerthreadpool.html

**Large coordinates.** Keep absolute geospatial values in double scalars and small
local vectors in the renderer; validate origin shifting across physics and materials.
https://docs.godotengine.org/en/4.5/tutorials/physics/large_world_coordinates.html

**Heightfield collision API.** Leaf collision uses HeightMapShape3D with explicit
width/depth, y values and horizontal spacing. Actual diagonal/contact equivalence
still requires the supplied local physics acceptance tests.
https://docs.godotengine.org/en/4.5/classes/class_heightmapshape3d.html

**MultiMesh.** Batch-level culling motivates regional batches rather than one enormous
instance set. The 4.5 tutorial itself has an outdated-content warning; validate
concrete APIs against the engine rather than assuming every tutorial detail is current.
https://docs.godotengine.org/en/4.5/tutorials/performance/using_multimesh.html

**Occlusion.** Godot's scene occlusion and the package's preloading/demand heuristic
operate at different stages. The built-in system does not itself decide which source
pages or numerical states to prepare. Origin-shifted occluders can incur rebuild costs;
profile any future procedural occluder path instead of adding it without measurement.
https://docs.godotengine.org/en/4.5/tutorials/3d/occlusion_culling.html

## Numerical refinement reference

Clawpack's AMR algorithm overview describes nested-grid and time-refinement concepts.
The package supplies transfer/accounting helpers only, not AMRClaw, GeoClaw, flux
refluxing or a validated moving-domain multiphysics implementation.
https://www.clawpack.org/amr_algorithm.html

All budgets, tile dimensions, lookahead durations, test-fixture parameters and visual
error thresholds in this package are proposed engineering settings or illustrative
values, not measured Yellowstone parameters or demonstrated hardware performance.
