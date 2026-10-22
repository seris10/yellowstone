# Park streaming overlook deck ledger

Specification: `fixes/fixes-66-park-streaming-overlook-deck.md`.

Baseline ledger written at document creation with every row `missing`;
rows updated with the implementation and its evidence.

| Item | Verdict | Implementation and evidence |
|---|---|---|
| Missing overlook deck in streamed mode | implemented | Baseline (headless walker probe and `walker_route_benchmark.gd -- --matrix`): streamed overlook anchor floor 47.786 m against 48.015 m baked; walking toward the boardwalk, the streamed first wall was the trunk collider of `census_lidar_0784_1581` (`Tile_core_0_8_20/StreamedVegetation`) 8.86 m from the anchor, the baked first wall an `OverlookDeck` rail at 1.92 m. `scripts/overlook_deck.gd` builds the deck; `bake_world.gd` `make_overlook()` calls it with the bake materials and `scene_root` ownership; `world.gd` `_boot_streamed_world()` builds it under `StreamedStructures` registered with the park frame, from `height_field.sample()` (master raster) and the saved deck, boardwalk and timber materials. Builder parity against a verbatim copy of the previous `make_overlook()`: 61/61 nodes identical (transforms, box sizes, ramp arrays, material paths, collision faces, ownership). After: streamed overlook floor 48.0149 m in the smoke, equal to baked; streamed first wall `StreamedStructures/OverlookDeck` rail at 1.92 m, equal to baked. `verification_receipt.gd` lists the builder as a bake input; `validate_multimesh.gd` ok with the receipt refreshed (1211770/1211770). |

Gates after implementation (Godot 4.5.1 headless): walker matrix baked 0
failed and streamed 0 failed; legacy and streamed smoke `SMOKE ok=true`;
`stream_midway_check.gd` 3970/0 (run before the builder, which it does not
load); `check_comment_style.py` and the prose pattern checker clean on
touched files. The baked scene was not rebuilt.
