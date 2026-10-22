# Park streaming overlook deck

## Scope

A structure gap in the opt-in park streaming runtime found while executing
the regression matrix of `docs/park_runtime/03_ACCEPTANCE.md` (`fixes-63`
ledger, regression matrix execution). The default world mode does not
change; the promotion gate stays closed. No scientific claim changes state.

## Findings and implementation

- Missing overlook deck in streamed mode. `tools/bake_world.gd`
  `make_overlook()` builds the Grand Prismatic overlook viewing platform,
  its entry ramp, timber posts and rails, each with trimesh collision,
  outside the route and feature pipeline. The streamed boot builds no
  equivalent, so the walker at the overlook anchor stands on terrain
  (47.79 m against 48.00 m on the baked deck) and can walk off the open
  hillside. The streamed walker benchmark run recorded this as a stuck leg
  at a streamed StaticBody3D near the deck exit. A headless walker probe
  identifies that body as the trunk collider of lidar census pine
  `census_lidar_0784_1581` (`placement_overrides.json`, position
  -247.75, 43.19, 150.75), 8.9 m downslope of the anchor. The same
  collider exists in the baked scene; there the deck rail stops the walker
  1.9 m from the anchor. Implementation: `scripts/overlook_deck.gd` holds
  the deck builder; `bake_world.gd` `make_overlook()` calls it with the
  bake materials and scene ownership, and `world.gd`
  `_boot_streamed_world()` calls it under a `StreamedStructures` node
  registered with the park frame, using the saved deck, boardwalk and
  timber materials and the master-raster heights the bake samples.
  `verification_receipt.gd` lists the builder among the bake inputs.

## Verification

- Builder parity: the shared builder and a verbatim copy of the previous
  `make_overlook()` produce identical node trees (names, transforms, mesh
  sizes and arrays, material paths, collision faces, ownership).
- Walker matrix case `walker_route_benchmark.gd -- --matrix`: walking from
  the overlook anchor toward the boardwalk, the first wall contact is an
  `OverlookDeck` member within 5 m of the anchor in both modes.
- Legacy and streamed smoke, `validate_multimesh.gd` with a refreshed
  receipt, `stream_midway_check.gd`, `check_comment_style.py` and the
  prose pattern checker on touched files.

## Sources

- `yellowstone_midway/tools/bake_world.gd` (`make_overlook`, `add_geometry`,
  `beam_between`, `ribbon`), `scripts/overlook_deck.gd`, `scripts/world.gd`,
  `scripts/verification_receipt.gd`.
- `yellowstone_midway/scenes/authored_world.tscn` (`OverlookDeck`).
- `evidence/park-streaming-benchmark-walker.json` (streamed segment 1).
