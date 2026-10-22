# Renderer spatial contracts ledger

Specification: `fixes/fixes-60-renderer-spatial-contracts.md`.

| Item | Verdict | Evidence |
|---|---|---|
| Core river bed clearance | implemented | `scripts/core_terrain.gd:344` applies the authored bed to the shared height grid. `tests/river_bed_clearance.gd` verifies collision data and saved render stations: 0/93 mainline and 0/49 outflow stations buried near the bridge; minimum clearances 0.546 m and 0.403 m. Source rasters remain unchanged. |
| River centerline coverage | implemented | `tools/bake_world.gd:366` retains the mapped center while compensating the opposite bank width. `tests/renderer_repairs.gd` samples the upstream source centerline at 0.1 m intervals and checks winding across all 16 reaches. |
| Geochemistry coordinates | implemented | `scripts/scientific_overlays.gd:126` joins sidecar cell identities to published replay positions. All 92 displayed markers match their published positions within 0.0001 m. |
| Distant canopy exclusion | implemented | `scripts/canopy_surface.gd:520` clears display cover and native coverage pixels for excluded cells after raw-source validation. All 658 excluded cells and their 5513 previously covered pixels clear; original mask bytes retain their hash. |
| Junction failure gate | implemented | `tools/validate_river_junctions.gd:32` enumerates expected source joins and measures both saved reaches. The 100 m displacement control retains all expected joins and produces failures. Saved bank widths replace receipt-width assertions. |
| Spatial bank height | implemented | `scripts/river_terrain.gd:70` builds a per-location stage field on the existing 4 m grid with 64 m support. `scripts/world.gd:1408` binds the field through the geographic frame. Fixtures verify stage variation, bounded support, thermal exclusion, and origin rebasing. |
| MultiMesh and smoke gates | implemented | `tools/validate_multimesh.gd:240` validates part-specific tree transforms, canopy deformation, forest-floor identities, and steam. All 1211770 slots across 26934 resources pass. One-meter corruption fails for all five tested families. `scripts/world.gd:1492` returns nonzero for failed smoke assertions; source hashes reject stale receipts. A forced receipt rejection produces exit 1. |
| Native water depth | implemented | `project.godot:253` disables MSAA and enables FXAA for finite depth reads under Godot 4.5.1 Mobile. `tests/water_depth_native.gd` measures 0.8465 m against the fixture's 0.8484 m ray column and verifies visible river opacity. Native bridge and mouth captures show connected water. |

Python verification: 2173 core tests passed with 14 optional skips, and 121
world-dependent tests passed in a separate interpreter. Fresh illustrative
build `ac2390aa7d40` reports checks passed; claims remain unaccepted.
Top-level provenance audit passes 47 files. Direct build audit retains 55
schema/status findings across 53 files; this broader artifact-contract debt
is unchanged. Frozen bridge captures disable physics; the separate native control run
passes 35 assertions with physics enabled. Five vegetation-tool tests pass.
The focused spatial suite passes 801 assertions. Style checks report zero
findings on the changed code, regression scripts, and spatial-contract
specification and ledger.
