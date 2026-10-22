# Park streaming vegetation build cost ledger

Specification: `fixes/fixes-65-park-streaming-vegetation-build-cost.md`.

Baseline ledger written at document creation with every row `missing`;
rows updated with the implementation and its evidence. All timings are
headless dummy-renderer timings on Godot 4.5.1.

| Item | Verdict | Implementation and evidence |
|---|---|---|
| Cold shared-asset load inside the first tile build | implemented | Baseline stream check: pager `build_ms_max` 17844.3 ms (first build), `build_ms_total` 25934.5 ms over 72 tiles. Cold probe: `CanopySurface.window_source()` 18455.6 ms, `load_billboard_batch` 527-991 ms per archetype, metadata 478 ms. `vegetation_pager.gd` now prepares during the boot hold: worker tasks run `CanopySurface.prepare_window_data()` and `Lodgepole.read_cutout_image()` per archetype; the main thread installs one asset group per frame through `Lodgepole.stage_cutout_images()`, `TileVegetation.prewarm_form()`/`prewarm_ground_cover()`, `ForestFloor.prewarm()`, `CanopySurface.install_window_source()` and `prewarm_supports()`. `world.gd` releases the hold when `can_enter()` and `park_vegetation.is_settled()` both hold; the status line names the vegetation wait; the streamed smoke asserts settled, no error and built tiles. After: `prepare_ms` 2431-2916 ms in the stream check and 3540-7116 ms in the streamed smoke, `prepare_step_ms_max` 71.5-83.7 ms. Background glTF loading through `ResourceLoader.load_threaded_request` was tried and crashed the stream check (SIGSEGV at `MultiMeshInstance3D.multimesh` in `_build_clusters`); without it the same run passed, so mesh scenes load on the main thread inside the install steps. |
| Canopy preparation loops | implemented | `read_source_data()` and `_prepare_surface()` use typed locals and a kernel table computed with the original expression. SHA-256 prefixes of corner upper/lower heights, normals, cover fraction, cell mask, mask and support images are identical before and after (`589b9993`, `a9309a93`, `4e2a98b9`, `95baf402`, `99d69339`, `fa45d1a5`, `b4c304a2`); read plus smoothing 13240 ms before, 5003 ms after. |
| Per-tile canopy cluster scan | implemented | `_cluster_batches()` scans the tile window only, in row-major window order; the full-grid filter visited 409,600 cells per tile. Steady builds fell from about 114 ms to about 12 ms per tile before the worker split. |
| Main-thread instance math | implemented | `PlanJob` in `vegetation_pager.gd` runs `TileVegetation.plan_tile()`, `CanopySurface.plan_window()` and `ForestFloor.plan_window()` on the worker pool (`max_plans_in_flight` 2) from the terrain job's prefetched records and a copy of the tile heights; `install_tile()`, `install_window()` and `_install_bin()` create resources on the main thread, one tile per frame. Retired tiles move their pending plan to an orphan list that is waited and dropped. Stream check after: main-thread `build_ms_max` 2.0-3.0 ms, `build_ms_total` 45-47 ms over 91-93 tiles; worker `plan_ms_max` 36-49 ms; streamed smoke `build_ms_max` 6.3-8.7 ms. Byte identity: per-tile fingerprints of 60 resident leaf tiles at three stops equal the `fixes-64` code (`60/60`). |
| Bake-path canopy clusters | implemented | Baseline: the branch `_build_clusters()` broke out of the LOD mesh loop once `meshes` held one entry, so `CanopySurface.build()` raised `Out of bounds get index '1'` after one cluster node; the Oct 16 baked scene (built before that change) holds 918 cluster nodes. The guard now tests `shared_meshes`. In-memory bake-path fingerprints: canopy and forest floor equal the branch code with only this guard fix applied; canopy carries 1018 children against 1021 under `main`, the difference being the `fixes-63` exclusion mask. The baked scene was not rebuilt. |
| Forest-floor snag materials | implemented | Preparation runs `ForestFloor.prewarm()` before `TileVegetation.prewarm_form("snag")`; floor snags keep `StandardMaterial3D`, matching `authored_world.tscn` (`snag_woody_2_1_-3_Bole_0` uses `StandardMaterial3D_53e38`). Binding the tree form first gave `tree_bark.gdshader` on one of 60 fingerprinted tiles. |

Gates after implementation (Godot 4.5.1 headless): `stream_midway_check.gd`
0 failures (3976 and 3977 checks over two runs), `ground_rebase_check.gd`
272/0, `run_tests.gd` 10/0, `field_codec_check.gd` 9/0;
`validate_canopy_surface.gd` ok (5118 checks); `validate_multimesh.gd` ok,
receipt refreshed for the new script hashes (1211770/1211770 slots);
legacy and streamed smoke `SMOKE ok=true`; `pytest tests/park_runtime`
115 passed; `check_comment_style.py` and the prose pattern checker clean on
touched files. Not tested: `validate_canopy_attachments.gd` requires a
real renderer and exits 2 headless; visible-renderer frame times.
