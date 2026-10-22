# Renderer spatial contracts

## Scope

Repair renderer spatial geometry and the MultiMesh verification contract. Preserve published scientific inputs,
simulation parameters, claim statuses, and unrelated working-tree edits.

## Acceptance

- Core channel beds clear the saved river surfaces around the bridge.
  Render and collision geometry share the authored bed correction.
- Curvature compensation preserves mapped centerline coverage and triangle
  winding. Width checks measure saved geometry.
- Geochemistry markers use published replay cell positions.
- Display exclusions clear cluster cells and distant coverage pixels.
- Expected junctions fail validation when displaced beyond tolerance.
- Bank height depends on surface coordinates and survives origin rebasing.
- MultiMesh checks cover tree LOD parts, canopy deformation, forest-floor
  records, and steam. Serialized corruption produces nonzero failures.
- Smoke assertions reject failed or stale verification receipts.
- Focused regressions, native bridge captures, Python tests, a fresh build,
  provenance commands, and style gates retain explicit coverage limits.

## Authored display values

The bed uses the existing 0.53 m wide-reach and 0.45 m narrow-reach render
depths. Bank blending retains 1.5 m from the core authoring metadata. The
bank-height lookup retains the 4 m geographic grid and 64 m support radius.
These choices carry authored display provenance and unknown uncertainty.
Frozen elevation rasters and scientific model volumes remain unchanged.

## Depth-buffer compatibility

The native Godot 4.5.1 Mobile renderer returns nonfinite sampled depth with
MSAA enabled on the tested Metal device. A controlled 0.53 m water plane
reproduces the failure; the same plane returns finite depth with MSAA off.
The renderer uses FXAA with MSAA disabled so river absorption and shoreline
opacity consume valid depth. The Godot depth-resolve implementation targets
4.6: https://github.com/godotengine/godot/pull/108636.
