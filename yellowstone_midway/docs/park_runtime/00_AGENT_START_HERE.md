# Yellowstone park-scale runtime: agent entry point

This is a source-and-migration package, not a request to optimize only the current
Midway scene. Target repository: `seris10/yellowstone`. Inspected baseline:
`c2b4c7923a6eeed61e2feca3946555826849ec67`. Target engine: Godot **4.5.1**, not the
latest stable documentation branch.

## First instruction

Read `docs/00_ARCHITECTURE_CONTRACT.md`, then `docs/01_CURRENT_FILE_EDITS.md`.
Run the read-only baseline check. Inspect any changed local files before editing.
Do not discard uncommitted work, silently reset the repository, or remove existing
scientific/visual tests to make the migration pass.

```sh
python /path/to/package/tools/verify_baseline.py --repo /path/to/yellowstone
python /path/to/package/tools/install_overlay.py --repo /path/to/yellowstone
# Review the dry-run list; this next command installs new files only.
python /path/to/package/tools/install_overlay.py --repo /path/to/yellowstone --apply
```

A baseline mismatch means rebase the edit instructions against the current source.
It never calls for rolling the repository back. The checker hashes four integration
anchors, not every project file. Read every file before modifying it.

## Required sequence

1. Run the supplied Python tests and the isolated Godot fixture. Fix any Godot
   compile/API errors first and record the exact engine/renderer. The package build
   environment did not contain Godot, so headless compilation is an acceptance gate.
2. Add opt-in project settings, keep the existing main scene unchanged, and run the
   streamed terrain fixture using Midway source data. Establish frame-time traces.
3. Integrate streamed terrain with the actual world and movement guard. Preserve
   routes, water boundaries, the 1 m core height authority, overlays and field notes.
   Do not promote an incomplete stripped-down scene as the finished application.
4. Integrate the existing scientific engine through `LegacyLiveDomain`, with its
   own worker disabled. Keep one clock owner. Finish the native checkpoint serializer
   before enabling durable persistence for this adapter.
5. Convert vegetation, wildlife and spatial materials one layer at a time. Complete
   the parity and conservation gates in `docs/03_ACCEPTANCE.md` before changing the
   default world mode.

Work in reviewable commits. Each commit states: affected contracts, exact tests,
measured performance, known regressions and remaining acceptance gates. Do not
promise a speedup based solely on architectural similarity to another engine.

## Definition of completion

Deliver source diffs, test reports, baseline/streamed comparison traces, and an
updated implementation-status table. `streaming_enabled=true` is not completion.
The scene must preserve scientific state across movement, unload/reload, rebase,
intervention, pause/resume, time acceleration and service restart.

## Explicitly prohibited substitutions

Do not replace real data with the included synthetic ridge or reservoir examples.
Do not replace the existing river solver with `ReservoirNetwork` to simplify
integration. Do not call a temporary diagnostic material visual parity. Do not
reinterpret the offline elevation index as permission to bake all future physical
states or a single enormous park scene. Do not let camera visibility determine
whether an upstream catchment, weather field or tracked animal continues to exist.
