# Packaging and input contract repairs

## Scope

Follow-up items recorded during the `fixes-58` batch 6 verification
(`fixes/progress.md`, batch 6 section). The runtime loads
`scenes/authored_world.scn` when present (244 MB binary, 12-13 s headless
load) and falls back to the `.tscn` (384 MB text, 44-46 s). Three contract
gaps remain around that change and the gamepad layer scheme. Retain the
public-export exclusion list's intent, the demo package contents, the
verification receipt coverage, and every keyboard binding.

## Findings and implementation

- Public export carries the binary scene. `tools/export_public.py:28`
  excludes only `yellowstone_midway/scenes/authored_world.tscn`. When a
  local bake has produced `authored_world.scn`, the public export includes
  244 MB of binary scene that the exclusion list means to keep local. Add
  the `.scn` to `EXCLUDED_PATHS` or generalize the exclusion to
  `authored_world.*`. Extend the export tests with a fixture tree that
  contains both scene files and asserts both stay out.
- Demo packaging accounts for only the text scene.
  `yellowstone_python/tools/package_demo.py:90` requires
  `scenes/authored_world.tscn`, and line 41 packs `*.tscn` only. A package
  built after a binary bake either ships both scenes (near double the
  bytes) or, once the text scene is excluded from somewhere, ships a
  runtime that prefers a missing `.scn`. Decide the package contract: pack
  exactly one scene format (the `.scn`, matching the runtime preference),
  require its presence, and update the requirement check, the packing
  glob, and the package tests together.
- Verification receipt misses the loaded file.
  `yellowstone_midway/scripts/verification_receipt.gd:6-7` hashes
  `res://scenes/authored_world.tscn` in `INPUTS`, but the runtime loads
  the `.scn` when present. The receipt then certifies a file the game did
  not read. Add the `.scn` to `INPUTS` when it exists (both files come
  from the same `PackedScene` in one bake call), or hash whichever file
  the loader resolves; state the chosen rule in the receipt output.
- Gamepad bindings dead under the layer scheme. `project.godot` binds
  `conditions` to joypad button 10 and `step_frame` to button 9, but
  `input_help.gd` `PAD_LAYERS` assigns neither action a layer, so
  `pressed()` requires layer 0 while pressing a shoulder button raises the
  layer to 1 or 2. Both actions are unreachable on a pad. Either assign
  both actions explicit layers in `PAD_LAYERS` (so they need the matching
  shoulder combination and the curated help page shows it), or move them
  to buttons free in layer 0. The curated controls page reads bindings
  live, so it follows whichever rule lands; verify the pad column shows
  the corrected combination.

## Verification

- `python3 -m pytest -q` stays green; new export and package tests pass.
- `python3 tools/check_comment_style.py` and the prose pattern checker
  clean on touched files.
- Export fixture: a tree containing both scene files exports neither.
- Package fixture: the demo package contains exactly one authored scene,
  matching the runtime preference, and its receipt validates.
- Receipt run: `verification_receipt.gd` covers the file the loader
  actually resolves, in both `.scn`-present and fallback states.
- Pad regression: `conditions` and `step_frame` reachable under the
  documented layer rule; the F1 page displays the same rule.

## Sources

- `fixes/progress.md`, `fixes-58` batch 6 section (open follow-ups).
- `yellowstone_midway/scripts/world.gd` loader (`authored_world.scn`
  preference with `.tscn` fallback).

Packaging contents remain a product decision recorded here as the chosen
contract; no scientific claim changes state under this document.
