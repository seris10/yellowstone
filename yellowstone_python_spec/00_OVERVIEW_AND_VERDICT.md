# Yellowstone Python — Overview, Verdict, and How to Expedite

Date: 2026-10-09. Scope: `yellowstone_midway` only.
Goal: walkable world where Python modeling is visible, even if much of the Python runs ahead of the renderer.

## 1. Verdict: stick with Yellowstone

Surveyed 8 Godot builds in `/Users/kreed/Downloads/` (see `shared-world-architecture/PROJECT_INVENTORY.md`):

| Build | Why not primary |
|---|---|
| `mojave_explorer/` | Best *existing* Python/sim (`sim.advance`, save schema, 80-taxa catalogue, 24 districts). But desert scrub is less visually provocative than geysers + river + forest. Use as code pattern reference, not stage. |
| `Mono_Basin_Godot/` + `GrantMono/` | Strong hydrology/limnology, 279k placements, 303 wildlife ranges. Bigger, heavier, needs LOD/origin work before walkable payoff. |
| `Sierra_Field_Atlas/` | Largest (138k placements, 11 regions) but region-scoped IDs repeat; not continuous geography. |
| `colorado_monument/` (Rim Rock), `Rim_Wash/` | Great canyon stratigraphy; datum/road-grade residuals + two overlapping implementations cause confusion. |
| `Seabright_to_Davenport/` | Best streaming reference (threaded, 6 pending/2 attach) but 187k anonymous placements need ID enrollment first; coastal, not thermal. |
| `Groundwork 2/` | Materials compiler only, not a world. |
| `yellowstone_midway/` | **Pick this.** 4,096 m square, EPSG:32612, baked + runnable in Godot 4.5.1 (F5), fixed IDs, separated source/draft/override/manual layers, 36,225 placements, 12 wildlife proxies, 6-reach river + 3 patch ecosystem already hot-reloadable via `data/ecosystem.json`. Thermal + river + forest + meadow in one view = maximum visible science per hour. |

This matches `shared-world-architecture/INTEGRATION_ORDER.md` M6: dual pilots Mojave + Yellowstone. You are doing the Yellowstone pilot.

## 2. The expedite strategy (what makes this faster than the project plan)

The project plan (`Yellowstone_Research_and_Future_Directions.md` Milestones A–D, Prompts 1–12) assumes art-first, calibration-first, tile-architecture-first. For your goal — *Python ahead of render, walk around and see it* — invert that:

1. **Don't rebuild terrain, don't touch Godot scenes first.** `tools/prepare_world.py` (542 lines) + `bake_world.gd` already baked 256 tiles from `references/dem.tif + orthophoto.jpg + yell_*_utm12.json`. Reuse. Python writes *sidecars* that the existing runtime already reads.
2. **Phase 0 (hours): drop-in numbers.** Existing `scripts/ecosystem.gd::configure()` + `step(1s)` + `scripts/world.gd::update_environment()` (every 0.3 s) already map `ecosystem.json → wind/foliage shader, steam density, river shader temperature_c, sun/sky/fog, fish/insect activity, wildlife FSM`. Any Python that writes a valid `ecosystem.json` is instantly visible with **zero GDScript changes**. This is the fastest loop.
3. **Phase 1 (days): offline advisers + visualizers.** Python proposes placements, plumes, snow, pool colors as PNG/JSON overlays + optional file-watch bridge. Player walks, presses M (map) / I (field notes) / Esc (starts) and sees them.
4. **Phase 2 (later): small GDScript shims only where proven.** E.g. read a new `derived/*.json` for pool-ring color or snow mask. Never block modeling on art.
5. **Label everything illustrative.** All coefficients are chosen, not calibrated (no bathymetry, no dated T/Q series, no soil Ksat — see `01_PYTHON_BUILD_SPEC.md` §8). Keep `parameter_provenance` in every output.

## 3. What the three docs are

- This file: verdict + fast path.
- `01_PYTHON_BUILD_SPEC.md`: the 11 Python modules to write, each with inputs (exact existing files), outputs (exact sidecar + Godot attach point), equations, acceptance test. This is the "generate all the python" work order.
- `02_PREREQS_ASSETS_CHECKLIST.md`: environment prerequisites + the minimal asset shopping list that expands visibility most, in priority order. Hand this to art/acquisition.

## 4. Research you actually have (so you don't re-hunt)

- Usable now: 4096 m / 1025² @ 4 m DEM (`references/terrain_source.f32` absolute, `data/terrain.f32` authored local); origin E0=512952.5950985841, N0=4930199.044097667, H0=2200 NAVD88; mapping `x=E-E0, y=H-2200, z=N0-N`; NAIP 2022-07-19 (2 m export, 0.625 m detail core); 22 road / 26 trail / 27 river / 15 lake features; Firehole flows north; Excelsior >4,000 gpm ≈ 0.252 m³/s (order-magnitude ref, used as 0.26 illustrative); 56-entry `data/species_catalogue.json`; 16 habitat IDs; `PHYSICAL_FIELD_CATALOG.json` (22 fields) + `GEOSPATIAL_CONTRACT.md` numerics (floor-indexing, 1-sample halo, diagonal `10-01`).
- In `/Users/kreed/Downloads/Recovered_Research_Reports/`: `Yellowstone_Research_and_Future_Directions.md` (= same as root copy, Part 1 §5 equations), `ECOLOGY_RESEARCH.md` (Osa pattern, reusable tick/structure), `Mojave_*` (best `sim.advance` + save pattern to copy), `Mono_Basin_*` (lake hydrology pattern).
- In `/Users/kreed/Downloads/Scientific_World_Geography_Session_2/`: contracts + `validate_geography.py` (47 tests) — reuse validators, don't reinvent indexing/interpolation.
- Missing (do NOT block on): pool bathymetry, branch discharges, dated river T/Q, soil depth/Ksat/conductivity, hydroperiod, bed temp/salinity layers (stay `null` per contract), snow calibration, animal counts. All new params go in `parameter_provenance` as illustrative.

## 5. Definition of done for "sufficient python"

- `yellowstone_python/` runs with one command, writes `derived/<build-id>/` without touching `yellowstone_midway/data/` until explicitly published.
- Publishing = copy validated JSON/PNG into `data/` or `assets/textures/` + F5 walk: river temps shift trout activity + steam, wind moves foliage + steam together, insects gate dipper/raven, biomass responds to grazing, pool rings recolor, snow respects thermal exclusion, study-mode sliders replay side-by-side.
- Every output carries `contract_version, world_id=yellowstone_midway, source_hashes, code_rev, units, status=illustrative`.
