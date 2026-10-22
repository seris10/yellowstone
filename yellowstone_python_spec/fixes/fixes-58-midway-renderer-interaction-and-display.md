# Midway renderer interaction and display repair

## Scope

Retain the baked world contract, published sidecar schemas, scientific
outputs, run modes and claim statuses. Repair player-facing interaction
(keys, panels, HUD), display shading (water, terrain, foliage) and authored
geometry (river junctions, railings, vegetation placement) in
`yellowstone_midway`. Source audit with quantified evidence and full fix
code: `fixes/audit-58-midway-renderer/` (main report plus water/river and
vegetation appendices). Section numbers below match that report.

Display parameters remain authored with unknown uncertainty. No scientific
claim changes state under this document.

## Implementation order

1. Study scene freeze (section 13). Critical; blocks force-quit data loss.
2. HUD, keys, field notes, map legend (sections 1, 6, 9-12). Script and
   project settings only; no re-bake.
3. Overlay feedback and groundwater publish gap (sections 2, 16.1).
4. Vegetation exclusions (section 15). Re-bake required.
5. Tree display color and crown form (sections 5, 14). Shader constants and
   impostor re-render.
6. Water shader and river geometry (sections 3, 7). Shader swap is
   runtime-only; junction and outflow repairs re-bake `authored_world.tscn`.
7. Terrain close detail (section 4). Shader-only except `water_level_m`
   plumbing.
8. Railing sweep (section 8). Re-bake.
9. Pipeline repairs (groundwater packaging, river `profile_status`
   stamping). Next build.

## Findings and implementation

- Study scene freeze (audit section 13). `scenes/study.tscn` reuses
  `scripts/world.gd`, so `Ctrl-S` re-runs the full world build and
  synchronously re-parses the 393 MB text `authored_world.tscn`
  (`world.gd:1072-1073`, `world.gd:136`). Replace the scene change with an
  in-scene study overlay (thermal probes plus simulation panel toggle), or
  remove the binding until study mode has distinct content. Full handler
  code in the audit report section 13.
- Build stamps and HUD toggles (audit sections 10, 11).
  `simulation_status_text()` (`world.gd:485-493`) prefixes build, release
  and scenario identifiers on every frame; `_python_mode_selected`
  (`world.gd:453-454`) appends `| baked Python build` to the bottom bar.
  Gate identifier detail behind the F4 perf probe and drop the bottom-bar
  suffix. Replace the boolean `photo_mode` kill-switch
  (`world.gd:1056-1058`, which also hides the menu, help, map and
  simulation panel) with a three-state cycle: full, minimal, hidden. Full
  code in audit sections 10-11.
- Menu key (audit section 12). `menu` is bound to Escape in
  `project.godot`; Escape always raises the menu and there is no
  cursor-release-only path. Rebind `menu` to P, move `plume` from P to O,
  and give Escape a mouse-capture toggle only. Update the bottom bar
  string, the menu panel text and the F1 dump in the same change. Edit
  list in audit section 12.
- Census key behavior (audit section 9). The `census` handler forces
  `map_view.visible = true` on every press and never closes the map
  (`world.gd:1080-1084`). Restrict U to the open map and surface a toast
  otherwise. Code in audit section 9.
- Field notes (audit section 1). The panel dumps raw JSON via
  `JSON.stringify(value).left(95)` (`world.gd:1335-1344`), truncating
  tokens mid-number, and opening it changes neither pause nor mouse state
  (`world.gd:1050-1052`). Replace with the notebook panel, structured
  per-sidecar digest and pause-while-open handler written in full in
  audit section 1.
- Map legend (audit section 6). `map_view.gd:73-78` draws the legend with
  width -1 (no clipping) so census suffixes bleed past the 590 px card,
  and hard-codes British `kilometre`. Clip to card width and use American
  spelling. Code in audit section 6.
- Dead overlay keys (audit section 2). Measured against release
  `8f7ed4ee574d...`: `groundwater_field.json` absent from the release (L
  inert); `overland_field.json` reports `max_depth_m` 0.0, giving a
  0.09-alpha full-map tint (J imperceptible); 0 of 276 geochemistry cells
  carry `silica_saturation_index` (G all-neutral pins); the plume quad
  covers only the 600 m Excelsior footprint (P invisible elsewhere);
  census has 0 finite `peak_exg` in 34,303 rows (U monochrome). Toggle
  return values are ignored by the caller. Wire the toast feedback and the
  data-driven help bar from audit section 2, and key geochemistry markers
  by river `id`; a first match on the duplicated name `FIREHOLE RIVER`
  (`scientific_overlays.gd:136-141`) can land on the wrong reach.
- Groundwater publish gap (audit section 16.1).
  `exporters/godot_sidecars.py:611-614` raises without a build-side
  groundwater sidecar and `publish.py:41` lists the file as optional, so
  the release shipped without it. Either publish the sidecar or remove
  the L binding and help text.
- River water shading (audit section 3). Replace
  `shaders/river_water.gdshader` with the v2 shader in
  `water_river_audit_appendix.md`: flow-aligned dual-octave normals with
  slope-scaled speed, Beer-Lambert depth color from `hint_depth_texture`
  with authored cross-section fallback, fresnel sky tint, sun glint,
  advected foam, depth-based soft shorelines. The uniform contract of
  `bake_world.gd:357-365` is preserved. Correct `channel_depth_m` from
  1.1 toward the measured 0.51-0.53 m in `configs/cross_sections.json`.
  Mobile renderer compatible; SSAO is silently off because
  `world.gd:853` gates it on `forward_plus`, so do not promise
  SSAO-dependent looks.
- River geometry at Firehole bridge (audit section 7). Route the
  Excelsior outflow through `river_ribbon()`; the trail `ribbon()` path
  used at `bake_world.gd:600` leaves a 53.5-degree self-folding kink at
  idx 65. Resolve the coplanar double surface where the outflow mouth
  lands exactly on Firehole vertex 398 (y=0.128, gap 0.00 m). Add a floor
  to the curvature clamp (`bake_world.gd:303-306`), feather junction cap
  rims, and snap junction endpoints. Full GDScript in the water appendix.
  The 34 m trench against the 22 m opaque core is resolved by the shader
  depth opacity, requiring no terrain change.
- Tributary truncation and provenance (audit sections 7, 16.2). Fairy
  Creek exits the domain 1344 m from the Firehole and White Creek 79 m
  short of the shared exit; both run parallel and never confluent, while
  `prepare_world.py:171` stamps every reach `profile_status: joined`.
  Repair the reach topology or the stamp; a joined claim requires a
  junction vertex within tolerance.
- Terrain close-range detail (audit section 4). The dominant blur term is
  `photo_weight` reaching 0.68 in the mineral basin at all camera
  distances (`ground_surface.gdshaderinc:107-108`), sourcing up to
  two-thirds of underfoot albedo from a 2 m/px photograph. Apply the
  distance gate `smoothstep(1.5, 8.0, view_dist)`, the two-octave detail
  normal (2-12 m), triplanar bank rock (replacing the planar `p.xz`
  projection that streaks on banks), height-above-water wet and stain
  bands, and the mineral AO repair. Full shader blocks and
  `terrain_materials.gd` binding changes in audit section 4; register new
  phases in `REPEAT_PHASES` so origin rebasing stays aligned. Raise
  `anisotropic_filtering_level` from 3 to 4 in `project.godot`.
- Tree display color (audit section 5). The canopy skin renders sunlit
  foliage at approximately `#2b361a` (luminance 0.193) against the
  photographic reference `#748033` (0.470): `canopy_surface.gdshader`
  base `vec3(0.12,0.17,0.08)` mixed at 88 percent. Impostor sprites are
  baked dark (`tools/render_lodgepole_impostors.py`), measured mean sRGB
  (0.19,0.26,0.14), then drawn unshaded. Apply the corrected constants,
  the ambient-fill patch for `yellowstone_atmosphere.gd` and the impostor
  emission-bake patch from the vegetation appendix. Photographic colors
  carry unknown exposure and white balance; treat the palette as a
  display target, preserving scientific outputs.
- Crown form and pale supports (audit section 14). Census crown ratios
  reach 0.08 (p10 0.35 over 23,026 add records), producing bare poles
  with tufts. Clamp display crown ratio. `canopy_surface.gdshader:103`
  assigns an sRGB-looking `vec3(0.19,0.14,0.085)` raw into linear ALBEDO,
  rendering support stems about 8x brighter than bark. Fix constants and
  clamps in the vegetation appendix.
- Vegetation exclusions (audit section 15). Authored placements are clean
  (0 violations in 63,554 records). LiDAR canopy support stems ignore
  routes, decks and pools: 321 active cells centered inside route
  corridors and 4 cells piercing the overlook deck (deck plane 48.07 m,
  stem tops 50.5-51.9 m). 527 grass override records from
  `placement_overrides.json::add` violate corridors, worst 3.59 m inside
  the Grand Loop Road centerline. Run
  `tools/apply_vegetation_exclusions.py` (full source in the vegetation
  appendix) and suppress or mask support stems inside corridors and deck
  footprints. Re-bake.
- Boardwalk railings (audit section 8). `beam_between` chains
  butt-jointed boxes aimed by `look_at` (`bake_world.gd:512-541`); bends
  leave outside gaps and inside overlaps, posts skip every other vertex
  and float past the deck edge on curves, and the lowest beam hangs 0.24
  m below the deck plane. Replace with the swept rectangular profile with
  miter-plane joints written in full in audit section 8; the bisector
  rule holds at any bend and grade. Re-bake.
- Scene serialization (audit section 16.11). `authored_world.tscn` is a
  393 MB text scene parsed at every launch. Save the baked result as
  binary `.scn` from `bake_world.gd`.
- Secondary interaction repairs (audit section 16). Toast guards for
  interventions without a live session and for the 2-hour jump at the
  replay end; separate the F1 help panel position from the field notes
  position; gate `simulation_panel` mouse capture on menu state; replace
  the raw InputMap dump with a curated controls page.

## Verification

- `python3 -m pytest -q`, a full `build`, and `audit_provenance` stay
  green; new modules ship with tests.
- Headless Godot validators (`tools/validate_baked.gd`,
  `tools/validate_core_cut.gd`, `tools/validate_multimesh.gd`,
  `tools/validate_census_map.gd`) and the `--smoke-test` anchor walk pass
  after each re-bake.
- Key remap regression: every entry in the data-driven bottom bar is
  pressed once in a live session and produces a visible effect or a
  toast; Escape never raises the menu; P raises it; O toggles the plume.
- Ctrl-S (or its replacement) leaves the session responsive; measure
  worst-frame time during the transition.
- Native Mobile/Metal captures: Firehole bridge (both banks, both
  directions), Excelsior mouth, overlook deck, trail corridor at the
  platform, steep bank at grazing angle, ground at 0.5 m eye distance.
  Compare against the retained reference photographs; record that
  photographic calibration is unmeasured.
- Vegetation exclusion receipt: zero active canopy cells and zero
  override records inside route corridors, deck footprints and pool
  rings; report counts before and after.
- River receipt: junction gaps within 1.5 m tolerance, minimum baked
  half-width per reach against authored width, no coplanar water pairs at
  the outflow mouth.
- Frame-time ABBA against the published package using fixed forcing and
  camera paths; record primitives and draw calls. The `fixes-57` median
  target (33.4 ms, p95 50 ms) remains the reference.
- Release packaging check lists `groundwater_field.json` present or the L
  binding absent; `profile_status` stamps match measured junctions.
- Comment style per `AGENTS.md` section 2; run
  `tools/check_comment_style.py` on touched files.

## Sources

- Audit report and appendices: `fixes/audit-58-midway-renderer/`.
- Godot spatial shader reference:
  https://docs.godotengine.org/en/stable/tutorials/shaders/shader_reference/spatial_shader.html
- Godot screen-reading shaders:
  https://docs.godotengine.org/en/stable/tutorials/shaders/screen-reading_shaders.html
- Godot environment and post-processing (SSR availability):
  https://docs.godotengine.org/en/stable/tutorials/3d/environment_and_post_processing.html
- Godot ProjectSettings (anisotropic filtering):
  https://docs.godotengine.org/en/stable/classes/class_projectsettings.html
- Godot shading language (sampler hints, source_color decode):
  https://docs.godotengine.org/en/stable/tutorials/shaders/shader_reference/shading_language.html
- Poly Haven texture sources: https://polyhaven.com/a/forrest_ground_03

Display palettes, crown clamps, bank bands and railing dimensions are
authored. River junction distances and texel densities are measured from
the pinned release data; photographic color targets remain uncalibrated.
Scientific claims stay `not_yet_accepted`.
