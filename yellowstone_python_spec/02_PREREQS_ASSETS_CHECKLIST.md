# Prereqs + Asset Gaps — Yellowstone Python Fast Path

## A. Prerequisites (get unblocked in < 1 hour)

### A1. Environment
- Python 3.10+ (contract tooling assumes it). Reuse `yellowstone_midway/tools/requirements.txt`:
  `numpy>=1.26,<3, scipy>=1.12,<2, Pillow>=10,<13, shapely>=2,<3, rasterio>=1.3,<2, pyproj>=3.6,<4`
- Add for new package: `pyyaml, pytest, streamlit (M10 only, optional), matplotlib (viz only)`.
- Godot 4.5.1, GL Compatibility baseline (project already runs F5 from `yellowstone_midway/project.godot`). No server, no network.
- Disk: build inputs already vendored in `references/` + `data/`; new `derived/` is small (JSON + PNG). Keep `integration/yellowstone/` sidecars + `derived/<build-id>/` OUTSIDE `yellowstone_midway/` until publish (per `INTEGRATION_ORDER.md` M4).

### A2. Files to have open (all exist — no downloads needed)
- Runtime hooks: `yellowstone_midway/scripts/ecosystem.gd`, `scripts/world.gd` (`update_environment` 0.3 s), `scripts/wildlife_actor.gd`, `scripts/height_field.gd`, `scripts/map_view.gd`.
- Drop-in target: `yellowstone_midway/data/ecosystem.json` (schema v1: `weather, river_reaches[6], patches[3], wildlife[12]`).
- Frozen inputs: `data/world.json` (routes/rivers/pools), `data/terrain.f32` (1025²), `data/placements.json` (36,225 — READ ONLY), `placement_overrides.json`, `botanical_placements.json`, `species_catalogue.json` (56), `assets/textures/habitat_mask.png`, `shaders/{terrain,water,thermal_apron,foliage,steam,boardwalk,trail}.gdshader`.
- Research: `Yellowstone_Research_and_Future_Directions.md` Part 1 §5 + `docs/ecology-research.md` §§5–6 + `docs/geography-research.md` + `Scientific_World_Geography_Session_2/{GEOSPATIAL_CONTRACT.md, PHYSICAL_FIELD_CATALOG.json, validate_geography.py}`.
- Validators to reuse: `tools/validate_world.py`, `tools/validate_ecology.gd`, `tools/validate_walk.gd`, `docs/VALIDATION.md` (heat residual format `~2.55e-10`, channel QA `references/channel_support_qa.json`).

### A3. Conventions (avoid the known failure modes)
- Origin: `x=E−512952.5950985841, y=H−2200.0, z=4930199.044097667−N`. Never assign raw UTM to float32 transform. Index with `floor`, 1-sample halo, diagonal `10-01`, GDAL centre `(0.5,0.5)`.
- Units on every interface; dimensionless indices labeled as such. `null` = missing (no fill, no non-finite). Source epoch (NAIP 2022-07-19) ≠ retrieval date. Excelsior 0.26 m³/s @ 62 °C is illustrative river-entry, not vent measurement.
- One clock owner; physical seconds for transport/biomass, `day_rate` phases light only. Conserve + report fluxes separately.

## B. Missing-asset checklist (priority order — biggest visibility per effort)

Each item: what to get, why it matters for Python visibility, minimal acceptable form, license note.

### P0 — unblocks the core demo (get or stub this week)
1. **Pool-shell + rim meshes (Grand Prismatic pool_1034_0, Excelsior pool_1030_0).** Today: flat terrain cut. Need: crater wall, shallow shelf, wetted rim, outflow lip as separate meshes preserving mapped outline. Accept: hand-sculpted low-poly shells + `pool_shells.json` from M03. Without this, M03 color work sits on wrong geometry.
2. **Thermal-apron eligibility texture.** Need: hydrothermal-ground vs vegetation mask at ~1 m (from USGS thermal polygons + NAIP detail) as `apron_mask.png`. Blocks correct exclusion (forest crossing bright patch = masking failure).
3. **Species-correct wildlife rigs × 5 (bison, Canada goose, American dipper, raven, rainbow/brown trout).** Today: articulated primitive proxies with correct metre dimensions but placeholder look. Accept: any free-to-personal-use rigged FBX/GLB at true scale + walk/graze/float/hold clips; keep existing `path_xz / river_id indices / lateral_offset_m` interface. Expands M05–M07 enormously.
4. **River cross-section set (Firehole 3 + Excelsior outflow 1).** Need: bank mesh + per-reach depth/velocity to replace uniform-width assumption (Prompt 3). Accept: 4 authored profiles + `depth_m, velocity_mps` per reach in `river_state.json`.

### P1 — makes simulation legible at walking distance
5. **Lodgepole-tuned pine set (replaces generic Poly Haven pine).** Today: reduced Poly Haven pine (CC0, generic). Need: lodgepole silhouette/color/thin-bark variant, 3 LODs + billboard, same MultiMesh slots. Without it M04 proposals look wrong at 2 m.
6. **Sedge/willow/lupine upgrades (beyond 30 demo clumps).** Today: 30 genus/guild clumps in `botanical_details.tscn`. Need: 2–3 variants per guild + snag/down-wood pieces for recruitment/mortality storytelling.
7. **Insect swarm + dipper perch stones.** Today: 8 tiny proxies at one offset. Need: GPU point/quad swarm driven by `insect_activity`, 2–3 perch stones with verified placement. Cheap, high life.
8. **Steam upgrade (billboard quads → soft volumetric-lite).** Today: quads with `density` from `steam_visibility`. Need: height-faded, wind-advected shader reading shared wind vector. M02 payoff depends on this.
9. **Boardwalk/overlook microdetail.** Need: planks, rails, deck edge, pool-rim crust fragments, drainage fingers (sculpted from `midway_orthophoto_detail.jpg`). Makes M03 shells believable at 0–5 m.

### P2 — seasons, sound, interpretation (do after P0/P1 move)
10. **Snow/phenology overlays.** Need: snow-depth shader mask (thermal holes) + 2 seasonal ground-detail textures + bare-branch/needle tint variants. For M08.
11. **Positional audio set.** Have: 4 NPS public-domain clips (retain location, credit NPS; Geyser Hill ≠ Midway — label as adapted). Need: Firehole whitewater bed, boardwalk footsteps, overlook wind shelter vs clearing, waterfall for future Fairy Falls. Keep loop seams + chorus-time labeling honest.
12. **Field-notes / binocular overlay art.** Need: `pool_cross_section.png`, `plume_map.png`, `refuge_map.png`, `suitability_*.png` framed as notebook plates (Prompt 5 without progression/XP). This is how ahead-of-render Python becomes visible before shaders catch up.
13. **Fairy Falls extension pack (deferred).** Cliff mesh, falls ribbon, spray + audio region, true-trail extension. Do NOT start until Milestone A walk (overlook-to-basin) passes.

### License hygiene (from docs/asset-research.md + THIRD_PARTY.md)
- Poly Haven geometry/textures: CC0 (page renders ≠ CC0 — don't scrape site). Keep derivative + attribution in manifest.
- NPS audio/photos: public domain, credit NPS, retain recording location, don't relabel.
- NAIP 2022: public domain via USGS; credit `USDA NAIP 2022, distributed by USGS The National Map`.
- Every new asset: add to `data/asset_manifest.json` with source URL, license, date, author, derivative note. No asset without provenance enters `handcrafted_details.tscn`.

## C. 2-week expedite checklist (copy-paste)

- [ ] Day 1: create `yellowstone_python/` + M00 + M01(6-reach)+M02; publish variant `ecosystem.json`; F5 walk Firehole bridge, confirm steam + trout respond.
- [ ] Day 2–3: M05+M06; insect/bird/fish traces logged; `CHECKS.json` green.
- [ ] Day 4–5: M04 patches-only + M07 paths; `grazer_tracks.png` + exclusion test.
- [ ] Week 2: M03 shells + apron + P0 assets 1–2 commissioned; notebook plates wired to I/M keys; M08 snow + M10 study sliders demo.
- [ ] Throughout: every publish bumps `build_id`, updates `parameter_provenance`, appends before/after eye-height captures (overlook, boardwalk, bridge, meadow) + deviation ledger.
